"""
tests/test_retrieval.py
────────────────────────
Week 3 — Comprehensive tests for Temporal Retrieval Preparation.

Coverage
────────
  1.  RetrievalRecord  — timestamp preserved, event_date parsed correctly
  2.  Chronological sorting — ASC and DESC
  3.  Date-range filtering — inclusive boundaries
  4.  Before/after temporal filtering — exclusive boundaries
  5.  Exact date filtering
  6.  Source provenance preserved — Slack/GitHub/Jira identifiable
  7.  Missing optional metadata handled safely (None, not crash)
  8.  Invalid temporal input rejected or handled clearly
  9.  RetrievalRequest validation — invalid sources rejected
  10. Entity filtering — canonical and display name matching
  11. Relation hint filtering
  12. Combined entity + temporal filter
  13. Limit enforcement
  14. SortOrder.DESC ordering
  15. TemporalFilter mode detection
  16. RetrievalRecordBuilder — builds records from a real/mock graph_ready_triples.json
  17. RetrievalRecordBuilder — skips malformed triples safely
  18. source_url extraction from metadata
  19. source_label property (citation readiness)
  20. RetrievalRequest.to_dict serialization
  21. TemporalFilter.to_dict serialization
  22. TemporalFilter start_date > end_date rejection
  23. RetrievalRecord.to_dict event_date serialization
  24. Empty entity / relation hint lists do not filter
  25. TemporalFilterEngine with all records when NONE mode
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# ── Imports under test ────────────────────────────────────────────────────────
from src.retrieval.models import (
    PipelineExecutionMetadata,
    RetrievalRecord,
    RetrievalRequest,
    SortOrder,
    TemporalFilter,
    TemporalFilterMode,
)
from src.retrieval.builder import RetrievalRecordBuilder
from src.retrieval.filter import TemporalFilterEngine


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_record(**overrides) -> RetrievalRecord:
    """Return a valid RetrievalRecord with optional field overrides."""
    base: Dict[str, Any] = {
        "record_id": str(uuid.uuid4()),
        "triple_id": str(uuid.uuid4()),
        "subject": "arun_sharma",
        "subject_display": "Arun Sharma",
        "subject_type": "Person",
        "relation": "ADVOCATED_FOR",
        "object": "gcp",
        "object_display": "GCP",
        "object_type": "Technology",
        "timestamp": "2023-03-15T10:30:00+00:00",
        "event_date": date(2023, 3, 15),
        "source": "slack",
        "source_id": "slack_001",
        "source_url": None,
        "evidence": "Arun suggested moving our services to GCP.",
        "confidence": 0.9,
        "extraction_mode": "llm_groq",
        "metadata": {},
    }
    base.update(overrides)
    return RetrievalRecord(**base)


# A set of sample records spanning different dates and sources
SAMPLE_RECORDS: List[RetrievalRecord] = [
    make_record(
        triple_id="aaa",
        subject="arun_sharma",
        relation="ADVOCATED_FOR",
        object="gcp",
        source="slack",
        source_id="slack_001",
        timestamp="2023-01-10T09:00:00+00:00",
        event_date=date(2023, 1, 10),
        confidence=0.9,
    ),
    make_record(
        triple_id="bbb",
        subject="priya_nair",
        subject_display="Priya Nair",
        relation="REVIEWED",
        object="auth_service",
        object_display="Auth Service",
        source="github",
        source_id="github_pr_007",
        timestamp="2023-03-15T14:00:00+00:00",
        event_date=date(2023, 3, 15),
        confidence=0.85,
    ),
    make_record(
        triple_id="ccc",
        subject="ravi_kumar",
        relation="ASSIGNED_TO",
        object="cg-101",
        source="jira",
        source_id="jira_001",
        timestamp="2022-11-20T08:00:00+00:00",
        event_date=date(2022, 11, 20),
        confidence=0.75,
    ),
    make_record(
        triple_id="ddd",
        subject="arun_sharma",
        relation="MIGRATED_TO",
        object="kubernetes",
        source="slack",
        source_id="slack_042",
        timestamp="2023-06-01T12:00:00+00:00",
        event_date=date(2023, 6, 1),
        confidence=0.8,
    ),
    make_record(
        triple_id="eee",
        subject="priya_nair",
        relation="RAISED_CONCERN",
        object="database_migration",
        source="jira",
        source_id="jira_015",
        timestamp="2023-03-15T11:00:00+00:00",
        event_date=date(2023, 3, 15),
        confidence=0.7,
    ),
]


def _engine() -> TemporalFilterEngine:
    return TemporalFilterEngine()


def _default_request(**overrides) -> RetrievalRequest:
    base = {
        "limit": 100,
        "sort_order": SortOrder.ASC,
    }
    base.update(overrides)
    return RetrievalRequest(**base)


# ─────────────────────────────────────────────────────────────────────────────
# 1. RetrievalRecord — timestamp preserved
# ─────────────────────────────────────────────────────────────────────────────


class TestRetrievalRecordTimestamp:
    def test_timestamp_preserved_exactly(self):
        ts = "2023-03-15T10:30:00+00:00"
        r = make_record(timestamp=ts)
        assert r.timestamp == ts

    def test_event_date_matches_timestamp_date(self):
        r = make_record(
            timestamp="2023-03-15T10:30:00+00:00",
            event_date=date(2023, 3, 15),
        )
        assert r.event_date == date(2023, 3, 15)

    def test_invalid_timestamp_rejected(self):
        with pytest.raises(ValueError, match="ISO-8601"):
            make_record(timestamp="not-a-date")

    def test_empty_timestamp_rejected(self):
        with pytest.raises(ValueError):
            make_record(timestamp="")

    def test_record_id_defaults_to_uuid(self):
        r = make_record()
        # Should be a valid UUID-shaped string
        assert len(r.record_id) == 36
        assert r.record_id.count("-") == 4


# ─────────────────────────────────────────────────────────────────────────────
# 2. Chronological sorting
# ─────────────────────────────────────────────────────────────────────────────


class TestChronologicalSort:
    def test_sort_asc_earliest_first(self):
        engine = _engine()
        sorted_records = engine.sort_chronologically(SAMPLE_RECORDS, SortOrder.ASC)
        dates = [r.event_date for r in sorted_records]
        assert dates == sorted(dates), "ASC sort should be earliest first"

    def test_sort_desc_latest_first(self):
        engine = _engine()
        sorted_records = engine.sort_chronologically(SAMPLE_RECORDS, SortOrder.DESC)
        dates = [r.event_date for r in sorted_records]
        assert dates == sorted(dates, reverse=True), "DESC sort should be latest first"

    def test_sort_does_not_mutate_input(self):
        original_order = [r.triple_id for r in SAMPLE_RECORDS]
        _engine().sort_chronologically(SAMPLE_RECORDS, SortOrder.ASC)
        assert [r.triple_id for r in SAMPLE_RECORDS] == original_order

    def test_sort_empty_list(self):
        assert _engine().sort_chronologically([], SortOrder.ASC) == []

    def test_sort_single_record(self):
        r = make_record()
        result = _engine().sort_chronologically([r], SortOrder.ASC)
        assert result == [r]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Date-range filtering
# ─────────────────────────────────────────────────────────────────────────────


class TestDateRangeFilter:
    def test_range_inclusive_both_ends(self):
        tf = TemporalFilter(start_date=date(2023, 1, 10), end_date=date(2023, 3, 15))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        # Includes 2023-01-10, 2023-03-15 x2; excludes 2022-11-20 and 2023-06-01
        for r in result:
            assert date(2023, 1, 10) <= r.event_date <= date(2023, 3, 15)

    def test_range_excludes_before_start(self):
        tf = TemporalFilter(start_date=date(2023, 1, 1))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert all(r.event_date >= date(2023, 1, 1) for r in result)
        # The 2022-11-20 record should be excluded
        triple_ids = [r.triple_id for r in result]
        assert "ccc" not in triple_ids

    def test_range_excludes_after_end(self):
        tf = TemporalFilter(end_date=date(2023, 3, 20))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert all(r.event_date <= date(2023, 3, 20) for r in result)
        triple_ids = [r.triple_id for r in result]
        assert "ddd" not in triple_ids

    def test_range_start_equals_end_exact_day(self):
        tf = TemporalFilter(start_date=date(2023, 3, 15), end_date=date(2023, 3, 15))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert len(result) == 2  # bbb and eee on 2023-03-15
        assert all(r.event_date == date(2023, 3, 15) for r in result)

    def test_range_empty_when_no_match(self):
        tf = TemporalFilter(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert result == []

    def test_range_start_after_end_rejected(self):
        with pytest.raises(ValueError, match="start_date"):
            TemporalFilter(start_date=date(2024, 1, 1), end_date=date(2023, 1, 1))


# ─────────────────────────────────────────────────────────────────────────────
# 4. Before / After temporal filtering
# ─────────────────────────────────────────────────────────────────────────────


class TestBeforeAfterFilter:
    def test_before_exclusive(self):
        tf = TemporalFilter(before_date=date(2023, 3, 15))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert all(r.event_date < date(2023, 3, 15) for r in result)
        # 2023-03-15 records (bbb, eee) must NOT be included
        triple_ids = [r.triple_id for r in result]
        assert "bbb" not in triple_ids
        assert "eee" not in triple_ids

    def test_after_exclusive(self):
        tf = TemporalFilter(after_date=date(2023, 3, 15))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert all(r.event_date > date(2023, 3, 15) for r in result)
        # Only 2023-06-01 (ddd) is strictly after
        assert len(result) == 1
        assert result[0].triple_id == "ddd"

    def test_before_all_excluded(self):
        tf = TemporalFilter(before_date=date(2022, 1, 1))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert result == []

    def test_after_all_excluded(self):
        tf = TemporalFilter(after_date=date(2030, 1, 1))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. Exact date filtering
# ─────────────────────────────────────────────────────────────────────────────


class TestExactDateFilter:
    def test_exact_date_matches_two_records(self):
        tf = TemporalFilter(exact_date=date(2023, 3, 15))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert len(result) == 2
        assert all(r.event_date == date(2023, 3, 15) for r in result)

    def test_exact_date_no_match(self):
        tf = TemporalFilter(exact_date=date(2021, 1, 1))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert result == []

    def test_exact_date_single_match(self):
        tf = TemporalFilter(exact_date=date(2023, 6, 1))
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert len(result) == 1
        assert result[0].triple_id == "ddd"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Source provenance preserved
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceProvenance:
    def test_slack_source_identifiable(self):
        slack_records = [r for r in SAMPLE_RECORDS if r.source == "slack"]
        assert len(slack_records) > 0
        for r in slack_records:
            assert r.source == "slack"
            assert r.source_id.startswith("slack_")

    def test_github_source_identifiable(self):
        github_records = [r for r in SAMPLE_RECORDS if r.source == "github"]
        assert len(github_records) > 0
        for r in github_records:
            assert r.source == "github"
            assert "github" in r.source_id

    def test_jira_source_identifiable(self):
        jira_records = [r for r in SAMPLE_RECORDS if r.source == "jira"]
        assert len(jira_records) > 0
        for r in jira_records:
            assert r.source == "jira"
            assert r.source_id.startswith("jira_")

    def test_source_label_slack(self):
        r = make_record(source="slack", source_id="slack_001")
        assert r.source_label == "Slack message slack_001"

    def test_source_label_github(self):
        r = make_record(source="github", source_id="github_pr_007")
        assert r.source_label == "GitHub PR github_pr_007"

    def test_source_label_jira(self):
        r = make_record(source="jira", source_id="jira_001")
        assert r.source_label == "Jira ticket jira_001"

    def test_evidence_preserved(self):
        evidence_text = "Arun suggested moving our services to GCP."
        r = make_record(evidence=evidence_text)
        assert r.evidence == evidence_text


# ─────────────────────────────────────────────────────────────────────────────
# 7. Missing optional metadata handled safely
# ─────────────────────────────────────────────────────────────────────────────


class TestMissingOptionalMetadata:
    def test_source_url_none_when_missing(self):
        r = make_record(source_url=None)
        assert r.source_url is None

    def test_subject_display_none_when_missing(self):
        r = make_record(subject_display=None)
        assert r.subject_display is None

    def test_object_display_none_when_missing(self):
        r = make_record(object_display=None)
        assert r.object_display is None

    def test_subject_type_none_when_missing(self):
        r = make_record(subject_type=None)
        assert r.subject_type is None

    def test_object_type_none_when_missing(self):
        r = make_record(object_type=None)
        assert r.object_type is None

    def test_extraction_mode_none_when_missing(self):
        r = make_record(extraction_mode=None)
        assert r.extraction_mode is None

    def test_metadata_defaults_to_empty_dict(self):
        r = make_record(metadata={})
        assert r.metadata == {}

    def test_to_dict_has_none_values_not_missing_keys(self):
        r = make_record(source_url=None, subject_display=None)
        d = r.to_dict()
        assert "source_url" in d
        assert d["source_url"] is None
        assert "subject_display" in d
        assert d["subject_display"] is None

    def test_entity_filter_ignores_none_display_names(self):
        """Entity filter must not crash when display names are None."""
        r = make_record(
            subject="arun_sharma",
            subject_display=None,
            object="gcp",
            object_display=None,
        )
        req = _default_request(entities=["arun_sharma"])
        result = _engine().apply([r], req)
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. Invalid temporal input rejected or handled clearly
# ─────────────────────────────────────────────────────────────────────────────


class TestInvalidTemporalInput:
    def test_invalid_timestamp_string_raises(self):
        with pytest.raises(ValueError, match="ISO-8601"):
            make_record(timestamp="2023-13-99")  # month 13 invalid

    def test_range_inverted_raises(self):
        with pytest.raises(ValueError, match="start_date"):
            TemporalFilter(start_date=date(2024, 6, 1), end_date=date(2023, 1, 1))

    def test_invalid_source_in_request_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            RetrievalRequest(sources=["twitter"])

    def test_limit_zero_raises(self):
        with pytest.raises(ValueError):
            RetrievalRequest(limit=0)

    def test_limit_negative_raises(self):
        with pytest.raises(ValueError):
            RetrievalRequest(limit=-5)

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValueError):
            make_record(confidence=1.5)

    def test_empty_subject_raises(self):
        with pytest.raises(ValueError):
            make_record(subject="")

    def test_empty_evidence_raises(self):
        with pytest.raises(ValueError):
            make_record(evidence="")


# ─────────────────────────────────────────────────────────────────────────────
# 9. RetrievalRequest validation
# ─────────────────────────────────────────────────────────────────────────────


class TestRetrievalRequest:
    def test_default_request_valid(self):
        req = RetrievalRequest()
        assert req.limit == 20
        assert req.sort_order == SortOrder.ASC
        assert req.sources == []
        assert req.entities == []
        assert req.relation_hints == []

    def test_sources_normalised_to_lowercase(self):
        req = RetrievalRequest(sources=["Slack", "GitHub"])
        assert req.sources == ["slack", "github"]

    def test_to_dict_contains_all_keys(self):
        req = RetrievalRequest(query_text="test", sources=["slack"])
        d = req.to_dict()
        assert "query_text" in d
        assert "entities" in d
        assert "relation_hints" in d
        assert "temporal_filter" in d
        assert "sources" in d
        assert "limit" in d
        assert "sort_order" in d

    def test_blank_entity_hints_stripped(self):
        req = RetrievalRequest(entities=["  ", "arun_sharma", ""])
        assert req.entities == ["arun_sharma"]


# ─────────────────────────────────────────────────────────────────────────────
# 10. Entity filtering
# ─────────────────────────────────────────────────────────────────────────────


class TestEntityFilter:
    def test_filter_by_canonical_subject(self):
        req = _default_request(entities=["arun_sharma"])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert all(
            r.subject == "arun_sharma" or r.object == "arun_sharma"
            for r in result
        )

    def test_filter_by_display_name(self):
        req = _default_request(entities=["Priya Nair"])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) > 0
        assert all(
            (r.subject_display and r.subject_display.lower() == "priya nair")
            or (r.object_display and r.object_display.lower() == "priya nair")
            or r.subject.lower() == "priya nair"
            or r.object.lower() == "priya nair"
            for r in result
        )

    def test_empty_entities_no_filter_applied(self):
        req = _default_request(entities=[])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) == len(SAMPLE_RECORDS)

    def test_nonexistent_entity_returns_empty(self):
        req = _default_request(entities=["nonexistent_entity_xyz"])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 11. Relation hint filtering
# ─────────────────────────────────────────────────────────────────────────────


class TestRelationFilter:
    def test_filter_by_exact_relation(self):
        req = _default_request(relation_hints=["ADVOCATED_FOR"])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) > 0
        assert all(r.relation == "ADVOCATED_FOR" for r in result)

    def test_relation_filter_case_insensitive_normalised(self):
        req = _default_request(relation_hints=["advocated_for"])
        result_lower = _engine().apply(SAMPLE_RECORDS, req)
        req2 = _default_request(relation_hints=["ADVOCATED_FOR"])
        result_upper = _engine().apply(SAMPLE_RECORDS, req2)
        assert [r.triple_id for r in result_lower] == [r.triple_id for r in result_upper]

    def test_empty_relation_hints_no_filter(self):
        req = _default_request(relation_hints=[])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) == len(SAMPLE_RECORDS)


# ─────────────────────────────────────────────────────────────────────────────
# 12. Combined entity + temporal filter
# ─────────────────────────────────────────────────────────────────────────────


class TestCombinedFilters:
    def test_entity_and_date_range(self):
        req = RetrievalRequest(
            entities=["arun_sharma"],
            temporal_filter=TemporalFilter(
                start_date=date(2023, 1, 1),
                end_date=date(2023, 12, 31),
            ),
            limit=100,
        )
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) > 0
        for r in result:
            assert date(2023, 1, 1) <= r.event_date <= date(2023, 12, 31)
            assert "arun_sharma" in (r.subject, r.object)

    def test_source_and_temporal(self):
        req = RetrievalRequest(
            sources=["slack"],
            temporal_filter=TemporalFilter(after_date=date(2023, 1, 1)),
            limit=100,
        )
        result = _engine().apply(SAMPLE_RECORDS, req)
        for r in result:
            assert r.source == "slack"
            assert r.event_date > date(2023, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 13. Limit enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestLimit:
    def test_limit_caps_results(self):
        req = _default_request(limit=2)
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) <= 2

    def test_limit_1_returns_exactly_one(self):
        req = _default_request(limit=1)
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) == 1

    def test_limit_larger_than_pool_returns_all(self):
        req = _default_request(limit=1000)
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) == len(SAMPLE_RECORDS)


# ─────────────────────────────────────────────────────────────────────────────
# 14. SortOrder.DESC ordering
# ─────────────────────────────────────────────────────────────────────────────


class TestSortOrderDesc:
    def test_desc_result_starts_with_latest_date(self):
        req = _default_request(sort_order=SortOrder.DESC)
        result = _engine().apply(SAMPLE_RECORDS, req)
        dates = [r.event_date for r in result]
        assert dates == sorted(dates, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# 15. TemporalFilter mode detection
# ─────────────────────────────────────────────────────────────────────────────


class TestTemporalFilterMode:
    def test_none_mode_when_no_fields_set(self):
        tf = TemporalFilter()
        assert tf.mode == TemporalFilterMode.NONE

    def test_exact_mode_when_exact_date_set(self):
        tf = TemporalFilter(exact_date=date(2023, 1, 1))
        assert tf.mode == TemporalFilterMode.EXACT

    def test_range_mode_when_start_and_end_set(self):
        tf = TemporalFilter(start_date=date(2023, 1, 1), end_date=date(2023, 12, 31))
        assert tf.mode == TemporalFilterMode.RANGE

    def test_range_mode_when_only_start_set(self):
        tf = TemporalFilter(start_date=date(2023, 1, 1))
        assert tf.mode == TemporalFilterMode.RANGE

    def test_range_mode_when_only_end_set(self):
        tf = TemporalFilter(end_date=date(2023, 12, 31))
        assert tf.mode == TemporalFilterMode.RANGE

    def test_before_mode(self):
        tf = TemporalFilter(before_date=date(2023, 6, 1))
        assert tf.mode == TemporalFilterMode.BEFORE

    def test_after_mode(self):
        tf = TemporalFilter(after_date=date(2023, 1, 1))
        assert tf.mode == TemporalFilterMode.AFTER

    def test_to_dict_mode_included(self):
        tf = TemporalFilter(start_date=date(2023, 1, 1), end_date=date(2023, 6, 1))
        d = tf.to_dict()
        assert d["mode"] == "range"
        assert d["start_date"] == "2023-01-01"
        assert d["end_date"] == "2023-06-01"
        assert d["exact_date"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 16. RetrievalRecordBuilder — builds records from mock graph_ready_triples
# ─────────────────────────────────────────────────────────────────────────────


MOCK_GRAPH_READY_TRIPLES: List[Dict[str, Any]] = [
    {
        "triple_id": "11111111-0000-0000-0000-000000000001",
        "subject": "arun_sharma",
        "subject_display": "Arun Sharma",
        "subject_type": "Person",
        "relation": "ADVOCATED_FOR",
        "object": "gcp",
        "object_display": "GCP",
        "object_type": "Technology",
        "timestamp": "2023-03-15T10:30:00+00:00",
        "source": "slack",
        "source_id": "slack_001",
        "evidence": "Arun suggested moving services to GCP.",
        "confidence": 0.9,
        "extraction_mode": "llm_groq",
        "metadata": {},
    },
    {
        "triple_id": "11111111-0000-0000-0000-000000000002",
        "subject": "priya_nair",
        "subject_display": "Priya Nair",
        "subject_type": "Person",
        "relation": "REVIEWED",
        "object": "auth_service",
        "object_display": "Auth Service",
        "object_type": "Service",
        "timestamp": "2023-04-01T09:00:00+00:00",
        "source": "github",
        "source_id": "github_pr_007",
        "evidence": "Priya reviewed the auth service PR.",
        "confidence": 0.85,
        "extraction_mode": "fallback",
        "metadata": {"html_url": "https://github.com/org/repo/pull/7"},
    },
    {
        "triple_id": "11111111-0000-0000-0000-000000000003",
        "subject": "ravi_kumar",
        "subject_display": "Ravi Kumar",
        "subject_type": "Person",
        "relation": "ASSIGNED_TO",
        "object": "cg-101",
        "object_display": "CG-101",
        "object_type": "Issue",
        "timestamp": "2022-11-20T08:00:00+00:00",
        "source": "jira",
        "source_id": "jira_001",
        "evidence": "Ravi was assigned CG-101.",
        "confidence": 0.75,
        "extraction_mode": "mock",
        "metadata": {},
    },
]


class TestRetrievalRecordBuilder:
    def test_build_returns_correct_count(self, tmp_path):
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, report, _meta = builder.build()

        assert report["total_input"] == 3
        assert report["records_built"] == 3
        assert report["records_skipped"] == 0
        assert len(records) == 3

    def test_built_records_preserve_timestamps(self, tmp_path):
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, _, _meta = builder.build()

        expected_ts = {
            "11111111-0000-0000-0000-000000000001": "2023-03-15T10:30:00+00:00",
            "11111111-0000-0000-0000-000000000002": "2023-04-01T09:00:00+00:00",
            "11111111-0000-0000-0000-000000000003": "2022-11-20T08:00:00+00:00",
        }
        for r in records:
            assert r.timestamp == expected_ts[r.triple_id]

    def test_event_dates_correctly_parsed(self, tmp_path):
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, _, _meta = builder.build()

        dates_by_id = {r.triple_id: r.event_date for r in records}
        assert dates_by_id["11111111-0000-0000-0000-000000000001"] == date(2023, 3, 15)
        assert dates_by_id["11111111-0000-0000-0000-000000000002"] == date(2023, 4, 1)
        assert dates_by_id["11111111-0000-0000-0000-000000000003"] == date(2022, 11, 20)

    def test_output_file_written(self, tmp_path):
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        builder.build()

        assert output_file.exists()
        data = json.loads(output_file.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 3

    def test_output_event_date_serialized_as_iso(self, tmp_path):
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        builder.build()

        data = json.loads(output_file.read_text(encoding="utf-8"))
        for record_dict in data:
            # event_date should be a string like "2023-03-15"
            assert isinstance(record_dict["event_date"], str)
            # Should be parseable
            date.fromisoformat(record_dict["event_date"])


# ─────────────────────────────────────────────────────────────────────────────
# 17. Builder skips malformed triples safely
# ─────────────────────────────────────────────────────────────────────────────


class TestBuilderSkipsMalformed:
    def test_skips_triple_with_invalid_timestamp(self, tmp_path):
        bad_triple = copy.deepcopy(MOCK_GRAPH_READY_TRIPLES[0])
        bad_triple["triple_id"] = "bad-ts-triple"
        bad_triple["timestamp"] = "not-a-timestamp"

        triples = MOCK_GRAPH_READY_TRIPLES + [bad_triple]
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(triples), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, report, _meta = builder.build()

        # 3 good, 1 bad = 3 built, 1 skipped
        assert report["records_built"] == 3
        assert report["records_skipped"] == 1
        assert any(s["triple_id"] == "bad-ts-triple" for s in report["skipped_details"])

    def test_does_not_crash_on_all_malformed(self, tmp_path):
        bad_triples = [
            {"triple_id": "x1", "timestamp": "bad", "subject": "a"},  # missing many fields
        ]
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(bad_triples), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, report, _meta = builder.build()

        assert records == []
        assert report["records_skipped"] == 1

    def test_missing_input_file_raises_file_not_found(self, tmp_path):
        builder = RetrievalRecordBuilder(
            input_path=tmp_path / "nonexistent.json",
            output_path=tmp_path / "out.json",
        )
        with pytest.raises(FileNotFoundError):
            builder.build()


# ─────────────────────────────────────────────────────────────────────────────
# 18. source_url extraction from metadata
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceUrlExtraction:
    def test_source_url_from_html_url_metadata(self, tmp_path):
        triple = copy.deepcopy(MOCK_GRAPH_READY_TRIPLES[1])
        # metadata has html_url key
        triple["metadata"] = {"html_url": "https://github.com/org/repo/pull/7"}
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps([triple]), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, _, _meta = builder.build()

        assert len(records) == 1
        assert records[0].source_url == "https://github.com/org/repo/pull/7"

    def test_source_url_none_when_no_metadata(self, tmp_path):
        triple = copy.deepcopy(MOCK_GRAPH_READY_TRIPLES[0])
        triple["metadata"] = {}
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps([triple]), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, _, _meta = builder.build()

        assert len(records) == 1
        assert records[0].source_url is None

    def test_source_url_from_permalink_key(self, tmp_path):
        triple = copy.deepcopy(MOCK_GRAPH_READY_TRIPLES[0])
        triple["metadata"] = {"permalink": "https://slack.com/archives/C001/p1234"}
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps([triple]), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, _, _meta = builder.build()

        assert records[0].source_url == "https://slack.com/archives/C001/p1234"


# ─────────────────────────────────────────────────────────────────────────────
# 19. source_label property
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceLabel:
    def test_unknown_source_capitalized(self):
        r = make_record(source="teams", source_id="teams_001")
        # unknown source → capitalized fallback
        assert "teams_001" in r.source_label

    def test_all_three_known_sources(self):
        for src, expected_prefix in [
            ("slack", "Slack message"),
            ("github", "GitHub PR"),
            ("jira", "Jira ticket"),
        ]:
            r = make_record(source=src, source_id=f"{src}_99")
            assert r.source_label.startswith(expected_prefix)


# ─────────────────────────────────────────────────────────────────────────────
# 20. RetrievalRequest.to_dict serialization
# ─────────────────────────────────────────────────────────────────────────────


class TestRetrievalRequestToDict:
    def test_to_dict_round_trip(self):
        req = RetrievalRequest(
            query_text="When did Arun advocate for GCP?",
            entities=["arun_sharma"],
            relation_hints=["ADVOCATED_FOR"],
            temporal_filter=TemporalFilter(start_date=date(2023, 1, 1)),
            sources=["slack"],
            limit=10,
            sort_order=SortOrder.DESC,
        )
        d = req.to_dict()
        assert d["query_text"] == "When did Arun advocate for GCP?"
        assert d["entities"] == ["arun_sharma"]
        assert d["relation_hints"] == ["ADVOCATED_FOR"]
        assert d["temporal_filter"]["mode"] == "range"
        assert d["sources"] == ["slack"]
        assert d["limit"] == 10
        assert d["sort_order"] == "desc"


# ─────────────────────────────────────────────────────────────────────────────
# 21. TemporalFilter.to_dict serialization
# ─────────────────────────────────────────────────────────────────────────────


class TestTemporalFilterToDict:
    def test_none_filter_to_dict(self):
        d = TemporalFilter().to_dict()
        assert d["mode"] == "none"
        assert d["exact_date"] is None
        assert d["start_date"] is None
        assert d["end_date"] is None
        assert d["before_date"] is None
        assert d["after_date"] is None

    def test_before_filter_to_dict(self):
        d = TemporalFilter(before_date=date(2023, 6, 1)).to_dict()
        assert d["mode"] == "before"
        assert d["before_date"] == "2023-06-01"


# ─────────────────────────────────────────────────────────────────────────────
# 22. RetrievalRecord.to_dict event_date serialization
# ─────────────────────────────────────────────────────────────────────────────


class TestRetrievalRecordToDict:
    def test_event_date_is_iso_string_in_dict(self):
        r = make_record(event_date=date(2023, 3, 15))
        d = r.to_dict()
        assert d["event_date"] == "2023-03-15"
        assert isinstance(d["event_date"], str)

    def test_all_expected_keys_present(self):
        r = make_record()
        d = r.to_dict()
        required = [
            "record_id", "triple_id", "subject", "relation", "object",
            "timestamp", "event_date", "source", "source_id", "evidence",
            "confidence",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"


# ─────────────────────────────────────────────────────────────────────────────
# 23. NONE temporal filter returns all records
# ─────────────────────────────────────────────────────────────────────────────


class TestNoneFilter:
    def test_none_filter_returns_all(self):
        tf = TemporalFilter()
        result = _engine().apply_temporal_filter(SAMPLE_RECORDS, tf)
        assert len(result) == len(SAMPLE_RECORDS)

    def test_request_with_no_filters_returns_all_up_to_limit(self):
        req = RetrievalRequest(limit=100)
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) == len(SAMPLE_RECORDS)


# ─────────────────────────────────────────────────────────────────────────────
# 24. Source filter
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceFilter:
    def test_slack_only_filter(self):
        req = _default_request(sources=["slack"])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert len(result) > 0
        assert all(r.source == "slack" for r in result)

    def test_multiple_sources(self):
        req = _default_request(sources=["slack", "github"])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert all(r.source in ("slack", "github") for r in result)

    def test_jira_only(self):
        req = _default_request(sources=["jira"])
        result = _engine().apply(SAMPLE_RECORDS, req)
        assert all(r.source == "jira" for r in result)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: builder output feeds into filter engine
# ─────────────────────────────────────────────────────────────────────────────


class TestBuilderToFilterIntegration:
    def test_built_records_can_be_filtered_by_date_range(self, tmp_path):
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, _, _meta = builder.build()

        req = RetrievalRequest(
            temporal_filter=TemporalFilter(start_date=date(2023, 1, 1)),
            limit=100,
        )
        result = _engine().apply(records, req)
        assert all(r.event_date >= date(2023, 1, 1) for r in result)
        # 2022 record should be excluded
        assert all(r.triple_id != "11111111-0000-0000-0000-000000000003" for r in result)

    def test_built_records_sorted_chronologically(self, tmp_path):
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, _, _meta = builder.build()

        req = RetrievalRequest(sort_order=SortOrder.ASC, limit=100)
        result = _engine().apply(records, req)

        dates = [r.event_date for r in result]
        assert dates == sorted(dates)


# ─────────────────────────────────────────────────────────────────────────────
# 26. PipelineExecutionMetadata — model, serialisation, and builder integration
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineExecutionMetadata:
    """Tests for the PipelineExecutionMetadata model and builder integration."""

    # ── Model construction ───────────────────────────────────────────────────

    def test_basic_construction(self):
        """Metadata can be constructed with required fields."""
        meta = PipelineExecutionMetadata(
            input_source="/data/processed/graph_ready_triples.json",
            total_records=100,
            records_built=95,
            skipped_records=5,
        )
        assert meta.total_records == 100
        assert meta.records_built == 95
        assert meta.skipped_records == 5
        assert meta.input_source == "/data/processed/graph_ready_triples.json"

    def test_default_pipeline_name(self):
        """Default pipeline_name contains expected Week 3 identifier."""
        meta = PipelineExecutionMetadata(
            input_source="/some/path.json",
            total_records=10,
            records_built=10,
            skipped_records=0,
        )
        assert "Week 3" in meta.pipeline_name
        assert "Temporal Retrieval" in meta.pipeline_name

    # ── Status auto-derivation ───────────────────────────────────────────────

    def test_status_success_when_no_skipped(self):
        """status == 'success' when skipped_records == 0."""
        meta = PipelineExecutionMetadata(
            input_source="/p.json",
            total_records=50,
            records_built=50,
            skipped_records=0,
        )
        assert meta.status == "success"

    def test_status_partial_when_skipped(self):
        """status == 'partial' when skipped_records > 0."""
        meta = PipelineExecutionMetadata(
            input_source="/p.json",
            total_records=50,
            records_built=45,
            skipped_records=5,
        )
        assert meta.status == "partial"

    def test_status_partial_all_skipped(self):
        """Even if every record is skipped, status is 'partial' (not 'failed')."""
        meta = PipelineExecutionMetadata(
            input_source="/p.json",
            total_records=10,
            records_built=0,
            skipped_records=10,
        )
        assert meta.status == "partial"

    # ── generated_at timestamp ───────────────────────────────────────────────

    def test_generated_at_is_set_by_default(self):
        """generated_at is auto-populated and is a non-empty string."""
        meta = PipelineExecutionMetadata(
            input_source="/p.json",
            total_records=1,
            records_built=1,
            skipped_records=0,
        )
        assert isinstance(meta.generated_at, str)
        assert len(meta.generated_at) > 0

    def test_generated_at_is_iso8601(self):
        """generated_at can be parsed as a valid ISO-8601 datetime."""
        meta = PipelineExecutionMetadata(
            input_source="/p.json",
            total_records=1,
            records_built=1,
            skipped_records=0,
        )
        # Should not raise
        parsed = datetime.fromisoformat(meta.generated_at)
        assert parsed is not None

    def test_generated_at_custom_value(self):
        """An explicit generated_at value is preserved."""
        ts = "2026-08-26T12:00:00+00:00"
        meta = PipelineExecutionMetadata(
            input_source="/p.json",
            total_records=1,
            records_built=1,
            skipped_records=0,
            generated_at=ts,
        )
        assert meta.generated_at == ts

    # ── to_dict serialisation ────────────────────────────────────────────────

    def test_to_dict_has_all_required_keys(self):
        """to_dict() contains all six required metadata keys."""
        meta = PipelineExecutionMetadata(
            input_source="/p.json",
            total_records=20,
            records_built=18,
            skipped_records=2,
        )
        d = meta.to_dict()
        required_keys = {
            "pipeline_name",
            "input_source",
            "total_records",
            "records_built",
            "skipped_records",
            "generated_at",
            "status",
        }
        assert required_keys.issubset(d.keys())

    def test_to_dict_values_match_model(self):
        """to_dict() values are consistent with model fields."""
        meta = PipelineExecutionMetadata(
            input_source="/data/graph_ready_triples.json",
            total_records=30,
            records_built=30,
            skipped_records=0,
        )
        d = meta.to_dict()
        assert d["total_records"] == 30
        assert d["records_built"] == 30
        assert d["skipped_records"] == 0
        assert d["status"] == "success"
        assert d["input_source"] == "/data/graph_ready_triples.json"

    def test_to_dict_is_json_serialisable(self):
        """to_dict() output can be round-tripped through json.dumps / json.loads."""
        import json
        meta = PipelineExecutionMetadata(
            input_source="/p.json",
            total_records=5,
            records_built=4,
            skipped_records=1,
        )
        serialised = json.dumps(meta.to_dict())
        restored = json.loads(serialised)
        assert restored["status"] == "partial"
        assert restored["total_records"] == 5

    # ── Builder writes summary file ──────────────────────────────────────────

    def test_builder_writes_summary_file(self, tmp_path):
        """builder.build() writes retrieval_prep_summary.json alongside the output."""
        import json
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"
        summary_file = tmp_path / "retrieval_prep_summary.json"

        builder = RetrievalRecordBuilder(
            input_path=input_file,
            output_path=output_file,
            summary_path=summary_file,
        )
        records, report, metadata = builder.build()

        assert summary_file.exists(), "retrieval_prep_summary.json was not written"

    def test_builder_summary_json_has_required_fields(self, tmp_path):
        """The written retrieval_prep_summary.json contains all required metadata fields."""
        import json
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "out.json"
        summary_file = tmp_path / "summary.json"

        builder = RetrievalRecordBuilder(
            input_path=input_file,
            output_path=output_file,
            summary_path=summary_file,
        )
        records, report, metadata = builder.build()

        with open(summary_file, encoding="utf-8") as fh:
            data = json.load(fh)

        for key in ("pipeline_name", "input_source", "total_records",
                    "records_built", "skipped_records", "generated_at", "status"):
            assert key in data, f"Missing key in summary JSON: {key!r}"

    def test_builder_summary_total_records_matches_input(self, tmp_path):
        """total_records in the summary equals the number of graph-ready triples loaded."""
        import json
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        records, report, metadata = builder.build()

        assert metadata.total_records == len(MOCK_GRAPH_READY_TRIPLES)
        assert metadata.records_built == len(records)
        assert metadata.skipped_records == report["records_skipped"]

    def test_builder_summary_status_success_on_clean_input(self, tmp_path):
        """A clean input (no malformed triples) yields status='success'."""
        import json
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        _records, _report, metadata = builder.build()

        assert metadata.status == "success"
        assert metadata.skipped_records == 0

    def test_builder_summary_status_partial_on_bad_input(self, tmp_path):
        """Malformed triples increment skipped_records and set status='partial'."""
        import json
        bad_triple = {"triple_id": "", "subject": ""}  # deliberately invalid
        triples = MOCK_GRAPH_READY_TRIPLES + [bad_triple]
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(triples), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        _records, _report, metadata = builder.build()

        assert metadata.skipped_records >= 1
        assert metadata.status == "partial"

    def test_builder_default_summary_path_placement(self, tmp_path):
        """When summary_path is omitted, the file lands next to the output file."""
        import json
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        _records, _report, _meta = builder.build()

        expected_summary = tmp_path / "retrieval_prep_summary.json"
        assert expected_summary.exists(), (
            f"Expected summary at {expected_summary} but it was not created."
        )

    def test_builder_returns_metadata_object(self, tmp_path):
        """builder.build() third return value is a PipelineExecutionMetadata instance."""
        import json
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        _records, _report, metadata = builder.build()

        assert isinstance(metadata, PipelineExecutionMetadata)

    def test_builder_data_contract_unchanged(self, tmp_path):
        """retrieval_ready_records.json must NOT contain any metadata fields."""
        import json
        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "out.json"

        builder = RetrievalRecordBuilder(input_path=input_file, output_path=output_file)
        builder.build()

        with open(output_file, encoding="utf-8") as fh:
            records_json = json.load(fh)

        # Must be a flat JSON array of record objects
        assert isinstance(records_json, list)
        for rec in records_json:
            # Metadata fields must NOT appear inside individual records
            assert "pipeline_name" not in rec
            assert "generated_at" not in rec
            assert "total_records" not in rec
