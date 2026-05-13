"""ingest.ingest_lc_graph — LangChain-native KG ingestion.

Called when ``GRAPH_BACKEND=langchain`` (or an LC-only store type is configured).
Uses ``LLMGraphTransformer`` for extraction and ``add_graph_documents`` for
writing to the LangChain property graph.

Entry points
------------
``ingest_lc_graph(system, nodes, documents)``
    Sync wrapper (runs the async path via ``asyncio.run``).

``aingest_lc_graph(system, nodes, documents)``
    Async path — preferred when the caller is already async.
    Returns total elapsed seconds (float) for performance logging.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hybrid_system import HybridSearchSystem

logger = logging.getLogger(__name__)


async def aingest_lc_graph(
    system: "HybridSearchSystem",
    nodes: List,
    documents: Optional[List] = None,
    schema_manager=None,
    lc_docs: Optional[List] = None,
) -> tuple:
    """Extract KG via LLMGraphTransformer and write to the LangChain graph store.

    Parameters
    ----------
    system:
        Live ``HybridSearchSystem`` instance — provides config, pg_adapter, and LLM.
    nodes:
        LlamaIndex ``TextNode`` / ``Document`` objects produced by the chunker.
        These are converted to LangChain ``Document`` objects before extraction.
        Ignored when *lc_docs* is provided (avoids double conversion).
    documents:
        Optional raw source documents (not used for extraction; reserved for future
        provenance metadata enrichment).
    schema_manager:
        Optional ``SchemaManager`` that holds an ``OntologyManager`` for ontology-
        guided extraction (``allowed_nodes`` / ``allowed_relationships``).
    lc_docs:
        Optional pre-split ``List[LCDocument]`` from the full-LC pipeline
        (``system._last_lc_chunks``).  When provided these are passed directly to
        the extractor, skipping the internal LI->LC conversion.  This is set
        automatically when ``CHUNKER_BACKEND=langchain``.

    Returns
    -------
    tuple[float, float]
        ``(total_seconds, extract_seconds)`` — total elapsed time (extract + write)
        and the KG extraction portion alone, for separate performance logging by the caller.
    """
    t_start = time.time()
    config = system.config

    # Verify the adapter is actually LC-backed
    pg_adapter = system.pg_adapter
    if pg_adapter is None or not pg_adapter.is_langchain():
        logger.warning(
            "aingest_lc_graph called but pg_adapter is not a LangChain adapter "
            "(is_langchain=%s). Skipping LC ingestion.",
            pg_adapter.is_langchain() if pg_adapter else "None",
        )
        return 0.0, 0.0

    lc_graph = pg_adapter.get_lc_graph()
    if lc_graph is None:
        logger.warning("aingest_lc_graph: lc_graph is None — graph store not connected. Skipping.")
        return 0.0, 0.0

    # Ensure the vector index DDL exists before we write any nodes.
    # Only Neo4j supports the `CREATE VECTOR INDEX` Cypher syntax used here.
    _is_neo4j_graph = "Neo4j" in type(lc_graph).__name__
    if _is_neo4j_graph and getattr(config, "langchain_pg_vector_search", False):
        _ensure_lc_vector_index_ddl(lc_graph, config)

    if not nodes and not lc_docs:
        logger.info("aingest_lc_graph: no nodes to process, skipping")
        return 0.0, 0.0

    # Resolve which input docs the extractor will process.
    # lc_docs (from CHUNKER_BACKEND=langchain) avoids LI->LC round-trip inside aextract.
    _extractor_input = lc_docs if lc_docs is not None else nodes
    _input_label = f"lc_docs={len(lc_docs)}" if lc_docs is not None else f"li_nodes={len(nodes)}"

    # Build LangChain LLM
    lc_llm = _get_lc_llm(config)
    if lc_llm is None:
        logger.error(
            "aingest_lc_graph: could not obtain a LangChain LLM for provider=%s. "
            "LC graph ingestion skipped.",
            getattr(config, "llm_provider", "unknown"),
        )
        return 0.0

    # Resolve ontology manager
    ontology_manager = _get_ontology_manager(config, schema_manager)
    use_ontology = bool(getattr(config, "use_ontology", False) and ontology_manager is not None)

    # Build the KG extractor adapter
    try:
        from langchain.process.kg_extractor_adapter import LangChainKGExtractorAdapter
    except ImportError as exc:
        logger.error("LangChainKGExtractorAdapter not available: %s. Install langchain-experimental.", exc)
        return

    disable_properties = getattr(config, "disable_properties", False)
    node_properties: List[str] = []
    rel_properties: List[str] = []
    if not disable_properties and ontology_manager is not None and use_ontology:
        try:
            seen: set = set()
            for entity in ontology_manager.entities.values():
                for prop_name in (entity.properties or {}):
                    if prop_name not in seen:
                        node_properties.append(prop_name)
                        seen.add(prop_name)
            seen_rel: set = set()
            for relation in ontology_manager.relations.values():
                for prop_name in (relation.properties or {}):
                    if prop_name not in seen_rel:
                        rel_properties.append(prop_name)
                        seen_rel.add(prop_name)
        except Exception as exc:
            logger.debug("Could not read ontology properties: %s", exc)

    strict_mode = bool(getattr(config, "strict_schema_validation", False))

    extractor = LangChainKGExtractorAdapter(
        lc_llm=lc_llm,
        ontology_manager=ontology_manager,
        use_ontology=use_ontology,
        node_properties=node_properties,
        relationship_properties=rel_properties,
        strict_mode=strict_mode,
    )

    # Extract GraphDocuments
    logger.info(
        "LC graph ingestion: extracting KG from %s (use_ontology=%s, strict=%s)",
        _input_label, use_ontology, strict_mode,
    )
    t_extract_start = time.time()
    try:
        graph_docs = await extractor.aextract(_extractor_input)
    except Exception as exc:
        logger.error("LC KG extraction failed: %s", exc, exc_info=True)
        return time.time() - t_start, 0.0
    t_extract = time.time() - t_extract_start

    if not graph_docs:
        logger.info(
            "LC graph ingestion: extraction produced 0 graph documents, nothing to store "
            "(extract=%.2fs)",
            t_extract,
        )
        return time.time() - t_start, t_extract

    total_nodes = sum(len(gd.nodes) for gd in graph_docs)
    total_rels = sum(len(gd.relationships) for gd in graph_docs)
    logger.info(
        "LC graph ingestion: extracted %d graph docs (%d nodes, %d relationships) "
        "in %.2fs — writing to graph store",
        len(graph_docs), total_nodes, total_rels, t_extract,
    )

    # Inject ref_doc_id onto every entity node in every GraphDocument so that
    # the incremental-update delete query (MATCH (n) WHERE n.ref_doc_id = $rid)
    # can find and remove the right nodes.  The value comes from the source
    # Document's metadata; if absent we fall back to the source document's id.
    _injected = 0
    for _gd in graph_docs:
        _src_meta = getattr(getattr(_gd, "source", None), "metadata", {}) or {}
        _rid = (
            _src_meta.get("ref_doc_id")
            or _src_meta.get("doc_id")
            or getattr(getattr(_gd, "source", None), "id", None)
        )
        if _rid:
            for _node in (_gd.nodes or []):
                if _node.properties is None:
                    _node.properties = {}
                if "ref_doc_id" not in _node.properties:
                    _node.properties["ref_doc_id"] = _rid
                    _injected += 1
    if _injected:
        logger.debug("LC graph ingestion: injected ref_doc_id onto %d entity nodes", _injected)

    # Write to graph store via add_graph_documents
    t_write_start = time.time()
    try:
        # If the underlying store adapter has its own add_graph_documents override
        # (e.g. FalkorDB inlines properties, NebulaGraph uses nGQL), use it directly.
        _pg_adapter = system.pg_adapter if system is not None and hasattr(system, "pg_adapter") else None
        _store_adapter = getattr(_pg_adapter, "_store_adapter", None)
        if _store_adapter is not None and hasattr(_store_adapter, "add_graph_documents"):
            # Run in a thread — some store clients (e.g. gremlinpython) start their own
            # event loop internally and cannot be called from within a running loop.
            await asyncio.to_thread(
                _store_adapter.add_graph_documents, graph_docs, include_source=True
            )
        else:
            # Neo4jGraph uses camelCase `baseEntityLabel`; ArcadeDBGraph (and others)
            # use snake_case `base_entity_label`.  Inspect the actual signature so
            # this works without a hard-coded store-type list.
            import inspect as _inspect
            try:
                _agd_sig = _inspect.signature(lc_graph.add_graph_documents)
                if "base_entity_label" in _agd_sig.parameters:
                    _entity_label_kwarg = {"base_entity_label": True}
                elif "baseEntityLabel" in _agd_sig.parameters:
                    _entity_label_kwarg = {"baseEntityLabel": True}
                else:
                    _entity_label_kwarg = {}
            except (AttributeError, ValueError):
                _entity_label_kwarg = {}
            # Run in a thread — some store clients (e.g. gremlinpython) start their own
            # event loop internally and cannot be called from within a running loop.
            await asyncio.to_thread(
                lc_graph.add_graph_documents,
                graph_docs,
                include_source=True,
                **_entity_label_kwarg,
            )
        # Stamp ref_doc_id onto Chunk nodes (written by include_source=True).
        # Neo4jGraph.add_graph_documents creates Chunk nodes whose `id` property
        # equals the LC Document's id (NOT the stable ref_doc_id). Stamp the
        # stable ref_doc_id now so delete can use: MATCH (n) WHERE n.ref_doc_id = $rid
        if hasattr(lc_graph, "query"):
            for _gd in graph_docs:
                _src = getattr(_gd, "source", None)
                _src_meta = getattr(_src, "metadata", {}) or {}
                _src_id = getattr(_src, "id", None)
                _rid = (
                    _src_meta.get("ref_doc_id")
                    or _src_meta.get("doc_id")
                    or _src_id
                )
                if _rid and _src_id:
                    try:
                        lc_graph.query(
                            "MATCH (c:Chunk {id: $cid}) SET c.ref_doc_id = $rid",
                            params={"cid": _src_id, "rid": _rid},
                        )
                    except Exception as _exc:
                        logger.debug("LC graph: could not stamp Chunk ref_doc_id: %s", _exc)

        # Each store adapter implements normalize_entity_names() in its own
        # query language (Cypher, AQL, SurrealQL …).  This delegates to the
        # right implementation without any hardcoded store-type list here.
        if system is not None and hasattr(system, "pg_adapter") and system.pg_adapter is not None:
            system.pg_adapter.normalize_entity_names()
        t_write = time.time() - t_write_start
        t_total = time.time() - t_start
        logger.info(
            "LC graph ingestion complete: %d nodes, %d relationships written to %s "
            "(extract=%.2fs, write=%.2fs, total=%.2fs)",
            total_nodes, total_rels, type(lc_graph).__name__,
            t_extract, t_write, t_total,
        )
    except Exception as exc:
        logger.error(
            "LC graph add_graph_documents failed for %s: %s",
            type(lc_graph).__name__, exc, exc_info=True,
        )
        raise

    # Stash graph_docs on the system so update_rdf_graph can export them natively
    # without any format conversion.  The RDF pipeline reads this in update_rdf_graph.
    if system is not None:
        system._lc_graph_docs = graph_docs

    # --- FalkorDB native vector index: store text chunks alongside the graph ---
    # FalkorDB supports a built-in vector index (FalkorDBVector) in the same
    # database.  When no external vector store is configured we write the chunks
    # here so that vector similarity search is available during retrieval.
    if "Falkor" in type(lc_graph).__name__ and system is not None:
        _store_adapter_fk = getattr(
            getattr(system, "pg_adapter", None), "_store_adapter", None
        )
        if _store_adapter_fk is not None and hasattr(_store_adapter_fk, "store_chunk_embeddings"):
            try:
                from langchain.llm.embedding_factory import build_lc_embedding
                _fk_embedding = build_lc_embedding(config)
                # Convert LlamaIndex nodes to LangChain Documents for the vector store
                from langchain_core.documents import Document as LCDocument
                _fk_lc_docs = [
                    LCDocument(
                        page_content=n.get_content() if hasattr(n, "get_content") else (n.text or ""),
                        metadata=getattr(n, "metadata", {}) or {},
                    )
                    for n in (nodes or [])
                    if (n.get_content() if hasattr(n, "get_content") else (n.text or ""))
                ]
                if _fk_lc_docs:
                    _store_adapter_fk.store_chunk_embeddings(_fk_lc_docs, _fk_embedding)
            except Exception as _fk_exc:
                logger.warning("FalkorDB chunk embedding store failed: %s", _fk_exc)

    # Populate embeddings on newly written nodes so the vector index is live.
    # Only supported for Neo4j (uses Neo4jVector.from_existing_graph).
    if "Neo4j" in type(lc_graph).__name__:
        _populate_neo4j_embeddings(system, lc_graph, config)

    # For ArcadeDB: refresh schema after normalize_entity_names so the QA
    # chain sees `name` in the schema (not just `id`).  Also pass the ontology
    # manager so its per-entity property definitions are merged in, giving the
    # LLM richer context for Cypher generation.
    if "ArcadeDB" in type(lc_graph).__name__:
        try:
            from langchain.graph.pg_store_adapters.arcadedb_lc_adapter import ArcadeDBLangChainAdapter
            _onto_mgr = getattr(getattr(system, "schema_manager", None), "ontology_manager", None)
            ArcadeDBLangChainAdapter._refresh_schema(lc_graph, ontology_manager=_onto_mgr)
            logger.debug("ArcadeDB: schema refreshed after ingestion")
        except Exception as _exc:
            logger.debug("ArcadeDB post-ingest schema refresh skipped: %s", _exc)

    return time.time() - t_start, t_extract


def ingest_lc_graph(
    system: "HybridSearchSystem",
    nodes: List,
    documents: Optional[List] = None,
    schema_manager=None,
) -> tuple:
    """Sync wrapper around :func:`aingest_lc_graph`.

    Returns
    -------
    tuple[float, float]
        ``(total_seconds, extract_seconds)`` forwarded from :func:`aingest_lc_graph`,
        or ``(0.0, 0.0)`` when called from inside a running event loop (fire-and-forget path).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in an event loop — schedule as task (caller must await)
            import concurrent.futures
            asyncio.ensure_future(
                aingest_lc_graph(system, nodes, documents, schema_manager)
            )
            return 0.0, 0.0
        else:
            return loop.run_until_complete(aingest_lc_graph(system, nodes, documents, schema_manager))
    except RuntimeError:
        return asyncio.run(aingest_lc_graph(system, nodes, documents, schema_manager))


