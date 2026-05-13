"""langchain.graph.retrievers.li_synonym_retriever — LI wrapper (Layer 1).

``SynonymExpanderRetriever`` wraps any LI ``BaseRetriever`` with a
``SynonymExpander`` pre-processing step.  Before each retrieval call,
``SynonymExpander.rewrite()`` appends LLM-generated synonyms to
``QueryBundle.custom_embedding_strs`` (leaving ``query_str`` unchanged for
SPARQL/Cypher chains).

``as_lc_retriever()`` constructs an ``LCSynonymRetriever`` wrapping the
inner retriever's LC counterpart (when available), so synonym expansion
also happens at the LC layer for ``EnsembleRetriever`` use.
"""
from __future__ import annotations

import logging
from typing import Any, List

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

logger = logging.getLogger(__name__)


class SynonymExpanderRetriever(BaseRetriever):
    """Wraps any BaseRetriever with a SynonymExpander pre-processing step.

    Usage::

        wrapped = SynonymExpanderRetriever(base=hybrid_retriever, expander=expander)

    Args:
        base:     The underlying retriever to delegate to.
        expander: A ``SynonymExpander`` instance.
    """

    def as_lc_retriever(self) -> Any:
        """Return an LC retriever for EnsembleRetriever integration.

        When the inner retriever exposes an LC counterpart, wraps it in an
        ``LCSynonymRetriever`` so synonym expansion also happens at the LC
        layer.  Falls back to an ``LItoLCRetriever`` shim otherwise.
        """
        _fn = getattr(self._base, "as_lc_retriever", None)
        if _fn is not None:
            from langchain.graph.retrievers.lc_synonym_retriever import LCSynonymRetriever
            _expander = self._expander

            def _expand_fn(query: str) -> List[str]:
                from llama_index.core.schema import QueryBundle as QB
                qb = _expander.rewrite(QB(query_str=query))
                return list(qb.custom_embedding_strs or [query])

            return LCSynonymRetriever(
                lc_retriever=_fn(),
                expand_fn=_expand_fn,
                label="lc_synonym",
            )
        from langchain.retriever_bridge import LItoLCRetriever
        return LItoLCRetriever(self)

    def __init__(self, base: BaseRetriever, expander: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base = base
        self._expander = expander

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        rewritten = self._expander.rewrite(query_bundle)
        return self._base._retrieve(rewritten)

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        prompt = self._expander._prompt_tmpl.format(
            max_keywords=self._expander._max_keywords,
            query=query_bundle.query_str,
        )
        try:
            response = await self._expander._llm.acomplete(prompt)
            rewritten = self._expander._build_bundle(query_bundle, response.text)
        except Exception as e:
            logger.debug(
                "SynonymExpander async rewrite failed: %s — using original query", e
            )
            rewritten = query_bundle
        if hasattr(self._base, "_aretrieve"):
            return await self._base._aretrieve(rewritten)
        return self._base._retrieve(rewritten)


__all__ = ["SynonymExpanderRetriever"]
