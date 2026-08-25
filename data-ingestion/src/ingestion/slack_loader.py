"""
src/ingestion/slack_loader.py
─────────────────────────────
SlackLoader parses the mock Slack workspace export and converts every
message (including thread replies) into a standardised RawEvent.

Each Slack message maps to exactly one RawEvent so the extraction pipeline
can reason about individual utterances rather than entire channels.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.ingestion.base import BaseDataLoader
from src.schemas.graph import DataSource, RawEvent

logger = logging.getLogger(__name__)


class SlackLoader(BaseDataLoader):
    """
    Loads data from ``data/raw/slack_history.json``.

    Expected JSON structure::

        {
            "workspace": "...",
            "channels": [
                {
                    "channel_id": "C001",
                    "channel_name": "infra-migration",
                    "messages": [
                        {
                            "message_id": "slack_001",
                            "author": "arun_sharma",
                            "timestamp": "2023-03-15T10:30:00Z",
                            "text": "...",
                            "thread_ts": null
                        },
                        ...
                    ]
                }
            ]
        }
    """

    def __init__(self, file_path) -> None:
        super().__init__(file_path, DataSource.SLACK)

    # ── Abstract implementation ───────────────────────────────────────────────

    def load(self) -> List[Dict[str, Any]]:
        """
        Flatten all channel messages into a single list of raw message dicts.

        Each dict is augmented with ``channel_id`` and ``channel_name`` so
        that the context is not lost when messages are flattened.
        """
        data = self.read_json()
        records: List[Dict[str, Any]] = []

        channels = data.get("channels", [])
        for channel in channels:
            channel_id = channel.get("channel_id", "unknown")
            channel_name = channel.get("channel_name", "unknown")

            for msg in channel.get("messages", []):
                records.append(
                    {
                        **msg,
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "workspace": data.get("workspace", ""),
                    }
                )

        logger.debug("SlackLoader: flattened %d messages from %d channels", len(records), len(channels))
        return records

    def to_events(self, raw_records: List[Dict[str, Any]]) -> List[RawEvent]:
        """Convert flat Slack message dicts into RawEvent objects."""
        events: List[RawEvent] = []

        for record in raw_records:
            try:
                # Parse timestamp – Slack exports ISO-8601 with a Z suffix
                ts_str: str = record.get("timestamp", "")
                timestamp = self._parse_timestamp(ts_str)

                content = self.clean_text(record.get("text", ""))
                if not content:
                    logger.warning("SlackLoader: skipping empty message %s", record.get("message_id"))
                    continue

                event = RawEvent(
                    source=DataSource.SLACK,
                    source_id=record["message_id"],
                    author=record.get("author", "unknown"),
                    content=content,
                    timestamp=timestamp,
                    channel=record.get("channel_name"),
                    thread_id=record.get("thread_ts"),   # None for top-level messages
                    labels=[],
                    metadata={
                        "workspace": record.get("workspace", ""),
                        "channel_id": record.get("channel_id", ""),
                        "display_name": record.get("display_name", ""),
                        "reactions": record.get("reactions", []),
                    },
                )
                events.append(event)

            except Exception as exc:
                logger.error(
                    "SlackLoader: failed to convert message %s – %s",
                    record.get("message_id", "?"),
                    exc,
                )

        return events

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_timestamp(ts_str: str) -> datetime:
        """Parse an ISO-8601 timestamp string into a timezone-aware datetime."""
        if not ts_str:
            return datetime.now(tz=timezone.utc)
        # Handle trailing Z → +00:00
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
