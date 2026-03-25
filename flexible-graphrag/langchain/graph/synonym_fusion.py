"""
SynonymFusion — builds a SynonymExpander and provides per-retriever wrapping helpers.

Extracted from HybridSearchSystem._setup_hybrid_retriever so that hybrid_system.py
stays focused on orchestration rather than retriever infrastructure.

Usage in _setup_hybrid_retriever:
    from langchain.graph.synonym_fusion import SynonymFusion

    fusion = SynonymFusion.from_config(config, llm)
    # wrap individual retrievers by tag:
    wrapped = fusion.wrap(retriever, "langchain_rdf_graph")
    # wrap the entire fusion retriever (scope=all):
    if fusion.is_all:
        hybrid_retriever = fusion.wrap_all(hybrid_retriever)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from llama_index.core.retrievers import BaseRetriever

if TYPE_CHECKING:
    from config import AppSettings

logger = logging.getLogger(__name__)


class SynonymFusion:
    """Holds a SynonymExpander and the active tag scope parsed from config."""

    def __init__(
        self,
        expander,                   # SynonymExpander | None
        active_tags: set,
        is_all: bool,
        is_none: bool,
    ):
        self._expander = expander
        self._active_tags = active_tags
        self.is_all = is_all
        self.is_none = is_none

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: "AppSettings", llm) -> "SynonymFusion":
        """Build a SynonymFusion from AppSettings.

        Returns a no-op instance when use_synonym_exploder is False or scope=none.
        """
        scope_raw = (
            getattr(config, "synonym_exploder_scope", "") or "langchain_pg_graph,langchain_pg_vector"
        ).strip().lower()

        is_all = scope_raw == "all"
        is_none = scope_raw in ("none", "")

        if not getattr(config, "use_synonym_exploder", False) or is_none:
            return cls(None, set(), is_all=False, is_none=True)

        if llm is None:
            logger.warning("use_synonym_exploder=true but llm not set — skipping SynonymExpander")
            return cls(None, set(), is_all=False, is_none=True)

        try:
            from langchain.graph.synonym_rewriter import SynonymExpander

            expander = SynonymExpander(
                llm=llm,
                max_keywords=int(getattr(config, "synonym_exploder_max_keywords", 8)),
            )
            active_tags: set = set() if is_all else {t.strip() for t in scope_raw.split(",") if t.strip()}
            logger.info(
                "SynonymExpander ready (scope=%s, tags=%s)",
                scope_raw,
                active_tags if not is_all else "ALL",
            )
            return cls(expander, active_tags, is_all=is_all, is_none=False)
        except Exception as e:
            logger.warning("Failed to build SynonymExpander: %s", e)
            return cls(None, set(), is_all=False, is_none=True)

    # ------------------------------------------------------------------
    # Wrapping helpers
    # ------------------------------------------------------------------

    def wrap(self, retriever: BaseRetriever, tag: str) -> BaseRetriever:
        """Wrap *retriever* with SynonymExpanderRetriever if *tag* is in the active scope.

        When scope=all, individual wrapping is skipped — wrap_all() is used instead
        after the QueryFusionRetriever is assembled.
        """
        if self._expander is None or self.is_all:
            return retriever
        if tag in self._active_tags:
            from langchain.graph.synonym_rewriter import SynonymExpanderRetriever

            return SynonymExpanderRetriever(base=retriever, expander=self._expander)
        return retriever

    def wrap_all(self, retriever: BaseRetriever) -> BaseRetriever:
        """Wrap the assembled fusion retriever when scope=all."""
        if not self.is_all or self._expander is None:
            return retriever
        try:
            from langchain.graph.synonym_rewriter import SynonymExpanderRetriever

            wrapped = SynonymExpanderRetriever(base=retriever, expander=self._expander)
            logger.info("Wrapped hybrid retriever with SynonymExpander (scope=all)")
            return wrapped
        except Exception as e:
            logger.warning("Failed to apply SynonymExpander (scope=all): %s", e)
            return retriever
