from typing import Union, Dict, Any, List, Set, Tuple
from pydantic import BaseModel, Field
from src.models import GraphExtractionResult, Entity, Relationship, GraphTriple, EntityType, RelationshipType
from src.errors import ExtractionValidationError
from src.utils.text_utils import normalize_entity_name, generate_entity_id


class ValidationResult(BaseModel):
    """Result container for extraction validation."""
    is_valid: bool = Field(..., description="True if extraction passed all validation checks")
    errors: List[str] = Field(default_factory=list, description="Critical validation errors")
    warnings: List[str] = Field(default_factory=list, description="Non-critical warnings")

    @property
    def has_errors(self) -> bool:
        """Convenience property indicating whether any critical validation errors were found."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Convenience property indicating whether non-critical validation warnings were found."""
        return len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings
        }


def validate_extraction(
    extraction: Union[Dict[str, Any], GraphExtractionResult],
    strict_triple_consistency: bool = True
) -> ValidationResult:
    """
    Validate a graph extraction result against strict Neo4j-readiness constraints.

    Validation Hierarchy:
    1. Schema & Structure: Valid JSON/Pydantic model conforming to GraphExtractionResult.
    2. Entity Integrity: Non-empty 'id', 'name', and 'type' for every entity.
    3. Duplicate Entity Detection: Warn on duplicate entity IDs or canonical name+type keys.
    4. Relationship Source & Target Integrity:
       - 'source', 'relation', and 'target' are non-empty.
       - Source entity exists in the extracted entities set (no dangling source).
       - Target entity exists in the extracted entities set (no dangling target).
    5. Duplicate Relationship Detection: Warn on exact duplicate (source, relation, target) tuples.
    6. Graph Triple Subject & Object Integrity:
       - 'subject', 'predicate', and 'object' are non-empty.
       - Subject entity exists in the extracted entities set (no dangling subject).
       - Object entity exists in the extracted entities set (no dangling object).
    7. Duplicate Triple Detection: Warn on exact duplicate (subject, predicate, object) tuples.
    8. Consistency: Relationships and Triples are consistent in structure and identifiers.
       When either array is non-empty but the other is empty, the missing side is flagged.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Parse and validate structure
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
            errors=[f"Unsupported extraction input type: {type(extraction).__name__}"],
            warnings=[]
        )

    # 2. Entity Integrity & Identifier Indexing
    known_references: Set[str] = set()
    seen_entity_ids: Dict[str, int] = {}          # entity_id -> first seen index
    seen_entity_name_types: Dict[str, int] = {}   # "TYPE:normalized_name" -> first seen index

    for idx, entity in enumerate(result.entities):
        # --- id field ---
        entity_id_raw = str(entity.id).strip() if entity.id else ""
        if not entity_id_raw:
            errors.append(f"Entity at index {idx} has empty or missing 'id'.")
        else:
            known_references.add(entity_id_raw.lower())
            # Duplicate ID detection
            if entity_id_raw.lower() in seen_entity_ids:
                warnings.append(
                    f"Entity at index {idx} has duplicate 'id' '{entity_id_raw}' "
                    f"(first seen at index {seen_entity_ids[entity_id_raw.lower()]})."
                )
            else:
                seen_entity_ids[entity_id_raw.lower()] = idx

        # --- name field ---
        entity_name_raw = str(entity.name).strip() if entity.name else ""
        if not entity_name_raw:
            errors.append(f"Entity at index {idx} has empty or missing 'name'.")
        else:
            known_references.add(entity_name_raw.lower())
            known_references.add(normalize_entity_name(entity_name_raw).strip().lower())

        # --- type field ---
        if not entity.type:
            errors.append(f"Entity at index {idx} ('{entity.name}') has empty or missing 'type'.")
        else:
            type_val = entity.type.value if hasattr(entity.type, "value") else str(entity.type)
            # Also detect when type resolved to OTHER due to an empty or unrecognised raw value
            raw_type = ""
            if isinstance(extraction, dict):
                raw_type_candidate = extraction.get("entities", [])
                if isinstance(raw_type_candidate, list) and idx < len(raw_type_candidate):
                    raw_type = str(raw_type_candidate[idx].get("type", "")).strip()
            if type_val == "OTHER" and (not raw_type or raw_type.upper() not in {
                "PERSON", "USER", "TEAM", "ORGANIZATION", "PROJECT", "REPOSITORY",
                "ISSUE", "TASK", "COMMIT", "PULL_REQUEST", "CHANNEL", "MESSAGE",
                "DOCUMENT", "SYSTEM", "SERVICE", "OTHER"
            }):
                if not raw_type:
                    errors.append(f"Entity at index {idx} ('{entity.name}') has empty or missing 'type'.")
                else:
                    warnings.append(f"Entity '{entity.name}' at index {idx} uses fallback type 'OTHER'.")
            elif type_val == "OTHER":
                warnings.append(f"Entity '{entity.name}' at index {idx} uses fallback type 'OTHER'.")
            if entity_name_raw:
                known_references.add(generate_entity_id(entity_name_raw, type_val).lower())

            # Duplicate entity (name + type) detection
            if entity_name_raw:
                norm_name_key = normalize_entity_name(entity_name_raw).strip().lower()
                name_type_key = f"{type_val.upper()}:{norm_name_key}"
                if name_type_key in seen_entity_name_types:
                    warnings.append(
                        f"Entity at index {idx} ('{entity_name_raw}', type '{type_val}') appears to be a "
                        f"duplicate of entity at index {seen_entity_name_types[name_type_key]}."
                    )
                else:
                    seen_entity_name_types[name_type_key] = idx

    # 3. Relationship Validation & Dangling Reference Check
    rel_tuples: Set[Tuple[str, str, str]] = set()
    seen_rel_tuples: Dict[Tuple[str, str, str], int] = {}

    for idx, rel in enumerate(result.relationships):
        src_raw = str(rel.source).strip() if rel.source else ""
        tgt_raw = str(rel.target).strip() if rel.target else ""

        if not src_raw:
            errors.append(f"Relationship at index {idx} has empty or missing 'source'.")
        if not rel.relation:
            errors.append(f"Relationship at index {idx} has empty or missing 'relation'.")
        if not tgt_raw:
            errors.append(f"Relationship at index {idx} has empty or missing 'target'.")

        # Source cross-reference check
        if src_raw:
            src_key = src_raw.lower()
            if src_key not in known_references:
                errors.append(
                    f"Relationship source '{rel.source}' does not exist in extracted entities."
                )

        # Target cross-reference check
        if tgt_raw:
            tgt_key = tgt_raw.lower()
            if tgt_key not in known_references:
                errors.append(
                    f"Relationship target '{rel.target}' does not exist in extracted entities."
                )

        if src_raw and rel.relation and tgt_raw:
            r_str = rel.relation.value if hasattr(rel.relation, "value") else str(rel.relation)
            if r_str == "OTHER":
                warnings.append(
                    f"Relationship ({rel.source} -> {rel.relation} -> {rel.target}) at index {idx} uses fallback relation 'OTHER'."
                )
            norm_tuple = (
                src_raw.lower(),
                r_str.strip().upper().replace(" ", "_"),
                tgt_raw.lower()
            )
            # Duplicate relationship detection
            if norm_tuple in seen_rel_tuples:
                warnings.append(
                    f"Relationship at index {idx} ({rel.source} -> {r_str} -> {rel.target}) is a "
                    f"duplicate of relationship at index {seen_rel_tuples[norm_tuple]}."
                )
            else:
                seen_rel_tuples[norm_tuple] = idx
                rel_tuples.add(norm_tuple)

    # 4. Triple Validation & Dangling Reference Check
    triple_tuples: Set[Tuple[str, str, str]] = set()
    seen_triple_tuples: Dict[Tuple[str, str, str], int] = {}

    for idx, triple in enumerate(result.triples):
        subj_raw = str(triple.subject).strip() if triple.subject else ""
        obj_raw = str(triple.object).strip() if triple.object else ""

        if not subj_raw:
            errors.append(f"Triple at index {idx} has empty or missing 'subject'.")
        if not triple.predicate or not str(triple.predicate).strip():
            errors.append(f"Triple at index {idx} has empty or missing 'predicate'.")
        if not obj_raw:
            errors.append(f"Triple at index {idx} has empty or missing 'object'.")

        # Subject cross-reference check
        if subj_raw:
            subj_key = subj_raw.lower()
            if subj_key not in known_references:
                errors.append(
                    f"Triple subject '{triple.subject}' does not exist in extracted entities."
                )

        # Object cross-reference check
        if obj_raw:
            obj_key = obj_raw.lower()
            if obj_key not in known_references:
                errors.append(
                    f"Triple object '{triple.object}' does not exist in extracted entities."
                )

        if subj_raw and triple.predicate and obj_raw:
            pred_raw_str = str(triple.predicate).strip()
            p_str = pred_raw_str.upper().replace(" ", "_")
            norm_triple = (subj_raw.lower(), p_str, obj_raw.lower())
            # Duplicate triple detection
            if norm_triple in seen_triple_tuples:
                warnings.append(
                    f"Triple at index {idx} ({triple.subject} -> {p_str} -> {triple.object}) is a "
                    f"duplicate of triple at index {seen_triple_tuples[norm_triple]}."
                )
            else:
                seen_triple_tuples[norm_triple] = idx
                triple_tuples.add(norm_triple)

    # 5. Relationship and Triple Consistency Check
    # Check consistency whenever either side is non-empty (not just when both are present).
    if strict_triple_consistency:
        if result.relationships and result.triples:
            # Check if relationships have matching triples
            missing_in_triples = rel_tuples - triple_tuples
            if missing_in_triples:
                for s, p, t in missing_in_triples:
                    errors.append(
                        f"Inconsistency: Relationship ({s} -> {p} -> {t}) does not have a corresponding graph triple."
                    )

            missing_in_rels = triple_tuples - rel_tuples
            if missing_in_rels:
                for s, p, t in missing_in_rels:
                    errors.append(
                        f"Inconsistency: Triple ({s} -> {p} -> {t}) does not have a corresponding relationship."
                    )
        elif result.relationships and not result.triples:
            # Relationships present but triples array is completely absent (after auto-generation should have run)
            warnings.append(
                f"Extraction has {len(result.relationships)} relationship(s) but no graph triples. "
                "Triples should be auto-generated from relationships."
            )
        elif result.triples and not result.relationships:
            # Triples present but relationships array is empty
            warnings.append(
                f"Extraction has {len(result.triples)} triple(s) but no corresponding relationships."
            )

    is_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings
    )
