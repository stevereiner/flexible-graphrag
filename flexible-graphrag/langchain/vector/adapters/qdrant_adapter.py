"""LangChain Qdrant vector store adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_qdrant import QdrantVectorStore as LCQdrant
    from qdrant_client import QdrantClient
    _QDRANT_AVAILABLE = True
except ImportError:
    _QDRANT_AVAILABLE = False


class QdrantVectorAdapter(LangChainVectorAdapter):
    """Vector store adapter backed by Qdrant.

    Configuration keys
    ------------------
    host             Qdrant host (default ``localhost``)
    port             Qdrant REST port (default ``6333``)
    api_key          API key for Qdrant Cloud (optional)
    https            Use HTTPS (default ``False``)
    collection_name  Collection to use (default ``hybrid_search``)
    vector_size      Embedding dimension — auto-detected from embedding if omitted
    embedding        LangChain Embeddings instance (required for ingestion)
    """

    @staticmethod
    def _ensure_collection(client, collection_name: str, embedding, vector_size: int = 0) -> None:
        """Create the Qdrant collection if it does not already exist."""
        try:
            client.get_collection(collection_name)
            return  # already exists
        except Exception:
            pass
        from qdrant_client.models import Distance, VectorParams
        dim = LangChainVectorAdapter._resolve_vector_size(vector_size, embedding)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        logger.info("QdrantVectorAdapter: created collection '%s' (dims=%d)", collection_name, dim)

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _QDRANT_AVAILABLE:
            raise ImportError(
                "langchain-qdrant and qdrant-client required. "
                "Install: pip install langchain-qdrant qdrant-client"
            )
        collection_name = config.get("collection_name", "hybrid_search")
        client = QdrantClient(
            host=config.get("host", "localhost"),
            port=config.get("port", 6333),
            api_key=config.get("api_key"),
            https=config.get("https", False),
        )
        self._ensure_collection(
            client, collection_name, embedding,
            vector_size=config.get("vector_size", 0),
        )
        store = LCQdrant(
            client=client,
            collection_name=collection_name,
            embedding=embedding,
            # Skip langchain_qdrant's internal embed_documents("dummy_text") validation
            # call.  We pre-validate the collection ourselves via _ensure_collection, so
            # the redundant sync embedding API call is unnecessary — and it fails when
            # OpenAIEmbeddings is initialised inside an async context (FastAPI lifespan /
            # lazy HybridSearchSystem init), where langchain_openai creates only an async
            # client and the sync client is None.
            validate_collection_config=False,
        )
        self._qdrant_client = client
        self._collection_name = collection_name
        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "QdrantVectorAdapter: collection=%s at %s:%s",
            collection_name,
            config.get("host", "localhost"),
            config.get("port", 6333),
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete all points whose payload matches the document ID.

        LangChain stores document metadata inside a ``metadata`` sub-dict in
        the Qdrant payload (e.g. ``metadata.ref_doc_id`` or ``metadata.doc_id``).
        We issue separate delete calls for all key variants so that documents
        ingested via different paths (LI chunker → ref_doc_id, LC chunker →
        doc_id) are all removed.
        """
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

            # All payload paths that could contain the stable document ID.
            key_candidates = [
                f"metadata.{self._delete_key}",   # LangChain nested (primary)
                f"metadata.doc_id",               # LC chunker path
                f"metadata.ref_doc_id",           # LI path stored via metadata
                self._delete_key,                 # flat top-level (LI native)
            ]
            # Deduplicate while preserving order
            seen: set = set()
            unique_keys = [k for k in key_candidates if not (k in seen or seen.add(k))]

            deleted_any = False
            for key in unique_keys:
                try:
                    self._qdrant_client.delete(
                        collection_name=self._collection_name,
                        points_selector=FilterSelector(
                            filter=Filter(
                                must=[FieldCondition(key=key, match=MatchValue(value=ref_doc_id))]
                            )
                        ),
                    )
                    deleted_any = True
                except Exception as inner_exc:
                    logger.debug("QdrantVectorAdapter: delete key=%s failed: %s", key, inner_exc)

            if deleted_any:
                logger.info(
                    "QdrantVectorAdapter: deleted points for ref_doc_id=%s (tried %d key(s))",
                    ref_doc_id, len(unique_keys),
                )
            else:
                logger.warning(
                    "QdrantVectorAdapter: no points deleted for ref_doc_id=%s — "
                    "the document may not have been indexed yet or uses a different key",
                    ref_doc_id,
                )
        except Exception as exc:
            logger.warning("QdrantVectorAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["QdrantVectorAdapter", "_QDRANT_AVAILABLE"]
