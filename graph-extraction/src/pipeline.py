import logging
from typing import Dict, Any, Optional, List
from src.extractor import GraphExtractor
from src.models import GraphExtractionResult
from src.validator import validate_extraction, ExtractionValidationError
from src.utils.text_utils import clean_text

logger = logging.getLogger(__name__)


def _serialize_extraction_output(
    result_model: GraphExtractionResult,
    validation: Any,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Helper function to serialize GraphExtractionResult Pydantic model to the standard
    dictionary output with stringified enum representations and validation metadata.
    """
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

    # Preserve optional metadata
    if metadata is not None:
        output_dict["metadata"] = metadata

    # Include validation status metadata
    if not validation.is_valid:
        output_dict["is_valid"] = False
        output_dict["validation_errors"] = validation.errors
    else:
        output_dict["is_valid"] = True

    return output_dict


def process_text(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    extractor: Optional[GraphExtractor] = None,
    raise_on_validation_error: bool = True,
    source: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main pipeline entry point for single enterprise text graph extraction.
    Backward compatible with Week 1 implementation while supporting optional source context.

    Args:
        text (str): Raw input enterprise text (Slack, GitHub, Jira, etc.).
            Non-string values are coerced to string before cleaning.
        metadata (dict, optional): Optional context metadata (e.g., source, timestamp).
            Non-dict values are ignored and excluded from output.
        extractor (GraphExtractor, optional): Pre-instantiated GraphExtractor instance.
        raise_on_validation_error (bool): If True, raises ExtractionValidationError when validation fails. Default True.
        source (str, optional): Data source identifier (e.g. 'slack', 'github', 'jira').

    Returns:
        Dict[str, Any]: Validated structured graph extraction payload.
    """
    # Coerce non-string text inputs to string
    if text is None:
        text = ""
    elif not isinstance(text, str):
        logger.warning(
            f"process_text received non-string input of type '{type(text).__name__}'. "
            "Coercing to string."
        )
        text = str(text)

    # Normalize metadata to dict or None
    if metadata is not None and not isinstance(metadata, dict):
        logger.warning(
            f"process_text received non-dict metadata of type '{type(metadata).__name__}'. "
            "Metadata will be excluded from output."
        )
        metadata = None

    cleaned_input = clean_text(text)

    # Base empty response structure
    if not cleaned_input:
        logger.info("Provided input text is empty or whitespace-only.")
        res = {
            "entities": [],
            "relationships": [],
            "triples": [],
            "is_valid": True
        }
        if metadata is not None:
            res["metadata"] = metadata
        return res

    # Instantiate extractor if not provided
    if extractor is None:
        extractor = GraphExtractor()

    source_val = source or (metadata.get("source") if isinstance(metadata, dict) else None)
    
    from src.errors import GraphExtractionError
    
    try:
        result_model = extractor.extract(cleaned_input, source=source_val)
        pruned = list(getattr(extractor, "_last_pruned", []))
        validation = validate_extraction(result_model)
        
        all_errors = list(validation.errors) + [
            f"Validation error: {p}" for p in pruned
        ]
        combined_is_valid = validation.is_valid and not pruned
        combined_warnings = validation.warnings
    except GraphExtractionError as e:
        logger.error(f"Extraction failed: {e}")
        all_errors = [f"Extraction failed: {str(e)}"]
        if hasattr(e, "errors") and getattr(e, "errors"):
            all_errors.extend(getattr(e, "errors"))
        
        if raise_on_validation_error:
            raise ExtractionValidationError(
                f"Graph extraction failed with error: {e}",
                errors=all_errors,
                original_error=e
            )
        
        result_model = GraphExtractionResult(entities=[], relationships=[], triples=[])
        combined_is_valid = False
        combined_warnings = []

    from src.validator import ValidationResult
    combined_validation = ValidationResult(
        is_valid=combined_is_valid,
        errors=all_errors,
        warnings=combined_warnings
    )

    if not combined_is_valid and not all_errors:
        # Fallback if no errors populated
        all_errors = ["Unknown validation failure."]
        
    if not combined_is_valid and result_model.entities:
        logger.error(
            f"Extraction validation failed with {len(all_errors)} error(s): {all_errors}"
        )
        if raise_on_validation_error:
            raise ExtractionValidationError(
                f"Graph extraction validation failed with {len(all_errors)} error(s).",
                errors=all_errors
            )

    return _serialize_extraction_output(result_model, combined_validation, metadata=metadata)


def process_records(
    records: List[Dict[str, Any]],
    extractor: Optional[GraphExtractor] = None,
    raise_on_validation_error: bool = True
) -> Dict[str, Any]:
    """
    Process multiple enterprise data records (Slack, GitHub, Jira) into a unified,
    cross-record deduplicated, normalized, and validated Neo4j-ready graph representation.

    Args:
        records (List[Dict[str, Any]]): List of record dictionaries containing 'text', 'source', 'metadata'.
        extractor (GraphExtractor, optional): Pre-instantiated GraphExtractor instance.
        raise_on_validation_error (bool): If True, raises ExtractionValidationError when validation fails. Default True.

    Returns:
        Dict[str, Any]: Consolidated Neo4j-ready graph dictionary containing:
            {
                "entities": [...],
                "relationships": [...],
                "triples": [...],
                "metadata": {
                    "records": [...]
                },
                "is_valid": True
            }
    """
    if not records:
        return {
            "entities": [],
            "relationships": [],
            "triples": [],
            "metadata": {"records": []},
            "is_valid": True
        }

    if extractor is None:
        extractor = GraphExtractor()

    raw_entities = []
    raw_relationships = []
    raw_triples = []
    records_metadata = []

    for idx, record in enumerate(records):
        if isinstance(record, str):
            record_dict = {"text": record}
        elif isinstance(record, dict):
            record_dict = record
        else:
            logger.warning(
                f"Skipping record at index {idx}: expected dictionary or string, got {type(record).__name__}."
            )
            continue

        text = record_dict.get("text", "")
        source = record_dict.get("source") or (
            record_dict.get("metadata", {}).get("source")
            if isinstance(record_dict.get("metadata"), dict)
            else None
        )
        
        raw_meta = record_dict.get("metadata")
        rec_metadata = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        if source and "source" not in rec_metadata:
            rec_metadata["source"] = source

        records_metadata.append(rec_metadata)

        cleaned_input = clean_text(text)
        if not cleaned_input:
            continue

        try:
            result_model = extractor.extract(cleaned_input, source=source)
            raw_entities.extend(result_model.entities)
            raw_relationships.extend(result_model.relationships)
            raw_triples.extend(result_model.triples)
        except Exception as e:
            logger.error(f"Error extracting record at index {idx}: {e}")
            if raise_on_validation_error:
                raise

    # Consolidated post-processing & cross-record deduplication
    consolidated_model = GraphExtractionResult(
        entities=raw_entities,
        relationships=raw_relationships,
        triples=raw_triples
    )

    processed_model = extractor.post_process(consolidated_model)

    # Collect any dangling-edge pruning info recorded during the last post_process call.
    pruned_batch = list(getattr(extractor, "_last_pruned", []))

    # Validate the consolidated extraction result
    validation = validate_extraction(processed_model)
    all_errors = list(validation.errors) + [
        f"Validation error: {p}" for p in pruned_batch
    ]
    combined_is_valid = validation.is_valid and not pruned_batch

    from src.validator import ValidationResult
    combined_validation = ValidationResult(
        is_valid=combined_is_valid,
        errors=all_errors,
        warnings=validation.warnings
    )

    if not combined_is_valid:
        logger.error(f"Batch extraction validation failed: {all_errors}")
        if raise_on_validation_error:
            raise ExtractionValidationError(
                f"Batch graph extraction validation failed with {len(all_errors)} error(s).",
                errors=all_errors
            )

    return _serialize_extraction_output(
        processed_model,
        combined_validation,
        metadata={"records": records_metadata}
    )


if __name__ == "__main__":
    import json
    sample_records = [
        {
            "source": "slack",
            "text": "Aathi discussed ChronoGraph issue with Karkuvel.",
            "metadata": {"channel": "#dev-chat", "timestamp": "2026-08-10T10:00:00Z"}
        },
        {
            "source": "github",
            "text": "Karkuvel committed abc1234 to ChronoGraph repository.",
            "metadata": {"repository": "ChronoGraph", "timestamp": "2026-08-10T11:00:00Z"}
        },
        {
            "source": "jira",
            "text": "Aathi was assigned CG-102 task.",
            "metadata": {"project": "CG", "timestamp": "2026-08-10T12:00:00Z"}
        }
    ]
    
    print("Processing Sample Multi-Source Records:")
    try:
        result = process_records(sample_records, raise_on_validation_error=False)
        print("\n--- BATCH EXTRACTION RESULT ---")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\nExecution note: {e}")
