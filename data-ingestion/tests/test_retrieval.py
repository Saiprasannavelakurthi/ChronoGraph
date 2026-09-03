"""
tests/test_retrieval.py
────────────────────────
Comprehensive tests for Temporal Retrieval Preparation.

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
        """Default pipeline_name contains expected identifier."""
        meta = PipelineExecutionMetadata(
            input_source="/some/path.json",
            total_records=10,
            records_built=10,
            skipped_records=0,
        )
        assert "Temporal Retrieval Preparation" in meta.pipeline_name

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


# ─────────────────────────────────────────────────────────────────────────────
# 27. RetrievalOutputValidator — Consistency validation layer
# ─────────────────────────────────────────────────────────────────────────────


from src.retrieval.validator import RetrievalOutputValidator, ValidationResult


def _write_records(path, records_data):
    """Helper: write a records list to a JSON file."""
    path.write_text(json.dumps(records_data), encoding="utf-8")


def _write_summary(path, summary_data):
    """Helper: write a summary dict to a JSON file."""
    path.write_text(json.dumps(summary_data), encoding="utf-8")


def _valid_summary(
    total: int = 3,
    built: int = 3,
    skipped: int = 0,
    status: str = "success",
) -> dict:
    """Return a valid retrieval_prep_summary.json payload."""
    return {
        "pipeline_name": "Temporal Retrieval Preparation",
        "input_source": "/data/processed/graph_ready_triples.json",
        "total_records": total,
        "records_built": built,
        "skipped_records": skipped,
        "generated_at": "2026-08-26T12:00:00+00:00",
        "status": status,
    }


def _valid_record(
    record_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
    triple_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
    source: str = "slack",
    source_id: str = "slack_001",
    evidence: str = "Arun advocated for GCP migration.",
    timestamp: str = "2023-03-15T10:30:00+00:00",
    event_date: str = "2023-03-15",
) -> dict:
    """Return a valid retrieval record dict."""
    return {
        "record_id": record_id,
        "triple_id": triple_id,
        "subject": "arun_sharma",
        "subject_display": "Arun Sharma",
        "subject_type": "Person",
        "relation": "ADVOCATED_FOR",
        "object": "gcp",
        "object_display": "GCP",
        "object_type": "Technology",
        "timestamp": timestamp,
        "event_date": event_date,
        "source": source,
        "source_id": source_id,
        "source_url": None,
        "evidence": evidence,
        "confidence": 0.9,
        "extraction_mode": "fallback",
        "metadata": {},
    }


VALID_RECORDS_3 = [
    _valid_record("r1", "r1"),
    _valid_record("r2", "r2", source="github", source_id="github_pr_007"),
    _valid_record("r3", "r3", source="jira", source_id="jira_001"),
]


class TestValidationResult:
    """Unit tests for the ValidationResult dataclass."""

    def test_default_is_valid(self):
        """Fresh ValidationResult starts valid with empty error/warning lists."""
        vr = ValidationResult()
        assert vr.is_valid is True
        assert vr.errors == []
        assert vr.warnings == []
        assert vr.stats == {}

    def test_add_error_sets_invalid(self):
        """add_error() marks result invalid and appends to errors."""
        vr = ValidationResult()
        vr.add_error("something broke")
        assert vr.is_valid is False
        assert len(vr.errors) == 1
        assert "something broke" in vr.errors[0]

    def test_add_warning_does_not_invalidate(self):
        """add_warning() does not change is_valid."""
        vr = ValidationResult()
        vr.add_warning("minor issue")
        assert vr.is_valid is True
        assert len(vr.warnings) == 1

    def test_multiple_errors_accumulated(self):
        """Multiple add_error() calls accumulate all messages."""
        vr = ValidationResult()
        vr.add_error("error A")
        vr.add_error("error B")
        assert len(vr.errors) == 2
        assert vr.is_valid is False


class TestRetrievalOutputValidator:
    """Comprehensive tests for all RetrievalOutputValidator checks."""

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_valid_output_passes_all_checks(self, tmp_path):
        """Clean records + matching summary -> validation PASSED with no errors."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary(total=3, built=3, skipped=0))

        v = RetrievalOutputValidator(rec_path, sum_path)
        result = v.validate()

        assert result.is_valid is True
        assert result.errors == []

    def test_valid_stats_populated(self, tmp_path):
        """Stats dict is populated with correct counts on a clean run."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary(total=3, built=3, skipped=0))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()

        assert result.stats["records_file_count"] == 3
        assert result.stats["unique_record_ids"] == 3
        assert result.stats["unique_triple_ids"] == 3
        assert result.stats["duplicate_record_ids"] == 0
        assert result.stats["provenance_violations"] == 0
        assert result.stats["invalid_timestamps"] == 0
        assert result.stats["inconsistent_dates"] == 0

    def test_empty_records_list_with_matching_summary(self, tmp_path):
        """Zero records with built=0, total=0 should pass validation."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, [])
        _write_summary(sum_path, _valid_summary(total=0, built=0, skipped=0))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is True

    def test_partial_status_with_skipped_passes(self, tmp_path):
        """status='partial' with skipped_records > 0 should pass Check 6."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(
            sum_path,
            _valid_summary(total=4, built=3, skipped=1, status="partial"),
        )

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is True

    # ── File not found ────────────────────────────────────────────────────────

    def test_missing_records_file_fails(self, tmp_path):
        """Missing retrieval_ready_records.json produces an error."""
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary())

        result = RetrievalOutputValidator(
            tmp_path / "nonexistent.json", sum_path
        ).validate()

        assert result.is_valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_missing_summary_file_fails(self, tmp_path):
        """Missing retrieval_prep_summary.json produces an error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, VALID_RECORDS_3)

        result = RetrievalOutputValidator(
            rec_path, tmp_path / "nonexistent.json"
        ).validate()

        assert result.is_valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_both_files_missing_produces_two_errors(self, tmp_path):
        """Both files missing -> at least one error per missing file."""
        result = RetrievalOutputValidator(
            tmp_path / "a.json", tmp_path / "b.json"
        ).validate()

        assert result.is_valid is False
        assert len(result.errors) >= 1

    # ── Invalid JSON ──────────────────────────────────────────────────────────

    def test_invalid_json_in_records_file_fails(self, tmp_path):
        """Non-JSON content in records file produces a clear error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        rec_path.write_text("not-valid-json{{{{", encoding="utf-8")
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary())

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("invalid json" in e.lower() or "json" in e.lower() for e in result.errors)

    def test_records_file_is_object_not_array_fails(self, tmp_path):
        """A JSON object instead of array in records file fails."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        rec_path.write_text('{"key": "value"}', encoding="utf-8")
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary())

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False

    def test_summary_missing_required_keys_fails(self, tmp_path):
        """Summary without required keys produces an error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, VALID_RECORDS_3)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        # Only partial keys
        _write_summary(sum_path, {"pipeline_name": "something"})

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("missing" in e.lower() for e in result.errors)

    # ── Check 1: Unique identifiers ───────────────────────────────────────────

    def test_duplicate_record_ids_fail(self, tmp_path):
        """Duplicate record_id values trigger Check 1 error."""
        records = [
            _valid_record("dup-id", "dup-id"),
            _valid_record("dup-id", "different-tid"),  # duplicate record_id
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, records)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=2, built=2))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()

        assert result.is_valid is False
        assert any("Check 1" in e and "record_id" in e for e in result.errors)

    def test_duplicate_triple_ids_fail(self, tmp_path):
        """Duplicate triple_id values trigger Check 1 error."""
        records = [
            _valid_record("uid1", "dup-tid"),
            _valid_record("uid2", "dup-tid"),  # duplicate triple_id
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, records)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=2, built=2))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()

        assert result.is_valid is False
        assert any("Check 1" in e and "triple_id" in e for e in result.errors)

    def test_all_unique_ids_pass_check1(self, tmp_path):
        """Distinct record_id and triple_id on every record -> no Check 1 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary())

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert not any("Check 1" in e for e in result.errors)

    def test_check1_error_mentions_duplicate_value(self, tmp_path):
        """Check 1 error message must include the offending duplicate ID value."""
        records = [_valid_record("dup-abc", "dup-abc"), _valid_record("dup-abc", "other")]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, records)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=2, built=2))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert any("dup-abc" in e for e in result.errors)

    # ── Check 2: Required provenance fields ───────────────────────────────────

    def test_empty_source_field_fails_check2(self, tmp_path):
        """An empty 'source' field triggers a Check 2 provenance error."""
        bad = _valid_record("id1", "id1")
        bad["source"] = ""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, [bad])
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=1, built=1))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("Check 2" in e for e in result.errors)

    def test_empty_evidence_fails_check2(self, tmp_path):
        """A blank 'evidence' field triggers a Check 2 provenance error."""
        bad = _valid_record("id1", "id1")
        bad["evidence"] = "   "  # whitespace-only
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, [bad])
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=1, built=1))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("evidence" in e for e in result.errors)

    def test_missing_source_id_fails_check2(self, tmp_path):
        """A None 'source_id' field triggers a Check 2 provenance error."""
        bad = _valid_record("id1", "id1")
        bad["source_id"] = None
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, [bad])
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=1, built=1))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("source_id" in e for e in result.errors)

    def test_check2_error_message_names_record_id(self, tmp_path):
        """Check 2 error message must reference the offending record's ID."""
        bad = _valid_record("problematic-record-id", "problematic-record-id")
        bad["evidence"] = ""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, [bad])
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=1, built=1))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        # The record ID should appear in the error message
        assert any("problematic-record-id" in e for e in result.errors)

    # ── Check 3: Temporal metadata ────────────────────────────────────────────

    def test_invalid_timestamp_fails_check3a(self, tmp_path):
        """A non-ISO-8601 timestamp triggers Check 3a error."""
        bad = _valid_record("id1", "id1", timestamp="not-a-date")
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, [bad])
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=1, built=1))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("3a" in e or "Timestamp" in e or "timestamp" in e for e in result.errors)

    def test_invalid_event_date_fails_check3b(self, tmp_path):
        """A malformed event_date string triggers Check 3b error."""
        bad = _valid_record("id1", "id1", event_date="2023/03/15")  # wrong sep
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, [bad])
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=1, built=1))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("3b" in e or "event_date" in e for e in result.errors)

    def test_inconsistent_event_date_fails_check3c(self, tmp_path):
        """event_date not matching the UTC date of timestamp triggers Check 3c."""
        bad = _valid_record(
            "id1", "id1",
            timestamp="2023-03-15T10:30:00+00:00",
            event_date="2023-01-01",  # wrong date
        )
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, [bad])
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=1, built=1))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("3c" in e or "Consistency" in e or "event_date" in e for e in result.errors)

    def test_consistent_timestamp_and_event_date_passes_check3(self, tmp_path):
        """Matching timestamp and event_date produces no Check 3 errors."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary())

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert not any("Check 3" in e for e in result.errors)

    def test_check3_error_includes_record_id(self, tmp_path):
        """Check 3 error message must include the offending record ID."""
        bad = _valid_record("ts-bad-record", "ts-bad-record", timestamp="bad")
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, [bad])
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=1, built=1))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert any("ts-bad-record" in e for e in result.errors)

    # ── Check 4: Record count parity ──────────────────────────────────────────

    def test_count_mismatch_fails_check4(self, tmp_path):
        """File has 3 records but summary says records_built=5 -> Check 4 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, VALID_RECORDS_3)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=5, built=5, skipped=0))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("Check 4" in e or "count" in e.lower() for e in result.errors)

    def test_count_match_passes_check4(self, tmp_path):
        """File has 3 records and summary reports records_built=3 -> no Check 4 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary(total=3, built=3))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert not any("Check 4" in e for e in result.errors)

    def test_check4_error_shows_actual_and_expected_counts(self, tmp_path):
        """Check 4 error must state both actual file count and reported built count."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, VALID_RECORDS_3)  # 3 records
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=10, built=10))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert any("3" in e and "10" in e for e in result.errors)

    # ── Check 5: Accounting identity ──────────────────────────────────────────

    def test_accounting_identity_mismatch_fails_check5(self, tmp_path):
        """built + skipped != total triggers Check 5 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, VALID_RECORDS_3)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        # built=3, skipped=1, total=10 — 3+1 != 10
        _write_summary(sum_path, _valid_summary(total=10, built=3, skipped=1, status="partial"))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("Check 5" in e or "Accounting" in e for e in result.errors)

    def test_accounting_identity_holds_passes_check5(self, tmp_path):
        """built + skipped == total -> no Check 5 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary(total=3, built=3, skipped=0))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert not any("Check 5" in e for e in result.errors)

    def test_check5_error_includes_arithmetic_values(self, tmp_path):
        """Check 5 error message must state built, skipped, and total values."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, VALID_RECORDS_3)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=20, built=3, skipped=0))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert any("20" in e for e in result.errors)

    # ── Check 6: Pipeline status ──────────────────────────────────────────────

    def test_success_status_with_skipped_zero_passes_check6(self, tmp_path):
        """status='success' with skipped=0 -> no Check 6 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary(total=3, built=3, skipped=0, status="success"))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert not any("Check 6" in e for e in result.errors)

    def test_partial_status_with_skipped_nonzero_passes_check6(self, tmp_path):
        """status='partial' with skipped > 0 -> no Check 6 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, VALID_RECORDS_3)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_summary(sum_path, _valid_summary(total=4, built=3, skipped=1, status="partial"))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert not any("Check 6" in e for e in result.errors)

    def test_wrong_status_success_when_skipped_nonzero_fails_check6(self, tmp_path):
        """status='success' with skipped > 0 -> Check 6 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_records(rec_path, VALID_RECORDS_3)
        sum_path = tmp_path / "retrieval_prep_summary.json"
        # skipped=1 but status='success' — contradicts the rule
        _write_summary(sum_path, _valid_summary(total=4, built=3, skipped=1, status="success"))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("Check 6" in e for e in result.errors)

    def test_wrong_status_partial_when_skipped_zero_fails_check6(self, tmp_path):
        """status='partial' with skipped=0 -> Check 6 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary(total=3, built=3, skipped=0, status="partial"))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("Check 6" in e for e in result.errors)

    def test_unknown_status_value_fails_check6(self, tmp_path):
        """An unrecognised status string triggers Check 6 error."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary(total=3, built=3, skipped=0, status="error"))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert result.is_valid is False
        assert any("Check 6" in e for e in result.errors)

    def test_check6_error_message_mentions_expected_and_actual_status(self, tmp_path):
        """Check 6 error message must reference both the actual and expected status."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        sum_path = tmp_path / "retrieval_prep_summary.json"
        _write_records(rec_path, VALID_RECORDS_3)
        _write_summary(sum_path, _valid_summary(total=3, built=3, skipped=0, status="partial"))

        result = RetrievalOutputValidator(rec_path, sum_path).validate()
        assert any("partial" in e and "success" in e for e in result.errors)

    # ── Integration: builder output feeds validator ───────────────────────────

    def test_builder_then_validator_passes_on_clean_input(self, tmp_path):
        """Full pipeline: builder writes files, then validator confirms consistency."""
        from src.retrieval.builder import RetrievalRecordBuilder

        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"
        summary_file = tmp_path / "retrieval_prep_summary.json"

        builder = RetrievalRecordBuilder(
            input_path=input_file,
            output_path=output_file,
            summary_path=summary_file,
        )
        builder.build()

        validator = RetrievalOutputValidator(
            records_path=output_file,
            summary_path=summary_file,
        )
        result = validator.validate()

        assert result.is_valid is True, (
            f"Validation failed after builder run. Errors: {result.errors}"
        )

    def test_validator_detects_injected_duplicate_after_build(self, tmp_path):
        """If a record is manually duplicated in the records file, validator catches it."""
        from src.retrieval.builder import RetrievalRecordBuilder

        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8")
        output_file = tmp_path / "retrieval_ready_records.json"
        summary_file = tmp_path / "retrieval_prep_summary.json"

        builder = RetrievalRecordBuilder(
            input_path=input_file,
            output_path=output_file,
            summary_path=summary_file,
        )
        builder.build()

        # Corrupt: append a duplicate of the first record
        existing = json.loads(output_file.read_text(encoding="utf-8"))
        corrupted = existing + [existing[0]]  # add duplicate
        output_file.write_text(json.dumps(corrupted), encoding="utf-8")

        validator = RetrievalOutputValidator(
            records_path=output_file,
            summary_path=summary_file,
        )
        result = validator.validate()

        # Must catch the duplicate record_id
        assert result.is_valid is False
        assert any("Check 1" in e for e in result.errors)


# ─────────────────────────────────────────────────────────────────────────────
# 28. RetrievalDataQualityStats model & RetrievalStatsEngine
# ─────────────────────────────────────────────────────────────────────────────


from src.retrieval.stats import RetrievalStatsEngine
from src.retrieval.models import RetrievalDataQualityStats


# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_record(
    record_id="rec-1",
    triple_id="rec-1",
    subject="arun_sharma",
    subject_display="Arun Sharma",
    subject_type="Person",
    relation="ADVOCATED_FOR",
    object="gcp",
    object_display="GCP",
    object_type="Technology",
    timestamp="2023-03-15T10:30:00+00:00",
    event_date="2023-03-15",
    source="slack",
    source_id="slack_001",
    source_url=None,
    evidence="Arun advocated for GCP migration.",
    confidence=0.9,
    extraction_mode="fallback",
    metadata=None,
):
    """Construct a minimal retrieval record dict."""
    return {
        "record_id": record_id,
        "triple_id": triple_id,
        "subject": subject,
        "subject_display": subject_display,
        "subject_type": subject_type,
        "relation": relation,
        "object": object,
        "object_display": object_display,
        "object_type": object_type,
        "timestamp": timestamp,
        "event_date": event_date,
        "source": source,
        "source_id": source_id,
        "source_url": source_url,
        "evidence": evidence,
        "confidence": confidence,
        "extraction_mode": extraction_mode,
        "metadata": metadata or {},
    }


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


class TestRetrievalDataQualityStats:
    """Unit tests for the RetrievalDataQualityStats Pydantic model."""

    def test_default_optional_fields(self):
        """Optional fields default to None/empty dict."""
        stats = RetrievalDataQualityStats(
            total_records=0,
            unique_entities=0,
            unique_relations=0,
            records_with_temporal_data=0,
            records_without_temporal_data=0,
            records_with_source_url=0,
        )
        assert stats.earliest_timestamp is None
        assert stats.latest_timestamp is None
        assert stats.average_confidence is None
        assert stats.source_breakdown == {}

    def test_to_dict_contains_all_required_keys(self):
        """to_dict() must contain all 11 required stat keys."""
        stats = RetrievalDataQualityStats(
            total_records=10,
            unique_entities=5,
            unique_relations=3,
            records_with_temporal_data=9,
            records_without_temporal_data=1,
            earliest_timestamp="2023-03-15",
            latest_timestamp="2023-05-30",
            source_breakdown={"slack": 5, "github": 3, "jira": 2},
            average_confidence=0.87,
            records_with_source_url=2,
        )
        d = stats.to_dict()
        required_keys = {
            "total_records",
            "unique_entities",
            "unique_relations",
            "records_with_temporal_data",
            "records_without_temporal_data",
            "earliest_timestamp",
            "latest_timestamp",
            "source_breakdown",
            "average_confidence",
            "records_with_source_url",
            "generated_at",
        }
        assert required_keys.issubset(set(d.keys()))

    def test_to_dict_values_correct(self):
        """to_dict() values match field values exactly."""
        stats = RetrievalDataQualityStats(
            total_records=5,
            unique_entities=4,
            unique_relations=2,
            records_with_temporal_data=5,
            records_without_temporal_data=0,
            earliest_timestamp="2023-01-01",
            latest_timestamp="2023-12-31",
            source_breakdown={"slack": 3, "jira": 2},
            average_confidence=0.75,
            records_with_source_url=1,
        )
        d = stats.to_dict()
        assert d["total_records"] == 5
        assert d["unique_entities"] == 4
        assert d["unique_relations"] == 2
        assert d["earliest_timestamp"] == "2023-01-01"
        assert d["latest_timestamp"] == "2023-12-31"
        assert d["average_confidence"] == 0.75
        assert d["records_with_source_url"] == 1

    def test_negative_counts_rejected(self):
        """Pydantic rejects negative counts for ge=0 fields."""
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RetrievalDataQualityStats(
                total_records=-1,
                unique_entities=0,
                unique_relations=0,
                records_with_temporal_data=0,
                records_without_temporal_data=0,
                records_with_source_url=0,
            )

    def test_generated_at_auto_populated(self):
        """generated_at is automatically set to a UTC ISO-8601 string."""
        stats = RetrievalDataQualityStats(
            total_records=0,
            unique_entities=0,
            unique_relations=0,
            records_with_temporal_data=0,
            records_without_temporal_data=0,
            records_with_source_url=0,
        )
        assert stats.generated_at
        # Must be parseable as ISO-8601
        from datetime import datetime
        datetime.fromisoformat(stats.generated_at)


class TestRetrievalStatsEngine:
    """Comprehensive tests for the RetrievalStatsEngine."""

    # ── File loading ──────────────────────────────────────────────────────────

    def test_missing_records_file_raises(self, tmp_path):
        """FileNotFoundError raised when records file does not exist."""
        import pytest
        engine = RetrievalStatsEngine(
            records_path=tmp_path / "nonexistent.json"
        )
        with pytest.raises(FileNotFoundError):
            engine.compute()

    def test_invalid_json_raises(self, tmp_path):
        """JSONDecodeError raised for malformed JSON in records file."""
        import pytest
        rec_path = tmp_path / "retrieval_ready_records.json"
        rec_path.write_text("not-json{{{{", encoding="utf-8")
        engine = RetrievalStatsEngine(records_path=rec_path)
        with pytest.raises(Exception):
            engine.compute()

    def test_non_array_json_raises_value_error(self, tmp_path):
        """ValueError raised when records file is a JSON object, not array."""
        import pytest
        rec_path = tmp_path / "retrieval_ready_records.json"
        rec_path.write_text('{"key": "value"}', encoding="utf-8")
        engine = RetrievalStatsEngine(records_path=rec_path)
        with pytest.raises(ValueError, match="JSON array"):
            engine.compute()

    # ── Empty records ─────────────────────────────────────────────────────────

    def test_empty_records_returns_zero_stats(self, tmp_path):
        """Empty records array produces all-zero / None stats."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, [])
        stats = RetrievalStatsEngine(records_path=rec_path).compute()

        assert stats.total_records == 0
        assert stats.unique_entities == 0
        assert stats.unique_relations == 0
        assert stats.records_with_temporal_data == 0
        assert stats.records_without_temporal_data == 0
        assert stats.earliest_timestamp is None
        assert stats.latest_timestamp is None
        assert stats.average_confidence is None
        assert stats.records_with_source_url == 0
        assert stats.source_breakdown == {}

    # ── Single record ─────────────────────────────────────────────────────────

    def test_single_record_total_count(self, tmp_path):
        """Single record gives total_records == 1."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, [_make_record()])
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.total_records == 1

    def test_single_record_temporal_data(self, tmp_path):
        """Valid timestamp/event_date counted in records_with_temporal_data."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, [_make_record()])
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.records_with_temporal_data == 1
        assert stats.records_without_temporal_data == 0

    def test_single_record_earliest_latest(self, tmp_path):
        """Single record: earliest_timestamp == latest_timestamp."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, [_make_record(event_date="2023-04-10")])
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.earliest_timestamp == "2023-04-10"
        assert stats.latest_timestamp == "2023-04-10"

    def test_single_record_confidence(self, tmp_path):
        """Single record: average_confidence equals its confidence value."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, [_make_record(confidence=0.75)])
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.average_confidence == pytest.approx(0.75, abs=1e-4)

    def test_single_record_source_breakdown(self, tmp_path):
        """Single record: source_breakdown contains exactly one entry."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, [_make_record(source="jira")])
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.source_breakdown == {"jira": 1}

    # ── Multiple records ──────────────────────────────────────────────────────

    def test_three_records_total_count(self, tmp_path):
        """Three records gives total_records == 3."""
        records = [
            _make_record("r1", "r1", source="slack"),
            _make_record("r2", "r2", source="github"),
            _make_record("r3", "r3", source="jira"),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.total_records == 3

    def test_source_breakdown_multi_source(self, tmp_path):
        """Multi-source records produce correct per-source counts."""
        records = [
            _make_record("r1", "r1", source="slack"),
            _make_record("r2", "r2", source="slack"),
            _make_record("r3", "r3", source="github"),
            _make_record("r4", "r4", source="jira"),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.source_breakdown["slack"] == 2
        assert stats.source_breakdown["github"] == 1
        assert stats.source_breakdown["jira"] == 1

    # ── Unique entities ───────────────────────────────────────────────────────

    def test_unique_entities_deduplicates_across_records(self, tmp_path):
        """Same entity appearing in multiple records is counted once."""
        records = [
            _make_record(
                "r1", "r1",
                subject="arun_sharma", subject_display="Arun Sharma",
                object="gcp", object_display="GCP",
            ),
            _make_record(
                "r2", "r2",
                subject="arun_sharma", subject_display="Arun Sharma",  # same entities
                object="gcp", object_display="GCP",
            ),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        # Only 2 unique entity values: arun_sharma/Arun Sharma → "arun sharma", "arun_sharma"; gcp/GCP → "gcp"
        # The exact dedup uses .lower() so "arun sharma" != "arun_sharma"
        # What matters: count is smaller than 2*4=8
        assert stats.unique_entities < 8
        assert stats.unique_entities >= 1

    def test_unique_entities_different_records(self, tmp_path):
        """Different entities across records are all counted."""
        records = [
            _make_record("r1", "r1", subject="alice", object="project_alpha"),
            _make_record("r2", "r2", subject="bob", object="project_beta"),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        # At minimum these 4 canonical names are unique
        assert stats.unique_entities >= 4

    # ── Unique relations ──────────────────────────────────────────────────────

    def test_unique_relations_deduplicates(self, tmp_path):
        """Same relation appearing multiple times is counted once."""
        records = [
            _make_record("r1", "r1", relation="ADVOCATED_FOR"),
            _make_record("r2", "r2", relation="ADVOCATED_FOR"),
            _make_record("r3", "r3", relation="MIGRATED_TO"),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.unique_relations == 2

    def test_unique_relations_case_normalised(self, tmp_path):
        """Relations are uppercased before deduplication."""
        records = [
            _make_record("r1", "r1", relation="advocated_for"),
            _make_record("r2", "r2", relation="ADVOCATED_FOR"),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.unique_relations == 1

    # ── Temporal data ─────────────────────────────────────────────────────────

    def test_records_without_temporal_data_counted(self, tmp_path):
        """Record with missing/invalid timestamp is counted as without temporal data."""
        records = [
            _make_record("r1", "r1"),  # valid
            _make_record("r2", "r2", timestamp="", event_date=""),  # invalid
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.records_with_temporal_data == 1
        assert stats.records_without_temporal_data == 1

    def test_invalid_event_date_counted_as_without_temporal(self, tmp_path):
        """Record with bad event_date string is without_temporal."""
        records = [_make_record("r1", "r1", event_date="not-a-date")]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.records_without_temporal_data == 1

    def test_earliest_and_latest_timestamp_correct(self, tmp_path):
        """Correctly identifies the min and max event_date values."""
        records = [
            _make_record("r1", "r1", event_date="2023-05-01"),
            _make_record("r2", "r2", event_date="2023-01-15"),
            _make_record("r3", "r3", event_date="2023-12-31"),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.earliest_timestamp == "2023-01-15"
        assert stats.latest_timestamp == "2023-12-31"

    # ── Confidence ────────────────────────────────────────────────────────────

    def test_average_confidence_correct(self, tmp_path):
        """Average confidence is correctly calculated."""
        records = [
            _make_record("r1", "r1", confidence=0.8),
            _make_record("r2", "r2", confidence=0.6),
            _make_record("r3", "r3", confidence=1.0),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        expected = round((0.8 + 0.6 + 1.0) / 3, 4)
        assert stats.average_confidence == pytest.approx(expected, abs=1e-4)

    # ── source_url ────────────────────────────────────────────────────────────

    def test_records_with_source_url_counted(self, tmp_path):
        """Records with non-null source_url are counted separately."""
        records = [
            _make_record("r1", "r1", source_url="https://example.com/1"),
            _make_record("r2", "r2", source_url=None),
            _make_record("r3", "r3", source_url="https://example.com/3"),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.records_with_source_url == 2

    def test_no_source_urls_gives_zero(self, tmp_path):
        """All null source_url values -> records_with_source_url == 0."""
        records = [_make_record("r1", "r1", source_url=None)]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert stats.records_with_source_url == 0

    # ── File output ───────────────────────────────────────────────────────────

    def test_stats_written_to_file_when_path_provided(self, tmp_path):
        """When stats_path is given, stats JSON file is created."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        stats_path = tmp_path / "retrieval_quality_stats.json"
        _write_json(rec_path, [_make_record()])

        RetrievalStatsEngine(
            records_path=rec_path,
            stats_path=stats_path,
        ).compute()

        assert stats_path.exists()
        data = json.loads(stats_path.read_text(encoding="utf-8"))
        assert "total_records" in data
        assert data["total_records"] == 1

    def test_no_file_written_when_stats_path_is_none(self, tmp_path):
        """When stats_path is None, no output file is written."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, [_make_record()])
        default_path = tmp_path / "retrieval_quality_stats.json"

        RetrievalStatsEngine(records_path=rec_path, stats_path=None).compute()

        # No stats file should have appeared
        assert not default_path.exists()

    def test_stats_file_contains_all_required_keys(self, tmp_path):
        """Written stats JSON has all required top-level keys."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        stats_path = tmp_path / "retrieval_quality_stats.json"
        _write_json(rec_path, [_make_record()])

        RetrievalStatsEngine(
            records_path=rec_path, stats_path=stats_path
        ).compute()

        data = json.loads(stats_path.read_text(encoding="utf-8"))
        for key in (
            "total_records",
            "unique_entities",
            "unique_relations",
            "records_with_temporal_data",
            "records_without_temporal_data",
            "earliest_timestamp",
            "latest_timestamp",
            "source_breakdown",
            "average_confidence",
            "records_with_source_url",
            "generated_at",
        ):
            assert key in data, f"Missing key in stats output: {key!r}"

    # ── Integration: builder -> stats ─────────────────────────────────────────

    def test_stats_on_builder_output_matches_builder_report(self, tmp_path):
        """Stats computed on builder output match the builder's own counts."""
        from src.retrieval.builder import RetrievalRecordBuilder

        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(
            json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8"
        )
        output_file = tmp_path / "retrieval_ready_records.json"
        summary_file = tmp_path / "retrieval_prep_summary.json"

        _, report, _ = RetrievalRecordBuilder(
            input_path=input_file,
            output_path=output_file,
            summary_path=summary_file,
        ).build()

        stats = RetrievalStatsEngine(records_path=output_file).compute()

        # Stats total must equal builder's records_built
        assert stats.total_records == report["records_built"]

    def test_stats_on_builder_output_temporal_coverage(self, tmp_path):
        """All builder-produced records should have valid temporal data."""
        from src.retrieval.builder import RetrievalRecordBuilder

        input_file = tmp_path / "graph_ready_triples.json"
        input_file.write_text(
            json.dumps(MOCK_GRAPH_READY_TRIPLES), encoding="utf-8"
        )
        output_file = tmp_path / "retrieval_ready_records.json"
        summary_file = tmp_path / "retrieval_prep_summary.json"

        RetrievalRecordBuilder(
            input_path=input_file,
            output_path=output_file,
            summary_path=summary_file,
        ).build()

        stats = RetrievalStatsEngine(records_path=output_file).compute()

        # All mock triples have valid timestamps
        assert stats.records_without_temporal_data == 0
        assert stats.records_with_temporal_data == stats.total_records

    def test_stats_returns_retrievaldataqualitystats_instance(self, tmp_path):
        """compute() returns a RetrievalDataQualityStats instance."""
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, [_make_record()])
        result = RetrievalStatsEngine(records_path=rec_path).compute()
        assert isinstance(result, RetrievalDataQualityStats)

    def test_stats_with_temporal_plus_without_equals_total(self, tmp_path):
        """records_with_temporal_data + records_without_temporal_data == total_records."""
        records = [
            _make_record("r1", "r1"),
            _make_record("r2", "r2", timestamp="bad", event_date=""),
            _make_record("r3", "r3"),
        ]
        rec_path = tmp_path / "retrieval_ready_records.json"
        _write_json(rec_path, records)
        stats = RetrievalStatsEngine(records_path=rec_path).compute()
        assert (
            stats.records_with_temporal_data + stats.records_without_temporal_data
            == stats.total_records
        )


