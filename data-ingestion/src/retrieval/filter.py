"""
src/retrieval/filter.py
────────────────────────
Temporal filtering and chronological sorting engine for retrieval records.

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

        # Step 5 — free-text query filter & relevance scoring
        has_query = bool(request.query_text and request.query_text.strip())
        if has_query:
            scored_records: List[RetrievalRecord] = []
            for r in result:
                score = self._match_and_score_text_query(r, request.query_text)
                if score is not None:
                    scored_records.append(r.model_copy(update={"relevance_score": score}))
            result = scored_records
            logger.debug("After free-text query filter: %d records", len(result))

        # Step 6 — sort records (relevance + chronological)
        result = self.sort_records(result, request.sort_order, has_query=has_query)

        # Step 7 — limit
        result = result[: request.limit]

        logger.info(
            "TemporalFilterEngine.apply: %d → %d records (limit=%d, query=%s)",
            len(records),
            len(result),
            request.limit,
            request.query_text,
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

    @staticmethod
    def sort_records(
        records: List[RetrievalRecord],
        order: SortOrder = SortOrder.ASC,
        has_query: bool = False,
    ) -> List[RetrievalRecord]:
        """
        Sort records by relevance score (if query active) and event_date / timestamp.

        When a query is active:
          - Primary sort: relevance_score DESC (highest score first)
          - Secondary sort: event_date and timestamp (ASC or DESC according to order)

        When no query is active:
          - Pure chronological sort by event_date and timestamp (ASC or DESC according to order)
        """
        if has_query:
            if order == SortOrder.DESC:
                return sorted(
                    records,
                    key=lambda r: (
                        r.relevance_score if r.relevance_score is not None else 0.0,
                        r.event_date,
                        r.timestamp,
                    ),
                    reverse=True,
                )
            else:
                return sorted(
                    records,
                    key=lambda r: (
                        -(r.relevance_score if r.relevance_score is not None else 0.0),
                        r.event_date,
                        r.timestamp,
                    ),
                )
        else:
            reverse = order == SortOrder.DESC
            return sorted(records, key=lambda r: (r.event_date, r.timestamp), reverse=reverse)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _match_and_score_text_query(
        record: RetrievalRecord,
        query: str,
    ) -> Optional[float]:
        """
        Perform deterministic case-insensitive free-text query matching and relevance scoring.

        Weights:
          - subject / object / entity display names: 3.0 weight per term (5.0 phrase bonus)
          - relation: 2.0 weight per term (3.0 phrase bonus)
          - evidence: 1.0 weight per term (2.0 phrase bonus)
          - source / source_id: 1.0 weight per term (1.0 phrase bonus)

        Returns:
          float: Relevance score if record matches query (score > 0).
          None: If record does not match query (score == 0).
        """
        if not query:
            return None
        q_clean = query.strip().lower()
        if not q_clean:
            return None

        raw_terms = [t for t in q_clean.split() if t]
        if not raw_terms:
            return None

        # Filter out common question stop words when query has multiple terms
        common_stop_words = {
            "what", "when", "where", "which", "who", "whom", "whose", "why",
            "how", "did", "does", "do", "for", "the", "a", "an", "in", "on",
            "at", "to", "is", "are", "was", "were", "of", "with", "by", "from",
        }
        if len(raw_terms) > 1:
            terms = [t for t in raw_terms if t not in common_stop_words]
            if not terms:
                terms = raw_terms
        else:
            terms = raw_terms

        subj = record.subject.lower()
        subj_disp = (record.subject_display or "").lower()
        obj = record.object.lower()
        obj_disp = (record.object_display or "").lower()
        rel = record.relation.lower()
        ev = record.evidence.lower()
        src = record.source.lower()
        src_id = record.source_id.lower()

        entity_text = f"{subj} {subj_disp} {obj} {obj_disp}"
        relation_text = rel
        evidence_text = ev
        source_text = f"{src} {src_id}"

        score = 0.0

        # Entity scoring
        if q_clean in entity_text:
            score += 5.0
        for t in terms:
            if t in entity_text:
                score += 3.0

        # Relation scoring
        if q_clean in relation_text:
            score += 3.0
        for t in terms:
            if t in relation_text or t in relation_text.replace("_", " "):
                score += 2.0

        # Evidence scoring
        if q_clean in evidence_text:
            score += 2.0
        for t in terms:
            if t in evidence_text:
                score += 1.0

        # Source scoring
        if q_clean in source_text:
            score += 1.0
        for t in terms:
            if t in source_text:
                score += 1.0

        if score > 0.0:
            return round(score, 2)
        return None

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
