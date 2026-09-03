"""
src/graph_prep/deduplicator.py
────────────────────────────────
Deterministic Duplicate Triple Detection.

A triple is considered a duplicate if it shares the same composite key:

    (subject_canonical, relation, object_canonical, timestamp_utc, source, source_id)

Deduplication policy
─────────────────────
* When two records share the same key, the one with the HIGHER confidence
  score is kept.  If confidence is equal, the first-encountered record wins
  (preserving insertion order from the upstream extractor).

* Records with DIFFERENT source_ids are NEVER automatically merged, even if
  all other fields match — they represent distinct source events.

* The DeduplicationReport provides full statistics and the list of
  discarded triple_ids so the team can audit what was removed.

Note: this module operates on ALREADY NORMALISED triple dicts (i.e., after
running EntityNormalizer and RelationNormalizer).  The composite key uses
the canonical subject/object names that were written by the normalizer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DuplicateRecord:
    """One detected duplicate — records which triple was kept and which dropped."""
    kept_triple_id: str
    dropped_triple_id: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kept_triple_id": self.kept_triple_id,
            "dropped_triple_id": self.dropped_triple_id,
            "reason": self.reason,
        }


@dataclass
class DeduplicationReport:
    """
    Statistics and audit log for the deduplication pass.

    Attributes
    ──────────
    input_count   : triples fed into the deduplicator
    duplicate_count : triples that were removed as duplicates
    unique_count  : final count of triples kept
    duplicates    : list of DuplicateRecord for audit purposes
    unique_triples : the deduplicated list of triple dicts
    """
    input_count: int = 0
    duplicate_count: int = 0
    unique_count: int = 0
    duplicates: List[DuplicateRecord] = field(default_factory=list)
    unique_triples: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_count": self.input_count,
            "duplicate_count": self.duplicate_count,
            "unique_count": self.unique_count,
            "duplicates": [d.to_dict() for d in self.duplicates],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Deduplicator
# ─────────────────────────────────────────────────────────────────────────────


class TripleDeduplicator:
    """
    Remove duplicate triples from a list of normalised triple dicts.

    Usage
    ─────
        deduplicator = TripleDeduplicator()
        report = deduplicator.deduplicate(normalised_triples)
        # report.unique_triples → deduplicated list
        # report.duplicates     → audit of what was removed and why
    """

    def deduplicate(self, triples: List[Dict[str, Any]]) -> DeduplicationReport:
        """
        Perform deterministic deduplication.

        Parameters
        ──────────
        triples : list of already-normalised triple dicts.

        Returns
        ───────
        DeduplicationReport with unique_triples populated.
        """
        report = DeduplicationReport(input_count=len(triples))

        # Map composite_key → best triple dict seen so far
        seen: Dict[Tuple, Dict[str, Any]] = {}

        for triple in triples:
            key = self._composite_key(triple)
            triple_id = triple.get("triple_id", "<no-id>")

            if key not in seen:
                seen[key] = triple
            else:
                existing = seen[key]
                existing_id = existing.get("triple_id", "<no-id>")
                existing_conf = float(existing.get("confidence", 0.0))
                current_conf = float(triple.get("confidence", 0.0))

                if current_conf > existing_conf:
                    # Replace with the higher-confidence record
                    report.duplicates.append(
                        DuplicateRecord(
                            kept_triple_id=triple_id,
                            dropped_triple_id=existing_id,
                            reason=(
                                f"Duplicate key; replaced with higher confidence "
                                f"({current_conf:.3f} > {existing_conf:.3f})"
                            ),
                        )
                    )
                    seen[key] = triple
                    logger.debug(
                        "Replaced triple %s with %s (conf %.3f > %.3f)",
                        existing_id, triple_id, current_conf, existing_conf,
                    )
                else:
                    # Keep the existing higher/equal-confidence record
                    report.duplicates.append(
                        DuplicateRecord(
                            kept_triple_id=existing_id,
                            dropped_triple_id=triple_id,
                            reason=(
                                f"Duplicate key; dropped lower/equal confidence "
                                f"({current_conf:.3f} <= {existing_conf:.3f})"
                            ),
                        )
                    )
                    logger.debug(
                        "Dropped duplicate triple %s (conf %.3f <= %.3f of %s)",
                        triple_id, current_conf, existing_conf, existing_id,
                    )

        report.unique_triples = list(seen.values())
        report.duplicate_count = len(report.duplicates)
        report.unique_count = len(report.unique_triples)

        logger.info(
            "Deduplication: %d input → %d unique (%d duplicates removed)",
            report.input_count,
            report.unique_count,
            report.duplicate_count,
        )
        return report

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _composite_key(triple: Dict[str, Any]) -> Tuple:
        """
        Build the deterministic composite key used for duplicate detection.

        We use the *canonical* subject/object names (written by the normalizer
        under the 'subject' and 'object' keys after normalization) together
        with relation, timestamp (UTC ISO string), source, and source_id.

        Two triples with the same (subject, relation, object, timestamp, source,
        source_id) are considered duplicates regardless of their triple_id or
        evidence text.
        """
        subject = str(triple.get("subject", "")).strip().lower()
        relation = str(triple.get("relation", "")).strip().upper()
        obj = str(triple.get("object", "")).strip().lower()
        # Timestamp is already UTC ISO string after normalization
        timestamp = str(triple.get("timestamp", "")).strip()
        source = str(triple.get("source", "")).strip().lower()
        source_id = str(triple.get("source_id", "")).strip()

        return (subject, relation, obj, timestamp, source, source_id)
