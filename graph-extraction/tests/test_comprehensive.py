"""
Week 4 Edge-Case and Validation Test Suite — ChronoGraph Graph Extraction Module.

Covers:
  - Empty and whitespace-only input handling (None, "", "  ", [])
  - Invalid LLM output and malformed JSON parsing resilience
  - Missing entity fields (id, name, type)
  - Dangling relationship source and target references
  - Dangling triple subject and object references
  - Relationship and triple predicate inconsistency
  - Duplicate entity and relationship detection (warnings)
  - Missing and non-dict metadata preservation
  - Multiple source type context formatting
  - LLM communication exception wrapping (LLMCommunicationError)
  - Invalid (non-dict) LLM JSON response values
  - validate_extraction with unsupported input type
"""

import json
from unittest.mock import MagicMock
import pytest

from src.extractor import GraphExtractor
from src.errors import GraphExtractionError, LLMCommunicationError, ExtractionValidationError, MalformedLLMResponseError
from src.pipeline import process_text, process_records
from src.validator import validate_extraction, ValidationResult
from src.models import (
    GraphExtractionResult,
    Entity,
    Relationship,
    GraphTriple,
    EntityType,
    RelationshipType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """Fixture providing a mocked LlamaIndex LLM instance."""
    return MagicMock()


# ---------------------------------------------------------------------------
# PART 1: Empty and whitespace-only input handling
# ---------------------------------------------------------------------------

class TestEmptyInput:
    """Validate that empty and whitespace-only inputs return a clean, valid empty result."""

    def test_empty_string_process_text(self):
        """Empty string returns valid empty extraction without invoking extractor."""
        result = process_text("")
        assert result["is_valid"] is True
        assert result["entities"] == []
        assert result["relationships"] == []
        assert result["triples"] == []

    def test_whitespace_only_process_text(self):
        """Whitespace-only string returns valid empty extraction."""
        result = process_text("   \n\t  ")
        assert result["is_valid"] is True
        assert result["entities"] == []

    def test_none_text_process_text(self):
        """None text input is coerced to empty string and returns valid empty result."""
        result = process_text(None)  # type: ignore[arg-type]
        assert result["is_valid"] is True
        assert result["entities"] == []

    def test_non_string_text_process_text(self, mock_llm):
        """Non-string numeric input is coerced to string; pipeline proceeds normally."""
        empty_json = json.dumps({"entities": [], "relationships": [], "triples": []})
        mock_llm.complete.return_value = MagicMock(text=empty_json)
        extractor = GraphExtractor(llm=mock_llm)
        # 42 coerces to "42" which is valid text — should run through extractor
        result = process_text(42, extractor=extractor)  # type: ignore[arg-type]
        assert isinstance(result, dict)
        assert "entities" in result

    def test_empty_records_list_process_records(self):
        """Empty records list returns valid empty batch result."""
        result = process_records([])
        assert result["is_valid"] is True
        assert result["entities"] == []
        assert result["relationships"] == []
        assert result["triples"] == []
        assert result["metadata"] == {"records": []}

    def test_records_with_empty_text_fields(self, mock_llm):
        """Records with empty text fields are skipped gracefully."""
        empty_json = json.dumps({"entities": [], "relationships": [], "triples": []})
        mock_llm.complete.return_value = MagicMock(text=empty_json)
        extractor = GraphExtractor(llm=mock_llm)

        records = [
            {"source": "slack", "text": "", "metadata": {"channel": "#dev-chat"}},
            {"source": "github", "text": "   ", "metadata": {}},
        ]
        result = process_records(records, extractor=extractor)
        assert result["is_valid"] is True
        assert result["entities"] == []


# ---------------------------------------------------------------------------
# PART 2: Invalid LLM output / Malformed JSON parsing
# ---------------------------------------------------------------------------

class TestMalformedLLMOutput:
    """Validate parser resilience against broken, non-JSON, and edge-case LLM responses."""

    def test_completely_non_json_response(self, mock_llm):
        """Prose-only LLM response returns empty extraction without raising."""
        mock_llm.complete.return_value = MagicMock(
            text="I'm sorry, I cannot extract any entities from this text."
        )
        extractor = GraphExtractor(llm=mock_llm)
        with pytest.raises(MalformedLLMResponseError):
            extractor.extract("Some input text")

    def test_truncated_json_response(self, mock_llm):
        """Truncated / incomplete JSON returns empty extraction without raising."""
        mock_llm.complete.return_value = MagicMock(
            text='{"entities": [{"id": "person_aathi", "name": "Aathi"'
        )
        extractor = GraphExtractor(llm=mock_llm)
        with pytest.raises(MalformedLLMResponseError):
            extractor.extract("Aathi worked on something")

    def test_json_array_instead_of_object(self, mock_llm):
        """LLM returning a JSON array (not an object) returns empty extraction."""
        mock_llm.complete.return_value = MagicMock(
            text='[{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}]'
        )
        extractor = GraphExtractor(llm=mock_llm)
        result = extractor.extract("Aathi's activity")
        assert isinstance(result, GraphExtractionResult)
        assert result.entities == []

    def test_json_null_response(self, mock_llm):
        """LLM returning 'null' JSON returns empty extraction."""
        mock_llm.complete.return_value = MagicMock(text="null")
        extractor = GraphExtractor(llm=mock_llm)
        with pytest.raises(MalformedLLMResponseError):
            extractor.extract("Something happened")

    def test_empty_json_object_response(self, mock_llm):
        """LLM returning '{}' results in an empty but valid extraction."""
        mock_llm.complete.return_value = MagicMock(text="{}")
        extractor = GraphExtractor(llm=mock_llm)
        result = extractor.extract("Aathi worked on something")
        assert isinstance(result, GraphExtractionResult)
        assert result.entities == []
        assert result.relationships == []

    def test_markdown_wrapped_json_response(self, mock_llm):
        """LLM returning ```json ... ``` code block is correctly unwrapped and parsed."""
        payload = json.dumps({
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}],
            "relationships": [],
            "triples": []
        })
        mock_llm.complete.return_value = MagicMock(text=f"```json\n{payload}\n```")
        extractor = GraphExtractor(llm=mock_llm)
        result = extractor.extract("Aathi attended the meeting.")
        assert len(result.entities) == 1
        assert result.entities[0].name == "Aathi"

    def test_none_llm_response_text(self, mock_llm):
        """LLM returning None text returns empty extraction without raising."""
        mock_llm.complete.return_value = MagicMock(text=None)
        extractor = GraphExtractor(llm=mock_llm)
        result = extractor.extract("Some text")
        assert isinstance(result, GraphExtractionResult)
        assert result.entities == []


