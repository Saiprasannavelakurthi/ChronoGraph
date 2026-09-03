# Week 4 — Retrieval Query API Contract

**Module Owner**: Karkuvel (`data-ingestion` branch)  
**Contract Version**: Week 4.0  
**Service Layer**: `src/retrieval/service.py` → `RetrievalService`  
**API Router / App**: `src/api/app.py`  
**Consumes**: `data/processed/retrieval_ready_records.json` & `data/processed/retrieval_quality_stats.json`  
**CLI Startup**: `python main.py --start-api` or `python main.py --serve-api`

---

## 1. Overview

The **Week 4 Temporal Retrieval Query API** exposes the pre-processed, citation-ready evidence records produced by the Week 3 retrieval pipeline over a standardized, high-performance REST interface.

It allows downstream components (such as the Temporal Routing Layer, GraphRAG Query Engine, or UI Frontend) to execute granular temporal and entity queries with chronological sorting and pagination guarantees.

### Architecture

```
                       HTTP Request
                            ↓
             FastAPI Endpoint Layer (app.py)
                            ↓
               Pydantic Request Validation
                (RetrievalQueryRequest)
                            ↓
         RetrievalService (src/retrieval/service.py)
                            ↓
          Load & Validate retrieval_ready_records.json
                            ↓
        TemporalFilterEngine (src/retrieval/filter.py)
   (Source → Entity → Relation → Temporal → Sort → Limit)
                            ↓
      Structured JSON Response (RetrievalQueryResponse)
                 with Full Provenance Metadata
```

---

## 2. API Endpoints Summary

| Method | Path | Summary | Description |
|---|---|---|---|
| `GET` | `/api/health` | Health & Data Availability Check | Returns service status, retrieval data presence on disk, and total record count. |
| `POST` | `/api/retrieval/query` | Temporal Retrieval Query | Filters, sorts, and limits evidence records according to multi-dimensional criteria. |
| `GET` | `/api/retrieval/stats` | Retrieval Quality Statistics | Returns data quality metrics (entity/relation counts, date ranges, source distribution). |

---

## 3. Endpoints Specification

### 3.1 `GET /api/health`

Liveness and data readiness probe.

#### Response: `200 OK`

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

#### Fields

| Field | Type | Description |
|---|---|---|
| `status` | `string` | `"ok"` if service is operational. |
| `service` | `string` | Name of the service. |
| `version` | `string` | API version (`"1.0.0"`). |
| `retrieval_data_available` | `boolean` | `true` if `retrieval_ready_records.json` exists on disk. |
| `retrieval_records_count` | `integer \| null` | Number of validated retrieval records on disk, or `null` if unavailable. |
| `timestamp` | `string (ISO-8601)` | Current UTC timestamp. |

---

### 3.2 `POST /api/retrieval/query`

Executes multi-criteria temporal retrieval.

#### Request Schema (`RetrievalQueryRequest`)

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | `string` | No | `null` | Natural-language query string (echoed in response). |
| `query_text` | `string` | No | `null` | Alias for `query`. |
| `entity_hints` | `List[string]` | No | `[]` | Filter by entities matching subject or object (canonical name or display name, case-insensitive). |
| `entities` | `List[string]` | No | `[]` | Alias for `entity_hints`. |
| `relation_hints` | `List[string]` | No | `[]` | Filter by normalized uppercase relation labels (e.g. `["MIGRATED_TO", "ADVOCATED_FOR"]`). |
| `sources` | `List[string]` | No | `[]` | Restrict results to source systems: `"slack"`, `"github"`, `"jira"`. Empty means all sources. |
| `exact_date` | `string (YYYY-MM-DD)` | No | `null` | Match events on this exact UTC calendar date. |
| `start_date` | `string (YYYY-MM-DD)` | No | `null` | Inclusive lower bound of calendar date range. |
| `end_date` | `string (YYYY-MM-DD)` | No | `null` | Inclusive upper bound of calendar date range. |
| `before_date` | `string (YYYY-MM-DD)` | No | `null` | Return only events strictly before this date (`< before_date`). |
| `after_date` | `string (YYYY-MM-DD)` | No | `null` | Return only events strictly after this date (`> after_date`). |
| `sort_order` | `string ("asc" \| "desc")` | No | `"asc"` | Chronological sort direction (`"asc"` = earliest first, `"desc"` = latest first). |
| `limit` | `integer (1 - 1000)` | No | `20` | Maximum number of records to return (backward compatibility alias). |
| `page` | `integer (>= 1)` | No | `1` | 1-based page number for pagination. |
| `page_size` | `integer (1 - 100)` | No | `20` | Number of items per page. Defaults to `limit` (or 20). |

#### Example Request (Paginated)

