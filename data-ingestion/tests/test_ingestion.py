"""
tests/test_ingestion.py
────────────────────────
Unit tests for the ChronoGraph data ingestion pipeline.

Tests cover:
  - SlackLoader: file loading, event conversion, timestamp parsing
  - GitHubLoader: PR + commit + review comment flattening
  - JiraLoader: ticket description + comment conversion
  - IngestionPipeline: merge, normalise, persist

All tests use the actual mock JSON files in data/raw/ so they also
validate the integrity of the mock datasets.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Project root on path via conftest or direct import
from src.ingestion.github_loader import GitHubLoader
from src.ingestion.jira_loader import JiraLoader
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.slack_loader import SlackLoader
from src.schemas.graph import DataSource, RawEvent

# ── Paths to mock datasets ────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SLACK_PATH = _PROJECT_ROOT / "data" / "raw" / "slack_history.json"
GITHUB_PATH = _PROJECT_ROOT / "data" / "raw" / "github_prs.json"
JIRA_PATH = _PROJECT_ROOT / "data" / "raw" / "jira_tickets.json"


# ─────────────────────────────────────────────────────────────────────────────
# SlackLoader tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSlackLoader:

    def test_slack_file_exists(self):
        assert SLACK_PATH.exists(), f"Mock Slack file missing: {SLACK_PATH}"

    def test_slack_load_returns_records(self):
        loader = SlackLoader(SLACK_PATH)
        records = loader.load()
        assert len(records) > 0, "SlackLoader.load() returned no records"

    def test_slack_records_have_required_fields(self):
        loader = SlackLoader(SLACK_PATH)
        records = loader.load()
        for rec in records:
            assert "message_id" in rec
            assert "author" in rec
            assert "text" in rec
            assert "timestamp" in rec
            assert "channel_name" in rec

    def test_slack_to_events_returns_raw_events(self):
        loader = SlackLoader(SLACK_PATH)
        events = loader.run()
        assert len(events) > 0
        for evt in events:
            assert isinstance(evt, RawEvent)
            assert evt.source == DataSource.SLACK

    def test_slack_event_timestamps_are_utc(self):
        loader = SlackLoader(SLACK_PATH)
        events = loader.run()
        for evt in events:
            assert evt.timestamp.tzinfo is not None, (
                f"Event {evt.source_id} has naive timestamp"
            )

    def test_slack_event_content_not_empty(self):
        loader = SlackLoader(SLACK_PATH)
        events = loader.run()
        for evt in events:
            assert evt.content.strip() != "", (
                f"Event {evt.source_id} has empty content"
            )

    def test_slack_event_preserves_source_id(self):
        loader = SlackLoader(SLACK_PATH)
        events = loader.run()
        source_ids = {evt.source_id for evt in events}
        # Our mock data has slack_001 through slack_016
        assert "slack_001" in source_ids

    def test_slack_event_preserves_author(self):
        loader = SlackLoader(SLACK_PATH)
        events = loader.run()
        authors = {evt.author for evt in events}
        assert "arun_sharma" in authors

    def test_slack_thread_reply_has_thread_id(self):
        loader = SlackLoader(SLACK_PATH)
        events = loader.run()
        # slack_002 is a reply (thread_ts = "slack_001")
        thread_events = [e for e in events if e.source_id == "slack_002"]
        assert len(thread_events) == 1
        assert thread_events[0].thread_id == "slack_001"

    def test_slack_loader_file_not_found(self):
        loader = SlackLoader(Path("/nonexistent/path.json"))
        with pytest.raises(FileNotFoundError):
            loader.load()


# ─────────────────────────────────────────────────────────────────────────────
# GitHubLoader tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGitHubLoader:

    def test_github_file_exists(self):
        assert GITHUB_PATH.exists(), f"Mock GitHub file missing: {GITHUB_PATH}"

    def test_github_load_returns_records(self):
        loader = GitHubLoader(GITHUB_PATH)
        records = loader.load()
        assert len(records) > 0

    def test_github_records_contain_all_subtypes(self):
        loader = GitHubLoader(GITHUB_PATH)
        records = loader.load()
        subtypes = {r.get("event_subtype") for r in records}
        assert "pr_description" in subtypes
        assert "commit" in subtypes
        assert "review_comment" in subtypes

    def test_github_to_events_returns_raw_events(self):
        loader = GitHubLoader(GITHUB_PATH)
        events = loader.run()
        assert len(events) > 0
        for evt in events:
            assert isinstance(evt, RawEvent)
            assert evt.source == DataSource.GITHUB

    def test_github_event_author_preserved(self):
        loader = GitHubLoader(GITHUB_PATH)
        events = loader.run()
        authors = {evt.author for evt in events}
        assert "vikram_patel" in authors
        assert "rohan_mehta" in authors

    def test_github_pr_description_has_title(self):
        loader = GitHubLoader(GITHUB_PATH)
        events = loader.run()
        pr_desc_events = [e for e in events if e.metadata.get("event_subtype") == "pr_description"]
        assert len(pr_desc_events) > 0
        for evt in pr_desc_events:
            assert evt.title is not None and evt.title != ""

    def test_github_event_source_id_preserved(self):
        loader = GitHubLoader(GITHUB_PATH)
        events = loader.run()
        source_ids = {evt.source_id for evt in events}
        assert "github_pr_001" in source_ids

    def test_github_timestamps_are_utc(self):
        loader = GitHubLoader(GITHUB_PATH)
        events = loader.run()
        for evt in events:
            assert evt.timestamp.tzinfo is not None

    def test_github_labels_preserved(self):
        loader = GitHubLoader(GITHUB_PATH)
        events = loader.run()
        # PR 001 has label "migration"
        migration_events = [e for e in events if "migration" in e.labels]
        assert len(migration_events) > 0


# ─────────────────────────────────────────────────────────────────────────────
# JiraLoader tests
# ─────────────────────────────────────────────────────────────────────────────

class TestJiraLoader:

    def test_jira_file_exists(self):
        assert JIRA_PATH.exists(), f"Mock Jira file missing: {JIRA_PATH}"

    def test_jira_load_returns_records(self):
        loader = JiraLoader(JIRA_PATH)
        records = loader.load()
        assert len(records) > 0

    def test_jira_records_contain_both_subtypes(self):
        loader = JiraLoader(JIRA_PATH)
        records = loader.load()
        subtypes = {r.get("event_subtype") for r in records}
        assert "ticket_description" in subtypes
        assert "ticket_comment" in subtypes

    def test_jira_to_events_returns_raw_events(self):
        loader = JiraLoader(JIRA_PATH)
        events = loader.run()
        assert len(events) > 0
        for evt in events:
            assert isinstance(evt, RawEvent)
            assert evt.source == DataSource.JIRA

    def test_jira_ticket_key_in_metadata(self):
        loader = JiraLoader(JIRA_PATH)
        events = loader.run()
        keys = {evt.metadata.get("ticket_key") for evt in events}
        assert "CLOUD-98" in keys

    def test_jira_assignee_in_metadata(self):
        loader = JiraLoader(JIRA_PATH)
        events = loader.run()
        assignees = {evt.metadata.get("assignee") for evt in events}
        assert "arun_sharma" in assignees

    def test_jira_linked_issues_preserved(self):
        loader = JiraLoader(JIRA_PATH)
        events = loader.run()
        events_with_links = [
            e for e in events
            if e.metadata.get("linked_issues")
        ]
        assert len(events_with_links) > 0


# ─────────────────────────────────────────────────────────────────────────────
# IngestionPipeline tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIngestionPipeline:

    def _make_pipeline(self, tmp_path: Path) -> IngestionPipeline:
        output = tmp_path / "normalized_events.json"
        return IngestionPipeline(
            slack_path=SLACK_PATH,
            github_path=GITHUB_PATH,
            jira_path=JIRA_PATH,
            output_path=output,
        )

    def test_pipeline_produces_events(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path)
        events = pipeline.run()
        assert len(events) > 0

    def test_pipeline_events_from_all_sources(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path)
        events = pipeline.run()
        sources = {evt.source for evt in events}
        assert DataSource.SLACK in sources
        assert DataSource.GITHUB in sources
        assert DataSource.JIRA in sources

    def test_pipeline_saves_output_file(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline.run()
        output = tmp_path / "normalized_events.json"
        assert output.exists(), "normalized_events.json was not created"

    def test_pipeline_output_is_valid_json(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline.run()
        output = tmp_path / "normalized_events.json"
        with open(output, "r") as fh:
            data = json.load(fh)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_pipeline_output_events_have_required_fields(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline.run()
        output = tmp_path / "normalized_events.json"
        with open(output, "r") as fh:
            data = json.load(fh)
        required_fields = {"event_id", "source", "source_id", "author", "content", "timestamp"}
        for item in data:
            for field in required_fields:
                assert field in item, f"Missing field '{field}' in event: {item.get('source_id')}"

    def test_pipeline_normalised_content_no_leading_whitespace(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path)
        events = pipeline.run()
        for evt in events:
            assert evt.content == evt.content.strip()

    def test_pipeline_max_events_truncation(self, tmp_path):
        output = tmp_path / "normalized_events_truncated.json"
        pipeline = IngestionPipeline(
            slack_path=SLACK_PATH,
            github_path=GITHUB_PATH,
            jira_path=JIRA_PATH,
            output_path=output,
            max_events=5,
        )
        events = pipeline.run()
        assert len(events) == 5

    def test_pipeline_to_llama_documents(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path)
        events = pipeline.run()
        docs = pipeline.to_llama_documents(events)
        assert len(docs) == len(events)
        # Each doc should have text and metadata
        for doc in docs:
            if isinstance(doc, dict):
                assert "text" in doc
                assert "metadata" in doc
            else:
                # LlamaIndex Document
                assert hasattr(doc, "text")
                assert hasattr(doc, "metadata")

    def test_pipeline_raw_files_unchanged(self, tmp_path):
        """Ensure pipeline does not modify the original raw data files."""
        import hashlib

        def file_hash(path):
            return hashlib.md5(path.read_bytes()).hexdigest()

        slack_hash_before = file_hash(SLACK_PATH)
        github_hash_before = file_hash(GITHUB_PATH)
        jira_hash_before = file_hash(JIRA_PATH)

        pipeline = self._make_pipeline(tmp_path)
        pipeline.run()

        assert file_hash(SLACK_PATH) == slack_hash_before
        assert file_hash(GITHUB_PATH) == github_hash_before
        assert file_hash(JIRA_PATH) == jira_hash_before
