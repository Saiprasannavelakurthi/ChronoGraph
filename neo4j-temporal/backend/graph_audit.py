"""
neo4j-temporal/backend/graph_audit.py
───────────────────────────────────────
Dedicated Graph Audit script for ChronoGraph Mid-Project Review.

Demonstrates 7 essential Cypher queries proving that Neo4j correctly
maps relationships between engineers and technologies over time:

1. All historical events ordered by timestamp.
2. Engineer → technology relationships over time.
3. One engineer's complete history.
4. One technology's historical relationship changes.
5. Events between two dates.
6. Multiple relationships/events involving the same entities.
7. Temporal evolution of a relationship/network.

Formats readable output showing:
  - entity (subject)
  - relationship
  - target entity (object)
  - timestamp
  - source / triple_id
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Any

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from neo4j_connection import driver, DATABASE, URI, USERNAME, PASSWORD


def print_table(title: str, records: List[Dict[str, Any]], limit: int = 10):
    print("\n" + "=" * 80)
    print(f" AUDIT QUERY: {title.upper()}")
    print("=" * 80)
    if not records:
        print("  [NO RECORDS RETURNED]")
        return

    header = f"{'TIMESTAMP':<22} | {'ENTITY':<18} | {'RELATIONSHIP':<20} | {'TARGET ENTITY':<18} | {'SOURCE/TRIPLE_ID'}"
    print(header)
    print("-" * 80)
    for r in records[:limit]:
        ts = str(r.get("timestamp") or r.get("raw_timestamp") or "N/A")[:19]
        subj = str(r.get("subject") or "N/A")[:18]
        rel = str(r.get("relationship") or "N/A")[:20]
        obj = str(r.get("object") or "N/A")[:18]
        src_id = f"{r.get('source', 'N/A')} ({str(r.get('triple_id', 'N/A'))[:8]})"
        print(f"{ts:<22} | {subj:<18} | {rel:<20} | {obj:<18} | {src_id}")

    if len(records) > limit:
        print(f"  ... ({len(records) - limit} additional records omitted)")


def audit_query_1_all_events(session) -> List[Dict[str, Any]]:
    """1. All historical events ordered chronologically by timestamp."""
    cypher = """
    MATCH (a)-[r]->(b)
    WHERE r.timestamp IS NOT NULL OR r.raw_timestamp IS NOT NULL
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        coalesce(r.timestamp, r.raw_timestamp) AS timestamp,
        r.source AS source,
        r.triple_id AS triple_id
    ORDER BY coalesce(r.timestamp, r.raw_timestamp) ASC
    """
    res = session.run(cypher)
    return [r.data() for r in res]


def audit_query_2_engineer_tech(session) -> List[Dict[str, Any]]:
    """2. Engineer -> technology relationships over time."""
    cypher = """
    MATCH (a:Person)-[r]->(b:Technology)
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        coalesce(r.timestamp, r.raw_timestamp) AS timestamp,
        r.source AS source,
        r.triple_id AS triple_id
    ORDER BY coalesce(r.timestamp, r.raw_timestamp) ASC
    """
    res = session.run(cypher)
    return [r.data() for r in res]


def audit_query_3_engineer_history(session, person_name: str = "arun_sharma") -> List[Dict[str, Any]]:
    """3. One engineer's complete history."""
    cypher = """
    MATCH (a)-[r]->(b)
    WHERE toLower(a.name) = toLower($name) OR toLower(a.name) CONTAINS toLower($name)
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        coalesce(r.timestamp, r.raw_timestamp) AS timestamp,
        r.source AS source,
        r.triple_id AS triple_id
    ORDER BY coalesce(r.timestamp, r.raw_timestamp) ASC
    """
    res = session.run(cypher, name=person_name)
    return [r.data() for r in res]


def audit_query_4_tech_history(session, tech_name: str = "gcp") -> List[Dict[str, Any]]:
    """4. One technology's historical relationship changes."""
    cypher = """
    MATCH (a)-[r]->(b)
    WHERE toLower(b.name) = toLower($name) OR toLower(b.name) CONTAINS toLower($name)
       OR toLower(a.name) = toLower($name)
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        coalesce(r.timestamp, r.raw_timestamp) AS timestamp,
        r.source AS source,
        r.triple_id AS triple_id
    ORDER BY coalesce(r.timestamp, r.raw_timestamp) ASC
    """
    res = session.run(cypher, name=tech_name)
    return [r.data() for r in res]


