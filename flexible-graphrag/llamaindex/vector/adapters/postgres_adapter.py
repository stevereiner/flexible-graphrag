"""LlamaIndex PostgreSQL (pgvector) vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexPostgresVectorAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by PostgreSQL with pgvector.

    Configuration keys
    ------------------
    host             Postgres host (default ``localhost``)
    port             Postgres port (default ``5432``)
    database         Database name (default ``postgres``)
    username         Database user (default ``postgres``)
    password         Database password
    table_name       Table for vectors (default ``hybrid_search_vectors``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.postgres import PGVectorStore

        table_name = config.get("table_name", "hybrid_search_vectors")
        store = PGVectorStore.from_params(
            database=config.get("database", "postgres"),
            host=config.get("host", "localhost"),
            password=config.get("password"),
            port=config.get("port", 5432),
            user=config.get("username", "postgres"),
            table_name=table_name,
            embed_dim=embed_dim,
        )
        super().__init__(store)
        logger.info("LlamaIndexPostgresVectorAdapter: host=%s table=%s embed_dim=%s",
                    config.get("host", "localhost"), table_name, embed_dim)


__all__ = ["LlamaIndexPostgresVectorAdapter"]
