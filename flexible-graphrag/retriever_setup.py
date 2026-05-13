"""
Hybrid retriever assembly for Flexible GraphRAG.

Builds the QueryFusionRetriever (or LangChain EnsembleRetriever when
RETRIEVAL_FUSION=langchain) from all configured search modalities
(vector, BM25, Elasticsearch/OpenSearch, property graph, RDF graph,
LangChain PG) and their per-retriever synonym expansion wrappers.
"""

import logging

logger = logging.getLogger(__name__)


def _to_lc_retriever(retriever):
    """Convert a retriever to an LC BaseRetriever, or return None.

    Uses the ``as_lc_retriever()`` protocol:
    - LC-backed retrievers return a real LC BaseRetriever directly.
    - LoggingRetriever always implements as_lc_retriever(): for LC-backed inners it
      returns LCLoggingRetriever; for LI-native inners it returns LItoLCRetriever(self)
      so RETRIEVAL_FUSION=langchain EnsembleRetriever can consume any retriever.
    - Bare LI-native retrievers with no as_lc_retriever() return None (rare — they're
      always wrapped by LoggingRetriever before reaching this function).
    """
    fn = getattr(retriever, "as_lc_retriever", None)
    if fn is not None:
        return fn()
    return None


def _try_build_lc_ensemble(retrievers) -> "tuple[object, bool]":
    """Try to build a LangChain EnsembleRetriever from *retrievers*.

    Returns ``(ensemble_retriever, success)``.
    ``success=False`` when any retriever is LI-native (can't be converted to LC).
    """
    try:
        from langchain_classic.retrievers.ensemble import EnsembleRetriever
    except ImportError:
        logger.warning(
            "RETRIEVAL_FUSION=langchain: EnsembleRetriever not available "
            "(install langchain-classic). Falling back to LlamaIndex fusion."
        )
        return None, False

    lc_retrievers = []
    for r in retrievers:
        lc_r = _to_lc_retriever(r)
        if lc_r is None:
            label = type(r).__name__
            logger.warning(
                "RETRIEVAL_FUSION=langchain: retriever '%s' has no as_lc_retriever() — "
                "falling back to QueryFusionRetriever", label
            )
            return None, False
        lc_retrievers.append(lc_r)

    n = len(lc_retrievers)
    if n == 0:
        return None, False
    weights = [1.0 / n] * n
    ensemble = EnsembleRetriever(retrievers=lc_retrievers, weights=weights)
    logger.info(
        "RETRIEVAL_FUSION=langchain: EnsembleRetriever built with %d LC retrievers (equal weights)",
        n,
    )
    return ensemble, True


