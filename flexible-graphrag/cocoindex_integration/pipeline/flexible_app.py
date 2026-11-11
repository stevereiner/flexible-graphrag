"""Flexible-source CocoIndex app and multi-source helpers.

Provides:
* ``_SOURCE_ENV_PREFIX`` / ``_harvest_env_prefix`` / ``_build_source_config_from_env``
  — source config assembly from environment variables.
* ``process_flexible_item`` / ``process_flexible_file``
  — ``@coco.fn(memo=True)`` entry points for eager and lazy flexible sources.
* ``flexible_app_main`` / ``build_flexible_source_app``
  — ``@coco.fn`` app_main and factory for the generic flexible-source app.
* ``build_app_for_config`` / ``build_apps_for_all_sources``
  — multi-source helpers called by :mod:`bridge` so each active datasource_config
  row gets its own ``coco.App`` without a manual "sync" button.

"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, NamedTuple, Optional

logger = logging.getLogger(__name__)

import cocoindex as coco  # noqa: E402

from cocoindex_integration.pipeline.env_config import load_config_from_env  # noqa: E402
from process.document_processor import format_parser_display_name  # noqa: E402
from cocoindex_integration.pipeline import run as _run  # noqa: E402
from cocoindex_integration.pipeline import selectors as _sel  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Source env-var prefix map
# ─────────────────────────────────────────────────────────────────────────────

_SOURCE_ENV_PREFIX: Dict[str, str] = {
    "s3": "S3_",
    "gcs": "GCS_",
    "azure_blob": "AZURE_BLOB_",
    "onedrive": "ONEDRIVE_",
    "sharepoint": "SHAREPOINT_",
    "google_drive": "GOOGLE_DRIVE_",
    "alfresco": "ALFRESCO_",
    "nuxeo": "NUXEO_",
    "box": "BOX_",
    "cmis": "CMIS_",
    "web": "WEB_",
    "wikipedia": "WIKIPEDIA_",
    "youtube": "YOUTUBE_",
}


def _harvest_env_prefix(prefix: str) -> Dict[str, Any]:
    """Collect all ``{PREFIX}_*`` env vars → ``{lowercased_key: value}``."""
    plen = len(prefix)
    return {
        _k[plen:].lower(): _v
        for _k, _v in os.environ.items()
        if _k.startswith(prefix)
    }


def _build_source_config_from_env(source_type: str) -> Dict[str, Any]:
    """Assemble a source config dict from env vars for the given source type.

    Collects ``{PREFIX}_*`` env vars for the source, then overlays shared
    credential vars (``AWS_*`` for S3, ``GOOGLE_APPLICATION_CREDENTIALS`` for
    GCS/Google Drive).  Returns a dict that flexible-graphrag datasource
    adapters and the CocoIndex bridge both accept.
    """
    st = source_type.lower()
    prefix = _SOURCE_ENV_PREFIX.get(st)
    cfg: Dict[str, Any] = _harvest_env_prefix(prefix) if prefix else {}

    # If the harvest produced a raw ``config`` key (i.e. the user set
    # {PREFIX}CONFIG='{...}' as a JSON string), parse and expand it so that
    # the individual credential keys are available.  Individual {PREFIX}_*
    # env vars (already in cfg) take precedence over the JSON block.
    if "config" in cfg:
        try:
            import json as _json  # noqa: PLC0415
            _parsed_cfg = _json.loads(cfg.pop("config"))
            if isinstance(_parsed_cfg, dict):
                # Merge: parsed JSON keys fill in gaps; explicit env vars win.
                _parsed_cfg.update(cfg)
                cfg = _parsed_cfg
        except Exception:
            cfg.pop("config", None)  # drop unusable raw string

    # Overlay shared credential vars.
    if st == "s3":
        # Parse S3_CONFIG JSON first (highest priority for S3 settings).
        _s3_cfg_raw = os.getenv("S3_CONFIG", "")
        if _s3_cfg_raw:
            try:
                import json as _json  # noqa: PLC0415
                _s3_parsed = _json.loads(_s3_cfg_raw)
                # S3_CONFIG keys take priority over individual S3_* vars.
                cfg.update(_s3_parsed)
            except Exception:
                pass
        # Normalise bucket_name → bucket (S3_BUCKET_NAME env var becomes bucket_name via prefix).
        if not cfg.get("bucket"):
            cfg["bucket"] = (
                cfg.pop("bucket_name", None)
                or os.getenv("S3_BUCKET_NAME", "")
                or os.getenv("S3_BUCKET", "")
            )
        # Standard AWS credential env vars as fallback.
        cfg.setdefault("access_key_id", os.getenv("AWS_ACCESS_KEY_ID", ""))
        cfg.setdefault("secret_access_key", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
        _region_val = (
            cfg.get("region_name")
            or cfg.get("region")
            or os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
        )
        cfg["region"] = _region_val
        cfg["region_name"] = _region_val
        _tok = os.getenv("AWS_SESSION_TOKEN")
        if _tok:
            cfg.setdefault("session_token", _tok)
    elif st in ("gcs", "google_drive"):
        cfg.setdefault("credentials_file", os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""))

    # filesystem has no env prefix — watch root comes from WATCH_DIR.
    if st == "filesystem":
        watch_dir = os.getenv("WATCH_DIR", "./cocoindex-docs")
        if "paths" not in cfg:
            cfg["paths"] = [watch_dir]
        cfg.setdefault("path", watch_dir)

    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Memoised entry points
# ─────────────────────────────────────────────────────────────────────────────

class _FlexibleEagerPayload(NamedTuple):
    """Per-item payload for eager (non-detector) ``mount_each`` sources."""

    file_bytes: bytes
    file_name: str
    file_path: str
    source_type: str
    modified_at: str
    source_metadata_json: str


@coco.fn(memo=True)  # type: ignore[misc]
async def process_flexible_item(
    payload: _FlexibleEagerPayload,
    cfg_json: str,
) -> str:
    """Process one item from an eager flexible-graphrag data source — memoised.

    CocoIndex fingerprints ``payload.file_bytes`` for change detection: the item
    is only reprocessed when the bytes change or ``cfg_json`` changes.
    """
    import traceback as _tb
    file_name = payload.file_name
    file_path = payload.file_path
    try:
        _run._emit_progress(event="file_stage", file_name=file_name, file_path=file_path, stage="downloaded")
        cfg = json.loads(cfg_json)
        source_metadata: Dict[str, Any] = (
            json.loads(payload.source_metadata_json) if payload.source_metadata_json else {}
        )
        await _run._run_pipeline(
            payload.file_bytes,
            file_name,
            file_path,
            payload.source_type,
            payload.modified_at,
            cfg,
            source_metadata,
        )
        return f"ok:{file_name}"
    except Exception as _exc:
        _err_msg = (
            f"[CocoIndex flexible pipeline ERROR] {type(_exc).__name__}: {_exc}\n"
            + _tb.format_exc()
        )
        logger.error(_err_msg)
        with open("cocoindex_pipeline_error.log", "a", encoding="utf-8") as _ef:
            _ef.write(_err_msg + "\n")
        # Guarantee a terminal file_done so live-mode progress hooks are released
        # even when the failure happened before _run_pipeline's own file_done.
        try:
            _run._emit_progress(
                event="file_done", file_name=file_name, file_path=file_path,
                status="failed", detail=f"{type(_exc).__name__}: {_exc}",
            )
        except Exception:  # noqa: BLE001
            pass
        return f"error:{type(_exc).__name__}:{_exc}"


@coco.fn(memo=True)  # type: ignore[misc]
async def process_flexible_file(file: Any, cfg_json: str) -> str:
    """Process one **lazy** ``FlexibleFile`` from a ``FlexibleMapView`` — memoised.

    CocoIndex fingerprints the ``FlexibleFile`` via its ``__coco_memo_state__``
    (mtime + etag/ordinal fingerprint), not the bytes, so change detection
    happens *before* any download.  Bytes are fetched on demand here only for
    changed files.
    """
    import traceback as _tb
    try:
        file_name = file.display_file_name
        file_path = file.display_path
        source_type = file.source_type
        modified_at = file.modified_at
        _run._emit_progress(event="file_stage", file_name=file_name, file_path=file_path, stage="downloading")
        file_bytes: bytes = await file.read()
        _run._emit_progress(event="file_stage", file_name=file_name, file_path=file_path, stage="downloaded")
        reader_metadata: Dict[str, Any] = dict(file.reader_metadata or {})
        cfg = json.loads(cfg_json)
        await _run._run_pipeline(
            file_bytes, file_name, file_path, source_type, modified_at, cfg,
            reader_metadata,
        )
        return f"ok:{file_name}"
    except Exception as _exc:
        _err_msg = (
            f"[CocoIndex flexible(lazy) pipeline ERROR] {type(_exc).__name__}: {_exc}\n"
            + _tb.format_exc()
        )
        logger.error(_err_msg)
        with open("cocoindex_pipeline_error.log", "a", encoding="utf-8") as _ef:
            _ef.write(_err_msg + "\n")
        # Guarantee a terminal file_done so live-mode progress hooks are released
        # even when the failure happened before _run_pipeline's own file_done
        # (file_name / file_path may not be bound yet — derive defensively).
        try:
            _fn = str(getattr(file, "display_file_name", None) or "source")
            _fp = str(getattr(file, "display_path", None) or _fn)
            _run._emit_progress(
                event="file_done", file_name=_fn, file_path=_fp,
                status="failed", detail=f"{type(_exc).__name__}: {_exc}",
            )
        except Exception:  # noqa: BLE001
            pass
        return f"error:{type(_exc).__name__}:{_exc}"


# ─────────────────────────────────────────────────────────────────────────────
# App-main and factory
# ─────────────────────────────────────────────────────────────────────────────

@coco.fn  # type: ignore[misc]
async def flexible_app_main(cfg_json: str) -> None:
    """Iterate a flexible-graphrag data source and mount one component per item.

    Two source families:

    * **Detector-backed** (filesystem, s3, gcs, azure_blob, google_drive,
      onedrive, sharepoint, box, alfresco, nuxeo) → mount a lazy ``FlexibleMapView``
      via ``mount_each``.  Bytes are pulled only for changed files.
    * **Non-detector** (web, wikipedia, youtube, cmis) → eager
      ``FlexibleDataSource`` scan.

    Wrapped so any exception is logged HERE with its traceback.  When app_main
    raises, CocoIndex cancels the child components and the caller sees only
    ``RuntimeError: Child component build cancelled`` — the original Python
    exception is swallowed by the engine boundary and appears in no log.
    """
    # BaseException, not Exception: the observed failure is a CancelledError,
    # which derives from BaseException and slips past `except Exception`.
    try:
        await _flexible_app_main_impl(cfg_json)
    except asyncio.CancelledError:
        # Routine teardown, not a failure -- see the note in FlexibleMapView.watch.
        logger.debug("flexible_app_main cancelled (normal teardown)")
        raise
    except BaseException as _exc:
        logger.error(
            "flexible_app_main FAILED (%s) — this is what CocoIndex reports as "
            "'Child component build cancelled'",
            type(_exc).__name__,
            exc_info=True,
        )
        raise


async def _flexible_app_main_impl(cfg_json: str) -> None:
    """Body of :func:`flexible_app_main` (see it for the contract)."""
    from cocoindex_integration.connectors.flexible.source import FlexibleDataSource  # noqa: PLC0415
    from cocoindex_integration.connectors.flexible._sources import DETECTOR_BACKED  # noqa: PLC0415

    cfg = json.loads(cfg_json)
    source_type = cfg.get("data_source", "filesystem")
    source_backend = str(cfg.get("source_backend", "flexible")).lower()
    # INFO, not DEBUG: when a build fails these few lines are the only record of
    # how far app_main got, and the default LOG_LEVEL is INFO.
    logger.debug(
        "flexible_app_main: source=%s backend=%s", source_type, source_backend,
    )

    await _sel._mount_native_target_roots(cfg)
    logger.debug("flexible_app_main [%s]: target roots mounted", source_type)

    # ── Native CocoIndex source (localfs / s3 / azure_blob / google_drive) ────
    # source_backend=cocoindex → list via the native connector and mount the
    # matching per-file worker.  cfg was prepared by build_app_for_config, so
    # both the lister and worker read the same derived keys.  If the native
    # connector's optional dependency is missing (lister returns None) we fall
    # through to the FlexibleDataSource path below.
    if source_backend == "cocoindex":
        from cocoindex_integration.pipeline.native_apps import (  # noqa: PLC0415
            NATIVE_READERS,
            wrap_native_view_for_deletes,
        )
        _reader = NATIVE_READERS.get(source_type)
        if _reader is not None:
            _lister, _worker = _reader
            _items = await _lister(cfg)
            if _items is not None:
                # Wrap the native connector's OWN view so flexible backends
                # (Elasticsearch, GraphDB RDF, …) also receive live DELETE signals.
                # CocoIndex's live views reconcile native targets (Qdrant, Neo4j)
                # automatically, but root TargetStateProviders (flexible backends)
                # only reconcile on a full app.update() catch-up — which CLI ``-L``
                # never runs.  The wrapper observes CocoIndex's own
                # ``subscriber.delete`` and is a no-op for non-live iterables
                # (S3/Azure/Drive, which reconcile via catch-up).  Source-agnostic:
                # any current/future live-watchable native source is covered.
                _items = wrap_native_view_for_deletes(_items, source_type, cfg)
                await coco.mount_each(_worker, _items, cfg_json)  # type: ignore[attr-defined]
                return
            logger.info(
                "native CocoIndex source %r unavailable — falling back to FlexibleDataSource",
                source_type,
            )

    source_cfg = _build_source_config_from_env(source_type)
    # UI-submitted sources carry their own connection params in cfg_json
    # (build_app_for_config stashes them under ``_source_config_override``).
    # Overlay them on top of the env-derived config so the detector + reader
    # use the UI's credentials/paths rather than the .env defaults.  The
    # primary .env source has no override (identical values), so this is a
    # no-op for it — the event detectors are hooked up either way.
    _src_override = cfg.get("_source_config_override")
    if isinstance(_src_override, dict) and _src_override:
        source_cfg = {**source_cfg, **_src_override}

    # ── Detector-backed sources → lazy FlexibleMapView ────────────────────────
    if source_type in DETECTOR_BACKED:
        from cocoindex_integration.connectors.flexible._map_view import FlexibleMapView  # noqa: PLC0415
        try:
            view = FlexibleMapView(source_type, source_cfg)
        except Exception as _mv_exc:
            logger.error("FlexibleMapView(%s) init failed: %s", source_type, _mv_exc)
            return
        logger.debug("flexible_app_main [%s]: mounting FlexibleMapView (lazy, change-aware)", source_type)
        await coco.mount_each(process_flexible_file, view, cfg_json)  # type: ignore[attr-defined]
        logger.debug("flexible_app_main [%s]: mount_each returned", source_type)
        return

    # ── Non-detector sources → eager scan ─────────────────────────────────────
    items: List[tuple] = []
    try:
        async for item in FlexibleDataSource(source_type, source_cfg):
            try:
                file_bytes = await item.get_bytes()
            except Exception as _be:
                logger.warning("Could not read bytes for %s: %s", item.key, _be)
                file_bytes = b""
            items.append((
                item.key,
                _FlexibleEagerPayload(
                    file_bytes,
                    item.file_name,
                    item.file_path,
                    item.source_type or source_type,
                    item.modified_at,
                    json.dumps(item.metadata) if item.metadata else "{}",
                ),
            ))
    except Exception as _src_exc:
        logger.error("FlexibleDataSource(%s) error: %s", source_type, _src_exc)
        return

    if not items:
        logger.info("FlexibleDataSource(%s): no documents found", source_type)
        return

    logger.info("flexible_app_main [%s]: FlexibleDataSource found %d item(s)", source_type, len(items))
    await coco.mount_each(process_flexible_item, items, cfg_json)  # type: ignore[attr-defined]


def build_flexible_source_app(*, skip_graph: "bool | None" = None) -> Any:
    """Return a ``coco.App`` that reads from a flexible-graphrag data source.

    Source type is set via ``DATA_SOURCE`` (e.g. ``s3``, ``gcs``,
    ``azure_blob``, ``filesystem``, …).  Credentials come from env vars.
    """
    _cfg = load_config_from_env()
    if skip_graph is not None:
        _cfg["enable_knowledge_graph"] = not skip_graph
        _cfg["_skip_graph"] = skip_graph
    _app = coco.App(  # type: ignore[attr-defined]
        "GraphRAGFlexible",
        flexible_app_main,
        cfg_json=json.dumps(_cfg, sort_keys=True),
    )
    _app._fgr_watchable = _compute_watchable(  # type: ignore[attr-defined]
        str(_cfg.get("data_source", "filesystem")),
        str(_cfg.get("source_backend", "flexible")),
    )
    return _app


# ─────────────────────────────────────────────────────────────────────────────
# Multi-source helpers — used by CocoIndexBridge (no sync button)
# ─────────────────────────────────────────────────────────────────────────────

# Source types that have a native CocoIndex source connector (used when
# source_backend=cocoindex — not a global preference order).
_COCO_NATIVE_SOURCES = frozenset({"filesystem", "localfs", "s3", "amazon_s3", "azure_blob", "google_drive"})


def _compute_watchable(data_source: str, source_backend: str) -> bool:
    """Return True if this source streams changes (→ persistent live stream).

    * ``source_backend=cocoindex``: only the native **localfs** connector has a
      live watcher (``walk_dir(live=True)``); native S3/Azure/Drive are
      scan-only → not watchable (bridge backup-polls them).
    * ``source_backend=flexible``: every **detector-backed** source
      (filesystem, s3, gcs, azure_blob, google_drive, onedrive, sharepoint,
      box, alfresco, nuxeo) streams changes via ``FlexibleMapView.watch()``.  The
      non-detector sources (web, wikipedia, youtube, cmis) are not watchable.
    """
    ds = (data_source or "").lower()
    sb = (source_backend or "flexible").lower()
    if sb == "cocoindex":
        return ds in ("filesystem", "localfs")
    try:
        from cocoindex_integration.connectors.flexible._sources import (  # noqa: PLC0415
            DETECTOR_BACKED,
        )
    except Exception:
        return False
    return ds in DETECTOR_BACKED

# Vector DBs with a native CocoIndex target connector (used when vector_backend=cocoindex).
_COCO_NATIVE_VECTOR_DBS = frozenset({"qdrant", "postgres", "lancedb"})

# PG DBs with a native CocoIndex target connector (used when graph_backend=cocoindex).
_COCO_NATIVE_PG_DBS = frozenset({"neo4j", "falkordb", "surrealdb"})

# PG DBs with a LlamaIndex property-graph adapter (all LI-capable stores).
# spanner: LlamaIndex SpannerPropertyGraphStore (LangChain SpannerGraphStore too since 0.10.0).
_LI_PG_DBS = frozenset({
    "neo4j", "falkordb", "memgraph", "arcadedb", "nebula",
    "ladybug", "neptune", "neptune_analytics", "spanner",
})

# PG DBs that are LangChain-only (no LlamaIndex adapter).
_LC_ONLY_PG_DBS = frozenset({
    "surrealdb", "arangodb", "apache_age", "hugegraph",
    "tigergraph", "cosmos_gremlin",
})

# Valid chunker backends — anything else falls back to llamaindex.
_VALID_CHUNKER_BACKENDS = frozenset({"llamaindex", "langchain", "cocoindex"})

# Built-in KG-extractor backends.  NOT a whitelist any more — any other value is
# resolved as a custom KGExtractor spec (see functions/kg_extractors.py).  Keep in
# sync with BUILTIN_KG_EXTRACTOR_BACKENDS there.
_VALID_KG_EXTRACTOR_BACKENDS = frozenset({"llamaindex", "langchain"})


def _resolve_pipeline_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *cfg* with all backend fields resolved and fallbacks applied.

    The **configured** source / target backend for each stage drives the first
    choice.  CocoIndex is never auto-selected — it is used only when explicitly
    set (e.g. ``SOURCE_BACKEND=cocoindex``, ``VECTOR_BACKEND=cocoindex``).
    When the configured backend is unavailable for the chosen DB or data source,
    a fallback is applied and logged.

    ``source_backend``  (configured → fallback when unavailable)
        ``cocoindex``  → native CocoIndex connector for ``data_source``
                       → ``flexible``
        ``flexible``   → kept (no upgrade to cocoindex)

    ``vector_backend``
        ``cocoindex``  → native CocoIndex connector for ``vector_db``
                       → ``llamaindex``
        ``llamaindex`` / ``langchain`` → kept

    ``graph_backend``  (DB-aware fallback only when configured backend unavailable)
        ``cocoindex``  → native CocoIndex connector for ``pg_graph_db``
                       → ``llamaindex`` if DB has a LI adapter
                       → ``langchain`` if DB is LC-only (e.g. surrealdb, arangodb)
        ``llamaindex`` → kept; → ``langchain`` if DB is LC-only
        ``langchain``  → kept (all 15 PG stores)
        ``pg_graph_db=none`` → graph_backend left as configured, no fallback

    ``chunker_backend``
        Must be ``llamaindex | langchain | cocoindex``
        → unknown values fall back to ``llamaindex``

    ``kg_extractor_backend``
        Must be ``llamaindex | langchain``
        → unknown values fall back to ``llamaindex``

    All other keys are left unchanged.  The original dict is not mutated.
    """
    resolved = dict(cfg)
    data_source = str(resolved.get("data_source", "filesystem")).lower()

    # ── source_backend ────────────────────────────────────────────────────────
    raw_src_backend = str(resolved.get("source_backend", "flexible")).lower()
    if raw_src_backend == "cocoindex":
        if data_source not in _COCO_NATIVE_SOURCES:
            logger.info(
                "source_backend=cocoindex not available for data_source=%s — falling back to flexible",
                data_source,
            )
            resolved["source_backend"] = "flexible"
        else:
            try:
                from cocoindex_integration.connectors.cocoindex.sources import (  # noqa: PLC0415
                    COCO_SOURCES,
                )
                if data_source not in COCO_SOURCES:
                    raise ImportError(f"{data_source} not in COCO_SOURCES")
            except Exception as _e:
                logger.info(
                    "source_backend=cocoindex unavailable (%s) — falling back to flexible", _e
                )
                resolved["source_backend"] = "flexible"

    # ── vector_backend ────────────────────────────────────────────────────────
    vector_db = str(resolved.get("vector_db", "none")).lower()
    raw_vec_backend = str(resolved.get("vector_backend", "llamaindex")).lower()
    if raw_vec_backend == "cocoindex":
        if vector_db not in _COCO_NATIVE_VECTOR_DBS:
            logger.info(
                "vector_backend=cocoindex not available for vector_db=%s — falling back to llamaindex",
                vector_db,
            )
            resolved["vector_backend"] = "llamaindex"
        else:
            try:
                from cocoindex_integration.connectors.cocoindex.vector import (  # noqa: PLC0415
                    COCO_VECTOR_TARGETS,
                )
                if vector_db not in COCO_VECTOR_TARGETS:
                    raise ImportError(f"{vector_db} not in COCO_VECTOR_TARGETS")
            except Exception as _e:
                logger.info(
                    "vector_backend=cocoindex unavailable (%s) — falling back to llamaindex", _e
                )
                resolved["vector_backend"] = "llamaindex"

    # ── graph_backend (fallback only when configured backend unavailable) ─────
    pg_graph_db = str(resolved.get("pg_graph_db", "none")).lower()
    raw_graph_backend = str(resolved.get("graph_backend", "llamaindex")).lower()

    # No PG graph DB configured — keep configured value as-is, skip fallback logic.
    if pg_graph_db in ("none", ""):
        raw_graph_backend = "none"  # skip the rest of the graph_backend block

    def _best_graph_backend_for_db(db: str) -> str:
        """Return the best available backend for *db* (LI preferred over LC)."""
        if db in _LI_PG_DBS:
            return "llamaindex"
        if db in _LC_ONLY_PG_DBS:
            return "langchain"
        return "llamaindex"  # unknown — try llamaindex, let it fail loudly

    if raw_graph_backend == "cocoindex":
        _coco_available = False
        if pg_graph_db in _COCO_NATIVE_PG_DBS:
            try:
                from cocoindex_integration.connectors.cocoindex.property_graph import (  # noqa: PLC0415
                    COCO_PG_TARGETS,
                )
                _coco_available = pg_graph_db in COCO_PG_TARGETS
            except Exception:
                pass

        if _coco_available:
            resolved["graph_backend"] = "cocoindex"
        else:
            _fallback = _best_graph_backend_for_db(pg_graph_db)
            logger.info(
                "graph_backend=cocoindex not available for pg_graph_db=%s — falling back to %s",
                pg_graph_db, _fallback,
            )
            resolved["graph_backend"] = _fallback

    elif raw_graph_backend == "llamaindex":
        # LI cannot write to langchain-only stores — fall through to langchain.
        if pg_graph_db in _LC_ONLY_PG_DBS:
            logger.info(
                "graph_backend=llamaindex not supported for pg_graph_db=%s (langchain-only) "
                "— falling back to langchain",
                pg_graph_db,
            )
            resolved["graph_backend"] = "langchain"
        # else: keep llamaindex (all _LI_PG_DBS are supported)

    # langchain: always keep — LC has adapters for all 15 PG stores.

    # ── chunker_backend ───────────────────────────────────────────────────────
    raw_chunker = str(resolved.get("chunker_backend", "llamaindex")).lower()
    if raw_chunker not in _VALID_CHUNKER_BACKENDS:
        logger.warning(
            "Unknown chunker_backend=%r — falling back to llamaindex", raw_chunker
        )
        resolved["chunker_backend"] = "llamaindex"
    else:
        resolved["chunker_backend"] = raw_chunker

    # ── kg_extractor_backend ──────────────────────────────────────────────────
    # Anything that is not built-in is treated as a custom KGExtractor spec (a
    # registered name, "module:Class", or "/path/mod.py:Class").  Preserve the
    # raw case for those — module and class names are case-sensitive, and so are
    # paths on POSIX — and only fold for the built-in comparison.
    raw_kg = str(
        resolved.get("kg_extractor_backend", resolved.get("kg_extractor_type", "llamaindex"))
    ).strip()
    if raw_kg.lower() in _VALID_KG_EXTRACTOR_BACKENDS:
        resolved["kg_extractor_backend"] = raw_kg.lower()
    else:
        # Resolve now so a typo surfaces at config time with the list of known
        # names, rather than as empty extraction results per chunk later.
        from cocoindex_integration.functions.kg_extractors import (  # noqa: PLC0415
            resolve_kg_extractor,
        )
        try:
            _cls = resolve_kg_extractor(raw_kg)
            logger.info(
                "kg_extractor_backend=%r → custom extractor %s (version=%s)",
                raw_kg, _cls.__name__, getattr(_cls, "version", "?"),
            )
            resolved["kg_extractor_backend"] = raw_kg
        except Exception as _exc:
            logger.warning(
                "Unknown kg_extractor_backend=%r (%s: %s) — falling back to llamaindex",
                raw_kg, type(_exc).__name__, _exc,
            )
            resolved["kg_extractor_backend"] = "llamaindex"

    return resolved


