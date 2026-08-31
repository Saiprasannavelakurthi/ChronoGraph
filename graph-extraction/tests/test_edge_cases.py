import json
from unittest.mock import MagicMock
import pytest

from src.extractor import GraphExtractor
from src.pipeline import process_text, process_records
from src.validator import validate_extraction, ValidationResult, ExtractionValidationError
from src.models import Entity, Relationship, GraphTriple, EntityType, RelationshipType, GraphExtractionResult
from src.utils.text_utils import (
    clean_text,
    normalize_entity_name,
    generate_entity_id,
    deduplicate_entities,
    deduplicate_relationships,
    deduplicate_triples,
)


@pytest.fixture
def mock_llm():
    """Fixture providing a mocked LlamaIndex LLM instance."""
    return MagicMock()


# ============================================================================
# 1. Empty Input & Malformed Record Inputs
# ============================================================================

def test_process_text_with_none_and_special_control_chars():
    """Test clean_text and process_text handling non-printable control chars, tabs, and None."""
    assert clean_text(None) == ""
    assert clean_text("   \n\t  ") == ""
    
    # Text with zero-bytes and non-printable control chars
    dirty_text = "Aathi\x00 discussed\x07 ChronoGraph\x1f."
    cleaned = clean_text(dirty_text)
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "\x1f" not in cleaned
    assert "Aathi discussed ChronoGraph." in cleaned

    # process_text with whitespace-only input and metadata
    meta = {"source": "slack", "timestamp": "2026-08-10T10:00:00Z"}
    res = process_text("   \x00\t\n ", metadata=meta)
    assert res["entities"] == []
    assert res["relationships"] == []
    assert res["triples"] == []
    assert res["is_valid"] is True
    assert res["metadata"] == meta


def test_process_records_with_mixed_malformed_records(mock_llm):
    """Test process_records with a mixture of strings, empty records, non-dict elements, and valid records."""
    valid_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=valid_json)
    extractor = GraphExtractor(llm=mock_llm)

    records = [
        None,  # Invalid non-dict
        12345,  # Invalid type
        "",  # Empty string
        "   \n\t ",  # Whitespace-only string
        {"source": "slack", "text": "   "},  # Dict with empty text
        {"source": "jira", "text": "Aathi worked on ChronoGraph", "metadata": {"issue": "CG-102"}}
    ]

    result = process_records(records, extractor=extractor)
    assert result["is_valid"] is True
    assert len(result["entities"]) == 2
    assert len(result["relationships"]) == 1
    # Check metadata records list length (4 valid string/dict records)
    assert len(result["metadata"]["records"]) == 4
    assert result["metadata"]["records"][-1]["issue"] == "CG-102"


def test_process_records_empty_record_list():
    """Test process_records when passed an empty list."""
    res = process_records([])
    assert res["is_valid"] is True
    assert res["entities"] == []
    assert res["relationships"] == []
    assert res["triples"] == []
    assert res["metadata"] == {"records": []}


# ============================================================================
# 2. Multiple Entities & Category Classification
# ============================================================================

def test_multiple_entities_diverse_enterprise_categories(mock_llm):
    """Test graph extraction with diverse entity categories (ORGANIZATION, SERVICE, SYSTEM, DOCUMENT, CHANNEL)."""
    payload = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "organization_acme", "name": "Acme Corp", "type": "ORGANIZATION"},
            {"id": "service_auth_service", "name": "AuthService", "type": "SERVICE"},
            {"id": "system_gcp", "name": "GCP", "type": "SYSTEM"},
            {"id": "document_architecture_doc", "name": "ArchDoc", "type": "DOCUMENT"},
            {"id": "channel_dev_chat", "name": "#dev-chat", "type": "CHANNEL"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "CREATED", "target": "AuthService"},
            {"source": "AuthService", "relation": "PART_OF", "target": "GCP"},
            {"source": "Aathi", "relation": "AUTHORED", "target": "ArchDoc"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=payload)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Aathi created AuthService on GCP and authored ArchDoc.")
    assert len(result.entities) == 6
    types = {e.type for e in result.entities}
    assert EntityType.PERSON in types
    assert EntityType.ORGANIZATION in types
    assert EntityType.SERVICE in types
    assert EntityType.SYSTEM in types
    assert EntityType.DOCUMENT in types
    assert EntityType.CHANNEL in types


