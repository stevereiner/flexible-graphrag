"""Shared helpers for the Flexible GraphRAG Langflow components.

Design (per project owner):
- Every node delegates to the REAL flexible-graphrag machinery — the same the FastAPI
  backend uses: the `ingest/*` pipeline functions + `retriever_setup` + the store/adapter
  layer (full LangChain + LlamaIndex support). NOT the legacy `components/` package.
- The ingestion nodes share ONE live "system" object (HybridSearchSystem — the full
  LangChain + LlamaIndex adapter layer, same as backend.py). Because a
  live system (DB connections, indexes, LLM) is not serializable, it is NOT put in the
  Data that flows along edges. Instead the Data Source node registers the system + run
  state in a process-level cache and threads only a short string run-key along the edges.
- Config comes from the backend `.env` (defaults); the Data Source node may override
  select settings (which DB, KG on/off) — applied as env vars before Settings() so they
  parse exactly like the backend.
- Query nodes (Hybrid Search, AI Query) are independent: each builds its own system and
  reconnects to the persistent stores.
"""

import os
import sys
import uuid

# Neutralise nest_asyncio.apply on Python 3.14+ (mirrors main.py) — the langflow process
# never runs main.py, so without this the KG extraction (and other async LlamaIndex paths)
# fail with "unknown async library, or not in async context". LlamaIndex (async_utils,
# elasticsearch store) calls nest_asyncio.apply() unconditionally; on 3.14 that breaks the
# event loop the OpenAI/httpx async client needs, so sniffio can't detect the loop. Patching
# the module attribute makes those calls a no-op (same approach the FastAPI backend uses).
if sys.version_info >= (3, 14):
    try:
        import nest_asyncio as _nest_asyncio_early
        _nest_asyncio_early.apply = lambda *a, **kw: None
    except ImportError:
        pass

# Make the flexible-graphrag package importable (editable install also covers this).
FG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if FG_DIR not in sys.path:
    sys.path.insert(0, FG_DIR)


def _patch_ssl_for_proxy() -> None:
    """Apply the backend's SSL fix inside the langflow process.

    The FastAPI backend runs main.py:_patch_ssl_context() at startup so HTTPS calls
    (OpenAI/Anthropic/embeddings) work behind a corporate SSL-inspecting proxy. langflow
    never runs main.py, so without this the LLM/embedding calls fail with
    APIConnectionError and the chunk/embed pipeline hangs on retries. Idempotent.
    """
    # Shared implementation — see flexible-graphrag/ssl_compat.py.  It is
    # idempotent, so calling it from several entry points is safe.
    try:
        from ssl_compat import patch_ssl_context as _patch  # noqa: PLC0415

        _patch()
    except Exception:
        pass


_patch_ssl_for_proxy()


# flexible-graphrag module loggers — routed to a dedicated detail file.
_FG_LOG_MODULES = {
    "config", "schema_manager", "ingest", "process", "stores", "adapters",
    "hybrid_system", "retriever_setup",
    "query_engine", "sources", "rdf", "llamaindex", "langchain", "observability",
    "incremental_system", "factories", "langflow_components", "backend",
}


def _setup_fg_logging() -> None:
    """Route flexible-graphrag's own logs to a dedicated detail file, separate from langflow.

    langflow's console/log keep their own --log-level (so you can run them quiet), while the
    full flexible-graphrag detail — including the DEBUG ontology/schema-loading lines that an
    INFO console drops — goes to flexible-graphrag/fg-detail.log. Set FG_LOG_LEVEL to change the
    file's level (default DEBUG). Idempotent.

    We set the flexible-graphrag module loggers (not the root) to the level: their records
    propagate to the handler below regardless of the root level, so this does NOT make
    langflow's console verbose.
    """
    try:
        import logging
        from logging.handlers import RotatingFileHandler

        root = logging.getLogger()
        if any(getattr(h, "_fg_detail", False) for h in root.handlers):
            return

        level = getattr(logging, (os.getenv("FG_LOG_LEVEL") or "DEBUG").upper(), logging.DEBUG)
        path = os.path.join(FG_DIR, "fg-detail.log")
        handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=2, encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler.addFilter(lambda r: r.name.split(".")[0] in _FG_LOG_MODULES)
        handler._fg_detail = True
        root.addHandler(handler)

        for name in _FG_LOG_MODULES:
            logging.getLogger(name).setLevel(level)
    except Exception:
        pass


