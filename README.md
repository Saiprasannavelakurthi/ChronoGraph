# ChronoGraph — data-ingestion

This branch contains **Karkuvel's data-ingestion module** for the ChronoGraph project.

## Module Location

All source code, tests, data, and documentation for this module is inside:

```
data-ingestion/
```

## Quick Start

```bash
cd data-ingestion
pip install -r requirements.txt

# Week 1 — Ingest + Extract
python main.py --run-all

# Week 2 — Graph-Ready Data Preparation
python main.py --prepare-graph

# Week 3 — Temporal Retrieval Preparation
python main.py --prepare-retrieval

# Run all tests
python -m pytest tests/ -q
```

See [`data-ingestion/README.md`](data-ingestion/README.md) for full documentation.