# ---------------------------------------------------------------------------
# LI-extraction -> LC-store write path
# ---------------------------------------------------------------------------


def _li_kg_to_lc_graph_docs(nodes: List) -> List:
    """Convert LI pre-extracted KG nodes to LangChain GraphDocument list.

    Reads KG_NODES_KEY / KG_RELATIONS_KEY from node metadata WITHOUT popping —
    the caller can still pass the same nodes to update_rdf_graph afterwards.
    """
    try:
        from langchain_community.graphs.graph_document import GraphDocument, Node, Relationship
        from langchain_core.documents import Document as LCDocument
    except ImportError:
        logger.warning(
            "_li_kg_to_lc_graph_docs: langchain_community not available — "
            "cannot convert LI KG to LC GraphDocuments"
        )
        return []

    from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY

    graph_docs = []
    for li_node in nodes:
        kg_nodes = li_node.metadata.get(KG_NODES_KEY, [])
        kg_rels = li_node.metadata.get(KG_RELATIONS_KEY, [])
        if not kg_nodes and not kg_rels:
            continue

        source_doc = LCDocument(
            page_content=(
                li_node.get_content() if hasattr(li_node, "get_content")
                else getattr(li_node, "text", "") or ""
            ),
            metadata={
                k: v for k, v in (li_node.metadata or {}).items()
                if k not in (KG_NODES_KEY, KG_RELATIONS_KEY)
            },
        )

        node_map = {en.name: Node(id=en.name, type=en.label) for en in kg_nodes}
        lc_nodes = list(node_map.values())

        lc_rels = []
        for rel in kg_rels:
            src_node = node_map.get(rel.source_id) or Node(id=rel.source_id, type="Entity")
            tgt_node = node_map.get(rel.target_id) or Node(id=rel.target_id, type="Entity")
            lc_rels.append(Relationship(source=src_node, target=tgt_node, type=rel.label))

        graph_docs.append(GraphDocument(nodes=lc_nodes, relationships=lc_rels, source=source_doc))

    return graph_docs


