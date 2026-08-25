"""
src/ingestion/jira_loader.py
────────────────────────────
JiraLoader parses the mock Jira project export.

Each of the following becomes a separate RawEvent:
  - Ticket description  (authored by the reporter)
  - Individual comments  (authored by the comment author)

This lets the extraction pipeline attribute decisions, concerns, and
actions to specific engineers at specific points in time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.ingestion.base import BaseDataLoader
from src.schemas.graph import DataSource, RawEvent

logger = logging.getLogger(__name__)


class JiraLoader(BaseDataLoader):
    """
    Loads data from ``data/raw/jira_tickets.json``.

    Expected JSON structure::

        {
            "project": "CLOUD",
            "tickets": [
                {
                    "ticket_id": "jira_001",
                    "key": "CLOUD-98",
                    "title": "...",
                    "type": "Story",
                    "status": "Done",
                    "assignee": "arun_sharma",
                    "reporter": "arun_sharma",
                    "created_at": "...",
                    "resolved_at": "...",
                    "description": "...",
                    "labels": [...],
                    "comments": [...]
                }
            ]
        }
    """

    def __init__(self, file_path) -> None:
        super().__init__(file_path, DataSource.JIRA)

    # ── Abstract implementation ───────────────────────────────────────────────

    def load(self) -> List[Dict[str, Any]]:
        """
        Flatten tickets and their comments into a single list.

        Each dict has an injected ``event_subtype``:
        ``"ticket_description"`` | ``"ticket_comment"``
        """
        data = self.read_json()
        records: List[Dict[str, Any]] = []
        project = data.get("project", "unknown")

        for ticket in data.get("tickets", []):
            ticket_id = ticket["ticket_id"]
            ticket_key = ticket.get("key", "")
            ticket_title = ticket.get("title", "")
            ticket_labels = ticket.get("labels", [])
            ticket_status = ticket.get("status", "")
            ticket_type = ticket.get("type", "")
            ticket_priority = ticket.get("priority", "")
            assignee = ticket.get("assignee", "unknown")
            reporter = ticket.get("reporter", "unknown")
            linked_issues = ticket.get("linked_issues", [])

            # ── 1. Ticket description ─────────────────────────────────────
            description = ticket.get("description", "").strip()
            if description:
                records.append({
                    "event_subtype": "ticket_description",
                    "source_id": ticket_id,
                    "author": reporter,
                    "content": f"[{ticket_key}] {ticket_title}\n\n{description}",
                    "timestamp": ticket.get("created_at", ""),
                    "title": ticket_title,
                    "labels": ticket_labels,
                    "project": project,
                    "ticket_id": ticket_id,
                    "ticket_key": ticket_key,
                    "ticket_type": ticket_type,
                    "ticket_status": ticket_status,
                    "ticket_priority": ticket_priority,
                    "assignee": assignee,
                    "reporter": reporter,
                    "resolved_at": ticket.get("resolved_at"),
                    "linked_issues": linked_issues,
                })

            # ── 2. Individual comments ────────────────────────────────────
            for comment in ticket.get("comments", []):
                records.append({
                    "event_subtype": "ticket_comment",
                    "source_id": comment.get("comment_id", ticket_id + "_c"),
                    "author": comment.get("author", "unknown"),
                    "content": self.clean_text(comment.get("body", "")),
                    "timestamp": comment.get("timestamp", ticket.get("created_at", "")),
                    "title": ticket_title,
                    "labels": ticket_labels,
                    "project": project,
                    "ticket_id": ticket_id,
                    "ticket_key": ticket_key,
                    "ticket_type": ticket_type,
                    "ticket_status": ticket_status,
                    "ticket_priority": ticket_priority,
                    "assignee": assignee,
                    "linked_issues": linked_issues,
                })

        logger.debug("JiraLoader: flattened %d records from %d tickets", len(records), len(data.get("tickets", [])))
        return records

    def to_events(self, raw_records: List[Dict[str, Any]]) -> List[RawEvent]:
        """Convert flat Jira record dicts into RawEvent objects."""
        events: List[RawEvent] = []

        for record in raw_records:
            try:
                content = record.get("content", "").strip()
                if not content:
                    continue

                timestamp = self._parse_timestamp(record.get("timestamp", ""))

                event = RawEvent(
                    source=DataSource.JIRA,
                    source_id=record["source_id"],
                    author=record.get("author", "unknown"),
                    content=content,
                    timestamp=timestamp,
                    channel=record.get("project"),            # project key in channel slot
                    thread_id=record.get("ticket_id"),        # ticket is the thread
                    title=record.get("title"),
                    labels=record.get("labels", []),
                    metadata={
                        "event_subtype": record.get("event_subtype", ""),
                        "ticket_id": record.get("ticket_id", ""),
                        "ticket_key": record.get("ticket_key", ""),
                        "ticket_type": record.get("ticket_type", ""),
                        "ticket_status": record.get("ticket_status", ""),
                        "ticket_priority": record.get("ticket_priority", ""),
                        "assignee": record.get("assignee", ""),
                        "resolved_at": record.get("resolved_at"),
                        "linked_issues": record.get("linked_issues", []),
                    },
                )
                events.append(event)

            except Exception as exc:
                logger.error(
                    "JiraLoader: failed to convert record %s – %s",
                    record.get("source_id", "?"),
                    exc,
                )

        return events

    @staticmethod
    def _parse_timestamp(ts_str: str) -> datetime:
        if not ts_str:
            return datetime.now(tz=timezone.utc)
        ts_str = ts_str.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(ts_str)
        except ValueError:
            logger.warning("JiraLoader: cannot parse timestamp '%s', using now()", ts_str)
            return datetime.now(tz=timezone.utc)