```json
{
  "query": "What decisions were made regarding GCP after April 2023?",
  "entity_hints": ["gcp", "arun_sharma"],
  "relation_hints": ["MIGRATED_TO", "ADVOCATED_FOR"],
  "sources": ["slack", "github"],
  "after_date": "2023-04-01",
  "sort_order": "asc",
  "page": 2,
  "page_size": 5
}
```

#### Response Schema (`RetrievalQueryResponse` — `200 OK`)

```json
{
  "query": "What decisions were made regarding GCP after April 2023?",
  "total_matches": 12,
  "returned_count": 5,
  "page": 2,
  "page_size": 5,
  "total_pages": 3,
  "has_next": true,
  "has_previous": true,
  "results": [
    {
      "record_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
      "triple_id": "779f3f63-0287-40b1-a5ca-82d74c784851",
      "subject": "karkuvel",
      "subject_display": "Karkuvel",
      "subject_type": "Person",
      "relation": "MIGRATED_TO",
      "object": "gcp",
      "object_display": "GCP",
      "object_type": "Technology",
      "timestamp": "2023-05-10T09:15:00+00:00",
      "event_date": "2023-05-10",
      "source": "github",
      "source_id": "github_pr_007",
      "source_url": "https://github.com/org/repo/pull/7",
      "evidence": "Karkuvel completed the migration to GCP.",
      "confidence": 0.95,
      "extraction_mode": "llm_groq",
      "metadata": {
        "html_url": "https://github.com/org/repo/pull/7"
      }
    }
  ],
  "applied_filters": {
    "query_text": "What decisions were made regarding GCP after April 2023?",
    "entities": ["gcp", "arun_sharma"],
    "relation_hints": ["MIGRATED_TO", "ADVOCATED_FOR"],
    "sources": ["slack", "github"],
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
    "page": 2,
    "page_size": 5
  },
  "generated_at": "2026-08-28T13:45:00.000000+00:00"
}
```

---

### 3.3 `GET /api/retrieval/stats`

Returns comprehensive data quality metrics computed from `retrieval_ready_records.json`.

#### Response: `200 OK`

```json
{
  "total_records": 142,
  "unique_entities": 30,
  "unique_relations": 8,
  "records_with_temporal_data": 142,
  "records_without_temporal_data": 0,
  "earliest_timestamp": "2023-03-15",
  "latest_timestamp": "2023-05-30",
  "source_breakdown": {
    "slack": 51,
    "jira": 51,
    "github": 40
  },
  "average_confidence": 0.8311,
  "records_with_source_url": 0,
  "generated_at": "2026-08-28T13:40:47.000000+00:00"
}
```

---

## 4. Filtering and Sorting Logic

The filtering engine evaluates constraints strictly in this deterministic sequence (without requiring an LLM or external search engine):

1. **Source System Filtering**: Records must match one of the allowed sources in `sources`.
2. **Entity Filtering**: Matches against `subject`, `object`, `subject_display`, or `object_display` (case-insensitive).
3. **Relation Filtering**: Matches normalized `relation` label against `relation_hints`.
4. **Temporal Filtering**:
   - `exact_date`: Matches `event_date == exact_date`.
   - `start_date` / `end_date`: Inclusive boundary check (`start_date <= event_date <= end_date`).
   - `before_date`: Strict upper bound (`event_date < before_date`).
   - `after_date`: Strict lower bound (`event_date > after_date`).
5. **Free-Text Query Matching & Relevance Scoring**:
   - When a free-text `query` (or `query_text`) is supplied, records are matched case-insensitively across `subject`, `object`, display names, `relation`, `evidence`, `source`, and `source_id`.
   - Deterministic relevance score weighting:
     - Entity match (`subject`/`object`/display names): **3.0** per term (+5.0 phrase bonus).
     - Relation label match: **2.0** per term (+3.0 phrase bonus).
     - Evidence snippet match: **1.0** per term (+2.0 phrase bonus).
     - Source system / ID match: **1.0** per term (+1.0 phrase bonus).
   - Only records with score > 0 are retained.
6. **Total Matches Calculation**: Count of all records passing steps 1–5.
7. **Sorting**:
   - When `query` is present: Primary sort by `relevance_score` (descending). Secondary tie-breaking sort by `(event_date, timestamp)` according to `sort_order` (`asc` or `desc`).
   - When `query` is omitted: Pure chronological sort on `(event_date, timestamp)` according to `sort_order`.
8. **Limit / Pagination**: Page slicing `[(page-1)*page_size : page*page_size]`.

---

## 5. Provenance Guarantees

Every result item in `results` contains the complete audit trail:
- `record_id` & `triple_id`: Deterministic UUID tracking the evidence back to its graph extraction triple.
- `source` & `source_id`: Source platform and native ID (e.g. `slack_001`, `github_pr_007`, `jira_001`).
- `source_url`: Permalinks / web URLs when available from source metadata.
- `evidence`: Verbatim text snippet from which the triple and temporal relation were extracted.
- `timestamp` & `event_date`: Verified UTC ISO-8601 timestamp and calendar date.