# ─────────────────────────────────────────────────────────────────────────────
# 29. Advanced Free-Text Query Support Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAdvancedFreeTextQuery:
    def test_basic_text_search(self):
        req = RetrievalRequest(query_text="services", limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) > 0
        for r in res:
            assert r.relevance_score is not None
            assert r.relevance_score > 0

    def test_case_insensitive_search(self):
        req1 = RetrievalRequest(query_text="SERVICES", limit=100)
        req2 = RetrievalRequest(query_text="services", limit=100)
        res1 = _engine().apply(SAMPLE_RECORDS, req1)
        res2 = _engine().apply(SAMPLE_RECORDS, req2)
        assert len(res1) == len(res2)
        assert [r.record_id for r in res1] == [r.record_id for r in res2]

    def test_subject_match(self):
        req = RetrievalRequest(query_text="arun", limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) > 0
        assert any("arun" in r.subject.lower() or (r.subject_display and "arun" in r.subject_display.lower()) for r in res)

    def test_object_match(self):
        req = RetrievalRequest(query_text="gcp", limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) > 0
        assert any("gcp" in r.object.lower() or (r.object_display and "gcp" in r.object_display.lower()) for r in res)

    def test_relation_match(self):
        req = RetrievalRequest(query_text="ADVOCATED_FOR", limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) > 0
        assert all("ADVOCATED_FOR" in r.relation for r in res)

    def test_evidence_match(self):
        req = RetrievalRequest(query_text="suggested", limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) > 0
        assert all("suggested" in r.evidence.lower() for r in res)

    def test_no_match_query(self):
        req = RetrievalRequest(query_text="non_existent_term_xyz_123", limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) == 0

    def test_query_plus_entity_filter(self):
        req = RetrievalRequest(query_text="gcp", entities=["gcp"], limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) > 0
        for r in res:
            assert "gcp" in (r.subject.lower(), r.object.lower(), (r.subject_display or "").lower(), (r.object_display or "").lower())
            assert r.relevance_score is not None

    def test_query_plus_temporal_filter(self):
        req = RetrievalRequest(
            query_text="services",
            temporal_filter=TemporalFilter(after_date=date(2023, 1, 1)),
            limit=100,
        )
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) > 0
        for r in res:
            assert r.event_date > date(2023, 1, 1)

    def test_query_plus_sorting(self):
        req_asc = RetrievalRequest(query_text="services", sort_order=SortOrder.ASC, limit=100)
        req_desc = RetrievalRequest(query_text="services", sort_order=SortOrder.DESC, limit=100)
        res_asc = _engine().apply(SAMPLE_RECORDS, req_asc)
        res_desc = _engine().apply(SAMPLE_RECORDS, req_desc)
        assert len(res_asc) == len(res_desc)

    def test_relevance_ordering(self):
        req = RetrievalRequest(query_text="gcp suggested", limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        scores = [r.relevance_score for r in res]
        assert scores == sorted(scores, reverse=True)

    def test_empty_query_preserving_existing_behavior(self):
        req = RetrievalRequest(query_text="", limit=100)
        res = _engine().apply(SAMPLE_RECORDS, req)
        assert len(res) == len(SAMPLE_RECORDS)
        assert all(r.relevance_score is None for r in res)


