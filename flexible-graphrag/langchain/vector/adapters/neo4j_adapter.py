"""LangChain Neo4j vector store adapter.

Uses the vector index built into Neo4j (5.11+) for approximate nearest-
neighbour search.  This is a *vector* adapter — for the property-graph QA
chain see :mod:`langchain.graph.pg_store_adapters.neo4j_adapter`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_neo4j import Neo4jVector
    _NEO4J_AVAILABLE = True
except ImportError:
    try:
        from langchain_community.vectorstores import Neo4jVector  # type: ignore
        _NEO4J_AVAILABLE = True
    except ImportError:
        _NEO4J_AVAILABLE = False


class Neo4jVectorAdapter(LangChainVectorAdapter):
    """Vector store adapter backed by Neo4j's native vector index.

    Uses ``langchain_neo4j.Neo4jVector`` (first-party) falling back to
    ``langchain_community``.

    Configuration keys
    ------------------
    url                 Bolt URL (default ``bolt://localhost:7687``)
    username            Neo4j user (default ``neo4j``)
    password            Neo4j password (required)
    database            Database name (default ``neo4j``)
    index_name          Vector index name (default ``hybrid_search_vector``)
    keyword_index_name  BM25 keyword index name for hybrid search (optional)
    node_label          Node label to store vectors on (default ``Chunk``)
    text_node_property  Property that holds chunk text (default ``text``)
    embedding_node_property  Property that holds the vector (default ``embedding``)
    embedding           LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _NEO4J_AVAILABLE:
            raise ImportError(
                "langchain-neo4j required. Install: pip install langchain-neo4j"
            )
        conn = dict(
            url=config.get("url", "bolt://localhost:7687"),
            username=config.get("username", "neo4j"),
            password=config["password"],
            database=config.get("database", "neo4j"),
        )
        index_kwargs = dict(
            index_name=config.get("index_name", "hybrid_search_vector"),
            keyword_index_name=config.get("keyword_index_name"),
            node_label=config.get("node_label", "Chunk"),
            text_node_property=config.get("text_node_property", "text"),
            embedding_node_property=config.get("embedding_node_property", "embedding"),
        )
        try:
            store = Neo4jVector.from_existing_index(
                embedding=embedding,
                **conn,
                **index_kwargs,
            )
            logger.info(
                "Neo4jVectorAdapter: connected to existing index '%s' at %s",
                index_kwargs["index_name"], conn["url"],
            )
        except ValueError as exc:
            if "does not exist" in str(exc).lower():
                # Index not created yet — initialise with empty documents list
                logger.info(
                    "Neo4jVectorAdapter: index '%s' not found, creating via from_documents([])",
                    index_kwargs["index_name"],
                )
                store = Neo4jVector.from_documents(
                    [],
                    embedding=embedding,
                    **conn,
                    **index_kwargs,
                )
            else:
                raise
        super().__init__(store=store, delete_key=delete_key)
        logger.info(
            "Neo4jVectorAdapter: index=%s at %s",
            index_kwargs["index_name"], conn["url"],
        )

    def close(self) -> None:
        """Close the underlying Neo4j driver to avoid ResourceWarning on GC."""
        store = getattr(self, "_store", None)
        if store is None:
            return
        try:
            driver = getattr(store, "_driver", None)
            if driver is not None:
                driver.close()
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()

    def delete(self, ref_doc_id: str) -> None:
        """Delete nodes from Neo4j matching doc_id or ref_doc_id via Cypher.

        The LC chunker path stores the stable ID under 'doc_id'; the LI path uses
        'ref_doc_id'.  Run both DETACH DELETE queries so either ingestion path is
        cleaned up correctly.
        """
        if self._store is None:
            return
        deleted = 0
        for key in ("doc_id", self._delete_key):
            try:
                result = self._store.query(
                    f"MATCH (n) WHERE n.`{key}` = $ref_id "
                    f"WITH n, count(n) AS cnt DETACH DELETE n RETURN cnt",
                    params={"ref_id": ref_doc_id},
                )
                cnt = result[0].get("cnt", 0) if result else 0
                deleted += cnt
            except Exception:
                pass
        if deleted:
            logger.info("Neo4jVectorAdapter: deleted %d node(s) for ref_doc_id=%s", deleted, ref_doc_id)
        else:
            logger.warning("Neo4jVectorAdapter: no nodes found for ref_doc_id=%s", ref_doc_id)


__all__ = ["Neo4jVectorAdapter", "_NEO4J_AVAILABLE"]
