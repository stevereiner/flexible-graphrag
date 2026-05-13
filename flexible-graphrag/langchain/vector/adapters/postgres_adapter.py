"""LangChain PostgreSQL (pgvector) vector store adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_postgres import PGVector
    _PGVECTOR_AVAILABLE = True
except ImportError:
    _PGVECTOR_AVAILABLE = False


class PostgresVectorAdapter(LangChainVectorAdapter):
    """Vector store adapter backed by PostgreSQL + pgvector.

    Configuration keys
    ------------------
    host         Postgres host (default ``localhost``)
    port         Postgres port (default ``5432``)
    username     Postgres user (default ``postgres``)
    password     Postgres password
    database     Database name (default ``postgres``)
    table_name   Table / collection name (default ``hybrid_search_vectors``)
    embeddings   LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _PGVECTOR_AVAILABLE:
            raise ImportError(
                "langchain-postgres required. Install: pip install langchain-postgres"
            )
        conn_str = (
            f"postgresql+psycopg://{config.get('username', 'postgres')}:"
            f"{config.get('password', '')}@{config.get('host', 'localhost')}:"
            f"{config.get('port', 5432)}/{config.get('database', 'postgres')}"
        )
        store = PGVector(
            connection=conn_str,
            collection_name=config.get("table_name", "hybrid_search_vectors"),
            embeddings=embedding,
        )
        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "PostgresVectorAdapter: table=%s at %s:%s/%s",
            config.get("table_name", "hybrid_search_vectors"),
            config.get("host", "localhost"),
            config.get("port", 5432),
            config.get("database", "postgres"),
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete vectors from PGVector by doc_id or ref_doc_id metadata.

        PGVector.delete() takes a list of document IDs, not a metadata filter.
        We find matching IDs first via similarity_search with a filter, then delete.
        The LC chunker path stores the stable ID under 'doc_id'; the LI path uses
        'ref_doc_id'.  Try both so either ingestion path is cleaned up correctly.
        """
        if self._store is None:
            return
        try:
            all_ids: list = []
            # LC chunker stores 'doc_id'; LI stores 'ref_doc_id' — try both
            for key in ("doc_id", self._delete_key):
                try:
                    results = self._store.similarity_search(
                        "", k=1000, filter={key: ref_doc_id}
                    )
                    ids = [r.id for r in results if hasattr(r, "id") and r.id]
                    all_ids.extend(ids)
                except Exception:
                    pass
            # deduplicate
            unique_ids = list(dict.fromkeys(all_ids))
            if unique_ids:
                self._store.delete(ids=unique_ids)
                logger.info(
                    "PostgresVectorAdapter: deleted %d vector(s) for ref_doc_id=%s",
                    len(unique_ids), ref_doc_id,
                )
            else:
                logger.warning(
                    "PostgresVectorAdapter: no vectors found for ref_doc_id=%s",
                    ref_doc_id,
                )
        except Exception as exc:
            logger.warning("PostgresVectorAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["PostgresVectorAdapter", "_PGVECTOR_AVAILABLE"]
