"""
Shared search index upsert step for all ingest entry points.
"""

import functools
import logging
import time

from llama_index.core import StorageContext, VectorStoreIndex

logger = logging.getLogger(__name__)

try:
    from observability import get_tracer
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    get_tracer = None

# ingest_mode values (mirrors update_vector)
INSERT = "insert"    # additive append — async_add (source, text)
REFRESH = "refresh"  # update by doc_id then add new — refresh_ref_docs (files re-ingest)


async def update_search(
    system,
    nodes: list,
    loop,
    *,
    ingest_mode: str = INSERT,
) -> float:
    """Upsert nodes into the configured search store / index.

    ingest_mode="insert"  — additive append: async_add
    ingest_mode="refresh" — update existing docs by ID, add new: refresh_ref_docs

    LC backends and first-time index creation are handled automatically regardless
    of ingest_mode.

    Returns elapsed seconds (0.0 if search store not configured).
    """
    if system.search_store is None:
        logger.info("Search database not configured")
        return 0.0

    start = time.time()
    store_type = type(system.search_store).__name__
    logger.info(f"Updating search index — {len(nodes)} nodes ({store_type}, mode={ingest_mode})")

    span = None
    if OBSERVABILITY_AVAILABLE:
        try:
            tracer = get_tracer(__name__)
            span = tracer.start_span("rag.search_indexing")
            span.set_attribute("search.num_nodes", len(nodes))
            span.set_attribute("search.store_type", store_type)
            span.set_attribute("search.ingest_mode", ingest_mode)
        except Exception as e:
            logger.debug(f"OTel span setup failed: {e}")
            span = None

    try:
        if hasattr(system.search_store, "is_langchain") and system.search_store.is_langchain():
            # Route aadd_documents through the adapter itself when it exposes
            # aadd_documents (e.g. BM25SearchAdapter, which must update its own
            # internal document list — calling get_store().aadd_documents would
            # write to the throw-away BM25Retriever object and leave the adapter
            # corpus unchanged).  Fall back to get_store() for adapters that
            # delegate persistence entirely to the underlying LC store object
            # (e.g. Elasticsearch, OpenSearch).
            if hasattr(system.search_store, "aadd_documents"):
                lc_target = system.search_store
            else:
                lc_target = system.search_store.get_store()

            lc_chunks = getattr(system, "_last_lc_chunks", None)
            if lc_chunks is not None:
                # Full LC pipe path: original LC docs from _run_langchain_chunk_pipeline.
                logger.info(
                    "[LC pipe] search: aadd_documents %d LC chunks directly "
                    "(CHUNKER_BACKEND=langchain, no LI->LC conversion) [%s]",
                    len(lc_chunks), store_type,
                )
                node_ids = await lc_target.aadd_documents(lc_chunks)
                logger.info(
                    "[LC pipe] search: wrote %d chunks to %s", len(node_ids), store_type,
                )
            else:
                # Fallback path: LlamaIndex nodes -> LC docs conversion (LI chunker backend).
                from langchain.utils import llamaindex_nodes_to_langchain_docs
                lc_docs = llamaindex_nodes_to_langchain_docs(nodes)
                logger.info(
                    "[LI pipe] search: converted %d LI nodes -> %d LC docs -> %s aadd_documents",
                    len(nodes), len(lc_docs), store_type,
                )
                node_ids = await lc_target.aadd_documents(lc_docs)
                logger.info("Added %d docs to %s via LC aadd_documents", len(node_ids), store_type)

        elif hasattr(system.search_store, "add_nodes"):
            # LlamaIndex BM25SearchAdapter — cumulative node accumulation.
            # add_nodes() appends to the internal docstore and invalidates the
            # cached retriever so the next search rebuilds BM25 from all docs.
            await loop.run_in_executor(None, system.search_store.add_nodes, nodes)
            logger.info(
                "[LI BM25] search: added %d nodes (total=%d)",
                len(nodes), len(system.search_store._docstore.docs),
            )

        elif not hasattr(system, "search_index") or system.search_index is None:
            search_sc = StorageContext.from_defaults(vector_store=system.search_store)
            create_si = functools.partial(
                VectorStoreIndex, nodes=nodes, storage_context=search_sc, show_progress=False
            )
            system.search_index = await loop.run_in_executor(None, create_si)

        elif ingest_mode == REFRESH:
            from llama_index.core import Document as LIDocument
            system.search_index.refresh_ref_docs(
                [LIDocument(text=n.text, metadata=n.metadata) for n in nodes if hasattr(n, "text")]
            )

        else:
            node_ids = await system.search_store.async_add(nodes)
            logger.info(f"Added {len(node_ids)} nodes to {store_type} via async_add")

        duration = time.time() - start
        if span:
            span.set_attribute("search.latency_ms", duration * 1000)
            span.set_attribute("search.status", "success")

    except Exception as e:
        duration = time.time() - start
        if span:
            span.set_attribute("search.status", "error")
            span.set_attribute("search.error", str(e))
            try: span.record_exception(e)
            except Exception: pass
        raise
    finally:
        if span:
            try: span.end()
            except Exception: pass

    logger.info(f"Search index: {duration:.2f}s")
    return duration
