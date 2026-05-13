"""langchain.search — LangChain search store implementations (ES, OpenSearch, BM25).

Structure
---------
lc_search_retriever     LCSearchRetriever (Layer 0, pure LC)
lc_retriever_wrapper    LangChainRetrieverWrapper (Layer 1, LI wrapper)
search_store_adapter    LangChainSearchAdapter (base)
retriever               LangChainSearchRetriever (LlamaIndex BaseRetriever)
adapters/
  bm25_adapter          BM25SearchAdapter, create_langchain_bm25_adapter
  elasticsearch_adapter ElasticsearchSearchAdapter
  opensearch_adapter    OpenSearchSearchAdapter
  factory               build_langchain_search_store
"""
from .lc_search_retriever import LCSearchRetriever
from .li_search_retriever import LangChainRetrieverWrapper
from .search_store_adapter import LangChainSearchAdapter
from .retriever import LangChainSearchRetriever
from .adapters.bm25_adapter import BM25SearchAdapter, create_langchain_bm25_adapter
from .adapters.elasticsearch_adapter import ElasticsearchSearchAdapter
from .adapters.opensearch_adapter import OpenSearchSearchAdapter
from .adapters.factory import build_langchain_search_store
from langchain.utils import llamaindex_nodes_to_langchain_docs
from adapters.search.search_store_adapter import SearchStoreAdapter

__all__ = [
    # base
    "SearchStoreAdapter",
    "LangChainSearchAdapter",
    # per-backend adapters
    "BM25SearchAdapter",
    "ElasticsearchSearchAdapter",
    "OpenSearchSearchAdapter",
    # retrievers (Layer 0 + Layer 1)
    "LCSearchRetriever",
    "LangChainRetrieverWrapper",
    "LangChainSearchRetriever",
    # helpers / factories
    "create_langchain_bm25_adapter",
    "llamaindex_nodes_to_langchain_docs",
    "build_langchain_search_store",
]
