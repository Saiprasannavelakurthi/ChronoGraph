"""
backend/optimize_graph.py
──────────────────────────
Week 4 — Graph Optimization

Every query in temporal_queries.py / temporal_router.py runs:
    MATCH (a)-[r]->(b) WHERE a.name = ... / r.timestamp >= ...

with NO node label or relationship type specified. Without indexes,
Neo4j has to scan every node/relationship in the graph for every query.

This script:
  1. Discovers every node label and relationship type actually present
     in the graph (dynamic — works regardless of which entity types the
     ingestion data contains: Person, Technology, Database, Service,
     Project, ArchitectureDecision, Issue, Problem, ...).
  2. Creates a range index on `name` for every label.
  3. Creates a range index on `timestamp` for every relationship type.
  4. Creates a uniqueness constraint on `triple_id` per relationship type
     to guarantee the temporal-preservation guarantee at the DB level,
     not just in application code.
  5. Prints a summary of what was created (or already existed).

Run this once after create_graph.py, and again any time new
entity/relationship types are added to the ingestion data.
"""

from neo4j_connection import driver, DATABASE


def get_existing_labels(session):
    result = session.run("CALL db.labels() YIELD label RETURN label")
    return [record["label"] for record in result]


def get_existing_relationship_types(session):
    result = session.run(
        "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
    )
    return [record["relationshipType"] for record in result]


def create_node_name_indexes(session, labels):
    created = []
    for label in labels:
        index_name = f"idx_{label.lower()}_name"
        query = f"""
        CREATE INDEX {index_name} IF NOT EXISTS
        FOR (n:`{label}`) ON (n.name)
        """
        session.run(query)
        created.append(index_name)
    return created


def create_relationship_timestamp_indexes(session, rel_types):
    created = []
    for rel_type in rel_types:
        index_name = f"idx_{rel_type.lower()}_timestamp"
        query = f"""
        CREATE INDEX {index_name} IF NOT EXISTS
        FOR ()-[r:`{rel_type}`]-() ON (r.timestamp)
        """
        session.run(query)
        created.append(index_name)
    return created


def create_triple_id_constraints(session, rel_types):
    """
    Guarantees at the database level that no two relationships of the
    same type share a triple_id — enforcing the temporal-preservation
    property that test_temporal_preservation.py currently only checks
    at the application/test level.
    """
    created = []
    for rel_type in rel_types:
        constraint_name = f"uniq_{rel_type.lower()}_triple_id"
        query = f"""
        CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
        FOR ()-[r:`{rel_type}`]-() REQUIRE r.triple_id IS UNIQUE
        """
        try:
            session.run(query)
            created.append(constraint_name)
        except Exception as e:
            # Relationship-property uniqueness constraints require
            # Neo4j Enterprise / Aura Professional+. Aura free/trial
            # tiers may reject this — degrade gracefully.
            print(f"  ! Skipped constraint {constraint_name}: {e}")
    return created


def list_current_indexes(session):
    result = session.run("SHOW INDEXES YIELD name, state, type RETURN name, state, type")
    return [record.data() for record in result]


def optimize():
    with driver.session(database=DATABASE) as session:
        labels = get_existing_labels(session)
        rel_types = get_existing_relationship_types(session)

        print(f"Discovered {len(labels)} node labels: {labels}")
        print(f"Discovered {len(rel_types)} relationship types: {rel_types}")
        print()

        name_indexes = create_node_name_indexes(session, labels)
        print(f"Created/verified {len(name_indexes)} node name indexes:")
        for idx in name_indexes:
            print(f"  - {idx}")
        print()

        ts_indexes = create_relationship_timestamp_indexes(session, rel_types)
        print(f"Created/verified {len(ts_indexes)} relationship timestamp indexes:")
        for idx in ts_indexes:
            print(f"  - {idx}")
        print()

        constraints = create_triple_id_constraints(session, rel_types)
        print(f"Created/verified {len(constraints)} triple_id uniqueness constraints:")
        for c in constraints:
            print(f"  - {c}")
        print()

        # Indexes are created asynchronously — wait for them to come online
        # before benchmarking, or the "before" run of benchmark_queries.py
        # will accidentally include an index that's still building.
        session.run("CALL db.awaitIndexes(300)")
        print("All indexes online.")


if __name__ == "__main__":
    optimize()
    driver.close()
