import os
import webbrowser
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
            # Week 4 — Performance tuning: bound and tune the connection
            # pool instead of using the (unbounded, untuned) defaults.
            # These values matter once multiple modules (this router,
            # Vembarasan's chat UI, concurrent test runs) share the same
            # Aura instance.
            self._driver = GraphDatabase.driver(
                uri,
                auth=(username, password),
                max_connection_pool_size=50,       # cap concurrent connections
                connection_acquisition_timeout=30,  # fail fast instead of hanging
                max_connection_lifetime=3600,       # recycle stale connections hourly
                connection_timeout=15,              # initial TCP/TLS connect timeout
                keep_alive=True,                    # survive idle periods (Aura free/trial tiers)
            )

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

            if "databases.neo4j.io" in (URI or ""):
                # Aura (cloud) instance — there is no local server, so
                # localhost:7474 will never work. Open the Aura Console
                # directly instead of just printing instructions.
                console_url = "https://console.neo4j.io"
                print("Neo4j Aura detected — opening the Aura Console in your browser:")
                print(f"  {console_url}")
                print("  Find your instance in the list and click 'Open' to launch Neo4j Browser.")
                try:
                    webbrowser.open(console_url)
                except Exception:
                    # Headless/server environments won't have a browser to open —
                    # the printed URL above still lets the user open it manually.
                    pass
            else:
                local_browser_url = "http://localhost:7474/browser/"
                print(f"Neo4j Browser: {local_browser_url}")
                try:
                    webbrowser.open(local_browser_url)
                except Exception:
                    pass

            return True
    except Exception as exc:
        print(f"Connection failed: {exc}")
        raise


if __name__ == "__main__":
    test_connection()
    driver.close()