"""LlamaIndex OpenSearch vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


def _drop_opensearch_index_if_incompatible(url: str, index: str,
                                           embedding_field: str) -> None:
    """Delete the OpenSearch index if its embedding field is not knn_vector type.

    LangChain's OpenSearch adapter creates indices without knn_vector mapping,
    so queries fail with 'Field embedding is not knn_vector type'.  Drop the
    index so the LlamaIndex adapter can recreate it with the correct mapping.
    """
    try:
        import requests
        resp = requests.get(f"{url}/{index}/_mapping", timeout=5)
        if resp.status_code == 404:
            return  # index doesn't exist yet — nothing to do
        if resp.status_code != 200:
            return
        mapping = resp.json()
        props = (mapping.get(index, {})
                        .get("mappings", {})
                        .get("properties", {}))
        emb_type = props.get(embedding_field, {}).get("type", "")
        if emb_type and emb_type != "knn_vector":
            logger.info(
                "OpenSearch index '%s' has embedding field type '%s' (not knn_vector) "
                "— deleting for fresh KNN-capable creation.",
                index, emb_type,
            )
            requests.delete(f"{url}/{index}", timeout=5)
    except Exception as _exc:
        logger.debug("OpenSearch schema check skipped: %s", _exc)


class LlamaIndexOpenSearchVectorAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by OpenSearch.

    Configuration keys
    ------------------
    url              OpenSearch endpoint (default ``http://localhost:9201``)
    index_name       Index name (default ``hybrid_search_vector``)
    embedding_field  Field for embeddings (default ``embedding``)
    text_field       Field for document text (default ``content``)
    search_pipeline  Optional search pipeline name
    username / password  HTTP basic auth (optional)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.opensearch import OpensearchVectorStore, OpensearchVectorClient

        url = config.get("url", "http://localhost:9201")
        index_name = config.get("index_name", "hybrid_search_vector")
        embedding_field = config.get("embedding_field", "embedding")

        _drop_opensearch_index_if_incompatible(url, index_name, embedding_field)

        client = OpensearchVectorClient(
            endpoint=url,
            index=index_name,
            dim=embed_dim,
            embedding_field=embedding_field,
            text_field=config.get("text_field", "content"),
            search_pipeline=config.get("search_pipeline"),
            http_auth=(config.get("username"), config.get("password")) if config.get("username") else None,
        )
        store = OpensearchVectorStore(client)
        super().__init__(store)
        logger.info("LlamaIndexOpenSearchVectorAdapter: url=%s index=%s embed_dim=%s",
                    url, index_name, embed_dim)


__all__ = ["LlamaIndexOpenSearchVectorAdapter"]
