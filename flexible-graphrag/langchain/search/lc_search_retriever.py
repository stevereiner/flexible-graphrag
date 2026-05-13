"""langchain.search.lc_search_retriever — Pure-LC search retriever (Layer 0).

``LCSearchRetriever`` wraps any ``langchain_core.BaseRetriever`` (BM25,
Elasticsearch, OpenSearch, …) and adds:
  - top_k truncation
  - source label injection into ``Document.metadata``
  - graceful async fall-through when the inner retriever has no ``ainvoke``

This is the LC counterpart consumed by ``LangChainRetrieverWrapper`` (Layer 1).
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

    class LCSearchRetriever(_LCBase):
        """Pure LC retriever wrapping any LangChain BaseRetriever.

        Applies a ``top_k`` hard cap and injects ``metadata["source"]`` so
        results are identifiable in fusion logs.  Score is not added (full-text
        / BM25 retrievers don't return relevance scores); the LI wrapper assigns
        a fixed ``base_score``.

        Args:
            lc_retriever: Any ``langchain_core.BaseRetriever`` instance.
            top_k:        Maximum documents to return.
            label:        Source label injected into ``metadata["source"]``.
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def __init__(
            self,
            lc_retriever: Any,
            top_k: int = 10,
            label: str = "lc_search",
        ) -> None:
            super().__init__()
            self._inner = lc_retriever
            self._top_k = top_k
            self._label = label

        # ------------------------------------------------------------------
        # internal helpers
        # ------------------------------------------------------------------

        def _build_docs(self, raw_docs: list) -> List[_LCDoc]:
            result: List[_LCDoc] = []
            for doc in raw_docs[: self._top_k]:
                text = doc.page_content or ""
                if not text.strip():
                    continue
                meta = dict(doc.metadata or {})
                meta.setdefault("source", self._label)
                result.append(_LCDoc(page_content=text, metadata=meta))
            return result

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
                raw = self._inner.invoke(query)
            except Exception as e:
                logger.warning(
                    "LCSearchRetriever(%s) error for '%s': %s",
                    self._label, query[:60], e,
                )
                return []
            return self._build_docs(raw)

        async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            import asyncio
            try:
                raw = await self._inner.ainvoke(query)
            except NotImplementedError:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, self._inner.invoke, query
                )
            except Exception as e:
                logger.warning(
                    "LCSearchRetriever(%s) async error for '%s': %s",
                    self._label, query[:60], e,
                )
                return []
            return self._build_docs(raw)

except ImportError:
    class LCSearchRetriever:  # type: ignore[no-redef]
        """Stub when ``langchain_core`` is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "langchain_core is required for LCSearchRetriever. "
                "Install with: uv pip install langchain-core"
            )


__all__ = ["LCSearchRetriever"]
