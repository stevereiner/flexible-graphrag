"""
LangChain graph retrieval components.

Exports the wrapper that adapts LangChain graph QA chains for use
inside LlamaIndex's QueryFusionRetriever, and the factory that builds
it from an AppSettings config object.
"""

from .retrievers.li_graph_query_retriever import GraphQueryRetriever, TextToGraphQueryRetriever
from .retrievers.lc_graph_retriever import LCGraphQARetriever
from .pg_retriever_factory import build_langchain_pg_retriever, build_langchain_pg_vector_retriever
from .retrievers.li_neo4j_vector_retriever import GraphEntityVectorRetriever
from .retrievers.li_logging_retriever import LoggingRetriever, wrap_with_logging
from .retrievers.synonym_fusion import SynonymFusion
from .pg_store_adapter import LangChainPGAdapter, _build_lc_graph
# ABC + factory — canonical home is adapters.graph.pg_store_adapter
from adapters.graph.pg_store_adapter import (
    PropertyGraphStoreAdapter,
    build_pg_store_adapter,
    nodes_to_graph_documents,
)
# RDF adapters — canonical home is adapters.graph.rdf_store_adapter
from adapters.graph.rdf_store_adapter import (
    RdfGraphStoreAdapter,
    FusekiGraphAdapter,
    OxigraphGraphAdapter,
    OntotextGraphAdapter,
    build_rdf_store_adapter,
)

__all__ = [
    "GraphQueryRetriever",
    "LCGraphQARetriever",
    "TextToGraphQueryRetriever",
    "build_langchain_pg_retriever",
    "build_langchain_pg_vector_retriever",
    "GraphEntityVectorRetriever",
    "LoggingRetriever",
    "wrap_with_logging",
    "SynonymFusion",
    "LangChainPGAdapter",
    "_build_lc_graph",
    "PropertyGraphStoreAdapter",
    "build_pg_store_adapter",
    "nodes_to_graph_documents",
    "RdfGraphStoreAdapter",
    "FusekiGraphAdapter",
    "OxigraphGraphAdapter",
    "OntotextGraphAdapter",
    "build_rdf_store_adapter",
]
