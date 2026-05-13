"""
AI-powered search and query engine for Flexible GraphRAG.

Owns the search() entry point, get_query_engine(), and the
extract_core_content() text-cleaning utility.
"""

import re
import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Any

from llama_index.core import QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure text-cleaning utility
# ---------------------------------------------------------------------------

def _dedup_and_sum_scores(nodes: List[NodeWithScore]) -> List[NodeWithScore]:
    """Group nodes by text content and sum their per-retriever scores.

    ``QueryFusionRetriever`` with ``mode="relative_score"`` assigns each
    retriever a weight of ``1/N`` (N = number of retrievers).  Deduplication
    inside the retriever uses ``node.hash = SHA256(text + metadata)``.
    Because each LC-backed retriever attaches different metadata
    (``_id``, ``_collection_name``, ``source_framework``, …), the *same*
    text chunk returned by three retrievers gets three different hashes and
    is never summed — every result caps at ``1/N``.

    This post-fusion pass groups by text content only, sums scores, and
    keeps the node with the richest metadata (highest individual score).
    The resulting scores are already in ``[0, 1]`` — a node found by all N
    retrievers at top rank earns ``N × (1/N) = 1.0``.
    """
    groups: dict = {}       # text_hash -> NodeWithScore (best metadata node)
    totals: dict = {}       # text_hash -> cumulative score

    for n in nodes:
        text = (n.text or "").strip()
        if not text:
            continue
        h = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
        s = n.score or 0.0
        if h not in groups:
            groups[h] = n
            totals[h] = s
        else:
            totals[h] += s
            if s > (groups[h].score or 0.0):
                groups[h] = n

    for h, n in groups.items():
        n.score = totals[h]

    return sorted(groups.values(), key=lambda x: x.score or 0.0, reverse=True)


class _DeduplicatingRetriever(BaseRetriever):
    """Thin wrapper that applies ``_dedup_and_sum_scores`` after retrieval.

    Used by ``get_query_engine`` so that the ``RetrieverQueryEngine`` LLM
    synthesis step also benefits from properly fused scores.
    """

    def __init__(self, inner: BaseRetriever) -> None:
        self._inner = inner
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return _dedup_and_sum_scores(self._inner.retrieve(query_bundle))

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return _dedup_and_sum_scores(await self._inner.aretrieve(query_bundle))


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


# Prefixes emitted by TextToGraphQueryRetriever intermediate steps.
# The GraphCypherQAChain / GraphSparqlQAChain intermediate_steps contain
# {"query": "<Cypher/SPARQL>"} and {"context": [...results...]} dicts.
# _format_step() serialises them as "query: MATCH ..." / "context: [...]"
# strings, but some chains (e.g. Neo4j) emit the raw context list directly
# as "[{'col': 'val'}, ...]" without the "context: " prefix.
# All of these are internal pipeline artefacts that should not be shown
# as user-facing search results.
_GRAPH_STEP_PREFIXES = (
    "query: match ",
    "query: select ",
    "query: optional match ",
    "query: with ",
    "query: create ",
    "query: merge ",
    "query: for ",        # AQL
    "query: g.v(",        # Gremlin
    "context: {",
    "context: [{",
    "context: [",
    "[{",                 # bare list-of-dicts from Neo4j/Cypher intermediate steps
    "[{'",               # same, single-quoted keys
)

# Map LangChain graph class names to human-readable source labels.
# RDF stores → "RDF Graph"; property graph stores → "Property Graph".
_RDF_GRAPH_CLASS_SUBSTRINGS = ("Ontotext", "Sparql", "Rdf", "Fuseki", "Oxigraph", "Neptune")


def _graph_type_label(graph_type: str) -> str:
    """Return 'RDF Graph' or 'Property Graph' based on the LangChain graph class name."""
    if not graph_type:
        return "Property Graph"
    gt_upper = graph_type.upper()
    if any(s.upper() in gt_upper for s in _RDF_GRAPH_CLASS_SUBSTRINGS):
        return "RDF Graph"
    return "Property Graph"