def create_rdf_graph_retriever(config, lc_graph_override=None, source_files=None):
    """Create LangChain-based RDF graph retriever if configured.

    Parameters
    ----------
    lc_graph_override:
        When provided, use this pre-built LangChain graph instead of
        re-building from config (avoids duplicate HTTP connections).
    source_files:
        Optional list of ingested file names to attach to each result node
        for source attribution in the UI.

    Returns
    -------
    TextToGraphQueryRetriever or None
    """
    rdf_store_type = str(getattr(config, "rdf_graph_db", "none"))

    if rdf_store_type == "none":
        logger.debug("RDF graph retrieval not enabled (RDF_GRAPH_DB=none)")
        return None

    try:
        from langchain.graph.retrievers.li_graph_query_retriever import TextToGraphQueryRetriever

        # Fast path: use pre-built LangChain graph from rdf_adapter
        if lc_graph_override is not None:
            logger.info(f"create_rdf_graph_retriever: using lc_graph from rdf_adapter ({rdf_store_type})")
            from langchain.llm.llm_factory import get_langchain_llm as _get_lc_llm
            lc_llm = _get_lc_llm(config)
            return TextToGraphQueryRetriever(
                langchain_graph=lc_graph_override,
                llm=lc_llm,
                source_files=source_files or [],
                config=config,
            )

        if rdf_store_type == "graphdb":
            from langchain.graph.rdf_store_adapters.graphdb_langchain_adapter import GraphDBLangChainAdapter

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

            from rdf.ontology_manager import resolve_user_config_path as _resolve_ontology_path

            if ontology_dir:
                import glob as _glob, os as _os
                _dir = _resolve_ontology_path(ontology_dir)
                ttl_files = sorted(_glob.glob(_os.path.join(_dir, "*.ttl")))
                if ttl_files:
                    ontology_file = ttl_files[0]
            elif ontology_paths:
                first = ontology_paths.split(",")[0].strip()
                if first:
                    ontology_file = _resolve_ontology_path(first)
            elif ontology_path:
                ontology_file = _resolve_ontology_path(ontology_path)

            if ontology_file:
                adapter_config["ontology_file"] = ontology_file
                logger.info("GraphDB LangChain adapter: loading ontology from %s", ontology_file)

            adapter = GraphDBLangChainAdapter(adapter_config)
            lc_graph = adapter.lc_graph
            logger.info("Created GraphDB LangChain adapter for retrieval")

        elif rdf_store_type == "neptune_rdf":
            from langchain.graph.rdf_store_adapters.neptune_rdf_adapter import NeptuneRDFAdapter

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
            from langchain.graph.rdf_store_adapters.fuseki_langchain_adapter import FusekiLangChainAdapter

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
            from langchain.graph.rdf_store_adapters.oxigraph_langchain_adapter import OxigraphLangChainAdapter

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
            source_files=source_files or [],
        )
        logger.info(f"Created LangChain RDF graph retriever for {rdf_store_type}")
        return retriever

    except ImportError as e:
        logger.warning(f"LangChain RDF retrieval not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to create RDF graph retriever: {e}", exc_info=True)
        return None


