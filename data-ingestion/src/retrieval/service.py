"""
src/retrieval/service.py
────────────────────────
Temporal Retrieval Service for ChronoGraph.

Orchestrates loading, validation, filtering, and query execution over
retrieval-ready evidence records with resilient error handling and
per-request observability metadata.

Architecture
────────────
    RetrievalQueryRequest (API schema)
               ↓
    RetrievalRequest (internal filter model)
               ↓
    RetrievalService (loads & validates retrieval_ready_records.json)
               ↓
    TemporalFilterEngine (filtering & sorting engine)
               ↓
    RetrievalQueryResponse (structured results with provenance)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from config.settings import settings
from src.retrieval.errors import (
    RetrievalDataCorruptedError,
    RetrievalDataError,
    RetrievalDataFormatError,
    RetrievalDataNotFoundError,
    RetrievalError,
    RetrievalServiceError,
)
from src.retrieval.filter import TemporalFilterEngine
from src.retrieval.models import (
    RetrievalHealthResponse,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalRecord,
    RetrievalRequest,
    RetrievalRequestMetadata,
)

logger = logging.getLogger(__name__)

# Re-export exceptions for backward compatibility
__all__ = [
    "RetrievalError",
    "RetrievalServiceError",
    "RetrievalDataError",
    "RetrievalDataNotFoundError",
    "RetrievalDataFormatError",
    "RetrievalDataCorruptedError",
    "RetrievalService",
]


class RetrievalService:
    """
    Service layer providing temporal retrieval queries over retrieval-ready records.

    Responsibilities:
      1. Safely load and validate retrieval records from disk.
      2. Cache loaded records in memory for high-performance querying.
      3. Accept API / programmatic queries and normalize to RetrievalRequest.
      4. Reuse TemporalFilterEngine for entity, relation, source, and chronological filtering.
      5. Compute total matching records prior to pagination/limit.
      6. Return structured RetrievalQueryResponse preserving full provenance.
      7. Provide health and data quality statistics inspectability.
    """

    def __init__(
        self,
        records_path: Optional[Path] = None,
        filter_engine: Optional[TemporalFilterEngine] = None,
        stats_path: Optional[Path] = None,
    ) -> None:
        self.records_path: Path = Path(records_path) if records_path else settings.retrieval_ready_records_path
        self.stats_path: Path = Path(stats_path) if stats_path else settings.retrieval_quality_stats_path
        self.filter_engine: TemporalFilterEngine = filter_engine or TemporalFilterEngine()
        self._cached_records: Optional[List[RetrievalRecord]] = None

    # ── Record Loading & Cache Management ────────────────────────────────────

    def load_records(self, force_reload: bool = False) -> List[RetrievalRecord]:
        """
        Load and validate RetrievalRecord objects from disk.

        Handles missing files, empty files, corrupted JSON, and skips invalid items.
        Caches records in memory unless force_reload is True.

        If reload fails, previous valid cached records are preserved.

        Returns:
            List[RetrievalRecord]: Validated retrieval records.

        Raises:
            RetrievalDataNotFoundError: If records file does not exist.
            RetrievalDataFormatError: If JSON syntax or top-level structure is corrupted.
            RetrievalServiceError: For unexpected file access errors.
        """
        if self._cached_records is not None and not force_reload:
            return self._cached_records

        if not self.records_path.exists():
            logger.error("Retrieval data file not found")
            raise RetrievalDataNotFoundError(
                "Retrieval data file not found. "
                "Run 'python main.py --prepare-retrieval' first."
            )

        try:
            with open(self.records_path, "r", encoding="utf-8") as fh:
                raw_content = fh.read().strip()
                if not raw_content:
                    logger.warning("Retrieval data file is empty")
                    self._cached_records = []
                    return []
                raw_records = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            logger.error("Corrupted JSON in retrieval data file: %s", exc)
            raise RetrievalDataFormatError(
                f"Invalid JSON in retrieval records file: {exc}"
            ) from exc
        except (RetrievalDataError, RetrievalServiceError):
            raise
        except Exception as exc:
            logger.error("Failed to read retrieval records file")
            raise RetrievalServiceError("Error reading retrieval records") from exc

        if not isinstance(raw_records, list):
            logger.error("Expected JSON list in retrieval data file, got %s", type(raw_records).__name__)
            raise RetrievalDataFormatError(
                f"Expected a JSON list of records, got {type(raw_records).__name__}"
            )

        valid_records: List[RetrievalRecord] = []
        invalid_count = 0

        for idx, item in enumerate(raw_records):
            if not isinstance(item, dict):
                logger.warning("Skipping non-dict record at index %d", idx)
                invalid_count += 1
                continue
            try:
                rec = RetrievalRecord(**item)
                valid_records.append(rec)
            except Exception as exc:
                logger.warning("Skipping invalid record at index %d: %s", idx, exc)
                invalid_count += 1

        logger.info(
            "records_loaded=%d records_skipped=%d",
            len(valid_records),
            invalid_count,
        )
        self._cached_records = valid_records
        return valid_records

    def clear_cache(self) -> None:
        """Clear cached records from memory."""
        self._cached_records = None

    # ── Query Execution ──────────────────────────────────────────────────────

    def query(
        self,
        request: Union[RetrievalQueryRequest, RetrievalRequest, Dict[str, Any]],
        request_id: Optional[str] = None,
    ) -> RetrievalQueryResponse:
        """
        Execute a temporal retrieval query against loaded records.

        Steps:
          1. Accept or generate a request_id for this query.
             When called from the HTTP endpoint, the middleware-generated ID is
             passed in so that response.metadata.request_id == X-Request-ID header.
             When called programmatically (tests, CLI), a new UUID is generated.
          2. Detect cache_hit before loading records.
          3. Safely load records (uses in-memory cache when available).
          4. Normalize request into RetrievalRequest.
          5. Apply TemporalFilterEngine filtering across source, entity, relation,
             and temporal boundaries.
          6. Compute total matching records prior to result limiting.
          7. Apply chronological sorting and limit.
          8. Measure total execution time (monotonic timer).
          9. Assemble structured RetrievalQueryResponse with RetrievalRequestMetadata.

        Parameters:
            request: RetrievalQueryRequest, RetrievalRequest, or raw dictionary.
            request_id: Optional caller-supplied request ID. If None, a new UUID
                        is generated. The API endpoint passes the middleware ID here
                        to ensure X-Request-ID == metadata.request_id.

        Returns:
            RetrievalQueryResponse: Complete structured response with observability metadata.
        """
        # Step 1: Use caller-supplied ID or generate a server-side UUID
        effective_request_id = request_id if request_id else str(uuid4())

        # Step 2: Detect cache hit BEFORE calling load_records
        cache_hit = self._cached_records is not None

        # Step 3: Start timing (monotonic timer)
        _query_start = time.perf_counter()

        # Step 4: Ensure records are loaded (uses in-memory cache when available)
        records = self.load_records()
        records_loaded = len(records)

        # Step 5: Normalize request
        retrieval_req: RetrievalRequest
        query_echo: Optional[str] = None
        page: int = 1
        page_size: int = 20

        if isinstance(request, RetrievalQueryRequest):
            query_echo = request.query or request.query_text
            retrieval_req = request.to_retrieval_request()
            page = request.page
            page_size = request.page_size or request.limit
        elif isinstance(request, RetrievalRequest):
            query_echo = request.query_text
            retrieval_req = request
            page = 1
            page_size = request.limit
        elif isinstance(request, dict):
            parsed = RetrievalQueryRequest(**request)
            query_echo = parsed.query or parsed.query_text
            retrieval_req = parsed.to_retrieval_request()
            page = parsed.page
            page_size = parsed.page_size or parsed.limit
        else:
            raise ValueError(f"Unsupported request type: {type(request).__name__}")

        # Step 6: Apply filter engine with unlimited limit to determine total_matches
        unlimited_limit = records_loaded + 1
        unlimited_req = retrieval_req.model_copy(update={"limit": unlimited_limit})
        _filter_start = time.perf_counter()
        all_filtered = self.filter_engine.apply(records, unlimited_req)
        _filter_ms = (time.perf_counter() - _filter_start) * 1000

        total_matches = len(all_filtered)

        # Step 7: Apply 1-based pagination
        if total_matches == 0:
            total_pages = 0
        else:
            total_pages = (total_matches + page_size - 1) // page_size

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_results = all_filtered[start_idx:end_idx] if start_idx < total_matches else []
        returned_count = len(page_results)

        has_next = page < total_pages
        has_previous = page > 1 and total_pages > 0

        # Step 8: Stop timing after all retrieval work is done
        execution_time_ms = (time.perf_counter() - _query_start) * 1000

        # Step 9: Construct applied filters summary
        applied_filters = {
            "query_text": retrieval_req.query_text,
            "entities": retrieval_req.entities,
            "relation_hints": retrieval_req.relation_hints,
            "sources": retrieval_req.sources,
            "temporal_mode": retrieval_req.temporal_filter.mode.value,
            "temporal_filter": retrieval_req.temporal_filter.to_dict(),
            "sort_order": retrieval_req.sort_order.value,
            "limit": retrieval_req.limit,
            "page": page,
            "page_size": page_size,
        }

        # Build observability metadata — safe fields only, never from user input
        obs_metadata = RetrievalRequestMetadata(
            request_id=effective_request_id,
            execution_time_ms=round(execution_time_ms, 3),
            returned_count=returned_count,
            total_count=total_matches,
            page=page,
            page_size=page_size,
            cache_hit=cache_hit,
        )

        # Structured, safe log — does NOT log query text, API keys, or env vars
        logger.info(
            "retrieval_query request_id=%s status=200 execution_ms=%.2f "
            "results=%d total_matches=%d cache_hit=%s page=%d page_size=%d",
            effective_request_id,
            execution_time_ms,
            returned_count,
            total_matches,
            cache_hit,
            page,
            page_size,
        )
        logger.debug(
            "retrieval_query_detail request_id=%s records_loaded=%d "
            "filtering_ms=%.2f total_pages=%d has_next=%s has_previous=%s",
            effective_request_id,
            records_loaded,
            _filter_ms,
            total_pages,
            has_next,
            has_previous,
        )

        return RetrievalQueryResponse(
            query=query_echo,
            total_matches=total_matches,
            returned_count=returned_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
            results=page_results,
            applied_filters=applied_filters,
            metadata=obs_metadata,
        )

    # ── Health & Statistics ──────────────────────────────────────────────────

    def get_health(self) -> RetrievalHealthResponse:
        """
        Check retrieval data availability and return health status.

        Returns ``status="ok"`` only when retrieval data is present and readable.
        Returns ``status="degraded"`` when data is missing or cannot be loaded.
        """
        available = self.records_path.exists()
        count: Optional[int] = None
        status = "ok"

        if available:
            try:
                records = self.load_records()
                count = len(records)
                if count == 0:
                    status = "degraded"
            except Exception:
                logger.warning("Could not load records for health check")
                count = None
                status = "degraded"
        else:
            status = "degraded"

        return RetrievalHealthResponse(
            status=status,
            service="ChronoGraph Retrieval API",
            version="1.0.0",
            retrieval_data_available=available,
            retrieval_records_count=count,
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Retrieve data quality statistics from disk or compute them on demand.

        Returns:
            Dict[str, Any]: JSON-compatible quality statistics dict.

        Raises:
            RetrievalDataNotFoundError: If neither stats nor records file exists.
            RetrievalDataFormatError: If records or stats data cannot be parsed.
            RetrievalServiceError: On computation failure.
        """
        if self.stats_path.exists():
            try:
                with open(self.stats_path, "r", encoding="utf-8") as fh:
                    raw_content = fh.read().strip()
                    if raw_content:
                        stats_json = json.loads(raw_content)
                        if isinstance(stats_json, dict):
                            return stats_json
            except Exception:
                logger.warning("Failed to read stats file; recomputing")

        # If stats file missing or unreadable, compute on-demand using records
        if not self.records_path.exists():
            raise RetrievalDataNotFoundError(
                "Cannot compute stats: retrieval records not found. "
                "Run 'python main.py --prepare-retrieval' first."
            )

        from src.retrieval.stats import RetrievalStatsEngine

        try:
            engine = RetrievalStatsEngine(
                records_path=self.records_path,
                stats_path=self.stats_path,
            )
            stats = engine.compute()
            return stats.to_dict()
        except FileNotFoundError as exc:
            raise RetrievalDataNotFoundError("Retrieval records not found") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise RetrievalDataFormatError(f"Corrupted records during stats computation: {exc}") from exc
        except (RetrievalDataError, RetrievalServiceError):
            raise
        except Exception as exc:
            logger.error("Failed to compute retrieval stats")
            raise RetrievalServiceError("Error computing retrieval stats") from exc
