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
from src.retrieval.service import (
    RetrievalDataCorruptedError,
    RetrievalDataNotFoundError,
    RetrievalService,
    RetrievalServiceError,
)

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

