import json
from unittest.mock import MagicMock
import pytest

from src.extractor import GraphExtractor
from src.errors import GraphExtractionError
from src.pipeline import process_text, process_records
from src.validator import validate_extraction, ExtractionValidationError
from src.utils.text_utils import generate_entity_id, normalize_entity_name


@pytest.fixture
def mock_llm():
    """Fixture providing a mocked LlamaIndex LLM instance."""
    return MagicMock()


def test_source_aware_extraction_slack(mock_llm):
    """Test source-aware extraction with Slack context."""
    llm_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "channel_dev_chat", "name": "#dev-chat", "type": "CHANNEL"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "PARTICIPATED_IN", "target": "#dev-chat"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=llm_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = process_text("Aathi posted in #dev-chat", source="slack", extractor=extractor)

    assert result["is_valid"] is True
    assert len(result["entities"]) == 2
    # Verify user prompt received source context
    called_prompt = mock_llm.complete.call_args[0][0]
    assert "Source Context: SLACK" in called_prompt


def test_source_aware_extraction_github(mock_llm):
    """Test source-aware extraction with GitHub context."""
    llm_json = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "commit_abc1234", "name": "abc1234", "type": "COMMIT"},
            {"id": "repository_chronograph", "name": "ChronoGraph", "type": "REPOSITORY"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "abc1234"},
            {"source": "abc1234", "relation": "PART_OF", "target": "ChronoGraph"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=llm_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = process_text("Karkuvel committed abc1234 to ChronoGraph", source="github", extractor=extractor)

    assert result["is_valid"] is True
    called_prompt = mock_llm.complete.call_args[0][0]
    assert "Source Context: GITHUB" in called_prompt


def test_source_aware_extraction_jira(mock_llm):
    """Test source-aware extraction with Jira context."""
    llm_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=llm_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = process_text("Aathi was assigned CG-102", source="jira", extractor=extractor)

    assert result["is_valid"] is True
    called_prompt = mock_llm.complete.call_args[0][0]
    assert "Source Context: JIRA" in called_prompt


def test_stable_entity_ids():
    """Test deterministic entity ID generation across sources and inputs."""
    assert generate_entity_id("Karkuvel", "PERSON") == "person_karkuvel"
    assert generate_entity_id("karkuvel", "PERSON") == "person_karkuvel"
    assert generate_entity_id("ChronoGraph", "REPOSITORY") == "repository_chronograph"
    assert generate_entity_id("CG-102", "ISSUE") == "issue_cg_102"
    assert generate_entity_id("abc1234", "COMMIT") == "commit_abc1234"
    assert generate_entity_id("#24", "PULL_REQUEST") == "pull_request_24"


def test_identifier_preservation():
    """Test that commit hashes, Jira issue IDs, PR numbers, and handles are preserved exactly."""
    assert normalize_entity_name("CG-102") == "CG-102"
    assert normalize_entity_name("abc1234") == "abc1234"
    assert normalize_entity_name("#24") == "#24"
    assert normalize_entity_name("@karkuvel") == "@karkuvel"


def test_batch_process_records(mock_llm):
    """Test batch processing across Slack, GitHub, and Jira records."""
    slack_resp = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "MENTIONED", "target": "Karkuvel"}
        ],
        "triples": []
    })
    github_resp = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "repository_chronograph", "name": "ChronoGraph", "type": "REPOSITORY"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "ChronoGraph"}
        ],
        "triples": []
    })
    jira_resp = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"}
        ],
        "triples": []
    })

    mock_llm.complete.side_effect = [
        MagicMock(text=slack_resp),
        MagicMock(text=github_resp),
        MagicMock(text=jira_resp)
    ]
    extractor = GraphExtractor(llm=mock_llm)

    records = [
        {
            "source": "slack",
            "text": "Aathi mentioned Karkuvel in slack.",
            "metadata": {"channel": "#dev-chat", "timestamp": "2026-08-10T10:00:00Z"}
        },
        {
            "source": "github",
            "text": "Karkuvel committed to ChronoGraph.",
            "metadata": {"repository": "ChronoGraph", "timestamp": "2026-08-10T11:00:00Z"}
        },
        {
            "source": "jira",
            "text": "Aathi was assigned CG-102.",
            "metadata": {"project": "CG", "timestamp": "2026-08-10T12:00:00Z"}
        }
    ]

    result = process_records(records, extractor=extractor)

    assert result["is_valid"] is True
    # Verify entity consolidation (Karkuvel appears in 2 records, Aathi in 2 records)
    # Total unique entities: Aathi, Karkuvel, ChronoGraph, CG-102 = 4
    entity_names = {e["name"] for e in result["entities"]}
    assert entity_names == {"Aathi", "Karkuvel", "ChronoGraph", "CG-102"}
    
    # Verify metadata preservation for every record
    records_meta = result["metadata"]["records"]
    assert len(records_meta) == 3
    assert records_meta[0]["channel"] == "#dev-chat"
    assert records_meta[1]["repository"] == "ChronoGraph"
    assert records_meta[2]["project"] == "CG"


def test_cross_record_deduplication(mock_llm):
    """Test entity deduplication across records while preserving distinct predicates."""
    rec1_json = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "WORKED_ON", "target": "ChronoGraph"}
        ],
        "triples": []
    })
    rec2_json = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "karkuvel", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "ChronoGraph"},
            {"source": "karkuvel", "relation": "WORKED_ON", "target": "ChronoGraph"}  # Exact duplicate relationship
        ],
        "triples": []
    })

    mock_llm.complete.side_effect = [
        MagicMock(text=rec1_json),
        MagicMock(text=rec2_json)
    ]
    extractor = GraphExtractor(llm=mock_llm)

    records = [
        {"source": "slack", "text": "Karkuvel worked on ChronoGraph.", "metadata": {}},
        {"source": "github", "text": "karkuvel committed to ChronoGraph.", "metadata": {}}
    ]

    result = process_records(records, extractor=extractor)

    # Entities should be deduplicated to 2 (Karkuvel and ChronoGraph)
    assert len(result["entities"]) == 2
    
    # Relationships should deduplicate exact duplicate (WORKED_ON) but keep distinct (COMMITTED)
    assert len(result["relationships"]) == 2
    rel_tuples = {(r["source"], r["relation"], r["target"]) for r in result["relationships"]}
    assert ("Karkuvel", "WORKED_ON", "ChronoGraph") in rel_tuples
    assert ("Karkuvel", "COMMITTED", "ChronoGraph") in rel_tuples


def test_graph_extraction_error_raised_on_llm_failure(mock_llm):
    """Test that GraphExtractionError is raised when the LLM API call fails."""
    mock_llm.complete.side_effect = Exception("Groq API 503 Service Unavailable")
    extractor = GraphExtractor(llm=mock_llm)

    with pytest.raises(GraphExtractionError) as exc_info:
        extractor.extract("Some input text")

    assert "LLM extraction API call failed" in str(exc_info.value)
    assert isinstance(exc_info.value.original_error, Exception)


def test_validation_dangling_reference_error():
    """Test that validator catches dangling entity references."""
    invalid_payload = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "REVIEWED", "target": "DanglingPR"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "REVIEWED", "object": "DanglingPR"}
        ]
    }
    
    validation = validate_extraction(invalid_payload)
    assert validation.is_valid is False
    assert any("dangling" in err.lower() for err in validation.errors)
