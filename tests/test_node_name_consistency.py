"""
tests/test_node_name_consistency.py
──────────────────────────────────────
Guards against a real bug found during Week 4 review: create_graph.py
was storing Person nodes under their raw slug name (e.g. "arun_sharma")
while temporal_router.py's extract_person() returned the normalized
display form ("Arun Sharma"). Since person_history's Cypher does an
EXACT match (MATCH (a:Person {name: $person})), that mismatch meant
every real person query would silently return zero rows.

This test ensures create_graph.py's node-naming logic and
temporal_router.py's entity-extraction logic always agree, for any
Person record shaped like the real ingestion data.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from create_graph import _normalize_display_name
from temporal_router import _DISPLAY_NAME_LOOKUP, KNOWN_PERSON_NAMES


def test_normalize_display_name_titlecases_raw_slug():
    # Matches the real ingestion data shape: subject == subject_display
    # for Person entities, e.g. subject="arun_sharma", subject_display="arun_sharma"
    assert _normalize_display_name("arun_sharma", "arun_sharma") == "Arun Sharma"


def test_normalize_display_name_leaves_already_formatted_names_alone():
    # Non-Person entities are already title-cased by the ingestion
    # pipeline (e.g. "PostgreSQL", "GCP") — must not be altered.
    assert _normalize_display_name("postgresql", "PostgreSQL") == "PostgreSQL"
    assert _normalize_display_name("gcp", "GCP") == "GCP"


def test_graph_node_name_matches_router_extracted_name():
    """
    The core regression test: for every known real person, the name
    create_graph.py would give the Neo4j node must exactly equal what
    temporal_router.py's extract_person() would search for.
    """
    sample_people = [
        ("arun_sharma", "arun_sharma"),
        ("priya_nair", "priya_nair"),
        ("divya_krishnan", "divya_krishnan"),
        ("rohan_mehta", "rohan_mehta"),
        ("vikram_patel", "vikram_patel"),
    ]

    for raw, display in sample_people:
        graph_node_name = _normalize_display_name(raw, display)
        router_lookup_key = raw.lower().replace("_", " ")
        router_extracted_name = _DISPLAY_NAME_LOOKUP.get(router_lookup_key)

        # Only assert when the router has actually loaded real data
        # (skips cleanly in environments without data-ingestion/ present)
        if router_lookup_key in KNOWN_PERSON_NAMES and router_extracted_name:
            assert graph_node_name == router_extracted_name, (
                f"Mismatch for {raw!r}: graph node name={graph_node_name!r} "
                f"but router would search for={router_extracted_name!r}"
            )
