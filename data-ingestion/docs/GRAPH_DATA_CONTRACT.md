# ChronoGraph — Graph Data Contract

**Owner:** Data Ingestion & Graph-Ready Pipeline (Week 2)
**Output File:** `data/processed/graph_ready_triples.json`
**Summary File:** `data/processed/graph_prep_summary.json`
**CLI Command:** `python main.py --prepare-graph`
**Last Updated:** Week 2 / Week 3

---

## 1. Purpose

`graph_ready_triples.json` is the **graph-ready data contract** produced by the Graph Preparation Pipeline.

The pipeline:

1. Reads `extracted_triples.json` (output from LLM/heuristic extraction)
2. Validates every triple against required schema rules
3. Normalises entity names, relation labels, and timestamps
4. Deduplicates identical triples while preserving maximum evidence and confidence
5. Writes `graph_ready_triples.json` and execution summary `graph_prep_summary.json`

Downstream modules consume `graph_ready_triples.json` for Neo4j graph loading and Week 3 temporal retrieval preparation.

---

## 2. Triple Schema

Each record in `graph_ready_triples.json` is a JSON object with the following fields:

| Field             | Type    | Required | Description |
|-------------------|---------|----------|-------------|
| `triple_id`       | string  | ✅       | Stable UUID. Uniquely identifies this triple across pipeline runs. |
| `subject`         | string  | ✅       | **Canonical name** of the subject entity (lowercase snake_case). |
| `subject_display` | string  | ✅       | Human-readable display name of the subject (preserves original case). |
| `subject_type`    | string  | ✅       | Semantic type of the subject (see [Entity Types](#5-entity-types)). |
| `relation`        | string  | ✅       | Directed relationship label in `ALL_CAPS_SNAKE_CASE`. |
| `object`          | string  | ✅       | **Canonical name** of the object entity (lowercase snake_case). |
| `object_display`  | string  | ✅       | Human-readable display name of the object. |
| `object_type`     | string  | ✅       | Semantic type of the object (see [Entity Types](#5-entity-types)). |
| `timestamp`       | string  | ✅       | UTC ISO-8601 datetime (see [Timestamp Format](#6-timestamp-format)). |
| `source`          | string  | ✅       | Data source system: `"slack"` \| `"github"` \| `"jira"`. |
| `source_id`       | string  | ✅       | Native event ID from the source system (e.g. `"slack_001"`). |
| `evidence`        | string  | ✅       | Verbatim sentence(s) from the source that support this triple. |
| `confidence`      | float   | ✅       | Extraction confidence score in `[0.0, 1.0]`. |
| `extraction_mode` | string  | ✅       | LLM backend that produced this triple (see [Extraction Modes](#7-extraction-modes)). |
| `metadata`        | object  | ✅       | Pass-through dict of extra fields from the extractor (may be `{}`). |

---

## 3. Example Record

```json
{
  "triple_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
  "subject": "arun_sharma",
  "subject_display": "arun_sharma",
  "subject_type": "Person",
  "relation": "ADVOCATED_FOR",
  "object": "gcp",
  "object_display": "GCP",
  "object_type": "Technology",
  "timestamp": "2023-03-15T10:30:00+00:00",
  "source": "slack",
  "source_id": "slack_001",
  "evidence": "I strongly believe we should start evaluating a migration to GCP.",
  "confidence": 0.9,
  "extraction_mode": "llm_groq",
  "metadata": {}
}
```

---

## 4. Conceptual Neo4j Mapping

> **Note:** This section is **documentation only**. Karkuvel's module does NOT connect
> to Neo4j or execute Cypher. The actual Cypher code is Saiprasanna's responsibility.

The following describes the **conceptual mapping** from the JSON contract to the Neo4j graph:

### Nodes

Each unique `subject` or `object` (by `canonical_name` + `entity_type`) becomes a Neo4j node:

```
subject  →  (:Person {name: "arun_sharma", display_name: "Arun Sharma"})
object   →  (:Technology {name: "gcp", display_name: "GCP"})
```

Use `MERGE` on `name` to avoid duplicate nodes across triples.

### Relationships

The `relation` field becomes a Neo4j relationship type:

```
(:Person)-[:ADVOCATED_FOR {...properties...}]->(:Technology)
```

Properties to attach to the relationship:

- `timestamp` — the temporal context of the relationship
- `source` — provenance system
- `source_id` — native event ID
- `evidence` — the verbatim supporting text
- `confidence` — extraction confidence score
- `triple_id` — stable unique ID for this relationship instance
- `extraction_mode` — which LLM backend produced this triple

### Full Conceptual Triple

```
(arun_sharma:Person)
    -[:ADVOCATED_FOR {
        timestamp: "2023-03-15T10:30:00+00:00",
        source: "slack",
        source_id: "slack_001",
        evidence: "...",
        confidence: 0.9,
        triple_id: "779f3f63-..."
    }]->
(gcp:Technology)
```

### Summary of Mapping

| JSON Field       | Neo4j Location |
|------------------|----------------|
| `subject`        | Source node `name` property |
| `subject_display`| Source node `display_name` property |
| `subject_type`   | Source node label |
| `relation`       | Relationship type |
| `object`         | Target node `name` property |
| `object_display` | Target node `display_name` property |
| `object_type`    | Target node label |
| `timestamp`      | Relationship property (temporal) |
| `source`         | Relationship property (provenance) |
| `source_id`      | Relationship property (provenance) |
| `evidence`       | Relationship property (provenance) |
| `confidence`     | Relationship property (quality) |
| `triple_id`      | Relationship property (unique key) |
| `extraction_mode`| Relationship property (metadata) |

---

## 5. Entity Types

Valid values for `subject_type` and `object_type`:

| Value                | Description |
|----------------------|-------------|
| `Person`             | Individual contributor, engineer, or stakeholder |
| `Technology`         | Cloud service, framework, programming language, tool |
| `Project`            | Engineering project, product, or initiative |
| `Service`            | Microservice, API service, or deployed workload |
| `Database`           | Database system or storage backend |
| `Organization`       | Company, department, or business unit |
| `Team`               | Engineering team or squad |
| `Architecture`       | Architectural pattern, system design, or decision |
| `ArchitectureDecision` | A specific ADR (Architecture Decision Record) |
| `Issue`              | Bug, ticket, or tracked problem |
| `Problem`            | System failure, incident, or identified issue |
| `Other`              | Uncategorized entities |
| `Unknown`            | Entity type could not be determined |

---

## 6. Relationship Types

Known relationship labels produced by the extraction pipeline:

| Label              | Meaning |
|--------------------|---------|
| `ADVOCATED_FOR`    | Entity proposed or supported an idea, technology, or approach |
| `ARGUED_AGAINST`   | Entity objected to or raised concerns about something |
| `COMMITTED_CODE`   | Person committed code to a repository |
| `REVIEWED`         | Person reviewed code, PR, or document |
| `ASSIGNED_TO`      | Task or issue was assigned to a person |
| `MIGRATED_TO`      | Entity or service was migrated to a new platform or technology |
| `RAISED_CONCERN`   | Entity raised a concern or risk |
| `DECIDED`          | Entity made a decision |
| `IMPLEMENTED`      | Entity implemented a feature, service, or change |
| `REPORTED_BUG`     | Person reported a bug or defect |
| `FIXED`            | Bug, issue, or defect was fixed |
| `APPROVED`         | Decision, PR, or change was approved |
| `BLOCKED_BY`       | Something is blocked by a dependency or issue |
| `RELATED_TO`       | Generic relationship between entities |
| `DEPRECATED`       | Technology, API, or pattern was deprecated |
| `ENROLLED_IN`      | Person enrolled in a training or program |
| `UNKNOWN`          | Relationship type could not be determined |

> **Note:** Custom relation types may appear in the data. Saiprasanna's module should
> handle them gracefully (e.g., create the relationship with whatever label is in the
> `relation` field). All labels are guaranteed to be in `ALL_CAPS_SNAKE_CASE` format.

---

## 7. Timestamp Format

All timestamps in `graph_ready_triples.json` are normalized to **UTC ISO-8601**:

```
YYYY-MM-DDTHH:MM:SS+00:00
```

Example: `"2023-03-15T10:30:00+00:00"`

- All timestamps are timezone-aware.
- All offsets are `+00:00` (UTC).
- Timestamps are parseable by Python's `datetime.fromisoformat()` and standard
  Neo4j datetime parsing.

---

## 8. Source & Provenance Fields

The `source` and `source_id` fields allow Saiprasanna to trace every graph
relationship back to its original enterprise event:

| Source   | `source_id` Pattern | Data file |
|----------|---------------------|-----------|
| `slack`  | `slack_001`, `slack_002`, … | `data/raw/slack_history.json` |
| `github` | `github_pr_001`, `github_commit_001`, … | `data/raw/github_prs.json` |
| `jira`   | `jira_001`, `jira_002`, … | `data/raw/jira_tickets.json` |

---

## 9. Confidence & Quality

The `confidence` field is a float in `[0.0, 1.0]`:

- Values produced by **Groq LLM** (`llm_groq`) are typically `0.85–0.95`.
- Values produced by the **fallback heuristic** (`fallback`) are typically `0.5–0.7`.
- Saiprasanna's module may filter low-confidence relationships if needed
  (e.g., `confidence < 0.6`), but this is a design decision for the Neo4j module.

---

## 10. Extraction Modes

| Value          | Description |
|----------------|-------------|
| `llm_groq`     | Extracted by Groq Cloud API (LLaMA-3.1) |
| `llm_ollama`   | Extracted by Ollama local inference (LLaMA-3) |
| `llm_openai`   | Extracted by OpenAI GPT |
| `fallback`     | Extracted by the deterministic heuristic fallback |
| `mock`         | Synthetic/mock data for testing |

---

## 11. Deduplication Guarantee

`graph_ready_triples.json` is guaranteed to contain **no exact duplicates**.

A duplicate is defined as two triples sharing the same composite key:

```
(subject, relation, object, timestamp, source, source_id)
```

When duplicates are detected, the record with the **higher confidence score** is kept.
If confidence is equal, the first-encountered record wins.

---

## 12. How to Consume This File

Saiprasanna's Neo4j module should:

1. **Read** `data/processed/graph_ready_triples.json` as a JSON array.
2. **Iterate** each record.
3. For each record:
   - Use `MERGE` on `subject` (canonical name + type) to create/reuse the subject node.
   - Use `MERGE` on `object` (canonical name + type) to create/reuse the object node.
   - Use `MERGE` or `CREATE` on the `relation` relationship, keyed on `triple_id`.
   - Attach all provenance fields (`timestamp`, `source`, `source_id`, `evidence`, `confidence`, `triple_id`) as relationship properties.
4. After loading, `graph_prep_summary.json` provides verification statistics.

---

## 13. Summary File (`graph_prep_summary.json`)

The companion summary file provides statistics for Saiprasanna to verify data quality:

```json
{
  "generated_at": "2023-03-15T10:30:00+00:00",
  "pipeline_stage": "Week 2 – Graph Preparation (Karkuvel)",
  "statistics": {
    "total_input_triples": 142,
    "valid_triples": 140,
    "invalid_triples": 2,
    "validation_errors": 2,
    "triples_after_deduplication": 138,
    "duplicates_removed": 2,
    "graph_ready_triples": 138
  },
  "entities": {
    "people": 8,
    "technologies": 12,
    "projects": 3,
    "services": 5,
    "issues": 4
  },
  "relations": {
    "unique_relation_types": 12,
    "relation_counts": {
      "ADVOCATED_FOR": 25,
      "ARGUED_AGAINST": 18,
      ...
    }
  },
  "sources": {
    "slack": 80,
    "github": 35,
    "jira": 23
  },
  "date_range": {
    "earliest": "2023-01-01T00:00:00+00:00",
    "latest": "2023-06-30T23:59:59+00:00"
  }
| JSON Field       | Neo4j Location |
|------------------|----------------|
| `subject`        | Source node `name` property |
| `subject_display`| Source node `display_name` property |
| `subject_type`   | Source node label |
| `relation`       | Relationship type |
| `object`         | Target node `name` property |
| `object_display` | Target node `display_name` property |
| `object_type`    | Target node label |
| `timestamp`      | Relationship property (temporal) |
| `source`         | Relationship property (provenance) |
| `source_id`      | Relationship property (provenance) |
| `evidence`       | Relationship property (provenance) |
| `confidence`     | Relationship property (quality) |
| `triple_id`      | Relationship property (unique key) |
| `extraction_mode`| Relationship property (metadata) |

---

## 5. Entity Types

Valid values for `subject_type` and `object_type`:

| Value                | Description |
|----------------------|-------------|
| `Person`             | Individual contributor, engineer, or stakeholder |
| `Technology`         | Cloud service, framework, programming language, tool |
| `Project`            | Engineering project, product, or initiative |
| `Service`            | Microservice, API service, or deployed workload |
| `Database`           | Database system or storage backend |
| `Organization`       | Company, department, or business unit |
| `Team`               | Engineering team or squad |
| `Architecture`       | Architectural pattern, system design, or decision |
| `ArchitectureDecision` | A specific ADR (Architecture Decision Record) |
| `Issue`              | Bug, ticket, or tracked problem |
| `Problem`            | System failure, incident, or identified issue |
| `Other`              | Uncategorized entities |
| `Unknown`            | Entity type could not be determined |

---

## 6. Relationship Types

Known relationship labels produced by the extraction pipeline:

| Label              | Meaning |
|--------------------|---------|
| `ADVOCATED_FOR`    | Entity proposed or supported an idea, technology, or approach |
| `ARGUED_AGAINST`   | Entity objected to or raised concerns about something |
| `COMMITTED_CODE`   | Person committed code to a repository |
| `REVIEWED`         | Person reviewed code, PR, or document |
| `ASSIGNED_TO`      | Task or issue was assigned to a person |
| `MIGRATED_TO`      | Entity or service was migrated to a new platform or technology |
| `RAISED_CONCERN`   | Entity raised a concern or risk |
| `DECIDED`          | Entity made a decision |
| `IMPLEMENTED`      | Entity implemented a feature, service, or change |
| `REPORTED_BUG`     | Person reported a bug or defect |
| `FIXED`            | Bug, issue, or defect was fixed |
| `APPROVED`         | Decision, PR, or change was approved |
| `BLOCKED_BY`       | Something is blocked by a dependency or issue |
| `RELATED_TO`       | Generic relationship between entities |
| `DEPRECATED`       | Technology, API, or pattern was deprecated |
| `ENROLLED_IN`      | Person enrolled in a training or program |
| `UNKNOWN`          | Relationship type could not be determined |

> **Note:** Custom relation types may appear in the data. Saiprasanna's module should
> handle them gracefully (e.g., create the relationship with whatever label is in the
> `relation` field). All labels are guaranteed to be in `ALL_CAPS_SNAKE_CASE` format.

---

## 7. Timestamp Format

All timestamps in `graph_ready_triples.json` are normalized to **UTC ISO-8601**:

```
YYYY-MM-DDTHH:MM:SS+00:00
```

Example: `"2023-03-15T10:30:00+00:00"`

- All timestamps are timezone-aware.
- All offsets are `+00:00` (UTC).
- Timestamps are parseable by Python's `datetime.fromisoformat()` and standard
  Neo4j datetime parsing.

---

## 8. Source & Provenance Fields

The `source` and `source_id` fields allow Saiprasanna to trace every graph
relationship back to its original enterprise event:

| Source   | `source_id` Pattern | Data file |
|----------|---------------------|-----------|
| `slack`  | `slack_001`, `slack_002`, … | `data/raw/slack_history.json` |
| `github` | `github_pr_001`, `github_commit_001`, … | `data/raw/github_prs.json` |
| `jira`   | `jira_001`, `jira_002`, … | `data/raw/jira_tickets.json` |

---

## 9. Confidence & Quality

The `confidence` field is a float in `[0.0, 1.0]`:

- Values produced by **Groq LLM** (`llm_groq`) are typically `0.85–0.95`.
- Values produced by the **fallback heuristic** (`fallback`) are typically `0.5–0.7`.
- Saiprasanna's module may filter low-confidence relationships if needed
  (e.g., `confidence < 0.6`), but this is a design decision for the Neo4j module.

---

## 10. Extraction Modes

| Value          | Description |
|----------------|-------------|
| `llm_groq`     | Extracted by Groq Cloud API (LLaMA-3.1) |
| `llm_ollama`   | Extracted by Ollama local inference (LLaMA-3) |
| `llm_openai`   | Extracted by OpenAI GPT |
| `fallback`     | Extracted by the deterministic heuristic fallback |
| `mock`         | Synthetic/mock data for testing |

---

## 11. Deduplication Guarantee

`graph_ready_triples.json` is guaranteed to contain **no exact duplicates**.

A duplicate is defined as two triples sharing the same composite key:

```
(subject, relation, object, timestamp, source, source_id)
```

When duplicates are detected, the record with the **higher confidence score** is kept.
If confidence is equal, the first-encountered record wins.

---

## 12. How to Consume This File

Saiprasanna's Neo4j module should:

1. **Read** `data/processed/graph_ready_triples.json` as a JSON array.
2. **Iterate** each record.
3. For each record:
   - Use `MERGE` on `subject` (canonical name + type) to create/reuse the subject node.
   - Use `MERGE` on `object` (canonical name + type) to create/reuse the object node.
   - Use `MERGE` or `CREATE` on the `relation` relationship, keyed on `triple_id`.
   - Attach all provenance fields (`timestamp`, `source`, `source_id`, `evidence`, `confidence`, `triple_id`) as relationship properties.
4. After loading, `graph_prep_summary.json` provides verification statistics.

---

## 13. Summary File (`graph_prep_summary.json`)

The companion summary file provides statistics for Saiprasanna to verify data quality:

```json
{
  "generated_at": "2023-03-15T10:30:00+00:00",
  "pipeline_stage": "Week 2 – Graph Preparation (Karkuvel)",
  "statistics": {
    "total_input_triples": 142,
    "valid_triples": 140,
    "invalid_triples": 2,
    "validation_errors": 2,
    "triples_after_deduplication": 138,
    "duplicates_removed": 2,
    "graph_ready_triples": 138
  },
  "entities": {
    "people": 8,
    "technologies": 12,
    "projects": 3,
    "services": 5,
    "issues": 4
  },
  "relations": {
    "unique_relation_types": 12,
    "relation_counts": {
      "ADVOCATED_FOR": 25,
      "ARGUED_AGAINST": 18,
      ...
    }
  },
  "sources": {
    "slack": 80,
    "github": 35,
    "jira": 23
  },
  "date_range": {
    "earliest": "2023-01-01T00:00:00+00:00",
    "latest": "2023-06-30T23:59:59+00:00"
  }
}
```

---

## 14. Scope Boundaries

This contract file and the `graph_ready_triples.json` output specify the graph-ready data format. This module does **NOT**:

- ❌ Connect directly to Neo4j instances in production
- ❌ Execute Cypher queries against live databases
- ❌ Provide UI or visualization frontend code

Those operations belong to downstream database and user interface layers.

---

## 15. Re-running Graph Preparation

To regenerate `graph_ready_triples.json`:

```bash
# Prerequisite: Ingest and extract data
python main.py --run-all

# Run Week 2 graph preparation
python main.py --prepare-graph
```

Or run the full pipeline in one command:

```bash
python main.py --run-week2-data
```

---

*Document prepared for ChronoGraph — Week 2 Data Integration & Graph-Ready Pipeline.*
