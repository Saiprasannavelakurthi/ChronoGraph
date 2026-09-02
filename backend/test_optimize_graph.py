"""
tests/test_optimize_graph.py
──────────────────────────────
Week 4 — unit tests for optimize_graph.py's index/constraint naming
logic. These use a fake session object (no live Neo4j connection
required) so they run in CI/local pytest without hitting Aura, the
same pattern used elsewhere in this test suite for offline-safe checks.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from optimize_graph import (
    create_node_name_indexes,
    create_relationship_timestamp_indexes,
)


class FakeSession:
    """Records every Cypher statement passed to session.run() instead of
    executing it, so we can assert on the generated index-creation
    statements without a live database."""

    def __init__(self):
        self.executed_queries = []

    def run(self, query, *args, **kwargs):
        self.executed_queries.append(query)
        return []


def test_create_node_name_indexes_covers_all_labels():
    session = FakeSession()
    labels = ["Person", "Technology", "Database", "Service"]

    created = create_node_name_indexes(session, labels)

    assert len(created) == len(labels)
    assert "idx_person_name" in created
    assert "idx_technology_name" in created
    # every label must have produced exactly one CREATE INDEX statement
    assert len(session.executed_queries) == len(labels)


def test_create_node_name_indexes_uses_if_not_exists():
    session = FakeSession()
    create_node_name_indexes(session, ["Person"])

    query = session.executed_queries[0]
    assert "IF NOT EXISTS" in query
    assert "ON (n.name)" in query
    assert "Person" in query


def test_create_relationship_timestamp_indexes_covers_all_types():
    session = FakeSession()
    rel_types = ["MIGRATED_TO", "REVIEWED", "RAISED_CONCERN"]

    created = create_relationship_timestamp_indexes(session, rel_types)

    assert len(created) == len(rel_types)
    assert "idx_migrated_to_timestamp" in created
    assert len(session.executed_queries) == len(rel_types)


def test_relationship_index_targets_timestamp_property():
    session = FakeSession()
    create_relationship_timestamp_indexes(session, ["ADVOCATED_FOR"])

    query = session.executed_queries[0]
    assert "ON (r.timestamp)" in query
    assert "ADVOCATED_FOR" in query


def test_empty_label_list_creates_nothing():
    session = FakeSession()
    created = create_node_name_indexes(session, [])

    assert created == []
    assert session.executed_queries == []
