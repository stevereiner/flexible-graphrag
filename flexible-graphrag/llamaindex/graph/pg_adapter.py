"""llamaindex.graph.pg_adapter — LlamaIndexPGAdapter."""
from __future__ import annotations

from typing import Any, List, Optional
import logging

from adapters.graph.pg_store_adapter import PropertyGraphStoreAdapter

logger = logging.getLogger(__name__)


class LlamaIndexPGAdapter(PropertyGraphStoreAdapter):
    """Wraps a LlamaIndex ``PropertyGraphStore`` for unified adapter usage.

    ``__getattr__`` delegation makes this a transparent proxy — LlamaIndex APIs
    that access store-specific properties (e.g. ``supports_vector_queries``,
    ``add``, ``upsert_nodes``) work without explicitly unwrapping the adapter.
    """

    def __init__(self, store):
        self._store = store

    def add_nodes(self, nodes: List, triplets: Optional[List] = None) -> None:
        """LlamaIndex ingestion is handled by the pipeline — this is a no-op here."""
        logger.debug("LlamaIndexPGAdapter.add_nodes: ingestion handled by LlamaIndex pipeline")

    def delete(self, ref_doc_id: str) -> None:
        if self._store is None:
            return
        try:
            self._store.delete(ref_doc_id)
            logger.info(f"Deleted graph nodes for ref_doc_id={ref_doc_id}")
        except Exception as exc:
            logger.warning(f"PG store delete failed for {ref_doc_id}: {exc}")

    def get_li_store(self):
        return self._store

    def get_lc_graph(self):
        return None

    def is_langchain(self) -> bool:
        return False

    def __getattr__(self, name: str):
        """Delegate unknown attribute access to the wrapped LlamaIndex store."""
        store = self.__dict__.get("_store")
        if store is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return getattr(store, name)
