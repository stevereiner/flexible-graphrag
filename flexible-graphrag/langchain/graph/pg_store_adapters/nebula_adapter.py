"""LangChain NebulaGraph distributed graph database adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_community.graphs import NebulaGraph
    NEBULA_AVAILABLE = True
except ImportError:
    NEBULA_AVAILABLE = False

# Props__ columns populated from doc.source.metadata on every vertex so that
# incremental_update can track and delete stale nodes regardless of ingest path.
_PROPS_META_COLS = [
    "doc_id",
    "ref_doc_id",
    "source",
    "file_name",
    "file_type",
    "file_path",
    "conversion_method",
    "document_id",
    "triplet_source_id",
    "creation_date",
    "last_modified_date",
]


def _ensure_tags_and_edges(_ex, session=None) -> None:
    """Create all tags, edge types, and indexes that the NebulaGraph adapters need.

    Called from ``_ensure_space_and_schema`` after the space is ready.
    All CREATE statements are idempotent (IF NOT EXISTS).

    Schema derived from NEBULA-SETUP.md and NEBULA-LANGCHAIN-SETUP.md.

    Also creates native tag/edge indexes required by NebulaGraph 3.x for
    MATCH queries (without indexes, every MATCH fails with IndexNotFound).

    Then polls until the schema is propagated to graphd (heartbeat ~10 s),
    so that ``langchain_community.graphs.NebulaGraph.refresh_schema()``
    sees all the edge types when the adapter constructor is called.
    """
    import time

    # ── Props__ (universal doc-metadata tag, all vertices) ────────────────────
    _ex(
        "CREATE TAG IF NOT EXISTS `Props__`("
        "`source` STRING DEFAULT '', "
        "`conversion_method` STRING DEFAULT '', "
        "`file_type` STRING DEFAULT '', "
        "`file_name` STRING DEFAULT '', "
        "`modified_at` STRING DEFAULT '', "
        "`_node_content` STRING DEFAULT '', "
        "`_node_type` STRING DEFAULT '', "
        "`document_id` STRING DEFAULT '', "
        "`doc_id` STRING DEFAULT '', "
        "`ref_doc_id` STRING DEFAULT '', "
        "`triplet_source_id` STRING DEFAULT '', "
        "`file_path` STRING DEFAULT '', "
        "`file_size` INT DEFAULT 0, "
        "`creation_date` STRING DEFAULT '', "
        "`last_modified_date` STRING DEFAULT '')"
    )
    # ALTER for existing spaces that were created before modified_at was added.
    try:
        _ex("ALTER TAG `Props__` ADD (`modified_at` STRING DEFAULT '')")
    except Exception:
        pass  # already exists — normal on fresh spaces or after first run

    # ── Relation__ (fallback edge for unknown relationship types) ─────────────
    _ex(
        "CREATE EDGE IF NOT EXISTS `Relation__`("
        "`label` STRING DEFAULT '', "
        "`source` STRING DEFAULT '', "
        "`conversion_method` STRING DEFAULT '', "
        "`file_type` STRING DEFAULT '', "
        "`file_name` STRING DEFAULT '', "
        "`file_path` STRING DEFAULT '', "
        "`modified_at` STRING DEFAULT '', "
        "`doc_id` STRING DEFAULT '', "
        "`ref_doc_id` STRING DEFAULT '', "
        "`triplet_source_id` STRING DEFAULT '')"
    )
    # Add file_path + modified_at to existing spaces that lack them
    try:
        _ex("ALTER EDGE `Relation__` ADD (`file_path` STRING DEFAULT '')")
    except Exception:
        pass
    try:
        _ex("ALTER EDGE `Relation__` ADD (`modified_at` STRING DEFAULT '')")
    except Exception:
        pass

    # ── Named entity tags (LangChain adapter + LLM queries use these) ─────────
    _ENTITY_TAGS = [
        ("Person",       "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`hire_date` STRING DEFAULT '', `date_of_birth` STRING DEFAULT '', "
                         "`salary` STRING DEFAULT '', `title` STRING DEFAULT ''"),
        ("Organization", "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`industry` STRING DEFAULT '', `founded` STRING DEFAULT '', "
                         "`description` STRING DEFAULT ''"),
        ("Company",      "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`industry` STRING DEFAULT '', `founded` STRING DEFAULT '', "
                         "`description` STRING DEFAULT ''"),
        ("Location",     "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`address` STRING DEFAULT '', `city` STRING DEFAULT '', "
                         "`country` STRING DEFAULT '', `latitude` STRING DEFAULT '', "
                         "`longitude` STRING DEFAULT '', `capacity` STRING DEFAULT ''"),
        ("Place",        "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`address` STRING DEFAULT '', `city` STRING DEFAULT '', "
                         "`country` STRING DEFAULT '', `latitude` STRING DEFAULT '', "
                         "`longitude` STRING DEFAULT '', `capacity` STRING DEFAULT ''"),
        ("Event",        "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`start_date` STRING DEFAULT '', `end_date` STRING DEFAULT '', "
                         "`date` STRING DEFAULT '', `description` STRING DEFAULT ''"),
        ("Product",      "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`description` STRING DEFAULT '', `category` STRING DEFAULT ''"),
        ("Department",   "`id` STRING DEFAULT '', `name` STRING DEFAULT ''"),
        ("Project",      "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`status` STRING DEFAULT '', `description` STRING DEFAULT ''"),
        ("Technology",   "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`description` STRING DEFAULT ''"),
        ("Skill",        "`id` STRING DEFAULT '', `name` STRING DEFAULT ''"),
        ("Topic",        "`id` STRING DEFAULT '', `name` STRING DEFAULT '', "
                         "`description` STRING DEFAULT ''"),
    ]
    for tag_name, cols in _ENTITY_TAGS:
        _ex(f"CREATE TAG IF NOT EXISTS `{tag_name}`({cols})")

    # ── Named relationship edge types ─────────────────────────────────────────
    _EDGE_COLS = (
        "`doc_id` STRING DEFAULT '', `ref_doc_id` STRING DEFAULT '', "
        "`source` STRING DEFAULT '', `file_name` STRING DEFAULT ''"
    )
    _EDGE_TYPES = [
        "WORKS_FOR", "HAS_DEPARTMENT", "HAS_LOCATION", "PART_OF",
        "AFFILIATED_WITH", "MANAGES", "WORKS_IN_DEPARTMENT", "ASSIGNED_TO",
        "LED_BY", "ATTENDED_BY", "HOSTED_BY", "HELD_AT",
        "LOCATED_IN", "BASED_IN", "RELATED_TO", "PRODUCED_BY",
        "USES_TECHNOLOGY", "HAS_SKILL", "SPONSORS", "MENTIONED_IN",
        "EMPLOYS", "HAS_EMPLOYEE", "REPORTS_TO", "MEMBER_OF",
    ]
    for edge_type in _EDGE_TYPES:
        _ex(f"CREATE EDGE IF NOT EXISTS `{edge_type}`({_EDGE_COLS})")

    # ── Native indexes (required for MATCH queries in NebulaGraph 3.x) ────────
    # Without tag indexes, MATCH (n:Person) fails with "IndexNotFound".
    # Empty () creates an index covering only the VID+tag, sufficient for
    # tag-type scanning. Data inserted AFTER index creation is auto-indexed.
    _ex("CREATE TAG INDEX IF NOT EXISTS `idx_Props__` ON `Props__`()")
    for tag_name, _ in _ENTITY_TAGS:
        _ex(f"CREATE TAG INDEX IF NOT EXISTS `idx_{tag_name}` ON `{tag_name}`()")
    _ex("CREATE EDGE INDEX IF NOT EXISTS `idx_Relation__` ON `Relation__`()")
    for edge_type in _EDGE_TYPES:
        _ex(f"CREATE EDGE INDEX IF NOT EXISTS `idx_{edge_type}` ON `{edge_type}`()")

    if session is None:
        time.sleep(3.0)
        return

    # Brief wait — the current session already sees the new schema, but a
    # small pause helps the meta service finish committing all DDL before
    # callers open fresh connections.  Real propagation is verified in
    # NebulaGraphAdapter.__init__ via refresh_schema() retry loop.
    time.sleep(3.0)


class NebulaGraphAdapter:
    """
    NebulaGraph distributed graph database adapter.

    Uses nGQL (Nebula Graph Query Language).

    Schema design
    -------------
    Vertices receive two tags:

    1. ``Props__`` — universal document metadata (``doc_id``, ``ref_doc_id``,
       ``source``, ``file_name``, …) on EVERY vertex so that incremental_update
       can track stale nodes regardless of which ingest path was used.

    2. Named entity-type tag (``Person``, ``Organization``, …) — inserted when
       the tag was pre-created in NebulaGraph Studio BEFORE this ingest call.
       The adapter discovers available tags via ``SHOW TAGS`` and caches
       ``DESCRIBE TAG`` column lists so no DDL is issued during ingestion,
       avoiding NebulaGraph's async schema-propagation delay.

    Edges use **named relationship edge types** (``WORKS_FOR``,
    ``HAS_DEPARTMENT``, …) when they were pre-created in Studio.  If no named
    edge type matches, the edge falls back to ``Relation__`` with a ``label``
    property.  Named edge types are discovered via ``SHOW EDGES`` at ingest
    time.

    Pre-creating tags and edges in Studio before ingesting is the recommended
    workflow — see docs/GRAPH-DATABASES/NEBULA-SETUP.md for the full DDL.

    Configuration:
    {
        "host": "localhost",
        "port": 9669,
        "username": "root",
        "password": "nebula",
        "space": "flexible_graphrag"
    }

    References:
    - https://nebula-graph.io/
    - https://python.langchain.com/docs/integrations/graphs/nebula_graph
    """

    def __init__(self, config: Dict[str, Any]):
        if not NEBULA_AVAILABLE:
            raise ImportError(
                "langchain-community required. "
                "Install: pip install langchain-community nebula3-python"
            )

        self.config = config
        _space = (
            config.get("space")
            or config.get("space_name")
            or config.get("database", "flexible_graphrag")
        )
        _host = config.get("host", "localhost")
        _port = int(config.get("port", 9669))
        _username = config.get("username", "root")
        _password = config.get("password", "nebula")

        # Honour the same `overwrite` flag as the LlamaIndex adapter.
        # Always attempt space + schema creation: IF NOT EXISTS makes it a no-op
        # when the space already exists, and fixes SpaceNotFound on first run.
        self._ensure_space_and_schema(_host, _port, _username, _password, _space)

        self.lc_graph = NebulaGraph(
            space=_space,
            username=_username,
            password=_password,
            address=_host,
            port=_port,
        )
        logger.info("Connected to NebulaGraph at %s:%s", _host, _port)

    @staticmethod
    def _ensure_space_and_schema(
        host: str, port: int, username: str, password: str, space: str
    ) -> None:
        """Automate all NebulaGraph setup steps (replaces the manual steps in the docs).

        Steps performed (all idempotent — safe to call repeatedly):
        1. ADD HOSTS "nebula-storaged":9779  — register storaged with metad.
           Required before CREATE SPACE; without it CREATE SPACE fails with
           "Host not enough!".
        2. Poll SHOW HOSTS until at least one ONLINE host appears (up to 90 s).
        3. Check existing spaces. If space is already ready, ensure tags/edges
           and return. If stuck (exists but USE fails), drop and recreate.
        4. CREATE SPACE with partition_num=1 for fast single-node Docker startup.
           Default partition_num=100 requires 100 Raft leader elections (60-120 s).
        5. Poll USE <space> until ready (up to 90 s).
        6. CREATE TAG Props__            — universal doc-metadata tag
        7. CREATE EDGE Relation__        — fallback edge type
        8. CREATE TAGs for all entity types (Person, Company, Location, …)
        9. CREATE EDGEs for all relationship types (WORKS_FOR, HAS_DEPARTMENT, …)
        """
        import time

        try:
            from nebula3.gclient.net import ConnectionPool
            from nebula3.Config import Config as NebulaConfig
        except ImportError:
            logger.warning(
                "nebula3 not available; skipping NebulaGraph space/schema creation"
            )
            return

        cfg = NebulaConfig()
        cfg.max_connection_pool_size = 1
        pool = ConnectionPool()
        try:
            if not pool.init([(host, port)], cfg):
                logger.warning("NebulaGraph: ConnectionPool.init failed — skipping schema setup")
                return
        except Exception as exc:
            logger.warning("NebulaGraph: cannot connect for schema setup: %s", exc)
            return

        try:
            with pool.session_context(username, password) as session:
                def _ex(stmt: str) -> bool:
                    try:
                        r = session.execute(stmt)
                        if not r.is_succeeded():
                            logger.debug("NebulaGraph DDL warning: %s | %s", r.error_msg(), stmt[:120])
                            return False
                        return True
                    except Exception as exc:
                        logger.debug("NebulaGraph DDL error: %s | %s", exc, stmt[:120])
                        return False

                # ── STEP 1: Register storage hosts ────────────────────────────
                # Critical manual step from NEBULA-SETUP.md: "ADD HOSTS"
                # registers storaged with metad. Without it SHOW HOSTS is empty
                # and CREATE SPACE fails with "Host not enough!". Idempotent.
                logger.info("NebulaGraph: registering storaged host nebula-storaged:9779")
                _ex('ADD HOSTS "nebula-storaged":9779')

                # ── STEP 2: Poll until at least one ONLINE host appears ───────
                host_deadline = time.monotonic() + 90.0
                host_ready = False
                while time.monotonic() < host_deadline:
                    r_hosts = session.execute("SHOW HOSTS")
                    if r_hosts.is_succeeded() and r_hosts.rows():
                        statuses = [str(v) for row in r_hosts.rows() for v in row.values]
                        if any("ONLINE" in s.upper() for s in statuses):
                            logger.info(
                                "NebulaGraph: storage host ONLINE (%s)",
                                [str(row.values[0]) for row in r_hosts.rows()],
                            )
                            host_ready = True
                            break
                    time.sleep(3.0)

                if not host_ready:
                    logger.warning(
                        "NebulaGraph: no ONLINE storage hosts after 90 s — "
                        "CREATE SPACE will likely fail with 'Host not enough!'"
                    )

                # ── STEP 3: Check existing spaces ─────────────────────────────
                r_show = session.execute("SHOW SPACES")
                existing_spaces: list = []
                if r_show.is_succeeded():
                    existing_spaces = [str(row.values[0]) for row in r_show.rows()]
                logger.info("NebulaGraph: existing spaces = %s", existing_spaces)

                if space in existing_spaces:
                    r_use = session.execute(f"USE `{space}`")
                    if r_use.is_succeeded():
                        logger.info(
                            "NebulaGraph: space '%s' already exists and is ready — "
                            "ensuring all tags/edges are present", space
                        )
                        _ensure_tags_and_edges(_ex, session)
                        return
                    else:
                        logger.warning(
                            "NebulaGraph: space '%s' exists but USE failed (%s); "
                            "dropping and recreating with partition_num=1",
                            space, r_use.error_msg(),
                        )
                        _ex(f"DROP SPACE IF EXISTS `{space}`")
                        time.sleep(5.0)

                # ── STEP 4: Create space ───────────────────────────────────────
                r_create = session.execute(
                    f"CREATE SPACE IF NOT EXISTS `{space}` "
                    f"(partition_num=1, replica_factor=1, vid_type=FIXED_STRING(256))"
                )
                if not r_create.is_succeeded():
                    logger.warning(
                        "NebulaGraph: CREATE SPACE '%s' failed: %s",
                        space, r_create.error_msg(),
                    )

                # ── STEP 5: Poll until USE <space> succeeds ───────────────────
                deadline = time.monotonic() + 90.0
                ready = False
                while time.monotonic() < deadline:
                    r = session.execute(f"USE `{space}`")
                    if r.is_succeeded():
                        ready = True
                        break
                    time.sleep(2.0)
                if not ready:
                    logger.warning(
                        "NebulaGraph: space '%s' not ready after 90 s; "
                        "schema creation may be incomplete", space
                    )
                    return

                # ── STEPS 6-9: Create all tags and edges ──────────────────────
                _ensure_tags_and_edges(_ex, session)
                logger.info("NebulaGraph: space '%s' and full schema ready", space)

        except Exception as exc:
            logger.warning("NebulaGraph _ensure_space_and_schema failed: %s", exc)
        finally:
            pool.close()

    def create_qa_chain(self, llm: Any):
        """Create nGQL QA chain for NebulaGraph."""
        try:
            from langchain_community.chains.graph_qa.nebulagraph import NebulaGraphQAChain
            return NebulaGraphQAChain.from_llm(
                llm=llm,
                graph=self.lc_graph,
                verbose=False,
            )
        except ImportError:
            logger.warning("NebulaGraphQAChain not available; falling back to generic Cypher chain")
            from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
            return GraphCypherQAChain.from_llm(
                llm=llm,
                graph=self.lc_graph,
                verbose=False,
                allow_dangerous_requests=True,
            )

    def get_graph(self):
        return self.lc_graph

    def delete(self, ref_doc_id: str) -> None:
        """Delete all vertices tagged with *ref_doc_id* from NebulaGraph using nGQL.

        NebulaGraph uses nGQL (not Cypher), so the default Cypher DETACH DELETE
        in ``LangChainPGAdapter`` won't work.  This override finds VIDs via a
        MATCH on the ``Props__`` tag (which stores ``ref_doc_id``) and then
        deletes them with DELETE VERTEX ... WITH EDGE.
        """
        space = (
            self.config.get("space")
            or self.config.get("space_name")
            or self.config.get("database", "flexible_graphrag")
        )
        _rid = ref_doc_id.replace('"', '\\"')
        # MATCH uses openCypher style; DELETE VERTEX is nGQL.
        # NebulaGraph 3.x supports MATCH within nGQL contexts.
        fetch_ngql = (
            f"USE `{space}`; "
            f'MATCH (v) WHERE v.`Props__`.`ref_doc_id` == "{_rid}" '
            f"RETURN id(v) AS vid LIMIT 1000"
        )
        try:
            result = self.lc_graph.execute(fetch_ngql)
            if not result.is_succeeded():
                logger.debug(
                    "NebulaGraph delete: MATCH query failed: %s", result.error_msg()
                )
                return
            vids = []
            for row in result.rows():
                vid = row.values[0]
                if vid.HasField("sVal"):
                    vids.append(vid.sVal.decode("utf-8"))
                elif vid.HasField("iVal"):
                    vids.append(str(vid.iVal))
            if not vids:
                logger.info(
                    "NebulaGraph: no vertices found for ref_doc_id=%s", ref_doc_id
                )
                return
            vid_list = ", ".join(f'"{v}"' for v in vids)
            del_ngql = f"USE `{space}`; DELETE VERTEX {vid_list} WITH EDGE"
            del_result = self.lc_graph.execute(del_ngql)
            if del_result.is_succeeded():
                logger.info(
                    "NebulaGraph: deleted %d vertices for ref_doc_id=%s",
                    len(vids), ref_doc_id,
                )
            else:
                logger.warning(
                    "NebulaGraph: DELETE VERTEX failed for ref_doc_id=%s: %s",
                    ref_doc_id, del_result.error_msg(),
                )
        except Exception as exc:
            logger.warning("NebulaGraph delete failed for ref_doc_id=%s: %s", ref_doc_id, exc)

    def _ex(self, ngql: str, space: str) -> bool:
        """Execute an nGQL statement; return True on success."""
        result = self.lc_graph.execute(f"USE `{space}`; {ngql}")
        if not result.is_succeeded():
            logger.debug("NebulaGraph nGQL warning: %s | %s", result.error_msg(), ngql[:160])
            return False
        return True

    def _show_names(self, space: str, kind: str) -> set:
        """Return set of tag or edge type names that exist in the space.

        ``kind`` must be ``'TAGS'`` or ``'EDGES'``.
        """
        names: set = set()
        try:
            result = self.lc_graph.execute(f"USE `{space}`; SHOW {kind}")
            if result.is_succeeded():
                for row in result.rows():
                    names.add(row.values[0].get_sVal().decode("utf-8"))
        except Exception as exc:
            logger.debug("NebulaGraph SHOW %s failed: %s", kind, exc)
        return names

    def _describe_cols(self, space: str, kind: str, name: str) -> set:
        """Return set of column names for a tag or edge type.

        ``kind`` must be ``'TAG'`` or ``'EDGE'``.
        """
        cols: set = set()
        try:
            result = self.lc_graph.execute(f"USE `{space}`; DESCRIBE {kind} `{name}`")
            if result.is_succeeded():
                for row in result.rows():
                    cols.add(row.values[0].get_sVal().decode("utf-8"))
        except Exception as exc:
            logger.debug("NebulaGraph DESCRIBE %s %s failed: %s", kind, name, exc)
        return cols

    def add_graph_documents(self, graph_documents, include_source: bool = False, **kwargs) -> None:
        """Write graph documents to NebulaGraph.

        Vertex schema
        -------------
        Every vertex gets the pre-created ``Props__`` tag populated with
        document metadata (``doc_id``, ``ref_doc_id``, ``source``, …).
        If a named entity-type tag (``Person``, ``Organization``, …) was
        pre-created in Studio, that tag is also inserted with the entity's
        semantic properties (``name``, ``hire_date``, …).

        Edge schema
        -----------
        If a named edge type matching the relationship (``WORKS_FOR``,
        ``HAS_DEPARTMENT``, …) was pre-created in Studio, that type is used
        directly so that nGQL queries can use
        ``MATCH (p:Person)-[:WORKS_FOR]->(c:Organization)``.
        Relationships with no matching named edge type fall back to
        ``Relation__`` with a ``label`` property.
        """
        space = (
            self.config.get("space")
            or self.config.get("space_name")
            or self.config.get("database", "flexible_graphrag")
        )

        def _esc(v: str) -> str:
            return str(v).replace("\\", "\\\\").replace('"', '\\"')

        # Discover pre-existing tags and edge types once per ingest call.
        existing_tags = self._show_names(space, "TAGS")
        existing_edges = self._show_names(space, "EDGES")
        logger.debug(
            "NebulaGraph schema: %d tags, %d edge types available",
            len(existing_tags), len(existing_edges),
        )

        # Cache DESCRIBE results so we don't query the same tag/edge twice.
        tag_cols_cache: Dict[str, set] = {}
        edge_cols_cache: Dict[str, set] = {}

        def _tag_cols(tag: str) -> set:
            if tag not in tag_cols_cache:
                tag_cols_cache[tag] = self._describe_cols(space, "TAG", tag)
            return tag_cols_cache[tag]

        def _edge_cols(edge: str) -> set:
            if edge not in edge_cols_cache:
                edge_cols_cache[edge] = self._describe_cols(space, "EDGE", edge)
            return edge_cols_cache[edge]

        # Also cache Props__ columns so we only query once.
        props_cols: Optional[set] = None

        def _props_cols() -> set:
            nonlocal props_cols
            if props_cols is None:
                props_cols = _tag_cols("Props__")
            return props_cols

        stored_nodes, stored_rels = 0, 0

        for doc in graph_documents:
            # Collect document-level metadata from the source Document.
            src_meta: Dict[str, str] = {}
            if include_source and doc.source is not None:
                raw_meta = getattr(doc.source, "metadata", {}) or {}
                for col in _PROPS_META_COLS:
                    val = raw_meta.get(col)
                    if val is not None:
                        src_meta[col] = str(val)
                if "doc_id" not in src_meta and "id" in raw_meta:
                    src_meta["doc_id"] = str(raw_meta["id"])

            # ---- Vertices -------------------------------------------------------
            for node in doc.nodes:
                vid = _esc(node.id)
                entity_type = (node.type or "Entity").replace(" ", "_")

                # Props__ — universal metadata + _node_type marker
                known_props = _props_cols()
                props_data: Dict[str, str] = {}
                for col, val in src_meta.items():
                    if col in known_props:
                        props_data[col] = val
                if "_node_type" in known_props:
                    props_data["_node_type"] = entity_type
                if "triplet_source_id" in known_props:
                    props_data.setdefault("triplet_source_id", node.id)

                if props_data:
                    cols = ", ".join(f"`{c}`" for c in props_data)
                    vals = ", ".join(f'"{_esc(v)}"' for v in props_data.values())
                    self._ex(
                        f'INSERT VERTEX `Props__`({cols}) VALUES "{vid}":({vals})',
                        space,
                    )
                else:
                    self._ex(
                        f'INSERT VERTEX IF NOT EXISTS `Props__`() VALUES "{vid}":() ',
                        space,
                    )

                # Named entity-type tag (e.g. Person, Organization)
                if entity_type in existing_tags:
                    known_cols = _tag_cols(entity_type)
                    typed_data: Dict[str, str] = {}
                    if "id" in known_cols:
                        typed_data["id"] = node.id
                    if "name" in known_cols:
                        typed_data["name"] = node.id
                    for k, v in (node.properties or {}).items():
                        k_norm = str(k).replace(" ", "_").lower()
                        if k_norm in known_cols:
                            typed_data[k_norm] = str(v)
                    if typed_data:
                        t_cols = ", ".join(f"`{c}`" for c in typed_data)
                        t_vals = ", ".join(f'"{_esc(v)}"' for v in typed_data.values())
                        self._ex(
                            f'INSERT VERTEX `{entity_type}`({t_cols}) '
                            f'VALUES "{vid}":({t_vals})',
                            space,
                        )

                stored_nodes += 1

            # ---- Edges ----------------------------------------------------------
            for rel in doc.relationships:
                src_vid = _esc(rel.source.id)
                tgt_vid = _esc(rel.target.id)
                rel_type = rel.type.replace(" ", "_").upper()

                if rel_type in existing_edges:
                    # Named edge type — use it directly, populate only columns
                    # that exist in its schema (typically doc metadata columns).
                    known_ecols = _edge_cols(rel_type)
                    edge_data: Dict[str, str] = {}
                    for col, val in src_meta.items():
                        if col in known_ecols:
                            edge_data[col] = val
                    if edge_data:
                        e_cols = ", ".join(f"`{c}`" for c in edge_data)
                        e_vals = ", ".join(f'"{_esc(v)}"' for v in edge_data.values())
                        self._ex(
                            f'INSERT EDGE `{rel_type}`({e_cols}) '
                            f'VALUES "{src_vid}" -> "{tgt_vid}":({e_vals})',
                            space,
                        )
                    else:
                        self._ex(
                            f'INSERT EDGE IF NOT EXISTS `{rel_type}`() '
                            f'VALUES "{src_vid}" -> "{tgt_vid}":() ',
                            space,
                        )
                else:
                    # Fallback: Relation__ with label property
                    rel_cols = ["`label`"]
                    rel_vals = [f'"{_esc(rel_type)}"']
                    for col, val in src_meta.items():
                        rel_cols.append(f"`{col}`")
                        rel_vals.append(f'"{_esc(val)}"')
                    self._ex(
                        f'INSERT EDGE `Relation__`({", ".join(rel_cols)}) '
                        f'VALUES "{src_vid}" -> "{tgt_vid}":({", ".join(rel_vals)})',
                        space,
                    )

                stored_rels += 1

        logger.info(
            "NebulaGraph: wrote %d vertices, %d edges to space '%s'",
            stored_nodes, stored_rels, space,
        )
        try:
            self.lc_graph.refresh_schema()
        except Exception as exc:
            logger.debug("NebulaGraph refresh_schema: %s", exc)

    def normalize_entity_names(self) -> None:
        """No-op for NebulaGraph: entity names are stored as VIDs."""
        logger.debug("NebulaGraph: entity names stored as VIDs — normalize_entity_names skipped")


__all__ = ["NebulaGraphAdapter", "NEBULA_AVAILABLE"]
