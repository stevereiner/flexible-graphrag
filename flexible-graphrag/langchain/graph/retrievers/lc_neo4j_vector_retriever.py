"""langchain.graph.retrievers.lc_neo4j_vector_retriever — Pure-LC Neo4j vector retriever (Layer 0).

``LCNeo4jVectorRetriever`` wraps a ``langchain_neo4j.Neo4jVector`` (or
``langchain_community`` equivalent) as a ``langchain_core.BaseRetriever``.

It calls ``similarity_search_with_score(query, k=top_k)`` and returns
``Document`` objects where:
  - ``page_content`` = the entity text (resolved via ``text_property``,
    falling back to ``name``, ``id``, or raw ``page_content``).
  - ``metadata["score"]`` = similarity score (for ``_docs_to_nodes``).
  - ``metadata["entity_name"]`` = same as page_content (convenience copy).
  - ``metadata["source"]`` = ``"langchain_pg_vector"``.

This is the LC counterpart consumed by ``GraphEntityVectorRetriever`` (Layer 1).
"""
from __future__ import annotations

import logging
from typing import Any, List

logger = logging.getLogger(__name__)

try:
    from langchain_core.retrievers import BaseRetriever as _LCBase
    from langchain_core.documents import Document as _LCDoc
    from langchain_core.callbacks.manager import (
        CallbackManagerForRetrieverRun,
        AsyncCallbackManagerForRetrieverRun,
    )
    from pydantic import ConfigDict

    class LCNeo4jVectorRetriever(_LCBase):
        """Pure LC retriever backed by a Neo4j vector index.

        Calls ``neo4j_vector.similarity_search_with_score(query, k=top_k)``
        and converts ``(Document, score)`` pairs to ``Document`` objects with
        the score embedded in ``metadata["score"]``.

        The resolved entity text is used as ``page_content`` so fusion
        de-duplication works on the actual entity name, not raw embeddings.

        Args:
            neo4j_vector:   A ``langchain_neo4j.Neo4jVector`` (or community
                            equivalent) already initialised against the target
                            index.
            top_k:          Number of results to return.
            text_property:  Node property to use as the returned text.
                            Falls back to ``name``, then ``id``, then
                            ``page_content``.
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def __init__(
            self,
            neo4j_vector: Any,
            top_k: int = 5,
            text_property: str = "name",
        ) -> None:
            super().__init__()
            self._neo4j_vector = neo4j_vector
            self._top_k = top_k
            self._text_property = text_property

        # ------------------------------------------------------------------
        # LC BaseRetriever interface
        # ------------------------------------------------------------------

        def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            try:
                results = self._neo4j_vector.similarity_search_with_score(
                    query, k=self._top_k
                )
            except Exception as e:
                logger.warning(
                    "LCNeo4jVectorRetriever error for '%s': %s", query[:60], e
                )
                return []

            docs: List[_LCDoc] = []
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
                out_meta = {
                    "source": "langchain_pg_vector",
                    "entity_name": str(text),
                    "score": float(score),
                    **{k: v for k, v in meta.items() if k != "embedding"},
                }
                docs.append(_LCDoc(page_content=str(text), metadata=out_meta))
            return docs

        async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            import asyncio
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_relevant_documents(query, run_manager=run_manager),
            )

except ImportError:
    class LCNeo4jVectorRetriever:  # type: ignore[no-redef]
        """Stub when ``langchain_core`` is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "langchain_core is required for LCNeo4jVectorRetriever. "
                "Install with: uv pip install langchain-core"
            )


__all__ = ["LCNeo4jVectorRetriever"]
