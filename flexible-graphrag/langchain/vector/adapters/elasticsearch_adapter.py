"""LangChain Elasticsearch vector store adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_elasticsearch import ElasticsearchStore as LCElastic
    _ES_AVAILABLE = True
except ImportError:
    _ES_AVAILABLE = False


class ElasticsearchVectorAdapter(LangChainVectorAdapter):
    """Dense vector store adapter backed by Elasticsearch.

    Configuration keys
    ------------------
    url          ES endpoint (default ``http://localhost:9200``)
    index_name   Index (default ``hybrid_search_vector``)
    username     Basic-auth username (optional)
    password     Basic-auth password (optional)
    embedding    LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _ES_AVAILABLE:
            raise ImportError(
                "langchain-elasticsearch required. Install: pip install langchain-elasticsearch"
            )
        self._es_url = config.get("url", "http://localhost:9200")
        self._index_name = config.get("index_name", "hybrid_search_vector")
        self._es_user = config.get("username")
        self._es_password = config.get("password")
        store = LCElastic(
            es_url=self._es_url,
            index_name=self._index_name,
            es_user=self._es_user,
            es_password=self._es_password,
            embedding=embedding,
        )
        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "ElasticsearchVectorAdapter: index=%s at %s",
            self._index_name,
            self._es_url,
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete ES documents matching ref_doc_id via delete-by-query.

        ``ElasticsearchStore.delete()`` requires internal document IDs, not a
        metadata filter.  Use the ``elasticsearch-py`` client directly instead.
        """
        try:
            from elasticsearch import Elasticsearch

            auth = (self._es_user, self._es_password) if self._es_user else None
            es = Elasticsearch(self._es_url, basic_auth=auth)

            def _field_clauses(field: str) -> list:
                return [
                    {"term": {f"metadata.{field}": ref_doc_id}},
                    {"term": {f"metadata.{field}.keyword": ref_doc_id}},
                    {"match_phrase": {f"metadata.{field}": ref_doc_id}},
                ]

            body = {
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
            resp = es.delete_by_query(index=self._index_name, body=body, refresh=True)
            deleted = resp.get("deleted", 0) if isinstance(resp, dict) else 0
            if deleted:
                logger.info(
                    "ElasticsearchVectorAdapter: deleted %d doc(s) for ref_doc_id=%s",
                    deleted, ref_doc_id,
                )
            else:
                logger.warning(
                    "ElasticsearchVectorAdapter: 0 docs deleted for ref_doc_id=%s",
                    ref_doc_id,
                )
        except Exception as exc:
            logger.warning("ElasticsearchVectorAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["ElasticsearchVectorAdapter", "_ES_AVAILABLE"]
