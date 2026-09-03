"""
src/retrieval/errors.py
───────────────────────
Custom exception hierarchy for the ChronoGraph Retrieval module.

Defines clear, domain-specific exceptions for retrieval data handling,
file validation, and service execution.
"""

from __future__ import annotations


class RetrievalError(Exception):
    """Base exception for all retrieval-related errors."""


class RetrievalServiceError(RetrievalError):
    """Base exception for retrieval service failures."""


class RetrievalDataError(RetrievalServiceError):
    """Base exception for retrieval data loading and validation failures."""


class RetrievalDataNotFoundError(RetrievalDataError):
    """Raised when required retrieval data files are not found on disk."""


class RetrievalDataCorruptedError(RetrievalDataError):
    """Raised when retrieval data is corrupted, invalid JSON, or unparseable."""


class RetrievalDataFormatError(RetrievalDataCorruptedError):
    """Raised when retrieval data has an invalid format, schema, or unexpected top-level structure."""
