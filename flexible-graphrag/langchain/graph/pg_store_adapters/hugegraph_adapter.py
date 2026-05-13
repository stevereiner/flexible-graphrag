"""LangChain HugeGraph distributed graph database adapter."""
from __future__ import annotations

import logging
import re
import sys
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_MAX_ID_LEN = 128       # HugeGraph custom string vertex ID length limit (conservative)
_MAX_PROP_LEN = 4096    # Max property value length

def _safe_label(name: str) -> str:
    """Convert an arbitrary string into a HugeGraph-safe label/property key name."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(name)).strip("_")
    return s[:128] or "unknown"

def _safe_id(node_id: str) -> str:
    """Sanitize a node ID into a HugeGraph-safe custom string vertex ID.

    HugeGraph rejects custom string IDs that contain spaces or other
    special characters with a 400 IllegalArgumentException.  Replace every
    run of whitespace with an underscore and strip any remaining characters
    that are not alphanumeric, underscore, or hyphen.
    """
    s = re.sub(r"\s+", "_", str(node_id))
    s = re.sub(r"[^A-Za-z0-9_\-]", "_", s).strip("_")
    return s[:_MAX_ID_LEN] or "unknown"

def _safe_val(v: Any) -> str:
    """Coerce a property value to a truncated string."""
    return str(v)[:_MAX_PROP_LEN]

# hugegraph-python ≥1.5.0 ships as the 'pyhugegraph' module.
# langchain_community.graphs.hugegraph imports from 'hugegraph.connection',
# the legacy module name used in hugegraph-python ≤1.0.x.
# We create a lightweight compatibility shim so the import resolves.
def _install_hugegraph_shim() -> bool:
    """Inject a 'hugegraph.connection' alias pointing at pyhugegraph."""
    try:
        from pyhugegraph.client import PyHugeClient  # type: ignore
        import types

        conn_mod = types.ModuleType("hugegraph.connection")
        conn_mod.PyHugeGraph = PyHugeClient  # type: ignore[attr-defined]

        hg_pkg = types.ModuleType("hugegraph")
        hg_pkg.connection = conn_mod

        sys.modules.setdefault("hugegraph", hg_pkg)
        sys.modules.setdefault("hugegraph.connection", conn_mod)
        return True
    except ImportError:
        return False

_hugegraph_shim_ok = _install_hugegraph_shim()

try:
    from langchain_community.graphs import HugeGraph
    HUGEGRAPH_AVAILABLE = True
except ImportError:
    HUGEGRAPH_AVAILABLE = False


class HugeGraphAdapter:
    """
    Apache HugeGraph distributed graph database adapter.

    Uses Gremlin and HugeGraph-specific APIs.
    ``add_graph_documents`` writes nodes as ``__Entity__`` vertices and
    relationships as named edge labels, with schema auto-provisioned on
    first call.

    Configuration:
    {
        "host": "localhost",
        "port": 8082,
        "username": "admin",
        "password": "password",
        "database": "hugegraph"
    }

    References:
    - https://hugegraph.apache.org/
    - https://python.langchain.com/docs/integrations/graphs/hugegraph
    """

    def __init__(self, config: Dict[str, Any]):
        if not HUGEGRAPH_AVAILABLE:
            raise ImportError(
                "langchain-community required. "
                "Install: pip install langchain-community hugegraph-python"
            )

        self.config = config
        self.lc_graph = HugeGraph(
            username=config.get("username", "admin"),
            password=config.get("password", "password"),
            address=config.get("host", "localhost"),
            port=int(config.get("port", 8082)),
            graph=config.get("database", "hugegraph"),
        )
        logger.info(
            "Connected to HugeGraph at %s:%s",
            config.get("host", "localhost"),
            config.get("port", 8082),
        )

    def create_qa_chain(self, llm: Any):
        """Create a QA chain for HugeGraph using the openCypher REST endpoint.

        Uses a custom Cypher generation prompt that explains HugeGraph's
        ``__Entity__`` labelling scheme so the LLM produces valid queries.
        """
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
        from langchain_core.prompts import PromptTemplate

        schema_str = self._build_structured_schema_str()
        view = self._cypher_view()

        _HG_CYPHER_TEMPLATE = """\
You are an expert Cypher query writer for Apache HugeGraph.
Given the schema below, write a Cypher query to answer the question.

Schema:
{schema}

