"""
langchain.search.adapters
=========================

One module per LangChain search backend.

Modules
-------
bm25_adapter           BM25SearchAdapter, create_langchain_bm25_adapter
elasticsearch_adapter  ElasticsearchSearchAdapter
opensearch_adapter     OpenSearchSearchAdapter
factory                build_langchain_search_store
"""
from .bm25_adapter import BM25SearchAdapter, create_langchain_bm25_adapter
from .elasticsearch_adapter import ElasticsearchSearchAdapter
from .opensearch_adapter import OpenSearchSearchAdapter
from .factory import build_langchain_search_store

__all__ = [
    "BM25SearchAdapter",
    "create_langchain_bm25_adapter",
    "ElasticsearchSearchAdapter",
    "OpenSearchSearchAdapter",
    "build_langchain_search_store",
]