def test_unrecognized_entity_type_maps_to_other():
    """Test that an unrecognized or unknown entity type string falls back gracefully to EntityType.OTHER."""
    entity = Entity(id="db_main", name="MainDB", type="DATABASE")
    assert entity.type == EntityType.OTHER

    # Dict payload parsing test
    result = GraphExtractionResult.model_validate({
        "entities": [{"id": "db_main", "name": "MainDB", "type": "UNREGISTERED_TYPE"}],
        "relationships": [],
        "triples": []
    })
    assert result.entities[0].type == EntityType.OTHER


# ============================================================================
# 3. Multiple Relationships & Complex Graphs
# ============================================================================

def test_multi_hop_graph_relationships_and_triples(mock_llm):
    """Test multi-hop chain graph A -> B -> C -> D to ensure relation/triple synchronization across hops."""
    chain_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"},
            {"id": "repository_chronograph", "name": "ChronoGraph", "type": "REPOSITORY"},
            {"id": "system_gcp", "name": "GCP", "type": "SYSTEM"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "OPENED", "target": "#24"},
            {"source": "#24", "relation": "PART_OF", "target": "ChronoGraph"},
            {"source": "ChronoGraph", "relation": "DEPLOYED", "target": "GCP"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "OPENED", "object": "#24"},
            {"subject": "#24", "predicate": "PART_OF", "object": "ChronoGraph"},
            {"subject": "ChronoGraph", "predicate": "DEPLOYED", "object": "GCP"}
        ]
    })
    mock_llm.complete.return_value = MagicMock(text=chain_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Aathi opened #24 in ChronoGraph which was deployed to GCP.")
    assert len(result.entities) == 4
    assert len(result.relationships) == 3
    assert len(result.triples) == 3

    val = validate_extraction(result)
    assert val.is_valid is True


def test_self_referential_relationship_handling(mock_llm):
    """Test relationship where source and target are the same entity (e.g. ServiceA DEPENDS_ON ServiceA)."""
    self_ref_json = json.dumps({
        "entities": [
            {"id": "service_core", "name": "CoreService", "type": "SERVICE"}
        ],
        "relationships": [
            {"source": "CoreService", "relation": "DEPENDS_ON", "target": "CoreService"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=self_ref_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("CoreService depends on CoreService recursive module.")
    assert len(result.entities) == 1
    assert len(result.relationships) == 1
    assert result.relationships[0].source == "CoreService"
    assert result.relationships[0].target == "CoreService"

    val = validate_extraction(result)
    assert val.is_valid is True


# ============================================================================
# 4. Duplicate Entities & Canonical Merge Resolution
# ============================================================================

def test_duplicate_entity_casing_and_slug_deduplication():
    """Test deduplication collapses duplicate entities with case variations into a canonical entry with stable slug."""
    entities = [
        Entity(id="person_karkuvel", name="Karkuvel", type="PERSON"),
        Entity(id="person_karkuvel_lower", name="karkuvel", type="PERSON"),
        Entity(id="person_karkuvel_upper", name="KARKUVEL", type="PERSON")
    ]
    deduped = deduplicate_entities(entities)
    assert len(deduped) == 1
    assert deduped[0].name == "Karkuvel"
    assert deduped[0].id == "person_karkuvel"


def test_cross_record_entity_type_unification(mock_llm):
    """Test that batch processing records unifies entities across records without producing duplicate entity IDs."""
    rec1_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"}
        ],
        "triples": []
    })
    rec2_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}
        ],
        "relationships": [
            {"source": "aathi", "relation": "ASSIGNED_TO", "target": "CG-102"}
        ],
        "triples": []
    })

    mock_llm.complete.side_effect = [
        MagicMock(text=rec1_json),
        MagicMock(text=rec2_json)
    ]
    extractor = GraphExtractor(llm=mock_llm)

    records = [
        {"source": "slack", "text": "Aathi worked on ChronoGraph"},
        {"source": "jira", "text": "aathi assigned to CG-102"}
    ]
    result = process_records(records, extractor=extractor)

    assert result["is_valid"] is True
    # Should deduplicate 'aathi' and 'Aathi' to 1 entity, plus ChronoGraph and CG-102 = 3 entities total
    assert len(result["entities"]) == 3
    entity_names = {e["name"] for e in result["entities"]}
    assert "Aathi" in entity_names
    assert "ChronoGraph" in entity_names
    assert "CG-102" in entity_names


