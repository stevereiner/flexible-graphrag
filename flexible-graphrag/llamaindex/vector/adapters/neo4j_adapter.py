"""LlamaIndex Neo4j vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexNeo4jVectorAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by Neo4j vector index.

    Configuration keys
    ------------------
    url              Bolt URL (default ``bolt://localhost:7687``)
    username         Neo4j username (default ``neo4j``)
    password         Neo4j password (required)
    database         Database name (default ``neo4j``)
    index_name       Vector index name (default ``hybrid_search_vector``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.neo4jvector import Neo4jVectorStore

        url = config.get("url", "bolt://localhost:7687")
        index_name = config.get("index_name", "hybrid_search_vector")
        store = Neo4jVectorStore(
            username=config.get("username", "neo4j"),
            password=config["password"],
            url=url,
            embedding_dimension=embed_dim,
            database=config.get("database", "neo4j"),
            index_name=index_name,
        )
        super().__init__(store)
        logger.info("LlamaIndexNeo4jVectorAdapter: url=%s index=%s embed_dim=%s",
                    url, index_name, embed_dim)


__all__ = ["LlamaIndexNeo4jVectorAdapter"]