_setup_fg_logging()

RUN_KEY = "_fg_run"

# Process-level cache of in-flight ingestion runs: run_key -> dict with the live system
# and the pipeline state (file_paths, documents, nodes, nodes_kg_extracted).
_RUNS: dict = {}
_MAX_RUNS = 8


# ------------------------------------------------------------------ config / system

def default_env_path() -> str:
    return os.path.join(FG_DIR, ".env")


def build_settings(config_path: str = "", overrides: dict | None = None):
    """Load the backend .env (defaults) + apply per-node overrides, then build Settings."""
    from dotenv import load_dotenv

    path = (config_path or "").strip() or default_env_path()
    if path and os.path.exists(path):
        # override=True so edits to .env (e.g. switching RDF_GRAPH_DB) are picked up on the
        # next node run without restarting langflow. UI overrides are applied AFTER this and
        # still win (set into os.environ below).
        load_dotenv(path, override=True)

    if overrides:
        for key, value in overrides.items():
            if value is None:
                continue
            sval = str(value).strip()
            if sval:
                os.environ[key] = sval

    # NLTK_DATA when not set, as in main.py
    from nltk_compat import use_plain_nltk_data  # noqa: PLC0415
    use_plain_nltk_data()

    from config import Settings
    return Settings()


_rdf_ontology_initialized = False


def _init_rdf_ontology(settings, system) -> None:
    """Replicate main.py's startup RDF/ontology init (which langflow never runs).

    Without this the ontology is never loaded, so langflow's KG extraction doesn't use it
    (and the ontology-loading logs never appear). Gated like the backend and done once per
    process. Loads the ontology into the global ontology_manager that the ingest path reads.
    """
    global _rdf_ontology_initialized
    if _rdf_ontology_initialized:
        return
    import logging
    _log = logging.getLogger("config")
    use_onto = getattr(settings, "use_ontology", False)
    rdf_stores = getattr(settings, "rdf_enabled_stores", None)
    _log.info(
        "RDF/Ontology init: use_ontology=%s, rdf_graph_db=%s, ontology_paths=%s, "
        "ontology_dir=%s, ontology_path=%s",
        use_onto, getattr(settings, "rdf_graph_db", None),
        getattr(settings, "ontology_paths", None), getattr(settings, "ontology_dir", None),
        getattr(settings, "ontology_path", None),
    )
    try:
        if use_onto or rdf_stores:
            from rdf.api_rdf_enhancements import initialize_rdf_system
            initialize_rdf_system(settings, getattr(system, "graph_index", None))
            _rdf_ontology_initialized = True
        else:
            _log.info("RDF/Ontology init skipped (use_ontology is false and no RDF stores enabled)")
    except Exception:
        import logging
        logging.getLogger("rdf").warning(
            "Failed to initialize RDF/Ontology system in langflow", exc_info=True
        )


def build_system(settings):
    """Create the shared system the same way backend.py does — HybridSearchSystem, the full
    LangChain + LlamaIndex adapter layer."""
    from hybrid_system import HybridSearchSystem
    system = HybridSearchSystem.from_settings(settings)
    _init_rdf_ontology(settings, system)
    return system


# ------------------------------------------------------------------ warm query system

# The independent query nodes (Hybrid Search, AI Query) otherwise call build_system() on
# EVERY run — a full HybridSearchSystem construction: LLM client + embedding-model init +
# store connections + fusion-retriever assembly. The FastAPI backend builds its system once
# and reuses it warm (cached `system` property), so flow-mode search/query was noticeably
# slower than direct mode. Cache a warm system per resolved .env path; rebuild only when that
# .env file changes (so config edits are still picked up without a langflow restart), or on
# an event-loop-affinity error (a cached async store client bound to a stale loop).
_QUERY_SYSTEM_CACHE: dict = {}  # env_path -> (mtime, system)