Important rules — read carefully:
- ALL entity nodes use the label __Entity__, regardless of type (Person, Organization, etc.).
  Never use labels like :Person, :Organization, :Location — they do not exist.
- To filter by entity type use: WHERE n.node_type = 'Person'
- The `name` property holds the entity's display name. Always use n.name (not n.id).
- Use case-insensitive partial matching for string comparisons:
    WHERE toLower(n.name) CONTAINS toLower("value")
- NEVER use UNION or UNION ALL — HugeGraph requires identical column names across
  all UNION arms and will reject queries that don't match. Use OPTIONAL MATCH instead.
- Typical query patterns:
    # Who works for a company
    MATCH (p:__Entity__)-[:WORKS_FOR]->(o:__Entity__)
    WHERE toLower(o.name) CONTAINS 'acme'
    RETURN p.name, p.node_type

    # All of an org's departments, locations, and leaders in one query
    MATCH (o:__Entity__) WHERE toLower(o.name) CONTAINS 'acme'
    OPTIONAL MATCH (o)-[:HAS_DEPARTMENT]->(d:__Entity__)
    OPTIONAL MATCH (o)-[:HAS_LOCATION]->(l:__Entity__)
    OPTIONAL MATCH (o)-[:LED_BY]->(ldr:__Entity__)
    RETURN o.name AS org,
           d.name AS department,
           l.name AS location,
           ldr.name AS leader

    # All relationships out of an entity
    MATCH (o:__Entity__)-[r]->(related:__Entity__)
    WHERE toLower(o.name) CONTAINS 'acme'
    RETURN type(r) AS relationship, related.name, related.node_type
    ORDER BY relationship

- Output ONLY the raw Cypher query — no explanation, no markdown fences.

