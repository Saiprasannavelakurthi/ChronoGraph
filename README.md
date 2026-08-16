# ChronoGraph

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![LlamaIndex](https://img.shields.io/badge/LlamaIndex-0.10%2B-purple.svg)](https://www.llamaindex.ai/)
[![Groq LLM](https://img.shields.io/badge/Groq-LLM_Inference-orange.svg)](https://groq.com/)
[![Tests](https://img.shields.io/badge/tests-230%20passed-brightgreen.svg)](https://docs.pytest.org/)

**ChronoGraph** is a Temporal GraphRAG pipeline engineered for enterprise forensics, knowledge graph extraction, and cross-platform communication analytics. It ingests unstructured developer communications (Slack messages, GitHub PRs/issues, Jira tickets), extracts temporal entity-relationship triples using LlamaIndex & Groq LLMs (with robust heuristic fallbacks), validates and normalizes entities/relations, deduplicates records, and produces a graph-ready data contract for downstream Neo4j temporal graph construction.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture & Directory Structure](#-architecture--directory-structure)
- [Data Pipeline & Data Contract](#-data-pipeline--data-contract)
- [Installation & Setup](#-installation--setup)
- [Configuration](#-configuration)
- [Usage & CLI Reference](#-usage--cli-reference)
- [FastAPI REST Service](#-fastapi-rest-service)
- [Airflow Orchestration](#-airflow-orchestration)
- [Testing](#-testing)
- [Pipeline Metrics & Summary](#-pipeline-metrics--summary)

---

## 🔍 Overview

Modern engineering organizations produce massive volumes of decision history across disparate channels: Slack discussions, Jira tickets, and GitHub pull requests. **ChronoGraph** solves the forensic challenge of tracking *who* advocated for *what*, *when*, and *why* across time.

```
       [ Slack ]       [ GitHub ]       [ Jira ]
           │                │               │
           ▼                ▼               ▼
   ┌─────────────────────────────────────────────────┐
   │            Multi-Source Ingestion Pipeline       │
   │  - Timestamp ISO-8601 Normalization            │
   │  - Text Cleaning & Metadata Standardisation    │
   └────────────────────────┬────────────────────────┘
                            │
                            ▼
               data/processed/normalized_events.json
                            │
                            ▼
   ┌─────────────────────────────────────────────────┐
   │          Temporal Triple Extraction             │
   │  - LlamaIndex + Groq LLM (llama-3.3-70b)       │
   │  - Rule-Based / Heuristic Fallback Engine      │
   └────────────────────────┬────────────────────────┘
                            │
                            ▼
               data/processed/extracted_triples.json
                            │
                            ▼
   ┌─────────────────────────────────────────────────┐
   │            Graph-Ready Preparation              │
   │  - Schema & Type Validation                     │
   │  - Canonical Name & Label Normalization         │
   │  - Entity Resolution & Deduplication            │
   └────────────────────────┬────────────────────────┘
                            │
                            ▼
               data/processed/graph_ready_triples.json
                                 +
               data/processed/graph_prep_summary.json
                            │
                            ▼
                      [ Neo4j Graph ]
```

---

## ✨ Key Features

1. **Multi-Source Data Ingestion**
   - Native loaders for **Slack**, **GitHub**, and **Jira** communication logs.
   - Text cleaning, entity sanitization, and standardized ISO-8601 UTC timestamp conversion.
2. **LLM-Powered Temporal Extraction**
   - Powered by **LlamaIndex** with **Groq** (`llama-3.3-70b-versatile`), **OpenAI**, or **Ollama** support.
   - Robust **Heuristic Fallback Engine** ensuring zero pipeline failures even when offline or unauthenticated.
3. **Graph Preparation & Data Integration**
   - **Validation**: Enforces mandatory fields, valid ISO timestamps, UUID stability, and confidence score bounds.
   - **Normalization**: Standardizes entity names to canonical `snake_case` while retaining original display names. Normalizes relations into 8 canonical types.
   - **Deduplication**: Resolves duplicate triples across multiple sources and retains maximum evidence and confidence score.
4. **Production-Ready Operations**
   - **FastAPI** application for HTTP-triggered ingestion, extraction, and triple retrieval.
   - **Apache Airflow DAG** (`chronograph_ingestion_dag.py`) for enterprise pipeline scheduling and DAG validation.
   - **Comprehensive Test Suite**: 230 passing pytest unit and integration tests.

---

## 📂 Architecture & Directory Structure

```
ChronoGraph/
├── config/
│   └── settings.py               # Pydantic env settings (paths, LLM keys, thresholds)
├── dags/
│   └── chronograph_ingestion_dag.py # Apache Airflow DAG definition
├── data/
│   ├── raw/                      # Raw mock datasets (slack, github, jira)
│   └── processed/
│       ├── normalized_events.json  # Output of Ingestion Pipeline
│       ├── extracted_triples.json   # Output of Extraction Pipeline
│       ├── graph_ready_triples.json # Final Graph-Ready Data Contract
│       └── graph_prep_summary.json  # Pipeline execution statistics
├── docs/
│   └── GRAPH_DATA_CONTRACT.md    # Neo4j integration schema specification
├── src/
│   ├── api/
│   │   └── app.py                # FastAPI endpoints & CORS configuration
│   ├── extraction/
│   │   ├── extractor.py          # LlamaIndex + Groq extractor with fallback logic
│   │   ├── fallback.py           # Heuristic rule-based regex triple extractor
│   │   └── prompts.py            # Extraction system prompts & schemas
│   ├── graph_prep/
│   │   ├── deduplicator.py       # Triple entity resolution & deduplication
│   │   ├── normalizer.py         # Canonical name, entity type, & relation normalizer
│   │   ├── pipeline.py           # End-to-end Graph Preparation Pipeline
│   │   └── validator.py          # Schema & data contract validator
│   ├── ingestion/
│   │   ├── base.py               # Abstract base loader class
│   │   ├── github_loader.py      # GitHub PRs and issues ingestor
│   │   ├── jira_loader.py        # Jira tickets ingestor
│   │   ├── slack_loader.py       # Slack messages ingestor
│   │   └── pipeline.py           # Multi-source ingestion orchestrator
│   └── schemas/
│       └── graph.py              # Pydantic schemas (RawEvent, Triple, ExtractedGraph)
├── tests/
│   ├── test_extraction.py        # Extraction & fallback unit tests
│   ├── test_graph_prep.py        # Validation, normalization & deduplication tests
│   └── test_ingestion.py         # Loader & ingestion pipeline tests
├── .env.example                  # Template for environment configuration
├── main.py                       # Unified CLI entrypoint
├── requirements.txt              # Dependency manifests
└── README.md                     # Project documentation
```

---

## 📊 Data Pipeline & Data Contract

Each triple in `graph_ready_triples.json` strictly adheres to the integration contract (`docs/GRAPH_DATA_CONTRACT.md`):

| Field | Type | Required | Description |
|---|---|---|---|
| `triple_id` | string | ✅ | Stable UUID uniquely identifying the triple |
| `subject` | string | ✅ | Canonical snake_case name of the subject entity |
| `subject_display` | string | ✅ | Human-readable original display name |
| `subject_type` | string | ✅ | Entity classification (`Person`, `Technology`, `Service`, `Project`, etc.) |
| `relation` | string | ✅ | Normalized relation (`MIGRATED_TO`, `REVIEWED`, `RAISED_CONCERN`, `ARGUED_AGAINST`, `IMPLEMENTED`, `ADVOCATED_FOR`, `ASSIGNED_TO`, `DEPRECATED`) |
| `object` | string | ✅ | Canonical snake_case name of the object entity |
| `object_display` | string | ✅ | Human-readable original display name |
| `object_type` | string | ✅ | Entity classification for the object |
| `timestamp` | string | ✅ | ISO-8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SS+00:00`) |
| `source` | string | ✅ | Source system (`slack`, `github`, `jira`) |
| `source_id` | string | ✅ | Native event ID from source system |
| `evidence` | string | ✅ | Supporting sentence or context from raw text |
| `confidence` | float | ✅ | Extraction confidence score in `[0.0, 1.0]` |
| `extraction_mode` | string | ✅ | Backend mode used (`llm_groq`, `llm_openai`, `heuristic_fallback`) |
| `metadata` | object | ✅ | Auxiliary metadata key-value dictionary |

---

## 🚀 Installation & Setup

### Prerequisites

- **Python 3.10+** (Tested on Python 3.10 - 3.13)
- **Git**

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Saiprasannavelakurthi/ChronoGraph.git
   cd ChronoGraph
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

Copy `.env.example` to `.env` and adjust the variables as required:

```bash
cp .env.example .env
```

### Key Environment Variables (`.env`)

```ini
# LLM Provider Configuration
# Supported options: mock, groq, openai, ollama
LLM_PROVIDER=groq

# Groq API Configuration
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# OpenAI / Ollama (Optional)
OPENAI_API_KEY=your_openai_key_here
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b

# Extraction Thresholds
EXTRACTION_MIN_CONFIDENCE=0.5
```

> **Note:** If `LLM_PROVIDER=mock` or no API key is supplied, ChronoGraph seamlessly uses its **Heuristic Fallback Engine** to extract triples without failing.

---

## 💻 Usage & CLI Reference

The unified CLI entrypoint `main.py` provides commands for executing pipeline stages individually or end-to-end:

### Pipeline Execution Commands

```bash
# 1. Run Data Ingestion (Slack + GitHub + Jira -> normalized_events.json)
python main.py --ingest

# 2. Run Triple Extraction (normalized_events.json -> extracted_triples.json)
python main.py --extract

# 3. Run Graph Preparation (validate + normalize + deduplicate -> graph_ready_triples.json)
python main.py --prepare-graph

# 4. Run Full Week 1 Pipeline (Ingest + Extract)
python main.py --run-all

# 5. Run Full End-to-End Pipeline (Ingest + Extract + Graph Preparation)
python main.py --run-week2-data
```

### Inspection & Utility Commands

```bash
# Print extracted triples JSON to stdout
python main.py --export-json

# Validate Airflow DAG import syntax
python main.py --validate-dag
```

---

## 🌐 FastAPI REST Service

Start the interactive API server using CLI or `uvicorn`:

```bash
python main.py --start-api
# or directly:
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Once running, access the interactive OpenAPI / Swagger UI at:
- **Swagger Documentation:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`

### API Endpoints

- `GET  /api/v1/health` — Liveness probe & system config details
- `POST /api/v1/ingest` — Trigger multi-source data ingestion pipeline
- `POST /api/v1/extract` — Trigger temporal triple extraction pipeline
- `GET  /api/v1/triples` — Query extracted triples with `source`, `relation`, and `limit` filters

---

## ⏱️ Airflow Orchestration

ChronoGraph includes a production-grade Apache Airflow DAG located in [`dags/chronograph_ingestion_dag.py`](file:///d:/ChronoGraph/dags/chronograph_ingestion_dag.py).

To validate the DAG syntax locally:
```bash
python main.py --validate-dag
```

---

## 🧪 Testing

The codebase maintains full test coverage across all modules using `pytest`.

Run the entire test suite:
```bash
pytest
```

Run specific test modules with detailed output:
```bash
pytest tests/test_ingestion.py -v
pytest tests/test_extraction.py -v
pytest tests/test_graph_prep.py -v
```

---

## 📈 Pipeline Metrics & Summary

Current pipeline run metrics recorded in `data/processed/graph_prep_summary.json`:

- **Total Input Triples Processed:** `142`
- **Valid Triples Output:** `142` (`0` validation errors)
- **Graph-Ready Triples:** `142`
- **Source Breakdown:**
  - **Slack:** `51` triples
  - **Jira:** `51` triples
  - **GitHub:** `40` triples
- **Top Relationships Extracted:**
  - `MIGRATED_TO`: 61
  - `REVIEWED`: 26
  - `RAISED_CONCERN`: 20
  - `ARGUED_AGAINST`: 11
  - `IMPLEMENTED`: 10
  - `ADVOCATED_FOR`: 8
  - `ASSIGNED_TO`: 3
  - `DEPRECATED`: 3

---

