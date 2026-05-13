"""factories.py — thin facade over modular llamaindex sub-packages.

All heavy implementation now lives in:
  llamaindex/llm/llm_factory.py          (create_llm, _resolve_pydantic_program_mode)
  llamaindex/llm/embedding_factory.py    (create_embedding_model, get_embedding_dimension)
  llamaindex/vector/vector_store_factory.py (create_vector_store)
  llamaindex/search/search_store_factory.py (create_search_store, create_bm25_retriever)
  llamaindex/graph/graph_store_factory.py   (create_graph_store)

This file is kept for backward-compatibility only.
"""
from typing import Dict, Any
import logging
import os

from llama_index.core.storage.docstore import SimpleDocumentStore

from config import LLMProvider, VectorDBType, PropertyGraphType, GraphDBType, SearchDBType

# Re-export helpers so any code that imports directly from factories.py still works.
from llamaindex.llm.llm_factory import (
    create_llm as _create_llm,
    _resolve_pydantic_program_mode,
    _FireworksStreaming,
)
from llamaindex.llm.embedding_factory import (
    create_embedding_model as _create_embedding_model,
    get_embedding_dimension,
)
from llamaindex.graph.graph_store_factory import create_graph_store as _create_graph_store



logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM instances - delegates to llamaindex.llm.llm_factory."""

    @staticmethod
    def create_llm(provider, config):
        return _create_llm(provider, config)

    @staticmethod
    def create_embedding_model(provider, config, settings):
        return _create_embedding_model(provider, config, settings)


class DatabaseFactory:
    """Factory for creating database connections - delegates to adapter layer."""

    @staticmethod
    def create_vector_store(db_type, config, llm_provider=None, llm_config=None, app_config=None):
        from adapters.vector.vector_store_adapter import build_vector_adapter
        return build_vector_adapter(db_type, config, llm_provider, llm_config, app_config)

    @staticmethod
    def create_graph_store(db_type, config, schema_config=None, has_separate_vector_store=False, llm_provider=None, llm_config=None, app_config=None):
        return _create_graph_store(db_type, config, schema_config, has_separate_vector_store, llm_provider, llm_config, app_config)

    @staticmethod
    def create_search_store(db_type, config, vector_db_type=None, llm_provider=None, llm_config=None, app_config=None):
        from adapters.search.search_store_adapter import build_search_adapter
        return build_search_adapter(db_type, config, vector_db_type, llm_provider, llm_config, app_config)

    @staticmethod
    def create_bm25_retriever(docstore, config=None):
        from llamaindex.search.search_store_factory import create_bm25_retriever as _create_bm25_retriever
        return _create_bm25_retriever(docstore, config)
