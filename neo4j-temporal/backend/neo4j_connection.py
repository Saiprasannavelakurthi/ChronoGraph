import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")
DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


class _SafeNeo4jDriver:
    """Safely handles Neo4j driver initialization without crashing on module import."""

    def __init__(self, uri, username, password):
        self.uri = uri
        self.username = username
        self.password = password
        self._driver = None
        if uri and username and password:
            self._driver = GraphDatabase.driver(uri, auth=(username, password))

    def session(self, *args, **kwargs):
        if not self._driver:
            missing = [
                name for name, val in [("NEO4J_URI", self.uri), ("NEO4J_USERNAME", self.username), ("NEO4J_PASSWORD", self.password)]
                if not val
            ]
            raise ValueError(
                f"Missing required Neo4j environment variable(s): {', '.join(missing)}. "
                "Check your .env file (see .env.example) to run live database operations."
            )
        return self._driver.session(*args, **kwargs)

    def close(self):
        if self._driver:
            self._driver.close()


# Single shared driver instance — safe to import even if .env is unconfigured
driver = _SafeNeo4jDriver(URI, USERNAME, PASSWORD)


def test_connection():
    if not (URI and USERNAME and PASSWORD):
        print("Neo4j connection check: Missing NEO4J_URI, NEO4J_USERNAME, or NEO4J_PASSWORD in .env.")
        print("Live database execution requires configured credentials (see .env.example).")
        return False
    try:
        with driver.session(database=DATABASE) as session:
            result = session.run(
                "RETURN 'ChronoGraph connection successful!' AS message"
            )
            print(result.single()["message"])
            print("Neo4j Browser: http://localhost:7474/browser/")
            return True
    except Exception as exc:
        print(f"Connection failed: {exc}")
        raise


if __name__ == "__main__":
    test_connection()
    driver.close()

