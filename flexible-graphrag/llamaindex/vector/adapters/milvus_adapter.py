"""LlamaIndex Milvus vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexMilvusAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by Milvus / Zilliz.

    Configuration keys
    ------------------
    host             Milvus host (default ``localhost``)
    port             Milvus port (default ``19530``)
    collection_name  Collection name (default ``hybrid_search``)
    username / password / token  Auth credentials (optional)
    overwrite        Overwrite existing collection (default ``False``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.milvus import MilvusVectorStore

        host = config.get("host", "localhost")
        port = config.get("port", 19530)
        collection_name = config.get("collection_name", "hybrid_search")
        uri = f"http://{host}:{port}"

        # Drop the collection if it was created by a different backend (e.g.
        # LangChain) and lacks LlamaIndex's '_node_content' field.  Without this,
        # inserting nodes raises DataNotMatchException (dynamic fields disabled).
        try:
            from pymilvus import MilvusClient as _MC
            _mc = _MC(uri=uri)
            if _mc.has_collection(collection_name):
                schema = _mc.describe_collection(collection_name)
                field_names = {f["name"] for f in schema.get("fields", [])}
                if "_node_content" not in field_names:
                    logger.info(
                        "Milvus collection '%s' lacks '_node_content' field "
                        "(created by a different backend) — dropping for fresh creation.",
                        collection_name,
                    )
                    _mc.drop_collection(collection_name)
            _mc.close()
        except Exception as _exc:
            logger.debug("Milvus schema check skipped: %s", _exc)

        store = MilvusVectorStore(
            uri=uri,
            collection_name=collection_name,
            dim=embed_dim,
            user=config.get("username"),
            password=config.get("password"),
            token=config.get("token"),
            overwrite=config.get("overwrite", False),
        )
        self._milvus_uri = uri
        self._collection_name = collection_name
        super().__init__(store)
        logger.info("LlamaIndexMilvusAdapter: uri=%s collection=%s embed_dim=%s",
                    uri, collection_name, embed_dim)

    def delete(self, ref_doc_id: str) -> None:
        """Delete Milvus documents matching ref_doc_id.

        The default LlamaIndex ``MilvusVectorStore.delete()`` builds an expression
        ``doc_id in ["<ref_doc_id>"]`` directly.  On Windows, the doc_id contains
        backslash path separators (e.g. ``C:\\path\\to\\file``).  Milvus's expression
        parser treats ``\\n``, ``\\t`` etc. as escape sequences → parse error.

        Fix: use the raw pymilvus ``MilvusClient`` with ``delete()`` which accepts a
        filter expression where we explicitly escape backslashes.
        """
        try:
            from pymilvus import MilvusClient
            client = MilvusClient(uri=self._milvus_uri)
            # Escape backslashes so Milvus expression parser doesn't treat them as escapes
            escaped = ref_doc_id.replace("\\", "\\\\")
            expr = f'doc_id == "{escaped}"'
            result = client.delete(collection_name=self._collection_name, filter=expr)
            deleted = len(result) if isinstance(result, list) else (result.get("delete_count", 0) if isinstance(result, dict) else 0)
            logger.info(
                "LlamaIndexMilvusAdapter: deleted %s doc(s) for ref_doc_id=%s",
                deleted or "?", ref_doc_id,
            )
        except Exception as exc:
            logger.warning("LlamaIndexMilvusAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["LlamaIndexMilvusAdapter"]
