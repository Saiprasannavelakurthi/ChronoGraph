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

from datetime import date, datetime
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
