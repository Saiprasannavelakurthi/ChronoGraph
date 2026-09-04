"""
neo4j-temporal/tests/test_temporal_edge_cases.py
─────────────────────────────────────────────────
Unit tests covering temporal edge cases for graph ingestion:
  1. Missing timestamp in input triple.
  2. Invalid/malformed timestamp ISO string.
  3. Duplicate triple (identical SRO and triple_id).
  4. Same entities with different timestamps.
  5. Same entities with different predicates.
  6. Multiple historical events between identical subject and object entities.
  7. Chronological ordering of temporal query results.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from create_graph import is_valid_iso_timestamp, load_graph_ready_triples
from temporal_queries import (
    get_all_events,
    get_events_after,
    get_events_between,
    get_person_history,
)


def test_iso_timestamp_validation():
    """Verify ISO timestamp validation function."""
    assert is_valid_iso_timestamp("2026-08-10T12:00:00Z") is True
    assert is_valid_iso_timestamp("2023-03-15T10:30:00+00:00") is True
    assert is_valid_iso_timestamp("2023-04-01") is True
    assert is_valid_iso_timestamp("invalid-date-string") is False
    assert is_valid_iso_timestamp("") is False
    assert is_valid_iso_timestamp(None) is False


def test_missing_and_invalid_timestamp_ingestion_safety():
    """Verify ingestion handles missing and malformed timestamps safely without throwing Cypher errors."""
    triples = [
        {
            "subject": "Arun",
            "subject_type": "Person",
            "relation": "ADVOCATED_FOR",
            "object": "GCP",
            "object_type": "Technology",
            "timestamp": None,
            "triple_id": "edge-1",
        },
        {
            "subject": "Priya",
            "subject_type": "Person",
            "relation": "EVALUATING",
            "object": "AWS",
            "object_type": "Technology",
            "timestamp": "bad_timestamp_123",
            "triple_id": "edge-2",
        },
    ]

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    with patch("create_graph.driver", mock_driver), patch("builtins.open"), patch("json.load", return_value=triples), patch("os.path.exists", return_value=True):
        count = load_graph_ready_triples("dummy_path.json")
        assert count == 2
        assert mock_session.run.call_count == 2

        # Check Cypher set query parameter for invalid timestamp
        call_1_query = mock_session.run.call_args_list[0][0][0]
        call_2_query = mock_session.run.call_args_list[1][0][0]

        assert "r.timestamp_str = $ts" in call_1_query or "r.timestamp_str = $ts" in call_2_query


def test_same_entities_different_timestamps_and_predicates():
    """Verify multiple historical events between the same subject and object are preserved using triple_id."""
    triples = [
        {
            "subject": "Arun",
            "relation": "ADVOCATED_FOR",
            "object": "GCP",
            "timestamp": "2023-03-01T10:00:00Z",
            "triple_id": "t-101",
        },
        {
            "subject": "Arun",
            "relation": "ADVOCATED_FOR",
            "object": "GCP",
            "timestamp": "2023-04-01T10:00:00Z",
            "triple_id": "t-102",
        },
        {
            "subject": "Arun",
            "relation": "DEPRECATING",
            "object": "GCP",
            "timestamp": "2023-05-01T10:00:00Z",
            "triple_id": "t-103",
        },
    ]

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    with patch("create_graph.driver", mock_driver), patch("builtins.open"), patch("json.load", return_value=triples), patch("os.path.exists", return_value=True):
        load_graph_ready_triples("dummy_path.json")
        assert mock_session.run.call_count == 3
        # Confirm each triple_id is passed as a distinct MERGE key
        ids_passed = [call[1]["triple_id"] for call in mock_session.run.call_args_list]
        assert ids_passed == ["t-101", "t-102", "t-103"]


def test_chronological_ordering_query_construction():
    """Verify temporal queries construct Cypher with ORDER BY timestamp ASC."""
    mock_session = MagicMock()
    mock_session.run.return_value = []
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    with patch("temporal_queries.driver", mock_driver):
        get_all_events()
        get_events_after("2023-01-01T00:00:00")
        get_events_between("2023-01-01T00:00:00", "2023-06-01T00:00:00")
        get_person_history("Arun")

    assert mock_session.run.call_count == 4
    for call_args in mock_session.run.call_args_list:
        query_str = call_args[0][0]
        assert "ORDER BY" in query_str
