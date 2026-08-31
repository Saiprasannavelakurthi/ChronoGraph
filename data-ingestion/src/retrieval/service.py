"""
src/retrieval/service.py
────────────────────────
Week 4 — Temporal Retrieval Service (Karkuvel's module).

Orchestrates the loading, validation, filtering, and query execution for
retrieval-ready evidence records with resilient error handling.

Architecture
────────────
    RetrievalQueryRequest (Week 4 API schema)
               ↓
    RetrievalRequest (Week 3 model)
               ↓
    RetrievalService (loads & validates retrieval_ready_records.json)
               ↓
    TemporalFilterEngine (Week 3 filtering & sorting engine)
               ↓
    RetrievalQueryResponse (structured results with provenance)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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
            logger.error("Retrieval data file not found: %s", self.records_path)
            raise RetrievalDataNotFoundError(
                f"Retrieval data file not found at '{self.records_path}'. "
                "Run 'python main.py --prepare-retrieval' or POST /api/v1/prepare-graph first."
            )

        try:
            with open(self.records_path, "r", encoding="utf-8") as fh:
                raw_content = fh.read().strip()
                if not raw_content:
                    logger.warning("Retrieval data file %s is empty", self.records_path)
                    self._cached_records = []
                    return []
                raw_records = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            logger.error("Corrupted JSON in retrieval data file %s: %s", self.records_path, exc)
            raise RetrievalDataFormatError(
                f"Invalid JSON in retrieval records file: {exc}"
            ) from exc
        except (RetrievalDataError, RetrievalServiceError):
            raise
        except Exception as exc:
            logger.error("Failed to read retrieval records file %s: %s", self.records_path, exc)
            raise RetrievalServiceError(f"Error reading retrieval records: {exc}") from exc

        if not isinstance(raw_records, list):
            logger.error("Expected JSON list in %s, got %s", self.records_path, type(raw_records).__name__)
            raise RetrievalDataFormatError(
                f"Expected a JSON list of records in {self.records_path}, got {type(raw_records).__name__}"
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
            "RetrievalService: Loaded %d valid records (skipped %d invalid) from %s",
            len(valid_records),
            invalid_count,
            self.records_path,
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
    ) -> RetrievalQueryResponse:
        """
        Execute a temporal retrieval query against loaded records.

        Steps:
          1. Safely load records.
          2. Normalize request into RetrievalRequest.
          3. Apply TemporalFilterEngine filtering across source, entity, relation,
             and temporal boundaries.
          4. Compute total matching records prior to result limiting.
          5. Apply chronological sorting and limit.
          6. Assemble structured RetrievalQueryResponse.

        Parameters:
            request: RetrievalQueryRequest, RetrievalRequest, or raw dictionary.

        Returns:
            RetrievalQueryResponse: Complete structured response.
        """
        # Step 1: Ensure records are loaded
        records = self.load_records()

        # Step 2: Normalize request
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
            # Parse via RetrievalQueryRequest for unified API schema support
            parsed = RetrievalQueryRequest(**request)
            query_echo = parsed.query or parsed.query_text
            retrieval_req = parsed.to_retrieval_request()
            page = parsed.page
            page_size = parsed.page_size or parsed.limit
        else:
            raise ValueError(f"Unsupported request type: {type(request).__name__}")

        # Step 3: Apply filter engine with unlimited limit to determine total_matches
        # TemporalFilterEngine is stateless and applies source -> entity -> relation -> temporal -> sort -> limit
        unlimited_limit = len(records) + 1
        unlimited_req = retrieval_req.model_copy(update={"limit": unlimited_limit})
        all_filtered = self.filter_engine.apply(records, unlimited_req)

        total_matches = len(all_filtered)

        # Step 4: Apply 1-based pagination
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

        # Step 5: Construct applied filters summary
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

        logger.info(
            "RetrievalService.query completed: %d total matches, %d returned (page=%d, page_size=%d, total_pages=%d)",
            total_matches,
            returned_count,
            page,
            page_size,
            total_pages,
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
        )

    # ── Health & Statistics ──────────────────────────────────────────────────

    def get_health(self) -> RetrievalHealthResponse:
        """
        Check retrieval data availability and return health status.
        """
        available = self.records_path.exists()
        count: Optional[int] = None
        if available:
            try:
                records = self.load_records()
                count = len(records)
            except Exception as exc:
                logger.warning("Could not read records for health check: %s", exc)
                count = None

        return RetrievalHealthResponse(
            status="ok",
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
            except Exception as exc:
                logger.warning("Failed to read stats file %s: %s; recomputing", self.stats_path, exc)

        # If stats file missing or unreadable, compute on-demand using records
        if not self.records_path.exists():
            raise RetrievalDataNotFoundError(
                f"Cannot compute stats: retrieval records not found at '{self.records_path}'"
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
            raise RetrievalDataNotFoundError(str(exc)) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise RetrievalDataFormatError(f"Corrupted records during stats computation: {exc}") from exc
        except (RetrievalDataError, RetrievalServiceError):
            raise
        except Exception as exc:
            logger.error("Failed to compute stats: %s", exc)
            raise RetrievalServiceError(f"Error computing retrieval stats: {exc}") from exc
