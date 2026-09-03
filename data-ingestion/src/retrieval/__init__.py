"""
src/retrieval/__init__.py
─────────────────────────
Week 3 & 4 — Temporal Retrieval Preparation & Service (Karkuvel's module).
Week 4 Day 7 — Added RetrievalRequestMetadata export.

Public API:

    from src.retrieval.models import RetrievalRecord, RetrievalRequest, TemporalFilter
    from src.retrieval.models import PipelineExecutionMetadata, RetrievalDataQualityStats
    from src.retrieval.builder import RetrievalRecordBuilder
    from src.retrieval.filter import TemporalFilterEngine
    from src.retrieval.validator import RetrievalOutputValidator, ValidationResult
    from src.retrieval.stats import RetrievalStatsEngine
    from src.retrieval.service import RetrievalService
    from src.retrieval.errors import (
        RetrievalError,
        RetrievalServiceError,
        RetrievalDataError,
        RetrievalDataNotFoundError,
        RetrievalDataFormatError,
        RetrievalDataCorruptedError,
    )

This module does NOT own Neo4j, Cypher, or natural-language-to-query conversion.
It prepares retrieval-ready evidence records, executes filtered/ranked temporal
queries, and exposes structured REST endpoints with high resilience.
"""

from src.retrieval.errors import (
    RetrievalDataCorruptedError,
    RetrievalDataError,
    RetrievalDataFormatError,
    RetrievalDataNotFoundError,
    RetrievalError,
    RetrievalServiceError,
)
from src.retrieval.models import (
    PipelineExecutionMetadata,
    RetrievalDataQualityStats,
    RetrievalHealthResponse,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalRecord,
    RetrievalRequest,
    RetrievalRequestMetadata,
    TemporalFilter,
)
from src.retrieval.builder import RetrievalRecordBuilder
from src.retrieval.filter import TemporalFilterEngine
from src.retrieval.service import RetrievalService
from src.retrieval.validator import RetrievalOutputValidator, ValidationResult
from src.retrieval.stats import RetrievalStatsEngine

__all__ = [
    "PipelineExecutionMetadata",
    "RetrievalDataQualityStats",
    "RetrievalHealthResponse",
    "RetrievalQueryRequest",
    "RetrievalQueryResponse",
    "RetrievalRecord",
    "RetrievalRequest",
    "RetrievalRequestMetadata",
    "TemporalFilter",
    "RetrievalRecordBuilder",
    "TemporalFilterEngine",
    "RetrievalService",
    "RetrievalError",
    "RetrievalServiceError",
    "RetrievalDataError",
    "RetrievalDataNotFoundError",
    "RetrievalDataFormatError",
    "RetrievalDataCorruptedError",
    "RetrievalOutputValidator",
    "ValidationResult",
    "RetrievalStatsEngine",
]
