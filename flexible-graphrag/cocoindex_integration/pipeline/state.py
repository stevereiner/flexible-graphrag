"""Shared mutable singletons for the CocoIndex pipeline.

All module-level globals that were in ``app.py`` live here.  Other pipeline
modules import this module and access/mutate attributes directly:

    from cocoindex_integration.pipeline import state as _state

    # read
    coll = _state._root_qdrant_coll

    # write  (never use ``global``)
    _state._root_qdrant_coll = new_handle

This gives a single source of truth without the ``global`` keyword — the
module-object reference is stable, so every attribute access reflects the
current value.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Target singletons — built once per ``cocoindex update`` run.
# Using singletons avoids re-loading LlamaIndex/PyTorch (~27 s) on every file.
# ─────────────────────────────────────────────────────────────────────────────
_vector_target_singleton: Optional[Any] = None
_pg_target_singleton: Optional[Any] = None
_rdf_target_singleton: Optional[Any] = None
_search_target_singleton: Optional[Any] = None

# CocoIndex TargetStateProviders — registered once per process.
_vector_provider: Optional[Any] = None
_pg_provider: Optional[Any] = None
_search_provider: Optional[Any] = None
_rdf_provider: Optional[Any] = None

# ─────────────────────────────────────────────────────────────────────────────
# Native target root handles (must be mounted at app_main / root scope so
# CocoIndex can reconcile per-file records across update cycles).
# ─────────────────────────────────────────────────────────────────────────────

# Qdrant
_root_qdrant_coll: Optional[Any] = None

# Neo4j (chunk table, entity table, direct Bolt driver)
_root_neo4j_chunk_tbl: Optional[Any] = None
_root_neo4j_entity_tbl: Optional[Any] = None
_root_neo4j_driver: Optional[Any] = None

# FalkorDB (same lifecycle as Neo4j)
_root_falkordb_chunk_tbl: Optional[Any] = None
_root_falkordb_entity_tbl: Optional[Any] = None
_root_falkordb_driver: Optional[Any] = None

# LanceDB
_root_lance_table: Optional[Any] = None

# Postgres / pgvector
_root_postgres_table: Optional[Any] = None

# SurrealDB (chunk table, entity table, direct client)
_root_surrealdb_chunk_tbl: Optional[Any] = None
_root_surrealdb_entity_tbl: Optional[Any] = None
_root_surrealdb_client: Optional[Any] = None

# ─────────────────────────────────────────────────────────────────────────────
# Runtime flags — set by CocoIndexBridge before each update() cycle.
# ─────────────────────────────────────────────────────────────────────────────

# True when a native PG graph write was skipped (tables unavailable at
# declaration time).  Bridge reads this to choose the UI completion message.
_native_pg_write_skipped: bool = False

# None  = use cfg["enable_knowledge_graph"] (default)
# True  = force KG extraction OFF for every file in this update() call
# False = force KG extraction ON
_runtime_skip_graph: "bool | None" = None
# Which graphs the next update() cycle builds (graph_flags.GraphFlags), set per request by the
# bridge; None = enable_knowledge_graph / skip_graph from cfg_json and the defaults
_runtime_graphs = None

# Per-file / per-stage progress hook — installed by bridge for one update cycle.
_progress_hook: "Optional[Callable[[dict], None]]" = None


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions for the native-PG write-skipped flag
# ─────────────────────────────────────────────────────────────────────────────

def native_pg_write_skipped() -> bool:
    """Return whether the last pipeline run skipped a native PG graph write."""
    return _native_pg_write_skipped


def reset_native_pg_write_skipped() -> None:
    """Clear the PG write-skipped flag (call at the start of each file)."""
    global _native_pg_write_skipped
    _native_pg_write_skipped = False
