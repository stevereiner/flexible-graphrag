"""LangChain ArangoDB property graph adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    from langchain_arangodb import ArangoGraph, ArangoGraphQAChain
    from langchain_arangodb.graphs.arangodb_graph import get_arangodb_client
    ARANGODB_AVAILABLE = True
except ImportError:
    ARANGODB_AVAILABLE = False


class ArangoDBAdapter:
    """
    ArangoDB multi-model database adapter.

    ArangoDB combines document store, graph, key-value, and full-text search
    with AQL (ArangoDB Query Language).

    Configuration:
    {
        "url": "http://localhost:8529",
        "database": "flexible-graphrag",
        "username": "root",
        "password": "password",
        "graph_name": "knowledge_graph"
    }

    References:
    - https://python.langchain.com/docs/integrations/graphs/arangodb
    """

    def __init__(self, config: Dict[str, Any]):
        if not ARANGODB_AVAILABLE:
            raise ImportError(
                "langchain-arangodb required. Install: pip install langchain-arangodb"
            )

        self.config = config
        _url = config.get("url", "http://localhost:8529")
        _dbname = config.get("database", "flexible-graphrag")
        _username = config.get("username", "root")
        _password = config.get("password", "")
        try:
            import logging as _logging
            _logging.getLogger("urllib3").setLevel(_logging.ERROR)

            # Ensure the target database exists; create it via _system if needed.
            _sys_db = get_arangodb_client(
                url=_url, dbname="_system",
                username=_username, password=_password,
            )
            if not _sys_db.has_database(_dbname):
                _sys_db.create_database(_dbname)
                logger.info("ArangoDB: created database '%s'", _dbname)

            _db = get_arangodb_client(
                url=_url, dbname=_dbname,
                username=_username, password=_password,
            )
            self.lc_graph = ArangoGraph(
                db=_db,
            )
        finally:
            import logging as _logging
            _logging.getLogger("urllib3").setLevel(_logging.WARNING)
        logger.info("Connected to ArangoDB at %s (database: %s)", _url, _dbname)

    def create_qa_chain(self, llm: Any):
        """Create AQL QA chain for natural language queries."""
        return ArangoGraphQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    def get_graph(self):
        return self.lc_graph

    def add_graph_documents(self, graph_documents, **kwargs):
        """Write graph documents, creating a named ArangoDB graph if configured."""
        graph_name = self.config.get("graph_name")
        if graph_name:
            kwargs.setdefault("graph_name", graph_name)
        self.lc_graph.add_graph_documents(graph_documents, **kwargs)

    def delete(self, ref_doc_id: str) -> None:
        """Delete all entity nodes tagged with *ref_doc_id* using AQL.

        ArangoDB uses AQL (not Cypher), so the default Cypher delete in
        ``LangChainPGAdapter`` would fail.  This override queries the
        *_ENTITY and *_LINKS_TO collections directly.

        IMPORTANT: always use AQL bind variables (@rid) rather than string
        interpolation.  AQL interprets backslash sequences in string literals
        (e.g. \\n as newline, \\i as invalid escape) so a Windows path like
        'c:\\newdev3\\...' will NOT match what was stored — the filter silently
        returns 0 rows.  Bind variables bypass this entirely.
        """
        graph_name = self.config.get("graph_name", "knowledge_graph")
        entity_col = f"{graph_name}_ENTITY"
        # langchain-arangodb names the edge collection *_LINKS_TO (not *_RELATIONSHIP)
        # when use_one_entity_collection=True (the default).
        relationship_col = f"{graph_name}_LINKS_TO"

        # Access the underlying python-arango db object directly for bind-var support.
        # ArangoGraph stores it as self.__db which Python mangles to _ArangoGraph__db.
        _db = getattr(self.lc_graph, "_ArangoGraph__db", None)

        if _db is not None:
            # Remove dangling edges first (edges don't carry ref_doc_id; identify them
            # by looking up each edge's source/target vertex).
            edge_aql = (
                f"FOR e IN `{relationship_col}` "
                f"  LET from_doc = DOCUMENT(e._from) "
                f"  LET to_doc   = DOCUMENT(e._to) "
                f"  FILTER from_doc.ref_doc_id == @rid OR to_doc.ref_doc_id == @rid "
                f"  REMOVE e IN `{relationship_col}` OPTIONS {{ignoreErrors: true}}"
            )
            node_aql = (
                f"FOR n IN `{entity_col}` "
                f"  FILTER n.ref_doc_id == @rid "
                f"  REMOVE n IN `{entity_col}` OPTIONS {{ignoreErrors: true}}"
            )
            # Debug: count matching nodes before deletion
            count_aql = (
                f"RETURN LENGTH(FOR n IN `{entity_col}` "
                f"  FILTER n.ref_doc_id == @rid RETURN 1)"
            )
            try:
                count_cursor = _db.aql.execute(count_aql, bind_vars={"rid": ref_doc_id})
                count = next(iter(count_cursor), 0)
                logger.info("ArangoDB: %d entity node(s) match ref_doc_id for deletion", count)
            except Exception as exc:
                logger.debug("ArangoDB count check failed: %s", exc)
            for aql in [edge_aql, node_aql]:
                try:
                    _db.aql.execute(aql, bind_vars={"rid": ref_doc_id})
                except Exception as exc:
                    logger.debug("ArangoDB delete (bind-var) failed (non-fatal): %s", exc)
        else:
            # Fallback: use langchain-arangodb query() with a simpler AQL.
            # This path may fail for ref_doc_ids containing backslashes (Windows paths).
            _rid = ref_doc_id.replace("'", "\\'")
            node_aql = (
                f"FOR n IN `{entity_col}` "
                f"  FILTER n.ref_doc_id == '{_rid}' "
                f"  REMOVE n IN `{entity_col}` OPTIONS {{ignoreErrors: true}}"
            )
            try:
                self.lc_graph.query(node_aql)
            except Exception as exc:
                logger.debug("ArangoDB delete (fallback) failed (non-fatal): %s", exc)

        logger.info("ArangoDB: deleted nodes/edges for ref_doc_id=%s", ref_doc_id)
        # Refresh schema so the QA chain doesn't use stale sample values from
        # deleted entities when generating AQL queries.
        try:
            self.lc_graph.refresh_schema()
        except Exception as exc:
            logger.debug("ArangoDB: refresh_schema after delete failed: %s", exc)

    def normalize_entity_names(self) -> None:
        """Ensure the 'name' field mirrors 'text' for AQL schema consistency."""
        graph_name = self.config.get("graph_name", "knowledge_graph")
        entity_col = f"{graph_name}_ENTITY"
        aql = (
            f"FOR n IN {entity_col} "
            f"  FILTER n.name == null AND n.text != null "
            f"  UPDATE n WITH {{name: n.text, id: n.text}} IN {entity_col}"
        )
        try:
            self.lc_graph.query(aql)
            logger.debug("ArangoDB: normalized entity names (id -> name)")
        except Exception as exc:
            logger.warning("ArangoDB normalize_entity_names failed: %s", exc)


__all__ = ["ArangoDBAdapter", "ARANGODB_AVAILABLE"]
