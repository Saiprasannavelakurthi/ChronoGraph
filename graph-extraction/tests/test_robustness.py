"""
Robustness and testability improvement tests -- ChronoGraph Graph Extraction Module.

Covers targeted gaps not duplicated in existing test suites:
  - normalize_entity_name: internal whitespace collapsing
  - normalize_entity_name: does not incorrectly merge distinct identifiers
  - validator: GraphExtractionResult with OTHER type -> warning, not error
  - validator: dangling relationship source error message content
  - validator: dangling triple object error message content
  - extractor: None LLM response -> empty result (not raise)
  - extractor: markdown JSON fence parsing (triple-backtick with language tag)
  - extractor: malformed JSON raises MalformedLLMResponseError with meaningful message
  - extractor: missing required fields in JSON raises MalformedLLMResponseError
"""

import json
import pytest
from unittest.mock import MagicMock

from src.extractor import GraphExtractor
from src.errors import MalformedLLMResponseError
from src.models import (
    GraphExtractionResult,
    Entity,
    Relationship,
    GraphTriple,
    EntityType,
    RelationshipType,
)
from src.utils.text_utils import normalize_entity_name
from src.validator import validate_extraction


# ---------------------------------------------------------------------------
# 1. Entity normalization -- internal whitespace collapsing
# ---------------------------------------------------------------------------


class TestNormalizeEntityNameWhitespace:
    """Verify that normalize_entity_name collapses internal whitespace."""

    def test_leading_trailing_spaces_are_stripped(self):
        """Leading and trailing spaces are removed."""
        assert normalize_entity_name("  Alice  ") == "Alice"

    def test_internal_double_space_is_collapsed(self):
        """Internal double spaces are collapsed to a single space."""
        result = normalize_entity_name("Alice  Smith")
        assert "  " not in result, f"Expected no double spaces, got {result!r}"
        assert result == "Alice Smith"

    def test_internal_tab_is_collapsed(self):
        """Internal tabs are collapsed to a single space."""
        result = normalize_entity_name("Alice\tSmith")
        assert "\t" not in result
        assert result == "Alice Smith"

    def test_all_lowercase_multiword_with_extra_spaces(self):
        """All-lowercase multi-word names with extra spaces normalize to Title Case."""
        result = normalize_entity_name("alice   smith")
        assert result == "Alice Smith"


class TestNormalizeEntityNameDoesNotMergeDistinctEntities:
    """Verify that normalization preserves meaningful differences between entity names."""

    def test_different_jira_keys_are_preserved(self):
        """Two different Jira issue keys remain distinct after normalization."""
        assert normalize_entity_name("CG-101") != normalize_entity_name("CG-102")

    def test_different_commit_hashes_are_preserved(self):
        """Two different commit hashes remain distinct after normalization."""
        assert normalize_entity_name("abc1234") != normalize_entity_name("def5678")

    def test_different_pr_numbers_are_preserved(self):
        """Two different PR numbers remain distinct after normalization."""
        assert normalize_entity_name("#24") != normalize_entity_name("#25")

    def test_camelcase_name_preserved(self):
        """CamelCase / PascalCase identifiers are returned unchanged."""
        assert normalize_entity_name("ChronoGraph") == "ChronoGraph"
        assert normalize_entity_name("FastAPI") == "FastAPI"


# ---------------------------------------------------------------------------
# 2. Validator -- GraphExtractionResult with OTHER type
# ---------------------------------------------------------------------------


