"""LlamaIndex BM25 search adapter.

Uses a cumulative in-memory docstore so documents from all ingestion batches
are included in every BM25 search — not just the most recently ingested batch.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
import logging
import os

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import QueryBundle, NodeWithScore

from llamaindex.search.search_store_factory import LlamaIndexSearchAdapter

logger = logging.getLogger(__name__)


class LlamaIndexBM25SearchAdapter(LlamaIndexSearchAdapter, BaseRetriever):
    """LlamaIndex search adapter backed by BM25.

    Maintains a cumulative :class:`SimpleDocumentStore` internally so that
    documents from every ingest call accumulate — unlike the old pattern of
    rebuilding the retriever from only the last batch.  This is important when
    ``VECTOR_DB=none`` (no vector index to fall back on for the docstore).

    Lifecycle
    ---------
    - Created once at startup by :mod:`stores.index_manager`.
    - :meth:`add_nodes` called by :mod:`ingest.update_search` after each batch.
    - :meth:`get_retriever` rebuilds ``BM25Retriever`` lazily whenever the
      document list changes.
    - :meth:`delete` removes documents by ``ref_doc_id`` metadata.

    Configuration keys
    ------------------
    similarity_top_k  Number of results to return (default ``10``)
    persist_dir       Optional path to persist the BM25 index (future use)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        # LlamaIndexSearchAdapter.__init__ sets self._store = None; we must
        # also initialise BaseRetriever explicitly since the MRO chain stops at
        # LlamaIndexSearchAdapter (which does not call super().__init__).
        LlamaIndexSearchAdapter.__init__(self, store=None)
        BaseRetriever.__init__(self)
        self._config = config or {}
        self._retriever = None
        from llama_index.core.storage.docstore import SimpleDocumentStore
        self._docstore = SimpleDocumentStore()

    # ------------------------------------------------------------------
    # SearchStoreAdapter interface
    # ------------------------------------------------------------------

    def is_langchain(self) -> bool:
        return False

    def get_store(self):
        return self.get_retriever()

    def delete(self, ref_doc_id: str) -> None:
        """Remove all nodes whose ``ref_doc_id`` or ``doc_id`` metadata matches.

        Filesystem nodes carry the stable doc_id under the ``doc_id`` metadata key
        (not ``ref_doc_id``), so both keys are checked.
        """
        to_remove = [
            nid for nid, node in self._docstore.docs.items()
            if node.metadata.get("ref_doc_id") == ref_doc_id
            or node.metadata.get("doc_id") == ref_doc_id
        ]
        if to_remove:
            for nid in to_remove:
                self._docstore.delete_document(nid)
            self._retriever = None  # invalidate cached retriever
            logger.info(
                "LlamaIndexBM25SearchAdapter: removed %d nodes for ref_doc_id=%s",
                len(to_remove), ref_doc_id,
            )
        else:
            logger.debug(
                "LlamaIndexBM25SearchAdapter: no nodes found for ref_doc_id=%s", ref_doc_id
            )

    # ------------------------------------------------------------------
    # BM25-specific helpers
    # ------------------------------------------------------------------

    def add_nodes(self, nodes: List[Any]) -> None:
        """Append *nodes* to the cumulative docstore and invalidate the cached retriever."""
        self._docstore.add_documents(nodes)
        self._retriever = None
        logger.info(
            "LlamaIndexBM25SearchAdapter: added %d nodes (total=%d)",
            len(nodes), len(self._docstore.docs),
        )

    def build_retriever(self, docstore=None):
        """Build (or rebuild) the BM25Retriever from the cumulative docstore.

        Accepts an optional *docstore* for backward compatibility; when omitted
        the internal cumulative docstore is used.
        """
        from llama_index.retrievers.bm25 import BM25Retriever

        store = docstore if docstore is not None else self._docstore
        if not store.docs:
            logger.warning("LlamaIndexBM25SearchAdapter: docstore is empty — no retriever built")
            return None
        logger.info(
            "LlamaIndexBM25SearchAdapter: building BM25Retriever from %d docs", len(store.docs)
        )
        self._retriever = BM25Retriever.from_defaults(
            docstore=store,
            similarity_top_k=self._config.get("similarity_top_k", 10),
        )
        persist_dir = self._config.get("persist_dir")
        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)
            logger.debug("LlamaIndexBM25SearchAdapter: persist_dir=%s (future use)", persist_dir)
        return self._retriever

    def get_retriever(self):
        """Return the cached BM25Retriever, rebuilding if the docstore changed."""
        if self._retriever is None and self._docstore.docs:
            self.build_retriever()
        return self._retriever

    # ------------------------------------------------------------------
    # BaseRetriever interface — makes this adapter usable directly in
    # QueryFusionRetriever without extracting the inner BM25Retriever.
    # This ensures that when _retriever is rebuilt after a delete/add the
    # fusion sees the updated index on the very next query.
    # ------------------------------------------------------------------

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        retriever = self.get_retriever()
        if retriever is None:
            return []
        return retriever.retrieve(query_bundle)


__all__ = ["LlamaIndexBM25SearchAdapter"]
