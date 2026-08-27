"""
src/retrieval/__init__.py
─────────────────────────
Week 3 — Temporal Retrieval Preparation (Karkuvel's module).

Public API:

    from src.retrieval.models import RetrievalRecord, RetrievalRequest, TemporalFilter
    from src.retrieval.models import PipelineExecutionMetadata, RetrievalDataQualityStats
    from src.retrieval.builder import RetrievalRecordBuilder
    from src.retrieval.filter import TemporalFilterEngine
    from src.retrieval.validator import RetrievalOutputValidator, ValidationResult
    from src.retrieval.stats import RetrievalStatsEngine

This module does NOT own Neo4j, Cypher, or natural-language-to-query conversion.
It prepares retrieval-ready evidence records and lightweight filter schemas so the
downstream Temporal Routing / GraphRAG engine can perform chronological retrieval.
"""

from src.retrieval.models import (
    PipelineExecutionMetadata,
    RetrievalDataQualityStats,
    RetrievalRecord,
    RetrievalRequest,
    TemporalFilter,
)
from src.retrieval.builder import RetrievalRecordBuilder
from src.retrieval.filter import TemporalFilterEngine
from src.retrieval.validator import RetrievalOutputValidator, ValidationResult
from src.retrieval.stats import RetrievalStatsEngine

__all__ = [
    "PipelineExecutionMetadata",
    "RetrievalDataQualityStats",
    "RetrievalRecord",
    "RetrievalRequest",
    "TemporalFilter",
    "RetrievalRecordBuilder",
    "TemporalFilterEngine",
    "RetrievalOutputValidator",
    "ValidationResult",
    "RetrievalStatsEngine",
]

