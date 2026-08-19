# ChronoGraph

ChronoGraph is a temporal knowledge-graph powered Retrieval-Augmented Generation (GraphRAG) system designed to ingest, structure, query, and visualize time-evolving knowledge.

---

## 📌 Mid-Review Branch Snapshot

> **Important Notice for Mid-Review Evaluation**
> 
> - **Temporary Review Snapshot**: The four modular folders in this `main` branch represent temporary snapshots of individual team member contributions for the Week 2 mid-review.
> - **Branch Representation**: Each folder maps directly to its corresponding feature branch.
> - **Post-Review Integration**: The ChronoGraph application will be consolidated into a unified codebase structure following the mid-review.
> - **Source Branches Preserved**: The original Git feature branches remain active, intact, and serve as the source of truth for ongoing development.

---

## 🏛️ Week 2 Mid-Review Architecture

```
                    ChronoGraph
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ↓                ↓                ↓
 data-ingestion   graph-extraction   neo4j-temporal
        │                │                │
        │                │                ↓
        │                │             Neo4j
        │                │
        └────────────────┘

                         +
                         │
                         ↓
                      rag-ui
```

> **Note**: This diagram represents the **Week 2 Mid-Review modular architecture** demonstrating each member's independent module deliverables prior to full system integration.

---

## 👥 Team Branches & Review Structure

```
ChronoGraph (main)
│
├── data-ingestion/       → Karkuvel (Branch: data-ingestion)
│   └── Data ingestion pipelines, deduplication, normalizer, and graph-ready data preparation
│
├── graph-extraction/     → Aathi Narayana Moorthi (Branch: graph-extraction)
│   └── LLM graph extraction module using Groq, entity/relation extraction, and validation
│
├── neo4j-temporal/       → Velakurthi Saiprasanna (Branch: neo4j-temporal)
│   └── Neo4j database integration, temporal graph modeling, timestamps, and Cypher queries
│
└── rag-ui/               → Vembarasan Nagarajan (Branch: rag-ui)
    └── Vite + React + Tailwind CSS chat interface and knowledge graph visualization UI
```

---

## ⚡ One-Command Mid-Review Demonstration

To execute and verify the complete integrated pipeline across all four member modules:

```bash
python run_midreview.py
```

This runner orchestrates:
1. **Stage 1 (`data-ingestion`)**: Executes Karkuvel's graph preparation pipeline to validate, normalize, and deduplicate triples into `graph_ready_triples.json`.
2. **Stage 2 (`graph-extraction`)**: Executes Aathi's multi-record batch extraction and verifies live Groq LLM extraction.
3. **Stage 3 (`neo4j-temporal`)**: Ingests `graph_ready_triples.json` into Neo4j (or reports clean diagnostic status if Neo4j is offline).
4. **Stage 4 (`rag-ui`)**: Verifies Nagaraj's React + Vite Chat UI and subgraph timeline.

---

## 🚀 Individual Module Run Guide

### 1. Karkuvel — Data Ingestion & Graph Preparation
- **Folder**: `data-ingestion/`
- **Commands**:
  ```bash
  cd data-ingestion
  pytest -q
  python main.py --prepare-graph
  python main.py --validate-dag
  ```
- **Output**:
  - `data/processed/graph_ready_triples.json` (142 validated, normalized, deduplicated triples)
  - `data/processed/graph_prep_summary.json` (pipeline execution statistics)
  - 230 passing pytest tests

### 2. Aathi Narayana Moorthi — LLM Graph Extraction
- **Folder**: `graph-extraction/`
- **Commands**:
  ```bash
  cd graph-extraction
  pytest -q
  python data/week2_demo.py
  ```
- **Output**:
  - Batch extraction demo outputting validated Neo4j-ready JSON (`entities`, `relationships`, `triples`, `metadata`, `is_valid: true`)
  - 28 passing pytest tests

### 3. Velakurthi Saiprasanna — Neo4j & Temporal Queries
- **Folder**: `neo4j-temporal/`
- **Commands**:
  ```bash
  cd neo4j-temporal
  # Syntax and import validation:
  python -m py_compile backend/create_graph.py backend/neo4j_connection.py backend/temporal_queries.py
  # Live execution (requires running Neo4j database + .env configuration):
  python backend/create_graph.py
  python backend/temporal_queries.py
  ```
- **Prerequisites**:
  - Requires a running Neo4j instance (Neo4j Desktop or Aura)
  - Configured `.env` with `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
  - Query definitions verified in `data/temporal_queries.json`

### 4. Vembarasan Nagarajan — Chatbot & Graph UI
- **Folder**: `rag-ui/`
- **Commands**:
  ```bash
  cd rag-ui
  npm install
  npm run build
  npm run dev
  ```
- **Output**:
  - Production build compiled successfully (`dist/`)
  - Live interactive UI running on `http://localhost:5173`
  - Current mode: Client-side UI + simulated `mockBot.js` with dynamic subgraph timeline rendering

---

## 📊 Mid-Review Status Summary

| Member | Module | Tests | Build / Run | Status | Data Flow |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Karkuvel** | `data-ingestion/` | 230 Passed | Pipeline Ran Successfully | **PASS** | Ingest raw sources → Output `graph_ready_triples.json` |
| **Aathi** | `graph-extraction/` | 28 Passed | Week 2 Demo Ran Successfully | **PASS** | Process multi-record text → Output validated graph JSON |
| **Saiprasanna** | `neo4j-temporal/` | Syntax Verified | Ready for live connection | **BLOCKED BY EXT SERVICE** | Hardcoded demo graph / queries require live Neo4j credentials |
| **Nagaraj** | `rag-ui/` | Build Verified | Vite Dev Server Live (:5173) | **PASS** | UI → Mock Data (`mockBot.js` + `buildTurnSubgraph`) |

---

## 🔄 Post-Mid-Review Team Integration Workflow

Following the mid-review, all team members will synchronize their branches with `main` to begin unified development:

```
                main (Integrated ChronoGraph Codebase)
                               │
       ┌───────────────────────┼───────────────────────┐
       ↓                       ↓                       ↓
data-ingestion          graph-extraction        neo4j-temporal / rag-ui
```

### Team Synchronization Commands

Each member runs the following from their local repository clone:

```bash
# 1. Update local main
git checkout main
git pull origin main

# 2. Merge main into your feature branch and push
# For Karkuvel:
git checkout data-ingestion
git merge main
git push origin data-ingestion

# For Aathi Narayana Moorthi:
git checkout graph-extraction
git merge main
git push origin graph-extraction

# For Velakurthi Saiprasanna:
git checkout neo4j-temporal
git merge main
git push origin neo4j-temporal

# For Vembarasan Nagarajan:
git checkout rag-ui
git merge main
git push origin rag-ui
```