# ChronoGraph — Neo4j Graph Database & Temporal Retrieval

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.20%2B-008CC1.svg)](https://neo4j.com/)
[![Neo4j Aura](https://img.shields.io/badge/Neo4j-Aura-4581C3.svg)](https://neo4j.com/cloud/platform/aura-graph-database/)
[![Tests](https://img.shields.io/badge/tests-21%20passed-brightgreen.svg)](https://docs.pytest.org/)

**ChronoGraph** is a Temporal GraphRAG pipeline engineered for enterprise forensics. This module — **`neo4j-temporal`** — is the graph storage and temporal retrieval layer. It ingests the graph-ready triples produced by the data-ingestion module, stores them in **Neo4j** as a time-aware knowledge graph with `triple_id`-preserved relationships, and exposes a **natural-language query router** that converts plain-English historical questions into parameterized Cypher.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Project Structure](#-project-structure)
- [Current Implementation Status](#-current-implementation-status)
- [Key Features](#-key-features)
- [Architecture & Data Flow](#️-architecture--data-flow)
- [Cross-Module Data Contract](#-cross-module-data-contract)
- [Installation & Setup](#-installation--setup)
- [Configuration](#️-configuration)
- [Usage & CLI Reference](#-usage--cli-reference)
- [Testing](#-testing)
- [Verified Metrics & Summary](#-verified-metrics--summary)

---

## 🔍 Overview

A new engineer joining a project needs to understand *why* a decision was made and *who* was involved — not just read fragmented paragraphs from a vector search. This module answers that by keeping every historical event as a distinct, timestamped relationship in a graph, then letting the router translate a question like *"Show Arun Sharma history"* directly into a Cypher traversal over real data.

```
graph_ready_triples.json  (from data-ingestion, 142 triples)
              │
              ▼
      create_graph.py
   (auto-detects real data, else falls back to demo graph)
              │
              ▼
         Neo4j Aura
  (Person / Technology / Database / Service /
   Project / Issue / Problem / ArchitectureDecision
   nodes, timestamped relationships, triple_id preserved)
              │
              ▼
      temporal_router.py
  Natural-language question
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
detect_intent  extract_entities  extract_dates
   └──────────┬──────────┘
              ▼
        build_query()
     (parameterized Cypher)
              │
              ▼
      execute_temporal_query()
              │
              ▼
      Temporal Results (chronological)
```

---

## 📂 Project Structure

```
neo4j-temporal/
├── .env                          # Local Neo4j Aura credentials (git-ignored)
├── .env.example                  # Template for environment configuration
├── .gitattributes                # Normalizes line endings (LF)
├── .gitignore                    # Ignores venv/, .env, __pycache__/
├── README.md                     # Module documentation
├── requirements.txt              # Python dependencies
│
├── backend/
│   ├── neo4j_connection.py       # Neo4j Aura driver connection
│   ├── create_graph.py           # Loads real triples (or demo fallback) into Neo4j
│   ├── temporal_queries.py       # Canned temporal Cypher queries
│   └── temporal_router.py        # NL question → intent → entity → Cypher → execute
│
├── data/
│   └── temporal_queries.json     # Query intent → Cypher templates
│
└── tests/
    ├── test_temporal_queries.py       # Intent detection, entity/date extraction, query building
    ├── test_temporal_preservation.py  # Verifies all 142 real triples preserved via triple_id
    └── test_real_entity_extraction.py # Verifies detection against real ingestion data (NEW)
```

---

## 📌 Current Implementation Status

### Implemented Modules

#### Week 1: Neo4j Setup & Basic Graph
- **Neo4j Aura Connection**: Configured driver connection via `.env` (`neo4j_connection.py`).
- **Basic Graph Creation**: `Person` / `Technology` nodes with `MERGE`-based relationship creation.
- **Environment Protection**: `.gitignore` excludes `.env` and `venv/` from version control.
- **Cypher Verification**: Manual Cypher queries confirmed in Neo4j Browser / Aura Console.

#### Week 2: Temporal Graph Retrieval
- **Timestamped Relationships**: Every relationship carries a `datetime()` timestamp property.
- **Temporal Query Library** (`temporal_queries.py`): all-events, person-history, technology-history, and date-range retrieval.
- **Chronological Ordering**: All temporal queries `ORDER BY r.timestamp`.

#### Week 3: Temporal Query Router + Real Data Integration
- **Natural-Language Router** (`temporal_router.py`): keyword/regex-based intent detection — `all_events`, `person_history`, `technology_history`, `events_after`, `events_between`.
- **Date Extraction**: Supports `YYYY-MM-DD`, `DD-MM-YYYY`, `DD/MM/YYYY`, and `Month Day, Year` formats.
- **Parameterized Cypher Generation**: `build_query()` maps detected intent + extracted entities/dates to a safe, predefined Cypher template.
- **Real Data Integration (NEW)**: `create_graph.py` auto-detects and ingests the real `graph_ready_triples.json` (142 triples from Slack/GitHub/Jira, produced by the `data-ingestion` module) — preserving every historical event as a distinct relationship keyed by `triple_id`, so duplicate `(subject, relation, object)` combinations across different timestamps are never overwritten.
- **Dynamic Entity Detection (NEW)**: Intent detection and `extract_person` / `extract_technology` now load the real entity list from the ingestion data at import time — covering real people (e.g. `Arun Sharma`) and real entities across 8 types (`Technology`, `Database`, `Service`, `Project`, `ArchitectureDecision`, `Issue`, `Problem`, plus `Person`) — with the original demo names (`Rahul`, `Priya`, `AWS`, `GCP`) retained as a fallback.
- **Display Name Normalization (NEW)**: Raw slug-style Person names from the ingestion data (e.g. `arun_sharma`) are auto-converted to natural display form (`Arun Sharma`); already well-formatted names (`PostgreSQL`, `GCP`) pass through unchanged.

---

## ✨ Key Features

1. **Temporal-First Graph Model**
   - Every relationship is timestamped and individually addressable via `triple_id`, so the same two entities can have many distinct historical events between them without being merged into one.
2. **Real Cross-Module Data Integration**
   - Auto-detects and ingests the actual `data-ingestion` module output — no manual data entry, no synthetic placeholders in the final graph.
3. **Natural-Language Temporal Router**
   - Converts questions like *"Show events between August 10 2026 and August 11 2026"* into safe, parameterized Cypher — never raw string interpolation of user input.
4. **Graceful Fallback**
   - If the ingestion data isn't present (e.g. running this module in isolation), the router and graph builder fall back to a small, self-contained demo dataset rather than failing.
5. **Comprehensive Test Suite**
   - 21 passing pytest tests covering intent detection, entity/date extraction, query building, triple preservation, and real-data entity resolution.

---

## 🏗️ Architecture & Data Flow

### Graph Construction

```
data-ingestion/data/processed/graph_ready_triples.json
        ↓
create_graph.py :: load_graph_ready_triples()
        ↓
  for each of 142 triples:
    MERGE (s:{subject_type} {name: $sub})
    MERGE (o:{object_type} {name: $obj})
    MERGE (s)-[r:{relation} {triple_id: $triple_id}]->(o)
    SET r.timestamp, r.evidence, r.source, r.confidence
        ↓
   Neo4j Aura (142 distinct temporal relationships)
```

**Execution Command:**
```bash
python backend/create_graph.py
```

### Natural-Language Query Routing

```
"Show Arun Sharma history"
        ↓
detect_intent()        → "person_history"
extract_person()       → "Arun Sharma"
        ↓
build_query()           → parameterized Cypher + params
        ↓
execute_temporal_query() → runs against Neo4j Aura
        ↓
Chronological results, printed + returned
```

**Execution Command:**
```bash
python backend/temporal_router.py
```

---

## 🔗 Cross-Module Data Contract

This module's full test suite and real-data graph construction depend on the `data-ingestion` module's output, which lives **outside** this repository as a sibling folder:

```
ChronoGraph-project/
├── data-ingestion/                              (Karkuvel's module)
│   └── data/processed/graph_ready_triples.json  ← required by this module
└── neo4j-temporal/                              ← this repo
```

| Scenario | Test Result |
|---|---|
| `data-ingestion/` present | **21 passed** — full real-data coverage |
| `data-ingestion/` absent | **14 passed**, 2 failed (`test_temporal_preservation.py`), 5 skipped (`test_real_entity_extraction.py`) |

To pull the latest ingestion output from the `data-ingestion` branch:
```bash
git show origin/data-ingestion:data-ingestion/data/processed/graph_ready_triples.json > ../data-ingestion-graph_ready_triples.json
mkdir -p ../data-ingestion/data/processed
mv ../data-ingestion-graph_ready_triples.json ../data-ingestion/data/processed/graph_ready_triples.json
```

---

## 🚀 Installation & Setup

### Prerequisites
- **Python 3.11+**
- **Git**
- A **Neo4j Aura** instance (or local Neo4j Desktop)

### Installation

1. **Navigate to the module directory:**
   ```bash
   cd neo4j-temporal
   ```

2. **Create and activate a virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv venv
     venv\Scripts\Activate.ps1
     ```
   - **Linux/macOS:**
     ```bash
     python -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and fill in your Neo4j Aura credentials:

```bash
cp .env.example .env
```

```ini
NEO4J_URI=neo4j+s://<your-instance-id>.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password_here
NEO4J_DATABASE=neo4j
```

> **Note:** `.env` is git-ignored. Never commit real credentials — rotate the Aura password if it's ever shared outside your team.

---

## 💻 Usage & CLI Reference

```bash
# Test the Neo4j connection
python backend/neo4j_connection.py

# Create the graph — loads real 142 triples if data-ingestion/ is present,
# otherwise falls back to the Week 1 demo graph
python backend/create_graph.py

# Run canned temporal queries (all events, person history, date range, etc.)
python backend/temporal_queries.py

# Run the natural-language temporal router (built-in demo questions)
python backend/temporal_router.py
```

**Ad-hoc real-entity query (Python one-liner):**
```bash
python -c "from backend.temporal_router import execute_temporal_query, driver; execute_temporal_query('Show Arun Sharma history'); driver.close()"
```

---

## 🧪 Testing

Run the entire test suite:
```bash
pytest -q
```

### Verified Test Status
**21 passed** across 3 test modules:
- `tests/test_temporal_queries.py` — intent detection, entity/date extraction, Cypher query building (Week 3)
- `tests/test_temporal_preservation.py` — verifies all 142 real triples generate distinct, `triple_id`-preserved relationships
- `tests/test_real_entity_extraction.py` — verifies detection works against real people and entities from the ingestion data, with graceful skip if that data is unavailable

---

## 📈 Verified Metrics & Summary

### Graph Data (from `data-ingestion/data/processed/graph_ready_triples.json`)
- **Total Triples Ingested:** `142`
- **Date Range:** `2023-03-15` → `2023-05-30`
- **Source Breakdown:** Slack `51` · Jira `51` · GitHub `40`
- **Entity Type Breakdown:** Person `5 unique` · Technology `58` · Database `28` · Service `22` · Project `15` · Problem `12` · Issue `5` · ArchitectureDecision `2`
- **Relationship Breakdown:** `MIGRATED_TO` 61 · `REVIEWED` 26 · `RAISED_CONCERN` 20 · `ARGUED_AGAINST` 11 · `IMPLEMENTED` 10 · `ADVOCATED_FOR` 8 · `ASSIGNED_TO` 3 · `DEPRECATED` 3

### Router Coverage
- **Before real-data integration:** 4 hardcoded names recognized (`Rahul`, `Priya`, `AWS`, `GCP`)
- **After real-data integration:** 2 demo names + all real entities from the ingestion data recognized dynamically, with natural display-name formatting

### Test Suite
- **16 → 21 tests** (added `test_real_entity_extraction.py`)
- **21 / 21 passing** with `data-ingestion/` present

---

## 🔮 Future Extensions

- Connect graph extraction (Aathi's module) directly into temporal storage.
- Extend `build_query()` to handle compound questions (e.g. *"What did Arun Sharma do with PostgreSQL?"*).
- Move from keyword/regex intent detection to LangChain-based NL routing, per the original module spec.
- Integrate the complete GraphRAG pipeline with the chatbot UI (Vembarasan's module).