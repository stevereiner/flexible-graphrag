"""LlamaIndex Neo4j property graph adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)


class LlamaIndexNeo4jGraphAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by Neo4j.

    Configuration keys
    ------------------
    url        Bolt URL (default ``bolt://localhost:7687``)
    username   Neo4j username (default ``neo4j``)
    password   Neo4j password (required)
    database   Database name (default ``neo4j``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

        url = config.get("url", "bolt://localhost:7687")
        store = Neo4jPropertyGraphStore(
            username=config.get("username", "neo4j"),
            password=config["password"],
            url=url,
            database=config.get("database", "neo4j"),
            refresh_schema=False,
        )
        super().__init__(store)
        logger.info("LlamaIndexNeo4jGraphAdapter: url=%s", url)


__all__ = ["LlamaIndexNeo4jGraphAdapter"]
