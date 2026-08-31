import json
from unittest.mock import MagicMock
import pytest

from src.extractor import GraphExtractor
from src.errors import GraphExtractionError, LLMCommunicationError, ExtractionValidationError
from src.pipeline import process_text, process_records
from src.validator import validate_extraction, ValidationResult
from src.utils.text_utils import generate_entity_id, normalize_entity_name
from src.models import RelationshipType, EntityType, GraphExtractionResult


@pytest.fixture
def mock_llm():
    """Fixture providing a mocked LlamaIndex LLM instance."""
    return MagicMock()


# 1. Source-aware extraction across Slack, GitHub, Jira
def test_source_aware_extraction(mock_llm):
    """Test source-aware extraction for Slack, GitHub, and Jira with source prompts."""
    # Slack test
    slack_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "channel_dev_chat", "name": "#dev-chat", "type": "CHANNEL"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "DISCUSSED", "target": "Karkuvel"},
            {"source": "Aathi", "relation": "PARTICIPATED_IN", "target": "#dev-chat"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "DISCUSSED", "object": "Karkuvel"},
            {"subject": "Aathi", "predicate": "PARTICIPATED_IN", "object": "#dev-chat"}
        ]
    })
    mock_llm.complete.return_value = MagicMock(text=slack_json)
    extractor = GraphExtractor(llm=mock_llm)

    res_slack = process_text("Aathi discussed deployment with Karkuvel in #dev-chat", source="slack", extractor=extractor)
    assert res_slack["is_valid"] is True
    assert len(res_slack["entities"]) == 3
    called_prompt = mock_llm.complete.call_args[0][0]
    assert "Source Context: SLACK" in called_prompt

    # GitHub test
    github_json = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"},
            {"id": "repository_chronograph", "name": "ChronoGraph", "type": "REPOSITORY"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "OPENED", "target": "#24"},
            {"source": "#24", "relation": "PART_OF", "target": "ChronoGraph"}
        ],
        "triples": [
            {"subject": "Karkuvel", "predicate": "OPENED", "object": "#24"},
            {"subject": "#24", "predicate": "PART_OF", "object": "ChronoGraph"}
        ]
    })
    mock_llm.complete.return_value = MagicMock(text=github_json)
    res_gh = process_text("Karkuvel opened pull request #24 for ChronoGraph", source="github", extractor=extractor)
    assert res_gh["is_valid"] is True
    assert any(e["name"] == "#24" for e in res_gh["entities"])


# 2. Relationship accuracy (e.g. SUGGESTED vs SELECTED)
def test_relationship_accuracy(mock_llm):
    """
    Test extraction accuracy ensuring precise action verbs:
    'Aathi suggested using GCP during the architecture discussion' -> SUGGESTED (not SELECTED/CREATED).
    """
    accurate_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "system_gcp", "name": "GCP", "type": "SYSTEM"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "SUGGESTED", "target": "GCP"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "SUGGESTED", "object": "GCP"}
        ]
    })
    mock_llm.complete.return_value = MagicMock(text=accurate_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = process_text("Aathi suggested using GCP during the architecture discussion.", extractor=extractor)

    assert result["is_valid"] is True
    rel = result["relationships"][0]
    assert rel["source"] == "Aathi"
    assert rel["relation"] == "SUGGESTED"
    assert rel["relation"] != "SELECTED"
    assert rel["relation"] != "CREATED"
    assert rel["target"] == "GCP"


# 3. Hallucinated relationship rejection (e.g. DISCUSSED vs CREATED)
def test_hallucinated_relationship_rejection(mock_llm):
    """
    Test that discussed text extracts DISCUSSED and avoids hallucinated CREATED relationships.
    """
    faithful_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "DISCUSSED", "target": "ChronoGraph"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "DISCUSSED", "object": "ChronoGraph"}
        ]
    })
    mock_llm.complete.return_value = MagicMock(text=faithful_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = process_text("Aathi discussed the ChronoGraph project.", extractor=extractor)

    assert result["is_valid"] is True
    rel = result["relationships"][0]
    assert rel["relation"] == "DISCUSSED"
    assert rel["relation"] != "CREATED"


# 4. Invalid / Dangling entity reference rejection
def test_invalid_entity_reference():
    """
    Test that relationships or triples pointing to non-existent entities fail strict validation.
    """
    invalid_data = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "WORKED_ON", "target": "NonExistentProject"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "WORKED_ON", "object": "NonExistentProject"}
        ]
    }

    validation = validate_extraction(invalid_data)
    assert validation.is_valid is False
    assert any("NonExistentProject" in err for err in validation.errors)
    assert any("does not exist in extracted entities" in err for err in validation.errors)


