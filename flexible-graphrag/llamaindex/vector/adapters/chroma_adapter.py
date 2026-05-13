"""LlamaIndex Chroma vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexChromaAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by Chroma.

    Configuration keys
    ------------------
    collection_name   Collection name (default ``hybrid_search``)
    host / port       HTTP client mode — connect to a running Chroma server
    persist_directory Local persistence path used when host/port not set
                      (default ``./chroma_db``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.chroma import ChromaVectorStore
        import chromadb

        collection_name = config.get("collection_name", "hybrid_search")
        host = config.get("host")
        port = config.get("port")
        if host and port:
            chroma_client = chromadb.HttpClient(host=host, port=port)
            logger.info("LlamaIndexChromaAdapter: HTTP mode %s:%s collection=%s", host, port, collection_name)
        else:
            persist_directory = config.get("persist_directory", "./chroma_db")
            chroma_client = chromadb.PersistentClient(path=persist_directory)
            logger.info("LlamaIndexChromaAdapter: local mode path=%s collection=%s",
                        persist_directory, collection_name)
        chroma_collection = chroma_client.get_or_create_collection(collection_name)
        store = ChromaVectorStore(chroma_collection=chroma_collection)
        super().__init__(store)


__all__ = ["LlamaIndexChromaAdapter"]
