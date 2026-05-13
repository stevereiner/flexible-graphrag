"""langchain.graph.retrievers.li_logging_retriever — LI wrapper (Layer 1).

``LoggingRetriever`` is the LI ``BaseRetriever`` decorator that adds
per-retrieval DEBUG logging and optional graph-noise filtering.

It delegates noise detection to the shared ``_is_graph_noise`` helper from
``lc_logging_retriever.py`` (Layer 0).

``as_lc_retriever()`` constructs an ``LCLoggingRetriever`` wrapping the
inner retriever's LC counterpart (when available), preserving logging and
noise filtering at the LC layer too.
"""
from __future__ import annotations

import logging
from typing import Any, List

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

from langchain.graph.retrievers.lc_logging_retriever import _is_graph_noise  # noqa: F401

logger = logging.getLogger(__name__)


class LoggingRetriever(BaseRetriever):
    """LI decorator adding per-result logging and graph noise filtering.

    ``as_lc_retriever()`` wraps the inner retriever's LC counterpart in an
    ``LCLoggingRetriever`` so the same behaviour is available in the
    EnsembleRetriever path.

    Args:
        inner:          The underlying retriever to decorate.
        label:          Label for log messages (e.g. ``"vector"``).
        prescore_graph: When ``True``, bare ``X -> REL -> Y`` triplet
                        strings are filtered so they don't displace real
                        text chunks in fusion.
    """

    def as_lc_retriever(self) -> Any:
        """Return an LC retriever for EnsembleRetriever integration.

        When the inner retriever is truly LC-backed (has its own as_lc_retriever),
        returns an LCLoggingRetriever wrapping it.
        For LI-native inner retrievers, wraps self in LItoLCRetriever so that
        RETRIEVAL_FUSION=langchain EnsembleRetriever can consume any retriever.
        """
        _fn = getattr(self._inner, "as_lc_retriever", None)
        if _fn is not None:
            from langchain.graph.retrievers.lc_logging_retriever import LCLoggingRetriever
            return LCLoggingRetriever(
                lc_retriever=_fn(),
                label=self._label,
                prescore_graph=self._prescore_graph,
            )
        from langchain.retriever_bridge import LItoLCRetriever
        return LItoLCRetriever(self)

    def __init__(
        self,
        inner: BaseRetriever,
        label: str,
        prescore_graph: bool = False,
    ) -> None:
        super().__init__()
        self._inner = inner
        self._label = label
        self._prescore_graph = prescore_graph

    def _postprocess(self, nodes: List[NodeWithScore]) -> List[NodeWithScore]:
        if self._prescore_graph:
            kept = [n for n in nodes if not _is_graph_noise((n.text or "").strip())]
            nodes = kept if kept else [n for n in nodes if (n.text or "").strip()]
        # Always tag nodes with _retriever_label so query_engine.py can append DB type
        # to the source display (e.g. "company-ontology-test.txt | Qdrant vector").
        for n in nodes:
            if n.node and n.node.metadata is not None:
                n.node.metadata.setdefault("_retriever_label", self._label)
        return nodes

    def _log_nodes(self, nodes: List[NodeWithScore]) -> None:
        scores = [n.score or 0.0 for n in nodes]
        if scores:
            score_summary = f"scores=[{', '.join(f'{s:.3f}' for s in scores[:5])}{'...' if len(scores) > 5 else ''}]"
        else:
            score_summary = "scores=[]"
        logger.info("[%s] returned %d nodes  %s", self._label, len(nodes), score_summary)
        for i, n in enumerate(nodes):
            txt = n.text or ""
            score = n.score or 0.0
            if len(txt) <= 200 or i < 3:
                preview = txt[:200].replace("\n", " ")
                logger.debug(
                    "  [%s][%d] score=%.3f  %r", self._label, i, score, preview
                )
            else:
                logger.debug("  [%s][%d] score=%.3f", self._label, i, score)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        nodes = self._inner.retrieve(query_bundle)
        nodes = self._postprocess(nodes)
        self._log_nodes(nodes)
        return nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        nodes = await self._inner.aretrieve(query_bundle)
        nodes = self._postprocess(nodes)
        self._log_nodes(nodes)
        return nodes


def wrap_with_logging(
    retriever: BaseRetriever,
    label: str,
    prescore_graph: bool = False,
) -> LoggingRetriever:
    """Wrap *retriever* with ``LoggingRetriever`` using *label* for log output."""
    return LoggingRetriever(retriever, label, prescore_graph=prescore_graph)


__all__ = ["LoggingRetriever", "wrap_with_logging"]
