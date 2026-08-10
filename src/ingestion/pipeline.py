"""
src/ingestion/pipeline.py
─────────────────────────
Unified data ingestion & preprocessing pipeline.

Responsibilities
────────────────
1. Run SlackLoader, GitHubLoader, JiraLoader in sequence.
2. Aggregate all RawEvent objects.
3. Normalise timestamps (convert to UTC, strip timezone for storage).
4. Clean text (whitespace, control chars).
5. Validate required fields via Pydantic.
6. Produce LlamaIndex Document objects for the extraction pipeline.
7. Persist normalised events to data/processed/normalized_events.json.

The pipeline deliberately does NOT touch the raw JSON files.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.ingestion.github_loader import GitHubLoader
from src.ingestion.jira_loader import JiraLoader
from src.ingestion.slack_loader import SlackLoader
from src.schemas.graph import RawEvent

logger = logging.getLogger(__name__)

# LlamaIndex import is optional – the pipeline works without it for testing
try:
    from llama_index.core import Document as LlamaDocument
    _LLAMA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _LLAMA_AVAILABLE = False
    logger.warning("llama-index-core not installed – LlamaIndex Documents will not be produced.")


class IngestionPipeline:
    """
    Orchestrates all three data loaders and produces clean, normalised events.

    Parameters
    ----------
    slack_path:
        Path to data/raw/slack_history.json
    github_path:
        Path to data/raw/github_prs.json
    jira_path:
        Path to data/raw/jira_tickets.json
    output_path:
        Where to write data/processed/normalized_events.json
    max_events:
        If > 0, truncate the merged event list to this size (useful for quick
        testing without processing the entire dataset).
    """

    def __init__(
        self,
        slack_path: Path,
        github_path: Path,
        jira_path: Path,
        output_path: Path,
        max_events: int = 0,
    ) -> None:
        self.slack_path = slack_path
        self.github_path = github_path
        self.jira_path = jira_path
        self.output_path = output_path
        self.max_events = max_events
        self._events: List[RawEvent] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> List[RawEvent]:
        """
        Execute the full ingestion pipeline.

        Steps
        ─────
        1. Load from each source.
        2. Merge into a single list.
        3. Normalise each event (timestamps, text).
        4. Optionally truncate.
        5. Persist to disk.

        Returns
        -------
        List[RawEvent]
            All normalised events (before any optional truncation is applied
            to the returned list).
        """
        logger.info("IngestionPipeline: starting ingestion from all sources")

        # ── Step 1: load ──────────────────────────────────────────────────────
        slack_events = self._load_source(SlackLoader(self.slack_path), "Slack")
        github_events = self._load_source(GitHubLoader(self.github_path), "GitHub")
        jira_events = self._load_source(JiraLoader(self.jira_path), "Jira")

        # ── Step 2: merge ─────────────────────────────────────────────────────
        all_events: List[RawEvent] = slack_events + github_events + jira_events
        logger.info("IngestionPipeline: merged %d total events", len(all_events))

        # ── Step 3: normalise ─────────────────────────────────────────────────
        normalised = [self._normalise(evt) for evt in all_events]
        normalised = [e for e in normalised if e is not None]  # drop None on error

        # ── Step 4: optional truncation ───────────────────────────────────────
        if self.max_events > 0:
            logger.info("IngestionPipeline: truncating to %d events", self.max_events)
            normalised = normalised[: self.max_events]

        self._events = normalised

        # ── Step 5: persist ───────────────────────────────────────────────────
        self._save(normalised)

        logger.info(
            "IngestionPipeline: complete – %d normalised events saved to %s",
            len(normalised),
            self.output_path,
        )
        return normalised

    def to_llama_documents(
        self, events: Optional[List[RawEvent]] = None
    ) -> List:
        """
        Convert RawEvents into LlamaIndex Document objects.

        Each Document carries the event content as its text, and all
        provenance fields in its metadata.  The extraction pipeline uses
        these Documents to feed text to the LLM.

        Parameters
        ----------
        events:
            List of events to convert.  Defaults to self._events if None.

        Returns
        -------
        List[LlamaDocument] | List[dict]
            LlamaIndex Documents when llama-index is installed; otherwise
            plain dicts so the pipeline can still run.
        """
        events = events or self._events
        docs = []
        for evt in events:
            meta = {
                "source": evt.source.value,
                "source_id": evt.source_id,
                "author": evt.author,
                "timestamp": evt.timestamp.isoformat(),
                "channel": evt.channel or "",
                "thread_id": evt.thread_id or "",
                "title": evt.title or "",
                "labels": ",".join(evt.labels),
            }
            if _LLAMA_AVAILABLE:
                docs.append(
                    LlamaDocument(
                        text=evt.content,
                        metadata=meta,
                        id_=evt.source_id,
                    )
                )
            else:
                # Fallback dict representation
                docs.append({"text": evt.content, "metadata": meta, "id": evt.source_id})
        return docs

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _load_source(loader, name: str) -> List[RawEvent]:
        """Run a loader and return its events; log but don't crash on error."""
        try:
            return loader.run()
        except FileNotFoundError as exc:
            logger.error("IngestionPipeline: %s file not found – %s", name, exc)
            return []
        except Exception as exc:
            logger.error("IngestionPipeline: %s loader failed – %s", name, exc)
            return []

    @staticmethod
    def _normalise(event: RawEvent) -> Optional[RawEvent]:
        """
        Apply normalisation rules to a single RawEvent in-place.

        - Ensure timestamp is UTC-aware.
        - Strip/collapse whitespace in content.
        - Remove control characters from content.
        """
        try:
            # Timestamp → UTC
            if event.timestamp.tzinfo is None:
                event.timestamp = event.timestamp.replace(tzinfo=timezone.utc)
            else:
                event.timestamp = event.timestamp.astimezone(timezone.utc)

            # Text cleaning
            content = event.content
            content = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", content)  # control chars
            content = re.sub(r"\s+", " ", content).strip()

            if not content:
                logger.warning("IngestionPipeline: dropping event %s – empty after cleaning", event.source_id)
                return None

            # Rebuild with cleaned content (Pydantic models are immutable by default,
            # so we use model_copy to avoid mutation issues)
            event = event.model_copy(update={"content": content})
            return event

        except Exception as exc:
            logger.error("IngestionPipeline: normalisation error for %s – %s", event.source_id, exc)
            return None

    def _save(self, events: List[RawEvent]) -> None:
        """Persist normalised events to JSON."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        serialisable = []
        for evt in events:
            d = evt.model_dump()
            # datetime → ISO string for JSON serialisation
            d["timestamp"] = evt.timestamp.isoformat()
            serialisable.append(d)

        with open(self.output_path, "w", encoding="utf-8") as fh:
            json.dump(serialisable, fh, indent=2, ensure_ascii=False, default=str)

        logger.info("IngestionPipeline: saved %d events → %s", len(events), self.output_path)
