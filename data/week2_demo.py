"""
ChronoGraph Week 2 Demonstration Script
Demonstrates multi-source batch extraction (Slack, GitHub, Jira),
stable entity IDs, cross-record entity deduplication, triple synchronization,
metadata preservation, and Neo4j-ready JSON generation.
"""

import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock
from src.extractor import GraphExtractor
from src.pipeline import process_records


def run_week2_demo():
    print("=" * 70)
    print("      CHRONOGRAPH WEEK 2 — LLM GRAPH EXTRACTION DEMO")
    print("=" * 70)

    # 1. Define multi-source enterprise records (Slack, GitHub, Jira)
    sample_records = [
        {
            "source": "slack",
            "text": "Aathi discussed the ChronoGraph ingestion pipeline with Karkuvel in #dev-chat.",
            "metadata": {
                "source": "slack",
                "channel": "#dev-chat",
                "timestamp": "2026-08-10T10:15:30Z"
            }
        },
        {
            "source": "github",
            "text": "Karkuvel committed abc1234 to the ChronoGraph repository and opened pull request #24. Aathi reviewed pull request #24 and merged it into main.",
            "metadata": {
                "source": "github",
                "repository": "ChronoGraph",
                "timestamp": "2026-08-10T11:45:10Z"
            }
        },
        {
            "source": "jira",
            "text": "Aathi was assigned the graph extraction task CG-102 for the ChronoGraph project.",
            "metadata": {
                "source": "jira",
                "project": "CG",
                "timestamp": "2026-08-10T14:20:00Z"
            }
        }
    ]

    print(f"\n[1] INPUT RECORDS: {len(sample_records)} enterprise records (Slack, GitHub, Jira)")
    for idx, r in enumerate(sample_records, 1):
        print(f"    Record {idx} ({r['source'].upper()}): {r['text']}")

    # 2. Mock LLM responses for each source record to execute without requiring live API credentials
    mock_llm = MagicMock()

    slack_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "channel_dev_chat", "name": "#dev-chat", "type": "CHANNEL"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "MENTIONED", "target": "Karkuvel"},
            {"source": "Aathi", "relation": "PARTICIPATED_IN", "target": "#dev-chat"}
        ],
        "triples": []
    })

    github_response = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "repository_chronograph", "name": "ChronoGraph", "type": "REPOSITORY"},
            {"id": "commit_abc1234", "name": "abc1234", "type": "COMMIT"},
            {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "abc1234"},
            {"source": "Karkuvel", "relation": "OPENED", "target": "#24"},
            {"source": "Aathi", "relation": "REVIEWED", "target": "#24"},
            {"source": "Aathi", "relation": "MERGED", "target": "#24"}
        ],
        "triples": []
    })

    jira_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
            {"id": "repository_chronograph", "name": "ChronoGraph", "type": "REPOSITORY"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"},
            {"source": "CG-102", "relation": "PART_OF", "target": "ChronoGraph"}
        ],
        "triples": []
    })

    mock_llm.complete.side_effect = [
        MagicMock(text=slack_response),
        MagicMock(text=github_response),
        MagicMock(text=jira_response)
    ]

    extractor = GraphExtractor(llm=mock_llm)

    # 3. Execute process_records() batch pipeline
    print("\n[2] EXECUTING PROCESS_RECORDS() BATCH EXTRACTION...")
    result = process_records(sample_records, extractor=extractor, raise_on_validation_error=True)

    print("\n[3] NEO4J-READY VALIDATED GRAPH OUTPUT:")
    print(json.dumps(result, indent=2))

    print("\n" + "=" * 70)
    print("      WEEK 2 DEMONSTRATION SUMMARY")
    print("=" * 70)
    print(f"  [OK] Status: Valid = {result.get('is_valid')}")
    print(f"  [OK] Entities Consolidated: {len(result['entities'])} unique entities with stable IDs")
    print(f"  [OK] Relationships Extracted: {len(result['relationships'])} relationships (multiple predicates preserved)")
    print(f"  [OK] Triples Synchronized: {len(result['triples'])} triples")
    print(f"  [OK] Metadata Preserved: {len(result['metadata']['records'])} record metadata blocks")
    print("=" * 70)


if __name__ == "__main__":
    run_week2_demo()