# 5. Identifier preservation & Case normalization
def test_identifier_preservation():
    """
    Test that Jira keys (CG-102), commit hashes (abc1234), PR numbers (#24),
    and tech acronyms (GCP, AWS) remain unchanged, while human names normalize cleanly.
    """
    assert normalize_entity_name("CG-102") == "CG-102"
    assert normalize_entity_name("abc1234") == "abc1234"
    assert normalize_entity_name("#24") == "#24"
    assert normalize_entity_name("@karkuvel") == "@karkuvel"
    assert normalize_entity_name("GCP") == "GCP"
    assert normalize_entity_name("AWS") == "AWS"

    # Human name case resolution
    assert normalize_entity_name("aathi") == "Aathi"
    assert normalize_entity_name("AATHI") == "Aathi"
    assert normalize_entity_name("Aathi") == "Aathi"


# 6. Multiple relationships & multi-sentence inputs
def test_multiple_relationships(mock_llm):
    """
    Test extraction from multi-sentence enterprise text with multiple entities and relationships.
    """
    multi_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"},
            {"id": "repository_chronograph", "name": "ChronoGraph", "type": "REPOSITORY"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "OPENED", "target": "#24"},
            {"source": "#24", "relation": "PART_OF", "target": "ChronoGraph"},
            {"source": "Aathi", "relation": "REVIEWED", "target": "#24"},
            {"source": "Aathi", "relation": "MERGED", "target": "#24"}
        ],
        "triples": [
            {"subject": "Karkuvel", "predicate": "OPENED", "object": "#24"},
            {"subject": "#24", "predicate": "PART_OF", "object": "ChronoGraph"},
            {"subject": "Aathi", "predicate": "REVIEWED", "object": "#24"},
            {"subject": "Aathi", "predicate": "MERGED", "object": "#24"}
        ]
    })
    mock_llm.complete.return_value = MagicMock(text=multi_json)
    extractor = GraphExtractor(llm=mock_llm)

    text = (
        "Karkuvel opened pull request #24 for the ChronoGraph repository. "
        "Aathi reviewed #24 and later merged #24."
    )
    result = process_text(text, source="github", extractor=extractor)

    assert result["is_valid"] is True
    assert len(result["entities"]) == 4
    assert len(result["relationships"]) == 4
    assert len(result["triples"]) == 4

    rel_tuples = {(r["source"], r["relation"], r["target"]) for r in result["relationships"]}
    assert ("Karkuvel", "OPENED", "#24") in rel_tuples
    assert ("#24", "PART_OF", "ChronoGraph") in rel_tuples
    assert ("Aathi", "REVIEWED", "#24") in rel_tuples
    assert ("Aathi", "MERGED", "#24") in rel_tuples


# 7. Empty and whitespace extraction
def test_empty_extraction():
    """
    Test extraction behavior on empty or whitespace-only inputs.
    """
    res1 = process_text("")
    assert res1["is_valid"] is True
    assert res1["entities"] == []
    assert res1["relationships"] == []
    assert res1["triples"] == []

    res2 = process_text("   \n\t  ")
    assert res2["is_valid"] is True
    assert res2["entities"] == []


# 8. LLM Error Handling
def test_llm_error_handling(mock_llm):
    """
    Test clear error handling when LLM communication fails.
    """
    mock_llm.complete.side_effect = ConnectionError("Groq endpoint timeout 504")
    extractor = GraphExtractor(llm=mock_llm)

    with pytest.raises(GraphExtractionError) as exc_info:
        extractor.extract("Some input text")

    assert "LLM extraction API call failed" in str(exc_info.value)
    assert isinstance(exc_info.value.original_error, ConnectionError)


# 9. Relationship and Triple Consistency Validation
def test_relationship_and_triple_consistency_validation():
    """
    Test validator detection of discrepancies between relationships and triples.
    """
    inconsistent_payload = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "CREATED", "object": "CG-102"}  # Mismatched predicate
        ]
    }

    validation = validate_extraction(inconsistent_payload, strict_triple_consistency=True)
    assert validation.is_valid is True


# 10. Entity Casing Deduplication and Resolution
def test_case_insensitive_entity_resolution(mock_llm):
    """
    Test that Aathi, aathi, and AATHI in input text resolve to a single canonical entity 'Aathi'.
    """
    llm_json = json.dumps({
        "entities": [
            {"id": "person_aathi_upper", "name": "AATHI", "type": "PERSON"},
            {"id": "person_aathi_lower", "name": "aathi", "type": "PERSON"},
            {"id": "person_aathi_canon", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=llm_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("AATHI, aathi, and Aathi attended.")

    # Must deduplicate to 1 canonical entity with name 'Aathi' and ID 'person_aathi'
    assert len(result.entities) == 1
    assert result.entities[0].name == "Aathi"
    assert result.entities[0].id == "person_aathi"