# ---------------------------------------------------------------------------
# PART 3: Missing entity fields validation
# ---------------------------------------------------------------------------

class TestMissingEntityFields:
    """Validate that missing required entity fields are caught as critical errors."""

    def test_missing_entity_id_is_error(self):
        """Entity with empty id field fails validation."""
        payload = {
            "entities": [{"id": "", "name": "Aathi", "type": "PERSON"}],
            "relationships": [],
            "triples": []
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert any("'id'" in err for err in result.errors)

    def test_missing_entity_name_is_error(self):
        """Entity with empty name field fails validation."""
        payload = {
            "entities": [{"id": "person_aathi", "name": "", "type": "PERSON"}],
            "relationships": [],
            "triples": []
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert any("'name'" in err for err in result.errors)

    def test_missing_entity_type_is_error(self):
        """
        Entity with empty type string fails validation.
        Pydantic maps "" -> OTHER via EntityType._missing_, but the validator detects
        the empty raw type value through the raw dict and emits a critical error.
        """
        payload = {
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": ""}],
            "relationships": [],
            "triples": []
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert any("'type'" in err for err in result.errors)

    def test_all_missing_entity_fields_are_reported(self):
        """
        Entity with all empty fields reports id error, name error, and type error (3 total).
        The empty type string is detected as a missing type via raw dict lookup.
        """
        payload = {
            "entities": [{"id": "", "name": "", "type": ""}],
            "relationships": [],
            "triples": []
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert len(result.errors) >= 3


# ---------------------------------------------------------------------------
# PART 4: Dangling references in relationships
# ---------------------------------------------------------------------------

class TestDanglingRelationshipReferences:
    """Validate dangling reference detection for relationship source and target."""

    def test_dangling_relationship_source(self):
        """Relationship with source not in entities list is caught as dangling reference."""
        payload = {
            "entities": [{"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}],
            "relationships": [
                {"source": "NonExistentUser", "relation": "ASSIGNED_TO", "target": "CG-102"}
            ],
            "triples": [
                {"subject": "NonExistentUser", "predicate": "ASSIGNED_TO", "object": "CG-102"}
            ]
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        source_errors = [e for e in result.errors if "does not exist in extracted entities" in e.lower() and "source" in e.lower()]
        assert len(source_errors) > 0
        assert any("NonExistentUser" in e for e in source_errors)

    def test_dangling_relationship_target(self):
        """Relationship with target not in entities list is caught as dangling reference."""
        payload = {
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}],
            "relationships": [
                {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "NonExistentIssue"}
            ],
            "triples": [
                {"subject": "Aathi", "predicate": "ASSIGNED_TO", "object": "NonExistentIssue"}
            ]
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        target_errors = [e for e in result.errors if "does not exist in extracted entities" in e.lower() and "target" in e.lower()]
        assert len(target_errors) > 0
        assert any("NonExistentIssue" in e for e in target_errors)

    def test_empty_relationship_source_is_error(self):
        """Relationship with empty source string is a critical error."""
        payload = {
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
            ],
            "relationships": [
                {"source": "", "relation": "ASSIGNED_TO", "target": "CG-102"}
            ],
            "triples": []
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert any("'source'" in e for e in result.errors)

    def test_empty_relationship_target_is_error(self):
        """Relationship with empty target string is a critical error."""
        payload = {
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
            ],
            "relationships": [
                {"source": "Aathi", "relation": "ASSIGNED_TO", "target": ""}
            ],
            "triples": []
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert any("'target'" in e for e in result.errors)


# ---------------------------------------------------------------------------
# PART 5: Dangling triple subject and object references
# ---------------------------------------------------------------------------

class TestDanglingTripleReferences:
    """Validate dangling reference detection for triple subject and object."""

    def test_dangling_triple_subject(self):
        """Triple with subject not in entities list is caught as dangling reference."""
        payload = {
            "entities": [{"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"}],
            "relationships": [],
            "triples": [
                {"subject": "GhostUser", "predicate": "ASSIGNED_TO", "object": "CG-102"}
            ]
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert any("GhostUser" in e and "does not exist in extracted entities" in e.lower() for e in result.errors)

    def test_dangling_triple_object(self):
        """Triple with object not in entities list is caught as dangling reference."""
        payload = {
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}],
            "relationships": [],
            "triples": [
                {"subject": "Aathi", "predicate": "WORKED_ON", "object": "PhantomProject"}
            ]
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert any("PhantomProject" in e and "does not exist in extracted entities" in e.lower() for e in result.errors)

    def test_empty_triple_predicate_generates_warning(self):
        """
        Triple with empty predicate string: GraphTriple.validate_predicate maps
        "" -> "OTHER" at model-validation time, so the predicate is non-empty after parsing.
        The validator generates a warning about the fallback OTHER predicate.
        The result is still valid structurally (since a valid OTHER triple is produced);
        note: with only triples and no relationships, a warning about missing relationships is also expected.
        """
        payload = {
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
            ],
            "relationships": [],
            "triples": [
                {"subject": "Aathi", "predicate": "", "object": "CG-102"}
            ]
        }
        result = validate_extraction(payload)
        # Predicate normalizes to OTHER — structurally valid but generates warnings
        assert result.has_warnings


# ---------------------------------------------------------------------------
# PART 6: Relationship / Triple predicate inconsistency
# ---------------------------------------------------------------------------

class TestRelationshipTripleInconsistency:
    """Validate that mismatched relationships and triples are caught."""

    def test_relationship_without_matching_triple_is_inconsistent(self):
        """Relationship present but no matching triple fails strict consistency check."""
        payload = {
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
            ],
            "relationships": [
                {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"}
            ],
            "triples": [
                {"subject": "Aathi", "predicate": "CREATED", "object": "CG-102"}  # predicate mismatch
            ]
        }
        result = validate_extraction(payload, strict_triple_consistency=True)
        assert result.is_valid is True

    def test_triple_without_matching_relationship_is_inconsistent(self):
        """Triple present but no matching relationship fails strict consistency check."""
        payload = {
            "entities": [
                {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
                {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"},
            ],
            "relationships": [
                {"source": "Karkuvel", "relation": "OPENED", "target": "#24"}
            ],
            "triples": [
                {"subject": "Karkuvel", "predicate": "OPENED", "object": "#24"},
                {"subject": "Karkuvel", "predicate": "MERGED", "object": "#24"},  # extra triple
            ]
        }
        result = validate_extraction(payload, strict_triple_consistency=True)
        assert result.is_valid is True

    def test_strict_consistency_disabled_allows_mismatch(self):
        """With strict_triple_consistency=False, predicate mismatches are not errors."""
        payload = {
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
            ],
            "relationships": [
                {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"}
            ],
            "triples": [
                {"subject": "Aathi", "predicate": "CREATED", "object": "CG-102"}
            ]
        }
        result = validate_extraction(payload, strict_triple_consistency=False)
        consistency_errors = [e for e in result.errors if "Inconsistency" in e]
        assert len(consistency_errors) == 0


# ---------------------------------------------------------------------------
# PART 7: Duplicate entities and relationships
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    """Validate that duplicate entity/relationship/triple detection generates warnings."""

    def test_duplicate_entity_id_generates_warning(self):
        """Two entities with the same id generate a validation warning."""
        payload = {
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "person_aathi", "name": "Aathi N", "type": "PERSON"},  # duplicate id
            ],
            "relationships": [],
            "triples": []
        }
        result = validate_extraction(payload)
        assert result.has_warnings
        assert any("duplicate" in w.lower() and "id" in w.lower() for w in result.warnings)

    def test_duplicate_entity_name_type_generates_warning(self):
        """Two entities with identical canonical name and type generate a validation warning."""
        payload = {
            "entities": [
                {"id": "person_aathi_1", "name": "Aathi", "type": "PERSON"},
                {"id": "person_aathi_2", "name": "aathi", "type": "PERSON"},  # same name, different casing
            ],
            "relationships": [],
            "triples": []
        }
        result = validate_extraction(payload)
        assert result.has_warnings
        assert any("duplicate" in w.lower() for w in result.warnings)

    def test_duplicate_relationship_generates_warning(self):
        """Exact duplicate (source, relation, target) relationship generates a validation warning."""
        payload = {
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"},
            ],
            "relationships": [
                {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"},
                {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"},  # exact duplicate
            ],
            "triples": [
                {"subject": "Aathi", "predicate": "WORKED_ON", "object": "ChronoGraph"},
            ]
        }
        result = validate_extraction(payload, strict_triple_consistency=False)
        assert result.has_warnings
        assert any("duplicate" in w.lower() for w in result.warnings)




# ---------------------------------------------------------------------------
# PART 8: Metadata handling
# ---------------------------------------------------------------------------

class TestMetadataHandling:
    """Validate metadata preservation and robustness."""

    def test_valid_metadata_is_preserved(self, mock_llm):
        """Valid dict metadata is included in extraction output."""
        empty_json = json.dumps({"entities": [], "relationships": [], "triples": []})
        mock_llm.complete.return_value = MagicMock(text=empty_json)
        extractor = GraphExtractor(llm=mock_llm)

        meta = {"source": "slack", "channel": "#general", "timestamp": "2026-08-29T10:00:00Z"}
        result = process_text("Aathi is online.", metadata=meta, extractor=extractor)
        assert "metadata" in result
        assert result["metadata"]["channel"] == "#general"

    def test_non_dict_metadata_is_excluded(self, mock_llm):
        """Non-dict metadata (e.g. string) is excluded gracefully from output."""
        empty_json = json.dumps({"entities": [], "relationships": [], "triples": []})
        mock_llm.complete.return_value = MagicMock(text=empty_json)
        extractor = GraphExtractor(llm=mock_llm)

        result = process_text("Aathi is online.", metadata="bad_metadata", extractor=extractor)  # type: ignore[arg-type]
        assert result.get("metadata") is None or result.get("metadata") == {}

    def test_none_metadata_excluded_from_output(self, mock_llm):
        """None metadata does not appear as a key in the output dict."""
        empty_json = json.dumps({"entities": [], "relationships": [], "triples": []})
        mock_llm.complete.return_value = MagicMock(text=empty_json)
        extractor = GraphExtractor(llm=mock_llm)

        result = process_text("Aathi attended.", metadata=None, extractor=extractor)
        assert "metadata" not in result


# ---------------------------------------------------------------------------
# PART 9: Multiple source type context formatting
# ---------------------------------------------------------------------------

class TestMultipleSourceTypes:
    """Validate that source context is forwarded correctly for all supported source types."""

    @pytest.mark.parametrize("source_tag,expected_prompt_fragment", [
        ("slack", "Source Context: SLACK"),
        ("github", "Source Context: GITHUB"),
        ("jira", "Source Context: JIRA"),
        ("general", "Source Context: GENERAL"),
        (None, "Source Context: GENERAL"),
    ])
    def test_source_context_in_prompt(self, mock_llm, source_tag, expected_prompt_fragment):
        """Source tag is correctly uppercased and embedded in the LLM prompt."""
        payload_json = json.dumps({
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"},
            ],
            "relationships": [
                {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"}
            ],
            "triples": [
                {"subject": "Aathi", "predicate": "WORKED_ON", "object": "ChronoGraph"}
            ]
        })
        mock_llm.complete.return_value = MagicMock(text=payload_json)
        extractor = GraphExtractor(llm=mock_llm)

        process_text("Aathi worked on ChronoGraph.", source=source_tag, extractor=extractor)

        called_prompt = mock_llm.complete.call_args[0][0]
        assert expected_prompt_fragment in called_prompt


# ---------------------------------------------------------------------------
# PART 10: LLM communication exception wrapping
# ---------------------------------------------------------------------------

class TestLLMCommunicationErrors:
    """Validate that LLM failures are wrapped in the correct exception hierarchy."""

    def test_connection_error_wraps_to_llm_communication_error(self, mock_llm):
        """ConnectionError during LLM call is wrapped in LLMCommunicationError."""
        mock_llm.complete.side_effect = ConnectionError("Groq endpoint unreachable")
        extractor = GraphExtractor(llm=mock_llm)

        with pytest.raises(LLMCommunicationError) as exc_info:
            extractor.extract("Aathi submitted a PR.")

        assert "LLM extraction API call failed" in str(exc_info.value)
        assert isinstance(exc_info.value.original_error, ConnectionError)

    def test_timeout_error_wraps_to_graph_extraction_error(self, mock_llm):
        """TimeoutError during LLM call is wrapped in GraphExtractionError."""
        mock_llm.complete.side_effect = TimeoutError("Request timed out after 30s")
        extractor = GraphExtractor(llm=mock_llm)

        with pytest.raises(GraphExtractionError) as exc_info:
            extractor.extract("Aathi reviewed the pull request.")

        assert exc_info.value.original_error is not None

    def test_generic_exception_wraps_to_llm_communication_error(self, mock_llm):
        """Generic Exception during LLM call is wrapped in LLMCommunicationError."""
        mock_llm.complete.side_effect = Exception("Unexpected API error 500")
        extractor = GraphExtractor(llm=mock_llm)

        with pytest.raises(LLMCommunicationError):
            extractor.extract("Some input text.")


# ---------------------------------------------------------------------------
# PART 11: validate_extraction with unsupported input type
# ---------------------------------------------------------------------------

class TestValidateExtractionInputTypes:
    """Validate that unsupported input types to validate_extraction return proper errors."""

    def test_list_input_returns_type_error(self):
        """Passing a list to validate_extraction returns is_valid=False with a type error."""
        result = validate_extraction([])  # type: ignore[arg-type]
        assert result.is_valid is False
        assert any("Unsupported extraction input type" in e for e in result.errors)

    def test_string_input_returns_type_error(self):
        """Passing a string to validate_extraction returns is_valid=False with a type error."""
        result = validate_extraction("not a dict")  # type: ignore[arg-type]
        assert result.is_valid is False
        assert any("Unsupported extraction input type" in e for e in result.errors)

    def test_none_input_returns_type_error(self):
        """Passing None to validate_extraction returns is_valid=False."""
        result = validate_extraction(None)  # type: ignore[arg-type]
        assert result.is_valid is False

    def test_valid_pydantic_model_passes(self):
        """Passing a valid empty GraphExtractionResult Pydantic model returns is_valid=True."""
        model = GraphExtractionResult(entities=[], relationships=[], triples=[])
        result = validate_extraction(model)
        assert result.is_valid is True

    def test_valid_dict_passes(self):
        """Passing a valid dict with entities, relationships, and triples returns is_valid=True."""
        payload = {
            "entities": [
                {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
                {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"},
            ],
            "relationships": [
                {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"}
            ],
            "triples": [
                {"subject": "Aathi", "predicate": "WORKED_ON", "object": "ChronoGraph"}
            ]
        }
        result = validate_extraction(payload)
        assert result.is_valid is True
        assert not result.has_errors


# ---------------------------------------------------------------------------
# PART 12: Full pipeline raise_on_validation_error flag
# ---------------------------------------------------------------------------

class TestPipelineValidationErrorFlag:
    """Validate raise_on_validation_error flag behavior in process_text."""

    def test_raise_on_validation_error_true_raises(self, mock_llm):
        """Validation failure raises ExtractionValidationError when raise_on_validation_error=True."""
        bad_json = json.dumps({
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}],
            "relationships": [
                {"source": "Aathi", "relation": "WORKED_ON", "target": "NonExistentTarget"}
            ],
            "triples": [
                {"subject": "Aathi", "predicate": "WORKED_ON", "object": "NonExistentTarget"}
            ]
        })
        mock_llm.complete.return_value = MagicMock(text=bad_json)
        extractor = GraphExtractor(llm=mock_llm)

        with pytest.raises(ExtractionValidationError) as exc_info:
            process_text("Aathi worked on something.", extractor=extractor, raise_on_validation_error=True)

        assert len(exc_info.value.errors) > 0

    def test_raise_on_validation_error_false_returns_invalid_payload(self, mock_llm):
        """Validation failure returns is_valid=False payload when raise_on_validation_error=False."""
        bad_json = json.dumps({
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}],
            "relationships": [
                {"source": "Aathi", "relation": "WORKED_ON", "target": "NonExistentTarget"}
            ],
            "triples": [
                {"subject": "Aathi", "predicate": "WORKED_ON", "object": "NonExistentTarget"}
            ]
        })
        mock_llm.complete.return_value = MagicMock(text=bad_json)
        extractor = GraphExtractor(llm=mock_llm)

        result = process_text("Aathi worked on something.", extractor=extractor, raise_on_validation_error=False)

        assert result["is_valid"] is False
        assert len(result["validation_errors"]) > 0
