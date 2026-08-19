"""
src/graph_prep/validator.py
────────────────────────────
Week 2 – Graph-Ready Data Validation (Karkuvel's module).

Validates every extracted triple against the schema defined in
src/schemas/graph.py.  Invalid records are NEVER silently discarded;
they are captured in a ValidationReport so the team can audit
data-quality issues.

Required fields per triple
──────────────────────────
    triple_id, subject, subject_type, relation, object, object_type,
    timestamp, source, source_id, evidence, confidence, extraction_mode

Business rules enforced
────────────────────────
    • subject, object, relation, source_id, evidence  → non-empty strings
    • timestamp  → parseable as ISO datetime
    • confidence → float in [0.0, 1.0]
    • source     → one of {slack, github, jira}
    • subject_type / object_type → one of EntityType enum values
    • extraction_mode → one of ExtractionMode enum values
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.schemas.graph import DataSource, EntityType, ExtractionMode

logger = logging.getLogger(__name__)

# All accepted string values (lower-cased for comparison)
_VALID_SOURCES = {s.value for s in DataSource}
_VALID_ENTITY_TYPES = {e.value for e in EntityType}
_VALID_EXTRACTION_MODES = {m.value for m in ExtractionMode}

# Required field names that must exist and be non-None
_REQUIRED_FIELDS = [
    "triple_id",
    "subject",
    "subject_type",
    "relation",
    "object",
    "object_type",
    "timestamp",
    "source",
    "source_id",
    "evidence",
    "confidence",
    "extraction_mode",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TripleError:
    """Details of one validation failure for a single triple."""
    triple_id: Optional[str]
    field: str
    value: Any
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "triple_id": self.triple_id,
            "field": self.field,
            "value": str(self.value),
            "message": self.message,
        }


@dataclass
class ValidationReport:
    """
    Summary produced by TripleValidator.validate_all().

    Attributes
    ──────────
    total_input      : number of raw records received
    valid_count      : records that passed all checks
    invalid_count    : records that failed at least one check
    errors           : list of TripleError details for audit purposes
    valid_triples    : the subset of input dicts that passed validation
    """
    total_input: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    errors: List[TripleError] = field(default_factory=list)
    valid_triples: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_input": self.total_input,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "error_count": len(self.errors),
            "errors": [e.to_dict() for e in self.errors],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Validator
# ─────────────────────────────────────────────────────────────────────────────


class TripleValidator:
    """
    Validates a list of raw triple dicts (as loaded from extracted_triples.json).

    Usage
    ─────
        validator = TripleValidator()
        report = validator.validate_all(triples)
        # report.valid_triples → passed records
        # report.errors        → detailed failure info
    """

    def validate_all(self, triples: List[Dict[str, Any]]) -> ValidationReport:
        """Validate every triple and return a ValidationReport."""
        report = ValidationReport(total_input=len(triples))

        for raw in triples:
            errors = self._validate_one(raw)
            if errors:
                report.invalid_count += 1
                report.errors.extend(errors)
                tid = raw.get("triple_id", "<no-id>")
                logger.warning(
                    "Triple %s failed validation: %s",
                    tid,
                    [e.message for e in errors],
                )
            else:
                report.valid_count += 1
                report.valid_triples.append(raw)

        logger.info(
            "Validation complete: %d valid / %d invalid out of %d total",
            report.valid_count,
            report.invalid_count,
            report.total_input,
        )
        return report

    # ── Private helpers ───────────────────────────────────────────────────────

    def _validate_one(self, raw: Dict[str, Any]) -> List[TripleError]:
        """Return a list of errors for a single triple dict (empty = valid)."""
        errs: List[TripleError] = []
        tid = raw.get("triple_id")

        def err(field: str, value: Any, msg: str) -> None:
            errs.append(TripleError(triple_id=tid, field=field, value=value, message=msg))

        # 1. Required fields must exist and be non-None
        for fname in _REQUIRED_FIELDS:
            if fname not in raw or raw[fname] is None:
                err(fname, None, f"Required field '{fname}' is missing or null")

        if errs:
            # No point running deeper checks if basics are missing
            return errs

        # 2. Non-empty string fields
        for fname in ("subject", "object", "relation", "source_id", "evidence", "triple_id"):
            val = raw[fname]
            if not isinstance(val, str) or not val.strip():
                err(fname, val, f"Field '{fname}' must be a non-empty string")

        # 3. Source must be a valid DataSource value
        src = raw.get("source", "")
        if src not in _VALID_SOURCES:
            err("source", src, f"Invalid source '{src}'. Must be one of {sorted(_VALID_SOURCES)}")

        # 4. Entity types
        for fname in ("subject_type", "object_type"):
            val = raw.get(fname, "")
            if val not in _VALID_ENTITY_TYPES:
                err(fname, val, f"Invalid entity type '{val}'. Must be one of {sorted(_VALID_ENTITY_TYPES)}")

        # 5. Extraction mode
        em = raw.get("extraction_mode", "")
        if em not in _VALID_EXTRACTION_MODES:
            err(
                "extraction_mode",
                em,
                f"Invalid extraction_mode '{em}'. Must be one of {sorted(_VALID_EXTRACTION_MODES)}",
            )

        # 6. Confidence must be float in [0.0, 1.0]
        conf = raw.get("confidence")
        try:
            conf_f = float(conf)  # type: ignore[arg-type]
            if not (0.0 <= conf_f <= 1.0):
                err("confidence", conf, f"Confidence {conf_f} is out of range [0.0, 1.0]")
        except (TypeError, ValueError):
            err("confidence", conf, f"Confidence '{conf}' is not a valid float")

        # 7. Timestamp must be parseable as ISO datetime
        ts = raw.get("timestamp")
        if not _is_valid_timestamp(ts):
            err("timestamp", ts, f"Timestamp '{ts}' is not a valid ISO datetime")

        return errs


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _is_valid_timestamp(value: Any) -> bool:
    """Return True if *value* is a datetime object or parseable ISO datetime string."""
    if isinstance(value, datetime):
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            datetime.strptime(value.replace("+00:00", "Z").replace("Z", "+00:00"), fmt)
            return True
        except ValueError:
            pass
    # Last resort: try Python's fromisoformat (Python 3.7+)
    try:
        datetime.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        pass
    return False
