# ChronoGraph — LLM Graph Extraction Module

**Module Owner:** Aathi Narayana Moorthi  
**Module:** LLM Graph Extraction

---

## 1. Project Overview

**ChronoGraph** is a Temporal GraphRAG system designed for enterprise forensic analysis across software development and team communication data.

This **`graph-extraction`** module forms the entry point of the ChronoGraph pipeline. It is responsible for extracting structured entities, relationships, and subject-predicate-object graph triples from unstructured enterprise text (Slack messages, GitHub commits and pull requests, Jira tickets) using Large Language Models (LLMs) via LlamaIndex. The extracted output is structured, validated, and normalized for downstream Neo4j temporal graph indexing.

---

## 2. Module Responsibility

The `graph-extraction` module performs the following core tasks:

- **Entity Extraction:** Identifies enterprise entities (people, repositories, issues, commits, pull requests, channels, systems, services, projects) mentioned in text.
- **Relationship Extraction:** Identifies explicit directional interactions and actions between extracted entities.
- **Graph Triple Generation:** Formulates `(subject, predicate, object)` triples synchronized 1-to-1 with extracted relationships.
- **Source-Aware Context Formatting:** Applies source-specific extraction guidance (Slack, GitHub, Jira, General) to the LLM prompt.
- **Entity Normalization:** Normalizes entity names consistently while preserving case-sensitive technical identifiers such as commit hashes (`abc1234`), Jira keys (`CG-102`), PR numbers (`#24`), and @handles.
- **Entity Deduplication:** Generates deterministic slug IDs (`person_aathi`, `issue_cg_102`) and deduplicates entities within and across multi-source records.
- **Graph Validation:** Enforces strict Neo4j-readiness constraints, including dangling reference detection, duplicate entity/relationship detection, and relationship-triple consistency checks.
- **Downstream Readiness:** Formats validated graph payloads for consumption by downstream temporal Neo4j storage modules.

---

## 3. Supported Data Sources

The current implementation supports context-aware extraction for the following enterprise data sources:

- **Slack:** Team communications, channel activity (`#dev-chat`), user mentions (`@user`), discussions (`DISCUSSED`), proposals (`SUGGESTED`), and channel participation (`PARTICIPATED_IN`).
- **GitHub:** Version control operations, repository references (`PART_OF`), commits (`COMMITTED`), pull requests (`OPENED`, `REVIEWED`, `MERGED`), and commit hashes (`abc1234`).
- **Jira:** Agile project management, issue tickets (`CG-102`), task assignments (`ASSIGNED_TO`), status transitions (`RESOLVED`, `CLOSED`), and task dependencies (`DEPENDS_ON`).

> **Note:** Input data is provided as structured text records with source context tags (`source="slack"`, `"github"`, `"jira"`). Live REST API or OAuth ingestion is outside the scope of this module.

---

## 4. Extraction Pipeline Architecture

The graph extraction workflow follows a sequential 8-stage pipeline:

```text
Input (Enterprise Text / Batch Records)
  |
  v
Input Cleaning & Validation (whitespace, control characters, empty guard)
  |
  v
Source-Aware Context Formatting (Slack / GitHub / Jira / General)
  |
  v
LLM Extraction (LlamaIndex LLM + System & User Prompts)
  |
  v
JSON Response Parsing (markdown unwrapping, JSON boundary detection, schema validation)
  |
  v
Entity Normalization & Deduplication (canonical names, deterministic slug IDs)
  |
  v
Relationship & Triple Post-Processing (synchronization, deduplication)
  |
  v
Graph Validation (5-tier integrity checks + duplicate & consistency detection)
  |
  v
Validated Neo4j-Ready Graph Payload (JSON)
```

---

## 5. Entity Extraction

Entities are extracted by the LLM and validated against the following allowed types:

| Entity Type | Description |
|---|---|
| `PERSON` | Human names |
| `USER` | System/platform user accounts |
| `TEAM` | Groups or teams |
| `ORGANIZATION` | Companies or organizations |
| `PROJECT` | Engineering projects |
| `REPOSITORY` | Code repositories |
| `ISSUE` | Bug reports, Jira tickets |
| `TASK` | Work items or tasks |
| `COMMIT` | Version control commits |
| `PULL_REQUEST` | Pull requests or merge requests |
| `CHANNEL` | Slack or communication channels |
| `MESSAGE` | Individual messages |
| `DOCUMENT` | Documentation or files |
| `SYSTEM` | Infrastructure systems or platforms |
| `SERVICE` | External services (GCP, AWS) |
| `OTHER` | Fallback for unrecognized types |

Each entity is assigned a deterministic slug ID (e.g., `person_aathi`, `issue_cg_102`, `pull_request_24`).

---

