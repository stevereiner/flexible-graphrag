"""LangChain OpenSearch search store adapter.

Wraps ``langchain_community.vectorstores.OpenSearchVectorSearch`` for
full-text / hybrid retrieval against an OpenSearch cluster.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.search.search_store_adapter import LangChainSearchAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_community.vectorstores import OpenSearchVectorSearch
    _OPENSEARCH_AVAILABLE = True
except ImportError:
    _OPENSEARCH_AVAILABLE = False


class OpenSearchSearchAdapter(LangChainSearchAdapter):
    """Full-text / dense search adapter backed by OpenSearch.

    Uses KNN vector search for retrieval; embedding is required for ingestion.
    Dense vector retrieval is handled by the separate vector store.

    Configuration keys
    ------------------
    url          OpenSearch endpoint (default ``http://localhost:9201``)
    index_name   Index to read/write (default ``hybrid_search_fulltext``)
    username     Basic-auth username (optional)
    password     Basic-auth password (optional)
    """

    def __init__(self, config: Dict[str, Any], embedding=None, delete_key: str = "ref_doc_id"):
        if not _OPENSEARCH_AVAILABLE:
            raise ImportError(
                "langchain-community required for OpenSearch. "
                "Install: pip install langchain-community opensearch-py"
            )
        http_auth = (
            (config.get("username"), config.get("password"))
            if config.get("username")
            else None
        )
        self._index_name = config.get("index_name", "hybrid_search_fulltext")
        store = OpenSearchVectorSearch(
            opensearch_url=config.get("url", "http://localhost:9201"),
            index_name=self._index_name,
            embedding_function=embedding,
            http_auth=http_auth,
        )
        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "OpenSearchSearchAdapter: index=%s at %s",
            config.get("index_name", "hybrid_search_fulltext"),
            config.get("url", "http://localhost:9201"),
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete documents matching *ref_doc_id* via delete-by-query.

        OpenSearchVectorSearch.delete() requires document IDs (not a filter), so we
        always use delete_by_query directly against the underlying opensearch-py client.
        Tries all metadata key variants (ref_doc_id / doc_id) and both term + keyword
        field variants to match whatever mapping OpenSearch auto-created.
        """
        if self._store is None:
            return
        client = getattr(self._store, "client", None)
        if client is None:
            logger.warning("OpenSearchSearchAdapter: no client available for delete")
            return

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
        try:
            resp = client.delete_by_query(
                index=self._index_name,
                body=delete_body,
                refresh=True,
            )
            deleted = resp.get("deleted", 0) if isinstance(resp, dict) else 0
            if deleted:
                logger.info(
                    "OpenSearchSearchAdapter: deleted %d doc(s) for ref_doc_id=%s",
                    deleted, ref_doc_id,
                )
            else:
                logger.warning(
                    "OpenSearchSearchAdapter: 0 docs deleted for ref_doc_id=%s — "
                    "doc may not have been indexed or already removed",
                    ref_doc_id,
                )
        except Exception as exc:
            logger.warning("OpenSearchSearchAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["OpenSearchSearchAdapter", "_OPENSEARCH_AVAILABLE"]
