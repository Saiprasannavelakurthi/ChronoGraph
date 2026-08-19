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

## 📦 Module Summaries

### 1. Data Ingestion (`data-ingestion/`)
- **Owner**: Karkuvel
- **Branch**: `data-ingestion`
- **Scope**: Multi-source data ingestion loaders (GitHub PRs, Jira tickets, Slack history), text cleaning, normalizer, entity deduplication, and schema validation generating graph-ready data contracts.

### 2. Graph Extraction (`graph-extraction/`)
- **Owner**: Aathi Narayana Moorthi
- **Branch**: `graph-extraction`
- **Scope**: LLM-powered knowledge extraction using Groq LLM API, prompt engineering for temporal triple extraction (subject, relation, object, timestamp), error handling, and pipeline validation.

### 3. Neo4j Temporal (`neo4j-temporal/`)
- **Owner**: Velakurthi Saiprasanna
- **Branch**: `neo4j-temporal`
- **Scope**: Neo4j graph database modeling, temporal relationship ingestion, validation of timestamps, and temporal Cypher query construction.

### 4. RAG UI (`rag-ui/`)
- **Owner**: Vembarasan Nagarajan
- **Branch**: `rag-ui`
- **Scope**: Responsive chat interface built with Vite, React, and Tailwind CSS, interactive message bubbles, typing indicators, mock backend integration, and knowledge graph panel visualization.

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