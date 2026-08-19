from typing import Union, Dict, Any, List
from pydantic import BaseModel, Field
from src.models import GraphExtractionResult, Entity, Relationship, GraphTriple


class ExtractionValidationError(Exception):
    """Exception raised when graph extraction validation fails."""
    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors


class ValidationResult(BaseModel):
    """Result container for extraction validation."""
    is_valid: bool = Field(..., description="True if extraction passed all validation checks")
    errors: List[str] = Field(default_factory=list, description="Critical validation errors")
    warnings: List[str] = Field(default_factory=list, description="Non-critical warnings")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings
        }


def validate_extraction(extraction: Union[Dict[str, Any], GraphExtractionResult]) -> ValidationResult:
    """
    Validate a graph extraction result.

    Verifies:
    - Proper schema structure & valid JSON/Pydantic model
    - Required fields on entities, relationships, and triples
    - Strict Cross-References: relationship source/target MUST exist as entities (errors if dangling)
    - Strict Cross-References: triple subject/object MUST exist as entities (errors if dangling)
    - Absence of malformed records
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Parse dictionary if passed
    result: GraphExtractionResult
    if isinstance(extraction, dict):
        try:
            result = GraphExtractionResult.model_validate(extraction)
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Invalid JSON/dictionary structure matching GraphExtractionResult schema: {e}"],
                warnings=[]
            )
    elif isinstance(extraction, GraphExtractionResult):
        result = extraction
    else:
        return ValidationResult(
            is_valid=False,
            errors=[f"Unsupported extraction input type: {type(extraction)}"],
            warnings=[]
        )

    # 1. Validate Entities & collect valid identifiers
    entity_names = set()
    entity_ids = set()

    for idx, entity in enumerate(result.entities):
        if not entity.id or not str(entity.id).strip():
            errors.append(f"Entity at index {idx} has empty or missing 'id'.")
        else:
            entity_ids.add(str(entity.id).strip().lower())

        if not entity.name or not str(entity.name).strip():
            errors.append(f"Entity at index {idx} has empty or missing 'name'.")
        else:
            entity_names.add(str(entity.name).strip().lower())

        if not entity.type:
            errors.append(f"Entity at index {idx} ('{entity.name}') has empty or missing 'type'.")

    # Known entity identifiers for cross-reference checks
    known_references = entity_names.union(entity_ids)

    # 2. Validate Relationships (Dangling references are now STRICT ERRORS for Neo4j readiness)
    for idx, rel in enumerate(result.relationships):
        if not rel.source or not str(rel.source).strip():
            errors.append(f"Relationship at index {idx} has empty or missing 'source'.")
        if not rel.relation:
            errors.append(f"Relationship at index {idx} has empty or missing 'relation'.")
        if not rel.target or not str(rel.target).strip():
            errors.append(f"Relationship at index {idx} has empty or missing 'target'.")

        # Cross-reference verification: Source must exist in entities
        if rel.source:
            src_key = str(rel.source).strip().lower()
            if src_key not in known_references:
                errors.append(
                    f"Relationship source '{rel.source}' at index {idx} is a dangling reference not found in extracted entities."
                )

        # Cross-reference verification: Target must exist in entities
        if rel.target:
            tgt_key = str(rel.target).strip().lower()
            if tgt_key not in known_references:
                errors.append(
                    f"Relationship target '{rel.target}' at index {idx} is a dangling reference not found in extracted entities."
                )

    # 3. Validate Triples (Dangling references are STRICT ERRORS)
    for idx, triple in enumerate(result.triples):
        if not triple.subject or not str(triple.subject).strip():
            errors.append(f"Triple at index {idx} has empty or missing 'subject'.")
        if not triple.predicate or not str(triple.predicate).strip():
            errors.append(f"Triple at index {idx} has empty or missing 'predicate'.")
        if not triple.object or not str(triple.object).strip():
            errors.append(f"Triple at index {idx} has empty or missing 'object'.")

        # Cross-reference verification: Subject must exist in entities
        if triple.subject:
            subj_key = str(triple.subject).strip().lower()
            if subj_key not in known_references:
                errors.append(
                    f"Triple subject '{triple.subject}' at index {idx} is a dangling reference not found in extracted entities."
                )

        # Cross-reference verification: Object must exist in entities
        if triple.object:
            obj_key = str(triple.object).strip().lower()
            if obj_key not in known_references:
                errors.append(
                    f"Triple object '{triple.object}' at index {idx} is a dangling reference not found in extracted entities."
                )

    is_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings
    )