def create_langchain_pg_retriever(config, source_files=None, lc_graph=None):
    """Delegate to langchain.graph.pg_retriever_factory."""
    from langchain.graph.pg_retriever_factory import build_langchain_pg_retriever
    return build_langchain_pg_retriever(config, source_files=source_files, lc_graph=lc_graph)


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
    from langchain.graph.retrievers.li_logging_retriever import wrap_with_logging
    from langchain.graph.retrievers.synonym_fusion import SynonymFusion

    config = system.config

    logger.info(f"Setting up hybrid retriever - SEARCH_DB={config.search_db}")
    logger.info(
        "Fusion property-graph routing: graph_backend=%s use_langchain_pg=%s "
        "langchain_pg_store_type=%s enable_kg=%s graph_index=%s",
        getattr(config, "graph_backend", None),
        getattr(config, "use_langchain_pg", False),
        getattr(config, "langchain_pg_store_type", None),
        getattr(config, "enable_knowledge_graph", None),
        system.graph_index is not None,
    )
    logger.debug(
        "Fusion inputs: rdf_graph_db=%s langchain_pg_vector_search=%s use_pg_neighborhood=%s",
        getattr(config, "rdf_graph_db", None),
        getattr(config, "langchain_pg_vector_search", False),
        getattr(config, "use_pg_neighborhood", False),
    )

    # Collect the filenames of documents known to this system instance so they can
    # be attached to graph QA result nodes for source attribution in the UI.
    _source_files: list = []
    _last_docs = getattr(system, "_last_ingested_documents", None) or []
    for _d in _last_docs:
        _fn = (getattr(_d, "metadata", None) or {}).get("file_name", "")
        if _fn and _fn not in _source_files:
            _source_files.append(_fn)
    if _source_files:
        logger.debug("Graph retriever source_files: %s", _source_files)

    has_vector = (
        system.vector_index is not None
        or (hasattr(system.vector_store, "is_langchain") and system.vector_store.is_langchain())
    )
    has_graph = config.enable_knowledge_graph and system.graph_index is not None
    has_search = config.search_db != SearchDBType.NONE
    has_langchain_rdf = (str(getattr(config, "rdf_graph_db", "none")) != "none")
    # Reflect the *actual* adapter state rather than the config flag alone.
    _pg_adapter = getattr(system, "pg_adapter", None)
    _pg_adapter_is_lc = (
        _pg_adapter is not None
        and hasattr(_pg_adapter, "is_langchain")
        and _pg_adapter.is_langchain()
    )
    has_langchain_pg = _pg_adapter_is_lc

    if not (has_vector or has_graph or has_search or has_langchain_rdf or has_langchain_pg):
        logger.warning("Cannot setup hybrid retriever: no search modalities available")
        return

    # ---- Vector retriever ----
    vector_retriever = None
    if has_vector:
        try:
            if hasattr(system.vector_store, "is_langchain") and system.vector_store.is_langchain():
                # LangChain vector backend — bypass VectorStoreIndex entirely
                from langchain.vector.li_vector_retriever import LangChainVectorStoreRetriever
                lc_raw_store = system.vector_store.get_store()
                vector_retriever = LangChainVectorStoreRetriever(
                    lc_store=lc_raw_store,
                    top_k=10,
                    store_name=str(config.vector_db),
                )
                logger.info(f"LangChain {config.vector_db} vector retriever created")
            elif system.vector_index is not None:
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

    # ---- FalkorDB native vector fallback ----
    # When GRAPH_DB=falkordb, LANGCHAIN_PG_VECTOR_SEARCH=true, and no external vector
    # store is configured, use FalkorDB's built-in vector index (Chunk nodes).
    # Chunk embeddings are written there during ingest (ingest_lc_graph.py).
    if vector_retriever is None and has_langchain_pg and getattr(config, "langchain_pg_vector_search", False):
        _fk_store_adapter = getattr(
            getattr(system, "pg_adapter", None), "_store_adapter", None
        )
        if _fk_store_adapter is not None and hasattr(_fk_store_adapter, "get_chunk_vector_store"):
            try:
                from langchain.llm.embedding_factory import build_lc_embedding
                from langchain.vector.li_vector_retriever import LangChainVectorStoreRetriever
                _fk_embedding = build_lc_embedding(config)
                _fk_vector_store = _fk_store_adapter.get_chunk_vector_store(_fk_embedding)
                if _fk_vector_store is not None:
                    vector_retriever = LangChainVectorStoreRetriever(
                        lc_store=_fk_vector_store,
                        top_k=10,
                        store_name="falkordb_vector",
                    )
                    logger.info(
                        "FalkorDB native vector retriever created (Chunk nodes in %s db)",
                        getattr(_fk_store_adapter, "config", {}).get("database", "falkor"),
                    )
                else:
                    logger.debug(
                        "FalkorDB chunk vector index not ready yet (ingest first to populate)"
                    )
            except Exception as _fk_vec_err:
                logger.debug("FalkorDB native vector retriever could not be created: %s", _fk_vec_err)
    bm25_retriever = None
    logger.info(f"Checking BM25 condition: search_db={config.search_db}, SearchDBType.BM25={SearchDBType.BM25}")
    if config.search_db == SearchDBType.BM25:
        search_backend = getattr(config, "search_backend", "llamaindex")
        bm25_config = {
            "similarity_top_k": config.bm25_similarity_top_k,
            "persist_dir": config.bm25_persist_dir,
        }

        if search_backend == "langchain":
            # LangChain BM25 — use the persistent BM25SearchAdapter stored on
            # system.search_store (populated cumulatively by update_search.py).
            # This ensures all ingested documents appear in the index, not just
            # the most recent batch.
            from langchain.search.adapters.bm25_adapter import BM25SearchAdapter
            lc_bm25_adapter = None
            if (
                hasattr(system, "search_store")
                and isinstance(system.search_store, BM25SearchAdapter)
            ):
                lc_bm25_adapter = system.search_store
                logger.info(
                    "LangChain BM25: using system.search_store (%d docs)",
                    len(lc_bm25_adapter._documents),
                )
            else:
                logger.error(
                    "LangChain BM25: system.search_store is not a BM25SearchAdapter "
                    "(got %s) — no BM25 retriever available",
                    type(getattr(system, "search_store", None)).__name__,
                )

            if lc_bm25_adapter is not None:
                # Wrap the adapter itself (not a snapshot of its inner retriever) so
                # the fusion always calls get_retriever() fresh after add/delete rebuilds.
                from langchain.search.li_search_retriever import LangChainAdapterDelegatingWrapper
                bm25_retriever = LangChainAdapterDelegatingWrapper(
                    lc_bm25_adapter,
                    top_k=config.bm25_similarity_top_k,
                    label="bm25",
                )
                logger.info(
                    "LangChain BM25 retriever ready (%d docs)",
                    len(lc_bm25_adapter._documents),
                )

        else:
            # LlamaIndex BM25 — use the cumulative LlamaIndexBM25SearchAdapter
            # stored on system.search_store (populated by update_search.py).
            from llamaindex.search.adapters.bm25_adapter import LlamaIndexBM25SearchAdapter
            if isinstance(getattr(system, "search_store", None), LlamaIndexBM25SearchAdapter):
                li_bm25_adapter = system.search_store
                # Fall back to vector_index docstore if adapter is empty (e.g.
                # first query before any ingest, or backend restarted with data
                # still in an external vector store).
                if not li_bm25_adapter._docstore.docs and system.vector_index and system.vector_index.docstore.docs:
                    li_bm25_adapter.add_nodes(list(system.vector_index.docstore.docs.values()))
                    logger.info(
                        "LI BM25: back-filled %d nodes from vector_index docstore",
                        len(li_bm25_adapter._docstore.docs),
                    )
                if li_bm25_adapter._docstore.docs or li_bm25_adapter.get_retriever() is not None:
                    # Use the adapter itself as the retriever — it implements BaseRetriever._retrieve()
                    # which always delegates through get_retriever(), so post-delete rebuilds are picked
                    # up immediately without the fusion holding a stale inner BM25Retriever reference.
                    bm25_retriever = li_bm25_adapter
                    logger.info(
                        "LI BM25 retriever ready (%d docs)", len(li_bm25_adapter._docstore.docs)
                    )
                else:
                    logger.warning("LI BM25: get_retriever() returned None (no documents ingested yet)")
            else:
                # Legacy fallback: rebuild from vector_index docstore (works when
                # VECTOR_DB is configured and accumulates docs across ingestions).
                docstore = None
                if system.vector_index and system.vector_index.docstore.docs:
                    docstore = system.vector_index.docstore
                    logger.info(
                        "LI BM25 (legacy): using vector_index docstore (%d docs)", len(docstore.docs)
                    )
                if docstore:
                    bm25_retriever = DatabaseFactory.create_bm25_retriever(docstore=docstore, config=bm25_config)
                    logger.info("LI BM25 retriever created from vector_index docstore (%d docs)", len(docstore.docs))
                else:
                    logger.error("LI BM25: no docstore available — retriever creation failed")
    else:
        logger.info(f"No BM25 retriever needed for search_db={config.search_db}")

    # ---- LlamaIndex graph retriever ----
    graph_retriever = None
    if has_langchain_pg:
        # LC PG adapter is live — the graph slot is filled by LC retrievers below.
        logger.info(
            "LC PG adapter is active: LangChain TextToGraphQueryRetriever used for property graph retrieval"
        )
        logger.debug("LlamaIndex graph_index present=%s (ignored for fusion graph slot)", system.graph_index is not None)
    elif config.enable_knowledge_graph and system.graph_index:
        graph_retriever = system.graph_index.as_retriever(
            include_text=True,
            similarity_top_k=5,
            include_metadata=True,
        )
        logger.debug("LlamaIndex graph retriever: PropertyGraphIndex.as_retriever similarity_top_k=5")

    # ---- Elasticsearch / OpenSearch search retriever ----
    search_retriever = None
    if system.search_store is not None:
        try:
            if hasattr(system.search_store, "is_langchain") and system.search_store.is_langchain():
                # LangChain search backend — wrap raw LC store directly
                from langchain.vector.li_vector_retriever import LangChainVectorStoreRetriever
                lc_raw_store = system.search_store.get_store()
                search_retriever = LangChainVectorStoreRetriever(
                    lc_store=lc_raw_store,
                    top_k=10,
                    store_name=str(config.search_db),
                )
                logger.info(f"LangChain {config.search_db} search retriever created")
            else:
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
    retriever_frameworks: list = []   # "LC" | "LI" — tracked at creation, not from wrapper attrs

    _vec_is_lc = hasattr(system.vector_store, "is_langchain") and system.vector_store.is_langchain()

    if vector_retriever is not None:
        _vec_syn_tag = "langchain_vector" if _vec_is_lc else "llamaindex_vector"
        retrievers.append(_wrap(_syn.wrap(vector_retriever, _vec_syn_tag), "vector"))
        retriever_types.append("vector")
        retriever_frameworks.append("LC" if _vec_is_lc else "LI")
        logger.info("Added vector retriever to fusion")
    else:
        logger.info("Vector retriever not available")

    if bm25_retriever is not None:
        _bm25_syn_tag = "langchain_search" if getattr(config, "search_backend", "llamaindex") == "langchain" else "llamaindex_search"
        retrievers.append(_wrap(_syn.wrap(bm25_retriever, _bm25_syn_tag), "BM25"))
        retriever_types.append("BM25")
        retriever_frameworks.append("LI")   # LlamaIndex BM25Retriever
        logger.info("Added BM25 retriever to fusion")
    elif search_retriever is not None:
        _search_is_lc = hasattr(system.search_store, "is_langchain") and system.search_store.is_langchain()
        _search_syn_tag = "langchain_search" if _search_is_lc else "llamaindex_search"
        retrievers.append(_wrap(_syn.wrap(search_retriever, _search_syn_tag), str(config.search_db)))
        retriever_types.append(str(config.search_db))
        retriever_frameworks.append("LC" if _search_is_lc else "LI")
        logger.info(f"Added {config.search_db} retriever to fusion")
    else:
        logger.info("No text search retriever available")

    if graph_retriever is not None:
        retrievers.append(_wrap(_syn.wrap(graph_retriever, "llamaindex_pg_graph"), f"graph({config.pg_graph_db})", prescore_graph=True))
        retriever_types.append("graph")
        retriever_frameworks.append("LI")   # LlamaIndex PropertyGraphIndex
        logger.info("Added LlamaIndex property graph retriever to fusion (tag=llamaindex_pg_graph)")
    elif not has_langchain_pg:
        # Only log absence when LC is not handling it
        logger.info(
            "LlamaIndex property graph retriever not in fusion (use_langchain_pg=%s, enable_kg=%s, graph_index=%s)",
            getattr(config, "use_langchain_pg", False),
            getattr(config, "enable_knowledge_graph", False),
            system.graph_index is not None,
        )

    # ---- RDF / LangChain retrievers ----
    # Use rdf_adapter.get_lc_graph() when available (faster — avoids rebuilding connections)
    rdf_lc_graph = None
    rdf_adapter = getattr(system, "rdf_adapter", None)
    if rdf_adapter is not None:
        try:
            rdf_lc_graph = rdf_adapter.get_lc_graph()
        except Exception as _exc:
            logger.debug(f"rdf_adapter.get_lc_graph() failed: {_exc}")
    rdf_retriever = create_rdf_graph_retriever(config, lc_graph_override=rdf_lc_graph, source_files=_source_files)
    if rdf_retriever is not None:
        # Graph QA retrievers must NOT be synonym-expanded: each synonym triggers a full
        # SPARQL-gen + LLM-answer cycle, producing near-duplicate paraphrases of the same
        # underlying data and multiplying latency by N synonyms.
        retrievers.append(_wrap(rdf_retriever, "rdf(langchain)"))
        retriever_types.append("rdf")
        retriever_frameworks.append("LC")   # always LangChain SPARQL chain
        logger.info("Added RDF graph retriever (LangChain) to fusion")
    else:
        logger.info("RDF graph retriever not available")

    # ---- Auto-routing: determine whether to use text-to-query or vector retriever ----
    # For LC backend with vector-capable stores (neo4j, etc.):
    #   primary = GraphEntityVectorRetriever (requires LANGCHAIN_PG_VECTOR_SEARCH=true).
    #   pg_neighborhood k-hop expansion: neo4j only, also requires LANGCHAIN_PG_VECTOR_SEARCH=true.
    #   TextToGraphQueryRetriever (text-to-query) is on by default (USE_LC_TEXT_TO_GRAPH=true).
    # For LC backend WITHOUT vector support (apache_age, hugegraph, nebula, falkordb, etc.) and
    #   all RDF stores: TextToGraphQueryRetriever (text-to-query) is always the graph retriever.
    from adapters.graph.pg_store_adapter import VECTOR_CAPABLE_PG_STORES
    _db_type = str(getattr(config, "pg_graph_db", "none") or "none").lower()
    # Use the actual adapter state (has_langchain_pg) so we don't try to build
    # LC retrievers when the adapter failed and fell back to LlamaIndex.
    _is_lc = has_langchain_pg
    _store_has_vector = _db_type in VECTOR_CAPABLE_PG_STORES
    _text_to_graph_override = getattr(config, "use_lc_text_to_graph", False)
    _pg_vector_enabled = getattr(config, "langchain_pg_vector_search", False)
    _use_pg_neighborhood = getattr(config, "use_pg_neighborhood", False)
    # Auto-enable neighborhood when vector search is on — entity stubs alone are useless for QA;
    # the neighborhood walk is what reaches connected text chunks.
    # Only applies to vector-capable stores (neo4j); skipped if user explicitly set it to false.
    _neighborhood_auto_enabled = False
    if _is_lc and _pg_vector_enabled and _store_has_vector and not _use_pg_neighborhood:
        _use_pg_neighborhood = True
        _neighborhood_auto_enabled = True
        logger.info(
            "Auto-enabled USE_PG_NEIGHBORHOOD: LANGCHAIN_PG_VECTOR_SEARCH=true requires neighborhood "
            "walk to reach text chunks (set USE_PG_NEIGHBORHOOD=true in .env to silence this)"
        )
    # text-to-query routing — LC backend only:
    #   LC non-vector stores (apache_age, hugegraph, nebula, …): ALWAYS required — only option.
    #   LC vector stores (neo4j, …): suppressed — vector+neighborhood handles retrieval.
    #     Enable explicitly with USE_LC_TEXT_TO_GRAPH=true if you want both.
    #   LC vector disabled (LANGCHAIN_PG_VECTOR_SEARCH=false): always enabled.
    #   LI backend: never enabled — LlamaIndex PropertyGraphIndex handles graph retrieval natively.
    _enable_text_to_graph = _is_lc and (not _store_has_vector or not _pg_vector_enabled or _text_to_graph_override)
    # vector: requires LANGCHAIN_PG_VECTOR_SEARCH=true AND LangChain backend — opt-in only.
    _enable_lc_vector = _is_lc and _pg_vector_enabled
    if _pg_vector_enabled and not _is_lc:
        logger.warning(
            "LANGCHAIN_PG_VECTOR_SEARCH=true is ignored: LangChain PG backend is not active "
            "(graph_backend=%s). Entity embeddings are only written by the LangChain ingest path. "
            "Set LANGCHAIN_PG_VECTOR_SEARCH=false to suppress this warning.",
            getattr(config, "graph_backend", "llamaindex"),
        )

    logger.debug(
        "LC graph retriever routing: store=%s is_lc=%s store_has_vector=%s "
        "enable_text_to_graph=%s enable_lc_vector=%s",
        _db_type, _is_lc, _store_has_vector, _enable_text_to_graph, _enable_lc_vector,
    )

    lc_pg_retriever = None
    if _enable_text_to_graph:
        # For embedded stores (Ladybug/Kùzu), reuse the existing lc_graph from the
        # system's pg_adapter to avoid opening a second DB connection to the same file.
        _existing_lc_graph = None
        if hasattr(system, "pg_adapter") and system.pg_adapter is not None:
            if hasattr(system.pg_adapter, "get_lc_graph"):
                _existing_lc_graph = system.pg_adapter.get_lc_graph()
        lc_pg_retriever = create_langchain_pg_retriever(
            config, source_files=_source_files, lc_graph=_existing_lc_graph
        )

    if lc_pg_retriever is not None:
        # Graph QA retrievers must NOT be synonym-expanded (see comment above rdf_retriever).
        retrievers.append(_wrap(lc_pg_retriever, "langchain_pg"))
        retriever_types.append("langchain_pg")
        retriever_frameworks.append("LC")
        logger.info(
            "Added LangChain text-to-query retriever to fusion (store_type=%s)",
            getattr(config, "langchain_pg_store_type", None),
        )
    else:
        if getattr(config, "use_langchain_pg", False) and not _enable_lc_vector:
            logger.warning(
                "use_langchain_pg=true but no graph retriever could be created "
                "(check LANGCHAIN_PG_STORE_TYPE, graph DB credentials, and langchain extras)"
            )
        else:
            logger.debug("LangChain text-to-query retriever not enabled (vector store handles graph retrieval)")

    lc_vec_retriever = None
    if _enable_lc_vector:
        if _db_type == "none":
            logger.debug("LC PG vector retrieval skipped — no graph DB configured")
        else:
            from langchain.graph.pg_retriever_factory import build_langchain_pg_vector_retriever
            lc_vec_retriever = build_langchain_pg_vector_retriever(
                config, embed_model=getattr(system, "embed_model", None)
            )
            if lc_vec_retriever is not None:
                retrievers.append(_wrap(_syn.wrap(lc_vec_retriever, "langchain_pg_vector"), "langchain_pg_vector"))
                retriever_types.append("langchain_pg_vector")
                retriever_frameworks.append("LC")
                logger.info("Added LangChain PG vector retriever to fusion (auto-enabled for %s)", _db_type)
            else:
                logger.warning(
                    "LC PG vector retrieval enabled for %s but retriever could not be built "
                    "(Neo4j requires __Entity__[embedding] index; other stores not yet supported)",
                    _db_type,
                )

    neighborhood_retriever = None
    if _use_pg_neighborhood and has_langchain_pg:
        if _db_type != "neo4j":
            logger.debug(
                "pg_neighborhood only implemented for neo4j (store=%s) — skipping",
                _db_type,
            )
        else:
            from langchain.graph.pg_retriever_factory import build_pg_neighborhood_retriever
            neighborhood_retriever = build_pg_neighborhood_retriever(
                config,
                embed_model=getattr(system, "embed_model", None),
                neo4j_vector=None,
                use_neighborhood=_use_pg_neighborhood,
            )
            if neighborhood_retriever is not None:
                retrievers.append(_wrap(_syn.wrap(neighborhood_retriever, "langchain_pg_neighborhood"), "pg_neighborhood"))
                retriever_types.append("pg_neighborhood")
                retriever_frameworks.append("LC")
                logger.info("Added PG neighborhood retriever to fusion%s", " (auto-enabled)" if _neighborhood_auto_enabled else "")
            else:
                logger.warning("use_pg_neighborhood=true but neighborhood retriever could not be created")

    # Trim synonym scope to only tags that have an active retriever.
    if _syn.tags:
        _active_syn_tags: set = set()
        _syn_tag_map = {
            "vector": "langchain_vector" if _vec_is_lc else "llamaindex_vector",
            "BM25": "llamaindex_search",
            "graph": "llamaindex_pg_graph",
            "langchain_pg_vector": "langchain_pg_vector",
            "pg_neighborhood": "langchain_pg_neighborhood",
        }
        for _rt in retriever_types:
            if _rt in _syn_tag_map:
                _active_syn_tags.add(_syn_tag_map[_rt])
            elif _rt in ("elasticsearch", "opensearch"):
                _search_is_lc = hasattr(system.search_store, "is_langchain") and system.search_store.is_langchain()
                _active_syn_tags.add("langchain_search" if _search_is_lc else "llamaindex_search")
        _syn.restrict_tags(_active_syn_tags)

    # Build per-retriever LC/LI summary using the framework list tracked at creation time.
    _r_labels = [f"{_rt}({_fw})" for _rt, _fw in zip(retriever_types, retriever_frameworks)]
    logger.info("Fusion retriever created with: %s", ", ".join(_r_labels))

    if not retrievers:
        has_any_configured = (
            str(config.vector_db) != "none" or
            str(config.search_db) != "none" or
            (str(config.pg_graph_db) != "none" and config.enable_knowledge_graph) or
            (str(getattr(config, "rdf_graph_db", "none")) != "none") or
            getattr(config, "use_langchain_pg", False)
        )
        if has_any_configured:
            error_msg = (
                f"No retrievers ready yet. Configured: VECTOR_DB={config.vector_db}, "
                f"GRAPH_DB={config.pg_graph_db}, SEARCH_DB={config.search_db}. "
                "Please ingest documents first."
            )
        else:
            error_msg = (
                "No retrievers available for fusion! All search modalities are disabled. "
                f"Current config: VECTOR_DB={config.vector_db}, "
                f"GRAPH_DB={config.pg_graph_db}, SEARCH_DB={config.search_db}. "
                "At least one must be enabled (not 'none')."
            )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Assign to system
    if len(retrievers) == 1:
        system.hybrid_retriever = retrievers[0]
        logger.info(f"Using single {retriever_types[0]} retriever directly (no fusion needed)")
    else:
        fusion = getattr(config, "retrieval_fusion", "llamaindex").lower()
        used_lc_fusion = False
        if fusion == "langchain":
            ensemble, success = _try_build_lc_ensemble(retrievers)
            if success:
                from langchain.search.li_search_retriever import LangChainRetrieverWrapper as _LCWrap
                system.hybrid_retriever = _LCWrap(
                    ensemble, top_k=15, label="lc_ensemble"
                )
                used_lc_fusion = True

        if not used_lc_fusion:
            system.hybrid_retriever = QueryFusionRetriever(
                retrievers=retrievers,
                mode="relative_score",
                similarity_top_k=15,
                num_queries=1,
                use_async=True,
            )
            if fusion == "langchain":
                logger.info(
                    "RETRIEVAL_FUSION=langchain: fell back to LlamaIndex QueryFusionRetriever "
                    "(mixed LI+LC retrievers)"
                )
            else:
                logger.info("Using QueryFusionRetriever for multiple retrievers (async enabled)")

    # Optional synonym exploder — "all" scope: wrap the entire fusion retriever.
    system.hybrid_retriever = _syn.wrap_all(system.hybrid_retriever)
    logger.info("Hybrid retriever setup completed")
