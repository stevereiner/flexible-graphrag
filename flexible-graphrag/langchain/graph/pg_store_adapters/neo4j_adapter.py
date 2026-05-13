"""LangChain Neo4j property graph adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
    NEO4J_AVAILABLE = True
except ImportError:
    try:
        from langchain_community.graphs import Neo4jGraph  # type: ignore
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain  # type: ignore
        NEO4J_AVAILABLE = True
    except ImportError:
        NEO4J_AVAILABLE = False


class Neo4jAdapter:
    """
    Neo4j property graph adapter.

    Uses the first-party ``langchain_neo4j`` package when available, falls
    back to ``langchain_community.graphs.Neo4jGraph``.

    Configuration (``config`` dict):
        url, username, password, database — Neo4j connection details.

    ``vector_index_config`` (optional):
        If supplied, ``CREATE VECTOR INDEX IF NOT EXISTS`` is run immediately
        on construction so the index is ready before any ingestion starts.
        Keys: index_name, node_label, embedding_property, dimensions.
        Example::

            {
                "index_name": "entity",
                "node_label": "__Entity__",
                "embedding_property": "embedding",
                "dimensions": 1536,
            }

    References:
    - https://python.langchain.com/docs/integrations/graphs/neo4j_cypher
    """

    def __init__(
        self,
        config: Dict[str, Any],
        vector_index_config: Optional[Dict[str, Any]] = None,
    ):
        if not NEO4J_AVAILABLE:
            raise ImportError(
                "langchain-neo4j required. Install: pip install langchain-neo4j"
            )

        self.config = config
        self.lc_graph = Neo4jGraph(
            url=config.get("url", "bolt://localhost:7687"),
            username=config.get("username", "neo4j"),
            password=config.get("password", "password"),
            database=config.get("database", "neo4j"),
        )
        logger.info("Connected to Neo4j at %s", config.get("url", "bolt://localhost:7687"))

        if vector_index_config:
            self._ensure_vector_index(vector_index_config)

    def _ensure_vector_index(self, vic: Dict[str, Any]) -> None:
        """Run ``CREATE VECTOR INDEX IF NOT EXISTS`` — idempotent DDL."""
        index_name  = vic.get("index_name", "entity")
        node_label  = vic.get("node_label", "__Entity__")
        emb_prop    = vic.get("embedding_property", "embedding")
        dims        = int(vic.get("dimensions", 1536))
        cypher = (
            f"CREATE VECTOR INDEX `{index_name}` IF NOT EXISTS "
            f"FOR (n:`{node_label}`) ON n.`{emb_prop}` "
            f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dims}, "
            f"`vector.similarity_function`: 'cosine'}}}}"
        )
        try:
            self.lc_graph.query(cypher)
            logger.info(
                "Neo4j vector index '%s' ensured (label=%s, dims=%d)",
                index_name, node_label, dims,
            )
        except Exception as exc:
            logger.warning("Could not ensure Neo4j vector index '%s': %s", index_name, exc)

    def create_qa_chain(self, llm: Any):
        """Create Cypher QA chain for Neo4j."""
        return GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    def get_graph(self):
        return self.lc_graph

    def close(self) -> None:
        """Close the underlying Neo4j driver to avoid ResourceWarning on GC."""
        graph = getattr(self, "lc_graph", None)
        if graph is None:
            return
        try:
            driver = getattr(graph, "_driver", None)
            if driver is not None:
                driver.close()
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()

    def normalize_entity_names(self) -> None:
        """SET name = id on __Entity__ nodes that lack a name property (Cypher)."""
        try:
            self.lc_graph.query(
                "MATCH (n:__Entity__) WHERE n.name IS NULL AND n.id IS NOT NULL "
                "SET n.name = n.id"
            )
            logger.debug("Neo4j: normalized entity names (id -> name)")
        except Exception as exc:
            logger.warning("Neo4j normalize_entity_names failed: %s", exc)


__all__ = ["Neo4jAdapter", "NEO4J_AVAILABLE"]
