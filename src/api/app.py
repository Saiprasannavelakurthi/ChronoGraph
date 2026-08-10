"""
src/api/app.py
──────────────
FastAPI application for ChronoGraph Week 1.

Provides a lightweight REST interface for triggering and inspecting the
ingestion and extraction pipelines.  This is optional for Week 1 but is
included to make the pipeline composable and testable over HTTP.

Endpoints
─────────
GET  /api/v1/health         → liveness probe
POST /api/v1/ingest         → run the data ingestion pipeline
POST /api/v1/extract        → run the triple extraction pipeline
GET  /api/v1/triples        → read extracted_triples.json

NOT implemented (Week 2+):
  - Neo4j graph endpoints
  - GraphRAG query endpoints
  - Temporal retrieval endpoints
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings
from src.extraction.extractor import TemporalTripleExtractor
from src.ingestion.pipeline import IngestionPipeline
from src.schemas.graph import Triple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ChronoGraph API",
    description=(
        "Week 1 REST interface for the ChronoGraph Temporal GraphRAG pipeline. "
        "Provides data ingestion, triple extraction, and result inspection endpoints."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────────────────────────


class IngestRequest(BaseModel):
    """Optional request body for the ingest endpoint."""
    max_events: int = 0  # 0 = unlimited


class ExtractRequest(BaseModel):
    """Optional request body for the extract endpoint."""
    max_events: int = 0           # 0 = unlimited
    llm_provider: str = ""        # overrides settings.llm_provider if provided


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_provider: str
    data_dir: str


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Liveness probe",
)
async def health() -> HealthResponse:
    """Return service status and configuration summary."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        llm_provider=settings.llm_provider,
        data_dir=str(settings.raw_data_dir),
    )


@app.post(
    "/api/v1/ingest",
    tags=["Pipeline"],
    summary="Run the data ingestion pipeline",
)
async def ingest(request: IngestRequest = IngestRequest()) -> Dict[str, Any]:
    """
    Execute the data ingestion pipeline:

    1. Load Slack, GitHub, and Jira mock data.
    2. Normalise timestamps and clean text.
    3. Save normalised events to data/processed/normalized_events.json.

    Returns a summary with event counts per source.
    """
    try:
        pipeline = IngestionPipeline(
            slack_path=settings.slack_raw_path,
            github_path=settings.github_raw_path,
            jira_path=settings.jira_raw_path,
            output_path=settings.normalized_events_path,
            max_events=request.max_events,
        )
        events = pipeline.run()

        counts: Dict[str, int] = {}
        for evt in events:
            counts[evt.source.value] = counts.get(evt.source.value, 0) + 1

        return {
            "status": "success",
            "total_events": len(events),
            "events_by_source": counts,
            "output_file": str(settings.normalized_events_path),
        }
    except Exception as exc:
        logger.error("Ingest endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/api/v1/extract",
    tags=["Pipeline"],
    summary="Run the triple extraction pipeline",
)
async def extract(request: ExtractRequest = ExtractRequest()) -> Dict[str, Any]:
    """
    Execute the triple extraction pipeline on normalised events.

    Reads data/processed/normalized_events.json (created by /ingest),
    runs the LlamaIndex extractor, and writes results to
    data/processed/extracted_triples.json.

    Falls back to the heuristic extractor if the LLM is unavailable.
    """
    normalized_path = settings.normalized_events_path
    if not normalized_path.exists():
        raise HTTPException(
            status_code=400,
            detail="normalized_events.json not found. Run /api/v1/ingest first.",
        )

    try:
        # Load normalised events from disk
        from src.schemas.graph import RawEvent
        with open(normalized_path, "r", encoding="utf-8") as fh:
            raw_list = json.load(fh)
        events = [RawEvent(**item) for item in raw_list]

        # Determine LLM provider
        provider = request.llm_provider or settings.llm_provider

        extractor = TemporalTripleExtractor(
            llm_provider=provider,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            groq_api_key=settings.groq_api_key,
            groq_model=settings.groq_model,
            min_confidence=settings.extraction_min_confidence,
            auto_fallback=True,
        )

        results = extractor.extract_batch(events, max_events=request.max_events)

        # Collect all triples and save
        all_triples: List[Triple] = []
        for result in results:
            all_triples.extend(result.triples)

        settings.processed_data_dir.mkdir(parents=True, exist_ok=True)
        with open(settings.extracted_triples_path, "w", encoding="utf-8") as fh:
            json.dump(
                [t.to_neo4j_dict() for t in all_triples],
                fh,
                indent=2,
                ensure_ascii=False,
                default=str,
            )

        mode_counts: Dict[str, int] = {}
        for t in all_triples:
            mode_counts[t.extraction_mode.value] = mode_counts.get(t.extraction_mode.value, 0) + 1

        return {
            "status": "success",
            "events_processed": len(events),
            "total_triples": len(all_triples),
            "triples_by_mode": mode_counts,
            "output_file": str(settings.extracted_triples_path),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Extract endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/api/v1/triples",
    tags=["Data"],
    summary="Read extracted triples",
)
async def get_triples(
    limit: int = 50,
    source: str = "",
    relation: str = "",
) -> Dict[str, Any]:
    """
    Read extracted_triples.json and return triples with optional filters.

    Query params
    ────────────
    limit:    Max number of triples to return (default 50, 0 = all).
    source:   Filter by source system (slack / github / jira).
    relation: Filter by relation label (e.g. ADVOCATED_FOR).
    """
    triples_path = settings.extracted_triples_path
    if not triples_path.exists():
        raise HTTPException(
            status_code=404,
            detail="extracted_triples.json not found. Run /api/v1/extract first.",
        )

    with open(triples_path, "r", encoding="utf-8") as fh:
        triples: List[Dict[str, Any]] = json.load(fh)

    # Filter
    if source:
        triples = [t for t in triples if t.get("source", "").lower() == source.lower()]
    if relation:
        triples = [t for t in triples if t.get("relation", "").upper() == relation.upper()]

    total = len(triples)
    if limit > 0:
        triples = triples[:limit]

    return {
        "total_matching": total,
        "returned": len(triples),
        "triples": triples,
    }
