"""langchain.graph.retrievers.li_neighborhood_retriever — LI wrapper (Layer 1).

``GraphNeighborhoodRetriever`` is the LI ``LCBackedLIRetriever`` wrapper
around ``LCNeighborhoodRetriever`` (Layer 0).

At construction time it adapts the ``QueryBundle``-based ``seed_id_getter``
(LlamaIndex convention) to the plain-string interface used by
``LCNeighborhoodRetriever``, then stores the LC retriever as
``self._lc_retriever``.

``_retrieve()`` delegates to ``self._lc_retriever.invoke(query_str)`` and
converts the returned ``Document`` list to ``NodeWithScore`` objects via
``_docs_to_nodes()``.

``as_lc_retriever()`` is provided by ``LCBackedLIRetriever`` and returns
``self._lc_retriever`` for direct use in ``EnsembleRetriever``.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, List, Tuple

from llama_index.core.schema import NodeWithScore, QueryBundle

from langchain.retriever_bridge import LCBackedLIRetriever
from langchain.graph.retrievers.lc_neighborhood_retriever import LCNeighborhoodRetriever

logger = logging.getLogger(__name__)


class GraphNeighborhoodRetriever(LCBackedLIRetriever):
    """LI retriever for k-hop property-graph neighborhood expansion.

    Holds an ``LCNeighborhoodRetriever`` as ``self._lc_retriever``.
    The ``seed_id_getter`` must accept a ``QueryBundle``; it is
    automatically wrapped to a plain-string interface at construction time.

    Args:
        seed_id_getter:     ``(QueryBundle) -> Iterable[str]`` — returns
                            seed node IDs from a vector similarity search.
        neighbor_query_fn:  ``(seed_ids, hop_depth) ->
                            Iterable[(id, text, score[, meta])]``
                            — executes the graph traversal.
        hop_depth:          Maximum relationship hops to expand.
        top_k:              Maximum results to return.
    """

    def __init__(
        self,
        seed_id_getter: Callable[[QueryBundle], Iterable[str]],
        neighbor_query_fn: Callable[[List[str], int], Iterable[Tuple[str, str, float]]],
        hop_depth: int = 2,
        top_k: int = 10,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._hop_depth = hop_depth
        self._top_k = top_k

        # Adapt: LC layer uses plain str; LI callers pass QueryBundle.
        _qb_getter = seed_id_getter

        def _str_seed_getter(query_str: str) -> Iterable[str]:
            return _qb_getter(QueryBundle(query_str=query_str))

        self._lc_retriever = LCNeighborhoodRetriever(
            seed_id_getter=_str_seed_getter,
            neighbor_query_fn=neighbor_query_fn,
            hop_depth=hop_depth,
            top_k=top_k,
        )

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        docs = self._lc_retriever.invoke(query_bundle.query_str)
        nodes = self._docs_to_nodes(docs, fallback_score=0.7, source_tag="pg_neighborhood")
        logger.debug(
            "GraphNeighborhoodRetriever: returned %d nodes for: %s",
            len(nodes), query_bundle.query_str[:80],
        )
        return nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        docs = await self._lc_retriever.ainvoke(query_bundle.query_str)
        nodes = self._docs_to_nodes(docs, fallback_score=0.7, source_tag="pg_neighborhood")
        logger.debug(
            "GraphNeighborhoodRetriever async: returned %d nodes for: %s",
            len(nodes), query_bundle.query_str[:80],
        )
        return nodes


__all__ = ["GraphNeighborhoodRetriever"]
