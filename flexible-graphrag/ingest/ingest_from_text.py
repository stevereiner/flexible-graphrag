"""
Raw-text ingestion entry point for Flexible GraphRAG.

ingest_text — wraps a raw string as a Document and runs the full pipeline
              (chunk, embed, vector index, graph index, search index).
"""

import functools
import logging

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.indices.property_graph import PropertyGraphIndex

from process.node_pipeline import build_ingestion_pipeline
from ingest._helpers import _check_cancellation, _get_loop

logger = logging.getLogger(__name__)


async def ingest_text(system, content: str, source_name: str = "text_input", processing_id: str = None):
    """Ingest raw text content.

    Args:
        system: HybridSearchSystem instance
        content: Raw text to ingest
        source_name: Display name for the text source
        processing_id: Optional ID for cancellation checking
    """
    from retriever_setup import setup_hybrid_retriever

    logger.info(f"Ingesting text content from: {source_name}")

    document = system.document_processor.process_text_content(content, source_name)

    if not hasattr(system, '_last_ingested_documents') or system._last_ingested_documents is None:
        system._last_ingested_documents = []
    system._last_ingested_documents.append(document)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Chunk + embed via canonical pipeline
    pipeline = build_ingestion_pipeline(system.config, system.embed_model)
    loop = _get_loop()
    run_pipeline = functools.partial(pipeline.run, documents=[document])
    nodes = await loop.run_in_executor(None, run_pipeline)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Vector index
    if system.vector_index is None:
        storage_context = StorageContext.from_defaults(vector_store=system.vector_store)
        create_vi = functools.partial(
            VectorStoreIndex,
            nodes=nodes,
            storage_context=storage_context,
            show_progress=False,
        )
        system.vector_index = await loop.run_in_executor(None, create_vi)
    else:
        system.vector_index.insert_nodes(nodes)

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Graph index
    kg_extractor = system.schema_manager.create_extractor(
        system.llm,
        llm_provider=system.config.llm_provider,
        extractor_type=system.config.kg_extractor_type,
    )

    storage_mode = getattr(system.config, "ingestion_storage_mode", "property_graph")

    # Run KG extraction on pre-chunked nodes (same pattern as ingest_from_source)
    from process.kg_extractor import run_kg_extractors_on_nodes
    nodes, num_entities, num_relations, _ = await run_kg_extractors_on_nodes(
        nodes, [kg_extractor], system.config, span_name="rag.graph_extraction.text"
    )
    logger.info(f"Text KG extraction complete: {num_entities} entities, {num_relations} relations")

    if storage_mode in ("rdf_only", "both"):
        from stores.index_manager import export_nodes_to_rdf_stores
        export_nodes_to_rdf_stores(nodes, system.config, schema_manager=system.schema_manager)

    if storage_mode != "rdf_only":
        graph_storage_context = StorageContext.from_defaults(property_graph_store=system.graph_store)
        if system.graph_index is None:
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
            create_gi = functools.partial(PropertyGraphIndex, **graph_kwargs)
            system.graph_index = await loop.run_in_executor(None, create_gi)
            logger.info(f"PropertyGraphIndex created from text nodes")
        else:
            _orig_extractors = system.graph_index._kg_extractors
            _orig_use_async = getattr(system.graph_index, '_use_async', False)
            system.graph_index._kg_extractors = []
            system.graph_index._use_async = False
            try:
                system.graph_index.insert_nodes(nodes)
            finally:
                system.graph_index._kg_extractors = _orig_extractors
                system.graph_index._use_async = _orig_use_async

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    # Search index
    if system.search_store is not None:
        if not hasattr(system, 'search_index') or system.search_index is None:
            search_sc = StorageContext.from_defaults(vector_store=system.search_store)
            create_si = functools.partial(VectorStoreIndex, nodes=nodes, storage_context=search_sc, show_progress=True)
            system.search_index = await loop.run_in_executor(None, create_si)
        else:
            node_ids = await system.search_store.async_add(nodes)
            logger.info(f"Added {len(node_ids)} nodes to search store via async_add")

    if _check_cancellation(processing_id):
        raise RuntimeError("Processing cancelled by user")

    setup_hybrid_retriever(system)
    logger.info("Text content ingestion completed successfully!")
