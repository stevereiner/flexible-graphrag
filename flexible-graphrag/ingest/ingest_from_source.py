"""
Source-document ingestion entry point for Flexible GraphRAG.

ingest_source_documents — takes pre-loaded Document objects from data sources
                          (web, YouTube, Wikipedia, S3, incremental updates)
                          and runs the full pipeline: chunk, embed, vector
                          index, graph index, search index.

For file paths see ingest/ingest_from_files.py.
For raw text see ingest/ingest_from_text.py.
"""

import asyncio
import functools
import time
from typing import List
import logging

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.indices.property_graph import PropertyGraphIndex

from process.node_pipeline import build_ingestion_pipeline
from ingest._helpers import _check_cancellation, _get_loop, generate_completion_message

logger = logging.getLogger(__name__)

try:
    from observability import get_tracer
    from observability.metrics import get_rag_metrics
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    get_tracer = None
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
            stable_doc_id = f"{config_id}:{file_path}"
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
    from stores.index_manager import export_nodes_to_rdf_stores

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

    # Step 1: Chunk + embed — single canonical pipeline
    pipeline_start = time.time()
    pipeline = build_ingestion_pipeline(system.config, system.embed_model)
    loop = _get_loop()
    run_pipeline = functools.partial(pipeline.run, documents=documents)
    nodes = await loop.run_in_executor(None, run_pipeline)
    pipeline_duration = time.time() - pipeline_start

    logger.info(f"IngestionPipeline: {pipeline_duration:.2f}s, {len(nodes)} nodes from {len(documents)} docs")
    logger.info(f"  Chunk size: {system.config.chunk_size}, overlap: {system.config.chunk_overlap}")
    for i, node in enumerate(nodes[:5]):
        logger.info(f"  Node[{i}] {len(node.text)} chars, metadata: {node.metadata}")
    if len(nodes) > 5:
        logger.info(f"  ... and {len(nodes)-5} more nodes")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 2: Vector index
    vector_duration = 0
    if system.vector_store is not None:
        vector_start = time.time()
        vector_store_type = type(system.vector_store).__name__
        logger.info(f"Creating vector index from {len(nodes)} nodes ({vector_store_type})")

        if system.vector_index is None:
            sc = StorageContext.from_defaults(vector_store=system.vector_store)
            create_vi = functools.partial(VectorStoreIndex, nodes=nodes, storage_context=sc, show_progress=False)
            system.vector_index = await loop.run_in_executor(None, create_vi)
        else:
            if (type(system.vector_store).__name__ == "WeaviateVectorStore" and
                    hasattr(system.vector_store, '_aclient') and system.vector_store._aclient is not None):
                if not system.vector_store._aclient.is_connected():
                    await system.vector_store._aclient.connect()
                node_ids = await system.vector_store.async_add(nodes)
                logger.info(f"Added {len(node_ids)} nodes to Weaviate via async_add")
            else:
                await loop.run_in_executor(None, system.vector_index.insert_nodes, nodes)

        vector_duration = time.time() - vector_start
        logger.info(f"Vector index: {vector_duration:.2f}s")
    else:
        logger.info("Vector search disabled")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 2.5: Search index
    search_duration = 0
    if system.search_store is not None:
        search_start = time.time()
        search_store_type = type(system.search_store).__name__
        logger.info(f"Creating search index from {len(nodes)} nodes ({search_store_type})")

        if not hasattr(system, 'search_index') or system.search_index is None:
            search_sc = StorageContext.from_defaults(vector_store=system.search_store)
            create_si = functools.partial(VectorStoreIndex, nodes=nodes, storage_context=search_sc, show_progress=False)
            system.search_index = await loop.run_in_executor(None, create_si)
        else:
            node_ids = await system.search_store.async_add(nodes)
            logger.info(f"Added {len(node_ids)} nodes to {search_store_type} via async_add")

        search_duration = time.time() - search_start
        logger.info(f"Search index: {search_duration:.2f}s")
    else:
        logger.info("Search database not configured")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 3: Knowledge graph
    logger.info(f"skip_graph={skip_graph}, graph_db={system.config.graph_db}, enable_kg={system.config.enable_knowledge_graph}")
    should_skip_graph = str(system.config.graph_db) == "none" or skip_graph or not system.config.enable_knowledge_graph
    graph_creation_duration = 0

    if should_skip_graph:
        if skip_graph and system.config.enable_knowledge_graph:
            logger.info("Knowledge graph SKIPPED (per-ingest skip_graph flag)")
            system.graph_intentionally_skipped = True
        elif not system.config.enable_knowledge_graph:
            logger.info("Knowledge graph disabled in config")
            system.graph_index = None
            system.graph_intentionally_skipped = False

        # Standalone RDF export when GRAPH_DB=none but rdf_only mode is active
        storage_mode = getattr(system.config, "ingestion_storage_mode", "property_graph")
        if storage_mode in ("rdf_only", "both") and getattr(system.config, "use_langchain_rdf", False):
            logger.info("rdf_only/both + GRAPH_DB=none: running standalone KG extraction for RDF export")
            try:
                rdf_nodes = list(nodes)
                kg_extractor = system.schema_manager.create_extractor(
                    system.llm,
                    llm_provider=system.config.llm_provider,
                    extractor_type=system.config.kg_extractor_type,
                )
                from process.kg_extractor import run_kg_extractors_on_nodes
                rdf_nodes, num_entities, num_relations, _ = await run_kg_extractors_on_nodes(
                    rdf_nodes, [kg_extractor], system.config, span_name="rag.graph_extraction.rdf_only"
                )
                logger.info(f"Standalone RDF extraction: {num_entities} entities, {num_relations} relations")
                export_nodes_to_rdf_stores(rdf_nodes, system.config, schema_manager=system.schema_manager)
            except Exception as rdf_exc:
                logger.error("Standalone RDF export failed: %s", rdf_exc, exc_info=True)
    else:
        # Knowledge graph is enabled and not skipped
        system.graph_intentionally_skipped = False
        graph_store_type = type(system.graph_store).__name__
        llm_model_name = getattr(system.llm, 'model', type(system.llm).__name__)

        kg_extractor = system.schema_manager.create_extractor(
            system.llm,
            llm_provider=system.config.llm_provider,
            extractor_type=system.config.kg_extractor_type,
        )
        logger.info(f"KG extractor setup for {graph_store_type}, LLM: {llm_model_name}")

        if system.graph_index is None:
            graph_storage_context = StorageContext.from_defaults(property_graph_store=system.graph_store)
            graph_creation_start = time.time()
            logger.info(f"New PropertyGraphIndex — {len(nodes)} pre-chunked nodes, LLM={llm_model_name}")

            graph_span = None
            if OBSERVABILITY_AVAILABLE:
                try:
                    tracer = get_tracer(__name__)
                    graph_span = tracer.start_span("rag.graph_extraction.create")
                    graph_span.set_attribute("graph.num_documents", len(documents))
                    graph_span.set_attribute("graph.llm_model", llm_model_name)
                    graph_span.set_attribute("graph.database_type", graph_store_type)
                    graph_span.set_attribute("graph.extractor_type", system.config.kg_extractor_type)
                except Exception:
                    graph_span = None

            try:
                from process.kg_extractor import run_kg_extractors_on_nodes
                nodes, num_entities, num_relations, _ = await run_kg_extractors_on_nodes(
                    nodes, [kg_extractor], system.config, span_name="rag.graph_extraction.create"
                )

                storage_mode = getattr(system.config, "ingestion_storage_mode", "property_graph")
                if storage_mode in ("rdf_only", "both"):
                    export_nodes_to_rdf_stores(nodes, system.config, schema_manager=system.schema_manager)

                if storage_mode == "rdf_only":
                    system.graph_index = None
                    graph_creation_duration = time.time() - graph_creation_start
                    logger.info(f"rdf_only: skipped PropertyGraphIndex, {num_entities} entities -> RDF stores")
                else:
                    graph_kwargs = {
                        "nodes": nodes,
                        "llm": system.llm,
                        "embed_model": system.embed_model,
                        "kg_extractors": [],
                        "property_graph_store": system.graph_store,
                        "storage_context": graph_storage_context,
                    }
                    if hasattr(system.graph_store, '__class__') and 'NeptuneAnalytics' in str(system.graph_store.__class__):
                        graph_kwargs["embed_kg_nodes"] = False
                    logger.info("Creating PropertyGraphIndex with pre-extracted nodes")
                    system.graph_index = PropertyGraphIndex(**graph_kwargs)
                    graph_creation_duration = time.time() - graph_creation_start
                    logger.info(f"PropertyGraphIndex created in {graph_creation_duration:.2f}s — {num_entities} entities, {num_relations} relations")

                if graph_span:
                    graph_span.set_attribute("graph.extraction_latency_ms", graph_creation_duration * 1000)
                    graph_span.set_attribute("graph.num_entities", num_entities)
                    graph_span.set_attribute("graph.num_relations", num_relations)
                    graph_span.set_attribute("graph.status", "success")

                if OBSERVABILITY_AVAILABLE and get_rag_metrics:
                    try:
                        get_rag_metrics().record_graph_extraction(
                            latency_ms=graph_creation_duration * 1000,
                            num_entities=num_entities,
                            num_relations=num_relations,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record graph metrics: {e}")

            except Exception as e:
                graph_creation_duration = time.time() - graph_creation_start
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

        else:
            # Update existing graph index
            graph_update_start = time.time()
            logger.info("Adding new documents to existing graph index...")

            graph_span = None
            if OBSERVABILITY_AVAILABLE:
                try:
                    tracer = get_tracer(__name__)
                    graph_span = tracer.start_span("rag.graph_extraction.update")
                    graph_span.set_attribute("graph.num_documents", len(documents))
                    graph_span.set_attribute("graph.database_type", graph_store_type)
                except Exception:
                    graph_span = None

            try:
                from process.kg_extractor import run_kg_extractors_on_nodes
                nodes, num_entities, num_relations, _ = await run_kg_extractors_on_nodes(
                    nodes, [kg_extractor], system.config, span_name="rag.graph_extraction.update"
                )
                logger.info(f"Inserting {len(nodes)} nodes with {num_entities} entities, {num_relations} relations")

                storage_mode = getattr(system.config, "ingestion_storage_mode", "property_graph")
                if storage_mode in ("rdf_only", "both"):
                    export_nodes_to_rdf_stores(nodes, system.config, schema_manager=system.schema_manager)

                if storage_mode != "rdf_only":
                    _orig_extractors = system.graph_index._kg_extractors
                    _orig_use_async = getattr(system.graph_index, '_use_async', False)
                    system.graph_index._kg_extractors = []
                    system.graph_index._use_async = False
                    try:
                        system.graph_index.insert_nodes(nodes)
                    finally:
                        system.graph_index._kg_extractors = _orig_extractors
                        system.graph_index._use_async = _orig_use_async

                graph_creation_duration = time.time() - graph_update_start
                logger.info(f"Graph index update: {graph_creation_duration:.2f}s")

                if graph_span:
                    graph_span.set_attribute("graph.update_latency_ms", graph_creation_duration * 1000)
                    graph_span.set_attribute("graph.num_entities", num_entities)
                    graph_span.set_attribute("graph.num_relations", num_relations)
                    graph_span.set_attribute("graph.status", "success")

                if OBSERVABILITY_AVAILABLE and get_rag_metrics:
                    try:
                        get_rag_metrics().record_graph_extraction(
                            latency_ms=graph_creation_duration * 1000,
                            num_entities=num_entities,
                            num_relations=num_relations,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record graph metrics: {e}")

            except Exception as e:
                graph_creation_duration = time.time() - graph_update_start
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

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    setup_hybrid_retriever(system)

    total_duration = time.time() - start_time
    logger.info(
        f"Direct document processing completed in {total_duration:.2f}s — "
        f"Pipeline: {pipeline_duration:.2f}s, Vector: {vector_duration:.2f}s, Graph: {graph_creation_duration:.2f}s"
    )

    if OBSERVABILITY_AVAILABLE and get_rag_metrics:
        try:
            m = get_rag_metrics()
            if pipeline_duration > 0:
                m.record_document_processing(latency_ms=pipeline_duration * 1000, num_chunks=len(nodes))
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
