# ChronoGraph

<<<<<<< Updated upstream
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
=======
## Member
>>>>>>> Stashed changes

**Velakurthi Saiprasanna**

<<<<<<< Updated upstream
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
=======
## Module

**Neo4j Graph Database & Temporal Retrieval**

------------------------------------------------------------------------

# Week 1 -- Neo4j & Temporal Graph Setup

### Completed Work

-   Set up Neo4j Desktop.
-   Created the ChronoGraph database.
-   Set up a Python 3.11 virtual environment.
-   Installed the Neo4j Python Driver and python-dotenv.
-   Configured Neo4j connection using `.env`.
-   Added `.gitignore` to protect environment files.
-   Created Python scripts for Neo4j connection and graph creation.
-   Successfully connected Python with Neo4j.
-   Created Person and Technology nodes.
-   Created relationships between entities.
-   Tested the graph using Cypher queries.

### Technologies

-   Python 3.11
-   Neo4j
-   Cypher
-   Git & GitHub
-   python-dotenv

------------------------------------------------------------------------

# Week 2 -- Temporal Graph Retrieval

### Completed Work

-   Added timestamps to graph relationships.
-   Created temporal events between people and technologies.
-   Implemented temporal queries in `temporal_queries.py`.
-   Retrieved all temporal events.
-   Retrieved events after a specific date.
-   Retrieved the history of a person.
-   Retrieved the history of a technology.
-   Retrieved events between two dates.
-   Added chronological ordering of events.
-   Verified temporal data in Neo4j Browser.
-   Tested the temporal queries successfully.

### Example Temporal Events

-   Rahul committed code to AWS.
-   Priya advocated for GCP.
-   Rahul argued against GCP.

### Technologies

-   Python
-   Neo4j
-   Cypher
-   Neo4j Python Driver

------------------------------------------------------------------------

# Week 3 -- Temporal Query Router

### Completed Work

-   Created `temporal_router.py`.
-   Added support for asking temporal questions in natural language.
-   Added intent detection for temporal queries.
-   Added generation of Cypher queries based on the detected intent.
-   Added support for date-based temporal questions.
-   Added support for events between two dates.
-   Executed the generated Cypher query on Neo4j.
-   Displayed the temporal results.
-   Added temporal query test cases.
-   Added temporal preservation tests.
-   Successfully passed all tests.

### Example Question

``` text
Show events between August 10 2026 and August 11 2026
```

### Generated Cypher

``` cypher
MATCH (a)-[r]->(b)
WHERE r.timestamp IS NOT NULL
AND r.timestamp >= datetime($start_date + 'T00:00:00')
AND r.timestamp <= datetime($end_date + 'T23:59:59')
RETURN a.name AS subject,
       type(r) AS relationship,
       b.name AS object,
       r.timestamp AS timestamp
ORDER BY r.timestamp
```

### Test Result

``` text
16 passed
```

------------------------------------------------------------------------

# Project Structure

``` text
neo4j-temporal/
│
├── backend/
│   ├── neo4j_connection.py
│   ├── create_graph.py
│   ├── temporal_queries.py
│   └── temporal_router.py
│
├── data/
│   └── temporal_queries.json
│
├── tests/
│   ├── test_temporal_preservation.py
│   └── test_temporal_queries.py
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

------------------------------------------------------------------------

# How to Run

### 1. Activate virtual environment

``` powershell
venv\Scripts\activate
```

### 2. Install requirements

``` powershell
pip install -r requirements.txt
```

### 3. Test Neo4j connection

``` powershell
python backend/neo4j_connection.py
```

### 4. Create the graph

``` powershell
python backend/create_graph.py
```

### 5. Run temporal queries

``` powershell
python backend/temporal_queries.py
```

### 6. Run the temporal router

``` powershell
python backend/temporal_router.py
```

### 7. Run tests

``` powershell
pytest -q
```

Expected result:

``` text
16 passed
```

------------------------------------------------------------------------

# Summary

### Week 1

Set up Neo4j and created the basic ChronoGraph.

### Week 2

Added timestamps and implemented temporal graph retrieval.

### Week 3

Added a temporal query router that accepts natural-language questions,
detects the query intent, generates Cypher, executes it on Neo4j, and
returns temporal results.

------------------------------------------------------------------------

# Future Extensions

-   Connect ChronoGraph with the data ingestion module.
-   Connect graph extraction with temporal storage.
-   Improve natural-language query handling.
-   Integrate the complete GraphRAG pipeline.
-   Add a user interface for querying the graph.
>>>>>>> Stashed changes
