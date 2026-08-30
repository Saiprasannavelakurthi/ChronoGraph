import json
from unittest.mock import MagicMock
import pytest
from src.pipeline import process_text
from src.extractor import GraphExtractor
from src.validator import ExtractionValidationError


def test_empty_input():
    """Test process_text with empty input string."""
    result = process_text("")
    assert result["entities"] == []
    assert result["relationships"] == []
    assert result["triples"] == []

    # Test empty input with metadata
    meta = {"source": "slack", "timestamp": "2026-08-10T10:00:00Z"}
    result_meta = process_text("   \n\t  ", metadata=meta)
    assert result_meta["entities"] == []
    assert result_meta["relationships"] == []
    assert result_meta["triples"] == []
    assert result_meta["metadata"] == meta


def test_pipeline_process_text():
    """Test full process_text pipeline with a mocked LLM extractor."""
    mock_llm = MagicMock()
    mock_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "ASKED", "target": "Karkuvel"},
            {"source": "Karkuvel", "relation": "WORKED_ON", "target": "ChronoGraph"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "ASKED", "object": "Karkuvel"},
            {"subject": "Karkuvel", "predicate": "WORKED_ON", "object": "ChronoGraph"}
        ]
    })
    mock_llm.complete.return_value = MagicMock(text=mock_response)

    extractor = GraphExtractor(llm=mock_llm)
    result = process_text("Aathi asked Karkuvel about ChronoGraph", extractor=extractor)

    assert "entities" in result
    assert "relationships" in result
    assert "triples" in result
    assert len(result["entities"]) == 3
    assert len(result["relationships"]) == 2
    assert len(result["triples"]) == 2


def test_metadata_preservation():
    """Test that metadata passed to process_text is preserved in the output dictionary."""
    mock_llm = MagicMock()
    mock_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=mock_response)

    extractor = GraphExtractor(llm=mock_llm)
    metadata_in = {"source": "jira", "timestamp": "2026-08-10T14:20:00Z", "task_id": "CG-102"}

    result = process_text("Aathi updated the task", metadata=metadata_in, extractor=extractor)

    assert "metadata" in result
    assert result["metadata"] == metadata_in
    assert result["metadata"]["source"] == "jira"


def test_pipeline_validation_failure_raises_exception():
    """Test that invalid extractions raise ExtractionValidationError when raise_on_validation_error=True."""
    mock_llm = MagicMock()
    # Invalid: relationship target 'UnknownSystem' is not an extracted entity
    mock_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "WORKED_ON", "target": "UnknownSystem"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=mock_response)

    extractor = GraphExtractor(llm=mock_llm)

    with pytest.raises(ExtractionValidationError) as exc_info:
        process_text("Aathi worked on UnknownSystem", extractor=extractor, raise_on_validation_error=True)

    assert "validation failed" in str(exc_info.value).lower()
    assert len(exc_info.value.errors) > 0


def test_pipeline_validation_failure_payload_when_no_raise():
    """Test that invalid extractions return is_valid=False payload when raise_on_validation_error=False."""
    mock_llm = MagicMock()
    mock_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "WORKED_ON", "target": "UnknownSystem"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=mock_response)

    extractor = GraphExtractor(llm=mock_llm)
    result = process_text("Aathi worked on UnknownSystem", extractor=extractor, raise_on_validation_error=False)

    assert result["is_valid"] is False
    assert "validation_errors" in result
    assert len(result["validation_errors"]) > 0


def test_case_preservation():
    """Test that commit hashes, Jira issue IDs, and usernames maintain case sensitive identifiers."""
    mock_llm = MagicMock()
    mock_response = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "commit_abc1234", "name": "abc1234", "type": "COMMIT"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "abc1234"},
            {"source": "Karkuvel", "relation": "ASSIGNED_TO", "target": "CG-102"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=mock_response)

    extractor = GraphExtractor(llm=mock_llm)
    result = process_text("Karkuvel committed abc1234 and was assigned CG-102", extractor=extractor)

    entities_by_name = {e["name"]: e for e in result["entities"]}
    assert "abc1234" in entities_by_name
    assert "CG-102" in entities_by_name
