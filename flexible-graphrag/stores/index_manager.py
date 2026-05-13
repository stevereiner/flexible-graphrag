"""
Database setup and index initialisation for Flexible GraphRAG.

Pure functions — no self, no class state.  The facade (HybridSearchSystem)
stores the returned objects as instance attributes and passes them to
downstream callers.
"""

from typing import Tuple, Optional, List
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database / store creation
# ---------------------------------------------------------------------------

def setup_databases(config) -> Tuple:
    """Create vector, graph, and search stores from configuration.

    Args:
        config: AppSettings instance

    Returns:
        (vector_store, graph_store, search_store) — any may be None if disabled
    """
    from factories import DatabaseFactory
    from config import SearchDBType
    from adapters.graph.pg_store_adapter import LC_ONLY_PG_STORES, LI_ONLY_PG_STORES

    # Vector database
    vector_store = DatabaseFactory.create_vector_store(
        config.vector_db,
        config.vector_db_config or {},
        config.llm_provider,
        config.llm_config,
        app_config=config,
    )
    if vector_store is None:
        logger.info("Vector search disabled - system will use only graph and/or fulltext search")

    # Warn when vector and graph backends are the same technology (e.g. both Neo4j).
    # In that configuration LlamaIndex writes text-chunk nodes TWICE per document:
    # once via Neo4jVectorStore (MERGE on :Chunk) and once via Neo4jPropertyGraphStore
    # (MERGE on :__Node__ then SET :Chunk), creating duplicate entries in the vector
    # index.  Use a different backend for VECTOR_DB to avoid this, e.g. Qdrant.
    if vector_store is not None:
        v_type = str(getattr(config, "vector_db", "")).lower()
        g_type = str(getattr(config, "pg_graph_db", "none")).lower()
        if v_type == g_type and v_type not in ("none", ""):
            logger.debug(
                "VECTOR_DB and PG_GRAPH_DB are both '%s' — "
                "text-chunk embeddings will be written by both VectorStoreIndex and "
                "PropertyGraphIndex; query-time deduplication handles the overlap.",
                v_type,
            )

    # Graph database
    graph_backend_str = (getattr(config, "graph_backend", "llamaindex") or "llamaindex").lower()
    db_type_str = str(config.pg_graph_db or "none").lower()

    if db_type_str == "none":
        graph_store = None
        logger.info("Graph search disabled - system will use only vector and/or fulltext search")
    elif (graph_backend_str == "langchain" or db_type_str in LC_ONLY_PG_STORES) and db_type_str not in LI_ONLY_PG_STORES:
        # LangChain adapter is built in _init_adapters; no LI PropertyGraphStore needed.
        # Returning None here lets initialize_indexes skip PropertyGraphIndex creation.
        graph_store = None
        logger.info(
            "LangChain property graph backend: %s (LangChain adapter used for ingestion and retrieval)",
            db_type_str,
        )
    else:
        graph_store = DatabaseFactory.create_graph_store(
            config.pg_graph_db,
            config.graph_db_config or {},
            config.get_active_schema(),
            has_separate_vector_store=(vector_store is not None),
            llm_provider=config.llm_provider,
            llm_config=config.llm_config,
            app_config=config,
        )
        if graph_store is None:
            logger.info("Graph search disabled - system will use only vector and/or fulltext search")

    # Search database
    if config.search_db == SearchDBType.NONE:
        search_store = None
        logger.info("Full-text search disabled - no search store created")
    elif config.search_db == SearchDBType.BM25:
        search_backend = getattr(config, "search_backend", "llamaindex") or "llamaindex"
        if search_backend == "langchain":
            from langchain.search.adapters.bm25_adapter import create_langchain_bm25_adapter
            search_store = create_langchain_bm25_adapter(
                k=getattr(config, "bm25_similarity_top_k", 10),
                persist_dir=getattr(config, "bm25_persist_dir", None),
            )
            logger.info(
                "LangChain BM25SearchAdapter created (persistent=%s)",
                bool(getattr(config, "bm25_persist_dir", None)),
            )
        else:
            from llamaindex.search.adapters.bm25_adapter import LlamaIndexBM25SearchAdapter
            search_store = LlamaIndexBM25SearchAdapter(config={
                "similarity_top_k": getattr(config, "bm25_similarity_top_k", 10),
                "persist_dir": getattr(config, "bm25_persist_dir", None),
            })
            logger.info(
                "LlamaIndex BM25SearchAdapter created (persistent=%s)",
                bool(getattr(config, "bm25_persist_dir", None)),
            )
    else:
        search_store = DatabaseFactory.create_search_store(
            config.search_db,
            config.search_db_config or {},
            config.vector_db,
            config.llm_provider,
            config.llm_config,
            app_config=config,
        )
        if search_store is not None:
            logger.info(f"Using external search engine: {config.search_db}")
        else:
            logger.info("Search store creation skipped (handled by factories.py logic)")

    # Validate at least one modality is enabled
    has_vector = str(config.vector_db) != "none"
    # graph_store may be None for LC-only stores (adapter built in _init_adapters)
    has_graph = str(config.pg_graph_db) != "none"
    has_rdf = str(getattr(config, "rdf_graph_db", "none")) != "none"
    has_search = str(config.search_db) != "none"
    has_langchain_pg = getattr(config, "use_langchain_pg", False)

    if not (has_vector or has_graph or has_rdf or has_search or has_langchain_pg):
        raise ValueError(
            "Invalid configuration: All search modalities are disabled! "
            "At least one of VECTOR_DB, PG_GRAPH_DB, RDF_GRAPH_DB, SEARCH_DB, or "
            "USE_LANGCHAIN_PG must be enabled (not 'none'). "
            f"Current config: VECTOR_DB={config.vector_db}, "
            f"PG_GRAPH_DB={config.pg_graph_db}, RDF_GRAPH_DB={getattr(config, 'rdf_graph_db', 'none')}, "
            f"SEARCH_DB={config.search_db}"
        )

    return vector_store, graph_store, search_store


