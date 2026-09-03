"""
src/graph_prep/normalizer.py
─────────────────────────────
Entity, Relation, and Timestamp Normalization.

Normalisation philosophy
─────────────────────────
* Entity names → deterministic, lowercase, underscore-separated canonical_name.
  The original display_name is always preserved alongside.

* Technology aliases → a curated dictionary maps well-known variants to a
  canonical form.  Only explicitly listed aliases are merged — we do NOT
  perform fuzzy/aggressive matching that could inadvertently merge different
  entities.

* Relations → uppercased SNAKE_CASE.  A small synonym dictionary canonicalises
  common misspellings / alternate forms.

* Timestamps → UTC ISO-8601 string: "YYYY-MM-DDTHH:MM:SS+00:00".

Design decision — no destructive merges
─────────────────────────────────────────
  "AWS" and "AWS Cloud" are treated as the same canonical entity because the
  alias dictionary explicitly declares it.  But "AWS" and "GCP" are never
  merged just because both are cloud providers.  Normalization is
  conservative by design.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Technology alias dictionary
# Keys   → lowercase representations the extractor might produce
# Values → canonical_name that will appear in graph_ready_triples.json
# ─────────────────────────────────────────────────────────────────────────────

_TECH_ALIASES: Dict[str, str] = {
    # AWS variants
    "amazon web services": "aws",
    "amazon aws": "aws",
    "aws cloud": "aws",
    "amazon s3": "aws_s3",
    "aws s3": "aws_s3",
    "s3": "aws_s3",
    "amazon rds": "aws_rds",
    "aws rds": "aws_rds",
    "rds": "aws_rds",
    "aws eks": "aws_eks",
    "amazon eks": "aws_eks",
    "eks": "aws_eks",
    # GCP variants
    "google cloud platform": "gcp",
    "google cloud": "gcp",
    "gcloud": "gcp",
    # GCP services
    "cloud sql": "cloudsql",
    "google cloud sql": "cloudsql",
    "cloudsql": "cloudsql",
    "gcs": "gcs",
    "google cloud storage": "gcs",
    "gke": "gke",
    "google kubernetes engine": "gke",
    "cloud run": "cloud_run",
    "google cloud run": "cloud_run",
    "bigquery": "bigquery",
    "google bigquery": "bigquery",
    # GCS+CloudSQL compound
    "gcs and cloudsql": "gcs_and_cloudsql",
    "gcs and cloud sql": "gcs_and_cloudsql",
    # Kubernetes
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    # Docker
    "docker": "docker",
    # Terraform
    "terraform": "terraform",
    # DataDog
    "datadog": "datadog",
    "data dog": "datadog",
    # Python
    "python": "python",
    # PostgreSQL
    "postgresql": "postgresql",
    "postgres": "postgresql",
    # Redis
    "redis": "redis",
    # Kafka
    "apache kafka": "kafka",
    "kafka": "kafka",
}

# ─────────────────────────────────────────────────────────────────────────────
# Relation synonym dictionary
# Maps non-standard / misspelled relation strings → canonical RelationType value
# ─────────────────────────────────────────────────────────────────────────────

_RELATION_SYNONYMS: Dict[str, str] = {
    # Common misspellings / alternate forms
    "COMMITED_CODE": "COMMITTED_CODE",
    "COMMIT_CODE": "COMMITTED_CODE",
    "COMMITTED_TO": "COMMITTED_CODE",
    "ADVOCATE_FOR": "ADVOCATED_FOR",
    "ADVOCATING_FOR": "ADVOCATED_FOR",
    "ARGUE_AGAINST": "ARGUED_AGAINST",
    "ARGUING_AGAINST": "ARGUED_AGAINST",
    "RAISE_CONCERN": "RAISED_CONCERN",
    "RAISING_CONCERN": "RAISED_CONCERN",
    "RAISING_CONCERNS": "RAISED_CONCERN",
    "MIGRATE_TO": "MIGRATED_TO",
    "MIGRATING_TO": "MIGRATED_TO",
    "ASSIGN_TO": "ASSIGNED_TO",
    "REPORT_BUG": "REPORTED_BUG",
    "REPORTING_BUG": "REPORTED_BUG",
    "BLOCK": "BLOCKED_BY",
    "BLOCKS": "BLOCKED_BY",
    "RELATE_TO": "RELATED_TO",
    "DEPRECATE": "DEPRECATED",
    "ENROLL_IN": "ENROLLED_IN",
    "APPROVES": "APPROVED",
    "IMPLEMENT": "IMPLEMENTED",
    "IMPLEMENTS": "IMPLEMENTED",
    "DECIDE": "DECIDED",
    "DECIDES": "DECIDED",
    "REVIEW": "REVIEWED",
    "REVIEWS": "REVIEWED",
    "FIX": "FIXED",
    "FIXES": "FIXED",
}


# ─────────────────────────────────────────────────────────────────────────────
# Entity Normalizer
# ─────────────────────────────────────────────────────────────────────────────


class EntityNormalizer:
    """
    Normalise entity names, producing both a canonical_name and display_name.

    The canonical_name is suitable for graph node identity keys.
    The display_name is the best human-readable form for UI rendering.

    Rules applied (in order)
    ────────────────────────
    1. Look up the lowercase form in the technology alias dictionary.
    2. If not found, convert the raw name to lowercase snake_case.
    3. Display name = original stripped value (title-cased only if all-caps).
    """

    def normalize(self, name: str) -> Tuple[str, str]:
        """
        Return (canonical_name, display_name) for *name*.

        Parameters
        ──────────
        name : str
            Raw entity name as produced by the LLM extractor.

        Returns
        ───────
        (canonical_name, display_name)
        """
        if not name or not name.strip():
            return ("", "")

        raw = name.strip()

        # Display name: if the original is ALL-CAPS convert to Title Case,
        # otherwise keep as-is (preserves "Arun Sharma", "GCP", "AWS").
        if raw.isupper() and len(raw) > 3:
            display = raw.title()
        else:
            display = raw

        lower = raw.lower()

        # Step 1 — technology alias lookup
        canonical = _TECH_ALIASES.get(lower)
        if canonical:
            logger.debug("Entity alias: '%s' → '%s'", raw, canonical)
            return (canonical, display)

        # Step 2 — generic snake_case conversion
        canonical = _to_snake_case(raw)
        return (canonical, display)


# ─────────────────────────────────────────────────────────────────────────────
# Relation Normalizer
# ─────────────────────────────────────────────────────────────────────────────


class RelationNormalizer:
    """
    Normalise relation labels to consistent ALL_CAPS_SNAKE_CASE.

    Steps
    ─────
    1. Strip and uppercase the input.
    2. Replace spaces and hyphens with underscores.
    3. Look up in the synonym dictionary for canonical mapping.
    """

    def normalize(self, relation: str) -> str:
        """Return the canonical relation label for *relation*."""
        if not relation or not relation.strip():
            return "UNKNOWN"

        # Uppercase + underscore-clean
        norm = relation.strip().upper().replace(" ", "_").replace("-", "_")
        # Collapse multiple underscores
        norm = re.sub(r"_+", "_", norm).strip("_")

        # Apply synonym mapping
        canonical = _RELATION_SYNONYMS.get(norm, norm)
        if canonical != norm:
            logger.debug("Relation synonym: '%s' → '%s'", norm, canonical)

        return canonical


# ─────────────────────────────────────────────────────────────────────────────
# Timestamp Normalizer
# ─────────────────────────────────────────────────────────────────────────────


class TimestampNormalizer:
    """
    Normalise timestamps to UTC ISO-8601 string format.

    Output format: "YYYY-MM-DDTHH:MM:SS+00:00"

    Handles
    ───────
    * datetime objects (aware or naive)
    * ISO strings with or without timezone offset
    * Naive timestamps are assumed to be UTC
    """

    # Parsing formats to attempt in order
    _FORMATS = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    def normalize(self, timestamp: Any) -> str:
        """
        Return a UTC ISO-8601 string for *timestamp*.

        If the timestamp cannot be parsed, the original string representation
        is returned unchanged (so no temporal data is lost).
        """
        if isinstance(timestamp, datetime):
            return self._to_utc_iso(timestamp)

        if not isinstance(timestamp, str) or not timestamp.strip():
            logger.warning("Timestamp is missing or not a string: %r — keeping as-is", timestamp)
            return str(timestamp) if timestamp is not None else ""

        # Try Python's fromisoformat first (handles +HH:MM offsets cleanly)
        try:
            dt = datetime.fromisoformat(timestamp.strip())
            return self._to_utc_iso(dt)
        except (ValueError, TypeError):
            pass

        # Try explicit format list
        ts_clean = timestamp.strip().replace("Z", "+00:00")
        for fmt in self._FORMATS:
            try:
                dt = datetime.strptime(ts_clean, fmt)
                return self._to_utc_iso(dt)
            except ValueError:
                continue

        # Fallback — return original to preserve temporal data
        logger.warning(
            "Could not parse timestamp '%s' to UTC ISO-8601; keeping original value.",
            timestamp,
        )
        return timestamp.strip()

    @staticmethod
    def _to_utc_iso(dt: datetime) -> str:
        """Convert *dt* to UTC and return ISO-8601 string."""
        if dt.tzinfo is None:
            # Naive → assume UTC
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _to_snake_case(text: str) -> str:
    """
    Convert *text* to a deterministic, lowercase snake_case identifier.

    Examples
    ────────
    "Arun Sharma"  → "arun_sharma"
    "ARUN SHARMA"  → "arun_sharma"
    "arun_sharma"  → "arun_sharma"
    "GCP"          → "gcp"
    "AWS Cloud"    → "aws_cloud"
    "auth-service" → "auth_service"
    """
    # Normalise unicode (e.g. é → e) then encode to ASCII
    text = unicodedata.normalize("NFKD", text).encode("ascii", errors="ignore").decode()

    # Replace common separators with a single space, then strip
    text = re.sub(r"[\s\-/\\]+", " ", text).strip()

    # Remove characters that are not word characters or spaces
    text = re.sub(r"[^\w\s]", "", text)

    # Lowercase and replace spaces with underscores
    text = text.lower().replace(" ", "_")

    # Collapse repeated underscores
    text = re.sub(r"_+", "_", text).strip("_")

    return text or "unknown"
