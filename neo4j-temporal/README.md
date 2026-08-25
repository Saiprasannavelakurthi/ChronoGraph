# ChronoGraph

## Week 1 – Neo4j Setup

### Completed Work

- Set up Neo4j Desktop and created the ChronoGraph database.
- Set up Python virtual environment.
- Installed Neo4j Python Driver and python-dotenv.
- Connected Python with Neo4j successfully.
- Created basic Person and Technology nodes.
- Created relationships between nodes.
- Tested the graph using Cypher queries.

### Technologies

- Python
- Neo4j
- Cypher
- python-dotenv
- Git & GitHub

---

## Week 2 – Temporal Graph

### Completed Work

- Added timestamps to graph relationships.
- Created temporal relationships between people and technologies.
- Created `temporal_queries.py`.
- Retrieved all events from the graph.
- Retrieved events after a specific date.
- Retrieved Rahul's history.
- Tested temporal queries in Neo4j Browser and Python.

### Temporal Events

| Person | Relationship | Technology | Date |
|---|---|---|---|
| Rahul | COMMITTED_CODE | AWS | 2026-08-10 |
| Priya | ADVOCATED_FOR | GCP | 2026-08-11 |
| Rahul | ARGUED_AGAINST | GCP | 2026-08-12 |

### Project Structure

```text
ChronoGraph/
├── backend/
│   ├── neo4j_connection.py
│   ├── create_graph.py
│   └── temporal_queries.py
├── data/
├── .env
├── .gitignore
└── README.md
