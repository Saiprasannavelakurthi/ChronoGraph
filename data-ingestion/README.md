# ChronoGraph — Data Ingestion & Temporal Retrieval Preparation

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![LlamaIndex](https://img.shields.io/badge/LlamaIndex-0.10%2B-purple.svg)](https://www.llamaindex.ai/)
[![Groq LLM](https://img.shields.io/badge/Groq-llama--3.1--8b--instant-orange.svg)](https://groq.com/)
[![Tests](https://img.shields.io/badge/tests-520%20passed-brightgreen.svg)](https://docs.pytest.org/)

**ChronoGraph** is a Temporal GraphRAG pipeline engineered for enterprise forensics, knowledge graph extraction, and cross-platform communication analytics. It ingests unstructured developer communications (Slack messages, GitHub PRs/issues, Jira tickets), extracts temporal entity-relationship triples using LlamaIndex & Groq LLMs (with robust heuristic fallbacks), validates and normalizes entities/relations, deduplicates records, prepares citation-ready chronological retrieval evidence records, and exposes a high-performance REST Retrieval Query API for downstream Temporal Routing and GraphRAG answer generation.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Project Structure](#-project-structure)
- [Current Implementation Status](#-current-implementation-status)
- [Key Features](#-key-features)
- [Architecture & Data Pipelines](#-architecture--data-pipelines)
- [Data Contracts](#-data-contracts)
- [Installation & Setup](#-installation--setup)
- [Configuration](#-configuration)
- [Usage & CLI Reference](#-usage--cli-reference)
- [FastAPI REST Service & Week 4 Retrieval API](#-fastapi-rest-service--week-4-retrieval-api)
- [Airflow Orchestration](#-airflow-orchestration)
- [Testing](#-testing)
- [Pipeline Metrics & Summary](#-pipeline-metrics--summary)

---

## 🔍 Overview

Modern engineering organizations produce massive volumes of decision history across disparate channels: Slack discussions, Jira tickets, and GitHub pull requests. **ChronoGraph** solves the forensic challenge of tracking *who* advocated for *what*, *when*, and *why* across time.

```
[ Slack ]       [ GitHub ]       [ Jira ]
     │               │               │
     └───────────────┼───────────────┘
                     ↓
              Data Ingestion
                     ↓
               Preprocessing
                     ↓
                  Airflow
                     ↓
             LlamaIndex + Groq
                     ↓
            Temporal Triples
                     ↓
         extracted_triples.json
                     ↓
          GraphPrepPipeline (Week 2)
                     ↓
         Validation + Normalization
                     ↓
              Deduplication
                     ↓
         graph_ready_triples.json
                     ↓
       RetrievalRecordBuilder (Week 3)
                     ↓
       retrieval_ready_records.json
                     ↓
       RetrievalService & API (Week 4)
                     ↓
         TemporalFilterEngine
                     ↓
      POST /api/retrieval/query
```

---

## 📂 Project Structure

This repository branch contains the standalone `data-ingestion` module:

```
data-ingestion/
├── .env                              # Local environment configuration (git-ignored)
├── .env.example                      # Template for environment configuration
├── .gitignore                        # Module git-ignore definitions
├── README.md                         # Module documentation
├── requirements.txt                  # Python dependencies
├── main.py                           # Unified CLI entrypoint
├── config/
│   ├── __init__.py
│   └── settings.py                   # Pydantic env settings (paths, LLM keys, thresholds)
├── dags/
│   ├── __init__.py
│   └── chronograph_ingestion_dag.py  # Apache Airflow DAG definition
├── data/
│   ├── raw/                          # Raw mock datasets (slack, github, jira)
│   │   ├── github_prs.json
│   │   ├── jira_tickets.json
│   │   └── slack_history.json
│   └── processed/
│       ├── normalized_events.json    # Output of Ingestion Pipeline
│       ├── extracted_triples.json    # Output of Extraction Pipeline
│       ├── graph_ready_triples.json  # Output of Graph Preparation Pipeline
│       ├── graph_prep_summary.json   # Week 2 pipeline execution summary
│       ├── retrieval_ready_records.json # Output of Retrieval Preparation Pipeline
│       ├── retrieval_prep_summary.json  # Week 3 pipeline execution metadata
│       └── retrieval_quality_stats.json # Week 3 data quality & coverage statistics
├── docs/
│   ├── GRAPH_DATA_CONTRACT.md        # Graph-ready data schema specification
│   ├── RETRIEVAL_DATA_CONTRACT.md    # Retrieval-ready data schema specification
│   └── RETRIEVAL_API_CONTRACT.md     # Week 4 Retrieval API OpenAPI / REST specification
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   └── app.py                    # FastAPI endpoints (ingestion, graph, Week 4 retrieval API)
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── extractor.py              # LlamaIndex + Groq extractor with fallback logic
│   │   ├── fallback.py               # Heuristic rule-based regex triple extractor
│   │   └── prompts.py                # Extraction system prompts & schemas
│   ├── graph_prep/
│   │   ├── __init__.py
│   │   ├── deduplicator.py           # Triple entity resolution & deduplication
│   │   ├── normalizer.py             # Canonical name, entity type, & relation normalizer
│   │   ├── pipeline.py               # End-to-end Graph Preparation Pipeline
│   │   └── validator.py              # Schema & data contract validator
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base.py                   # Abstract base loader class
│   │   ├── github_loader.py          # GitHub PRs and issues ingestor
│   │   ├── jira_loader.py            # Jira tickets ingestor
│   │   ├── slack_loader.py           # Slack messages ingestor
│   │   └── pipeline.py               # Multi-source ingestion orchestrator
│   ├── retrieval/
│   │   ├── __init__.py               # Public exports (models, builder, filter engine, validator, stats, service, errors)
│   │   ├── builder.py                # Builds RetrievalRecord list + writes execution metadata
│   │   ├── errors.py                 # Retrieval domain exception hierarchy (RetrievalDataNotFoundError, RetrievalDataFormatError, etc.)
│   │   ├── filter.py                 # In-memory chronological, entity, & free-text ranking filter engine
│   │   ├── models.py                 # RetrievalRecord, TemporalFilter, RetrievalRequest, RetrievalQueryRequest, RetrievalQueryResponse, RetrievalHealthResponse
│   │   ├── service.py                # Week 4 RetrievalService orchestrating safe loading, caching, filtering & API querying
│   │   ├── stats.py                  # Data quality and coverage statistics engine (RetrievalStatsEngine)
│   │   └── validator.py              # Post-build consistency validator (RetrievalOutputValidator)
│   └── schemas/
│       ├── __init__.py
│       └── graph.py                  # Pydantic schemas (RawEvent, Triple, ExtractedGraph)
└── tests/
    ├── __init__.py
    ├── test_extraction.py            # Extraction & fallback unit tests (Week 1)
    ├── test_graph_prep.py            # Validation, normalization & deduplication tests (Week 2)
    ├── test_ingestion.py             # Loader & ingestion pipeline tests (Week 1)
    ├── test_retrieval.py             # Retrieval preparation, builder, and filter tests (Week 3)
    └── test_retrieval_api.py         # RetrievalService & FastAPI query endpoints tests (Week 4)
```
│   └── RETRIEVAL_DATA_CONTRACT.md    # Retrieval-ready data schema specification
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   └── app.py                    # FastAPI endpoints & CORS configuration
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── extractor.py              # LlamaIndex + Groq extractor with fallback logic
│   │   ├── fallback.py               # Heuristic rule-based regex triple extractor
│   │   └── prompts.py                # Extraction system prompts & schemas
│   ├── graph_prep/
│   │   ├── __init__.py
│   │   ├── deduplicator.py           # Triple entity resolution & deduplication
│   │   ├── normalizer.py             # Canonical name, entity type, & relation normalizer
│   │   ├── pipeline.py               # End-to-end Graph Preparation Pipeline
│   │   └── validator.py              # Schema & data contract validator
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base.py                   # Abstract base loader class
│   │   ├── github_loader.py          # GitHub PRs and issues ingestor
│   │   ├── jira_loader.py            # Jira tickets ingestor
│   │   ├── slack_loader.py           # Slack messages ingestor
│   │   └── pipeline.py               # Multi-source ingestion orchestrator
│   ├── retrieval/
│   │   ├── __init__.py               # Public exports (models, builder, filter engine, validator, stats)
│   │   ├── builder.py                # Builds RetrievalRecord list + writes execution metadata
│   │   ├── filter.py                 # In-memory chronological & entity filter engine
│   │   ├── models.py                 # RetrievalRecord, TemporalFilter, RetrievalRequest, PipelineExecutionMetadata, RetrievalDataQualityStats
│   │   ├── stats.py                  # Data quality and coverage statistics engine (RetrievalStatsEngine)
│   │   └── validator.py              # Post-build consistency validator (RetrievalOutputValidator)
│   └── schemas/
│       ├── __init__.py
│       └── graph.py                  # Pydantic schemas (RawEvent, Triple, ExtractedGraph)
└── tests/
    ├── __init__.py
    ├── test_extraction.py            # Extraction & fallback unit tests
    ├── test_graph_prep.py            # Validation, normalization & deduplication tests
    ├── test_ingestion.py             # Loader & ingestion pipeline tests
    └── test_retrieval.py             # Retrieval preparation, builder, and filter tests
```

---

## 📌 Current Implementation Status

### Implemented Modules

#### Week 1: Multi-Source Ingestion & Extraction
- **Multi-Source Ingestion**: Data loaders for Slack messages, GitHub PRs/issues, and Jira tickets.
- **Data Preprocessing**: ISO-8601 UTC timestamp normalization and text cleaning.
- **Airflow Orchestration**: Automated DAG scheduling (`chronograph_ingestion_dag.py`).
- **LlamaIndex Extraction**: Core integration with Groq LLM (`llama-3.1-8b-instant`).
- **Groq LLM Extraction**: Structured extraction of temporal entity-relation-entity triples.
- **Triple Extraction**: Extraction of subject, relation, object, timestamp, source, and evidence.
- **Fallback Extraction**: Rule-based regex heuristic engine (`extraction_mode = "fallback"`) ensuring robust execution without external API dependencies.

#### Week 2: Graph-Ready Data Preparation
- **Triple Validation**: Schema validation, required field enforcement, timestamp ISO-8601 validation, and score bounding.
- **Entity Normalization**: Standardizing entity names into canonical `snake_case` while preserving original display names and entity types.
- **Relation Normalization**: Mapping relationship labels to canonical uppercase categories (e.g. `ADVOCATED_FOR`, `MIGRATED_TO`, `REVIEWED`).
- **Timestamp Normalization**: Ensuring strict UTC ISO-8601 format across all triples.
- **Deduplication**: Resolving duplicate triples across sources while preserving max evidence context and confidence.
- **Graph-Ready Data Generation**: Outputting `data/processed/graph_ready_triples.json`.
- **Graph Preparation Summary**: Generating `data/processed/graph_prep_summary.json` containing pipeline statistics.
- **Data Contract**: Establishing the formal contract for graph integration ([`docs/GRAPH_DATA_CONTRACT.md`](docs/GRAPH_DATA_CONTRACT.md)).

#### Week 3: Temporal Retrieval Preparation
- **RetrievalRecord Model**: Citation-ready evidence unit retaining complete provenance (`source`, `source_id`, `source_url`, `evidence`, `timestamp`, `event_date`, `confidence`).
- **TemporalFilter Model**: Chronological filter specification supporting `exact`, `range`, `before`, and `after` modes with automatic mode detection.
- **RetrievalRequest Schema**: Lightweight filter schema packaging natural-language queries, entity hints, relation hints, temporal bounds, source filters, limit, and sort direction.
- **RetrievalRecordBuilder**: Transforms `graph_ready_triples.json` into `retrieval_ready_records.json`, parsing calendar dates and extracting source URLs from metadata without data fabrication.
- **PipelineExecutionMetadata**: After each run, writes `retrieval_prep_summary.json` capturing `pipeline_name`, `input_source`, `total_records`, `records_built`, `skipped_records`, `generated_at` (UTC), and `status`.
- **TemporalFilterEngine**: In-memory Python engine applying chronological sorting (ASC/DESC), date range filtering, before/after filtering, exact date filtering, entity matching, and relation filtering.
- **RetrievalOutputValidator**: Post-build consistency validator verifying identifiers, provenance, temporal metadata validity, and accounting identities.
- **RetrievalStatsEngine**: Computes data quality and coverage statistics (`unique_entities`, `unique_relations`, `source_breakdown`, `average_confidence`) into `retrieval_quality_stats.json`.
- **Data Contract**: Formal specification for temporal retrieval records and execution metadata ([`docs/RETRIEVAL_DATA_CONTRACT.md`](docs/RETRIEVAL_DATA_CONTRACT.md)).

#### Week 4: Temporal Retrieval Query API & Error Resilience
- **RetrievalService Layer**: Service layer in `src/retrieval/service.py` that loads, validates, and caches `retrieval_ready_records.json`, normalizes queries, executes multi-dimensional filtering and relevance scoring via `TemporalFilterEngine`, computes total matches before limits, and formats structured responses.
- **Resilient Error Handling (Day 4)**:
  - Custom domain exceptions (`RetrievalDataNotFoundError`, `RetrievalDataFormatError`, `RetrievalServiceError`) mapped to safe HTTP 404/500 responses without exposing local filesystem paths, database credentials, or stack traces.
  - Resilient cache management ensuring that previously valid cached records are preserved and remain queryable even if a reload attempt fails.
  - Partial file corruption tolerance skipping malformed individual records with warning logs.
- **FastAPI Endpoints**:
  - `GET /api/health` — Health check reporting service status, data availability on disk, and total record count.
  - `POST /api/retrieval/query` — Flexible temporal retrieval endpoint accepting natural language queries, entity hints, relation labels, source filters, date ranges/bounds, sorting, and pagination with full provenance.
  - `GET /api/retrieval/stats` — Retrieval quality and coverage statistics.
- **CLI Integration**: FastAPI server startup via `python main.py --start-api` or `python main.py --serve-api`.
- **API Contract**: Full REST / OpenAPI specification in [`docs/RETRIEVAL_API_CONTRACT.md`](docs/RETRIEVAL_API_CONTRACT.md).

---

## ✨ Key Features

1. **Multi-Source Data Ingestion**
   - Native loaders for **Slack**, **GitHub**, and **Jira** communication logs.
   - Text cleaning, entity sanitization, and standardized ISO-8601 UTC timestamp conversion.
2. **LLM-Powered Temporal Extraction**
   - Powered by **LlamaIndex** with **Groq** (`llama-3.1-8b-instant`), **OpenAI**, or **Ollama** support.
   - Robust **Heuristic Fallback Engine** (`extraction_mode = "fallback"`) ensuring zero pipeline failures even when offline or unauthenticated.
3. **Graph Preparation & Integration (Week 2)**
   - **Validation**: Enforces mandatory fields, valid ISO timestamps, UUID stability, and confidence score bounds.
   - **Normalization**: Standardizes entity names to canonical `snake_case` while retaining original display names. Normalizes relations into canonical types.
   - **Deduplication**: Resolves duplicate triples across multiple sources and retains maximum evidence and confidence score.
   - **Graph-Ready Output**: Produces `data/processed/graph_ready_triples.json`.
4. **Temporal Retrieval Preparation (Week 3)**
   - **Provenance-Preserving Records**: Generates `RetrievalRecord` units preserving exact source IDs and URLs for verifiable UI citations.
   - **Chronological Indexing**: Extracts UTC calendar `event_date` for high-performance temporal filtering.
   - **Flexible In-Memory Filtering**: Supports exact date, inclusive range, exclusive before/after, entity matching, relation filtering, and ASC/DESC chronological sorting.
   - **Retrieval-Ready Output**: Produces `data/processed/retrieval_ready_records.json`.
   - **Pipeline Execution Metadata**: Emits `data/processed/retrieval_prep_summary.json` containing execution metrics.
5. **Temporal Retrieval Query API (Week 4)**
   - **REST Query Interface**: Structured querying over REST (`POST /api/retrieval/query`).
   - **Multi-Filter Support**: Combined entity, relation, source system, and chronological boundary filters.
   - **FastAPI Validation**: Strict request schema validation with Pydantic.
   - **Zero Knowledge Loss**: Preserves complete evidence strings, timestamps, and source URLs in every query response.
6. **Production-Ready Operations**
   - **FastAPI** application for HTTP-triggered ingestion, extraction, and temporal retrieval queries.
   - **Apache Airflow DAG** (`chronograph_ingestion_dag.py`) for enterprise pipeline scheduling.
   - **Comprehensive Test Suite**: 457 passing pytest unit and integration tests.

---

## 🏗️ Architecture & Data Pipelines

### Week 2 Pipeline: Graph Preparation
```
normalized_events.json
        ↓
extraction / triple processing
        ↓
extracted_triples.json
        ↓
GraphPrepPipeline
        ↓
validation (src/graph_prep/validator.py)
normalization (src/graph_prep/normalizer.py)
deduplication (src/graph_prep/deduplicator.py)
        ↓
graph_ready_triples.json
```

**Execution Command**:
```bash
python main.py --prepare-graph
```

**Verified Output**:
- `142` graph-ready triples
- `142` valid triples (`0` invalid)
- `0` duplicates removed

### Week 3 Pipeline: Temporal Retrieval Preparation
```
graph_ready_triples.json
        ↓
RetrievalRecordBuilder (src/retrieval/builder.py)
        ├──→ retrieval_ready_records.json   (data contract)
        └──→ retrieval_prep_summary.json    (execution metadata)
        ↓
TemporalFilterEngine (src/retrieval/filter.py)
```

**Execution Command**:
```bash
python main.py --prepare-retrieval
```

**Verified Output**:
- `142` retrieval-ready records
- `0` skipped records
- `status: success`

### Week 4 Pipeline: Temporal Retrieval API Layer
```
HTTP Request
    ↓
POST /api/retrieval/query  /  GET /api/health  /  GET /api/retrieval/stats
    ↓
RetrievalQueryRequest Schema Validation
    ↓
RetrievalService (src/retrieval/service.py)
    ↓
Load & Cache retrieval_ready_records.json
    ↓
TemporalFilterEngine (src/retrieval/filter.py)
(Source → Entity → Relation → Temporal Boundaries → Sorting)
    ↓
Total Matches Calculation & Pagination Limit
    ↓
Structured RetrievalQueryResponse
```

---

## 📑 Data Contracts

- **Graph Data Contract**: [`docs/GRAPH_DATA_CONTRACT.md`](docs/GRAPH_DATA_CONTRACT.md) defines the schema for `graph_ready_triples.json`.
- **Retrieval Data Contract**: [`docs/RETRIEVAL_DATA_CONTRACT.md`](docs/RETRIEVAL_DATA_CONTRACT.md) defines the schema for `retrieval_ready_records.json`, `RetrievalRequest`, and `retrieval_prep_summary.json`.
- **Retrieval API Contract**: [`docs/RETRIEVAL_API_CONTRACT.md`](docs/RETRIEVAL_API_CONTRACT.md) defines the REST endpoints, schemas, and error contracts for Week 4.

---

## 🚀 Installation & Setup

### Prerequisites

- **Python 3.10+** (Tested on Python 3.10 - 3.13)
- **Git**

### Installation

1. **Navigate to the module directory:**
   ```bash
   cd data-ingestion
   ```

2. **Create and activate a virtual environment:**
   - **Linux/macOS:**
     ```bash
     python -m venv venv
     source venv/bin/activate
     ```
   - **Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and adjust variables as required:

```bash
cp .env.example .env
```

### Key Environment Variables (`.env`)

```ini
# LLM Provider Configuration
# Supported options: groq, ollama, openai, mock
LLM_PROVIDER=groq

# Groq API Configuration
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant

# OpenAI / Ollama (Optional)
OPENAI_API_KEY=your_openai_key_here
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# Extraction Thresholds
EXTRACTION_MIN_CONFIDENCE=0.5
```

> **Note:** If `LLM_PROVIDER=mock` or no API key is supplied, ChronoGraph seamlessly uses its **Heuristic Fallback Engine** (`fallback`) to extract triples without failing.

---

## 💻 Usage & CLI Reference

The unified CLI entrypoint `main.py` provides commands for executing pipeline stages individually or end-to-end:

### Pipeline Execution Commands

```bash
# Week 1 — Run Data Ingestion (Slack + GitHub + Jira -> normalized_events.json)
python main.py --ingest

# Week 1 — Run Triple Extraction (normalized_events.json -> extracted_triples.json)
python main.py --extract

# Week 1 — Run Full Week 1 Pipeline (Ingest + Extract)
python main.py --run-all

# Week 2 — Run Graph Preparation (validate + normalize + deduplicate -> graph_ready_triples.json)
python main.py --prepare-graph

# Week 2 — Run Full Week 2 Pipeline (Ingest + Extract + Graph Preparation)
python main.py --run-week2-data

# Week 3: Build retrieval-ready records from graph_ready_triples.json
python main.py --prepare-retrieval

# Week 3: Compute data quality statistics from retrieval_ready_records.json
python main.py --retrieval-stats

# Week 3: Full pipeline — ingest -> extract -> graph prep -> retrieval prep
python main.py --run-week3-data
```

### Inspection & API Server Commands

```bash
# Print extracted triples JSON to stdout
python main.py --export-json

# Validate Airflow DAG import syntax
python main.py --validate-dag

# Start FastAPI server on :8000 (Week 4 Retrieval API)
python main.py --start-api
# or alias:
python main.py --serve-api
```

---

## 🌐 FastAPI REST Service & Week 4 Retrieval API

Start the interactive API server using CLI or `uvicorn`:

```bash
python main.py --start-api
# or:
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Once running, access the interactive OpenAPI / Swagger UI at:
- **Swagger Documentation:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`

### Week 4 Primary API Endpoints

#### 1. Health & Data Availability (`GET /api/health`)

```bash
curl -X GET http://localhost:8000/api/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "ChronoGraph Retrieval API",
  "version": "1.0.0",
  "retrieval_data_available": true,
  "retrieval_records_count": 142,
  "timestamp": "2026-08-28T13:45:00.000000+00:00"
}
```

#### 2. Temporal Retrieval Query (`POST /api/retrieval/query`)

Executes multi-criteria temporal retrieval. When a `query` (or `query_text`) is provided, performs deterministic, explainable case-insensitive free-text search across subject, object, display names, relation, evidence, source, and source ID. Matches are scored with lightweight relevance weights (Entity: 3.0, Relation: 2.0, Evidence: 1.0, Source: 1.0) without requiring an LLM or external search database.

```bash
curl -X POST http://localhost:8000/api/retrieval/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What happened with AWS after April 2023?",
    "entity_hints": ["AWS"],
    "after_date": "2023-04-01",
    "sort_order": "asc",
    "page": 1,
    "page_size": 5
  }'
```

**Response:**
```json
{
  "query": "What happened with AWS after April 2023?",
  "total_matches": 18,
  "returned_count": 5,
  "page": 1,
  "page_size": 5,
  "total_pages": 4,
  "has_next": true,
  "has_previous": false,
  "results": [
    {
      "record_id": "96c09dfd-b4b6-455b-9d41-3b7c9366df04",
      "triple_id": "96c09dfd-b4b6-455b-9d41-3b7c9366df04",
      "subject": "arun_sharma",
      "subject_display": "Arun Sharma",
      "subject_type": "Person",
      "relation": "ADVOCATED_FOR",
      "object": "aws",
      "object_display": "AWS",
      "object_type": "Technology",
      "timestamp": "2023-04-05T11:20:00+00:00",
      "event_date": "2023-04-05",
      "source": "slack",
      "source_id": "slack_012",
      "source_url": null,
      "evidence": "Arun noted AWS managed services could reduce ops overhead.",
      "confidence": 0.9,
      "extraction_mode": "llm_groq",
      "metadata": {}
    }
  ],
  "applied_filters": {
    "query_text": "What happened with AWS after April 2023?",
    "entities": ["AWS"],
    "relation_hints": [],
    "sources": [],
    "temporal_mode": "after",
    "temporal_filter": {
      "mode": "after",
      "exact_date": null,
      "start_date": null,
      "end_date": null,
      "before_date": null,
      "after_date": "2023-04-01"
    },
    "sort_order": "asc",
    "limit": 5,
    "page": 1,
    "page_size": 5
  },
  "generated_at": "2026-08-28T13:45:00.000000+00:00"
}
```

#### 3. Retrieval Data Quality Statistics (`GET /api/retrieval/stats`)

```bash
curl -X GET http://localhost:8000/api/retrieval/stats
```

---

## ⏱️ Airflow Orchestration

ChronoGraph includes a production-grade Apache Airflow DAG located in [`dags/chronograph_ingestion_dag.py`](dags/chronograph_ingestion_dag.py).

To validate the DAG syntax locally:
```bash
python main.py --validate-dag
```

---

## 🧪 Testing

The codebase maintains complete test coverage across all modules using `pytest`.

Run the entire test suite:
```bash
python -m pytest tests/ -q
```

### Verified Test Status
- **520 passed** tests across 5 test modules:
  - `tests/test_ingestion.py` — Ingestion loaders, preprocessing, and normalization (Week 1)
  - `tests/test_extraction.py` — LlamaIndex/Groq extraction and heuristic fallbacks (Week 1)
  - `tests/test_graph_prep.py` — Graph preparation validation, normalization, and deduplication (Week 2)
  - `tests/test_retrieval.py` — RetrievalRecordBuilder, TemporalFilterEngine, models, RetrievalOutputValidator, RetrievalStatsEngine, and RetrievalDataQualityStats (Week 3)
  - `tests/test_retrieval_api.py` — RetrievalService unit tests, FastAPI query endpoints, pagination, free-text ranking, and error resilience (Week 4)

---

## 📈 Pipeline Metrics & Summary

### Week 2: Graph Preparation Metrics (`data/processed/graph_prep_summary.json`)
- **Total Input Triples:** `142`
- **Valid Triples Output:** `142`
- **Invalid Triples:** `0`
- **Duplicates Removed:** `0`
- **Graph-Ready Triples:** `142`
- **Source Breakdown:**
  - **Slack:** `51` triples
  - **Jira:** `51` triples
  - **GitHub:** `40` triples
- **Top Extracted Relationships:**
  - `MIGRATED_TO`: 61
  - `REVIEWED`: 26
  - `RAISED_CONCERN`: 20
  - `ARGUED_AGAINST`: 11
  - `IMPLEMENTED`: 10
  - `ADVOCATED_FOR`: 8
  - `ASSIGNED_TO`: 3
  - `DEPRECATED`: 3

### Week 3: Retrieval Preparation Metrics (`data/processed/retrieval_ready_records.json`)
- **Total Graph-Ready Input:** `142`
- **Retrieval Records Built:** `142`
- **Records Skipped:** `0`
- **Source Breakdown:**
  - **Slack:** `51` records
  - **Jira:** `51` records
  - **GitHub:** `40` records
- **Date Range:** `2023-03-15` → `2023-05-30`

### Week 4: Temporal Retrieval API Metrics
- **Retrieval Ready Pool:** `142` validated records
- **Supported Filter Modes:** Exact Date, Date Range (inclusive), Before Date (exclusive), After Date (exclusive), Entity Matching, Relation Filtering, Source Filtering
- **Provenance Coverage:** 100% of records retain source system, native ID, verbatim evidence, and UTC event timestamp

