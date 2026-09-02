import re
from typing import List, Dict, Set
from src.models import Entity, Relationship, GraphTriple, EntityType, RelationshipType


# Pre-compile regex patterns for text cleaning
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
MULTI_SPACE_PATTERN = re.compile(r'[ \t]+')
MULTI_NEWLINE_PATTERN = re.compile(r'\n+')

def clean_text(text: str) -> str:
    """
    Clean and preprocess enterprise input text.
    Strips leading/trailing whitespace, normalizes internal spaces,
    and removes non-printable control characters.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text.strip():
        return ""
    # Remove control characters except newlines/tabs
    text = CONTROL_CHARS_PATTERN.sub('', text)
    # Normalize multiple whitespace characters to single space while preserving basic line breaks
    text = MULTI_SPACE_PATTERN.sub(' ', text)
    text = MULTI_NEWLINE_PATTERN.sub('\n', text)
    return text.strip()


# Patterns for preserving case-sensitive identifiers
COMMIT_HASH_PATTERN = re.compile(r'^[0-9a-f]{6,40}$', re.IGNORECASE)
JIRA_KEY_PATTERN = re.compile(r'^[A-Z0-9]+-\d+$')
PR_ISSUE_NUM_PATTERN = re.compile(r'^#?\d+$')
HANDLE_PATTERN = re.compile(r'^@[A-Za-z0-9_-]+$')
REPO_PATTERN = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')

# Known technical acronyms and enterprise systems to preserve in uppercase
KNOWN_TECH_ACRONYMS: Set[str] = {
    "GCP", "AWS", "API", "SDK", "REST", "JIRA", "SQL", "PR", "CI", "CD",
    "CI/CD", "VCS", "ID", "JSON", "LLM", "UI", "RAG", "NEO4J", "HTTP",
    "URL", "DB", "IAM", "OS", "CLI", "RPC", "GRPC", "K8S", "GKE", "EC2",
    "S3", "RDS", "VPC", "SSO", "OAUTH"
}


def normalize_entity_name(name: str) -> str:
    """
    Normalize entity name.
    Preserves case-sensitive identifiers like GitHub usernames (@handle), commit hashes,
    PR/issue numbers (#24), Jira keys (CG-102), and technical systems (GCP, AWS),
    while consistently resolving case variations for general human names (Aathi, aathi, AATHI -> Aathi).
    """
    if not name:
        return ""

    raw_name = name.strip()

    # Preserve exact patterns: commit hashes, Jira keys, PR numbers, @handles, repo names
    if (COMMIT_HASH_PATTERN.match(raw_name) or 
        JIRA_KEY_PATTERN.match(raw_name) or 
        PR_ISSUE_NUM_PATTERN.match(raw_name) or 
        HANDLE_PATTERN.match(raw_name) or
        REPO_PATTERN.match(raw_name)):
        return raw_name

    # Preserve known tech acronyms and cloud platforms in uppercase
    if raw_name.upper() in KNOWN_TECH_ACRONYMS:
        return raw_name.upper()

    # Clean surrounding punctuation except # or @
    cleaned = re.sub(r'^[^\w#@]+|[^\w]+$', '', raw_name)
    if not cleaned:
        cleaned = raw_name

    # Collapse internal multiple spaces/tabs to a single space
    cleaned = re.sub(r'[ \t]+', ' ', cleaned).strip()

    # Normalize all-uppercase or all-lowercase names to Title Case (e.g. 'AATHI' / 'aathi' -> 'Aathi')
    # Preserves CamelCase/PascalCase (e.g. 'ChronoGraph', 'FastAPI', 'Neo4j')
    if cleaned.isupper() or cleaned.islower():
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
        name="GCP", type="SYSTEM" -> "system_gcp"
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

        # Name key based on canonical normalized name
        name_key = f"{type_str.upper()}:{norm_name.lower()}"
        
        if name_key in seen_names:
            existing = seen_names[name_key]
            # Prefer more descriptive/specific name unless existing is a technical hash
            if (len(entity.name) > len(existing.name) and 
                not COMMIT_HASH_PATTERN.match(entity.name) and 
                not JIRA_KEY_PATTERN.match(entity.name)):
                old_id = existing.id
                existing.name = normalize_entity_name(entity.name)
                new_id = generate_entity_id(existing.name, type_str)
                existing.id = new_id
                if old_id != new_id and old_id in seen_ids:
                    del seen_ids[old_id]
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
    Deduplicate relationships list while preserving distinct predicates.
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
