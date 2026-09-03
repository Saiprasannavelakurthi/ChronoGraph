# ChronoGraph: Graph Extraction Module

## 1. Project Overview

**ChronoGraph** is an enterprise knowledge graph system designed to ingest, process, and query software engineering workflows across tools like Slack, GitHub, and Jira. 

The **Graph Extraction module** acts as the crucial middle layer of the ChronoGraph architecture. It is responsible for parsing unstructured, noisy enterprise text and deterministically extracting a structured entity-relationship knowledge graph (composed of entities, relationships, and Subject-Predicate-Object triples). 

**Why LLM-based Extraction?** 
Traditional NLP pipelines struggle with the contextual nuance of enterprise software terminology (e.g., distinguishing between a Jira issue "CG-102" and a commit hash, or understanding that "opening" a PR implies a specific relationship). We leverage strict, constrained Large Language Models (via LlamaIndex) combined with rigorous programmatic validation to ensure highly accurate, zero-hallucination graph representations that are robust enough to populate Neo4j for downstream GraphRAG applications.

---

## 2. Graph Extraction Workflow

The implemented execution flow for processing enterprise records operates as follows:

1. **Input Records**: Raw text data and optional metadata (e.g., Slack messages, GitHub PRs) enter the pipeline.
2. **Text Cleaning / Normalization**: Text is stripped of control characters; exact technical identifiers (commit hashes, Jira keys, Slack handles) are preserved verbatim.
3. **LLM Extraction**: A strongly-prompted LLM parses the text and strictly identifies stated facts, returning a structured JSON response.
4. **Entity Extraction**: Entities are instantiated into Pydantic models.
5. **Relationship Extraction**: Explicit relationships between source and target entities are identified.
6. **Graph Triple Generation**: Relationships are fully synchronized into (Subject -> Predicate -> Object) triples.
7. **Deduplication / Normalization**: Entities are deduplicated using deterministically generated slugs. Duplicate relationships and triples are merged.
8. **Validation**: The entire payload is strictly checked. Dangling references (edges pointing to non-existent entities) are flagged or rejected. Consistency between relationships and triples is enforced.
9. **Final GraphExtractionResult**: A standardized, Neo4j-ready dictionary is serialized, containing `entities`, `relationships`, `triples`, and an `is_valid` flag indicating structural health.

---

## 3. Final Project Structure

