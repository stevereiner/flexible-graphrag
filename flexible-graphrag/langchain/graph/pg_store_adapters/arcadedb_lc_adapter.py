"""LangChain ArcadeDB multi-model graph adapter.

Uses the official ``langchain-arcadedb`` package (https://github.com/ArcadeData/langchain-arcadedb)
which connects via the Bolt protocol (Neo4j Python driver).

Note: ArcadeDB's primary LlamaIndex integration (used for ingestion) lives in
``llamaindex.graph``. This LangChain adapter is used for text-to-Cypher
retrieval when GRAPH_BACKEND=langchain is set explicitly.

ArcadeDB must be started with the Bolt plugin enabled:
  -e JAVA_OPTS="-Darcadedb.server.plugins=Bolt:com.arcadedb.bolt.BoltProtocolPlugin"
Bolt port default: 7687. HTTP port (2480) is NOT used here.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


def _sql_id(ident: str) -> str:
    """Backtick-quote an ArcadeDB SQL identifier (strip embedded backticks)."""
    return f"`{str(ident).replace('`', '')}`"


# LlamaIndex copies node-level metadata (file path, source, doc_id, …) into
# every entity node's properties during KG extraction.  These are *ingestion*
# metadata fields, not graph-model properties.  We skip them when collecting the
# set of columns to pre-declare on ArcadeDB types so we don't flood the schema
# with dozens of filesystem metadata columns on every vertex type.
_LI_METADATA_SKIP: frozenset = frozenset({
    "source", "conversion_method", "file_type", "file_name",
    "file_path", "modified_at", "modified at", "doc_id",
    # ref_doc_id is explicitly added as a baseline — don't skip it here
})

try:
    from langchain_arcadedb import ArcadeDBGraph
    ARCADEDB_LC_AVAILABLE = True
except ImportError:
    ARCADEDB_LC_AVAILABLE = False


class ArcadeDBLangChainAdapter:
    """
    ArcadeDB multi-model graph database LangChain adapter.

    ArcadeDB supports Documents, Graph, Key-Value, and Time Series models
    with native Cypher via Bolt protocol (Neo4j-compatible driver).

    Configuration:
    {
        "url": "bolt://localhost:7687",
        "username": "root",
        "password": "playwithdata",
        "database": "flexible_graphrag"
    }

    References:
    - https://github.com/ArcadeData/langchain-arcadedb
    - https://docs.arcadedb.com/
    """

    def __init__(self, config: Dict[str, Any]):
        if not ARCADEDB_LC_AVAILABLE:
            raise ImportError(
                "langchain-arcadedb required. "
                "Install: pip install langchain-arcadedb"
            )

        self.config = config
        host = config.get("host", "localhost")
        http_port = config.get("port", 2480)
        username = config.get("username", "root")
        password = config.get("password", "playwithdata")
        database = config.get("database", "flexible_graphrag")

        # Ensure the ArcadeDB database exists before opening a Bolt connection.
        # ArcadeDB creates databases via its HTTP REST API; Bolt queries will
        # fail with "Database does not exist" if the DB was never created.
        self._ensure_database_http(host, http_port, username, password, database)

        # ArcadeDBGraph uses the Neo4j Bolt driver — URL must be bolt://, not http://
        # ArcadeDB Bolt default is 7689 to avoid conflict with Neo4j (7687) and MemGraph (7688).
        bolt_url = config.get("bolt_url") or config.get("url")
        if not bolt_url:
            bolt_port = config.get("bolt_port", 7689)
            bolt_url = f"bolt://{host}:{bolt_port}"
            logger.debug("ArcadeDB LangChain adapter: derived Bolt URL %s from host/port config", bolt_url)
        elif bolt_url.startswith("http"):
            # Graceful fallback: if caller passed HTTP URL, derive Bolt URL
            host = bolt_url.split("://", 1)[-1].split(":")[0]
            bolt_url = f"bolt://{host}:7687"
            logger.warning(
                "ArcadeDB LangChain adapter requires Bolt URL; derived %s from config", bolt_url
            )
        self._bolt_url = bolt_url
        self.lc_graph = ArcadeDBGraph(
            url=bolt_url,
            username=username,
            password=password,
            database=database,
        )
        # The langchain_arcadedb schema.py calls driver.execute_query() without
        # database_=, so schema introspection silently returns empty results.
        # Force a correct refresh via graph.query() which includes the database.
        self._refresh_schema(self.lc_graph)
        logger.info("Connected to ArcadeDB (Bolt/LC) at %s", bolt_url)

    @staticmethod
    def _ensure_database_http(
        host: str, port: int, username: str, password: str, database: str
    ) -> None:
        """Create the ArcadeDB database if it does not exist.

        Uses the ``arcadedb-python`` client (already a project dependency via
        the LlamaIndex ArcadeDB graph store).  This is the same approach used
        by ``ArcadeDBPropertyGraphStore._init_remote``.
        """
        try:
            from arcadedb_python.api.sync import SyncClient
            from arcadedb_python.dao.database import DatabaseDao

            client = SyncClient(
                host=host,
                port=port,
                username=username,
                password=password,
                content_type="application/json",
            )
            if not DatabaseDao.exists(client, database):
                DatabaseDao.create(client, database)
                logger.info("ArcadeDB: created database '%s'", database)
            else:
                logger.debug("ArcadeDB database '%s' already exists", database)
        except Exception as exc:
            # Non-fatal: Bolt may still work if DB was created by another path
            logger.warning(
                "ArcadeDB database-ensure failed for '%s' (non-fatal): %s",
                database, exc,
            )

    @staticmethod
    def _refresh_schema(graph, ontology_manager=None) -> None:
        """Refresh ArcadeDBGraph schema using graph.query() so the database
        context is included.

        langchain_arcadedb's refresh_schema() calls driver.execute_query()
        without database_= and silently returns an empty schema.  graph.query()
        correctly passes database_=self._database, so we replicate the
        introspection here and write the results back onto the graph object.

        If *ontology_manager* is provided, its per-entity property definitions
        are merged in so the LLM sees rich property names even when nodes only
        have ``id``/``name`` stored in the database.
        """
        try:
            _TYPE_MAP = {int: "INTEGER", float: "FLOAT", str: "STRING",
                         bool: "BOOLEAN", list: "LIST"}

            def _infer(v):
                for py_t, s in _TYPE_MAP.items():
                    if isinstance(v, py_t):
                        return s
                return "STRING"

            labels = [
                r["label"]
                for r in graph.query(
                    "MATCH (n) RETURN DISTINCT labels(n)[0] AS label"
                )
                if r.get("label")
            ]

            node_props: dict = {}
            for label in labels:
                try:
                    rows = graph.query(f"MATCH (n:`{label}`) RETURN n LIMIT 25")
                    props: dict = {}
                    for row in rows:
                        node = row.get("n") or {}
                        if hasattr(node, "items"):
                            for k, v in node.items():
                                if k not in props and v is not None:
                                    props[k] = _infer(v)
                    node_props[label] = [{"property": k, "type": t} for k, t in props.items()]
                except Exception:
                    node_props[label] = []

            # Merge ontology-defined properties so the LLM sees richer schema
            # even when nodes only have id/name stored in the DB.
            if ontology_manager is not None:
                try:
                    onto_props = ontology_manager.get_entity_properties()  # {EntityName: {prop: type}}
                    for label in labels:
                        onto = onto_props.get(label) or onto_props.get(label.upper()) or onto_props.get(label.lower())
                        if not onto:
                            continue
                        existing_keys = {p["property"] for p in node_props.get(label, [])}
                        for prop_name, prop_type in onto.items():
                            if prop_name not in existing_keys:
                                node_props.setdefault(label, []).append(
                                    {"property": prop_name, "type": str(prop_type).upper() or "STRING"}
                                )
                except Exception as _oe:
                    logger.debug("Could not merge ontology properties into schema: %s", _oe)

            relationships = [
                {"start": r["start"], "type": r["type"], "end": r["end"]}
                for r in graph.query(
                    "MATCH (a)-[r]->(b) "
                    "RETURN DISTINCT labels(a)[0] AS start, "
                    "type(r) AS type, labels(b)[0] AS end"
                )
                if r.get("start") and r.get("end")
            ]

            structured = {
                "node_props": node_props,
                "rel_props": {},
                "relationships": relationships,
                "metadata": {"constraint": [], "index": []},
            }

            from langchain_arcadedb.schema import format_schema
            graph._structured_schema = structured
            graph._schema = format_schema(structured)
            logger.info(
                "ArcadeDB schema refreshed: %d labels, %d relationship patterns",
                len(labels), len(relationships),
            )
        except Exception as exc:
            logger.warning("ArcadeDB schema refresh via graph.query() failed: %s", exc)

    def add_graph_documents(
        self,
        graph_documents: list,
        include_source: bool = False,
        **kwargs,
    ) -> None:
        """Pre-create all vertex types before delegating to langchain_arcadedb.

        ArcadeDB's OpenCypher engine (Bolt) requires vertex types to be
        pre-declared in the schema.  Unlike Neo4j, a ``MATCH (n:`UnknownType`...)``
        raises ``SchemaException: Type with name 'X' was not found`` if that type
        was never registered — even when only used as a relationship endpoint.

        ``LLMGraphTransformer`` often produces relationships whose source or target
        nodes are *not* listed in ``document.nodes`` (e.g. ``Place`` appearing only
        as a target of ``LOCATED_IN``).  Those types would never be created by the
        default add_graph_documents, causing every relationship to that type to fail.

        Fix: collect all types from both nodes AND relationship endpoints, then
        register any that are missing via ArcadeDB SQL DDL using the same
        ``SyncClient`` + ``DatabaseDao`` pattern as ``_ensure_database_http``.
        """
        host = self.config.get("host", "localhost")
        http_port = self.config.get("port", 2480)
        username = self.config.get("username", "root")
        password = self.config.get("password", "playwithdata")
        database = self.config.get("database", "flexible_graphrag")

        # Collect every vertex type referenced in this batch (nodes + rel endpoints)
        all_types: set = set()
        for doc in graph_documents:
            for n in doc.nodes:
                if n.type:
                    all_types.add(n.type)
            for rel in doc.relationships:
                if rel.source.type:
                    all_types.add(rel.source.type)
                if rel.target.type:
                    all_types.add(rel.target.type)

        if include_source:
            all_types.add("Document")

        if all_types:
            self._ensure_vertex_types(host, http_port, username, password, database, all_types)

        # ArcadeDB (like Apache AGE) shares a namespace for vertex and edge types.
        # If the LLM produces a relationship type that collides with a vertex type
        # (e.g. DATE as both a node and a relationship), ArcadeDB rejects the MERGE.
        # Rename colliding relationship types by appending _REL.
        vertex_type_names = all_types  # already collected above
        for doc in graph_documents:
            for rel in doc.relationships:
                if rel.type and rel.type in vertex_type_names:
                    rel.type = rel.type + "_REL"
                if rel.properties is None:
                    rel.properties = {}

        # ArcadeDB requires every property used in OpenCypher ``SET n += row.properties``
        # (and ``SET r += row.properties``) to exist on the type DDL first.  Empty
        # ``CREATE VERTEX TYPE`` leaves no columns, so the first batch MERGE fails with
        # a generic Bolt UnknownError.  Pre-declare properties via SQL before LC import.
        edge_types: Set[str] = set()
        vprops: dict[str, Set[str]] = defaultdict(set)
        eprops: dict[str, Set[str]] = defaultdict(set)
        for doc in graph_documents:
            for n in doc.nodes:
                if not n.type:
                    continue
                if n.properties is None:
                    n.properties = {}
                # Match normalize_entity_names / Surreal-style adapters: QA chains filter on name.
                n.properties.setdefault("name", str(n.id))
                # Skip LI ingestion-metadata keys — they are not graph-model properties
                # and would flood the schema with filesystem columns on every type.
                vprops[n.type].update(
                    k for k in n.properties if k not in _LI_METADATA_SKIP
                )
            for rel in doc.relationships:
                if rel.type:
                    edge_types.add(rel.type)
                rp = rel.properties
                if rel.type and isinstance(rp, dict):
                    eprops[rel.type].update(rp.keys())
        if include_source:
            edge_types.add("MENTIONED_IN")
            vprops["Document"].add("content")
        for t in all_types:
            vprops[t].update(("id", "name", "ref_doc_id"))
        self._ensure_edge_types(host, http_port, username, password, database, edge_types)
        self._ensure_type_properties_sql(
            host, http_port, username, password, database, vprops, eprops
        )

        self.lc_graph.add_graph_documents(
            graph_documents, include_source=include_source, **kwargs
        )

    @staticmethod
    def _ensure_vertex_types(
        host: str, port: int, username: str, password: str,
        database: str, type_names: set,
    ) -> None:
        """Create vertex types via ``DatabaseDao.query()`` if they don't exist.

        Uses the same ``SyncClient`` + ``DatabaseDao`` pattern as
        ``_ensure_database_http`` so there is no raw-requests dependency here.
        Falls back silently if ``arcadedb_python`` is not installed.
        """
        try:
            from arcadedb_python.api.sync import SyncClient
            from arcadedb_python.dao.database import DatabaseDao

            client = SyncClient(
                host=host,
                port=port,
                username=username,
                password=password,
                content_type="application/json",
            )
            db = DatabaseDao(client, database)
            for type_name in sorted(type_names):
                try:
                    db.query(
                        "sql",
                        f"CREATE VERTEX TYPE {_sql_id(type_name)} IF NOT EXISTS",
                        is_command=True,
                    )
                    logger.debug("ArcadeDB: ensured vertex type '%s'", type_name)
                except Exception as exc:
                    logger.debug(
                        "ArcadeDB: CREATE VERTEX TYPE '%s' (non-fatal): %s",
                        type_name, exc,
                    )
        except Exception as exc:
            logger.warning(
                "ArcadeDB _ensure_vertex_types failed (non-fatal): %s", exc
            )

    @staticmethod
    def _ensure_edge_types(
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        type_names: Set[str],
    ) -> None:
        if not type_names:
            return
        try:
            from arcadedb_python.api.sync import SyncClient
            from arcadedb_python.dao.database import DatabaseDao

            client = SyncClient(
                host=host,
                port=port,
                username=username,
                password=password,
                content_type="application/json",
            )
            db = DatabaseDao(client, database)
            for type_name in sorted(type_names):
                try:
                    db.query(
                        "sql",
                        f"CREATE EDGE TYPE {_sql_id(type_name)} IF NOT EXISTS",
                        is_command=True,
                    )
                    logger.debug("ArcadeDB: ensured edge type '%s'", type_name)
                except Exception as exc:
                    logger.debug(
                        "ArcadeDB: CREATE EDGE TYPE '%s' (non-fatal): %s",
                        type_name,
                        exc,
                    )
        except Exception as exc:
            logger.warning("ArcadeDB _ensure_edge_types failed (non-fatal): %s", exc)

    @staticmethod
    def _ensure_type_properties_sql(
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        vertex_props: dict[str, Set[str]],
        edge_props: dict[str, Set[str]],
    ) -> None:
        """Declare STRING properties on vertex and edge types before Cypher SET +=."""
        if not vertex_props and not edge_props:
            return
        try:
            from arcadedb_python.api.sync import SyncClient
            from arcadedb_python.dao.database import DatabaseDao

            client = SyncClient(
                host=host,
                port=port,
                username=username,
                password=password,
                content_type="application/json",
            )
            db = DatabaseDao(client, database)

            for vtype, props in sorted(vertex_props.items()):
                for prop in sorted(props):
                    if not prop:
                        continue
                    stmt = (
                        f"CREATE PROPERTY {_sql_id(vtype)}.{_sql_id(prop)} IF NOT EXISTS STRING"
                    )
                    try:
                        db.query("sql", stmt, is_command=True)
                    except Exception as exc:
                        logger.debug(
                            "ArcadeDB: CREATE PROPERTY vertex %s.%s: %s",
                            vtype,
                            prop,
                            exc,
                        )

            for etype, props in sorted(edge_props.items()):
                for prop in sorted(props):
                    if not prop:
                        continue
                    stmt = (
                        f"CREATE PROPERTY {_sql_id(etype)}.{_sql_id(prop)} IF NOT EXISTS STRING"
                    )
                    try:
                        db.query("sql", stmt, is_command=True)
                    except Exception as exc:
                        logger.debug(
                            "ArcadeDB: CREATE PROPERTY edge %s.%s: %s",
                            etype,
                            prop,
                            exc,
                        )
        except Exception as exc:
            logger.warning(
                "ArcadeDB _ensure_type_properties_sql failed (non-fatal): %s", exc
            )

    def create_qa_chain(self, llm: Any):
        """Create Cypher QA chain for ArcadeDB via GraphCypherQAChain."""
        try:
            from langchain_neo4j import GraphCypherQAChain
        except ImportError:
            from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
        return GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    def get_graph(self):
        return self.lc_graph

    def normalize_entity_names(self) -> None:
        """Copy id -> name on all nodes that have id but no name.

        ArcadeDB's add_graph_documents writes entity nodes with only an ``id``
        property.  Setting ``name = id`` lets Cypher QA chains (which typically
        filter on ``n.name``) find nodes correctly.
        Unlike the Neo4j adapter, ArcadeDB does not use the ``__Entity__``
        base label, so we match all nodes regardless of label.
        """
        try:
            self.lc_graph.query(
                "MATCH (n) WHERE n.name IS NULL AND n.id IS NOT NULL "
                "SET n.name = n.id"
            )
            logger.debug("ArcadeDB: normalized entity names (id -> name) on all nodes")
        except Exception as exc:
            logger.warning("ArcadeDB normalize_entity_names failed: %s", exc)


__all__ = ["ArcadeDBLangChainAdapter", "ARCADEDB_LC_AVAILABLE"]
