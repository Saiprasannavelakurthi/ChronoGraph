import logging
from typing import Dict, Any, Optional, List
from src.extractor import GraphExtractor
from src.models import GraphExtractionResult
from src.validator import validate_extraction, ExtractionValidationError
from src.utils.text_utils import clean_text

logger = logging.getLogger(__name__)


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
        metadata (dict, optional): Optional context metadata (e.g., source, timestamp).
        extractor (GraphExtractor, optional): Pre-instantiated GraphExtractor instance.
        raise_on_validation_error (bool): If True, raises ExtractionValidationError when validation fails. Default True.
        source (str, optional): Data source identifier (e.g. 'slack', 'github', 'jira').

    Returns:
        Dict[str, Any]: Validated structured graph extraction payload.
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

    source_val = source or (metadata.get("source") if isinstance(metadata, dict) else None)
    result_model = extractor.extract(cleaned_input, source=source_val)

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

    # Preserve optional metadata
    if metadata is not None:
        output_dict["metadata"] = metadata

    # Include validation status metadata if not raising exception
    if not validation.is_valid:
        output_dict["is_valid"] = False
        output_dict["validation_errors"] = validation.errors
    else:
        output_dict["is_valid"] = True

    return output_dict


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

    for record in records:
        text = record.get("text", "")
        source = record.get("source") or (record.get("metadata", {}).get("source") if isinstance(record.get("metadata"), dict) else None)
        
        rec_metadata = dict(record.get("metadata") or {})
        if source and "source" not in rec_metadata:
            rec_metadata["source"] = source

        records_metadata.append(rec_metadata)

        cleaned_input = clean_text(text)
        if not cleaned_input:
            continue

        result_model = extractor.extract(cleaned_input, source=source)
        raw_entities.extend(result_model.entities)
        raw_relationships.extend(result_model.relationships)
        raw_triples.extend(result_model.triples)

    # Consolidated post-processing & cross-record deduplication
    consolidated_model = GraphExtractionResult(
        entities=raw_entities,
        relationships=raw_relationships,
        triples=raw_triples
    )

    processed_model = extractor.post_process(consolidated_model)

    # Validate the consolidated extraction result
    validation = validate_extraction(processed_model)
    if not validation.is_valid:
        logger.error(f"Batch extraction validation failed: {validation.errors}")
        if raise_on_validation_error:
            raise ExtractionValidationError(
                f"Batch graph extraction validation failed with {len(validation.errors)} error(s).",
                errors=validation.errors
            )

    output_dict = processed_model.model_dump()

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

    # Preserve all record metadata under metadata.records
    output_dict["metadata"] = {
        "records": records_metadata
    }

    if not validation.is_valid:
        output_dict["is_valid"] = False
        output_dict["validation_errors"] = validation.errors
    else:
        output_dict["is_valid"] = True

    return output_dict


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
