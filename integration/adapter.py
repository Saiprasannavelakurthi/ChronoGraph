"""
integration/adapter.py
──────────────────────
Integration adapter bridging Karkuvel's data-ingestion events to
Aathi's graph-extraction module.

Reads:
  data-ingestion/data/processed/normalized_events.json

Transforms events and calls:
  graph-extraction/src/pipeline.py::process_records()

Writes:
  integration/outputs/graph_extraction_result.json

CLI Usage:
  python integration/adapter.py               # Default: deterministic mock mode
  python integration/adapter.py --live-groq   # Optional: live Groq Cloud extraction (if GROQ_API_KEY is configured)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_INGESTION_DIR = ROOT_DIR / "data-ingestion"
GRAPH_EXTRACTION_DIR = ROOT_DIR / "graph-extraction"
OUTPUT_DIR = ROOT_DIR / "integration" / "outputs"


def adapt_normalized_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Converts Karkuvel's normalized events into Aathi's extraction record schema:
      {
          "source": "slack" | "github" | "jira",
          "text": "...",
          "metadata": { ... }
      }
    """
    adapted = []
    for evt in events:
        text_content = ""
        title = evt.get("title")
        content = evt.get("content", "")
        if title:
            text_content = f"{title}: {content}"
        else:
            text_content = content

        record = {
            "source": evt.get("source", "slack"),
            "text": text_content,
            "metadata": {
                "event_id": evt.get("event_id"),
                "source_id": evt.get("source_id"),
                "author": evt.get("author"),
                "timestamp": evt.get("timestamp"),
                "channel": evt.get("channel"),
                "title": evt.get("title"),
                **evt.get("metadata", {})
            }
        }
        adapted.append(record)
    return adapted