def log_pipeline_config(cfg_requested: Dict[str, Any], cfg_resolved: Dict[str, Any]) -> None:
    """Emit startup log lines matching the regular flexible-graphrag format.

    Mirrors ``HybridSystem.__init__`` sections:
      ``=== PIPELINE BACKEND ===``
      ``=== LLM CONFIGURATION ===``
      ``=== DATABASE CONFIGURATION ===``
      ``=== FRAMEWORK CONFIGURATION (configured → actual) ===``

    Parameters
    ----------
    cfg_requested:
        Raw config before :func:`_resolve_pipeline_config` (what was asked for).
    cfg_resolved:
        Config after resolution (what will actually be used).
    """
    def _v(d: Dict, *keys: str, default: str = "none") -> str:
        for k in keys:
            v = d.get(k)
            if v is not None and str(v).strip():
                return str(v)
        return default

    # ── Pipeline backend ──────────────────────────────────────────────────────
    logger.info("=== COCOINDEX PIPELINE CONFIGURATION (bridge) ===")
    logger.info("=== PIPELINE BACKEND ===")
    data_source = _v(cfg_resolved, "data_source", default="filesystem")
    src_backend = _v(cfg_resolved, "source_backend", default="flexible")
    config_id = cfg_resolved.get("config_id", "")
    logger.info("Pipeline Backend  : CocoIndex pipeline with CocoIndex and Flexible (LlamaIndex / LangChain) stages supported")
    # "Primary source" label — avoids confusion when CocoIndexBridge also loads
    # additional sources from datasource_config (logged separately by bridge).
    _src_label = "Source (primary)"
    logger.info("%s : %s  [source_backend: %s]%s",
                _src_label, data_source, src_backend,
                f"  config_id={config_id}" if config_id else "")

    # ── LLM / embedding ───────────────────────────────────────────────────────
    logger.info("=== LLM CONFIGURATION ===")
    logger.info("LLM Provider      : %s", _v(cfg_resolved, "llm_provider"))
    _model_val = _v(cfg_resolved, "llm_model", default="")
    if _model_val:
        logger.info("LLM Model         : %s", _model_val)
    _temp = cfg_resolved.get("llm_temperature", cfg_resolved.get("temperature"))
    if _temp is not None:
        logger.info("LLM Temperature   : %s", _temp)
    logger.info("Embedding Kind    : %s", _v(cfg_resolved, "embedding_kind"))
    logger.info("Embedding Model   : %s", _v(cfg_resolved, "embedding_model"))
    _edim = cfg_resolved.get("embedding_dimension") or cfg_resolved.get("embedding_dim")
    if _edim:
        logger.info("Embedding Dims    : %s", _edim)

    _D = 22  # DB label column width
    _F = 21  # Framework label column width

    # ── Databases ─────────────────────────────────────────────────────────────
    logger.info("=== DATABASE CONFIGURATION ===")
    logger.info(f"{'Property Graph DB':<{_D}}: %s", _v(cfg_resolved, "pg_graph_db"))
    logger.info(f"{'RDF Graph DB':<{_D}}: %s", _v(cfg_resolved, "rdf_graph_db"))
    logger.info(f"{'Vector DB':<{_D}}: %s", _v(cfg_resolved, "vector_db"))
    logger.info(f"{'Search DB':<{_D}}: %s", _v(cfg_resolved, "search_db"))
    _kg_enabled = cfg_resolved.get("enable_knowledge_graph", True)
    _skip = cfg_resolved.get("_skip_graph", False)
    logger.info(
        f"{'KG Extraction / Store':<{_D}}: %s",
        False if _skip else bool(_kg_enabled),
    )

    # ── Framework config: configured vs actual ────────────────────────────────
    logger.info("=== FRAMEWORK CONFIGURATION ===")

    _FW_LABELS = {
        "cocoindex": "CocoIndex",
        "llamaindex": "LlamaIndex",
        "langchain":  "LangChain",
        "flexible":   "Flexible",
        "none":       "none",
    }

    def _fw_label(raw: str) -> str:
        return _FW_LABELS.get(str(raw).lower(), str(raw))

    def _fmt(key: str, default: str = "llamaindex") -> str:
        """'LlamaIndex' when same, 'CocoIndex configured, used LlamaIndex' on fallback."""
        req = str(cfg_requested.get(key, default)).lower()
        act = str(cfg_resolved.get(key, default)).lower()
        if req == act:
            return _fw_label(act)
        return f"{_fw_label(req)} configured, used {_fw_label(act)}"

    logger.info(f"{'Source Backend':<{_F}}: %s", _fmt("source_backend", "flexible"))
    logger.info(f"{'Property Graph Store':<{_F}}: %s", _fmt("graph_backend"))
    logger.info(f"{'RDF Graph Store':<{_F}}: LangChain / RDFLib")
    logger.info(f"{'Vector Store':<{_F}}: %s", _fmt("vector_backend"))
    logger.info(f"{'Search Store':<{_F}}: %s", _fmt("search_backend"))
    logger.info(
        f"{'Document Parser':<{_F}}: %s",
        format_parser_display_name(_v(cfg_resolved, "parser_type", default="docling")),
    )
    logger.info(f"{'Chunking / Splitting':<{_F}}: %s", _fmt("chunker_backend"))
    _kg_on = bool(_kg_enabled) and not _skip
    if _kg_on:
        _kg_line = _fmt("kg_extractor_backend")
    else:
        _kg_line = "disabled (ENABLE_KNOWLEDGE_GRAPH=false or skip_graph)"
    logger.info(f"{'KG Extraction':<{_F}}: %s", _kg_line)
    _fusion = _v(cfg_resolved, "retrieval_fusion", default="llamaindex")
    logger.info(
        f"{'Retrieval Fusion':<{_F}}: %s",
        "LangChain (EnsembleRetriever)" if _fusion == "langchain"
        else "LlamaIndex (QueryFusionRetriever)",
    )