async def aingest_li_to_lc_graph(
    system: "HybridSearchSystem",
    nodes: List,
) -> float:
    """Write LI-extracted KG nodes to the LC graph store WITHOUT re-running LLMGraphTransformer.

    Called when GRAPH_BACKEND=langchain but KG_EXTRACTOR_BACKEND=llamaindex (default).
    LI extraction (SchemaLLMPathExtractor) has already populated metadata['nodes'] and
    metadata['relations'] on each node.  This function converts that data to LC
    GraphDocuments and writes it to the configured graph store via add_graph_documents.

    Metadata keys are READ (not popped) so the caller can still pass nodes to
    update_rdf_graph afterwards.

    Returns write duration in seconds.
    """
    t_start = time.time()
    pg_adapter = system.pg_adapter
    if pg_adapter is None or not pg_adapter.is_langchain():
        return 0.0

    lc_graph = pg_adapter.get_lc_graph()
    if lc_graph is None:
        logger.warning("aingest_li_to_lc_graph: lc_graph is None — skipping")
        return 0.0

    config = system.config

    if "Neo4j" in type(lc_graph).__name__ and getattr(config, "langchain_pg_vector_search", False):
        _ensure_lc_vector_index_ddl(lc_graph, config)

    graph_docs = _li_kg_to_lc_graph_docs(nodes)
    if not graph_docs:
        logger.info("aingest_li_to_lc_graph: no KG data found in nodes — nothing to write")
        return 0.0

    total_lc_nodes = sum(len(gd.nodes) for gd in graph_docs)
    total_lc_rels = sum(len(gd.relationships) for gd in graph_docs)
    logger.info(
        "LC graph write (LI extraction): %d graph docs (%d nodes, %d rels) -> %s",
        len(graph_docs), total_lc_nodes, total_lc_rels, type(lc_graph).__name__,
    )

    # Inject ref_doc_id onto every entity node so that the incremental-update
    # delete query (MATCH (n) WHERE n.ref_doc_id = $rid DETACH DELETE n) can
    # find and remove the right nodes.  Same injection as aingest_lc_graph.
    _injected = 0
    for _gd in graph_docs:
        _src_meta = getattr(getattr(_gd, "source", None), "metadata", {}) or {}
        _rid = (
            _src_meta.get("ref_doc_id")
            or _src_meta.get("doc_id")
            or getattr(getattr(_gd, "source", None), "id", None)
        )
        if _rid:
            for _node in (_gd.nodes or []):
                if _node.properties is None:
                    _node.properties = {}
                if "ref_doc_id" not in _node.properties:
                    _node.properties["ref_doc_id"] = _rid
                    _injected += 1
    if _injected:
        logger.debug("LC graph (LI->LC): injected ref_doc_id onto %d entity nodes", _injected)

    # Use the store adapter's add_graph_documents when available — this handles
    # stores that don't implement add_graph_documents on the raw graph object
    # (e.g. NebulaGraph, HugeGraph) or that need extra processing before the
    # call (e.g. Cosmos Gremlin needs partition-key injection, Ladybug needs
    # allowed_relationships).  The adapter wraps the raw graph internally.
    _pg_adapter = system.pg_adapter if system is not None and hasattr(system, "pg_adapter") else None
    _store_adapter = getattr(_pg_adapter, "_store_adapter", None)

    try:
        if _store_adapter is not None and hasattr(_store_adapter, "add_graph_documents"):
            # Run in a thread — some clients (e.g. gremlinpython) start their own
            # event loop internally and cannot be called from within a running loop.
            await asyncio.to_thread(
                _store_adapter.add_graph_documents, graph_docs, include_source=True
            )
        else:
            import inspect as _inspect
            try:
                _agd_sig = _inspect.signature(lc_graph.add_graph_documents)
                if "base_entity_label" in _agd_sig.parameters:
                    _entity_label_kwarg = {"base_entity_label": True}
                elif "baseEntityLabel" in _agd_sig.parameters:
                    _entity_label_kwarg = {"baseEntityLabel": True}
                else:
                    _entity_label_kwarg = {}
            except (AttributeError, ValueError):
                _entity_label_kwarg = {}

            await asyncio.to_thread(
                lc_graph.add_graph_documents,
                graph_docs,
                include_source=True,
                **_entity_label_kwarg,
            )
    except Exception as exc:
        logger.error(
            "aingest_li_to_lc_graph: add_graph_documents failed for %s: %s",
            type(lc_graph).__name__, exc, exc_info=True,
        )
        raise

    if system is not None and hasattr(system, "pg_adapter") and system.pg_adapter is not None:
        system.pg_adapter.normalize_entity_names()

    if "Neo4j" in type(lc_graph).__name__:
        _populate_neo4j_embeddings(system, lc_graph, config)

    try:
        lc_graph.refresh_schema()
        logger.debug("LC graph schema refreshed after LI->LC write")
    except Exception as exc:
        logger.debug("LC graph schema refresh skipped: %s", exc)

    t_write = time.time() - t_start
    logger.info(
        "LC graph write complete: %d nodes, %d rels written to %s in %.2fs",
        total_lc_nodes, total_lc_rels, type(lc_graph).__name__, t_write,
    )
    return t_write


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _ensure_lc_vector_index_ddl(lc_graph, config) -> None:
    """Run ``CREATE VECTOR INDEX IF NOT EXISTS`` — pure DDL, no data needed.

    Called at the start of ingestion so the index exists before
    ``add_graph_documents`` writes any nodes.  Also called by ``Neo4jAdapter``
    at construction when ``vector_index_config`` is provided, so this is
    effectively a no-op on the second call (``IF NOT EXISTS``).
    """
    index_name  = getattr(config, "langchain_pg_vector_index", "entity")
    node_label  = getattr(config, "langchain_pg_vector_node_label", "__Entity__")
    emb_prop    = getattr(config, "langchain_pg_vector_embedding_property", "embedding")
    dims        = int(getattr(config, "embedding_dimension", 1536) or 1536)
    cypher = (
        f"CREATE VECTOR INDEX `{index_name}` IF NOT EXISTS "
        f"FOR (n:`{node_label}`) ON n.`{emb_prop}` "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dims}, "
        f"`vector.similarity_function`: 'cosine'}}}}"
    )
    try:
        lc_graph.query(cypher)
        logger.debug("Vector index '%s' DDL ensured (dims=%d)", index_name, dims)
    except Exception as exc:
        logger.warning("Could not ensure vector index DDL '%s': %s", index_name, exc)



