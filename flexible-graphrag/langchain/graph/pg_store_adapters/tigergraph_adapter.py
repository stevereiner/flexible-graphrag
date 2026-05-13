"""LangChain TigerGraph distributed analytics graph database adapter."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    from langchain_community.graphs import TigerGraph
    TIGERGRAPH_AVAILABLE = True
except ImportError:
    TIGERGRAPH_AVAILABLE = False

# Characters unsafe for TigerGraph vertex IDs
_UNSAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_\-\.]")


def _safe_id(raw: str) -> str:
    """Sanitise a node ID for use as a TigerGraph PRIMARY_ID."""
    return _UNSAFE_ID_RE.sub("_", raw.replace(" ", "_")).strip("_") or "unknown"


class TigerGraphAdapter:
    """
    TigerGraph distributed graph analytics database adapter.

    Uses GSQL (Graph SQL) via pyTigerGraph.  ``add_graph_documents`` creates the
    ``__Entity__`` vertex type and ``__Relationship__`` edge type on demand then
    upserts all nodes and edges via the REST++ API.

    Configuration:
    {
        "host": "http://localhost",
        "port": 14240,            # GraphStudio / GSQL server port (docker: 14240:14240)
        "restpp_port": 9002,      # RESTPP HTTP API port (docker: 9002:9000)
        "database": "MyGraph",
        "username": "tigergraph",
        "password": "tigergraph",
        "gsql_secret": ""
    }

    Docker: docker/includes/tigergraph.yaml
      - Port 14240 → GraphStudio UI + GSQL server  http://localhost:14240
      - Port 9002  → RESTPP / GSQL HTTP API        http://localhost:9002  (container 9000)

    Note: ``langchain_community.graphs.TigerGraph`` was designed for TigerGraph Cloud
    with the NLQS (Natural Language Query Service).  For a local Docker instance, we
    create the ``pyTigerGraph.TigerGraphConnection`` manually and set ``nlqs_host`` to
    the local host so the not-None guard in ``set_connection()`` passes.
    NLQS-based AI features are not available without the actual cloud service.

    References:
    - https://www.tigergraph.com/
    - https://python.langchain.com/docs/integrations/graphs/tigergraph
    - https://pytigergraph.github.io/pyTigerGraph/
    """

    def __init__(self, config: Dict[str, Any]):
        if not TIGERGRAPH_AVAILABLE:
            raise ImportError(
                "langchain-community required. "
                "Install: pip install langchain-community pyTigerGraph"
            )

        self.config = config

        try:
            from pyTigerGraph import TigerGraphConnection
        except ImportError as exc:
            raise ImportError(
                "pyTigerGraph is required for TigerGraph support. "
                "Install: pip install pyTigerGraph"
            ) from exc

        host        = config.get("host", "http://localhost")
        graphname   = config.get("database", "MyGraph")
        username    = config.get("username", "tigergraph")
        password    = config.get("password", "tigergraph")
        gs_port     = int(config.get("port", 14240))        # GraphStudio / GSQL server
        restpp_port = int(config.get("restpp_port", 9002))  # RESTPP API (container 9000 → host 9002)

        # Typed as Any so free attribute access (gsqlSecret, ai.nlqs_host, …)
        # works without stubs — pyTigerGraph's type information is incomplete.
        conn: Any = TigerGraphConnection(
            host=host,
            graphname=graphname,
            username=username,
            password=password,
            gsPort=gs_port,
            restppPort=restpp_port,
        )
        if config.get("gsql_secret"):
            conn.gsqlSecret = config["gsql_secret"]

        # langchain_community TigerGraph.set_connection() raises ConnectionError if
        # conn.ai.nlqs_host is None (guards against missing NLQS cloud service).
        # For a local Docker TigerGraph without NLQS, we set it to the host URL so
        # the not-None check passes.  NLQS AI features won't be available.
        conn.ai.nlqs_host = host

        # Auto-setup: create global types + graph in one idempotent sequence.
        self._ensure_graph_and_schema(conn, graphname)

        self.lc_graph = TigerGraph(conn=conn)  # type: ignore[possibly-unbound]
        logger.info("Connected to TigerGraph at %s (gsPort=%s, restppPort=%s, graph=%s)",
                    host, gs_port, restpp_port, graphname)

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    def _ensure_graph_and_schema(self, conn: Any, graphname: str) -> None:
        """Idempotent setup: global types → graph with those types.

        TigerGraph requires vertex/edge types to be created in the **global
        catalog** before they can be referenced in any graph.  The cleanest
        one-shot approach is therefore:

        1. ``CREATE VERTEX __Entity__ (...)``          — global, safe to retry
        2. ``CREATE UNDIRECTED EDGE __Relationship__ (...)`` — global, safe to retry
        3. ``CREATE GRAPH {graphname}(__Entity__, __Relationship__)``
              — if the graph already exists but is empty, drop + recreate
              — if it already has both types, skip entirely
        """
        def _gsql(stmt: str, label: str) -> str:
            try:
                r = conn.gsql(stmt)
                logger.info("TigerGraph %s: %s", label, str(r)[:300])
                return str(r)
            except Exception as exc:
                logger.info("TigerGraph %s (%s): %s", label, "may already exist", exc)
                return str(exc)

        # ── Step 1 & 2: global type declarations ─────────────────────────────
        _gsql(
            "CREATE VERTEX __Entity__ "
            "(PRIMARY_ID id STRING, name STRING, node_type STRING, source STRING) "
            'WITH primary_id_as_attribute="true"',
            "CREATE VERTEX __Entity__",
        )
        _gsql(
            "CREATE UNDIRECTED EDGE __Relationship__ "
            "(FROM __Entity__, TO __Entity__, rel_type STRING, source STRING)",
            "CREATE EDGE __Relationship__",
        )

        # ── Step 3: attach types to the graph ─────────────────────────────────
        # Fast-path: graph already has both types
        try:
            schema = conn.getSchema(force=True)
            vtypes = {vt.get("Name", "") for vt in schema.get("VertexTypes", [])}
            etypes = {et.get("Name", "") for et in schema.get("EdgeTypes", [])}
            if "__Entity__" in vtypes and "__Relationship__" in etypes:
                logger.debug("TigerGraph: %s already has __Entity__ + __Relationship__", graphname)
                return
        except Exception:
            vtypes, etypes = set(), set()

        # Try creating the graph with the types (works on first run)
        r = _gsql(
            f"CREATE GRAPH {graphname}(__Entity__, __Relationship__)",
            f"CREATE GRAPH {graphname}",
        )

        # If the graph already existed (and is empty), drop + recreate
        if "already exists" in r.lower() or "exist" in r.lower() or "could not be created" in r.lower():
            logger.info(
                "TigerGraph: %s exists without __Entity__ — dropping queries then graph", graphname
            )
            # Must drop all installed queries before DROP GRAPH will succeed
            try:
                conn.gsql(f"USE GRAPH {graphname}")
                r2 = conn.gsql("DROP QUERY *")
                logger.info("TigerGraph DROP QUERY *: %s", str(r2)[:200])
            except Exception as exc:
                logger.debug("TigerGraph DROP QUERY * (OK if none): %s", exc)
            _gsql(f"DROP GRAPH {graphname}", f"DROP GRAPH {graphname}")
            _gsql(
                f"CREATE GRAPH {graphname}(__Entity__, __Relationship__)",
                f"CREATE GRAPH {graphname} (retry)",
            )

        # Final verification
        try:
            new_schema = conn.getSchema(force=True)
            new_vtypes = {vt.get("Name", "") for vt in new_schema.get("VertexTypes", [])}
            logger.info("TigerGraph schema after setup: vtypes=%s", new_vtypes)
        except Exception as exc:
            logger.warning("TigerGraph final getSchema failed: %s", exc)

    # Keep the old names as thin wrappers so any subclass overrides still work.
    def _ensure_graph(self, conn: Any, graphname: str) -> None:
        self._ensure_graph_and_schema(conn, graphname)

    def _ensure_schema(self, conn: Any, graphname: str) -> None:
        self._ensure_graph_and_schema(conn, graphname)

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def add_graph_documents(
        self,
        graph_documents: List[Any],
        include_source: bool = False,
    ) -> None:
        """Write extracted graph documents to TigerGraph via REST++ upsert API.

        Ensures ``__Entity__`` and ``__Relationship__`` schema types exist before
        upserting.  Uses batch operations for efficiency.
        """
        graphname = self.config.get("database", "MyGraph")
        conn = self.lc_graph.conn

        # Ensure vertex / edge types are in the schema (fast-path if already there)
        self._ensure_graph_and_schema(conn, graphname)

        total_nodes = total_edges = 0

        for doc in graph_documents:
            source_id = ""
            if include_source and doc.source:
                source_id = doc.source.metadata.get("source", "")

            # ---- Upsert vertices ----------------------------------------
            vertices = []
            for node in doc.nodes:
                vid  = _safe_id(node.id)
                name = node.id
                ntype = node.type or ""
                vertices.append((vid, {"name": name, "node_type": ntype, "source": source_id}))

            if vertices:
                try:
                    written = conn.upsertVertices("__Entity__", vertices)
                    total_nodes += written if isinstance(written, int) else len(vertices)
                except Exception as exc:
                    logger.warning("TigerGraph upsertVertices error: %s", exc)

            # ---- Upsert edges -------------------------------------------
            edges: List[tuple] = []
            for rel in doc.relationships:
                src = _safe_id(rel.source.id)
                tgt = _safe_id(rel.target.id)
                rtype = (rel.type or "RELATED_TO").upper().replace(" ", "_")
                edges.append((src, tgt, {"rel_type": rtype, "source": source_id}))

            if edges:
                try:
                    written = conn.upsertEdges(
                        "__Entity__", "__Relationship__", "__Entity__", edges
                    )
                    total_edges += written if isinstance(written, int) else len(edges)
                except Exception as exc:
                    logger.warning("TigerGraph upsertEdges error: %s", exc)

        logger.info(
            "TigerGraph: upserted %d vertices, %d edges into %s",
            total_nodes, total_edges, graphname,
        )

    # ------------------------------------------------------------------
    # Post-ingest normalisation
    # ------------------------------------------------------------------

    def normalize_entity_names(self) -> None:
        """Fill empty ``name`` properties from the vertex ID using an interpreted query.

        Uses ``runInterpretedQuery`` so no prior query installation is needed.
        """
        graphname = self.config.get("database", "MyGraph")
        # POST-ACCUM is required for vertex attribute updates in GSQL;
        # ACCUM is for edge-set operations and cannot update vertex attributes.
        gsql = (
            f"INTERPRET QUERY() FOR GRAPH {graphname} {{\n"
            f"  Seed = {{__Entity__.*}};\n"
            f"  X = SELECT s FROM Seed:s\n"
            f"      WHERE s.name == \"\" AND s.id != \"\"\n"
            f"      POST-ACCUM s.name = s.id;\n"
            f"  PRINT X;\n"
            f"}}"
        )
        try:
            conn = getattr(self.lc_graph, "conn", None)
            if conn is None:
                return
            result = conn.runInterpretedQuery(gsql)
            logger.debug("TigerGraph: normalized entity names, result: %s", result)
        except Exception as exc:
            logger.warning("TigerGraph normalize_entity_names failed: %s", exc)

    # ------------------------------------------------------------------
    # QA chain + retrieval
    # ------------------------------------------------------------------

    def create_qa_chain(self, llm: Any):
        """Create GSQL QA chain for TigerGraph.

        Tries ``TigerGraphQAChain`` first (NLQS, cloud-only); falls back to the
        custom GSQL interpreted-query chain wired in
        ``lc_graph_retriever._build_qa_chain``.
        """
        try:
            from langchain_community.chains.graph_qa.tigergraph import TigerGraphQAChain  # type: ignore[import-not-found]
            return TigerGraphQAChain.from_llm(
                llm=llm,
                graph=self.lc_graph,
                verbose=False,
            )
        except (ImportError, Exception) as exc:
            logger.debug("TigerGraphQAChain unavailable (%s); chain built by retriever factory", exc)
            return None

    def get_graph(self):
        # Return a lightweight wrapper whose .query() runs GSQL via conn.gsql()
        # instead of the NLQS AI endpoint (which requires TigerGraph Cloud port 80).
        # This lets /api/graph/query work against local Docker TigerGraph instances.
        lc_graph = self.lc_graph
        conn = lc_graph._conn  # pyTigerGraphConnection

        _conn_ref = conn
        _lc_graph_ref = lc_graph

        class _TigerGraphGSQLView:
            """Thin wrapper exposing a .query(gsql) method via the GSQL endpoint.

            Exposes ``conn`` so that ``build_gsql_tigergraph`` in
            ``retrievers/chains/_gsql.py`` can detect it and use the custom
            interpreted-query chain instead of falling back to GraphCypherQAChain.
            """

            schema = getattr(_lc_graph_ref, "schema", "")
            structured_schema = getattr(_lc_graph_ref, "structured_schema", {})

            def __init__(self):
                # Bind conn as an instance attribute so hasattr(graph, "conn") is True
                # and _gsql.py can read graph.conn directly.
                self.conn = _conn_ref

            def get_structured_schema(self) -> dict:  # type: ignore[override]
                return getattr(_lc_graph_ref, "get_structured_schema", lambda: {})()

            def query(self, gsql: str, params: dict = {}) -> list:
                try:
                    result = _conn_ref.gsql(gsql)
                    if isinstance(result, str):
                        return [{"result": result}]
                    if isinstance(result, list):
                        return result
                    return [{"result": str(result)}]
                except Exception as exc:
                    logger.debug("TigerGraph GSQL query failed: %s", exc)
                    return [{"error": str(exc)}]

            def refresh_schema(self) -> None:
                try:
                    _lc_graph_ref.refresh_schema()
                except Exception:
                    pass

        return _TigerGraphGSQLView()

    def get_lc_graph(self):
        """Return the GSQL view for /api/graph/query routing (avoids NLQS port 80)."""
        return self.get_graph()


__all__ = ["TigerGraphAdapter", "TIGERGRAPH_AVAILABLE"]
