# ChronoGraph — Week 2 Mid-Review Integration Layer

This directory provides the orchestration runner for the Week 2 Mid-Review demonstration.

## Purpose

The integration layer connects the four member modules into a single verifiable data flow:

```
                    ENTERPRISE DATA
                          │
              ┌───────────┼───────────┐
              ↓           ↓           ↓
            Slack       GitHub       Jira
              └───────────┼───────────┘
                          ↓
                  data-ingestion/
                          ↓
                 normalized events
                          ↓
                 graph extraction
                          ↓
                 graph-ready triples
                          ↓
                 neo4j-temporal/
                          ↓
                  Temporal Graph
                          ↓
                     rag-ui/
                          ↓
                  Graph + Timeline
```

## Module Boundaries

The four member folders remain strictly separate:
- `data-ingestion/` → Karkuvel (Data Ingestion & Graph Preparation)
- `graph-extraction/` → Aathi Narayana Moorthi (LLM Graph Extraction)
- `neo4j-temporal/` → Velakurthi Saiprasanna (Neo4j Temporal Database)
- `rag-ui/` → Vembarasan Nagarajan (Chat + Subgraph Timeline UI)

## Execution

Run the complete mid-review demonstration from the repository root:

```bash
python run_midreview.py
```
