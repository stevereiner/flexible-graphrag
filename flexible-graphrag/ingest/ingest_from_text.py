"""
Raw-text ingestion entry point for Flexible GraphRAG.

ingest_text — wraps a raw string as a Document and runs the full pipeline
              (chunk, embed, vector index, graph index, search index).
"""

import logging

from ingest._helpers import _check_cancellation, _get_loop
from ingest.run_chunk_pipeline import run_chunk_pipeline
from ingest.update_vector import update_vector
from ingest.update_search import update_search
from ingest.update_pg_graph import update_pg_graph
from ingest.update_rdf_graph import update_rdf_graph

logger = logging.getLogger(__name__)


async def ingest_text(
    system,
    content: str,
    source_name: str = "text_input",
    processing_id: str = None,
    skip_graph: bool = False,
):
    """Ingest raw text content.

    Args:
        system: HybridSearchSystem instance
        content: Raw text to ingest
        source_name: Display name for the text source
        processing_id: Optional ID for cancellation checking
        skip_graph: Skip knowledge graph extraction (faster, vector+search only)
    """
    from retriever_setup import setup_hybrid_retriever

    logger.info(f"Ingesting text content from: {source_name}")

    document = system.document_processor.process_text_content(content, source_name)

    if not hasattr(system, '_last_ingested_documents') or system._last_ingested_documents is None:
        system._last_ingested_documents = []
    system._last_ingested_documents.append(document)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 1: Chunk + embed
    loop = _get_loop()
    nodes, chunk_duration = await run_chunk_pipeline(system, [document], loop)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 2: Vector index  (insert — always additive for text)
    vector_duration = await update_vector(system, nodes, loop)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 3: Search index
    search_duration = await update_search(system, nodes, loop)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 4: PG graph
    nodes, nodes_kg_extracted, kg_duration, graph_duration, _, _ = await update_pg_graph(
        system, nodes, [document], loop, skip_graph=skip_graph
    )

    # Step 4b: RDF graph
    rdf_kg_duration, rdf_store_duration = await update_rdf_graph(
        system, nodes, nodes_kg_extracted=nodes_kg_extracted, skip_graph=skip_graph
    )

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    setup_hybrid_retriever(system)
    logger.info(
        f"Text ingestion completed -- "
        f"Chunk: {chunk_duration:.2f}s, Vector: {vector_duration:.2f}s, "
        f"Search: {search_duration:.2f}s, KG: {kg_duration + rdf_kg_duration:.2f}s, "
        f"Graph: {graph_duration:.2f}s, RDF: {rdf_store_duration:.2f}s"
    )
