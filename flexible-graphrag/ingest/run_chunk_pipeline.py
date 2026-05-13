"""
Shared chunking step for all ingest entry points.

Supports two backends controlled by ``config.chunker_backend``:

* ``llamaindex`` (default) — LlamaIndex ``IngestionPipeline`` with
  ``SentenceSplitter``.  Unchanged from original behaviour.
* ``langchain`` — Full LC post-reader pipeline:

  1. LangChain text splitter (``LC_SPLITTER_TYPE``) splits LI Documents
     into ``List[LCDocument]`` — stored on ``system._last_lc_chunks``.
  2. Thin LI ``TextNode`` bridge nodes (no embeddings) are created so
     KG-extraction and RDF-export consumers work unchanged.
  3. If the vector/search stores are LC-backed the bridge nodes are
     returned as-is; each store calls ``add_documents`` on
     ``_last_lc_chunks`` and handles its own embedding.
  4. If any configured store is LI-native, the bridge nodes are run
     through an embed-only LI ``IngestionPipeline`` so they carry
     embeddings for ``insert_nodes``.

LlamaIndex *readers* are always used — only the text-splitting and
downstream write steps change when ``CHUNKER_BACKEND=langchain``.
"""

import functools
import logging
import re
import time

from process.node_pipeline import build_ingestion_pipeline, build_embed_only_pipeline

logger = logging.getLogger(__name__)


def _sanitize_metadata_keys(nodes: list) -> None:
    """Normalise metadata keys in-place for stores that reject spaces / special chars.

    Some vector stores (Milvus, Weaviate) only accept field names matching
    ``[A-Za-z_][A-Za-z0-9_]*``.  LlamaIndex emits ``"modified at"`` (with a
    space) which causes insertion failures in those stores.
    Sanitises: spaces/hyphens -> ``_``; strip remaining non-word chars;
    prefix digit-starting results with ``_``.
    """
    def _clean(key: str) -> str:
        s = re.sub(r"[\s\-]+", "_", key)
        s = re.sub(r"[^A-Za-z0-9_]", "", s)
        if s and s[0].isdigit():
            s = "_" + s
        return s or "_unknown"

    for node in nodes:
        if node.metadata:
            node.metadata = {_clean(k): v for k, v in node.metadata.items()}


async def run_chunk_pipeline(system, documents: list, loop) -> tuple:
    """Chunk (and optionally embed) documents, returning ``(nodes, duration_seconds)``.

    Dispatches to :func:`_run_llamaindex_chunk_pipeline` or
    :func:`_run_langchain_chunk_pipeline` based on
    ``system.config.chunker_backend``.

    Sets ``system._last_ingested_nodes`` as a side-effect.
    For the LC path also sets ``system._last_lc_chunks`` with the raw
    LangChain ``Document`` objects so downstream update_vector /
    update_search can write them directly without LI->LC conversion.
    """
    # Clear LC chunks from any previous ingest run before starting
    system._last_lc_chunks = None

    backend = getattr(system.config, "chunker_backend", "llamaindex").lower()
    if backend == "langchain":
        logger.info("[chunk] backend=langchain (full LC post-reader pipeline)")
        return await _run_langchain_chunk_pipeline(system, documents, loop)

    logger.info("[chunk] backend=llamaindex (LI SentenceSplitter + embed pipeline)")
    return await _run_llamaindex_chunk_pipeline(system, documents, loop)


# ---------------------------------------------------------------------------
# LlamaIndex path (original behaviour, unchanged)
# ---------------------------------------------------------------------------

