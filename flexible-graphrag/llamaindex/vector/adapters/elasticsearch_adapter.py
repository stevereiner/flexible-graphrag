"""LlamaIndex Elasticsearch vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexElasticsearchVectorAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by Elasticsearch (dense vector).

    Configuration keys
    ------------------
    url              Elasticsearch URL (default ``http://localhost:9200``)
    index_name       Index name (default ``hybrid_search_vector``)
    username         HTTP basic auth username (optional)
    password         HTTP basic auth password (optional)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.elasticsearch import ElasticsearchStore, AsyncDenseVectorStrategy

        self._index_name = config.get("index_name", "hybrid_search_vector")
        self._es_url = config.get("url", "http://localhost:9200")
        self._es_user = config.get("username")
        self._es_password = config.get("password")
        store = ElasticsearchStore(
            index_name=self._index_name,
            es_url=self._es_url,
            es_user=self._es_user,
            es_password=self._es_password,
            retrieval_strategy=AsyncDenseVectorStrategy(),
        )
        super().__init__(store)
        logger.info("LlamaIndexElasticsearchVectorAdapter: url=%s index=%s embed_dim=%s",
                    self._es_url, self._index_name, embed_dim)

    def delete(self, ref_doc_id: str) -> None:
        """Delete ES documents matching ref_doc_id via direct HTTP delete-by-query.

        ``ElasticsearchStore.delete()`` is async-only (delegates to ``adelete``),
        which raises ``This event loop is already running`` when called from a sync
        context inside FastAPI.  We use the ``elasticsearch-py`` client directly
        instead, which is synchronous.
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
                            _field_clauses("ref_doc_id")
                            + _field_clauses("doc_id")
                        ),
                        "minimum_should_match": 1,
                    }
                }
            }
            resp = es.delete_by_query(index=self._index_name, body=body, refresh=True)
            deleted = resp.get("deleted", 0) if isinstance(resp, dict) else 0
            if deleted:
                logger.info(
                    "LlamaIndexElasticsearchVectorAdapter: deleted %d doc(s) for ref_doc_id=%s",
                    deleted, ref_doc_id,
                )
            else:
                logger.warning(
                    "LlamaIndexElasticsearchVectorAdapter: 0 docs deleted for ref_doc_id=%s",
                    ref_doc_id,
                )
        except Exception as exc:
            logger.warning("LlamaIndexElasticsearchVectorAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["LlamaIndexElasticsearchVectorAdapter"]
