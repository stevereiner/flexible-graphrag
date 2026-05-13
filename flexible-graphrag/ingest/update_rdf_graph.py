"""
Shared RDF graph export step for all ingest entry points.

Replaces ingest/rdf_export.py — import update_rdf_graph from here directly.
"""

import logging
import time

from ingest._helpers import make_kg_extractor

logger = logging.getLogger(__name__)


def _should_export_rdf(config, skip_graph: bool) -> bool:
    return (
        str(getattr(config, "rdf_graph_db", "none")).lower() not in ("none", "")
        and config.enable_knowledge_graph
        and not skip_graph
    )


async def update_rdf_graph(
    system,
    nodes: list,
    *,
    nodes_kg_extracted: bool = False,
    skip_graph: bool = False,
    span_name: str = "rag.graph_extraction.rdf",
) -> tuple:
    """Export nodes to all configured RDF stores.

    If nodes_kg_extracted is True the caller already ran KG extraction and
    the triples are embedded in nodes — export directly without a second LLM
    call.  Otherwise a standalone extraction pass is run first on a copy of
    the nodes (LC backend path, or any path where extraction wasn't done).

    Returns (kg_extraction_seconds, rdf_store_seconds) — both 0.0 if skipped.
    """
    if not _should_export_rdf(system.config, skip_graph):
        return 0.0, 0.0

    from stores.rdf_manager import export_nodes_to_rdf_stores

    t_kg = 0.0
    t_store = 0.0
    try:
        lc_graph_docs = getattr(system, "_lc_graph_docs", None)
        if lc_graph_docs is not None:
            # LC extraction path: export directly from GraphDocuments — no format conversion.
            system._lc_graph_docs = None  # consume
            from stores.rdf_manager import export_lc_graph_docs_to_rdf_stores
            t_store_start = time.time()
            export_lc_graph_docs_to_rdf_stores(
                lc_graph_docs, nodes, system.config,
                schema_manager=system.schema_manager,
            )
            t_store = time.time() - t_store_start
        elif nodes_kg_extracted:
            t_store_start = time.time()
            export_nodes_to_rdf_stores(nodes, system.config, schema_manager=system.schema_manager)
            t_store = time.time() - t_store_start
        else:
            logger.info("RDF export: running standalone KG extraction (%s)", span_name)
            rdf_nodes = list(nodes)
            rdf_extractor = make_kg_extractor(system)
            from process.kg_extractor import run_kg_extractors_on_nodes
            t_kg_start = time.time()
            rdf_nodes, num_entities, num_relations, _ = await run_kg_extractors_on_nodes(
                rdf_nodes, [rdf_extractor], system.config, span_name=span_name
            )
            t_kg = time.time() - t_kg_start
            logger.info("RDF extraction: %d entities, %d relations (%.2fs)", num_entities, num_relations, t_kg)
            t_store_start = time.time()
            export_nodes_to_rdf_stores(rdf_nodes, system.config, schema_manager=system.schema_manager)
            t_store = time.time() - t_store_start
    except Exception as exc:
        logger.error("RDF export failed: %s", exc, exc_info=True)

    duration = t_kg + t_store
    logger.info(f"RDF graph: {duration:.2f}s (KG extraction: {t_kg:.2f}s, store write: {t_store:.2f}s)")
    return t_kg, t_store
