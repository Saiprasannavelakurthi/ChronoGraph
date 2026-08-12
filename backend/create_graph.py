from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)


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

        # Create relationships
        session.run("""
            MATCH (rahul:Person {name: "Rahul"})
            MATCH (priya:Person {name: "Priya"})
            MATCH (aws:Technology {name: "AWS"})
            MATCH (gcp:Technology {name: "GCP"})

            MERGE (rahul)-[:ADVOCATED_FOR]->(gcp)
            MERGE (priya)-[:ARGUED_AGAINST]->(gcp)
            MERGE (rahul)-[:COMMITTED_CODE]->(aws)
        """)

        print("Basic ChronoGraph created successfully!")


if __name__ == "__main__":
    create_basic_graph()
    driver.close()