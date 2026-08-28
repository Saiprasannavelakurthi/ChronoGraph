"""
src/api/app.py
──────────────
FastAPI application for ChronoGraph.

Provides REST interfaces for data ingestion, triple extraction, graph-ready
preparation, and Week 4 temporal retrieval query functionality.

Endpoints
─────────
Week 4 Primary Retrieval Endpoints:
  GET  /api/health            → service & retrieval data availability probe
  POST /api/retrieval/query   → temporal evidence retrieval query
  GET  /api/retrieval/stats   → retrieval data quality statistics

Pipeline Endpoints:
  GET  /api/v1/health         → legacy liveness probe
  POST /api/v1/ingest         → run the data ingestion pipeline
  POST /api/v1/extract        → run the triple extraction pipeline
  GET  /api/v1/triples        → read extracted_triples.json
  GET  /api/v1/graph-ready    → read graph_ready_triples.json
  POST /api/v1/prepare-graph  → run the graph preparation pipeline
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings
from src.extraction.extractor import TemporalTripleExtractor
from src.ingestion.pipeline import IngestionPipeline
from src.retrieval.models import (
    RetrievalHealthResponse,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
)
from src.retrieval.service import (
    RetrievalDataCorruptedError,
    RetrievalDataNotFoundError,
    RetrievalService,
    RetrievalServiceError,
)
from src.schemas.graph import Triple

logger = logging.getLogger(__name__)

# Global retrieval service instance
retrieval_service = RetrievalService()

# ─────────────────────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ChronoGraph API",
    description=(
        "REST interface for the ChronoGraph Temporal GraphRAG pipeline. "
        "Provides data ingestion, triple extraction, graph preparation, and temporal retrieval queries."
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


# ─────────────────────────────────────────────────────────────────────────────
# Week 2 endpoints – Graph-Ready Data (Karkuvel's module)
# ─────────────────────────────────────────────────────────────────────────────
# These endpoints serve / trigger Karkuvel's graph preparation pipeline.
# They do NOT connect to Neo4j; they expose the graph_ready_triples.json
# file that Saiprasanna's Neo4j module will consume.


@app.get(
    "/api/v1/graph-ready",
    tags=["Week 2 – Graph Data"],
    summary="Read graph-ready triples (Week 2 output)",
)
async def get_graph_ready(
    limit: int = 50,
    source: str = "",
    relation: str = "",
    subject: str = "",
) -> Dict[str, Any]:
    """
    Return records from graph_ready_triples.json with optional filters.

    This file is produced by Karkuvel's Week 2 graph preparation pipeline
    (run POST /api/v1/prepare-graph or 'python main.py --prepare-graph').

    Query params
    ────────────
    limit    : Max records to return (0 = all, default 50).
    source   : Filter by source system (slack / github / jira).
    relation : Filter by relation label (e.g. ADVOCATED_FOR).
    subject  : Filter by canonical subject name (partial, case-insensitive).
    """
    graph_ready_path = settings.graph_ready_triples_path
    if not graph_ready_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "graph_ready_triples.json not found. "
                "Run POST /api/v1/prepare-graph or 'python main.py --prepare-graph' first."
            ),
        )

    with open(graph_ready_path, "r", encoding="utf-8") as fh:
        triples: List[Dict[str, Any]] = json.load(fh)

    # Apply optional filters
    if source:
        triples = [t for t in triples if t.get("source", "").lower() == source.lower()]
    if relation:
        triples = [t for t in triples if t.get("relation", "").upper() == relation.upper()]
    if subject:
        triples = [
            t for t in triples
            if subject.lower() in t.get("subject", "").lower()
        ]

    total = len(triples)
    if limit > 0:
        triples = triples[:limit]

    return {
        "total_matching": total,
        "returned": len(triples),
        "source_file": str(graph_ready_path),
        "triples": triples,
    }


@app.post(
    "/api/v1/prepare-graph",
    tags=["Week 2 – Graph Data"],
    summary="Run the Week 2 graph preparation pipeline",
)
async def prepare_graph() -> Dict[str, Any]:
    """
    Execute Karkuvel's graph preparation pipeline:

    1. Load extracted_triples.json (Week 1 output).
    2. Validate all triples against the graph schema.
    3. Normalise entity names, relation labels, and timestamps.
    4. Deduplicate using deterministic composite-key logic.
    5. Write graph_ready_triples.json and graph_prep_summary.json.

    Run /api/v1/ingest and /api/v1/extract first to generate the input.
    This endpoint does NOT connect to Neo4j.
    """
    if not settings.extracted_triples_path.exists():
        raise HTTPException(
            status_code=400,
            detail=(
                "extracted_triples.json not found. "
                "Run POST /api/v1/extract first."
            ),
        )

    try:
        from src.graph_prep.pipeline import GraphPrepPipeline

        pipeline = GraphPrepPipeline(
            input_path=settings.extracted_triples_path,
            output_path=settings.graph_ready_triples_path,
            summary_path=settings.graph_prep_summary_path,
        )
        result = pipeline.run()
        summary = result["summary"]
        stats = summary["statistics"]

        return {
            "status": "success",
            "total_input_triples": stats["total_input_triples"],
            "valid_triples": stats["valid_triples"],
            "invalid_triples": stats["invalid_triples"],
            "duplicates_removed": stats["duplicates_removed"],
            "graph_ready_triples": stats["graph_ready_triples"],
            "output_file": str(settings.graph_ready_triples_path),
            "summary_file": str(settings.graph_prep_summary_path),
            "date_range": summary["date_range"],
            "entities": summary["entities"],
            "sources": summary["sources"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("prepare-graph endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Week 4 Primary Endpoints — Temporal Retrieval Query API
# ─────────────────────────────────────────────────────────────────────────────


@app.get(
    "/api/health",
    response_model=RetrievalHealthResponse,
    tags=["System"],
    summary="Service & retrieval data health check",
)
async def api_health() -> RetrievalHealthResponse:
    """
    Return API service health status, retrieval data availability on disk,
    and total loaded record count.
    """
    return retrieval_service.get_health()


@app.post(
    "/api/retrieval/query",
    response_model=RetrievalQueryResponse,
    tags=["Retrieval"],
    summary="Query temporal retrieval records",
)
async def query_retrieval(request: RetrievalQueryRequest) -> RetrievalQueryResponse:
    """
    Execute a structured temporal retrieval query against retrieval-ready evidence records.

    Features:
      - Validates query schema via FastAPI & Pydantic
      - Entity hint filtering (subject / object match)
      - Relation label filtering
      - Source system filtering ('slack', 'github', 'jira')
      - Temporal filtering (exact date, date range, before date, after date)
      - Chronological sorting (ASC / DESC)
      - Result limit and total match count prior to limit
      - Complete evidence provenance preservation
    """
    try:
        return retrieval_service.query(request)
    except RetrievalDataNotFoundError as exc:
        logger.warning("Retrieval query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RetrievalDataCorruptedError as exc:
        logger.error("Corrupted retrieval data encountered during query: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Retrieval data file is corrupted or cannot be parsed.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error in /api/retrieval/query: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error occurred while processing retrieval query.",
        ) from exc


@app.get(
    "/api/retrieval/stats",
    tags=["Retrieval"],
    summary="Get retrieval data quality statistics",
)
async def get_retrieval_stats() -> Dict[str, Any]:
    """
    Expose Week 3 retrieval data quality and coverage statistics.

    Reads retrieval_quality_stats.json or computes statistics on-demand.
    """
    try:
        return retrieval_service.get_stats()
    except RetrievalDataNotFoundError as exc:
        logger.warning("Retrieval stats unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error in /api/retrieval/stats: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error occurred while retrieving data statistics.",
        ) from exc


