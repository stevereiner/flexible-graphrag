"""langchain.search.retriever — LlamaIndex-compatible search retriever.

Wraps any :class:`~adapters.search.search_store_adapter.SearchStoreAdapter`
(BM25, Elasticsearch, OpenSearch) as a LlamaIndex :class:`BaseRetriever` so
it can participate in ``QueryFusionRetriever`` alongside vector and graph
retrievers.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

logger = logging.getLogger(__name__)


class LangChainSearchRetriever(BaseRetriever):
    """LlamaIndex BaseRetriever that delegates to a LangChain search backend.

    Works with every :class:`~adapters.search.search_store_adapter.SearchStoreAdapter`
    implementation.  Dispatch priority:

    1. ``invoke`` — any modern ``langchain_core.BaseRetriever`` (BM25, ES retriever, …)
    2. ``similarity_search`` — raw ``VectorStore`` objects (ES / OpenSearch store)

    Parameters
    ----------
    search_adapter:
        Any ``SearchStoreAdapter`` instance.
    k:
        Maximum number of documents to retrieve.
    fallback_score:
        Score assigned when the backend does not return relevance scores.
    """

    def __init__(
        self,
        search_adapter: Any,
        k: int = 10,
        fallback_score: float = 0.7,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._adapter = search_adapter
        self._k = k
        self._fallback_score = fallback_score

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lc_retriever(self) -> Any:
        """Return the raw LangChain retriever / store from the adapter."""
        if hasattr(self._adapter, "get_retriever") and callable(self._adapter.get_retriever):
            return self._adapter.get_retriever()
        return self._adapter.get_store()

    def _docs_to_nodes(self, docs) -> List[NodeWithScore]:
        nodes: List[NodeWithScore] = []
        for doc in docs:
            meta = doc.metadata.copy() if doc.metadata else {}
            meta["source_framework"] = "langchain_search"
            meta["retriever_type"] = type(self._adapter).__name__
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
        try:
            lc_obj = self._get_lc_retriever()
            if lc_obj is None:
                logger.debug("LangChainSearchRetriever: no retriever available (empty corpus?)")
                return []

            # BaseRetriever (BM25Retriever, ElasticsearchRetriever, …) — invoke is always present.
            # Raw VectorStore (ES / OpenSearch store) falls back to similarity_search.
            if hasattr(lc_obj, "invoke"):
                docs = lc_obj.invoke(query_str)
            elif hasattr(lc_obj, "similarity_search"):
                docs = lc_obj.similarity_search(query_str, k=self._k)
            else:
                logger.warning(
                    "LangChainSearchRetriever: don't know how to query %s",
                    type(lc_obj).__name__,
                )
                return []

            nodes = self._docs_to_nodes(docs)
            logger.info(
                "LangChainSearchRetriever (%s): %d results for %r",
                type(self._adapter).__name__,
                len(nodes),
                query_str[:80],
            )
            return nodes[: self._k]

        except Exception as exc:
            logger.error("LangChainSearchRetriever error: %s", exc, exc_info=True)
            return []

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Async path — tries ``ainvoke`` first, falls back to sync executor."""
        query_str = query_bundle.query_str
        try:
            lc_obj = self._get_lc_retriever()
            if lc_obj is None:
                return []

            if hasattr(lc_obj, "ainvoke"):
                docs = await lc_obj.ainvoke(query_str)
                return self._docs_to_nodes(docs)[: self._k]

        except Exception as exc:
            logger.warning("LangChainSearchRetriever async failed, falling back to sync: %s", exc)

        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._retrieve, query_bundle)


__all__ = ["LangChainSearchRetriever"]
