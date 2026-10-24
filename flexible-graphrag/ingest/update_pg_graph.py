"""
Shared PG graph index step for all ingest entry points.
"""

import functools
import logging
import time

from llama_index.core import StorageContext
from llama_index.core.indices.property_graph import PropertyGraphIndex
from llama_index.core.schema import TransformComponent

from ingest._helpers import make_kg_extractor

logger = logging.getLogger(__name__)


class _NoOpExtractor(TransformComponent):
    """A KG extractor that extracts nothing.

    Exists solely to be truthy.  ``PropertyGraphIndex`` does
    ``self._kg_extractors = kg_extractors or [SimpleLLMPathExtractor(), ...]``
    (llama_index/core/indices/property_graph/base.py:124), so passing ``[]`` to
    say "do not extract" is read as "not specified" and replaced by LlamaIndex's
    defaults — which ``__init__`` then runs over the nodes.

    In this pipeline KG extraction is a separate preprocessing step (that is
    what produces the entity/relation counts and stage timings), so a second
    pass inside the index is pure duplication: an unschema'd
    ``SimpleLLMPathExtractor`` run whose output is written alongside the real
    one, with names sentence-cased by its ``.capitalize()`` normalisation
    ("Priya raman" beside "Priya Raman"), no type labels (``EntityNode.label``
    stays ``"entity"``), and free-form relations ("Attended by", "Ran by")
    beside the schema's ATTENDED / ASSIGNED_TO.  Measured on one ontology-guided
    ingest: 23 shadow entities against 20 real ones.
    """

    def __call__(self, nodes, **kwargs):
        return nodes

    async def acall(self, nodes, **kwargs):
        return nodes

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
    graphs=None,
    skip_graph: bool = False,
    pre_extracted: bool = False,
    span_name: str = "rag.graph_extraction",
) -> tuple:
    """Run KG extraction and update the PG graph index (LI or LC backend).

    ``graphs`` (graph_flags.GraphFlags) says which graphs this ingest builds; ``skip_graph`` is
    the older single flag (both off), used when ``graphs`` is not given. With the property graph
    off but RDF on, extraction still runs here (for update_rdf_graph to reuse) and the property
    graph is not written -- the same as PG_GRAPH_DB=none.

    Handles:
    - graphs / enable_knowledge_graph gating
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
    from graph_flags import GraphFlags
    flags = graphs if graphs is not None else GraphFlags.of(skip_graph, default=GraphFlags.defaults(system.config))
    config = system.config
    pg_configured = str(config.pg_graph_db) != "none"
    rdf_configured = str(getattr(config, "rdf_graph_db", "none")).lower() not in ("none", "")
    want_pg = flags.graph and pg_configured
    want_rdf = flags.rdf and rdf_configured
    # Extraction is for the property graph, or only for RDF to reuse (written to no PG store)
    pg_disabled = not want_pg

    if not config.enable_knowledge_graph or not (want_pg or want_rdf):
        if config.enable_knowledge_graph and (pg_configured or rdf_configured):
            logger.info(f"Knowledge graph SKIPPED for this ingest ({flags.describe()})")
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
        + ("" if want_pg else " (extraction for RDF only, no property graph write)")
    )

    _kg_backend = (getattr(system.config, "kg_extractor_backend", "llamaindex") or "llamaindex").lower()
    _is_lc_adapter = getattr(system.pg_adapter, "is_langchain", lambda: False)()

    if _is_lc_adapter and _kg_backend == "langchain" and not want_pg:
        # LC extraction writes the property graph as it goes: leave it to update_rdf_graph's
        # own extraction when only RDF is wanted
        logger.info("Property graph off for this ingest: RDF extracts on its own (LC backend)")
        return nodes, False, 0.0, 0.0, 0, 0

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
        # entity/relation counts stashed on the system by aingest_lc_graph (LC path returns
        # durations, not counts) — surface them so the KG node + summary report real numbers.
        lc_ents = getattr(system, "_last_lc_kg_entities", 0)
        lc_rels = getattr(system, "_last_lc_kg_relations", 0)
        return nodes, False, lc_extract, lc_write, lc_ents, lc_rels

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
        if pre_extracted:
            # Nodes were already KG-extracted upstream (e.g. a separate KG Extraction
            # node). Skip the LLM extraction and just count from metadata; Phase B
            # (graph store I/O) runs as normal with kg_extractors=[].
            from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY
            num_entities = sum(len(n.metadata.get(KG_NODES_KEY, []) or []) for n in nodes)
            num_relations = sum(len(n.metadata.get(KG_RELATIONS_KEY, []) or []) for n in nodes)
            extraction_duration = 0.0
            logger.info(
                f"KG pre-extracted: {num_entities} entities, {num_relations} relations "
                f"(skipping re-extraction)"
            )
        else:
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

        # Property-graph stores (Neo4j, etc.) reject dict-valued properties
        # ("Property values can only be of primitive types or arrays thereof. Encountered: Map{}").
        # Two sources of dicts: (a) chunk-node metadata from readers like AzStorageBlobReader
        # (Azure custom-metadata map), and (b) the extracted ENTITY/RELATION .properties — KG
        # extraction copies source metadata into them, and PropertyGraphIndex upserts those same
        # objects (popped from KG_NODES_KEY/KG_RELATIONS_KEY). Stringify non-primitives in both.
        try:
            import json as _json
            from llama_index.core.graph_stores.types import KG_NODES_KEY as _KGN, KG_RELATIONS_KEY as _KGR

            def _prim(_v):
                return _v is None or isinstance(_v, (str, int, float, bool))

            def _clean_dict(_d):
                if not isinstance(_d, dict):
                    return
                for _k, _v in list(_d.items()):
                    if _prim(_v):
                        continue
                    # Neo4j accepts arrays of primitives but NOT arrays containing null
                    # ("Collections containing null values can not be stored in properties" —
                    # e.g. SharePoint's allowed_sharePointGroup_display_names=[null,null,null]).
                    # Keep only all-non-null-primitive lists; stringify anything else.
                    if isinstance(_v, (list, tuple)) and all(
                        isinstance(_x, (str, int, float, bool)) for _x in _v
                    ):
                        _d[_k] = list(_v)
                    else:
                        try:
                            _d[_k] = _json.dumps(_v, default=str)
                        except Exception:
                            _d[_k] = str(_v)

            for _n in nodes:
                _md = getattr(_n, "metadata", None)
                if not isinstance(_md, dict):
                    continue
                # (b) extracted entity / relation properties (same objects that get upserted)
                for _kg_key in (_KGN, _KGR):
                    for _obj in _md.get(_kg_key, []) or []:
                        _clean_dict(getattr(_obj, "properties", None))
                # (a) chunk-node metadata — leave the KG containers (objects) in place
                for _k in list(_md.keys()):
                    if _k not in (_KGN, _KGR):
                        _sub = {_k: _md[_k]}
                        _clean_dict(_sub)
                        _md[_k] = _sub[_k]
        except Exception as _san_err:
            logger.warning(f"Graph node-metadata sanitization skipped: {_san_err}")

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
            # kg_extractors=[] does NOT disable extraction.  base.py:124 is
            #     self._kg_extractors = kg_extractors or [SimpleLLMPathExtractor…]
            # so an empty list is falsy and LlamaIndex substitutes its defaults,
            # which __init__ then runs over the nodes (base.py:204/209).  The
            # index also cannot be built without nodes, so there is no window in
            # which to blank them first.  A one-element no-op list is truthy, so
            # ours is kept and nothing extracts.
            graph_kwargs["kg_extractors"] = [_NoOpExtractor()]
            system.graph_index = await loop.run_in_executor(
                None, functools.partial(PropertyGraphIndex, **graph_kwargs)
            )

            # Why this matters: extraction already ran as a preprocessing step
            # (that is what produced `nodes` above, and what gives us the
            # entity/relation counts and stage timings).  Left in place, the
            # defaults run a SECOND, unschema'd LLM extraction whose output is
            # written alongside the real one:
            #   * names normalised by default_parse_triplets_fn's .capitalize()
            #     -> "Priya raman" beside the schema pass's "Priya Raman"
            #   * no type, so EntityNode.label stays "entity"
            #   * free-form relations ("Attended by", "Ran by", "Wrote up")
            #     beside the schema's ATTENDED / ASSIGNED_TO
            # Measured on one ontology-guided ingest: 23 shadow entities against
            # 20 real ones, and 29 shadow relations against 25 — i.e. over half
            # the graph, plus a second LLM pass per document.
            #
            # The insert_nodes path below already blanks these by hand for the
            # same reason; do it once here so the index simply never extracts.
            try:
                system.graph_index._kg_extractors = []
            except Exception:  # noqa: BLE001 - never fail an ingest over this
                logger.debug("Could not clear _kg_extractors on the new index", exc_info=True)

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
