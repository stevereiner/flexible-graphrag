"""LangChain SurrealDB multi-model graph adapter.

Uses langchain-surrealdb (>=0.2.0) which ships ``SurrealDBGraph`` and
``SurrealDBGraphQAChain`` in its experimental module.

Connection strategy
-------------------
``SurrealDBGraph.__init__`` is typed ``SurrealConnection`` =
``BlockingWsSurrealConnection | BlockingHttpSurrealConnection``.  All its
internal helpers (``_query``, ``delete_nodes``, ``add_graph_documents``) call
``connection.query_raw()`` / ``connection.delete()`` synchronously.

``langchain-surrealdb`` 0.2.1 also defines ``SurrealAsyncConnection`` =
``AsyncWsSurrealConnection | AsyncHttpSurrealConnection`` on line 17 of
``surrealdb_graph.py``, but that alias is a dead stub — no async graph class
was ever implemented in the library.

This module fills that gap with ``SurrealDBGraphAsync``, a drop-in async twin
of ``SurrealDBGraph`` that uses ``await connection.query_raw()`` and
``await connection.delete()`` throughout.  ``AsyncSurrealDBAdapter`` wraps it
and manages the ``AsyncWsSurrealConnection`` lifecycle.

``SurrealDBAdapter`` (sync) is kept for backwards compatibility and for callers
that need a ``GraphStore``-compatible object (e.g. ``SurrealDBGraphQAChain``).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_surrealdb.experimental.surrealdb_graph import (
        SurrealDBGraph,
        CREATE_SOURCE_QUERY,
        CREATE_NODE_QUERY,
        RELATE_QUERY,
    )
    from langchain_surrealdb.experimental.graph_qa.chain import SurrealDBGraphQAChain
    SURREALDB_AVAILABLE = True
except ImportError:
    SURREALDB_AVAILABLE = False


def _make_sync_connection(url: str):
    """Return a blocking SurrealDB WebSocket (or HTTP) connection."""
    try:
        from surrealdb.connections.blocking_ws import BlockingWsSurrealConnection
        return BlockingWsSurrealConnection(url)
    except Exception:
        from surrealdb.connections.blocking_http import BlockingHttpSurrealConnection
        return BlockingHttpSurrealConnection(url)


class SurrealDBAdapter:
    """
    SurrealDB multi-model database adapter.

    Supports graph relationships (RELATE), document store, SurrealQL,
    real-time queries (Live SELECT), and full-text search.

    Two connections are managed:

    * **Blocking** (``BlockingWsSurrealConnection``) — required by
      ``SurrealDBGraph`` / ``SurrealDBGraphQAChain`` which call sync methods.
    * **Async** (``AsyncWsSurrealConnection``) — for FastAPI endpoint handlers
      and any direct SurrealQL that must not block the event loop.
      Activated by calling ``await adapter.connect_async()`` after construction.

    Configuration:
    {
        "url": "ws://localhost:8010/rpc",
        "namespace": "flexible_graphrag",
        "database": "graphrag",
        "username": "root",
        "password": "rootpassword"
    }

    Docker: surrealdb/surrealdb:v2.x mapped to host port 8010.

    References:
    - https://surrealdb.com/docs
    - https://github.com/surrealdb/langchain-surrealdb
    """

    def __init__(self, config: Dict[str, Any]):
        if not SURREALDB_AVAILABLE:
            raise ImportError(
                "langchain-surrealdb and surrealdb required. "
                "Install: uv pip install langchain-surrealdb surrealdb"
            )

        self.config = config
        self._url = config.get("url") or "ws://localhost:8010/rpc"
        self._namespace = config.get("namespace") or "flexible_graphrag"
        self._database = config.get("database") or "graphrag"
        self._username = config.get("username") or "root"
        self._password = config.get("password") or "rootpassword"

        # --- blocking connection for SurrealDBGraph ---
        sync_conn = _make_sync_connection(self._url)
        sync_conn.signin({"username": self._username, "password": self._password})
        sync_conn.use(self._namespace, self._database)
        self.lc_graph = SurrealDBGraph(sync_conn)
        logger.info(
            "SurrealDB (sync) connected: %s  ns=%s  db=%s",
            self._url, self._namespace, self._database,
        )

        # --- async connection (AsyncWsSurrealConnection) ---
        # Not opened yet; call connect_async() to activate.
        self._async_conn: Optional[Any] = None

    # ------------------------------------------------------------------
    # Async connection lifecycle
    # ------------------------------------------------------------------

    async def connect_async(self) -> None:
        """Open the async WebSocket connection.

        Safe to call multiple times — a no-op if already connected.
        Intended to be awaited once from a FastAPI ``lifespan`` handler or
        the first async endpoint that needs direct SurrealQL access.
        """
        if self._async_conn is not None:
            return
        from surrealdb.connections.async_ws import AsyncWsSurrealConnection
        conn = AsyncWsSurrealConnection(self._url)
        await conn.connect()
        await conn.signin({"username": self._username, "password": self._password})
        await conn.use(self._namespace, self._database)
        self._async_conn = conn
        logger.info(
            "SurrealDB (async) connected: %s  ns=%s  db=%s",
            self._url, self._namespace, self._database,
        )

    async def close_async(self) -> None:
        """Close the async connection gracefully."""
        if self._async_conn is not None:
            await self._async_conn.close()
            self._async_conn = None

    # ------------------------------------------------------------------
    # Direct async SurrealQL
    # ------------------------------------------------------------------

    async def query_async(self, surql: str, vars: Optional[Dict[str, Any]] = None) -> Any:
        """Run *surql* on the async connection.

        Opens the connection automatically on first call.
        """
        if self._async_conn is None:
            await self.connect_async()
        return await self._async_conn.query(surql, vars or {})

    async def query_raw_async(
        self, surql: str, vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run *surql* and return the raw response envelope."""
        if self._async_conn is None:
            await self.connect_async()
        return await self._async_conn.query_raw(surql, vars or {})

    # ------------------------------------------------------------------
    # LangChain integration
    # ------------------------------------------------------------------

    def add_graph_documents(
        self,
        graph_documents: List[Any],
        include_source: bool = False,
    ) -> None:
        """Write graph documents to SurrealDB, injecting ``name`` and ``type``
        fields into each node's stored properties.

        ``LLMGraphTransformer`` puts the entity name in ``node.id`` but leaves
        ``node.properties`` empty (or sparse).  ``SurrealDBGraph`` stores only
        ``node.properties`` as the record content, so without this injection a
        query like ``WHERE string::lowercase(name) CONTAINS "acme"`` always
        returns an empty result set.
        """
        for doc in graph_documents:
            for node in doc.nodes:
                node.properties.setdefault("name", node.id)
                node.properties.setdefault("type", node.type)
        self.lc_graph.add_graph_documents(
            graph_documents, include_source=include_source
        )

    def create_qa_chain(self, llm: Any):
        """Create SurrealQL QA chain (uses the blocking connection)."""
        return SurrealDBGraphQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    def get_graph(self) -> SurrealDBGraph:
        return self.lc_graph

    # ------------------------------------------------------------------
    # Utility helpers — sync and async variants
    # ------------------------------------------------------------------

    def normalize_entity_names(self) -> None:
        """Copy id -> name on entity records (blocking)."""
        surql = (
            "UPDATE type::table('__Entity__') "
            "SET name = id "
            "WHERE name = NONE AND id != NONE"
        )
        try:
            self.lc_graph.query(surql)
            logger.debug("SurrealDB: normalized entity names (sync)")
        except Exception as exc:
            logger.warning("SurrealDB normalize_entity_names failed: %s", exc)

    async def normalize_entity_names_async(self) -> None:
        """Copy id -> name on entity records (async, non-blocking)."""
        surql = (
            "UPDATE type::table('__Entity__') "
            "SET name = id "
            "WHERE name = NONE AND id != NONE"
        )
        try:
            await self.query_async(surql)
            logger.debug("SurrealDB: normalized entity names (async)")
        except Exception as exc:
            logger.warning("SurrealDB normalize_entity_names_async failed: %s", exc)


