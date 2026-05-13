"""llamaindex.search.adapters — per-backend LlamaIndex search adapter classes."""
from .factory import create_search_store
from .bm25_adapter import LlamaIndexBM25SearchAdapter
from .elasticsearch_adapter import LlamaIndexElasticsearchSearchAdapter
from .opensearch_adapter import LlamaIndexOpenSearchSearchAdapter

__all__ = [
    "create_search_store",
    "LlamaIndexBM25SearchAdapter",
    "LlamaIndexElasticsearchSearchAdapter",
    "LlamaIndexOpenSearchSearchAdapter",
]
