"""
File-path ingestion entry point for Flexible GraphRAG.

ingest_documents — takes a list of file paths, runs DocumentProcessor
                   (Docling/LlamaParse), then the full pipeline:
                   chunk, embed, vector index, graph index, search index.

For raw text see ingest/ingest_from_text.py.
For pre-loaded Document objects see ingest/ingest_from_source.py.
"""

import time
from pathlib import Path
from typing import List, Union
import logging

from ingest._helpers import _check_cancellation, _get_loop, generate_completion_message
from ingest.run_chunk_pipeline import run_chunk_pipeline
from ingest.update_vector import update_vector
from ingest.update_search import update_search
from ingest.update_openarch import update_openarch
from ingest.update_pg_graph import update_pg_graph
from ingest.update_rdf_graph import update_rdf_graph

logger = logging.getLogger(__name__)

try:
    from observability.metrics import get_rag_metrics
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    get_rag_metrics = None


async def ingest_documents(
    system,
    file_paths: List[Union[str, Path]],
    processing_id: str = None,
    status_callback=None,
    graphs=None,
    skip_graph: bool = False,
):
    """Process and ingest documents from file paths into all search modalities.

    Args:
        system: HybridSearchSystem instance
        file_paths: List of file paths to ingest
        processing_id: Optional ID for cancellation/progress tracking
        status_callback: Optional callable(processing_id, status, message, progress, ...)
        graphs: which graphs to build (graph_flags.GraphFlags: property graph, RDF)
        skip_graph: older single flag, both graphs off (used when ``graphs`` is not given)
    """
    from retriever_setup import setup_hybrid_retriever
    from ingest._helpers import warmup_hybrid_retriever
    from stores.index_manager import persist_indexes

    def _update_progress(message, progress, current_file=None, current_phase=None, files_completed=0):
        if status_callback:
            status_callback(
                processing_id=processing_id,
                status="processing",
                message=message,
                progress=progress,
                current_file=current_file,
                current_phase=current_phase,
                files_completed=files_completed,
                total_files=len(file_paths),
            )

    # Clear partial state before starting
    if (system.vector_index is None) != (system.graph_index is None):
        logger.warning("Detected partial system state - clearing before new ingestion")
        system.vector_index = None
        system.graph_index = None
        system.hybrid_retriever = None
    if system.hybrid_retriever is None and (system.vector_index is not None or system.graph_index is not None):
        logger.warning("Detected incomplete retriever setup - clearing before new ingestion")
        system.vector_index = None
        system.graph_index = None
        system.hybrid_retriever = None

    # Step 1: Convert files via DocumentProcessor (Docling / LlamaParse)
    logger.info("Converting documents with Docling...")
    _update_progress("Converting documents with Docling...", 20, current_phase="docling")
    documents = await system.document_processor.process_documents(file_paths, processing_id=processing_id)
    if not documents:
        raise ValueError("No documents were successfully processed")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 2: Chunk + embed
    logger.info("Processing documents into nodes...")
    _update_progress("Splitting documents into chunks...", 30, current_phase="chunking")

    if not hasattr(system, '_last_ingested_documents') or system._last_ingested_documents is None:
        system._last_ingested_documents = []
    previous_count = len(system._last_ingested_documents)
    system._last_ingested_documents.extend(documents)
    logger.info(f"Added {len(documents)} documents. Total stored: {len(system._last_ingested_documents)} (previous: {previous_count})")

    logger.info(f"=== PRE-CHUNKING: {len(documents)} Documents ===")
    for i, doc in enumerate(documents[:5]):
        logger.info(f"  Doc[{i}] length: {len(doc.text)} chars, metadata: {doc.metadata}")
    if len(documents) > 5:
        logger.info(f"  ... and {len(documents)-5} more documents")

    _ingest_start = time.time()

    loop = _get_loop()
    nodes, chunk_duration = await run_chunk_pipeline(system, documents, loop)

    embed_model_name = getattr(system.embed_model, 'model_name', type(system.embed_model).__name__)
    logger.info(f"IngestionPipeline completed in {chunk_duration:.2f}s — {len(nodes)} nodes, embed={embed_model_name}")
    logger.info(f"  Chunk size: {system.config.chunk_size}, overlap: {system.config.chunk_overlap}")
    logger.info(f"  Avg nodes/doc: {len(nodes)/len(documents):.2f}")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 3: Vector index
    _update_progress("Building vector index...", 50, current_phase="indexing")
    vector_duration = await update_vector(system, nodes, loop, ingest_mode="refresh")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 3.5: Search index
    _update_progress("Building search index...", 55, current_phase="search_indexing")
    search_duration = await update_search(system, nodes, loop, ingest_mode="refresh")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 3.6: OpenArch content repository (ENABLE_OPENARCH)
    if getattr(system, "openarch_store", None) is not None:
        _update_progress("Writing documents to OpenArch...", 62, current_phase="openarch_indexing")
        await update_openarch(system, nodes, documents)
        if _check_cancellation(processing_id):
            raise RuntimeError("Processing cancelled by user")

    # Step 4: PG graph
    _update_progress("Extracting knowledge graph...", 70, current_phase="kg_extraction")
    # which graphs this ingest builds (graph_flags.py; skip_graph is the older single flag)
    from graph_flags import GraphFlags
    flags = graphs if graphs is not None else GraphFlags.of(
        skip_graph, default=GraphFlags.defaults(system.config))

    nodes, nodes_kg_extracted, kg_duration, graph_duration, _, _ = await update_pg_graph(
        system, nodes, documents, loop, graphs=flags,
    )
    if not system.graph_intentionally_skipped:
        _update_progress("Knowledge graph ready", 78, current_phase="kg_extraction")

    # Step 4b: RDF graph
    if flags.rdf and str(getattr(system.config, "rdf_graph_db", "none")) != "none":
        _update_progress("Writing RDF graph…", 85, current_phase="rdf_indexing")
    rdf_kg_duration, rdf_store_duration = await update_rdf_graph(
        system, nodes, nodes_kg_extracted=nodes_kg_extracted, graphs=flags
    )

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 5: Setup hybrid retriever + persist
    setup_hybrid_retriever(system)
    await warmup_hybrid_retriever(system)
    persist_indexes(system.config, system.vector_index, system.graph_index)

    total_duration = time.time() - _ingest_start
    timing_summary = (
        f"{total_duration:.2f}s — Chunk: {chunk_duration:.2f}s, "
        f"Vector: {vector_duration:.2f}s, Search: {search_duration:.2f}s, "
        f"KG: {kg_duration + rdf_kg_duration:.2f}s, "
        f"Graph: {graph_duration:.2f}s, RDF: {rdf_store_duration:.2f}s"
    )
    logger.info(f"Document ingestion completed in {timing_summary}")

    if OBSERVABILITY_AVAILABLE and get_rag_metrics:
        try:
            m = get_rag_metrics()
            m.record_document_processing(latency_ms=chunk_duration * 1000, num_chunks=len(nodes))
            if system.vector_store and vector_duration > 0:
                m.record_vector_indexing(latency_ms=vector_duration * 1000, num_vectors=len(nodes))
            try:
                from opentelemetry import metrics as otel_metrics
                mp = otel_metrics.get_meter_provider()
                if hasattr(mp, 'force_flush'):
                    mp.force_flush(timeout_millis=5000)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Failed to record ingestion metrics: {e}")

    if status_callback:
        from backend import PROCESSING_STATUS
        data_source = PROCESSING_STATUS.get(processing_id, {}).get("data_source") or "filesystem"
        file_count = PROCESSING_STATUS.get(processing_id, {}).get("file_count")
        chunk_count = PROCESSING_STATUS.get(processing_id, {}).get("chunk_count")
        logger.info(f"Completion - data_source={data_source!r}, file_count={file_count}, chunk_count={chunk_count}")

        if data_source == "youtube":
            doc_count = 1
        elif file_count and chunk_count and file_count != chunk_count:
            doc_count = file_count
        else:
            doc_count = len(documents)

        ui_message = generate_completion_message(system.config, doc_count, graphs=flags)
        logger.info(f"Ingestion complete: {ui_message} ({timing_summary})")
        status_callback(
            processing_id=processing_id,
            status="completed",
            message=ui_message,
            progress=100,
        )
