"""
AI-powered search and query engine for Flexible GraphRAG.

Owns the search() entry point, get_query_engine(), and the
extract_core_content() text-cleaning utility.
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Any

from llama_index.core import QueryBundle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure text-cleaning utility
# ---------------------------------------------------------------------------

_PREFIXES_TO_REMOVE = [
    "here are some facts extracted from the provided text:",
    "facts extracted from the provided text:",
    "extracted facts:",
    "key information:",
    "summary:",
    "important points:",
    "main points:",
    "key facts:",
    "extracted information:",
    "document summary:",
    "content summary:",
    "text summary:",
    "document facts:",
    "content facts:",
    "text facts:",
    "based on the provided text:",
    "from the provided text:",
    "the text contains:",
    "the document contains:",
    "the content includes:",
    "the information shows:",
    "the facts indicate:",
    "the data reveals:",
    "the analysis shows:",
    "the summary indicates:",
    "the key points are:",
    "the main findings are:",
    "the important details are:",
    "the relevant information is:",
    "the document states:",
    "the text states:",
    "the content states:",
    "the information states:",
    "the facts show:",
    "the data shows:",
    "the analysis reveals:",
    "the summary shows:",
    "the key points show:",
    "the main findings show:",
    "the important details show:",
    "the relevant information shows:",
    "the following facts were extracted:",
    "extracted from the document:",
    "the document reveals:",
    "the text reveals:",
    "the content reveals:",
    "the information indicates:",
    "the facts demonstrate:",
    "the data indicates:",
    "the analysis indicates:",
    "the summary demonstrates:",
    "the key points indicate:",
    "the main findings indicate:",
    "the important details indicate:",
    "the relevant information indicates:",
    "the document demonstrates:",
    "the text demonstrates:",
    "the content demonstrates:",
    "the information demonstrates:",
    "the facts suggest:",
    "the data suggests:",
    "the analysis suggests:",
    "the summary suggests:",
    "the key points suggest:",
    "the main findings suggest:",
    "the important details suggest:",
    "the relevant information suggests:",
]

_SUFFIXES_TO_REMOVE = [
    "end of document",
    "end of text",
    "document ends",
    "text ends",
    "this concludes the document",
    "this concludes the text",
    "this ends the document",
    "this ends the text",
]

_ER_PATTERNS = [
    r'^[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+:',
    r'^[A-Za-z\s]+->[A-Za-z\s]+:',
    r'^[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+:',
    r'^[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+:',
]

_ORIGINAL_PATTERNS = [
    r'LONDON.*?September.*?\d{4}.*?Alfresco',
    r'[A-Z]{2,}.*?\d{1,2}.*?\d{4}.*?[A-Za-z]+',
    r'[A-Z][a-z]+.*?\d{1,2},.*?\d{4}',
    r'[A-Z][a-z]+.*?\d{1,2}.*?\d{4}',
    r'[A-Z][a-z]+.*?\d{1,2}.*?\d{4}.*?[A-Za-z]+',
    r'[A-Z]{2,}.*?\d{1,2}.*?\d{4}',
    r'[A-Z][a-z]+.*?\d{1,2}.*?\d{4}.*?[A-Za-z]+.*?[A-Za-z]+',
]

_RELATION_LINK_RE = re.compile(r'^[^>\n]+->\s*[A-Z_]+\s*->\s*[^\n]+$')


def extract_core_content(text: str) -> str:
    """Extract core content by removing common KG/QA prefixes and suffixes."""
    text_lower = text.lower().strip()

    for prefix in _PREFIXES_TO_REMOVE:
        if text_lower.startswith(prefix.lower()):
            idx = text.lower().find(prefix.lower())
            if idx != -1:
                text = text[idx + len(prefix):].strip()
            break

    text_lower = text.lower().strip()
    for suffix in _SUFFIXES_TO_REMOVE:
        if text_lower.endswith(suffix.lower()):
            idx = text.lower().rfind(suffix.lower())
            if idx != -1:
                text = text[:idx].strip()
            break

    for er_pattern in _ER_PATTERNS:
        if re.match(er_pattern, text.strip()):
            for pattern in _ORIGINAL_PATTERNS:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    text = text[match.start():]
                    break
            break

    return text.strip()


def _is_relation_link(txt: str) -> bool:
    """True if txt is purely a bare X -> REL -> Y relation link with no real content."""
    if not txt:
        return False
    if '\n' in txt:
        return False
    if len(txt) > 300:
        return False
    return bool(_RELATION_LINK_RE.match(txt))


# ---------------------------------------------------------------------------
# Search entry point
# ---------------------------------------------------------------------------

async def search(system, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """Execute hybrid search across all configured modalities.

    Args:
        system: HybridSearchSystem instance
        query: Natural-language query string
        top_k: Maximum number of results to return

    Returns:
        List of result dicts with keys: rank, content, score, source,
        file_type, file_name
    """
    from retriever_setup import setup_hybrid_retriever

    # Ensure Weaviate async client is connected before search
    if system.vector_store and type(system.vector_store).__name__ == "WeaviateVectorStore":
        if hasattr(system.vector_store, '_aclient') and system.vector_store._aclient is not None:
            if not system.vector_store._aclient.is_connected():
                await system.vector_store._aclient.connect()
                logger.info("Connected Weaviate async client for search operation")

    # Lazy retriever initialisation
    if not system.hybrid_retriever:
        logger.info("Hybrid retriever not initialized - setting up now...")
        setup_hybrid_retriever(system)
        if not system.hybrid_retriever:
            use_langchain_rdf = getattr(system.config, "use_langchain_rdf", False)
            if use_langchain_rdf and str(system.config.vector_db) == "none" and str(system.config.search_db) == "none":
                raise ValueError(
                    "RDF graph retriever could not be initialised. "
                    "Check that the RDF store is running, USE_LANGCHAIN_RDF=true, "
                    "and RDF_STORE_TYPE is set correctly. See server logs for details."
                )
            raise ValueError("No search indexes available. The databases may be empty or disconnected.")

    logger.info(f"Searching for query: '{query}' with top_k={top_k}")
    logger.info(f"Available documents: {len(system._last_ingested_documents) if hasattr(system, '_last_ingested_documents') else 0}")

    retrieval_start = datetime.now()
    logger.info(f"Starting hybrid retrieval at {retrieval_start.strftime('%H:%M:%S.%f')[:-3]}")

    query_bundle = QueryBundle(query_str=query)

    _retrieve_attempts = 0
    while True:
        try:
            _retrieve_attempts += 1
            raw_results = await system.hybrid_retriever.aretrieve(query_bundle)
            break
        except Exception as e:
            error_msg = str(e)
            if (
                'index_not_found_exception' in error_msg or
                'no such index' in error_msg or
                "doesn't exist" in error_msg or
                'Not found' in error_msg or
                'could not find class' in error_msg or
                'NotFoundError' in str(type(e))
            ):
                logger.warning(f"Collection/Index not found: {error_msg}")
                logger.info("Databases may be empty or collection/index not created yet. Please ingest documents first.")
                return []
            _is_transient = any(p in error_msg for p in (
                "Error code: 400", "Error code: 429", "Error code: 500", "Error code: 503",
                "Connection", "timeout", "invalid_request_error",
            ))
            if _is_transient and _retrieve_attempts < 3:
                import asyncio as _asyncio
                _wait = 5 * _retrieve_attempts
                logger.warning(
                    f"Search retrieval attempt {_retrieve_attempts} failed "
                    f"(transient): {error_msg[:120]} — retrying in {_wait}s"
                )
                await _asyncio.sleep(_wait)
            else:
                raise

    retrieval_end = datetime.now()
    retrieval_duration = (retrieval_end - retrieval_start).total_seconds()
    logger.info(f"Hybrid retrieval completed in {retrieval_duration:.3f}s")

    # Filter out zero-relevance results; skip filtering in graph-only mode
    no_vector = str(system.config.vector_db) == "none"
    no_search = str(system.config.search_db) == "none"
    graph_only = (
        no_vector and no_search and
        str(system.config.graph_db) != "none" and
        system.config.enable_knowledge_graph
    )

    if graph_only:
        #filtered_results = [r for r in raw_results if not _is_relation_link((r.text or '').strip())]
        filtered = [r for r in raw_results if not _is_relation_link((r.text or '').strip())]
        if not filtered and raw_results:
            filtered = [r for r in raw_results if (r.text or '').strip()]
        filtered_results = filtered
        logger.info(f"Raw results: {len(raw_results)}, Filtered (graph-only): {len(filtered_results)}")
    else:
        filtered_results = [r for r in raw_results if r.score is not None and r.score > 0.001]
        pre_rel = len(filtered_results)
        filtered_results = [r for r in filtered_results if not _is_relation_link((r.text or '').strip())]
        logger.info(f"Raw: {len(raw_results)}, after score filter: {pre_rel}, after relation link filter: {len(filtered_results)}")

    for i, result in enumerate(raw_results):
        clean_preview = result.text[:50].encode('ascii', 'ignore').decode('ascii')
        logger.debug(f"Result {i}: score={result.score:.3f}, text_preview={clean_preview}...")

    results = filtered_results[:top_k]

    # Check for partial initialisation
    missing_required = False
    if str(system.config.vector_db) != "none" and not system.vector_index:
        missing_required = True
        logger.warning(f"Vector DB {system.config.vector_db} enabled but vector_index is missing")
    if (
        str(system.config.graph_db) != "none" and
        system.config.enable_knowledge_graph and
        not system.graph_index and
        not system.graph_intentionally_skipped
    ):
        missing_required = True
        logger.warning(f"Graph DB {system.config.graph_db} enabled but graph_index is missing")

    if missing_required:
        logger.warning("System in partial state - missing required indexes, clearing and requiring re-ingestion")
        system.vector_index = None
        system.graph_index = None
        system.hybrid_retriever = None
        raise ValueError("System not initialized. Please ingest documents first.")

    logger.info(f"Retrieved {len(results)} results from hybrid search")

    # Deduplication
    seen_content: set = set()
    seen_sources: dict = {}
    deduplicated_results = []

    for result in results:
        source = result.metadata.get("source", "Unknown")
        full_text = result.text.strip()
        core_content = extract_core_content(full_text)
        content_hash = core_content[:300].strip().lower()
        content_key = f"{source}::{content_hash}"

        similar_found = False
        if source in seen_sources:
            for existing_content in seen_sources[source]:
                if len(content_hash) > 50 and len(existing_content) > 50:
                    overlap = len(set(content_hash.split()) & set(existing_content.split()))
                    total_words = len(set(content_hash.split()) | set(existing_content.split()))
                    if total_words > 0 and overlap / total_words > 0.7:
                        similar_found = True
                        break

        if not similar_found and "->" in full_text:
            for existing_result in deduplicated_results:
                existing_text = existing_result.text.strip()
                existing_core = extract_core_content(existing_text)
                if "->" not in existing_text and len(existing_core) > 50:
                    overlap = len(set(core_content.split()) & set(existing_core.split()))
                    total_words = len(set(core_content.split()) | set(existing_core.split()))
                    if total_words > 0 and overlap / total_words > 0.6:
                        similar_found = True
                        break

        if content_key not in seen_content and not similar_found:
            seen_content.add(content_key)
            seen_sources.setdefault(source, []).append(content_hash)
            deduplicated_results.append(result)
            logger.debug(f"Added result from {source}: {core_content[:100].encode('ascii','ignore').decode('ascii')}...")
        else:
            logger.debug(f"Deduplicated result from {source}: {core_content[:100].encode('ascii','ignore').decode('ascii')}...")

    formatted_results = []
    for i, result in enumerate(deduplicated_results[:top_k]):
        display_text = extract_core_content(result.text)
        formatted_results.append({
            "rank": i + 1,
            "content": display_text,
            "score": getattr(result, 'score', 0.0),
            "source": result.metadata.get("source", "Unknown"),
            "file_type": result.metadata.get("file_type", "Unknown"),
            "file_name": result.metadata.get("file_name", "Unknown"),
        })

    logger.info(f"Deduplication: {len(results)} -> {len(deduplicated_results)} -> {len(formatted_results)} final results")

    # Observability metrics
    if system._observability_enabled:
        try:
            from observability.metrics import get_rag_metrics
            metrics = get_rag_metrics()
            retrieval_latency_ms = retrieval_duration * 1000
            top_score = formatted_results[0]["score"] if formatted_results else None
            metrics.record_retrieval(
                latency_ms=retrieval_latency_ms,
                num_documents=len(formatted_results),
                top_score=top_score,
                attributes={"query_length": len(query), "top_k": top_k},
            )
            logger.info(f"Recorded retrieval metrics: {retrieval_latency_ms:.2f}ms, {len(formatted_results)} docs")
        except Exception as e:
            logger.warning(f"Failed to record retrieval metrics: {e}")

    return formatted_results


# ---------------------------------------------------------------------------
# Query engine
# ---------------------------------------------------------------------------

def get_query_engine(system, **kwargs):
    """Build and return a RetrieverQueryEngine for Q&A.

    Args:
        system: HybridSearchSystem instance
        **kwargs: Passed through to RetrieverQueryEngine.from_args
    """
    from retriever_setup import setup_hybrid_retriever
    from llama_index.core.query_engine import RetrieverQueryEngine

    # Weaviate connectivity note (async connect happens on first query)
    if system.vector_store and type(system.vector_store).__name__ == "WeaviateVectorStore":
        logger.info("Weaviate async client will be connected on first query")

    # Lazy retriever initialisation
    if not system.hybrid_retriever:
        logger.info("Hybrid retriever not initialized - setting up now...")
        setup_hybrid_retriever(system)
        if not system.hybrid_retriever:
            use_langchain_rdf = getattr(system.config, "use_langchain_rdf", False)
            if use_langchain_rdf and str(system.config.vector_db) == "none" and str(system.config.search_db) == "none":
                raise ValueError(
                    "RDF graph retriever could not be initialised. "
                    "Check that the RDF store is running, USE_LANGCHAIN_RDF=true, "
                    "and RDF_STORE_TYPE is set correctly. See server logs for details."
                )
            raise ValueError("No search indexes available. The databases may be empty or disconnected.")

    # Partial state check
    missing_required = False
    if str(system.config.vector_db) != "none" and not system.vector_index:
        missing_required = True
        logger.warning(f"Vector DB {system.config.vector_db} enabled but vector_index is missing")
    if (
        str(system.config.graph_db) != "none" and
        system.config.enable_knowledge_graph and
        not system.graph_index and
        not system.graph_intentionally_skipped
    ):
        missing_required = True
        logger.warning(f"Graph DB {system.config.graph_db} enabled but graph_index is missing")

    if missing_required:
        logger.warning("System in partial state - clearing and requiring re-ingestion")
        system.vector_index = None
        system.graph_index = None
        system.hybrid_retriever = None
        raise ValueError("System not initialized. Please ingest documents first.")

    try:
        return RetrieverQueryEngine.from_args(
            retriever=system.hybrid_retriever,
            llm=system.llm,
            **kwargs,
        )
    except Exception as e:
        if "vector schema index" in str(e) or "There is no such vector schema index" in str(e):
            logger.warning(f"Detected missing vector indexes in Neo4j: {str(e)}")
            system.vector_index = None
            system.graph_index = None
            system.hybrid_retriever = None
            raise ValueError("System not initialized. Please ingest documents first.")
        raise