# ---------------------------------------------------------------------------
# Index initialisation (reconnect to existing data on startup)
# ---------------------------------------------------------------------------

def initialize_indexes(config, vector_store, graph_store, search_store, llm, embed_model) -> Tuple:
    """Create LlamaIndex index objects that reconnect to existing stores.

    Empty node lists are passed so no data is written — only the connection
    to pre-existing data is established.

    Args:
        config: AppSettings instance
        vector_store, graph_store, search_store: store objects from setup_databases
        llm: LlamaIndex LLM instance
        embed_model: LlamaIndex embedding model instance

    Returns:
        (vector_index, graph_index, search_index) — any may be None if disabled
    """
    from llama_index.core import VectorStoreIndex, StorageContext
    from llama_index.core.indices.property_graph import PropertyGraphIndex
    from config import SearchDBType

    logger.info("=== INITIALIZING INDEXES (LlamaIndex) ===")

    # Unwrap adapter objects — LlamaIndex APIs require the raw underlying stores,
    # not our PropertyGraphStoreAdapter / VectorStoreAdapter wrapper classes.
    # Skip unwrapping for LangChain-backed stores — they cannot be used with
    # LlamaIndex VectorStoreIndex (different .add() API).
    _vector_is_lc = hasattr(vector_store, "is_langchain") and vector_store.is_langchain()
    li_vector_store = None if _vector_is_lc else (
        vector_store.get_store() if hasattr(vector_store, "get_store") else vector_store
    )
    li_graph_store = graph_store.get_li_store() if hasattr(graph_store, "get_li_store") else graph_store
    _search_is_lc = hasattr(search_store, "is_langchain") and search_store.is_langchain()
    li_search_store = None if _search_is_lc else (
        search_store.get_store() if hasattr(search_store, "get_store") else search_store
    )

    # Vector index
    if li_vector_store is not None:
        logger.info("Reconnecting to vector store...")
        storage_context = StorageContext.from_defaults(vector_store=li_vector_store)
        vector_index = VectorStoreIndex(
            nodes=[],
            storage_context=storage_context,
            show_progress=False,
        )
        logger.info("  LlamaIndex vector index ready (connected to existing data)")
    else:
        logger.info("LlamaIndex vector index: disabled")
        vector_index = None

    # Graph index
    if li_graph_store is not None and config.enable_knowledge_graph:
        logger.info("Reconnecting to graph store...")
        graph_index = PropertyGraphIndex(
            nodes=[],
            property_graph_store=li_graph_store,
            llm=llm,
            embed_model=embed_model,
            show_progress=False,
        )
        logger.info("  LlamaIndex graph index ready (connected to existing data)")
    else:
        logger.info("LlamaIndex graph index: disabled")
        graph_index = None

    # Search index
    if li_search_store is not None and config.search_db not in [SearchDBType.NONE, SearchDBType.BM25]:
        logger.info("Initializing search store...")
        try:
            search_storage_context = StorageContext.from_defaults(vector_store=li_search_store)
            search_index = VectorStoreIndex([], storage_context=search_storage_context)
            logger.info("  LlamaIndex search index ready (will be created on first ingestion if needed)")
        except Exception as e:
            logger.warning(f"  Could not initialize search index: {e}")
            search_index = None
    else:
        logger.info("LlamaIndex search index: disabled")
        search_index = None

    # BM25 status — separate from the external search index
    _search_db_val = str(getattr(config.search_db, 'value', config.search_db)).lower()
    if _search_db_val == 'bm25':
        _bm25_fw = "LangChain" if (getattr(config, 'search_backend', 'llamaindex') or 'llamaindex').lower() == 'langchain' else 'LlamaIndex'
        logger.info("BM25: %s", _bm25_fw)
    else:
        logger.info("BM25: none")

    logger.info("=== INDEXES READY ===")
    if vector_index and graph_index:
        logger.info("LlamaIndex ready (vector + graph)")
    elif vector_index:
        logger.info("LlamaIndex ready (vector only)")
    elif graph_index:
        logger.info("LlamaIndex ready (graph only)")
    else:
        # LlamaIndex indexes are off — describe what IS active via LangChain
        _active = []
        if str(getattr(config, 'vector_db', 'none')).lower() not in ('none', ''):
            _active.append('vector')
        if str(getattr(config, 'search_db', 'none')).lower() not in ('none', 'bm25', ''):
            _active.append('search')
        if getattr(config, 'use_langchain_pg', False):
            _active.append('property graph')
        if str(getattr(config, 'rdf_graph_db', 'none')).lower() not in ('none', ''):
            _active.append('rdf graph')
        if _active:
            logger.info("System ready (LangChain: %s)", ', '.join(_active))
        else:
            logger.info("System ready (no stores configured)")

    logger.info("Database connections established")
    return vector_index, graph_index, search_index


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def persist_indexes(config, vector_index, graph_index) -> None:
    """Persist indexes to disk if configured in config."""
    if hasattr(config, 'vector_persist_dir') and config.vector_persist_dir and vector_index:
        logger.info(f"Persisting vector index to: {config.vector_persist_dir}")
        vector_index.storage_context.persist(persist_dir=config.vector_persist_dir)

    if hasattr(config, 'graph_persist_dir') and config.graph_persist_dir and graph_index:
        logger.info(f"Persisting graph index to: {config.graph_persist_dir}")
        graph_index.storage_context.persist(persist_dir=config.graph_persist_dir)

    logger.info("Index persistence completed")
