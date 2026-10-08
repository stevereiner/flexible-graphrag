"""LangChain ArangoDB property graph adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict

from ._graph_docs import normalize_graph_documents

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
        """Write graph documents, creating a named ArangoDB graph if configured.

        ``langchain_arangodb`` creates endpoint-only nodes via ``_get_node_key``
        without going through ``doc.nodes``, so relationship endpoints never
        received a ``ref_doc_id`` and survived incremental delete.  The shared
        normalizer folds them into ``doc.nodes`` and stamps the delete key.
        """
        graph_name = self.config.get("graph_name")
        if graph_name:
            kwargs.setdefault("graph_name", graph_name)

        normalize_graph_documents(graph_documents)

        self.lc_graph.add_graph_documents(graph_documents, **kwargs)

    def delete(self, ref_doc_id: str) -> None:
        """Delete SOURCE + ENTITY nodes/edges for *ref_doc_id* using AQL.

        ArangoDB uses AQL (not Cypher), so the default Cypher delete in
        ``LangChainPGAdapter`` would fail.

        IMPORTANT: always use AQL bind variables (@rid) rather than string
        interpolation.  AQL interprets backslash sequences in string literals
        (e.g. \\n as newline, \\i as invalid escape) so a Windows path like
        'c:\\newdev3\\...' will NOT match what was stored — the filter silently
        returns 0 rows.  Bind variables bypass this entirely.

        Order matters: remove this document's ``*_SOURCE`` doc and its
        ``*_HAS_SOURCE`` edges first, then the entities stamped with this rid,
        then sweep entities left with **no** remaining source link.  Deleting
        everything reachable from the source instead would take out entities
        that other documents still reference.

        Each step is a separate query — AQL restricts reading a collection that
        is modified in the same query, so a combined nested-``REMOVE`` version
        can be rejected outright.
        """
        graph_name = self.config.get("graph_name", "knowledge_graph")
        entity_col = f"{graph_name}_ENTITY"
        # langchain-arangodb names the edge collection *_LINKS_TO (not *_RELATIONSHIP)
        # when use_one_entity_collection=True (the default).
        relationship_col = f"{graph_name}_LINKS_TO"
        source_col = f"{graph_name}_SOURCE"
        has_source_col = f"{graph_name}_HAS_SOURCE"

        # Access the underlying python-arango db object directly for bind-var support.
        # ArangoGraph stores it as self.__db which Python mangles to _ArangoGraph__db.
        _db = getattr(self.lc_graph, "_ArangoGraph__db", None)

        if _db is not None:
            count_aql = (
                f"RETURN LENGTH(FOR n IN `{entity_col}` "
                f"  FILTER n.ref_doc_id == @rid OR n.doc_id == @rid RETURN 1)"
            )
            try:
                count_cursor = _db.aql.execute(count_aql, bind_vars={"rid": ref_doc_id})
                count = next(iter(count_cursor), 0)
                logger.info("ArangoDB: %d entity node(s) match ref_doc_id for deletion", count)
            except Exception as exc:
                logger.debug("ArangoDB count check failed: %s", exc)

            _sids = (
                f"LET sids = (FOR s IN `{source_col}` "
                f"  FILTER s.ref_doc_id == @rid OR s.doc_id == @rid RETURN s._id) "
            )
            steps = [
                # 0) LINKS_TO edges extracted from this document: each carries the key of the
                #    SOURCE it came from (source_id). Exact -- an entity's ref_doc_id is only
                #    that of the last document that wrote it, so it cannot say whose edge is whose.
                (
                    f"LET skeys = (FOR s IN `{source_col}` "
                    f"  FILTER s.ref_doc_id == @rid OR s.doc_id == @rid RETURN s._key) "
                    f"FOR e IN `{relationship_col}` "
                    f"  FILTER e.source_id IN skeys "
                    f"  REMOVE e IN `{relationship_col}` OPTIONS {{ignoreErrors: true}}"
                ),
                # 1) Scoped orphan sweep — must run BEFORE the HAS_SOURCE edges are
                #    removed.  Candidates are only entities linked to *this*
                #    document's sources; any that another document also links to
                #    keeps that edge and survives.  Reads SOURCE/HAS_SOURCE and
                #    writes ENTITY — different collections, so this is legal AQL.
                (
                    _sids
                    + f"FOR e IN `{has_source_col}` "
                    f"  FILTER e._to IN sids "
                    f"  LET others = LENGTH(FOR e2 IN `{has_source_col}` "
                    f"    FILTER e2._from == e._from AND e2._to NOT IN sids "
                    f"    LIMIT 1 RETURN 1) "
                    f"  FILTER others == 0 "
                    f"  REMOVE PARSE_IDENTIFIER(e._from).key IN `{entity_col}` "
                    f"    OPTIONS {{ignoreErrors: true}}"
                ),
                # 2) HAS_SOURCE edges pointing at this document's SOURCE docs.
                (
                    _sids
                    + f"FOR e IN `{has_source_col}` "
                    f"  FILTER e._to IN sids "
                    f"  REMOVE e IN `{has_source_col}` OPTIONS {{ignoreErrors: true}}"
                ),
                # 3) The SOURCE docs themselves.
                (
                    f"FOR s IN `{source_col}` "
                    f"  FILTER s.ref_doc_id == @rid OR s.doc_id == @rid "
                    f"  REMOVE s IN `{source_col}` OPTIONS {{ignoreErrors: true}}"
                ),
                # 4) ENTITY nodes stamped with this rid (the normalizer stamps
                #    relationship endpoints too, so this is now complete).
                (
                    f"FOR n IN `{entity_col}` "
                    f"  FILTER n.ref_doc_id == @rid OR n.doc_id == @rid "
                    f"  REMOVE n IN `{entity_col}` OPTIONS {{ignoreErrors: true}}"
                ),
                # 5) LINKS_TO edges left dangling by the removals above.
                (
                    f"FOR e IN `{relationship_col}` "
                    f"  FILTER DOCUMENT(e._from) == null OR DOCUMENT(e._to) == null "
                    f"  REMOVE e IN `{relationship_col}` OPTIONS {{ignoreErrors: true}}"
                ),
            ]
            for aql in steps:
                try:
                    # ArangoDB rejects a bind variable the query does not use (the dangling
                    # sweep has none), so bind @rid only where it appears
                    _db.aql.execute(aql, bind_vars={"rid": ref_doc_id} if "@rid" in aql else {})
                except Exception as exc:
                    logger.warning("ArangoDB delete step failed: %s — AQL: %s", exc, aql)
        else:
            # Fallback: use langchain-arangodb query() with a simpler AQL.
            # Escape the backslash before the quote: the other order doubles the quote's
            # own escape and ends the AQL string literal early (GHSA-vqrg-773h-4wxc).
            _rid = ref_doc_id.replace("\\", "\\\\").replace("'", "\\'")
            node_aql = (
                f"FOR n IN `{entity_col}` "
                f"  FILTER n.ref_doc_id == '{_rid}' OR n.doc_id == '{_rid}' "
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
