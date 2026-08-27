"""
tests/test_real_entity_extraction.py
─────────────────────────────────────
Verifies that entity extraction and intent detection work against the
real people and entities from Karkuvel's data-ingestion module
(graph_ready_triples.json), not just the Week 1/2 demo names
(Rahul, Priya, AWS, GCP).
"""

import sys
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from temporal_router import detect_intent, extract_person, extract_technology

DATA_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "data-ingestion" / "data" / "processed" / "graph_ready_triples.json"
)

requires_real_data = pytest.mark.skipif(
    not DATA_FILE.exists(),
    reason="data-ingestion module output not found alongside this repo",
)


@requires_real_data
def test_real_person_intent_detected():
    assert detect_intent("Show arun sharma history") == "person_history"


@requires_real_data
def test_real_person_extracted_with_clean_display_name():
    # Raw ingestion data stores Person names as slugs (arun_sharma);
    # extract_person should return a human-readable form.
    assert extract_person("Show arun sharma history") == "Arun Sharma"


@requires_real_data
def test_real_technology_intent_detected():
    assert detect_intent("Show postgresql history") == "technology_history"


@requires_real_data
def test_real_technology_extracted():
    assert extract_technology("Show kubernetes events") == "Kubernetes"


@requires_real_data
def test_demo_names_still_work_alongside_real_data():
    # Backward compatibility: original Week 1/2 demo names must keep working.
    assert extract_person("Show Rahul history") == "Rahul"
    assert extract_technology("Show GCP history") == "GCP"
