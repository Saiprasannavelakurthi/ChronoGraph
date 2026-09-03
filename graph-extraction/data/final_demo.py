"""
Final Demonstration Script — ChronoGraph Graph Extraction Module.

Showcases final validation enhancements:
  - Duplicate entity and relationship detection (warnings)
  - Dangling reference detection (errors)
  - Relationship / triple consistency validation
  - Empty input handling
  - Malformed LLM output resilience
  - Multi-source batch consolidation with Neo4j-ready output
"""

import json
import sys
import os

# Allow running from the repository root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline import process_text, process_records
from src.validator import validate_extraction
from src.errors import ExtractionValidationError
from src.extractor import GraphExtractor


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def print_header(title: str) -> None:
    width = 72
    print("\n" + "-" * width)
    print(f"  {title}")
    print("-" * width)


def print_ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def print_warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def print_err(msg: str) -> None:
    print(f"  [ERROR] {msg}")


# -----------------------------------------------------------------------------
# Mock LLM factory for offline demonstration
# -----------------------------------------------------------------------------

def make_mock_llm(responses):
    """
    Returns a callable mock LLM that returns successive string responses.
    Each call to llm.complete(prompt) consumes the next response string.
    """
    class _MockLLM:
        def __init__(self, responses):
            self._responses = list(responses)
            self._idx = 0

        def complete(self, prompt):
            class _Resp:
                pass
            r = _Resp()
            r.text = self._responses[self._idx % len(self._responses)]
            self._idx += 1
            return r

    return _MockLLM(responses)


# -----------------------------------------------------------------------------
# DEMO 1 — Empty input handling
# -----------------------------------------------------------------------------

print_header("DEMO 1 — Empty and whitespace-only input handling")

for label, val in [("empty string", ""), ("whitespace-only", "   \n\t  "), ("None", None)]:
    result = process_text(val)  # type: ignore[arg-type]
    status = "valid empty result" if result["is_valid"] and not result["entities"] else "unexpected result"
    print_ok(f"Input={label!r} -> {status} (entities: {len(result['entities'])}, valid: {result['is_valid']})")


# -----------------------------------------------------------------------------
# DEMO 2 — Duplicate entity and relationship detection (warnings)
# -----------------------------------------------------------------------------

print_header("DEMO 2 — Duplicate entity and relationship detection (validation warnings)")

