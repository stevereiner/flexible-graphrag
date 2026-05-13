"""LangChain OpenSearch vector store adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_community.vectorstores import OpenSearchVectorSearch
    _OPENSEARCH_AVAILABLE = True
except ImportError:
    _OPENSEARCH_AVAILABLE = False


class OpenSearchVectorAdapter(LangChainVectorAdapter):
    """Dense vector store adapter backed by OpenSearch.

    Configuration keys
    ------------------
    url              OpenSearch endpoint (default ``http://localhost:9201``)
    index_name       Index (default ``hybrid_search_vector``)
    username         Basic-auth username (optional)
    password         Basic-auth password (optional)
    embedding_function  LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _OPENSEARCH_AVAILABLE:
            raise ImportError(
                "langchain-community required for OpenSearch. "
                "Install: pip install langchain-community opensearch-py"
            )
        self._os_url = config.get("url", "http://localhost:9201")
        self._index_name = config.get("index_name", "hybrid_search_vector")
        http_auth = (
            (config.get("username"), config.get("password"))
            if config.get("username")
            else None
        )
        self._http_auth = http_auth
        store = OpenSearchVectorSearch(
            opensearch_url=self._os_url,
            index_name=self._index_name,
            embedding_function=embedding,
            http_auth=http_auth,
        )
        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "OpenSearchVectorAdapter: index=%s at %s",
            self._index_name,
            self._os_url,
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete OpenSearch documents matching ref_doc_id via delete-by-query.

        ``OpenSearchVectorSearch.delete()`` requires internal document IDs, not a
        metadata filter.  Use the opensearch-py client directly instead.
        """
        client = getattr(self._store, "client", None)
        if client is None:
            try:
                from opensearchpy import OpenSearch
                kwargs: Dict[str, Any] = {"hosts": [self._os_url]}
                if self._http_auth:
                    kwargs["http_auth"] = self._http_auth
                client = OpenSearch(**kwargs)
            except Exception as exc:
                logger.warning("OpenSearchVectorAdapter: cannot create client for delete: %s", exc)
                return

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
        try:
            resp = client.delete_by_query(index=self._index_name, body=body, params={"refresh": "true"})
            deleted = resp.get("deleted", 0) if isinstance(resp, dict) else 0
            if deleted:
                logger.info(
                    "OpenSearchVectorAdapter: deleted %d doc(s) for ref_doc_id=%s",
                    deleted, ref_doc_id,
                )
            else:
                logger.warning(
                    "OpenSearchVectorAdapter: 0 docs deleted for ref_doc_id=%s",
                    ref_doc_id,
                )
        except Exception as exc:
            logger.warning("OpenSearchVectorAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["OpenSearchVectorAdapter", "_OPENSEARCH_AVAILABLE"]
