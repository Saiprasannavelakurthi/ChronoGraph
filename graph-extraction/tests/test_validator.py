import pytest
from src.validator import validate_extraction, ValidationResult, ExtractionValidationError


def test_validation_success():
    """Test validation on a completely valid extraction structure."""
    valid_data = {
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "ChronoGraph"}
        ],
        "triples": [
            {"subject": "Karkuvel", "predicate": "COMMITTED", "object": "ChronoGraph"}
        ]
    }

    result = validate_extraction(valid_data)
    assert isinstance(result, ValidationResult)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_validation_missing_entity_fields():
    """Test validation failure when an entity is missing required fields."""
    invalid_data = {
        "entities": [
            {"id": "", "name": "", "type": "PERSON"}
        ],
        "relationships": [],
        "triples": []
    }

    result = validate_extraction(invalid_data)
    assert result.is_valid is False
    assert len(result.errors) > 0


def test_validation_dangling_relationship_reference_is_error():
    """Test that relationship source/target not present in entities is treated as a validation error."""
    dangling_ref_data = {
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "UnknownRepo"}
        ],
        "triples": [
            {"subject": "Karkuvel", "predicate": "COMMITTED", "object": "UnknownRepo"}
        ]
    }

    result = validate_extraction(dangling_ref_data)
    # Dangling reference must fail validation for Neo4j compatibility
    assert result.is_valid is False
    assert len(result.errors) >= 2
    assert any("UnknownRepo" in err for err in result.errors)


def test_validation_malformed_json_dict():
    """Test handling of non-dict or malformed objects passed to validator."""
    result = validate_extraction("Not a dict or GraphExtractionResult")
    assert len(result.errors) > 0

def test_validation_error_message_format():
    """Test that validation error messages include exact relation/triple details."""
    invalid_data = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "COMMITTED", "target": "Unknown"}
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "COMMITTED", "object": "Unknown"}
        ]
    }
    result = validate_extraction(invalid_data)
    assert result.is_valid is False
    
    # Check that error strings contain the formatted tuple
    rel_error_found = any("(Aathi -> COMMITTED -> Unknown)" in e for e in result.errors)
    trip_error_found = any("(Aathi -> COMMITTED -> Unknown)" in e for e in result.errors)
    
    assert rel_error_found, "Expected formatted tuple in relationship error message"
    assert trip_error_found, "Expected formatted tuple in triple error message"
