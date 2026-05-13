"""langchain.search.li_search_retriever — LI wrapper for LC search retrievers (Layer 1).

``LangChainRetrieverWrapper`` bridges any LangChain search retriever (BM25,
Elasticsearch, OpenSearch, …) into LlamaIndex's ``QueryFusionRetriever``
by holding an ``LCSearchRetriever`` (Layer 0).

``as_lc_retriever()`` (from ``LCBackedLIRetriever``) returns the
``LCSearchRetriever`` directly for use in ``EnsembleRetriever``.
"""
from __future__ import annotations

import logging
from typing import Any, List

from llama_index.core.schema import NodeWithScore, QueryBundle

from langchain.retriever_bridge import LCBackedLIRetriever
from langchain.search.lc_search_retriever import LCSearchRetriever

logger = logging.getLogger(__name__)


class LangChainRetrieverWrapper(LCBackedLIRetriever):
    """LI retriever backed by any LangChain BaseRetriever.

    Wraps ``lc_retriever`` in an ``LCSearchRetriever`` (Layer 0) which
    handles top_k capping, source labelling, and async fall-through.
    Converts returned ``Document`` objects to ``NodeWithScore`` via the
    base-class ``_docs_to_nodes()`` helper, using *base_score* as the
    fixed relevance score (full-text retrievers produce no scores).

    ``as_lc_retriever()`` is inherited from ``LCBackedLIRetriever`` and
    returns ``self._lc_retriever`` (the ``LCSearchRetriever``) for direct
    use in ``EnsembleRetriever``.

    Args:
        lc_retriever: A LangChain ``BaseRetriever`` instance.
        top_k:        Maximum results to return.
        label:        Label for logging (e.g. ``"bm25"``).
        base_score:   Fixed score for all returned docs. Defaults to ``1.0``.
    """

    def __init__(
        self,
        lc_retriever: Any,
        top_k: int = 10,
        label: str = "lc_retriever",
        base_score: float = 1.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._top_k = top_k
        self._label = label
        self._base_score = base_score
        # Layer 0 LC retriever — also exposed via as_lc_retriever()
        self._lc_retriever = LCSearchRetriever(lc_retriever, top_k=top_k, label=label)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        try:
            docs = self._lc_retriever.invoke(query_bundle.query_str)
        except Exception as e:
            logger.warning("LangChainRetrieverWrapper(%s) error: %s", self._label, e)
            return []
        nodes = self._docs_to_nodes(
            docs, fallback_score=self._base_score, source_tag=self._label
        )
        logger.debug(
            "LangChainRetrieverWrapper(%s) returned %d nodes", self._label, len(nodes)
        )
        return nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        try:
            docs = await self._lc_retriever.ainvoke(query_bundle.query_str)
        except Exception as e:
            logger.warning(
                "LangChainRetrieverWrapper(%s) async error: %s", self._label, e
            )
            return []
        nodes = self._docs_to_nodes(
            docs, fallback_score=self._base_score, source_tag=self._label
        )
        logger.debug(
            "LangChainRetrieverWrapper(%s) async returned %d nodes", self._label, len(nodes)
        )
        return nodes


class LangChainAdapterDelegatingWrapper(LCBackedLIRetriever):
    """LI retriever that calls ``adapter.get_retriever()`` on *every* retrieval.

    Unlike ``LangChainRetrieverWrapper`` — which captures a single retriever
    instance at construction time — this wrapper holds the *adapter* object and
    resolves the current retriever on each query.  This is essential for in-memory
    adapters (BM25) where the inner retriever is rebuilt after every add/delete so
    that the fusion always uses the up-to-date index.

    Args:
        adapter:    A :class:`~langchain.search.adapters.bm25_adapter.BM25SearchAdapter`
                    (or any object with a ``get_retriever()`` method).
        top_k:      Maximum results to return.
        label:      Label for logging (e.g. ``"bm25"``).
        base_score: Fixed score for all returned docs. Defaults to ``1.0``.
    """

    def __init__(
        self,
        adapter: Any,
        top_k: int = 10,
        label: str = "lc_bm25",
        base_score: float = 1.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._adapter = adapter
        self._top_k = top_k
        self._label = label
        self._base_score = base_score
        # Expose a dummy _lc_retriever so as_lc_retriever() works — it will
        # wrap the adapter's *current* retriever via a thin proxy.
        self._lc_retriever = None  # type: ignore[assignment]

    def _current_retriever(self):
        return self._adapter.get_retriever()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        retriever = self._current_retriever()
        if retriever is None:
            logger.debug("LangChainAdapterDelegatingWrapper(%s): no retriever yet (empty)", self._label)
            return []
        lc_r = LCSearchRetriever(retriever, top_k=self._top_k, label=self._label)
        try:
            docs = lc_r.invoke(query_bundle.query_str)
        except Exception as e:
            logger.warning("LangChainAdapterDelegatingWrapper(%s) error: %s", self._label, e)
            return []
        nodes = self._docs_to_nodes(docs, fallback_score=self._base_score, source_tag=self._label)
        logger.debug("LangChainAdapterDelegatingWrapper(%s) returned %d nodes", self._label, len(nodes))
        return nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        retriever = self._current_retriever()
        if retriever is None:
            return []
        lc_r = LCSearchRetriever(retriever, top_k=self._top_k, label=self._label)
        try:
            docs = await lc_r.ainvoke(query_bundle.query_str)
        except Exception as e:
            logger.warning("LangChainAdapterDelegatingWrapper(%s) async error: %s", self._label, e)
            return []
        return self._docs_to_nodes(docs, fallback_score=self._base_score, source_tag=self._label)


__all__ = ["LangChainRetrieverWrapper", "LangChainAdapterDelegatingWrapper"]