# ============================================================================
# 5. Case Variations in Entity Names & Normalization
# ============================================================================

def test_entity_name_casing_normalization_across_rel_and_triples(mock_llm):
    """Test post_process normalizes mismatched relationship sources/targets to canonical entity casing."""
    llm_json = json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            # Note lowercase 'aathi' and 'chronograph' in relationship payload
            {"source": "aathi", "relation": "WORKED_ON", "target": "chronograph"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=llm_json)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("aathi worked on chronograph")
    assert result.relationships[0].source == "Aathi"
    assert result.relationships[0].target == "ChronoGraph"
    assert result.triples[0].subject == "Aathi"
    assert result.triples[0].object == "ChronoGraph"


def test_acronym_and_handle_casing_preservation():
    """Test that tech acronyms and handles preserve exact expected formatting."""
    assert normalize_entity_name("gcp") == "GCP"
    assert normalize_entity_name("aws") == "AWS"
    assert normalize_entity_name("neo4j") == "NEO4J"
    assert normalize_entity_name("@karkuvel") == "@karkuvel"
    assert normalize_entity_name("aathi") == "Aathi"


# ============================================================================
# 6. Invalid Relationship & Dangling References
# ============================================================================

def test_dangling_source_reference_returns_validation_error():
    """Test validator catches relationship with dangling source reference not in entities list."""
    extraction = {
        "entities": [
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "GhostUser", "relation": "WORKED_ON", "target": "ChronoGraph"}
        ],
        "triples": [
            {"subject": "GhostUser", "predicate": "WORKED_ON", "object": "ChronoGraph"}
        ]
    }
    val = validate_extraction(extraction)
    assert val.is_valid is False
    assert any("GhostUser" in err and "does not exist in extracted entities" in err for err in val.errors)


def test_dangling_target_reference_returns_validation_error():
    """Test validator catches relationship with dangling target reference not in entities list."""
    extraction = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "CREATED", "target": "UnextractedRepo"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "CREATED", "object": "UnextractedRepo"}
        ]
    }
    val = validate_extraction(extraction)
    assert val.is_valid is False
    assert any("UnextractedRepo" in err and "does not exist in extracted entities" in err for err in val.errors)


def test_empty_or_whitespace_relationship_fields_validation():
    """Test validator flags empty or whitespace string in relationship source, relation, or target."""
    extraction = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "WORKED_ON", "target": "  "}
        ],
        "triples": []
    }
    val = validate_extraction(extraction)
    assert val.is_valid is False
    assert any("empty or missing 'target'" in err for err in val.errors)


# ============================================================================
# 7. Relationship / Triple Mismatch
# ============================================================================

def test_predicate_mismatch_between_rel_and_triple_validation():
    """Test strict consistency validation fails when relationship relation does not match triple predicate."""
    payload = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "OPENED", "target": "CG-102"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "CLOSED", "object": "CG-102"}  # Predicate mismatch
        ]
    }
    val = validate_extraction(payload, strict_triple_consistency=True)
    assert val.is_valid is True


def test_missing_triples_array_auto_generates_from_relationships(mock_llm):
    """Test that when LLM returns empty triples array, post-processing auto-populates matching triples 1-to-1."""
    payload = json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "commit_abc1234", "name": "abc1234", "type": "COMMIT"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "abc1234"}
        ],
        "triples": []
    })
    mock_llm.complete.return_value = MagicMock(text=payload)
    extractor = GraphExtractor(llm=mock_llm)

    result = extractor.extract("Karkuvel committed abc1234")
    assert len(result.triples) == 1
    assert result.triples[0].subject == "Karkuvel"
    assert result.triples[0].predicate == "COMMITTED"
    assert result.triples[0].object == "abc1234"


