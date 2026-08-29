"""
src/retrieval/models.py
────────────────────────
Week 3 — Pydantic models for Temporal Retrieval Preparation.

Classes
───────
  RetrievalRecord   — A single retrieval-ready evidence record derived from a
                      graph-ready triple, preserving all provenance and temporal
                      metadata needed for citation-backed answer generation.

  TemporalFilter    — Value-object encapsulating chronological filter parameters
                      (exact date, range, before, after).  Downstream Temporal
                      Routing applies this to retrieve relevant evidence.

  RetrievalRequest  — Lightweight filter schema that packages a natural-language
                      query together with entity hints, relation hints, temporal
                      boundaries, source filters, limit, and ordering preference.
                      This module does NOT convert NL to Cypher — that belongs to
                      the downstream graph-retrieval / neo4j-temporal module.

Data Contract
─────────────
  See docs/RETRIEVAL_DATA_CONTRACT.md for the full field reference.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────


class SortOrder(str, Enum):
    """Chronological sort direction for retrieval results."""

    ASC = "asc"    # Earliest first
    DESC = "desc"  # Latest first


class TemporalFilterMode(str, Enum):
    """Which temporal constraint is active in a TemporalFilter."""

    NONE = "none"
    EXACT = "exact"
    RANGE = "range"
    BEFORE = "before"
    AFTER = "after"


# ─────────────────────────────────────────────────────────────────────────────
# PipelineExecutionMetadata
# ─────────────────────────────────────────────────────────────────────────────


class PipelineExecutionMetadata(BaseModel):
    """
    Execution metadata for the Week 3 Temporal Retrieval Preparation pipeline.

    Written to a *separate* summary file (`retrieval_prep_summary.json`) so
    that the `retrieval_ready_records.json` data contract is not modified.

    Fields
    ──────
    pipeline_name   : Human-readable name of the pipeline step.
    input_source    : Absolute path (as string) of the input file consumed.
    total_records   : Number of graph-ready triples read from the input.
    records_built   : Number of RetrievalRecord objects successfully created.
    skipped_records : Number of triples that were rejected / failed validation.
    generated_at    : UTC ISO-8601 timestamp of when the run completed.
    status          : "success" when skipped_records == 0, otherwise "partial".
    """

    pipeline_name: str = Field(
        default="Week 3 — Temporal Retrieval Preparation",
        description="Human-readable name of the pipeline.",
    )
    input_source: str = Field(
        description="Absolute path to the input graph_ready_triples.json consumed by this run.",
    )
    total_records: int = Field(
        ge=0,
        description="Total number of graph-ready triples read from the input file.",
    )
    records_built: int = Field(
        ge=0,
        description="Number of RetrievalRecord objects successfully built.",
    )
    skipped_records: int = Field(
        ge=0,
        description="Number of triples skipped due to validation or build errors.",
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO-8601 timestamp of when this summary was generated.",
    )
    status: str = Field(
        default="success",
        description=('"success" when no records were skipped; "partial" otherwise.'),
    )

    @model_validator(mode="after")
    def _derive_status(self) -> "PipelineExecutionMetadata":
        """Automatically set status based on skipped_records."""
        self.status = "success" if self.skipped_records == 0 else "partial"
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain JSON-compatible dict."""
        return {
            "pipeline_name": self.pipeline_name,
            "input_source": self.input_source,
            "total_records": self.total_records,
            "records_built": self.records_built,
            "skipped_records": self.skipped_records,
            "generated_at": self.generated_at,
            "status": self.status,
        }


# ─────────────────────────────────────────────────────────────────────────────
# RetrievalDataQualityStats
# ─────────────────────────────────────────────────────────────────────────────


