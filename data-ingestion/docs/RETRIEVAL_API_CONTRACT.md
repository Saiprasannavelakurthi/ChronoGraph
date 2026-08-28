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
| `limit` | `integer (1 - 1000)` | No | `20` | Maximum number of records to return. |

#### Example Request

```json
{
  "query": "What decisions were made regarding GCP after April 2023?",
  "entity_hints": ["gcp", "arun_sharma"],
  "relation_hints": ["MIGRATED_TO", "ADVOCATED_FOR"],
  "sources": ["slack", "github"],
  "after_date": "2023-04-01",
  "sort_order": "asc",
  "limit": 5
}
```

#### Response Schema (`RetrievalQueryResponse` — `200 OK`)

```json
{
  "query": "What decisions were made regarding GCP after April 2023?",
  "total_matches": 12,
  "returned_count": 5,
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
    "limit": 5
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

The filtering engine evaluates constraints strictly in this deterministic sequence:

1. **Source System Filtering**: Records must match one of the allowed sources in `sources`.
2. **Entity Filtering**: Matches against `subject`, `object`, `subject_display`, or `object_display` (case-insensitive).
3. **Relation Filtering**: Matches normalized `relation` label against `relation_hints`.
4. **Temporal Filtering**:
   - `exact_date`: Matches `event_date == exact_date`.
   - `start_date` / `end_date`: Inclusive boundary check (`start_date <= event_date <= end_date`).
   - `before_date`: Strict upper bound (`event_date < before_date`).
   - `after_date`: Strict lower bound (`event_date > after_date`).
5. **Total Matches Calculation**: Count of all records passing steps 1–4.
6. **Chronological Sorting**: Sorted on `(event_date, timestamp)` in ASC or DESC order.
7. **Limit / Pagination**: Sliced to `[:limit]`.

---

## 5. Provenance Guarantees

Every result item in `results` contains the complete audit trail:
- `record_id` & `triple_id`: Deterministic UUID tracking the evidence back to its graph extraction triple.
- `source` & `source_id`: Source platform and native ID (e.g. `slack_001`, `github_pr_007`, `jira_001`).
- `source_url`: Permalinks / web URLs when available from source metadata.
- `evidence`: Verbatim text snippet from which the triple and temporal relation were extracted.
- `timestamp` & `event_date`: Verified UTC ISO-8601 timestamp and calendar date.

---

## 6. Error Handling

| HTTP Status | Condition | Example Response Body |
|---|---|---|
| `404 Not Found` | `retrieval_ready_records.json` missing on disk | `{"detail": "Retrieval data file not found at ... Run 'python main.py --prepare-retrieval' first."}` |
| `422 Unprocessable Entity` | Invalid request parameters (e.g. `start_date > end_date`, unknown source name, `limit < 1`) | `{"detail": [{"loc": ["body", "start_date"], "msg": "start_date must not be after end_date", "type": "value_error"}]}` |
| `500 Internal Server Error` | File corruption or server error | `{"detail": "Retrieval data file is corrupted or cannot be parsed."}` |
