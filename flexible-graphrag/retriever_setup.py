"""
Hybrid retriever assembly for Flexible GraphRAG.

Builds the QueryFusionRetriever from all configured search modalities
(vector, BM25, Elasticsearch/OpenSearch, property graph, RDF graph,
LangChain PG) and their per-retriever synonym expansion wrappers.
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RDF / LangChain retriever helpers (extracted from HybridSearchSystem)
# ---------------------------------------------------------------------------

def create_rdf_graph_retriever(config):
    """Create LangChain-based RDF graph retriever if configured.

    Returns:
        TextToGraphQueryRetriever or None
    """
    use_langchain_rdf = getattr(config, "use_langchain_rdf", False)
    rdf_store_type = getattr(config, "rdf_store_type", None)

    if not use_langchain_rdf or not rdf_store_type:
        logger.debug("RDF graph retrieval not enabled")
        return None

    try:
        from langchain.graph.langchain_retriever_wrapper import TextToGraphQueryRetriever

        if rdf_store_type == "graphdb":
            from langchain.graph.langchain_adapters.graphdb_langchain_adapter import GraphDBLangChainAdapter

            adapter_config = {
                "base_url": getattr(config, "graphdb_base_url", "http://localhost:7200"),
                "repository": getattr(config, "graphdb_repository", "flexible-graphrag"),
                "username": getattr(config, "graphdb_username", "admin"),
                "password": getattr(config, "graphdb_password", "admin"),
            }

            # Resolve ontology file for schema loading — prefer local files over
            # querying GraphDB (avoids "Missing graph in results" when ontology is
            # only in a named graph, not the default graph).
            ontology_file = None
            ontology_dir = getattr(config, "ontology_dir", None)
            ontology_paths = getattr(config, "ontology_paths", None)
            ontology_path = getattr(config, "ontology_path", None)

            if ontology_dir:
                import glob as _glob, os as _os
                ttl_files = sorted(_glob.glob(_os.path.join(ontology_dir, "*.ttl")))
                if ttl_files:
                    ontology_file = ttl_files[0]
            elif ontology_paths:
                first = ontology_paths.split(",")[0].strip()
                if first:
                    ontology_file = first
            elif ontology_path:
                ontology_file = ontology_path

            if ontology_file:
                adapter_config["ontology_file"] = ontology_file
                logger.info("GraphDB LangChain adapter: loading ontology from %s", ontology_file)

            adapter = GraphDBLangChainAdapter(adapter_config)
            lc_graph = adapter.lc_graph
            logger.info("Created GraphDB LangChain adapter for retrieval")

        elif rdf_store_type == "neptune_rdf":
            from langchain.graph.langchain_adapters.neptune_rdf_adapter import NeptuneRDFAdapter

            adapter_config = {
                "host": getattr(config, "neptune_host", None),
                "port": getattr(config, "neptune_port", 8182),
                "region": getattr(config, "neptune_region", "us-east-1"),
                "use_iam_auth": getattr(config, "neptune_use_iam_auth", False),
                "use_https": getattr(config, "neptune_use_https", True),
            }
            adapter = NeptuneRDFAdapter(adapter_config)
            lc_graph = adapter.lc_graph
            logger.info("Created Neptune RDF LangChain adapter for retrieval")

        elif rdf_store_type == "fuseki":
            from langchain.graph.langchain_adapters.fuseki_langchain_adapter import FusekiLangChainAdapter

            adapter_config = {
                "base_url": getattr(config, "fuseki_base_url", "http://localhost:3030"),
                "dataset": getattr(config, "fuseki_dataset", "flexible-graphrag"),
            }
            fuseki_user = getattr(config, "fuseki_username", None)
            fuseki_pass = getattr(config, "fuseki_password", None)
            if fuseki_user:
                adapter_config["username"] = fuseki_user
            if fuseki_pass:
                adapter_config["password"] = fuseki_pass

            adapter = FusekiLangChainAdapter(adapter_config)
            lc_graph = adapter.lc_graph
            logger.info("Created Fuseki LangChain adapter for retrieval")

        elif rdf_store_type == "oxigraph":
            from langchain.graph.langchain_adapters.oxigraph_langchain_adapter import OxigraphLangChainAdapter

            oxigraph_url = getattr(config, "oxigraph_url", None) or "http://localhost:7878"
            adapter_config = {"url": oxigraph_url}
            adapter = OxigraphLangChainAdapter(adapter_config)
            lc_graph = adapter.lc_graph
            logger.info("Created Oxigraph LangChain adapter for retrieval")

        else:
            logger.warning(f"Unsupported RDF store type for LangChain retrieval: {rdf_store_type}")
            return None

        retriever = TextToGraphQueryRetriever(
            langchain_graph=lc_graph,
            llm=get_langchain_llm(config),
            top_k=getattr(config, "rdf_retrieval_top_k", 5),
            include_intermediate_steps=True,
        )
        logger.info(f"Created LangChain RDF graph retriever for {rdf_store_type}")
        return retriever

    except ImportError as e:
        logger.warning(f"LangChain RDF retrieval not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to create RDF graph retriever: {e}", exc_info=True)
        return None


def create_langchain_pg_retriever(config):
    """Delegate to langchain.graph.pg_retriever_factory."""
    from langchain.graph.pg_retriever_factory import build_langchain_pg_retriever
    return build_langchain_pg_retriever(config)


def get_langchain_llm(config):
    """Delegate to langchain.llm.llm_factory."""
    from langchain.llm.llm_factory import get_langchain_llm as _get
    return _get(config)


# ---------------------------------------------------------------------------
# Main hybrid retriever builder
# ---------------------------------------------------------------------------

def setup_hybrid_retriever(system) -> None:
    """Assemble and assign system.hybrid_retriever from all configured modalities.

    Reads from system: config, vector_index, graph_index, embed_model,
    vector_store, search_store, search_index, llm, _last_ingested_documents.
    Writes: system.hybrid_retriever.

    Args:
        system: HybridSearchSystem instance
    """
    from llama_index.core.retrievers import QueryFusionRetriever
    from factories import DatabaseFactory
    from config import SearchDBType, VectorDBType
    from langchain.graph.logging_retriever import wrap_with_logging
    from langchain.graph.synonym_fusion import SynonymFusion

    config = system.config

    logger.info(f"Setting up hybrid retriever - SEARCH_DB={config.search_db}")

    has_vector = system.vector_index is not None
    has_graph = config.enable_knowledge_graph and system.graph_index is not None
    has_search = config.search_db != SearchDBType.NONE
    has_langchain_rdf = getattr(config, "use_langchain_rdf", False)
    has_langchain_pg = getattr(config, "use_langchain_pg", False)

    if not (has_vector or has_graph or has_search or has_langchain_rdf or has_langchain_pg):
        logger.warning("Cannot setup hybrid retriever: no search modalities available")
        return

    # ---- Vector retriever ----
    vector_retriever = None
    if has_vector:
        try:
            if system.vector_index is not None:
                if config.vector_db == VectorDBType.OPENSEARCH:
                    from llama_index.core.vector_stores.types import VectorStoreQueryMode
                    vector_retriever = system.vector_index.as_retriever(
                        similarity_top_k=10,
                        embed_model=system.embed_model,
                        vector_store_query_mode=VectorStoreQueryMode.DEFAULT,
                    )
                    logger.info("OpenSearch vector retriever created with DEFAULT mode")
                else:
                    vector_retriever = system.vector_index.as_retriever(
                        similarity_top_k=10,
                        embed_model=system.embed_model,
                    )
                    logger.info(f"{config.vector_db} vector retriever created")
        except Exception as check_error:
            logger.warning(f"Could not create vector retriever: {check_error}")
    else:
        logger.info("Vector search disabled - no vector retriever")

    # ---- BM25 retriever ----
    bm25_retriever = None
    logger.info(f"Checking BM25 condition: search_db={config.search_db}, SearchDBType.BM25={SearchDBType.BM25}")
    if config.search_db == SearchDBType.BM25:
        bm25_config = {
            "similarity_top_k": config.bm25_similarity_top_k,
            "persist_dir": config.bm25_persist_dir,
        }
        docstore = None
        if system.vector_index and system.vector_index.docstore.docs:
            docstore = system.vector_index.docstore
            logger.info(f"Creating BM25 retriever with {len(docstore.docs)} documents from vector index")
        elif hasattr(system, '_last_ingested_documents') and system._last_ingested_documents:
            from llama_index.core.storage.docstore import SimpleDocumentStore
            docstore = SimpleDocumentStore()
            docstore.add_documents(system._last_ingested_documents)
            logger.info(f"Created standalone docstore with {len(system._last_ingested_documents)} documents for BM25")
            for doc_id, doc in docstore.docs.items():
                content_preview = doc.text[:100] + "..." if len(doc.text) > 100 else doc.text
                logger.info(f"Doc {doc_id}: {content_preview}")
                logger.info(f"Doc {doc_id} metadata: {doc.metadata}")
        elif hasattr(system, '_last_ingested_documents'):
            logger.warning(f"_last_ingested_documents exists but is empty: {system._last_ingested_documents}")
        else:
            logger.warning("_last_ingested_documents attribute not found - documents not stored during ingestion")

        if docstore:
            bm25_retriever = DatabaseFactory.create_bm25_retriever(docstore=docstore, config=bm25_config)
            logger.info(f"Built-in BM25 retriever created successfully with {len(docstore.docs)} documents")
        else:
            logger.error("No docstore available - BM25 retriever creation failed")
    else:
        logger.info(f"No BM25 retriever needed for search_db={config.search_db}")

    # ---- LlamaIndex graph retriever ----
    graph_retriever = None
    if getattr(config, "use_langchain_pg", False):
        logger.info("use_langchain_pg=true: skipping LlamaIndex graph_index retriever")
    elif config.enable_knowledge_graph and system.graph_index:
        graph_retriever = system.graph_index.as_retriever(
            include_text=True,
            similarity_top_k=5,
            include_metadata=True,
        )

    # ---- Elasticsearch / OpenSearch search retriever ----
    search_retriever = None
    if system.search_store is not None:
        try:
            search_index = getattr(system, 'search_index', None)
            if search_index is None:
                logger.info("Search index not yet initialised - skipping retriever (will be available after first ingestion)")
            else:
                if config.search_db == SearchDBType.OPENSEARCH:
                    from llama_index.core.vector_stores.types import VectorStoreQueryMode
                    search_retriever = search_index.as_retriever(
                        similarity_top_k=10,
                        vector_store_query_mode=VectorStoreQueryMode.TEXT_SEARCH,
                    )
                    logger.info("Created OpenSearch retriever with TEXT_SEARCH mode")
                else:
                    search_retriever = search_index.as_retriever(similarity_top_k=10)
                    logger.info(f"Created {config.search_db} retriever")
        except Exception as e:
            logger.warning(f"Failed to create {config.search_db} retriever: {e} - continuing without it")

    # ---- Per-retriever logging + synonym expansion ----
    def _wrap(retriever, label, prescore_graph: bool = False):
        return wrap_with_logging(retriever, label, prescore_graph=prescore_graph)

    _syn = SynonymFusion.from_config(config, getattr(system, "llm", None))

    retrievers = []
    retriever_types = []

    if vector_retriever is not None:
        retrievers.append(_wrap(_syn.wrap(vector_retriever, "llamaindex_vector"), "vector"))
        retriever_types.append("vector")
        logger.info("Added vector retriever to fusion")
    else:
        logger.info("Vector retriever not available")

    if bm25_retriever is not None:
        retrievers.append(_wrap(_syn.wrap(bm25_retriever, "llamaindex_search"), "BM25"))
        retriever_types.append("BM25")
        logger.info("Added BM25 retriever to fusion")
    elif search_retriever is not None:
        retrievers.append(_wrap(_syn.wrap(search_retriever, "llamaindex_search"), str(config.search_db)))
        retriever_types.append(str(config.search_db))
        logger.info(f"Added {config.search_db} retriever to fusion")
    else:
        logger.info("No text search retriever available")

    if graph_retriever is not None:
        retrievers.append(_wrap(_syn.wrap(graph_retriever, "llamaindex_pg_graph"), f"graph({config.graph_db})", prescore_graph=True))
        retriever_types.append("graph")
        logger.info("Added graph retriever to fusion")
    else:
        logger.info("Graph retriever not available")

    # ---- RDF / LangChain retrievers ----
    rdf_retriever = create_rdf_graph_retriever(config)
    if rdf_retriever is not None:
        retrievers.append(_wrap(_syn.wrap(rdf_retriever, "langchain_rdf_graph"), "rdf(langchain)"))
        retriever_types.append("rdf")
        logger.info("Added RDF graph retriever (LangChain) to fusion")
    else:
        logger.info("RDF graph retriever not available")

    lc_pg_retriever = create_langchain_pg_retriever(config)
    if lc_pg_retriever is not None:
        retrievers.append(_wrap(_syn.wrap(lc_pg_retriever, "langchain_pg_graph"), "langchain_pg"))
        retriever_types.append("langchain_pg")
        logger.info("Added LangChain property graph retriever to fusion")
    else:
        if getattr(config, "use_langchain_pg", False):
            logger.warning("use_langchain_pg=true but LangChain PG retriever could not be created")

    lc_vec_retriever = None
    if getattr(config, "langchain_pg_vector_search", False):
        from langchain.graph.pg_retriever_factory import build_langchain_pg_vector_retriever
        lc_vec_retriever = build_langchain_pg_vector_retriever(
            config, embed_model=getattr(system, "embed_model", None)
        )
        if lc_vec_retriever is not None:
            retrievers.append(_wrap(_syn.wrap(lc_vec_retriever, "langchain_pg_vector"), "langchain_pg_vector"))
            retriever_types.append("langchain_pg_vector")
            logger.info("Added LangChain PG vector retriever to fusion")
        else:
            logger.warning("langchain_pg_vector_search=true but vector retriever could not be created")

    neighborhood_retriever = None
    if getattr(config, "use_pg_neighborhood", False):
        from langchain.graph.pg_retriever_factory import build_pg_neighborhood_retriever
        neighborhood_retriever = build_pg_neighborhood_retriever(
            config,
            embed_model=getattr(system, "embed_model", None),
            neo4j_vector=None,
        )
        if neighborhood_retriever is not None:
            retrievers.append(_wrap(_syn.wrap(neighborhood_retriever, "langchain_pg_neighborhood"), "pg_neighborhood"))
            retriever_types.append("pg_neighborhood")
            logger.info("Added PG neighborhood retriever to fusion")
        else:
            logger.warning("use_pg_neighborhood=true but neighborhood retriever could not be created")

    logger.info(f"Fusion retriever created with {', '.join(retriever_types)} retrievers")

    if not retrievers:
        has_any_configured = (
            str(config.vector_db) != "none" or
            str(config.search_db) != "none" or
            (str(config.graph_db) != "none" and config.enable_knowledge_graph) or
            getattr(config, "use_langchain_rdf", False) or
            getattr(config, "use_langchain_pg", False)
        )
        if has_any_configured:
            error_msg = (
                f"No retrievers ready yet. Configured: VECTOR_DB={config.vector_db}, "
                f"GRAPH_DB={config.graph_db}, SEARCH_DB={config.search_db}. "
                "Please ingest documents first."
            )
        else:
            error_msg = (
                "No retrievers available for fusion! All search modalities are disabled. "
                f"Current config: VECTOR_DB={config.vector_db}, "
                f"GRAPH_DB={config.graph_db}, SEARCH_DB={config.search_db}. "
                "At least one must be enabled (not 'none')."
            )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Assign to system
    if len(retrievers) == 1:
        system.hybrid_retriever = retrievers[0]
        logger.info(f"Using single {retriever_types[0]} retriever directly (no fusion needed)")
    else:
        system.hybrid_retriever = QueryFusionRetriever(
            retrievers=retrievers,
            mode="relative_score",
            similarity_top_k=15,
            num_queries=1,
            use_async=True,
        )
        logger.info("Using QueryFusionRetriever for multiple retrievers (async enabled)")

    # Optional synonym exploder — "all" scope: wrap the entire fusion retriever.
    system.hybrid_retriever = _syn.wrap_all(system.hybrid_retriever)
    logger.info("Hybrid retriever setup completed")
