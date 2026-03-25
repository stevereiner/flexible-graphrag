"""
LangChain Neo4j Vector Retriever

Wraps langchain_neo4j.Neo4jVector (or langchain_community equivalent) as a
LlamaIndex BaseRetriever so it can participate in QueryFusionRetriever alongside
the GraphCypherQAChain retriever.

This enables vector-similarity search against entity nodes stored in Neo4j
(or any graph store that exposes a vector index) independently of whether a
LlamaIndex PropertyGraphIndex is configured.  Useful when the graph store only
has LangChain support (no LlamaIndex graph store adapter).

The retriever queries the specified vector index, retrieves the top-K most
similar nodes, and returns their text / name as NodeWithScore objects.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

logger = logging.getLogger(__name__)


class GraphEntityVectorRetriever(BaseRetriever):
    """LlamaIndex retriever backed by a Neo4j vector index via LangChain.

    Queries a named vector index in Neo4j (e.g. the ``entity`` index on
    ``__Entity__[embedding]`` that LlamaIndex creates during ingestion) using
    the query embedding, then returns the matched nodes as TextNode objects
    for fusion.

    Args:
        neo4j_vector:   A ``langchain_neo4j.Neo4jVector`` (or community
                        equivalent) already initialised against the target index.
        embed_model:    LlamaIndex embedding model used to embed the query.
        top_k:          Number of results to return.
        text_property:  Node property to use as the returned text.
                        Falls back to ``name``, then ``id``, then the node id.
    """

    def __init__(
        self,
        neo4j_vector: Any,
        embed_model: Any,
        top_k: int = 5,
        text_property: str = "name",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._neo4j_vector = neo4j_vector
        self._embed_model = embed_model
        self._top_k = top_k
        self._text_property = text_property

    # ------------------------------------------------------------------
    # BaseRetriever interface
    # ------------------------------------------------------------------

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_str = query_bundle.query_str
        # If custom_embedding_strs are present (e.g. from SynonymExpander), embed
        # them all and merge results — take the highest score per unique node text.
        embedding_queries = list(query_bundle.custom_embedding_strs or [])
        if not embedding_queries:
            embedding_queries = [query_str]

        seen: dict = {}  # text -> (node, score)
        for eq in embedding_queries:
            try:
                results = self._neo4j_vector.similarity_search_with_score(
                    eq, k=self._top_k
                )
            except Exception as e:
                logger.warning("LangChain Neo4j vector search error for '%s': %s", eq[:60], e)
                continue
            for doc, score in results:
                meta = doc.metadata or {}
                text = (
                    meta.get(self._text_property)
                    or meta.get("name")
                    or meta.get("id")
                    or doc.page_content
                    or ""
                )
                if not text:
                    continue
                existing_score = seen.get(text, (None, -1.0))[1]
                if float(score) > existing_score:
                    node = TextNode(
                        text=str(text),
                        metadata={
                            "source": meta.get("name", meta.get("id", "")),
                            **{k: v for k, v in meta.items() if k not in ("embedding",)},
                        },
                    )
                    seen[text] = (NodeWithScore(node=node, score=float(score)), float(score))

        nodes = [nws for nws, _ in sorted(seen.values(), key=lambda x: x[1], reverse=True)][: self._top_k]
        logger.debug(
            "LangChain Neo4j vector retriever returned %d nodes for query: %s",
            len(nodes), query_str[:80],
        )
        return nodes
