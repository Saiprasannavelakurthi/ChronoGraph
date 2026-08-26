"""
src/retrieval/__init__.py
─────────────────────────
Week 3 — Temporal Retrieval Preparation (Karkuvel's module).

Public API:

    from src.retrieval.models import RetrievalRecord, RetrievalRequest, TemporalFilter
    from src.retrieval.models import PipelineExecutionMetadata
    from src.retrieval.builder import RetrievalRecordBuilder
    from src.retrieval.filter import TemporalFilterEngine

This module does NOT own Neo4j, Cypher, or natural-language-to-query conversion.
It prepares retrieval-ready evidence records and lightweight filter schemas so the
downstream Temporal Routing / GraphRAG engine can perform chronological retrieval.
"""

from src.retrieval.models import (
    PipelineExecutionMetadata,
    RetrievalRecord,
    RetrievalRequest,
    TemporalFilter,
)
from src.retrieval.builder import RetrievalRecordBuilder
from src.retrieval.filter import TemporalFilterEngine

__all__ = [
    "PipelineExecutionMetadata",
    "RetrievalRecord",
    "RetrievalRequest",
    "TemporalFilter",
    "RetrievalRecordBuilder",
    "TemporalFilterEngine",
]
