"""LangChain Apache AGE (PostgreSQL graph extension) adapter.

Uses ``langchain-age`` (>=0.2.0) which ships:
  - ``AGEGraph``             — property graph store with Cypher queries
  - ``AGEGraphCypherQAChain`` — LLM QA chain over the graph
  - ``AGEVector``            — pgvector-backed VectorStore with optional graph linkage

Dedicated PostgreSQL service
----------------------------
The adapter targets the ``flexible_graphrag_age`` database on the
``apache-age`` container (port 5434), which runs PostgreSQL 18 with both
the ``age`` and ``vector`` extensions enabled.  A single connection therefore
supports Cypher graph traversal *and* vector similarity search without any
additional service.

Configuration:
{
    "host":            "localhost",
    "port":            5434,
    "database":        "flexible_graphrag_age",
    "username":        "postgres",
    "password":        "password",
    "graph_name":      "knowledge_graph",
    "collection_name": "langchain_age_vectors",   # pgvector table
    "search_type":     "hybrid"                   # "vector" or "hybrid"
}

Docker: apache-age container (docker/includes/apache-age.yaml) — dedicated
service for graph + vector search (port 5434).  The incremental sync state
and standalone pgvector store live separately on postgres-pgvector (port 5433).

References:
- https://age.apache.org/
- https://github.com/BAEM1N/langchain-age
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_age import AGEGraph, AGEGraphCypherQAChain, AGEVector, DistanceStrategy, SearchType
    APACHE_AGE_AVAILABLE = True
except ImportError:
    APACHE_AGE_AVAILABLE = False


def _conn_string(host: str, port: int, database: str, username: str, password: str) -> str:
    """Build both libpq key=value string (AGEGraph) and psycopg3 URI (AGEVector)."""
    return f"host={host} port={port} dbname={database} user={username} password={password}"


def _psycopg_uri(host: str, port: int, database: str, username: str, password: str) -> str:
    return f"postgresql://{username}:{password}@{host}:{port}/{database}"


def _extract_return_aliases(cypher: str) -> List[str]:
    """Extract column aliases from the RETURN clause, respecting parentheses nesting.

    The standard ``extract_cypher_return_aliases`` from ``langchain_age`` splits
    the RETURN clause on all commas, including those inside function arguments
    (e.g. ``coalesce(p.name, p.id)``).  This produces spurious extra aliases and
    can cause duplicate column names in the AGE SQL wrapper.

    This implementation walks the RETURN clause character-by-character and only
    splits on commas at depth 0 (outside any parentheses / brackets).
    """
    import re

    # Extract just the RETURN clause (stop at ORDER / LIMIT / SKIP)
    m = re.search(
        r"\bRETURN\b(.+?)(?:\bORDER\b|\bLIMIT\b|\bSKIP\b|$)",
        cypher,
        re.IGNORECASE | re.DOTALL,
    )
    return_clause = m.group(1).strip() if m else ""

    if not return_clause:
        return ["result"]

    # Parenthesis-aware split
    terms: List[str] = []
    depth = 0
    buf: List[str] = []
    for ch in return_clause:
        if ch in ("(", "["):
            depth += 1
            buf.append(ch)
        elif ch in (")", "]"):
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            terms.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        terms.append("".join(buf).strip())

    aliases: List[str] = []
    seen: set = set()
    for i, term in enumerate(terms):
        as_m = re.search(r"\bAS\s+(\w+)\s*$", term, re.IGNORECASE)
        if as_m:
            alias = as_m.group(1)
        else:
            tokens = re.findall(r"\w+", term)
            alias = tokens[-1] if tokens else f"col{i}"
        # Deduplicate: if the same alias appears twice append an index
        base = alias
        idx = 2
        while alias in seen:
            alias = f"{base}_{idx}"
            idx += 1
        seen.add(alias)
        aliases.append(alias)

    return aliases if aliases else ["result"]


class _AGEGraphFixed(AGEGraph):
    """AGEGraph subclass that replaces setUpAge with a psycopg3-native implementation.

    The ``age`` package (``age.setUpAge``) uses psycopg2 APIs internally:
    ``psycopg2.sql.SQL().format()`` produces ``psycopg2.sql.Composed`` objects
    that psycopg3 cursors cannot execute, raising either
    ``TypeError: unhashable type: 'Composed'`` or ``expected bytes, Composed found``.

    We replace ``_connect`` entirely, reproducing the necessary AGE session
    setup (LOAD age, search_path, graph existence check) using plain psycopg3
    parameterised queries so no psycopg2 objects are involved.
    """

    def _connect(self):
        # The age package (age.cypher, age.execCypher) is psycopg2-only:
        # it passes psycopg2.sql.Composed objects to cursor.execute(), which
        # psycopg3 cannot handle.  Using a psycopg2 connection makes everything
        # in the age package work correctly while keeping langchain_age's
        # higher-level API (which is just duck-typed) fully functional.
        import psycopg2
        conn = psycopg2.connect(self._conn_string)
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("LOAD 'age'")
            cur.execute('SET search_path = ag_catalog, "$user", public')
            cur.execute(
                "SELECT COUNT(*) FROM ag_catalog.ag_graph WHERE name = %s",
                (self.graph_name,),
            )
            if cur.fetchone()[0] == 0:
                raise RuntimeError(
                    f"AGE graph '{self.graph_name}' does not exist. "
                    "Check that _ensure_graph_exists() ran successfully."
                )
        conn.commit()
        return conn

    def _run_write(self, cypher_stmt: str) -> None:
        """Override to use dollar-quoting instead of age_sdk.cypher().

        age_sdk.cypher() calls cursor.mogrify() then str() on the bytes result,
        producing \\xNN hex sequences for any non-ASCII characters.  PostgreSQL's
        AGE Cypher parser rejects \\x escapes (only JSON escapes are valid).

        Dollar-quoting ($cypher$...$cypher$) passes content as a raw string with
        no escape processing, so Unicode entity names and properties work cleanly.
        """
        with self._conn.cursor() as cur:
            cur.execute("LOAD 'age'")
            cur.execute('SET search_path = ag_catalog, "$user", public')
            # Dollar-quoting tag unlikely to appear in any generated Cypher
            stmt = (
                "SELECT * FROM cypher(%s, $cypher$"
                + cypher_stmt
                + "$cypher$) AS (v agtype)"
            )
            cur.execute(stmt, (self.graph_name,))
        self._conn.commit()

    def query(self, query_str: str, params: Optional[dict] = None) -> List[Dict[str, Any]]:
        """Override to use dollar-quoting for reads (mirrors _run_write fix).

        The default implementation calls age_sdk.cypher() which:
        1. Invokes age_prepare_cypher() — a separate round-trip that can fail
           on certain valid Cypher patterns (e.g. variable-length paths with
           explicit minimum hops: ``[*1..]``).
        2. Uses cursor.mogrify() whose byte output can contain \\xNN escape
           sequences that PostgreSQL rejects inside Cypher.
        3. Uses a naive comma-split to extract RETURN aliases, so function
           calls with multiple arguments (e.g. ``coalesce(p.name, p.id) AS name``)
           are split incorrectly, producing duplicate column names.

        Dollar-quoting bypasses issues 1 and 2.  Issue 3 is fixed by a
        parenthesis-aware alias extractor that respects nesting.
        """
        from langchain_age.graphs.age_graph import validate_cypher, agobj_to_dict

        error = validate_cypher(query_str)
        if error:
            raise ValueError(f"Invalid Cypher: {error}")

        aliases = _extract_return_aliases(query_str)
        # Double-quote every alias so numeric tokens like '1' become '"1" agtype'
        # (a valid but unusual column name) rather than bare '1 agtype' which
        # is rejected by PostgreSQL as a syntax error.
        col_defs = ", ".join(f'"{a}" agtype' for a in aliases)

        stmt = (
            "SELECT * FROM cypher(%s, $cypher$"
            + query_str
            + f"$cypher$) AS ({col_defs})"
        )

        logger.debug("AGE read query: %s", query_str[:300])

        with self._conn.cursor() as cur:
            if self._timeout:
                cur.execute(
                    "SET LOCAL statement_timeout = %s",
                    (int(self._timeout * 1000),),
                )
            try:
                cur.execute(stmt, (self.graph_name,))
                if cur.description is None:
                    self._conn.commit()
                    return []
                col_names = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
            except Exception:
                self._conn.rollback()
                raise

        self._conn.commit()

        results: List[Dict[str, Any]] = []
        for row in rows:
            record: Dict[str, Any] = {}
            for col, val in zip(col_names, row):
                converted = agobj_to_dict(val)
                record[col] = self._sanitize_value(converted) if self._sanitize else converted
            results.append(record)
        return results


class ApacheAGEAdapter:
    """
    Apache AGE adapter — graph (Cypher) + vector search in one PostgreSQL database.

    Wraps both ``AGEGraph`` (graph traversal / QA) and ``AGEVector``
    (pgvector similarity + hybrid search), both targeting the same
    ``flexible_graphrag_age`` database.

    The ``AGEVector`` instance is created lazily on first access via
    ``get_vector_store(embedding)``.  Pass an ``Embeddings`` instance
    once; subsequent calls return the cached store.
    """

    def __init__(self, config: Dict[str, Any]):
        if not APACHE_AGE_AVAILABLE:
            raise ImportError(
                "langchain-age required. "
                "Install: uv pip install langchain-age"
            )

        self.config = config
        self._host     = config.get("host", "localhost")
        self._port     = int(config.get("port", 5434))
        self._database = config.get("database", "flexible_graphrag_age")
        self._username = config.get("username", "postgres")
        self._password = config.get("password", "password")
        self._graph_name      = config.get("graph_name", "knowledge_graph")
        self._collection_name = config.get("collection_name", "langchain_age_vectors")
        self._search_type     = config.get("search_type", "hybrid")

        self._ensure_graph_exists()

        conn_str = _conn_string(
            self._host, self._port, self._database, self._username, self._password
        )
        self.lc_graph = _AGEGraphFixed(
            connection_string=conn_str,
            graph_name=self._graph_name,
            enhanced_schema=True,
        )
        logger.info(
            "Apache AGE connected: %s:%s/%s  graph=%s",
            self._host, self._port, self._database, self._graph_name,
        )

        self._vector_store: Optional[AGEVector] = None

    # ------------------------------------------------------------------
    # Graph setup helpers
    # ------------------------------------------------------------------

    def _ensure_graph_exists(self) -> None:
        """Ensure the AGE extension is installed and the graph exists.

        The ``AGEGraph`` constructor calls ``setUpAge`` which does a hard
        ``fetchone()[0]`` on ``ag_catalog.ag_graph`` — it raises a TypeError
        if the graph is missing, and a relation-not-found error if the AGE
        extension itself hasn't been installed yet.

        We handle both here via a plain psycopg connection (autocommit DDL)
        so the adapter is self-bootstrapping regardless of whether the
        container init scripts ran (they only run on a completely empty volume).
        """
        try:
            import psycopg
        except ImportError:
            logger.warning(
                "psycopg not available — cannot bootstrap AGE graph '%s'. "
                "Ensure it was created by the container init scripts.",
                self._graph_name,
            )
            return

        conn_str = _conn_string(
            self._host, self._port, self._database, self._username, self._password
        )
        try:
            with psycopg.connect(conn_str, autocommit=True) as conn:
                with conn.cursor() as cur:
                    # Step 1: ensure extensions are installed
                    # (safe to run repeatedly — IF NOT EXISTS guards)
                    cur.execute("CREATE EXTENSION IF NOT EXISTS age")
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute("LOAD 'age'")
                    cur.execute("SET search_path = ag_catalog, \"$user\", public")

                    # Step 2: create graph if absent
                    cur.execute(
                        "SELECT COUNT(*) FROM ag_catalog.ag_graph WHERE name = %s",
                        (self._graph_name,),
                    )
                    exists = cur.fetchone()[0] > 0
                    if not exists:
                        cur.execute(
                            "SELECT ag_catalog.create_graph(%s)", (self._graph_name,)
                        )
                        logger.info(
                            "Apache AGE: created graph '%s' in %s",
                            self._graph_name, self._database,
                        )
                    else:
                        logger.debug(
                            "Apache AGE: graph '%s' already exists", self._graph_name
                        )
        except Exception as exc:
            logger.warning(
                "Apache AGE: could not bootstrap graph '%s': %s — "
                "AGEGraph constructor will fail if graph is absent.",
                self._graph_name, exc,
            )

    def create_qa_chain(self, llm: Any):
        """Create a Cypher QA chain over the AGE graph."""
        return AGEGraphCypherQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    def get_graph(self) -> AGEGraph:
        return self.lc_graph

    # ------------------------------------------------------------------
    # Vector store  (AGEVector = pgvector + optional AGE graph linkage)
    # ------------------------------------------------------------------

    def get_vector_store(self, embedding: Any) -> AGEVector:
        """Return the ``AGEVector`` store, creating it on first call.

        Args:
            embedding: Any LangChain ``Embeddings`` instance.
        """
        if self._vector_store is None:
            search_type = (
                SearchType.HYBRID
                if self._search_type == "hybrid"
                else SearchType.VECTOR
            )
            self._vector_store = AGEVector(
                connection_string=_psycopg_uri(
                    self._host, self._port, self._database,
                    self._username, self._password,
                ),
                embedding_function=embedding,
                collection_name=self._collection_name,
                distance_strategy=DistanceStrategy.COSINE,
                search_type=search_type,
                age_graph_name=self._graph_name,
            )
            logger.info(
                "AGEVector store ready: table=%s  search=%s  graph=%s",
                self._collection_name, self._search_type, self._graph_name,
            )
        return self._vector_store

    def create_hnsw_index(self) -> None:
        """Create HNSW index on the vector table (faster ANN search)."""
        if self._vector_store is None:
            raise RuntimeError("Call get_vector_store(embedding) first.")
        self._vector_store.create_hnsw_index()
        logger.info("AGEVector: HNSW index created on %s", self._collection_name)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_graph_documents(
        self,
        graph_documents: List[Any],
        include_source: bool = False,
        **kwargs,
    ) -> None:
        """Write graph documents to Apache AGE using the dollar-quoting write path.

        Apache AGE enforces strict separation between vertex labels and edge
        labels — a label name may be registered as one OR the other, never both.
        When the LLM extracts a node type AND a relationship type with the same
        name (e.g. ``DATE``), the upstream ``AGEGraph.add_graph_documents``
        raises ``Expecting edge label, found existing vertex label``.

        This override collects all node-type names first, then renames any
        relationship type that collides by appending ``_REL``.  The renaming is
        purely at the AGE storage layer — the QA chain never sees the raw edge
        types because it issues Cypher generated by the LLM against the schema.

        It also injects ``ref_doc_id`` from node.properties (pre-populated by
        ``aingest_li_to_lc_graph`` / ``aingest_lc_graph``) so that the
        incremental-delete path can find and remove the correct nodes.
        """
        import json as _json

        def _esc_str(v: str) -> str:
            """JSON-encode a string for embedding inside an AGE Cypher literal."""
            return _json.dumps(str(v))

        def _props_to_cypher(props: dict) -> str:
            """Convert a dict to an AGE-compatible Cypher map literal."""
            if not props:
                return "{}"
            parts = []
            for k, v in props.items():
                safe_k = str(k).replace("`", "")
                if isinstance(v, bool):
                    parts.append(f"`{safe_k}`: {str(v).lower()}")
                elif isinstance(v, (int, float)):
                    parts.append(f"`{safe_k}`: {v}")
                else:
                    parts.append(f"`{safe_k}`: {_esc_str(v)}")
            return "{" + ", ".join(parts) + "}"

        def _run(cypher: str) -> None:
            try:
                self.lc_graph._run_write(cypher)
            except Exception as exc:
                logger.debug("AGE write (non-fatal): %s | cypher: %s", exc, cypher[:200])

        for doc in graph_documents:
            # Collect all vertex label names from this document so we can detect
            # relationship type collisions before attempting the edge MERGE.
            node_types: set = {node.type for node in (doc.nodes or [])}

            # Write vertex nodes
            for node in (doc.nodes or []):
                props = dict(node.properties or {})
                props["id"] = node.id
                props.setdefault("name", node.id)
                _run(
                    f"MERGE (n:`{node.type}` {{id: {_esc_str(node.id)}}}) "
                    f"SET n += {_props_to_cypher(props)}"
                )

            # Write edges — rename rel type if it collides with a vertex label.
            for rel in (doc.relationships or []):
                rel_type = rel.type
                if rel_type in node_types:
                    rel_type = rel_type + "_REL"
                    logger.debug(
                        "AGE: renamed relationship type %r -> %r to avoid vertex label collision",
                        rel.type, rel_type,
                    )
                src_props = dict(rel.source.properties or {})
                src_props["id"] = rel.source.id
                tgt_props = dict(rel.target.properties or {})
                tgt_props["id"] = rel.target.id
                edge_props = _props_to_cypher(rel.properties or {})

                # Ensure source / target nodes exist (idempotent MERGE)
                _run(
                    f"MERGE (a:`{rel.source.type}` {{id: {_esc_str(rel.source.id)}}})"
                )
                _run(
                    f"MERGE (b:`{rel.target.type}` {{id: {_esc_str(rel.target.id)}}})"
                )
                _run(
                    f"MATCH (a:`{rel.source.type}` {{id: {_esc_str(rel.source.id)}}}), "
                    f"(b:`{rel.target.type}` {{id: {_esc_str(rel.target.id)}}}) "
                    f"MERGE (a)-[r:`{rel_type}`]->(b) SET r += {edge_props}"
                )

            # Source document node + MENTIONS edges (when include_source=True)
            if include_source and doc.source is not None:
                src_meta = doc.source.metadata or {}
                src_id = src_meta.get("source") or src_meta.get("doc_id") or "unknown"
                content = doc.source.page_content.replace("'", "\\'")[:500]
                _rid = src_meta.get("ref_doc_id") or src_meta.get("doc_id") or ""
                _run(
                    f"MERGE (s:Document {{source: {_esc_str(src_id)}}}) "
                    f"SET s.content = {_esc_str(content)}, s.ref_doc_id = {_esc_str(_rid)}"
                )
                for node in (doc.nodes or []):
                    _run(
                        f"MATCH (s:Document {{source: {_esc_str(src_id)}}}), "
                        f"(n:`{node.type}` {{id: {_esc_str(node.id)}}}) "
                        f"MERGE (s)-[:MENTIONS]->(n)"
                    )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def delete(self, ref_doc_id: str) -> None:
        """Delete all nodes tagged with *ref_doc_id* from the AGE graph.

        ``_AGEGraphFixed.query()`` only handles SELECT-style Cypher (with RETURN
        aliases) and fails on DETACH DELETE.  We issue the write directly via
        ``_run_write`` on the AGEGraph instance, which uses the dollar-quoting
        pattern to bypass the age_sdk.cypher() escaping issues.

        The ref_doc_id value is embedded directly after JSON-escaping so that
        special characters (backslashes, double-quotes) don't break the Cypher
        string literal inside the dollar-quoted block.
        """
        import json as _json
        # JSON-encode the string (adds surrounding quotes and escapes special chars).
        _rid_json = _json.dumps(ref_doc_id)  # e.g. "\"some\\value\""
        cypher = f"MATCH (n) WHERE n.ref_doc_id = {_rid_json} DETACH DELETE n"
        try:
            self.lc_graph._run_write(cypher)
            logger.info("Apache AGE: deleted nodes for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("Apache AGE delete failed for ref_doc_id=%s: %s", ref_doc_id, exc)

    def normalize_entity_names(self) -> None:
        """Copy id -> name on entity nodes (Cypher / AGE)."""
        try:
            self.lc_graph.query(
                "MATCH (n:__Entity__) WHERE n.name IS NULL AND n.id IS NOT NULL "
                "SET n.name = n.id"
            )
            logger.debug("Apache AGE: normalized entity names (id -> name)")
        except Exception as exc:
            logger.warning("Apache AGE normalize_entity_names failed: %s", exc)

    def graph_vector_search(
        self,
        embedding: Any,
        query: str,
        k: int = 4,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """Vector similarity search that also returns AGE graph context.

        Convenience wrapper: initialises ``AGEVector`` if needed, then
        delegates to ``similarity_search``.
        """
        store = self.get_vector_store(embedding)
        return store.similarity_search(query, k=k, filter=filter)


__all__ = ["ApacheAGEAdapter", "APACHE_AGE_AVAILABLE"]
