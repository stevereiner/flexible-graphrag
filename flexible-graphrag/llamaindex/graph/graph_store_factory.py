"""LlamaIndex property graph store factory — extracted from factories.py.

Provides :func:`create_graph_store` for all :class:`PropertyGraphType` values.
``factories.py`` delegates to this module so all existing call-sites continue to work.

Per-backend creation logic lives in :mod:`llamaindex.graph.adapters`.
"""
from __future__ import annotations

from typing import Dict, Any
import logging

from config import PropertyGraphType, LLMProvider

logger = logging.getLogger(__name__)


def create_graph_store(
    db_type: PropertyGraphType,
    config: Dict[str, Any],
    schema_config: Dict[str, Any] = None,
    has_separate_vector_store: bool = False,
    llm_provider: LLMProvider = None,
    llm_config: Dict[str, Any] = None,
    app_config=None,
):
    """Create a LlamaIndex property graph store.

    Matches the original ``DatabaseFactory.create_graph_store`` signature.
    """
    from llamaindex.graph.adapters.factory import create_graph_store as _create
    return _create(
        db_type, config,
        schema_config=schema_config,
        has_separate_vector_store=has_separate_vector_store,
        llm_provider=llm_provider,
        llm_config=llm_config,
        app_config=app_config,
    )