async def _run_llamaindex_chunk_pipeline(system, documents: list, loop) -> tuple:
    """Chunk + embed via LlamaIndex IngestionPipeline (SentenceSplitter).

    Path: LI reader docs -> SentenceSplitter -> LI TextNodes -> LI embed -> nodes
    Logging: INFO on completion; DEBUG for per-node detail.
    """
    pipeline = build_ingestion_pipeline(system.config, system.embed_model)
    run_fn = functools.partial(pipeline.run, documents=documents)
    start = time.time()
    nodes = await loop.run_in_executor(None, run_fn)
    duration = time.time() - start

    _sanitize_metadata_keys(nodes)
    system._last_ingested_nodes = nodes

    logger.info(
        "[LI pipe] chunk+embed: %.2fs, %d nodes from %d docs "
        "[splitter=SentenceSplitter(chars), chunk_size=%d, overlap=%d]",
        duration, len(nodes), len(documents),
        system.config.chunk_size, system.config.chunk_overlap,
    )
    _log_node_sample(nodes)
    return nodes, duration


# ---------------------------------------------------------------------------
# LangChain full-LC path
# ---------------------------------------------------------------------------

async def _run_langchain_chunk_pipeline(system, documents: list, loop) -> tuple:
    """Full LC post-reader pipeline: LC split -> LC docs -> bridge LI nodes.

    Flow
    ----
    1. ``LangChainChunkerAdapter.split_documents(li_docs)``
       -> ``List[LCDocument]`` (original LC docs, no LI round-trip)
    2. Stash on ``system._last_lc_chunks`` for update_vector / update_search
       fast paths (they call ``add_documents`` directly — no re-embedding).
    3. ``langchain_docs_to_llamaindex_nodes(lc_chunks)``
       -> thin bridge nodes (text + metadata, NO embeddings)
    4. If any configured store is LI-native: run bridge nodes through
       ``build_embed_only_pipeline`` so they carry embeddings for
       ``insert_nodes``.  LC stores skip this step entirely.

    Logging
    -------
    INFO  — split count, whether LI embed step runs, total timing.
    DEBUG — per-node detail, _last_lc_chunks stash confirmation.
    """
    from adapters.process.chunker_adapter import build_chunker_adapter
    from langchain.utils import langchain_docs_to_llamaindex_nodes, sanitize_langchain_doc_metadata

    splitter_type = getattr(system.config, "lc_splitter_type", "recursive")
    logger.info(
        "[LC pipe] split: splitter=%s, chunk_size=%d, overlap=%d, source_docs=%d",
        splitter_type, system.config.chunk_size, system.config.chunk_overlap, len(documents),
    )

    adapter = build_chunker_adapter(system.config)
    start = time.time()

    # ── Step 1: LC split -> List[LCDocument] ─────────────────────────────────
    split_fn = functools.partial(adapter.split_documents, documents)
    lc_chunks: list = await loop.run_in_executor(None, split_fn)
    split_dur = time.time() - start

    if not lc_chunks:
        logger.warning("[LC pipe] split produced 0 chunks from %d documents", len(documents))
        system._last_lc_chunks = []
        system._last_ingested_nodes = []
        return [], split_dur

    # Sanitise metadata keys so strict stores (Milvus, Weaviate) accept them
    lc_chunks = sanitize_langchain_doc_metadata(lc_chunks)

    logger.info("[LC pipe] split: %d LC chunks in %.2fs (splitter=%s)", len(lc_chunks), split_dur, splitter_type)

    # ── Step 2: stash LC docs for downstream update_vector / update_search ───
    system._last_lc_chunks = lc_chunks
    logger.debug("[LC pipe] stashed %d lc_chunks on system._last_lc_chunks", len(lc_chunks))

    # ── Step 3: thin bridge nodes for KG / RDF consumers (conditional) ──────
    needs_bridge = _needs_li_bridge(system)
    vector_needs_embed = _store_needs_li_embeddings(getattr(system, "vector_store", None))
    search_needs_embed = _store_needs_li_embeddings(getattr(system, "search_store", None))
    li_pg_needs_embed  = _li_pg_needs_embeddings(system) and needs_bridge
    needs_li_embed     = vector_needs_embed or search_needs_embed or li_pg_needs_embed

    if needs_bridge or needs_li_embed:
        bridge_nodes = langchain_docs_to_llamaindex_nodes(lc_chunks)
        logger.debug(
            "[LC pipe] bridge: %d LI TextNodes created (needs_bridge=%s, "
            "vector_embed=%s, search_embed=%s, li_pg_embed=%s)",
            len(bridge_nodes), needs_bridge, vector_needs_embed,
            search_needs_embed, li_pg_needs_embed,
        )
    else:
        bridge_nodes = []
        _rdf_configured = str(getattr(system.config, "rdf_graph_db", "none")).lower() not in ("none", "")
        logger.info(
            "[LC pipe] bridge: skipped — all stores LC-backed, no LI embed needed "
            "(vector_lc=%s, search_lc=%s, li_kg=%s, rdf_configured=%s — RDF uses LC graph docs directly)",
            not vector_needs_embed, not search_needs_embed,
            _li_pg_active(system),
            _rdf_configured,
        )

    # ── Step 4: LI embed only if a consumer needs pre-computed embeddings ─────
    if needs_li_embed and bridge_nodes:
        logger.info(
            "[LC pipe] embed: LI embed required "
            "(vector_lc=%s, search_lc=%s, li_pg=%s) "
            "— embedding %d bridge nodes via LI model",
            not vector_needs_embed, not search_needs_embed,
            li_pg_needs_embed, len(bridge_nodes),
        )
        pipeline = build_embed_only_pipeline(system.embed_model)
        embed_fn = functools.partial(pipeline.run, nodes=bridge_nodes, show_progress=False)
        bridge_nodes = await loop.run_in_executor(None, embed_fn)
        logger.debug("[LC pipe] embed: %d nodes embedded via LI model", len(bridge_nodes))
    elif bridge_nodes:
        logger.info(
            "[LC pipe] embed: skipped — bridge nodes needed for KG/RDF but no embedding required "
            "(LI stores absent, BM25-only, or PropertyGraphIndex embeds its own entities)"
        )
    else:
        logger.info(
            "[LC pipe] embed: skipped — no bridge nodes needed "
            "(all stores LC-backed; each calls add_documents with its own embedding)"
        )

    duration = time.time() - start
    _sanitize_metadata_keys(bridge_nodes)
    system._last_ingested_nodes = bridge_nodes

    logger.info(
        "[LC pipe] done: %.2fs total — %d LC chunks stashed, %d bridge nodes returned",
        duration, len(lc_chunks), len(bridge_nodes),
    )
    _log_node_sample(bridge_nodes)
    return bridge_nodes, duration


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _needs_li_bridge(system) -> bool:
    """True if LI bridge TextNodes must be created from the LC chunks.

    Bridge nodes are needed by:
    - LI KG (``GRAPH_BACKEND=llamaindex``): ``PropertyGraphIndex.insert_nodes(nodes)``
    - RDF export when LC KG has NOT already produced ``system._lc_graph_docs``
      (LC KG writes ``_lc_graph_docs`` and ``update_rdf_graph`` uses those directly)

    Bridge nodes are NOT needed when:
    - ``GRAPH_BACKEND=langchain``: ``aingest_lc_graph`` receives ``lc_docs`` directly
    - RDF is disabled
    - KG is disabled entirely
    """
    config = system.config
    kg_enabled = getattr(config, "enable_knowledge_graph", True)
    pg_db  = str(getattr(config, "pg_graph_db",  "none") or "none").lower()
    rdf_db = str(getattr(config, "rdf_graph_db", "none") or "none").lower()

    pg_adapter = getattr(system, "pg_adapter", None)
    pg_is_lc   = bool(pg_adapter is not None
                      and hasattr(pg_adapter, "is_langchain")
                      and pg_adapter.is_langchain())

    kg_extractor_backend = str(
        getattr(config, "kg_extractor_backend", "llamaindex") or "llamaindex"
    ).lower()

    # LI KG active: GRAPH_BACKEND=llamaindex AND KG enabled AND PG DB configured,
    # OR GRAPH_BACKEND=langchain but KG_EXTRACTOR_BACKEND=llamaindex (LI does the
    # extraction, then the extracted KG nodes are written to the LC graph store).
    li_kg_active = (
        kg_enabled
        and pg_db not in ("none", "")
        and (not pg_is_lc or kg_extractor_backend == "llamaindex")
    )

    # RDF needs LI nodes unless LC KG runs first (which sets _lc_graph_docs).
    # If KG_EXTRACTOR_BACKEND=llamaindex, LI extraction always runs first, so
    # _lc_graph_docs will NOT be set — RDF export must use LI nodes.
    lc_kg_active = (
        kg_enabled
        and pg_db not in ("none", "")
        and pg_is_lc
        and kg_extractor_backend == "langchain"
    )
    rdf_needs_li = rdf_db not in ("none", "") and not lc_kg_active

    needs = li_kg_active or rdf_needs_li
    logger.debug(
        "[LC pipe] _needs_li_bridge: %s (li_kg=%s, rdf_needs_li=%s, lc_kg=%s, kg_extractor=%s)",
        needs, li_kg_active, rdf_needs_li, lc_kg_active, kg_extractor_backend,
    )
    return needs


