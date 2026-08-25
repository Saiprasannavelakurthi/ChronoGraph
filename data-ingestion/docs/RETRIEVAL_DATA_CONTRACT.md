# Week 3 — Retrieval-Ready Data Contract

**Module Owner**: Karkuvel (data-ingestion branch)  
**Contract Version**: Week 3  
**Produced By**: `src/retrieval/builder.py` → `RetrievalRecordBuilder`  
**Output File**: `data/processed/retrieval_ready_records.json`  
**CLI Command**: `python main.py --prepare-retrieval`

---

## Overview

The retrieval-ready data contract defines the schema for evidence records
prepared by the Week 3 Temporal Retrieval Preparation layer.

These records are derived from the Week 2 `graph_ready_triples.json` output
and are designed to be consumed directly by the downstream **Temporal Routing
/ GraphRAG engine** for chronological retrieval, evidence ranking, and
citation-backed answer generation.

This module does **NOT**:
- Write to Neo4j
- Execute Cypher queries
- Convert natural language to Cypher (that belongs to neo4j-temporal)

This module **DOES**:
- Derive clean, flat, retrieval-ready records from graph-ready triples
- Preserve all provenance (source system, native ID, source URL if available)
- Parse and index the event calendar date for chronological retrieval
- Provide a lightweight filter schema (`RetrievalRequest`) that downstream
  routing can use to slice the evidence pool

---

## Output Format: `retrieval_ready_records.json`

Each entry in the JSON array is a **RetrievalRecord**.

### Required Fields

| Field | Type | Description |
|---|---|---|
| `record_id` | `string (UUID)` | Stable identifier for this retrieval record. Set equal to `triple_id`. |
| `triple_id` | `string (UUID)` | The original triple UUID from `graph_ready_triples.json`. |
| `subject` | `string` | Canonical snake_case subject entity name (e.g. `arun_sharma`). |
| `relation` | `string` | Normalized relation label in UPPER_SNAKE_CASE (e.g. `ADVOCATED_FOR`). |
| `object` | `string` | Canonical snake_case object entity name (e.g. `gcp`). |
| `timestamp` | `string (ISO-8601)` | Full UTC ISO-8601 timestamp from the source event (e.g. `2023-03-15T10:30:00+00:00`). |
| `event_date` | `string (ISO-8601 date)` | Calendar date in UTC extracted from `timestamp` (e.g. `2023-03-15`). Used for chronological indexing and filtering. |
| `source` | `string` | Source system: `"slack"`, `"github"`, or `"jira"`. |
| `source_id` | `string` | Native event ID from the source system (e.g. `slack_001`, `github_pr_007`, `jira_001`). |
| `evidence` | `string` | Verbatim supporting sentence(s) from the original enterprise event. |
| `confidence` | `float [0.0, 1.0]` | Extraction confidence score. |

### Optional Fields

| Field | Type | Description |
|---|---|---|
| `subject_display` | `string \| null` | Human-readable original display name for the subject. `null` if not available. |
| `subject_type` | `string \| null` | Entity type classification (e.g. `Person`, `Technology`, `Service`, `Issue`). `null` if unknown. |
| `object_display` | `string \| null` | Human-readable original display name for the object. `null` if not available. |
| `object_type` | `string \| null` | Entity type classification for the object. `null` if unknown. |
| `source_url` | `string \| null` | URL to the source artifact (e.g. GitHub PR URL, Slack permalink). Extracted from `metadata.html_url`, `metadata.url`, `metadata.source_url`, or `metadata.permalink`. Set to `null` if no URL is present in metadata. **Never fabricated.** |
| `extraction_mode` | `string \| null` | Which extraction backend produced the original triple (`llm_groq`, `fallback`, `mock`, etc.). |
| `metadata` | `object` | Pass-through metadata dictionary from the graph-ready triple. May be empty. |

---

## Example RetrievalRecord

```json
{
  "record_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
  "triple_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
  "subject": "arun_sharma",
  "subject_display": "Arun Sharma",
  "subject_type": "Person",
  "relation": "ADVOCATED_FOR",
  "object": "gcp",
  "object_display": "GCP",
  "object_type": "Technology",
  "timestamp": "2023-03-15T10:30:00+00:00",
  "event_date": "2023-03-15",
  "source": "slack",
  "source_id": "slack_001",
  "source_url": null,
  "evidence": "Arun suggested moving our services to GCP.",
  "confidence": 0.9,
  "extraction_mode": "llm_groq",
  "metadata": {}
}
```

---

## Retrieval Request Schema: `RetrievalRequest`

The `RetrievalRequest` is a lightweight filter schema packaged in
`src/retrieval/models.py`. It is the **input contract** for the downstream
Temporal Routing engine.

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `query_text` | `string \| null` | `null` | Natural-language question or search string (passed through to downstream NL routing — not evaluated here). |
| `entities` | `string[]` | `[]` | Entity names to filter by (canonical snake_case or display name, case-insensitive). |
| `relation_hints` | `string[]` | `[]` | Relation labels to filter by (UPPER_SNAKE_CASE preferred, case-insensitive). |
| `temporal_filter` | `TemporalFilter` | `{}` (no filter) | Chronological filter parameters (see below). |
| `sources` | `string[]` | `[]` | Restrict to these source systems (`"slack"`, `"github"`, `"jira"`). Empty = all sources. |
| `limit` | `integer [1..1000]` | `20` | Maximum number of retrieval records to return. |
| `sort_order` | `"asc" \| "desc"` | `"asc"` | Chronological sort direction. `"asc"` = earliest first. `"desc"` = latest first. |

