"""
src/extraction/extractor.py
────────────────────────────
LlamaIndex-based temporal triple extractor.

This is the primary extraction component for Week 1.  It uses LlamaIndex to
interact with the configured LLM (Ollama/Llama 3 or OpenAI) and extract
structured Entity → [RELATION] → Entity triples from RawEvents.

Architecture
────────────

  RawEvent
     │
     ▼
  Build prompt  (src/extraction/prompts.py)
     │
     ▼
  LlamaIndex LLM.complete()   ← Ollama/Llama3 (default) or OpenAI
     │
     ▼
  Parse JSON response
     │
     ▼
  Validate via Pydantic Triple model
     │
     ▼
  ExtractionResult

If the LLM is unavailable or returns invalid JSON, the extractor falls back
to FallbackExtractor automatically unless ``auto_fallback=False`` is set.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from src.extraction.fallback import FallbackExtractor
from src.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from src.schemas.graph import (
    DataSource,
    EntityType,
    ExtractionMode,
    ExtractionResult,
    RawEvent,
    Triple,
)

logger = logging.getLogger(__name__)


class TemporalTripleExtractor:
    """
    LlamaIndex-powered triple extractor with automatic fallback.

    Parameters
    ----------
    llm_provider:
        One of ``"groq"``, ``"ollama"``, ``"openai"``, or ``"mock"``.
    ollama_base_url:
        Base URL of the Ollama server (default: http://localhost:11434).
    ollama_model:
        Ollama model tag (default: ``"llama3"``).
    openai_api_key:
        OpenAI API key.  Only used when ``llm_provider="openai"``.
    openai_model:
        OpenAI model name (default: ``"gpt-4o-mini"``).
    groq_api_key:
        Groq API key. Only used when ``llm_provider="groq"``.
    groq_model:
        Groq model name (default: ``"llama-3.1-8b-instant"``).
    min_confidence:
        Discard triples below this threshold.
    auto_fallback:
        If True, automatically use FallbackExtractor when the LLM call fails.
    """

    def __init__(
        self,
        llm_provider: str = "mock",
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "llama3",
        openai_api_key: str = "",
        openai_model: str = "gpt-4o-mini",
        groq_api_key: str = "",
        groq_model: str = "llama-3.1-8b-instant",
        min_confidence: float = 0.5,
        auto_fallback: bool = True,
    ) -> None:
        self.llm_provider = llm_provider.lower()
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.groq_api_key = groq_api_key
        self.groq_model = groq_model
        self.min_confidence = min_confidence
        self.auto_fallback = auto_fallback

        self._llm = None  # lazy-initialised on first call
        self._fallback = FallbackExtractor(min_confidence=min_confidence)

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(self, event: RawEvent) -> ExtractionResult:
        """
        Extract triples from a single RawEvent.

        Tries the configured LLM first; falls back to heuristics if the LLM
        call fails and ``auto_fallback=True``.

        Parameters
        ----------
        event:
            Normalised RawEvent from the ingestion pipeline.

        Returns
        -------
        ExtractionResult
        """
        if self.llm_provider in ("mock", "fallback"):
            logger.debug("Extractor: fallback mode → using fallback extractor")
            return self._fallback.extract(event)

        try:
            llm = self._get_llm()
            return self._extract_with_llm(llm, event)
        except Exception as exc:
            logger.warning("Extractor: LLM call failed (%s) – %s", self.llm_provider, exc)
            if self.auto_fallback:
                logger.info("Extractor: falling back to heuristic extractor for event %s", event.source_id)
                return self._fallback.extract(event)
            return ExtractionResult(
                event_id=event.event_id,
                source_id=event.source_id,
                source=event.source,
                extraction_mode=ExtractionMode.FALLBACK,
                triples=[],
                error=str(exc),
            )

    def extract_batch(
        self, events: List[RawEvent], max_events: int = 0
    ) -> List[ExtractionResult]:
        """
        Extract triples from a list of RawEvents.

        Parameters
        ----------
        events:
            List of normalised events from the ingestion pipeline.
        max_events:
            If > 0, only process this many events (useful for quick demos).

        Returns
        -------
        List[ExtractionResult]
        """
        if max_events > 0:
            events = events[:max_events]

        results: List[ExtractionResult] = []
        total = len(events)
        for idx, evt in enumerate(events, 1):
            logger.info(
                "Extractor: processing event %d/%d  [%s] %s",
                idx, total, evt.source.value, evt.source_id,
            )
            res = self.extract(evt)
            results.append(res)

            # Polite delay for cloud APIs to avoid 429 rate limits
            if self.llm_provider in ("groq", "openai") and idx < total:
                time.sleep(1.5)

        total_triples = sum(len(r.triples) for r in results)
        logger.info(
            "Extractor: batch complete – %d events → %d triples",
            len(events), total_triples,
        )
        return results

    # ── LLM interaction ───────────────────────────────────────────────────────

    def _get_llm(self):
        """Lazily initialise the LlamaIndex LLM instance."""
        if self._llm is not None:
            return self._llm

        if self.llm_provider == "groq":
            self._llm = self._init_groq()
        elif self.llm_provider == "ollama":
            self._llm = self._init_ollama()
        elif self.llm_provider == "openai":
            self._llm = self._init_openai()
        else:
            raise ValueError(f"Unknown llm_provider: {self.llm_provider!r}")

        return self._llm

    def _init_groq(self):
        """Initialise the LlamaIndex Groq LLM."""
        if not self.groq_api_key:
            raise ValueError("groq_api_key is required when llm_provider=groq")
        try:
            from llama_index.llms.groq import Groq
            llm = Groq(
                model=self.groq_model,
                api_key=self.groq_api_key,
                temperature=0.0,
            )
            logger.info(
                "Extractor: initialised Groq LLM (model=%s)", self.groq_model
            )
            return llm
        except ImportError as exc:
            raise ImportError(
                "llama-index-llms-groq is not installed. "
                "Run: pip install llama-index-llms-groq"
            ) from exc

    def _init_ollama(self):
        """Initialise the LlamaIndex Ollama LLM."""
        try:
            from llama_index.llms.ollama import Ollama
            llm = Ollama(
                model=self.ollama_model,
                base_url=self.ollama_base_url,
                request_timeout=120.0,
                json_mode=False,
            )
            logger.info("Extractor: initialised Ollama LLM (model=%s, url=%s)", self.ollama_model, self.ollama_base_url)
            return llm
        except ImportError as exc:
            raise ImportError(
                "llama-index-llms-ollama is not installed. "
                "Run: pip install llama-index-llms-ollama"
            ) from exc

    def _init_openai(self):
        """Initialise the LlamaIndex OpenAI LLM."""
        if not self.openai_api_key:
            raise ValueError("openai_api_key is required when llm_provider=openai")
        try:
            from llama_index.llms.openai import OpenAI
            llm = OpenAI(
                model=self.openai_model,
                api_key=self.openai_api_key,
                temperature=0.0,
            )
            logger.info("Extractor: initialised OpenAI LLM (model=%s)", self.openai_model)
            return llm
        except ImportError as exc:
            raise ImportError(
                "llama-index-llms-openai is not installed. "
                "Run: pip install llama-index-llms-openai"
            ) from exc

    def _extract_with_llm(self, llm, event: RawEvent) -> ExtractionResult:
        """Call the LLM and parse its JSON response into Triple objects."""
        user_prompt = build_user_prompt(
            content=event.content,
            source=event.source.value,
            source_id=event.source_id,
            author=event.author,
            timestamp=event.timestamp.isoformat(),
            channel=event.channel or "",
        )

        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

        # Map provider string to ExtractionMode enum
        _mode_map = {
            "groq":   ExtractionMode.LLM_GROQ,
            "ollama": ExtractionMode.LLM_OLLAMA,
            "openai": ExtractionMode.LLM_OPENAI,
        }
        mode = _mode_map.get(self.llm_provider, ExtractionMode.FALLBACK)

        # Execute completion with rate-limit retry support
        max_retries = 3
        raw_text = ""
        for attempt in range(max_retries):
            try:
                response = llm.complete(full_prompt)
                raw_text = response.text if hasattr(response, "text") else str(response)
                break
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    if attempt < max_retries - 1:
                        sleep_time = (attempt + 1) * 12
                        logger.warning("Extractor: Groq 429 rate limit hit. Waiting %ds (attempt %d/%d)...", sleep_time, attempt + 1, max_retries)
                        time.sleep(sleep_time)
                        continue
                raise RuntimeError(f"LLM completion failed: {exc}") from exc

        triples = self._parse_llm_response(raw_text, event, mode=mode)

        return ExtractionResult(
            event_id=event.event_id,
            source_id=event.source_id,
            source=event.source,
            extraction_mode=mode,
            triples=triples,
        )

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse_llm_response(
        self, raw_text: str, event: RawEvent, mode: ExtractionMode = ExtractionMode.LLM_GROQ
    ) -> List[Triple]:
        """
        Parse the LLM's raw text response into validated Triple objects.

        Handles common LLM formatting quirks:
        - Markdown code fences (```json ... ```)
        - Leading/trailing non-JSON text
        - Single-object responses (not wrapped in a list)
        """
        triples: List[Triple] = []

        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip()
        cleaned = re.sub(r"```", "", cleaned).strip()

        # Attempt to locate a JSON array
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            # Try single-object response
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                cleaned = f"[{match.group(0)}]"
            else:
                logger.warning("Extractor: no JSON found in LLM response for event %s", event.source_id)
                return []
        else:
            cleaned = match.group(0)

        raw_list: List[Dict[str, Any]] = []
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                raw_list = parsed
            elif isinstance(parsed, dict):
                raw_list = [parsed]
        except json.JSONDecodeError:
            # Fallback: extract individual JSON objects using regex
            dict_matches = re.findall(r"\{[^{}]*\}", cleaned, re.DOTALL)
            for dm in dict_matches:
                try:
                    obj = json.loads(dm)
                    if isinstance(obj, dict):
                        raw_list.append(obj)
                except Exception:
                    pass
            if not raw_list:
                logger.warning("Extractor: JSON parse error for event %s – could not parse array or dicts", event.source_id)
                return []

        for item in raw_list:
            try:
                # ── Sanitise LLM-provided values ────────────────────────────
                # Source: LLM may return "text", "unknown", etc. — always fall back
                raw_source = str(item.get("source", event.source.value) or event.source.value)
                try:
                    source = DataSource(raw_source)
                except ValueError:
                    source = event.source

                # source_id: LLM may return null — always fall back to event id
                source_id = item.get("source_id") or event.source_id

                # timestamp: LLM may return null — fall back to event timestamp
                raw_ts = item.get("timestamp")
                timestamp = self._coerce_timestamp(raw_ts if raw_ts else None, event.timestamp)

                # evidence: strip any null / empty string
                evidence = str(item.get("evidence") or event.content[:200])

                # object must be non-empty
                obj = str(item.get("object", "") or "")
                if not obj:
                    continue

                subj_str = str(item.get("subject") or event.author)
                subj_type = self._coerce_entity_type(item.get("subject_type"))
                if subj_type == EntityType.UNKNOWN:
                    subj_type = self._infer_entity_type(subj_str, event.content)

                obj_type = self._coerce_entity_type(item.get("object_type"))
                if obj_type == EntityType.UNKNOWN:
                    obj_type = self._infer_entity_type(obj, event.content)

                triple = Triple(
                    subject=subj_str,
                    subject_type=subj_type,
                    relation=str(item.get("relation", "RELATED_TO") or "RELATED_TO"),
                    object=obj,
                    object_type=obj_type,
                    timestamp=timestamp,
                    source=source,
                    source_id=source_id,
                    evidence=evidence,
                    confidence=float(item.get("confidence") or 0.7),
                    extraction_mode=mode,
                )
                if triple.confidence >= self.min_confidence:
                    triples.append(triple)
            except Exception as exc:
                logger.warning("Extractor: invalid triple dict %s – %s", item, exc)

        return triples

    @classmethod
    def _coerce_entity_type(cls, value: Optional[str]) -> EntityType:
        """Parse raw string into EntityType enum, handling case variations and aliases."""
        if not value or not isinstance(value, str):
            return EntityType.UNKNOWN

        val_str = value.strip()
        # Direct enum value match
        try:
            return EntityType(val_str)
        except ValueError:
            pass

        val_upper = val_str.upper().replace(" ", "_").replace("-", "_")

        # Member name match (e.g. PERSON -> EntityType.PERSON)
        for member in EntityType:
            if member.name == val_upper or member.value.upper() == val_upper:
                return member

        # Alias map
        alias_map = {
            "INDIVIDUAL": EntityType.PERSON,
            "USER": EntityType.PERSON,
            "DEVELOPER": EntityType.PERSON,
            "ENGINEER": EntityType.PERSON,
            "AUTHOR": EntityType.PERSON,
            "TECH": EntityType.TECHNOLOGY,
            "TOOL": EntityType.TECHNOLOGY,
            "LIBRARY": EntityType.TECHNOLOGY,
            "FRAMEWORK": EntityType.TECHNOLOGY,
            "MICROSERVICE": EntityType.SERVICE,
            "APP": EntityType.SERVICE,
            "COMPONENT": EntityType.SERVICE,
            "DB": EntityType.DATABASE,
            "DATASTORE": EntityType.DATABASE,
            "BUG": EntityType.ISSUE,
            "TICKET": EntityType.ISSUE,
            "PULL_REQUEST": EntityType.ISSUE,
            "PR": EntityType.ISSUE,
            "VULNERABILITY": EntityType.PROBLEM,
            "RISK": EntityType.PROBLEM,
            "DECISION": EntityType.ARCHITECTURE_DECISION,
            "ADR": EntityType.ARCHITECTURE_DECISION,
        }
        return alias_map.get(val_upper, EntityType.UNKNOWN)

    @classmethod
    def _infer_entity_type(cls, entity_name: str, context_text: str) -> EntityType:
        """Heuristic fallback to infer entity type from name and context text."""
        name_clean = entity_name.strip()
        name_lower = name_clean.lower()

        # Known person handles/names
        person_names = {
            "arun_sharma", "priya_nair", "rohan_mehta", "divya_krishnan", "vikram_patel",
            "arun", "priya", "rohan", "divya", "vikram",
        }
        if name_lower in person_names or any(p in name_lower for p in ["sharma", "nair", "mehta", "krishnan", "patel"]):
            return EntityType.PERSON

        # Jira Issue keys or PRs
        if re.search(r"^[A-Z]+-\d+$", name_clean) or re.search(r"\bPR\s*#?\d+\b", name_clean, re.I):
            return EntityType.ISSUE

        # Database terms
        db_keywords = {"postgresql", "postgres", "cloudsql", "mongodb", "redis", "s3", "rds", "gcs", "database", "datastore"}
        if name_lower in db_keywords or any(k in name_lower for k in ["sql", "postgres", "redis", "mongo", "s3"]):
            return EntityType.DATABASE

        # Service terms
        service_keywords = {"auth_service", "authentication_service", "api_gateway", "service", "microservice"}
        if name_lower in service_keywords or "service" in name_lower or "gateway" in name_lower:
            return EntityType.SERVICE

        # Technology terms
        tech_keywords = {"gcp", "aws", "kubernetes", "gke", "eks", "docker", "jwt", "boto3", "python", "node", "java", "go", "react"}
        if name_lower in tech_keywords or any(k in name_lower for k in ["cloud", "gcp", "aws", "kubernetes", "docker", "jwt"]):
            return EntityType.TECHNOLOGY

        # Problem / Issue terms
        problem_keywords = {"vulnerability", "race_condition", "race condition", "bug", "issue", "cost", "concern"}
        if any(k in name_lower for k in problem_keywords):
            return EntityType.PROBLEM

        # Project terms
        if "migration" in name_lower or "phase" in name_lower or "project" in name_lower:
            return EntityType.PROJECT

        # Date / Temporal string terms
        if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4})\b", name_lower):
            return EntityType.OTHER

        # Architecture decision terms
        if "adr" in name_lower or "architecture" in name_lower:
            return EntityType.ARCHITECTURE_DECISION

        return EntityType.OTHER

    @staticmethod
    def _coerce_timestamp(value: Optional[str], fallback) -> Any:
        if not value:
            return fallback
        try:
            value = value.replace("Z", "+00:00")
            from datetime import datetime
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return fallback
