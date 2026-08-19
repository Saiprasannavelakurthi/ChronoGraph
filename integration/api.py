"""
integration/api.py
──────────────────
Minimal REST API for the ChronoGraph Week 2 Integrated Mid-Review.

Endpoints:
  GET /api/health   → Service health and summary stats
  GET /api/graph    → Real graph-ready nodes, edges, and timeline for UI
  GET /api/triples  → Raw graph-ready triples list
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_INGESTION_DIR = ROOT_DIR / "data-ingestion"
GRAPH_READY_PATH = DATA_INGESTION_DIR / "data" / "processed" / "graph_ready_triples.json"
SUMMARY_PATH = DATA_INGESTION_DIR / "data" / "processed" / "graph_prep_summary.json"

app = FastAPI(
    title="ChronoGraph Integration API",
    description="Week 2 Integration API connecting graph-ready data to UI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    triples_exist = GRAPH_READY_PATH.exists()
    count = 0
    if triples_exist:
        with open(GRAPH_READY_PATH, "r", encoding="utf-8") as f:
            count = len(json.load(f))
    return {
        "status": "online",
        "stage": "Week 2 Mid-Review Integration",
        "graph_ready_triples_available": triples_exist,
        "triple_count": count,
    }


@app.get("/api/graph")
def get_graph(limit: int = 25) -> Dict[str, Any]:
    """
    Returns real ChronoGraph graph-ready nodes and edges formatted for React Flow,
    along with a chronological timeline of enterprise events.
    """
    if not GRAPH_READY_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="graph_ready_triples.json not found. Run data-ingestion pipeline first.",
        )

    with open(GRAPH_READY_PATH, "r", encoding="utf-8") as f:
        triples: List[Dict[str, Any]] = json.load(f)

    # Sort triples chronologically
    sorted_triples = sorted(triples, key=lambda t: t.get("timestamp", ""))
    selected_triples = sorted_triples[:limit] if limit > 0 else sorted_triples

    # Build React Flow nodes and edges
    nodes = []
    edges = []
    seen_nodes = set()

    # Layout coordinates
    SPACING_X = 260
    ENTITY_SPACING_X = 92
    TURN_Y = 160
    ENTITY_Y = 300

    timeline = []

    for idx, t in enumerate(selected_triples, start=1):
        subj = t.get("subject_display") or t.get("subject")
        obj = t.get("object_display") or t.get("object")
        rel = t.get("relation", "RELATED_TO")
        ts = t.get("timestamp", "")
        source = t.get("source", "")
        evidence = t.get("evidence", "")

        # Format timestamp for node display
        time_display = ts[:10] if len(ts) >= 10 else ts

        turn_id = f"turn-{idx}"
        nodes.append({
            "id": turn_id,
            "type": "turnNode",
            "position": {"x": idx * SPACING_X, "y": TURN_Y},
            "data": {
                "label": f"[{source.upper()}] {subj} → {obj}",
                "time": time_display,
                "relation": rel,
                "evidence": evidence
            }
        })

        # Subject entity node
        subj_node_id = f"{turn_id}-subj"
        nodes.append({
            "id": subj_node_id,
            "type": "entityNode",
            "position": {"x": idx * SPACING_X - (ENTITY_SPACING_X / 2), "y": ENTITY_Y},
            "data": {"label": f"{subj} ({t.get('subject_type', 'Entity')})"}
        })

        # Object entity node
        obj_node_id = f"{turn_id}-obj"
        nodes.append({
            "id": obj_node_id,
            "type": "entityNode",
            "position": {"x": idx * SPACING_X + (ENTITY_SPACING_X / 2), "y": ENTITY_Y + 40},
            "data": {"label": f"{obj} ({t.get('object_type', 'Entity')})"}
        })

        # Edges from turn to entities
        edges.append({
            "id": f"radial-{subj_node_id}",
            "source": turn_id,
            "sourceHandle": "entity-out",
            "target": subj_node_id,
            "targetHandle": "entity-in",
            "type": "straight",
            "style": {"stroke": "#CBD0DD", "strokeWidth": 1.5, "strokeDasharray": "3 3"}
        })
        edges.append({
            "id": f"radial-{obj_node_id}",
            "source": turn_id,
            "sourceHandle": "entity-out",
            "target": obj_node_id,
            "targetHandle": "entity-in",
            "type": "straight",
            "style": {"stroke": "#CBD0DD", "strokeWidth": 1.5, "strokeDasharray": "3 3"}
        })

        # Spine edge connecting turns chronologically
        if idx > 1:
            prev_turn_id = f"turn-{idx-1}"
            edges.append({
                "id": f"spine-{prev_turn_id}-{turn_id}",
                "source": prev_turn_id,
                "sourceHandle": "spine-out",
                "target": turn_id,
                "targetHandle": "spine-in",
                "type": "smoothstep",
                "animated": True,
                "style": {"stroke": "#7C6FF0", "strokeWidth": 2}
            })

        timeline.append({
            "id": t.get("triple_id"),
            "timestamp": ts,
            "subject": subj,
            "relation": rel,
            "object": obj,
            "source": source,
            "evidence": evidence,
            "confidence": t.get("confidence", 1.0)
        })

    summary_stats = {}
    if SUMMARY_PATH.exists():
        with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
            summary_stats = json.load(f)

    return {
        "status": "success",
        "dataset": "ChronoGraph Real Enterprise Triples",
        "total_triples_in_dataset": len(triples),
        "returned_triples": len(selected_triples),
        "nodes": nodes,
        "edges": edges,
        "timeline": timeline,
        "statistics": summary_stats.get("statistics", {}),
        "date_range": summary_stats.get("date_range", {})
    }
