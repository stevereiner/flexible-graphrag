"""LlamaIndex Elasticsearch search (BM25 fulltext) adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.search.search_store_factory import LlamaIndexSearchAdapter

logger = logging.getLogger(__name__)


class LlamaIndexElasticsearchSearchAdapter(LlamaIndexSearchAdapter):
    """LlamaIndex search adapter backed by Elasticsearch (BM25 / fulltext).

    Configuration keys
    ------------------
    url              Elasticsearch URL (default ``http://localhost:9200``)
    index_name       Index name (default ``hybrid_search_fulltext``)
    username / password  HTTP basic auth (optional)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.elasticsearch import ElasticsearchStore, AsyncBM25Strategy

        index_name = config.get("index_name", "hybrid_search_fulltext")
        es_url = config.get("url", "http://localhost:9200")
        store = ElasticsearchStore(
            index_name=index_name,
            es_url=es_url,
            es_user=config.get("username"),
            es_password=config.get("password"),
            retrieval_strategy=AsyncBM25Strategy(),
        )
        super().__init__(store)
        logger.info("LlamaIndexElasticsearchSearchAdapter: url=%s index=%s", es_url, index_name)


__all__ = ["LlamaIndexElasticsearchSearchAdapter"]
