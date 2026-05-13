"""Factory for LangChain search store adapters.

Routes a ``SearchDBType`` + config dict to the correct
:class:`~adapters.search.search_store_adapter.SearchStoreAdapter` subclass.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from adapters.search.search_store_adapter import SearchStoreAdapter

logger = logging.getLogger(__name__)


def build_langchain_search_store(
    db_type,
    config: Dict[str, Any],
    app_config=None,
    delete_key: str = "ref_doc_id",
) -> SearchStoreAdapter:
    """Instantiate the right LangChain search adapter for *db_type*.

    Parameters
    ----------
    db_type:
        A :class:`~config.SearchDBType` value.
    config:
        Backend-specific connection dict (url, index_name, username, …).
    app_config:
        Optional ``AppSettings`` object; used to read BM25 parameters
        (``bm25_similarity_top_k``, ``bm25_persist_dir``) and embedding config.
    delete_key:
        Metadata field used to identify docs on delete (default ``ref_doc_id``).
    """
    from config import SearchDBType

    if db_type == SearchDBType.BM25:
        from langchain.search.adapters.bm25_adapter import BM25SearchAdapter

        k = getattr(app_config, "bm25_similarity_top_k", 10) if app_config else 10
        persist_dir = getattr(app_config, "bm25_persist_dir", None) if app_config else None
        logger.info("build_langchain_search_store: BM25 (k=%d, persist_dir=%s)", k, persist_dir)
        return BM25SearchAdapter(k=k, persist_dir=persist_dir)

    if db_type == SearchDBType.ELASTICSEARCH:
        from langchain.search.adapters.elasticsearch_adapter import ElasticsearchSearchAdapter

        return ElasticsearchSearchAdapter(config, delete_key=delete_key)

    if db_type == SearchDBType.OPENSEARCH:
        from langchain.search.adapters.opensearch_adapter import OpenSearchSearchAdapter
        from langchain.llm.embedding_factory import build_lc_embedding

        lc_embedding = build_lc_embedding(app_config) if app_config else None
        return OpenSearchSearchAdapter(config, embedding=lc_embedding, delete_key=delete_key)

    raise NotImplementedError(
        f"LangChain search adapter not implemented for db_type='{db_type}'. "
        "Use search_backend='llamaindex' for this store type."
    )


__all__ = ["build_langchain_search_store"]
