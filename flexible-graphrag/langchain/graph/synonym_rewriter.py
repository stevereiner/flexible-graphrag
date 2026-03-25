"""
Synonym Expander — LLM-based query rewriter for hybrid retrieval

Mirrors LlamaIndex's LLMSynonymRetriever behavior but as a pre-processing step
applied *before* selected retrievers in the fusion pipeline, so the retrievers
that benefit most from keyword expansion receive the enriched query.

Classes
-------
    SynonymExpander          — Rewrites a QueryBundle with LLM-generated synonyms.
    SynonymExpanderRetriever — Wraps any BaseRetriever with a SynonymExpander.

Scope control
-------------
``SYNONYM_EXPLODER_SCOPE`` in config / .env is a comma-separated list of retriever
tags, or one of the special values ``all`` / ``none``.

Per-retriever tags:
    llamaindex_vector           — LlamaIndex VectorStoreIndex retriever
    llamaindex_search           — LlamaIndex BM25 / Elasticsearch / OpenSearch
    llamaindex_pg_graph         — LlamaIndex PropertyGraph graph_retriever
    langchain_pg_vector         — LangChain PG vector retriever
    langchain_rdf_graph         — LangChain RDF/SPARQL retriever
    langchain_pg_graph          — LangChain property-graph Cypher QA retriever
    langchain_pg_neighborhood   — PG neighborhood k-hop retriever

Special values:
    all   — SynonymExpanderRetriever wraps the entire QueryFusionRetriever after it
            is built (one LLM call per query, all modalities receive enriched query).
    none  — synonym exploder disabled (same as USE_SYNONYM_EXPLODER=false).

Default: ``langchain_pg_graph,langchain_vector``

The actual scope is enforced in hybrid_system.py at wiring time via
``_maybe_wrap_synonym(retriever, tag)``.  This module only provides the two
building-block classes and is not aware of scope or config.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

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
    """Rewrites a QueryBundle by appending LLM-generated synonyms to custom_embedding_strs.

    The original ``query_str`` is preserved unchanged so LLM-based query generators
    (SPARQL, Cypher text-to-query chains) receive a clean, unmodified question.
    Synonyms are placed in ``custom_embedding_strs`` so vector similarity searches
    benefit from the expanded terms — same pattern as LlamaIndex's LLMSynonymRetriever.

    Args:
        llm:            A LlamaIndex LLM instance (must support ``.complete()``).
        max_keywords:   Maximum number of synonyms to request from the LLM.
        prompt_tmpl:    Optional override for the prompt template.  Must contain
                        ``{max_keywords}`` and ``{query}`` placeholders.
    """

    def __init__(
        self,
        llm: object,
        max_keywords: int = 8,
        prompt_tmpl: Optional[str] = None,
    ):
        self._llm = llm
        self._max_keywords = max_keywords
        self._prompt_tmpl = prompt_tmpl or _DEFAULT_PROMPT

    def rewrite(self, qb: QueryBundle) -> QueryBundle:
        """Return a new QueryBundle with synonyms added to custom_embedding_strs.

        The original ``query_str`` is preserved unchanged so that LLM-based
        query generators (SPARQL, Cypher) receive a clean question.
        Synonyms are placed in ``custom_embedding_strs`` so that vector
        similarity searches (which use that field for embedding) benefit from
        the expanded terms — same pattern as LlamaIndex's LLMSynonymRetriever.

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

        parts = [p.strip() for p in raw.split("^") if p.strip()]

        # Deduplicate case-insensitively; skip any part that is just the original query
        original_lower = qb.query_str.lower()
        unique: List[str] = []
        seen: set = set()
        for p in parts:
            key = p.lower()
            if key not in seen and key != original_lower:
                seen.add(key)
                unique.append(p)

        if not unique:
            logger.debug("SynonymExpander: no synonyms generated for: %s", qb.query_str[:80])
            return qb

        # Keep original query_str clean for LLM query-generators (SPARQL/Cypher).
        # Append synonyms to custom_embedding_strs — used by vector similarity search.
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


class SynonymExpanderRetriever(BaseRetriever):
    """Wraps any BaseRetriever with a SynonymExpander pre-processing step.

    Usage::

        wrapped = SynonymExpanderRetriever(base=hybrid_retriever, expander=expander)

    Args:
        base:     The underlying retriever to delegate to.
        expander: A SynonymExpander instance.
    """

    def __init__(self, base: BaseRetriever, expander: SynonymExpander, **kwargs):
        super().__init__(**kwargs)
        self._base = base
        self._expander = expander

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        rewritten = self._expander.rewrite(query_bundle)
        return self._base._retrieve(rewritten)

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        rewritten = self._expander.rewrite(query_bundle)
        if hasattr(self._base, "_aretrieve"):
            return await self._base._aretrieve(rewritten)
        return self._base._retrieve(rewritten)