def build_app_for_config(
    source_config: Dict[str, Any],
    *,
    app_name: Optional[str] = None,
    skip_graph: "bool | None" = None,
) -> Any:
    """Build a single ``coco.App`` for one datasource_config row.

    Unlike the standalone ``build_*_app()`` factory functions (which re-read env
    vars), this function derives the **complete pipeline config** from
    *source_config* so that per-row overrides in ``connection_params`` — source
    credentials, which vector/graph/search/rdf DB to use, which chunker or KG
    extractor backend, etc. — are all honoured.  Unavailable backends are
    downgraded with a warning instead of crashing.

    Parameters
    ----------
    source_config:
        Dict built from a ``datasource_config`` row merged with the base .env
        config.  Keys from ``connection_params`` (JSONB) are merged in by the
        caller (:func:`build_apps_for_all_sources`).
    app_name:
        Override the CocoIndex app name (default: ``GraphRAG_{source}_{id}``).
    skip_graph:
        When *True*, KG extraction is disabled for this source regardless of env.
    """
    from cocoindex_integration.pipeline.native_apps import (  # noqa: PLC0415
        NATIVE_READERS,
        _prepare_native_source_cfg,
    )

    # 1. Merge: base .env → connection_params → top-level source_config keys.
    cfg: Dict[str, Any] = dict(load_config_from_env())
    conn_params = source_config.get("connection_params") or {}
    if isinstance(conn_params, str):
        try:
            conn_params = json.loads(conn_params)
        except Exception:
            conn_params = {}
    cfg.update(conn_params)
    cfg.update({k: v for k, v in source_config.items() if k != "connection_params"})

    # Stash the raw connection params so flexible_app_main can build the
    # detector/reader with the UI-submitted credentials (not just .env vars).
    # This is what makes a UI source's event detectors work regardless of
    # whether its config matches the .env defaults.
    if conn_params:
        cfg["_source_config_override"] = dict(conn_params)

    # 2. Apply skip_graph override.
    if skip_graph is not None:
        cfg["enable_knowledge_graph"] = not skip_graph
        cfg["_skip_graph"] = skip_graph

    # 3. Resolve all backend fields with fallbacks.
    cfg = _resolve_pipeline_config(cfg)

    data_source = str(cfg.get("data_source", "filesystem")).lower()
    config_id = str(cfg.get("config_id", ""))
    if app_name is None:
        app_name = f"GraphRAG_{data_source}_{config_id}" if config_id else f"GraphRAG_{data_source}"

    use_native = str(cfg.get("source_backend", "flexible")).lower() == "cocoindex"

    # 4. For native CocoIndex sources, fill in derived keys (azure account_url,
    #    google_drive credential path / folder ids) so both the connector lister
    #    and the per-file worker inside flexible_app_main read the same values.
    _native = use_native and data_source in NATIVE_READERS
    if _native:
        _prepare_native_source_cfg(cfg)

    cfg_json = json.dumps(cfg, sort_keys=True)

    # Tag every app the bridge builds with its change-detection capability so it
    # can dispatch: watchable → persistent live stream; else → backup poll.
    _watchable = _compute_watchable(data_source, str(cfg.get("source_backend", "flexible")))

    def _ret(_a: Any) -> Any:
        _a._fgr_watchable = _watchable  # type: ignore[attr-defined]
        return _a

    # 5. Single app_main for every source.  flexible_app_main dispatches native
    #    CocoIndex sources through NATIVE_READERS (localfs/s3/azure_blob/
    #    google_drive) and every flexible-graphrag source through
    #    FlexibleDataSource.  cfg_json carries the full resolved pipeline config
    #    so _run_pipeline selects the right chunker/KG/vector/graph/search
    #    backends and (for native sources) the right lister + worker.
    logger.info(
        "build_app_for_config [%s]: source=%s backend=%s%s",
        app_name, data_source, cfg.get("source_backend", "flexible"),
        " (native CocoIndex connector)" if _native else "",
    )
    return _ret(coco.App(  # type: ignore[attr-defined]
        app_name,
        flexible_app_main,
        cfg_json=cfg_json,
    ))


