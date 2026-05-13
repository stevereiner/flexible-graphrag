"""LangChain Elasticsearch search store adapter.

Wraps ``langchain_elasticsearch.ElasticsearchStore`` for full-text / hybrid
retrieval.  The underlying ES client connects lazily on first use.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.search.search_store_adapter import LangChainSearchAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_elasticsearch import ElasticsearchStore
    from langchain_elasticsearch import BM25RetrievalStrategy
    _ES_AVAILABLE = True
except ImportError:
    _ES_AVAILABLE = False


class ElasticsearchSearchAdapter(LangChainSearchAdapter):
    """Full-text search adapter backed by Elasticsearch.

    Uses ``BM25RetrievalStrategy`` so no embedding model is required for
    the search store.  Dense vector retrieval is handled by the separate
    vector store.

    Configuration keys
    ------------------
    url          ES endpoint (default ``http://localhost:9200``)
    index_name   ES index to read/write (default ``hybrid_search_fulltext``)
    username     Basic-auth username (optional)
    password     Basic-auth password (optional)
    api_key      API key (optional, overrides username/password)
    """

    def __init__(self, config: Dict[str, Any], delete_key: str = "ref_doc_id"):
        if not _ES_AVAILABLE:
            raise ImportError(
                "langchain-elasticsearch required. Install: pip install langchain-elasticsearch"
            )
        self._index_name = config.get("index_name", "hybrid_search_fulltext")
        store = ElasticsearchStore(
            es_url=config.get("url", "http://localhost:9200"),
            index_name=self._index_name,
            es_user=config.get("username"),
            es_password=config.get("password"),
            strategy=BM25RetrievalStrategy(),
        )
        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "ElasticsearchSearchAdapter: index=%s at %s (BM25)",
            config.get("index_name", "hybrid_search_fulltext"),
            config.get("url", "http://localhost:9200"),
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete documents where ``ref_doc_id`` matches via ES delete-by-query."""
        if self._store is None:
            return
        try:
            # ElasticsearchStore exposes the underlying sync client as .client
            # and the index name as .index_name — use delete_by_query directly.
            es_client = getattr(self._store, "client", None)
            index_name = self._index_name  # set from config at __init__, always correct
            if es_client is not None:
                # Build a broad query that matches the ref_doc_id across both
                # 'ref_doc_id' and 'doc_id' metadata keys, and using both term
                # (requires keyword mapping) and match_phrase (works on analyzed
                # text fields).  This covers all metadata key conventions and
                # ES mapping styles used by different chunker backends.
                def _field_clauses(field: str) -> list:
                    return [
                        {"term": {f"metadata.{field}": ref_doc_id}},
                        {"term": {f"metadata.{field}.keyword": ref_doc_id}},
                        {"match_phrase": {f"metadata.{field}": ref_doc_id}},
                    ]

                delete_body = {
                    "query": {
                        "bool": {
                            "should": (
                                _field_clauses(self._delete_key)
                                + _field_clauses("doc_id")
                                + _field_clauses("ref_doc_id")
                            ),
                            "minimum_should_match": 1,
                        }
                    }
                }
                logger.debug(
                    "ElasticsearchSearchAdapter delete_by_query index=%s",
                    index_name,
                )
                result = es_client.delete_by_query(
                    index=index_name,
                    body=delete_body,
                    refresh=True,
                )
                deleted = result.get("deleted", 0)
                logger.info(
                    "ElasticsearchSearchAdapter: deleted %d doc(s) for %s=%s",
                    deleted, self._delete_key, ref_doc_id,
                )
                if deleted == 0:
                    logger.warning(
                        "ElasticsearchSearchAdapter: 0 docs deleted for %s=%s — "
                        "check that metadata field is indexed",
                        self._delete_key, ref_doc_id,
                    )
            else:
                logger.warning("ElasticsearchSearchAdapter: no ES client available for delete")
        except Exception as exc:
            logger.warning("ElasticsearchSearchAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["ElasticsearchSearchAdapter", "_ES_AVAILABLE"]
