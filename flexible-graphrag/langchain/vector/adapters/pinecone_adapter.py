"""LangChain Pinecone vector store adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_pinecone import PineconeVectorStore
    from pinecone import Pinecone
    _PINECONE_AVAILABLE = True
except ImportError:
    _PINECONE_AVAILABLE = False


class PineconeVectorAdapter(LangChainVectorAdapter):
    """Vector store adapter backed by Pinecone.

    Configuration keys
    ------------------
    api_key     Pinecone API key (required)
    index_name  Pinecone index name (default ``hybrid-search``)
    embedding   LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _PINECONE_AVAILABLE:
            raise ImportError(
                "langchain-pinecone and pinecone-client required. "
                "Install: pip install langchain-pinecone pinecone-client"
            )
        pc = Pinecone(api_key=config["api_key"])
        index = pc.Index(config.get("index_name", "hybrid-search"))
        store = PineconeVectorStore(index=index, embedding=embedding)
        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "PineconeVectorAdapter: index=%s",
            config.get("index_name", "hybrid-search"),
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete vectors from Pinecone matching doc_id or ref_doc_id in metadata.

        The LC chunker path stores the stable ID under 'doc_id'; the LI path uses
        'ref_doc_id'.  Issue both filter deletes so either ingestion path is cleaned up.
        """
        if self._store is None:
            return
        for key in ("doc_id", self._delete_key):
            try:
                self._store.delete(filter={key: {"$eq": ref_doc_id}})
            except Exception as exc:
                logger.debug("PineconeVectorAdapter delete (key=%s) failed for %s: %s", key, ref_doc_id, exc)
        logger.info("PineconeVectorAdapter: deleted docs for ref_doc_id=%s", ref_doc_id)


__all__ = ["PineconeVectorAdapter", "_PINECONE_AVAILABLE"]
