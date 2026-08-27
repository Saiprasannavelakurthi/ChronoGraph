"""
src/retrieval/stats.py
───────────────────────
Week 3 — Retrieval data quality and coverage statistics engine.

RetrievalStatsEngine reads retrieval_ready_records.json and computes a
RetrievalDataQualityStats summary covering:

  * total_records               — total records in the file
  * unique_entities             — distinct entity values (subjects + objects)
  * unique_relations            — distinct relation type labels
  * records_with_temporal_data  — records with valid timestamp + event_date
  * records_without_temporal_data — records missing or with invalid temporal data
  * earliest_timestamp          — earliest event_date found (YYYY-MM-DD)
  * latest_timestamp            — latest event_date found (YYYY-MM-DD)
  * source_breakdown            — per-source record counts
  * average_confidence          — mean confidence score
  * records_with_source_url     — count of records with a non-null source_url

The engine is read-only: it never modifies any file.  The output statistics
are optionally written to retrieval_quality_stats.json.

Public API
──────────
    from src.retrieval.stats import RetrievalStatsEngine

    engine = RetrievalStatsEngine(
        records_path=Path("data/processed/retrieval_ready_records.json"),
        stats_path=Path("data/processed/retrieval_quality_stats.json"),  # optional
    )
    stats = engine.compute()
    # stats: RetrievalDataQualityStats
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.retrieval.models import RetrievalDataQualityStats

logger = logging.getLogger(__name__)


class RetrievalStatsEngine:
    """
    Computes data quality and coverage statistics from retrieval_ready_records.json.

    Parameters
    ──────────
    records_path : Path to retrieval_ready_records.json (required).
    stats_path   : Optional destination path for retrieval_quality_stats.json.
                   If provided, the computed stats are written there after each
                   compute() call.

    Usage
    ─────
        engine = RetrievalStatsEngine(
            records_path=Path("data/processed/retrieval_ready_records.json"),
            stats_path=Path("data/processed/retrieval_quality_stats.json"),
        )
        stats = engine.compute()
        print(stats.total_records)       # 142
        print(stats.unique_entities)     # e.g. 38
        print(stats.unique_relations)    # e.g. 8
        print(stats.earliest_timestamp)  # "2023-03-15"
        print(stats.latest_timestamp)    # "2023-05-30"
    """

    def __init__(
        self,
        records_path: Path,
        stats_path: Optional[Path] = None,
    ) -> None:
        self.records_path = Path(records_path)
        self.stats_path = Path(stats_path) if stats_path is not None else None

    # ── Public API ────────────────────────────────────────────────────────────

    def compute(self) -> RetrievalDataQualityStats:
        """
        Load retrieval_ready_records.json and compute quality statistics.

        Returns
        ───────
        RetrievalDataQualityStats — fully populated statistics object.

        Raises
        ──────
        FileNotFoundError : If retrieval_ready_records.json does not exist.
        ValueError        : If the file is not a valid JSON array.
        """
        records = self._load_records()
        stats = self._compute_stats(records)

        if self.stats_path is not None:
            self._write_stats(stats)

        logger.info(
            "RetrievalStatsEngine: computed stats for %d records "
            "(unique_entities=%d, unique_relations=%d, "
            "with_temporal=%d, without_temporal=%d)",
            stats.total_records,
            stats.unique_entities,
            stats.unique_relations,
            stats.records_with_temporal_data,
            stats.records_without_temporal_data,
        )
        return stats

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_records(self) -> List[Dict[str, Any]]:
        """Load and validate retrieval_ready_records.json."""
        if not self.records_path.exists():
            raise FileNotFoundError(
                f"retrieval_ready_records.json not found at '{self.records_path}'. "
                "Run 'python main.py --prepare-retrieval' first."
            )
        with open(self.records_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(
                f"Expected a JSON array in '{self.records_path}', "
                f"got {type(data).__name__}."
            )
        return data

    def _compute_stats(
        self, records: List[Dict[str, Any]]
    ) -> RetrievalDataQualityStats:
        """Compute all statistics from the loaded records list."""
        if not records:
            return RetrievalDataQualityStats(
                total_records=0,
                unique_entities=0,
                unique_relations=0,
                records_with_temporal_data=0,
                records_without_temporal_data=0,
                earliest_timestamp=None,
                latest_timestamp=None,
                source_breakdown={},
                average_confidence=None,
                records_with_source_url=0,
            )

        # ── Accumulate per-record values ──────────────────────────────────────
        entity_set: set = set()
        relation_set: set = set()
        source_counts: Dict[str, int] = {}
        event_dates: List[date] = []
        confidence_sum: float = 0.0
        confidence_count: int = 0
        with_temporal: int = 0
        without_temporal: int = 0
        with_source_url: int = 0

        for rec in records:
            # Entities: collect subject + object (canonical + display names)
            for field in ("subject", "subject_display", "object", "object_display"):
                val = rec.get(field)
                if val and str(val).strip():
                    entity_set.add(str(val).strip().lower())

            # Relations
            relation = rec.get("relation")
            if relation and str(relation).strip():
                relation_set.add(str(relation).strip().upper())

            # Sources
            source = rec.get("source", "")
            if source:
                source_lower = str(source).lower()
                source_counts[source_lower] = source_counts.get(source_lower, 0) + 1

            # Temporal data
            ts = rec.get("timestamp")
            ed = rec.get("event_date")
            parsed_date: Optional[date] = None
            ts_valid = False
            ed_valid = False

            if ts and str(ts).strip():
                try:
                    datetime.fromisoformat(str(ts))
                    ts_valid = True
                except (ValueError, TypeError):
                    pass

            if ed and str(ed).strip():
                try:
                    parsed_date = date.fromisoformat(str(ed))
                    ed_valid = True
                except (ValueError, TypeError):
                    pass

            if ts_valid and ed_valid:
                with_temporal += 1
                if parsed_date is not None:
                    event_dates.append(parsed_date)
            else:
                without_temporal += 1

            # Confidence
            conf = rec.get("confidence")
            if conf is not None:
                try:
                    fconf = float(conf)
                    confidence_sum += fconf
                    confidence_count += 1
                except (TypeError, ValueError):
                    pass

            # source_url
            if rec.get("source_url"):
                with_source_url += 1

        # ── Derive aggregated values ──────────────────────────────────────────
        earliest: Optional[str] = min(event_dates).isoformat() if event_dates else None
        latest: Optional[str] = max(event_dates).isoformat() if event_dates else None
        avg_confidence: Optional[float] = (
            round(confidence_sum / confidence_count, 4)
            if confidence_count > 0
            else None
        )

        return RetrievalDataQualityStats(
            total_records=len(records),
            unique_entities=len(entity_set),
            unique_relations=len(relation_set),
            records_with_temporal_data=with_temporal,
            records_without_temporal_data=without_temporal,
            earliest_timestamp=earliest,
            latest_timestamp=latest,
            source_breakdown=dict(sorted(source_counts.items())),
            average_confidence=avg_confidence,
            records_with_source_url=with_source_url,
        )

    def _write_stats(self, stats: RetrievalDataQualityStats) -> None:
        """Write computed stats to retrieval_quality_stats.json."""
        if self.stats_path is None:
            return
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.stats_path, "w", encoding="utf-8") as fh:
            json.dump(stats.to_dict(), fh, indent=2, ensure_ascii=False)
        logger.info(
            "RetrievalStatsEngine: wrote quality stats -> %s",
            self.stats_path,
        )
