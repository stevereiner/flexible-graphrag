"""
langchain.graph.retrievers
==========================

Two-layer retriever architecture.

Layer 0 — pure LC (``langchain_core.BaseRetriever``):
    lc_graph_retriever.py          LCGraphQARetriever
    lc_neighborhood_retriever.py   LCNeighborhoodRetriever
    lc_neo4j_vector_retriever.py   LCNeo4jVectorRetriever
    lc_synonym_retriever.py        LCSynonymRetriever
    lc_logging_retriever.py        LCLoggingRetriever
    chains/_*.py                   Per-language chain builders

Layer 1 — LI wrappers (``LCBackedLIRetriever`` / ``BaseRetriever`` +
          ``as_lc_retriever()``):
    li_graph_query_retriever.py    GraphQueryRetriever / TextToGraphQueryRetriever
    li_neo4j_vector_retriever.py   GraphEntityVectorRetriever
    li_neighborhood_retriever.py   GraphNeighborhoodRetriever
    li_synonym_retriever.py        SynonymExpanderRetriever
    li_logging_retriever.py        LoggingRetriever, wrap_with_logging
    synonym_rewriter.py            SynonymExpander (standalone utility)
    synonym_fusion.py              SynonymFusion

Bridge (langchain/retriever_bridge.py):
    LCBackedLIRetriever — ABC for all Layer-1 wrappers holding an LC retriever
    LItoLCRetriever     — wraps any LI retriever as a proper LC BaseRetriever
"""

# ── Layer 1: LI wrappers ──────────────────────────────────────────────────
from .li_graph_query_retriever import GraphQueryRetriever, TextToGraphQueryRetriever
from .li_neo4j_vector_retriever import GraphEntityVectorRetriever
from .li_neighborhood_retriever import GraphNeighborhoodRetriever
from .li_synonym_retriever import SynonymExpanderRetriever
from .li_logging_retriever import LoggingRetriever, wrap_with_logging
from .synonym_rewriter import SynonymExpander
from .synonym_fusion import SynonymFusion

# ── Layer 0: pure LC retrievers ───────────────────────────────────────────
from .lc_graph_retriever import LCGraphQARetriever, detect_query_type
from .lc_neighborhood_retriever import LCNeighborhoodRetriever
from .lc_neo4j_vector_retriever import LCNeo4jVectorRetriever
from .lc_synonym_retriever import LCSynonymRetriever
from .lc_logging_retriever import LCLoggingRetriever, _is_graph_noise

__all__ = [
    # Layer 1 — graph query
    "GraphQueryRetriever",
    "TextToGraphQueryRetriever",  # backward-compat alias
    # Layer 1 — other
    "GraphEntityVectorRetriever",
    "GraphNeighborhoodRetriever",
    "SynonymExpander",
    "SynonymExpanderRetriever",
    "SynonymFusion",
    "LoggingRetriever",
    "wrap_with_logging",
    # Layer 0 — pure LC
    "LCGraphQARetriever",
    "detect_query_type",
    "LCNeighborhoodRetriever",
    "LCNeo4jVectorRetriever",
    "LCSynonymRetriever",
    "LCLoggingRetriever",
    "_is_graph_noise",
]
