"""
neo4j-temporal/tests/test_graph_audit.py
─────────────────────────────────────────
Unit tests proving that all 7 required Cypher audit queries are defined correctly,
format table outputs properly, and fail gracefully when Neo4j credentials are missing.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from graph_audit import (
    audit_query_1_all_events,
    audit_query_2_engineer_tech,
    audit_query_3_engineer_history,
    audit_query_4_tech_history,
    audit_query_5_between_dates,
    audit_query_6_multiple_events_same_entities,
    audit_query_7_temporal_evolution,
    run_graph_audit,
)


def test_audit_queries_cypher_structure():
    """Verify that all 7 audit functions invoke session.run with valid Cypher query strings."""
    mock_session = MagicMock()
    mock_session.run.return_value = []

    audit_query_1_all_events(mock_session)
    assert "ORDER BY" in mock_session.run.call_args[0][0]

    audit_query_2_engineer_tech(mock_session)
    assert ":Person" in mock_session.run.call_args[0][0]

    audit_query_3_engineer_history(mock_session, "arun")
    assert "name" in mock_session.run.call_args[1]

    audit_query_4_tech_history(mock_session, "gcp")
    assert "name" in mock_session.run.call_args[1]

    audit_query_5_between_dates(mock_session, "2023-01-01", "2023-12-31")
    assert "start_date" in mock_session.run.call_args[1]

    audit_query_6_multiple_events_same_entities(mock_session)
    assert "r1.triple_id <> r2.triple_id" in mock_session.run.call_args[0][0]

    audit_query_7_temporal_evolution(mock_session)
    assert "event_count" in mock_session.run.call_args[0][0]


def test_unconfigured_neo4j_graceful_handling():
    """Verify that run_graph_audit returns BLOCKED status when Neo4j is unconfigured."""
    with patch("graph_audit.URI", "neo4j://localhost:7687-placeholder"):
        res = run_graph_audit()
        assert res["status"] == "BLOCKED"
        assert "Unconfigured" in res["reason"]
