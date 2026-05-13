"""LangChain LadybugDB property graph adapter (embedded).

Ladybug schema design
---------------------
REL TABLE GROUP
  A Ladybug REL TABLE is bound to exactly one FROM src TO dst pair.  Using
  the same relationship type across different source/target label combinations
  requires REL TABLE GROUP.  We always create relationship tables as GROUP so
  that incremental ingestion of new documents can extend the schema.

ALTER TABLE … ADD FROM … TO …
  Used to add new (src, dst) pairs to an existing REL TABLE GROUP.  Fails
  with "already exists" if the pair is already there — that is benign.

  Note: the schema introspection API (_get_rel_table_names) returns only the
  first (src, dst) pair for a GROUP table.  Because of this we always attempt
  ALTER for every pair in a batch and treat "already exists" as a success
  signal — the pair is in the schema and data inserts will work.

WAL / CHECKPOINT
  Ladybug accumulates writes in a write-ahead log.  We run CHECKPOINT at the
  end of every add_graph_documents call to flush data to disk immediately.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_ALREADY_EXISTS = "already exists"  # Ladybug error text for duplicate schema pairs

try:
    from langchain_ladybug import LadybugGraph, LadybugQAChain
    LADYBUG_LC_AVAILABLE = True
except ImportError:
    LADYBUG_LC_AVAILABLE = False


class LangChainLadybugAdapter:
    """LadybugDB embedded property graph adapter (LangChain backend).

    Ladybug is a high-performance embedded graph database with a structured
    property graph model and Cypher query language.  See https://docs.ladybugdb.com/

    This adapter manages schema expansion automatically so that new entity
    types and relationship type/label combinations introduced by successive
    documents are added incrementally without requiring a manual schema
    definition up-front.

    Configuration keys
    ------------------
    db_dir   : directory for the database file (default ``./ladybug_lc``)
    db_file  : filename inside db_dir (default ``database.lbug``)
    """

    def __init__(self, config: Dict[str, Any]):
        if not LADYBUG_LC_AVAILABLE:
            raise ImportError(
                "langchain-ladybug is required for LangChainLadybugAdapter. "
                "Install: uv pip install langchain-ladybug"
            )

        import ladybug as lb

        self.config = config
        db_dir  = config.get("db_dir",  "./ladybug_lc")
        db_file = config.get("db_file", "database.lbug")
        self._db_path = os.path.join(db_dir, db_file)
        os.makedirs(db_dir, exist_ok=True)

        self._db = lb.Database(self._db_path)
        self.lc_graph = LadybugGraph(self._db, allow_dangerous_requests=True)

        logger.info("LangChainLadybugAdapter: opened DB at %s", self._db_path)

    # ------------------------------------------------------------------
    # Required adapter interface
    # ------------------------------------------------------------------

    def get_graph(self) -> Any:
        """Return the underlying LadybugGraph instance."""
        return self.lc_graph

    def create_qa_chain(self, llm: Any) -> Any:
        """Build a LadybugQAChain for text-to-Cypher QA."""
        return LadybugQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def _load_existing_schema(self, conn) -> tuple[set, dict]:
        """Return (existing_node_types, existing_rel_pairs).

        existing_rel_pairs maps rel_type -> set of (src_label, dst_label).
        Note: only the first pair per REL TABLE GROUP is returned by the
        schema API; the caller must handle this via _alter_rel_table.
        """
        node_types: set = set()
        rel_pairs: dict = {}
        try:
            for t in conn._get_node_table_names():
                node_types.add(t)
        except Exception as exc:
            logger.debug("Ladybug: could not read node table names: %s", exc)
        try:
            for t in conn._get_rel_table_names():
                rel_pairs.setdefault(t["name"], set()).add((t["src"], t["dst"]))
        except Exception as exc:
            logger.debug("Ladybug: could not read rel table names: %s", exc)
        return node_types, rel_pairs

    def _alter_rel_table(self, conn, rel_type: str, src: str, dst: str) -> bool:
        """Issue ``ALTER TABLE rel_type ADD FROM src TO dst``.

        Returns True if the pair is now in the schema (either added just now
        or was already there).  Returns False only on unexpected DDL errors.

        The schema introspection API only returns the first (src, dst) pair
        for a REL TABLE GROUP.  We therefore always attempt ALTER and treat
        ``"already exists"`` as a benign success — the pair is in the schema
        and data inserts will work correctly.
        """
        try:
            conn.execute(f"ALTER TABLE {rel_type} ADD FROM {src} TO {dst};")
            logger.debug("Ladybug: extended %s with FROM %s TO %s", rel_type, src, dst)
            return True
        except RuntimeError as exc:
            msg = str(exc)
            if _ALREADY_EXISTS in msg:
                # Pair is already in the schema (ALTER idempotent at data level).
                logger.debug(
                    "Ladybug: %s FROM %s TO %s already in schema (idempotent)",
                    rel_type, src, dst,
                )
                return True
            logger.warning(
                "Ladybug ALTER %s ADD FROM %s TO %s failed: %s", rel_type, src, dst, exc
            )
            return False
        except Exception as exc:
            logger.debug(
                "Ladybug ALTER %s ADD FROM %s TO %s: %s", rel_type, src, dst, exc
            )
            return False

    def add_graph_documents(
        self,
        graph_documents: List[Any],
        include_source: bool = False,
        **kwargs,
    ) -> None:
        """Write graph documents to Ladybug using a schema-aware write loop."""
        if not graph_documents:
            return

        conn = self.lc_graph.conn

        # ---- Phase 0: read existing schema ----------------------------------
        existing_node_types, existing_rel_pairs = self._load_existing_schema(conn)

        # ---- Phase 1: collect schema for this batch -------------------------
        new_node_types: set = set()
        new_rel_pairs: dict = {}   # rel_type -> set of (src, dst)

        for doc in graph_documents:
            for node in doc.nodes:
                new_node_types.add(node.type)
            for rel in doc.relationships:
                new_node_types.add(rel.source.type)
                new_node_types.add(rel.target.type)
                new_rel_pairs.setdefault(rel.type, set()).add(
                    (rel.source.type, rel.target.type)
                )

        all_node_types = existing_node_types | new_node_types

        # ---- Phase 1a: create new entity node tables ------------------------
        for node_type in sorted(new_node_types - existing_node_types):
            try:
                conn.execute(
                    f"CREATE NODE TABLE IF NOT EXISTS {node_type} "
                    f"(id STRING, type STRING, ref_doc_id STRING DEFAULT '', PRIMARY KEY(id));"
                )
            except Exception as exc:
                logger.debug("Ladybug node table DDL %s: %s", node_type, exc)
            # Ensure ref_doc_id column exists on tables created before this fix.
            try:
                conn.execute(
                    f"ALTER TABLE {node_type} ADD ref_doc_id STRING DEFAULT ''"
                )
            except Exception:
                pass  # "already exists" — benign

        # ---- Phase 1b: create Chunk table (when include_source) -------------
        if include_source and "Chunk" not in existing_node_types:
            try:
                conn.execute(
                    "CREATE NODE TABLE IF NOT EXISTS Chunk "
                    "(id STRING, text STRING, type STRING, ref_doc_id STRING DEFAULT '', PRIMARY KEY(id));"
                )
                all_node_types.add("Chunk")
            except Exception as exc:
                logger.debug("Ladybug Chunk table DDL: %s", exc)
            try:
                conn.execute("ALTER TABLE Chunk ADD ref_doc_id STRING DEFAULT ''")
            except Exception:
                pass  # column already exists

        # ---- Phase 1c: create / extend entity rel tables --------------------
        for rel_type, batch_pairs in new_rel_pairs.items():
            existing = existing_rel_pairs.get(rel_type, set())

            if existing:
                # Table already exists — try ALTER for every pair in this
                # batch.  The schema API only exposes the first pair per GROUP
                # table so we can't skip pairs that were added in prior runs.
                # _alter_rel_table silently accepts "already exists" responses.
                for src, dst in sorted(batch_pairs):
                    self._alter_rel_table(conn, rel_type, src, dst)
            else:
                # Fresh table — use GROUP so future ALTER works if needed.
                pairs_ddl = ", ".join(
                    f"FROM {src} TO {dst}" for src, dst in sorted(batch_pairs)
                )
                try:
                    conn.execute(
                        f"CREATE REL TABLE GROUP IF NOT EXISTS {rel_type} "
                        f"({pairs_ddl});"
                    )
                except Exception as exc:
                    logger.debug("Ladybug rel table DDL %s: %s", rel_type, exc)

        # ---- Phase 1d: MENTIONS rel table (include_source) ------------------
        if include_source:
            entity_types = all_node_types - {"Chunk"}
            existing_mentions = existing_rel_pairs.get("MENTIONS", set())

            if existing_mentions:
                # Table already exists — extend with any new entity types.
                # Same tolerant ALTER pattern as Phase 1c.
                for nt in sorted(entity_types):
                    self._alter_rel_table(conn, "MENTIONS", "Chunk", nt)
            elif entity_types:
                # Fresh MENTIONS table — create as GROUP.
                mentions_ddl = ", ".join(
                    f"FROM Chunk TO {nt}" for nt in sorted(entity_types)
                )
                try:
                    conn.execute(
                        f"CREATE REL TABLE GROUP IF NOT EXISTS MENTIONS "
                        f"({mentions_ddl});"
                    )
                except Exception as exc:
                    logger.debug("Ladybug MENTIONS DDL: %s", exc)

        # ---- Phase 2a: MERGE entity nodes -----------------------------------
        nodes_written = 0
        for doc in graph_documents:
            # Extract ref_doc_id from the source document metadata for delete tracking.
            _src_meta = getattr(getattr(doc, "source", None), "metadata", {}) or {}
            _rid = (
                _src_meta.get("ref_doc_id")
                or _src_meta.get("doc_id")
                or getattr(getattr(doc, "source", None), "id", None)
                or ""
            )
            # Also pick it up from pre-injected node properties (set by aingest_lc_graph).
            for node in doc.nodes:
                _node_rid = (node.properties or {}).get("ref_doc_id") or _rid
                try:
                    conn.execute(
                        f"MERGE (e:{node.type} {{id: $id}}) SET e.type = 'entity', e.ref_doc_id = $rid",
                        parameters={"id": node.id, "rid": _node_rid},
                    )
                    nodes_written += 1
                except Exception as exc:
                    logger.debug(
                        "Ladybug node merge %s/%s: %s", node.type, node.id, exc
                    )

        # ---- Phase 2b: MERGE entity edges -----------------------------------
        edges_written = 0
        for doc in graph_documents:
            for rel in doc.relationships:
                try:
                    conn.execute(
                        f"MATCH (e1:{rel.source.type} {{id: $src}}), "
                        f"(e2:{rel.target.type} {{id: $dst}}) "
                        f"MERGE (e1)-[:{rel.type}]->(e2)",
                        parameters={
                            "src": rel.source.id,
                            "dst": rel.target.id,
                        },
                    )
                    edges_written += 1
                except Exception as exc:
                    logger.debug(
                        "Ladybug edge merge %s-[%s]->%s: %s",
                        rel.source.type, rel.type, rel.target.type, exc,
                    )

        # ---- Phase 2c: Chunk nodes + MENTIONS (when include_source) ---------
        # Run whenever include_source=True regardless of whether there are new
        # node types — all entity types in the batch are already in the schema.
        chunks_written = 0
        mentions_written = 0
        if include_source:
            for doc in graph_documents:
                src = doc.source
                if src is None:
                    continue
                chunk_id = src.metadata.get("id") or hashlib.md5(
                    src.page_content.encode("utf-8")
                ).hexdigest()
                _c_rid = (
                    src.metadata.get("ref_doc_id")
                    or src.metadata.get("doc_id")
                    or ""
                )
                try:
                    conn.execute(
                        "MERGE (c:Chunk {id: $id}) "
                        "SET c.text = $text, c.type = 'text_chunk', c.ref_doc_id = $rid",
                        parameters={"id": chunk_id, "text": src.page_content, "rid": _c_rid},
                    )
                    chunks_written += 1
                except Exception as exc:
                    logger.debug("Ladybug chunk merge %s: %s", chunk_id, exc)
                    continue

                for node in doc.nodes:
                    try:
                        conn.execute(
                            f"MATCH (c:Chunk {{id: $cid}}), "
                            f"(e:{node.type} {{id: $eid}}) "
                            f"MERGE (c)-[:MENTIONS]->(e)",
                            parameters={"cid": chunk_id, "eid": node.id},
                        )
                        mentions_written += 1
                    except Exception as exc:
                        logger.debug(
                            "Ladybug MENTIONS %s->%s/%s: %s",
                            chunk_id, node.type, node.id, exc,
                        )

        # ---- Phase 3: CHECKPOINT — flush write-ahead log to disk -----------
        try:
            conn.execute("CHECKPOINT")
            logger.debug("LangChainLadybugAdapter: CHECKPOINT complete")
        except Exception as exc:
            logger.debug("LangChainLadybugAdapter: CHECKPOINT failed: %s", exc)

        # ---- Phase 4: refresh schema on the LadybugGraph --------------------
        self.lc_graph.refresh_schema()

        logger.info(
            "LangChainLadybugAdapter: wrote %d node(s), %d edge(s), "
            "%d chunk(s), %d mention(s) from %d graph doc(s) "
            "[%d node types, %d rel types]",
            nodes_written, edges_written, chunks_written, mentions_written,
            len(graph_documents), len(new_node_types), len(new_rel_pairs),
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, ref_doc_id: str) -> None:
        """Delete all entity and Chunk nodes tagged with *ref_doc_id*.

        Ladybug Cypher supports MATCH with parameterized queries.  We
        iterate all entity node types visible in the schema and issue a
        targeted MATCH/DELETE for each to avoid cross-label scans (Ladybug
        does not support the label-agnostic ``MATCH (n) WHERE ...`` pattern
        that Neo4j uses for DETACH DELETE across all labels).
        """
        conn = self.lc_graph.conn
        try:
            node_table_names = list(conn._get_node_table_names())
        except Exception as exc:
            logger.debug("Ladybug: could not enumerate node tables: %s", exc)
            node_table_names = []

        deleted = 0
        for table in node_table_names:
            try:
                # DETACH DELETE removes the node and all its relationships.
                # Plain DELETE fails silently when the node has incoming/outgoing
                # edges (e.g. MENTIONS from a Chunk node), leaving the node intact.
                conn.execute(
                    f"MATCH (n:{table} {{ref_doc_id: $rid}}) DETACH DELETE n",
                    parameters={"rid": ref_doc_id},
                )
                deleted += 1
            except Exception as exc:
                logger.debug("Ladybug delete on %s: %s", table, exc)

        try:
            conn.execute(
                "MATCH (c:Chunk {ref_doc_id: $rid}) DETACH DELETE c",
                parameters={"rid": ref_doc_id},
            )
        except Exception as exc:
            logger.debug("Ladybug Chunk delete: %s", exc)

        try:
            conn.execute("CHECKPOINT")
        except Exception as exc:
            logger.debug("Ladybug CHECKPOINT after delete: %s", exc)

        logger.info(
            "LangChainLadybugAdapter: deleted nodes for ref_doc_id=%s (%d tables scanned)",
            ref_doc_id, deleted,
        )

    # ------------------------------------------------------------------
    # Post-ingest normalization
    # ------------------------------------------------------------------

    def normalize_entity_names(self) -> None:
        """No-op: Ladybug nodes use ``id`` as the identity field.

        The QA prompt instructs the LLM to match via
        ``toLower(n.id) CONTAINS 'keyword'`` so no separate ``name``
        property is needed.
        """
        logger.debug(
            "LangChainLadybugAdapter.normalize_entity_names: skipped "
            "(Ladybug schema is fixed; QA chain uses n.id directly)"
        )


__all__ = ["LangChainLadybugAdapter", "LADYBUG_LC_AVAILABLE"]
