"""adapters.vector.vector_store_adapter — VectorStoreAdapter ABC and factory."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class VectorStoreAdapter(ABC):
    """Unified interface for vector stores (LlamaIndex or LangChain backend)."""

    @abstractmethod
    def get_store(self):
        """Return the underlying store object."""

    @abstractmethod
    def delete(self, ref_doc_id: str) -> None:
        """Delete all vectors associated with *ref_doc_id*."""

    @abstractmethod
    def is_langchain(self) -> bool:
        """Return True if this adapter wraps a LangChain store."""


def build_vector_adapter(
    db_type,
    config: Dict[str, Any],
    llm_provider=None,
    llm_config: Optional[Dict[str, Any]] = None,
    app_config=None,
    vector_backend: Optional[str] = None,
) -> VectorStoreAdapter:
    """Create a :class:`VectorStoreAdapter` for *db_type*.

    Parameters
    ----------
    vector_backend:
        ``"llamaindex"`` (default) or ``"langchain"``.
    """
    backend = (vector_backend or getattr(app_config, "vector_backend", "llamaindex") or "llamaindex").lower()
    logger.info("Vector store backend: %s (db_type=%s)", backend, db_type)

    # No vector DB configured — nothing to build regardless of backend
    if str(db_type).lower() in ("none", ""):
        return None

    if backend == "langchain":
        from langchain.vector.adapters.factory import build_lc_vector_store
        # build_lc_vector_store returns the adapter instance directly (not just
        # the raw store) so each backend's delete() override is preserved.
        return build_lc_vector_store(db_type, config, app_config)

    from llamaindex.vector.vector_store_factory import create_vector_store
    return create_vector_store(db_type, config, llm_provider, llm_config, app_config)