Question: {question}
Cypher query:"""

        try:
            cypher_prompt = PromptTemplate(
                input_variables=["schema", "question"],
                template=_HG_CYPHER_TEMPLATE,
            )
        except Exception:
            cypher_prompt = None

        kwargs: Dict[str, Any] = {
            "llm": llm,
            "graph": view,
            "allow_dangerous_requests": True,
            "verbose": False,
        }
        if cypher_prompt:
            kwargs["cypher_prompt"] = cypher_prompt

        chain = GraphCypherQAChain.from_llm(**kwargs)
        try:
            chain.graph_schema = schema_str
        except Exception:
            pass
        return chain

    def _build_structured_schema_str(self) -> str:
        """Build a clean, LLM-readable schema string from the HugeGraph REST API."""
        import requests as _req

        host  = self.config.get("host", "localhost")
        port  = int(self.config.get("port", 8082))
        graph = self.config.get("database", "hugegraph")
        base  = f"http://{host}:{port}/graphs/{graph}/schema"
        username = self.config.get("username")
        password = self.config.get("password")
        auth = (username, password) if username and password else None

        try:
            vl_data = _req.get(f"{base}/vertexlabels", auth=auth, timeout=10).json()
            el_data = _req.get(f"{base}/edgelabels",   auth=auth, timeout=10).json()
            node_lines = []
            for vl in vl_data.get("vertexlabels", []):
                props = ", ".join(f"{p}: STRING" for p in vl.get("properties", []))
                node_lines.append(f"- {vl['name']} {{{props}}}")
            rel_lines = []
            for el in el_data.get("edgelabels", []):
                src  = el.get("source_label", "__Entity__")
                tgt  = el.get("target_label", "__Entity__")
                name = el.get("name", "")
                if name and name != "TEST_REL":
                    rel_lines.append(f"(:{src})-[:{name}]->(:{tgt})")
            return (
                "Node properties:\n"
                + "\n".join(node_lines)
                + "\n\nRelationship types:\n"
                + "\n".join(rel_lines)
            )
        except Exception as exc:
            logger.debug("HugeGraph schema string build failed: %s", exc)
            return self.lc_graph.schema or ""


    def _cypher_request(self, query: str) -> List[Any]:
        """Execute *query* against HugeGraph's openCypher REST endpoint.

        If the query contains UNION / UNION ALL (which HugeGraph rejects when
        column names differ across arms), each arm is executed individually and
        results are merged.  Returns the ``result.data`` list, or ``[]`` on error.
        """
        import re
        if re.search(r'\bUNION\b', query, flags=re.IGNORECASE):
            return self._cypher_request_split_union(query)
        return self._cypher_request_raw(query)

    def _cypher_request_raw(self, query: str) -> List[Any]:
        """Single POST to HugeGraph's openCypher REST endpoint."""
        import requests as _req

        host  = self.config.get("host", "localhost")
        port  = int(self.config.get("port", 8082))
        graph = self.config.get("database", "hugegraph")
        url   = f"http://{host}:{port}/graphs/{graph}/cypher"

        username = self.config.get("username")
        password = self.config.get("password")
        auth = (username, password) if username and password else None

        try:
            resp = _req.post(
                url,
                data=query,
                headers={"Content-Type": "application/json"},
                auth=auth,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("status", {}).get("code", 200) != 200:
                msg = body["status"].get("message", "")
                logger.warning("HugeGraph Cypher error: %s | query: %s", msg, query[:200])
                return []
            return body.get("result", {}).get("data") or []
        except Exception as exc:
            logger.warning("HugeGraph Cypher request failed: %s | query: %s", exc, query[:200])
            return []

    def _cypher_request_split_union(self, query: str) -> List[Any]:
        """Split a UNION query into arms, execute each, and merge results."""
        import re
        arms = re.split(r'\bUNION(?:\s+ALL)?\b', query, flags=re.IGNORECASE)
        merged: List[Any] = []
        seen: set = set()
        for arm in arms:
            arm = arm.strip()
            if not arm:
                continue
            try:
                rows = self._cypher_request_raw(arm)
                for row in rows:
                    key = str(row)
                    if key not in seen:
                        seen.add(key)
                        merged.append(row)
            except Exception as exc:
                logger.debug("HugeGraph UNION arm failed: %s | arm: %.200s", exc, arm)
        return merged


    def _cypher_view(self) -> Any:
        """Return a ``GraphStore``-compatible object wired to the Cypher endpoint.

        Inherits from ``langchain_community.graphs.graph_store.GraphStore`` so
        that pydantic's ``isinstance`` check inside ``GraphCypherQAChain``
        passes.  Implements all required abstract methods.
        """
        from langchain_community.graphs.graph_store import GraphStore as _GS
        from langchain_community.graphs.graph_document import GraphDocument as _GD

        adapter = self

        _underlying = self.lc_graph   # pyhugegraph client — has .address/.port/.graph etc.

        class _HugeGraphCypherView(_GS):
            """Thin Cypher-endpoint view over HugeGraph for LangChain QA chains.

            - ``get_schema`` — schema string for Cypher generation prompt
            - ``get_structured_schema`` — structured dict for ``construct_schema()``
            - ``query(cypher, params={})`` — routes to HugeGraph openCypher REST
            - ``add_graph_documents`` — delegates to adapter

            Exposes raw client attributes (address, port, graph, username, password)
            so that ``build_cypher_hugegraph`` in retrievers/chains/_hugegraph.py can
            construct the schema REST URL without needing the underlying client directly.
            """

            # Forward connection attributes from the underlying pyhugegraph client so
            # the chain builder in _hugegraph.py can call _hg.address / _hg.port etc.
            address  = getattr(_underlying, "address",  "localhost")
            port     = getattr(_underlying, "port",     8082)
            graph    = getattr(_underlying, "graph",    "hugegraph")
            username = getattr(_underlying, "username", None)
            password = getattr(_underlying, "password", None)

            @property
            def get_schema(self) -> str:
                return adapter.lc_graph.schema

            @property
            def schema(self) -> str:
                return adapter.lc_graph.schema

            @property
            def get_structured_schema(self) -> Dict[str, Any]:
                return adapter._build_structured_schema()

            @property
            def structured_schema(self) -> Dict[str, Any]:
                return adapter._build_structured_schema()

            def query(self, query: str, params: dict = {}) -> List[Any]:
                return adapter._cypher_request(query)

            def refresh_schema(self) -> None:
                adapter.lc_graph.refresh_schema()

            def add_graph_documents(
                self,
                graph_documents: List[_GD],
                include_source: bool = False,
            ) -> None:
                adapter.add_graph_documents(graph_documents, include_source=include_source)

        return _HugeGraphCypherView()

    def get_graph(self):
        # Return the Cypher-capable view so that lc_graph.query(cypher) routes through
        # the HugeGraph openCypher endpoint instead of the Gremlin protocol.
        # The Gremlin client (self.lc_graph) uses blocking gremlinpython which raises
        # "Cannot run event loop" when called from an async FastAPI handler.
        try:
            return self._cypher_view()
        except Exception:
            return self.lc_graph

    def get_lc_graph(self):
        """Return the Cypher view for /api/graph/query routing."""
        return self.get_graph()

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    def _get_pyhugeclient(self):
        """Return a fresh ``PyHugeClient`` connected to the configured server."""
        from pyhugegraph.client import PyHugeClient
        return PyHugeClient(
            self.config.get("host", "localhost"),
            str(self.config.get("port", 8082)),
            self.config.get("database", "hugegraph"),
            self.config.get("username", "admin"),
            self.config.get("password", "password"),
        )

    def _build_structured_schema(self) -> Dict[str, Any]:
        """Return a ``structured_schema`` dict for ``GraphCypherQAChain``.

        Fetches vertex/edge labels directly from the HugeGraph REST API and
        translates them into LangChain's expected format::

            {
                "node_props":    {label: [{"property": name, "type": "STRING"}, ...]},
                "rel_props":     {},
                "relationships": [{"start": src, "type": rel, "end": tgt}, ...],
                "metadata":      {},
            }
        """
        import requests as _req

        host  = self.config.get("host", "localhost")
        port  = int(self.config.get("port", 8082))
        graph = self.config.get("database", "hugegraph")
        base  = f"http://{host}:{port}/graphs/{graph}/schema"
        username = self.config.get("username")
        password = self.config.get("password")
        auth = (username, password) if username and password else None

        node_props: Dict[str, Any] = {}
        relationships: List[Any] = []

        try:
            vl_resp = _req.get(f"{base}/vertexlabels", auth=auth, timeout=10)
            for vl in vl_resp.json().get("vertexlabels", []):
                name = vl.get("name", "")
                node_props[name] = [
                    {"property": p, "type": "STRING"}
                    for p in vl.get("properties", [])
                ]
        except Exception as exc:
            logger.debug("HugeGraph _build_structured_schema vertexlabels: %s", exc)

        try:
            el_resp = _req.get(f"{base}/edgelabels", auth=auth, timeout=10)
            for el in el_resp.json().get("edgelabels", []):
                relationships.append({
                    "start": el.get("source_label", "__Entity__"),
                    "type":  el.get("name", ""),
                    "end":   el.get("target_label", "__Entity__"),
                })
        except Exception as exc:
            logger.debug("HugeGraph _build_structured_schema edgelabels: %s", exc)

        return {
            "node_props":    node_props,
            "rel_props":     {},
            "relationships": relationships,
            "metadata":      {},
        }

    def _ensure_property_key(self, schema, name: str, _created: Set[str]) -> None:
        """Create a TEXT property key in HugeGraph if it does not already exist."""
        safe = _safe_label(name)
        if safe in _created:
            return
        try:
            schema.propertyKey(safe).asText().ifNotExist().create()
        except Exception as exc:
            logger.debug("HugeGraph propertyKey %r: %s", safe, exc)
        _created.add(safe)

    def _ensure_vertex_label(self, schema, label: str, props: List[str], _created: Set[str]) -> None:
        """Ensure vertex label exists with ALL requested properties.

        Uses ``ifNotExist().create()`` for the initial creation, then calls
        ``append()`` for each property not yet registered on the label.  This
        handles the case where the label was created in an earlier run with a
        smaller property set (adding new properties via ``create()`` would be
        silently ignored by ``ifNotExist()``).
        """
        cache_key = f"VL:{label}"
        if cache_key in _created:
            return
        # Step 1: create (no-op if already exists)
        try:
            builder = schema.vertexLabel(label).useCustomizeStringId()
            if props:
                builder = builder.properties(*props).nullableKeys(*props)
            builder.ifNotExist().create()
        except Exception as exc:
            logger.debug("HugeGraph vertexLabel create %r: %s", label, exc)

        # Step 2: append any properties not yet on the label
        for prop in (props or []):
            try:
                schema.vertexLabel(label).properties(prop).nullableKeys(prop).append()
            except Exception as exc:
                logger.debug("HugeGraph vertexLabel append %r.%r: %s", label, prop, exc)

        _created.add(cache_key)

    def _ensure_edge_label(
        self,
        schema,
        rel_type: str,
        src_label: str,
        tgt_label: str,
        _created: Set[str],
    ) -> None:
        """Create an edge label linking *src_label* → *tgt_label* (if not exists)."""
        cache_key = f"EL:{rel_type}"
        if cache_key in _created:
            return
        try:
            schema.edgeLabel(rel_type).link(src_label, tgt_label).ifNotExist().create()
        except Exception as exc:
            logger.debug("HugeGraph edgeLabel %r: %s", rel_type, exc)
        _created.add(cache_key)

    # ------------------------------------------------------------------
    # add_graph_documents
    # ------------------------------------------------------------------

    def add_graph_documents(
        self,
        graph_docs: List[Any],
        include_source: bool = True,
    ) -> None:
        """Write LangChain ``GraphDocument`` objects into HugeGraph.

        All nodes are stored under the ``__Entity__`` vertex label using
        *custom string IDs* so that multiple calls with the same data are
        idempotent (HugeGraph overwrites an existing vertex when the same ID
        is re-submitted).  Relationships become edge labels linking
        ``__Entity__`` → ``__Entity__``.

        Parameters
        ----------
        graph_docs:
            List of ``langchain_community.graphs.graph_document.GraphDocument``
            objects produced by ``LLMGraphTransformer.convert_to_graph_documents``.
        include_source:
            When ``True``, source documents are also added as ``__Chunk__``
            vertices (the default).  Set to ``False`` to skip them.
        """
        client = self._get_pyhugeclient()
        schema = client.schema()
        graph_api = client.graph()

        _schema_created: Set[str] = set()

        # ---- 1. Collect all property names from the batch ---------------
        all_props: Set[str] = {"name", "node_type"}
        for gd in graph_docs:
            for node in gd.nodes:
                for k in node.properties:
                    all_props.add(_safe_label(k))
            for rel in gd.relationships:
                for k in rel.properties:
                    all_props.add(_safe_label(k))

        # ---- 2. Ensure property keys exist ------------------------------
        for prop in sorted(all_props):
            self._ensure_property_key(schema, prop, _schema_created)
        if include_source:
            for p in ("source_text", "source_id"):
                self._ensure_property_key(schema, p, _schema_created)

        # ---- 3. Ensure __Entity__ vertex label --------------------------
        entity_props = sorted(all_props)
        self._ensure_vertex_label(schema, "__Entity__", entity_props, _schema_created)

        # ---- 4. Ensure __Chunk__ vertex label ---------------------------
        if include_source:
            self._ensure_vertex_label(schema, "__Chunk__", ["source_id", "source_text"], _schema_created)

        # ---- 5. Ensure edge labels (all link __Entity__ → __Entity__) ---
        all_rel_types: Set[str] = set()
        edge_label_props: Dict[str, Set[str]] = {}
        for gd in graph_docs:
            for rel in gd.relationships:
                rel_label = _safe_label(rel.type)
                all_rel_types.add(rel_label)
                for k in rel.properties:
                    edge_label_props.setdefault(rel_label, set()).add(_safe_label(k))
        for rel_type in sorted(all_rel_types):
            self._ensure_edge_label(schema, rel_type, "__Entity__", "__Entity__", _schema_created)

        if include_source:
            self._ensure_edge_label(schema, "MENTIONS", "__Chunk__", "__Entity__", _schema_created)

        # Append any edge properties not yet registered on their labels
        for edge_label, props_set in edge_label_props.items():
            for prop in sorted(props_set):
                self._ensure_property_key(schema, prop, _schema_created)
                try:
                    schema.edgeLabel(edge_label).properties(prop).nullableKeys(prop).append()
                except Exception as exc:
                    logger.debug("HugeGraph edgeLabel append %r.%r: %s", edge_label, prop, exc)

        # ---- 5b. Secondary index on __Entity__.name (enables WHERE n.name = ...) ---
        try:
            schema.indexLabel("entity_by_name").onV("__Entity__").by("name").secondary().ifNotExist().create()
        except Exception as exc:
            logger.debug("HugeGraph indexLabel entity_by_name: %s", exc)

        # ---- 6. Add vertices (batch) ------------------------------------
        vertex_batch: List[Any] = []
        vertex_ids: Set[str] = set()

        for gd in graph_docs:
            for node in gd.nodes:
                vid = _safe_id(node.id)
                if vid in vertex_ids:
                    continue
                vertex_ids.add(vid)
                props: Dict[str, str] = {
                    "name": _safe_val(node.properties.get("name", node.id)),
                    "node_type": _safe_val(node.type),
                }
                for k, v in node.properties.items():
                    safe_k = _safe_label(k)
                    if safe_k not in ("name", "node_type"):
                        props[safe_k] = _safe_val(v)
                vertex_batch.append(("__Entity__", props, vid))

        # HugeGraph batch-vertex API doesn't support custom IDs; add individually.
        for label, props, vid in vertex_batch:
            try:
                graph_api.addVertex(label, props, id=vid)
            except Exception as exc:
                logger.debug("HugeGraph addVertex id=%r: %s", vid, exc)

        # ---- 7. Add source document vertices ----------------------------
        chunk_vertex_ids: Dict[str, str] = {}
        if include_source:
            for gd in graph_docs:
                if gd.source is None:
                    continue
                src_path = gd.source.metadata.get("file_path") or gd.source.metadata.get("source", "")
                chunk_vid = _safe_id(src_path or gd.source.page_content[:64])
                chunk_vertex_ids[id(gd)] = chunk_vid
                chunk_props = {
                    "source_id": _safe_val(src_path),
                    "source_text": _safe_val(gd.source.page_content[:512]),
                }
                try:
                    graph_api.addVertex("__Chunk__", chunk_props, id=chunk_vid)
                except Exception as exc:
                    logger.debug("HugeGraph addVertex __Chunk__ id=%r: %s", chunk_vid, exc)

        # ---- 8. Add edges (batch) ----------------------------------------
        # addEdges requires (edge_label, out_id, in_id, out_v_label, in_v_label, props)
        edge_batch: List[tuple] = []
        for gd in graph_docs:
            for rel in gd.relationships:
                src_vid = _safe_id(rel.source.id)
                tgt_vid = _safe_id(rel.target.id)
                rel_label = _safe_label(rel.type)
                edge_props: Dict[str, str] = {
                    _safe_label(k): _safe_val(v) for k, v in rel.properties.items()
                }
                edge_batch.append((rel_label, src_vid, tgt_vid, "__Entity__", "__Entity__", edge_props))

            if include_source:
                chunk_vid = chunk_vertex_ids.get(id(gd))
                if chunk_vid:
                    for node in gd.nodes:
                        edge_batch.append(("MENTIONS", chunk_vid, _safe_id(node.id), "__Chunk__", "__Entity__", {}))

        # Split into chunks to stay within HugeGraph's batch size limits
        _BATCH = 200
        for i in range(0, len(edge_batch), _BATCH):
            batch_slice = edge_batch[i : i + _BATCH]
            try:
                graph_api.addEdges(batch_slice)
            except Exception as exc:
                logger.warning("HugeGraph addEdges batch failed, retrying one-by-one: %s", exc)
                for item in batch_slice:
                    try:
                        graph_api.addEdges([item])
                    except Exception as exc2:
                        logger.debug(
                            "HugeGraph addEdge %s→%s [%s]: %s",
                            item[1], item[2], item[0], exc2,
                        )

        logger.info(
            "HugeGraph add_graph_documents: %d vertices, %d edges written",
            len(vertex_batch),
            len(edge_batch),
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete all ``__Entity__`` nodes tagged with *ref_doc_id* from HugeGraph.

        Uses the openCypher endpoint via :meth:`_cypher_request`.
        HugeGraph UNION rules apply (no UNION across delete branches) so we
        issue a single query matching all entity types by ``ref_doc_id``.
        """
        _rid = ref_doc_id.replace("'", "\\'")
        # DETACH DELETE removes the node and all incident edges automatically.
        cypher = (
            f"MATCH (n:__Entity__) WHERE n.ref_doc_id = '{_rid}' DETACH DELETE n"
        )
        try:
            self._cypher_request(cypher)
            logger.info("HugeGraph: deleted __Entity__ nodes for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("HugeGraph delete failed for ref_doc_id=%s: %s", ref_doc_id, exc)

    def normalize_entity_names(self) -> None:
        """Copy the vertex custom-string ID into the ``name`` property for any
        ``__Entity__`` node whose ``name`` is not yet set.

        Uses the HugeGraph openCypher endpoint via :meth:`_cypher_request`.
        """
        self._cypher_request(
            "MATCH (n:__Entity__) WHERE n.name IS NULL OR n.name = '' "
            "SET n.name = toString(id(n))"
        )
        logger.debug("HugeGraph: normalize_entity_names complete")


__all__ = ["HugeGraphAdapter", "HUGEGRAPH_AVAILABLE"]
