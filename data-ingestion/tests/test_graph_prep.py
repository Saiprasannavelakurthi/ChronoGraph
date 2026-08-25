"""
tests/test_graph_prep.py
─────────────────────────
Week 2 – Tests for Karkuvel's Data Integration & Graph-Ready Data Pipeline.

Coverage
────────
    • TripleValidator   — valid & invalid cases for all 12 required fields
    • EntityNormalizer  — canonical names, display names, technology aliases
    • RelationNormalizer — UPPER_SNAKE_CASE, synonym mapping
    • TimestampNormalizer — UTC ISO-8601 parsing & output
    • TripleDeduplicator — duplicate detection, confidence preference, counts
    • GraphPrepPipeline  — integration test with real extracted_triples.json

All Week 1 tests continue to pass (not removed or weakened).
"""

from __future__ import annotations

import json
import copy
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

# ── Imports under test ────────────────────────────────────────────────────────
from src.graph_prep.validator import TripleValidator, ValidationReport, TripleError
from src.graph_prep.normalizer import EntityNormalizer, RelationNormalizer, TimestampNormalizer
from src.graph_prep.deduplicator import TripleDeduplicator, DeduplicationReport
from src.graph_prep.pipeline import GraphPrepPipeline


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

VALID_TRIPLE: Dict[str, Any] = {
    "triple_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
    "subject": "arun_sharma",
    "subject_type": "Person",
    "relation": "ADVOCATED_FOR",
    "object": "GCP",
    "object_type": "Technology",
    "timestamp": "2023-03-15T10:30:00+00:00",
    "source": "slack",
    "source_id": "slack_001",
    "evidence": "Arun suggested moving services to GCP.",
    "confidence": 0.9,
    "extraction_mode": "llm_groq",
}


def make_triple(**overrides) -> Dict[str, Any]:
    """Return a copy of VALID_TRIPLE with the specified fields overridden."""
    t = copy.deepcopy(VALID_TRIPLE)
    t.update(overrides)
    return t


