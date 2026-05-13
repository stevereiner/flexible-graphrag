"""langchain.graph.retrievers.synonym_rewriter — SynonymExpander utility.

``SynonymExpander`` is a framework-neutral utility that rewrites a
LlamaIndex ``QueryBundle`` by appending LLM-generated synonyms to
``custom_embedding_strs``, leaving ``query_str`` unchanged so SPARQL/Cypher
chains receive a clean, unmodified question.

The LI retriever wrapper (``SynonymExpanderRetriever``) lives in
``li_synonym_retriever.py``.

Scope control
-------------
``SYNONYM_EXPLODER_SCOPE`` in config / .env is a comma-separated list of
retriever tags, or ``all`` / ``none``.  Useful tags:
    llamaindex_vector, llamaindex_search, langchain_pg_vector,
    langchain_pg_neighborhood

    NOTE: Do NOT include langchain_rdf_graph or langchain_pg_graph (graph QA
    chains).  Each synonym expansion triggers a full LLM query-generation +
    answer cycle, producing near-duplicate results and multiplying latency.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from llama_index.core.schema import QueryBundle

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "Given the user query below, generate up to {max_keywords} synonyms or "
    "closely related search keywords that would help retrieve relevant information.\n"
    "Return them as a SINGLE LINE, separated by '^', no extra text or explanation.\n"
    "Keep keywords concise (1-3 words each). Do not repeat the original query words.\n\n"
    "QUERY: {query}\n"
    "KEYWORDS:"
)


class SynonymExpander:
    """Rewrites a QueryBundle by appending LLM-generated synonyms to
    ``custom_embedding_strs``.

    The original ``query_str`` is preserved unchanged so LLM-based query
    generators (SPARQL, Cypher) receive a clean question.  Synonyms are
    placed in ``custom_embedding_strs`` so vector similarity searches benefit
    from the expanded terms — same pattern as LlamaIndex's
    ``LLMSynonymRetriever``.

    Args:
        llm:            A LlamaIndex LLM instance (must support ``.complete()``).
        max_keywords:   Maximum number of synonyms to request.
        prompt_tmpl:    Optional override for the prompt template.  Must
                        contain ``{max_keywords}`` and ``{query}`` placeholders.
    """

    def __init__(
        self,
        llm: object,
        max_keywords: int = 8,
        prompt_tmpl: Optional[str] = None,
    ) -> None:
        self._llm = llm
        self._max_keywords = max_keywords
        self._prompt_tmpl = prompt_tmpl or _DEFAULT_PROMPT

    def rewrite(self, qb: QueryBundle) -> QueryBundle:
        """Return a new QueryBundle with synonyms added to custom_embedding_strs.

        Falls back to the original QueryBundle on any LLM error.
        """
        prompt = self._prompt_tmpl.format(
            max_keywords=self._max_keywords,
            query=qb.query_str,
        )
        try:
            raw: str = self._llm.complete(prompt).text
        except Exception as e:
            logger.warning("SynonymExpander LLM call failed: %s — using original query", e)
            return qb
        return self._build_bundle(qb, raw)

    def _build_bundle(self, qb: QueryBundle, raw: str) -> QueryBundle:
        """Parse raw LLM synonym output into an enriched QueryBundle."""
        parts = [p.strip() for p in raw.split("^") if p.strip()]
        original_lower = qb.query_str.lower()
        unique: List[str] = []
        seen: set = set()
        for p in parts:
            key = p.lower()
            if key not in seen and key != original_lower:
                seen.add(key)
                unique.append(p)

        if not unique:
            logger.debug(
                "SynonymExpander: no synonyms generated for: %s", qb.query_str[:80]
            )
            return qb

        existing_embedding_strs = list(qb.custom_embedding_strs or [qb.query_str])
        enriched_embedding_strs = existing_embedding_strs + unique

        logger.debug(
            "SynonymExpander: '%s' -> %d keywords: %s",
            qb.query_str[:60],
            len(unique),
            " | ".join(unique),
        )
        return QueryBundle(
            query_str=qb.query_str,
            custom_embedding_strs=enriched_embedding_strs,
            embedding=qb.embedding,
        )


__all__ = ["SynonymExpander"]