async def build_apps_for_all_sources(
    db_url: str,
    skip_config_ids: Optional[set] = None,
) -> List[Any]:
    """Query ``datasource_config`` and build one ``coco.App`` per active source.

    This is the "no sync button" entry point — called by :class:`CocoIndexBridge`
    on startup so every UI-configured datasource automatically starts processing.

    Parameters
    ----------
    db_url:
        SQLAlchemy-compatible async connection URL for the incremental-updates
        PostgreSQL database (``POSTGRES_INCREMENTAL_URL`` env var).
    skip_config_ids:
        Optional set of config_id strings to skip (used to exclude the primary
        .env source which is already running as apps[0]).

    Returns a (possibly empty) list of ``coco.App`` instances.  Each app
    self-registers with CocoIndex on construction; the caller passes the list
    to ``coco.start_blocking()`` or runs them concurrently via
    ``asyncio.gather(*[app.update() for app in apps])``.
    """
    apps: List[Any] = []
    try:
        import asyncpg  # noqa: PLC0415
    except ImportError:
        logger.warning(
            "asyncpg not available — multi-source startup skipped. "
            "Only the default .env source will be processed."
        )
        return apps

    base_cfg = load_config_from_env()
    try:
        conn = await asyncpg.connect(db_url)
    except Exception as _conn_exc:
        logger.warning(
            "Could not connect to incremental DB (%s) — "
            "multi-source startup skipped: %s", db_url, _conn_exc,
        )
        return apps

    try:
        rows = await conn.fetch(
            """
            SELECT config_id, source_type, source_name, connection_params,
                   refresh_interval_seconds, is_active
            FROM datasource_config
            WHERE is_active = TRUE
            ORDER BY created_at
            """
        )
    except Exception as _qe:
        logger.warning("datasource_config query failed — multi-source startup skipped: %s", _qe)
        await conn.close()
        return apps
    finally:
        await conn.close()

    logger.info(
        "CocoIndex multi-source: found %d active datasource_config row(s)", len(rows)
    )

    for row in rows:
        if skip_config_ids and str(row["config_id"]) in skip_config_ids:
            logger.debug(
                "CocoIndex multi-source: skipping primary source config_id=%s", row["config_id"]
            )
            continue
        try:
            conn_params = row["connection_params"] or {}
            if isinstance(conn_params, str):
                try:
                    conn_params = json.loads(conn_params)
                except Exception:
                    conn_params = {}

            source_config: Dict[str, Any] = dict(base_cfg)
            source_config.update(conn_params)
            source_config["config_id"] = str(row["config_id"])
            source_config["data_source"] = str(row["source_type"])
            source_config["source_name"] = str(row["source_name"] or "")
            if row["refresh_interval_seconds"]:
                source_config["refresh_interval_seconds"] = int(row["refresh_interval_seconds"])

            app_obj = build_app_for_config(source_config)
            apps.append(app_obj)
            logger.info(
                "CocoIndex multi-source: registered app for %s (%s)",
                row["source_name"] or row["source_type"],
                row["config_id"],
            )
        except Exception as _build_exc:
            logger.error(
                "CocoIndex multi-source: failed to build app for config_id=%s source=%s: %s",
                row.get("config_id"), row.get("source_type"), _build_exc,
            )

    return apps