_DB_NAME_MAP = {
    "opensearch": "OpenSearch", "elasticsearch": "Elasticsearch",
    "qdrant": "Qdrant", "chroma": "Chroma", "pinecone": "Pinecone",
    "weaviate": "Weaviate", "milvus": "Milvus", "neo4j": "Neo4j",
    "ladybug": "LadybugDB", "falkordb": "FalkorDB", "nebula": "NebulaGraph",
    "neptune": "Neptune", "neptune_analytics": "Neptune Analytics",
    "memgraph": "Memgraph", "arcadedb": "ArcadeDB", "arangodb": "ArangoDB",
    "apache_age": "Apache AGE", "cosmos_gremlin": "Azure Cosmos DB for Gremlin",
    "spanner": "Spanner Graph", "hugegraph": "HugeGraph", "tigergraph": "TigerGraph",
    "surrealdb": "SurrealDB", "fuseki": "Apache Jena Fuseki",
    "oxigraph": "Oxigraph", "graphdb": "Ontotext GraphDB", "bm25": "BM25",
    "postgres": "PostgreSQL",
}


def _pretty_db(key: str) -> str:
    return _DB_NAME_MAP.get(str(key).lower(), str(key).title())


def _retriever_label_to_display(label: str, config: Any) -> str:
    """Convert a LoggingRetriever label to a human-readable DB-type string.

    Returns strings like "Qdrant vector", "Elasticsearch search",
    "Neo4j property graph", "Ontotext GraphDB rdf graph".
    Returns "" for unrecognised labels (caller falls back to existing logic).
    """
    if not label:
        return ""
    lo = label.lower()
    if lo.startswith("graph("):
        db = label[6:].rstrip(")")
        return f"{_pretty_db(db)} property graph"
    if lo in ("rdf(langchain)", "rdf"):
        rdf_db = str(getattr(config, "rdf_graph_db", "") or "")
        return f"{_pretty_db(rdf_db)} rdf graph" if rdf_db and rdf_db != "none" else "RDF Graph"
    if lo == "vector":
        vdb = str(getattr(config, "vector_db", "") or "")
        return f"{_pretty_db(vdb)} vector" if vdb and vdb != "none" else "vector"
    if lo in ("elasticsearch", "opensearch"):
        return f"{_pretty_db(lo)} search"
    if lo == "bm25":
        return "BM25 search"
    if lo in ("langchain_pg", "langchain_pg_vector", "pg_neighborhood"):
        pgdb = str(getattr(config, "pg_graph_db", "") or "")
        return f"{_pretty_db(pgdb)} property graph" if pgdb and pgdb != "none" else "Property Graph"
    return ""


def _is_graph_intermediate_step(txt: str) -> bool:
    """True for raw query strings and context dicts from intermediate_steps.

    TextToGraphQueryRetriever surfaces the generated Cypher/SPARQL query and
    the raw query results as extra nodes when ``include_intermediate_steps=True``.
    These contain useful context for AI QA but are noise in the search display.
    """
    if not txt:
        return False
    s = txt.strip().lower()
    return any(s.startswith(p) for p in _GRAPH_STEP_PREFIXES)


