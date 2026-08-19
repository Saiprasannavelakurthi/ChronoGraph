"""
src/ingestion/github_loader.py
──────────────────────────────
GitHubLoader parses the mock GitHub PR export.

Each of the following is converted into a separate RawEvent:
  - PR description  (authored by the PR creator)
  - Individual commits  (authored by the committer)
  - Review comments  (authored by the reviewer)

This fine-grained decomposition lets the extraction pipeline attribute
specific statements to specific engineers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.ingestion.base import BaseDataLoader
from src.schemas.graph import DataSource, RawEvent

logger = logging.getLogger(__name__)


class GitHubLoader(BaseDataLoader):
    """
    Loads data from ``data/raw/github_prs.json``.

    Expected JSON structure::

        {
            "repository": "acme-platform",
            "pull_requests": [
                {
                    "pr_id": "github_pr_001",
                    "number": 78,
                    "title": "...",
                    "author": "vikram_patel",
                    "reviewers": [...],
                    "state": "merged",
                    "created_at": "...",
                    "merged_at": "...",
                    "description": "...",
                    "labels": [...],
                    "commits": [...],
                    "review_comments": [...]
                }
            ]
        }
    """

    def __init__(self, file_path) -> None:
        super().__init__(file_path, DataSource.GITHUB)

    # ── Abstract implementation ───────────────────────────────────────────────

    def load(self) -> List[Dict[str, Any]]:
        """
        Flatten PRs, commits, and review comments into a single list.

        Each returned dict has an injected ``event_subtype`` field:
        ``"pr_description"`` | ``"commit"`` | ``"review_comment"``
        """
        data = self.read_json()
        records: List[Dict[str, Any]] = []
        repository = data.get("repository", "unknown")

        for pr in data.get("pull_requests", []):
            pr_id = pr["pr_id"]
            pr_title = pr.get("title", "")
            pr_labels = pr.get("labels", [])
            pr_number = pr.get("number", 0)

            # ── 1. PR description ─────────────────────────────────────────
            description = pr.get("description", "").strip()
            if description:
                records.append({
                    "event_subtype": "pr_description",
                    "source_id": pr_id,
                    "author": pr.get("author", "unknown"),
                    "content": f"[PR #{pr_number}] {pr_title}\n\n{description}",
                    "timestamp": pr.get("created_at", ""),
                    "title": pr_title,
                    "labels": pr_labels,
                    "repository": repository,
                    "pr_id": pr_id,
                    "pr_number": pr_number,
                    "state": pr.get("state", ""),
                    "reviewers": pr.get("reviewers", []),
                    "merged_at": pr.get("merged_at"),
                })

            # ── 2. Individual commits ─────────────────────────────────────
            for commit in pr.get("commits", []):
                records.append({
                    "event_subtype": "commit",
                    "source_id": commit.get("commit_sha", pr_id + "_commit"),
                    "author": commit.get("author", pr.get("author", "unknown")),
                    "content": self.clean_text(commit.get("message", "")),
                    "timestamp": commit.get("timestamp", pr.get("created_at", "")),
                    "title": pr_title,
                    "labels": pr_labels,
                    "repository": repository,
                    "pr_id": pr_id,
                    "pr_number": pr_number,
                })

            # ── 3. Review comments ────────────────────────────────────────
            for rc in pr.get("review_comments", []):
                records.append({
                    "event_subtype": "review_comment",
                    "source_id": rc.get("comment_id", pr_id + "_rc"),
                    "author": rc.get("author", "unknown"),
                    "content": self.clean_text(rc.get("body", "")),
                    "timestamp": rc.get("timestamp", pr.get("created_at", "")),
                    "title": pr_title,
                    "labels": pr_labels,
                    "repository": repository,
                    "pr_id": pr_id,
                    "pr_number": pr_number,
                    "file": rc.get("file", ""),
                    "line": rc.get("line"),
                })

        logger.debug("GitHubLoader: flattened %d records from %d PRs", len(records), len(data.get("pull_requests", [])))
        return records

    def to_events(self, raw_records: List[Dict[str, Any]]) -> List[RawEvent]:
        """Convert flat GitHub record dicts into RawEvent objects."""
        events: List[RawEvent] = []

        for record in raw_records:
            try:
                content = record.get("content", "").strip()
                if not content:
                    continue

                timestamp = self._parse_timestamp(record.get("timestamp", ""))

                event = RawEvent(
                    source=DataSource.GITHUB,
                    source_id=record["source_id"],
                    author=record.get("author", "unknown"),
                    content=content,
                    timestamp=timestamp,
                    channel=record.get("repository"),          # repo name in channel slot
                    thread_id=record.get("pr_id"),             # PR is the thread
                    title=record.get("title"),
                    labels=record.get("labels", []),
                    metadata={
                        "event_subtype": record.get("event_subtype", ""),
                        "pr_id": record.get("pr_id", ""),
                        "pr_number": record.get("pr_number"),
                        "state": record.get("state", ""),
                        "reviewers": record.get("reviewers", []),
                        "merged_at": record.get("merged_at"),
                        "file": record.get("file", ""),
                        "line": record.get("line"),
                    },
                )
                events.append(event)

            except Exception as exc:
                logger.error(
                    "GitHubLoader: failed to convert record %s – %s",
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
            logger.warning("GitHubLoader: cannot parse timestamp '%s', using now()", ts_str)
            return datetime.now(tz=timezone.utc)
