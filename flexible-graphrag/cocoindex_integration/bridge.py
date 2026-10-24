"""
CocoIndex bridge — runs the CocoIndex pipeline inside the flexible-graphrag server.

When ``PIPELINE_BACKEND=cocoindex`` is set in ``.env``, this bridge is started
alongside the FastAPI server and replaces the default ingest pipeline
(LlamaIndex / LangChain stages) for memoized, incremental document processing.
Note: LlamaIndex and LangChain can be still used *inside* the CocoIndex pipeline
for KG extraction, chunking, embedding, and writing to flexible targets.

Capabilities (same as ``cocoindex_integration/pipeline/app.py``)
-----------------------------------------------------------------
Sources  (DATA_SOURCE + SOURCE_BACKEND in ``.env``)
  SOURCE_BACKEND=cocoindex (native CocoIndex connectors, change-tracked):
    filesystem  — CocoIndex native ``localfs`` connector (path + mtime tracking)
    s3          — CocoIndex native S3 connector
    azure_blob  — CocoIndex native Azure Blob connector
    google_drive— CocoIndex native Google Drive connector

  SOURCE_BACKEND=flexible (flexible-graphrag adapters via FlexibleDataSource):
    filesystem / s3 / gcs / azure_blob / onedrive / sharepoint / google_drive /
    box / alfresco / nuxeo / cmis / web / wikipedia / youtube
    (all 14 flexible-graphrag datasource adapters)

  Additional sources configured via the UI data-source tab are loaded from
  the ``datasource_config`` Postgres table at bridge startup — no manual sync
  needed.  With ``PIPELINE_BACKEND=cocoindex``, flexible event detectors and
  ``datasource_config`` still apply; CocoIndex owns change processing (no
  Postgres ``document_state``).  Mutually exclusive with
  ``ENABLE_INCREMENTAL_UPDATES=true`` (FG incremental re-ingests via
  ``hybrid_system``, not CocoIndex) and ``ENABLE_LANGFLOW_FLOWS=true``
  (CocoIndex not supported in Langflow flows).  ``main.py`` skips the FG
  orchestrator and force-disables Langflow when CocoIndex is active.

Targets  (driven by flexible-graphrag ``.env`` config — same knobs as the main server)
  VECTOR_DB    — 10 supported vector stores via ``FlexibleVectorTarget``
                 (or native CocoIndex Qdrant / LanceDB / Postgres+pgvector when VECTOR_BACKEND=cocoindex)
  PG_GRAPH_DB  — 15 property graph stores via ``FlexiblePGTarget``
                 (or native CocoIndex Neo4j / FalkorDB / SurrealDB when GRAPH_BACKEND=cocoindex)
  RDF_GRAPH_DB — Fuseki / GraphDB / Oxigraph / Neptune RDF via ``FlexibleRDFTarget``
  SEARCH_DB    — Elasticsearch / OpenSearch / BM25 via ``FlexibleSearchTarget``

Functions  (all configured via ``.env``)
  Document processing  — Docling (default) , LlamaParse, or LiteParse
  Chunking             — LlamaIndex SentenceSplitter or LangChain splitters
  KG extraction        — LlamaIndex SchemaLLMPathExtractor / DynamicLLMPathExtractor
                         or LangChain LLMGraphTransformer; ontology support (USE_ONTOLOGY=true)
  Embedding            — all 9+ LlamaIndex / LangChain embedding providers

Lifecycle within the flexible-graphrag server
  1. ``bridge.start()``  — initialise the CocoIndex Rust engine, load .env config,
                           build the pipeline app (native CocoIndex or flexible source).
  2. ``await bridge.update()``  — one-shot: process all pending / changed documents.
     Called automatically on server startup and can be triggered via
     ``POST /api/cocoindex/sync-now``.
  3. Background polling (optional) — set ``COCOINDEX_POLL_INTERVAL=60`` (seconds)
     to have the bridge re-run ``update()`` periodically.
  4. ``bridge.stop()``  — clean CocoIndex engine shutdown on server exit.

Ingestion via REST API / UI file upload
  File upload (UI or ``POST /api/ingest``) with ``PIPELINE_BACKEND=cocoindex``:
  - ``SOURCE_BACKEND=cocoindex`` + ``DATA_SOURCE=filesystem``: file is copied
    into WATCH_DIR and ``bridge.update()`` picks it up via the native localfs
    connector (CocoIndex LMDB change detection).
  - ``SOURCE_BACKEND=flexible`` + ``DATA_SOURCE=filesystem``: file goes through
    the flexible filesystem datasource adapter inside the CocoIndex pipeline.
  - Cloud sources (S3, Azure Blob, etc.): ingestion flows through the configured
    source backend directly — file upload path is not applicable.
  - Any UI-picked source that differs from the primary .env source (e.g. Alfresco
    when DATA_SOURCE=filesystem): routed to ``bridge.ingest_source()``, which
    builds a dedicated CocoIndex app for that source on the fly, processes it
    through the CocoIndex pipeline, and (when "keep in sync" is checked) persists
    it to ``datasource_config`` and keeps it updated via a per-source live task.
  Search and QA (``POST /api/search`` etc.) are unaffected — they read from the
  same indices (Qdrant / Neo4j / Elasticsearch) that CocoIndex writes to.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Monitoring import is deferred inside CocoIndexBridge so it does not
# add a hard dependency when cocoindex itself is unavailable.
try:
    from cocoindex_integration import monitoring as _monitoring_mod
    _MONITORING_MOD: Any = _monitoring_mod
except Exception:  # noqa: BLE001
    _MONITORING_MOD = None

# ---------------------------------------------------------------------------
# CocoIndex availability guard
# ---------------------------------------------------------------------------
_COCO_AVAILABLE = False
try:
    import cocoindex as coco  # type: ignore[import-untyped]
    _COCO_AVAILABLE = True
except ImportError:
    coco = None  # type: ignore[assignment]


class CocoIndexBridge:
    """Manages the CocoIndex pipeline within the flexible-graphrag FastAPI server.

    Equivalent to running ``cocoindex update cocoindex_integration/pipeline/app.py``
    but integrated into the server process:
    - Shares the same ``.env`` config as the flexible-graphrag server
    - Starts / stops with the FastAPI lifespan context manager
    - Exposes ``await bridge.update()`` for on-demand processing
    - Optionally polls on a schedule (``COCOINDEX_POLL_INTERVAL``)
    - Exposes ``bridge.ingest_files(paths)`` so the REST ingest handler can
      copy uploaded files into WATCH_DIR and trigger the CocoIndex pipeline

    Both app types from ``pipeline/app.py`` are supported:
      ``localfs``   — CocoIndex native connector; default for DATA_SOURCE=filesystem
      ``flexible``  — FlexibleDataSource; used for all other source types
    """

    def __init__(self, fg_config=None) -> None:
        """
        Args:
            fg_config: flexible-graphrag ``Settings`` instance (or None to load
                from env).  Used for ``cocoindex_db_path`` and ``pipeline_backend``.
        """
        self._fg_config = fg_config
        self._app: Any = None          # primary coco.App (from .env)
        self._apps: List[Any] = []     # all apps: [_app] + DB-sourced apps
        self._started: bool = False
        self._bg_task: Optional[asyncio.Task] = None
        self._last_update: Optional[Dict[str, Any]] = None
        self._update_count: int = 0

        if "DATA_SOURCE" in os.environ:
            _ds = os.getenv("DATA_SOURCE", "").strip().lower()
            self._data_source: str = "" if _ds in ("", "none") else _ds
        else:
            self._data_source: str = "filesystem"
        # SOURCE_BACKEND=flexible forces the FlexibleDataSource path even for
        # filesystem; auto/cocoindex keep the native localfs App for filesystem.
        self._source_backend: str = os.getenv("SOURCE_BACKEND", "flexible").lower()

        # Capability-based dispatch (no COCOINDEX_LIVE flag — always live):
        #   * "watchable" apps (native localfs walk_dir(live=True); every flexible
        #     detector-backed source via FlexibleMapView.watch()) get a persistent
        #     ``app.update(live=True)`` stream — CocoIndex does the initial scan,
        #     watches for changes, and reconciles deletes internally.  A periodic
        #     full rescan (COCOINDEX_POLL_INTERVAL) backs up the watcher (baked
        #     into walk_dir(rescan_interval=…) for localfs; the FlexibleMapView
        #     detectors run their own internal polling for cloud sources).
        #   * non-watchable apps (native S3/Azure/Drive scan; flexible
        #     web/wikipedia/youtube/cmis) are reconciled by a single backup poll
        #     every COCOINDEX_POLL_INTERVAL.
        self._live_tasks: List[asyncio.Task] = []   # one _run_live task per watchable app
        self._poll_task: Optional[asyncio.Task] = None  # single backup poll for non-watchable apps
        self._watch_apps: List[Any] = []            # apps with a live stream
        self._poll_apps: List[Any] = []             # apps reconciled by the backup poll
        # Registry of runtime-built apps (UI-submitted via ingest_source) keyed by
        # app name — for idempotent reuse (CocoIndex rejects duplicate app names).
        self._source_apps: Dict[str, Any] = {}
        # app names that already have a dedicated live task (avoids duplicates).
        self._live_task_names: set = set()

        # Dedicated directory that CocoIndex's localfs connector monitors.
        # This is intentionally SEPARATE from ./uploads (the transient REST
        # staging area) so that leftover upload files from previous sessions
        # are not auto-ingested on startup.
        # Files explicitly ingested via POST /api/ingest are copied here by
        # ingest_files().  WATCH_DIR overrides for CLI testing.
        _default_source_dir = "./cocoindex-docs"
        self._source_dir: str = os.getenv("WATCH_DIR", _default_source_dir)

        # Single refresh cadence (seconds).  Used as: the backup-poll interval for
        # non-watchable apps, the localfs walk_dir(rescan_interval=…) backup, and
        # the restart backoff for a live stream that ends/errors.  Set to 0 to
        # disable the backup poll for non-watchable apps.
        try:
            self._poll_interval: int = int(float(os.getenv("COCOINDEX_POLL_INTERVAL", "60")))
        except Exception:
            self._poll_interval = 60
        self._db_path: str = (
            (fg_config and getattr(fg_config, "cocoindex_db_path", None))
            or os.getenv("COCOINDEX_DB", "./cocoindex.db")
        )

        # Upload directory — where REST /api/upload saves files
        self._uploads_dir: str = "./uploads"

        # Tracks the current effective skip_graph value baked into self._app's
        # cfg_json.  None = app not yet built / reflects ENABLE_KNOWLEDGE_GRAPH
        # from .env with no override.
        self._effective_skip_graph: Optional[bool] = None

        # Optional Postgres monitor (CocoIngestMonitor) — None until start().
        self._monitor: Optional[Any] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise the CocoIndex runtime and build the pipeline app.

        Must be called once before any ``update()`` call.  Idempotent if
        called multiple times.
        """
        if self._started:
            return
        if not _COCO_AVAILABLE:
            raise RuntimeError(
                "cocoindex is not installed. "
                "Run: uv pip install flexible-graphrag[cocoindex]"
            )

        # Make the LMDB path available to CocoIndex's Settings.from_env()
        if not os.getenv("COCOINDEX_DB"):
            os.environ["COCOINDEX_DB"] = self._db_path

        # Ensure the source directory exists before CocoIndex tries to scan it.
        # For the localfs connector this must happen before coco.start() /
        # build_pipeline_app() so the Rust engine doesn't get a missing-dir error.
        if self._data_source in ("filesystem", ""):
            Path(self._source_dir).mkdir(parents=True, exist_ok=True)
            logger.info(
                "CocoIndexBridge: source dir ready: %s", self._source_dir
            )

        logger.info(
            "CocoIndexBridge: starting (source=%s, source_dir=%s, db=%s)",
            self._data_source or "(none)", self._source_dir, self._db_path,
        )

        # Start the CocoIndex Rust engine / default environment
        await coco.start()
        self._started = True

        # Build the pipeline app — same app builders as pipeline/app.py.
        # Skip when DATA_SOURCE is empty: no primary .env source; UI picks sources.
        if self._data_source:
            self._app = self._build_pipeline_app(skip_graph=None)
        else:
            self._app = None
            logger.info(
                "CocoIndexBridge: DATA_SOURCE empty — no primary app "
                "(UI-configured sources only)"
            )

        # Run an initial update to process any already-present files.
        # CocoIndex's LMDB memoization handles change detection; the
        # FlexibleVectorHandler (registered in app_main) handles deletions.
        # Initialise Postgres monitor (best-effort; None when disabled/unreachable)
        if _MONITORING_MOD is not None:
            self._monitor = await _MONITORING_MOD.get_monitor()

        # Upsert a datasource_config row for the primary .env source so it
        # shows in the UI and can be tracked alongside UI-configured sources.
        _inc_url_early = os.getenv("POSTGRES_INCREMENTAL_URL", "")
        _primary_config_id: Optional[str] = None
        if _inc_url_early and self._data_source:
            _primary_config_id = await self._upsert_primary_datasource_config(_inc_url_early)

        # Build the multi-source app list.  The primary _app (from .env) is index 0
        # when DATA_SOURCE is set.  Additional apps come from datasource_config.
        self._apps = [self._app] if self._app is not None else []
        if _inc_url_early:
            try:
                from cocoindex_integration.pipeline.flexible_app import (  # noqa: PLC0415
                    build_apps_for_all_sources,
                )
                _db_apps = await build_apps_for_all_sources(
                    _inc_url_early,
                    skip_config_ids={_primary_config_id} if _primary_config_id else None,
                )
                for _db_app in _db_apps:
                    if _db_app is not None and _db_app not in self._apps:
                        self._apps.append(_db_app)
                if len(_db_apps) > 0:
                    logger.info(
                        "CocoIndexBridge: %d additional app(s) loaded from datasource_config",
                        len(_db_apps),
                    )
            except Exception as _dba_exc:
                logger.warning(
                    "CocoIndexBridge: failed to load datasource_config apps: %s", _dba_exc
                )

        # Tag the primary app's capability if the builder didn't (e.g. a
        # pipeline-module app reused in _build_pipeline_app).
        for _a in self._apps:
            if _a is not None and not hasattr(_a, "_fgr_watchable"):
                _a._fgr_watchable = self._compute_watchable(  # type: ignore[attr-defined]
                    self._data_source, self._source_backend
                )

        # Initial catch-up for every app BEFORE any live stream starts (no
        # concurrency).  Watchable apps then hand off to their live streams.
        if self._apps:
            logger.info(
                "CocoIndexBridge: running initial update (%d app(s)) ...",
                len(self._apps),
            )
            await self.update(trigger="startup", apps=self._apps)
        else:
            logger.info(
                "CocoIndexBridge: no apps at startup — waiting for UI-configured sources"
            )

        # Partition apps by capability and start the live streams + backup poll.
        self._partition_apps()
        for _wa in self._watch_apps:
            self._start_live_task(_wa)
        self._ensure_poll_loop()

        logger.info(
            "CocoIndexBridge: %d watchable app(s) live-streaming, %d app(s) on %ds backup poll",
            len(self._watch_apps), len(self._poll_apps), self._poll_interval,
        )

    async def stop(self) -> None:
        """Gracefully stop all live streams + the backup poll and the engine."""
        # Cancel every per-app live stream (startup + runtime ingest_source).
        _all_tasks = list(self._live_tasks)
        if self._poll_task is not None:
            _all_tasks.append(self._poll_task)
        if self._bg_task is not None:  # legacy field, kept for safety
            _all_tasks.append(self._bg_task)
        for _task in _all_tasks:
            if _task and not _task.done():
                _task.cancel()
                try:
                    await _task
                except asyncio.CancelledError:
                    pass
        self._live_tasks = []
        self._poll_task = None
        self._bg_task = None
        self._live_task_names = set()

        if self._monitor is not None:
            await self._monitor.close()
            self._monitor = None

        if self._started:
            try:
                await coco.stop()
                logger.info("CocoIndexBridge: stopped")
            except Exception as exc:
                logger.warning("CocoIndexBridge: stop error: %s", exc)
            finally:
                self._started = False

    # ------------------------------------------------------------------
    # Capability-based dispatch helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_watchable(data_source: str, source_backend: str) -> bool:
        """Delegate to flexible_app._compute_watchable (single source of truth)."""
        try:
            from cocoindex_integration.pipeline.flexible_app import (  # noqa: PLC0415
                _compute_watchable as _cw,
            )
            return _cw(data_source, source_backend)
        except Exception:
            return False

    def _partition_apps(self) -> None:
        """Split ``self._apps`` into watchable (live-stream) and poll-only lists."""
        self._watch_apps = [
            a for a in self._apps
            if a is not None and getattr(a, "_fgr_watchable", False)
        ]
        self._poll_apps = [
            a for a in self._apps
            if a is not None and not getattr(a, "_fgr_watchable", False)
        ]

    def _start_live_task(self, app_obj: Any) -> None:
        """Start a persistent live-stream task for *app_obj* (idempotent by name)."""
        name = getattr(app_obj, "_name", str(app_obj))
        if name in self._live_task_names:
            return
        task = asyncio.create_task(self._run_live(app_obj), name=f"cocoindex-live-{name}")
        self._live_tasks.append(task)
        self._live_task_names.add(name)

    def _ensure_poll_loop(self) -> None:
        """Start the single backup poll loop if there are poll-only apps."""
        if self._poll_interval <= 0:
            return
        if not self._poll_apps:
            return
        if self._poll_task is not None and not self._poll_task.done():
            return
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="cocoindex-bridge-poll"
        )

    # ------------------------------------------------------------------
    # Datasource config registration
    # ------------------------------------------------------------------

    async def _upsert_primary_datasource_config(self, db_url: str) -> Optional[str]:
        """Upsert a datasource_config row for the primary .env-configured source.

        This makes the source visible in the UI datasource list and allows
        monitoring to associate a stable config_id with it.  Uses a
        deterministic UUID (uuid5) so the same row is reused across restarts.
        Best-effort — never raises into the caller.
        """
        import json as _json  # noqa: PLC0415

        try:
            import asyncpg  # noqa: PLC0415
        except ImportError:
            return None

        st = self._data_source  # e.g. "s3", "filesystem", "gcs"

        # Fetch the full parsed env config (used for identity + per-field extraction).
        try:
            from cocoindex_integration.pipeline.flexible_app import (  # noqa: PLC0415
                _build_source_config_from_env,
            )
            raw_cfg = _build_source_config_from_env(st)
        except Exception:
            raw_cfg = {}

        # Build connection_params by parsing the source's {PREFIX}CONFIG env var
        # directly (e.g. S3_CONFIG, GCS_CONFIG, AZURE_BLOB_CONFIG, ONEDRIVE_CONFIG …).
        # Using the raw JSON means ALL user-supplied fields are stored automatically
        # — credentials, pubsub_subscription, account_url, sqs_queue_url, etc. —
        # without per-source field enumeration.
        # Falls back to raw_cfg minus the env-prefix noise keys when the {PREFIX}CONFIG
        # var is absent (source configured via individual vars instead of a JSON blob).
        try:
            from cocoindex_integration.pipeline.flexible_app import (  # noqa: PLC0415
                _SOURCE_ENV_PREFIX as _SEP,
            )
        except Exception:
            _SEP = {}

        _src_prefix = _SEP.get(st, "")
        _cfg_env_var = (_src_prefix.upper() + "CONFIG") if _src_prefix else ""
        _cfg_raw = os.getenv(_cfg_env_var, "") if _cfg_env_var else ""

        # Keys that _build_source_config_from_env adds as noise (duplicates /
        # SDK-internal aliases) — stripped from the raw_cfg fallback path.
        _NOISE = frozenset({"config", "bucket_name", "region",
                             "access_key_id", "secret_access_key", "paths"})

        if st == "filesystem":
            conn_params: Dict[str, Any] = {"path": self._source_dir}
            # Match _resolve_config_id() in main.py: "filesystem|<path>" with pipe separator.
            _identity = f"filesystem|{self._source_dir}"
        else:
            try:
                conn_params = _json.loads(_cfg_raw) if _cfg_raw else {}
            except Exception:
                conn_params = {}

            if not conn_params:
                # Fallback when no JSON blob env var: use raw_cfg, drop noise.
                conn_params = {
                    k: v for k, v in raw_cfg.items()
                    if k not in _NOISE and v not in ("", None)
                }

            # Deterministic UUID identity: source_type + primary key + optional prefix.
            _primary = (
                conn_params.get("bucket") or conn_params.get("bucket_name")              # S3, GCS
                or conn_params.get("container_name") or conn_params.get("container")     # Azure Blob
                or conn_params.get("folder_id")   # Google Drive, Box
                or conn_params.get("site_id")     # SharePoint
                or conn_params.get("server_url")  # Alfresco, CMIS
                or conn_params.get("path", self._source_dir)
            )
            _pfx = conn_params.get("prefix", "")
            _identity = f"{st}:{_primary}:{_pfx}" if _pfx else f"{st}:{_primary}"

        config_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, _identity))
        _display_id = (
            conn_params.get("bucket") or conn_params.get("bucket_name")
            or conn_params.get("container_name") or conn_params.get("container")
            or conn_params.get("folder_id") or self._source_dir
        )
        source_name = f"{st} ({_display_id})"

        try:
            conn = await asyncpg.connect(db_url)
            try:
                await conn.execute(
                    """
                    INSERT INTO datasource_config
                        (config_id, project_id, source_type, source_name,
                         connection_params, refresh_interval_seconds,
                         enable_change_stream, is_active)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, TRUE)
                    ON CONFLICT (config_id) DO UPDATE
                        SET source_name       = EXCLUDED.source_name,
                            connection_params = EXCLUDED.connection_params,
                            is_active         = TRUE,
                            updated_at        = NOW()
                    """,
                    config_id,
                    "default",
                    st,
                    source_name,
                    _json.dumps(conn_params),
                    self._poll_interval,
                    bool(raw_cfg.get("sqs_queue_url") or raw_cfg.get("connection_string")),
                )
                logger.info(
                    "CocoIndexBridge: upserted datasource_config row "
                    "(config_id=%s source=%s name=%r)",
                    config_id, st, source_name,
                )
            finally:
                await conn.close()
            return config_id
        except Exception as _exc:  # noqa: BLE001
            logger.warning(
                "CocoIndexBridge: could not upsert datasource_config: %s", _exc
            )
            return None

    async def _upsert_datasource_config_row(
        self,
        db_url: str,
        *,
        config_id: str,
        source_type: str,
        source_name: str,
        connection_params: Dict[str, Any],
    ) -> None:
        """Best-effort upsert of a datasource_config row for a UI-submitted source.

        Persists a UI-configured source so that on the next server restart
        :func:`build_apps_for_all_sources` rebuilds its CocoIndex app and the
        live/poll loop keeps it updated — no manual re-ingest needed.  Never
        raises into the caller.
        """
        import json as _json  # noqa: PLC0415

        try:
            import asyncpg  # noqa: PLC0415
        except ImportError:
            return
        try:
            conn = await asyncpg.connect(db_url)
            try:
                await conn.execute(
                    """
                    INSERT INTO datasource_config
                        (config_id, project_id, source_type, source_name,
                         connection_params, refresh_interval_seconds,
                         enable_change_stream, is_active)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, TRUE)
                    ON CONFLICT (config_id) DO UPDATE
                        SET source_name       = EXCLUDED.source_name,
                            connection_params = EXCLUDED.connection_params,
                            is_active         = TRUE,
                            updated_at        = NOW()
                    """,
                    config_id,
                    "default",
                    source_type,
                    source_name,
                    _json.dumps(connection_params),
                    self._poll_interval,
                    bool(
                        connection_params.get("sqs_queue_url")
                        or connection_params.get("connection_string")
                        or connection_params.get("pubsub_subscription")
                    ),
                )
                logger.info(
                    "CocoIndexBridge: upserted datasource_config row "
                    "(config_id=%s source=%s name=%r)",
                    config_id, source_type, source_name,
                )
            finally:
                await conn.close()
        except Exception as _exc:  # noqa: BLE001
            logger.warning(
                "CocoIndexBridge: could not upsert datasource_config for %s: %s",
                source_type, _exc,
            )

    # ------------------------------------------------------------------
    # Pipeline operations
    # ------------------------------------------------------------------

    def _make_monitor_hook(
        self,
        run_id: str,
        trigger: str,
        outer_cb: Optional[Any],
    ) -> Any:
        """Return a sync progress hook that writes file rows to cocoindex_ingest_log.

        This is the ONLY writer of per-file rows — callers pass their own
        ``progress_cb`` for UI updates and must not log to the same table
        themselves, or every event lands twice under two different run_ids.

        Volume is controlled by ``COCOINDEX_MONITOR_DETAIL``: ``summary``
        (default) writes one terminal row per file; ``stages`` writes every
        stage transition.

        Called from within CocoIndex's async pipeline so asyncio.get_running_loop()
        is always available.  Each DB write is fire-and-forget (create_task) so
        it never blocks the pipeline.  Errors are silently dropped.
        """
        monitor = self._monitor

        def _hook(event: dict) -> None:
            if outer_cb is not None:
                try:
                    outer_cb(event)
                except Exception:
                    pass
            if monitor is None:
                return
            evt = event.get("event")
            if evt not in ("file_stage", "file_done"):
                return
            stage = event.get("stage", "done") if evt == "file_stage" else "done"
            status = event.get("status") if evt == "file_done" else None
            if not _MONITORING_MOD.should_log_stage(stage, evt == "file_done"):
                return
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    monitor.log(
                        run_id=run_id,
                        stage=stage,
                        trigger=trigger,
                        file_name=event.get("file_name"),
                        file_path=event.get("file_path"),
                        status=status,
                        detail=event.get("detail"),
                    )
                )
            except Exception:
                pass

        return _hook

    async def update(
        self,
        full_reprocess: bool = False,
        progress_cb: Optional[Any] = None,
        trigger: str = "manual",
        apps: Optional[List[Any]] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run one CocoIndex update cycle (process all pending/changed files).

        CocoIndex's LMDB memoization ensures only new or modified documents
        are re-processed.  Pass ``full_reprocess=True`` to force a complete
        rebuild (equivalent to deleting cocoindex.db and re-running).

        ``progress_cb`` (optional) is a callable ``fn(event: dict) -> None``
        that receives per-file / per-stage progress events emitted by the
        pipeline (``_run_pipeline`` / ``process_flexible_file`` etc.).  It is
        installed via the pipeline module's ``set_progress_hook`` for the
        duration of this cycle only and cleared in the ``finally`` block.

        Deletions are handled natively by CocoIndex's reconciler:

        * **Flexible targets** (Elasticsearch, LlamaIndex vector, …) — the
          ``FlexibleVectorHandler`` receives ``NON_EXISTENCE`` for missing files
          and issues the appropriate deletes.
        * **Native targets** (Qdrant, Neo4j with ``VECTOR_BACKEND=cocoindex`` /
          ``GRAPH_BACKEND=cocoindex``) — tracked as ``managed_by=SYSTEM``; the
          reconciler issues point/node-level DELETEs automatically.

        Returns a dict with ``status``, ``stats``, and ``elapsed`` keys.
        """
        # ``self._app`` is None in UI-sources-only mode (DATA_SOURCE="" / "none"),
        # where every app comes from datasource_config instead.  Gating on
        # ``self._app`` alone made the startup catch-up AND every backup poll
        # return "Bridge not started" in that mode, so non-watchable UI sources
        # (web / wikipedia / youtube / cmis, native S3 / Azure / Drive) never
        # reconciled at all.  Only a bridge with no apps whatsoever is an error.
        if not self._started:
            return {"status": "error", "error": "Bridge not started"}
        if self._app is None and not self._apps:
            return {"status": "error", "error": "Bridge has no apps to update"}

        # Create run_id early so both the progress hook and log_run_summary share
        # it.  Callers that already have a job id (the REST ingest handler passes
        # its processing_id) supply it so DB rows join back to the UI job.
        run_id = run_id or str(uuid.uuid4())

        # Install the per-file/per-stage progress hook for this cycle.
        # When _monitor is active we wrap the caller's hook (if any) with one
        # that also fire-and-forgets _monitor.log() rows into cocoindex_ingest_log.
        # In live mode the hook stays active until the caller clears it (main.py
        # finally block) so staged uploads and folder drops emit PG monitor rows.
        _hook_installed = False
        _effective_hook = progress_cb
        if self._monitor is not None:
            _effective_hook = self._make_monitor_hook(
                run_id=run_id,
                trigger=trigger,
                outer_cb=progress_cb,
            )
        if _effective_hook is not None:
            try:
                self._get_pipeline_module().set_progress_hook(_effective_hook)
                _hook_installed = True
            except Exception as _he:  # noqa: BLE001
                logger.debug("CocoIndexBridge: could not install progress hook: %s", _he)

        # Decide which apps to reconcile this cycle.
        #   * explicit ``apps=`` (startup / poll loop) → use as given.
        #   * apps=None with live streams already running → reconcile only the
        #     poll-only apps; watchable apps are handled by their live streams,
        #     and a concurrent one-shot update() on a live app is unsafe.  The
        #     progress hook stays installed (above) so the live stream still
        #     emits per-file progress for UI feedback.
        #   * apps=None before any live stream (startup) → reconcile all apps.
        _live_active = any(not t.done() for t in self._live_tasks)
        if apps is not None:
            _apps_to_run = [a for a in apps if a is not None]
        elif _live_active:
            _apps_to_run = [a for a in self._poll_apps if a is not None]
        else:
            _apps_to_run = self._apps if self._apps else ([self._app] if self._app else [])
        t0 = time.perf_counter()
        logger.info(
            "CocoIndexBridge: update starting (trigger=%s, full_reprocess=%s, "
            "run_id=%s, apps=%d)",
            trigger, full_reprocess, run_id, len(_apps_to_run),
        )
        # Aggregate counters across all apps.
        _total_adds = _total_deletes = _total_unchanged = _total_errors = 0
        _all_errors: List[str] = []
        _comp_summaries: List[str] = []   # per-app component breakdown → run_log note
        elapsed = 0.0
        result: Dict[str, Any] = {"status": "ok"}
        try:
            for _i, _a in enumerate(_apps_to_run):
                if _a is None:
                    continue
                _app_name = getattr(_a, "_name", f"app[{_i}]")
                try:
                    handle = _a.update(full_reprocess=full_reprocess)
                    _app_result = await handle
                    stats = handle.stats()
                    # Document-level, not the all-component aggregate: "adds"
                    # must mean documents so the UI and cocoindex_run_log agree
                    # with what the user actually ingested.
                    _c = _document_level_counters(stats)
                    _total_adds += _c["adds"]
                    _total_deletes += _c["deletes"]
                    _total_unchanged += _c["unchanged"]
                    _total_errors += _c["errors"]
                    if _c["adds"] > 0 or _c["deletes"] > 0 or _c["errors"] > 0:
                        logger.info(
                            "CocoIndexBridge [%s]: adds=%d deletes=%d unchanged=%d errors=%d",
                            _app_name, _c["adds"], _c["deletes"], _c["unchanged"], _c["errors"],
                        )
                    _comp_str = _component_summary_str(stats)
                    if _comp_str:
                        logger.debug("CocoIndexBridge [%s] components: %s", _app_name, _comp_str)
                        _comp_summaries.append(f"{_app_name} :: {_comp_str}")
                except Exception as _app_exc:
                    logger.error(
                        "CocoIndexBridge: update error for app '%s': %s",
                        _app_name, _app_exc, exc_info=True,
                    )
                    _all_errors.append(f"{_app_name}: {_app_exc}")

            elapsed = time.perf_counter() - t0
            self._update_count += 1

            result = {
                "status": "ok" if not _all_errors else "partial",
                "elapsed": round(elapsed, 2),
                "update_count": self._update_count,
                "apps": len(_apps_to_run),
                "adds": _total_adds,
                "deletes": _total_deletes,
                "unchanged": _total_unchanged,
                "errors": _total_errors,
            }
            if _all_errors:
                result["app_errors"] = _all_errors

            if apps is None and _live_active and self._watch_apps and not _apps_to_run:
                # Nothing ran in this one-shot cycle because the only relevant
                # source(s) are watchable and reconciled by their live stream(s).
                # Signal deferral so the REST ingest handler waits for the live
                # stream's per-file progress events (rather than reporting
                # completion immediately).  When a poll-only app WAS processed
                # here (_apps_to_run non-empty) we do NOT defer.
                result["live_deferred"] = True
                result["live_watch_apps"] = len(self._watch_apps)
                result.setdefault(
                    "note", "watchable sources reconciled by their live stream(s)"
                )

            if _total_adds > 0 or _total_deletes > 0 or _total_errors > 0:
                logger.info(
                    "CocoIndexBridge: update #%d done in %.1fs "
                    "[trigger=%s adds=%d deletes=%d unchanged=%d errors=%d]",
                    self._update_count, elapsed, trigger,
                    _total_adds, _total_deletes, _total_unchanged, _total_errors,
                )
            else:
                logger.info(
                    "CocoIndexBridge: update #%d done in %.1fs "
                    "[trigger=%s unchanged=%d — nothing to do]",
                    self._update_count, elapsed, trigger, _total_unchanged,
                )

            if _total_deletes > 0:
                logger.info(
                    "CocoIndexBridge: %d record(s) deleted from targets. "
                    "Note: CocoIndex constraint indexes are permanent root-schema guards "
                    "— they survive until you run 'python scripts/cleanup.py'.",
                    _total_deletes,
                )

            if self._monitor is not None:
                await self._monitor.log_run_summary(
                    run_id=run_id,
                    trigger=trigger,
                    stats={
                        "adds": _total_adds,
                        "deletes": _total_deletes,
                        "unchanged": _total_unchanged,
                        "errors": _total_errors,
                    },
                    elapsed_s=elapsed,
                    update_count=self._update_count,
                    note=" | ".join(_comp_summaries) or None,
                )

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.error("CocoIndexBridge: update error: %s", exc, exc_info=True)
            result = {"status": "error", "error": str(exc), "elapsed": round(elapsed, 2)}
        finally:
            # Clear runtime skip_graph flag after each cycle so background
            # polling / subsequent requests aren't affected.
            self._get_pipeline_module().set_runtime_graphs(None)
            if self._effective_skip_graph is not None:
                _pipeline_mod = self._get_pipeline_module()
                _pipeline_mod.set_runtime_skip_graph(None)
                self._effective_skip_graph = None
            # Clear the progress hook so background polling / later cycles do
            # not report into a stale processing_id.
            #
            # EXCEPTION — live-deferred: when this one-shot cycle ran nothing
            # because the source is watchable (handled by its live stream), the
            # actual per-file work happens asynchronously in _run_live AFTER this
            # update() returns.  _run_live relies on the globally-installed hook,
            # so we must LEAVE it installed here — otherwise the live stream's
            # ``file_done`` events never reach the caller's progress_cb, the
            # REST handler's _live_done event never fires, and the request hangs
            # until its 600s timeout (processing status never completes).
            # The caller (main.py _run_cocoindex_bg finally) clears it once the
            # live stream has reported completion (or timed out).
            if _hook_installed and not result.get("live_deferred"):
                try:
                    self._get_pipeline_module().set_progress_hook(None)
                except Exception:  # noqa: BLE001
                    pass

        self._last_update = result
        return result

    async def sync_now(self, full_reprocess: bool = False) -> Dict[str, Any]:
        """Trigger a manual CocoIndex update — mirrors ``POST /api/sync/sync-now``.

        Equivalent to running ``cocoindex update cocoindex_integration/pipeline/app.py``
        from the CLI.  CocoIndex's LMDB memoization ensures only new or modified
        documents are re-processed (unless ``full_reprocess=True``).

        Args:
            full_reprocess: invalidate all LMDB memo state and reprocess every
                document from scratch.  Use after changing chunking / extraction
                config.  Equivalent to deleting cocoindex.db then re-running.
        """
        return await self.update(full_reprocess=full_reprocess, trigger="ui")

    async def ingest_source(
        self,
        data_source: str,
        connection_params: Dict[str, Any],
        *,
        config_id: Optional[str] = None,
        source_name: Optional[str] = None,
        skip_graph: bool = False,
        graphs=None,
        enable_sync: bool = False,
        progress_cb: Optional[Any] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build (or reuse) a CocoIndex app for a UI-submitted data source and run it.

        Used when ``PIPELINE_BACKEND=cocoindex`` and the UI data-source dialog
        submits a source that is *not* the primary ``.env`` source (e.g. the user
        picks Alfresco / S3 / Box / CMIS interactively).  The submitted source is
        still processed through the CocoIndex pipeline:

        1. A ``coco.App`` is built for the source config (or reused if one with
           the same name already exists — idempotent re-ingest).
        2. A one-shot ``app.update()`` is awaited so the UI Process tab shows
           real per-file progress and a proper completion.
        3. When ``enable_sync`` is set: the source is persisted to
           ``datasource_config`` (so a restart rebuilds it) and kept continuously
           updated based on its capability — a **watchable** source (detector-backed
           / native localfs) gets a dedicated ``_run_live`` stream; a
           non-watchable source (native S3/Azure/Drive, flexible
           web/wikipedia/youtube/cmis) is added to the backup poll list and
           reconciled every ``COCOINDEX_POLL_INTERVAL``.
        4. When ``enable_sync`` is *not* set: the source is processed exactly once
           (one-shot) and not persisted — CocoIndex still records memo state in
           the LMDB (``cocoindex.db``) under the app name, so an explicit re-ingest
           skips unchanged content, but nothing re-scans it on its own.

        Args:
            data_source: source type (e.g. ``alfresco``, ``s3``, ``box``).
            connection_params: source credentials/paths from the UI request
                (same shape stored in ``datasource_config.connection_params``).
            config_id: stable UUID for this source (from the ingest handler).
            source_name: human-readable label for the UI/datasource list.
            skip_graph: disable KG extraction for this source.
            enable_sync: when True (the UI "keep in sync" checkbox), the source is
                persisted to ``datasource_config`` and kept continuously updated
                (live stream for watchable sources, backup poll otherwise).  When
                False the source is processed once (one-shot) and not persisted.
            progress_cb: per-file/per-stage progress hook (UI Process tab).
        """
        if not self._started:
            return {"status": "error", "error": "Bridge not started"}

        from cocoindex_integration.pipeline.flexible_app import (  # noqa: PLC0415
            build_app_for_config,
        )

        app_name = (
            f"GraphRAG_{data_source}_{config_id}" if config_id
            else f"GraphRAG_{data_source}"
        )

        # Reuse an already-built app with the same name (idempotent re-ingest):
        # check the runtime registry first, then the primary / datasource_config apps.
        app = self._source_apps.get(app_name)
        if app is None:
            for _a in self._apps:
                if _a is not None and getattr(_a, "_name", None) == app_name:
                    app = _a
                    break

        newly_built = False
        if app is None:
            source_config: Dict[str, Any] = {
                "connection_params": connection_params,
                "config_id": config_id or "",
                "data_source": data_source,
                "source_name": source_name or data_source,
            }
            try:
                app = build_app_for_config(
                    source_config, app_name=app_name, skip_graph=skip_graph,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "CocoIndexBridge.ingest_source: build failed for source=%s: %s",
                    data_source, exc, exc_info=True,
                )
                return {"status": "error", "error": str(exc), "app_name": app_name}
            self._source_apps[app_name] = app
            newly_built = True
            logger.info(
                "CocoIndexBridge.ingest_source: registered new app '%s' (source=%s)",
                app_name, data_source,
            )

        # Register in the master app list so status() reflects it.
        if app is not None and app not in self._apps:
            self._apps.append(app)

        # Persist to datasource_config so a restart rebuilds it automatically
        # (only when the UI requested continuous sync).  Idempotent upsert.
        _inc_url = os.getenv("POSTGRES_INCREMENTAL_URL", "")
        if enable_sync and _inc_url and config_id:
            await self._upsert_datasource_config_row(
                _inc_url,
                config_id=config_id,
                source_type=data_source,
                source_name=source_name or f"{data_source} ({config_id[:8]})",
                connection_params=connection_params,
            )

        # If this source already has a running live stream (re-ingest of a synced
        # watchable source), a concurrent one-shot update() would race the stream
        # — skip it and let the live stream reconcile the change.
        if app_name in self._live_task_names:
            logger.info(
                "CocoIndexBridge.ingest_source [%s]: live stream already active — "
                "change will be reconciled by the stream (skipping one-shot update)",
                app_name,
            )
            result = {
                "status": "ok", "source_ingest": True, "app_name": app_name,
                "note": "live stream active — reconciled by the stream",
            }
            self._last_update = result
            return result

        # One-shot awaited update with the progress hook installed for UI feedback.
        run_id = run_id or str(uuid.uuid4())
        _effective_hook = progress_cb
        if self._monitor is not None:
            _effective_hook = self._make_monitor_hook(
                run_id=run_id, trigger="ui", outer_cb=progress_cb,
            )
        _hook_installed = False
        if _effective_hook is not None:
            try:
                self._get_pipeline_module().set_progress_hook(_effective_hook)
                _hook_installed = True
            except Exception as _he:  # noqa: BLE001
                logger.debug("CocoIndexBridge.ingest_source: hook install failed: %s", _he)

        # Apply the graphs (or the older skip_graph) via the runtime flags for this cycle.
        self._apply_skip_graph(skip_graph, graphs)

        t0 = time.perf_counter()
        result: Dict[str, Any] = {
            "status": "ok", "source_ingest": True, "app_name": app_name,
        }
        try:
            handle = app.update(full_reprocess=False)
            await handle
            stats = handle.stats()
            _c = _document_level_counters(stats)
            elapsed = time.perf_counter() - t0
            self._update_count += 1
            result.update({
                "elapsed": round(elapsed, 2),
                "adds": _c["adds"], "deletes": _c["deletes"],
                "unchanged": _c["unchanged"], "errors": _c["errors"],
                "update_count": self._update_count,
            })
            logger.info(
                "CocoIndexBridge.ingest_source [%s]: adds=%d deletes=%d unchanged=%d "
                "errors=%d (%.1fs)",
                app_name, _c["adds"], _c["deletes"], _c["unchanged"], _c["errors"], elapsed,
            )
            if self._monitor is not None:
                await self._monitor.log_run_summary(
                    run_id=run_id,
                    trigger="ui",
                    stats={
                        "adds": _c["adds"], "deletes": _c["deletes"],
                        "unchanged": _c["unchanged"], "errors": _c["errors"],
                    },
                    elapsed_s=elapsed,
                    update_count=self._update_count,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "CocoIndexBridge.ingest_source [%s]: update error: %s",
                app_name, exc, exc_info=True,
            )
            result = {"status": "error", "error": str(exc), "app_name": app_name}
        finally:
            self._get_pipeline_module().set_runtime_graphs(None)
            if self._effective_skip_graph is not None:
                self._get_pipeline_module().set_runtime_skip_graph(None)
                self._effective_skip_graph = None
            if _hook_installed:
                try:
                    self._get_pipeline_module().set_progress_hook(None)
                except Exception:  # noqa: BLE001
                    pass

        # Keep the source updating continuously when sync is requested, based on
        # its change-detection capability:
        #   * watchable  → dedicated live-stream task (event-driven + rescan backup)
        #   * otherwise  → add to the backup poll list (reconciled every interval)
        if enable_sync:
            _watchable = bool(getattr(app, "_fgr_watchable", False))
            if _watchable:
                self._start_live_task(app)
                logger.info(
                    "CocoIndexBridge.ingest_source: live task started for '%s'", app_name
                )
            else:
                if app not in self._poll_apps:
                    self._poll_apps.append(app)
                self._ensure_poll_loop()
                logger.info(
                    "CocoIndexBridge.ingest_source: '%s' added to backup poll (%ds)",
                    app_name, self._poll_interval,
                )

        self._last_update = result
        return result

    async def ingest_files(
        self,
        file_paths: List[str],
        *,
        skip_graph: bool = False,
        graphs=None,
        move: bool = False,
        progress_cb: Optional[Any] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a list of files through the CocoIndex pipeline.

        Called by the REST ``POST /api/ingest`` handler (and the UI file-upload
        flow) when ``PIPELINE_BACKEND=cocoindex`` and ``data_source=filesystem``,
        regardless of whether ``SOURCE_BACKEND`` is ``cocoindex`` or ``flexible``.
        Cloud source types (s3, azure_blob, etc.) do not use this path — they
        are processed directly by their source connector on ``bridge.update()``.

        **skip_graph support**
        ``skip_graph`` is respected as a true per-request flag.  The bridge
        tracks the current ``enable_knowledge_graph`` setting baked into
        the app's ``cfg_json``.  When the requested ``skip_graph`` value
        differs from the current setting, the bridge rebuilds the ``coco.App``
        with updated ``cfg_json`` (same app name, same LMDB state).  CocoIndex
        detects the changed memo key and reprocesses the source documents under
        the new config — the CocoIndex-idiomatic way to apply a config change.

        Typical patterns
        ~~~~~~~~~~~~~~~~
        * Folder A always ingested with ``skip_graph=False`` (default) — KG
          populated for every document.
        * Folder B / a specific user flow ingests with ``skip_graph=True`` —
          only vector + search targets are populated, KG is skipped.
        * Switching back to ``skip_graph=False`` rebuilds the app and
          reprocesses so KG is filled in.

        **Server mode (REST file upload flow):**
        Files arrive in ``./uploads/`` via ``POST /api/upload``, then
        ``POST /api/ingest`` sends their filenames (relative or absolute).
        This method resolves relative names from the uploads directory and
        copies them into the CocoIndex source directory (``./cocoindex-docs``
        by default) so CocoIndex's ``localfs`` connector can pick them up.
        ``./uploads`` is a shared staging area and is intentionally kept
        separate from the CocoIndex watch directory.

        **Standalone/testing mode (WATCH_DIR):**
        If ``WATCH_DIR`` is set to a different directory, files are copied
        there instead.  This is useful when running ``cocoindex update app.py``
        from the CLI against a separate docs folder.

        Args:
            file_paths: filenames or paths from the ingest request.  May be:
                - Relative filenames (from UI upload) → resolved from ``./uploads/``
                - Absolute paths (from MCP / filesystem source) → used as-is
            skip_graph: if True, KG extraction (Neo4j / RDF) is disabled for
                this update cycle.  The pipeline still writes to vector + search
                stores.  A value different from the previous call causes the app
                to be rebuilt with an updated ``cfg_json`` memo key.
            move: if True, move source files instead of copying (disk I/O saving
                when source and destination are on the same filesystem).
        """
        # ── graphs / skip_graph: runtime flags for this cycle ──────────────────
        self._apply_skip_graph(skip_graph, graphs)

        if self._data_source not in ("filesystem", ""):
            # For cloud / remote sources the FlexibleDataSource polls the remote
            # source directly — just trigger a regular update.
            logger.info(
                "CocoIndexBridge.ingest_files: source=%s — triggering update (no file copy needed)",
                self._data_source,
            )
            result = await self.update(
                progress_cb=progress_cb, trigger="ui", run_id=run_id,
            )
            result["note"] = (
                f"File copy skipped for source='{self._data_source}'; "
                "CocoIndex polls the remote source directly."
            )
            return result

        uploads = Path(self._uploads_dir)
        source_dir = Path(self._source_dir)
        source_dir.mkdir(parents=True, exist_ok=True)

        # Resolve each path — relative names are looked up in the uploads dir
        resolved: List[Path] = []
        for fp in file_paths:
            p = Path(fp)
            if p.is_absolute() and p.exists():
                resolved.append(p)
            elif (uploads / p.name).exists():
                resolved.append(uploads / p.name)
            elif p.exists():
                resolved.append(p)
            else:
                logger.warning("CocoIndexBridge.ingest_files: not found — %s", fp)

        # If source_dir somehow equals uploads dir (should not happen with the
        # ./cocoindex-docs default), skip the copy.  Otherwise stage files.
        ingested: List[str] = []
        errors: List[str] = []

        # Pre-install the progress hook BEFORE copying files to the watch directory.
        #
        # Race condition: watchfiles runs in a Rust background thread.  As soon as
        # shutil.copy2 / shutil.move completes, watchfiles can detect the new file
        # and CocoIndex will queue process_localfs_file() via
        # asyncio.run_coroutine_threadsafe() (call_soon_threadsafe).  The event loop
        # processes that queued task at the NEXT await point — which is the `await
        # self.update(...)` call below.  If the hook is not yet installed when
        # process_localfs_file emits its "file_done" event, _live_done is never set
        # and main.py hangs for the full timeout.
        #
        # Installing the hook here (before the copy) is safe: it is a plain Python
        # attribute assignment (no await, no I/O), and update() will reinstall it
        # below, possibly wrapping it with the monitor callback.  Any "file_done"
        # event captured by this early hook still reaches the caller's progress_cb,
        # which is exactly what main.py's _coco_progress needs to set _live_done.
        if progress_cb is not None:
            try:
                self._get_pipeline_module().set_progress_hook(progress_cb)
                logger.debug(
                    "CocoIndexBridge.ingest_files: pre-installed progress hook "
                    "before file copy to close watchfiles race window"
                )
            except Exception as _phe:  # noqa: BLE001
                logger.debug(
                    "CocoIndexBridge.ingest_files: could not pre-install progress hook: %s",
                    _phe,
                )

        needs_copy = source_dir.resolve() != uploads.resolve()
        if needs_copy:
            for src in resolved:
                dst = source_dir / src.name
                try:
                    # ── Cache-hit detection ─────────────────────────────────────────
                    # When the destination file already exists with IDENTICAL content,
                    # CocoIndex's @coco.fn(memo=True) will return the cached result
                    # without executing the worker body.  That means _run_pipeline
                    # never runs, so no "file_done" event is emitted, and main.py's
                    # _live_done asyncio.Event never gets set → 600-second hang.
                    #
                    # Detect this early: if size + MD5 match, skip the copy and emit
                    # file_done(status="skipped") directly so _live_done is set
                    # immediately.  The CocoIndex state is already current; no copy
                    # (and no CocoIndex re-processing) is needed.
                    _cache_hit = False
                    if not move and dst.exists():
                        try:
                            if dst.stat().st_size == src.stat().st_size:
                                import hashlib
                                _src_md5 = hashlib.md5(src.read_bytes()).hexdigest()
                                _dst_md5 = hashlib.md5(dst.read_bytes()).hexdigest()
                                _cache_hit = (_src_md5 == _dst_md5)
                        except Exception as _he:  # noqa: BLE001
                            logger.debug(
                                "CocoIndexBridge: hash check failed for %s: %s",
                                src.name, _he,
                            )

                    if _cache_hit:
                        ingested.append(str(dst))
                        logger.info(
                            "CocoIndexBridge.ingest_files: %s already current "
                            "(identical content) — emitting file_done immediately; "
                            "CocoIndex will cache-hit",
                            src.name,
                        )
                        if progress_cb is not None:
                            try:
                                progress_cb({
                                    "event": "file_done",
                                    "file_name": src.name,
                                    "file_path": str(dst),
                                    "status": "skipped",
                                    "detail": "cache_hit",
                                })
                            except Exception:  # noqa: BLE001
                                pass
                        continue

                    if move:
                        shutil.move(str(src), dst)
                    else:
                        shutil.copy2(src, dst)
                    ingested.append(str(dst))
                    logger.debug(
                        "CocoIndexBridge: %s %s -> %s",
                        "moved" if move else "copied", src.name, dst,
                    )
                except Exception as exc:
                    errors.append(f"{src.name}: {exc}")
                    logger.warning("CocoIndexBridge: copy error %s: %s", src.name, exc)
            logger.info(
                "CocoIndexBridge.ingest_files: %d file(s) staged in %s",
                len(ingested), source_dir,
            )
        else:
            # source_dir == uploads dir — files already in place, no copy needed.
            # Still emit file_done for each file so _live_done is set; CocoIndex
            # will cache-hit on all of them (content hasn't changed).
            ingested = [str(r) for r in resolved]
            logger.info(
                "CocoIndexBridge.ingest_files: %d file(s) already in source dir %s "
                "— emitting file_done(skipped) for each",
                len(ingested), source_dir,
            )
            if progress_cb is not None:
                for _r in resolved:
                    try:
                        progress_cb({
                            "event": "file_done",
                            "file_name": _r.name,
                            "file_path": str(_r),
                            "status": "skipped",
                            "detail": "cache_hit",
                        })
                    except Exception:  # noqa: BLE001
                        pass

        result = await self.update(
            progress_cb=progress_cb, trigger="ui", run_id=run_id,
        )
        result["files_ingested"] = ingested
        if errors:
            result["file_errors"] = errors
        return result

    async def ingest_text(
        self,
        content: str,
        source_name: str = "text_input.txt",
        *,
        skip_graph: bool = False,
        graphs=None,
        progress_cb: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Ingest raw text via the CocoIndex filesystem path.

        Writes ``content`` to a file under the CocoIndex source directory, then
        calls :meth:`ingest_files`.  REST ``/api/ingest-text`` stages into
        ``uploads/`` and uses ``ingest_files`` directly; this helper is for
        callers that want to write into the watch dir in one step.
        """
        source_dir = Path(self._source_dir)
        source_dir.mkdir(parents=True, exist_ok=True)

        name = Path(source_name or "text_input.txt").name
        if not name.lower().endswith((".txt", ".md", ".markdown", ".html", ".htm")):
            name = f"{name}.txt"
        if not name or name in (".", ".."):
            name = "text_input.txt"

        dest = source_dir / name
        dest.write_text(content, encoding="utf-8")
        logger.info(
            "CocoIndexBridge.ingest_text: wrote %d chars -> %s",
            len(content), dest,
        )
        return await self.ingest_files(
            [str(dest)],
            skip_graph=skip_graph,
            graphs=graphs,
            progress_cb=progress_cb,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return a status dict suitable for ``GET /api/cocoindex/status``."""
        _app_names = [
            getattr(a, "_name", str(a))
            for a in self._apps
            if a is not None
        ]
        return {
            "pipeline_backend": "cocoindex",
            "started": self._started,
            "data_source": self._data_source,
            "source_dir": self._source_dir,
            "uploads_dir": self._uploads_dir,
            "db_path": self._db_path,
            "poll_interval_seconds": self._poll_interval,
            "watchable_apps": len(self._watch_apps),
            "poll_apps": len(self._poll_apps),
            "live_tasks": len([t for t in self._live_tasks if not t.done()]),
            "update_count": self._update_count,
            "app_name": self._app._name if self._app is not None else None,
            "app_names": _app_names,
            "num_apps": len(self._apps),
            # skip_graph: None = env default, True/False = last per-request override
            "skip_graph": self._effective_skip_graph,
            "last_update": self._last_update,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_skip_graph(self, skip_graph: bool, graphs=None) -> None:
        """Apply a per-request skip_graph override for the next update() cycle.

        Only ``skip_graph=True`` forces KG off for this cycle.  ``skip_graph=False``
        (the API default) honours ``ENABLE_KNOWLEDGE_GRAPH`` from ``.env`` — it does
        not force extraction on.

        CocoIndex registers each app by name exactly once — recreating it to
        change cfg_json raises ``ValueError: already registered``.  Instead,
        a module-level runtime flag (``_runtime_skip_graph`` in
        ``pipeline/app.py``) is set here and read inside ``_run_pipeline``
        before deciding whether to run KG extraction.  ``update()`` in the
        bridge clears the flag after the cycle completes.

        Args:
            skip_graph: the value requested by the current ingest call.
            graphs: which graphs it builds (graph_flags.GraphFlags); when given it decides,
                graph by graph (``pipeline/run.py`` _resolve_graphs).
        """
        _pipeline = self._get_pipeline_module()
        _pipeline.set_runtime_graphs(graphs)
        if graphs is not None:
            logger.info("CocoIndexBridge: this update cycle builds %s", graphs.describe())
            skip_graph = graphs.none
        if skip_graph:
            if self._effective_skip_graph is True:
                return
            logger.info(
                "CocoIndexBridge: skip_graph=True — disabling KG extraction "
                "for this update cycle via runtime flag",
            )
            _pipeline.set_runtime_skip_graph(True)
            self._effective_skip_graph = True
        elif self._effective_skip_graph is not None:
            _pipeline.set_runtime_skip_graph(None)
            self._effective_skip_graph = None

    @staticmethod
    def _get_pipeline_module() -> Any:
        """Return the actual ``cocoindex_integration.pipeline.app`` module object.

        ``import cocoindex_integration.pipeline.app as x`` resolves via attribute
        lookup on the package and returns the module-level ``app`` variable (a
        ``coco.App`` instance) rather than the module itself, because
        ``pipeline/__init__.py`` re-exports ``app`` from the submodule.
        Using ``sys.modules`` always returns the real module regardless of
        what ``__init__.py`` re-exports.
        """
        import sys
        import importlib

        mod_name = "cocoindex_integration.pipeline.app"
        if mod_name not in sys.modules:
            importlib.import_module(mod_name)
        return sys.modules[mod_name]

    def _build_pipeline_app(self, skip_graph: Optional[bool] = None) -> Any:
        """Return the coco.App for the configured source type.

        All source/backend resolution (native vs flexible, availability checks,
        fallbacks) is delegated to ``_build_default_app`` →
        ``build_app_for_config`` → ``_resolve_pipeline_config``.

        Per-request ``skip_graph`` changes are handled at runtime via
        ``set_runtime_skip_graph`` — not by recreating the app.
        """
        _pipeline = self._get_pipeline_module()
        # Reuse an already-registered app if one exists (CocoIndex rejects
        # duplicate app names within the same process).
        existing = (
            getattr(_pipeline, "_flexible_app", None)
            or getattr(_pipeline, "app", None)
        )
        if existing is not None:
            logger.info(
                "CocoIndexBridge: using registered app '%s'", existing._name,
            )
            return existing

        # No registered app yet — build one. _build_default_app handles all
        # source type + backend resolution via _resolve_pipeline_config.
        source_dir = self._source_dir if self._data_source in ("filesystem", "") else None
        logger.info(
            "CocoIndexBridge: building app (source=%s, source_dir=%s)",
            self._data_source, source_dir,
        )
        return _pipeline._build_default_app(source_dir)

    async def _poll_loop(self) -> None:
        """Backup reconcile loop for non-watchable apps (native S3/Azure/Drive;
        flexible web/wikipedia/youtube/cmis).

        Runs ``update(apps=self._poll_apps)`` every ``_poll_interval`` seconds.
        Watchable apps are NOT touched here — they are handled by their live
        streams.  CocoIndex's LMDB memoization means only new/changed documents
        are reprocessed.
        """
        while True:
            try:
                await asyncio.sleep(self._poll_interval)
                if not self._poll_apps:
                    continue
                logger.debug(
                    "CocoIndexBridge: backup poll — reconciling %d app(s) …",
                    len(self._poll_apps),
                )
                await self.update(trigger="poll", apps=self._poll_apps)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("CocoIndexBridge: poll update error: %s", exc)

    async def _run_live(self, app_obj: Any) -> None:
        """Persistent live-stream task for one watchable ``coco.App``.

        Runs a one-shot catch-up scan (to pick up anything that changed while a
        previous stream was down), then ``app.update(live=True)`` which watches
        the source for changes and reconciles adds / updates / deletes as they
        happen:

        * native localfs — ``walk_dir(live=True)`` returns a ``LiveMapView`` that
          watches the directory (watchfiles) with a ``rescan_interval`` backup;
        * flexible detector-backed sources — ``FlexibleMapView.watch()`` keeps the
          detector alive and forwards ``detector.get_changes()`` events.

        If the stream ends or errors it is restarted after ``_poll_interval``
        seconds (bounded to ≥5 s).  Progress flows through the globally-installed
        progress hook so the UI Process tab still shows per-file activity.
        """
        _app_name = getattr(app_obj, "_name", str(app_obj))
        _backoff = max(5, self._poll_interval or 60)
        _seq = 0
        _loop_iter = 0   # 0 = first entry; >0 = restart after stream error
        while True:
            try:
                # Catch-up scan before (re-)entering the live stream.
                # SKIP on the first entry: start() already ran update(trigger="startup")
                # for all apps.  Running update() again immediately creates a second
                # walk_dir(live=True) instance before CocoIndex has cleaned up the
                # first one (Windows OS watcher race) → concurrent file.read() →
                # PermissionError on the second attempt.  Only needed on restart.
                if _loop_iter > 0:
                    try:
                        _cu = app_obj.update()
                        await _cu
                        _cs = _document_level_counters(_cu.stats())
                        if _cs["adds"] > 0 or _cs["deletes"] > 0 or _cs["errors"] > 0:
                            logger.info(
                                "CocoIndexBridge [%s catch-up]: adds=%d deletes=%d unchanged=%d",
                                _app_name, _cs["adds"], _cs["deletes"], _cs["unchanged"],
                            )
                    except asyncio.CancelledError:
                        raise
                    except Exception as _ce:  # noqa: BLE001
                        logger.debug("CocoIndexBridge [%s catch-up] error: %s", _app_name, _ce)
                _loop_iter += 1

                logger.info("CocoIndexBridge [%s]: starting live update stream …", _app_name)
                handle = app_obj.update(live=True)
                _prev_adds = _prev_deletes = _prev_unch = _prev_errors = 0
                try:
                    async for snapshot in handle.watch():
                        _seq += 1
                        # snapshot is an UpdateSnapshot — _document_level_counters
                        # unwraps .stats; reading it directly yields all zeros,
                        # which is why live rows never used to be logged.
                        _c = _document_level_counters(snapshot)
                        d_adds    = _c["adds"]      - _prev_adds
                        d_deletes = _c["deletes"]   - _prev_deletes
                        d_unch    = _c["unchanged"] - _prev_unch
                        d_errors  = _c["errors"]    - _prev_errors
                        _prev_adds    = _c["adds"]
                        _prev_deletes = _c["deletes"]
                        _prev_unch    = _c["unchanged"]
                        _prev_errors  = _c["errors"]
                        if d_adds > 0 or d_deletes > 0 or d_errors > 0:
                            logger.info(
                                "CocoIndexBridge [%s live #%d]: "
                                "adds=%d deletes=%d unchanged=%d errors=%d",
                                _app_name, _seq, d_adds, d_deletes, d_unch, d_errors,
                            )
                            if self._monitor is not None:
                                try:
                                    await self._monitor.log_run_summary(
                                        run_id=str(uuid.uuid4()),
                                        trigger="live",
                                        stats={
                                            "adds": d_adds, "deletes": d_deletes,
                                            "unchanged": d_unch, "errors": d_errors,
                                        },
                                        update_count=_seq,
                                    )
                                except Exception:  # noqa: BLE001
                                    pass
                except StopAsyncIteration:
                    pass
                logger.info(
                    "CocoIndexBridge [%s]: live stream finished — restarting in %ds",
                    _app_name, _backoff,
                )
                await asyncio.sleep(_backoff)
            except asyncio.CancelledError:
                logger.info("CocoIndexBridge [%s]: live stream cancelled", _app_name)
                break
            except Exception as exc:
                logger.warning("CocoIndexBridge [%s]: live error: %s", _app_name, exc)
                await asyncio.sleep(_backoff)



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ZERO_COUNTERS = dict(adds=0, deletes=0, unchanged=0, reprocesses=0,
                      errors=0, in_progress=0, finished=0)

#: Component names that process ONE DOCUMENT each.  Everything else CocoIndex
#: reports (parse_document, _embed_chunks_cached, extract_kg_*) is a sub-step
#: that runs once per file OR once per chunk, so summing every component — which
#: is what ``UpdateStats.total`` does — produces a number that is neither a file
#: count nor a chunk count.  ``_document_level_counters`` filters to these.
_DOC_LEVEL_COMPONENTS = (
    "process_flexible_file",
    "process_flexible_item",
    "process_localfs_file",
    "process_s3_file",
    "process_azure_blob_file",
    "process_google_drive_file",
    "process_document",
)


def _unwrap_stats(stats: Any) -> Any:
    """Return the ``UpdateStats`` behind *stats*, whatever shape it arrives in.

    ``handle.watch()`` yields ``UpdateSnapshot(stats=…, status=…, result=…)``
    — a NamedTuple that has no ``total`` and no ``num_*`` fields of its own.
    Passing one straight into a counter reader silently returns all zeros
    (which is why live-mode logging reported nothing).  ``handle.stats()``
    returns the ``UpdateStats`` directly, and some callers pass a bare
    ``ComponentStats``; all three are accepted here.
    """
    return getattr(stats, "stats", stats)


def _extract_stats_counters(stats: Any) -> dict:
    """Pull scalar counters out of a CocoIndex UpdateStats/ComponentStats/UpdateSnapshot.

    Returns a dict with: adds, deletes, unchanged, reprocesses, errors,
    in_progress, finished.  All values default to 0.

    NOTE: these are CocoIndex's *component-level* totals — the sum across every
    mounted component, not a document count.  Use
    :func:`_document_level_counters` when the number is shown to a user or
    written to ``cocoindex_run_log``.
    """
    stats = _unwrap_stats(stats)
    if stats is None:
        return dict(_ZERO_COUNTERS)
    # UpdateStats has a .total (ComponentStats); ComponentStats is used directly.
    cs = getattr(stats, "total", stats)
    return {
        "adds":        getattr(cs, "num_adds", 0),
        "deletes":     getattr(cs, "num_deletes", 0),
        "unchanged":   getattr(cs, "num_unchanged", 0),
        "reprocesses": getattr(cs, "num_reprocesses", 0),
        "errors":      getattr(cs, "num_errors", 0),
        "in_progress": getattr(cs, "num_in_progress", 0),
        "finished":    getattr(cs, "num_finished", 0),
    }


def _document_level_counters(stats: Any) -> dict:
    """Return counters restricted to the per-document components.

    ``UpdateStats.total`` aggregates every component CocoIndex ran — the
    per-file worker *plus* ``parse_document`` (once per file) *plus*
    ``_embed_chunks_cached`` (once per file) *plus* ``extract_kg_*`` (once per
    **chunk**).  Ingesting one 5-chunk document can therefore report
    ``adds=8``, which reads as "8 documents" and is simply wrong.

    This filters ``by_component`` down to :data:`_DOC_LEVEL_COMPONENTS` so
    "adds" means documents added.  Falls back to the aggregate total when no
    document-level component is present (older CocoIndex builds, or a stats
    object that carries no per-component breakdown).
    """
    stats = _unwrap_stats(stats)
    if stats is None:
        return dict(_ZERO_COUNTERS)
    by_component = getattr(stats, "by_component", None) or {}
    if not by_component:
        return _extract_stats_counters(stats)

    totals = dict(_ZERO_COUNTERS)
    matched = False
    for name, cs in by_component.items():
        if not any(_doc in str(name) for _doc in _DOC_LEVEL_COMPONENTS):
            continue
        matched = True
        totals["adds"] += getattr(cs, "num_adds", 0)
        totals["deletes"] += getattr(cs, "num_deletes", 0)
        totals["unchanged"] += getattr(cs, "num_unchanged", 0)
        totals["reprocesses"] += getattr(cs, "num_reprocesses", 0)
        totals["errors"] += getattr(cs, "num_errors", 0)
        totals["in_progress"] += getattr(cs, "num_in_progress", 0)
        totals["finished"] += getattr(cs, "num_finished", 0)

    if not matched:
        return _extract_stats_counters(stats)
    return totals


def _component_summary_str(stats: Any) -> Optional[str]:
    """Return a compact per-component breakdown string for debug logging.

    Example: "process_document: +2 -0 =5 E0 | embed_chunks: +2 -0 =5 E0"
    """
    stats = _unwrap_stats(stats)
    if stats is None:
        return None
    try:
        by_component = getattr(stats, "by_component", None) or {}
        if not by_component:
            return None
        parts = []
        for name, cs in by_component.items():
            adds = getattr(cs, "num_adds", 0)
            dels = getattr(cs, "num_deletes", 0)
            unch = getattr(cs, "num_unchanged", 0)
            errs = getattr(cs, "num_errors", 0)
            parts.append(f"{name}: +{adds} -{dels} ={unch} E{errs}")
        return " | ".join(parts)
    except Exception:
        return None


def is_available() -> bool:
    """Return True if the ``cocoindex`` package is installed."""
    return _COCO_AVAILABLE
