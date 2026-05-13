"""LangChain Weaviate vector store adapter.

Wraps ``langchain_weaviate.vectorstores.WeaviateVectorStore`` (first-party,
preferred) falling back to ``langchain_community.vectorstores.Weaviate``.

Weaviate v4 offers two client variants:
- Sync  ``weaviate.connect_to_custom()``   — used when an event loop is already
  running (FastAPI / uvicorn context).  ``add_documents`` is called via
  ``run_in_executor`` so the sync client is safe here.
- Async ``weaviate.use_async_with_custom()`` — used in a standalone (no-loop)
  context where ``asyncio.run()`` can take over.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_weaviate.vectorstores import WeaviateVectorStore
    _WEAVIATE_AVAILABLE = True
    _WEAVIATE_PACKAGE = "langchain_weaviate"
except ImportError:
    try:
        from langchain_community.vectorstores import Weaviate as WeaviateVectorStore  # type: ignore
        _WEAVIATE_AVAILABLE = True
        _WEAVIATE_PACKAGE = "langchain_community"
    except ImportError:
        _WEAVIATE_AVAILABLE = False
        _WEAVIATE_PACKAGE = None


def _parse_url(url: str):
    """Return (host, http_port, http_secure) from a URL string."""
    http_secure = url.startswith("https://")
    stripped = url.replace("https://", "").replace("http://", "")
    if ":" in stripped:
        host_part, port_part = stripped.rsplit(":", 1)
        try:
            http_port = int(port_part)
        except ValueError:
            http_port = 443 if http_secure else 8081
        host = host_part
    else:
        host = stripped
        http_port = 443 if http_secure else 8081
    return host, http_port, http_secure


def _build_weaviate_client_sync(config: Dict[str, Any]):
    """Construct a Weaviate v4 **sync** client from *config*.

    Used when an asyncio event loop is already running (FastAPI context).
    The sync client is thread-safe for ``run_in_executor`` calls.
    """
    import weaviate

    url: str = config.get("url", "http://localhost:8081")
    grpc_port: int = config.get("grpc_port", 50051)
    api_key: Optional[str] = config.get("api_key")
    additional_headers: dict = config.get("additional_headers", {})

    host, http_port, http_secure = _parse_url(url)

    from weaviate.classes.init import AdditionalConfig, Timeout

    kwargs: Dict[str, Any] = dict(
        http_host=host,
        http_port=http_port,
        http_secure=http_secure,
        grpc_host=host,
        grpc_port=grpc_port,
        grpc_secure=http_secure,
        skip_init_checks=True,
        additional_config=AdditionalConfig(timeout=Timeout(init=60, query=60, insert=180)),
        headers=additional_headers,
    )
    if api_key:
        from weaviate.classes.init import Auth
        kwargs["auth_credentials"] = Auth.api_key(api_key)

    client = weaviate.connect_to_custom(**kwargs)
    logger.info("Weaviate sync client connected to %s", url)
    return client


def _build_weaviate_client_async(config: Dict[str, Any]):
    """Construct and connect a Weaviate v4 **async** client from *config*.

    Used when there is NO running event loop (script / non-ASGI context).
    ``asyncio.run()`` drives the connect call.
    """
    import weaviate

    url: str = config.get("url", "http://localhost:8081")
    grpc_port: int = config.get("grpc_port", 50051)
    api_key: Optional[str] = config.get("api_key")
    additional_headers: dict = config.get("additional_headers", {})

    host, http_port, http_secure = _parse_url(url)

    from weaviate.classes.init import AdditionalConfig, Timeout

    kwargs: Dict[str, Any] = dict(
        http_host=host,
        http_port=http_port,
        http_secure=http_secure,
        grpc_host=host,
        grpc_port=grpc_port,
        grpc_secure=http_secure,
        skip_init_checks=True,
        additional_config=AdditionalConfig(timeout=Timeout(init=60, query=60, insert=180)),
        headers=additional_headers,
    )
    if api_key:
        from weaviate.classes.init import Auth
        kwargs["auth_credentials"] = Auth.api_key(api_key)

    async_client = weaviate.use_async_with_custom(**kwargs)
    asyncio.run(async_client.connect())
    logger.info("Weaviate async client connected to %s", url)
    return async_client


class WeaviateVectorAdapter(LangChainVectorAdapter):
    """Vector store adapter backed by Weaviate.

    Uses ``langchain_weaviate.WeaviateVectorStore`` (first-party) falling back
    to ``langchain_community.vectorstores.Weaviate``.

    Configuration keys
    ------------------
    url                Weaviate HTTP endpoint (default ``http://localhost:8081``)
    grpc_port          gRPC port (default ``50051``)
    api_key            API key for Weaviate Cloud (optional)
    additional_headers Extra HTTP headers, e.g. for inference API keys (optional)
    index_name         Weaviate class/collection name (default ``HybridSearch``)
    text_key           Property that holds the text (default ``content``)
    embedding          LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _WEAVIATE_AVAILABLE:
            raise ImportError(
                "langchain-weaviate required. Install: pip install langchain-weaviate weaviate-client"
            )

        index_name = config.get("index_name", "HybridSearch")
        text_key = config.get("text_key", "content")

        if _WEAVIATE_PACKAGE == "langchain_weaviate":
            # Prefer sync client when inside a running event loop (FastAPI) so
            # that add_documents (called via run_in_executor) works without
            # nested asyncio issues.  Fall back to async client otherwise.
            try:
                asyncio.get_running_loop()
                client = _build_weaviate_client_sync(config)
                logger.info("Weaviate: using sync client (event loop detected)")
            except RuntimeError:
                client = _build_weaviate_client_async(config)
                logger.info("Weaviate: using async client (no event loop)")

            store = WeaviateVectorStore(
                client=client,
                index_name=index_name,
                text_key=text_key,
                embedding=embedding,
            )
        else:
            # langchain_community path — uses synchronous v3 client
            import weaviate as _weaviate

            wv_client = _weaviate.Client(
                url=config.get("url", "http://localhost:8081"),
                auth_client_secret=(
                    _weaviate.AuthApiKey(api_key=config["api_key"])
                    if config.get("api_key")
                    else None
                ),
            )
            store = WeaviateVectorStore(
                client=wv_client,
                index_name=index_name,
                text_key=text_key,
                embedding=embedding,
            )

        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "WeaviateVectorAdapter (%s): index=%s at %s",
            _WEAVIATE_PACKAGE,
            index_name,
            config.get("url", "http://localhost:8081"),
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete Weaviate objects where doc_id or ref_doc_id matches.

        ``WeaviateVectorStore.delete()`` (langchain_weaviate) takes a list of
        string IDs, not a metadata filter dict.  Use the underlying client's
        ``filter_by_property`` to perform a metadata-based delete instead.

        The LC chunker path stores the stable ID under 'doc_id'; the LI path uses
        'ref_doc_id'.  Try both properties so either ingestion path is cleaned up.
        """
        if self._store is None:
            return
        client = getattr(self._store, "_client", None)
        if client is None:
            try:
                self._store.delete(filter={"doc_id": ref_doc_id})
            except Exception as exc:
                logger.warning("WeaviateVectorAdapter delete (fallback) failed for %s: %s", ref_doc_id, exc)
            return
        try:
            from weaviate.classes.query import Filter
            collection = client.collections.get(
                getattr(self._store, "_index_name", "HybridSearch")
            )
            deleted = 0
            for key in ("doc_id", self._delete_key):
                try:
                    result = collection.data.delete_many(
                        where=Filter.by_property(key).equal(ref_doc_id)
                    )
                    # result.matches is the count of objects that matched
                    matches = getattr(result, "matches", None)
                    if matches:
                        deleted += matches
                except Exception:
                    pass
            if deleted:
                logger.info("WeaviateVectorAdapter: deleted %d object(s) for ref_doc_id=%s", deleted, ref_doc_id)
            else:
                logger.warning("WeaviateVectorAdapter: no objects found for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("WeaviateVectorAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["WeaviateVectorAdapter", "_WEAVIATE_AVAILABLE"]