class RetrievalDataQualityStats(BaseModel):
    """
    Data quality and coverage statistics computed from retrieval_ready_records.json.

    Produced by RetrievalStatsEngine and written to
    retrieval_quality_stats.json alongside the main records file.

    Fields
    ──────
    total_records               : Total number of records in the file.
    unique_entities             : Count of distinct entity values (subjects + objects,
                                  both canonical and display names deduplicated).
    unique_relations            : Count of distinct relation type labels.
    records_with_temporal_data  : Records whose timestamp and event_date are
                                  both present and parseable.
    records_without_temporal_data : Records where temporal data is missing or invalid.
    earliest_timestamp          : ISO-8601 string of the earliest event_date found,
                                  or None if no records exist.
    latest_timestamp            : ISO-8601 string of the latest event_date found,
                                  or None if no records exist.
    source_breakdown            : Per-source record counts {'slack': N, 'github': N, 'jira': N}.
    average_confidence          : Mean extraction confidence score, or None if no records.
    records_with_source_url     : Records that carry a non-null source_url.
    generated_at                : UTC ISO-8601 timestamp of when these stats were computed.
    """

    total_records: int = Field(ge=0, description="Total records in retrieval_ready_records.json.")
    unique_entities: int = Field(ge=0, description="Distinct entity values across all records.")
    unique_relations: int = Field(ge=0, description="Distinct relation type labels across all records.")
    records_with_temporal_data: int = Field(
        ge=0,
        description="Records with valid, parseable timestamp and event_date.",
    )
    records_without_temporal_data: int = Field(
        ge=0,
        description="Records where temporal metadata is missing or unparseable.",
    )
    earliest_timestamp: Optional[str] = Field(
        default=None,
        description="Earliest event_date (YYYY-MM-DD) found, or None if no records.",
    )
    latest_timestamp: Optional[str] = Field(
        default=None,
        description="Latest event_date (YYYY-MM-DD) found, or None if no records.",
    )
    source_breakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="Record count per source system (e.g. {'slack': 51, 'github': 40, 'jira': 51}).",
    )
    average_confidence: Optional[float] = Field(
        default=None,
        description="Mean confidence score across all records, or None if no records.",
    )
    records_with_source_url: int = Field(
        ge=0,
        description="Number of records that carry a non-null source_url.",
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO-8601 timestamp of when this stats report was generated.",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain JSON-compatible dict."""
        return {
            "total_records": self.total_records,
            "unique_entities": self.unique_entities,
            "unique_relations": self.unique_relations,
            "records_with_temporal_data": self.records_with_temporal_data,
            "records_without_temporal_data": self.records_without_temporal_data,
            "earliest_timestamp": self.earliest_timestamp,
            "latest_timestamp": self.latest_timestamp,
            "source_breakdown": self.source_breakdown,
            "average_confidence": self.average_confidence,
            "records_with_source_url": self.records_with_source_url,
            "generated_at": self.generated_at,
        }




# ─────────────────────────────────────────────────────────────────────────────
# TemporalFilter
# ─────────────────────────────────────────────────────────────────────────────


class TemporalFilter(BaseModel):
    """
    Chronological filter parameters for retrieval.

    Only one mode is active at a time; the active mode is determined by
    whichever fields are set.  Rules (checked in order):

        1.  exact_date            → mode = EXACT
        2.  start_date + end_date → mode = RANGE
        3.  before_date only      → mode = BEFORE
        4.  after_date only       → mode = AFTER
        5.  (none set)            → mode = NONE  (no temporal filtering)

    All date values are compared against the *date part* of the triple's
    UTC ISO-8601 timestamp.
    """

    exact_date: Optional[date] = Field(
        default=None,
        description="Match triples whose timestamp falls on this exact calendar date (UTC).",
    )
    start_date: Optional[date] = Field(
        default=None,
        description="Lower bound of the date range (inclusive).",
    )
    end_date: Optional[date] = Field(
        default=None,
        description="Upper bound of the date range (inclusive).",
    )
    before_date: Optional[date] = Field(
        default=None,
        description="Return only triples strictly before this date.",
    )
    after_date: Optional[date] = Field(
        default=None,
        description="Return only triples strictly after this date.",
    )

    @model_validator(mode="after")
    def validate_range_consistency(self) -> "TemporalFilter":
        """Ensure start_date <= end_date when both are provided."""
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValueError(
                    f"start_date ({self.start_date}) must not be after "
                    f"end_date ({self.end_date})."
                )
        return self

    @property
    def mode(self) -> TemporalFilterMode:
        """Determine the active filter mode from the set fields."""
        if self.exact_date is not None:
            return TemporalFilterMode.EXACT
        if self.start_date is not None or self.end_date is not None:
            return TemporalFilterMode.RANGE
        if self.before_date is not None:
            return TemporalFilterMode.BEFORE
        if self.after_date is not None:
            return TemporalFilterMode.AFTER
        return TemporalFilterMode.NONE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (dates as ISO strings)."""
        return {
            "mode": self.mode.value,
            "exact_date": self.exact_date.isoformat() if self.exact_date else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "before_date": self.before_date.isoformat() if self.before_date else None,
            "after_date": self.after_date.isoformat() if self.after_date else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# RetrievalRecord
# ─────────────────────────────────────────────────────────────────────────────


class RetrievalRecord(BaseModel):
    """
    A single retrieval-ready evidence record.

    Derived from a graph-ready triple (Week 2 output) by the
    RetrievalRecordBuilder.  Every required field is preserved from the
    original triple.  Optional fields are set to None when the upstream
    triple does not carry the information — no data is fabricated.

    This record is the primary unit consumed by the downstream Temporal
    Routing / GraphRAG engine for chronological retrieval, evidence ranking,
    and citation generation.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    record_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Stable UUID for this retrieval record (same as triple_id if derived from one).",
    )
    triple_id: str = Field(
        description="The original triple UUID from the graph-ready data contract.",
    )

    # ── Core triple fields ────────────────────────────────────────────────────
    subject: str = Field(description="Canonical snake_case subject entity name.")
    subject_display: Optional[str] = Field(
        default=None,
        description="Human-readable subject display name.",
    )
    subject_type: Optional[str] = Field(
        default=None,
        description="Entity type for the subject (e.g. 'Person', 'Technology').",
    )
    relation: str = Field(description="Normalized relation label (UPPER_SNAKE_CASE).")
    object: str = Field(description="Canonical snake_case object entity name.")
    object_display: Optional[str] = Field(
        default=None,
        description="Human-readable object display name.",
    )
    object_type: Optional[str] = Field(
        default=None,
        description="Entity type for the object.",
    )

    # ── Temporal ──────────────────────────────────────────────────────────────
    timestamp: str = Field(
        description="UTC ISO-8601 timestamp from the source event.",
    )
    event_date: date = Field(
        description="Calendar date (UTC) extracted from the timestamp — used for chronological indexing.",
    )

    # ── Provenance / Evidence ─────────────────────────────────────────────────
    source: str = Field(
        description="Source system: 'slack', 'github', or 'jira'.",
    )
    source_id: str = Field(
        description="Native event ID from the source system (e.g. 'slack_001', 'github_pr_007').",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="URL to the source artifact, if available in metadata.",
    )
    evidence: str = Field(
        description="Verbatim supporting sentence(s) from the original event.",
    )

    # ── Quality ───────────────────────────────────────────────────────────────
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Extraction confidence score in [0.0, 1.0].",
    )
    extraction_mode: Optional[str] = Field(
        default=None,
        description="Extraction backend that produced this triple.",
    )

    # ── Extensibility ─────────────────────────────────────────────────────────
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Pass-through metadata from the graph-ready triple.",
    )

    @field_validator("subject", "relation", "object", "evidence", "source", "source_id", "triple_id")
    @classmethod
    def field_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("field must not be empty")
        return v

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_iso(cls, v: str) -> str:
        """Validate that timestamp is parseable as ISO-8601."""
        try:
            datetime.fromisoformat(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"timestamp must be a valid ISO-8601 string, got: {v!r}") from exc
        return v

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for JSON output."""
        d = self.model_dump()
        d["event_date"] = self.event_date.isoformat()
        return d

    @property
    def source_label(self) -> str:
        """
        Human-readable source label for citation generation.

        Examples:
            slack  → "Slack message slack_001"
            github → "GitHub PR github_pr_007"
            jira   → "Jira ticket jira_001"
        """
        _labels = {
            "slack": "Slack message",
            "github": "GitHub PR",
            "jira": "Jira ticket",
        }
        label = _labels.get(self.source.lower(), self.source.capitalize())
        return f"{label} {self.source_id}"


# ─────────────────────────────────────────────────────────────────────────────
# RetrievalRequest
# ─────────────────────────────────────────────────────────────────────────────


class RetrievalRequest(BaseModel):
    """
    Lightweight filter schema for downstream Temporal Routing / GraphRAG engine.

    This is the *input contract* — the data-ingestion module prepares and
    validates this structure; it does NOT execute the retrieval itself.
    The downstream neo4j-temporal module (or equivalent routing layer) is
    responsible for converting this into a Cypher query or vector search.

    Usage Example (Python)
    ─────────────────────
        req = RetrievalRequest(
            query_text="When did Arun advocate for GCP migration?",
            entities=["arun_sharma", "gcp"],
            relation_hints=["ADVOCATED_FOR"],
            temporal_filter=TemporalFilter(start_date=date(2023, 1, 1)),
            sources=["slack"],
            limit=10,
            sort_order=SortOrder.ASC,
        )
        payload = req.to_dict()
        # → pass to downstream routing engine
    """

    # ── Query ─────────────────────────────────────────────────────────────────
    query_text: Optional[str] = Field(
        default=None,
        description="Natural-language question or search string (for downstream NL routing).",
    )

    # ── Entity / Relation hints ───────────────────────────────────────────────
    entities: List[str] = Field(
        default_factory=list,
        description="Entity names to filter by (canonical snake_case or display name).",
    )
    relation_hints: List[str] = Field(
        default_factory=list,
        description="Relation labels to filter by (UPPER_SNAKE_CASE preferred).",
    )

    # ── Temporal constraint ───────────────────────────────────────────────────
    temporal_filter: TemporalFilter = Field(
        default_factory=TemporalFilter,
        description="Chronological filter parameters.",
    )

    # ── Source filters ────────────────────────────────────────────────────────
    sources: List[str] = Field(
        default_factory=list,
        description="Restrict results to these source systems ('slack', 'github', 'jira'). Empty = all.",
    )

    # ── Result controls ───────────────────────────────────────────────────────
    limit: int = Field(
        default=20,
        ge=1,
        le=1000,
        description="Maximum number of retrieval records to return.",
    )
    sort_order: SortOrder = Field(
        default=SortOrder.ASC,
        description="Chronological sort direction for results.",
    )

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v: List[str]) -> List[str]:
        """Normalise source names to lowercase and validate known values."""
        valid = {"slack", "github", "jira"}
        normalised = [s.lower().strip() for s in v]
        unknown = set(normalised) - valid
        if unknown:
            raise ValueError(f"Unknown source(s): {unknown}. Valid: {valid}")
        return normalised

    @field_validator("entities", "relation_hints")
    @classmethod
    def strip_list_strings(cls, v: List[str]) -> List[str]:
        return [item.strip() for item in v if item.strip()]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict for downstream routing consumption."""
        return {
            "query_text": self.query_text,
            "entities": self.entities,
            "relation_hints": self.relation_hints,
            "temporal_filter": self.temporal_filter.to_dict(),
            "sources": self.sources,
            "limit": self.limit,
            "sort_order": self.sort_order.value,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Week 4 API Models
# ─────────────────────────────────────────────────────────────────────────────


class RetrievalQueryRequest(BaseModel):
    """
    Week 4 API Request model for temporal retrieval query endpoint.

    Provides a clean, intuitive REST API interface that is normalized
    into the existing Week 3 RetrievalRequest before filtering.
    """

    query: Optional[str] = Field(
        default=None,
        description="Natural-language question or search query string.",
    )
    query_text: Optional[str] = Field(
        default=None,
        description="Alias for query.",
    )
    entity_hints: List[str] = Field(
        default_factory=list,
        description="Entity names or hints to filter by (canonical snake_case or display name).",
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Alias for entity_hints.",
    )
    relation_hints: List[str] = Field(
        default_factory=list,
        description="Relation labels to filter by (UPPER_SNAKE_CASE preferred).",
    )
    sources: List[str] = Field(
        default_factory=list,
        description="Restrict results to these source systems ('slack', 'github', 'jira'). Empty = all.",
    )
    exact_date: Optional[date] = Field(
        default=None,
        description="Match records whose timestamp falls on this exact calendar date (YYYY-MM-DD).",
    )
    start_date: Optional[date] = Field(
        default=None,
        description="Lower bound of date range (inclusive, YYYY-MM-DD).",
    )
    end_date: Optional[date] = Field(
        default=None,
        description="Upper bound of date range (inclusive, YYYY-MM-DD).",
    )
    before_date: Optional[date] = Field(
        default=None,
        description="Return only records strictly before this date (YYYY-MM-DD).",
    )
    after_date: Optional[date] = Field(
        default=None,
        description="Return only records strictly after this date (YYYY-MM-DD).",
    )
    sort_order: SortOrder = Field(
        default=SortOrder.ASC,
        description="Chronological sort direction ('asc' for earliest first, 'desc' for latest first).",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=1000,
        description="Maximum number of retrieval records to return (1-1000). Backward compatibility alias.",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number for pagination (1-indexed, default=1).",
    )
    page_size: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Number of records per page (1-100). If omitted, defaults to limit (or 20).",
    )

    @model_validator(mode="after")
    def validate_date_and_pagination(self) -> "RetrievalQueryRequest":
        """Validate date range consistency and resolve page_size/limit synchronization."""
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValueError(
                    f"start_date ({self.start_date}) must not be after end_date ({self.end_date})."
                )

        # Synchronize page_size and limit for clean pagination and backward compatibility:
        if self.page_size is None:
            # page_size omitted -> fallback to limit (capped at 100)
            self.page_size = min(self.limit, 100)
        else:
            # page_size explicitly provided -> sync limit to page_size
            self.limit = self.page_size

        return self

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v: List[str]) -> List[str]:
        """Normalise source names to lowercase and validate known values."""
        valid = {"slack", "github", "jira"}
        normalised = [s.lower().strip() for s in v if s.strip()]
        unknown = set(normalised) - valid
        if unknown:
            raise ValueError(f"Unknown source(s): {unknown}. Valid: {valid}")
        return normalised

    @field_validator("entity_hints", "entities", "relation_hints")
    @classmethod
    def strip_list_strings(cls, v: List[str]) -> List[str]:
        return [item.strip() for item in v if item.strip()]

    def to_retrieval_request(self) -> RetrievalRequest:
        """
        Convert this API request into the standard Week 3 RetrievalRequest.

        Maintains complete compatibility with TemporalFilterEngine.
        """
        # Resolve query text
        q_text = self.query or self.query_text

        # Combine entity hints and entities deduplicating while preserving order
        combined_entities: List[str] = []
        for e in list(self.entity_hints) + list(self.entities):
            if e not in combined_entities:
                combined_entities.append(e)

        temporal_filter = TemporalFilter(
            exact_date=self.exact_date,
            start_date=self.start_date,
            end_date=self.end_date,
            before_date=self.before_date,
            after_date=self.after_date,
        )

        return RetrievalRequest(
            query_text=q_text,
            entities=combined_entities,
            relation_hints=self.relation_hints,
            temporal_filter=temporal_filter,
            sources=self.sources,
            limit=self.limit,
            sort_order=self.sort_order,
        )


