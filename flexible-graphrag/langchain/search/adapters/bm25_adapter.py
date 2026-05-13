"""LangChain BM25 search store adapter.

In-memory full-text retrieval backed by ``rank_bm25`` with optional JSON
persistence to disk so the document corpus survives restarts.
"""
from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

from adapters.search.search_store_adapter import SearchStoreAdapter
from langchain.utils import llamaindex_nodes_to_langchain_docs

logger = logging.getLogger(__name__)


class BM25SearchAdapter(SearchStoreAdapter):
    """LangChain BM25Retriever adapter — rank_bm25-backed, in-memory with optional JSON persistence.

    Lifecycle
    ---------
    - Call :meth:`add_documents` after ingestion to populate.
    - Call :meth:`persist` to write docs to disk.
    - Use :meth:`from_persist_dir` at startup to restore without re-ingesting.
    - :meth:`get_retriever` rebuilds the BM25 index whenever the document list changes.
    - :meth:`delete` removes docs by ``ref_doc_id`` metadata and invalidates the cached retriever.
    """

    _DOCS_FILE = "bm25_docs.json"

    def __init__(
        self,
        documents=None,
        k: int = 10,
        persist_dir: Optional[str] = None,
        preprocess_func=None,
    ):
        self._documents = list(documents) if documents else []
        self._k = k
        self._persist_dir = persist_dir
        self._preprocess_func = preprocess_func
        self._retriever = None

    # ------------------------------------------------------------------
    # SearchStoreAdapter interface
    # ------------------------------------------------------------------

    def get_store(self):
        return self.get_retriever()

    def delete(self, ref_doc_id: str) -> None:
        before = len(self._documents)
        self._documents = [
            d for d in self._documents
            if d.metadata.get("ref_doc_id") != ref_doc_id
            and d.metadata.get("doc_id") != ref_doc_id
        ]
        removed = before - len(self._documents)
        if removed:
            self._retriever = None
            logger.info("BM25SearchAdapter: removed %d docs for ref_doc_id=%s", removed, ref_doc_id)
        else:
            logger.debug("BM25SearchAdapter: no docs found for ref_doc_id=%s", ref_doc_id)

    def is_langchain(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # BM25-specific helpers
    # ------------------------------------------------------------------

    def add_documents(self, documents) -> None:
        """Append *documents* and invalidate the cached retriever."""
        self._documents.extend(documents)
        self._retriever = None

    async def aadd_documents(self, documents) -> list:
        """Async wrapper for :meth:`add_documents` (BM25 is CPU-only, no async needed).

        Returns a list of empty-string IDs to match the ``aadd_documents``
        contract expected by :mod:`ingest.update_search`.
        """
        self.add_documents(documents)
        return [""] * len(list(documents))

    def get_retriever(self):
        """Return a ready-to-use ``BM25Retriever``, rebuilding if needed."""
        if self._retriever is None:
            self._retriever = self._build()
        return self._retriever

    def persist(self, persist_dir: Optional[str] = None) -> None:
        """Serialise the document list to ``<persist_dir>/bm25_docs.json``."""
        target = persist_dir or self._persist_dir
        if not target:
            return
        os.makedirs(target, exist_ok=True)
        path = os.path.join(target, self._DOCS_FILE)
        data = [{"page_content": d.page_content, "metadata": d.metadata} for d in self._documents]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("BM25SearchAdapter: persisted %d docs to %s", len(self._documents), path)

    @classmethod
    def from_persist_dir(
        cls,
        persist_dir: str,
        k: int = 10,
        preprocess_func=None,
    ) -> "BM25SearchAdapter":
        """Load a previously persisted adapter from *persist_dir*.

        Returns an empty adapter if the file does not exist.
        """
        from langchain_core.documents import Document as LCDocument

        path = os.path.join(persist_dir, cls._DOCS_FILE)
        if not os.path.exists(path):
            logger.info("BM25SearchAdapter: no persisted docs at %s, starting empty", path)
            return cls(k=k, persist_dir=persist_dir, preprocess_func=preprocess_func)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        docs = [LCDocument(page_content=d["page_content"], metadata=d.get("metadata", {})) for d in data]
        logger.info("BM25SearchAdapter: loaded %d docs from %s", len(docs), path)
        return cls(documents=docs, k=k, persist_dir=persist_dir, preprocess_func=preprocess_func)

    def _build(self):
        from langchain_community.retrievers import BM25Retriever

        if not self._documents:
            return None
        kwargs = {"k": self._k}
        if self._preprocess_func is not None:
            kwargs["preprocess_func"] = self._preprocess_func
        retriever = BM25Retriever.from_documents(self._documents, **kwargs)
        logger.info(
            "BM25SearchAdapter: built BM25Retriever with %d documents, k=%d",
            len(self._documents),
            self._k,
        )
        return retriever


def create_langchain_bm25_adapter(
    nodes_or_docs=None,
    k: int = 10,
    persist_dir: Optional[str] = None,
    preprocess_func=None,
) -> BM25SearchAdapter:
    """Build a :class:`BM25SearchAdapter` from LlamaIndex nodes/docs or LangChain Documents.

    If *persist_dir* is given and ``bm25_docs.json`` exists there, the
    persisted document list is loaded instead of converting *nodes_or_docs*.
    """
    if persist_dir:
        docs_file = os.path.join(persist_dir, BM25SearchAdapter._DOCS_FILE)
        if os.path.exists(docs_file):
            return BM25SearchAdapter.from_persist_dir(persist_dir, k=k, preprocess_func=preprocess_func)

    lc_docs: list = []
    if nodes_or_docs:
        from langchain_core.documents import Document as LCDocument

        first = next((n for n in nodes_or_docs), None)
        if first is not None and isinstance(first, LCDocument):
            lc_docs = list(nodes_or_docs)
        else:
            lc_docs = llamaindex_nodes_to_langchain_docs(nodes_or_docs)

    adapter = BM25SearchAdapter(documents=lc_docs, k=k, persist_dir=persist_dir, preprocess_func=preprocess_func)
    logger.info("BM25SearchAdapter created with %d documents, k=%d", len(lc_docs), k)
    return adapter


__all__ = [
    "BM25SearchAdapter",
    "create_langchain_bm25_adapter",
]
