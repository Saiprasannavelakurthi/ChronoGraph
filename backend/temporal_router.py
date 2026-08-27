import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase


# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

QUERY_FILE = BASE_DIR / "data" / "temporal_queries.json"


# ---------------------------------------------------------
# Load temporal query definitions
# ---------------------------------------------------------

with open(QUERY_FILE, "r", encoding="utf-8") as file:
    QUERY_DEFINITIONS = json.load(file)


# ---------------------------------------------------------
# Load real entity names from the data-ingestion module
# ---------------------------------------------------------
#
# Week 1/2 used a hardcoded demo graph (Rahul, Priya, AWS, GCP).
# Week 3 now integrates Karkuvel's real graph_ready_triples.json,
# which contains real people (e.g. arun_sharma) and entities of many
# types (Technology, Database, Service, Project, ArchitectureDecision,
# Issue, Problem). Instead of hardcoding names, we load the known
# entities from that file so intent detection and entity extraction
# work on real data, not just the demo names.

GRAPH_DATA_CANDIDATES = [
    BASE_DIR.parent / "data-ingestion" / "data" / "processed" / "graph_ready_triples.json",
    Path("data-ingestion/data/processed/graph_ready_triples.json"),
    Path("../data-ingestion/data/processed/graph_ready_triples.json"),
]

# Fallback demo names always stay valid so Week 1/2 behavior and
# existing tests keep working even if the ingestion file is absent.
KNOWN_PERSON_NAMES = {"rahul", "priya"}
KNOWN_TECHNOLOGY_NAMES = {"aws", "gcp"}

# display-name lookup so we can return the properly cased form,
# e.g. "arun_sharma" -> "Arun Sharma"
_DISPLAY_NAME_LOOKUP = {"rahul": "Rahul", "priya": "Priya", "aws": "AWS", "gcp": "GCP"}


def _load_known_entities():
    """
    Populate KNOWN_PERSON_NAMES / KNOWN_TECHNOLOGY_NAMES from the real
    ingestion data if it's available. Non-Person entity types
    (Technology, Database, Service, Project, ArchitectureDecision,
    Issue, Problem) are all treated as "technology" style lookups so
    build_query's technology_history intent can match any of them.
    """
    for candidate in GRAPH_DATA_CANDIDATES:
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                triples = json.load(f)

            for t in triples:
                for role in ("subject", "object"):
                    entity_type = t.get(f"{role}_type", "")
                    raw_name = t.get(role, "")
                    display_name = t.get(f"{role}_display", raw_name)

                    if not raw_name:
                        continue

                    key = raw_name.lower().replace("_", " ")

                    if entity_type == "Person":
                        KNOWN_PERSON_NAMES.add(key)
                    else:
                        KNOWN_TECHNOLOGY_NAMES.add(key)

                    # The ingestion pipeline title-cases most entity
                    # types (e.g. "PostgreSQL", "GCP") but leaves
                    # Person display names as raw slugs
                    # (e.g. "arun_sharma"). Clean those up so answers
                    # read naturally.
                    if display_name == raw_name and "_" in display_name:
                        display_name = display_name.replace("_", " ").title()

                    _DISPLAY_NAME_LOOKUP[key] = display_name

            break  # stop at the first candidate that exists


_load_known_entities()


# ---------------------------------------------------------
# Neo4j connection
# ---------------------------------------------------------

if not NEO4J_PASSWORD:
    raise ValueError(
        "NEO4J_PASSWORD is missing. Please configure it in your .env file."
    )

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
)


# ---------------------------------------------------------
# Date extraction
# ---------------------------------------------------------

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12
}


def normalize_date(date_string):
    """
    Convert supported date formats into YYYY-MM-DD.
    """

    date_string = date_string.strip()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d"
    ]

    for fmt in formats:
        try:
            date = datetime.strptime(date_string, fmt)
            return date.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Example: August 10, 2026
    match = re.match(
        r"([A-Za-z]+)\s+(\d{1,2})(?:,\s*|\s+)(\d{4})",
        date_string
    )

    if match:
        month_name = match.group(1).lower()
        day = int(match.group(2))
        year = int(match.group(3))

        if month_name in MONTHS:
            return f"{year:04d}-{MONTHS[month_name]:02d}-{day:02d}"

    raise ValueError(f"Unsupported date format: {date_string}")


# ---------------------------------------------------------
# Intent detection
# ---------------------------------------------------------

