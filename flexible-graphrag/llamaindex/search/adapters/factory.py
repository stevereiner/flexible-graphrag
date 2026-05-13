"""llamaindex.search.adapters.factory — dispatch to per-backend adapter classes."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from config import SearchDBType

logger = logging.getLogger(__name__)


def create_search_store(db_type: SearchDBType, config: Dict[str, Any], embed_dim: Optional[int] = None):
    """Instantiate the right :class:`LlamaIndexSearchAdapter` subclass for *db_type*
    and return it.

    Returns ``None`` for ``SearchDBType.NONE``.
    For ``SearchDBType.BM25`` returns a :class:`LlamaIndexBM25SearchAdapter` whose
    BM25 retriever is built lazily via :meth:`~LlamaIndexBM25SearchAdapter.build_retriever`.
    """
    if db_type == SearchDBType.NONE:
        logger.info("Full-text search disabled - no search store created")
        return None

    if db_type == SearchDBType.BM25:
        from llamaindex.search.adapters.bm25_adapter import LlamaIndexBM25SearchAdapter
        return LlamaIndexBM25SearchAdapter(config)

    if db_type == SearchDBType.ELASTICSEARCH:
        from llamaindex.search.adapters.elasticsearch_adapter import LlamaIndexElasticsearchSearchAdapter
        return LlamaIndexElasticsearchSearchAdapter(config, embed_dim)

    if db_type == SearchDBType.OPENSEARCH:
        from llamaindex.search.adapters.opensearch_adapter import LlamaIndexOpenSearchSearchAdapter
        return LlamaIndexOpenSearchSearchAdapter(config, embed_dim)

    raise ValueError(f"Unsupported search database: {db_type}")
