"""langchain.vector.retriever — LlamaIndex-compatible vector retriever.

Wraps any LangChain VectorStore (or its ``as_retriever()`` result) as a
LlamaIndex :class:`BaseRetriever` so it participates in
``QueryFusionRetriever`` alongside search and graph retrievers.

``LangChainVectorRetriever`` accepts either:

- A :class:`~langchain.vector.vector_store_adapter.LangChainVectorAdapter`
  (or any subclass) — ``get_store().as_retriever()`` is called automatically.
- A raw LangChain VectorStore or BaseRetriever — passed directly.
"""
from __future__ import annotations

import logging
from typing import Any, List

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

logger = logging.getLogger(__name__)


class LangChainVectorRetriever(BaseRetriever):
    """LlamaIndex BaseRetriever that delegates to a LangChain vector backend.

    Parameters
    ----------
    store_or_retriever:
        A LangChain ``VectorStore``, a ``VectorStoreRetriever``, any
        ``BaseRetriever``, or a
        :class:`~langchain.vector.vector_store_adapter.LangChainVectorAdapter`.
    k:
        Number of nearest neighbours to retrieve.
    fallback_score:
        Score assigned when the backend does not return relevance values.
    search_type:
        Passed to ``VectorStore.as_retriever(search_type=…)``.
        Common values: ``"similarity"`` (default), ``"mmr"``.
    """

    def __init__(
        self,
        store_or_retriever: Any,
        k: int = 10,
        fallback_score: float = 0.7,
        search_type: str = "similarity",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._k = k
        self._fallback_score = fallback_score
        self._search_type = search_type
        self._lc_retriever = self._resolve(store_or_retriever)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, obj: Any):
        """Unwrap adapters / VectorStores into a LangChain retriever."""
        # LangChainVectorAdapter or any adapter with get_store()
        if hasattr(obj, "get_store") and callable(obj.get_store):
            obj = obj.get_store()
            if obj is None:
                return None

        # LangChain VectorStore — convert to retriever
        if hasattr(obj, "as_retriever") and callable(obj.as_retriever):
            return obj.as_retriever(
                search_type=self._search_type,
                search_kwargs={"k": self._k},
            )

        # Already a retriever (BM25Retriever, VectorStoreRetriever, etc.)
        return obj

    def _docs_to_nodes(self, docs) -> List[NodeWithScore]:
        nodes: List[NodeWithScore] = []
        for doc in docs:
            meta = doc.metadata.copy() if doc.metadata else {}
            meta["source_framework"] = "langchain_vector"
            meta["retriever_type"] = type(self._lc_retriever).__name__
            node = TextNode(text=doc.page_content or "", metadata=meta)
            score = float(
                getattr(doc, "score", None)
                or meta.get("score")
                or meta.get("relevance_score")
                or self._fallback_score
            )
            nodes.append(NodeWithScore(node=node, score=score))
        return nodes

    # ------------------------------------------------------------------
    # BaseRetriever interface
    # ------------------------------------------------------------------

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_str = query_bundle.query_str
        if self._lc_retriever is None:
            logger.debug("LangChainVectorRetriever: no retriever available")
            return []
        try:
            if hasattr(self._lc_retriever, "invoke"):
                docs = self._lc_retriever.invoke(query_str)
            else:
                docs = self._lc_retriever.get_relevant_documents(query_str)  # type: ignore[attr-defined]

            nodes = self._docs_to_nodes(docs)
            logger.info(
                "LangChainVectorRetriever (%s): %d results for %r",
                type(self._lc_retriever).__name__,
                len(nodes),
                query_str[:80],
            )
            return nodes[: self._k]

        except Exception as exc:
            logger.error("LangChainVectorRetriever error: %s", exc, exc_info=True)
            return []

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Async path — tries ``ainvoke`` first, falls back to sync executor."""
        if self._lc_retriever is None:
            return []
        query_str = query_bundle.query_str
        try:
            if hasattr(self._lc_retriever, "ainvoke"):
                docs = await self._lc_retriever.ainvoke(query_str)
                return self._docs_to_nodes(docs)[: self._k]

            if hasattr(self._lc_retriever, "aget_relevant_documents"):
                docs = await self._lc_retriever.aget_relevant_documents(query_str)  # type: ignore[attr-defined]
                return self._docs_to_nodes(docs)[: self._k]

        except Exception as exc:
            logger.warning("LangChainVectorRetriever async failed, falling back to sync: %s", exc)

        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._retrieve, query_bundle)


__all__ = ["LangChainVectorRetriever"]