---

## 6. Error Handling & Resilience

The ChronoGraph Retrieval API enforces secure, consistent error handling without exposing internal stack traces, local filesystem paths, or environment variables to API clients.

### 6.1 HTTP Status Codes & Error Responses

| HTTP Status | Trigger Condition | Response Structure | Description |
|---|---|---|---|
| `404 Not Found` | `retrieval_ready_records.json` or stats missing on disk | `{"detail": "Retrieval data file not found. Run 'python main.py --prepare-retrieval' first."}` | Raised when evidence data has not been prepared. Safe message returned. |
| `422 Unprocessable Entity` | Pydantic validation failure (e.g. invalid date order, non-existent source enum, invalid page/limit) | `{"detail": [{"loc": ["body", "start_date"], "msg": "start_date must not be after end_date", "type": "value_error"}]}` | Standard FastAPI/Pydantic validation errors with field location details. |
| `500 Internal Server Error` | File corruption, invalid JSON, or unparseable top-level data structure | `{"detail": "Retrieval data file is corrupted or cannot be parsed."}` | Domain format error safely wrapped to prevent data leakage. |
| `500 Internal Server Error` | Unexpected internal server or service runtime failure | `{"detail": "Internal server error occurred while processing retrieval query."}` | Sanitized generic message; full traceback logged internally. |

### 6.2 Resilience & Caching Guarantees

1. **In-Memory Cache Preservation**: Successfully loaded records remain safely cached. If a subsequent `load_records(force_reload=True)` fails due to file deletion or syntax errors, the existing cache is preserved and remains queryable.
2. **Partial Corruption Tolerance**: If individual records in `retrieval_ready_records.json` are malformed or missing required fields, they are logged as warnings and skipped, allowing all valid records to load successfully.
3. **Empty File Safety**: An empty `retrieval_ready_records.json` is treated cleanly as zero records (`[]`) without throwing unhandled exceptions.
4. **Information Security**: Error responses never include Python tracebacks, database URIs, local filesystem directory structures, or API tokens.

---

## 7. Request Validation Limits (Week 4 Day 6)

All request validation is enforced by Pydantic at the FastAPI layer before any business logic executes. Invalid requests return `HTTP 422 Unprocessable Entity`.

### 7.1 Text Field Limits

| Field | Constraint | Description |
|---|---|---|
| `query` | max 2 000 characters | Natural-language search string. Treated purely as data — never executed as SQL, Cypher, or shell command. |
| `query_text` | max 2 000 characters | Alias for `query`. Same constraint applies. |

### 7.2 List Field Limits

| Field | Constraint | Description |
|---|---|---|
| `entity_hints` | max 50 items | Entity filter list. Prevents unreasonably large per-request filtering. |
| `entities` | max 50 items | Alias for `entity_hints`. Same constraint applies. |
| `relation_hints` | max 50 items | Relation label filter list. |
| `sources` | values restricted to `"slack"`, `"github"`, `"jira"` | Any unknown source value triggers a 422 response. Empty list means all sources. |

### 7.3 Numeric Field Limits

| Field | Constraint | Description |
|---|---|---|
| `limit` | 1 – 1 000 | Maximum number of records to return (backward compatibility). |
| `page` | 1 – 9 999 | 1-based page number. Prevents unreasonably large offset calculations. |
| `page_size` | 1 – 100 | Records per page. |

### 7.4 Date Field Constraints

| Field | Constraint |
|---|---|
| `exact_date`, `start_date`, `end_date`, `before_date`, `after_date` | Must be a valid ISO 8601 calendar date (`YYYY-MM-DD`). Malformed strings return 422. |
| `start_date` / `end_date` pair | `start_date` must not be after `end_date`. Inverted ranges return 422. |

### 7.5 Text Input Safety

Free-text query values in `query` / `query_text` are treated **purely as data**:

- They are matched case-insensitively against record fields using string operations.
- They are **never** interpolated into SQL, Cypher, shell commands, or filesystem paths.
- Special characters (SQL injection patterns, Cypher clauses, shell metacharacters, XSS payloads, path traversal sequences) are all handled safely and simply return 0 results if no records match.

### 7.6 Response Safety Guarantees

API responses at all times:

- Do **not** include Python tracebacks.
- Do **not** expose local filesystem paths.
- Do **not** expose environment variables, API keys, or database connection strings.
- Do **not** expose raw exception messages from service or data errors.
- Return only structured, sanitised `{"detail": "..."}` messages for all error statuses.

---

## 8. Observability & Audit Metadata (Week 4 Day 7)

Every successful `POST /api/retrieval/query` response now includes a `metadata` field providing per-request tracing information.

