"""
src/extraction/fallback.py
──────────────────────────
Heuristic / rule-based fallback extractor.

This module allows ChronoGraph to run the pipeline WITHOUT:
  - An OpenAI or Groq API key
  - A running Ollama server
  - Any network access

How it works
────────────
The fallback uses a deterministic pattern-matching approach:
  1. Keyword → relation mapping (e.g. "suggest" → ADVOCATED_FOR).
  2. Author → subject entity.
  3. Technology / project keyword dictionary for object entities.

Results are clearly labelled with ``extraction_mode = ExtractionMode.FALLBACK``
so that downstream consumers (Neo4j loader) can distinguish heuristic
triples from LLM-generated ones.

Limitations
───────────
- Does not understand context or negation.
- May miss complex multi-hop relationships.
- Confidence scores are heuristic (not probabilistic).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.schemas.graph import (
    DataSource,
    EntityType,
    ExtractionMode,
    ExtractionResult,
    RawEvent,
    Triple,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Keyword dictionaries
# ─────────────────────────────────────────────────────────────────────────────

# Maps text patterns → (relation_label, base_confidence)
RELATION_PATTERNS: List[Tuple[re.Pattern, str, float]] = [
    # High-signal patterns first to ensure correct priority
    (re.compile(r"\b(urgent|critical security|vulnerability|race.condition)\w*\b", re.I),        "RAISED_CONCERN", 0.85),
    (re.compile(r"\b(suggest|advocat|recommend|propos|push for|argue for|support)\w*\b", re.I), "ADVOCATED_FOR", 0.80),
    (re.compile(r"\b(against|reject|disagree|skepti|argue against|oppos)\w*\b", re.I),          "ARGUED_AGAINST", 0.75),
    (re.compile(r"\b(commit|push\w* code|open\w* PR|merg\w* PR|submit\w* PR)\w*\b", re.I),      "COMMITTED_CODE", 0.85),
    (re.compile(r"\b(review\w*|approved?|LGTM|approv\w*)\b", re.I),                             "REVIEWED", 0.80),
    (re.compile(r"\b(assign\w*|own\w*|responsible for|lead\w*)\w*\b", re.I),                    "ASSIGNED_TO", 0.75),
    (re.compile(r"\b(migrat\w*|replac\w*|switch\w* to|moved?\s+to|transition)\w*\b", re.I),     "MIGRATED_TO", 0.82),
    (re.compile(r"\b(concern|flag\w*|warn\w*|risk|issue)\w*\b", re.I),                          "RAISED_CONCERN", 0.70),
    (re.compile(r"\b(decid\w*|decision|approv\w* the|formally\s+approv)\w*\b", re.I),           "DECIDED", 0.78),
    (re.compile(r"\b(implement\w*|built?|develop\w*|creat\w* the|complet\w*)\w*\b", re.I),      "IMPLEMENTED", 0.75),
    (re.compile(r"\b(report\w*|identify|identifi\w*|found|discover)\w*\b", re.I),               "REPORTED_BUG", 0.72),
    (re.compile(r"\b(fix\w*|patch\w*|resolv\w*|address\w*)\w*\b", re.I),                        "FIXED", 0.80),
    (re.compile(r"\b(deprecat\w*|remov\w*|drop\w*)\w*\b", re.I),                                "DEPRECATED", 0.78),
    (re.compile(r"\b(enroll\w*|train\w*|certif\w*)\w*\b", re.I),                                "ENROLLED_IN", 0.75),
]

# Technology and project keywords → (canonical name, EntityType)
TECH_KEYWORDS: Dict[str, Tuple[str, EntityType]] = {
    r"\bGCP\b":                            ("GCP", EntityType.TECHNOLOGY),
    r"\bGoogle Cloud\b":                   ("GCP", EntityType.TECHNOLOGY),
    r"\bGoogle Kubernetes Engine\b":       ("GKE", EntityType.TECHNOLOGY),
    r"\bGKE\b":                            ("GKE", EntityType.TECHNOLOGY),
    r"\bGoogle Cloud Storage\b":           ("GCS", EntityType.DATABASE),
    r"\bGCS\b":                            ("GCS", EntityType.DATABASE),
    r"\bCloud SQL\b":                      ("CloudSQL", EntityType.DATABASE),
    r"\bAWS\b":                            ("AWS", EntityType.TECHNOLOGY),
    r"\bAmazon Web Services\b":            ("AWS", EntityType.TECHNOLOGY),
    r"\bEKS\b":                            ("EKS", EntityType.TECHNOLOGY),
    r"\bS3\b":                             ("AWS_S3", EntityType.DATABASE),
    r"\bRDS\b":                            ("AWS_RDS", EntityType.DATABASE),
    r"\bKubernetes\b":                     ("Kubernetes", EntityType.TECHNOLOGY),
    r"\bDocker\b":                         ("Docker", EntityType.TECHNOLOGY),
    r"\bRedis\b":                          ("Redis", EntityType.DATABASE),
    r"\bPostgreSQL\b":                     ("PostgreSQL", EntityType.DATABASE),
    r"\bPostgres\b":                       ("PostgreSQL", EntityType.DATABASE),
    r"\bMongoDB\b":                        ("MongoDB", EntityType.DATABASE),
    r"\bJWT\b":                            ("JWT_authentication", EntityType.TECHNOLOGY),
    r"\bboto3\b":                          ("boto3", EntityType.TECHNOLOGY),
    r"\bauthentication.service\b":         ("authentication_service", EntityType.SERVICE),
    r"\bauth.service\b":                   ("authentication_service", EntityType.SERVICE),
    r"\bapi.gateway\b":                    ("api_gateway", EntityType.SERVICE),
    r"\bAPI gateway\b":                    ("api_gateway", EntityType.SERVICE),
    r"\bGCP migration\b":                  ("GCP_migration_project", EntityType.PROJECT),
    r"\bphase 1\b":                        ("Phase1_migration", EntityType.PROJECT),
    r"\bCloud Architecture\b":             ("Cloud_Architecture_Decision", EntityType.ARCHITECTURE_DECISION),
    r"\bADR\b":                            ("Architecture_Decision_Record", EntityType.ARCHITECTURE_DECISION),
    r"\brace condition\b":                 ("JWT_race_condition", EntityType.PROBLEM),
    r"\bsecurity vulnerability\b":         ("security_vulnerability", EntityType.PROBLEM),
    r"\bcost\w*\b":                        ("cloud_cost_concern", EntityType.PROBLEM),
    r"\bCLOUD-\d+\b":                      ("Jira_Issue", EntityType.ISSUE),
}

# Known person handles in the mock dataset
PERSON_HANDLES = {
    "arun_sharma", "priya_nair", "rohan_mehta", "divya_krishnan", "vikram_patel",
}


class FallbackExtractor:
    """
    Deterministic heuristic triple extractor.

    This extractor is used when no LLM backend is configured or available.
    Results are clearly marked as ``extraction_mode = ExtractionMode.FALLBACK``.
    """

    def __init__(self, min_confidence: float = 0.5) -> None:
        """
        Parameters
        ----------
        min_confidence:
            Discard triples whose heuristic confidence falls below this value.
        """
        self.min_confidence = min_confidence

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(self, event: RawEvent) -> ExtractionResult:
        """
        Extract triples from a single RawEvent using heuristic rules.

        Parameters
        ----------
        event:
            A normalised RawEvent from the ingestion pipeline.

        Returns
        -------
        ExtractionResult
            Container with all triples found (may be empty).
        """
        triples: List[Triple] = []

        text = event.content
        author = event.author

        # Determine the best-matching relation for this text
        matched_relation, base_confidence = self._match_relation(text)

        if matched_relation is None:
            # No relation matched – return empty result
            return ExtractionResult(
                event_id=event.event_id,
                source_id=event.source_id,
                source=event.source,
                extraction_mode=ExtractionMode.FALLBACK,
                triples=[],
            )

        # Find object entities mentioned in the text
        objects = self._find_objects(text)

        for obj_name, obj_type in objects:
            confidence = self._adjust_confidence(base_confidence, text, obj_name)
            if confidence < self.min_confidence:
                continue

            evidence = self._extract_evidence(text, obj_name, matched_relation)

            try:
                triple = Triple(
                    subject=author,
                    subject_type=self._classify_person(author),
                    relation=matched_relation,
                    object=obj_name,
                    object_type=obj_type,
                    timestamp=event.timestamp,
                    source=event.source,
                    source_id=event.source_id,
                    evidence=evidence or text[:300],
                    confidence=round(confidence, 3),
                    extraction_mode=ExtractionMode.FALLBACK,
                    metadata={"extractor": "heuristic"},
                )
                triples.append(triple)
            except Exception as exc:
                logger.warning("FallbackExtractor: could not build triple – %s", exc)

        return ExtractionResult(
            event_id=event.event_id,
            source_id=event.source_id,
            source=event.source,
            extraction_mode=ExtractionMode.FALLBACK,
            triples=triples,
        )

    def extract_batch(self, events: List[RawEvent]) -> List[ExtractionResult]:
        """
        Extract triples from a list of RawEvents.

        Parameters
        ----------
        events:
            List of normalised events from the ingestion pipeline.

        Returns
        -------
        List[ExtractionResult]
            One ExtractionResult per input event.
        """
        results = []
        for evt in events:
            result = self.extract(evt)
            results.append(result)
        total_triples = sum(len(r.triples) for r in results)
        logger.info(
            "FallbackExtractor: processed %d events → %d triples",
            len(events),
            total_triples,
        )
        return results

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _match_relation(text: str) -> Tuple[Optional[str], float]:
        """Return the first matching relation label and its base confidence."""
        for pattern, relation, confidence in RELATION_PATTERNS:
            if pattern.search(text):
                return relation, confidence
        return None, 0.0

    @staticmethod
    def _find_objects(text: str) -> List[Tuple[str, EntityType]]:
        """Return all technology/project/problem entities mentioned in text."""
        found: List[Tuple[str, EntityType]] = []
        seen: set = set()
        for pattern_str, (name, etype) in TECH_KEYWORDS.items():
            if re.search(pattern_str, text, re.I) and name not in seen:
                found.append((name, etype))
                seen.add(name)
        return found

    @staticmethod
    def _adjust_confidence(base: float, text: str, obj_name: str) -> float:
        """Slightly boost confidence if the object name appears verbatim."""
        if obj_name.lower().replace("_", " ") in text.lower():
            return min(1.0, base + 0.05)
        return base

    @staticmethod
    def _extract_evidence(text: str, obj_name: str, relation: str) -> Optional[str]:
        """
        Find the most relevant sentence mentioning the object or relation keyword.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        obj_clean = obj_name.lower().replace("_", " ")
        for sent in sentences:
            if obj_clean in sent.lower():
                return sent.strip()[:500]
        # Fallback: first sentence
        return sentences[0].strip()[:500] if sentences else None

    @staticmethod
    def _classify_person(author: str) -> EntityType:
        """Return PERSON type if the author is in the known set, else UNKNOWN."""
        if author.lower() in PERSON_HANDLES:
            return EntityType.PERSON
        return EntityType.UNKNOWN
