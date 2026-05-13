"""
Shared PG graph index step for all ingest entry points.
"""

import functools
import logging
import time

from llama_index.core import StorageContext
from llama_index.core.indices.property_graph import PropertyGraphIndex

from ingest._helpers import make_kg_extractor

logger = logging.getLogger(__name__)

try:
    from observability import get_tracer
    from observability.metrics import get_rag_metrics
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    get_tracer = None
    get_rag_metrics = None


async def update_pg_graph(
    system,
    nodes: list,
    documents: list,
    loop,
    *,
    skip_graph: bool = False,
    span_name: str = "rag.graph_extraction",
) -> tuple:
    """Run KG extraction and update the PG graph index (LI or LC backend).

    Handles:
    - skip_graph / enable_knowledge_graph gating
    - LC backend (LLMGraphTransformer via aingest_lc_graph)
    - LI backend: first-time create and incremental update
    - pg_disabled path (extraction runs for RDF, PropertyGraphIndex skipped)
    - Neptune Analytics embed_kg_nodes=False
    - OTel spans with separate extraction vs graph-update attributes
    - Metrics recording (entity / relation counts, latency)

    Returns:
        (nodes, nodes_kg_extracted, extraction_duration, graph_update_duration,
         num_entities, num_relations)

    Sets system.graph_index and system.graph_intentionally_skipped as side-effects.
    """
    should_skip_graph = skip_graph or not system.config.enable_knowledge_graph
    pg_disabled = str(system.config.pg_graph_db) == "none"

    if should_skip_graph:
        if skip_graph and system.config.enable_knowledge_graph:
            logger.info("Knowledge graph SKIPPED (per-ingest skip_graph flag)")
            system.graph_intentionally_skipped = True
        else:
            logger.info("Knowledge graph disabled in config")
            system.graph_index = None
            system.graph_intentionally_skipped = False
        return nodes, False, 0.0, 0.0, 0, 0

    system.graph_intentionally_skipped = False
    graph_store_type = type(system.graph_store).__name__
    llm_model_name = getattr(system.llm, "model", type(system.llm).__name__)
    logger.info(
        f"PG graph — {len(nodes)} nodes, store={graph_store_type}, LLM={llm_model_name}"
    )

    _kg_backend = (getattr(system.config, "kg_extractor_backend", "llamaindex") or "llamaindex").lower()
    _is_lc_adapter = getattr(system.pg_adapter, "is_langchain", lambda: False)()

    # LC backend with LC extractor — extraction and graph update handled together.
    if _is_lc_adapter and _kg_backend == "langchain":
        _lc_store_label = (
            getattr(system.pg_adapter, "store_type", None)
            or str(getattr(system.config, "langchain_pg_store_type", "") or "")
            or str(getattr(system.config, "pg_graph_db", "") or "")
            or "unknown"
        )
        logger.info("LC graph backend (%s): LLMGraphTransformer ingestion", _lc_store_label)
        from ingest.ingest_lc_graph import aingest_lc_graph
        # Pass lc_docs (from CHUNKER_BACKEND=langchain) when available to skip LI->LC conversion.
        _lc_docs = getattr(system, "_last_lc_chunks", None)
        if _lc_docs is not None:
            logger.info(
                "[LC pipe] graph: passing %d LC chunks directly to aingest_lc_graph "
                "(no LI->LC conversion)", len(_lc_docs),
            )
        else:
            logger.debug("[LC pipe] graph: no _last_lc_chunks, using %d LI bridge nodes", len(nodes))
        lc_total, lc_extract = await aingest_lc_graph(
            system, nodes, documents, schema_manager=system.schema_manager,
            lc_docs=_lc_docs,
        )
        # Report extraction time under kg_duration, graph write under graph_update_duration
        lc_write = lc_total - lc_extract
        return nodes, False, lc_extract, lc_write, 0, 0

    # LI backend
    kg_extractor = make_kg_extractor(system)
    graph_storage_context = StorageContext.from_defaults(
        property_graph_store=system.graph_store
    )

    graph_span = None
    token = None
    extraction_duration = 0.0
    graph_update_duration = 0.0
    num_entities = num_relations = 0

    if OBSERVABILITY_AVAILABLE:
        try:
            from opentelemetry import context as otel_ctx, trace as otel_trace
            tracer = get_tracer(__name__)
            graph_span = tracer.start_span(span_name)
            graph_span.set_attribute("graph.num_documents", len(documents))
            graph_span.set_attribute("graph.llm_model", llm_model_name)
            graph_span.set_attribute("graph.database_type", graph_store_type)
            graph_span.set_attribute("graph.extractor_type", system.config.kg_extractor_type)
            graph_span.set_attribute("graph.pg_disabled", pg_disabled)
            ctx = otel_trace.set_span_in_context(graph_span)
            token = otel_ctx.attach(ctx)
        except Exception as e:
            logger.debug(f"OTel span setup failed: {e}")

    try:
        # --- Phase A: KG extraction (LLM-intensive) ---
        from process.kg_extractor import run_kg_extractors_on_nodes
        extraction_start = time.time()
        nodes, num_entities, num_relations, _ = await run_kg_extractors_on_nodes(
            nodes, [kg_extractor], system.config, span_name=span_name
        )
        extraction_duration = time.time() - extraction_start
        logger.info(
            f"KG extraction: {num_entities} entities, {num_relations} relations "
            f"in {extraction_duration:.2f}s"
        )

        if graph_span:
            graph_span.set_attribute("graph.extraction_latency_ms", extraction_duration * 1000)
            graph_span.set_attribute("graph.num_entities", num_entities)
            graph_span.set_attribute("graph.num_relations", num_relations)

        # --- Phase B: Graph DB update (store I/O) ---
        graph_update_start = time.time()

        if pg_disabled:
            graph_update_duration = 0.0
            logger.info(
                f"PG_GRAPH_DB=none: skipped PropertyGraphIndex, "
                f"{num_entities} entities -> RDF store"
            )

        elif _is_lc_adapter and system.graph_store is None:
            # LC backend with LI extraction: graph_store is None (setup_databases skips it
            # for LC backends).  Convert the already-extracted LI KG to LC GraphDocuments
            # and write directly to the LC graph store.  PropertyGraphIndex is skipped —
            # no wasted in-memory writes and no embedding of KG nodes.
            # Metadata['nodes'] / ['relations'] is READ (not popped) so RDF export works.
            from ingest.ingest_lc_graph import aingest_li_to_lc_graph
            logger.info(
                "LC backend + LI extraction: writing %d entities, %d relations "
                "directly to LC graph store (PropertyGraphIndex skipped)",
                num_entities, num_relations,
            )
            graph_update_duration = await aingest_li_to_lc_graph(system, nodes)

        elif system.graph_index is None:
            # LI backend: create PropertyGraphIndex backed by the real graph store.
            # PropertyGraphIndex._insert_nodes pops metadata['nodes'] / ['relations'],
            # so save them first and restore afterwards for RDF export.
            from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY
            _saved_kg = [
                (n.metadata.get(KG_NODES_KEY, []), n.metadata.get(KG_RELATIONS_KEY, []))
                for n in nodes
            ]

            graph_kwargs = {
                "nodes": nodes,
                "llm": system.llm,
                "embed_model": system.embed_model,
                "kg_extractors": [],
                "property_graph_store": system.graph_store,
                "storage_context": graph_storage_context,
            }
            if "NeptuneAnalytics" in graph_store_type:
                graph_kwargs["embed_kg_nodes"] = False
                logger.info("Neptune Analytics detected: embed_kg_nodes=False")
            logger.info("Creating PropertyGraphIndex with pre-extracted nodes")
            system.graph_index = await loop.run_in_executor(
                None, functools.partial(PropertyGraphIndex, **graph_kwargs)
            )
            graph_update_duration = time.time() - graph_update_start
            logger.info(
                f"PropertyGraphIndex created in {graph_update_duration:.2f}s — "
                f"{num_entities} entities, {num_relations} relations"
            )

            # Restore KG metadata (popped by PropertyGraphIndex) so RDF export can read it.
            for node, (kg_n, kg_r) in zip(nodes, _saved_kg):
                if kg_n:
                    node.metadata[KG_NODES_KEY] = kg_n
                if kg_r:
                    node.metadata[KG_RELATIONS_KEY] = kg_r

        else:
            # LI backend incremental insert — same pop/restore pattern.
            from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY
            _saved_kg = [
                (n.metadata.get(KG_NODES_KEY, []), n.metadata.get(KG_RELATIONS_KEY, []))
                for n in nodes
            ]

            _orig_extractors = system.graph_index._kg_extractors
            _orig_use_async = getattr(system.graph_index, "_use_async", False)
            system.graph_index._kg_extractors = []
            system.graph_index._use_async = False
            try:
                system.graph_index.insert_nodes(nodes)
            finally:
                system.graph_index._kg_extractors = _orig_extractors
                system.graph_index._use_async = _orig_use_async
            graph_update_duration = time.time() - graph_update_start
            logger.info(
                f"Graph index updated in {graph_update_duration:.2f}s — "
                f"{num_entities} entities, {num_relations} relations"
            )

            for node, (kg_n, kg_r) in zip(nodes, _saved_kg):
                if kg_n:
                    node.metadata[KG_NODES_KEY] = kg_n
                if kg_r:
                    node.metadata[KG_RELATIONS_KEY] = kg_r

        if graph_span:
            graph_span.set_attribute("graph.update_latency_ms", graph_update_duration * 1000)
            graph_span.set_attribute("graph.status", "success")

        if OBSERVABILITY_AVAILABLE and get_rag_metrics:
            try:
                get_rag_metrics().record_graph_extraction(
                    latency_ms=(extraction_duration + graph_update_duration) * 1000,
                    num_entities=num_entities,
                    num_relations=num_relations,
                )
            except Exception as e:
                logger.warning(f"Failed to record graph metrics: {e}")

    except Exception as e:
        if graph_span:
            graph_span.set_attribute("graph.status", "error")
            graph_span.set_attribute("graph.error", str(e))
            try: graph_span.record_exception(e)
            except Exception: pass
        raise
    finally:
        if graph_span:
            try: graph_span.end()
            except Exception: pass
        if token is not None:
            try:
                from opentelemetry import context as otel_ctx
                otel_ctx.detach(token)
            except Exception: pass

    return nodes, True, extraction_duration, graph_update_duration, num_entities, num_relations