# ─────────────────────────────────────────────────────────────────────────────
# TripleValidator Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTripleValidator:
    def setup_method(self):
        self.v = TripleValidator()

    # ── Valid record ──────────────────────────────────────────────────────────

    def test_valid_triple_passes(self):
        report = self.v.validate_all([VALID_TRIPLE])
        assert report.valid_count == 1
        assert report.invalid_count == 0
        assert len(report.errors) == 0
        assert report.valid_triples == [VALID_TRIPLE]

    def test_multiple_valid_triples(self):
        triples = [make_triple(triple_id=str(uuid.uuid4())) for _ in range(5)]
        report = self.v.validate_all(triples)
        assert report.valid_count == 5
        assert report.invalid_count == 0

    # ── Required field missing ─────────────────────────────────────────────────

    @pytest.mark.parametrize("field", [
        "triple_id", "subject", "subject_type", "relation", "object",
        "object_type", "timestamp", "source", "source_id", "evidence",
        "confidence", "extraction_mode",
    ])
    def test_missing_required_field_is_invalid(self, field):
        t = make_triple()
        del t[field]
        report = self.v.validate_all([t])
        assert report.invalid_count == 1
        fields_with_errors = [e.field for e in report.errors]
        assert field in fields_with_errors

    # ── Empty string fields ────────────────────────────────────────────────────

    @pytest.mark.parametrize("field", ["subject", "object", "relation", "source_id", "evidence"])
    def test_empty_string_field_is_invalid(self, field):
        t = make_triple(**{field: ""})
        report = self.v.validate_all([t])
        assert report.invalid_count == 1

    def test_whitespace_only_subject_is_invalid(self):
        t = make_triple(subject="   ")
        report = self.v.validate_all([t])
        assert report.invalid_count == 1

    # ── Source validation ──────────────────────────────────────────────────────

    @pytest.mark.parametrize("source", ["slack", "github", "jira"])
    def test_valid_sources_pass(self, source):
        t = make_triple(source=source)
        report = self.v.validate_all([t])
        assert report.valid_count == 1

    @pytest.mark.parametrize("bad_source", ["twitter", "email", "linear", "neo4j", ""])
    def test_invalid_source_rejected(self, bad_source):
        t = make_triple(source=bad_source)
        report = self.v.validate_all([t])
        assert report.invalid_count == 1

    # ── Confidence validation ──────────────────────────────────────────────────

    @pytest.mark.parametrize("conf", [0.0, 0.5, 1.0, 0.99])
    def test_valid_confidence_passes(self, conf):
        t = make_triple(confidence=conf)
        report = self.v.validate_all([t])
        assert report.valid_count == 1

    @pytest.mark.parametrize("bad_conf", [-0.1, 1.01, 2.0, "high", None])
    def test_invalid_confidence_rejected(self, bad_conf):
        t = make_triple(confidence=bad_conf)
        report = self.v.validate_all([t])
        assert report.invalid_count == 1

    # ── Timestamp validation ───────────────────────────────────────────────────

    @pytest.mark.parametrize("ts", [
        "2023-03-15T10:30:00+00:00",
        "2023-03-15T10:30:00",
        "2023-03-15T10:30:00Z",
        "2023-03-15",
        "2023-03-15 10:30:00",
    ])
    def test_valid_timestamps_pass(self, ts):
        t = make_triple(timestamp=ts)
        report = self.v.validate_all([t])
        assert report.valid_count == 1, f"Expected valid, got errors for ts={ts!r}"

    @pytest.mark.parametrize("bad_ts", ["not-a-date", "15/03/2023", ""])
    def test_invalid_timestamps_rejected(self, bad_ts):
        t = make_triple(timestamp=bad_ts)
        report = self.v.validate_all([t])
        assert report.invalid_count == 1

    # ── Entity type validation ─────────────────────────────────────────────────

    @pytest.mark.parametrize("etype", [
        "Person", "Technology", "Project", "Service", "Database",
        "Organization", "Team", "Architecture", "Issue", "Other",
        "Problem", "ArchitectureDecision", "Unknown",
    ])
    def test_valid_entity_types_pass(self, etype):
        t = make_triple(subject_type=etype, object_type=etype)
        report = self.v.validate_all([t])
        assert report.valid_count == 1

    def test_invalid_entity_type_rejected(self):
        t = make_triple(subject_type="Robot")
        report = self.v.validate_all([t])
        assert report.invalid_count == 1

    # ── Extraction mode validation ────────────────────────────────────────────

    @pytest.mark.parametrize("mode", ["llm_groq", "llm_ollama", "llm_openai", "fallback", "mock"])
    def test_valid_extraction_modes_pass(self, mode):
        t = make_triple(extraction_mode=mode)
        report = self.v.validate_all([t])
        assert report.valid_count == 1

    def test_invalid_extraction_mode_rejected(self):
        t = make_triple(extraction_mode="gpt_turbo")
        report = self.v.validate_all([t])
        assert report.invalid_count == 1

    # ── Mixed batch ───────────────────────────────────────────────────────────

    def test_mixed_valid_invalid_batch(self):
        triples = [
            make_triple(),  # valid
            make_triple(subject="", triple_id=str(uuid.uuid4())),  # invalid
            make_triple(triple_id=str(uuid.uuid4())),  # valid
            make_triple(source="reddit", triple_id=str(uuid.uuid4())),  # invalid
        ]
        report = self.v.validate_all(triples)
        assert report.total_input == 4
        assert report.valid_count == 2
        assert report.invalid_count == 2
        assert len(report.errors) >= 2

    # ── ValidationReport serialization ────────────────────────────────────────

    def test_validation_report_to_dict(self):
        t = make_triple(source="bad_source")
        report = self.v.validate_all([t])
        d = report.to_dict()
        assert "total_input" in d
        assert "valid_count" in d
        assert "invalid_count" in d
        assert "errors" in d
        assert isinstance(d["errors"], list)

    def test_triple_error_to_dict(self):
        err = TripleError(triple_id="abc", field="source", value="bad", message="Invalid source")
        d = err.to_dict()
        assert d["triple_id"] == "abc"
        assert d["field"] == "source"
        assert d["message"] == "Invalid source"


