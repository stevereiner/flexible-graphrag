"""LlamaIndex ArcadeDB property graph adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)


class LlamaIndexArcadeDBAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by ArcadeDB.

    Configuration keys
    ------------------
    host / port           Remote connection (defaults ``localhost:2480``)
    username / password   Auth credentials
    database              Database name (default ``flexible_graphrag``)
    include_basic_schema  Include basic node/edge schema (default ``True``)
    mode                  ``remote`` (default) or ``embedded``
    db_path               Path for embedded mode (default ``./arcadedb_data``)
    embedded_server       Start embedded HTTP server (default ``False``)
    embedded_server_port  Port for embedded HTTP server (default ``2482``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.graph_stores.arcadedb import ArcadeDBPropertyGraphStore

        database = config.get("database", "flexible_graphrag")
        include_basic_schema = config.get("include_basic_schema", True)
        mode = config.get("mode", "remote")

        if mode == "embedded":
            db_path = config.get("db_path", "./arcadedb_data")
            embedded_server = config.get("embedded_server", False)
            embedded_server_port = config.get("embedded_server_port", 2482)
            store = ArcadeDBPropertyGraphStore(
                mode="embedded",
                db_path=db_path,
                database=database,
                embedded_server=embedded_server,
                embedded_server_port=embedded_server_port,
                embedded_server_password=config.get("embedded_server_password"),
                embedding_dimension=embed_dim,
                include_basic_schema=include_basic_schema,
            )
            logger.info("LlamaIndexArcadeDBAdapter: embedded db_path=%s embed_dim=%s", db_path, embed_dim)
        else:
            host = config.get("host", "localhost")
            port = config.get("port", 2480)
            store = ArcadeDBPropertyGraphStore(
                host=host,
                port=port,
                username=config.get("username", "root"),
                password=config.get("password", "playwithdata"),
                database=database,
                embedding_dimension=embed_dim,
                include_basic_schema=include_basic_schema,
            )
            logger.info("LlamaIndexArcadeDBAdapter: host=%s:%s embed_dim=%s", host, port, embed_dim)
        super().__init__(store)


__all__ = ["LlamaIndexArcadeDBAdapter"]
