"""LlamaIndex Ladybug property graph adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging
import os

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)


class LlamaIndexLadybugAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by Ladybug (embedded graph DB).

    Configuration keys
    ------------------
    db_dir / db_file         Database path (defaults ``./ladybug/database.lbug``)
    use_vector_index         Enable built-in vector index (default ``True``)
    has_structured_schema    Use a structured relationship schema (default ``False``)
    strict_schema            Enforce strict schema validation (default ``False``)

    Additional kwargs passed to :meth:`__init__`
    --------------------------------------------
    schema_config       Optional dict with ``validation_schema``
    llm_provider        LLM provider for building the embedding model
    llm_config          LLM configuration dict
    app_config          Application-level config object (used for ontology, schema_name, etc.)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        embed_dim: Optional[int] = None,
        schema_config: Optional[Dict[str, Any]] = None,
        llm_provider=None,
        llm_config: Optional[Dict[str, Any]] = None,
        app_config=None,
    ):
        from llama_index.graph_stores.ladybug import LadybugPropertyGraphStore
        import ladybug as lb

        db_dir = config.get("db_dir", "./ladybug")
        db_file = config.get("db_file", "database.lbug")
        db_path = os.path.join(db_dir, db_file)
        use_vector_index = config.get("use_vector_index", True)
        has_structured_schema = config.get("has_structured_schema", False)
        strict_schema = config.get("strict_schema", False)
        os.makedirs(db_dir, exist_ok=True)
        ladybug_db = lb.Database(db_path)

        relationship_schema = self._resolve_schema(
            schema_config, has_structured_schema, app_config,
        )
        if relationship_schema is False:
            has_structured_schema = False
            relationship_schema = None

        embed_model = self._build_embed_model(llm_provider, llm_config, app_config)
        resolved_embed_dim = (
            getattr(embed_model, "embed_dim", None)
            or getattr(embed_model, "dimensions", None)
            or getattr(embed_model, "output_dimensionality", None)
        )
        if resolved_embed_dim is None:
            try:
                test = embed_model.get_text_embedding("hello")
                resolved_embed_dim = len(test)
                logger.info("LlamaIndexLadybugAdapter: detected embed_dim=%s via test", resolved_embed_dim)
            except Exception as exc:
                logger.warning("LlamaIndexLadybugAdapter: could not detect embed_dim: %s", exc)

        logger.info(
            "LlamaIndexLadybugAdapter: path=%s use_vector_index=%s has_structured_schema=%s "
            "strict_schema=%s embed_dim=%s schema_count=%s",
            db_path, use_vector_index, has_structured_schema, strict_schema, resolved_embed_dim,
            len(relationship_schema) if relationship_schema else 0,
        )
        store = LadybugPropertyGraphStore(
            ladybug_db,
            relationship_schema=relationship_schema if has_structured_schema else None,
            has_structured_schema=has_structured_schema,
            strict_schema=strict_schema,
            use_vector_index=use_vector_index,
            embed_model=embed_model,
            embed_dimension=resolved_embed_dim,
        )
        super().__init__(store)

    @staticmethod
    def _resolve_schema(schema_config, has_structured_schema, app_config):
        """Resolve the relationship schema from ontology, schema_config, or defaults.

        Returns the resolved list, ``None`` if none found, or ``False`` to
        signal that ``has_structured_schema`` should be disabled.
        """
        use_ontology = app_config is not None and getattr(app_config, "use_ontology", False)
        if use_ontology:
            try:
                from rdf.api_rdf_enhancements import ontology_manager as _om
                if _om and _om.validation_schema:
                    schema = list(_om.validation_schema)
                    logger.info("LlamaIndexLadybugAdapter: ontology schema (%d triples)", len(schema))
                    return schema
                if _om:
                    entities = list(_om.entities.keys())
                    relations = list(_om.relations.keys())
                    if entities and relations:
                        schema = [(e, r, e2) for r in relations for e in entities for e2 in entities]
                        logger.info("LlamaIndexLadybugAdapter: derived %d schema permutations", len(schema))
                        return schema
                    logger.info("LlamaIndexLadybugAdapter: ontology empty - unstructured mode")
            except (ImportError, AttributeError) as exc:
                logger.debug("LlamaIndexLadybugAdapter: ontology load failed: %s", exc)

        if schema_config and schema_config.get("validation_schema"):
            raw = schema_config["validation_schema"]
            if isinstance(raw, dict) and "relationships" in raw:
                raw = raw["relationships"]
            if isinstance(raw, list):
                schema = [tuple(item) for item in raw if isinstance(item, (list, tuple)) and len(item) == 3]
                logger.info("LlamaIndexLadybugAdapter: schema_config schema (%d triples)", len(schema))
                return schema

        if has_structured_schema:
            schema_name = getattr(app_config, "schema_name", "default") if app_config else "default"
            if schema_name == "default":
                try:
                    from llama_index.core.indices.property_graph.transformations.schema_llm import DEFAULT_VALIDATION_SCHEMA
                    schema = list(DEFAULT_VALIDATION_SCHEMA)
                    logger.info("LlamaIndexLadybugAdapter: built-in LlamaIndex schema (%d triples)", len(schema))
                    return schema
                except ImportError:
                    logger.warning("LlamaIndexLadybugAdapter: DEFAULT_VALIDATION_SCHEMA unavailable - unstructured mode")
                    return False
            else:
                logger.warning("LlamaIndexLadybugAdapter: no schema for schema_name='%s' - unstructured mode", schema_name)
                return False

        return None

    @staticmethod
    def _build_embed_model(llm_provider, llm_config, app_config):
        if llm_provider and llm_config:
            from llamaindex.llm.embedding_factory import create_embedding_model
            model = create_embedding_model(llm_provider, llm_config, settings=app_config)
            provider_name = llm_provider.value if hasattr(llm_provider, "value") else str(llm_provider)
            logger.info("LlamaIndexLadybugAdapter: embedding model provider=%s", provider_name)
            return model
        from llama_index.embeddings.openai import OpenAIEmbedding
        logger.warning("LlamaIndexLadybugAdapter: no LLM provider — falling back to OpenAI embeddings")
        return OpenAIEmbedding(model_name="text-embedding-3-small")


__all__ = ["LlamaIndexLadybugAdapter"]
