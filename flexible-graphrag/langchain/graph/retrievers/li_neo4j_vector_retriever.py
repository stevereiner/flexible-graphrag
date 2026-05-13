"""langchain.graph.retrievers.li_neo4j_vector_retriever — LI wrapper (Layer 1).

``GraphEntityVectorRetriever`` is the LI ``LCBackedLIRetriever`` wrapper
around ``LCNeo4jVectorRetriever`` (Layer 0).

Adds multi-query support: when ``QueryBundle.custom_embedding_strs`` is
populated (e.g. by ``SynonymExpander``), the LC retriever is invoked once
per term and results are merged by page_content, keeping the highest score.

``as_lc_retriever()`` prefers ``neo4j_vector.as_retriever()`` (idiomatic LC
VectorStore path) and falls back to ``self._lc_retriever``.
"""
from __future__ import annotations

import logging
from typing import Any, List

from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from langchain.retriever_bridge import LCBackedLIRetriever
from langchain.graph.retrievers.lc_neo4j_vector_retriever import LCNeo4jVectorRetriever

logger = logging.getLogger(__name__)


class GraphEntityVectorRetriever(LCBackedLIRetriever):
    """LI retriever backed by a Neo4j entity vector index via LangChain.

    Holds an ``LCNeo4jVectorRetriever`` as ``self._lc_retriever``.
    Loops over ``QueryBundle.custom_embedding_strs`` for multi-term search,
    deduplicating by entity text and keeping the highest score.

    ``as_lc_retriever()`` returns ``neo4j_vector.as_retriever(...)`` when
    available, otherwise ``self._lc_retriever``.

    Args:
        neo4j_vector:   A ``langchain_neo4j.Neo4jVector`` already initialised
                        against the target index.
        embed_model:    LlamaIndex embedding model (kept for API compat; Neo4j
                        vector handles embedding internally).
        top_k:          Number of results to return.
        text_property:  Node property to use as the returned text.
    """

    def __init__(
        self,
        neo4j_vector: Any,
        embed_model: Any,
        top_k: int = 5,
        text_property: str = "name",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._neo4j_vector = neo4j_vector
        self._embed_model = embed_model  # kept for API compat
        self._top_k = top_k
        self._text_property = text_property
        # Layer 0 LC retriever
        self._lc_retriever = LCNeo4jVectorRetriever(
            neo4j_vector, top_k=top_k, text_property=text_property
        )

    def as_lc_retriever(self) -> Any:
        """Return an LC retriever for EnsembleRetriever integration.

        Prefers ``neo4j_vector.as_retriever()`` — the idiomatic LC
        VectorStore retriever.  Falls back to ``self._lc_retriever``.
        """
        if hasattr(self._neo4j_vector, "as_retriever"):
            return self._neo4j_vector.as_retriever(search_kwargs={"k": self._top_k})
        return self._lc_retriever

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_str = query_bundle.query_str
        embedding_queries = list(query_bundle.custom_embedding_strs or [])
        if not embedding_queries:
            embedding_queries = [query_str]

        seen: dict = {}  # text -> (NodeWithScore, score)
        for eq in embedding_queries:
            docs = self._lc_retriever.invoke(eq)
            for doc in docs:
                text = doc.page_content or ""
                if not text:
                    continue
                score = float((doc.metadata or {}).get("score", 0.0))
                existing_score = seen.get(text, (None, -1.0))[1]
                if score > existing_score:
                    meta = dict(doc.metadata or {})
                    node = TextNode(text=text, metadata=meta)
                    seen[text] = (NodeWithScore(node=node, score=score), score)

        nodes = [
            nws for nws, _ in sorted(seen.values(), key=lambda x: x[1], reverse=True)
        ][: self._top_k]
        logger.debug(
            "GraphEntityVectorRetriever returned %d nodes for: %s",
            len(nodes), query_str[:80],
        )
        return nodes


__all__ = ["GraphEntityVectorRetriever"]
