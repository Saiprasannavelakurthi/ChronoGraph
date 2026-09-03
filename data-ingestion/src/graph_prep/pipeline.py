"""
src/graph_prep/pipeline.py
───────────────────────────
Graph-Ready Data Pipeline.

Orchestrates the full graph preparation flow:

    extracted_triples.json
          ↓
    1. Validate          (TripleValidator)
          ↓
    2. Normalize         (EntityNormalizer + RelationNormalizer + TimestampNormalizer)
          ↓
    3. Deduplicate       (TripleDeduplicator)
          ↓
    4. Write outputs:
          data/processed/graph_ready_triples.json
          data/processed/graph_prep_summary.json

Output contract
───────────────
Each record in graph_ready_triples.json contains:

    {
        "triple_id":        str   — stable UUID
        "subject":          str   — canonical_name (snake_case)
        "subject_display":  str   — original display name
        "subject_type":     str   — EntityType value
        "relation":         str   — UPPERCASE_SNAKE_CASE
        "object":           str   — canonical_name (snake_case)
        "object_display":   str   — original display name
        "object_type":      str   — EntityType value
        "timestamp":        str   — UTC ISO-8601 ("YYYY-MM-DDTHH:MM:SS+00:00")
        "source":           str   — "slack" | "github" | "jira"
        "source_id":        str   — native source event ID
        "evidence":         str   — verbatim supporting sentence(s)
        "confidence":       float — [0.0, 1.0]
        "extraction_mode":  str   — ExtractionMode value
        "metadata":         dict  — pass-through from extractor (may be empty)
    }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.graph_prep.deduplicator import DeduplicationReport, TripleDeduplicator
from src.graph_prep.normalizer import (
    EntityNormalizer,
    RelationNormalizer,
    TimestampNormalizer,
)
from src.graph_prep.validator import TripleValidator, ValidationReport

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────


class GraphPrepPipeline:
    """
    End-to-end graph preparation pipeline.

    Parameters
    ──────────
    input_path  : Path to extracted_triples.json.
    output_path : Destination for graph_ready_triples.json.
    summary_path: Destination for graph_prep_summary.json.

    Usage
    ─────
        pipeline = GraphPrepPipeline(
            input_path  = Path("data/processed/extracted_triples.json"),
            output_path = Path("data/processed/graph_ready_triples.json"),
            summary_path= Path("data/processed/graph_prep_summary.json"),
        )
        result = pipeline.run()
        # result["graph_ready_count"]  → int
        # result["summary"]            → dict
    """

    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        summary_path: Path,
    ) -> None:
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.summary_path = Path(summary_path)

        self._validator = TripleValidator()
        self._entity_norm = EntityNormalizer()
        self._relation_norm = RelationNormalizer()
        self._ts_norm = TimestampNormalizer()
        self._deduplicator = TripleDeduplicator()

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        """
        Execute the full pipeline and write outputs.

        Returns
        ───────
        A dict with:
            graph_ready_count  : int
            validation_report  : ValidationReport
            dedup_report       : DeduplicationReport
            summary            : dict (same content as graph_prep_summary.json)
        """
        logger.info("=== GraphPrepPipeline starting ===")

        # ── Step 1: Load ───────────────────────────────────────────────────────
        raw_triples = self._load_extracted_triples()
        logger.info("Loaded %d triples from %s", len(raw_triples), self.input_path)

        # ── Step 2: Validate ───────────────────────────────────────────────────
        val_report: ValidationReport = self._validator.validate_all(raw_triples)
        logger.info(
            "Validation: %d valid, %d invalid",
            val_report.valid_count,
            val_report.invalid_count,
        )

        # ── Step 3: Normalize ──────────────────────────────────────────────────
        normalised = [self._normalize_triple(t) for t in val_report.valid_triples]
        logger.info("Normalised %d triples", len(normalised))

        # ── Step 4: Deduplicate ────────────────────────────────────────────────
        dedup_report: DeduplicationReport = self._deduplicator.deduplicate(normalised)
        logger.info(
            "Deduplication: %d → %d unique (%d removed)",
            dedup_report.input_count,
            dedup_report.unique_count,
            dedup_report.duplicate_count,
        )

        # ── Step 5: Write graph_ready_triples.json ────────────────────────────
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as fh:
            json.dump(
                dedup_report.unique_triples,
                fh,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        logger.info("Wrote %d graph-ready triples → %s", dedup_report.unique_count, self.output_path)

        # ── Step 6: Build & write summary ─────────────────────────────────────
        summary = self._build_summary(
            raw_triples=raw_triples,
            val_report=val_report,
            dedup_report=dedup_report,
        )
        with open(self.summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False, default=str)
        logger.info("Wrote graph prep summary → %s", self.summary_path)

        logger.info("=== GraphPrepPipeline complete ===")
        return {
            "graph_ready_count": dedup_report.unique_count,
            "validation_report": val_report,
            "dedup_report": dedup_report,
            "summary": summary,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_extracted_triples(self) -> List[Dict[str, Any]]:
        """Load and return the raw list from extracted_triples.json."""
        if not self.input_path.exists():
            raise FileNotFoundError(
                f"extracted_triples.json not found at '{self.input_path}'. "
                "Run 'python main.py --run-all' to generate it."
            )
        with open(self.input_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(
                f"Expected a JSON array in '{self.input_path}', got {type(data).__name__}"
            )
        return data

    def _normalize_triple(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce a normalised triple dict from a validated raw dict.

        Adds subject_display / object_display fields while replacing
        subject / object with their canonical_name forms.
        Relation is normalised to ALL_CAPS_SNAKE_CASE.
        Timestamp is converted to UTC ISO-8601.
        """
        # Entity normalization
        subj_canonical, subj_display = self._entity_norm.normalize(raw["subject"])
        obj_canonical, obj_display = self._entity_norm.normalize(raw["object"])

        # Relation normalization
        relation_norm = self._relation_norm.normalize(raw["relation"])

        # Timestamp normalization
        timestamp_norm = self._ts_norm.normalize(raw["timestamp"])

        return {
            "triple_id": raw["triple_id"],
            "subject": subj_canonical,
            "subject_display": subj_display,
            "subject_type": raw["subject_type"],
            "relation": relation_norm,
            "object": obj_canonical,
            "object_display": obj_display,
            "object_type": raw["object_type"],
            "timestamp": timestamp_norm,
            "source": raw["source"],
            "source_id": raw["source_id"],
            "evidence": raw["evidence"],
            "confidence": float(raw["confidence"]),
            "extraction_mode": raw["extraction_mode"],
            # Pass metadata through if present
            "metadata": raw.get("metadata", {}),
        }

    def _build_summary(
        self,
        raw_triples: List[Dict[str, Any]],
        val_report: ValidationReport,
        dedup_report: DeduplicationReport,
    ) -> Dict[str, Any]:
        """Build the graph_prep_summary dict."""
        unique = dedup_report.unique_triples

        # Entity type counts
        entity_type_counts: Dict[str, int] = {}
        # Count unique subjects+objects together (by entity type)
        for t in unique:
            st = t.get("subject_type", "Unknown")
            ot = t.get("object_type", "Unknown")
            entity_type_counts[st] = entity_type_counts.get(st, 0) + 1
            entity_type_counts[ot] = entity_type_counts.get(ot, 0) + 1

        # Relation counts
        relation_counts: Dict[str, int] = {}
        for t in unique:
            rel = t.get("relation", "UNKNOWN")
            relation_counts[rel] = relation_counts.get(rel, 0) + 1

        # Source counts
        source_counts: Dict[str, int] = {}
        for t in unique:
            src = t.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        # Date range
        timestamps = []
        for t in unique:
            ts_str = t.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    timestamps.append(ts)
                except (ValueError, TypeError):
                    pass

        date_range: Dict[str, Optional[str]] = {"earliest": None, "latest": None}
        if timestamps:
            date_range["earliest"] = min(timestamps).isoformat()
            date_range["latest"] = max(timestamps).isoformat()

        # Unique entities per type
        people: set = set()
        technologies: set = set()
        projects: set = set()
        services: set = set()
        issues: set = set()

        for t in unique:
            for role in ("subject", "object"):
                name = t.get(role, "")
                etype = t.get(f"{role}_type", "")
                if etype == "Person":
                    people.add(name)
                elif etype == "Technology":
                    technologies.add(name)
                elif etype == "Project":
                    projects.add(name)
                elif etype == "Service":
                    services.add(name)
                elif etype == "Issue":
                    issues.add(name)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_stage": "Graph Preparation",
            "input_file": str(self.input_path).replace("\\", "/"),
            "output_file": str(self.output_path).replace("\\", "/"),
            "statistics": {
                "total_input_triples": val_report.total_input,
                "valid_triples": val_report.valid_count,
                "invalid_triples": val_report.invalid_count,
                "validation_errors": len(val_report.errors),
                "triples_after_deduplication": dedup_report.unique_count,
                "duplicates_removed": dedup_report.duplicate_count,
                "graph_ready_triples": dedup_report.unique_count,
            },
            "entities": {
                "people": len(people),
                "technologies": len(technologies),
                "projects": len(projects),
                "services": len(services),
                "issues": len(issues),
                "entity_type_mention_counts": entity_type_counts,
            },
            "relations": {
                "unique_relation_types": len(relation_counts),
                "relation_counts": dict(sorted(relation_counts.items(), key=lambda x: -x[1])),
            },
            "sources": {
                "slack": source_counts.get("slack", 0),
                "github": source_counts.get("github", 0),
                "jira": source_counts.get("jira", 0),
                "by_source": source_counts,
            },
            "date_range": date_range,
            "validation_report": val_report.to_dict(),
            "deduplication_report": dedup_report.to_dict(),
        }
