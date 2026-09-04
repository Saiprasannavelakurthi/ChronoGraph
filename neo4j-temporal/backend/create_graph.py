import json
import os
import re
from pathlib import Path
from neo4j_connection import driver, DATABASE


def is_valid_iso_timestamp(ts_str: str) -> bool:
    """Checks if a string is a valid ISO timestamp format acceptable by Neo4j datetime()."""
    if not ts_str or not isinstance(ts_str, str):
        return False
    # Basic check for YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format
    pattern = r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$"
    return bool(re.match(pattern, ts_str))


def create_schema_indexes_and_constraints(session):
    """
    Creates Neo4j constraints and indexes to optimize query performance and ensure entity uniqueness.
    """
    entity_types = ["Person", "Technology", "Service", "Repository", "Issue", "Pull_Request", "Project", "Entity"]
    for et in entity_types:
        try:
            session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (e:{et}) REQUIRE e.name IS UNIQUE")
        except Exception:
            pass


def create_basic_graph():
    """Fallback sample graph creation for basic demonstration."""
    with driver.session(database=DATABASE) as session:
        create_schema_indexes_and_constraints(session)
        # Create people
        session.run("""
            MERGE (rahul:Person {name: "Rahul"})
            MERGE (priya:Person {name: "Priya"})
        """)

        # Create technologies
        session.run("""
            MERGE (aws:Technology {name: "AWS"})
            MERGE (gcp:Technology {name: "GCP"})
        """)

        # Create relationships WITH timestamps
        session.run("""
            MATCH (rahul:Person {name: "Rahul"})
            MATCH (priya:Person {name: "Priya"})
            MATCH (aws:Technology {name: "AWS"})
            MATCH (gcp:Technology {name: "GCP"})

            MERGE (rahul)-[r1:COMMITTED_CODE {triple_id: "demo-1"}]->(aws)
            SET r1.timestamp = datetime("2026-08-10T00:00:00")

            MERGE (priya)-[r2:ADVOCATED_FOR {triple_id: "demo-2"}]->(gcp)
            SET r2.timestamp = datetime("2026-08-11T00:00:00")

            MERGE (rahul)-[r3:ARGUED_AGAINST {triple_id: "demo-3"}]->(gcp)
            SET r3.timestamp = datetime("2026-08-12T00:00:00")
        """)

        print("Basic ChronoGraph created successfully (with timestamps)!")


def load_graph_ready_triples(file_path=None, create_constraints: bool = False):
    """
    Ingests graph-ready triples (from data-ingestion pipeline) into Neo4j,
    creating temporal nodes and relationships with timestamps.
    """
    if file_path is None:
        candidates = [
            Path(__file__).resolve().parent.parent.parent / "data-ingestion" / "data" / "processed" / "graph_ready_triples.json",
            Path("data-ingestion/data/processed/graph_ready_triples.json"),
            Path("../data-ingestion/data/processed/graph_ready_triples.json"),
        ]
        for c in candidates:
            if c.exists():
                file_path = str(c)
                break

    if not file_path or not os.path.exists(file_path):
        print("Graph-ready triples file not found. Falling back to basic demo graph.")
        return create_basic_graph()

    with open(file_path, "r", encoding="utf-8") as f:
        triples = json.load(f)

    print(f"Ingesting {len(triples)} graph-ready triples into Neo4j...")
    with driver.session(database=DATABASE) as session:
        if create_constraints:
            create_schema_indexes_and_constraints(session)
        for idx, t in enumerate(triples):
            sub = t.get("subject_display") or t.get("subject", "Unknown")
            sub_type = (t.get("subject_type") or "Entity").replace(" ", "_")
            obj = t.get("object_display") or t.get("object", "Unknown")
            obj_type = (t.get("object_type") or "Entity").replace(" ", "_")
            rel = t.get("relation", "RELATED_TO").replace(" ", "_").upper()
            ts = t.get("timestamp")
            evidence = t.get("evidence", "")
            source = t.get("source", "")
            confidence = float(t.get("confidence", 1.0))
            triple_id = t.get("triple_id") or f"triple-{idx}"

            # Safely handle missing/invalid timestamps
            valid_ts = is_valid_iso_timestamp(ts)
            ts_cypher_set = "r.timestamp = datetime($ts)" if valid_ts else "r.timestamp_str = $ts"

            # Use triple_id in relationship MERGE to preserve multiple historical events
            # between the same subject and object across different timestamps
            query = f"""
            MERGE (s:{sub_type} {{name: $sub}})
            MERGE (o:{obj_type} {{name: $obj}})
            MERGE (s)-[r:{rel} {{triple_id: $triple_id}}]->(o)
            SET {ts_cypher_set},
                r.raw_timestamp = $ts,
                r.evidence = $evidence,
                r.source = $source,
                r.confidence = $confidence
            """
            session.run(
                query,
                sub=sub,
                obj=obj,
                ts=ts,
                evidence=evidence,
                source=source,
                confidence=confidence,
                triple_id=triple_id,
            )

    print(f"Successfully ingested {len(triples)} temporal triples into Neo4j!")
    return len(triples)



if __name__ == "__main__":
    try:
        load_graph_ready_triples()
    except Exception as exc:
        print(f"Neo4j graph loading skipped: {exc}")
    finally:
        driver.close()


