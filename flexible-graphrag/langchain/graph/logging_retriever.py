"""
LoggingRetriever — per-retriever result logging and noise filtering.

Wraps any LlamaIndex BaseRetriever to:
  - Log result count and previews at INFO level with a configurable label.
  - Filter bare relation-link / MENTIONS triplet strings from graph retriever output
    (prescore_graph=True) so they don't displace real TextChunk results in fusion.
"""

from __future__ import annotations

import logging
import re
from typing import List

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

logger = logging.getLogger(__name__)

_REL_RE = re.compile(r"^[^>\n]+->\s*[A-Z_]+\s*->\s*[^\n]+$")


def _is_graph_noise(txt: str) -> bool:
    """Return True for bare X -> REL -> Y triplet strings and MENTIONS noise."""
    if not txt:
        return False
    if "\n" in txt or len(txt) > 300:
        return False
    return bool(_REL_RE.match(txt))


class LoggingRetriever(BaseRetriever):
    """Wraps a retriever to add per-result logging and graph noise filtering."""

    def __init__(self, inner: BaseRetriever, label: str, prescore_graph: bool = False):
        super().__init__()
        self._inner = inner
        self._label = label
        self._prescore_graph = prescore_graph

    def _postprocess(self, nodes: List[NodeWithScore]) -> List[NodeWithScore]:
        """Filter bare relation links / MENTIONS noise from graph retriever output."""
        if self._prescore_graph:
            kept = [n for n in nodes if not _is_graph_noise((n.text or "").strip())]
            # If all nodes were triplet strings (docstore empty after restart), keep them
            # rather than returning nothing.
            nodes = kept if kept else [n for n in nodes if (n.text or "").strip()]
        return nodes

    def _log_nodes(self, nodes: List[NodeWithScore]) -> None:
        logger.debug("[%s] returned %d nodes", self._label, len(nodes))
        for i, n in enumerate(nodes):
            txt = n.text or ""
            score = n.score or 0.0
            # Short text (entity/triplet strings): show in full.
            # Long text (TextChunk bodies): preview first 3, score-only after.
            if len(txt) <= 200 or i < 3:
                preview = txt[:200].replace("\n", " ")
                logger.debug("  [%s][%d] score=%.3f  %r", self._label, i, score, preview)
            else:
                logger.debug("  [%s][%d] score=%.3f", self._label, i, score)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        nodes = self._inner.retrieve(query_bundle)
        nodes = self._postprocess(nodes)
        self._log_nodes(nodes)
        return nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        # Delegate to async path of inner retriever if available,
        # otherwise run sync in thread executor to stay non-blocking.
        import asyncio

        try:
            nodes = await self._inner.aretrieve(query_bundle)
        except Exception:
            loop = asyncio.get_event_loop()
            nodes = await loop.run_in_executor(None, self._retrieve, query_bundle)
            return nodes
        nodes = self._postprocess(nodes)
        self._log_nodes(nodes)
        return nodes


def wrap_with_logging(
    retriever: BaseRetriever,
    label: str,
    prescore_graph: bool = False,
) -> LoggingRetriever:
    """Wrap *retriever* with LoggingRetriever using *label* for log output."""
    return LoggingRetriever(retriever, label, prescore_graph=prescore_graph)
