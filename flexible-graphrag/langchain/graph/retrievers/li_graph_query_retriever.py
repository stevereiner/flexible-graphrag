"""
langchain.graph.retrievers.li_graph_query_retriever
===================================================

Layer-1 LlamaIndex wrapper around LCGraphQARetriever.

GraphQueryRetriever
    Thin LI BaseRetriever that wraps an LCGraphQARetriever and converts
    LC Documents -> LI NodeWithScore.  All chain logic (prompts, schema
    cleaning, query sanitizers) lives in ``lc_graph_retriever.py`` and
    ``chains/_*.py``.

    Exposes ``as_lc_retriever()`` (via LCBackedLIRetriever) so it can
    participate directly in LangChain's EnsembleRetriever.

TextToGraphQueryRetriever
    Backward-compat alias for GraphQueryRetriever.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from llama_index.core.schema import NodeWithScore, QueryBundle

from langchain.retriever_bridge import LCBackedLIRetriever
from langchain.graph.retrievers.lc_graph_retriever import (
    LCGraphQARetriever,
    _build_qa_chain,
)

logger = logging.getLogger(__name__)


class GraphQueryRetriever(LCBackedLIRetriever):
    """LI BaseRetriever backed by an LCGraphQARetriever.

    Converts LC Documents to LI NodeWithScore.  Full chain and formatting
    logic lives in ``LCGraphQARetriever``.

    Args:
        langchain_graph:           Any LangChain graph store object.
        llm:                       LangChain LLM for query generation.
        qa_chain_factory:          Optional callable ``(graph, llm) -> chain``
                                   to override auto-detection.
        top_k:                     Maximum result nodes to return.
        include_intermediate_steps: Surface intermediate chain steps as
                                    additional context nodes.
        source_files:              File names to embed in result metadata
                                   for source attribution in the UI.
    """

    def __init__(
        self,
        langchain_graph: Any,
        llm: Any,
        qa_chain_factory: Optional[Any] = None,
        top_k: int = 5,
        include_intermediate_steps: bool = True,
        source_files: Optional[List[str]] = None,
        config: Any = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if qa_chain_factory is not None:
            chain = qa_chain_factory(langchain_graph, llm)
            self._lc_retriever = LCGraphQARetriever(
                chain=chain,
                graph=langchain_graph,
                top_k=top_k,
                include_intermediate=include_intermediate_steps,
                source_files=source_files,
            )
        else:
            self._lc_retriever = LCGraphQARetriever.from_graph(
                graph=langchain_graph,
                llm=llm,
                top_k=top_k,
                include_intermediate_steps=include_intermediate_steps,
                source_files=source_files,
                config=config,
            )
        logger.info(
            "GraphQueryRetriever ready for graph '%s'",
            type(langchain_graph).__name__,
        )

    # ------------------------------------------------------------------
    # LI retrieval interface
    # ------------------------------------------------------------------

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        try:
            docs = self._lc_retriever.invoke(query_bundle.query_str)
        except Exception as exc:
            logger.error("GraphQueryRetriever._retrieve error: %s", exc, exc_info=True)
            return []
        nodes = self._docs_to_nodes(docs, fallback_score=1.0, source_tag="langchain_graph")
        self._apply_intermediate_scores(nodes)
        return nodes[: self._lc_retriever._top_k]

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        try:
            docs = await self._lc_retriever.ainvoke(query_bundle.query_str)
        except Exception as exc:
            logger.error("GraphQueryRetriever._aretrieve error: %s", exc, exc_info=True)
            return []
        nodes = self._docs_to_nodes(docs, fallback_score=1.0, source_tag="langchain_graph")
        self._apply_intermediate_scores(nodes)
        return nodes[: self._lc_retriever._top_k]

    @staticmethod
    def _apply_intermediate_scores(nodes: List[NodeWithScore]) -> None:
        """Override score for intermediate-step nodes stored in metadata."""
        for nws in nodes:
            cached = nws.node.metadata.get("_intermediate_score")
            if cached is not None:
                nws.score = float(cached)


# Backward-compat alias — existing code using TextToGraphQueryRetriever still works.
TextToGraphQueryRetriever = GraphQueryRetriever

__all__ = ["GraphQueryRetriever", "TextToGraphQueryRetriever"]
