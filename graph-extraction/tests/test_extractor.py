import json
from unittest.mock import MagicMock
import pytest

from src.extractor import GraphExtractor
from src.models import EntityType, RelationshipType, GraphExtractionResult


@pytest.fixture
def mock_llm():
    """Fixture providing a mocked LlamaIndex LLM instance."""
    mock = MagicMock()
    return mock


def test_entity_extraction(mock_llm):
    """Test extracting entities from mock LLM response."""
    llm_json_response = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "WORKED_ON", "target": "ChronoGraph"}
        ],
        "triples": [
            {"subject": "Karkuvel", "predicate": "WORKED_ON", "object": "ChronoGraph"}
        ]
    })
    
    mock_llm.complete.return_value = MagicMock(text=llm_json_response)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Karkuvel worked on ChronoGraph")

    assert len(result.entities) == 2
    assert result.entities[0].name == "Karkuvel"
    assert result.entities[0].type == EntityType.PERSON
    assert result.entities[1].name == "ChronoGraph"
    assert result.entities[1].type == EntityType.PROJECT


def test_relationship_extraction(mock_llm):
    """Test relationship extraction and type mapping."""
    llm_json_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"}
        ],
        "triples": []
    })

    mock_llm.complete.return_value = MagicMock(text=llm_json_response)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Aathi was assigned to CG-102")

    assert len(result.relationships) == 1
    assert result.relationships[0].source == "Aathi"
    assert result.relationships[0].relation == RelationshipType.ASSIGNED_TO
    assert result.relationships[0].target == "CG-102"


def test_triple_generation(mock_llm):
    """Test auto-generation of triples when LLM omits triples array."""
    llm_json_response = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "commit_abc123", "name": "abc123", "type": "COMMIT"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "abc123"}
        ],
        "triples": []
    })

    mock_llm.complete.return_value = MagicMock(text=llm_json_response)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Karkuvel committed abc123")

    assert len(result.triples) == 1
    assert result.triples[0].subject == "Karkuvel"
    assert result.triples[0].predicate == "COMMITTED"
    assert result.triples[0].object == "abc123"


def test_duplicate_entities(mock_llm):
    """Test entity deduplication and name normalization."""
    llm_json_response = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "person_karkuvel_p", "name": "Karkuvel P", "type": "PERSON"},
            {"id": "person_karkuvel_lower", "name": "karkuvel", "type": "PERSON"}
        ],
        "relationships": [],
        "triples": []
    })

    mock_llm.complete.return_value = MagicMock(text=llm_json_response)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Karkuvel, Karkuvel P, and karkuvel participated.")

    # Deduplicated by normalized name key
    assert len(result.entities) <= 2
    entity_names = [e.name for e in result.entities]
    assert "Karkuvel P" in entity_names or "Karkuvel" in entity_names


def test_duplicate_relationships(mock_llm):
    """Test relationship deduplication."""
    llm_json_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"},
            {"source": "aathi", "relation": "WORKED_ON", "target": "chronograph"}
        ],
        "triples": []
    })

    mock_llm.complete.return_value = MagicMock(text=llm_json_response)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Aathi worked on ChronoGraph")

    assert len(result.relationships) == 1
    assert result.relationships[0].source == "Aathi"


def test_invalid_llm_output(mock_llm):
    """Test graceful fallback when LLM output is malformed markdown or invalid JSON."""
    mock_llm.complete.return_value = MagicMock(text="Sorry, I cannot process this text format.")
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Invalid text output response")

    assert isinstance(result, GraphExtractionResult)
    assert len(result.entities) == 0
    assert len(result.relationships) == 0
    assert len(result.triples) == 0


def test_multiple_relationships_between_same_entities(mock_llm):
    """Test that multiple distinct predicates between the same source and target entities are preserved."""
    llm_json_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "REVIEWED", "target": "#24"},
            {"source": "Aathi", "relation": "MERGED", "target": "#24"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "REVIEWED", "object": "#24"},
            {"subject": "Aathi", "predicate": "MERGED", "object": "#24"}
        ]
    })

    mock_llm.complete.return_value = MagicMock(text=llm_json_response)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Aathi reviewed pull request #24 and later merged it into main.")

    # Expect 2 distinct relationships and 2 distinct triples for the same entity pair
    assert len(result.relationships) == 2
    assert len(result.triples) == 2

    rel_types = {r.relation.value if hasattr(r.relation, "value") else str(r.relation) for r in result.relationships}
    triple_preds = {t.predicate for t in result.triples}

    assert rel_types == {"REVIEWED", "MERGED"}
    assert triple_preds == {"REVIEWED", "MERGED"}


def test_unknown_relationship_handling_maps_to_other(mock_llm):
    """Test that unsupported relationship predicates (e.g. TRANSFERRED_TO) map consistently to OTHER in both relationships and triples."""
    llm_json_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "system_main", "name": "System", "type": "SYSTEM"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "TRANSFERRED_TO", "target": "System"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "TRANSFERRED_TO", "object": "System"}
        ]
    })

    mock_llm.complete.return_value = MagicMock(text=llm_json_response)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Aathi transferred data to System")

    assert len(result.relationships) == 1
    assert len(result.triples) == 1

    rel = result.relationships[0]
    triple = result.triples[0]

    rel_str = rel.relation.value if hasattr(rel.relation, "value") else str(rel.relation)
    
    assert rel_str == "OTHER"
    assert triple.predicate == "OTHER"
    assert rel_str == triple.predicate


def test_relationship_and_triple_synchronization(mock_llm):
    """Test that every extracted relationship has a corresponding identical triple."""
    llm_json_response = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "MERGED", "target": "#24"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "MERGED", "object": "#24"}
        ]
    })

    mock_llm.complete.return_value = MagicMock(text=llm_json_response)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Aathi merged #24")

    # Assert relationships and triples are synchronized 1-to-1
    assert len(result.relationships) == len(result.triples)
    rel_tuples = {(r.source, r.relation.value if hasattr(r.relation, "value") else str(r.relation), r.target) for r in result.relationships}
    triple_tuples = {(t.subject, t.predicate, t.object) for t in result.triples}

    assert rel_tuples == triple_tuples
    assert ("Aathi", "MERGED", "#24") in rel_tuples
    assert ("Aathi", "MERGED", "#24") in triple_tuples





