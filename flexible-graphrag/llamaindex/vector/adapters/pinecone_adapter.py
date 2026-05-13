"""LlamaIndex Pinecone vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexPineconeAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by Pinecone.

    Configuration keys
    ------------------
    api_key          Pinecone API key (required)
    index_name       Pinecone index name (default ``hybrid-search``)
    cloud            Cloud provider (default ``aws``)
    region           Cloud region (default ``us-east-1``)
    metric           Distance metric (default ``cosine``)
    namespace        Pinecone namespace (optional)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.pinecone import PineconeVectorStore
        from pinecone import Pinecone, ServerlessSpec

        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("Pinecone API key is required")
        index_name = config.get("index_name", "hybrid-search")
        cloud = config.get("cloud", "aws")
        region = config.get("region", "us-east-1")
        metric = config.get("metric", "cosine")

        pc = Pinecone(api_key=api_key)
        existing_indexes = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing_indexes:
            logger.info("LlamaIndexPineconeAdapter: creating index '%s' (dim=%s)", index_name, embed_dim)
            pc.create_index(
                name=index_name,
                dimension=embed_dim,
                metric=metric,
                spec=ServerlessSpec(cloud=cloud, region=region),
            )
        pinecone_index = pc.Index(index_name)
        store = PineconeVectorStore(pinecone_index=pinecone_index, namespace=config.get("namespace"))
        super().__init__(store)
        logger.info("LlamaIndexPineconeAdapter: index=%s cloud=%s region=%s embed_dim=%s",
                    index_name, cloud, region, embed_dim)


__all__ = ["LlamaIndexPineconeAdapter"]
