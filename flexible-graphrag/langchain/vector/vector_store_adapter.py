"""langchain.vector.vector_store_adapter — LangChain vector store base adapter.

ABC lives in :mod:`adapters.vector.vector_store_adapter`.
Per-backend adapters live in :mod:`langchain.vector.adapters`.
LlamaIndex implementation lives in :mod:`llamaindex.vector.vector_store_factory`.
"""
from __future__ import annotations

import logging
from typing import Any

from adapters.vector.vector_store_adapter import VectorStoreAdapter

logger = logging.getLogger(__name__)


class LangChainVectorAdapter(VectorStoreAdapter):
    """Generic wrapper for a LangChain VectorStore (Qdrant, Chroma, ES, etc.).

    Subclasses specialise construction for specific backends
    (see :mod:`langchain.vector.adapters`).  This base class can also be
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
            logger.info("LangChain vector: deleted docs for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("LangChain vector delete failed for %s: %s", ref_doc_id, exc)

    def is_langchain(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Helpers for subclasses that need to auto-create their backing store
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_vector_size(vector_size: int, embedding) -> int:
        """Return a concrete vector dimension.

        Resolution order:
        1. *vector_size* argument (pre-computed by factory from app_config)
        2. ``embedding.embed_query("hello")`` (one API call — last resort)
        3. 1536 (safe default for OpenAI small)
        """
        if vector_size and vector_size > 0:
            return vector_size
        if embedding is not None:
            try:
                return len(embedding.embed_query("hello"))
            except Exception:
                pass
        return 1536


__all__ = ["LangChainVectorAdapter"]
