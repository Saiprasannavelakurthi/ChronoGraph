"""
src/extraction/prompts.py
─────────────────────────
Prompt templates for the ChronoGraph temporal triple extraction pipeline.

Design principles
─────────────────
- Be explicit about the output format so structured parsing is reliable.
- Request ONLY relationships that are directly supported by the source text.
- Require temporal grounding for every extracted triple.
- Keep the prompt concise to minimise token cost with local LLMs.
- Include few-shot examples to guide small models (Llama 3 7B).
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Extract Entity → Relation → Entity triples from enterprise records (Slack, GitHub, Jira).

RULES:
1. Extract ONLY stated relationships. Every triple MUST have these 10 fields:
   - subject (str)
   - subject_type: "Person", "Technology", "Project", "Service", "Database", "Organization", "Team", "Architecture", "Issue", "Problem", "ArchitectureDecision", "Other"
   - relation: SNAKE_CASE (ADVOCATED_FOR, ARGUED_AGAINST, COMMITTED_CODE, REVIEWED, ASSIGNED_TO, MIGRATED_TO, RAISED_CONCERN, DECIDED, IMPLEMENTED, REPORTED_BUG, FIXED, APPROVED, BLOCKED_BY, RELATED_TO, DEPRECATED, ENROLLED_IN)
   - object (str)
   - object_type: "Person", "Technology", "Project", "Service", "Database", "Organization", "Team", "Architecture", "Issue", "Problem", "ArchitectureDecision", "Other"
   - timestamp: ISO 8601 string from metadata
   - source: "slack", "github", or "jira"
   - source_id: string event identifier
   - confidence: float between 0.0 and 1.0
   - evidence: exact quote supporting the triple
2. Return ONLY a valid JSON array of objects. No markdown, no extra commentary."""

USER_PROMPT_TEMPLATE = """EVENT METADATA:
source: {source} | source_id: {source_id} | author: {author} | timestamp: {timestamp} | channel: {channel}

EVENT TEXT:
{content}

EXAMPLE JSON OUTPUT:
[
  {{
    "subject": "{author}",
    "subject_type": "Person",
    "relation": "ADVOCATED_FOR",
    "object": "GCP",
    "object_type": "Technology",
    "timestamp": "{timestamp}",
    "source": "{source}",
    "source_id": "{source_id}",
    "confidence": 0.9,
    "evidence": "suggested evaluating GCP migration"
  }}
]

Return JSON array:"""

# ─────────────────────────────────────────────────────────────────────────────
# Helper to render the user prompt for a given RawEvent
# ─────────────────────────────────────────────────────────────────────────────


def build_user_prompt(
    content: str,
    source: str,
    source_id: str,
    author: str,
    timestamp: str,
    channel: str = "",
) -> str:
    """
    Render the user prompt template with the provided event fields.

    Parameters
    ----------
    content:
        The text content of the event.
    source:
        The source system name (e.g. "slack").
    source_id:
        The native event ID.
    author:
        The author username.
    timestamp:
        ISO 8601 timestamp string.
    channel:
        Channel / repo / project name (optional).

    Returns
    -------
    str
        A fully-rendered prompt string ready to pass to the LLM.
    """
    return USER_PROMPT_TEMPLATE.format(
        source=source,
        source_id=source_id,
        author=author,
        timestamp=timestamp,
        channel=channel or "N/A",
        content=content,
    )
