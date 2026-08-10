"""
src/schemas/graph.py
────────────────────
Pydantic v2 models for ChronoGraph Week 1.

All data that flows through the pipeline is typed via these models.
The Triple model is the primary Week 2 contract – every field is required
and documented so the Neo4j ingestion layer can consume it without guessing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────


class DataSource(str, Enum):
    """Supported data-source types for enterprise forensics."""

    SLACK = "slack"
    GITHUB = "github"
    JIRA = "jira"


class ExtractionMode(str, Enum):
    """Which extraction backend produced a triple."""

    LLM_GROQ = "llm_groq"
    LLM_OLLAMA = "llm_ollama"
    LLM_OPENAI = "llm_openai"
    FALLBACK = "fallback"
    MOCK = "mock"


class EntityType(str, Enum):
    """High-level entity categories used across the forensics graph."""

    PERSON = "Person"
    TECHNOLOGY = "Technology"
    PROJECT = "Project"
    SERVICE = "Service"
    DATABASE = "Database"
    ORGANIZATION = "Organization"
    TEAM = "Team"
    ARCHITECTURE = "Architecture"
    ISSUE = "Issue"
    OTHER = "Other"
    PROBLEM = "Problem"
    ARCHITECTURE_DECISION = "ArchitectureDecision"
    UNKNOWN = "Unknown"


class RelationType(str, Enum):
    """Known relation types extracted from enterprise communications."""

    ADVOCATED_FOR = "ADVOCATED_FOR"
    ARGUED_AGAINST = "ARGUED_AGAINST"
    COMMITTED_CODE = "COMMITTED_CODE"
    REVIEWED = "REVIEWED"
    ASSIGNED_TO = "ASSIGNED_TO"
    MIGRATED_TO = "MIGRATED_TO"
    RAISED_CONCERN = "RAISED_CONCERN"
    DECIDED = "DECIDED"
    IMPLEMENTED = "IMPLEMENTED"
    REPORTED_BUG = "REPORTED_BUG"
    FIXED = "FIXED"
    APPROVED = "APPROVED"
    BLOCKED_BY = "BLOCKED_BY"
    RELATED_TO = "RELATED_TO"
    DEPRECATED = "DEPRECATED"
    ENROLLED_IN = "ENROLLED_IN"
    UNKNOWN = "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# Raw Event  (output of data loaders)
# ─────────────────────────────────────────────────────────────────────────────


class RawEvent(BaseModel):
    """
    A normalised, source-agnostic representation of a single enterprise event.

    Every loader converts its native format (Slack message, GitHub commit,
    Jira comment, etc.) into a RawEvent before the preprocessing pipeline
    takes over.
    """

    # Stable identifier that survives across pipeline re-runs
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this event.",
    )
    source: DataSource = Field(description="Which system this event came from.")
    source_id: str = Field(
        description="The native ID from the source system (e.g. slack_001, github_pr_001)."
    )
    author: str = Field(description="Username / identifier of the event author.")
    content: str = Field(description="Full text content of the event.")
    timestamp: datetime = Field(description="When the event occurred (UTC).")

    # Optional contextual fields – populated when available
    channel: Optional[str] = Field(
        default=None,
        description="Slack channel name or GitHub repository or Jira project key.",
    )
    thread_id: Optional[str] = Field(
        default=None, description="ID of the parent thread/PR/ticket."
    )
    title: Optional[str] = Field(
        default=None, description="Title of the parent PR, ticket, or thread."
    )
    labels: List[str] = Field(
        default_factory=list, description="Tags/labels attached to the event."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific extra fields preserved for downstream use.",
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be empty")
        return v

    @field_validator("author")
    @classmethod
    def author_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("author must not be empty")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Entity  (a node in the future graph)
# ─────────────────────────────────────────────────────────────────────────────


class Entity(BaseModel):
    """
    Represents a single node in the temporal knowledge graph.

    Entities are extracted from RawEvents by the LlamaIndex pipeline.
    In Week 2 each Entity becomes a Neo4j node.
    """

    name: str = Field(description="Canonical name of the entity.")
    entity_type: EntityType = Field(
        default=EntityType.UNKNOWN,
        description="Semantic category of the entity.",
    )
    aliases: List[str] = Field(
        default_factory=list,
        description="Alternative names / identifiers for this entity.",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("entity name must not be empty")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Relationship  (an edge between two entities)
# ─────────────────────────────────────────────────────────────────────────────


class Relationship(BaseModel):
    """
    A directed, labelled relationship between two entities.

    In Week 2 this becomes a Neo4j relationship between two Node objects.
    """

    relation_type: str = Field(
        description="Relationship label (e.g. ADVOCATED_FOR, COMMITTED_CODE)."
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional properties on the relationship (e.g. PR number).",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Triple  (the primary Week 2 contract)
# ─────────────────────────────────────────────────────────────────────────────


class Triple(BaseModel):
    """
    An Entity → [RELATION] → Entity triple with temporal and provenance metadata.

    This is the primary output of Week 1 and the primary input for Week 2
    Neo4j ingestion.  Every field is documented so the Week 2 team can
    consume the file without ambiguity.

    Example JSON::

        {
            "subject":    "arun_sharma",
            "relation":   "ADVOCATED_FOR",
            "object":     "GCP",
            "timestamp":  "2023-03-15T10:30:00",
            "source":     "slack",
            "source_id":  "slack_001",
            "confidence": 0.92,
            "evidence":   "Arun suggested moving our services to GCP."
        }
    """

    # ── Core triple ───────────────────────────────────────────────────────────
    subject: str = Field(description="Name of the subject entity.")
    subject_type: EntityType = Field(
        default=EntityType.UNKNOWN,
        description="Semantic type of the subject entity.",
    )
    relation: str = Field(
        description="Directed relationship label (ALL_CAPS_SNAKE_CASE recommended)."
    )
    object: str = Field(description="Name of the object entity.")
    object_type: EntityType = Field(
        default=EntityType.UNKNOWN,
        description="Semantic type of the object entity.",
    )

    # ── Temporal ──────────────────────────────────────────────────────────────
    timestamp: datetime = Field(
        description="When this relationship occurred (from the source event)."
    )

    # ── Provenance ────────────────────────────────────────────────────────────
    source: DataSource = Field(description="Which system the evidence came from.")
    source_id: str = Field(
        description="Native event ID from the source system."
    )
    evidence: str = Field(
        description="The verbatim sentence(s) that support this triple."
    )

    # ── Quality ───────────────────────────────────────────────────────────────
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Extraction confidence score in [0.0, 1.0].",
    )
    extraction_mode: ExtractionMode = Field(
        default=ExtractionMode.FALLBACK,
        description="Which extraction backend produced this triple.",
    )

    # ── Optional ──────────────────────────────────────────────────────────────
    triple_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable identifier for this triple.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra fields for extensibility (Week 2+ use).",
    )

    @field_validator("subject", "object", "relation", "evidence")
    @classmethod
    def field_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("field must not be empty")
        return v

    @field_validator("relation")
    @classmethod
    def relation_uppercase(cls, v: str) -> str:
        """Normalise relation labels to ALL_CAPS_SNAKE_CASE."""
        return v.upper().replace(" ", "_")

    def to_neo4j_dict(self) -> Dict[str, Any]:
        """
        Serialize to a dict shaped for Week 2 Neo4j ingestion.

        Returns a flat dict with explicit typing hints so Cypher
        ``CREATE`` / ``MERGE`` statements can consume it directly.
        """
        return {
            "triple_id": self.triple_id,
            "subject": self.subject,
            "subject_type": self.subject_type.value,
            "relation": self.relation,
            "object": self.object,
            "object_type": self.object_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source.value,
            "source_id": self.source_id,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "extraction_mode": self.extraction_mode.value,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Extraction Result  (wrapper for a batch of triples from one event)
# ─────────────────────────────────────────────────────────────────────────────


class ExtractionResult(BaseModel):
    """Container for all triples extracted from a single RawEvent."""

    event_id: str = Field(description="ID of the source RawEvent.")
    source_id: str = Field(description="Native source ID of the event.")
    source: DataSource
    extraction_mode: ExtractionMode
    triples: List[Triple] = Field(default_factory=list)
    error: Optional[str] = Field(
        default=None,
        description="Error message if extraction failed for this event.",
    )

    @property
    def succeeded(self) -> bool:
        return self.error is None and len(self.triples) > 0
