"""
File-path ingestion entry point for Flexible GraphRAG.

ingest_documents — takes a list of file paths, runs DocumentProcessor
                   (Docling/LlamaParse), then the full pipeline:
                   chunk, embed, vector index, graph index, search index.

For raw text see ingest/ingest_from_text.py.
For pre-loaded Document objects see ingest/ingest_from_source.py.
"""

import functools
import time
from pathlib import Path
from typing import List, Union
import logging

from llama_index.core import StorageContext, VectorStoreIndex, Document
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


async def ingest_documents(
    system,
    file_paths: List[Union[str, Path]],
    processing_id: str = None,
    status_callback=None,
    skip_graph: bool = False,
):
    """Process and ingest documents from file paths into all search modalities.

    Args:
        system: HybridSearchSystem instance
        file_paths: List of file paths to ingest
        processing_id: Optional ID for cancellation/progress tracking
        status_callback: Optional callable(processing_id, status, message, progress, ...)
        skip_graph: If True, skip KG extraction for this ingest (temporary override)
    """
    from retriever_setup import setup_hybrid_retriever
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

    # Step 1: Convert documents via DocumentProcessor (Docling / LlamaParse)
    logger.info("Converting documents with Docling...")
    _update_progress("Converting documents with Docling...", 20, current_phase="docling")
    documents = await system.document_processor.process_documents(file_paths, processing_id=processing_id)
    if not documents:
        raise ValueError("No documents were successfully processed")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 2: Chunk + embed — single canonical pipeline
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

    pipeline_start = time.time()
    pipeline = build_ingestion_pipeline(system.config, system.embed_model)
    loop = _get_loop()
    run_pipeline = functools.partial(pipeline.run, documents=documents)
    nodes = await loop.run_in_executor(None, run_pipeline)
    pipeline_duration = time.time() - pipeline_start

    embed_model_name = getattr(system.embed_model, 'model_name', type(system.embed_model).__name__)
    logger.info(f"IngestionPipeline completed in {pipeline_duration:.2f}s — {len(nodes)} nodes, embed={embed_model_name}")
    logger.info(f"  Chunk size: {system.config.chunk_size}, overlap: {system.config.chunk_overlap}")
    logger.info(f"  Avg nodes/doc: {len(nodes)/len(documents):.2f}")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 3: Vector index
    vector_duration = 0
    if system.vector_store is not None:
        vector_start = time.time()
        vector_store_type = type(system.vector_store).__name__
        logger.info(f"Updating vector index with {len(nodes)} nodes ({vector_store_type})")
        _update_progress("Building vector index...", 50, current_phase="indexing")

        if system.vector_index is None:
            vector_storage_context = StorageContext.from_defaults(vector_store=system.vector_store)
            create_vi = functools.partial(
                VectorStoreIndex,
                nodes=nodes,
                storage_context=vector_storage_context,
                show_progress=True,
            )
            system.vector_index = await loop.run_in_executor(None, create_vi)
        else:
            system.vector_index.refresh_ref_docs(
                [Document(text=n.text, metadata=n.metadata) for n in nodes if hasattr(n, 'text')]
            )

        vector_duration = time.time() - vector_start
        logger.info(f"Vector index updated in {vector_duration:.2f}s")
    else:
        logger.info("Vector search disabled - skipping vector index creation")
        _update_progress("Vector search disabled - skipping...", 50, current_phase="indexing")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 3.5: Search index (Elasticsearch / OpenSearch)
    if system.search_store is not None:
        search_start = time.time()
        _update_progress("Building search index...", 55, current_phase="search_indexing")
        if not hasattr(system, 'search_index') or system.search_index is None:
            search_sc = StorageContext.from_defaults(vector_store=system.search_store)
            create_si = functools.partial(VectorStoreIndex, nodes=nodes, storage_context=search_sc, show_progress=True)
            system.search_index = await loop.run_in_executor(None, create_si)
        else:
            system.search_index.refresh_ref_docs(
                [Document(text=n.text, metadata=n.metadata) for n in nodes if hasattr(n, 'text')]
            )
        logger.info(f"Search index updated in {time.time()-search_start:.2f}s")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Step 4: Knowledge graph
    should_skip_graph = str(system.config.graph_db) == "none" or skip_graph or not system.config.enable_knowledge_graph
    graph_creation_duration = 0

    if should_skip_graph:
        if skip_graph and system.config.enable_knowledge_graph:
            logger.info("Knowledge graph SKIPPED (per-ingest skip_graph flag)")
            _update_progress("Skipping knowledge graph extraction...", 70, current_phase="kg_extraction")
            system.graph_intentionally_skipped = True
        elif not system.config.enable_knowledge_graph:
            logger.info("Knowledge graph disabled in config")
            _update_progress("Skipping knowledge graph extraction...", 70, current_phase="kg_extraction")
            system.graph_index = None
            system.graph_intentionally_skipped = False
    else:
        system.graph_intentionally_skipped = False
        graph_store_type = type(system.graph_store).__name__
        llm_model_name = getattr(system.llm, 'model', type(system.llm).__name__)

        logger.info(f"Creating graph index from {len(nodes)} nodes ({graph_store_type}, LLM: {llm_model_name})")
        _update_progress("Extracting knowledge graph...", 70, current_phase="kg_extraction")

        kg_extractor = system.schema_manager.create_extractor(
            system.llm,
            llm_provider=system.config.llm_provider,
            extractor_type=system.config.kg_extractor_type,
        )
        graph_storage_context = StorageContext.from_defaults(
            property_graph_store=system.graph_store,
            docstore=system.vector_index.docstore,
        )

        # Pass transformations=[] so LlamaIndex does NOT re-chunk — nodes are already chunked.
        graph_index_kwargs = {
            "documents": documents,
            "llm": system.llm,
            "embed_model": system.embed_model,
            "kg_extractors": [kg_extractor],
            "storage_context": graph_storage_context,
            "transformations": [],
            "show_progress": True,
            "include_embeddings": True,
            "include_metadata": True,
            "use_async": False,
        }
        if hasattr(system.graph_store, '__class__') and 'NeptuneAnalytics' in str(system.graph_store.__class__):
            graph_index_kwargs["embed_kg_nodes"] = False
            logger.info("Neptune Analytics detected: embed_kg_nodes=False")

        graph_span = None
        token = None
        graph_creation_start = time.time()

        if OBSERVABILITY_AVAILABLE:
            try:
                from opentelemetry import context as otel_ctx, trace as otel_trace
                tracer = get_tracer(__name__)
                graph_span = tracer.start_span("rag.graph_extraction")
                graph_span.set_attribute("graph.num_documents", len(documents))
                graph_span.set_attribute("graph.llm_model", llm_model_name)
                graph_span.set_attribute("graph.database_type", graph_store_type)
                graph_span.set_attribute("graph.extractor_type", system.config.kg_extractor_type)
                ctx = otel_trace.set_span_in_context(graph_span)
                token = otel_ctx.attach(ctx)
            except Exception as e:
                logger.debug(f"OTel span setup failed: {e}")

        try:
            create_gi = functools.partial(PropertyGraphIndex.from_documents, **graph_index_kwargs)
            system.graph_index = await loop.run_in_executor(None, create_gi)
            graph_creation_duration = time.time() - graph_creation_start
            logger.info(f"PropertyGraphIndex creation completed in {graph_creation_duration:.2f}s")

            num_entities, num_relations = 0, 0
            try:
                if hasattr(system.graph_index, 'property_graph_store'):
                    pg_store = system.graph_index.property_graph_store
                    if hasattr(pg_store, 'get_triplets'):
                        triplets = pg_store.get_triplets()
                        if triplets:
                            unique_entities = set()
                            for t in triplets:
                                if hasattr(t, 'subject_id'): unique_entities.add(t.subject_id)
                                if hasattr(t, 'object_id'): unique_entities.add(t.object_id)
                            num_entities = len(unique_entities)
                            num_relations = len(triplets)
                    if num_entities == 0 and hasattr(pg_store, 'get_schema'):
                        schema = pg_store.get_schema(refresh=True)
                        if isinstance(schema, dict):
                            num_entities = len(schema.get('nodes', []))
                            num_relations = len(schema.get('relationships', []))
            except Exception as cnt_err:
                logger.debug(f"Could not count graph entities: {cnt_err}")

            logger.info(f"Graph extraction: {num_entities} entities, {num_relations} relations in {graph_creation_duration:.2f}s")

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
            if token is not None:
                try:
                    from opentelemetry import context as otel_ctx
                    otel_ctx.detach(token)
                except Exception: pass

        if _check_cancellation(processing_id):
            raise RuntimeError("Processing cancelled by user")

    # Step 5: Setup hybrid retriever + persist
    setup_hybrid_retriever(system)
    persist_indexes(system.config, system.vector_index, system.graph_index)

    total_duration = time.time() - pipeline_start

    logger.info(f"Document ingestion completed in {total_duration:.2f}s — Pipeline: {pipeline_duration:.2f}s, Vector: {vector_duration:.2f}s, Graph: {graph_creation_duration:.2f}s")

    if OBSERVABILITY_AVAILABLE and get_rag_metrics:
        try:
            m = get_rag_metrics()
            m.record_document_processing(latency_ms=pipeline_duration * 1000, num_chunks=len(nodes))
            if system.vector_store and vector_duration > 0:
                m.record_vector_indexing(latency_ms=vector_duration * 1000, num_vectors=len(nodes))
            try:
                from opentelemetry import metrics as otel_metrics
                mp = otel_metrics.get_meter_provider()
                if hasattr(mp, 'force_flush'):
                    mp.force_flush(timeout_millis=5000)
            except Exception: pass
        except Exception as e:
            logger.warning(f"Failed to record ingestion metrics: {e}")

    if status_callback:
        from backend import PROCESSING_STATUS
        data_source = PROCESSING_STATUS.get(processing_id, {}).get("data_source", "")
        file_count = PROCESSING_STATUS.get(processing_id, {}).get("file_count")
        chunk_count = PROCESSING_STATUS.get(processing_id, {}).get("chunk_count")
        logger.info(f"Completion - data_source={data_source!r}, file_count={file_count}, chunk_count={chunk_count}")

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
