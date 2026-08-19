# ChronoGraph — LLM Graph Extraction Module

**Module Owner:** Aathi Narayana Moorthi  
**Module:** LLM Graph Extraction

---

## Overview

The **LLM Graph Extraction** module converts cleaned enterprise data (Slack communications, GitHub commits/PRs/issues, Jira tasks/projects) into a normalized, validated, and synchronized graph representation (entities, relationships, subject-predicate-object triples, and source metadata).

> **Module Scope Boundary:**  
> This module prepares validated graph data for the Neo4j module. Neo4j storage, Cypher queries, temporal retrieval, GraphRAG, and UI components are implemented by downstream modules and are outside the scope of Aathi's module.

---

## Features

### Week 1 Baseline Features
* LlamaIndex + Groq (Llama 3.3 70B) integration
* Structured entity, relationship, and graph triple extraction
* Pydantic schemas and strict graph validation
* Entity name normalization and deduplication
* Relationship/triple synchronization
* Unknown relationship mapping to `OTHER`
* Preserved backward-compatible single text interface (`process_text()`)

### Week 2 Enhanced Features
* **Source-Aware Extraction:** Tailored prompt context for Slack, GitHub, and Jira inputs.
* **Batch Processing:** Multi-record processing interface (`process_records()`).
* **Stable Entity IDs:** Deterministic slug ID generation (`person_karkuvel`, `repository_chronograph`, `issue_cg_102`, `commit_abc1234`, `pull_request_24`).
* **Cross-Record Deduplication:** Consolidates identical entities appearing across multiple Slack, GitHub, and Jira records into single canonical entities.
* **Exact Identifier Preservation:** Preserves hashes (`abc1234`), issue keys (`CG-102`), PR numbers (`#24`), and handles (`@karkuvel`).
* **Multiple Predicate Preservation:** Retains distinct relationships between identical entity pairs (e.g. `Aathi --REVIEWED--> #24` and `Aathi --MERGED--> #24`).
* **Metadata Preservation:** Retains all input record metadata under `metadata.records`.
* **Explicit Error Handling:** Clear separation between valid empty extractions, invalid LLM outputs, and API/network failures (`GraphExtractionError` in `src/errors.py`).

---

## Usage

### Single Text Processing (`process_text`)

```python
from src.pipeline import process_text

text = "Karkuvel committed changes abc1234 to the ChronoGraph repository."
metadata = {"source": "github", "timestamp": "2026-08-10T11:45:10Z"}

result = process_text(text, metadata=metadata, source="github")
print(result)
```

### Multi-Record Batch Processing (`process_records`)

```python
from src.pipeline import process_records

records = [
    {
        "source": "slack",
        "text": "Aathi discussed ChronoGraph with Karkuvel in #dev-chat.",
        "metadata": {"channel": "#dev-chat", "timestamp": "2026-08-10T10:15:30Z"}
    },
    {
        "source": "github",
        "text": "Karkuvel committed abc1234 to ChronoGraph repository.",
        "metadata": {"repository": "ChronoGraph", "timestamp": "2026-08-10T11:45:10Z"}
    },
    {
        "source": "jira",
        "text": "Aathi was assigned CG-102 task.",
        "metadata": {"project": "CG", "timestamp": "2026-08-10T14:20:00Z"}
    }
]

result = process_records(records)
print(result)
```

---

## Neo4j-Ready JSON Output Contract

```json
{
  "entities": [
    {
      "id": "person_aathi",
      "name": "Aathi",
      "type": "PERSON"
    },
    {
      "id": "person_karkuvel",
      "name": "Karkuvel",
      "type": "PERSON"
    },
    {
      "id": "repository_chronograph",
      "name": "ChronoGraph",
      "type": "REPOSITORY"
    },
    {
      "id": "commit_abc1234",
      "name": "abc1234",
      "type": "COMMIT"
    },
    {
      "id": "issue_cg_102",
      "name": "CG-102",
      "type": "ISSUE"
    }
  ],
  "relationships": [
    {
      "source": "Karkuvel",
      "relation": "COMMITTED",
      "target": "abc1234"
    },
    {
      "source": "Aathi",
      "relation": "ASSIGNED_TO",
      "target": "CG-102"
    }
  ],
  "triples": [
    {
      "subject": "Karkuvel",
      "predicate": "COMMITTED",
      "object": "abc1234"
    },
    {
      "subject": "Aathi",
      "predicate": "ASSIGNED_TO",
      "object": "CG-102"
    }
  ],
  "metadata": {
    "records": [
      {
        "source": "slack",
        "channel": "#dev-chat",
        "timestamp": "2026-08-10T10:15:30Z"
      },
      {
        "source": "github",
        "repository": "ChronoGraph",
        "timestamp": "2026-08-10T11:45:10Z"
      },
      {
        "source": "jira",
        "project": "CG",
        "timestamp": "2026-08-10T14:20:00Z"
      }
    ]
  },
  "is_valid": true
}
```

---

## Testing & Verification

Run the full automated pytest suite:

```bash
python -m pytest -v
```

Expected output: **28 passed** (19 Week 1 baseline tests + 9 Week 2 tests).

Run the standalone Week 2 demo:

```bash
python data/week2_demo.py
```