## 6. Relationship Extraction

The LLM extracts explicit directional relationships using the following allowed types:

`WORKED_ON`, `CREATED`, `ASSIGNED_TO`, `ASSIGNED`, `AUTHORED`, `MENTIONED`, `REVIEWED`, `COMMITTED`, `OPENED`, `CLOSED`, `MERGED`, `PART_OF`, `BELONGS_TO`, `DEPENDS_ON`, `RELATED_TO`, `PARTICIPATED_IN`, `SUGGESTED`, `DISCUSSED`, `APPROVED`, `RESOLVED`, `DEPLOYED`, `FIXED`, `OTHER`

Each relationship links a `source` entity to a `target` entity via a `relation` predicate. Unknown predicates fall back to `OTHER`.

---

## 7. Graph Triple Generation

Each extracted relationship is synchronized 1-to-1 with a graph triple:

```
Relationship: { source: "Aathi", relation: "ASSIGNED_TO", target: "CG-102" }
Triple:        { subject: "Aathi", predicate: "ASSIGNED_TO", object: "CG-102" }
```

If the LLM omits the `triples` array, it is automatically generated from the `relationships` array by `GraphExtractionResult.ensure_triples_populated`.

---

## 8. Entity Normalization

Normalization is performed in `src/utils/text_utils.py`:

- **Identifier Preservation:** Commit hashes (`abc1234`), Jira keys (`CG-102`), PR numbers (`#24`), @handles (`@karkuvel`), and known tech acronyms (`GCP`, `AWS`) are preserved exactly.
- **Case Normalization:** All-uppercase or all-lowercase human names are converted to Title Case (`AATHI` → `Aathi`, `karkuvel` → `Karkuvel`). CamelCase names are preserved.
- **Slug Generation:** Each entity receives a deterministic slug ID: `person_karkuvel`, `issue_cg_102`, `commit_abc1234`, `pull_request_24`.
- **Deduplication:** Entities with the same canonical name and type are collapsed to a single canonical record.

---

## 9. Validation

Graph validation is implemented in `src/validator.py` and runs on every extraction before serialization. The validation hierarchy:

1. **Schema & Structure Conformance:** Validates that the input matches `GraphExtractionResult` Pydantic schema.
2. **Entity Field Integrity:** Ensures every entity has a non-empty `id`, `name`, and a recognized `type`. Empty type strings are flagged as errors.
3. **Duplicate Entity Detection:** Warns when two entities share the same `id` or the same canonical `(name, type)` key.
4. **Dangling Relationship Reference Check:** Verifies that relationship `source` and `target` both exist in the extracted entities set.
5. **Duplicate Relationship Detection:** Warns when the same `(source, relation, target)` tuple appears more than once.
6. **Dangling Triple Reference Check:** Verifies that triple `subject` and `object` both exist in the extracted entities set.
7. **Duplicate Triple Detection:** Warns when the same `(subject, predicate, object)` tuple appears more than once.
8. **1-to-1 Relationship–Triple Consistency Check (strict mode):** Ensures every relationship has a matching triple and vice-versa. Can be disabled with `strict_triple_consistency=False`.

`validate_extraction()` returns a `ValidationResult` with `is_valid`, `errors`, and `warnings` fields.

---

## 10. Error Handling

The exception hierarchy is defined in `src/errors.py`:

| Exception | When Raised |
|---|---|
| `GraphExtractionError` | Base class for all extraction errors |
| `LLMCommunicationError` | LLM API call fails (network, timeout, auth) |
| `MalformedLLMResponseError` | LLM response cannot be parsed into valid graph output |
| `ExtractionValidationError` | Extracted graph fails strict validation checks |

- **Empty input:** Returns a valid empty result — no exception raised.
- **None or non-string input:** Coerced to string; pipeline continues gracefully.
- **Malformed JSON:** Logged at WARNING level; returns empty result without raising.
- **Non-dict metadata:** Logged at WARNING level; metadata excluded from output.
- **Validation failures:** Raises `ExtractionValidationError` (with `errors` list) when `raise_on_validation_error=True`. Returns `is_valid=False` payload when `False`.
- **LLM failures:** Always raises `LLMCommunicationError` with the original exception preserved in `.original_error`.

---

## 11. Project Structure

