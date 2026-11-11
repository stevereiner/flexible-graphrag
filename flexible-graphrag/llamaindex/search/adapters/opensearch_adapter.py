"""LlamaIndex OpenSearch search (fulltext) adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.search.search_store_factory import LlamaIndexSearchAdapter

logger = logging.getLogger(__name__)


class LlamaIndexOpenSearchSearchAdapter(LlamaIndexSearchAdapter):
    """LlamaIndex search adapter backed by OpenSearch (TEXT_SEARCH mode).

    Configuration keys
    ------------------
    url              OpenSearch endpoint (default ``http://localhost:9201``)
    index_name       Index name (default ``hybrid_search_fulltext``)
    embedding_field  Embedding field name (default ``embedding``)
    text_field       Text field name (default ``content``)
    username / password  HTTP basic auth (optional)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.opensearch import OpensearchVectorStore, OpensearchVectorClient

        index_name = config.get("index_name", "hybrid_search_fulltext")
        url = config.get("url", "http://localhost:9201")
        analyzer = config.get("analyzer") or "standard"
        # OpensearchVectorClient's default settings, plus the index's default analyzer (used for the
        # text field when the index is created)
        from adapters.search.analysis import analysis_settings
        settings = {"index": {"knn": True, "knn.algo_param.ef_search": 100}, **(analysis_settings(analyzer) or {})}
        client = OpensearchVectorClient(
            settings=settings,
            endpoint=url,
            index=index_name,
            dim=embed_dim,
            embedding_field=config.get("embedding_field", "embedding"),
            text_field=config.get("text_field", "content"),
            http_auth=(config.get("username"), config.get("password")) if config.get("username") else None,
        )
        store = OpensearchVectorStore(client)
        super().__init__(store)
        logger.info("LlamaIndexOpenSearchSearchAdapter: url=%s index=%s analyzer=%s (TEXT_SEARCH mode)",
                    url, index_name, analyzer)


__all__ = ["LlamaIndexOpenSearchSearchAdapter"]