def _is_entity_name_stub(txt: str) -> bool:
    """True if txt is a bare entity name with no document content.

    LangChain property graph retrievers return ``__Entity__`` nodes whose
    ``page_content`` is just their name (e.g. "Acme Corporation").  These short
    noun phrases without sentence-ending punctuation add noise to search results
    and should be suppressed so real text passages and QA answers rank first.

    Heuristic: text shorter than 80 chars that does not end with sentence
    punctuation (.  ?  !) is treated as an entity stub.
    """
    s = txt.strip()
    if not s:
        return False
    if len(s) >= 80:
        return False          # long enough to be real document content
    if s[-1] in ".?!":
        return False          # ends with sentence punctuation → real content
    return True


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
            has_rdf = str(getattr(system.config, "rdf_graph_db", "none")) != "none"
            if has_rdf and str(system.config.vector_db) == "none" and str(system.config.search_db) == "none":
                raise ValueError(
                    "RDF graph retriever could not be initialised. "
                    "Check that the RDF store is running and RDF_GRAPH_DB is set correctly. "
                    "See server logs for details."
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
            raw_results = _dedup_and_sum_scores(raw_results)
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
        str(system.config.pg_graph_db) != "none" and
        system.config.enable_knowledge_graph
    )

    if graph_only:
        #filtered_results = [r for r in raw_results if not _is_relation_link((r.text or '').strip())]
        filtered = [r for r in raw_results if not _is_relation_link((r.text or '').strip())]
        filtered = [r for r in filtered if not _is_graph_intermediate_step((r.text or '').strip())]
        filtered = [r for r in filtered if not _is_entity_name_stub((r.text or '').strip())]
        # Drop zero-score results that are noise (raw dicts, unparsed context) unless
        # they are the only results available.
        non_zero = [r for r in filtered if (r.score or 0.0) > 0.0]
        filtered = non_zero if non_zero else filtered
        if not filtered and raw_results:
            filtered = [r for r in raw_results if (r.text or '').strip()]
        filtered_results = filtered
        logger.info(f"Raw results: {len(raw_results)}, Filtered (graph-only): {len(filtered_results)}")
    else:
        show_intermediate = getattr(system.config, "langchain_pg_intermediate_steps", False)
        # Keep results with non-None score and valid text content.
        # Do NOT drop score==0.0 results when they have content — QueryFusionRetriever's
        # relative_score mode always normalises the lowest-scored doc to 0.0, which is valid
        # content, not noise. Only drop None-score or score<0 (error/placeholder) entries.
        filtered_results = [
            r for r in raw_results
            if r.score is not None and r.score >= 0.0 and (r.text or "").strip()
        ]
        pre_rel = len(filtered_results)
        filtered_results = [r for r in filtered_results if not _is_relation_link((r.text or '').strip())]
        # When intermediate steps are enabled, preserve langchain_graph_intermediate nodes;
        # otherwise filter them along with entity name stubs.
        def _keep_intermediate(r) -> bool:
            if show_intermediate and r.metadata.get("source") == "langchain_graph_intermediate":
                return True
            return not _is_graph_intermediate_step((r.text or '').strip())
        filtered_results = [r for r in filtered_results if _keep_intermediate(r)]
        def _keep_stub(r) -> bool:
            if show_intermediate and r.metadata.get("source") == "langchain_graph_intermediate":
                return True
            return not _is_entity_name_stub((r.text or '').strip())
        filtered_results = [r for r in filtered_results if _keep_stub(r)]
        logger.info(f"Raw: {len(raw_results)}, after score filter: {pre_rel}, after relation link filter: {len(filtered_results)}, show_intermediate={show_intermediate}")

    for i, result in enumerate(raw_results):
        clean_preview = result.text[:50].encode('ascii', 'ignore').decode('ascii')
        logger.debug(f"Result {i}: score={result.score:.3f}, text_preview={clean_preview}...")

    results = filtered_results[:top_k]

    # Check for partial initialisation
    missing_required = False
    _vector_is_lc = hasattr(system.vector_store, "is_langchain") and system.vector_store.is_langchain()
    if str(system.config.vector_db) != "none" and not system.vector_index and not _vector_is_lc:
        missing_required = True
        logger.warning(f"Vector DB {system.config.vector_db} enabled but vector_index is missing")
    _is_lc_pg = (
        getattr(system.config, "graph_backend", "llamaindex").lower() == "langchain"
        or getattr(system.config, "use_langchain_pg", False)
    )
    if (
        str(system.config.pg_graph_db) != "none" and
        system.config.enable_knowledge_graph and
        not system.graph_intentionally_skipped
    ):
        if _is_lc_pg:
            # LangChain backend: graph_index is intentionally absent; check pg_adapter instead
            if getattr(system, "pg_adapter", None) is None:
                missing_required = True
                logger.warning(f"Graph DB {system.config.pg_graph_db} (langchain) enabled but pg_adapter is missing")
        elif not system.graph_index:
            missing_required = True
            logger.warning(f"Graph DB {system.config.pg_graph_db} enabled but graph_index is missing")

    if missing_required:
        logger.warning("System in partial state - missing required indexes, clearing and requiring re-ingestion")
        system.vector_index = None
        system.graph_index = None
        system.hybrid_retriever = None
        raise ValueError("System not initialized. Please ingest documents first.")

    logger.info(f"Retrieved {len(results)} results from hybrid search")

    # Deduplication — three layers:
    # 1. Exact node_id match (same LlamaIndex node returned by multiple retrievers)
    # 2. Exact content hash (same text, different source metadata tag)
    # 3. High word-overlap (near-duplicate text chunks)
    seen_node_ids: set = set()
    seen_content: set = set()
    seen_by_source: dict = {}
    deduplicated_results = []

    for result in results:
        # Layer 1: node_id exact dedup
        node_id = getattr(result, "node_id", None) or getattr(getattr(result, "node", None), "node_id", None)
        if node_id and node_id in seen_node_ids:
            logger.debug(f"Deduplicated (node_id) {node_id}: {result.text[:60].encode('ascii','ignore').decode('ascii')}...")
            continue
        if node_id:
            seen_node_ids.add(node_id)

        source = result.metadata.get("source", "Unknown")
        full_text = result.text.strip()
        core_content = extract_core_content(full_text)
        # Layer 2: content-hash dedup — intentionally NOT prefixed with source
        content_hash = core_content[:300].strip().lower()

        if content_hash in seen_content:
            logger.debug(f"Deduplicated (content) from {source}: {core_content[:60].encode('ascii','ignore').decode('ascii')}...")
            continue

        # Layer 3: high word-overlap within same source tag
        similar_found = False
        if source in seen_by_source:
            for existing_content in seen_by_source[source]:
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

        if not similar_found:
            seen_content.add(content_hash)
            seen_by_source.setdefault(source, []).append(content_hash)
            deduplicated_results.append(result)
            logger.debug(f"Added result from {source}: {core_content[:100].encode('ascii','ignore').decode('ascii')}...")
        else:
            logger.debug(f"Deduplicated (overlap) from {source}: {core_content[:100].encode('ascii','ignore').decode('ascii')}...")

    # Re-score if all scores are suspiciously flat (QueryFusionRetriever relative_score
    # divides every score by num_retrievers, so unique-content results all land at 1/N).
    # When the score range is < 0.05 (e.g., everything at 0.250), preserve the ORDER
    # that QFR already computed and assign rank-based scores [1.0 … 0.20].
    if deduplicated_results:
        _scores = [r.score or 0.0 for r in deduplicated_results]
        _score_range = max(_scores) - min(_scores)
        if _score_range < 0.05 and max(_scores) > 0:
            _n = len(deduplicated_results)
            for _i, _r in enumerate(deduplicated_results):
                _r.score = round(1.0 - (_i / max(_n - 1, 1)) * 0.80, 3) if _n > 1 else 1.0

    formatted_results = []
    for i, result in enumerate(deduplicated_results[:top_k]):
        display_text = extract_core_content(result.text)
        logger.debug(
            "Format result[%d]: raw_text=%r -> display_text=%r",
            i, (result.text or "")[:120], display_text[:120],
        )
        _meta = result.metadata or {}
        _file_name = _meta.get("file_name", "")
        _src_tag         = _meta.get("source", "")
        _graph_type      = _meta.get("graph_type", "")   # e.g. "OntotextGraphDBGraph"
        _retriever_label = _meta.get("_retriever_label", "")  # set by LoggingRetriever for all nodes
        _KG_TAGS = {"langchain_graph_qa", "langchain_graph_intermediate", "rdf"}

        logger.debug(
            "Format result[%d]: source=%r file_name=%r graph_type=%r retriever_label=%r score=%.3f text=%r meta=%r",
            i, _src_tag, _file_name, _graph_type, _retriever_label, getattr(result, 'score', 0.0),
            (result.text or "")[:80], dict(_meta),
        )

        # Build a human-readable DB type string from the retriever label when available.
        _db_type_str = _retriever_label_to_display(_retriever_label, system.config)

        # Determine whether this is a graph / RDF result that has no standalone filename
        # (LC SPARQL QA chain results) vs a text chunk that happens to carry graph metadata.
        _is_lc_graph = _src_tag in _KG_TAGS or _src_tag.startswith("langchain_")

        if _db_type_str:
            # LoggingRetriever tagged this node — combine filename (if any) with DB type.
            _fn_clean = _file_name if _file_name and _file_name not in ("Unknown", "") else ""
            if not _fn_clean:
                # Graph/RDF QA chain results have no file_name but do carry source_files.
                _src_files = _meta.get("source_files", [])
                if _src_files:
                    _fn_clean = ", ".join(_src_files[:2])
                    if len(_src_files) > 2:
                        _fn_clean += f" (+{len(_src_files) - 2} more)"
            display_source = f"{_fn_clean} | {_db_type_str}" if _fn_clean else _db_type_str
        elif _is_lc_graph:
            # LC graph QA chain result without a retriever label — use graph class name.
            _graph_label = _graph_type_label(_graph_type)
            _src_files = _meta.get("source_files", [])
            if _src_files:
                _files_str = ", ".join(_src_files[:2])
                if len(_src_files) > 2:
                    _files_str += f" (+{len(_src_files) - 2} more)"
                display_source = f"{_files_str} | {_graph_label}"
            else:
                display_source = _graph_label
        elif _file_name and _file_name not in ("Unknown", ""):
            display_source = _file_name
        elif _src_tag and _src_tag not in ("Unknown", ""):
            display_source = _src_tag
        else:
            display_source = "Unknown"
            logger.info(
                "Result[%d] source=Unknown — metadata keys: %s",
                i, list(_meta.keys()),
            )

        # file_name in the response: always send empty when we have a DB-type label so the
        # frontend falls through to result.source (= "filename | DB type").  Only populate
        # file_name as a raw filename fallback when no DB-type label is available.
        _resp_file_name = "" if _db_type_str else (_file_name or "")

        formatted_results.append({
            "rank": i + 1,
            "content": display_text,
            "score": getattr(result, 'score', 0.0),
            "source": display_source,
            "file_type": _meta.get("file_type", ""),
            "file_name": _resp_file_name,
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
            has_rdf = str(getattr(system.config, "rdf_graph_db", "none")) != "none"
            if has_rdf and str(system.config.vector_db) == "none" and str(system.config.search_db) == "none":
                raise ValueError(
                    "RDF graph retriever could not be initialised. "
                    "Check that the RDF store is running and RDF_GRAPH_DB is set correctly. "
                    "See server logs for details."
                )
            raise ValueError("No search indexes available. The databases may be empty or disconnected.")

    # Partial state check
    missing_required = False
    _vector_is_lc = hasattr(system.vector_store, "is_langchain") and system.vector_store.is_langchain()
    if str(system.config.vector_db) != "none" and not system.vector_index and not _vector_is_lc:
        missing_required = True
        logger.warning(f"Vector DB {system.config.vector_db} enabled but vector_index is missing")
    _is_lc_pg = (
        getattr(system.config, "graph_backend", "llamaindex").lower() == "langchain"
        or getattr(system.config, "use_langchain_pg", False)
    )
    if (
        str(system.config.pg_graph_db) != "none" and
        system.config.enable_knowledge_graph and
        not system.graph_intentionally_skipped
    ):
        if _is_lc_pg:
            if getattr(system, "pg_adapter", None) is None:
                missing_required = True
                logger.warning(f"Graph DB {system.config.pg_graph_db} (langchain) enabled but pg_adapter is missing")
        elif not system.graph_index:
            missing_required = True
            logger.warning(f"Graph DB {system.config.pg_graph_db} enabled but graph_index is missing")

    if missing_required:
        logger.warning("System in partial state - clearing and requiring re-ingestion")
        system.vector_index = None
        system.graph_index = None
        system.hybrid_retriever = None
        raise ValueError("System not initialized. Please ingest documents first.")

    try:
        return RetrieverQueryEngine.from_args(
            retriever=_DeduplicatingRetriever(system.hybrid_retriever),
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
