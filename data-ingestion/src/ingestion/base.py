"""
src/ingestion/base.py
─────────────────────
Abstract base class for all ChronoGraph data loaders.

Every concrete loader (SlackLoader, GitHubLoader, JiraLoader) inherits from
BaseDataLoader and must implement the two abstract methods:
  - load()     → parse the raw JSON into native Python dicts
  - to_events() → convert those dicts into validated RawEvent objects
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from src.schemas.graph import DataSource, RawEvent

logger = logging.getLogger(__name__)


class BaseDataLoader(ABC):
    """
    Abstract base for all data loaders.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the source JSON file.
    source:
        The DataSource enum value that identifies this loader's origin system.
    """

    def __init__(self, file_path: Path, source: DataSource) -> None:
        self.file_path = Path(file_path)
        self.source = source
        self._raw_data: Dict[str, Any] = {}

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def load(self) -> List[Dict[str, Any]]:
        """
        Read the raw JSON file and return a list of raw record dicts.

        Subclasses must open self.file_path, parse the JSON, and return a
        flat list where each item represents one logical event (message,
        commit, ticket comment, etc.).
        """
        ...

    @abstractmethod
    def to_events(self, raw_records: List[Dict[str, Any]]) -> List[RawEvent]:
        """
        Convert a list of raw record dicts into validated RawEvent objects.

        Parameters
        ----------
        raw_records:
            The output of self.load().

        Returns
        -------
        List[RawEvent]
            Validated, normalised events ready for the preprocessing pipeline.
        """
        ...

    # ── Concrete helpers ──────────────────────────────────────────────────────

    def read_json(self) -> Dict[str, Any]:
        """Load and return the raw JSON file as a Python dict."""
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"[{self.__class__.__name__}] File not found: {self.file_path}"
            )
        logger.info(
            "%s reading file: %s", self.__class__.__name__, self.file_path
        )
        with open(self.file_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def run(self) -> List[RawEvent]:
        """
        Convenience method that executes the full load → convert pipeline.

        Returns
        -------
        List[RawEvent]
            All validated events from this source.
        """
        raw_records = self.load()
        events = self.to_events(raw_records)
        logger.info(
            "%s produced %d events from %s",
            self.__class__.__name__,
            len(events),
            self.file_path.name,
        )
        return events

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def clean_text(text: str) -> str:
        """Strip leading/trailing whitespace and collapse internal whitespace."""
        import re
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text
