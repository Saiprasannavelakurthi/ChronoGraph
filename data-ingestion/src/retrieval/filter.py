"""
src/retrieval/filter.py
─────────────────────────
Week 3 — Temporal filtering and chronological sorting for retrieval records.

The TemporalFilterEngine applies a RetrievalRequest's filter criteria to a
list of RetrievalRecord objects entirely in Python, without touching Neo4j or
any external service.  This is data/retrieval *preparation* logic — it
enables the data-ingestion module to pre-screen evidence records before
handing them to the downstream Temporal Routing engine.

Supported operations
────────────────────
  • Exact date match          — records whose event_date == filter.exact_date
  • Date range (inclusive)    — start_date <= event_date <= end_date
  • Before (exclusive)        — event_date < filter.before_date
  • After  (exclusive)        — event_date > filter.after_date
  • Entity filtering          — subject or object (canonical or display) matches
  • Relation filtering        — relation label matches any hint
  • Source filtering          — source system matches any allowed source
  • Chronological sort        — ascending (earliest first) or descending (latest first)
  • Limit                     — cap result count

Public API
──────────
    engine = TemporalFilterEngine()
    results = engine.apply(records, request)
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.retrieval.models import (
    RetrievalRecord,
    RetrievalRequest,
    SortOrder,
    TemporalFilter,
    TemporalFilterMode,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────


class TemporalFilterEngine:
    """
    Applies temporal and entity filters to a list of RetrievalRecord objects.

    This component is stateless — all state is supplied via the
    RetrievalRequest argument.

    Usage
    ─────
        engine = TemporalFilterEngine()
        results = engine.apply(records, request)
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def apply(
        self,
        records: List[RetrievalRecord],
        request: RetrievalRequest,
    ) -> List[RetrievalRecord]:
        """
        Filter and sort `records` according to `request`.

        Filtering is applied in this order:
          1. Source filter
          2. Entity filter (subject or object match)
          3. Relation hint filter
          4. Temporal filter (exact / range / before / after)
          5. Chronological sort
          6. Limit

        Parameters
        ──────────
        records : List[RetrievalRecord]  — input pool of evidence records.
        request : RetrievalRequest       — filter / sort / limit parameters.

        Returns
        ───────
        List[RetrievalRecord] — filtered, sorted, and limited results.
        """
        result = list(records)

        # Step 1 — source filter
        if request.sources:
            result = [r for r in result if r.source.lower() in request.sources]
            logger.debug("After source filter: %d records", len(result))

        # Step 2 — entity filter
        if request.entities:
            entity_set = {e.lower() for e in request.entities}
            result = [
                r for r in result
                if self._entity_matches(r, entity_set)
            ]
            logger.debug("After entity filter: %d records", len(result))

        # Step 3 — relation hint filter
        if request.relation_hints:
            hints = {h.upper() for h in request.relation_hints}
            result = [r for r in result if r.relation.upper() in hints]
            logger.debug("After relation filter: %d records", len(result))

        # Step 4 — temporal filter
        tf = request.temporal_filter
        if tf.mode != TemporalFilterMode.NONE:
            result = self.apply_temporal_filter(result, tf)
            logger.debug("After temporal filter (%s): %d records", tf.mode.value, len(result))

        # Step 5 — chronological sort
        result = self.sort_chronologically(result, request.sort_order)

        # Step 6 — limit
        result = result[: request.limit]

        logger.info(
            "TemporalFilterEngine.apply: %d → %d records (limit=%d)",
            len(records),
            len(result),
            request.limit,
        )
        return result

    def apply_temporal_filter(
        self,
        records: List[RetrievalRecord],
        temporal_filter: TemporalFilter,
    ) -> List[RetrievalRecord]:
        """
        Apply only the temporal portion of the filter to `records`.

        Can be called independently when only temporal filtering is needed.

        Parameters
        ──────────
        records        : Input evidence records.
        temporal_filter: The TemporalFilter to apply.

        Returns
        ───────
        Filtered list of RetrievalRecord.
        """
        mode = temporal_filter.mode

        if mode == TemporalFilterMode.NONE:
            return list(records)

        if mode == TemporalFilterMode.EXACT:
            target = temporal_filter.exact_date
            return [r for r in records if r.event_date == target]

        if mode == TemporalFilterMode.RANGE:
            start = temporal_filter.start_date
            end = temporal_filter.end_date
            result = list(records)
            if start:
                result = [r for r in result if r.event_date >= start]
            if end:
                result = [r for r in result if r.event_date <= end]
            return result

        if mode == TemporalFilterMode.BEFORE:
            threshold = temporal_filter.before_date
            return [r for r in records if r.event_date < threshold]

        if mode == TemporalFilterMode.AFTER:
            threshold = temporal_filter.after_date
            return [r for r in records if r.event_date > threshold]

        # Defensive default — should never reach here
        logger.warning("Unknown TemporalFilterMode '%s'; returning all records.", mode)
        return list(records)

    @staticmethod
    def sort_chronologically(
        records: List[RetrievalRecord],
        order: SortOrder = SortOrder.ASC,
    ) -> List[RetrievalRecord]:
        """
        Sort records by event_date and timestamp string.

        Parameters
        ──────────
        records : List[RetrievalRecord]
        order   : SortOrder.ASC (earliest first) or SortOrder.DESC (latest first).

        Returns
        ───────
        New sorted list (input is not mutated).
        """
        reverse = order == SortOrder.DESC
        return sorted(records, key=lambda r: (r.event_date, r.timestamp), reverse=reverse)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _entity_matches(record: RetrievalRecord, entity_set: set) -> bool:
        """
        Return True if any entity hint matches the record's subject or object.

        Matching is case-insensitive and checks both canonical (snake_case) and
        display names.
        """
        candidates = {
            record.subject.lower(),
            record.object.lower(),
        }
        if record.subject_display:
            candidates.add(record.subject_display.lower())
        if record.object_display:
            candidates.add(record.object_display.lower())

        return bool(candidates & entity_set)
