"""
src/graph_prep/__init__.py
──────────────────────────
Week 2 – Karkuvel's Data Integration & Graph-Ready Data Pipeline.

This module validates, normalizes (entities, relations, timestamps),
and deduplicates extracted triples from Week 1, producing a clean
graph_ready_triples.json for Saiprasanna's Neo4j ingestion module.

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