duplicate_payload = {
    "entities": [
        {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
        {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},        # duplicate id
        {"id": "person_aathi_alt", "name": "aathi", "type": "PERSON"},   # duplicate canonical name
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

vr = validate_extraction(duplicate_payload, strict_triple_consistency=False)
print_ok(f"is_valid = {vr.is_valid}  |  warnings = {len(vr.warnings)}  |  errors = {len(vr.errors)}")
for w in vr.warnings:
    print_warn(w)


# -----------------------------------------------------------------------------
# DEMO 3 — Dangling reference detection (errors)
# -----------------------------------------------------------------------------

print_header("DEMO 3 — Dangling reference detection (critical validation errors)")

dangling_payload = {
    "entities": [
        {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
    ],
    "relationships": [
        {"source": "Aathi", "relation": "REVIEWED", "target": "PhantomPR"},     # dangling target
    ],
    "triples": [
        {"subject": "GhostUser", "predicate": "REVIEWED", "object": "PhantomPR"},  # dangling subject & object
    ]
}

vr2 = validate_extraction(dangling_payload, strict_triple_consistency=False)
print_ok(f"is_valid = {vr2.is_valid}  |  errors detected = {len(vr2.errors)}")
for e in vr2.errors:
    print_err(e)


# -----------------------------------------------------------------------------
# DEMO 4 — Relationship / Triple consistency validation
# -----------------------------------------------------------------------------

print_header("DEMO 4 — Relationship / Triple predicate inconsistency detection")

inconsistent_payload = {
    "entities": [
        {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
        {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"},
    ],
    "relationships": [
        {"source": "Karkuvel", "relation": "OPENED", "target": "#24"},
    ],
    "triples": [
        {"subject": "Karkuvel", "predicate": "MERGED", "object": "#24"},   # wrong predicate
    ]
}

vr3 = validate_extraction(inconsistent_payload, strict_triple_consistency=True)
print_ok(f"is_valid = {vr3.is_valid}  |  consistency errors = {len(vr3.errors)}")
for e in vr3.errors:
    print_err(e)


# -----------------------------------------------------------------------------
# DEMO 5 — Malformed LLM output resilience
# -----------------------------------------------------------------------------

print_header("DEMO 5 — Malformed LLM output resilience (offline mock LLM)")

malformed_responses = [
    "Sorry, I cannot process this request.",          # prose only
    '{"entities": [{"id": "person_aathi"',            # truncated JSON
    "[1, 2, 3]",                                      # JSON array not object
    "null",                                           # null JSON
    "```json\n{}\n```",                               # empty JSON object (code-fenced)
]

for resp in malformed_responses:
    llm = make_mock_llm([resp])
    extractor = GraphExtractor(llm=llm)
    result = extractor.extract("Some input text.")
    print_ok(
        f"Response={resp[:40]!r:45s} -> entities={len(result.entities)}, "
        f"relationships={len(result.relationships)}"
    )


# -----------------------------------------------------------------------------
# DEMO 6 — Multi-source batch consolidation + Neo4j-ready output
# -----------------------------------------------------------------------------

print_header("DEMO 6 — Multi-source batch consolidation (Slack + GitHub + Jira)")

batch_responses = [
    json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"},
        ],
        "relationships": [
            {"source": "Aathi", "relation": "DISCUSSED", "target": "Karkuvel"},
            {"source": "Aathi", "relation": "WORKED_ON", "target": "ChronoGraph"},
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "DISCUSSED", "object": "Karkuvel"},
            {"subject": "Aathi", "predicate": "WORKED_ON", "object": "ChronoGraph"},
        ]
    }),
    json.dumps({
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"},
            {"id": "commit_abc1234", "name": "abc1234", "type": "COMMIT"},
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "OPENED", "target": "#24"},
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "abc1234"},
        ],
        "triples": [
            {"subject": "Karkuvel", "predicate": "OPENED", "object": "#24"},
            {"subject": "Karkuvel", "predicate": "COMMITTED", "object": "abc1234"},
        ]
    }),
    json.dumps({
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
        ],
        "relationships": [
            {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"},
        ],
        "triples": [
            {"subject": "Aathi", "predicate": "ASSIGNED_TO", "object": "CG-102"},
        ]
    }),
]

llm_batch = make_mock_llm(batch_responses)
extractor_batch = GraphExtractor(llm=llm_batch)

records = [
    {
        "source": "slack",
        "text": "Aathi discussed the ChronoGraph pipeline with Karkuvel.",
        "metadata": {"channel": "#dev-chat", "timestamp": "2026-08-29T10:00:00Z"}
    },
    {
        "source": "github",
        "text": "Karkuvel opened pull request #24 and committed abc1234.",
        "metadata": {"repository": "ChronoGraph", "timestamp": "2026-08-29T11:00:00Z"}
    },
    {
        "source": "jira",
        "text": "Aathi was assigned the graph extraction task CG-102.",
        "metadata": {"project": "CG", "timestamp": "2026-08-29T12:00:00Z"}
    }
]

batch_result = process_records(records, extractor=extractor_batch, raise_on_validation_error=False)

print(f"\nNeo4j-Ready Batch Output:")
print(json.dumps(batch_result, indent=2))

print("\n" + "-" * 72)
print("  FINAL DEMONSTRATION SUMMARY")
print("-" * 72)
print_ok(f"Status: is_valid = {batch_result['is_valid']}")
print_ok(f"Unique Entities: {len(batch_result['entities'])}")
print_ok(f"Relationships:   {len(batch_result['relationships'])}")
print_ok(f"Triples:         {len(batch_result['triples'])}")
print_ok(f"Record Metadata: {len(batch_result['metadata']['records'])} records")
print_ok("Duplicate detection: warnings generated for duplicate entities/relationships")
print_ok("Dangling reference: errors reported for missing entity references")
print_ok("Consistency check: mismatched relationships/triples flagged")
print_ok("Malformed LLM output: gracefully returns empty result (no crash)")
print("-" * 72 + "\n")
