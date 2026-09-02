import json
import re
import logging
from typing import Optional, Dict, Any
from src.errors import GraphExtractionError, LLMCommunicationError, MalformedLLMResponseError
from src.config import Config
from src.models import GraphExtractionResult, Entity, Relationship, GraphTriple, RelationshipType
from src.prompts import GRAPH_EXTRACTION_SYSTEM_PROMPT, GRAPH_EXTRACTION_USER_PROMPT
from src.utils.text_utils import (
    clean_text,
    deduplicate_entities,
    deduplicate_relationships,
    deduplicate_triples,
    normalize_entity_name,
    generate_entity_id,
)

logger = logging.getLogger(__name__)


class GraphExtractor:
    """
    LlamaIndex-backed Enterprise Knowledge Graph Extractor.
    Extracts structured entities, relationships, and graph triples from enterprise text.
    """

    def __init__(self, llm=None):
        """
        Initialize GraphExtractor with optional custom LlamaIndex LLM or default configured LLM.
        """
        self.llm = llm or Config.get_llm()
        # Tracks dangling edges pruned during the most recent extract() call.
        self._last_pruned: list = []

    def extract(self, text: str, source: Optional[str] = None) -> GraphExtractionResult:
        """
        Main extraction entry point.
        Processes enterprise text and returns a structured GraphExtractionResult.
        
        Args:
            text (str): Input text content.
            source (str, optional): Enterprise data source type (e.g. 'slack', 'github', 'jira').
        """
        cleaned_input = clean_text(text)
        if not cleaned_input:
            logger.info("Empty or whitespace-only text provided for extraction.")
            return GraphExtractionResult(entities=[], relationships=[], triples=[])

        source_str = source.upper() if source else "GENERAL"
        user_prompt = GRAPH_EXTRACTION_USER_PROMPT.format(text=cleaned_input, source=source_str)

        try:
            raw_response = self._call_llm(user_prompt)
        except Exception as e:
            logger.error(f"Error during graph extraction LLM API processing: {e}")
            raise LLMCommunicationError(f"LLM extraction API call failed: {e}", original_error=e)

        result = self._parse_llm_response(raw_response)

        # Post-process, normalize, and deduplicate; capture any pruned dangling edges.
        self._last_pruned = []
        processed_result = self.post_process(result, _pruned=self._last_pruned)
        return processed_result

    def _call_llm(self, prompt: str) -> str:
        """
        Invoke LlamaIndex LLM instance. Supports both LlamaIndex LLM objects and mock LLM calls.
        """
        if self.llm is None:
            raise ValueError(
                "LLM instance is not configured. Ensure API keys or a custom LLM instance are provided."
            )

        full_prompt = f"{GRAPH_EXTRACTION_SYSTEM_PROMPT}\n\n{prompt}"

        # Standard LlamaIndex LLM complete interface
        if hasattr(self.llm, "complete") and callable(self.llm.complete):
            response = self.llm.complete(full_prompt)
            return getattr(response, "text", str(response))
        # Call object if callable (for mocks or simple functions)
        elif callable(self.llm):
            return str(self.llm(full_prompt))
        else:
            raise ValueError(
                f"Configured LLM object of type '{type(self.llm).__name__}' does not support LlamaIndex 'complete' method or callable invocation."
            )

    def _parse_llm_response(self, response_text: str) -> GraphExtractionResult:
        """
        Extract JSON payload from raw LLM output and construct Pydantic GraphExtractionResult.
        Returns an empty GraphExtractionResult on any parse or validation failure rather than
        raising, so that the caller can decide whether to treat it as an error.
        """
        if response_text is None:
            logger.warning("LLM returned None response text. Returning empty extraction result.")
            return GraphExtractionResult(entities=[], relationships=[], triples=[])

        if not response_text.strip():
            logger.info("LLM returned empty response text.")
            raise MalformedLLMResponseError("LLM returned empty response text.")

        json_str = response_text.strip()
        snippet = response_text[:300]

        # Explicitly check for markdown fences first
        md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_str, re.DOTALL | re.IGNORECASE)
        if md_match:
            json_str = md_match.group(1)
        else:
            # Fallback: Locate first '{' and last '}' to robustly extract JSON object,
            # handling leading/trailing text.
            start_idx = json_str.find("{")
            end_idx = json_str.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = json_str[start_idx:end_idx + 1]
            else:
                error_msg = f"LLM response contains no recognizable JSON object boundaries. Response snippet: {snippet!r}"
                logger.warning(error_msg)
                raise MalformedLLMResponseError(error_msg)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as err:
            error_msg = f"Failed to parse LLM JSON response (JSONDecodeError at position {err.pos}): {err.msg}. Response snippet: {snippet!r}"
            logger.warning(error_msg)
            raise MalformedLLMResponseError(error_msg, original_error=err)

        if not isinstance(data, dict):
            error_msg = f"LLM JSON payload is not a dictionary (got {type(data).__name__}). Response snippet: {snippet!r}"
            logger.warning(error_msg)
            raise MalformedLLMResponseError(error_msg)

        try:
            return GraphExtractionResult.model_validate(data)
        except Exception as val_err:
            error_msg = f"LLM extraction payload failed GraphExtractionResult schema validation: {val_err}. Parsed data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
            logger.warning(error_msg)
            raise MalformedLLMResponseError(error_msg, original_error=val_err)

    def post_process(
        self,
        result: GraphExtractionResult,
        _pruned: Optional[list] = None,
    ) -> GraphExtractionResult:
        """
        Public method to normalize entity names/IDs, deduplicate entities, relationships, and triples.
        Ensure missing triple objects are auto-generated from relationships.
        
        Dangling relationships/triples (referencing non-existent entities) are dropped with a warning
        and recorded in the ``_pruned`` list if one is provided, so callers can surface the information.
        """
        # Deduplicate entities
        entities = deduplicate_entities(result.entities)

        # Build lookup for normalized entity names
        entity_name_map = {e.name.lower(): e.name for e in entities}
        for e in entities:
            entity_name_map[e.id.lower()] = e.name
        
        valid_entity_names = set(entity_name_map.values())

        # Post-process relationships
        processed_rels = []
        for rel in result.relationships:
            src_norm = normalize_entity_name(rel.source)
            tgt_norm = normalize_entity_name(rel.target)

            src_name = entity_name_map.get(src_norm.lower(), src_norm)
            tgt_name = entity_name_map.get(tgt_norm.lower(), tgt_norm)
            
            rel_val = rel.relation.value if hasattr(rel.relation, "value") else str(rel.relation)
            rel_enum = RelationshipType(rel_val) if not isinstance(rel.relation, RelationshipType) else rel.relation

            processed_rels.append(
                Relationship(
                    source=src_name,
                    relation=rel_enum,
                    target=tgt_name,
                )
            )

        # Post-process triples
        processed_triples = []
        if result.triples:
            for t in result.triples:
                subj_norm = normalize_entity_name(t.subject)
                obj_norm = normalize_entity_name(t.object)
                subj_name = entity_name_map.get(subj_norm.lower(), subj_norm)
                obj_name = entity_name_map.get(obj_norm.lower(), obj_norm)

                pred_val = t.predicate.value if hasattr(t.predicate, "value") else str(t.predicate)
                pred_enum = RelationshipType(pred_val)

                processed_triples.append(
                    GraphTriple(
                        subject=subj_name,
                        predicate=pred_enum.value,
                        object=obj_name,
                    )
                )

        # Synchronize relationships and triples using complete (source, predicate, target) tuples
        combined_tuples = []

        for r in processed_rels:
            r_str = r.relation.value if hasattr(r.relation, "value") else str(r.relation)
            combined_tuples.append((r.source, r_str, r.target))

        for t in processed_triples:
            combined_tuples.append((t.subject, t.predicate, t.object))

        # Preserve order while collecting unique (source, predicate, target) tuples
        unique_tuples = list(dict.fromkeys(combined_tuples))

        # Filter out dangling relationships/triples to maintain graph consistency
        consistent_tuples = []
        for s, p, t in unique_tuples:
            if s in valid_entity_names and t in valid_entity_names:
                consistent_tuples.append((s, p, t))
            else:
                msg = f"Dangling edge dropped: ({s} -> {p} -> {t}) — one or both entities missing from extraction."
                logger.warning(msg)
                if _pruned is not None:
                    _pruned.append(msg)

        # Build synchronized Relationships and GraphTriples matching 1-to-1
        final_rels = [Relationship(source=s, relation=p, target=t) for (s, p, t) in consistent_tuples]
        final_triples = [GraphTriple(subject=s, predicate=p, object=t) for (s, p, t) in consistent_tuples]

        rels = deduplicate_relationships(final_rels)
        triples = deduplicate_triples(final_triples)

        return GraphExtractionResult(
            entities=entities,
            relationships=rels,
            triples=triples,
        )

    # Backward compatible alias for private post_process
    _post_process = post_process
