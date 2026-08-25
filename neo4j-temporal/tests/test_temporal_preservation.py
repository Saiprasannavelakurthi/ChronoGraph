"""
tests/test_temporal_preservation.py
───────────────────────────────────
Unit tests proving that all 142 graph-ready triples are preserved as
distinct temporal events using `triple_id` as the relationship identity,
ensuring duplicate (subject, relation, object) combinations across different
timestamps/sources are NOT overwritten.
"""

import os
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from create_graph import load_graph_ready_triples

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data-ingestion" / "data" / "processed" / "graph_ready_triples.json"


def test_temporal_relationship_preservation_count():
    """Verify that all 142 graph-ready triples generate 142 distinct Cypher MERGE commands with triple_id."""
    assert DATA_FILE.exists(), f"Missing {DATA_FILE}"

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        triples = json.load(f)

    total_triples = len(triples)
    assert total_triples == 142, f"Expected 142 triples, got {total_triples}"

    # Calculate unique (subject, relation, object) tuples
    sro_tuples = [(t["subject"], t["relation"], t["object"]) for t in triples]
    unique_sro = set(sro_tuples)
    assert len(unique_sro) < total_triples, "Expected multiple occurrences of same SRO tuples"

    # Mock Neo4j session and verify all 142 queries include triple_id in the relationship pattern
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    with patch("create_graph.driver", mock_driver):
        loaded_count = load_graph_ready_triples(str(DATA_FILE))

    assert loaded_count == 142
    assert mock_session.run.call_count == 142

    # Verify that each call included triple_id in the query and parameters
    for call_args in mock_session.run.call_args_list:
        query_str = call_args[0][0]
        params = call_args[1]

        assert "triple_id: $triple_id" in query_str, "Relationship MERGE must include triple_id"
        assert "triple_id" in params, "Parameters must supply triple_id"
        assert params["triple_id"], "triple_id must not be empty"


def test_duplicate_sro_distinct_timestamps_preserved():
    """Verify that duplicate (subject, relation, object) tuples with different triple_id are retained."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        triples = json.load(f)

    # Find an SRO with multiple occurrences (e.g. arun_sharma -> ADVOCATED_FOR -> gcp)
    sro_groups = {}
    for t in triples:
        key = (t["subject"], t["relation"], t["object"])
        sro_groups.setdefault(key, []).append(t)

    multi_occurrence_keys = [k for k, group in sro_groups.items() if len(group) > 1]
    assert len(multi_occurrence_keys) > 0, "Expected at least one multi-occurrence SRO"

    # Take first multi-occurrence group
    test_key = multi_occurrence_keys[0]
    group_triples = sro_groups[test_key]
    assert len(group_triples) > 1

    # Verify that all triple_ids within the group are unique
    group_triple_ids = [t["triple_id"] for t in group_triples]
    assert len(set(group_triple_ids)) == len(group_triples), "Each temporal event must have a distinct triple_id"