class TestValidatorOtherTypeOnModelInput:
    """
    Verify that validate_extraction does not produce a false-positive error
    when called with a GraphExtractionResult model (not a dict) that contains
    an entity with EntityType.OTHER.
    """

    def test_model_with_explicit_other_type_is_warning_not_error(self):
        """Entity with type=OTHER on a model input produces a warning, not an error."""
        model = GraphExtractionResult(
            entities=[Entity(id="widget_foo", name="FooWidget", type=EntityType.OTHER)],
            relationships=[],
            triples=[],
        )
        result = validate_extraction(model)
        assert result.is_valid is True, (
            f"Expected is_valid=True; errors={result.errors}"
        )
        assert any("OTHER" in w for w in result.warnings), (
            "Expected a warning about fallback type OTHER"
        )

    def test_model_with_unrecognised_type_coerced_to_other_is_warning_not_error(self):
        """Entity constructed with an unrecognised type string (coerced to OTHER) is a warning."""
        # Entity(type='WIDGET') -> EntityType.OTHER via _missing_
        model = GraphExtractionResult(
            entities=[Entity(id="widget_bar", name="BarWidget", type="WIDGET")],
            relationships=[],
            triples=[],
        )
        assert model.entities[0].type == EntityType.OTHER
        result = validate_extraction(model)
        assert result.is_valid is True, (
            f"Expected is_valid=True; errors={result.errors}"
        )

    def test_dict_with_empty_type_is_error(self):
        """Dict input with explicitly empty type string remains an error (regression guard)."""
        payload = {
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": ""}],
            "relationships": [],
            "triples": [],
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        assert any("'type'" in e for e in result.errors)

    def test_dict_with_unrecognised_type_is_warning_not_error(self):
        """Dict input with an unrecognised (but non-empty) type string is a warning."""
        payload = {
            "entities": [{"id": "widget_foo", "name": "FooWidget", "type": "WIDGET"}],
            "relationships": [],
            "triples": [],
        }
        result = validate_extraction(payload)
        assert result.is_valid is True
        assert any("OTHER" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 3. Validator -- dangling reference error message content
# ---------------------------------------------------------------------------


class TestValidatorDanglingErrorMessages:
    """Verify that dangling-reference errors contain meaningful context."""

    def test_dangling_relationship_source_error_names_the_entity(self):
        """Error for a dangling relationship source identifies the missing entity name."""
        payload = {
            "entities": [{"id": "project_cg", "name": "ChronoGraph", "type": "PROJECT"}],
            "relationships": [
                {"source": "GhostDev", "relation": "WORKED_ON", "target": "ChronoGraph"}
            ],
            "triples": [
                {"subject": "GhostDev", "predicate": "WORKED_ON", "object": "ChronoGraph"}
            ],
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        source_errors = [e for e in result.errors if "source" in e and "GhostDev" in e]
        assert len(source_errors) > 0, (
            f"Expected source error mentioning GhostDev; got {result.errors}"
        )
        assert "does not exist in extracted entities" in source_errors[0]

    def test_dangling_triple_object_error_names_the_entity(self):
        """Error for a dangling triple object identifies the missing entity name."""
        payload = {
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}],
            "relationships": [],
            "triples": [
                {"subject": "Aathi", "predicate": "WORKED_ON", "object": "PhantomProject"}
            ],
        }
        result = validate_extraction(payload)
        assert result.is_valid is False
        object_errors = [e for e in result.errors if "object" in e and "PhantomProject" in e]
        assert len(object_errors) > 0, (
            f"Expected object error mentioning PhantomProject; got {result.errors}"
        )
        assert "does not exist in extracted entities" in object_errors[0]


# ---------------------------------------------------------------------------
# 4. Extractor -- LLM response handling
# ---------------------------------------------------------------------------


class TestExtractorLLMResponseHandling:
    """Verify _parse_llm_response handles edge-case LLM outputs correctly."""

    def test_none_llm_response_returns_empty_result(self):
        """When the LLM response text is None, return an empty result (do not raise)."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(text=None)
        extractor = GraphExtractor(llm=mock_llm)

        result = extractor.extract("Some input text")

        assert isinstance(result, GraphExtractionResult)
        assert result.entities == []
        assert result.relationships == []
        assert result.triples == []

    def test_markdown_fence_with_language_tag_is_parsed(self):
        """JSON wrapped in ```json ... ``` (with language tag) is correctly extracted."""
        payload = json.dumps({
            "entities": [{"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"}],
            "relationships": [],
            "triples": [],
        })
        llm_text = f"```json\n{payload}\n```"

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(text=llm_text)
        extractor = GraphExtractor(llm=mock_llm)

        result = extractor.extract("Karkuvel worked on something")

        assert len(result.entities) == 1
        assert result.entities[0].name == "Karkuvel"

    def test_markdown_fence_without_language_tag_is_parsed(self):
        """JSON wrapped in plain ``` ... ``` (no language tag) is correctly extracted."""
        payload = json.dumps({
            "entities": [{"id": "person_aathi", "name": "Aathi", "type": "PERSON"}],
            "relationships": [],
            "triples": [],
        })
        llm_text = f"```\n{payload}\n```"

        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(text=llm_text)
        extractor = GraphExtractor(llm=mock_llm)

        result = extractor.extract("Aathi worked on something")

        assert len(result.entities) == 1
        assert result.entities[0].name == "Aathi"

    def test_malformed_json_raises_with_meaningful_message(self):
        """Malformed JSON raises MalformedLLMResponseError with a descriptive message."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            text='{"entities": [BROKEN JSON HERE'
        )
        extractor = GraphExtractor(llm=mock_llm)

        with pytest.raises(MalformedLLMResponseError) as exc_info:
            extractor.extract("Some text")

        error_msg = str(exc_info.value)
        assert any(
            fragment in error_msg
            for fragment in ("JSONDecodeError", "parse", "malformed", "JSON")
        ), f"Expected descriptive error, got: {error_msg!r}"

    def test_missing_required_entity_fields_raises_with_meaningful_message(self):
        """JSON with entities missing required fields raises MalformedLLMResponseError."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            text=json.dumps({
                "entities": [{"id": "person_aathi"}],  # missing name and type
                "relationships": [],
                "triples": [],
            })
        )
        extractor = GraphExtractor(llm=mock_llm)

        with pytest.raises(MalformedLLMResponseError) as exc_info:
            extractor.extract("Some text")

        error_msg = str(exc_info.value)
        assert "validation" in error_msg.lower(), (
            f"Expected validation-related error, got: {error_msg!r}"
        )

    def test_empty_llm_response_raises_malformed_error(self):
        """Empty (whitespace-only) LLM response raises MalformedLLMResponseError."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(text="   ")
        extractor = GraphExtractor(llm=mock_llm)

        with pytest.raises(MalformedLLMResponseError, match="empty response"):
            extractor.extract("Some input text")
