import sys
from pathlib import Path
import pytest


# Add backend directory to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

sys.path.insert(0, str(BACKEND_DIR))


from temporal_router import (
    detect_intent,
    extract_person,
    extract_technology,
    extract_dates,
    build_query
)


# ---------------------------------------------------------
# Intent tests
# ---------------------------------------------------------

def test_all_events_intent():
    assert detect_intent(
        "Show all temporal events"
    ) == "all_events"


def test_person_history_intent():
    assert detect_intent(
        "Show Rahul history"
    ) == "person_history"


def test_technology_history_intent():
    assert detect_intent(
        "Show GCP history"
    ) == "technology_history"


def test_events_after_intent():
    assert detect_intent(
        "Show events after August 10 2026"
    ) == "events_after"


def test_events_between_intent():
    assert detect_intent(
        "Show events between August 10 2026 and August 11 2026"
    ) == "events_between"


# ---------------------------------------------------------
# Entity extraction tests
# ---------------------------------------------------------

def test_extract_person():
    assert extract_person(
        "Show Rahul history"
    ) == "Rahul"


def test_extract_technology():
    assert extract_technology(
        "Show GCP history"
    ) == "GCP"


# ---------------------------------------------------------
# Date extraction tests
# ---------------------------------------------------------

def test_extract_date():
    dates = extract_dates(
        "Show events after August 10 2026"
    )

    assert dates == ["2026-08-10"]


def test_extract_two_dates():
    dates = extract_dates(
        "Show events between August 10 2026 and August 11 2026"
    )

    assert dates == [
        "2026-08-10",
        "2026-08-11"
    ]


# ---------------------------------------------------------
# Query building tests
# ---------------------------------------------------------

def test_build_person_query():

    intent, query, parameters = build_query(
        "Show Rahul history"
    )

    assert intent == "person_history"
    assert "MATCH" in query
    assert parameters["person"] == "Rahul"


def test_build_technology_query():

    intent, query, parameters = build_query(
        "Show GCP history"
    )

    assert intent == "technology_history"
    assert "MATCH" in query
    assert parameters["technology"] == "GCP"


def test_build_after_date_query():

    intent, query, parameters = build_query(
        "Show events after August 10 2026"
    )

    assert intent == "events_after"
    assert parameters["start_date"] == "2026-08-10"


def test_build_between_dates_query():

    intent, query, parameters = build_query(
        "Show events between August 10 2026 and August 11 2026"
    )

    assert intent == "events_between"

    assert parameters["start_date"] == "2026-08-10"

    assert parameters["end_date"] == "2026-08-11"


# ---------------------------------------------------------
# Invalid query tests
# ---------------------------------------------------------

def test_invalid_question():

    with pytest.raises(ValueError):

        build_query(
            "Tell me something random"
        )