# ─────────────────────────────────────────────────────────────────────────────
# EntityNormalizer Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEntityNormalizer:
    def setup_method(self):
        self.n = EntityNormalizer()

    # ── Person normalization ──────────────────────────────────────────────────

    def test_title_case_person(self):
        canonical, display = self.n.normalize("Arun Sharma")
        assert canonical == "arun_sharma"
        assert display == "Arun Sharma"

    def test_underscore_person(self):
        canonical, display = self.n.normalize("arun_sharma")
        assert canonical == "arun_sharma"
        assert display == "arun_sharma"

    def test_uppercase_person_gets_title_display(self):
        canonical, display = self.n.normalize("ARUN SHARMA")
        assert canonical == "arun_sharma"
        # ALL-CAPS with length > 3 → title-cased for display
        assert display == "Arun Sharma"

    # ── Technology alias normalization ────────────────────────────────────────

    @pytest.mark.parametrize("variant,expected_canonical", [
        ("AWS", "aws"),
        ("aws", "aws"),
        ("Amazon Web Services", "aws"),
        ("AWS Cloud", "aws"),          # alias dict maps 'aws cloud' → 'aws'
        ("GCP", "gcp"),
        ("Google Cloud Platform", "gcp"),
        ("Google Cloud", "gcp"),
        ("gcp", "gcp"),
        ("GKE", "gke"),
        ("Google Kubernetes Engine", "gke"),
        ("Cloud SQL", "cloudsql"),
        ("GCS", "gcs"),
        ("Google Cloud Storage", "gcs"),
        ("CloudSQL", "cloudsql"),
        ("Kubernetes", "kubernetes"),
        ("k8s", "kubernetes"),
        ("BigQuery", "bigquery"),
        ("Kafka", "kafka"),
        ("Apache Kafka", "kafka"),
        ("PostgreSQL", "postgresql"),
        ("Postgres", "postgresql"),
    ])
    def test_technology_alias_normalization(self, variant, expected_canonical):
        canonical, _ = self.n.normalize(variant)
        assert canonical == expected_canonical, f"normalize({variant!r}) = {canonical!r}, expected {expected_canonical!r}"

    # ── Display name preservation ──────────────────────────────────────────────

    def test_display_name_preserved_for_aws(self):
        _, display = self.n.normalize("AWS")
        assert display == "AWS"  # 3 chars — not converted to Title Case

    def test_display_name_preserved_for_gcp(self):
        _, display = self.n.normalize("GCP")
        assert display == "GCP"

    def test_display_name_preserved_for_mixed_case(self):
        _, display = self.n.normalize("Arun Sharma")
        assert display == "Arun Sharma"

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_empty_name_returns_empty_strings(self):
        canonical, display = self.n.normalize("")
        assert canonical == ""
        assert display == ""

    def test_whitespace_only_returns_empty(self):
        canonical, display = self.n.normalize("   ")
        assert canonical == ""
        assert display == ""

    def test_hyphenated_entity(self):
        canonical, display = self.n.normalize("auth-service")
        assert canonical == "auth_service"

    def test_special_chars_stripped(self):
        canonical, _ = self.n.normalize("API/Gateway")
        assert canonical == "api_gateway"

    def test_different_entities_not_merged(self):
        c_aws, _ = self.n.normalize("AWS")
        c_gcp, _ = self.n.normalize("GCP")
        assert c_aws != c_gcp


