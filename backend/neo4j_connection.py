import os
import webbrowser
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

driver = GraphDatabase.driver(
    URI,
    auth=(USERNAME, PASSWORD)
)


def test_connection():
    with driver.session(database=DATABASE) as session:
        result = session.run(
            "RETURN 'ChronoGraph connection successful!' AS message"
        )
        print(result.single()["message"])

        browser_url = "http://localhost:7474/browser/"
        print(f"Neo4j Browser: {browser_url}")

        # # Automatically open Neo4j Browser
        # webbrowser.open(browser_url)


if __name__ == "__main__":
    test_connection()
    driver.close()