import re
from typing import List, Dict
from src.models import Entity, Relationship, GraphTriple, EntityType, RelationshipType


def clean_text(text: str) -> str:
    """
    Clean and preprocess enterprise input text.
    Strips leading/trailing whitespace, normalizes internal spaces,
    and removes non-printable control characters.
    """
    if not text:
        return ""
    # Remove control characters except newlines/tabs
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Normalize multiple whitespace characters to single space while preserving basic line breaks
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()


# Patterns for preserving case-sensitive identifiers
COMMIT_HASH_PATTERN = re.compile(r'^[0-9a-f]{6,40}$', re.IGNORECASE)
JIRA_KEY_PATTERN = re.compile(r'^[A-Z0-9]+-\d+$')
PR_ISSUE_NUM_PATTERN = re.compile(r'^#?\d+$')
HANDLE_PATTERN = re.compile(r'^@[A-Za-z0-9_-]+$')


def normalize_entity_name(name: str) -> str:
    """
    Normalize entity name.
    Preserves case-sensitive identifiers like GitHub usernames (@handle), commit hashes,
    PR/issue numbers (#24), and Jira keys (CG-102), while standardizing whitespace and title casing for general text.
    """
    if not name:
        return ""

    raw_name = name.strip()

    # Do not mutate commit hashes, Jira issue keys, PR numbers, or @handles
    if (COMMIT_HASH_PATTERN.match(raw_name) or 
        JIRA_KEY_PATTERN.match(raw_name) or 
        PR_ISSUE_NUM_PATTERN.match(raw_name) or 
        HANDLE_PATTERN.match(raw_name)):
        return raw_name

    # If all uppercase (like PROJ-123 or API), keep as is
    if raw_name.isupper() and len(raw_name) <= 6:
        return raw_name

    # Basic normalization for names: strip surrounding punctuation except # or @
    cleaned = re.sub(r'^[^\w#@]+|[^\w]+$', '', raw_name)
    if not cleaned:
        cleaned = raw_name

    # Title-case single/multi word human names if lowercase (e.g. 'karkuvel' -> 'Karkuvel')
    if cleaned.islower():
        return cleaned.title()

    return cleaned


def generate_entity_id(name: str, entity_type: str) -> str:
    """
    Generate a deterministic slug identifier for an entity.
    Examples:
        name="Karkuvel", type="PERSON" -> "person_karkuvel"
        name="CG-102", type="ISSUE" -> "issue_cg_102"
        name="#24", type="PULL_REQUEST" -> "pull_request_24"
        name="abc1234", type="COMMIT" -> "commit_abc1234"
    """
    if hasattr(entity_type, "value"):
        type_str = str(entity_type.value)
    else:
        type_str = str(entity_type)
    
    type_prefix = type_str.lower().replace("entitytype.", "")
    norm_name = name.strip().lower()

    # Replace non-alphanumeric chars with underscore
    slug = re.sub(r'[^a-z0-9]+', '_', norm_name).strip('_')
    if not slug:
        slug = "unnamed"
    return f"{type_prefix}_{slug}"


def deduplicate_entities(entities: List[Entity]) -> List[Entity]:
    """
    Deduplicate entities list while preserving canonical entity details.
    Normalizes names and produces stable deterministic entity IDs across occurrences.
    """
    seen_ids: Dict[str, Entity] = {}
    seen_names: Dict[str, Entity] = {}

    for entity in entities:
        norm_name = normalize_entity_name(entity.name)
        type_str = entity.type.value if isinstance(entity.type, EntityType) else str(entity.type)
        
        # Calculate canonical stable ID deterministically
        entity_id = generate_entity_id(norm_name, type_str)

        # Check if we already have this entity by name (case-insensitive) or canonical ID
        name_key = f"{type_str.upper()}:{norm_name.lower()}"
        
        if name_key in seen_names:
            existing = seen_names[name_key]
            # Update name if current name is more complete (e.g. 'Karkuvel P' vs 'Karkuvel')
            if len(entity.name) > len(existing.name) and not COMMIT_HASH_PATTERN.match(entity.name):
                existing.name = entity.name
                # Re-generate deterministic ID if canonical name updated
                new_id = generate_entity_id(entity.name, type_str)
                existing.id = new_id
                seen_ids[new_id] = existing
            continue
        elif entity_id in seen_ids:
            continue
        else:
            # Create updated entity with stable deterministic ID
            updated_entity = Entity(
                id=entity_id,
                name=norm_name,
                type=entity.type
            )
            seen_ids[entity_id] = updated_entity
            seen_names[name_key] = updated_entity

    return list(seen_ids.values())


def deduplicate_relationships(relationships: List[Relationship]) -> List[Relationship]:
    """
    Deduplicate relationships list.
    """
    seen = set()
    deduped = []
    for rel in relationships:
        src = normalize_entity_name(rel.source)
        tgt = normalize_entity_name(rel.target)
        rel_type = rel.relation.value if isinstance(rel.relation, RelationshipType) else str(rel.relation)
        key = (src.lower(), rel_type.upper(), tgt.lower())
        if key not in seen:
            seen.add(key)
            deduped.append(Relationship(
                source=src,
                relation=rel.relation,
                target=tgt
            ))
    return deduped


def deduplicate_triples(triples: List[GraphTriple]) -> List[GraphTriple]:
    """
    Deduplicate graph triples list.
    """
    seen = set()
    deduped = []
    for t in triples:
        subj = normalize_entity_name(t.subject)
        obj = normalize_entity_name(t.object)
        pred = t.predicate.strip().upper().replace(" ", "_")
        key = (subj.lower(), pred, obj.lower())
        if key not in seen:
            seen.add(key)
            deduped.append(GraphTriple(
                subject=subj,
                predicate=pred,
                object=obj
            ))
    return deduped
