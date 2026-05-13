"""langchain.graph.retrievers.lc_synonym_retriever — Pure-LC multi-query retriever (Layer 0).

``LCSynonymRetriever`` wraps any ``langchain_core.BaseRetriever`` and runs it
once per expanded query string, merging the results.

Query expansion is decoupled via an ``expand_fn: (str) -> List[str]`` callable
injected at construction time.  The caller is responsible for generating the
expanded list (which should include the original query).  This keeps the LC
class framework-neutral — no LlamaIndex LLM calls happen here.

Typical use: the LI wrapper ``SynonymExpanderRetriever`` constructs this class
with an expand_fn that calls ``SynonymExpander.rewrite()`` synchronously.

Results are deduplicated by ``page_content``; only the first occurrence of
each text is kept (order = first-retrieved, so highest-scoring from first
query term wins under standard retriever ordering).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_core.retrievers import BaseRetriever as _LCBase
    from langchain_core.documents import Document as _LCDoc
    from langchain_core.callbacks.manager import (
        CallbackManagerForRetrieverRun,
        AsyncCallbackManagerForRetrieverRun,
    )
    from pydantic import ConfigDict

    class LCSynonymRetriever(_LCBase):
        """Pure LC multi-query retriever driven by an external expand_fn.

        Calls ``expand_fn(query)`` to get all query strings (including the
        original), then invokes the wrapped retriever once per string.
        Deduplicates by ``page_content`` — first occurrence wins.

        Args:
            lc_retriever: The inner LC ``BaseRetriever`` to search with.
            expand_fn:    ``(str) -> List[str]`` — given the original query,
                          returns a list of all query strings to run.
                          Must include the original query if desired.
                          Should be fast / synchronous; run in executor for
                          the async path.
            top_k:        Maximum results to return after deduplication.
            label:        Label for logging.
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def __init__(
            self,
            lc_retriever: Any,
            expand_fn: Callable[[str], List[str]],
            top_k: int = 10,
            label: str = "lc_synonym",
        ) -> None:
            super().__init__()
            self._inner = lc_retriever
            self._expand_fn = expand_fn
            self._top_k = top_k
            self._label = label

        # ------------------------------------------------------------------
        # internal
        # ------------------------------------------------------------------

        def _run_queries(self, queries: List[str]) -> List[_LCDoc]:
            seen: dict = {}  # page_content -> Document
            for q in queries:
                try:
                    docs = self._inner.invoke(q)
                except Exception as e:
                    logger.debug(
                        "LCSynonymRetriever(%s) inner invoke error for '%s': %s",
                        self._label, q[:60], e,
                    )
                    continue
                for doc in docs:
                    text = doc.page_content or ""
                    if text and text not in seen:
                        seen[text] = doc
            return list(seen.values())[: self._top_k]

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
                queries = list(self._expand_fn(query)) or [query]
            except Exception as e:
                logger.warning(
                    "LCSynonymRetriever(%s) expand_fn error: %s", self._label, e
                )
                queries = [query]
            return self._run_queries(queries)

        async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            # expand_fn may call a sync LLM; run in executor to avoid blocking.
            import asyncio
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_relevant_documents(query, run_manager=run_manager),
            )

except ImportError:
    class LCSynonymRetriever:  # type: ignore[no-redef]
        """Stub when ``langchain_core`` is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "langchain_core is required for LCSynonymRetriever. "
                "Install with: uv pip install langchain-core"
            )


__all__ = ["LCSynonymRetriever"]
