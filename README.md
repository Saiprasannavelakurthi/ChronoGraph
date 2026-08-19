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

## 🏛️ Week 2 Integrated Data Flow

```
                     ENTERPRISE DATA (Slack, GitHub, Jira)
                                      │
                                      ▼
                      1. data-ingestion (Karkuvel)
                         → Output: normalized_events.json & graph_ready_triples.json
                                      │
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
            2. graph-extraction (Aathi)    3. neo4j-temporal (Saiprasanna)
               → integration/adapter.py       → Ingestion of graph_ready_triples
                 processes normalized_events    into Neo4j & Temporal Queries
               → Output: extraction_result.json      │
                        │                           │
                        └─────────────┬─────────────┘
                                      ▼
                      4. Integration API (GET /api/graph)
                         → Serves real graph-ready nodes, edges, timeline
                                      │
                                      ▼
                      5. rag-ui (Nagaraj)
                         → Chat Interface + Subgraph Timeline UI
```

---

## 👥 Team Ownership & Review Structure

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
├── rag-ui/               → Vembarasan Nagarajan (Branch: rag-ui)
│   └── Vite + React + Tailwind CSS chat interface and knowledge graph visualization UI
│
└── integration/          → Integration Layer (Adapter, REST API, Outputs)
```

---

## ⚡ Automated Mid-Review Pipeline Verification

To execute and verify the complete integrated pipeline across all four member modules:

```bash
python run_midreview.py
```

*Optional — Run with live Groq LLM extraction (requires `GROQ_API_KEY` in `.env`):*
```bash
python run_midreview.py --live-groq
```

### What this runner verifies:
1. **Stage 1 (`data-ingestion`)**: Executes Karkuvel's graph preparation pipeline to validate, normalize, and deduplicate 142 triples into `graph_ready_triples.json`.
2. **Stage 2 (`graph-extraction`)**: Connects Karkuvel's `normalized_events.json` to Aathi's `process_records()` pipeline via `integration/adapter.py`. The default mid-review run uses **deterministic mock extraction** for reproducibility. Live Groq extraction is optional.
3. **Stage 3 (`neo4j-temporal`)**: Compiles Python bytecode (`py_compile`) and verifies `create_graph.py` graph-ready loader and temporal queries. (If Neo4j credentials are unconfigured, reports clean `BLOCKED BY EXT SERVICE`).
4. **Stage 4 (`integration-api`)**: Validates the Integration API endpoints (`GET /api/health` and `GET /api/graph`) using FastAPI test client.
5. **Stage 5 (`rag-ui`)**: Verifies the production build (`npm run build`) and checks if the local dev server is active.

---

## 🖥️ Live Browser Mid-Review Demonstration Guide

To run the live interactive demonstration with real ChronoGraph graph data:

### Step 1 — Generate Graph-Ready Data
```bash
cd data-ingestion
pytest -q
python main.py --prepare-graph
cd ..
```

### Step 2 — Run Aathi Extraction Adapter
```bash
# Default deterministic mock mode:
python integration/adapter.py

# Or with live Groq API (if configured in .env):
python integration/adapter.py --live-groq
```

### Step 3 — Start Integration API (Terminal 1)
From project root:
```bash
python -m uvicorn integration.api:app --host 127.0.0.1 --port 8000
```
*Verify in browser:* [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### Step 4 — Start RAG UI (Terminal 2)
```bash
cd rag-ui
npm run dev
```
*Open in browser:* [http://localhost:5173](http://localhost:5173)

- The UI fetches `/api/graph` via the Vite dev proxy (`http://127.0.0.1:8000`).
- The right panel renders **real ChronoGraph graph-ready entities and temporal events**.
- If the API server is offline, the UI gracefully falls back to interactive simulated timeline mode.
- *Note:* Chat replies remain simulated (`src/data/mockBot.js`) for Week 2.

### Step 5 — Neo4j Temporal Queries
*(When a local or cloud Neo4j instance is running and configured in `.env`)*:
```bash
cd neo4j-temporal
python backend/create_graph.py
python backend/temporal_queries.py
```
*(If Neo4j is not running, the loader and temporal query suite are verified and marked as BLOCKED BY EXT SERVICE).*

---

## 📊 Mid-Review Status Summary

| Member | Module | Tests | Build / Run | Status | Data Flow |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Karkuvel** | `data-ingestion/` | 230 Passed | Pipeline Ran Successfully | **PASS** | Ingest raw sources → Output `graph_ready_triples.json` |
| **Aathi** | `graph-extraction/` | 28 Passed | Adapter Ran Successfully | **PASS** | `normalized_events.json` → `process_records()` → `graph_extraction_result.json` |
| **Saiprasanna** | `neo4j-temporal/` | Syntax Compiled | Handoff & Queries Verified | **BLOCKED BY EXT SERVICE** | `graph_ready_triples.json` loader ready; live DB requires `.env` credentials |
| **Integration** | `integration/` | Endpoints Verified | REST API Active (:8000) | **PASS** | `graph_ready_triples.json` → `GET /api/graph` |
| **Nagaraj** | `rag-ui/` | Build Verified | Vite Dev Server (:5173) | **PASS** | UI loads real graph data via `/api/graph` with simulated chat fallback |

---

## 🔄 Post-Mid-Review Team Integration Workflow

Following the mid-review, all team members will synchronize their branches with `main` to begin unified development:

```bash
# 1. Update local main
git checkout main
git pull origin main

# 2. Merge main into your feature branch and push
# For Karkuvel:
git checkout data-ingestion && git merge main && git push origin data-ingestion

# For Aathi Narayana Moorthi:
git checkout graph-extraction && git merge main && git push origin graph-extraction

# For Velakurthi Saiprasanna:
git checkout neo4j-temporal && git merge main && git push origin neo4j-temporal

# For Vembarasan Nagarajan:
git checkout rag-ui && git merge main && git push origin rag-ui
```