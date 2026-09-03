"""
src/retrieval/builder.py
────────────────────────
Builds RetrievalRecord list from graph-ready triples.

The RetrievalRecordBuilder reads the existing graph_ready_triples.json
produced by the GraphPrepPipeline and transforms each record into a
RetrievalRecord — the retrieval-ready evidence unit for downstream Temporal
Routing.

Design Principles
─────────────────
  • No data is invented.  Every field in RetrievalRecord is derived from the
    corresponding field in the source triple dict, or set to None/empty if the
    source dict does not contain it.
  • source_url is extracted from metadata if present; otherwise None.
  • event_date is parsed from the triple's timestamp string.
  • Malformed records are skipped with a logged warning (never crash).
  • A PipelineExecutionMetadata summary is written to a *separate* file
    (retrieval_prep_summary.json) after every run.  The
    retrieval_ready_records.json contract is not altered.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.retrieval.models import PipelineExecutionMetadata, RetrievalRecord

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────────────────────────────────────


class RetrievalRecordBuilder:
    """
    Converts graph-ready triple dicts into RetrievalRecord objects.

    Parameters
    ──────────
    input_path : Path to graph_ready_triples.json.
    output_path: Destination for retrieval_ready_records.json.

    Usage
    ─────
        builder = RetrievalRecordBuilder(
            input_path  = Path("data/processed/graph_ready_triples.json"),
            output_path = Path("data/processed/retrieval_ready_records.json"),
        )
        records, report = builder.build()
        # records: List[RetrievalRecord]
        # report : dict with statistics
    """

    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        summary_path: Optional[Path] = None,
    ) -> None:
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        # Derive summary path: same dir as output, named retrieval_prep_summary.json
        if summary_path is None:
            self.summary_path: Path = self.output_path.parent / "retrieval_prep_summary.json"
        else:
            self.summary_path = Path(summary_path)

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self) -> tuple[List[RetrievalRecord], Dict[str, Any], PipelineExecutionMetadata]:
        """
        Load graph-ready triples and build retrieval-ready records.

        Returns
        ───────
        (records, report, metadata)
            records  : List[RetrievalRecord] — successfully built records.
            report   : dict — build statistics (total, success, skipped).
            metadata : PipelineExecutionMetadata — execution metadata written
                       to retrieval_prep_summary.json.
        """
        raw_triples = self._load_graph_ready_triples()
        logger.info(
            "RetrievalRecordBuilder: loaded %d graph-ready triples from %s",
            len(raw_triples),
            self.input_path,
        )

        records: List[RetrievalRecord] = []
        skipped: List[Dict[str, Any]] = []

        for i, triple in enumerate(raw_triples):
            try:
                record = self._build_record(triple)
                records.append(record)
            except Exception as exc:
                triple_id = triple.get("triple_id", f"index_{i}")
                logger.warning(
                    "Skipping triple '%s' — build error: %s",
                    triple_id,
                    exc,
                )
                skipped.append({"triple_id": triple_id, "error": str(exc)})

        self._write_output(records)

        report = {
            "total_input": len(raw_triples),
            "records_built": len(records),
            "records_skipped": len(skipped),
            "skipped_details": skipped,
            "output_path": str(self.output_path),
        }
        logger.info(
            "RetrievalRecordBuilder: built %d records, skipped %d",
            len(records),
            len(skipped),
        )

        metadata = self._write_summary(len(raw_triples), len(records), len(skipped))

        return records, report, metadata

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_graph_ready_triples(self) -> List[Dict[str, Any]]:
        """Load and return the raw list from graph_ready_triples.json."""
        if not self.input_path.exists():
            raise FileNotFoundError(
                f"graph_ready_triples.json not found at '{self.input_path}'. "
                "Run 'python main.py --prepare-graph' to generate it."
            )
        with open(self.input_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(
                f"Expected a JSON array in '{self.input_path}', got {type(data).__name__}"
            )
        return data

    def _build_record(self, triple: Dict[str, Any]) -> RetrievalRecord:
        """
        Convert a single graph-ready triple dict into a RetrievalRecord.

        Fields mapped:
            triple_id        → triple_id (= record_id)
            subject          → subject
            subject_display  → subject_display (None if missing)
            subject_type     → subject_type    (None if missing)
            relation         → relation
            object           → object
            object_display   → object_display  (None if missing)
            object_type      → object_type     (None if missing)
            timestamp        → timestamp + event_date (parsed from timestamp)
            source           → source
            source_id        → source_id
            metadata.url /
            metadata.source_url → source_url  (None if missing)
            evidence         → evidence
            confidence       → confidence
            extraction_mode  → extraction_mode (None if missing)
            metadata         → metadata (pass-through)
        """
        triple_id: str = triple["triple_id"]
        timestamp_str: str = triple["timestamp"]

        # Parse event_date from timestamp
        event_date = self._parse_event_date(timestamp_str, triple_id)

        # Extract source_url from metadata if present (never fabricated)
        metadata: Dict[str, Any] = triple.get("metadata") or {}
        source_url: Optional[str] = (
            metadata.get("url")
            or metadata.get("source_url")
            or metadata.get("html_url")
            or metadata.get("permalink")
            or None
        )

        return RetrievalRecord(
            record_id=triple_id,
            triple_id=triple_id,
            subject=triple["subject"],
            subject_display=triple.get("subject_display") or None,
            subject_type=triple.get("subject_type") or None,
            relation=triple["relation"],
            object=triple["object"],
            object_display=triple.get("object_display") or None,
            object_type=triple.get("object_type") or None,
            timestamp=timestamp_str,
            event_date=event_date,
            source=triple["source"],
            source_id=triple["source_id"],
            source_url=source_url,
            evidence=triple["evidence"],
            confidence=float(triple["confidence"]),
            extraction_mode=triple.get("extraction_mode") or None,
            metadata=metadata,
        )

    @staticmethod
    def _parse_event_date(timestamp_str: str, triple_id: str):
        """
        Parse the calendar date from a UTC ISO-8601 timestamp string.

        Falls back to today's date with a warning if parsing fails (this
        should not happen for well-formed graph-ready triples).
        """
        from datetime import date, timezone
        try:
            dt = datetime.fromisoformat(timestamp_str)
            # Normalise to UTC date
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            return dt.date()
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Could not parse timestamp '%s' for triple '%s': %s — using today's UTC date.",
                timestamp_str,
                triple_id,
                exc,
            )
            from datetime import date
            return date.today()

    def _write_output(self, records: List[RetrievalRecord]) -> None:
        """Write retrieval_ready_records.json (data contract unchanged)."""
        import json
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as fh:
            json.dump(
                [r.to_dict() for r in records],
                fh,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        logger.info(
            "Wrote %d retrieval-ready records → %s",
            len(records),
            self.output_path,
        )

    def _write_summary(
        self,
        total_records: int,
        records_built: int,
        skipped_records: int,
    ) -> "PipelineExecutionMetadata":
        """Build and persist PipelineExecutionMetadata to retrieval_prep_summary.json."""
        import json
        from config.settings import PROJECT_ROOT

        try:
            input_source = str(self.input_path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
        except Exception:
            input_source = str(self.input_path).replace("\\", "/")

        metadata = PipelineExecutionMetadata(
            input_source=input_source,
            total_records=total_records,
            records_built=records_built,
            skipped_records=skipped_records,
        )
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.summary_path, "w", encoding="utf-8") as fh:
            json.dump(metadata.to_dict(), fh, indent=2, ensure_ascii=False)
        logger.info(
            "Wrote pipeline execution metadata → %s (status=%s)",
            self.summary_path,
            metadata.status,
        )
        return metadata
