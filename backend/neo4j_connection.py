import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Fail fast with a clear message instead of a cryptic driver error
missing = [
    name for name, value in
    [("NEO4J_URI", URI), ("NEO4J_USERNAME", USERNAME), ("NEO4J_PASSWORD", PASSWORD)]
    if not value
]
if missing:
    raise ValueError(
        f"Missing required environment variable(s): {', '.join(missing)}. "
        "Check your .env file (see .env.example)."
    )

# Single shared driver instance — import this from other modules instead of
# creating a new GraphDatabase.driver() in every file.
driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))


def test_connection():
    try:
        with driver.session(database=DATABASE) as session:
            result = session.run(
                "RETURN 'ChronoGraph connection successful!' AS message"
            )
            print(result.single()["message"])
            print("Neo4j Browser: http://localhost:7474/browser/")
    except Exception as exc:
        print(f"Connection failed: {exc}")
        raise


if __name__ == "__main__":
    test_connection()
    driver.close()
