"""
tests/test_retrieval_api.py
───────────────────────────
Week 4 — Test suite for Temporal Retrieval Service & FastAPI Endpoints.

Coverage:
  1. Direct unit tests for RetrievalService
  2. Health endpoint (GET /api/health)
  3. Retrieval query endpoint (POST /api/retrieval/query)
     - Basic query
     - Entity filtering (subject / object / display names)
     - Relation filtering
     - Source filtering (slack, github, jira)
     - Exact date filtering
     - Date range filtering
     - Before date filtering
     - After date filtering
     - Chronological sorting (ASC / DESC)
     - Result limit and total_matches calculation
     - Empty result handling
     - Provenance information preservation
     - Validation errors (422)
     - Missing retrieval data handling (404)
     - Corrupted data file handling (500)
  4. Retrieval quality stats endpoint (GET /api/retrieval/stats)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from src.api.app import app
from src.retrieval.filter import TemporalFilterEngine
from src.retrieval.models import (
    RetrievalHealthResponse,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalRecord,
    RetrievalRequest,
    SortOrder,
    TemporalFilter,
)
from src.retrieval.errors import (
    RetrievalDataCorruptedError,
    RetrievalDataError,
    RetrievalDataFormatError,
    RetrievalDataNotFoundError,
    RetrievalError,
    RetrievalServiceError,
)
from src.retrieval.service import RetrievalService

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_records_data() -> List[Dict[str, Any]]:
    return [
        {
            "record_id": "rec_001",
            "triple_id": "rec_001",
            "subject": "arun_sharma",
            "subject_display": "Arun Sharma",
            "subject_type": "Person",
            "relation": "ADVOCATED_FOR",
            "object": "gcp",
            "object_display": "GCP",
            "object_type": "Technology",
            "timestamp": "2023-03-15T10:30:00+00:00",
            "event_date": "2023-03-15",
            "source": "slack",
            "source_id": "slack_001",
            "source_url": None,
            "evidence": "Arun suggested migrating services to GCP.",
            "confidence": 0.9,
            "extraction_mode": "llm_groq",
            "metadata": {},
        },
        {
            "record_id": "rec_002",
            "triple_id": "rec_002",
            "subject": "priya_patel",
            "subject_display": "Priya Patel",
            "subject_type": "Person",
            "relation": "RAISED_CONCERN",
            "object": "aws_costs",
            "object_display": "AWS Costs",
            "object_type": "Issue",
            "timestamp": "2023-04-01T14:00:00+00:00",
            "event_date": "2023-04-01",
            "source": "jira",
            "source_id": "jira_001",
            "source_url": None,
            "evidence": "Priya raised concern about rising AWS costs.",
            "confidence": 0.85,
            "extraction_mode": "llm_groq",
            "metadata": {},
        },
        {
            "record_id": "rec_003",
            "triple_id": "rec_003",
            "subject": "karkuvel",
            "subject_display": "Karkuvel",
            "subject_type": "Person",
            "relation": "MIGRATED_TO",
            "object": "gcp",
            "object_display": "GCP",
            "object_type": "Technology",
            "timestamp": "2023-05-10T09:15:00+00:00",
            "event_date": "2023-05-10",
            "source": "github",
            "source_id": "github_pr_007",
            "source_url": "https://github.com/org/repo/pull/7",
            "evidence": "Karkuvel completed the migration to GCP.",
            "confidence": 0.95,
            "extraction_mode": "llm_groq",
            "metadata": {"html_url": "https://github.com/org/repo/pull/7"},
        },
    ]


@pytest.fixture
def temp_records_file(tmp_path: Path, sample_records_data: List[Dict[str, Any]]) -> Path:
    file_path = tmp_path / "retrieval_ready_records.json"
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(sample_records_data, fh, indent=2)
    return file_path


@pytest.fixture
def temp_stats_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "retrieval_quality_stats.json"
    stats_data = {
        "total_records": 3,
        "unique_entities": 5,
        "unique_relations": 3,
        "records_with_temporal_data": 3,
        "records_without_temporal_data": 0,
        "earliest_timestamp": "2023-03-15",
        "latest_timestamp": "2023-05-10",
        "source_breakdown": {"slack": 1, "jira": 1, "github": 1},
        "average_confidence": 0.9,
        "records_with_source_url": 1,
        "generated_at": "2026-08-28T00:00:00+00:00",
    }
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(stats_data, fh, indent=2)
    return file_path


# ─────────────────────────────────────────────────────────────────────────────
# 1. RetrievalService Unit Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRetrievalService:
    def test_load_records_success(self, temp_records_file: Path) -> None:
        service = RetrievalService(records_path=temp_records_file)
        records = service.load_records()
        assert len(records) == 3
        assert isinstance(records[0], RetrievalRecord)
        assert records[0].record_id == "rec_001"
        assert records[0].subject == "arun_sharma"

    def test_load_records_missing_file_raises(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "non_existent.json"
        service = RetrievalService(records_path=missing_path)
        with pytest.raises(RetrievalDataNotFoundError) as exc_info:
            service.load_records()
        assert "not found" in str(exc_info.value).lower()

    def test_load_records_corrupted_json_raises(self, tmp_path: Path) -> None:
        corrupted_path = tmp_path / "corrupted.json"
        corrupted_path.write_text("{invalid json", encoding="utf-8")
        service = RetrievalService(records_path=corrupted_path)
        with pytest.raises(RetrievalDataCorruptedError):
            service.load_records()

    def test_load_records_non_list_raises(self, tmp_path: Path) -> None:
        non_list_path = tmp_path / "non_list.json"
        non_list_path.write_text('{"key": "value"}', encoding="utf-8")
        service = RetrievalService(records_path=non_list_path)
        with pytest.raises(RetrievalDataCorruptedError):
            service.load_records()

    def test_load_records_empty_file(self, tmp_path: Path) -> None:
        empty_path = tmp_path / "empty.json"
        empty_path.write_text("", encoding="utf-8")
        service = RetrievalService(records_path=empty_path)
        records = service.load_records()
        assert records == []

    def test_load_records_skips_invalid_entries(self, tmp_path: Path, sample_records_data: List[Dict[str, Any]]) -> None:
        mixed_data = list(sample_records_data)
        mixed_data.append({"invalid": "record without required fields"})
        mixed_data.append("not a dict")
        path = tmp_path / "mixed.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(mixed_data, fh)

        service = RetrievalService(records_path=path)
        records = service.load_records()
        assert len(records) == 3

    def test_query_with_retrieval_query_request(self, temp_records_file: Path) -> None:
        service = RetrievalService(records_path=temp_records_file)
        req = RetrievalQueryRequest(
            query="When did Arun suggest GCP?",
            entity_hints=["arun_sharma"],
            limit=10,
        )
        resp = service.query(req)
        assert isinstance(resp, RetrievalQueryResponse)
        assert resp.total_matches == 1
        assert resp.returned_count == 1
        assert resp.results[0].subject == "arun_sharma"
        assert resp.results[0].object == "gcp"
        assert resp.query == "When did Arun suggest GCP?"

    def test_query_with_week3_retrieval_request(self, temp_records_file: Path) -> None:
        service = RetrievalService(records_path=temp_records_file)
        req = RetrievalRequest(
            query_text="Find GCP migrations",
            relation_hints=["MIGRATED_TO"],
            limit=5,
        )
        resp = service.query(req)
        assert resp.total_matches == 1
        assert resp.results[0].subject == "karkuvel"

    def test_query_total_matches_independent_of_limit(self, temp_records_file: Path) -> None:
        service = RetrievalService(records_path=temp_records_file)
        # 2 records match GCP entity (rec_001 and rec_003)
        req = RetrievalQueryRequest(
            entity_hints=["GCP"],
            limit=1,
        )
        resp = service.query(req)
        assert resp.total_matches == 2
        assert resp.returned_count == 1
        assert len(resp.results) == 1

    def test_get_health(self, temp_records_file: Path) -> None:
        service = RetrievalService(records_path=temp_records_file)
        health = service.get_health()
        assert health.status == "ok"
        assert health.retrieval_data_available is True
        assert health.retrieval_records_count == 3

    def test_get_health_when_file_missing(self, tmp_path: Path) -> None:
        service = RetrievalService(records_path=tmp_path / "missing.json")
        health = service.get_health()
        assert health.status == "ok"
        assert health.retrieval_data_available is False
        assert health.retrieval_records_count is None

    def test_get_stats_from_file(self, temp_records_file: Path, temp_stats_file: Path) -> None:
        service = RetrievalService(records_path=temp_records_file, stats_path=temp_stats_file)
        stats = service.get_stats()
        assert stats["total_records"] == 3
        assert stats["unique_entities"] == 5

    def test_get_stats_computes_when_stats_file_missing(self, temp_records_file: Path, tmp_path: Path) -> None:
        missing_stats_path = tmp_path / "no_stats.json"
        service = RetrievalService(records_path=temp_records_file, stats_path=missing_stats_path)
        stats = service.get_stats()
        assert stats["total_records"] == 3
        assert stats["unique_entities"] == 8
        assert stats["unique_relations"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 2. FastAPI Health Endpoint Tests (GET /api/health)
# ─────────────────────────────────────────────────────────────────────────────


class TestApiHealthEndpoint:
    def test_health_endpoint_success(self) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "ChronoGraph Retrieval API"
        assert data["version"] == "1.0.0"
        assert "retrieval_data_available" in data
        assert "retrieval_records_count" in data
        assert "timestamp" in data

    def test_health_when_data_missing(self) -> None:
        with patch.object(
            RetrievalService,
            "get_health",
            return_value=RetrievalHealthResponse(
                status="ok",
                retrieval_data_available=False,
                retrieval_records_count=None,
            ),
        ):
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["retrieval_data_available"] is False
            assert data["retrieval_records_count"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. FastAPI Retrieval Query Endpoint Tests (POST /api/retrieval/query)
# ─────────────────────────────────────────────────────────────────────────────


class TestApiRetrievalQueryEndpoint:
    def test_basic_query_all(self) -> None:
        response = client.post("/api/retrieval/query", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] >= 142
        assert data["returned_count"] <= 20
        assert len(data["results"]) == data["returned_count"]
        assert "applied_filters" in data
        assert "generated_at" in data

    def test_entity_hint_filtering(self) -> None:
        payload = {
            "query": "What did Arun advocate for?",
            "entity_hints": ["arun_sharma"],
            "limit": 10,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "What did Arun advocate for?"
        assert data["total_matches"] > 0
        for r in data["results"]:
            assert "arun" in r["subject"].lower() or "arun" in r["object"].lower()

    def test_relation_filtering(self) -> None:
        payload = {
            "relation_hints": ["MIGRATED_TO"],
            "limit": 5,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        for r in data["results"]:
            assert r["relation"] == "MIGRATED_TO"

    def test_source_filtering_slack(self) -> None:
        payload = {
            "sources": ["slack"],
            "limit": 10,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 51
        for r in data["results"]:
            assert r["source"] == "slack"

    def test_source_filtering_github(self) -> None:
        payload = {
            "sources": ["github"],
            "limit": 10,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 40
        for r in data["results"]:
            assert r["source"] == "github"

    def test_source_filtering_jira(self) -> None:
        payload = {
            "sources": ["jira"],
            "limit": 10,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 51
        for r in data["results"]:
            assert r["source"] == "jira"

    def test_exact_date_filtering(self) -> None:
        payload = {
            "exact_date": "2023-03-15",
            "limit": 20,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        for r in data["results"]:
            assert r["event_date"] == "2023-03-15"

    def test_date_range_filtering(self) -> None:
        payload = {
            "start_date": "2023-04-01",
            "end_date": "2023-04-30",
            "limit": 50,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        for r in data["results"]:
            assert "2023-04-01" <= r["event_date"] <= "2023-04-30"

    def test_before_date_filtering(self) -> None:
        payload = {
            "before_date": "2023-04-01",
            "limit": 50,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        for r in data["results"]:
            assert r["event_date"] < "2023-04-01"

    def test_after_date_filtering(self) -> None:
        payload = {
            "after_date": "2023-04-01",
            "limit": 50,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        for r in data["results"]:
            assert r["event_date"] > "2023-04-01"

    def test_chronological_sort_asc(self) -> None:
        payload = {
            "sort_order": "asc",
            "limit": 30,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        dates = [r["event_date"] for r in response.json()["results"]]
        assert dates == sorted(dates)

    def test_chronological_sort_desc(self) -> None:
        payload = {
            "sort_order": "desc",
            "limit": 30,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        dates = [r["event_date"] for r in response.json()["results"]]
        assert dates == sorted(dates, reverse=True)

    def test_limit_control(self) -> None:
        payload = {
            "limit": 5,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["returned_count"] == 5
        assert len(data["results"]) == 5
        assert data["total_matches"] >= 142

    def test_empty_result_match(self) -> None:
        payload = {
            "entity_hints": ["non_existent_entity_xyz_999"],
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 0
        assert data["returned_count"] == 0
        assert data["results"] == []

    def test_provenance_preservation(self) -> None:
        payload = {
            "limit": 1,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        record = response.json()["results"][0]
        # Required provenance fields
        assert "record_id" in record
        assert "triple_id" in record
        assert "source" in record
        assert "source_id" in record
        assert "evidence" in record
        assert "timestamp" in record
        assert "event_date" in record
        assert "confidence" in record

    def test_invalid_request_date_range_validation_422(self) -> None:
        # start_date > end_date should trigger validation error
        payload = {
            "start_date": "2023-05-01",
            "end_date": "2023-04-01",
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 422

    def test_invalid_request_unknown_source_422(self) -> None:
        payload = {
            "sources": ["invalid_source_system"],
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 422

    def test_invalid_request_limit_out_of_bounds_422(self) -> None:
        payload = {
            "limit": 0,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 422

    def test_missing_retrieval_data_404(self) -> None:
        with patch.object(
            RetrievalService,
            "query",
            side_effect=RetrievalDataNotFoundError("Data file not found"),
        ):
            response = client.post("/api/retrieval/query", json={})
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_corrupted_retrieval_data_500(self) -> None:
        with patch.object(
            RetrievalService,
            "query",
            side_effect=RetrievalDataCorruptedError("JSON syntax error"),
        ):
            response = client.post("/api/retrieval/query", json={})
            assert response.status_code == 500
            assert "corrupted" in response.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# 4. FastAPI Retrieval Stats Endpoint Tests (GET /api/retrieval/stats)
# ─────────────────────────────────────────────────────────────────────────────


class TestApiRetrievalStatsEndpoint:
    def test_get_stats_success(self) -> None:
        response = client.get("/api/retrieval/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] == 142
        assert data["unique_entities"] == 30
        assert data["unique_relations"] == 8
        assert "source_breakdown" in data
        assert data["source_breakdown"]["slack"] == 51
        assert data["source_breakdown"]["jira"] == 51
        assert data["source_breakdown"]["github"] == 40

    def test_get_stats_missing_file_404(self) -> None:
        with patch.object(
            RetrievalService,
            "get_stats",
            side_effect=RetrievalDataNotFoundError("Records not found"),
        ):
            response = client.get("/api/retrieval/stats")
            assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 5. Retrieval API Pagination & Performance Tests (Week 4 Day 2)
# ─────────────────────────────────────────────────────────────────────────────


class TestApiPagination:
    def test_first_page(self) -> None:
        response = client.post("/api/retrieval/query", json={"page": 1, "page_size": 5})
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert data["returned_count"] == 5
        assert len(data["results"]) == 5
        assert data["has_next"] is True
        assert data["has_previous"] is False

    def test_second_page(self) -> None:
        p1 = client.post("/api/retrieval/query", json={"page": 1, "page_size": 5}).json()
        p2 = client.post("/api/retrieval/query", json={"page": 2, "page_size": 5}).json()
        assert p2["page"] == 2
        assert p2["page_size"] == 5
        assert p2["returned_count"] == 5
        assert p2["has_next"] is True
        assert p2["has_previous"] is True
        # Page 2 results must be distinct from Page 1
        p1_ids = [r["record_id"] for r in p1["results"]]
        p2_ids = [r["record_id"] for r in p2["results"]]
        assert set(p1_ids).isdisjoint(set(p2_ids))

    def test_last_page(self) -> None:
        resp_all = client.post("/api/retrieval/query", json={"page": 1, "page_size": 100}).json()
        total_pages = resp_all["total_pages"]
        response = client.post("/api/retrieval/query", json={"page": total_pages, "page_size": 100})
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == total_pages
        assert data["has_next"] is False
        assert data["has_previous"] is True
        assert data["returned_count"] > 0

    def test_page_beyond_available_results(self) -> None:
        response = client.post("/api/retrieval/query", json={"page": 9999, "page_size": 10})
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 9999
        assert data["returned_count"] == 0
        assert data["results"] == []
        assert data["has_next"] is False
        assert data["has_previous"] is True

    def test_page_size_behavior(self) -> None:
        response = client.post("/api/retrieval/query", json={"page": 1, "page_size": 3})
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 3
        assert data["returned_count"] == 3
        assert len(data["results"]) == 3

    def test_total_pages_calculation(self) -> None:
        response = client.post("/api/retrieval/query", json={"page_size": 10})
        assert response.status_code == 200
        data = response.json()
        total_matches = data["total_matches"]
        expected_total_pages = (total_matches + 9) // 10
        assert data["total_pages"] == expected_total_pages

    def test_has_next_and_has_previous_flags(self) -> None:
        # Page 1 of multi-page
        p1 = client.post("/api/retrieval/query", json={"page": 1, "page_size": 10}).json()
        assert p1["has_next"] is True
        assert p1["has_previous"] is False

        # Middle page
        p2 = client.post("/api/retrieval/query", json={"page": 2, "page_size": 10}).json()
        assert p2["has_next"] is True
        assert p2["has_previous"] is True

    def test_page_zero_rejection_422(self) -> None:
        response = client.post("/api/retrieval/query", json={"page": 0})
        assert response.status_code == 422

    def test_negative_page_rejection_422(self) -> None:
        response = client.post("/api/retrieval/query", json={"page": -5})
        assert response.status_code == 422

    def test_page_size_zero_rejection_422(self) -> None:
        response = client.post("/api/retrieval/query", json={"page_size": 0})
        assert response.status_code == 422

    def test_excessive_page_size_rejection_422(self) -> None:
        response = client.post("/api/retrieval/query", json={"page_size": 101})
        assert response.status_code == 422

    def test_filtering_and_pagination_together(self) -> None:
        payload = {
            "sources": ["slack"],
            "page": 2,
            "page_size": 10,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 51
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert data["returned_count"] == 10
        for r in data["results"]:
            assert r["source"] == "slack"

    def test_sorting_and_pagination_together(self) -> None:
        p1 = client.post("/api/retrieval/query", json={"sort_order": "desc", "page": 1, "page_size": 5}).json()
        p2 = client.post("/api/retrieval/query", json={"sort_order": "desc", "page": 2, "page_size": 5}).json()

        d1 = [r["event_date"] for r in p1["results"]]
        d2 = [r["event_date"] for r in p2["results"]]
        assert d1 == sorted(d1, reverse=True)
        assert d2 == sorted(d2, reverse=True)
        assert min(d1) >= max(d2)

    def test_backward_compatibility_limit_only(self) -> None:
        # Existing Day 1 limit-only request must return first N records seamlessly
        payload = {
            "entity_hints": ["gcp"],
            "limit": 5,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert data["returned_count"] == min(5, data["total_matches"])
        assert len(data["results"]) == data["returned_count"]

    def test_empty_results_pagination(self) -> None:
        payload = {
            "entity_hints": ["non_existent_entity_xyz_999"],
            "page": 1,
            "page_size": 10,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 0
        assert data["returned_count"] == 0
        assert data["total_pages"] == 0
        assert data["has_next"] is False
        assert data["has_previous"] is False
        assert data["results"] == []

    def test_direct_retrieval_service_pagination(self, temp_records_file: Path) -> None:
        service = RetrievalService(records_path=temp_records_file)
        req = RetrievalQueryRequest(page=2, page_size=1)
        resp = service.query(req)
        assert resp.total_matches == 3
        assert resp.total_pages == 3
        assert resp.page == 2
        assert resp.page_size == 1
        assert resp.returned_count == 1
        assert resp.has_next is True
        assert resp.has_previous is True

    def test_cached_retrieval_data_reused(self, temp_records_file: Path) -> None:
        service = RetrievalService(records_path=temp_records_file)
        res1 = service.query(RetrievalQueryRequest(query="test"))
        assert service._cached_records is not None
        assert len(service._cached_records) == 3

        # Patch builtins.open to verify disk is not re-read on subsequent queries
        with patch("builtins.open", side_effect=RuntimeError("Disk should not be read when cached")):
            res2 = service.query(RetrievalQueryRequest(query="test"))
            assert res2.total_matches == res1.total_matches
            assert res2.returned_count == res1.returned_count


# ─────────────────────────────────────────────────────────────────────────────
# 6. Week 4 Day 3 Free-Text Query API Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestApiFreeTextQueryEndpoint:
    def test_api_basic_text_search(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "migration"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        for r in data["results"]:
            assert r["relevance_score"] is not None
            assert r["relevance_score"] > 0

    def test_api_case_insensitive_search(self) -> None:
        r1 = client.post("/api/retrieval/query", json={"query": "MIGRATION"}).json()
        r2 = client.post("/api/retrieval/query", json={"query": "migration"}).json()
        assert r1["total_matches"] == r2["total_matches"]

    def test_api_subject_matching(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "arun"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        assert any("arun" in r["subject"].lower() for r in data["results"])

    def test_api_object_matching(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "gcp"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        assert any("gcp" in r["object"].lower() for r in data["results"])

    def test_api_display_name_matching(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "Arun"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        assert any("arun" in r["subject"].lower() or (r["subject_display"] and "arun" in r["subject_display"].lower()) for r in data["results"])

    def test_api_relation_matching(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "MIGRATED_TO"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        assert all("MIGRATED_TO" in r["relation"] for r in data["results"])

    def test_api_evidence_matching(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "leadership"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        assert all("leadership" in r["evidence"].lower() for r in data["results"])

    def test_api_source_matching(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "jira"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        assert any("jira" in r["source"].lower() or "jira" in r["source_id"].lower() for r in data["results"])

    def test_api_no_match_query(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "non_existent_xyz_999"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 0
        assert data["returned_count"] == 0
        assert data["results"] == []

    def test_api_query_plus_entity_filter(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "migration", "entity_hints": ["gcp"]})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0

    def test_api_query_plus_relation_filter(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "gcp", "relation_hints": ["MIGRATED_TO"]})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        for r in data["results"]:
            assert r["relation"] == "MIGRATED_TO"

    def test_api_query_plus_source_filter(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "migration", "sources": ["slack"]})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        for r in data["results"]:
            assert r["source"] == "slack"

    def test_api_query_plus_temporal_filter(self) -> None:
        payload = {
            "query": "migration",
            "after_date": "2023-04-01",
            "page": 1,
            "page_size": 10,
        }
        response = client.post("/api/retrieval/query", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        for r in data["results"]:
            assert r["event_date"] > "2023-04-01"

    def test_api_query_plus_pagination(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "migration", "page": 1, "page_size": 5})
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert data["returned_count"] == 5
        assert len(data["results"]) == 5

    def test_api_query_plus_sorting_asc_desc(self) -> None:
        r_asc = client.post("/api/retrieval/query", json={"query": "migration", "sort_order": "asc", "page_size": 10}).json()
        r_desc = client.post("/api/retrieval/query", json={"query": "migration", "sort_order": "desc", "page_size": 10}).json()
        assert r_asc["total_matches"] == r_desc["total_matches"]

    def test_api_relevance_ordering(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "gcp migration"})
        assert response.status_code == 200
        scores = [r["relevance_score"] for r in response.json()["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_api_backward_compatibility_empty_query(self) -> None:
        response = client.post("/api/retrieval/query", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 142
        for r in data["results"]:
            assert r["relevance_score"] is None

    def test_api_existing_limit_behavior(self) -> None:
        response = client.post("/api/retrieval/query", json={"query": "migration", "limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert data["returned_count"] == 3
        assert len(data["results"]) == 3


# ─────────────────────────────────────────────────────────────────────────────
# 7. Week 4 Day 4 Error Handling & Resilience Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRetrievalErrorHandlingAndResilience:
    """Comprehensive test suite for Week 4 Day 4 Error Handling & Resilience."""

    def test_missing_retrieval_file_exception(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "missing_records.json"
        service = RetrievalService(records_path=non_existent)
        with pytest.raises(RetrievalDataNotFoundError) as exc_info:
            service.load_records()
        assert isinstance(exc_info.value, RetrievalDataError)
        assert isinstance(exc_info.value, RetrievalServiceError)
        assert isinstance(exc_info.value, RetrievalError)

    def test_empty_retrieval_file_handling(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "retrieval_ready_records.json"
        empty_file.write_text("   \n  ", encoding="utf-8")
        service = RetrievalService(records_path=empty_file)
        records = service.load_records()
        assert records == []
        # Querying an empty records file should return 0 results safely without crashing
        resp = service.query(RetrievalQueryRequest(query="test"))
        assert resp.total_matches == 0
        assert resp.returned_count == 0
        assert resp.results == []

    def test_invalid_json_raises_format_error(self, tmp_path: Path) -> None:
        corrupted_file = tmp_path / "corrupted.json"
        corrupted_file.write_text("{ unclosed json: [1, 2, 3", encoding="utf-8")
        service = RetrievalService(records_path=corrupted_file)
        with pytest.raises(RetrievalDataFormatError):
            service.load_records()

    def test_invalid_top_level_structure_dict(self, tmp_path: Path) -> None:
        dict_file = tmp_path / "dict_top_level.json"
        dict_file.write_text('{"records": [{"record_id": "123"}]}', encoding="utf-8")
        service = RetrievalService(records_path=dict_file)
        with pytest.raises(RetrievalDataFormatError) as exc_info:
            service.load_records()
        assert "Expected a JSON list of records" in str(exc_info.value)

    def test_invalid_top_level_structure_primitive(self, tmp_path: Path) -> None:
        primitive_file = tmp_path / "primitive.json"
        primitive_file.write_text('"just a string"', encoding="utf-8")
        service = RetrievalService(records_path=primitive_file)
        with pytest.raises(RetrievalDataFormatError):
            service.load_records()

    def test_malformed_individual_records_skipped(
        self, tmp_path: Path, sample_records_data: List[Dict[str, Any]]
    ) -> None:
        mixed_records = list(sample_records_data)
        # Add non-dict item
        mixed_records.append(12345)
        mixed_records.append("string item")
        # Add item missing required fields
        mixed_records.append({"source": "slack", "invalid": "record"})
        mixed_records.append({"record_id": "invalid_date", "timestamp": "not-a-timestamp"})

        mixed_file = tmp_path / "mixed.json"
        with open(mixed_file, "w", encoding="utf-8") as fh:
            json.dump(mixed_records, fh)

        service = RetrievalService(records_path=mixed_file)
        records = service.load_records()
        # Only the 3 valid records from sample_records_data should be loaded
        assert len(records) == 3
        assert [r.record_id for r in records] == ["rec_001", "rec_002", "rec_003"]

    def test_missing_required_fields_skipped(
        self, tmp_path: Path, sample_records_data: List[Dict[str, Any]]
    ) -> None:
        # Create a record missing 'evidence' and 'subject'
        bad_rec = dict(sample_records_data[0])
        del bad_rec["evidence"]
        del bad_rec["subject"]

        data = [bad_rec, sample_records_data[1]]
        file_path = tmp_path / "missing_fields.json"
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        service = RetrievalService(records_path=file_path)
        records = service.load_records()
        assert len(records) == 1
        assert records[0].record_id == "rec_002"

    def test_api_404_safe_response_when_retrieval_data_missing(self) -> None:
        with patch.object(
            RetrievalService,
            "query",
            side_effect=RetrievalDataNotFoundError("Data file not found at /secret/path/on/disk"),
        ):
            response = client.post("/api/retrieval/query", json={"query": "test"})
            assert response.status_code == 404
            data = response.json()
            assert "detail" in data
            # Message must be safe and not reveal filesystem secrets
            assert "not found" in data["detail"].lower()
            assert "/secret/path/on/disk" not in data["detail"]
            assert "Traceback" not in data["detail"]

    def test_api_500_safe_response_when_corrupted_data(self) -> None:
        with patch.object(
            RetrievalService,
            "query",
            side_effect=RetrievalDataFormatError("Corrupted JSON at char 42 on /var/internal/db"),
        ):
            response = client.post("/api/retrieval/query", json={"query": "test"})
            assert response.status_code == 500
            data = response.json()
            assert "detail" in data
            assert "corrupted" in data["detail"].lower()
            assert "/var/internal/db" not in data["detail"]
            assert "Traceback" not in data["detail"]

    def test_api_500_safe_response_on_unexpected_exception(self) -> None:
        with patch.object(
            RetrievalService,
            "query",
            side_effect=RuntimeError("Secret DB connection failed: postgres://admin:secretPass@internal-db:5432"),
        ):
            response = client.post("/api/retrieval/query", json={"query": "test"})
            assert response.status_code == 500
            data = response.json()
            assert "detail" in data
            # Must return generic safe message and NOT leak DB URL or secrets
            assert data["detail"] == "Internal server error occurred while processing retrieval query."
            assert "postgres://" not in data["detail"]
            assert "secretPass" not in data["detail"]

    def test_api_invalid_request_returns_422(self) -> None:
        # Invalid sort_order value
        response = client.post("/api/retrieval/query", json={"sort_order": "random_order"})
        assert response.status_code == 422

        # Invalid page number (<= 0)
        response = client.post("/api/retrieval/query", json={"page": -1})
        assert response.status_code == 422

        # Invalid source list containing invalid types
        response = client.post("/api/retrieval/query", json={"sources": 12345})
        assert response.status_code == 422

    def test_cached_valid_data_remains_usable_on_failed_reload(
        self, tmp_path: Path, sample_records_data: List[Dict[str, Any]]
    ) -> None:
        file_path = tmp_path / "records.json"
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(sample_records_data, fh)

        service = RetrievalService(records_path=file_path)
        # Initial load succeeds
        initial_records = service.load_records()
        assert len(initial_records) == 3

        # Now corrupt the file on disk
        file_path.write_text("{ corrupt json", encoding="utf-8")

        # Attempting force_reload raises RetrievalDataFormatError
        with pytest.raises(RetrievalDataFormatError):
            service.load_records(force_reload=True)

        # But the previous cached records must remain intact and usable!
        cached = service.load_records(force_reload=False)
        assert len(cached) == 3
        assert [r.record_id for r in cached] == ["rec_001", "rec_002", "rec_003"]

        # Queries still execute successfully using cached records
        resp = service.query(RetrievalQueryRequest(query="arun"))
        assert resp.total_matches == 1
        assert resp.results[0].subject == "arun_sharma"

    def test_force_reload_behavior(
        self, tmp_path: Path, sample_records_data: List[Dict[str, Any]]
    ) -> None:
        file_path = tmp_path / "records.json"
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(sample_records_data[:2], fh)

        service = RetrievalService(records_path=file_path)
        records_initial = service.load_records()
        assert len(records_initial) == 2

        # Update disk file with 3 records
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(sample_records_data, fh)

        # Without force_reload, cached 2 records are returned
        assert len(service.load_records()) == 2

        # With force_reload=True, new 3 records are loaded into cache
        records_updated = service.load_records(force_reload=True)
        assert len(records_updated) == 3

    def test_stats_api_safe_error_handling(self) -> None:
        with patch.object(
            RetrievalService,
            "get_stats",
            side_effect=RetrievalDataNotFoundError("Stats records not found on /server/path"),
        ):
            response = client.get("/api/retrieval/stats")
            assert response.status_code == 404
            data = response.json()
            assert "not found" in data["detail"].lower()
            assert "/server/path" not in data["detail"]

    def test_api_health_safe_when_unreadable_data(self, tmp_path: Path) -> None:
        unreadable_file = tmp_path / "unreadable.json"
        unreadable_file.write_text("invalid json", encoding="utf-8")
        service = RetrievalService(records_path=unreadable_file)
        health = service.get_health()
        assert health.status == "ok"
        assert health.retrieval_data_available is True
        assert health.retrieval_records_count is None
    def test_successful_retrieval_behavior_remains_unchanged(self) -> None:
        # Full integration test against real dataset
        response = client.post(
            "/api/retrieval/query",
            json={
                "query": "GCP",
                "sources": ["slack", "github"],
                "sort_order": "desc",
                "page": 1,
                "page_size": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] > 0
        assert data["returned_count"] <= 10
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert len(data["results"]) == data["returned_count"]
        # Verify provenance integrity
        for rec in data["results"]:
            assert rec["record_id"]
            assert rec["source"] in ["slack", "github"]
            assert rec["evidence"]
            assert rec["timestamp"]


# ─────────────────────────────────────────────────────────────────────────────
# 8. Week 4 Day 5 — Performance & Cache Regression Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRetrievalPerformanceCacheRegression:
    """
    Deterministic tests proving that the in-memory cache avoids repeated
    disk reads, that force_reload triggers exactly one additional read,
    and that multiple different queries reuse the same cached records.
    """

    # ── File-read regression ─────────────────────────────────────────────────

    def test_first_query_reads_file_once(
        self, temp_records_file: Path, sample_records_data: List[Dict[str, Any]]
    ) -> None:
        """First call to load_records() must read the file exactly once."""
        service = RetrievalService(records_path=temp_records_file)
        assert service._cached_records is None  # nothing cached yet

        read_calls: List[str] = []
        original_open = open

        def counting_open(path, *args, **kwargs):
            read_calls.append(str(path))
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=counting_open):
            records = service.load_records()

        assert len(records) == 3
        # Exactly one open() call that touches the records file
        records_file_reads = [c for c in read_calls if "retrieval_ready_records" in c]
        assert len(records_file_reads) == 1

    def test_second_query_does_not_read_file(
        self, temp_records_file: Path
    ) -> None:
        """After the first load, subsequent queries must NOT touch the disk."""
        service = RetrievalService(records_path=temp_records_file)
        # Prime the cache with the first query
        resp1 = service.query(RetrievalQueryRequest(query="arun"))
        assert service._cached_records is not None

        # Subsequent query: patch open() so any disk access raises immediately
        with patch("builtins.open", side_effect=RuntimeError("Disk must not be read on cache hit")):
            resp2 = service.query(RetrievalQueryRequest(query="gcp"))

        # Results must be consistent with the cached data
        assert resp2.total_matches >= 0  # deterministic: 0 or more from 3 records
        assert resp1.total_matches >= 0

    def test_force_reload_reads_file_again(
        self, temp_records_file: Path, sample_records_data: List[Dict[str, Any]]
    ) -> None:
        """force_reload=True must trigger exactly one additional file read."""
        service = RetrievalService(records_path=temp_records_file)

        # Initial load — primes cache
        service.load_records()
        assert service._cached_records is not None

        read_calls: List[str] = []
        original_open = open

        def counting_open(path, *args, **kwargs):
            read_calls.append(str(path))
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=counting_open):
            reloaded = service.load_records(force_reload=True)

        assert len(reloaded) == 3
        records_file_reads = [c for c in read_calls if "retrieval_ready_records" in c]
        assert len(records_file_reads) == 1, (
            "force_reload=True should cause exactly one additional disk read"
        )

    # ── Multiple queries share one cache ────────────────────────────────────

    def test_multiple_different_queries_use_same_cache(
        self, temp_records_file: Path
    ) -> None:
        """Different queries against the same service instance must never reload from disk."""
        service = RetrievalService(records_path=temp_records_file)
        # Prime cache
        service.load_records()
        cache_id = id(service._cached_records)

        queries = [
            RetrievalQueryRequest(query="arun"),
            RetrievalQueryRequest(entity_hints=["gcp"]),
            RetrievalQueryRequest(relation_hints=["MIGRATED_TO"]),
            RetrievalQueryRequest(sources=["slack"]),
            RetrievalQueryRequest(sort_order="desc"),
        ]

        for q in queries:
            with patch("builtins.open", side_effect=RuntimeError("Disk must not be accessed")):
                service.query(q)
            # Cache object identity must not change
            assert id(service._cached_records) == cache_id

    def test_three_successive_queries_same_total_matches(
        self, temp_records_file: Path
    ) -> None:
        """Same query issued three times must return identical total_matches."""
        service = RetrievalService(records_path=temp_records_file)
        req = RetrievalQueryRequest(entity_hints=["gcp"])

        r1 = service.query(req)
        r2 = service.query(req)
        r3 = service.query(req)

        assert r1.total_matches == r2.total_matches == r3.total_matches
        assert r1.total_matches == 2  # rec_001 and rec_003

    # ── Cache behavior after invalid reload ─────────────────────────────────

    def test_cache_preserved_after_failed_force_reload(
        self, tmp_path: Path, sample_records_data: List[Dict[str, Any]]
    ) -> None:
        """If force_reload fails, the previously cached data must remain usable."""
        file_path = tmp_path / "retrieval_ready_records.json"
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(sample_records_data, fh)

        service = RetrievalService(records_path=file_path)
        initial = service.load_records()
        assert len(initial) == 3

        # Corrupt the file
        file_path.write_text("{ bad json", encoding="utf-8")

        with pytest.raises(RetrievalDataFormatError):
            service.load_records(force_reload=True)

        # Cache must still hold the 3 good records
        assert service._cached_records is not None
        assert len(service._cached_records) == 3

        # Querying must succeed using cached records
        with patch("builtins.open", side_effect=RuntimeError("Must not re-read")):
            resp = service.query(RetrievalQueryRequest(entity_hints=["gcp"]))
        assert resp.total_matches == 2

    # ── Large result set pagination ─────────────────────────────────────────

    def test_large_result_set_paginated_completely(self) -> None:
        """Paginate through all 142 production records using page_size=20."""
        page_size = 20
        page = 1
        collected_ids: List[str] = []
        total_matches: int = -1

        while True:
            resp = client.post(
                "/api/retrieval/query",
                json={"page": page, "page_size": page_size},
            )
            assert resp.status_code == 200
            data = resp.json()

            if total_matches == -1:
                total_matches = data["total_matches"]
                assert total_matches == 142

            collected_ids.extend(r["record_id"] for r in data["results"])

            if not data["has_next"]:
                break
            page += 1

        assert len(collected_ids) == total_matches
        # No duplicate record IDs across pages
        assert len(set(collected_ids)) == total_matches

    def test_large_result_single_page(self) -> None:
        """Requesting page_size=100 returns first 100 records cleanly."""
        resp = client.post("/api/retrieval/query", json={"page": 1, "page_size": 100})
        assert resp.status_code == 200
        data = resp.json()
        assert data["returned_count"] == 100
        assert data["total_matches"] == 142
        assert data["total_pages"] == 2

    # ── Combined filters + pagination ────────────────────────────────────────

    def test_entity_filter_then_pagination(self) -> None:
        """Filter by entity then paginate; total_matches must be stable across pages."""
        p1 = client.post(
            "/api/retrieval/query",
            json={"entity_hints": ["gcp"], "page": 1, "page_size": 3},
        ).json()
        p2 = client.post(
            "/api/retrieval/query",
            json={"entity_hints": ["gcp"], "page": 2, "page_size": 3},
        ).json()

        assert p1["total_matches"] == p2["total_matches"]
        assert p1["total_matches"] > 0

        p1_ids = {r["record_id"] for r in p1["results"]}
        p2_ids = {r["record_id"] for r in p2["results"]}
        assert p1_ids.isdisjoint(p2_ids), "Page 1 and page 2 results must be distinct"

    def test_text_query_then_pagination(self) -> None:
        """Free-text query results must paginate consistently."""
        resp_p1 = client.post(
            "/api/retrieval/query",
            json={"query": "migration", "page": 1, "page_size": 5},
        )
        resp_p2 = client.post(
            "/api/retrieval/query",
            json={"query": "migration", "page": 2, "page_size": 5},
        )
        assert resp_p1.status_code == 200
        assert resp_p2.status_code == 200

        d1 = resp_p1.json()
        d2 = resp_p2.json()

        assert d1["total_matches"] == d2["total_matches"]
        assert d1["returned_count"] == 5

        p1_ids = {r["record_id"] for r in d1["results"]}
        p2_ids = {r["record_id"] for r in d2["results"]}
        assert p1_ids.isdisjoint(p2_ids)

    def test_sort_desc_then_pagination(self) -> None:
        """Descending sort must be maintained across pagination boundaries."""
        p1 = client.post(
            "/api/retrieval/query",
            json={"sort_order": "desc", "page": 1, "page_size": 10},
        ).json()
        p2 = client.post(
            "/api/retrieval/query",
            json={"sort_order": "desc", "page": 2, "page_size": 10},
        ).json()

        d1 = [r["event_date"] for r in p1["results"]]
        d2 = [r["event_date"] for r in p2["results"]]
        assert d1 == sorted(d1, reverse=True), "Page 1 must be sorted desc"
        assert d2 == sorted(d2, reverse=True), "Page 2 must be sorted desc"
        # Boundary: earliest date on page 1 must be >= latest date on page 2
        assert min(d1) >= max(d2)

    def test_combined_source_entity_filter(self) -> None:
        """Source + entity combined filter must return only matching records."""
        resp = client.post(
            "/api/retrieval/query",
            json={"sources": ["github"], "entity_hints": ["gcp"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert r["source"] == "github"
            assert "gcp" in r["subject"].lower() or "gcp" in r["object"].lower()

    def test_combined_source_relation_filter(self) -> None:
        """Source + relation combined filter must honour both constraints."""
        resp = client.post(
            "/api/retrieval/query",
            json={"sources": ["jira"], "relation_hints": ["RAISED_CONCERN"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert r["source"] == "jira"
            assert r["relation"] == "RAISED_CONCERN"

    def test_combined_query_source_temporal(self) -> None:
        """Free-text + source + temporal combined filter."""
        resp = client.post(
            "/api/retrieval/query",
            json={
                "query": "gcp",
                "sources": ["slack"],
                "after_date": "2023-03-01",
                "page": 1,
                "page_size": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert r["source"] == "slack"
            assert r["event_date"] > "2023-03-01"
            assert r["relevance_score"] is not None

    # ── API success after previous error scenario ────────────────────────────

    def test_api_recovers_after_simulated_error(self) -> None:
        """After a simulated error response, the API must serve valid requests correctly."""
        # Simulate an error first
        with patch.object(
            RetrievalService,
            "query",
            side_effect=RetrievalDataNotFoundError("simulated"),
        ):
            err_resp = client.post("/api/retrieval/query", json={})
            assert err_resp.status_code == 404

        # Normal query must succeed immediately after
        ok_resp = client.post("/api/retrieval/query", json={"limit": 5})
        assert ok_resp.status_code == 200
        data = ok_resp.json()
        assert data["total_matches"] > 0
        assert data["returned_count"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# 9. Week 4 Day 5 — API Endpoint Regression Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestApiRetrievalRegression:
    """Verify that all existing endpoints continue to behave correctly after Day 5 changes."""

    def test_health_endpoint_still_returns_ok(self) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "ChronoGraph Retrieval API"
        assert data["version"] == "1.0.0"
        assert "retrieval_data_available" in data

    def test_stats_endpoint_still_returns_data(self) -> None:
        resp = client.get("/api/retrieval/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_records"] == 142
        assert "source_breakdown" in data

    def test_normal_query_regression(self) -> None:
        resp = client.post("/api/retrieval/query", json={"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] == 142
        assert data["returned_count"] == 10
        assert len(data["results"]) == 10

    def test_paginated_query_regression(self) -> None:
        resp = client.post("/api/retrieval/query", json={"page": 3, "page_size": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 3
        assert data["returned_count"] == 10
        assert data["has_previous"] is True

    def test_free_text_query_regression(self) -> None:
        resp = client.post("/api/retrieval/query", json={"query": "migration", "limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] > 0
        for r in data["results"]:
            assert r["relevance_score"] is not None

    def test_temporal_query_regression(self) -> None:
        resp = client.post(
            "/api/retrieval/query",
            json={"start_date": "2023-03-01", "end_date": "2023-06-30", "limit": 20},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] > 0
        for r in data["results"]:
            assert "2023-03-01" <= r["event_date"] <= "2023-06-30"

    def test_combined_query_regression(self) -> None:
        resp = client.post(
            "/api/retrieval/query",
            json={
                "query": "gcp",
                "entity_hints": ["gcp"],
                "sources": ["slack", "github"],
                "sort_order": "desc",
                "page": 1,
                "page_size": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] > 0
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_error_response_regression(self) -> None:
        # 422 on invalid input
        resp = client.post("/api/retrieval/query", json={"page": -1})
        assert resp.status_code == 422

        # 404 on missing data
        with patch.object(
            RetrievalService,
            "query",
            side_effect=RetrievalDataNotFoundError("missing"),
        ):
            resp = client.post("/api/retrieval/query", json={})
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()

        # 500 on corrupted data
        with patch.object(
            RetrievalService,
            "query",
            side_effect=RetrievalDataFormatError("bad json"),
        ):
            resp = client.post("/api/retrieval/query", json={})
            assert resp.status_code == 500
            assert "corrupted" in resp.json()["detail"].lower()