def _build_default_app(source_dir: "str | None" = None) -> Any:
    """Build the app implied by ``.env`` (``DATA_SOURCE`` / ``SOURCE_BACKEND``).

    ``source_dir`` is an optional CLI override for filesystem sources.
    All backend resolution (including fallbacks) goes through
    :func:`_resolve_pipeline_config` → :func:`build_app_for_config`.
    """
    _app_cfg = dict(load_config_from_env())
    # Overlay source-specific env vars (S3_BUCKET, AZURE_CONTAINER, etc.) so
    # the native connector has the credentials it needs when called from the
    # bridge (no connection_params dict in that path).
    _data_source = _app_cfg.get("data_source", "filesystem")
    _src_env = _build_source_config_from_env(str(_data_source))
    # Source-specific vars fill gaps; base env config (llm, embedding, dbs) takes precedence.
    _app_cfg = {**_src_env, **_app_cfg}
    # CLI source_dir overrides WATCH_DIR for filesystem sources.
    #
    # It must go in via ``connection_params`` as well as the top level:
    # ``flexible_app_main`` rebuilds its source config from the environment and
    # only overlays ``_source_config_override`` (which build_app_for_config
    # derives from connection_params).  Setting the top-level keys alone reaches
    # the native localfs lister but is silently dropped on the flexible path, so
    # ``python -m cocoindex_integration.pipeline.app <dir>`` kept scanning
    # WATCH_DIR instead of <dir>.
    if source_dir:
        _app_cfg["path"] = source_dir
        _app_cfg["watch_dir"] = source_dir
        _app_cfg["paths"] = [source_dir]
        _conn = dict(_app_cfg.get("connection_params") or {})
        _conn.update({
            "path": source_dir,
            "paths": [source_dir],
            "watch_dir": source_dir,
        })
        _app_cfg["connection_params"] = _conn
    return build_app_for_config(_app_cfg)
