"""
src/graph_prep/__init__.py
──────────────────────────
Data Integration & Graph-Ready Data Pipeline.

This module validates, normalizes (entities, relations, timestamps),
and deduplicates extracted triples, producing a clean
graph_ready_triples.json for downstream graph database ingestion.

Public API
──────────
    from src.graph_prep.validator import TripleValidator, ValidationReport
    from src.graph_prep.normalizer import EntityNormalizer, RelationNormalizer, TimestampNormalizer
    from src.graph_prep.deduplicator import TripleDeduplicator, DeduplicationReport
    from src.graph_prep.pipeline import GraphPrepPipeline
"""

from src.graph_prep.validator import TripleValidator, ValidationReport
from src.graph_prep.normalizer import EntityNormalizer, RelationNormalizer, TimestampNormalizer
from src.graph_prep.deduplicator import TripleDeduplicator, DeduplicationReport
from src.graph_prep.pipeline import GraphPrepPipeline

__all__ = [
    "TripleValidator",
    "ValidationReport",
    "EntityNormalizer",
    "RelationNormalizer",
    "TimestampNormalizer",
    "TripleDeduplicator",
    "DeduplicationReport",
    "GraphPrepPipeline",
]