---

## Temporal Filter Schema: `TemporalFilter`

Controls which records pass the chronological filter. At most one mode is
active per request.

| Field | Type | Mode Activated |
|---|---|---|
| `exact_date` | `date \| null` | `EXACT` — records whose `event_date == exact_date` |
| `start_date` + `end_date` | `date \| null` | `RANGE` — `start_date <= event_date <= end_date` (inclusive) |
| `start_date` only | `date \| null` | `RANGE` — `event_date >= start_date` |
| `end_date` only | `date \| null` | `RANGE` — `event_date <= end_date` |
| `before_date` | `date \| null` | `BEFORE` — `event_date < before_date` (exclusive) |
| `after_date` | `date \| null` | `AFTER` — `event_date > after_date` (exclusive) |

### Validation Rules
- `start_date` must not be after `end_date` when both are set. An error is raised if violated.
- All comparison is against the **UTC calendar date** derived from the triple's ISO-8601 timestamp.

### Mode Priority (evaluated in order)
1. `exact_date` set → `EXACT`
2. `start_date` or `end_date` set → `RANGE`
3. `before_date` set → `BEFORE`
4. `after_date` set → `AFTER`
5. None set → `NONE` (no temporal filtering applied)

---

## Evidence Provenance Behavior

The retrieval module preserves source identifiers from the original data
without fabrication.

| Source | Source ID Format | Source URL Origin |
|---|---|---|
| Slack | `slack_XXX` | `metadata.permalink` or `metadata.url` |
| GitHub | `github_pr_XXX` / `github_issue_XXX` | `metadata.html_url` or `metadata.url` |
| Jira | `jira_XXX` | `metadata.url` or `metadata.source_url` |

If no URL key is found in metadata, `source_url` is set to `null`.

The `source_label` property provides a human-readable citation label:
- `slack_001` → `"Slack message slack_001"`
- `github_pr_007` → `"GitHub PR github_pr_007"`
- `jira_001` → `"Jira ticket jira_001"`

---

## Chronological Sorting Behavior

Records are sorted by `(event_date, timestamp)`:
- `sort_order = "asc"` → earliest timestamp first (default)
- `sort_order = "desc"` → latest timestamp first

Multiple records with the same `event_date` are further ordered by the full
ISO-8601 `timestamp` string.

---

## Filtering Behavior Summary

| Filter | Mechanism | Notes |
|---|---|---|
| Source | Exact match on `source` field | Case-insensitive |
| Entity | Match `subject` or `object` (canonical or display) | Case-insensitive |
| Relation | Match `relation` | Normalized to UPPER_SNAKE_CASE before comparison |
| Temporal | Date comparison on `event_date` | See TemporalFilter modes |
| Limit | Applied after all filters and sort | Max 1000 |

---

## Backward Compatibility

This Week 3 contract extends, but does not replace or break, the Week 2
graph-ready data contract (`docs/GRAPH_DATA_CONTRACT.md`).

| Artifact | Week | Status |
|---|---|---|
| `normalized_events.json` | Week 1 | Unchanged |
| `extracted_triples.json` | Week 1 | Unchanged |
| `graph_ready_triples.json` | Week 2 | Unchanged — the Week 3 builder reads this file |
| `graph_prep_summary.json` | Week 2 | Unchanged |
| `retrieval_ready_records.json` | **Week 3** | New output |

---

## CLI Usage

```bash
# Generate retrieval_ready_records.json from existing graph_ready_triples.json
cd data-ingestion
python main.py --prepare-retrieval

# Run the full Week 3 pipeline from scratch (ingest -> extract -> graph prep -> retrieval prep)
python main.py --run-week3-data
```

---

## Example Input/Output Flow

**Input** (`graph_ready_triples.json`, Week 2 output, sample record):

```json
{
  "triple_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
  "subject": "arun_sharma",
  "subject_display": "Arun Sharma",
  "subject_type": "Person",
  "relation": "ADVOCATED_FOR",
  "object": "gcp",
  "object_display": "GCP",
  "object_type": "Technology",
  "timestamp": "2023-03-15T10:30:00+00:00",
  "source": "slack",
  "source_id": "slack_001",
  "evidence": "Arun suggested moving our services to GCP.",
  "confidence": 0.9,
  "extraction_mode": "llm_groq",
  "metadata": {}
}
```

**Output** (`retrieval_ready_records.json`, Week 3 output):

```json
{
  "record_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
  "triple_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
  "subject": "arun_sharma",
  "subject_display": "Arun Sharma",
  "subject_type": "Person",
  "relation": "ADVOCATED_FOR",
  "object": "gcp",
  "object_display": "GCP",
  "object_type": "Technology",
  "timestamp": "2023-03-15T10:30:00+00:00",
  "event_date": "2023-03-15",
  "source": "slack",
  "source_id": "slack_001",
  "source_url": null,
  "evidence": "Arun suggested moving our services to GCP.",
  "confidence": 0.9,
  "extraction_mode": "llm_groq",
  "metadata": {}
}
```

**Key additions in Week 3 output**:
- `event_date`: `"2023-03-15"` — extracted from `timestamp`, used for chronological indexing
- `record_id`: set equal to `triple_id` for stable identification
- `source_url`: `null` when not available in metadata (never fabricated)