def run_aathi_extraction_on_karkuvel_data(
    max_records: int = 5,
    use_live_groq: bool = False
) -> Dict[str, Any]:
    """
    Executes Aathi's extraction pipeline on a representative sample of Karkuvel's normalized events.
    """
    events_path = DATA_INGESTION_DIR / "data" / "processed" / "normalized_events.json"
    if not events_path.exists():
        raise FileNotFoundError(f"Normalized events not found at {events_path}. Run data ingestion first.")

    with open(events_path, "r", encoding="utf-8") as f:
        raw_events = json.load(f)

    # Take a representative sample across Slack, GitHub, Jira
    slack_evts = [e for e in raw_events if e.get("source") == "slack"][:2]
    github_evts = [e for e in raw_events if e.get("source") == "github"][:2]
    jira_evts = [e for e in raw_events if e.get("source") == "jira"][:1]
    sampled_events = (slack_evts + github_evts + jira_evts)[:max_records]

    adapted_records = adapt_normalized_events(sampled_events)

    # Add graph-extraction to sys.path
    if str(GRAPH_EXTRACTION_DIR) not in sys.path:
        sys.path.insert(0, str(GRAPH_EXTRACTION_DIR))

    from src.pipeline import process_records
    from src.extractor import GraphExtractor

    groq_api_key = os.getenv("GROQ_API_KEY")
    has_valid_groq = bool(groq_api_key and not groq_api_key.startswith("gsk_your_groq_api_key"))

    mode_used = "deterministic_mock"
    extractor = None

    if use_live_groq:
        if has_valid_groq:
            try:
                print("  [Adapter] GROQ_API_KEY detected. Initializing live Groq LLM extractor...")
                extractor = GraphExtractor()
                mode_used = "live_groq"
            except Exception as err:
                print(f"  [Adapter] Live Groq initialization failed ({err}), falling back to deterministic mock.")
                extractor = None
        else:
            print("  [Adapter] Live Groq requested but GROQ_API_KEY is missing/placeholder. Using deterministic mock mode.")
            extractor = None

    if extractor is None:
        mode_used = "deterministic_mock"
        mock_llm = MagicMock()
        # Deterministic extraction outputs conforming to the sampled events
        mock_llm.complete.side_effect = [
            # Slack event 1 (Arun Sharma proposal)
            MagicMock(text=json.dumps({
                "entities": [
                    {"id": "person_arun_sharma", "name": "arun_sharma", "type": "PERSON"},
                    {"id": "tech_gcp", "name": "GCP", "type": "TECHNOLOGY"},
                    {"id": "tech_aws", "name": "AWS", "type": "TECHNOLOGY"},
                    {"id": "service_auth", "name": "authentication_service", "type": "SERVICE"}
                ],
                "relationships": [
                    {"source": "arun_sharma", "relation": "ADVOCATED_FOR", "target": "GCP"},
                    {"source": "arun_sharma", "relation": "EVALUATING", "target": "AWS"},
                    {"source": "arun_sharma", "relation": "PROPOSED_MIGRATION", "target": "authentication_service"}
                ],
                "triples": []
            })),
            # Slack event 2 (Priya Nair response)
            MagicMock(text=json.dumps({
                "entities": [
                    {"id": "person_priya_nair", "name": "priya_nair", "type": "PERSON"},
                    {"id": "tech_aws", "name": "AWS", "type": "TECHNOLOGY"},
                    {"id": "tech_gcp", "name": "GCP", "type": "TECHNOLOGY"}
                ],
                "relationships": [
                    {"source": "priya_nair", "relation": "ADVOCATED_FOR", "target": "AWS"},
                    {"source": "priya_nair", "relation": "ARGUED_AGAINST", "target": "GCP"}
                ],
                "triples": []
            })),
            # GitHub event 1 (Karkuvel PR)
            MagicMock(text=json.dumps({
                "entities": [
                    {"id": "person_karkuvel", "name": "karkuvel", "type": "PERSON"},
                    {"id": "repo_chronograph", "name": "ChronoGraph", "type": "REPOSITORY"},
                    {"id": "pr_24", "name": "#24", "type": "PULL_REQUEST"}
                ],
                "relationships": [
                    {"source": "karkuvel", "relation": "OPENED", "target": "#24"},
                    {"source": "#24", "relation": "PART_OF", "target": "ChronoGraph"}
                ],
                "triples": []
            })),
            # GitHub event 2 (Aathi review & merge)
            MagicMock(text=json.dumps({
                "entities": [
                    {"id": "person_aathi", "name": "aathi", "type": "PERSON"},
                    {"id": "pr_24", "name": "#24", "type": "PULL_REQUEST"}
                ],
                "relationships": [
                    {"source": "aathi", "relation": "REVIEWED", "target": "#24"},
                    {"source": "aathi", "relation": "MERGED", "target": "#24"}
                ],
                "triples": []
            })),
            # Jira event 1 (Aathi task assignment)
            MagicMock(text=json.dumps({
                "entities": [
                    {"id": "person_aathi", "name": "aathi", "type": "PERSON"},
                    {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
                    {"id": "project_cg", "name": "ChronoGraph", "type": "PROJECT"}
                ],
                "relationships": [
                    {"source": "aathi", "relation": "ASSIGNED_TO", "target": "CG-102"},
                    {"source": "CG-102", "relation": "PART_OF", "target": "ChronoGraph"}
                ],
                "triples": []
            }))
        ]
        extractor = GraphExtractor(llm=mock_llm)

    result = process_records(adapted_records, extractor=extractor, raise_on_validation_error=False)
    result["extraction_mode"] = mode_used
    result["events_processed"] = len(sampled_events)
    result["total_dataset_events"] = len(raw_events)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / "graph_extraction_result.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return {
        "result": result,
        "output_file": str(out_file),
        "mode": mode_used,
        "events_processed": len(sampled_events),
        "total_dataset_events": len(raw_events),
        "entity_count": len(result.get("entities", [])),
        "relationship_count": len(result.get("relationships", [])),
        "triple_count": len(result.get("triples", [])),
        "is_valid": result.get("is_valid", False)
    }


def main():
    parser = argparse.ArgumentParser(description="ChronoGraph Ingestion-to-Extraction Adapter")
    parser.add_argument(
        "--live-groq",
        action="store_true",
        help="Use live Groq Cloud API for extraction (requires GROQ_API_KEY in .env)",
    )
    args = parser.parse_args()

    res = run_aathi_extraction_on_karkuvel_data(use_live_groq=args.live_groq)
    print("=" * 60)
    print("  CHRONOGRAPH INGESTION -> EXTRACTION ADAPTER")
    print("=" * 60)
    print(f"  Extraction Mode       : {res['mode']}")
    print(f"  Events Sampled        : {res['events_processed']} of {res['total_dataset_events']}")
    print(f"  Entities Extracted    : {res['entity_count']}")
    print(f"  Relationships Extracted: {res['relationship_count']}")
    print(f"  Triples Synchronized  : {res['triple_count']}")
    print(f"  Validation (is_valid) : {res['is_valid']}")
    print(f"  Output Artifact       : {res['output_file']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
