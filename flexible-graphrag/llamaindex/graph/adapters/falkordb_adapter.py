"""LlamaIndex FalkorDB property graph adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)


class LlamaIndexFalkorDBAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by FalkorDB.

    Configuration keys
    ------------------
    url       FalkorDB URL (default ``falkor://localhost:6379``)
    database  Database name (default ``falkor``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.graph_stores.falkordb import FalkorDBPropertyGraphStore
        from llamaindex.graph.adapters.falkordb_param_patch import ensure_falkordb_stringify_patch

        url = config.get("url", "falkor://localhost:6379")
        database = config.get("database", "falkor")
        ensure_falkordb_stringify_patch()
        store = FalkorDBPropertyGraphStore(
            url=url,
            database=database,
            refresh_schema=False,
            sanitize_query_output=True,
        )
        try:
            logger.info("LlamaIndexFalkorDBAdapter: creating indexes for optimization...")
            store.client.query("CREATE INDEX FOR (e:__Entity__) ON (e.name)")
            store.client.query("CREATE INDEX FOR (e:__Entity__) ON (e.id)")
            store.client.query("CREATE INDEX FOR (c:Chunk) ON (c.id)")
            logger.info("LlamaIndexFalkorDBAdapter: indexes created successfully")
        except Exception as exc:
            logger.warning("LlamaIndexFalkorDBAdapter: index creation failed (may already exist): %s", exc)
        super().__init__(store)
        logger.info("LlamaIndexFalkorDBAdapter: url=%s database=%s", url, database)


__all__ = ["LlamaIndexFalkorDBAdapter"]