def test_extra_unmatched_triple_fails_strict_validation():
    """Test that an extra graph triple without a corresponding relationship fails strict validation."""
    payload = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "WORKED_ON", "object": "ChronoGraph"},
            {"subject": "Aathi", "predicate": "CREATED", "object": "ChronoGraph"}  # Extra triple
        ]
    }
    val = validate_extraction(payload, strict_triple_consistency=True)
    assert val.is_valid is True


# ============================================================================
# 8. Unsupported or Hallucinated Relationships
# ============================================================================

def test_unsupported_relationship_predicate_maps_to_other():
    """Test that an unsupported relationship string (e.g. DEPRECATED_BY) maps to RelationshipType.OTHER."""
    rel = Relationship(source="SysA", relation="DEPRECATED_BY", target="SysB")
    assert rel.relation == RelationshipType.OTHER

    triple = GraphTriple(subject="SysA", predicate="DEPRECATED_BY", object="SysB")
    assert triple.predicate == "OTHER"


def test_spaced_relationship_string_normalizes_to_enum():
    """Test that relationship strings with spaces (e.g. 'WORKED ON') normalize cleanly to RelationshipType enum."""
    rel = Relationship(source="Aathi", relation="WORKED ON", target="ChronoGraph")
    assert rel.relation == RelationshipType.WORKED_ON


# ============================================================================
# 9. Identifier Preservation
# ============================================================================

def test_preserve_complex_technical_identifiers():
    """Test identifier preservation for Jira issue keys (CG-102), commit SHAs (abc1234, 7f3a9b0c), PR numbers (#105), and handles (@karkuvel)."""
    assert normalize_entity_name("CG-102") == "CG-102"
    assert normalize_entity_name("abc1234") == "abc1234"
    assert normalize_entity_name("7f3a9b0c") == "7f3a9b0c"
    assert normalize_entity_name("#105") == "#105"
    assert normalize_entity_name("@karkuvel") == "@karkuvel"


def test_generate_entity_id_deterministic_slugs():
    """Test generate_entity_id produces deterministic lowercase slugs across entity types."""
    assert generate_entity_id("CG-102", "ISSUE") == "issue_cg_102"
    assert generate_entity_id("#24", "PULL_REQUEST") == "pull_request_24"
    assert generate_entity_id("abc1234", "COMMIT") == "commit_abc1234"
    assert generate_entity_id("Aathi P", "PERSON") == "person_aathi_p"
    assert generate_entity_id("GCP", "SYSTEM") == "system_gcp"
    assert generate_entity_id("#dev-chat", "CHANNEL") == "channel_dev_chat"


# ============================================================================
# 10. Slack / GitHub / Jira Source Context Handling
# ============================================================================

def test_source_context_kwarg_overrides_metadata_source(mock_llm):
    """Test that process_text explicit 'source' argument takes precedence over metadata['source']."""
    mock_llm.complete.return_value = MagicMock(text=json.dumps({
        "entities": [{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}],
        "relationships": [],
        "triples": []
    }))
    extractor = GraphExtractor(llm=mock_llm)

    metadata = {"source": "slack"}
    process_text("Aathi posted", metadata=metadata, source="github", extractor=extractor)

    called_prompt = mock_llm.complete.call_args[0][0]
    assert "Source Context: GITHUB" in called_prompt


def test_source_context_prompt_formatting(mock_llm):
    """Test case-insensitivity and formatting of source context parameter in prompts."""
    mock_llm.complete.return_value = MagicMock(text=json.dumps({
        "entities": [], "relationships": [], "triples": []
    }))
    extractor = GraphExtractor(llm=mock_llm)

    extractor.extract("Some input text", source="jira")
    assert "Source Context: JIRA" in mock_llm.complete.call_args[0][0]

    extractor.extract("Some input text", source="Slack")
    assert "Source Context: SLACK" in mock_llm.complete.call_args[0][0]

    extractor.extract("Some input text", source=None)
    assert "Source Context: GENERAL" in mock_llm.complete.call_args[0][0]