```text
graph-extraction/
├── .env.example            # Template for environment configuration
├── .gitignore              # Git file exclusion rules
├── README.md               # Module documentation
├── requirements.txt        # Python package dependencies
├── data/                   # Sample datasets and demonstration scripts
│   ├── demo_run.py         # Multi-record batch extraction demo
│   ├── real_groq_demo.py   # Live Groq API demonstration script
│   ├── sample_input.json   # Sample input enterprise records
│   ├── sample_output.json  # Sample Neo4j-ready output JSON
│   ├── week2_demo.py       # Batch processing and deduplication demo
│   ├── week3_demo.py       # Accuracy, reliability, and validation demo
│   └── week4_demo.py       # Validation, error handling, and edge-case demo
├── src/                    # Production source code
│   ├── __init__.py
│   ├── config.py           # Configuration loader & LlamaIndex LLM provider
│   ├── errors.py           # Custom exception hierarchy
│   ├── extractor.py        # GraphExtractor: LLM invocation, parsing, post-processing
│   ├── models.py           # Pydantic schema models (Entity, Relationship, GraphTriple, GraphExtractionResult)
│   ├── pipeline.py         # Entry points: process_text(), process_records(), serialization
│   ├── prompts.py          # Evidence-grounded system & user prompt templates
│   ├── validator.py        # 8-tier graph validation logic
│   └── utils/
│       ├── __init__.py
│       └── text_utils.py   # Text cleaning, normalization, slug generation, deduplication
└── tests/                  # Automated pytest test suite
    ├── __init__.py
    ├── test_edge_cases.py  # Extended edge-case test suite
    ├── test_extractor.py   # Unit tests for GraphExtractor
    ├── test_pipeline.py    # Integration tests for process_text and process_records
    ├── test_validator.py   # Validation logic tests
    ├── test_week2.py       # Source-aware batch processing tests
    ├── test_week3.py       # Accuracy, reliability, and consistency tests
    └── test_week4.py       # Week 4 edge-case, error handling, and regression tests
```

---

## 12. Installation

### Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- `pip` package manager

### Setup Instructions

1. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   ```

2. **Activate the virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS:**
     ```bash
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 13. Environment Configuration

Copy `.env.example` to create your local `.env` file:

```bash
cp .env.example .env
```

Then fill in your API credentials.

### Environment Variables

| Variable | Description | Default | Example |
|---|---|---|---|
| `LLM_PROVIDER` | LLM service provider | `groq` | `groq`, `ollama`, `openai` |
| `LLM_MODEL` | LLM model identifier | `llama-3.3-70b-versatile` | `llama-3.3-70b-versatile`, `llama3` |
| `GROQ_API_KEY` | Groq API Key | None | `gsk_your_api_key_here` |
| `LLM_API_KEY` | Fallback API Key | None | `sk-your_api_key_here` |
| `LLM_BASE_URL` | API base URL | `https://api.groq.com/openai/v1` | `http://localhost:11434` (Ollama) |
| `LLM_TEMPERATURE` | Model temperature | `0.0` | `0.0` (deterministic) |
| `EXTRACTION_MAX_RETRIES` | Max API retries | `2` | `2` |
| `LOG_LEVEL` | Logging verbosity | `INFO` | `DEBUG`, `INFO`, `ERROR` |

> **Security:** Never commit real API keys to source control. `.env` is excluded via `.gitignore`.

---

## 14. Running the Demos

The demonstration scripts use offline mock LLMs by default — no API key is required unless you run `real_groq_demo.py`.

```bash
# General multi-record extraction demo (Slack, GitHub, Jira)
python data/demo_run.py

# Week 2: Batch processing and cross-record deduplication demo
python data/week2_demo.py

# Week 3: Accuracy, reliability, and validation demo
python data/week3_demo.py

# Week 4: Validation, error handling, and edge-case demo
python data/week4_demo.py
```

---

## 15. Running Tests

Run the full automated pytest suite:

```bash
python -m pytest -v
```

Run individual test files:

```bash
# Week 4 edge-case and regression tests
python -m pytest tests/test_week4.py -v

# Validator tests
python -m pytest tests/test_validator.py -v

# Edge-case tests
python -m pytest tests/test_edge_cases.py -v
```

### What the Tests Cover
- Entity extraction, classification, and deterministic slug generation.
- Exact preservation of identifiers (Jira keys `CG-102`, commit SHAs `abc1234`, PRs `#24`, handles `@user`).
- Source-aware prompt formatting for `SLACK`, `GITHUB`, and `JIRA`.
- Action verb precision (`SUGGESTED` vs `CREATED`, `DISCUSSED` vs `AUTHORED`).
- 8-tier validation hierarchy: schema, entity fields, dangling references, duplicates, and consistency.
- Empty string, `None`, whitespace-only, and non-string input handling.
- Malformed, truncated, and non-JSON LLM response resilience.
- LLM communication exception wrapping (`LLMCommunicationError`).
- Duplicate entity, relationship, and triple detection (warnings).

---

## 16. Graph Extraction Output

`process_text()` and `process_records()` produce a validated dictionary conforming to the standard output contract:

