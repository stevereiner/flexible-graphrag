"""
LangChain PG Neighborhood Retriever

Store-agnostic k-hop graph expansion retriever.  Given a set of seed node IDs
(typically produced by a vector similarity search), it traverses outward N hops
in the property graph and returns the text/name of every node it reaches as
NodeWithScore objects suitable for LlamaIndex QueryFusionRetriever.

Public API
----------
    GraphNeighborhoodRetriever  — BaseRetriever subclass for fusion
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, List, Optional, Tuple

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

logger = logging.getLogger(__name__)


class GraphNeighborhoodRetriever(BaseRetriever):
    """K-hop neighborhood expansion retriever for property graphs.

    Expands from seed node IDs obtained via ``seed_id_getter(query_bundle)``
    up to ``hop_depth`` hops using ``neighbor_query_fn(seed_ids, hop_depth)``,
    which must return an iterable of ``(node_id, text, score)`` tuples.

    Args:
        seed_id_getter:     ``(QueryBundle) -> Iterable[str]`` — returns seed
                            node IDs, e.g. from a vector similarity search.
        neighbor_query_fn:  ``(seed_ids, hop_depth) -> Iterable[(id, text, score)]``
                            — executes the actual graph traversal.
        hop_depth:          Maximum number of relationship hops to expand.
        top_k:              Maximum number of results to return.
    """

    def __init__(
        self,
        seed_id_getter: Callable[[QueryBundle], Iterable[str]],
        neighbor_query_fn: Callable[[List[str], int], Iterable[Tuple[str, str, float]]],
        hop_depth: int = 2,
        top_k: int = 10,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._seed_id_getter = seed_id_getter
        self._neighbor_query_fn = neighbor_query_fn
        self._hop_depth = hop_depth
        self._top_k = top_k

    # ------------------------------------------------------------------
    # BaseRetriever interface
    # ------------------------------------------------------------------

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        # 1. Get seed IDs from the vector similarity search
        try:
            seed_ids = list(self._seed_id_getter(query_bundle))
        except Exception as e:
            logger.warning("GraphNeighborhoodRetriever seed_id_getter error: %s", e)
            return []

        if not seed_ids:
            logger.debug("GraphNeighborhoodRetriever: no seed IDs for query: %s", query_bundle.query_str[:80])
            return []

        # 2. Expand the neighborhood
        try:
            rows = list(self._neighbor_query_fn(seed_ids, self._hop_depth))
        except Exception as e:
            logger.warning("GraphNeighborhoodRetriever neighbor_query_fn error: %s", e)
            return []

        # 3. Deduplicate by node id, keep highest score
        seen: dict[str, Tuple[str, float]] = {}
        for node_id, text, score in rows:
            if not text:
                continue
            existing_score = seen.get(node_id, (None, -1.0))[1]
            if score > existing_score:
                seen[node_id] = (text, score)

        # 4. Sort by score descending, apply top_k
        ranked = sorted(seen.items(), key=lambda kv: kv[1][1], reverse=True)[: self._top_k]

        nodes: List[NodeWithScore] = []
        for node_id, (text, score) in ranked:
            node = TextNode(
                text=str(text),
                metadata={"source": str(node_id)},
            )
            nodes.append(NodeWithScore(node=node, score=float(score)))

        logger.debug(
            "GraphNeighborhoodRetriever: %d seeds -> %d unique neighbors (top_k=%d) for: %s",
            len(seed_ids),
            len(seen),
            self._top_k,
            query_bundle.query_str[:80],
        )
        return nodes