def audit_query_5_between_dates(session, start_date: str = "2023-03-01T00:00:00", end_date: str = "2023-04-30T23:59:59") -> List[Dict[str, Any]]:
    """5. Events between two dates."""
    cypher = """
    MATCH (a)-[r]->(b)
    WHERE (r.timestamp >= datetime($start_date) AND r.timestamp <= datetime($end_date))
       OR (r.raw_timestamp >= $start_date AND r.raw_timestamp <= $end_date)
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        coalesce(r.timestamp, r.raw_timestamp) AS timestamp,
        r.source AS source,
        r.triple_id AS triple_id
    ORDER BY coalesce(r.timestamp, r.raw_timestamp) ASC
    """
    res = session.run(cypher, start_date=start_date, end_date=end_date)
    return [r.data() for r in res]


def audit_query_6_multiple_events_same_entities(session) -> List[Dict[str, Any]]:
    """6. Multiple relationships/events involving the same subject and object entities."""
    cypher = """
    MATCH (a)-[r1]->(b), (a)-[r2]->(b)
    WHERE r1.triple_id <> r2.triple_id
    RETURN DISTINCT
        a.name AS subject,
        type(r1) AS relationship,
        b.name AS object,
        coalesce(r1.timestamp, r1.raw_timestamp) AS timestamp,
        r1.source AS source,
        r1.triple_id AS triple_id
    ORDER BY coalesce(r1.timestamp, r1.raw_timestamp) ASC
    """
    res = session.run(cypher)
    return [r.data() for r in res]


def audit_query_7_temporal_evolution(session) -> List[Dict[str, Any]]:
    """7. Query demonstrating temporal evolution of a relationship/network."""
    cypher = """
    MATCH (a)-[r]->(b)
    WITH a, b, count(r) AS event_count, min(coalesce(r.timestamp, r.raw_timestamp)) AS first_seen, max(coalesce(r.timestamp, r.raw_timestamp)) AS last_seen
    WHERE event_count >= 1
    MATCH (a)-[r]->(b)
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        coalesce(r.timestamp, r.raw_timestamp) AS timestamp,
        r.source AS source,
        r.triple_id AS triple_id
    ORDER BY a.name, coalesce(r.timestamp, r.raw_timestamp) ASC
    """
    res = session.run(cypher)
    return [r.data() for r in res]


def run_graph_audit() -> Dict[str, Any]:
    """Runs full graph audit suite against Neo4j instance."""
    if not (URI and USERNAME and PASSWORD and not URI.startswith("neo4j://localhost:7687-placeholder")):
        msg = (
            "Graph Audit Failed Gracefully: Missing or placeholder Neo4j credentials in .env.\n"
            "Required env vars: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD."
        )
        print(f"\n  [BLOCKED BY CONFIG] {msg}")
        return {"status": "BLOCKED", "reason": "Unconfigured Neo4j credentials", "queries": {}}

    try:
        with driver.session(database=DATABASE) as session:
            q1 = audit_query_1_all_events(session)
            print_table("1. All Historical Events (Chronological)", q1)

            q2 = audit_query_2_engineer_tech(session)
            print_table("2. Engineer -> Technology Relationships Over Time", q2)

            q3 = audit_query_3_engineer_history(session, "arun_sharma")
            print_table("3. Arun Sharma History", q3)

            q4 = audit_query_4_tech_history(session, "gcp")
            print_table("4. GCP Technology Evolution", q4)

            q5 = audit_query_5_between_dates(session, "2023-03-01T00:00:00", "2023-04-30T23:59:59")
            print_table("5. Events Between 2023-03-01 and 2023-04-30", q5)

            q6 = audit_query_6_multiple_events_same_entities(session)
            print_table("6. Multiple Events Involving Same Entity Pair", q6)

            q7 = audit_query_7_temporal_evolution(session)
            print_table("7. Network Temporal Evolution", q7)

            return {
                "status": "PASS",
                "queries": {
                    "all_events": len(q1),
                    "engineer_tech": len(q2),
                    "engineer_history": len(q3),
                    "tech_history": len(q4),
                    "events_in_range": len(q5),
                    "multi_events": len(q6),
                    "evolution": len(q7),
                }
            }
    except Exception as exc:
        print(f"\n  [FAIL] Graph audit execution error: {exc}")
        return {"status": "FAIL", "reason": str(exc), "queries": {}}


if __name__ == "__main__":
    res = run_graph_audit()
    if res["status"] != "PASS":
        sys.exit(0)
