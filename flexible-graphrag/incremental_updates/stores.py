"""Where the incremental registry is kept: the datasource configs and the document state.

- ``postgres`` (default): the ``datasource_config`` and ``document_state`` tables at
  POSTGRES_INCREMENTAL_URL;
- ``openarch`` (INCREMENTAL_STATE_STORE=openarch): the OpenArch tree, with the OPENARCH_*
  settings: data sources under OPENARCH_DATASOURCES_PATH, document state on the source
  documents under OPENARCH_ROOT_PATH (see openarch/registry.py). No PostgreSQL needed.
- ``sqlite`` (INCREMENTAL_STATE_STORE=sqlite): the same tables in a SQLite file,
  SQLITE_INCREMENTAL_PATH (see sqlite_store.py). No database server needed.
"""
from __future__ import annotations

import os
from typing import Optional

KINDS = ("postgres", "openarch", "sqlite")
_LABELS = {"postgres": "PostgreSQL", "openarch": "OpenArch", "sqlite": "SQLite"}


def state_store_kind() -> str:
    """``postgres``, ``openarch`` or ``sqlite`` (INCREMENTAL_STATE_STORE)."""
    kind = os.getenv("INCREMENTAL_STATE_STORE", "postgres").strip().lower() or "postgres"
    if kind not in KINDS:
        raise ValueError(f"INCREMENTAL_STATE_STORE={kind!r}: use postgres, openarch or sqlite")
    return kind


def state_store_label() -> str:
    """The registry's store, for messages."""
    return _LABELS[state_store_kind()]


def state_store_configured() -> bool:
    """Whether the registry's store is set up: POSTGRES_INCREMENTAL_URL for PostgreSQL (OpenArch
    and SQLite have defaults for all their settings)."""
    return state_store_kind() != "postgres" or bool(os.getenv("POSTGRES_INCREMENTAL_URL"))


def _openarch_settings() -> dict:
    from config import openarch_settings
    return openarch_settings(None)


def new_config_manager(postgres_url: Optional[str] = None):
    """A ConfigManager on the configured store (call ``initialize()`` before use)."""
    kind = state_store_kind()
    if kind == "openarch":
        from openarch.registry import OpenArchConfigManager
        return OpenArchConfigManager(_openarch_settings())
    if kind == "sqlite":
        from incremental_updates.sqlite_store import SqliteConfigManager
        return SqliteConfigManager()
    from incremental_updates.config_manager import ConfigManager
    return ConfigManager(postgres_url or os.getenv("POSTGRES_INCREMENTAL_URL"))


def new_state_manager(postgres_url: Optional[str] = None):
    """A StateManager on the configured store (call ``initialize()`` before use)."""
    kind = state_store_kind()
    if kind == "openarch":
        from openarch.registry import OpenArchStateManager
        return OpenArchStateManager(_openarch_settings())
    if kind == "sqlite":
        from incremental_updates.sqlite_store import SqliteStateManager
        return SqliteStateManager()
    from incremental_updates.state_manager import StateManager
    return StateManager(postgres_url or os.getenv("POSTGRES_INCREMENTAL_URL"))
