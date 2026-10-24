"""Core pipeline processing component.

Contains:
* :func:`_emit_progress` / :func:`set_progress_hook` — per-file progress events.
* :func:`set_runtime_skip_graph` — runtime KG override used by the bridge.
* :func:`process_document` — ``@coco.fn(memo=True)`` entry point for the full
  flexible-graphrag pipeline (parse → chunk → embed → KG → write to all targets).
* :func:`_run_pipeline` — the underlying coroutine that does the actual work.

All mutable singletons are owned by :mod:`state`; target pickers and root-mount
helpers live in :mod:`selectors`; provider registration lives in :mod:`providers`.

"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

import cocoindex as coco  # noqa: E402

from cocoindex_integration.pipeline import state as _state  # noqa: E402
from cocoindex_integration.pipeline import providers as _providers  # noqa: E402
from cocoindex_integration.pipeline import selectors as _sel  # noqa: E402
from cocoindex_integration.pipeline.embedding import (  # noqa: E402
    _build_embed_cfg_json,
    _embed_chunks_cached,
)


# ─────────────────────────────────────────────────────────────────────────────
# Progress hook
# ─────────────────────────────────────────────────────────────────────────────

def set_progress_hook(hook: Optional[Callable[[dict], None]]) -> None:
    """Set or clear the per-file/per-stage progress hook for the next cycle.

    ``hook`` receives a small dict with at least ``event`` and ``file_name``.
    Passing ``None`` disables progress reporting.  The bridge sets this before
    each ``update()`` and clears it afterward.
    """
    _state._progress_hook = hook


def _emit_progress(**fields: Any) -> None:
    """Safely dispatch a progress event to the runtime hook (never raises)."""
    hook = _state._progress_hook
    if hook is None:
        return
    try:
        hook(fields)
    except Exception as _pe:  # noqa: BLE001
        logger.debug("progress hook error (ignored): %s", _pe)


# ─────────────────────────────────────────────────────────────────────────────
# Runtime skip_graph override
# ─────────────────────────────────────────────────────────────────────────────

def set_runtime_skip_graph(value: "bool | None") -> None:
    """Set or clear the runtime skip_graph override for the next update() cycle.

    Args:
        value: ``True`` — force KG extraction off for all files in the next
               ``app.update()`` call.
               ``None`` — honour ``enable_knowledge_graph`` from cfg_json / .env.
               (``False`` is not used — callers pass ``None`` to clear an override.)
    """
    _state._runtime_skip_graph = value if value is True else None


def set_runtime_graphs(graphs) -> None:
    """Set (a graph_flags.GraphFlags) or clear (None) which graphs the next update() cycle
    builds: the property graph and the RDF graph, each on its own."""
    _state._runtime_graphs = graphs


def _resolve_graphs(cfg: Dict[str, Any]):
    """Which graphs this document gets: the runtime flags of this cycle, else cfg_json's
    (_enabled_graph / _enabled_rdf, _skip_graph), else DEFAULT_ENABLED_GRAPH / _RDF."""
    from graph_flags import GraphFlags
    if _state._runtime_graphs is not None:
        return _state._runtime_graphs
    return GraphFlags.resolve(cfg.get("_enabled_graph"), cfg.get("_enabled_rdf"), cfg.get("_skip_graph"))


def _resolve_enable_kg(cfg: Dict[str, Any]) -> bool:
    """True when KG extraction should run for this document (before target checks)."""
    if _state._runtime_skip_graph is True:
        return False
    if cfg.get("_skip_graph") is True:
        return False
    return bool(cfg.get("enable_knowledge_graph", True))


# ─────────────────────────────────────────────────────────────────────────────
# Core pipeline — memoised @coco.fn entry point
# ─────────────────────────────────────────────────────────────────────────────

@coco.fn(memo=True)
def _apply_entity_resolution(
    strategy: str,
    pg_triples: List[Any],
    rdf_rows: List[Any],
    llm_provider: str,
    llm_config_json: str,
    file_name: str = "",
) -> None:
    """Merge entity-name spellings across one document's rows, in place.

    Synchronous on purpose — the caller runs it in a worker thread so the
    ``llm`` strategy's internal ``asyncio.run()`` has no running loop to clash
    with.  Never raises: de-duplication is an enhancement, and failing it must
    not fail an ingest.
    """
    from cocoindex_integration.entity_resolution import resolve_entity_names  # noqa: PLC0415

    names: List[str] = []
    for _t in (pg_triples or []):
        names.extend((_t.subject, _t.obj))
    for _r in (rdf_rows or []):
        names.extend((_r.subject_label, _r.obj_label))
    if not names:
        return

    llm = embed_model = None
    if strategy == "llm":
        # Both are required — resolve_entity_names downgrades to 'normalize'
        # with a warning when either is missing, which reads as "llm did nothing".
        from cocoindex_integration.functions.embedding import get_llamaindex_embedding  # noqa: PLC0415
        from cocoindex_integration.functions.llm import get_llama_index_llm  # noqa: PLC0415
        try:
            llm = get_llama_index_llm(
                llm_provider or os.getenv("LLM_PROVIDER", "openai"),
                json.loads(llm_config_json or "{}"),
            )
            embed_model = get_llamaindex_embedding()
        except Exception as _exc:  # noqa: BLE001
            logger.warning("Entity resolution: cannot build models (%s)", _exc)

    canonical = resolve_entity_names(
        names, strategy=strategy, llm=llm, embed_model=embed_model
    )
    _merged = {k: v for k, v in canonical.items() if k != v}
    if not _merged:
        return

    for _t in (pg_triples or []):
        _t.subject = canonical.get(_t.subject, _t.subject)
        _t.obj = canonical.get(_t.obj, _t.obj)
    for _r in (rdf_rows or []):
        _r.subject_label = canonical.get(_r.subject_label, _r.subject_label)
        _r.obj_label = canonical.get(_r.obj_label, _r.obj_label)

    logger.info(
        "[resolve] %s: merged %d entity name(s) in '%s' (e.g. %s)",
        strategy, len(_merged), file_name,
        ", ".join(f"{k!r}->{v!r}" for k, v in list(_merged.items())[:3]),
    )


async def process_document(
    file_bytes: bytes,
    file_name: str,
    file_path: str,
    source_type: str,
    modified_at: str,
    cfg_json: str,                     # JSON-serialised config dict for memo key
) -> None:
    """Full flexible-graphrag pipeline as a single memoised CocoIndex component.

    Memoised on (file_bytes, cfg_json).  Changing any config value — model,
    chunk size, ontology, extractor type — only re-processes affected documents.

    Parameters
    ----------
    cfg_json:
        JSON from ``load_config_from_env()``.  Include it as a pipeline
        argument so CocoIndex fingerprints it and re-runs when config changes.
    """
    cfg = json.loads(cfg_json)
    await _run_pipeline(file_bytes, file_name, file_path, source_type, modified_at, cfg)


# ─────────────────────────────────────────────────────────────────────────────
# _run_pipeline — the actual workhorse
# ─────────────────────────────────────────────────────────────────────────────

async def _run_pipeline(
    file_bytes: bytes,
    file_name: str,
    file_path: str,
    source_type: str,
    modified_at: str,
    cfg: Dict[str, Any],
    source_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """parse → chunk → embed → KG extract → write to targets."""
    import os as _os

    _state.reset_native_pg_write_skipped()

    _reader_metadata: Dict[str, Any] = dict(source_metadata) if source_metadata else {}

    from cocoindex_integration.functions.doc_processing import (
        parse_document, build_parse_cfg_json, decode_parse_result,
    )
    from cocoindex_integration.functions.chunking import (
        split_with_llamaindex, split_with_langchain, split_with_cocoindex,
    )
    from cocoindex_integration.functions.kg_extraction import (
        extract_kg_llamaindex, extract_kg_langchain, extract_kg_custom,
        load_ontology_schema_json, load_extractor_config_json,
        _kg_result_from_json,
    )

    import time as _time_mod
    _t0 = _time_mod.perf_counter()

    # ── 1. Parse ─────────────────────────────────────────────────────────────
    _emit_progress(event="file_stage", file_name=file_name, file_path=file_path, stage="parsing")
    _parse_result = await parse_document(file_bytes, file_name, build_parse_cfg_json(cfg))
    text, _parse_metadata = decode_parse_result(_parse_result)
    logger.debug("[timing] %s parse=%.1fs", file_name, _time_mod.perf_counter() - _t0)
    _emit_progress(event="file_stage", file_name=file_name, file_path=file_path, stage="parsed")

    if not text or not text.strip():
        logger.warning("Empty text for '%s' — skipping", file_name)
        _emit_progress(event="file_done", file_name=file_name, file_path=file_path, status="skipped")
        return

    # ── 2. Chunk ─────────────────────────────────────────────────────────────
    chunk_size = cfg.get("chunk_size", 1024)
    overlap = cfg.get("chunk_overlap", 128)
    _chunker = cfg.get("chunker_backend", "llamaindex").lower()
    if _chunker == "langchain":
        _lc_st = cfg.get("lc_splitter_type", "recursive")
        chunks = split_with_langchain(text, chunk_size, overlap, _lc_st)
        logger.info(
            "[chunk] LangChain %sSplitter: %d chunk(s) from '%s' (size=%d overlap=%d)",
            _lc_st.capitalize(), len(chunks), file_name, chunk_size, overlap,
        )
    elif _chunker == "cocoindex":
        _coco_splitter = cfg.get("cocoindex_splitter_type", "recursive")
        _coco_lang = cfg.get("cocoindex_language", "")
        if _coco_splitter == "recursive" and not _coco_lang:
            try:
                from cocoindex.ops.text import detect_code_language
                _coco_lang = detect_code_language(filename=file_name) or ""
            except (ImportError, Exception):
                _coco_lang = ""
        _raw_seps = cfg.get("cocoindex_separators", "")
        if _raw_seps and _coco_splitter == "separator":
            from cocoindex_integration.functions.chunking import _parse_cocoindex_separators
            _seps_list = _parse_cocoindex_separators(_raw_seps)
            _seps_json = json.dumps(_seps_list)
        else:
            _seps_json = ""
        chunks = split_with_cocoindex(text, chunk_size, overlap, _coco_splitter, _coco_lang, _seps_json)
        if _coco_splitter == "recursive":
            _lang_note = f" language={_coco_lang}" if _coco_lang else " language=auto"
        else:
            _seps_display = json.loads(_seps_json) if _seps_json else ["\\n{2,}", "[.!?…]\\s+", "[:;]\\s+"]
            _lang_note = f" separators={_seps_display}"
        logger.info(
            "[chunk] CocoIndex %sSplitter:%s -> %d chunk(s) from '%s' (size=%d overlap=%d)",
            _coco_splitter.capitalize(), _lang_note, len(chunks), file_name, chunk_size, overlap,
        )
    else:  # "llamaindex" (default)
        chunks = split_with_llamaindex(text, chunk_size, overlap)
        logger.info(
            "[chunk] LlamaIndex SentenceSplitter: %d chunk(s) from '%s' (size=%d overlap=%d)",
            len(chunks), file_name, chunk_size, overlap,
        )

    if not chunks:
        _emit_progress(event="file_done", file_name=file_name, file_path=file_path, status="skipped")
        return
    _emit_progress(event="file_stage", file_name=file_name, file_path=file_path,
                   stage="chunked", detail=str(len(chunks)))

    doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_type}:{file_path}"))

    total_chunks = len(chunks)
    _, ext = _os.path.splitext(file_name)
    file_type = ext.lstrip(".").lower()

    # ── Canonical metadata ────────────────────────────────────────────────────
    _base_metadata: Dict[str, Any] = {}
    _base_metadata.update(_reader_metadata)
    _base_metadata.update(_parse_metadata)
    _base_meta_update: dict = {
        "doc_id": doc_id,
        "ref_doc_id": doc_id,
        "file_name": file_name,
        "file_path": file_path,
        "file_type": file_type,
        "source_type": source_type,
    }
    # Only include modified_at when non-empty — Elasticsearch date fields reject "".
    if modified_at:
        _base_meta_update["modified_at"] = modified_at
    _base_metadata.update(_base_meta_update)

    def _chunk_metadata(chunk_index: int, start_idx: int = 0, end_idx: int = 0) -> Dict[str, Any]:
        meta = dict(_base_metadata)
        meta["chunk_index"] = chunk_index
        meta["total_chunks"] = total_chunks
        if start_idx:
            meta["start_char_idx"] = start_idx
        if end_idx:
            meta["end_char_idx"] = end_idx
        return meta

    enable_kg = _resolve_enable_kg(cfg)
    # NOT lowercased — a custom spec can be "pkg.mod:MyExtractor" or a Windows
    # path, both of which are case-sensitive.  Only the built-in comparison folds.
    kg_backend = str(cfg.get("kg_extractor_backend", "llamaindex"))
    _kg_custom_spec = ""
    _kg_custom_version = ""
    if enable_kg and kg_backend.lower() not in ("llamaindex", "langchain"):
        # Resolve once per document rather than per chunk, and read the version
        # here so it can enter extract_kg_custom's memo key.
        from cocoindex_integration.functions.kg_extractors import (  # noqa: PLC0415
            resolve_kg_extractor,
        )
        try:
            _kg_cls = resolve_kg_extractor(kg_backend)
            _kg_custom_spec = kg_backend
            _kg_custom_version = str(getattr(_kg_cls, "version", "") or "")
            logger.info(
                "[kg] custom extractor: %s (name=%s version=%s)",
                _kg_cls.__name__, getattr(_kg_cls, "name", "?"), _kg_custom_version,
            )
        except Exception as _exc:
            logger.error(
                "[kg] cannot resolve kg_extractor_backend=%r (%s: %s) — "
                "falling back to llamaindex",
                kg_backend, type(_exc).__name__, _exc,
            )
            kg_backend = "llamaindex"
    llm_provider = cfg.get("llm_provider", "openai")
    llm_config_json = cfg.get("llm_config_json", "{}")
    extractor_config_json = load_extractor_config_json()

    vector_target = _sel._pick_vector_target(cfg)
    pg_target = _sel._pick_pg_target(cfg)
    rdf_target = _sel._pick_rdf_target(cfg)
    # each graph only when this ingest builds it (graph_flags.py)
    _graphs = _resolve_graphs(cfg)
    if not _graphs.graph:
        pg_target = None
    if not _graphs.rdf:
        rdf_target = None
    search_target = _sel._pick_search_target(cfg)

    _kg_will_run = enable_kg and (pg_target is not None or rdf_target is not None)
    schema_json = (
        load_ontology_schema_json(
            ontology_paths=cfg.get("ontology_paths") or None,
            ontology_dir=cfg.get("ontology_dir") or None,
            use_ontology=cfg.get("use_ontology", False),
        )
        if _kg_will_run
        else ""
    )

    # ── 3. Initialise targets ─────────────────────────────────────────────────
    _t_setup = _time_mod.perf_counter()
    _target_names = {
        id(vector_target): "vector",
        id(pg_target): "pg_graph",
        id(rdf_target): "rdf_graph",
        id(search_target): "search",
    }
    for _t in (vector_target, pg_target, rdf_target, search_target):
        if _t is None or not hasattr(_t, "setup"):
            continue
        try:
            await _t.setup()
        except Exception as _setup_exc:
            _tname = _target_names.get(id(_t), type(_t).__name__)
            logger.warning(
                "Target '%s' setup failed — that store will be skipped: %s",
                _tname, _setup_exc,
            )
            if _t is vector_target:
                vector_target = None  # type: ignore[assignment]
            elif _t is pg_target:
                pg_target = None  # type: ignore[assignment]
            elif _t is rdf_target:
                rdf_target = None  # type: ignore[assignment]
            elif _t is search_target:
                search_target = None  # type: ignore[assignment]
    logger.debug("[timing] %s target_setup=%.1fs", file_name, _time_mod.perf_counter() - _t_setup)

    from cocoindex_integration.connectors.rows import (  # noqa: PLC0415
        VectorRow, ChunkRow, KGTripleRow, SearchRow,
    )
    from cocoindex_integration.connectors.flexible.vector import _FileVectorSpec  # noqa: PLC0415
    from cocoindex_integration.connectors.flexible.property_graph import _FilePGSpec  # noqa: PLC0415
    from cocoindex_integration.connectors.flexible.search import _FileSearchSpec  # noqa: PLC0415
    from cocoindex_integration.connectors.flexible.rdf import _FileRDFSpec  # noqa: PLC0415

    # ── 3b. Batch-embed via memoized helper ──────────────────────────────────
    _all_chunk_texts: List[str] = [getattr(c, "text", str(c)) for c in chunks]
    _all_embeddings: List[List[float]] = [[] for _ in chunks]

    _vector_uses_coco_embed = (
        vector_target is not None
        and cfg.get("vector_backend", "llamaindex") == "cocoindex"
    )
    # All vector targets need embeddings — flexible (llamaindex/langchain) targets call
    # insert_nodes() which requires node.embedding to be set, same as native CocoIndex
    # targets.  The old condition only covered native targets, causing
    # "embedding not set" errors when skip_graph=True (which clears the KG path that
    # previously provided the only non-native reason to embed).
    _needs_embeddings = (vector_target is not None) or (pg_target is not None and enable_kg)
    if _needs_embeddings and _all_chunk_texts:
        try:
            _t_emb = _time_mod.perf_counter()
            _embed_cfg_json = _build_embed_cfg_json(cfg)
            _embed_result_json = await _embed_chunks_cached(
                json.dumps(_all_chunk_texts),
                _embed_cfg_json,
            )
            _all_embeddings = json.loads(_embed_result_json)
            logger.debug(
                "[timing] %s embed=%.1fs (%d chunks)",
                file_name, _time_mod.perf_counter() - _t_emb, len(_all_chunk_texts),
            )
        except Exception as _be:
            logger.warning("Embedding failed for '%s': %s", file_name, _be)
    if _needs_embeddings:
        _emit_progress(event="file_stage", file_name=file_name, file_path=file_path, stage="embedded")

    _kg_timeout = int(
        cfg.get("kg_extraction_timeout", None)
        or os.getenv("KG_EXTRACTION_TIMEOUT", "120")
    )

    _vec_rows: List[VectorRow] = []
    _search_rows: List[SearchRow] = []
    _pg_chunks: List[ChunkRow] = []
    _pg_triples: List[KGTripleRow] = []
    _rdf_rows: List[Any] = []

    _kg_enabled = _kg_will_run

    try:
        if _kg_enabled:
            _emit_progress(
                event="file_stage", file_name=file_name, file_path=file_path,
                stage="kg_extracting",
            )
            logger.info(
                "[kg] extracting from '%s' (%d chunk(s), backend=%s)",
                file_name, total_chunks, kg_backend,
            )

        # ── 4. Per-chunk processing ───────────────────────────────────────────
        for i, chunk in enumerate(chunks):
            chunk_text = getattr(chunk, "text", str(chunk))
            if not chunk_text.strip():
                continue

            chunk_id: str = getattr(chunk, "node_id", None) or f"{doc_id}:chunk:{i}"
            embedding: List[float] = _all_embeddings[i] if i < len(_all_embeddings) else []

            # 4b. Write vector row
            if vector_target is not None:
                start_idx = getattr(chunk, "start_char_idx", 0) or 0
                end_idx = getattr(chunk, "end_char_idx", 0) or 0
                vrow = VectorRow(
                    doc_id=doc_id,
                    chunk_index=i,
                    text=chunk_text,
                    embedding=embedding,
                    file_name=file_name,
                    file_path=file_path,
                    file_type=file_type,
                    source_type=source_type,
                    modified_at=modified_at,
                    ref_doc_id=doc_id,
                    start_char_idx=start_idx,
                    end_char_idx=end_idx,
                    total_chunks=total_chunks,
                    metadata=_chunk_metadata(i, start_idx, end_idx),
                )
                _vec_rows.append(vrow)

            # 4c. Search row
            if search_target is not None:
                srow = SearchRow(
                    doc_id=doc_id,
                    chunk_index=i,
                    text=chunk_text,
                    embedding=embedding,
                    file_name=file_name,
                    file_path=file_path,
                    file_type=file_type,
                    source_type=source_type,
                    modified_at=modified_at,
                    ref_doc_id=doc_id,
                    metadata=_chunk_metadata(i),
                )
                _search_rows.append(srow)

            # 4c-pg. Chunk node for property graph
            if pg_target is not None and enable_kg:
                crow = ChunkRow(
                    doc_id=doc_id,
                    chunk_index=i,
                    chunk_id=chunk_id,
                    chunk_text=chunk_text,
                    file_name=file_name,
                    file_path=file_path,
                    file_type=file_type,
                    modified_at=modified_at,
                    embedding=embedding if embedding else None,
                    metadata=_chunk_metadata(i),
                )
                _pg_chunks.append(crow)

            # 4d. KG extraction
            if enable_kg and (pg_target is not None or rdf_target is not None):
                try:
                    _kg_kwargs = dict(
                        schema_json=schema_json,
                        llm_provider=llm_provider,
                        llm_config_json=llm_config_json,
                        extractor_config_json=extractor_config_json,
                    )
                    if _kg_custom_spec:
                        _extract_coro = extract_kg_custom(
                            chunk_text,
                            extractor_spec=_kg_custom_spec,
                            extractor_version=_kg_custom_version,
                            **_kg_kwargs,
                        )
                    elif kg_backend.lower() == "langchain":
                        _extract_coro = extract_kg_langchain(chunk_text, **_kg_kwargs)
                    else:
                        _extract_coro = extract_kg_llamaindex(chunk_text, **_kg_kwargs)
                    _kg_raw = await asyncio.wait_for(_extract_coro, timeout=_kg_timeout)
                    kg_result = _kg_result_from_json(_kg_raw)
                    logger.info(
                        "[kg] chunk %d of '%s': %d triple(s) extracted (backend=%s)",
                        i, file_name, len(kg_result.triples), kg_backend,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "KG extraction timed out after %ds for chunk %d of '%s' — skipping",
                        _kg_timeout, i, file_name,
                    )
                    continue
                except Exception as exc:
                    logger.warning("KG extraction error for chunk %d of '%s': %s", i, file_name, exc)
                    continue

                # Entity properties live on kg_result.entities, keyed by name,
                # while the row is triple-shaped — so index them once per chunk
                # and attach each endpoint's properties to the triples it
                # appears in.  Without this the extractor's KGEntity.properties
                # (everything an ontology's owl:DatatypeProperty declarations
                # produce) is discarded at the row boundary and never reaches
                # any target.
                _entity_props: Dict[str, Dict[str, Any]] = {}
                if not cfg.get("disable_properties", False):
                    for _ent in (getattr(kg_result, "entities", None) or []):
                        _ep = getattr(_ent, "properties", None) or {}
                        # KGEntity's name field is `label` (entity_type holds the
                        # type); triples key their endpoints on that same string.
                        _en = getattr(_ent, "label", "") or ""
                        if _en and _ep:
                            # First occurrence wins, matching how a conflicting
                            # entity TYPE is resolved downstream.
                            _entity_props.setdefault(_en, dict(_ep))

                def _props_json(_name: str) -> str:
                    _p = _entity_props.get(_name)
                    return json.dumps(_p, sort_keys=True) if _p else "{}"

                for j, triple in enumerate(kg_result.triples):
                    kgrow = KGTripleRow(
                        doc_id=doc_id,
                        triple_index=j,
                        subject=triple.subject,
                        subject_type=triple.subject_type,
                        predicate=triple.predicate,
                        obj=triple.obj,
                        obj_type=triple.obj_type,
                        chunk_id=chunk_id,
                        file_name=file_name,
                        source_type=source_type,
                        ref_doc_id=doc_id,
                        properties_json=json.dumps(triple.relation_properties) if triple.relation_properties else "{}",
                        subject_properties_json=_props_json(triple.subject),
                        obj_properties_json=_props_json(triple.obj),
                    )
                    if pg_target is not None:
                        _pg_triples.append(kgrow)
                    if rdf_target is not None:
                        _rdf_rows.append(kgrow)

        if _kg_enabled:
            _emit_progress(
                event="file_stage", file_name=file_name, file_path=file_path,
                stage="kg_extracted",
                detail=str(len(_pg_triples)),
            )

        # ── 5. Declare target states with CocoIndex ──────────────────────────
        from cocoindex_integration.connectors.cocoindex.vector import CocoQdrant  # noqa: PLC0415
        from cocoindex_integration.connectors.cocoindex.vector import CocoLanceDB  # noqa: PLC0415
        from cocoindex_integration.connectors.cocoindex.vector import CocoPostgres  # noqa: PLC0415
        from cocoindex_integration.connectors.cocoindex.property_graph import CocoNeo4j  # noqa: PLC0415
        from cocoindex_integration.connectors.cocoindex.property_graph import CocoFalkorDB  # noqa: PLC0415
        from cocoindex_integration.connectors.cocoindex.property_graph import CocoSurrealDB  # noqa: PLC0415
        from cocoindex_integration.connectors.seam import (  # noqa: PLC0415
            is_coco_vector as _is_coco_vector,
            is_coco_pg as _is_coco_pg,
        )

        if vector_target is not None and _vec_rows:
            _emit_progress(
                event="file_stage", file_name=file_name, file_path=file_path,
                stage="vector_indexing", detail=str(len(_vec_rows)),
            )

        if isinstance(vector_target, CocoQdrant) and _vec_rows:
            try:
                from qdrant_client.models import PointStruct as _QdrantPoint  # noqa: PLC0415
                _q_coll = _state._root_qdrant_coll
                if _q_coll is None:
                    logger.warning(
                        "[native/qdrant] root collection mount unavailable — "
                        "skipping Qdrant write for '%s'", file_name,
                    )
                else:
                    for _vr in _vec_rows:
                        _pt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{_vr.doc_id}:{_vr.chunk_index}"))
                        _q_coll.declare_point(_QdrantPoint(
                            id=_pt_id,
                            vector={"text-dense": _vr.embedding},
                            payload={
                                **(_vr.metadata or {}),
                                "doc_id": _vr.doc_id,
                                "chunk_index": _vr.chunk_index,
                                "text": _vr.text,
                                "file_name": _vr.file_name,
                                "file_path": _vr.file_path,
                                "file_type": _vr.file_type,
                                "source_type": _vr.source_type,
                                "modified_at": _vr.modified_at,
                                "ref_doc_id": _vr.ref_doc_id,
                                "start_char_idx": _vr.start_char_idx,
                                "end_char_idx": _vr.end_char_idx,
                                "total_chunks": _vr.total_chunks,
                            },
                        ))
                    logger.info(
                        "[native/qdrant] declared %d point(s) for '%s' in collection '%s'",
                        len(_vec_rows), file_name, vector_target.collection_name,
                    )
            except Exception as _qe:
                logger.error("[native/qdrant] declaration failed for '%s': %s", file_name, _qe)

        elif isinstance(vector_target, CocoLanceDB) and _vec_rows:
            try:
                _l_table = _state._root_lance_table
                if _l_table is None:
                    logger.warning(
                        "[native/lancedb] root table mount unavailable — "
                        "skipping LanceDB write for '%s'", file_name,
                    )
                else:
                    for _vr in _vec_rows:
                        _pt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{_vr.doc_id}:{_vr.chunk_index}"))
                        _meta = dict(_vr.metadata or {})
                        _l_table.declare_row(row={
                            "point_id": _pt_id,
                            **(_meta or {}),
                            "doc_id": _vr.doc_id,
                            "chunk_index": _vr.chunk_index,
                            "text": _vr.text,
                            "file_name": _vr.file_name,
                            "file_path": _vr.file_path,
                            "file_type": _vr.file_type,
                            "source_type": _vr.source_type,
                            "modified_at": _vr.modified_at,
                            "ref_doc_id": _vr.ref_doc_id,
                            "start_char_idx": _vr.start_char_idx,
                            "end_char_idx": _vr.end_char_idx,
                            "total_chunks": _vr.total_chunks,
                            "metadata_json": json.dumps(_meta, default=str),
                            "embedding": _vr.embedding,
                        })
                    logger.info(
                        "[native/lancedb] declared %d row(s) for '%s' in table '%s'",
                        len(_vec_rows), file_name, vector_target.table_name,
                    )
            except Exception as _le:
                logger.error("[native/lancedb] declaration failed for '%s': %s", file_name, _le)

        elif isinstance(vector_target, CocoPostgres) and _vec_rows:
            try:
                _pg_table = _state._root_postgres_table
                if _pg_table is None:
                    logger.warning(
                        "[native/postgres] root table mount unavailable — "
                        "skipping Postgres write for '%s'", file_name,
                    )
                else:
                    for _vr in _vec_rows:
                        _pt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{_vr.doc_id}:{_vr.chunk_index}"))
                        _meta = dict(_vr.metadata or {})
                        _pg_table.declare_row(row={
                            "point_id": _pt_id,
                            **(_meta or {}),
                            "doc_id": _vr.doc_id,
                            "chunk_index": _vr.chunk_index,
                            "text": _vr.text,
                            "file_name": _vr.file_name,
                            "file_path": _vr.file_path,
                            "file_type": _vr.file_type,
                            "source_type": _vr.source_type,
                            "modified_at": _vr.modified_at,
                            "ref_doc_id": _vr.ref_doc_id,
                            "start_char_idx": _vr.start_char_idx,
                            "end_char_idx": _vr.end_char_idx,
                            "total_chunks": _vr.total_chunks,
                            "metadata_json": json.dumps(_meta, default=str),
                            "embedding": _vr.embedding,
                        })
                    logger.info(
                        "[native/postgres] declared %d row(s) for '%s' in table '%s'",
                        len(_vec_rows), file_name, vector_target.table_name,
                    )
            except Exception as _pe:
                logger.error("[native/postgres] declaration failed for '%s': %s", file_name, _pe)

        elif vector_target is not None and not _is_coco_vector(vector_target):
            _vp = _providers._get_or_create_vector_provider(vector_target)
            if _vp is not None:
                from cocoindex_integration.connectors.flexible.base import (  # noqa: PLC0415
                    note_target_pending,
                )
                note_target_pending(doc_id)
                coco.declare_target_state(
                    _vp.target_state(doc_id, _FileVectorSpec(doc_id=doc_id, rows=_vec_rows))
                )

        # ── 4f. Entity-name de-duplication ────────────────────────────────
        # Runs here, after every chunk of this document has been extracted and
        # before anything is written, because extraction is per chunk: "Bob" in
        # one chunk and "Bob Smith" in the next are only comparable once both
        # exist.  Per document, not per corpus — merging across documents would
        # need a view this function does not have.
        _resolution = str(cfg.get("entity_resolution", "none") or "none").lower()
        if _resolution != "none" and (_pg_triples or _rdf_rows):
            try:
                # In a thread: resolve_entity_names() uses asyncio.run() for the
                # llm strategy, which raises inside a running loop and is caught
                # as a silent downgrade to normalize.
                await asyncio.to_thread(
                    _apply_entity_resolution,
                    _resolution, _pg_triples, _rdf_rows,
                    llm_provider, llm_config_json, file_name,
                )
            except Exception as _re:  # noqa: BLE001 - resolution is an enhancement
                logger.warning(
                    "Entity resolution failed for '%s' (%s) — writing unmerged names",
                    file_name, _re,
                )

        # ── 5A. CocoIndex-native Neo4j / FalkorDB / SurrealDB ──────────────
        if pg_target is not None and (_pg_chunks or _pg_triples):
            _emit_progress(
                event="file_stage", file_name=file_name, file_path=file_path,
                stage="graph_indexing",
                detail=f"{len(_pg_chunks)} chunks, {len(_pg_triples)} triples",
            )
        if isinstance(pg_target, (CocoNeo4j, CocoFalkorDB, CocoSurrealDB)):
            await _sel._ensure_native_pg_roots_if_missing(cfg)
            if isinstance(pg_target, CocoNeo4j):
                _pg_log = "neo4j"
                _chunk_tbl = _state._root_neo4j_chunk_tbl
                _entity_tbl = _state._root_neo4j_entity_tbl
                _pg_driver = _state._root_neo4j_driver
            elif isinstance(pg_target, CocoFalkorDB):
                _pg_log = "falkordb"
                _chunk_tbl = _state._root_falkordb_chunk_tbl
                _entity_tbl = _state._root_falkordb_entity_tbl
                _pg_driver = _state._root_falkordb_driver
            else:
                _pg_log = "surrealdb"
                _chunk_tbl = _state._root_surrealdb_chunk_tbl
                _entity_tbl = _state._root_surrealdb_entity_tbl
                _pg_driver = _state._root_surrealdb_client
            try:
                from cocoindex_integration.connectors.cocoindex._runtime import (  # noqa: PLC0415
                    SHARED_ENTITY_LABEL as _SHARED_ENTITY_LABEL,
                    SHARED_NODE_LABEL   as _SHARED_NODE_LABEL,
                    _safe_rel_type      as _safe_rel_type_neo4j,
                )
                from cocoindex_integration.connectors.flexible.base import (  # noqa: PLC0415
                    parse_entity_props as _parse_entity_props,
                )
                from cocoindex_integration.connectors.cocoindex.property_graph import (  # noqa: PLC0415
                    ensure_node_stubs_sync        as _ensure_node_stubs_sync,
                    write_relations_sync          as _write_neo4j_relations_sync,
                    set_entity_type_labels_sync   as _set_entity_type_labels_sync,
                    set_entity_properties_sync    as _set_entity_properties_sync,
                )

                _F_ENT = "Entity"
                _F_REL = "RELATED_TO"

                _all_types: Dict[str, set] = {}
                for _tr in _pg_triples:
                    _st = (_tr.subject_type or _F_ENT).strip() or _F_ENT
                    _ot = (_tr.obj_type     or _F_ENT).strip() or _F_ENT
                    _all_types.setdefault(_tr.subject, set()).add(_st)
                    _all_types.setdefault(_tr.obj,     set()).add(_ot)

                def _type_labels(_name: str) -> List[str]:
                    _types = sorted(_all_types.get(_name, {_F_ENT}) - {_F_ENT})
                    return _types if _types else [_F_ENT]

                _entity_names = sorted(
                    {_tr.subject for _tr in _pg_triples}
                    | {_tr.obj for _tr in _pg_triples}
                )
                _entity_emb: Dict[str, List[float]] = {}
                if _entity_names:
                    try:
                        _ent_emb_json = await _embed_chunks_cached(
                            json.dumps(_entity_names),
                            _build_embed_cfg_json(cfg),
                        )
                        _ent_vecs = json.loads(_ent_emb_json)
                        _entity_emb = {
                            _n: _ent_vecs[_k]
                            for _k, _n in enumerate(_entity_names)
                            if _k < len(_ent_vecs) and _ent_vecs[_k]
                        }
                    except Exception as _eexc:
                        logger.warning("Entity embedding failed for '%s': %s", file_name, _eexc)

                _emb_dim = (
                    len(_all_embeddings[0]) if _all_embeddings and _all_embeddings[0]
                    else (len(next(iter(_entity_emb.values()))) if _entity_emb else 0)
                )

                if _emb_dim > 0 and _entity_tbl is not None:
                    if isinstance(pg_target, CocoSurrealDB):
                        pg_target._declare_vector_index(_entity_tbl, _emb_dim)
                    else:
                        pg_target._declare_vector_index(_entity_tbl, _SHARED_ENTITY_LABEL, _emb_dim)

                if _chunk_tbl is None or _entity_tbl is None:
                    _state._native_pg_write_skipped = True
                    logger.error(
                        "[native/%s] root tables unavailable — "
                        "skipping graph write for '%s'. "
                        "Ensure the database is running and reachable.",
                        _pg_log, file_name,
                    )
                else:
                    for _cr in _pg_chunks:
                        _chunk_row: Dict[str, Any] = {
                            pg_target.chunk_pk: _cr.chunk_id,
                            "_node_type":   "TextNode",
                            "doc_id":       _cr.doc_id,
                            "chunk_index":  _cr.chunk_index,
                            "text":         _cr.chunk_text,
                            "file_name":    _cr.file_name,
                            "file_path":    _cr.file_path,
                            "file_type":    _cr.file_type,
                            "modified_at":  _cr.modified_at,
                        }
                        if _cr.embedding:
                            _chunk_row["embedding"] = _cr.embedding
                        _chunk_tbl.declare_record(row=_chunk_row)

                    _seen_entities: set = set()
                    _seen_mentions: set = set()
                    _cypher_relations: List[Dict[str, Any]] = []
                    _cypher_mentions:  List[Dict[str, Any]] = []
                    _entity_id_labels: Dict[str, List[str]] = {}
                    # Ontology-declared entity properties, patched onto the nodes
                    # after CocoIndex writes the fixed TableSchema columns.  The
                    # schema is a fixed column set, so per-type properties
                    # (SALARY on PERSON, BUDGET on PROJECT) cannot live in it —
                    # same reason entity_labels needs its own post-MERGE patch.
                    _entity_id_props: Dict[str, Dict[str, Any]] = {}

                    for _idx, _tr in enumerate(_pg_triples):
                        _pp = (_tr.predicate or _F_REL).strip() or _F_REL
                        _head_id = f"{_tr.doc_id}:{_tr.subject}"
                        _tail_id = f"{_tr.doc_id}:{_tr.obj}"

                        if _head_id not in _seen_entities:
                            _h_labels = _type_labels(_tr.subject)
                            _h_row: Dict[str, Any] = {
                                pg_target.entity_pk:  _head_id,
                                "name":               _tr.subject,
                                "entity_type":        _h_labels[0],
                                "entity_labels":      _h_labels,
                                "doc_id":             _tr.doc_id,
                                "ref_doc_id":         _tr.ref_doc_id,
                                "file_name":          _tr.file_name,
                                "source_type":        _tr.source_type,
                            }
                            if _tr.chunk_id:
                                _h_row["triplet_source_id"] = _tr.chunk_id
                            _h_vec = _entity_emb.get(_tr.subject)
                            if _h_vec:
                                _h_row["embedding"] = _h_vec
                            _entity_tbl.declare_record(row=_h_row)
                            _seen_entities.add(_head_id)
                            _entity_id_labels[_head_id] = _h_labels
                            _h_props = _parse_entity_props(
                                getattr(_tr, "subject_properties_json", "{}"))
                            if _h_props:
                                _entity_id_props.setdefault(_head_id, _h_props)

                        if _tail_id not in _seen_entities:
                            _t_labels = _type_labels(_tr.obj)
                            _t_row: Dict[str, Any] = {
                                pg_target.entity_pk:  _tail_id,
                                "name":               _tr.obj,
                                "entity_type":        _t_labels[0],
                                "entity_labels":      _t_labels,
                                "doc_id":             _tr.doc_id,
                                "ref_doc_id":         _tr.ref_doc_id,
                                "file_name":          _tr.file_name,
                                "source_type":        _tr.source_type,
                            }
                            if _tr.chunk_id:
                                _t_row["triplet_source_id"] = _tr.chunk_id
                            _t_vec = _entity_emb.get(_tr.obj)
                            if _t_vec:
                                _t_row["embedding"] = _t_vec
                            _entity_tbl.declare_record(row=_t_row)
                            _seen_entities.add(_tail_id)
                            _entity_id_labels[_tail_id] = _t_labels
                            _t_props = _parse_entity_props(
                                getattr(_tr, "obj_properties_json", "{}"))
                            if _t_props:
                                _entity_id_props.setdefault(_tail_id, _t_props)

                        _cypher_relations.append({
                            "from_id":   _head_id,
                            "to_id":     _tail_id,
                            "rel_type":  _safe_rel_type_neo4j(_pp),
                            "rel_id":    f"{_tr.doc_id}:rel:{_idx}",
                            "predicate": _pp,
                            "doc_id":    _tr.doc_id,
                            "chunk_id":  _tr.chunk_id or "",
                        })

                        for _eid in (_head_id, _tail_id):
                            _mk = (_tr.chunk_id or "", _eid)
                            if _mk[0] and _mk not in _seen_mentions:
                                _cypher_mentions.append({
                                    "chunk_id":   _tr.chunk_id,
                                    "entity_id":  _eid,
                                    "mention_id": f"{_tr.chunk_id}->{_eid}",
                                    "doc_id":     _tr.doc_id,
                                })
                                _seen_mentions.add(_mk)

                    if _pg_driver is not None and (_cypher_relations or _cypher_mentions):
                        try:
                            _chunk_ids_for_stub = [_cr.chunk_id for _cr in _pg_chunks]
                            if isinstance(pg_target, CocoSurrealDB):
                                from cocoindex_integration.connectors.cocoindex.property_graph._surreal import (  # noqa: PLC0415
                                    ensure_node_stubs_surreal_sync,
                                    write_relations_surreal_sync,
                                    set_entity_properties_surreal_sync,
                                )
                                await asyncio.to_thread(
                                    ensure_node_stubs_surreal_sync,
                                    _pg_driver,
                                    list(_seen_entities),
                                    _chunk_ids_for_stub,
                                    pg_target.entity_table_name,
                                    pg_target.chunk_table_name,
                                )
                                await asyncio.to_thread(
                                    write_relations_surreal_sync,
                                    _pg_driver,
                                    doc_id,
                                    _cypher_relations,
                                    _cypher_mentions,
                                    pg_target.chunk_table_name,
                                    pg_target.entity_table_name,
                                    pg_target.mention_rel_type,
                                )
                                if _entity_id_props:
                                    await asyncio.to_thread(
                                        set_entity_properties_surreal_sync,
                                        _pg_driver,
                                        _entity_id_props,
                                        pg_target.entity_table_name,
                                    )
                            else:
                                await asyncio.to_thread(
                                    _ensure_node_stubs_sync,
                                    _pg_driver,
                                    list(_seen_entities),
                                    _chunk_ids_for_stub,
                                    _SHARED_ENTITY_LABEL,
                                    _SHARED_NODE_LABEL,
                                )
                                if _entity_id_labels:
                                    await asyncio.to_thread(
                                        _set_entity_type_labels_sync,
                                        _pg_driver,
                                        _entity_id_labels,
                                        _SHARED_ENTITY_LABEL,
                                    )
                                if _entity_id_props:
                                    await asyncio.to_thread(
                                        _set_entity_properties_sync,
                                        _pg_driver,
                                        _entity_id_props,
                                        _SHARED_ENTITY_LABEL,
                                    )
                                await asyncio.to_thread(
                                    _write_neo4j_relations_sync,
                                    _pg_driver,
                                    doc_id,
                                    _cypher_relations,
                                    _cypher_mentions,
                                    _SHARED_ENTITY_LABEL,
                                    _SHARED_NODE_LABEL,
                                    pg_target.relation_type_prefix,
                                    pg_target.mention_rel_type,
                                )
                        except Exception as _re:
                            logger.warning(
                                "[native/%s] relation write failed for '%s': %s",
                                _pg_log, file_name, _re,
                            )
                    elif (_cypher_relations or _cypher_mentions) and _pg_driver is None:
                        _driver_label = (
                            "SurrealDB client" if isinstance(pg_target, CocoSurrealDB)
                            else "Cypher driver"
                        )
                        logger.warning(
                            "[native/%s] no direct %s — "
                            "%d relation(s) + %d MENTIONS skipped for '%s'",
                            _pg_log, _driver_label,
                            len(_cypher_relations), len(_cypher_mentions), file_name,
                        )

                    _all_type_names = sorted({
                        _tl
                        for _n in _all_types
                        for _tl in _type_labels(_n)
                    })
                    _all_rel_types = sorted({
                        _safe_rel_type_neo4j((_tr.predicate or _F_REL).strip() or _F_REL)
                        for _tr in _pg_triples
                    })
                    logger.info(
                        "[native/%s] declared %d chunk(s), %d entity(ies) "
                        "across type(s) %s, %d relation(s) across type(s) %s, "
                        "%d MENTIONS (emb_dim=%d) for '%s'",
                        _pg_log,
                        len(_pg_chunks), len(_seen_entities),
                        _all_type_names,
                        len(_cypher_relations), _all_rel_types,
                        len(_cypher_mentions), _emb_dim,
                        file_name,
                    )
            except Exception as _ne:
                logger.error(
                    "[native/%s] declaration failed for '%s': %s",
                    _pg_log, file_name, _ne,
                )

        elif pg_target is not None and not _is_coco_pg(pg_target):
            _pp = _providers._get_or_create_pg_provider(pg_target)
            if _pp is not None:
                from cocoindex_integration.connectors.flexible.base import (  # noqa: PLC0415
                    note_target_pending,
                )
                note_target_pending(doc_id)
                coco.declare_target_state(
                    _pp.target_state(
                        doc_id,
                        _FilePGSpec(doc_id=doc_id, triples=_pg_triples, chunks=_pg_chunks),
                    )
                )

        if search_target is not None and _search_rows:
            _emit_progress(
                event="file_stage", file_name=file_name, file_path=file_path,
                stage="search_indexing", detail=str(len(_search_rows)),
            )
            _sp = _providers._get_or_create_search_provider(search_target)
            if _sp is not None:
                from cocoindex_integration.connectors.flexible.base import (  # noqa: PLC0415
                    note_target_pending,
                )
                note_target_pending(doc_id)
                coco.declare_target_state(
                    _sp.target_state(doc_id, _FileSearchSpec(doc_id=doc_id, rows=_search_rows))
                )

        if rdf_target is not None and _rdf_rows:
            _emit_progress(
                event="file_stage", file_name=file_name, file_path=file_path,
                stage="rdf_indexing", detail=str(len(_rdf_rows)),
            )
            _rp = _providers._get_or_create_rdf_provider(rdf_target)
            if _rp is not None:
                from cocoindex_integration.connectors.flexible.base import (  # noqa: PLC0415
                    note_target_pending,
                )
                note_target_pending(doc_id)
                coco.declare_target_state(
                    _rp.target_state(doc_id, _FileRDFSpec(doc_id=doc_id, rows=_rdf_rows))
                )

        _emit_progress(
            event="file_stage", file_name=file_name, file_path=file_path,
            stage="indexing_complete",
        )

    finally:
        for _t in (vector_target, pg_target, rdf_target, search_target):
            if _t is not None and hasattr(_t, "finalize"):
                try:
                    await _t.finalize()  # type: ignore[union-attr]
                except Exception as _fe:
                    logger.error("Target finalize error: %s", _fe)
        _emit_progress(event="file_done", file_name=file_name, file_path=file_path, status="completed")
