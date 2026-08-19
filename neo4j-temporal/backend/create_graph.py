from neo4j_connection import driver, DATABASE


def create_basic_graph():
    with driver.session(database=DATABASE) as session:

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

        # Create relationships WITH timestamps, matching the README's
        # temporal events table:
        #   Rahul COMMITTED_CODE   AWS  2026-08-10
        #   Priya ADVOCATED_FOR    GCP  2026-08-11
        #   Rahul ARGUED_AGAINST   GCP  2026-08-12
        session.run("""
            MATCH (rahul:Person {name: "Rahul"})
            MATCH (priya:Person {name: "Priya"})
            MATCH (aws:Technology {name: "AWS"})
            MATCH (gcp:Technology {name: "GCP"})

            MERGE (rahul)-[r1:COMMITTED_CODE]->(aws)
            SET r1.timestamp = datetime("2026-08-10T00:00:00")

            MERGE (priya)-[r2:ADVOCATED_FOR]->(gcp)
            SET r2.timestamp = datetime("2026-08-11T00:00:00")

            MERGE (rahul)-[r3:ARGUED_AGAINST]->(gcp)
            SET r3.timestamp = datetime("2026-08-12T00:00:00")
        """)

        print("Basic ChronoGraph created successfully (with timestamps)!")


if __name__ == "__main__":
    create_basic_graph()
    driver.close()