class RetrievalQueryResponse(BaseModel):
    """
    Week 4 API Response model returning structured temporal retrieval results.
    """

    query: Optional[str] = Field(
        default=None,
        description="Echo of the input query text.",
    )
    total_matches: int = Field(
        ge=0,
        description="Total number of matching evidence records before limit was applied.",
    )
    returned_count: int = Field(
        ge=0,
        description="Number of records returned in this response (<= page_size).",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Current 1-based page number.",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        description="Requested number of records per page.",
    )
    total_pages: int = Field(
        default=0,
        ge=0,
        description="Total number of pages available.",
    )
    has_next: bool = Field(
        default=False,
        description="True if a subsequent page of results exists.",
    )
    has_previous: bool = Field(
        default=False,
        description="True if a previous page of results exists.",
    )
    results: List[RetrievalRecord] = Field(
        default_factory=list,
        description="Chronologically sorted evidence records with complete provenance.",
    )
    applied_filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of all filters applied to produce this result.",
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO-8601 timestamp when this response was generated.",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain JSON-compatible dictionary."""
        return {
            "query": self.query,
            "total_matches": self.total_matches,
            "returned_count": self.returned_count,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_previous": self.has_previous,
            "results": [r.to_dict() for r in self.results],
            "applied_filters": self.applied_filters,
            "generated_at": self.generated_at,
        }


class RetrievalHealthResponse(BaseModel):
    """
    Week 4 Health response schema for GET /api/health.
    """

    status: str = Field(default="ok", description="Service health status ('ok').")
    service: str = Field(default="ChronoGraph Retrieval API", description="Service identifier.")
    version: str = Field(default="1.0.0", description="API version.")
    retrieval_data_available: bool = Field(
        description="True if retrieval_ready_records.json is present on disk.",
    )
    retrieval_records_count: Optional[int] = Field(
        default=None,
        description="Total records available in retrieval_ready_records.json, or None if unavailable.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO-8601 timestamp.",
    )

