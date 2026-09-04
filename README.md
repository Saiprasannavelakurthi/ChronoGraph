# ChronoGraph

ChronoGraph is a temporal knowledge-graph powered Retrieval-Augmented Generation (GraphRAG) system designed to ingest, structure, query, and visualize time-evolving knowledge.

---

## 📌 Mid-Review Branch Snapshot

> **Important Notice for Mid-Review Evaluation**
> 
> - **Temporary Review Snapshot**: The four modular folders in this `main` branch represent temporary snapshots of individual team member contributions for the Week 2 mid-review.
> - **Branch Representation**: Each folder maps directly to its corresponding feature branch.
> - **Post-Review Integration**: The ChronoGraph application will be consolidated into a unified codebase structure following the mid-review.
> - **Source Branches Preserved**: The original Git feature branches remain intact and serve as the source of truth for ongoing development.

---

## 🏛️ ChronoGraph End-to-End Pipeline Architecture

```
                    Data Sources (Slack, GitHub, Jira)
                                    │
                                    ▼
                             Data Ingestion
                                    │
                                    ▼
                            Graph Extraction
                                    │
                                    ▼
                         graph_ready_triples.json
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
           Neo4j Temporal Graph             Graph/Timeline API
                     │                             │
                     ▼                             ▼
          Temporal Cypher Queries            React Flow UI
```

---

## 👥 Team Ownership & Module Structure

```
ChronoGraph (main)
│
├── data-ingestion/       → Karkuvel (Branch: data-ingestion)
│   └── Data ingestion pipelines, deduplication, normalizer, and graph-ready data preparation
│
├── graph-extraction/     → Aathi Narayana Moorthi (Branch: graph-extraction)
│   └── LLM graph extraction module using Groq, entity/relation extraction, accuracy audit, and validation
│
├── neo4j-temporal/       → Velakurthi Saiprasanna (Branch: neo4j-temporal)
│   └── Neo4j database integration, temporal graph modeling, timestamps, Cypher audit queries, and edge-case tests
│
├── rag-ui/               → Vembarasan Nagarajan (Branch: rag-ui)
│   └── Vite + React + Tailwind CSS chat interface and knowledge graph timeline visualization UI
│
└── integration/          → Integration Layer (Adapter, REST API, Outputs)
```

---

## ⚡ Automated Mid-Review Pipeline Verification

To execute and verify the complete integrated pipeline across all member modules:

```bash
python run_midreview.py
```

*Optional — Run with live Groq LLM extraction (requires `GROQ_API_KEY` in `.env`):*
```bash
python run_midreview.py --live-groq
```

### What this runner verifies:
1. **Stage 1 (`data-ingestion`)**: Executes Karkuvel's graph preparation pipeline to validate, normalize, and deduplicate 142 triples into `graph_ready_triples.json`.
2. **Stage 2 (`graph-extraction`)**: Connects Karkuvel's `normalized_events.json` to Aathi's `process_records()` pipeline via `integration/adapter.py`.
3. **Stage 2B (`extraction-accuracy`)**: Validates grounding of extracted triples against normalized source events (`normalized_events.json`) and reports grounding accuracy (100.00%).
4. **Stage 3 (`neo4j-temporal`)**: Compiles Python bytecode and executes graph creation and Cypher graph audit routines (`graph_audit.py`). If Neo4j credentials are unconfigured in `.env`, reports clean `BLOCKED BY EXT SERVICE`.
5. **Stage 4 (`integration-api`)**: Validates the Integration API endpoints (`GET /api/health` and `GET /api/graph`) using FastAPI test client.
6. **Stage 5 (`rag-ui`)**: Verifies the production build (`npm run build`) and checks if the local dev server is active.

---

## 🧪 Running Unit & Integration Tests

To run the complete test suite (37/37 tests passing):

```bash
python -m pytest graph-extraction/tests neo4j-temporal/tests
```

### Running Extraction Accuracy Audit:
```bash
python graph-extraction/tests/test_extraction_accuracy.py
```

### Running Neo4j Graph Audit (7 Cypher Queries):
```bash
python neo4j-temporal/backend/graph_audit.py
```

---

## 🖥️ Live Browser Mid-Review Demonstration Guide

To run the live interactive demonstration with real ChronoGraph graph data:

### Step 1 — Generate Graph-Ready Data
```bash
cd data-ingestion
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
npm ci
npm run build
npm run dev
```
*Open in browser:* [http://localhost:5173](http://localhost:5173)

---

## 📊 Mid-Review Status Summary Matrix

| Member | Module | Tests | Build / Run | Status | Data Flow |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Karkuvel** | `data-ingestion/` | 230 Passed | Pipeline Ran Successfully | **PASS** | Ingest raw sources → Output `graph_ready_triples.json` |
| **Aathi** | `graph-extraction/` | 29 Passed | Adapter & Accuracy Audit Ran | **PASS** | `normalized_events.json` → `process_records()` (100% Grounded) |
| **Saiprasanna** | `neo4j-temporal/` | 8 Passed | Handoff, Queries & Audit Verified | **BLOCKED / PASS** | `graph_ready_triples.json` loader ready; live DB requires `.env` |
| **Integration** | `integration/` | Endpoints Verified | REST API Active (:8000) | **PASS** | `graph_ready_triples.json` → `GET /api/graph` |
| **Nagaraj** | `rag-ui/` | Build Verified | Vite Dev Server (:5173) | **PASS** | UI loads real graph data via `/api/graph` with timeline visualization |

---

## 🔄 Post-Mid-Review Team Integration Workflow

Following the mid-review, all team members will synchronize their branches with `main` to begin unified development for Week 3:

```bash
# 1. Update local main
git checkout main
git pull origin main

# 2. Merge main into your feature branch and push
git checkout data-ingestion && git merge main && git push origin data-ingestion
git checkout graph-extraction && git merge main && git push origin graph-extraction
git checkout neo4j-temporal && git merge main && git push origin neo4j-temporal
git checkout rag-ui && git merge main && git push origin rag-ui
```