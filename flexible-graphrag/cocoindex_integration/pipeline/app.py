"""flexible-graphrag as a CocoIndex pipeline app.

This module is the **thin entry point** for the CocoIndex pipeline.  All
implementation has been split into dedicated submodules:

* :mod:`state`       — module-level singletons and runtime flags
* :mod:`providers`   — ``TargetStateProvider`` registration helpers
* :mod:`selectors`   — target / source pickers and native root-mount helpers
* :mod:`run`         — ``process_document`` ``@coco.fn`` + ``_run_pipeline``
* :mod:`native_apps`  — native CocoIndex source apps (localfs, S3, Azure Blob, Google Drive)
* :mod:`flexible_app`— flexible-source app and multi-source bridge helpers

How this module is invoked
--------------------------
Three entry points — all require ``PIPELINE_BACKEND=cocoindex`` in ``.env``:

1. **Full UI app** (recommended)::

       uv run start.py
       # CocoIndexBridge replaces HybridSystem.
       #
       # DATA_SOURCE (primary .env source):
       #   unset            → default ``filesystem``; primary app starts immediately
       #   filesystem|s3|…  → that primary source starts immediately (no
       #                      datasource_config row required for it)
       #   "" or none       → no primary .env source; bridge stays lazy until the
       #                      UI Data Source tab (or REST/MCP) calls ingest —
       #                      apps are built per config via build_app_for_config()
       #
       # Additional sources from the UI Data Source tab still auto-start when
       # present in datasource_config (on bridge startup / first ingest).

2. **Standalone — ``cocoindex update``** (CocoIndex CLI; no UI)::

       cd flexible-graphrag
       cocoindex update cocoindex_integration/pipeline/app.py
       #
       # Reads DATA_SOURCE / SOURCE_BACKEND / VECTOR_DB / etc. from .env.
       # Use a real DATA_SOURCE (unset → filesystem).  ``""`` / ``none`` is for
       # UI-driven ingest only (no primary app for ``cocoindex update``).
       #
       # Options apply only to ``cocoindex update`` (not to ``python -m`` below):
       #   https://cocoindex.io/docs/cli/#update
       #   -L, --live           live mode — keep processing after initial catch-up
       #   --full-reprocess     reprocess everything; invalidate caches
       #   --reset              drop existing setup first (like ``cocoindex drop``)
       #   --preview            plan target actions without applying them
       #   -f, --force          skip confirmation prompts
       #   -q, --quiet          suppress stats / stdout noise
       # Global: --env-file PATH, --app-dir PATH
       # APP_TARGET: path/to/app.py | module | path/to/app.py:AppName

3. **Standalone — ``python -m``** (same ``.env``; no CocoIndex CLI flags)::

       python -m cocoindex_integration.pipeline.app [optional_watch_dir]
       # Only optional positional watch dir for filesystem; then ``coco.start_blocking()``.
       # ``--live`` / ``--full-reprocess`` / ``--reset`` / etc. are ``cocoindex update`` only.

Config that drives target selection
-------------------------------------
All config comes from flexible-graphrag's ``.env`` — no extra flags needed.

  PG_GRAPH_DB     Property graph database (15 options):
                    neo4j | falkordb | surrealdb | arcadedb | memgraph |
                    nebula | hugegraph | arangodb | apache_age | tigergraph |
                    ladybug | cosmos_gremlin | spanner | neptune |
                    neptune_analytics | none

  RDF_GRAPH_DB    RDF triple store (4 options, default: none):
                    fuseki | graphdb | oxigraph | neptune_rdf | none

  VECTOR_DB       Vector store for chunk embeddings (10 options):
                    qdrant | neo4j | elasticsearch | opensearch | chroma |
                    milvus | weaviate | pinecone | postgres | lancedb | none

  SEARCH_DB       Full-text / BM25 search index:
                    elasticsearch | opensearch | bm25 | none

  GRAPH_BACKEND   llamaindex | langchain | cocoindex  (default: llamaindex)
  VECTOR_BACKEND  llamaindex | langchain | cocoindex  (default: llamaindex)

  DATA_SOURCE     Primary source from .env (14 options):
                    unset → filesystem (default)
                    filesystem | s3 | gcs | azure_blob | onedrive |
                    sharepoint | google_drive | alfresco | nuxeo | box |
                    cmis | web | wikipedia | youtube
                    "" or none → no primary source; UI Data Source tab / REST / MCP
  SOURCE_BACKEND  flexible | cocoindex  (default: flexible)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

import cocoindex as coco  # noqa: E402

# Apply sniffio / anyio / httpcore patches before any pipeline code runs.
# In UI mode main.py applies these; in CLI mode (cocoindex update app.py)
# main.py is never imported, so we apply them here instead.
from cocoindex_integration._compat import apply_async_patches, setup_cli_logging  # noqa: E402
apply_async_patches()

# Set up file + console logging when running under `cocoindex update app.py`
# (no main.py → no log file by default).  Guarded: if main.py already added
# a FileHandler we do nothing, so there are no duplicate log files in UI mode.
if not any(isinstance(_h, logging.FileHandler) for _h in logging.getLogger().handlers):
    _log_file = setup_cli_logging("flexible-graphrag-coco")
    # Print so it shows up in the cocoindex update terminal banner.
    print(f"  Log file         : {_log_file}", flush=True)

from cocoindex_integration.pipeline.env_config import load_config_from_env  # noqa: E402

# ── Re-export the public surface from submodules ───────────────────────────
from cocoindex_integration.pipeline.run import (  # noqa: F401
    process_document,
    set_progress_hook,
    set_runtime_skip_graph,
    set_runtime_graphs,
)
# Re-exported so callers that hold the *module* (see the note below) can read the
# native-PG write flag without reaching into pipeline.state directly.
from cocoindex_integration.pipeline.state import (  # noqa: F401
    native_pg_write_skipped,
    reset_native_pg_write_skipped,
)
# Per-file workers for the native CocoIndex connectors.  There is a single
# app_main (flexible_app_main); it dispatches native sources through
# native_apps.NATIVE_READERS.  These workers are re-exported so CocoIndex can
# resolve the @coco.fn components referenced by mount_each.
from cocoindex_integration.pipeline.native_apps import (  # noqa: F401
    NATIVE_READERS,
    process_localfs_file,
    process_s3_file,
    process_azure_blob_file,
    process_google_drive_file,
)
from process.document_processor import format_parser_display_name  # noqa: E402

from cocoindex_integration.pipeline.flexible_app import (  # noqa: F401
    flexible_app_main,
    process_flexible_item,
    process_flexible_file,
    build_flexible_source_app,
    build_app_for_config,
    build_apps_for_all_sources,
    _build_default_app,
    _build_source_config_from_env,
    _resolve_pipeline_config,
    log_pipeline_config,
    _SOURCE_ENV_PREFIX,
)

# ─────────────────────────────────────────────────────────────────────────────
# Module-level ``app`` — required for ``cocoindex update app.py``
# ─────────────────────────────────────────────────────────────────────────────
# Build once on import when a primary .env source is configured.
# Skip when DATA_SOURCE is explicitly "" or "none" — bridge defers to UI sources
# and builds per-source apps via build_app_for_config() on first ingest.
# When this file is run as ``__main__`` the CLI block below builds it instead —
# so an optional directory argument can be honoured without double registration.


def _primary_data_source_configured() -> bool:
    if "DATA_SOURCE" not in os.environ:
        return True  # unset → default filesystem primary app
    ds = os.getenv("DATA_SOURCE", "").strip().lower()
    return ds not in ("", "none")


app: Any = (
    _build_default_app()
    if __name__ != "__main__" and _primary_data_source_configured()
    else None
)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point  (python -m cocoindex_integration.pipeline.app)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _cfg_raw = load_config_from_env()
    _cfg_resolved = _resolve_pipeline_config(_cfg_raw)
    data_source = _cfg_resolved.get("data_source", "filesystem")
    _source_backend = str(_cfg_resolved.get("source_backend", "flexible")).lower()
    _force_flexible = _source_backend == "flexible"

    # Emit the same structured startup log as the regular pipeline.
    log_pipeline_config(_cfg_raw, _cfg_resolved)

    # Also print a quick summary to stdout for ``cocoindex update`` invocations.
    def _fmt(key: str, d: str = "llamaindex") -> str:
        r = str(_cfg_raw.get(key, d)).lower()
        a = str(_cfg_resolved.get(key, d)).lower()
        return r if r == a else f"{r} configured, used {a}"

    print("flexible-graphrag CocoIndex pipeline with CocoIndex and Flexible (LlamaIndex / LangChain) stages supported")
    print(f"  PIPELINE_BACKEND : cocoindex")
    print(f"  DATA_SOURCE      : {data_source}")
    print(f"  SOURCE_BACKEND   : {_fmt('source_backend', 'flexible')}")
    print(f"  DOCUMENT_PARSER  : {format_parser_display_name(_cfg_resolved.get('parser_type', 'docling'))}")
    print(f"  CHUNKER_BACKEND  : {_fmt('chunker_backend')}")
    print(f"  KG_EXTRACTOR     : {_fmt('kg_extractor_backend')}")
    print(f"  GRAPH_BACKEND    : {_fmt('graph_backend')}")
    print(f"  VECTOR_BACKEND   : {_fmt('vector_backend')}")
    print(f"  PG_GRAPH_DB      : {_cfg_resolved['pg_graph_db']}")
    print(f"  RDF_GRAPH_DB     : {_cfg_resolved['rdf_graph_db']}")
    print(f"  VECTOR_DB        : {_cfg_resolved['vector_db']}")
    print(f"  SEARCH_DB        : {_cfg_resolved['search_db']}")
    print(f"  LLM_PROVIDER     : {_cfg_resolved['llm_provider']}")
    print(f"  EMBEDDING_KIND   : {_cfg_resolved.get('embedding_kind', 'openai')}")
    print(f"  USE_ONTOLOGY     : {_cfg_resolved['use_ontology']}")

    cli_source_dir = sys.argv[1] if len(sys.argv) > 1 else None
    app = _build_default_app(cli_source_dir)
    # One app_main for every source (flexible_app_main); the source_backend
    # decides whether it lists via a native CocoIndex connector or a flexible
    # data source.
    _native_conn = (not _force_flexible) and data_source in NATIVE_READERS
    _app_name = getattr(app, "_name", "GraphRAG")
    if data_source in ("filesystem", "localfs"):
        _dir = cli_source_dir or os.getenv("WATCH_DIR", "./cocoindex-docs")
        _via = "native localfs" if _native_conn else "flexible"
        print(f"  App            : {_app_name} (dir={_dir}, {_via})")
    else:
        _via = "native CocoIndex connector" if _native_conn else "flexible"
        print(f"  App            : {_app_name} (source={data_source}, {_via})")

    coco.start_blocking()  # type: ignore[attr-defined]
