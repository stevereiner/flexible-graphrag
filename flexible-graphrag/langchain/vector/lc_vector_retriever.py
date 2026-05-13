"""langchain.vector.lc_vector_retriever — Pure-LC vector retriever (Layer 0).

``LCVectorRetriever`` wraps any LangChain ``VectorStore``, calls
``similarity_search_with_score`` and embeds the score in
``Document.metadata["score"]`` so the LI wrapper (``li_vector_retriever.py``)
can recover it via ``_docs_to_nodes``.
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

    class LCVectorRetriever(_LCBase):
        """Pure LC retriever over any LangChain VectorStore.

        Calls ``similarity_search_with_score(query, k=top_k)`` and returns
        ``Document`` objects with the similarity score stored under
        ``metadata["score"]`` so LI wrappers and ``_docs_to_nodes`` can
        recover it.

        Args:
            lc_store:   A LangChain ``VectorStore`` (Qdrant, Chroma, …).
            top_k:      Maximum results per query.
            store_name: Label for logging.
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def __init__(
            self,
            lc_store: Any,
            top_k: int = 10,
            store_name: str = "lc_vector",
        ) -> None:
            super().__init__()
            self._lc_store = lc_store
            self._top_k = top_k
            self._store_name = store_name

        def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            try:
                results = self._lc_store.similarity_search_with_score(
                    query, k=self._top_k
                )
            except Exception as e:
                logger.warning(
                    "LCVectorRetriever(%s) error for '%s': %s",
                    self._store_name, query[:60], e,
                )
                return []
            docs: List[_LCDoc] = []
            for doc, score in results:
                text = doc.page_content or ""
                if not text.strip():
                    continue
                meta = dict(doc.metadata or {})
                meta["score"] = float(score)
                meta.setdefault("source", self._store_name)
                docs.append(_LCDoc(page_content=text, metadata=meta))
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
    class LCVectorRetriever:  # type: ignore[no-redef]
        """Stub when ``langchain_core`` is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "langchain_core is required for LCVectorRetriever. "
                "Install with: uv pip install langchain-core"
            )


__all__ = ["LCVectorRetriever"]
