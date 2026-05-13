"""langchain.graph.retrievers.lc_logging_retriever — Pure-LC logging decorator (Layer 0).

``LCLoggingRetriever`` wraps any ``langchain_core.BaseRetriever`` and adds:
  - ``DEBUG``-level logging of result count after each retrieval call.
  - Optional noise filtering (``prescore_graph=True``) that strips bare
    ``X -> REL -> Y`` triplet strings from graph retriever output before
    they can displace real TextChunk results in fusion.

This is the LC counterpart consumed by ``LoggingRetriever`` (Layer 1).
"""
from __future__ import annotations

import logging
import re
from typing import Any, List

logger = logging.getLogger(__name__)

_REL_RE = re.compile(r"^[^>\n]+->\s*[A-Z_]+\s*->\s*[^\n]+$")


def _is_graph_noise(txt: str) -> bool:
    """Return True for bare ``X -> REL -> Y`` triplet strings."""
    if not txt or "\n" in txt or len(txt) > 300:
        return False
    return bool(_REL_RE.match(txt))


try:
    from langchain_core.retrievers import BaseRetriever as _LCBase
    from langchain_core.documents import Document as _LCDoc
    from langchain_core.callbacks.manager import (
        CallbackManagerForRetrieverRun,
        AsyncCallbackManagerForRetrieverRun,
    )
    from pydantic import ConfigDict

    class LCLoggingRetriever(_LCBase):
        """Pure LC logging + noise-filter decorator.

        Wraps any ``langchain_core.BaseRetriever`` to add per-call DEBUG
        logging and optional graph-noise filtering.

        Args:
            lc_retriever:  The inner LC ``BaseRetriever`` to delegate to.
            label:         Label used in log messages (e.g. ``"bm25"``).
            prescore_graph: When ``True``, bare ``X -> REL -> Y`` triplet
                            strings are filtered from results so they don't
                            displace real text chunks in fusion.
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def __init__(
            self,
            lc_retriever: Any,
            label: str,
            prescore_graph: bool = False,
        ) -> None:
            super().__init__()
            self._inner = lc_retriever
            self._label = label
            self._prescore_graph = prescore_graph

        # ------------------------------------------------------------------
        # internal
        # ------------------------------------------------------------------

        def _filter_noise(self, docs: List[_LCDoc]) -> List[_LCDoc]:
            if not self._prescore_graph:
                return docs
            kept = [d for d in docs if not _is_graph_noise((d.page_content or "").strip())]
            # Keep at least the non-empty docs if everything was noise.
            return kept if kept else [d for d in docs if (d.page_content or "").strip()]

        def _tag_docs(self, docs: List[_LCDoc]) -> List[_LCDoc]:
            """Inject ``_retriever_label`` into each Document's metadata.

            Mirrors the ``LoggingRetriever._postprocess`` tag so that Documents
            flowing through the pure-LC EnsembleRetriever path carry the same
            label as those flowing through the LI ``LItoLCRetriever`` path.
            Uses ``setdefault`` to preserve any label already set by an inner
            retriever (e.g. a nested logging wrapper).
            """
            for doc in docs:
                if doc.metadata is not None:
                    doc.metadata.setdefault("_retriever_label", self._label)
            return docs

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
                docs = self._inner.invoke(query)
            except Exception as e:
                logger.warning(
                    "LCLoggingRetriever(%s) error for '%s': %s",
                    self._label, query[:60], e,
                )
                return []
            docs = self._filter_noise(docs)
            docs = self._tag_docs(docs)
            logger.debug("[%s] returned %d docs", self._label, len(docs))
            return docs

        async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            import asyncio
            try:
                docs = await self._inner.ainvoke(query)
            except NotImplementedError:
                docs = await asyncio.get_event_loop().run_in_executor(
                    None, self._inner.invoke, query
                )
            except Exception as e:
                logger.warning(
                    "LCLoggingRetriever(%s) async error for '%s': %s",
                    self._label, query[:60], e,
                )
                return []
            docs = self._filter_noise(docs)
            docs = self._tag_docs(docs)
            logger.debug("[%s] async returned %d docs", self._label, len(docs))
            return docs

except ImportError:
    class LCLoggingRetriever:  # type: ignore[no-redef]
        """Stub when ``langchain_core`` is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "langchain_core is required for LCLoggingRetriever. "
                "Install with: uv pip install langchain-core"
            )


__all__ = ["LCLoggingRetriever", "_is_graph_noise"]
