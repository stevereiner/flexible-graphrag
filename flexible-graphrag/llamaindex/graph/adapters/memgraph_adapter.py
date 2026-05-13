"""LlamaIndex Memgraph property graph adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)


class LlamaIndexMemgraphAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by Memgraph.

    Configuration keys
    ------------------
    url        Bolt URL (default ``bolt://localhost:7688``)
    username   Username (default empty string)
    password   Password (default empty string)
    database   Database name (default ``memgraph``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.graph_stores.memgraph import MemgraphPropertyGraphStore

        url = config.get("url", "bolt://localhost:7688")
        database = config.get("database", "memgraph")
        store = MemgraphPropertyGraphStore(
            username=config.get("username", ""),
            password=config.get("password", ""),
            url=url,
            database=database,
            refresh_schema=False,
        )
        super().__init__(store)
        logger.info("LlamaIndexMemgraphAdapter: url=%s database=%s", url, database)


__all__ = ["LlamaIndexMemgraphAdapter"]
