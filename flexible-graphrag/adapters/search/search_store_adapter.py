"""adapters.search.search_store_adapter — SearchStoreAdapter ABC and factory."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SearchStoreAdapter(ABC):
    """Unified interface for full-text / BM25 search stores."""

    @abstractmethod
    def get_store(self):
        """Return the underlying store object."""

    @abstractmethod
    def delete(self, ref_doc_id: str) -> None:
        """Delete all search documents associated with *ref_doc_id*."""

    @abstractmethod
    def is_langchain(self) -> bool:
        """Return True if this adapter wraps a LangChain store."""


def build_search_adapter(
    db_type,
    config: Dict[str, Any],
    vector_db_type=None,
    llm_provider=None,
    llm_config: Optional[Dict[str, Any]] = None,
    app_config=None,
) -> SearchStoreAdapter:
    """Create a :class:`SearchStoreAdapter` for *db_type*.

    When ``app_config.search_backend == 'langchain'`` the entire request is
    delegated to :func:`langchain.search.adapters.factory.build_langchain_search_store`
    which handles BM25, Elasticsearch, and OpenSearch via their LangChain
    implementations.  All other backends use the LlamaIndex path.
    """
    from config import SearchDBType

    search_backend = getattr(app_config, "search_backend", "llamaindex") if app_config else "llamaindex"
    logger.info("Search store backend: %s (db_type=%s)", search_backend, db_type)

    # No search DB configured — nothing to build regardless of backend
    if str(db_type).lower() in ("none", ""):
        return None

    if search_backend == "langchain":
        from langchain.search.adapters.factory import build_langchain_search_store
        return build_langchain_search_store(db_type, config, app_config)

    from llamaindex.search.search_store_factory import create_search_store
    return create_search_store(db_type, config, vector_db_type, llm_provider, llm_config, app_config)
