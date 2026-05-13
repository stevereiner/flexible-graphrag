"""LlamaIndex Qdrant vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexQdrantAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by Qdrant.

    Configuration keys
    ------------------
    host             Qdrant host (default ``localhost``)
    port             Qdrant REST port (default ``6333``)
    api_key          API key for Qdrant Cloud (optional)
    https            Use HTTPS (default ``False``)
    collection_name  Collection to use (default ``hybrid_search``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.qdrant import QdrantVectorStore
        from qdrant_client import QdrantClient, AsyncQdrantClient

        host = config.get("host", "localhost")
        port = config.get("port", 6333)
        collection_name = config.get("collection_name", "hybrid_search")

        client = QdrantClient(
            host=host, port=port,
            api_key=config.get("api_key"),
            https=config.get("https", False),
            check_compatibility=False,
        )
        aclient = AsyncQdrantClient(
            host=host, port=port,
            api_key=config.get("api_key"),
            https=config.get("https", False),
            check_compatibility=False,
        )

        # Drop the collection if it contains any points from a different backend
        # (e.g. LangChain) that lack LlamaIndex's '_node_content' / 'text' payload
        # keys.  Collections can be mixed (some LI points, some LC points), so we
        # check ALL points in the first batch — if ANY lacks both keys, drop.
        try:
            if client.collection_exists(collection_name):
                sample = client.scroll(collection_name, limit=20, with_payload=True)
                points = sample[0]
                if points:
                    bad = [
                        p for p in points
                        if "_node_content" not in (p.payload or {})
                        and "text" not in (p.payload or {})
                    ]
                    if bad:
                        logger.info(
                            "Qdrant collection '%s' has %d/%d non-LlamaIndex-format points "
                            "— deleting for fresh creation.",
                            collection_name, len(bad), len(points),
                        )
                        client.delete_collection(collection_name)
        except Exception as _exc:
            logger.debug("Qdrant format check skipped: %s", _exc)

        store = QdrantVectorStore(client=client, aclient=aclient, collection_name=collection_name)
        super().__init__(store)
        logger.info("LlamaIndexQdrantAdapter: collection=%s at %s:%s",
                    collection_name, host, port)


__all__ = ["LlamaIndexQdrantAdapter"]
