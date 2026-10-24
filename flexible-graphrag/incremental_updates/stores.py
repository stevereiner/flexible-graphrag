"""Where the incremental registry is kept: the datasource configs and the document state.

- ``postgres`` (default): the ``datasource_config`` and ``document_state`` tables at
  POSTGRES_INCREMENTAL_URL;
- ``openarch`` (INCREMENTAL_STATE_STORE=openarch): the OpenArch tree, with the OPENARCH_*
  settings: data sources under OPENARCH_DATASOURCES_PATH, document state on the source
  documents under OPENARCH_ROOT_PATH (see openarch/registry.py). No PostgreSQL needed.
"""
from __future__ import annotations

import os
from typing import Optional


def state_store_kind() -> str:
    """``postgres`` or ``openarch`` (INCREMENTAL_STATE_STORE)."""
    kind = os.getenv("INCREMENTAL_STATE_STORE", "postgres").strip().lower() or "postgres"
    if kind not in ("postgres", "openarch"):
        raise ValueError(f"INCREMENTAL_STATE_STORE={kind!r}: use postgres or openarch")
    return kind


def state_store_label() -> str:
    """The registry's store, for messages."""
    return "OpenArch" if state_store_kind() == "openarch" else "PostgreSQL"


def state_store_configured() -> bool:
    """Whether the registry's store is set up: POSTGRES_INCREMENTAL_URL for PostgreSQL (OpenArch
    has defaults for all its settings)."""
    return state_store_kind() == "openarch" or bool(os.getenv("POSTGRES_INCREMENTAL_URL"))


def _openarch_settings() -> dict:
    from config import openarch_settings
    return openarch_settings(None)


def new_config_manager(postgres_url: Optional[str] = None):
    """A ConfigManager on the configured store (call ``initialize()`` before use)."""
    if state_store_kind() == "openarch":
        from openarch.registry import OpenArchConfigManager
        return OpenArchConfigManager(_openarch_settings())
    from incremental_updates.config_manager import ConfigManager
    return ConfigManager(postgres_url or os.getenv("POSTGRES_INCREMENTAL_URL"))


def new_state_manager(postgres_url: Optional[str] = None):
    """A StateManager on the configured store (call ``initialize()`` before use)."""
    if state_store_kind() == "openarch":
        from openarch.registry import OpenArchStateManager
        return OpenArchStateManager(_openarch_settings())
    from incremental_updates.state_manager import StateManager
    return StateManager(postgres_url or os.getenv("POSTGRES_INCREMENTAL_URL"))