# ---------------------------------------------------------------------------
# Async graph class — fills the gap left by langchain-surrealdb 0.2.1
#
# ``langchain-surrealdb`` defines ``SurrealAsyncConnection`` but never ships a
# matching async graph class.  This is a faithful async re-implementation of
# ``SurrealDBGraph`` using ``AsyncWsSurrealConnection`` / ``AsyncHttpSurrealConnection``.
# ---------------------------------------------------------------------------

class SurrealDBGraphAsync:
    """Async twin of ``SurrealDBGraph`` that uses ``AsyncWsSurrealConnection``.

    All methods that touch the database are coroutines; the caller is
    responsible for ``await``-ing them.

    Usage::

        conn = AsyncWsSurrealConnection("ws://localhost:8010")
        await conn.connect()
        await conn.signin({"username": "root", "password": "rootpassword"})
        await conn.use("flexible_graphrag", "graphrag")
        graph = SurrealDBGraphAsync(conn)

        schema = await graph.get_schema()
        results = await graph.query("SELECT * FROM graph_Person LIMIT 5")
    """

    def __init__(
        self,
        connection: Any,  # AsyncWsSurrealConnection | AsyncHttpSurrealConnection
        *,
        table_prefix: str = "graph_",
        relation_prefix: str = "relation_",
    ) -> None:
        self.connection = connection
        self.table_prefix = table_prefix
        self.relation_prefix = relation_prefix

    async def _query(self, surql: str, vars: Dict[str, Any]) -> Dict[str, Any]:
        return await self.connection.query_raw(surql, vars)

    async def get_schema(self) -> str:
        info = await self._query("INFO FOR DB", {})
        nodes: List[str] = []
        edges: List[str] = []
        temp = info.get("result")
        if isinstance(temp, list) and temp and isinstance(temp[0], dict) and "result" in temp[0]:
            temp = temp[0]["result"]
        if isinstance(temp, dict) and "tables" in temp and isinstance(temp["tables"], dict):
            for table in temp["tables"].keys():
                assert isinstance(table, str)
                if table.startswith(self.table_prefix):
                    nodes.append(table)
                elif table.startswith(self.relation_prefix):
                    edges.append(table)
        return json.dumps({"nodes": nodes, "edges": edges})

    async def query(
        self,
        surql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        res = await self._query(surql, params or {})
        if "error" in res:
            raise Exception(res["error"]["message"])
        result = res["result"][0]["result"]
        if isinstance(result, list):
            return result
        raise ValueError(f"Unexpected result type: {type(result)} value={result}")

    async def delete_nodes(
        self, ids: Optional[List[tuple]] = None
    ) -> None:
        if SURREALDB_AVAILABLE:
            from surrealdb import RecordID
        else:
            raise ImportError("surrealdb package required")

        if ids is not None:
            for table, _id in ids:
                if _id is None:
                    await self.connection.delete(table)
                else:
                    await self.connection.delete(RecordID(table, _id))
        else:
            info = await self.connection.query("INFO FOR DB", {})
            if isinstance(info, dict) and "tables" in info and isinstance(info["tables"], dict):
                for table in info["tables"].keys():
                    await self.connection.delete(table)
            await self.connection.delete(self.table_prefix + "source")

    async def add_graph_documents(
        self,
        graph_documents: List[Any],
        include_source: bool = False,
    ) -> None:
        """Async version of ``SurrealDBGraph.add_graph_documents``."""
        if SURREALDB_AVAILABLE:
            from surrealdb import RecordID
        else:
            raise ImportError("surrealdb package required")

        def _record_id(node: Any) -> Any:
            return RecordID(self.table_prefix + node.type, node.id)

        for doc in graph_documents:
            source = None
            if include_source:
                raw = await self._query(
                    CREATE_SOURCE_QUERY,
                    {
                        "table": self.table_prefix + "source",
                        "content": {
                            "page_content": doc.source.page_content,
                            "metadata": doc.source.metadata,
                        },
                    },
                )
                source = raw["result"][0]["result"][0]

            for node in doc.nodes:
                content = {"name": node.id, "type": node.type, **node.properties}
                await self._query(
                    CREATE_NODE_QUERY,
                    {"record_id": _record_id(node), "content": content},
                )
                if include_source and source is not None:
                    await self._query(
                        RELATE_QUERY,
                        {
                            "in": source["id"],
                            "relation": "MENTIONS",
                            "out": _record_id(node),
                            "content": {},
                        },
                    )

            for rel in doc.relationships:
                await self._query(
                    RELATE_QUERY,
                    {
                        "in": _record_id(rel.source),
                        "relation": self.relation_prefix + rel.type,
                        "out": _record_id(rel.target),
                        "content": rel.properties,
                    },
                )


# ---------------------------------------------------------------------------
# Async-native adapter — uses SurrealDBGraphAsync throughout
# ---------------------------------------------------------------------------

class AsyncSurrealDBAdapter:
    """Async-native SurrealDB adapter backed by ``AsyncWsSurrealConnection``.

    Construct it, then call ``await adapter.connect()`` before use.
    All graph and query operations are non-blocking coroutines.

    Configuration keys are identical to ``SurrealDBAdapter``::

        {
            "url": "ws://localhost:8010/rpc",
            "namespace": "flexible_graphrag",
            "database": "graphrag",
            "username": "root",
            "password": "rootpassword"
        }
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        if not SURREALDB_AVAILABLE:
            raise ImportError(
                "langchain-surrealdb and surrealdb required. "
                "Install: uv pip install langchain-surrealdb surrealdb"
            )
        self.config = config
        self._url = config.get("url") or "ws://localhost:8010/rpc"
        self._namespace = config.get("namespace") or "flexible_graphrag"
        self._database = config.get("database") or "graphrag"
        self._username = config.get("username") or "root"
        self._password = config.get("password") or "rootpassword"
        self._conn: Optional[Any] = None
        self.graph: Optional[SurrealDBGraphAsync] = None

    async def connect(self) -> None:
        """Open the WebSocket connection and select namespace/database.

        Safe to call multiple times.
        """
        if self._conn is not None:
            return
        from surrealdb.connections.async_ws import AsyncWsSurrealConnection
        conn = AsyncWsSurrealConnection(self._url)
        await conn.connect()
        await conn.signin({"username": self._username, "password": self._password})
        await conn.use(self._namespace, self._database)
        self._conn = conn
        self.graph = SurrealDBGraphAsync(conn)
        logger.info(
            "SurrealDB (async) connected: %s  ns=%s  db=%s",
            self._url, self._namespace, self._database,
        )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            self.graph = None

    async def query(self, surql: str, vars: Optional[Dict[str, Any]] = None) -> Any:
        if self._conn is None:
            await self.connect()
        return await self._conn.query(surql, vars or {})

    async def query_raw(self, surql: str, vars: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self._conn is None:
            await self.connect()
        return await self._conn.query_raw(surql, vars or {})

    async def normalize_entity_names(self) -> None:
        surql = (
            "UPDATE type::table('__Entity__') "
            "SET name = id "
            "WHERE name = NONE AND id != NONE"
        )
        try:
            await self.query(surql)
            logger.debug("SurrealDB: normalized entity names (async)")
        except Exception as exc:
            logger.warning("SurrealDB normalize_entity_names failed: %s", exc)

    def get_graph(self) -> Optional[SurrealDBGraphAsync]:
        return self.graph


__all__ = [
    "SurrealDBAdapter",
    "AsyncSurrealDBAdapter",
    "SurrealDBGraphAsync",
    "SURREALDB_AVAILABLE",
]