def get_query_system(config_path: str = "", force: bool = False):
    """Warm, cached system for the query nodes; (re)build on .env change or force=True."""
    path = (config_path or "").strip() or default_env_path()
    try:
        mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
    except OSError:
        mtime = 0.0
    cached = _QUERY_SYSTEM_CACHE.get(path)
    if not force and cached is not None and cached[0] == mtime:
        return cached[1]
    settings = build_settings(config_path=config_path)
    system = build_system(settings)
    _QUERY_SYSTEM_CACHE[path] = (mtime, system)
    return system


async def run_with_query_system(config_path, run):
    """Run ``await run(system)`` with the warm cached query system. If a cached system's async
    store client is bound to a closed/different event loop, rebuild once and retry — so the
    cache speeds up the common case without ever introducing loop-affinity failures."""
    try:
        return await run(get_query_system(config_path))
    except RuntimeError as e:
        if "loop" not in str(e).lower():
            raise
        return await run(get_query_system(config_path, force=True))


def get_loop():
    from ingest._helpers import _get_loop
    return _get_loop()


# ------------------------------------------------------------------ run cache

def start_run(system, **fields) -> str:
    """Register a new ingestion run holding the live system; return its run-key."""
    # An ingestion is starting — invalidate the warm query-system cache so the next search /
    # AI query rebuilds against the indexes this run creates/updates. Without this, a query
    # system built BEFORE the indexes existed (e.g. pre-warm on a fresh DB, or a search issued
    # before the first ingest) would keep serving stale / missing index handles. Cheap: the
    # next query just pays one system rebuild.
    _QUERY_SYSTEM_CACHE.clear()

    key = uuid.uuid4().hex
    _RUNS[key] = {"system": system, **fields}
    # bound memory: drop oldest runs
    if len(_RUNS) > _MAX_RUNS:
        for old in list(_RUNS.keys())[:-_MAX_RUNS]:
            _RUNS.pop(old, None)
    return key


def run_graphs(run: dict):
    """Which graphs this run builds (graph_flags.GraphFlags): enabled_graph / enabled_rdf from the
    trigger payload, else the older skip_graph, else DEFAULT_ENABLED_GRAPH / _RDF."""
    from graph_flags import GraphFlags
    system = run.get("system")
    return GraphFlags.resolve(run.get("enabled_graph"), run.get("enabled_rdf"), run.get("skip_graph"),
                              config=getattr(system, "config", None))


def get_run(value) -> dict:
    """Resolve the run dict from an inbound Data (or list) carrying the run-key."""
    for item in (value if isinstance(value, list) else [value]):
        d = getattr(item, "data", None)
        if isinstance(d, dict) and d.get(RUN_KEY):
            entry = _RUNS.get(d[RUN_KEY])
            if entry is None:
                raise ValueError(
                    "Ingestion run expired — re-run the flow starting from the Data Source node."
                )
            entry["_key"] = d[RUN_KEY]
            return entry
    raise ValueError("No ingestion run on input — connect this node to the Data Source chain.")


def make_payload(run_key: str, stage: str = "", **stats):
    """Data that flows along edges: only the serializable run-key + small stats."""
    from langflow.schema import Data
    data = {RUN_KEY: run_key, "stage": stage}
    data.update(stats)
    return Data(data=data)


def has_ingest_chunks(run) -> bool:
    """True when the run has chunks to store — LlamaIndex nodes (``run['nodes']``) OR the
    LangChain chunk pipeline's stashed LC documents (``system._last_lc_chunks``).

    The all-LangChain backend produces 0 LI nodes (chunks are LC documents stashed on the
    system and written via ``add_documents``), so a bare ``not nodes`` check wrongly bails on
    it. The ``update_vector``/``update_search``/``update_pg_graph`` functions already route
    LC via ``is_langchain()`` + ``_last_lc_chunks``, so the store nodes just need to not bail."""
    if run.get("nodes"):
        return True
    return bool(getattr(run.get("system"), "_last_lc_chunks", None))


def ingest_chunk_count(run) -> int:
    """How many chunks are being stored — LlamaIndex nodes if present, else the stashed
    LangChain chunks (``system._last_lc_chunks``). Use for status/labels so the all-LC backend
    doesn't report 0 (its chunks are LC docs, not LI nodes)."""
    nodes = run.get("nodes")
    if nodes:
        return len(nodes)
    lc = getattr(run.get("system"), "_last_lc_chunks", None)
    return len(lc) if lc else 0