```text
graph-extraction/
│
├── data/
│   ├── final_demo.py
│   ├── sample_input.json
│   └── sample_output.json
│
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── errors.py
│   ├── extractor.py
│   ├── models.py
│   ├── pipeline.py
│   ├── prompts.py
│   ├── validator.py
│   └── utils/
│       ├── __init__.py
│       └── text_utils.py
│
├── tests/
│   ├── __init__.py
│   ├── test_comprehensive.py
│   ├── test_edge_cases.py
│   ├── test_extractor.py
│   ├── test_pipeline.py
│   ├── test_robustness.py
│   └── test_validator.py
│
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 4. File-by-File Documentation

### Source Code (`src/`)

- **`src/config.py`**: Configuration manager that loads LLM provider settings (Groq, OpenAI, Ollama) and handles environment API key validation.
- **`src/errors.py`**: Defines custom domain exceptions (`GraphExtractionError`, `LLMCommunicationError`, `MalformedLLMResponseError`, `ExtractionValidationError`) used to gracefully identify and intercept failure states.
- **`src/extractor.py`**: Contains the core `GraphExtractor` class. It manages LLM communication, parses raw JSON output, catches malformed LLM responses gracefully, and performs post-processing synchronization (linking relationships to triples).
- **`src/models.py`**: Defines strict Pydantic schemas and Enums (`Entity`, `Relationship`, `GraphTriple`, `GraphExtractionResult`) that act as the single source of truth for the extracted data structures.
- **`src/pipeline.py`**: The primary public API (`process_text`, `process_records`). It orchestrates extraction, validation, and error handling. It ensures that any upstream validation failures are cleanly serialized into an `is_valid: False` dictionary instead of abruptly crashing the application.
- **`src/prompts.py`**: Houses the highly-tuned, zero-hallucination system and user prompts. It guides the LLM on how to extract evidence-grounded facts based on distinct enterprise contexts.
- **`src/validator.py`**: The structural enforcer. It validates the integrity of the extraction, ensuring there are no missing fields, no dangling entity references, and perfect consistency between relationships and triples.
- **`src/utils/text_utils.py`**: Contains deterministic text normalization routines and advanced Regex patterns to protect exact casing for technical identifiers (like GitHub commit hashes and Slack `@handles`) while standardizing general entity names.

### Data & Demos (`data/`)

- **`data/final_demo.py`**: An executable demonstration script. It simulates a multi-source (Slack, GitHub, Jira) pipeline run using a mock LLM. It actively demonstrates how the system deduplicates entities, flags dangling references, and handles completely malformed JSON responses without crashing. Run this to see the pipeline in action.
- **`data/sample_input.json`**: Reference file showing the expected schema of raw, unstructured ingestion records.
- **`data/sample_output.json`**: Reference file demonstrating a finalized, validated Neo4j-ready output payload.

### Test Suite (`tests/`)

- **`tests/test_comprehensive.py`**: The overarching integration test suite checking validation flags, error fallbacks, and multi-source context handling (Slack vs Jira vs GitHub).
- **`tests/test_edge_cases.py`**: Focuses on bizarre or extreme text inputs, multi-hop relationship consistency, exact technical identifier regex protection, and exact deterministic slug generation.
- **`tests/test_extractor.py`**: Tests the `GraphExtractor` class directly. Validates that markdown-wrapped JSON is properly extracted, unexpected LLM strings fail safely, and triples are accurately synchronized with relationships.
- **`tests/test_pipeline.py`**: Tests the orchestrator logic to ensure exceptions bubble up correctly when configured, or are safely trapped in the `is_valid: False` serialization when batch processing.
- **`tests/test_robustness.py`**: Checks text-level robustness and ensures that validation error strings are clear, informative, and accurately identify the offending nodes.
- **`tests/test_validator.py`**: Isolated unit tests for the strict structural rules in `validator.py` (catching missing fields, dangling edges, and duplicates).

### Root Files

- **`requirements.txt`**: Standard Python package dependencies (e.g., `llama-index-core`, `pydantic`, `pytest`).
- **`.env.example`**: Template showing required configuration variables (`LLM_PROVIDER`, `GROQ_API_KEY`).
- **`.gitignore`**: Defines standard files and generated artifacts (like `__pycache__`) to exclude from version control.

---

## 5. Source Code Responsibilities

The architecture maintains a strict, uni-directional flow of responsibility:

1. A caller invokes **`pipeline.py`** (`process_text` or `process_records`).
2. **`pipeline.py`** uses **`utils/text_utils.py`** to sanitize the raw text before passing it to the extractor.
3. **`pipeline.py`** instantiates **`extractor.py`** (`GraphExtractor`), utilizing **`config.py`** to obtain the active LLM client.
4. **`extractor.py`** formats prompts from **`prompts.py`** and sends them to the LLM. 
5. The LLM's response is mapped directly into the Pydantic schemas defined in **`models.py`**. If the LLM hallucinates or returns malformed data, **`extractor.py`** raises custom exceptions from **`errors.py`**.
6. **`extractor.py`** uses **`utils/text_utils.py`** to perform deduplication and normalization on the resulting models.
7. **`pipeline.py`** then hands the resulting `GraphExtractionResult` to **`validator.py`**, which strictly audits the internal structure (checking for dangling references and consistency).
8. **`pipeline.py`** intercepts any validation errors or `GraphExtractionError`s, logs them, and returns a final serialized dictionary.

---

## 6. Installation

1. Ensure you have Python 3.10+ installed.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and configure your chosen LLM provider (e.g., `GROQ_API_KEY`).

## 7. Running the Demo

To run the offline executable demo (which demonstrates deduplication, dangling reference handling, and edge-case resilience):

```bash
python data/final_demo.py
```

## 8. Running the Tests

The extensive `pytest` suite guarantees the stability of all extraction, validation, and pipeline components.

```bash
python -m pytest -v
```
