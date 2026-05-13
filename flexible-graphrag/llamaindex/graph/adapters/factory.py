"""llamaindex.graph.adapters.factory — dispatch to per-backend adapter classes."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from config import PropertyGraphType, LLMProvider

logger = logging.getLogger(__name__)


def create_graph_store(
    db_type: PropertyGraphType,
    config: Dict[str, Any],
    schema_config: Optional[Dict[str, Any]] = None,
    has_separate_vector_store: bool = False,
    llm_provider: LLMProvider = None,
    llm_config: Optional[Dict[str, Any]] = None,
    app_config=None,
):
    """Instantiate the right :class:`LlamaIndexPGAdapter` subclass for *db_type*
    and return it. Returns ``None`` for ``PropertyGraphType.NONE``."""
    from llamaindex.llm.embedding_factory import get_embedding_dimension

    if db_type == PropertyGraphType.NONE:
        logger.info("Graph search disabled - no graph store created")
        return None

    embedding_kind = getattr(app_config, "embedding_kind", None) if app_config else None
    embedding_model = getattr(app_config, "embedding_model", None) if app_config else None
    embedding_dimension = getattr(app_config, "embedding_dimension", None) if app_config else None
    embed_dim = get_embedding_dimension(
        embedding_kind=embedding_kind,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
    )

    logger.info("Creating graph store with type: %s", db_type)

    if db_type == PropertyGraphType.NEO4J:
        from llamaindex.graph.adapters.neo4j_adapter import LlamaIndexNeo4jGraphAdapter
        return LlamaIndexNeo4jGraphAdapter(config, embed_dim)

    if db_type == PropertyGraphType.LADYBUG:
        from llamaindex.graph.adapters.ladybug_adapter import LlamaIndexLadybugAdapter
        return LlamaIndexLadybugAdapter(
            config, embed_dim,
            schema_config=schema_config,
            llm_provider=llm_provider,
            llm_config=llm_config,
            app_config=app_config,
        )

    if db_type == PropertyGraphType.FALKORDB:
        from llamaindex.graph.adapters.falkordb_adapter import LlamaIndexFalkorDBAdapter
        return LlamaIndexFalkorDBAdapter(config, embed_dim)

    if db_type == PropertyGraphType.ARCADEDB:
        from llamaindex.graph.adapters.arcadedb_adapter import LlamaIndexArcadeDBAdapter
        return LlamaIndexArcadeDBAdapter(config, embed_dim)

    if db_type == PropertyGraphType.MEMGRAPH:
        from llamaindex.graph.adapters.memgraph_adapter import LlamaIndexMemgraphAdapter
        return LlamaIndexMemgraphAdapter(config, embed_dim)

    if db_type == PropertyGraphType.NEBULA:
        from llamaindex.graph.adapters.nebula_adapter import LlamaIndexNebulaAdapter
        return LlamaIndexNebulaAdapter(config, embed_dim)

    if db_type == PropertyGraphType.NEPTUNE:
        from llamaindex.graph.adapters.neptune_adapter import LlamaIndexNeptuneAdapter
        return LlamaIndexNeptuneAdapter(config, embed_dim)

    if db_type == PropertyGraphType.NEPTUNE_ANALYTICS:
        from llamaindex.graph.adapters.neptune_analytics_adapter import LlamaIndexNeptuneAnalyticsAdapter
        return LlamaIndexNeptuneAnalyticsAdapter(config, embed_dim)

    if db_type == PropertyGraphType.SPANNER:
        from llamaindex.graph.adapters.spanner_adapter import LlamaIndexSpannerAdapter
        return LlamaIndexSpannerAdapter(config, embed_dim)

    raise ValueError(f"Unsupported graph database: {db_type}")
