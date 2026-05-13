"""LlamaIndex Weaviate vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import asyncio
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexWeaviateAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by Weaviate.

    Configuration keys
    ------------------
    url              Weaviate HTTP URL (default ``http://localhost:8081``)
    index_name       Class / collection name (default ``HybridSearch``)
    text_key         Property used for text content (default ``content``)
    api_key          Weaviate API key (optional)
    additional_headers  Extra HTTP headers dict (optional)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.weaviate import WeaviateVectorStore
        import weaviate

        url = config.get("url", "http://localhost:8081")
        self._index_name = config.get("index_name", "HybridSearch")
        host = url.replace("http://", "").replace("https://", "").split(":")[0]
        http_port = int(url.split(":")[-1]) if ":" in url.replace("http://", "") else 8081
        http_secure = url.startswith("https://")
        grpc_host = config.get("grpc_host", "localhost")
        grpc_port = int(config.get("grpc_port", 50051))

        from weaviate.classes.init import AdditionalConfig, Timeout
        common_kwargs: Dict[str, Any] = dict(
            http_host=host, http_port=http_port, http_secure=http_secure,
            grpc_host=grpc_host, grpc_port=grpc_port, grpc_secure=False,
            skip_init_checks=True,
            additional_config=AdditionalConfig(timeout=Timeout(init=60, query=60, insert=180)),
            headers=config.get("additional_headers", {}),
        )

        if config.get("api_key"):
            from weaviate.classes.init import Auth
            common_kwargs["auth_credentials"] = Auth.api_key(config.get("api_key"))

        async_client = weaviate.use_async_with_custom(**common_kwargs)

        try:
            try:
                asyncio.get_running_loop()
                logger.warning("LlamaIndexWeaviateAdapter: event loop running — client will connect on first use")
            except RuntimeError:
                asyncio.run(async_client.connect())
                logger.info("LlamaIndexWeaviateAdapter: async client connected")
        except Exception as exc:
            logger.warning("LlamaIndexWeaviateAdapter: pre-connect failed: %s — will connect on first use", exc)

        # Also create a sync client for synchronous delete() calls.
        # WeaviateVectorStore.delete() is sync and requires a WeaviateClient (not async).
        self._sync_client = None
        try:
            self._sync_client = weaviate.connect_to_custom(
                http_host=host, http_port=http_port, http_secure=http_secure,
                grpc_host=grpc_host, grpc_port=grpc_port, grpc_secure=False,
                skip_init_checks=True,
                additional_config=AdditionalConfig(timeout=Timeout(init=60, query=60, insert=180)),
                headers=config.get("additional_headers", {}),
                **({"auth_credentials": common_kwargs["auth_credentials"]} if "auth_credentials" in common_kwargs else {}),
            )
            logger.info("LlamaIndexWeaviateAdapter: sync client connected for delete()")
        except Exception as exc:
            logger.warning("LlamaIndexWeaviateAdapter: sync client unavailable: %s — delete() may fail", exc)

        store = WeaviateVectorStore(
            weaviate_client=async_client,
            index_name=self._index_name,
            text_key=config.get("text_key", "content"),
        )
        super().__init__(store)
        logger.info("LlamaIndexWeaviateAdapter: url=%s index=%s", url, self._index_name)

    def delete(self, ref_doc_id: str) -> None:
        """Delete Weaviate objects matching ref_doc_id via the sync client.

        ``WeaviateVectorStore.delete()`` requires a synchronous ``WeaviateClient``
        which is not the same as the async client used for queries.  We maintain a
        separate sync client specifically for delete operations.
        """
        if self._sync_client is None:
            logger.warning(
                "LlamaIndexWeaviateAdapter: no sync client — cannot delete ref_doc_id=%s", ref_doc_id
            )
            return
        try:
            from weaviate.classes.query import Filter
            collection = self._sync_client.collections.get(self._index_name)
            collection.data.delete_many(
                where=Filter.by_property("ref_doc_id").equal(ref_doc_id)
            )
            logger.info(
                "LlamaIndexWeaviateAdapter: deleted objects for ref_doc_id=%s from %s",
                ref_doc_id, self._index_name,
            )
        except Exception as exc:
            logger.warning("LlamaIndexWeaviateAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["LlamaIndexWeaviateAdapter"]
