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

    # Graph database
    graph_store = DatabaseFactory.create_graph_store(
        config.graph_db,
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
        search_store = None
        logger.info("Using BM25 retriever for full-text search (no external search engine required)")
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
    has_graph = str(config.graph_db) != "none"
    has_search = str(config.search_db) != "none"
    has_langchain_rdf = getattr(config, "use_langchain_rdf", False)
    has_langchain_pg = getattr(config, "use_langchain_pg", False)

    if not (has_vector or has_graph or has_search or has_langchain_rdf or has_langchain_pg):
        raise ValueError(
            "Invalid configuration: All search modalities are disabled! "
            "At least one of VECTOR_DB, GRAPH_DB, SEARCH_DB, USE_LANGCHAIN_RDF, or "
            "USE_LANGCHAIN_PG must be enabled (not 'none'). "
            f"Current config: VECTOR_DB={config.vector_db}, "
            f"GRAPH_DB={config.graph_db}, SEARCH_DB={config.search_db}"
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

    logger.info("=== INITIALIZING INDEXES ===")

    # Vector index
    if vector_store is not None:
        logger.info("Reconnecting to vector store...")
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        vector_index = VectorStoreIndex(
            nodes=[],
            storage_context=storage_context,
            show_progress=False,
        )
        logger.info("  Vector index ready (connected to existing data)")
    else:
        logger.info("Vector index disabled")
        vector_index = None

    # Graph index
    if graph_store is not None and config.enable_knowledge_graph:
        logger.info("Reconnecting to graph store...")
        graph_index = PropertyGraphIndex(
            nodes=[],
            property_graph_store=graph_store,
            llm=llm,
            embed_model=embed_model,
            show_progress=False,
        )
        logger.info("  Graph index ready (connected to existing data)")
    else:
        logger.info("Graph index disabled")
        graph_index = None

    # Search index
    if search_store is not None and config.search_db not in [SearchDBType.NONE, SearchDBType.BM25]:
        logger.info("Initializing search store...")
        try:
            search_storage_context = StorageContext.from_defaults(vector_store=search_store)
            search_index = VectorStoreIndex([], storage_context=search_storage_context)
            logger.info("  Search index ready (will be created on first ingestion if needed)")
        except Exception as e:
            logger.warning(f"  Could not initialize search index: {e}")
            search_index = None
    else:
        logger.info("Search index disabled or using BM25 (no external store)")
        search_index = None

    logger.info("=== INDEXES READY ===")
    if vector_index and graph_index:
        logger.info("System ready for search (vector + graph)")
    elif vector_index:
        logger.info("System ready for search (vector only)")
    elif graph_index:
        logger.info("System ready for search (graph only)")
    else:
        logger.info("System ready (search-only mode)")

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


# ---------------------------------------------------------------------------
# RDF store helpers
# ---------------------------------------------------------------------------

def export_nodes_to_rdf_stores(nodes: List, config, schema_manager=None) -> None:
    """Push extracted KG nodes/relations to all enabled RDF stores.

    Called after run_kg_extractors_on_nodes() when ingestion_storage_mode
    is 'rdf_only' or 'both'.
    """
    from rdf.kg_to_rdf_converter import convert_nodes_to_rdf, DEFAULT_BASE_NS, DEFAULT_ONTO_NS
    from rdf.store.rdf_store_factory import RDFStoreFactory

    rdf_store_configs = config.get_rdf_store_configs()
    if not rdf_store_configs:
        logger.warning(
            "ingestion_storage_mode requires RDF stores but none are configured. "
            "Set FUSEKI_ENABLED, GRAPHDB_ENABLED, or OXIGRAPH_ENABLED."
        )
        return

    onto_ns = DEFAULT_ONTO_NS
    ontology_manager = None
    if schema_manager is not None:
        try:
            ontology_manager = schema_manager.ontology_manager
            if ontology_manager:
                iri = getattr(ontology_manager, "ontology_iri", None)
                if iri:
                    onto_ns = iri.rstrip("#/") + "#"
        except Exception:
            pass

    base_ns = getattr(config, "rdf_base_namespace", DEFAULT_BASE_NS)
    graph_uri = base_ns.rstrip("/")
    annotation_syntax = config.rdf_annotation_syntax

    logger.info("Converting extracted KG to RDF (annotation_syntax=%s)...", annotation_syntax)
    rdf_graph, turtle_annotated = convert_nodes_to_rdf(
        nodes,
        base_ns=base_ns,
        onto_ns=onto_ns,
        ontology_manager=ontology_manager,
        annotation_syntax=annotation_syntax,
    )
    logger.info("RDF graph built: %d triples", len(rdf_graph))

    for store_cfg in rdf_store_configs:
        store_name = store_cfg.get("name", "unknown")
        store_type = store_cfg.get("type", store_name)
        try:
            adapter = RDFStoreFactory.create(store_type, store_cfg.get("config", {}))
            adapter.store_rdf_annotations(turtle_annotated, graph_uri=graph_uri)
            logger.info("Exported KG to RDF store '%s' (%s)", store_name, store_type)
        except Exception as e:
            logger.error(
                "Failed to export KG to RDF store '%s': %s", store_name, e, exc_info=True
            )


def delete_from_rdf_stores(ref_doc_id: str, config) -> None:
    """Delete all triples for ref_doc_id from every configured RDF store.

    Errors are logged but never raised so a failed RDF delete never blocks
    the rest of the delete cycle.
    """
    storage_mode = getattr(config, "ingestion_storage_mode", "property_graph")
    if storage_mode not in ("rdf_only", "both"):
        return

    from rdf.store.rdf_store_factory import RDFStoreFactory
    from rdf.kg_to_rdf_converter import DEFAULT_BASE_NS

    rdf_store_configs = config.get_rdf_store_configs()
    if not rdf_store_configs:
        return

    graph_uri = DEFAULT_BASE_NS.rstrip("/")
    for store_cfg in rdf_store_configs:
        store_name = store_cfg.get("name", "unknown")
        store_type = store_cfg.get("type", store_name)
        try:
            adapter = RDFStoreFactory.create(store_type, store_cfg.get("config", {}))
            adapter.delete_doc(ref_doc_id, graph_uri=graph_uri)
            logger.info(
                "Deleted RDF triples for doc '%s' from store '%s'",
                ref_doc_id, store_name,
            )
        except Exception as e:
            logger.warning(
                "Failed to delete RDF triples for doc '%s' from store '%s': %s",
                ref_doc_id, store_name, e,
            )
