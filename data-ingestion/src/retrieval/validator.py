"""
src/retrieval/validator.py
──────────────────────────
Week 3 — Output consistency validator for Temporal Retrieval Preparation.

RetrievalOutputValidator verifies that the generated retrieval output is
internally consistent after the builder has run. It reads the two output
artefacts produced by RetrievalRecordBuilder and cross-checks them against
each other and against a set of structural rules from the data contract.

Validation Checks
─────────────────
  1. Unique identifiers   — every record_id / triple_id must be unique.
  2. Required provenance  — source, source_id, and evidence must be non-empty.
  3. Temporal metadata    — timestamp must be ISO-8601; event_date must be
                            parseable and consistent with the timestamp.
  4. Record count parity  — records_built in retrieval_prep_summary.json must
                            equal the number of records in retrieval_ready_records.json.
  5. Accounting identity  — records_built + skipped_records == total_records.
  6. Pipeline status      — status field must equal "success" when
                            skipped_records == 0, else "partial".
  7. Error messages       — all errors carry a clear, human-readable message
                            naming the offending field, record ID, and
                            expected vs. actual value.

Public API
──────────
    from src.retrieval.validator import RetrievalOutputValidator

    validator = RetrievalOutputValidator(
        records_path=Path("data/processed/retrieval_ready_records.json"),
        summary_path=Path("data/processed/retrieval_prep_summary.json"),
    )
    result = validator.validate()
    # result.is_valid  -> bool
    # result.errors    -> List[str]
    # result.warnings  -> List[str]
    # result.stats     -> dict  (counts, checked fields)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ValidationResult
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """
    Holds the outcome of a single RetrievalOutputValidator.validate() run.

    Attributes
    ──────────
    is_valid  : True if no errors were found (warnings are non-blocking).
    errors    : List of human-readable error strings (blocking failures).
    warnings  : List of human-readable warning strings (non-blocking notices).
    stats     : Diagnostic statistics collected during validation.
    """

    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, msg: str) -> None:
        """Record a blocking validation error and mark the result invalid."""
        self.is_valid = False
        self.errors.append(msg)
        logger.error("Validation error: %s", msg)

    def add_warning(self, msg: str) -> None:
        """Record a non-blocking warning (is_valid stays unaffected)."""
        self.warnings.append(msg)
        logger.warning("Validation warning: %s", msg)


# ─────────────────────────────────────────────────────────────────────────────
# RetrievalOutputValidator
# ─────────────────────────────────────────────────────────────────────────────


class RetrievalOutputValidator:
    """
    Post-build consistency validator for Week 3 retrieval output artefacts.

    Validates two files produced by RetrievalRecordBuilder:
      * retrieval_ready_records.json  — the evidence record array
      * retrieval_prep_summary.json   — the pipeline execution metadata

    All checks are read-only — this class never modifies any file.

    Parameters
    ──────────
    records_path : Path to retrieval_ready_records.json.
    summary_path : Path to retrieval_prep_summary.json.

    Usage
    ─────
        validator = RetrievalOutputValidator(
            records_path=Path("data/processed/retrieval_ready_records.json"),
            summary_path=Path("data/processed/retrieval_prep_summary.json"),
        )
        result = validator.validate()
        if not result.is_valid:
            for err in result.errors:
                print(f"ERROR: {err}")
    """

    # Required string fields in each record dict (must be non-empty strings)
    _REQUIRED_STR_FIELDS = (
        "record_id",
        "triple_id",
        "source",
        "source_id",
        "evidence",
    )

    # Required metadata keys in retrieval_prep_summary.json
    _REQUIRED_SUMMARY_KEYS = (
        "pipeline_name",
        "input_source",
        "total_records",
        "records_built",
        "skipped_records",
        "generated_at",
        "status",
    )

    def __init__(self, records_path: Path, summary_path: Path) -> None:
        self.records_path = Path(records_path)
        self.summary_path = Path(summary_path)

    # ── Public API ────────────────────────────────────────────────────────────

    def validate(self) -> ValidationResult:
        """
        Run all validation checks and return a consolidated ValidationResult.

        Returns
        ───────
        ValidationResult — populated with errors, warnings, and stats.
        """
        result = ValidationResult()

        # Load files (file-not-found -> immediate failure for that artefact)
        records = self._load_records(result)
        summary = self._load_summary(result)

        if records is None or summary is None:
            # Cannot do further cross-checks without both artefacts
            return result

        # Collect top-level stats
        result.stats["records_file_count"] = len(records)
        result.stats["summary_total_records"] = summary.get("total_records")
        result.stats["summary_records_built"] = summary.get("records_built")
        result.stats["summary_skipped_records"] = summary.get("skipped_records")
        result.stats["summary_status"] = summary.get("status")

        # ── Check 1: Unique record_id / triple_id ─────────────────────────────
        self._check_unique_identifiers(records, result)

        # ── Check 2: Required provenance / source fields present ─────────────
        self._check_required_provenance(records, result)

        # ── Check 3: Temporal metadata valid and consistent ──────────────────
        self._check_temporal_metadata(records, result)

        # ── Check 4: records_built in summary == actual file record count ────
        self._check_record_count_parity(records, summary, result)

        # ── Check 5: records_built + skipped_records == total_records ────────
        self._check_accounting_identity(summary, result)

        # ── Check 6: Pipeline status correctly represented ───────────────────
        self._check_pipeline_status(summary, result)

        logger.info(
            "RetrievalOutputValidator: validation %s — %d error(s), %d warning(s)",
            "PASSED" if result.is_valid else "FAILED",
            len(result.errors),
            len(result.warnings),
        )
        return result

    # ── File loaders ──────────────────────────────────────────────────────────

    def _load_records(
        self, result: ValidationResult
    ) -> Optional[List[Dict[str, Any]]]:
        """Load retrieval_ready_records.json; record error and return None on failure."""
        if not self.records_path.exists():
            result.add_error(
                f"retrieval_ready_records.json not found at '{self.records_path}'. "
                "Run 'python main.py --prepare-retrieval' to generate it."
            )
            return None
        try:
            with open(self.records_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            result.add_error(
                f"retrieval_ready_records.json contains invalid JSON: {exc}"
            )
            return None
        if not isinstance(data, list):
            result.add_error(
                f"retrieval_ready_records.json must be a JSON array, "
                f"got {type(data).__name__}."
            )
            return None
        return data

    def _load_summary(
        self, result: ValidationResult
    ) -> Optional[Dict[str, Any]]:
        """Load retrieval_prep_summary.json; record error and return None on failure."""
        if not self.summary_path.exists():
            result.add_error(
                f"retrieval_prep_summary.json not found at '{self.summary_path}'. "
                "Run 'python main.py --prepare-retrieval' to generate it."
            )
            return None
        try:
            with open(self.summary_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            result.add_error(
                f"retrieval_prep_summary.json contains invalid JSON: {exc}"
            )
            return None
        if not isinstance(data, dict):
            result.add_error(
                f"retrieval_prep_summary.json must be a JSON object, "
                f"got {type(data).__name__}."
            )
            return None
        missing = [k for k in self._REQUIRED_SUMMARY_KEYS if k not in data]
        if missing:
            result.add_error(
                f"retrieval_prep_summary.json is missing required key(s): "
                f"{missing}. "
                f"Expected keys: {list(self._REQUIRED_SUMMARY_KEYS)}."
            )
            return None
        return data

    # ── Check implementations ─────────────────────────────────────────────────

    def _check_unique_identifiers(
        self,
        records: List[Dict[str, Any]],
        result: ValidationResult,
    ) -> None:
        """
        Check 1 — Every record_id and triple_id must be unique across all records.

        Duplicates suggest a builder bug (the same triple was processed twice)
        and would cause downstream retrieval collisions.
        """
        seen_record_ids: Dict[str, int] = {}
        seen_triple_ids: Dict[str, int] = {}
        dup_record_ids: List[str] = []
        dup_triple_ids: List[str] = []

        for i, rec in enumerate(records):
            rid = rec.get("record_id", "")
            tid = rec.get("triple_id", "")

            if rid:
                if rid in seen_record_ids:
                    if rid not in dup_record_ids:
                        dup_record_ids.append(rid)
                else:
                    seen_record_ids[rid] = i

            if tid:
                if tid in seen_triple_ids:
                    if tid not in dup_triple_ids:
                        dup_triple_ids.append(tid)
                else:
                    seen_triple_ids[tid] = i

        if dup_record_ids:
            result.add_error(
                f"Check 1 (Unique Identifiers): {len(dup_record_ids)} duplicate "
                f"record_id value(s) in retrieval_ready_records.json. "
                f"Duplicates: {dup_record_ids[:5]}"
                f"{'...' if len(dup_record_ids) > 5 else ''}. "
                "Each record must have a globally unique record_id."
            )

        if dup_triple_ids:
            result.add_error(
                f"Check 1 (Unique Identifiers): {len(dup_triple_ids)} duplicate "
                f"triple_id value(s) in retrieval_ready_records.json. "
                f"Duplicates: {dup_triple_ids[:5]}"
                f"{'...' if len(dup_triple_ids) > 5 else ''}. "
                "Each record must have a globally unique triple_id."
            )

        result.stats["unique_record_ids"] = len(seen_record_ids)
        result.stats["unique_triple_ids"] = len(seen_triple_ids)
        result.stats["duplicate_record_ids"] = len(dup_record_ids)
        result.stats["duplicate_triple_ids"] = len(dup_triple_ids)

        if not dup_record_ids and not dup_triple_ids:
            logger.debug(
                "Check 1 passed: all %d record_id/triple_id values are unique.",
                len(records),
            )

    def _check_required_provenance(
        self,
        records: List[Dict[str, Any]],
        result: ValidationResult,
    ) -> None:
        """
        Check 2 — Required provenance / source fields must be present and non-empty.

        Fields checked: record_id, triple_id, source, source_id, evidence.
        """
        violations: List[str] = []

        for i, rec in enumerate(records):
            rid = rec.get("record_id") or f"index_{i}"
            for fname in self._REQUIRED_STR_FIELDS:
                value = rec.get(fname)
                if not value or not str(value).strip():
                    violations.append(
                        f"record '{rid}' — field '{fname}' is missing or empty "
                        f"(got {value!r})"
                    )

        if violations:
            result.add_error(
                f"Check 2 (Required Provenance): {len(violations)} required-field "
                f"violation(s) in retrieval_ready_records.json. "
                f"Sample: {violations[:5]}"
                f"{'...' if len(violations) > 5 else ''}. "
                "Fields 'record_id', 'triple_id', 'source', 'source_id', and "
                "'evidence' must be non-empty strings in every record."
            )
        else:
            logger.debug(
                "Check 2 passed: all %d records have required provenance fields.",
                len(records),
            )

        result.stats["provenance_violations"] = len(violations)

    def _check_temporal_metadata(
        self,
        records: List[Dict[str, Any]],
        result: ValidationResult,
    ) -> None:
        """
        Check 3 — Temporal metadata must be valid and internally consistent.

        Rules:
          3a. 'timestamp' must be parseable as ISO-8601.
          3b. 'event_date' must be parseable as YYYY-MM-DD.
          3c. 'event_date' must equal the UTC calendar date of 'timestamp'.
        """
        invalid_timestamps: List[str] = []
        invalid_event_dates: List[str] = []
        inconsistent_dates: List[str] = []

        for i, rec in enumerate(records):
            rid = rec.get("record_id") or f"index_{i}"
            ts = rec.get("timestamp")
            ed = rec.get("event_date")

            # 3a — timestamp
            parsed_ts: Optional[datetime] = None
            if not ts or not str(ts).strip():
                invalid_timestamps.append(
                    f"record '{rid}' — 'timestamp' is missing or empty (got {ts!r})"
                )
            else:
                try:
                    parsed_ts = datetime.fromisoformat(str(ts))
                except (ValueError, TypeError):
                    invalid_timestamps.append(
                        f"record '{rid}' — 'timestamp' is not valid ISO-8601 "
                        f"(got {ts!r})"
                    )

            # 3b — event_date
            parsed_ed: Optional[date] = None
            if not ed or not str(ed).strip():
                invalid_event_dates.append(
                    f"record '{rid}' — 'event_date' is missing or empty (got {ed!r})"
                )
            else:
                try:
                    parsed_ed = date.fromisoformat(str(ed))
                except (ValueError, TypeError):
                    invalid_event_dates.append(
                        f"record '{rid}' — 'event_date' is not a valid ISO date "
                        f"(got {ed!r})"
                    )

            # 3c — consistency
            if parsed_ts is not None and parsed_ed is not None:
                ts_utc = parsed_ts
                if ts_utc.tzinfo is not None:
                    ts_utc = ts_utc.astimezone(timezone.utc)
                expected = ts_utc.date()
                if parsed_ed != expected:
                    inconsistent_dates.append(
                        f"record '{rid}' — 'event_date' ({parsed_ed.isoformat()}) "
                        f"does not match UTC calendar date of 'timestamp' "
                        f"({expected.isoformat()})"
                    )

        if invalid_timestamps:
            result.add_error(
                f"Check 3a (Temporal Timestamp): {len(invalid_timestamps)} "
                f"invalid timestamp(s). "
                f"Sample: {invalid_timestamps[:3]}"
                f"{'...' if len(invalid_timestamps) > 3 else ''}. "
                "'timestamp' must be a valid ISO-8601 datetime string."
            )
        if invalid_event_dates:
            result.add_error(
                f"Check 3b (Temporal event_date): {len(invalid_event_dates)} "
                f"invalid event_date(s). "
                f"Sample: {invalid_event_dates[:3]}"
                f"{'...' if len(invalid_event_dates) > 3 else ''}. "
                "'event_date' must be a valid ISO date string (YYYY-MM-DD)."
            )
        if inconsistent_dates:
            result.add_error(
                f"Check 3c (Temporal Consistency): {len(inconsistent_dates)} "
                f"record(s) where 'event_date' does not match the UTC date of "
                f"'timestamp'. "
                f"Sample: {inconsistent_dates[:3]}"
                f"{'...' if len(inconsistent_dates) > 3 else ''}."
            )

        result.stats["invalid_timestamps"] = len(invalid_timestamps)
        result.stats["invalid_event_dates"] = len(invalid_event_dates)
        result.stats["inconsistent_dates"] = len(inconsistent_dates)

        if not (invalid_timestamps or invalid_event_dates or inconsistent_dates):
            logger.debug(
                "Check 3 passed: all %d records have valid, consistent temporal metadata.",
                len(records),
            )

    def _check_record_count_parity(
        self,
        records: List[Dict[str, Any]],
        summary: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """
        Check 4 — records_built in the summary must equal the actual record count
        in retrieval_ready_records.json.

        Invariant: len(retrieval_ready_records.json) == records_built
        """
        actual = len(records)
        built = summary.get("records_built")

        if not isinstance(built, int):
            result.add_error(
                f"Check 4 (Record Count Parity): 'records_built' in "
                f"retrieval_prep_summary.json is not an integer (got {built!r})."
            )
            return

        if actual != built:
            result.add_error(
                f"Check 4 (Record Count Parity): retrieval_ready_records.json "
                f"contains {actual} record(s) but retrieval_prep_summary.json "
                f"reports records_built={built}. "
                "These must be equal — the summary must reflect what was written "
                "to the records file."
            )
        else:
            logger.debug(
                "Check 4 passed: file record count (%d) matches records_built (%d).",
                actual,
                built,
            )

    def _check_accounting_identity(
        self,
        summary: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """
        Check 5 — records_built + skipped_records == total_records.

        Confirms the builder did not silently drop or double-count any input triple.
        """
        total = summary.get("total_records")
        built = summary.get("records_built")
        skipped = summary.get("skipped_records")

        if not all(isinstance(v, int) for v in (total, built, skipped)):
            result.add_error(
                "Check 5 (Accounting Identity): 'total_records', 'records_built', "
                "and 'skipped_records' must all be integers in "
                "retrieval_prep_summary.json. "
                f"Got: total={total!r}, built={built!r}, skipped={skipped!r}."
            )
            return

        if built + skipped != total:
            result.add_error(
                f"Check 5 (Accounting Identity): records_built ({built}) + "
                f"skipped_records ({skipped}) = {built + skipped}, "
                f"but total_records = {total}. "
                "Invariant: records_built + skipped_records == total_records."
            )
        else:
            logger.debug(
                "Check 5 passed: %d + %d == %d (accounting identity holds).",
                built,
                skipped,
                total,
            )

    def _check_pipeline_status(
        self,
        summary: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """
        Check 6 — The pipeline status must be correctly represented.

        Rules:
          * status == "success"  when skipped_records == 0
          * status == "partial"  when skipped_records > 0
        """
        status = summary.get("status")
        skipped = summary.get("skipped_records")

        valid_statuses = {"success", "partial"}
        if status not in valid_statuses:
            result.add_error(
                f"Check 6 (Pipeline Status): 'status' has unrecognised value "
                f"{status!r} in retrieval_prep_summary.json. "
                f"Valid values: {sorted(valid_statuses)}."
            )
            return

        if not isinstance(skipped, int):
            result.add_error(
                f"Check 6 (Pipeline Status): cannot verify status consistency — "
                f"'skipped_records' is not an integer (got {skipped!r})."
            )
            return

        expected = "success" if skipped == 0 else "partial"
        if status != expected:
            result.add_error(
                f"Check 6 (Pipeline Status): status is {status!r} but "
                f"skipped_records={skipped} requires status={expected!r}. "
                "Status must be 'success' when skipped_records == 0 "
                "and 'partial' when skipped_records > 0."
            )
        else:
            logger.debug(
                "Check 6 passed: status=%r is consistent with skipped_records=%d.",
                status,
                skipped,
            )