### 8.1 `RetrievalRequestMetadata` — Response Field

The `metadata` field is added to `RetrievalQueryResponse`. It is `null` only if the service layer fails before metadata can be produced; under normal operation it is always populated.

#### `metadata` Object Fields

| Field | Type | Description |
|---|---|---|
| `request_id` | `string (UUID)` | Server-generated UUID uniquely identifying this request. Safe to log. Never derived from user input. |
| `execution_time_ms` | `float (>= 0)` | Wall-clock time in milliseconds measured with a monotonic timer from the start of `query()` to completion. Always non-negative. |
| `returned_count` | `integer (>= 0)` | Number of evidence records returned in this response page. Equals `len(results)`. |
| `total_count` | `integer (>= 0)` | Total number of matching records before pagination was applied. Equals `total_matches`. |
| `page` | `integer (>= 1)` | Current 1-based page number. |
| `page_size` | `integer (>= 1)` | Number of records per page as applied. |
| `cache_hit` | `boolean` | `true` if records were served from the in-memory cache (a prior request already loaded them). `false` if records were loaded from disk for this request. |
| `timestamp` | `string (ISO-8601)` | UTC timestamp when this metadata object was generated. |

#### Example Response with Metadata

```json
{
  "query": "GCP migration",
  "total_matches": 12,
  "returned_count": 5,
  "page": 1,
  "page_size": 5,
  "total_pages": 3,
  "has_next": true,
  "has_previous": false,
  "results": [...],
  "applied_filters": {...},
  "generated_at": "2026-09-03T15:45:00.000000+00:00",
  "metadata": {
    "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "execution_time_ms": 4.217,
    "returned_count": 5,
    "total_count": 12,
    "page": 1,
    "page_size": 5,
    "cache_hit": true,
    "timestamp": "2026-09-03T15:45:00.000000+00:00"
  }
}
```

---

### 8.2 `X-Request-ID` Response Header

Every HTTP response (including 4xx and 5xx error responses) includes the `X-Request-ID` header:

```
X-Request-ID: f47ac10b-58cc-4372-a567-0e02b2c3d479
```

- The ID is always **generated server-side** using `uuid4()`.
- The ID is **never derived from user input** or any sensitive environment variable.
- API clients can use this header to correlate their request with server-side log entries.
- The middleware attaches the same ID to both the response header and the `metadata.request_id` field in the JSON body.

---

### 8.3 Request ID in Error Responses

For safe 4xx and 5xx responses, the `request_id` is included in the JSON body to enable log correlation:

```json
{
  "detail": "Retrieval data file not found. Run 'python main.py --prepare-retrieval' first.",
  "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

The `request_id` in error responses:
- Is the **same** UUID generated at middleware layer for that HTTP request.
- Is a safe UUID — it never contains, echoes, or reflects any user query text, credentials, or internal paths.

---

### 8.4 Execution Time Measurement

- Measured with `time.perf_counter()` (monotonic wall-clock timer).
- Starts at the beginning of `RetrievalService.query()` (after request ID generation).
- Stops after all filtering, pagination, and metadata assembly.
- Reported in **milliseconds** rounded to 3 decimal places.
- Always `>= 0`. Cache-hit requests still report a small but non-negative execution time for the query dispatch overhead.
- **Not** a substitute for external APM instrumentation; it measures retrieval logic time only.

---

### 8.5 Cache Observability

| `cache_hit` Value | Meaning |
|---|---|
| `false` | Records were loaded from `retrieval_ready_records.json` on disk for this request. |
| `true` | Records were already in the `RetrievalService` in-memory cache from a prior request. |

Cache behavior itself is **unchanged** from Weeks 3–4. Day 7 only adds observability reporting of whether the current request benefited from the cache.

---

### 8.6 Structured Safe Logging

The retrieval query endpoint emits a structured log line for every request containing only safe metadata:

```
retrieval_query request_id=<uuid> endpoint=/api/retrieval/query method=POST
status=200 execution_ms=4.22 results=5 total_matches=12 cache_hit=True page=1 page_size=5
```

**Logged:** `request_id`, HTTP method, endpoint path, HTTP status code, `execution_ms`, result count, `total_matches`, `cache_hit`, `page`, `page_size`.

**Never logged:**
- Query text (`query` / `query_text`)
- API keys or tokens
- Environment variable values
- Database connection strings
- Local filesystem paths
- Python tracebacks

---

### 8.7 Backward Compatibility

The `metadata` field is **additive only**:
- Existing clients that do not read `metadata` are unaffected.
- All pre-existing response fields (`query`, `total_matches`, `returned_count`, `page`, `page_size`, `total_pages`, `has_next`, `has_previous`, `results`, `applied_filters`, `generated_at`) are unchanged.
- Existing error response `detail` messages are unchanged.
- All Day 6 input validation (422 responses) continues to function identically.