def _populate_neo4j_embeddings(system, lc_graph, config):
    """Compute and store embeddings on ``__Entity__`` nodes that have none.

    Called after ``add_graph_documents`` so every newly written node gets an
    embedding set and is picked up by the vector index automatically.
    Only runs when ``LANGCHAIN_PG_VECTOR_SEARCH=true``.
    """
    if not getattr(config, "langchain_pg_vector_search", False):
        return

    graph_db_config = getattr(config, "graph_db_config", {}) or {}
    url      = graph_db_config.get("url", "bolt://localhost:7687")
    username = graph_db_config.get("username", "neo4j")
    password = graph_db_config.get("password", "password")
    database = graph_db_config.get("database", "neo4j")

    index_name         = getattr(config, "langchain_pg_vector_index", "entity")
    node_label         = getattr(config, "langchain_pg_vector_node_label", "__Entity__")
    embedding_property = getattr(config, "langchain_pg_vector_embedding_property", "embedding")
    text_property      = getattr(config, "langchain_pg_vector_text_property", "name")

    try:
        from langchain_neo4j import Neo4jVector
    except ImportError:
        try:
            from langchain_community.vectorstores import Neo4jVector  # type: ignore
        except ImportError:
            logger.debug("Neo4jVector not available — skipping embedding population")
            return

    try:
        from langchain.graph.pg_retriever_factory import _LlamaIndexEmbeddingAdapter
        from factories import LLMFactory
        embed_model = getattr(system, "embed_model", None)
        if embed_model is None:
            embed_model = LLMFactory.create_embedding_model(
                config.llm_provider, config.llm_config, settings=config
            )
        lc_embeddings = _LlamaIndexEmbeddingAdapter(embed_model)
    except Exception as exc:
        logger.warning("LC vector index: could not build embedding adapter: %s", exc)
        return

    t0 = time.time()
    logger.info(
        "LC vector index: populating embeddings on '%s' nodes (text_prop=%s) ...",
        node_label, text_property,
    )
    try:
        # from_existing_graph walks all nodes matching node_label, computes
        # embeddings for those missing embedding_property, and stores them.
        # The index already exists (DDL was run before add_graph_documents)
        # so Neo4j indexes each embedding as it is written.
        vs = Neo4jVector.from_existing_graph(
            embedding=lc_embeddings,
            url=url,
            username=username,
            password=password,
            database=database,
            index_name=index_name,
            node_label=node_label,
            text_node_properties=[text_property],
            embedding_node_property=embedding_property,
        )
        # Explicitly close the driver so the Neo4j connection pool is released.
        try:
            if hasattr(vs, "_driver") and vs._driver is not None:
                vs._driver.close()
            elif hasattr(vs, "close"):
                vs.close()
        except Exception:
            pass
        logger.info(
            "LC vector index '%s' embedding population complete (%.2fs)",
            index_name, time.time() - t0,
        )
    except Exception as exc:
        logger.warning(
            "LC vector embedding population failed (non-fatal): %s — "
            "vector search may return no results until next ingestion.",
            exc,
        )

def _get_lc_llm(config):
    """Obtain a LangChain chat model from config, with fallback to BothLLMAdapter."""
    # Check if a Both adapter is available (holds one LI + one LC instance)
    try:
        from adapters.llm.llm_adapter import BothLLMAdapter
        llm_adapter = getattr(config, "_llm_adapter", None)
        if isinstance(llm_adapter, BothLLMAdapter):
            return llm_adapter.get_lc_llm()
    except ImportError:
        pass

    # Fall back to building an LC LLM from scratch
    try:
        from langchain.llm.llm_factory import get_langchain_llm
        return get_langchain_llm(config)
    except Exception as exc:
        logger.warning("Could not build LangChain LLM: %s", exc)
        return None


def _get_ontology_manager(config, schema_manager=None):
    """Resolve an OntologyManager from schema_manager or global state."""
    if schema_manager is not None:
        om = getattr(schema_manager, "ontology_manager", None)
        if om is not None:
            return om

    try:
        from rdf.api_rdf_enhancements import ontology_manager as _global_om
        return _global_om
    except (ImportError, AttributeError):
        return None
