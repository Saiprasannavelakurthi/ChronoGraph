# ChronoGraph
## Week 1 – Neo4j & Temporal Graph Setup

### Member
**Velakurthi Saiprasanna**

### Module
**Neo4j Graph Database & Temporal Retrieval**

### Completed Work

- Set up Neo4j Desktop and created the **ChronoGraph** local instance.
- Configured and verified the Neo4j `neo4j` database.
- Set up a **Python 3.11 virtual environment** for the project.
- Installed the Neo4j Python driver and `python-dotenv`.
- Configured Neo4j connection details using environment variables in `.env`.
- Added `.gitignore` to protect `.env`, `venv`, and Python cache files.
- Created a Python script to test the connection between the application and Neo4j.
- Successfully established the **Python → Neo4j** connection.
- Created the initial ChronoGraph structure with:
  - Person nodes
  - Technology nodes
  - Relationships between entities
- Tested the basic graph using Cypher queries in Neo4j.

### Technologies Used

- Python 3.11
- Neo4j Desktop
- Neo4j Python Driver
- Cypher
- python-dotenv
- Git & GitHub

### Project Structure

```text
backend/
├── neo4j_connection.py
└── create_graph.py

data/
.env
.gitignore
README.md
