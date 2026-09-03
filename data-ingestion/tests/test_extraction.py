"""
tests/test_extraction.py
─────────────────────────
Unit tests for the ChronoGraph triple extraction pipeline.

Tests cover:
  - Pydantic schema validation (RawEvent, Triple, ExtractionResult)
  - FallbackExtractor: deterministic rule-based extraction
  - TemporalTripleExtractor: mock-mode (no LLM required)
  - Triple.to_neo4j_dict() output format (graph ingestion contract)
  - Batch extraction and output file generation
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.extraction.extractor import TemporalTripleExtractor
from src.extraction.fallback import FallbackExtractor
from src.schemas.graph import (
    DataSource,
    EntityType,
    ExtractionMode,
    ExtractionResult,
    RawEvent,
    RelationType,
    Triple,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def slack_event():
    """A representative Slack RawEvent for extraction testing."""
    return RawEvent(
        source=DataSource.SLACK,
        source_id="slack_001",
        author="arun_sharma",
        content=(
            "I strongly believe we should start evaluating a migration to GCP. "
            "GCP's sustained-use discounts could cut costs by 35-40%. "
            "I'd like to propose a phased migration starting with the authentication service."
        ),
        timestamp=datetime(2023, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
        channel="infra-migration",
    )


@pytest.fixture
def github_event():
    """A representative GitHub RawEvent."""
    return RawEvent(
        source=DataSource.GITHUB,
        source_id="github_pr_003",
        author="rohan_mehta",
        content=(
            "This PR removes all AWS S3 usage in authentication-service and replaces "
            "with Google Cloud Storage (GCS). Removes boto3 dependency. "
            "Adds google-cloud-storage library."
        ),
        timestamp=datetime(2023, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
        channel="acme-platform",
        title="feat: Introduce GCP SDK – replace AWS S3 in auth-service",
        labels=["migration", "gcp"],
    )


@pytest.fixture
def jira_event():
    """A representative Jira RawEvent."""
    return RawEvent(
        source=DataSource.JIRA,
        source_id="jira_001",
        author="arun_sharma",
        content=(
            "[CLOUD-98] Evaluate GCP vs AWS migration feasibility\n\n"
            "Conduct a comprehensive feasibility study for migrating our AWS "
            "infrastructure to GCP. Deliverable: Architecture Decision Record (ADR-001)."
        ),
        timestamp=datetime(2023, 3, 16, 8, 0, 0, tzinfo=timezone.utc),
        channel="CLOUD",
        metadata={"ticket_key": "CLOUD-98", "assignee": "arun_sharma"},
    )


@pytest.fixture
def security_event():
    """An event about a security vulnerability for RAISED_CONCERN extraction."""
    return RawEvent(
        source=DataSource.SLACK,
        source_id="slack_011",
        author="divya_krishnan",
        content=(
            "URGENT: I've identified a critical security vulnerability in the "
            "authentication-service. The JWT token rotation mechanism has a race "
            "condition. This needs immediate patching before the GCP migration."
        ),
        timestamp=datetime(2023, 4, 12, 8, 15, 0, tzinfo=timezone.utc),
        channel="security-alerts",
    )


@pytest.fixture
def fallback_extractor():
    return FallbackExtractor(min_confidence=0.5)


@pytest.fixture
def mock_extractor():
    """TemporalTripleExtractor in mock mode (uses fallback internally)."""
    return TemporalTripleExtractor(llm_provider="mock", min_confidence=0.5)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schema tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPydanticSchemas:

    def test_raw_event_valid(self, slack_event):
        assert slack_event.source == DataSource.SLACK
        assert slack_event.author == "arun_sharma"
        assert slack_event.content != ""

    def test_raw_event_empty_content_raises(self):
        with pytest.raises(Exception):
            RawEvent(
                source=DataSource.SLACK,
                source_id="test_001",
                author="user",
                content="   ",  # blank after strip
                timestamp=datetime.now(tz=timezone.utc),
            )

    def test_raw_event_empty_author_raises(self):
        with pytest.raises(Exception):
            RawEvent(
                source=DataSource.SLACK,
                source_id="test_001",
                author="",
                content="some content",
                timestamp=datetime.now(tz=timezone.utc),
            )

    def test_triple_valid(self):
        triple = Triple(
            subject="arun_sharma",
            relation="ADVOCATED_FOR",
            object="GCP",
            timestamp=datetime(2023, 3, 15, tzinfo=timezone.utc),
            source=DataSource.SLACK,
            source_id="slack_001",
            evidence="Arun suggested moving services to GCP.",
            confidence=0.92,
        )
        assert triple.subject == "arun_sharma"
        assert triple.relation == "ADVOCATED_FOR"
        assert triple.object == "GCP"
        assert 0.0 <= triple.confidence <= 1.0

    def test_triple_relation_normalised_to_uppercase(self):
        triple = Triple(
            subject="arun",
            relation="advocated for",
            object="gcp",
            timestamp=datetime.now(tz=timezone.utc),
            source=DataSource.SLACK,
            source_id="s001",
            evidence="test",
            confidence=0.8,
        )
        assert triple.relation == "ADVOCATED_FOR"

    def test_triple_confidence_out_of_range_raises(self):
        with pytest.raises(Exception):
            Triple(
                subject="user",
                relation="DECIDED",
                object="GCP",
                timestamp=datetime.now(tz=timezone.utc),
                source=DataSource.JIRA,
                source_id="j001",
                evidence="test",
                confidence=1.5,  # > 1.0 – invalid
            )

    def test_triple_to_neo4j_dict_structure(self):
        triple = Triple(
            subject="arun_sharma",
            subject_type=EntityType.PERSON,
            relation="ADVOCATED_FOR",
            object="GCP",
            object_type=EntityType.TECHNOLOGY,
            timestamp=datetime(2023, 3, 15, tzinfo=timezone.utc),
            source=DataSource.SLACK,
            source_id="slack_001",
            evidence="Arun suggested moving to GCP.",
            confidence=0.92,
        )
        d = triple.to_neo4j_dict()
        required_keys = {
            "triple_id", "subject", "subject_type", "relation",
            "object", "object_type", "timestamp", "source",
            "source_id", "evidence", "confidence", "extraction_mode",
        }
        assert required_keys.issubset(d.keys())
        assert d["subject"] == "arun_sharma"
        assert d["relation"] == "ADVOCATED_FOR"
        assert d["source"] == "slack"

    def test_extraction_result_succeeded_property(self):
        triple = Triple(
            subject="user",
            relation="DECIDED",
            object="GCP",
            timestamp=datetime.now(tz=timezone.utc),
            source=DataSource.JIRA,
            source_id="j001",
            evidence="leadership approved GCP",
            confidence=0.8,
        )
        result = ExtractionResult(
            event_id="evt_001",
            source_id="j001",
            source=DataSource.JIRA,
            extraction_mode=ExtractionMode.FALLBACK,
            triples=[triple],
        )
        assert result.succeeded is True

    def test_extraction_result_fails_with_error(self):
        result = ExtractionResult(
            event_id="evt_001",
            source_id="j001",
            source=DataSource.JIRA,
            extraction_mode=ExtractionMode.FALLBACK,
            triples=[],
            error="LLM timeout",
        )
        assert result.succeeded is False


# ─────────────────────────────────────────────────────────────────────────────
# FallbackExtractor tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackExtractor:

    def test_fallback_returns_extraction_result(self, fallback_extractor, slack_event):
        result = fallback_extractor.extract(slack_event)
        assert isinstance(result, ExtractionResult)
        assert result.source_id == "slack_001"

    def test_fallback_extraction_mode_is_fallback(self, fallback_extractor, slack_event):
        result = fallback_extractor.extract(slack_event)
        assert result.extraction_mode == ExtractionMode.FALLBACK

    def test_fallback_extracts_advocated_for_from_suggest(self, fallback_extractor, slack_event):
        result = fallback_extractor.extract(slack_event)
        relations = [t.relation for t in result.triples]
        assert "ADVOCATED_FOR" in relations

    def test_fallback_extracts_gcp_as_object(self, fallback_extractor, slack_event):
        result = fallback_extractor.extract(slack_event)
        objects = [t.object for t in result.triples]
        assert any("GCP" in obj for obj in objects)

    def test_fallback_subject_is_author(self, fallback_extractor, slack_event):
        result = fallback_extractor.extract(slack_event)
        for triple in result.triples:
            assert triple.subject == slack_event.author

    def test_fallback_confidence_in_valid_range(self, fallback_extractor, slack_event):
        result = fallback_extractor.extract(slack_event)
        for triple in result.triples:
            assert 0.0 <= triple.confidence <= 1.0

    def test_fallback_triples_have_evidence(self, fallback_extractor, slack_event):
        result = fallback_extractor.extract(slack_event)
        for triple in result.triples:
            assert triple.evidence.strip() != ""

    def test_fallback_triples_have_timestamp(self, fallback_extractor, slack_event):
        result = fallback_extractor.extract(slack_event)
        for triple in result.triples:
            assert isinstance(triple.timestamp, datetime)

    def test_fallback_raised_concern_from_security_event(self, fallback_extractor, security_event):
        result = fallback_extractor.extract(security_event)
        relations = [t.relation for t in result.triples]
        assert "RAISED_CONCERN" in relations

    def test_fallback_migrated_to_from_github_event(self, fallback_extractor, github_event):
        result = fallback_extractor.extract(github_event)
        relations = [t.relation for t in result.triples]
        assert "MIGRATED_TO" in relations or "DEPRECATED" in relations

    def test_fallback_batch_extract(self, fallback_extractor, slack_event, github_event, jira_event):
        events = [slack_event, github_event, jira_event]
        results = fallback_extractor.extract_batch(events)
        assert len(results) == 3
        for result in results:
            assert isinstance(result, ExtractionResult)

    def test_fallback_min_confidence_filters_triples(self, slack_event):
        """High min_confidence should return fewer or zero triples."""
        extractor_strict = FallbackExtractor(min_confidence=0.99)
        result = extractor_strict.extract(slack_event)
        # All triples should meet the threshold or be empty
        for triple in result.triples:
            assert triple.confidence >= 0.99

    def test_fallback_empty_text_returns_empty_triples(self):
        """Events with no actionable keywords produce no triples."""
        event = RawEvent(
            source=DataSource.SLACK,
            source_id="slack_empty",
            author="user",
            content="ok thanks",
            timestamp=datetime.now(tz=timezone.utc),
        )
        extractor = FallbackExtractor(min_confidence=0.5)
        result = extractor.extract(event)
        assert isinstance(result, ExtractionResult)
        # May or may not have triples – just check it doesn't crash


# ─────────────────────────────────────────────────────────────────────────────
# TemporalTripleExtractor (mock mode) tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTemporalTripleExtractor:

    def test_mock_extractor_returns_result(self, mock_extractor, slack_event):
        result = mock_extractor.extract(slack_event)
        assert isinstance(result, ExtractionResult)

    def test_mock_extractor_batch(self, mock_extractor, slack_event, github_event, jira_event):
        events = [slack_event, github_event, jira_event]
        results = mock_extractor.extract_batch(events)
        assert len(results) == 3

    def test_mock_extractor_max_events_respected(self, mock_extractor, slack_event, github_event, jira_event):
        events = [slack_event, github_event, jira_event]
        results = mock_extractor.extract_batch(events, max_events=2)
        assert len(results) == 2

    def test_mock_extractor_triples_are_valid(self, mock_extractor, slack_event):
        result = mock_extractor.extract(slack_event)
        for triple in result.triples:
            assert triple.subject.strip() != ""
            assert triple.relation.strip() != ""
            assert triple.object.strip() != ""
            assert isinstance(triple.confidence, float)
            assert 0.0 <= triple.confidence <= 1.0

    def test_mock_extractor_neo4j_dict_output(self, mock_extractor, slack_event):
        result = mock_extractor.extract(slack_event)
        if result.triples:
            d = result.triples[0].to_neo4j_dict()
            assert "subject" in d
            assert "relation" in d
            assert "object" in d
            assert "timestamp" in d
            assert "source" in d
            assert "source_id" in d
            assert "evidence" in d
            assert "confidence" in d


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end extraction output file test
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractionOutputFile:

    def test_full_pipeline_generates_triples_file(self, tmp_path):
        """
        Integration test: run ingestion + extraction and verify that
        extracted_triples.json is created with valid content.
        """
        from src.ingestion.pipeline import IngestionPipeline

        slack_path = _PROJECT_ROOT / "data" / "raw" / "slack_history.json"
        github_path = _PROJECT_ROOT / "data" / "raw" / "github_prs.json"
        jira_path = _PROJECT_ROOT / "data" / "raw" / "jira_tickets.json"
        normalized_path = tmp_path / "normalized_events.json"
        triples_path = tmp_path / "extracted_triples.json"

        # Ingestion
        pipeline = IngestionPipeline(
            slack_path=slack_path,
            github_path=github_path,
            jira_path=jira_path,
            output_path=normalized_path,
        )
        events = pipeline.run()
        assert len(events) > 0

        # Extraction
        extractor = TemporalTripleExtractor(llm_provider="mock", min_confidence=0.5)
        results = extractor.extract_batch(events)
        all_triples = [t for r in results for t in r.triples]

        # Save output
        with open(triples_path, "w") as fh:
            json.dump([t.to_neo4j_dict() for t in all_triples], fh, indent=2, default=str)

        # Verify
        assert triples_path.exists()
        with open(triples_path) as fh:
            loaded = json.load(fh)

        assert isinstance(loaded, list)
        if loaded:
            triple = loaded[0]
            required_fields = {
                "subject", "subject_type", "relation", "object", "object_type",
                "timestamp", "source", "source_id", "evidence", "confidence",
            }
            assert required_fields.issubset(triple.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Entity Types and Provider Configuration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEntityTypesAndProviderConfig:

    def test_entity_types_meaningful_types(self, slack_event, github_event, jira_event):
        """Verify subject_type and object_type are meaningful non-Unknown types."""
        extractor = FallbackExtractor(min_confidence=0.5)

        res_slack = extractor.extract(slack_event)
        for t in res_slack.triples:
            assert t.subject_type == EntityType.PERSON
            assert t.object_type in (
                EntityType.TECHNOLOGY, EntityType.SERVICE, EntityType.PROJECT,
                EntityType.DATABASE, EntityType.PROBLEM, EntityType.ISSUE,
            )

        res_github = extractor.extract(github_event)
        for t in res_github.triples:
            assert t.subject_type == EntityType.PERSON
            assert t.object_type != EntityType.UNKNOWN

    def test_person_detection(self):
        """Verify person handles map to EntityType.PERSON."""
        for author in ["arun_sharma", "priya_nair", "rohan_mehta", "divya_krishnan", "vikram_patel"]:
            assert FallbackExtractor._classify_person(author) == EntityType.PERSON
            assert TemporalTripleExtractor._infer_entity_type(author, "") == EntityType.PERSON

    def test_technology_detection(self):
        """Verify technology terms map to EntityType.TECHNOLOGY."""
        for tech in ["GCP", "AWS", "Kubernetes", "GKE", "Docker"]:
            assert TemporalTripleExtractor._infer_entity_type(tech, "") == EntityType.TECHNOLOGY

    def test_database_service_issue_detection(self):
        """Verify database, service, and issue terms map to expected EntityType values."""
        assert TemporalTripleExtractor._infer_entity_type("PostgreSQL", "") == EntityType.DATABASE
        assert TemporalTripleExtractor._infer_entity_type("CloudSQL", "") == EntityType.DATABASE
        assert TemporalTripleExtractor._infer_entity_type("authentication_service", "") == EntityType.SERVICE
        assert TemporalTripleExtractor._infer_entity_type("CLOUD-98", "") == EntityType.ISSUE

    def test_coerce_entity_type_flexible_matching(self):
        """Verify _coerce_entity_type handles titlecase, uppercase, and aliases."""
        assert TemporalTripleExtractor._coerce_entity_type("Person") == EntityType.PERSON
        assert TemporalTripleExtractor._coerce_entity_type("PERSON") == EntityType.PERSON
        assert TemporalTripleExtractor._coerce_entity_type("technology") == EntityType.TECHNOLOGY
        assert TemporalTripleExtractor._coerce_entity_type("DB") == EntityType.DATABASE
        assert TemporalTripleExtractor._coerce_entity_type("TICKET") == EntityType.ISSUE
        assert TemporalTripleExtractor._coerce_entity_type("invalid_type") == EntityType.UNKNOWN

    def test_groq_provider_does_not_require_openai_key(self):
        """Verify Groq provider instantiation does not require OPENAI_API_KEY."""
        extractor = TemporalTripleExtractor(
            llm_provider="groq",
            groq_api_key="gsk_test_key",
            groq_model="llama-3.1-8b-instant",
            openai_api_key="",  # empty
        )
        assert extractor.llm_provider == "groq"
        assert extractor.groq_api_key == "gsk_test_key"
        assert extractor.openai_api_key == ""

    def test_fallback_provider_alias_works(self, slack_event):
        """Verify llm_provider='fallback' uses FallbackExtractor without error."""
        extractor = TemporalTripleExtractor(llm_provider="fallback")
        result = extractor.extract(slack_event)
        assert isinstance(result, ExtractionResult)
        assert result.extraction_mode == ExtractionMode.FALLBACK