```json
{
  "entities": [
    { "id": "person_aathi",         "name": "Aathi",       "type": "PERSON" },
    { "id": "issue_cg_102",         "name": "CG-102",      "type": "ISSUE" },
    { "id": "pull_request_24",      "name": "#24",         "type": "PULL_REQUEST" },
    { "id": "repository_chronograph","name": "ChronoGraph","type": "REPOSITORY" }
  ],
  "relationships": [
    { "source": "Aathi",  "relation": "ASSIGNED_TO", "target": "CG-102" },
    { "source": "Aathi",  "relation": "REVIEWED",    "target": "#24" },
    { "source": "Aathi",  "relation": "MERGED",       "target": "#24" },
    { "source": "#24",    "relation": "PART_OF",      "target": "ChronoGraph" }
  ],
  "triples": [
    { "subject": "Aathi", "predicate": "ASSIGNED_TO", "object": "CG-102" },
    { "subject": "Aathi", "predicate": "REVIEWED",    "object": "#24" },
    { "subject": "Aathi", "predicate": "MERGED",       "object": "#24" },
    { "subject": "#24",   "predicate": "PART_OF",      "object": "ChronoGraph" }
  ],
  "metadata": {
    "records": [
      { "source": "jira",   "project": "CG" },
      { "source": "github", "repository": "ChronoGraph" }
    ]
  },
  "is_valid": true
}
```

When validation fails with `raise_on_validation_error=False`, the output also includes:

```json
{
  "is_valid": false,
  "validation_errors": ["Relationship target 'X' at index 0 is a dangling reference..."]
}
```

---

## 17. Development Summary

### Week 1 — Core Pipeline & Initial Setup
Established the initial extraction pipeline, LlamaIndex integration (`src/extractor.py`), Pydantic schema models (`src/models.py`), entity normalization, deterministic slug ID generation, and primary 5-tier validation logic (`src/validator.py`).

### Week 2 — Batch Processing, Identifiers & Source Context
Added multi-record batch processing (`process_records()`), source-aware context prompts for Slack, GitHub, and Jira, cross-record entity deduplication, and exact identifier preservation for Jira keys (`CG-102`), commit SHAs (`abc1234`), and PR numbers (`#24`).

### Week 3 — Accuracy, Reliability & Comprehensive Testing
Enhanced prompt engineering for zero hallucination and evidence grounding, expanded action verb taxonomy (`SUGGESTED`, `DISCUSSED`, `APPROVED`, `RESOLVED`, `DEPLOYED`, `FIXED`), formalized the validation hierarchy, implemented the custom exception hierarchy (`src/errors.py`), and expanded the automated pytest suite to 61 tests.

### Week 4 — Final Validation, Stabilization & Documentation
- **Validation enhancements:** Added duplicate entity ID detection, duplicate canonical `(name, type)` detection, duplicate relationship detection, duplicate triple detection, and orphan-side warnings when only relationships or only triples are present.
- **Bug fixes:** Fixed empty entity type string not being flagged as an error (Pydantic maps `""` to `OTHER` via `_missing_` before the validator ran).
- **Error handling improvements:** Improved diagnostic logging in `extractor._parse_llm_response` — JSON position, parsed data keys, and 300-character response snippets are now included in all warning messages. Added explicit `None` response guard. Added early return with warning when no JSON object boundaries are found.
- **Pipeline robustness:** `process_text` now coerces `None` and non-string inputs to string, and rejects non-dict metadata gracefully with a logged warning.
- **Edge-case tests:** Created `tests/test_week4.py` with 49 targeted tests across 8 test classes covering all cases above.
- **Regression:** All 110 tests (61 existing + 49 new) pass with exit code 0.
- **Week 4 demo:** Created `data/week4_demo.py` showcasing all new validation and error handling capabilities using offline mock LLMs.
- **README:** Fully updated to accurately document all current Week 1–4 functionality.
- **requirements.txt:** Reviewed and confirmed against actual imports — no changes required.

---

## 18. Current Limitations

- **Source Ingestion:** Slack, GitHub, and Jira data is provided via text string records. Live REST API and OAuth ingestion adapters are not implemented in this module.
- **LLM Dependency:** Real extraction requires a configured LLM endpoint (Groq API key, local Ollama, or OpenAI). Unit and regression tests use mock LLM instances for fully offline execution.
- **Temporal Metadata:** The module extracts and preserves timestamp metadata from input records but does not perform temporal graph reasoning itself. Temporal indexing is the responsibility of the downstream Neo4j module.

---

## 19. Downstream Neo4j Integration

The output produced by this `graph-extraction` module — validated, normalized entities, relationships, and graph triples — is structured to serve as the direct input payload for the downstream ChronoGraph Neo4j temporal graph indexing and temporal GraphRAG retrieval pipeline.
