"""llamaindex.search.search_store_factory — LlamaIndex search store factory.

Provides :func:`create_search_store` and :func:`create_bm25_retriever`.
``factories.py`` delegates to this module so all existing call-sites continue to work.

Per-backend creation logic lives in :mod:`llamaindex.search.adapters`.
The ABC lives in :mod:`adapters.search.search_store_adapter`.
LangChain implementations (BM25SearchAdapter, LangChainSearchAdapter) live in
:mod:`langchain.search`.
"""
from __future__ import annotations

from typing import Dict, Any, Optional
import logging

from config import SearchDBType, VectorDBType, LLMProvider
from llamaindex.llm.embedding_factory import get_embedding_dimension
from adapters.search.search_store_adapter import SearchStoreAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LlamaIndex adapter
# ---------------------------------------------------------------------------

class LlamaIndexSearchAdapter(SearchStoreAdapter):
    """Base LlamaIndex search store adapter.

    Per-backend subclasses live in :mod:`llamaindex.search.adapters`.
    Each subclass builds its own store in ``__init__`` and calls
    ``super().__init__(store)``.

    ``__getattr__`` delegation makes this a transparent proxy so LlamaIndex
    APIs that access store-specific attributes work without unwrapping.
    """

    def __init__(self, store):
        self._store = store

    def get_store(self):
        return self._store

    def delete(self, ref_doc_id: str) -> None:
        if self._store is None:
            return
        try:
            self._store.delete(ref_doc_id)
            logger.info(f"Deleted search docs for ref_doc_id={ref_doc_id}")
        except Exception as exc:
            logger.warning(f"Search store delete failed for {ref_doc_id}: {exc}")

    def is_langchain(self) -> bool:
        return False

    def __getattr__(self, name: str):
        """Delegate unknown attribute access to the wrapped LlamaIndex store."""
        store = self.__dict__.get("_store")
        if store is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return getattr(store, name)


# ---------------------------------------------------------------------------
# LlamaIndex store creation (from factories.py — unchanged)
# ---------------------------------------------------------------------------

def create_search_store(
    db_type: SearchDBType,
    config: Dict[str, Any],
    vector_db_type: VectorDBType = None,
    llm_provider: LLMProvider = None,
    llm_config: Dict[str, Any] = None,
    app_config=None,
) -> SearchStoreAdapter:
    """Create and return a :class:`LlamaIndexSearchAdapter` subclass for *db_type*."""
    from llamaindex.search.adapters.factory import create_search_store as _create

    embedding_kind = getattr(app_config, "embedding_kind", None) if app_config else None
    embedding_model = getattr(app_config, "embedding_model", None) if app_config else None
    embedding_dimension = getattr(app_config, "embedding_dimension", None) if app_config else None
    embed_dim = get_embedding_dimension(
        embedding_kind=embedding_kind,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
    )
    logger.info(f"Detected embedding dimension for search store: {embed_dim} (kind: {embedding_kind}, model: {embedding_model})")
    return _create(db_type, config, embed_dim)


def create_bm25_retriever(docstore, config: Dict[str, Any] = None):
    """Create a LlamaIndex BM25 retriever from *docstore*.

    Instantiates :class:`~llamaindex.search.adapters.bm25_adapter.LlamaIndexBM25SearchAdapter`
    and calls :meth:`~LlamaIndexBM25SearchAdapter.build_retriever` on it.
    """
    from llamaindex.search.adapters.bm25_adapter import LlamaIndexBM25SearchAdapter
    adapter = LlamaIndexBM25SearchAdapter(config)
    return adapter.build_retriever(docstore)


def build_search_adapter(
    db_type: SearchDBType,
    config: Dict[str, Any],
    vector_db_type: VectorDBType = None,
    llm_provider: LLMProvider = None,
    llm_config: Dict[str, Any] = None,
    app_config=None,
) -> SearchStoreAdapter:
    """Convenience wrapper delegating to :func:`adapters.search.build_search_adapter`."""
    from adapters.search.search_store_adapter import build_search_adapter as _build
    return _build(db_type, config, vector_db_type, llm_provider, llm_config, app_config)
