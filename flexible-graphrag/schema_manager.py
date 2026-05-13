from llama_index.core.indices.property_graph import SchemaLLMPathExtractor, SimpleLLMPathExtractor, DynamicLLMPathExtractor
from llama_index.core.prompts import PromptTemplate
from typing import List, Dict, Any, Literal
import logging

logger = logging.getLogger(__name__)


class SchemaManager:
    """Manages schema definitions for entity and relationship extraction"""

    def __init__(self, schema_config: Dict[str, Any] = None, app_config=None):
        self.schema_config = schema_config or {}
        self.app_config = app_config
        self._ontology_manager = None
        self._ontology_loaded = False

    def _get_ontology_manager(self):
        """Lazy-load ontology manager from RDF system if available"""
        if not self._ontology_loaded:
            self._ontology_loaded = True  # Only try once
            try:
                from rdf.api_rdf_enhancements import ontology_manager
                if ontology_manager:
                    self._ontology_manager = ontology_manager
                    logger.info(f"SchemaManager: Found ontology with {len(ontology_manager.entities)} entities, {len(ontology_manager.relations)} relations")
            except (ImportError, AttributeError) as e:
                logger.debug(f"SchemaManager: No ontology manager available: {e}")
        return self._ontology_manager

    @property
    def ontology_manager(self):
        """Public property for accessing the ontology manager."""
        return self._get_ontology_manager()

    @staticmethod
    def _to_literal(values: List[str]):
        """Convert a list of strings to a Literal type for SchemaLLMPathExtractor.

        LlamaIndex's get_entity_class/get_relation_class use the type annotation directly
        in Pydantic's create_model. When strict=True it must be a Literal type, not a plain
        list, otherwise Pydantic raises PydanticSchemaGenerationError.
        """
        return Literal[tuple(values)]  # type: ignore[valid-type]

    def create_extractor(self, llm, llm_provider=None, extractor_type: str = "schema"):
        """Create knowledge graph extractor with optional schema enforcement

        Args:
            llm: The LLM instance to use
            llm_provider: The LLM provider enum (for provider-specific handling)
            extractor_type: "simple", "schema", or "dynamic"
        """

        # Check if ontology is available
        ontology_manager = self._get_ontology_manager()
        use_ontology = ontology_manager and hasattr(self.app_config, 'use_ontology') and self.app_config.use_ontology
        disable_properties_global = self.app_config.disable_properties if (self.app_config and hasattr(self.app_config, 'disable_properties')) else False

        # Use 4 workers for all LLM providers - Ollama parallel processing now properly configured
        workers = 4

        # Log LLM provider for debugging
        from config import LLMProvider
        is_ollama = (llm_provider == LLMProvider.OLLAMA) if llm_provider else False
        logger.info(f"LLM Provider Detection: {llm_provider} -> is_ollama={is_ollama} -> workers={workers}")
        if is_ollama:
            logger.info(f"OLLAMA PARALLEL PROCESSING: Using {workers} workers with OLLAMA_NUM_PARALLEL=4 configuration")

        # NOTE: Bedrock requires DynamicLLMPathExtractor — BedrockConverse's Converse API
        # raises a ValidationException when SchemaLLMPathExtractor sends its tool schema
        # (toolConfig.toolChoice.any not supported, or invalid ToolUse sequence).
        # TODO: Retest Bedrock once LlamaIndex updates BedrockConverse tool schema generation.
        #
        # Fireworks: SchemaLLMPathExtractor previously threw code exceptions and Dynamic gave 0
        #   entities. Root cause was max_tokens=256 (default) — fixed in factories.py (32768).
        #   SchemaLLMPathExtractor uses achat_with_tools (function calling) which Fireworks
        #   supports — retesting with function mode now that max_tokens is correct.
        #   DynamicLLMPathExtractor uses apredict() (plain text); _custom_is_function_calling
        #   is set False on extractor LLM so achat() returns text not tool calls.
        #
        # Groq: DynamicLLMPathExtractor now working (fixed context_window + max_tokens in
        #   factories.py, 2026-03-17). SchemaLLMPathExtractor previously broken due to old
        #   LlamaIndex astructured_predict injecting tool_choice="required" into llm_kwargs
        #   which FunctionCallingProgram.acall then stripped. Current LlamaIndex uses
        #   FunctionCallingProgram directly (pydantic_program_mode=FUNCTION) which does NOT
        #   inject tool_choice into llm_kwargs — that path is bypassed. Worth retesting.
        #   For now keeping both in switch_to_dynamic_providers as DynamicLLMPathExtractor
        #   is confirmed working. To try SchemaLLMPathExtractor: set KG_EXTRACTOR_TYPE=schema
        #   and remove groq/fireworks from switch_to_dynamic_providers below.
        #
        # openai_like: SchemaLLMPathExtractor returns 0 entities (same tool_choice conflict
        #   as Groq — OpenAILike class is used for both). DynamicLLMPathExtractor works once
        #   is_function_calling_model is reset to False in _make_dynamic_extractor (apredict
        #   must use plain text, not tool calls). Context window defaults to 4096 in factories.py
        #   — set OPENAI_LIKE_CONTEXT_WINDOW in .env for local servers with larger windows.
        #
        # openrouter: OpenRouter extends OpenAILike with is_function_calling_model=False by default.
        #   SchemaLLMPathExtractor returns 0 entities instantly even with valid credits — genuine
        #   tool-calling incompatibility (same pattern as openai_like/groq). Switch to Dynamic.
        switch_to_simple_providers = []
        # vllm: OpenAI-compatible server strictly rejects tool_choice="required" when tools=[].
        # SchemaLLMPathExtractor injects tool_choice="required" unconditionally -> HTTP 400.
        # DynamicLLMPathExtractor avoids tool_choice, works fine with vLLM.
        switch_to_dynamic_providers = ["bedrock", "fireworks", "groq", "openai_like", "openrouter", "vllm"]

        # LiteLLM routing to Ollama models: SchemaLLMPathExtractor returns 0 entities
        # (same tool_choice conflict as direct Ollama). Switch to Dynamic for ollama/* models.
        if llm_provider and str(llm_provider).lower() == "litellm":
            litellm_model = getattr(llm, "model", "") or ""
            if litellm_model.startswith("ollama/"):
                switch_to_dynamic_providers = switch_to_dynamic_providers + ["litellm"]

        llm_provider_str = str(llm_provider).lower() if llm_provider else None
        logger.info(f"Checking provider '{llm_provider_str}' for extractor compatibility")
        if llm_provider_str in switch_to_simple_providers:
            if extractor_type in ("schema", "dynamic"):
                logger.warning(f"Provider {llm_provider}: SchemaLLMPathExtractor and DynamicLLMPathExtractor both broken — forcing SimpleLLMPathExtractor")
                extractor_type = "simple"
        elif llm_provider_str in switch_to_dynamic_providers:
            if extractor_type == "schema":
                logger.warning(f"Provider {llm_provider}: SchemaLLMPathExtractor incompatible — switching to DynamicLLMPathExtractor")
                extractor_type = "dynamic"

        # Get configurable values - environment variable has priority, schema provides defaults
        schema_max_triplets = self.schema_config.get('max_triplets_per_chunk', 20) if self.schema_config else 20
        schema_max_paths = self.schema_config.get('max_paths_per_chunk', 20) if self.schema_config else 20

        # Environment variable overrides schema value if set
        max_triplets = getattr(self.app_config, 'max_triplets_per_chunk', schema_max_triplets) if self.app_config else schema_max_triplets
        max_paths = getattr(self.app_config, 'max_paths_per_chunk', schema_max_paths) if self.app_config else schema_max_paths

        logger.info(f"Extraction limits: max_triplets_per_chunk={max_triplets}, max_paths_per_chunk={max_paths}")

        def _make_dynamic_extractor(kwargs: dict) -> "DynamicLLMPathExtractor":
            """
            Create a DynamicLLMPathExtractor and fix two LlamaIndex bugs:

            Bug 1 (props): __init__ converts None props to [] — causing _aextract to always
            call _apredict_with_props even when no props were requested, sending an
            empty-string props prompt that confuses some LLMs.
            Fix: after construction, reset empty-list props back to None so _aextract
            takes the _apredict_without_props path (clean JSON prompt, no props section).

            Bug 2 (prompt braces): DEFAULT_DYNAMIC_EXTRACT_PROMPT contains {{...}} escaped
            braces in its GUIDELINES/EXAMPLE sections. LlamaIndex's SafeFormatter uses
            regex substitution (not str.format) so it never collapses {{ -> {.
            The model receives literal {{head}} instead of {head} in JSON examples,
            causing it to return malformed output or empty string.
            Fix: replace {{ and }} in the template with single braces before use.
            """
            extractor = DynamicLLMPathExtractor(**kwargs)
            has_entity_props = bool(kwargs.get("allowed_entity_props"))
            has_relation_props = bool(kwargs.get("allowed_relation_props"))
            if not has_entity_props:
                extractor.allowed_entity_props = None
            if not has_relation_props:
                extractor.allowed_relation_props = None
            # Fix prompt double-brace escaping bug
            if hasattr(extractor, 'extract_prompt') and extractor.extract_prompt is not None:
                raw = extractor.extract_prompt.template
                if '{{' in raw or '}}' in raw:
                    fixed = raw.replace('{{', '{').replace('}}', '}')
                    extractor.extract_prompt = PromptTemplate(fixed)
                    logger.info("DynamicLLMPathExtractor: fixed double-brace escaping in extract_prompt")

            # Fix: DynamicLLMPathExtractor uses llm.apredict() (plain text completion),
            # NOT tool/function calling. If function calling is enabled, achat() returns a
            # tool_call response with content=None, which apredict() collapses to ''.
            # Force function calling off on the extractor's LLM instance so achat()
            # returns plain text. The LLM object in factories.py is unaffected.
            #
            # Two attribute patterns depending on LLM class:
            #   _custom_is_function_calling — Fireworks (OpenAI-derived, set via is_function_calling kwarg)
            #   is_function_calling_model   — Groq/OpenAILike (plain Pydantic field, default False,
            #                                 but set True in factories.py for Groq and openai_like)
            #
            # Scoped to switch_to_dynamic_providers only (bedrock, fireworks, groq, openai_like).
            # Confirmed safe: OpenAI, Anthropic, Ollama, Gemini — none have these attrs set True.
            if llm_provider_str in switch_to_dynamic_providers and hasattr(extractor, 'llm'):
                _llm = extractor.llm
                if hasattr(_llm, '_custom_is_function_calling') and _llm._custom_is_function_calling:
                    _llm._custom_is_function_calling = False
                    logger.info("DynamicLLMPathExtractor: set llm._custom_is_function_calling=False (apredict uses plain text, not tool calls)")
                elif hasattr(_llm, 'is_function_calling_model') and _llm.is_function_calling_model:
                    _llm.is_function_calling_model = False
                    logger.info("DynamicLLMPathExtractor: set llm.is_function_calling_model=False (apredict uses plain text, not tool calls)")
            props_info = f"entity_props={'yes' if has_entity_props else 'no'}, relation_props={'yes' if has_relation_props else 'no'}"
            logger.info(f"DynamicLLMPathExtractor created: {props_info}, disable_properties_global={disable_properties_global}")

            return extractor

        # Handle dynamic extractor type
        if extractor_type == "dynamic":
            logger.info("Using DynamicLLMPathExtractor for flexible relationship discovery")

            # Check for ontology guidance first, then fall back to schema_config
            if use_ontology:
                entities = list(ontology_manager.entities.keys())
                relations = list(ontology_manager.relations.keys())

                # Extract entity properties from ontology
                # Format: [(property_name, property_type), ...] - properties are global
                entity_props = []
                seen_props = set()
                for entity_name, entity in ontology_manager.entities.items():
                    if entity.properties:
                        for prop_name, prop_type in entity.properties.items():
                            prop_key = (prop_name, prop_type)
                            if prop_key not in seen_props:
                                entity_props.append(prop_key)
                                seen_props.add(prop_key)

                # Extract relation properties from ontology
                relation_props = []
                seen_rel_props = set()
                for relation_name, relation in ontology_manager.relations.items():
                    if relation.properties:
                        for prop_name, prop_type in relation.properties.items():
                            prop_key = (prop_name, prop_type)
                            if prop_key not in seen_rel_props:
                                relation_props.append(prop_key)
                                seen_rel_props.add(prop_key)

                logger.info(f"Using ontology guidance: {len(entities)} entity types, {len(relations)} relation types from ontology")
                if entity_props:
                    logger.info(f"Using ontology properties: {len(entity_props)} unique entity properties defined")
                if relation_props:
                    logger.info(f"Using ontology properties: {len(relation_props)} unique relation properties defined")

                extractor_kwargs = {
                    "llm": llm,
                    "max_triplets_per_chunk": max_triplets,
                    "num_workers": workers,
                    "allowed_entity_types": entities,
                    "allowed_relation_types": relations
                }

                # Add entity properties if available
                # DynamicLLMPathExtractor._apredict_with_props does ", ".join(...) on these —
                # tuples cause TypeError. Convert to "name (type)" strings.
                if entity_props and not disable_properties_global:
                    extractor_kwargs["allowed_entity_props"] = [f"{n} ({t})" for n, t in entity_props]

                # Add relation properties if available
                if relation_props and not disable_properties_global:
                    extractor_kwargs["allowed_relation_props"] = [f"{n} ({t})" for n, t in relation_props]

                return _make_dynamic_extractor(extractor_kwargs)
            elif self.schema_config:
                logger.info("Providing schema guidance to DynamicLLMPathExtractor")

                # Extract entity and relation types from schema
                entities = self.schema_config.get("entities", [])
                relations = self.schema_config.get("relations", [])
                properties_dict = self.schema_config.get("properties", {})
                relation_properties_dict = self.schema_config.get("relation_properties", {})

                # Extract entity properties (deduplicated)
                entity_props = []
                seen_props = set()
                for entity_name, props in properties_dict.items():
                    for prop_name, prop_type in props.items():
                        prop_key = (prop_name, prop_type)
                        if prop_key not in seen_props:
                            entity_props.append(prop_key)
                            seen_props.add(prop_key)

                # Extract relation properties (deduplicated)
                relation_props = []
                seen_rel_props = set()
                for relation_name, props in relation_properties_dict.items():
                    for prop_name, prop_type in props.items():
                        prop_key = (prop_name, prop_type)
                        if prop_key not in seen_rel_props:
                            relation_props.append(prop_key)
                            seen_rel_props.add(prop_key)

                logger.info(f"Dynamic extractor with {len(entities)} entity types, {len(relations)} relation types from schema")
                if entity_props:
                    logger.info(f"Using schema properties: {len(entity_props)} unique entity properties defined")
                if relation_props:
                    logger.info(f"Using schema properties: {len(relation_props)} unique relation properties defined")

                # With initial schema - provide starting guidance but allow expansion
                extractor_kwargs = {
                    "llm": llm,
                    "max_triplets_per_chunk": max_triplets,
                    "num_workers": workers,
                    "allowed_entity_types": entities,
                    "allowed_relation_types": relations
                }

                # Add entity properties if available
                # DynamicLLMPathExtractor._apredict_with_props does ", ".join(...) on these —
                # tuples cause TypeError. Convert to "name (type)" strings.
                if entity_props and not disable_properties_global:
                    extractor_kwargs["allowed_entity_props"] = [f"{n} ({t})" for n, t in entity_props]

                # Add relation properties if available
                if relation_props and not disable_properties_global:
                    extractor_kwargs["allowed_relation_props"] = [f"{n} ({t})" for n, t in relation_props]

                return _make_dynamic_extractor(extractor_kwargs)
            else:
                logger.info("Using DynamicLLMPathExtractor without schema or ontology - full LLM freedom")
                # Without schema or ontology - complete freedom to infer schema
                return _make_dynamic_extractor({
                    "llm": llm,
                    "max_triplets_per_chunk": max_triplets,
                    "num_workers": workers
                })

        # Handle simple extractor type
        if extractor_type == "simple":
            logger.info(f"Using SimpleLLMPathExtractor (extractor_type=simple)")
            return SimpleLLMPathExtractor(
                llm=llm,
                max_paths_per_chunk=max_paths,
                num_workers=workers
            )

        # Default to schema-based extraction (SchemaLLMPathExtractor)
        logger.info(f"Using SchemaLLMPathExtractor with LLM: {llm.model}")

        # strict=True: only extract entity/relation types defined in the schema (Pydantic-enforced)
        # strict=False: schema guides extraction but LLM may also produce types outside the schema
        # LlamaIndex requires possible_entities/relations to be a Literal type (not a plain list)
        # when strict=True. We convert our lists to Literal before passing to the extractor.
        strict_mode = True
        if self.app_config and hasattr(self.app_config, 'strict_schema_validation'):
            strict_mode = self.app_config.strict_schema_validation
        logger.info(f"SchemaLLMPathExtractor strict={strict_mode} ({'schema-only' if strict_mode else 'schema + open'})")

        disable_properties = False
        if self.app_config and hasattr(self.app_config, 'disable_properties'):
            disable_properties = self.app_config.disable_properties
            if disable_properties:
                logger.warning("Properties disabled via DISABLE_PROPERTIES config")

        # Check for ontology guidance first, then fall back to schema_config
        if use_ontology:
            entities = list(ontology_manager.entities.keys())
            relations = list(ontology_manager.relations.keys())

            # Extract entity properties from ontology
            # Format: [(property_name, property_type), ...] - properties are global, not entity-specific
            entity_props = []
            seen_props = set()
            for entity_name, entity in ontology_manager.entities.items():
                if entity.properties:
                    for prop_name, prop_type in entity.properties.items():
                        prop_key = (prop_name, prop_type)
                        if prop_key not in seen_props:
                            entity_props.append(prop_key)
                            seen_props.add(prop_key)

            # Extract relation properties from ontology
            relation_props = []
            seen_rel_props = set()
            for relation_name, relation in ontology_manager.relations.items():
                if relation.properties:
                    for prop_name, prop_type in relation.properties.items():
                        prop_key = (prop_name, prop_type)
                        if prop_key not in seen_rel_props:
                            relation_props.append(prop_key)
                            seen_rel_props.add(prop_key)

            logger.info(f"Using ontology guidance: {len(entities)} entity types, {len(relations)} relation types from ontology")
            if entity_props and not disable_properties:
                logger.info(f"Using ontology properties: {len(entity_props)} unique entity properties defined")
            if relation_props and not disable_properties:
                logger.info(f"Using ontology properties: {len(relation_props)} unique relation properties defined")

            extractor_kwargs = {
                "llm": llm,
                "possible_entities": self._to_literal(entities) if strict_mode else entities,
                "possible_relations": self._to_literal(relations) if strict_mode else relations,
                "strict": strict_mode,
                "max_triplets_per_chunk": max_triplets,
                "num_workers": workers
            }

            # Add entity properties if available (unless disabled)
            if entity_props and not disable_properties:
                extractor_kwargs["possible_entity_props"] = entity_props

            # Add relation properties if available (unless disabled)
            if relation_props and not disable_properties:
                extractor_kwargs["possible_relation_props"] = relation_props

            return SchemaLLMPathExtractor(**extractor_kwargs)
        elif self.schema_config:
            entities = self.schema_config.get("entities", [])
            relations = self.schema_config.get("relations", [])
            properties_dict = self.schema_config.get("properties", {})
            relation_properties_dict = self.schema_config.get("relation_properties", {})

            # Extract entity properties
            # Format: [(property_name, property_type), ...] - properties are global, not entity-specific
            entity_props = []
            seen_props = set()
            for entity_name, props in properties_dict.items():
                for prop_name, prop_type in props.items():
                    prop_key = (prop_name, prop_type)
                    if prop_key not in seen_props:
                        entity_props.append(prop_key)
                        seen_props.add(prop_key)

            # Extract relation properties
            relation_props = []
            seen_rel_props = set()
            for relation_name, props in relation_properties_dict.items():
                for prop_name, prop_type in props.items():
                    prop_key = (prop_name, prop_type)
                    if prop_key not in seen_rel_props:
                        relation_props.append(prop_key)
                        seen_rel_props.add(prop_key)

            logger.info(f"Using user schema: {len(entities)} entity types, {len(relations)} relation types from schema config")
            if entity_props and not disable_properties:
                logger.info(f"Using schema properties: {len(entity_props)} unique entity properties defined")
            if relation_props and not disable_properties:
                logger.info(f"Using schema properties: {len(relation_props)} unique relation properties defined")

            extractor_kwargs = {
                "llm": llm,
                "possible_entities": self._to_literal(entities) if strict_mode else entities,
                "possible_relations": self._to_literal(relations) if strict_mode else relations,
                "strict": strict_mode,
                "num_workers": workers,
                "max_triplets_per_chunk": max_triplets
            }

            # Add entity properties if available (unless disabled)
            if entity_props and not disable_properties:
                extractor_kwargs["possible_entity_props"] = entity_props

            # Add relation properties if available (unless disabled)
            if relation_props and not disable_properties:
                extractor_kwargs["possible_relation_props"] = relation_props

            return SchemaLLMPathExtractor(**extractor_kwargs)
        else:
            # No schema or ontology - use default flexible extraction
            logger.info("No schema or ontology provided - using default flexible extraction")
            return SchemaLLMPathExtractor(
                llm=llm,
                strict=False,
                num_workers=workers,
                max_triplets_per_chunk=max_triplets
            )
