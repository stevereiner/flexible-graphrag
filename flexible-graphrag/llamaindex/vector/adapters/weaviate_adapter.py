"""LlamaIndex Weaviate vector store adapter."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexWeaviateAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by Weaviate.

    Uses a **sync** Weaviate client as the store backend.  Async LlamaIndex
    paths (``async_add`` / ``aquery``) are patched to run the sync methods in
    a worker thread via ``asyncio.to_thread``.

    Why sync (not async)
    --------------------
    An async client connected with ``asyncio.run()`` (e.g. when FlexibleVector
    builds this adapter in ``asyncio.to_thread``) binds to a throwaway loop that
    closes immediately → later ``aquery`` fails with ``WeaviateClosedClientError``.
    Lazy-connect on the FastAPI loop only helps the instance that was connected;
    search uses the *startup* adapter, which never went through ``insert_nodes``.
    A connected sync client works for both ingest and search regardless of which
    adapter instance performed the write.

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
        from weaviate.classes.init import AdditionalConfig, Timeout

        url = config.get("url", "http://localhost:8081")
        self._index_name = config.get("index_name", "HybridSearch")
        host = url.replace("http://", "").replace("https://", "").split(":")[0]
        http_port = int(url.split(":")[-1]) if ":" in url.replace("http://", "") else 8081
        http_secure = url.startswith("https://")
        grpc_host = config.get("grpc_host", "localhost")
        grpc_port = int(config.get("grpc_port", 50051))

        connect_kwargs: Dict[str, Any] = dict(
            http_host=host,
            http_port=http_port,
            http_secure=http_secure,
            grpc_host=grpc_host,
            grpc_port=grpc_port,
            grpc_secure=False,
            skip_init_checks=True,
            additional_config=AdditionalConfig(
                timeout=Timeout(init=60, query=60, insert=180)
            ),
            headers=config.get("additional_headers", {}),
        )
        if config.get("api_key"):
            from weaviate.classes.init import Auth
            connect_kwargs["auth_credentials"] = Auth.api_key(config.get("api_key"))

        self._sync_client = weaviate.connect_to_custom(**connect_kwargs)
        logger.info("LlamaIndexWeaviateAdapter: sync client connected")

        from llama_index.vector_stores.weaviate.utils import NODE_SCHEMA
        from adapters.vector.weaviate_collection import ensure_weaviate_collection

        ensure_weaviate_collection(self._sync_client, self._index_name, NODE_SCHEMA)

        store = WeaviateVectorStore(
            weaviate_client=self._sync_client,
            index_name=self._index_name,
            text_key=config.get("text_key", "content"),
        )
        self._install_async_bridges(store)
        super().__init__(store)
        logger.info("LlamaIndexWeaviateAdapter: url=%s index=%s", url, self._index_name)

    @staticmethod
    def _install_async_bridges(store: Any) -> None:
        """Route LlamaIndex async APIs through the sync client in a worker thread.

        ``WeaviateVectorStore`` is a Pydantic model — normal attribute assignment
        rejects unknown fields (``async_add`` / overriding ``aquery``).  Use
        ``object.__setattr__`` to install the bridges.
        """
        _sync_add = store.add
        _sync_query = store.query

        async def _async_add(nodes: List[Any], **kwargs: Any) -> List[str]:
            return await asyncio.to_thread(_sync_add, nodes, **kwargs)

        async def _aquery(query: Any, **kwargs: Any) -> Any:
            return await asyncio.to_thread(_sync_query, query, **kwargs)

        object.__setattr__(store, "async_add", _async_add)
        object.__setattr__(store, "aquery", _aquery)

    def delete(self, ref_doc_id: str) -> None:
        """Delete Weaviate objects matching ref_doc_id via the sync client."""
        if self._sync_client is None:
            logger.warning(
                "LlamaIndexWeaviateAdapter: no sync client — cannot delete ref_doc_id=%s",
                ref_doc_id,
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
                ref_doc_id,
                self._index_name,
            )
        except Exception as exc:
            logger.warning(
                "LlamaIndexWeaviateAdapter delete failed for %s: %s", ref_doc_id, exc
            )


__all__ = ["LlamaIndexWeaviateAdapter"]
