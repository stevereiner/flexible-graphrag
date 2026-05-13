"""
Source-document ingestion entry point for Flexible GraphRAG.

ingest_source_documents — takes pre-loaded Document objects from data sources
                          (web, YouTube, Wikipedia, S3, incremental updates)
                          and runs the full pipeline: chunk, embed, vector
                          index, graph index, search index.

For file paths see ingest/ingest_from_files.py.
For raw text see ingest/ingest_from_text.py.
"""

import time
from typing import List
import logging

from ingest._helpers import _check_cancellation, _get_loop, generate_completion_message
from ingest.run_chunk_pipeline import run_chunk_pipeline
from ingest.update_vector import update_vector
from ingest.update_search import update_search
from ingest.update_pg_graph import update_pg_graph
from ingest.update_rdf_graph import update_rdf_graph

logger = logging.getLogger(__name__)

try:
    from observability.metrics import get_rag_metrics
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    get_rag_metrics = None


# ---------------------------------------------------------------------------
# Stable doc-id assignment (incremental sync helper)
# ---------------------------------------------------------------------------

def _assign_stable_doc_ids(documents: List, config_id: str) -> None:
    """Assign stable config_id-prefixed doc_ids to documents in-place.

    Called when config_id is provided so that the incremental update engine
    can consistently locate and replace documents across re-ingestions.
    """
    logger.info(f"Setting stable doc_id for {len(documents)} documents (config_id={config_id})")
    for doc in documents:
        if hasattr(doc, 'id_') and doc.id_ and str(doc.id_).startswith(f"{config_id}:"):
            logger.info(f"  Document already has doc_id: {doc.id_} - skipping")
            continue

        file_name = doc.metadata.get('file_name', '')
        file_path = doc.metadata.get('file_path', '')
        source_type = doc.metadata.get('source', '')
        stable_doc_id = None

        if source_type == 'google_drive':
            gd_file_id = doc.metadata.get('file id', '')
            if gd_file_id:
                stable_doc_id = f"{config_id}:{gd_file_id}"
        elif source_type == 'azure_blob' or doc.metadata.get('container_name'):
            container = doc.metadata.get('container', doc.metadata.get('container_name', ''))
            blob = doc.metadata.get('name', '')
            if container and blob:
                stable_doc_id = f"{config_id}:{container}/{blob}"
            elif file_path:
                stable_doc_id = f"{config_id}:{file_path}"
            else:
                stable_doc_id = f"{config_id}:{file_name}"
        elif source_type == 's3' or doc.metadata.get('s3_uri'):
            s3_uri = doc.metadata.get('s3_uri', '')
            if s3_uri:
                stable_doc_id = f"{config_id}:{s3_uri}"
            else:
                bucket = doc.metadata.get('bucket_name', '')
                key = doc.metadata.get('s3_key', file_name)
                stable_doc_id = f"{config_id}:s3://{bucket}/{key}" if bucket else f"{config_id}:{key}"
        elif source_type == 'gcs' or doc.metadata.get('bucket_name'):
            bucket = doc.metadata.get('bucket_name', '')
            key = file_path if file_path else file_name
            stable_doc_id = f"{config_id}:{bucket}/{key}" if bucket else f"{config_id}:{key}"
        elif source_type == 'box':
            path_collection = doc.metadata.get('path_collection', '')
            name = doc.metadata.get('name', file_name)
            sep = '' if path_collection.endswith('/') else '/'
            stable_doc_id = f"{config_id}:{path_collection}{sep}{name}" if path_collection else f"{config_id}:{name}"
        elif source_type == 'alfresco':
            stable_fp = doc.metadata.get('stable_file_path', '')
            if stable_fp:
                stable_doc_id = f"{config_id}:{stable_fp}"
            elif doc.metadata.get('alfresco_id'):
                stable_doc_id = f"{config_id}:alfresco://{doc.metadata['alfresco_id']}"
            elif file_path:
                stable_doc_id = f"{config_id}:{file_path}"
            else:
                stable_doc_id = f"{config_id}:{file_name}"
        elif source_type in ['onedrive', 'sharepoint']:
            stable_fp = doc.metadata.get('stable_file_path', '')
            stable_doc_id = f"{config_id}:{stable_fp}" if stable_fp else (
                f"{config_id}:{file_path}" if file_path else f"{config_id}:{file_name}"
            )
        elif file_path:
            # Normalize filesystem paths on Windows so the doc_id stored in metadata
            # and vector stores matches what the filesystem detector produces (lowercase).
            # Without this, LanceDB/Milvus/Chroma store "C:\..." but delete gets "c:\...".
            try:
                from incremental_updates.path_utils import normalize_filesystem_path
                _norm_path = normalize_filesystem_path(file_path)
            except Exception:
                _norm_path = file_path
            stable_doc_id = f"{config_id}:{_norm_path}"
        elif file_name:
            stable_doc_id = f"{config_id}:{file_name}"
        else:
            logger.warning("  No file_name/file_path in metadata, skipping doc_id assignment")
            continue

        doc.id_ = stable_doc_id
        doc.metadata['doc_id'] = stable_doc_id
        logger.info(f"  Set stable doc_id: {stable_doc_id}")