# ─────────────────────────────────────────────────────────────────────────────
# RelationNormalizer Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRelationNormalizer:
    def setup_method(self):
        self.n = RelationNormalizer()

    # ── Basic normalization ───────────────────────────────────────────────────

    @pytest.mark.parametrize("raw,expected", [
        ("ADVOCATED_FOR", "ADVOCATED_FOR"),
        ("advocated_for", "ADVOCATED_FOR"),
        ("advocated for", "ADVOCATED_FOR"),
        ("ARGUED_AGAINST", "ARGUED_AGAINST"),
        ("COMMITTED_CODE", "COMMITTED_CODE"),
        ("IMPLEMENTED", "IMPLEMENTED"),
        ("APPROVED", "APPROVED"),
        ("MIGRATED_TO", "MIGRATED_TO"),
        ("RAISED_CONCERN", "RAISED_CONCERN"),
        ("DECIDED", "DECIDED"),
        ("REVIEWED", "REVIEWED"),
        ("ASSIGNED_TO", "ASSIGNED_TO"),
    ])
    def test_known_relations_normalized(self, raw, expected):
        assert self.n.normalize(raw) == expected

    # ── Synonym mapping ───────────────────────────────────────────────────────

    @pytest.mark.parametrize("raw,expected", [
        ("COMMITED_CODE", "COMMITTED_CODE"),          # misspelling
        ("COMMIT_CODE", "COMMITTED_CODE"),             # alternate form
        ("ADVOCATE_FOR", "ADVOCATED_FOR"),             # singular
        ("RAISE_CONCERN", "RAISED_CONCERN"),           # singular
        ("MIGRATE_TO", "MIGRATED_TO"),                 # non-past
        ("IMPLEMENT", "IMPLEMENTED"),
        ("APPROVES", "APPROVED"),
        ("BLOCKS", "BLOCKED_BY"),
        ("REVIEW", "REVIEWED"),
    ])
    def test_relation_synonyms_mapped(self, raw, expected):
        assert self.n.normalize(raw) == expected

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_empty_relation_returns_unknown(self):
        assert self.n.normalize("") == "UNKNOWN"

    def test_whitespace_relation_returns_unknown(self):
        assert self.n.normalize("   ") == "UNKNOWN"

    def test_relation_with_spaces_gets_underscores(self):
        result = self.n.normalize("RELATED TO")
        assert " " not in result

    def test_custom_relation_uppercased(self):
        result = self.n.normalize("worked_on")
        assert result == "WORKED_ON"

    def test_multiple_underscores_collapsed(self):
        result = self.n.normalize("RAISED__CONCERN")
        assert "__" not in result


