"""
langchain.retriever_bridge
==========================

Bridge classes between LangChain and LlamaIndex retrievers.

LCBackedLIRetriever
    Abstract LlamaIndex BaseRetriever for all LC-backed LI wrappers.
    Subclasses set ``self._lc_retriever`` and get ``as_lc_retriever()``
    and ``_docs_to_nodes()`` for free.

LItoLCRetriever
    LangChain BaseRetriever wrapping any LlamaIndex BaseRetriever.
    Used when an LI-native retriever (VectorIndexRetriever, BM25Retriever,
    PropertyGraphRetriever, etc.) must participate in EnsembleRetriever.
"""
from __future__ import annotations

import logging
from typing import Any, List

from llama_index.core.retrievers import BaseRetriever as _LIBase
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LCBackedLIRetriever — base for all LC -> LI direction wrappers
# ---------------------------------------------------------------------------

class LCBackedLIRetriever(_LIBase):
    """Abstract LI BaseRetriever for wrappers that hold an LC BaseRetriever.

    Subclasses must:
      1. Set ``self._lc_retriever`` to a ``langchain_core`` ``BaseRetriever``
         instance in ``__init__``.
      2. Implement ``_retrieve()`` and optionally ``_aretrieve()``.

    Provided for free:
      - ``lc_retriever`` property — returns the underlying LC retriever.
      - ``as_lc_retriever()`` — returns the LC retriever directly for use
        in ``EnsembleRetriever`` (no shim needed).
      - ``_docs_to_nodes()`` — standard LC Document -> NodeWithScore conversion.
    """

    _lc_retriever: Any = None  # set by subclass __init__

    @property
    def lc_retriever(self) -> Any:
        """The underlying LC BaseRetriever."""
        return self._lc_retriever

    def as_lc_retriever(self) -> Any:
        """Return the LC retriever for direct use in EnsembleRetriever.

        Since ``_lc_retriever`` is already a proper ``langchain_core``
        ``BaseRetriever``, no shim is needed.  Subclasses that do NOT yet
        have an LC counterpart override this to return
        ``LItoLCRetriever(self)`` as a fallback.
        """
        return self._lc_retriever

    def _docs_to_nodes(
        self,
        docs: list,
        fallback_score: float = 0.7,
        source_tag: str = "langchain",
    ) -> List[NodeWithScore]:
        """Convert a list of LC Documents to LI NodeWithScore objects.

        Score resolution order (per document):
          1. ``doc.metadata["score"]`` or ``doc.metadata["relevance_score"]`` (not-None
             check, so a legitimate 0.0 is preserved rather than treated as falsy)
          2. ``getattr(doc, "score", None)``  (some stores attach it directly)
          3. Rank-based decay for multiple docs with no embedded score:
             ``fallback_score - i * 0.05`` (min 0.05) — preserves the ordering signal
             from ranked retrievers (e.g. EnsembleRetriever).
          4. *fallback_score* for single-doc results (e.g. graph QA answer nodes).

        Post-batch normalisation:
          Full-text BM25 engines (Elasticsearch, OpenSearch) return raw TF-IDF scores
          that can exceed 1.0 (e.g. 1.559).  If any raw score in the batch exceeds 1.0
          the entire batch is linearly rescaled to [0, 1] using the batch min/max.
          This prevents BM25 from inflating ``QueryFusionRetriever``'s
          ``relative_score`` denominator and squashing all other retrievers to ~0.
        """
        # --- Pass 1: filter empty docs and compute raw scores ---
        n = len(docs)
        items: list = []  # (text, meta, raw_score)
        for i, doc in enumerate(docs):
            text = doc.page_content or ""
            if not text:
                continue
            meta = dict(doc.metadata or {})
            # Use is-not-None checks so a legitimate 0.0 score is preserved.
            embedded: float | None = None
            for _key in ("score", "relevance_score"):
                _val = meta.get(_key)
                if _val is not None:
                    try:
                        embedded = float(_val)
                        break
                    except (TypeError, ValueError):
                        pass
            if embedded is None:
                _attr = getattr(doc, "score", None)
                if _attr is not None:
                    try:
                        embedded = float(_attr)
                    except (TypeError, ValueError):
                        pass

            if embedded is not None:
                raw = embedded
            elif n > 1:
                raw = max(0.05, fallback_score - i * 0.05)
            else:
                raw = fallback_score

            items.append((text, meta, raw))

        if not items:
            return []

        # --- Pass 2: per-batch normalisation when any score exceeds 1.0 ---
        raw_scores = [r for _, _, r in items]
        if max(raw_scores) > 1.0:
            min_s, max_s = min(raw_scores), max(raw_scores)
            rng = max_s - min_s
            if rng > 0:
                items = [(t, m, (s - min_s) / rng) for t, m, s in items]
            else:
                items = [(t, m, 1.0) for t, m, _ in items]

        # --- Pass 3: build NodeWithScore objects ---
        nodes: List[NodeWithScore] = []
        for text, meta, score in items:
            meta.setdefault("source_framework", source_tag)
            nodes.append(
                NodeWithScore(node=TextNode(text=text, metadata=meta), score=score)
            )
        return nodes


# ---------------------------------------------------------------------------
# LItoLCRetriever — LI -> LC direction wrapper (for EnsembleRetriever)
# ---------------------------------------------------------------------------

try:
    from langchain_core.retrievers import BaseRetriever as _LCBase
    from langchain_core.documents import Document as _LCDoc
    from langchain_core.callbacks.manager import (
        CallbackManagerForRetrieverRun,
        AsyncCallbackManagerForRetrieverRun,
    )
    from pydantic import ConfigDict

    class LItoLCRetriever(_LCBase):  # type: ignore[no-redef]
        """LC BaseRetriever that wraps any LI BaseRetriever.

        Enables LI-native retrievers (``VectorIndexRetriever``,
        ``BM25Retriever``, ``PropertyGraphRetriever``, etc.) to participate
        in LangChain's ``EnsembleRetriever`` by translating the LC retrieval
        interface to the LI ``retrieve()`` / ``aretrieve()`` interface.

        Args:
            li_retriever: Any LlamaIndex ``BaseRetriever`` instance.
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def __init__(self, li_retriever: _LIBase):
            super().__init__()
            self._li = li_retriever

        def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            nodes = self._li.retrieve(QueryBundle(query_str=query))
            return [
                _LCDoc(
                    page_content=n.text or "",
                    metadata={**n.metadata, "_li_score": n.score or 0.0},
                )
                for n in nodes
                if n.text
            ]

        async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            nodes = await self._li.aretrieve(QueryBundle(query_str=query))
            return [
                _LCDoc(
                    page_content=n.text or "",
                    metadata={**n.metadata, "_li_score": n.score or 0.0},
                )
                for n in nodes
                if n.text
            ]

except ImportError:
    class LItoLCRetriever:  # type: ignore[no-redef]
        """Stub when ``langchain_core`` is not installed."""

        def __init__(self, li_retriever: Any):
            raise ImportError(
                "langchain_core is required for LItoLCRetriever. "
                "Install with: uv pip install langchain-core"
            )


__all__ = ["LCBackedLIRetriever", "LItoLCRetriever"]
