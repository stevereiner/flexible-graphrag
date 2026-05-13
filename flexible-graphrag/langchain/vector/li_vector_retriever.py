"""langchain.vector.li_vector_retriever — LI wrapper for LC vector stores (Layer 1).

``LangChainVectorStoreRetriever`` bridges any LangChain ``VectorStore`` into
LlamaIndex's ``QueryFusionRetriever`` by holding an ``LCVectorRetriever``
(Layer 0) and looping over ``QueryBundle.custom_embedding_strs`` for
synonym-expansion support.

``as_lc_retriever()`` returns ``lc_store.as_retriever()`` when available
(idiomatic LC path for EnsembleRetriever) or the ``LCVectorRetriever``.
"""
from __future__ import annotations

import logging
from typing import Any, List

from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from langchain.retriever_bridge import LCBackedLIRetriever
from langchain.vector.lc_vector_retriever import LCVectorRetriever

logger = logging.getLogger(__name__)


class LangChainVectorStoreRetriever(LCBackedLIRetriever):
    """LlamaIndex retriever backed by any LangChain VectorStore.

    Holds an ``LCVectorRetriever`` as ``self._lc_retriever``.
    Loops over ``QueryBundle.custom_embedding_strs`` (synonym expansion
    terms) so every expanded term gets its own similarity search; results
    are deduplicated by ``page_content``, keeping the highest score.

    ``as_lc_retriever()`` returns ``lc_store.as_retriever(...)`` when the
    store supports it — the idiomatic LC vector path for EnsembleRetriever.
    Falls back to ``self._lc_retriever`` (``LCVectorRetriever``) otherwise.

    Args:
        lc_store:   A LangChain ``VectorStore`` instance (Qdrant, Chroma, …).
        top_k:      Maximum results to return.
        store_name: Label for logging (e.g. ``"qdrant"``).
    """

    def __init__(
        self,
        lc_store: Any,
        top_k: int = 10,
        store_name: str = "lc_vector",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._lc_store = lc_store
        self._top_k = top_k
        self._store_name = store_name
        # Layer 0 LC retriever — exposed via as_lc_retriever() fallback
        self._lc_retriever = LCVectorRetriever(lc_store, top_k=top_k, store_name=store_name)

    def as_lc_retriever(self) -> Any:
        """Return an LC retriever for EnsembleRetriever integration.

        Prefers ``lc_store.as_retriever()`` — the idiomatic LC VectorStore
        path that most stores optimise for.  Falls back to the
        ``LCVectorRetriever`` wrapper when ``as_retriever`` is absent.
        """
        if hasattr(self._lc_store, "as_retriever"):
            return self._lc_store.as_retriever(search_kwargs={"k": self._top_k})
        return self._lc_retriever

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_str = query_bundle.query_str
        embedding_queries = list(query_bundle.custom_embedding_strs or [])
        if not embedding_queries:
            embedding_queries = [query_str]

        # Store (TextNode, raw_score) so we can normalise before building NodeWithScore.
        seen: dict = {}  # page_content -> (TextNode, raw_score)
        for eq in embedding_queries:
            docs = self._lc_retriever.invoke(eq)
            for doc in docs:
                text = doc.page_content or ""
                if not text:
                    continue
                score = float((doc.metadata or {}).get("score", 0.7))
                existing_score = seen.get(text, (None, -1.0))[1]
                if score > existing_score:
                    meta = dict(doc.metadata or {})
                    seen[text] = (TextNode(text=text, metadata=meta), score)

        if not seen:
            return []

        # Normalise to [0, 1] when any score exceeds 1.0.
        # Full-text BM25 (Elasticsearch, OpenSearch) returns raw TF-IDF scores
        # that are unbounded — e.g. 1.559.  If left unnormalised they inflate
        # QueryFusionRetriever's relative_score max and squash all other
        # retrievers' scores to near-zero.
        raw_scores = [s for _, s in seen.values()]
        if max(raw_scores) > 1.0:
            min_s, max_s = min(raw_scores), max(raw_scores)
            rng = max_s - min_s
            if rng > 0:
                seen = {t: (n, (s - min_s) / rng) for t, (n, s) in seen.items()}
            else:
                seen = {t: (n, 1.0) for t, (n, _) in seen.items()}

        nodes = [
            NodeWithScore(node=n, score=s)
            for n, s in sorted(seen.values(), key=lambda x: x[1], reverse=True)
        ][: self._top_k]
        logger.debug(
            "LangChainVectorStoreRetriever(%s) returned %d nodes for: %s",
            self._store_name, len(nodes), query_str[:80],
        )
        return nodes


__all__ = ["LangChainVectorStoreRetriever"]