# ─────────────────────────────────────────────────────────────────────────────
# TimestampNormalizer Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTimestampNormalizer:
    def setup_method(self):
        self.n = TimestampNormalizer()

    # ── Standard ISO formats ──────────────────────────────────────────────────

    def test_utc_offset_timestamp(self):
        result = self.n.normalize("2023-03-15T10:30:00+00:00")
        assert result == "2023-03-15T10:30:00+00:00"

    def test_naive_timestamp_assumed_utc(self):
        result = self.n.normalize("2023-03-15T10:30:00")
        assert "+00:00" in result or "Z" in result or "UTC" in result

    def test_z_suffix_timestamp(self):
        result = self.n.normalize("2023-03-15T10:30:00Z")
        assert result.startswith("2023-03-15T10:30:00")

    def test_non_utc_offset_converted_to_utc(self):
        # IST = UTC+5:30
        result = self.n.normalize("2023-03-15T16:00:00+05:30")
        # 16:00 IST = 10:30 UTC
        assert "10:30:00" in result
        assert "+00:00" in result

    # ── datetime object input ─────────────────────────────────────────────────

    def test_datetime_object_aware(self):
        dt = datetime(2023, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = self.n.normalize(dt)
        assert "2023-03-15T10:30:00" in result

    def test_datetime_object_naive_assumed_utc(self):
        dt = datetime(2023, 3, 15, 10, 30, 0)
        result = self.n.normalize(dt)
        assert "2023-03-15T10:30:00" in result

    # ── Timestamp output is UTC ISO-8601 ──────────────────────────────────────

    def test_output_is_valid_iso_string(self):
        result = self.n.normalize("2023-03-15T10:30:00+00:00")
        # Must be parseable back to datetime
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_date_only_string(self):
        result = self.n.normalize("2023-03-15")
        assert "2023-03-15" in result

    def test_unparseable_timestamp_returned_as_is(self):
        bad_ts = "not-a-date"
        result = self.n.normalize(bad_ts)
        assert result == bad_ts  # fallback: original preserved

    def test_none_timestamp_returns_empty_string(self):
        result = self.n.normalize(None)
        assert result == ""

    def test_empty_string_timestamp(self):
        result = self.n.normalize("")
        # Should return empty or the original
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# TripleDeduplicator Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTripleDeduplicator:
    def setup_method(self):
        self.d = TripleDeduplicator()

    def _make_normalised(**overrides) -> Dict[str, Any]:
        """Make a normalised (snake_case subject/object) triple."""
        t = {
            "triple_id": str(uuid.uuid4()),
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
            "evidence": "Arun suggested GCP.",
            "confidence": 0.9,
            "extraction_mode": "llm_groq",
            "metadata": {},
        }
        t.update(overrides)
        return t

    _make_normalised = staticmethod(_make_normalised)

    # ── No duplicates ─────────────────────────────────────────────────────────

    def test_no_duplicates_all_kept(self):
        triples = [
            self._make_normalised(source_id="slack_001"),
            self._make_normalised(source_id="slack_002"),  # different source_id
            self._make_normalised(source_id="slack_003"),
        ]
        report = self.d.deduplicate(triples)
        assert report.unique_count == 3
        assert report.duplicate_count == 0
        assert report.input_count == 3

    # ── Exact duplicate ───────────────────────────────────────────────────────

    def test_exact_duplicate_removed(self):
        base = self._make_normalised()
        dup = copy.deepcopy(base)
        dup["triple_id"] = str(uuid.uuid4())  # different ID, same content key

        report = self.d.deduplicate([base, dup])
        assert report.unique_count == 1
        assert report.duplicate_count == 1

    # ── Higher confidence kept ────────────────────────────────────────────────

    def test_higher_confidence_replaces_lower(self):
        low = self._make_normalised(confidence=0.7)
        high = self._make_normalised(confidence=0.95)  # same key, higher conf

        report = self.d.deduplicate([low, high])
        assert report.unique_count == 1
        kept = report.unique_triples[0]
        assert kept["confidence"] == 0.95

    def test_lower_confidence_does_not_replace_higher(self):
        high = self._make_normalised(confidence=0.95)
        low = self._make_normalised(confidence=0.7)

        report = self.d.deduplicate([high, low])
        assert report.unique_count == 1
        kept = report.unique_triples[0]
        assert kept["confidence"] == 0.95

    # ── Different source_ids are never merged ─────────────────────────────────

    def test_different_source_ids_not_merged(self):
        t1 = self._make_normalised(source_id="slack_001")
        t2 = self._make_normalised(source_id="slack_002")
        # Same subject, relation, object, timestamp, source — but different source_id
        report = self.d.deduplicate([t1, t2])
        assert report.unique_count == 2

    # ── Different relations → different records ───────────────────────────────

    def test_different_relations_kept(self):
        t1 = self._make_normalised(relation="ADVOCATED_FOR")
        t2 = self._make_normalised(relation="ARGUED_AGAINST")
        report = self.d.deduplicate([t1, t2])
        assert report.unique_count == 2

    # ── Deduplication report ──────────────────────────────────────────────────

    def test_dedup_report_counts_correct(self):
        t1 = self._make_normalised()
        t2 = self._make_normalised()  # same key
        t3 = self._make_normalised(source_id="slack_002")  # different

        report = self.d.deduplicate([t1, t2, t3])
        assert report.input_count == 3
        assert report.unique_count == 2
        assert report.duplicate_count == 1

    def test_dedup_report_to_dict(self):
        t1 = self._make_normalised()
        t2 = self._make_normalised()
        report = self.d.deduplicate([t1, t2])
        d = report.to_dict()
        assert "input_count" in d
        assert "duplicate_count" in d
        assert "unique_count" in d
        assert "duplicates" in d

    def test_empty_input_returns_empty_report(self):
        report = self.d.deduplicate([])
        assert report.unique_count == 0
        assert report.duplicate_count == 0
        assert report.input_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# GraphPrepPipeline Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGraphPrepPipeline:
    """
    Integration tests that run the pipeline against the actual
    data/processed/extracted_triples.json produced by Week 1.

    These tests are skipped if the file does not exist (e.g., CI without
    the Week 1 pipeline having run).
    """

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from config.settings import settings
        self.input_path = settings.extracted_triples_path
        self.output_path = tmp_path / "graph_ready_triples.json"
        self.summary_path = tmp_path / "graph_prep_summary.json"

    def _make_pipeline(self) -> GraphPrepPipeline:
        return GraphPrepPipeline(
            input_path=self.input_path,
            output_path=self.output_path,
            summary_path=self.summary_path,
        )

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_pipeline_runs_without_error(self):
        pipeline = self._make_pipeline()
        result = pipeline.run()
        assert isinstance(result, dict)
        assert "graph_ready_count" in result
        assert result["graph_ready_count"] >= 0

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_output_file_written(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        assert self.output_path.exists()

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_summary_file_written(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        assert self.summary_path.exists()

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_output_contains_required_fields(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        with open(self.output_path, "r", encoding="utf-8") as fh:
            triples = json.load(fh)
        assert isinstance(triples, list)
        required = {
            "triple_id", "subject", "subject_display", "subject_type",
            "relation", "object", "object_display", "object_type",
            "timestamp", "source", "source_id", "evidence", "confidence",
            "extraction_mode",
        }
        for t in triples:
            missing = required - set(t.keys())
            assert not missing, f"Triple missing fields: {missing}"

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_output_relations_are_uppercase_snake_case(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        with open(self.output_path, "r", encoding="utf-8") as fh:
            triples = json.load(fh)
        for t in triples:
            rel = t["relation"]
            assert rel == rel.upper(), f"Relation not uppercased: {rel!r}"
            assert " " not in rel, f"Relation contains space: {rel!r}"

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_output_timestamps_are_iso_utc(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        with open(self.output_path, "r", encoding="utf-8") as fh:
            triples = json.load(fh)
        for t in triples:
            ts = t["timestamp"]
            # Must be parseable
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                pytest.fail(f"Timestamp not valid ISO: {ts!r}")
            # Must be timezone-aware
            assert dt.tzinfo is not None, f"Timestamp not UTC-aware: {ts!r}"

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_output_sources_are_valid(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        with open(self.output_path, "r", encoding="utf-8") as fh:
            triples = json.load(fh)
        valid_sources = {"slack", "github", "jira"}
        for t in triples:
            assert t["source"] in valid_sources, f"Invalid source: {t['source']!r}"

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_confidence_in_range(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        with open(self.output_path, "r", encoding="utf-8") as fh:
            triples = json.load(fh)
        for t in triples:
            conf = t["confidence"]
            assert 0.0 <= float(conf) <= 1.0, f"Confidence out of range: {conf}"

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_evidence_is_preserved(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        with open(self.output_path, "r", encoding="utf-8") as fh:
            triples = json.load(fh)
        for t in triples:
            assert isinstance(t["evidence"], str) and t["evidence"].strip(), \
                f"Evidence missing or empty in triple {t['triple_id']}"

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_subject_canonical_is_lowercase_snake_case(self):
        pipeline = self._make_pipeline()
        pipeline.run()
        with open(self.output_path, "r", encoding="utf-8") as fh:
            triples = json.load(fh)
        for t in triples:
            subj = t["subject"]
            assert subj == subj.lower(), f"Canonical subject not lowercase: {subj!r}"
            assert " " not in subj, f"Canonical subject contains space: {subj!r}"

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_summary_has_required_keys(self):
        pipeline = self._make_pipeline()
        result = pipeline.run()
        summary = result["summary"]
        assert "statistics" in summary
        assert "entities" in summary
        assert "sources" in summary
        assert "relations" in summary
        assert "date_range" in summary
        stats = summary["statistics"]
        assert "total_input_triples" in stats
        assert "valid_triples" in stats
        assert "invalid_triples" in stats
        assert "graph_ready_triples" in stats
        assert "duplicates_removed" in stats

    @pytest.mark.skipif(
        not Path("data/processed/extracted_triples.json").exists(),
        reason="extracted_triples.json not found; run --run-all first",
    )
    def test_graph_ready_count_leq_input_count(self):
        pipeline = self._make_pipeline()
        result = pipeline.run()
        stats = result["summary"]["statistics"]
        assert stats["graph_ready_triples"] <= stats["total_input_triples"]

    # ── Error handling ────────────────────────────────────────────────────────

    def test_pipeline_raises_when_input_missing(self, tmp_path):
        pipeline = GraphPrepPipeline(
            input_path=tmp_path / "nonexistent.json",
            output_path=tmp_path / "out.json",
            summary_path=tmp_path / "summary.json",
        )
        with pytest.raises(FileNotFoundError):
            pipeline.run()

    def test_pipeline_with_synthetic_data(self, tmp_path):
        """Verify pipeline behaviour using a small synthetic JSON dataset."""
        synthetic = [
            {
                "triple_id": str(uuid.uuid4()),
                "subject": "Alice",
                "subject_type": "Person",
                "relation": "ADVOCATED_FOR",
                "object": "AWS",
                "object_type": "Technology",
                "timestamp": "2023-01-01T09:00:00+00:00",
                "source": "slack",
                "source_id": "slack_001",
                "evidence": "Alice advocates for AWS.",
                "confidence": 0.85,
                "extraction_mode": "fallback",
            },
            # Duplicate with same key but lower confidence
            {
                "triple_id": str(uuid.uuid4()),
                "subject": "alice",
                "subject_type": "Person",
                "relation": "advocated_for",
                "object": "aws",
                "object_type": "Technology",
                "timestamp": "2023-01-01T09:00:00+00:00",
                "source": "slack",
                "source_id": "slack_001",
                "evidence": "Alice advocates for AWS (dup).",
                "confidence": 0.7,
                "extraction_mode": "fallback",
            },
            # Distinct record
            {
                "triple_id": str(uuid.uuid4()),
                "subject": "Bob",
                "subject_type": "Person",
                "relation": "ARGUED_AGAINST",
                "object": "GCP",
                "object_type": "Technology",
                "timestamp": "2023-01-02T10:00:00+00:00",
                "source": "github",
                "source_id": "github_001",
                "evidence": "Bob argued against GCP.",
                "confidence": 0.9,
                "extraction_mode": "fallback",
            },
        ]

        in_path = tmp_path / "extracted_triples.json"
        out_path = tmp_path / "graph_ready_triples.json"
        sum_path = tmp_path / "summary.json"

        with open(in_path, "w") as fh:
            json.dump(synthetic, fh)

        pipeline = GraphPrepPipeline(
            input_path=in_path,
            output_path=out_path,
            summary_path=sum_path,
        )
        result = pipeline.run()

        # 3 input triples, 1 duplicate → 2 graph-ready
        stats = result["summary"]["statistics"]
        assert stats["total_input_triples"] == 3
        assert stats["graph_ready_triples"] == 2
        assert stats["duplicates_removed"] == 1

        # Check output file
        with open(out_path) as fh:
            out_triples = json.load(fh)
        assert len(out_triples) == 2

        # The higher-confidence alice triple should survive
        alice_triples = [t for t in out_triples if t["subject"] == "alice"]
        assert len(alice_triples) == 1
        assert alice_triples[0]["confidence"] == 0.85

        # Relations must be uppercase
        for t in out_triples:
            assert t["relation"] == t["relation"].upper()