# ---------------------------------------------------------------------------
# ingest_source_documents
# ---------------------------------------------------------------------------

async def ingest_source_documents(
    system,
    documents: List,
    processing_id: str = None,
    status_callback=None,
    skip_graph: bool = False,
    config_id: str = None,
):
    """Process a list of pre-fetched documents into all search modalities.

    Used by web, YouTube, Wikipedia sources and the incremental update engine.
    Unlike ingest_documents (which takes file paths), this function receives
    Document objects that have already been fetched/parsed by a data source.

    Args:
        system: HybridSearchSystem instance
        documents: List of LlamaIndex Document objects
        processing_id: Optional ID for cancellation/progress tracking
        status_callback: Optional callable for progress updates
        skip_graph: If True, skip KG extraction for this ingest
        config_id: Optional stable config_id for incremental sync (assigns stable doc_ids)
    """
    from retriever_setup import setup_hybrid_retriever

    logger.info(f"Processing {len(documents)} documents directly...")
    start_time = time.time()

    if config_id:
        _assign_stable_doc_ids(documents, config_id)

    system._last_ingested_documents = documents
    logger.info(f"=== PRE-CHUNKING: {len(documents)} Documents ===")
    for i, doc in enumerate(documents[:5]):
        logger.info(f"  Doc[{i}] length: {len(doc.text)} chars, metadata: {doc.metadata}")
    if len(documents) > 5:
        logger.info(f"  ... and {len(documents)-5} more documents")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 1: Chunk + embed
    loop = _get_loop()
    nodes, chunk_duration = await run_chunk_pipeline(system, documents, loop)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 2: Vector index
    vector_duration = await update_vector(system, nodes, loop)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 3: Search index
    search_duration = await update_search(system, nodes, loop)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 4: PG graph
    nodes, nodes_kg_extracted, kg_duration, graph_duration, _, _ = await update_pg_graph(
        system, nodes, documents, loop, skip_graph=skip_graph
    )

    # Step 4b: RDF graph
    rdf_kg_duration, rdf_store_duration = await update_rdf_graph(system, nodes, nodes_kg_extracted=nodes_kg_extracted, skip_graph=skip_graph)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    setup_hybrid_retriever(system)

    total_duration = time.time() - start_time
    logger.info(
        f"Direct document processing completed in {total_duration:.2f}s — "
        f"Chunk: {chunk_duration:.2f}s, Vector: {vector_duration:.2f}s, "
        f"Search: {search_duration:.2f}s, KG: {kg_duration + rdf_kg_duration:.2f}s, "
        f"Graph: {graph_duration:.2f}s, RDF: {rdf_store_duration:.2f}s"
    )

    if OBSERVABILITY_AVAILABLE and get_rag_metrics:
        try:
            m = get_rag_metrics()
            if chunk_duration > 0:
                m.record_document_processing(latency_ms=chunk_duration * 1000, num_chunks=len(nodes))
            if vector_duration > 0:
                m.record_vector_indexing(latency_ms=vector_duration * 1000, num_vectors=len(nodes))
            try:
                from opentelemetry import metrics as otel_metrics
                mp = otel_metrics.get_meter_provider()
                if hasattr(mp, 'force_flush'):
                    mp.force_flush(timeout_millis=5000)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Failed to record processing metrics: {e}")

    if status_callback:
        from backend import PROCESSING_STATUS
        data_source = PROCESSING_STATUS.get(processing_id, {}).get("data_source", "")
        file_count = PROCESSING_STATUS.get(processing_id, {}).get("file_count")
        chunk_count = PROCESSING_STATUS.get(processing_id, {}).get("chunk_count")
        logger.info(f"Completion (_direct) — data_source={data_source!r}, file_count={file_count}")

        if data_source == "youtube":
            doc_count = 1
        elif file_count and chunk_count and file_count != chunk_count:
            doc_count = file_count
        else:
            doc_count = len(documents)

        status_callback(
            processing_id=processing_id,
            status="completed",
            message=generate_completion_message(system.config, doc_count, skip_graph=skip_graph),
            progress=100,
        )