def detect_intent(question):
    """
    Identify the temporal query type from a natural-language question.
    """

    text = question.lower().strip()

    # Date range
    if (
        ("between" in text or "from" in text)
        and ("and" in text or "to" in text)
    ):
        return "events_between"

    # Events after / since a date
    if any(
        phrase in text
        for phrase in [
            "after",
            "since",
            "from"
        ]
    ):
        return "events_after"

    # Technology history (now covers any non-Person entity from the
    # real ingestion data: Technology, Database, Service, Project, etc.)
    if any(
        technology in text
        for technology in KNOWN_TECHNOLOGY_NAMES
    ) and any(
        word in text
        for word in ["history", "events", "related", "activity"]
    ):
        return "technology_history"

    # Person history (covers real people from the ingestion data,
    # e.g. "arun_sharma", in addition to the original demo names)
    if any(
        person in text
        for person in KNOWN_PERSON_NAMES
    ) and any(
        word in text
        for word in ["history", "events", "activity", "actions"]
    ):
        return "person_history"

    # All events
    if any(
        phrase in text
        for phrase in [
            "all events",
            "all temporal events",
            "show everything",
            "show all events",
            "all activities"
        ]
    ):
        return "all_events"

    # Default
    return None


# ---------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------

def extract_person(question):
    text = question.lower()

    # Prefer the longest match first so "arun sharma" wins over
    # a shorter partial match if both happened to appear.
    for person in sorted(KNOWN_PERSON_NAMES, key=len, reverse=True):
        if person in text:
            return _DISPLAY_NAME_LOOKUP.get(person, person.title())

    return None


def extract_technology(question):
    text = question.lower()

    for technology in sorted(KNOWN_TECHNOLOGY_NAMES, key=len, reverse=True):
        if technology in text:
            return _DISPLAY_NAME_LOOKUP.get(technology, technology.upper())

    return None


def extract_dates(question):
    """
    Extract dates from common natural-language formats.
    """

    dates = []

    # YYYY-MM-DD
    matches = re.findall(
        r"\b\d{4}-\d{2}-\d{2}\b",
        question
    )

    dates.extend(matches)

    # DD-MM-YYYY
    matches = re.findall(
        r"\b\d{2}-\d{2}-\d{4}\b",
        question
    )

    for match in matches:
        dates.append(normalize_date(match))

    # DD/MM/YYYY
    matches = re.findall(
        r"\b\d{2}/\d{2}/\d{4}\b",
        question
    )

    for match in matches:
        dates.append(normalize_date(match))

    # Month Day, Year
    matches = re.findall(
        r"\b(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2}(?:,\s*|\s+)\d{4}\b",
        question,
        re.IGNORECASE
    )

    for match in matches:
        dates.append(normalize_date(match))

    return dates


# ---------------------------------------------------------
# Query builder
# ---------------------------------------------------------

def build_query(question):
    """
    Convert a natural-language question into a safe,
    predefined Cypher query and parameters.
    """

    intent = detect_intent(question)

    if intent is None:
        raise ValueError(
            "Could not understand the temporal question."
        )

    definition = QUERY_DEFINITIONS[intent]

    query = definition["cypher"]
    parameters = {}

    # Person history
    if intent == "person_history":
        person = extract_person(question)

        if not person:
            raise ValueError(
                "Please specify a person such as Rahul or Priya."
            )

        parameters["person"] = person

    # Technology history
    elif intent == "technology_history":
        technology = extract_technology(question)

        if not technology:
            raise ValueError(
                "Please specify a technology such as AWS or GCP."
            )

        parameters["technology"] = technology

    # Events after date
    elif intent == "events_after":
        dates = extract_dates(question)

        if not dates:
            raise ValueError(
                "Please specify a date."
            )

        parameters["start_date"] = dates[0]

    # Events between dates
    elif intent == "events_between":
        dates = extract_dates(question)

        if len(dates) < 2:
            raise ValueError(
                "Please specify two dates."
            )

        parameters["start_date"] = dates[0]
        parameters["end_date"] = dates[1]

    return intent, query, parameters


# ---------------------------------------------------------
# Execute query
# ---------------------------------------------------------

def execute_temporal_query(question):

    print("\n===== NATURAL LANGUAGE QUESTION =====")
    print(question)

    try:
        intent, query, parameters = build_query(question)

        print("\n===== DETECTED INTENT =====")
        print(intent)

        print("\n===== GENERATED CYPHER =====")
        print(query)

        print("\n===== PARAMETERS =====")
        print(parameters)

        with driver.session(database=DATABASE) as session:
            result = session.run(
                query,
                parameters
            )

            records = [
                record.data()
                for record in result
            ]

        print("\n===== TEMPORAL RESULTS =====")

        if not records:
            print("No matching temporal events found.")
        else:
            for record in records:
                print(record)

        return records

    except Exception as error:
        print("\nERROR:")
        print(error)

        return []


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

if __name__ == "__main__":

    questions = [
        "Show all temporal events",

        "Show Rahul history",

        "Show GCP history",

        "Show events after August 10 2026",

        "Show events between August 10 2026 and August 11 2026"
    ]

    try:
        for question in questions:
            execute_temporal_query(question)

    finally:
        driver.close()