def _store_needs_li_embeddings(store) -> bool:
    """True if *store* requires pre-computed embeddings on LI TextNodes.

    - LC stores (``is_langchain() == True``): handle their own embedding
      inside ``add_documents`` — no pre-computed embeddings needed.
    - BM25 stores: text-only, no embeddings required.
    - LI vector / search stores (ES, OpenSearch, Qdrant-LI, etc.):
      ``insert_nodes`` / ``async_add`` expect ``node.embedding`` to be set.
    - ``None`` (store not configured): no embedding needed.
    """
    if store is None:
        return False
    if hasattr(store, "is_langchain") and store.is_langchain():
        return False
    store_type = type(store).__name__.lower()
    if "bm25" in store_type:
        return False   # BM25 is term-frequency only, no vector embeddings
    return True        # LI vector / search store: needs pre-embedded nodes


def _li_pg_needs_embeddings(system) -> bool:
    """True if the LI PropertyGraphIndex needs embeddings on bridge nodes.

    ``PropertyGraphIndex`` uses ``embed_model`` to embed the text-chunk nodes
    that back its vector component.  When ``GRAPH_BACKEND=llamaindex`` and the
    PG store is configured, bridge nodes must carry embeddings so that the
    chunk vector search inside the PG index works correctly.
    """
    config = system.config
    if not getattr(config, "enable_knowledge_graph", True):
        return False
    pg_db = str(getattr(config, "pg_graph_db", "none") or "none").lower()
    if pg_db in ("none", ""):
        return False
    pg_adapter = getattr(system, "pg_adapter", None)
    if pg_adapter is None:
        return False
    # LI adapter: NOT a LangChain adapter
    return not (hasattr(pg_adapter, "is_langchain") and pg_adapter.is_langchain())


def _li_pg_active(system) -> bool:
    """True when a LI PropertyGraphStore is configured (GRAPH_BACKEND=llamaindex)."""
    config = system.config
    pg_db = str(getattr(config, "pg_graph_db", "none") or "none").lower()
    if pg_db in ("none", "") or not getattr(config, "enable_knowledge_graph", True):
        return False
    pg_adapter = getattr(system, "pg_adapter", None)
    if pg_adapter is None:
        return False
    return not (hasattr(pg_adapter, "is_langchain") and pg_adapter.is_langchain())


def _log_node_sample(nodes: list) -> None:
    for i, node in enumerate(nodes[:3]):
        logger.debug("  Node[%d] %d chars, metadata: %s", i, len(node.text or ""), node.metadata)
    if len(nodes) > 3:
        logger.debug("  ... and %d more nodes", len(nodes) - 3)
    # INFO-level summary (first node text snippet only)
    if nodes:
        snippet = (nodes[0].text or "")[:80].replace("\n", " ")
        logger.info("  sample[0]: %r", snippet)
