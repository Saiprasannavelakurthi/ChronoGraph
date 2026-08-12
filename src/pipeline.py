import logging
from typing import Dict, Any, Optional
from src.extractor import GraphExtractor
from src.validator import validate_extraction, ExtractionValidationError
from src.utils.text_utils import clean_text

logger = logging.getLogger(__name__)


def process_text(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    extractor: Optional[GraphExtractor] = None,
    raise_on_validation_error: bool = True
) -> Dict[str, Any]:
    """
    Main pipeline entry point for enterprise text graph extraction.

    Args:
        text (str): Raw input enterprise text (Slack, GitHub, Jira, etc.).
        metadata (dict, optional): Optional context metadata (e.g., source, timestamp). Preserved for Week 2 Neo4j/Temporal integration.
        extractor (GraphExtractor, optional): Pre-instantiated GraphExtractor instance (useful for testing/mocking).
        raise_on_validation_error (bool): If True, raises ExtractionValidationError when validation fails. Default True.

    Returns:
        Dict[str, Any]: Validated structured graph extraction payload containing:
            {
                "entities": [...],
                "relationships": [...],
                "triples": [...],
                "metadata": {...}  # Included if metadata parameter was provided
            }

    Raises:
        ExtractionValidationError: If validation fails and raise_on_validation_error is True.
    """
    cleaned_input = clean_text(text)
    
    # Base empty response structure
    if not cleaned_input:
        logger.info("Provided input text is empty.")
        res = {
            "entities": [],
            "relationships": [],
            "triples": []
        }
        if metadata is not None:
            res["metadata"] = metadata
        return res

    # Instantiate extractor if not provided
    if extractor is None:
        extractor = GraphExtractor()

    result_model = extractor.extract(cleaned_input)

    # Validate extraction result
    validation = validate_extraction(result_model)
    if not validation.is_valid:
        logger.error(f"Extraction validation failed with errors: {validation.errors}")
        if raise_on_validation_error:
            raise ExtractionValidationError(
                f"Graph extraction validation failed with {len(validation.errors)} error(s).",
                errors=validation.errors
            )

    # Convert Pydantic model to dictionary
    output_dict = result_model.model_dump()

    # Convert Enum objects to string representation
    for entity in output_dict.get("entities", []):
        if hasattr(entity.get("type"), "value"):
            entity["type"] = entity["type"].value
        else:
            entity["type"] = str(entity.get("type"))

    for rel in output_dict.get("relationships", []):
        if hasattr(rel.get("relation"), "value"):
            rel["relation"] = rel["relation"].value
        else:
            rel["relation"] = str(rel.get("relation"))

    # Preserve optional metadata for Week 2
    if metadata is not None:
        output_dict["metadata"] = metadata

    # Include validation status metadata if not raising exception
    if not validation.is_valid:
        output_dict["is_valid"] = False
        output_dict["validation_errors"] = validation.errors
    else:
        output_dict["is_valid"] = True

    return output_dict


if __name__ == "__main__":
    import json
    sample_text = (
        "Karkuvel committed code to the ChronoGraph repository. "
        "Aathi reviewed the pull request created by Karkuvel."
    )
    sample_meta = {"source": "github", "timestamp": "2026-08-10T14:00:00Z"}
    
    print("Processing Sample Enterprise Text with Metadata:")
    print(f"Text: {sample_text}")
    print(f"Metadata: {sample_meta}")
    
    # For local demo run when LLM API key is not configured, catch and log if LLM key is needed
    try:
        result = process_text(sample_text, metadata=sample_meta, raise_on_validation_error=False)
        print("\n--- EXTRACTION RESULT ---")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\nExecution note: {e}")
