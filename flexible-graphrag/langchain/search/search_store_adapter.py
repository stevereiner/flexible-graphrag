"""langchain.search.search_store_adapter — LangChain search store base adapter.

ABC lives in :mod:`adapters.search.search_store_adapter`.
Per-backend adapters live in :mod:`langchain.search.adapters`.
LlamaIndex implementation lives in :mod:`llamaindex.search.search_store_factory`.
"""
from __future__ import annotations

import logging
from typing import Any

from adapters.search.search_store_adapter import SearchStoreAdapter

logger = logging.getLogger(__name__)


class LangChainSearchAdapter(SearchStoreAdapter):
    """Generic wrapper for a LangChain search store (Elasticsearch, OpenSearch, …).

    Subclasses specialise construction for specific backends
    (see :mod:`langchain.search.adapters`).  This base class can also be
    used directly when a pre-built LangChain store object is available.
    """

    def __init__(self, store: Any, delete_key: str = "ref_doc_id"):
        self._store = store
        self._delete_key = delete_key

    def get_store(self) -> Any:
        return self._store

    def delete(self, ref_doc_id: str) -> None:
        if self._store is None:
            return
        try:
            if hasattr(self._store, "delete"):
                self._store.delete(filter={self._delete_key: ref_doc_id})
            logger.info("LangChain search: deleted docs for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("LangChain search delete failed for %s: %s", ref_doc_id, exc)

    def is_langchain(self) -> bool:
        return True


__all__ = ["LangChainSearchAdapter"]
