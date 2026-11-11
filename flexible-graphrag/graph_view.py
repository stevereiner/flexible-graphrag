"""The Graph tab's data: the property-graph subgraph of a set of documents, as plain nodes + edges.

planning/Graph Tab/GRAPH-TAB-PLAN.md. main.py resolves a scope / processing job / doc-id list to the
doc ids the asker may read; this module asks the property graph store for the relationships
extracted from those documents and returns one shape for every store::

    {"nodes": [{"id", "label", "type", "properties"[, "kind": "chunk"]}],
     "edges": [{"id", "source", "target", "type", "properties", "doc_ids"[, "kind": "mention"]}],
     "documents": {doc_id: metadata}, "truncated": bool, "store": str}

With ``include_chunks`` the chunks of those documents come too (LangChain's source "Document"
nodes are chunks as well), with their MENTIONS edges to the entities extracted from them.

A relationship belongs to a document the way scope_filter.py already decides it for scoped
questions (relationships carry the doc id; entities are shared, so never scope by an entity's).
Read-only, and no query text ever comes from the caller: doc ids and node ids go in as
parameters, or quoted for the stores that take none.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Labels every entity has (or chunk / document labels): never a node's type
_GENERIC_LABELS = {"__entity__", "__node__", "entity", "entity__", "props__", "node",
                   "__chunk__", "chunk", "document", "__document__", "base"}
# Relationship types that tie a chunk / document to its entities, not facts
_STRUCTURAL_RELS = {"MENTIONS", "HAS_CHUNK", "SOURCE", "PART_OF_DOCUMENT"}
# Properties never sent to the browser
_DROP_PROPS = {"embedding", "text_embedding", "vector", "_node_content"}
# The source document's metadata, which the pipeline copies onto every entity and relationship:
# sent once per document (``documents``), not on each node / edge. Plus any *_id and file_* key.
_DOC_META = {"source", "modified_at", "created_at", "creation_date", "last_modified_date",
             "last_modified", "content_type", "mime_type", "conversion_method", "format_used",
             "llamaparse_tier", "total_pages", "page_count", "page_label", "stable_file_path",
             "path", "url", "size", "parser", "title", "author", "document_title"}
# Provenance links: kept off the properties (the edge's doc_ids says it)
_LINK_PROPS = {"doc_id", "ref_doc_id", "triplet_source_id", "document_id", "job_id"}


def _is_doc_meta(key: str) -> bool:
    k = key.lower()
    return k in _DOC_META or k.startswith("file_") or (k.endswith("_id") and k != "id")

_PARAM_CYPHER = {"neo4j", "memgraph", "falkordb", "neptune", "neptune_analytics"}
_LC_CYPHER = {"neo4j", "memgraph", "falkordb", "arcadedb", "apache_age", "hugegraph"}

MAX_LIMIT = 5000
CHUNK_TEXT_MAX = 4000  # characters of a chunk's text sent for the details panel


def store_type(system) -> str:
    v = getattr(getattr(system, "config", None), "pg_graph_db", "")
    return str(getattr(v, "value", v) or "none").lower()


def is_langchain(system) -> bool:
    """The resolved graph backend (LC-only stores are LangChain whatever GRAPH_BACKEND says)."""
    adapter = getattr(system, "pg_adapter", None)
    return adapter is not None and hasattr(adapter, "is_langchain") and adapter.is_langchain()


def capabilities(system) -> Dict[str, Any]:
    """What the Graph tab can show with this deployment's property graph store."""
    store = store_type(system)
    lc = is_langchain(system)
    if store == "none" or system is None:
        ok, typed = False, False
    elif lc:
        ok = True
        typed = store in _LC_CYPHER or store == "tigergraph"  # TigerGraph: _lc_entity_types
    else:
        ok = getattr(system, "graph_index", None) is not None
        typed = store in _PARAM_CYPHER or store in ("arcadedb", "ladybug", "spanner")
    chunks = ok and ((lc and store in _LC_CYPHER) or
                     (not lc and (store in _PARAM_CYPHER or store in ("arcadedb", "spanner"))))
    return {"store": store, "backend": "langchain" if lc else "llamaindex",
            "subgraph": ok, "neighbors": ok, "types": typed, "chunks": chunks, "rdf": False}


# ---------------------------------------------------------------- normalizing

def _plain(v: Any) -> Any:
    """Apache AGE returns agtype strings still JSON-quoted."""
    if isinstance(v, str) and len(v) > 1 and v[0] == v[-1] == '"':
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _clean(props: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(the element's own properties, its source document's metadata)."""
    if not isinstance(props, dict):
        return {}, {}
    out, meta = {}, {}
    for k, v in props.items():
        if k in _DROP_PROPS or "embedding" in str(k).lower() or v is None or k in _LINK_PROPS:
            continue
        if isinstance(v, (list, tuple)) and len(v) > 32 and all(isinstance(x, (int, float)) for x in v[:8]):
            continue  # an unnamed vector
        v = v if isinstance(v, (str, int, float, bool)) else _jsonable(v)
        (meta if _is_doc_meta(str(k)) else out)[k] = v
    return out, meta


def _jsonable(v: Any) -> Any:
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)


def _type_of(labels: Any, props: Dict[str, Any]) -> str:
    for lab in (labels if isinstance(labels, (list, tuple)) else [labels] if labels else []):
        lab = _plain(lab)
        if lab and str(lab).lower() not in _GENERIC_LABELS:
            return str(lab)
    for k in ("label", "type", "entity_type"):
        v = props.get(k)
        if isinstance(v, str) and v and v.lower() not in _GENERIC_LABELS:
            return v
    return "Entity"


class _Graph:
    """Collects (a, rel, b, doc_id) rows into nodes + edges, at most ``limit`` edges."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[str, Dict[str, Any]] = {}
        self.documents: Dict[str, Dict[str, Any]] = {}  # doc id -> its metadata, once
        self.truncated = False
        self.mentions = 0

    def _doc(self, doc_id: Any, meta: Dict[str, Any], props: Any = None) -> None:
        # An element found through another document's chunk carries its owner's file metadata
        owner = _plain(props.get("doc_id") or props.get("ref_doc_id")) if isinstance(props, dict) else None
        if owner is not None and str(owner) != str(doc_id):
            return
        if doc_id and meta:
            d = self.documents.setdefault(str(doc_id), {})
            for k, v in meta.items():
                d.setdefault(k, v)

    def _node(self, end: Dict[str, Any], doc_id: Any) -> Optional[str]:
        nid = _plain(end.get("id")) or _plain(end.get("name"))
        if nid is None or nid == "":
            return None
        nid = str(nid)
        if nid not in self.nodes:
            props, meta = _clean(end.get("props"))
            self._doc(doc_id, meta, end.get("props"))
            name = _plain(end.get("name")) or props.get("name") or nid
            node_type = _type_of(end.get("labels"), props)
            for k in ("id", "name"):
                props.pop(k, None)
            self.nodes[nid] = {"id": nid, "label": str(name), "type": node_type, "properties": props}
        return nid

    def add(self, a: Dict[str, Any], rel: Any, b: Dict[str, Any], doc_id: Any,
            rel_props: Any = None) -> None:
        rel = str(_plain(rel) or "RELATED_TO")
        if rel.upper() in _STRUCTURAL_RELS:
            return
        doc_id = _plain(doc_id)
        sa, sb = _plain(a.get("id")) or _plain(a.get("name")), _plain(b.get("id")) or _plain(b.get("name"))
        if sa in (None, "") or sb in (None, ""):
            return
        key = f"{sa}|{rel}|{sb}"
        edge = self.edges.get(key)
        if edge is None:
            if len(self.edges) >= self.limit:
                self.truncated = True
                return
            source, target = self._node(a, doc_id), self._node(b, doc_id)
            props, meta = _clean(rel_props)
            edge = self.edges[key] = {"id": key, "source": source, "target": target, "type": rel,
                                      "properties": props, "doc_ids": []}
        else:
            meta = _clean(rel_props)[1]
        self._doc(doc_id, meta, rel_props)
        if doc_id and doc_id not in edge["doc_ids"]:
            edge["doc_ids"].append(str(doc_id))

    def mention(self, chunk_id: Any, text: Any, entity: Dict[str, Any], doc_id: Any) -> None:
        """A chunk and its MENTIONS edge to an entity; at most ``limit`` of these, apart from facts."""
        cid, doc_id = _plain(chunk_id), _plain(doc_id)
        if cid in (None, ""):
            return
        cid = f"chunk:{cid}"  # never the same id as an entity
        if cid not in self.nodes:
            text = str(_plain(text) or "")
            preview = " ".join(text.split())[:40]
            self.nodes[cid] = {"id": cid, "label": preview or "chunk", "type": "Chunk", "kind": "chunk",
                               "properties": {"text": text[:CHUNK_TEXT_MAX]}, "doc_ids": []}
        chunk = self.nodes[cid]
        if doc_id and str(doc_id) not in chunk["doc_ids"]:
            chunk["doc_ids"].append(str(doc_id))
        if self.mentions >= self.limit:
            self.truncated = True
            return
        eid = self._node(entity, doc_id)
        if eid is None:
            return
        key = f"{cid}|MENTIONS|{eid}"
        if key not in self.edges:
            self.mentions += 1
            self.edges[key] = {"id": key, "source": cid, "target": eid, "type": "MENTIONS",
                               "kind": "mention", "properties": {},
                               "doc_ids": [str(doc_id)] if doc_id else []}

    def result(self, store: str) -> Dict[str, Any]:
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values()),
                "documents": self.documents, "truncated": self.truncated, "store": store}


# ---------------------------------------------------------------- store queries

def _quoted(ids: Iterable[str], quote: str = "'") -> str:
    q = quote
    return "[%s]" % ", ".join(q + str(d).replace("\\", "\\\\").replace(q, "\\" + q) + q for d in ids)


def _end(r: Dict[str, Any], p: str) -> Dict[str, Any]:
    return {"id": r.get(f"{p}_id"), "name": r.get(f"{p}_name"), "labels": r.get(f"{p}_labels"),
            "props": r.get(f"{p}_props")}


def _rows(result: Any) -> List[Dict[str, Any]]:
    if isinstance(result, dict):  # column-major {col: [values]}
        cols = list(result.keys())
        return [dict(zip(cols, vals)) for vals in zip(*(result[c] or [] for c in cols))]
    return [r for r in (result or []) if isinstance(r, dict) and "error" not in r]


def _li_cypher(store, kind: str, doc_ids: List[str], node_id: Optional[str], limit: int):
    """LlamaIndex Cypher stores: relationships whose doc_id (or ref_doc_id) is in scope, plus
    those between two entities one chunk of a scope document MENTIONS.

    A relationship two documents both produce is stored once, with one document's doc_id
    (Neo4j keeps the first writer's, the others the last's), so by doc_id alone the other
    document's graph misses it. Every chunk MENTIONS the entities extracted from it, and a
    relationship comes from a chunk that mentions both its ends."""
    projection = "{.*, embedding: null}" if kind == "neo4j" else None

    def props(v: str) -> str:
        return f"{v} {projection}" if projection else f"properties({v})"

    returns = (f"RETURN a.id AS a_id, a.name AS a_name, labels(a) AS a_labels, {props('a')} AS a_props, "
               f"type(r) AS rel, {props('r')} AS r_props, "
               f"b.id AS b_id, b.name AS b_name, labels(b) AS b_labels, {props('b')} AS b_props, "
               "doc_id LIMIT %d" % int(limit))
    if kind == "arcadedb":  # no query parameters: the ids go in the text
        ids = _quoted(doc_ids)
        node = ""
        if node_id is not None:
            nid = _quoted([node_id])[1:-1]
            node = f" AND (a.id = {nid} OR b.id = {nid})"
        params = None
        queries = [
            f"MATCH (a)-[r]->(b) WHERE (r.doc_id IN {ids} OR r.ref_doc_id IN {ids}){node} "
            "WITH a, r, b, coalesce(r.doc_id, r.ref_doc_id) AS doc_id " + returns,
            f"MATCH (c)-[:MENTIONS]->(a)-[r]->(b)<-[:MENTIONS]-(c) WHERE c.ref_doc_id IN {ids}{node} "
            "WITH DISTINCT a, r, b, c.ref_doc_id AS doc_id " + returns,
        ]
    else:
        node = ""
        params = {"doc_ids": doc_ids}
        if node_id is not None:
            node = " AND (a.id = $node_id OR b.id = $node_id)"
            params["node_id"] = node_id
        queries = [
            "MATCH (a:__Entity__)-[r]->(b:__Entity__) "
            f"WHERE (r.doc_id IN $doc_ids OR r.ref_doc_id IN $doc_ids){node} "
            "WITH a, r, b, coalesce(r.doc_id, r.ref_doc_id) AS doc_id " + returns,
            "MATCH (c:Chunk)-[:MENTIONS]->(a:__Entity__)-[r]->(b:__Entity__)<-[:MENTIONS]-(c) "
            f"WHERE c.ref_doc_id IN $doc_ids{node} "
            "WITH DISTINCT a, r, b, c.ref_doc_id AS doc_id " + returns,
        ]
    out = []
    for i, query in enumerate(queries):
        try:
            rows = store.structured_query(query, param_map=params) if params else store.structured_query(query)
        except Exception as e:
            if i == 0:
                raise
            logger.info(f"[graph view({kind})] relationships via chunk mentions not available: {e}")
            break
        out += [(_end(r, "a"), r.get("rel"), _end(r, "b"), r.get("doc_id"), r.get("r_props")) for r in _rows(rows)]
    return out


def _li_ladybug(store, doc_ids, node_id, limit):
    # Kuzu dialect: relationships carry the id of the chunk they came from, chunks the doc id;
    # an entity's type is its `label` column
    where = "r.triplet_source_id = c.id"
    params = {"doc_ids": doc_ids}
    if node_id is not None:
        where += " AND (a.id = $node_id OR b.id = $node_id)"
        params["node_id"] = node_id
    returns = ("RETURN DISTINCT a.id AS a_id, a.name AS a_name, a.label AS a_labels, "
               "b.id AS b_id, b.name AS b_name, b.label AS b_labels, r.label AS rel, "
               f"c.ref_doc_id AS doc_id LIMIT {int(limit)}")
    node = " AND (a.id = $node_id OR b.id = $node_id)" if node_id is not None else ""
    out = []
    # A relationship keeps one chunk id (the last writer's); one another document also
    # produces is found through that document's chunk mentioning both its ends (see _li_cypher)
    for query in ("MATCH (c:Chunk) WHERE c.ref_doc_id IN $doc_ids "
                  f"MATCH (a)-[r]->(b) WHERE {where} " + returns,
                  "MATCH (c:Chunk)-[:MENTIONS]->(a), (c)-[:MENTIONS]->(b), (a)-[r]->(b) "
                  f"WHERE c.ref_doc_id IN $doc_ids{node} " + returns):
        rows = store.structured_query(query, param_map=params)
        out += [(_end(r, "a"), r.get("rel"), _end(r, "b"), r.get("doc_id"), None) for r in _rows(rows)]
    return out


def _li_nebula(store, doc_ids, node_id, limit):
    rows = store.structured_query(
        "MATCH (a:`Entity__`)-[r:`Relation__`]->(b:`Entity__`) WHERE r.doc_id IN $doc_ids "
        "RETURN a.Entity__.name AS a_name, r.label AS rel, b.Entity__.name AS b_name, "
        f"r.doc_id AS doc_id LIMIT {int(limit)}",
        param_map={"doc_ids": doc_ids})
    out = [({"name": r.get("a_name")}, r.get("rel"), {"name": r.get("b_name")}, r.get("doc_id"), None)
           for r in _rows(rows)]
    try:  # plus those between two entities one chunk of a scope document MENTIONS (see _li_cypher)
        rows = store.structured_query(
            "MATCH (c:`Chunk__`)-[:`MENTIONS`]->(a:`Entity__`)-[r:`Relation__`]->(b:`Entity__`)"
            "<-[:`MENTIONS`]-(c) WHERE c.Props__.ref_doc_id IN $doc_ids "
            "RETURN DISTINCT a.Entity__.name AS a_name, r.label AS rel, b.Entity__.name AS b_name, "
            f"c.Props__.ref_doc_id AS doc_id LIMIT {int(limit)}",
            param_map={"doc_ids": doc_ids})
        out += [({"name": r.get("a_name")}, r.get("rel"), {"name": r.get("b_name")}, r.get("doc_id"), None)
                for r in _rows(rows)]
    except Exception as e:
        logger.info(f"[graph view(nebula)] relationships via chunk mentions not available: {e}")
    return [f for f in out if node_id is None or node_id in (f[0]["name"], f[2]["name"])]


# Spanner Graph (GQL, llama-index-spanner's flexible schema): one node and one edge table, the
# entity / relationship type in a `label` column, everything else in a JSON `properties` column
def _spanner_end(r: Dict[str, Any], p: str) -> Dict[str, Any]:
    props = r.get(f"{p}_props")
    try:
        props = json.loads(props) if isinstance(props, str) else props
    except ValueError:
        props = None
    return {"id": r.get(f"{p}_id"), "name": r.get(f"{p}_name"),
            "labels": [r.get(f"{p}_label")] if r.get(f"{p}_label") else None, "props": props}


def _li_spanner(store, doc_ids, node_id, limit):
    """As _li_cypher: relationships whose doc_id is in scope, plus those between two entities
    one chunk of a scope document MENTIONS (llamaindex/graph/relation_mentions.py)."""
    node = " AND (a.id = @node_id OR b.id = @node_id)" if node_id is not None else ""
    params = {"doc_ids": list(doc_ids)}
    if node_id is not None:
        params["node_id"] = node_id
    returns = ("a.id AS a_id, a.name AS a_name, a.label AS a_label, TO_JSON_STRING(a.properties) AS a_props, "
               "r.label AS rel, TO_JSON_STRING(r.properties) AS r_props, "
               "b.id AS b_id, b.name AS b_name, b.label AS b_label, TO_JSON_STRING(b.properties) AS b_props")
    queries = [
        "MATCH (a)-[r]->(b) WHERE r.label <> 'MENTIONS' AND "
        "(JSON_VALUE(r.properties.doc_id) IN UNNEST(@doc_ids) OR JSON_VALUE(r.properties.ref_doc_id) IN UNNEST(@doc_ids))"
        f"{node} RETURN {returns}, COALESCE(JSON_VALUE(r.properties.doc_id), JSON_VALUE(r.properties.ref_doc_id)) "
        f"AS doc_id LIMIT {int(limit)}",
        "MATCH (c)-[m1]->(a), (c)-[m2]->(b), (a)-[r]->(b) WHERE m1.label = 'MENTIONS' AND m2.label = 'MENTIONS' "
        f"AND r.label <> 'MENTIONS' AND JSON_VALUE(c.properties.ref_doc_id) IN UNNEST(@doc_ids){node} "
        f"RETURN DISTINCT {returns}, JSON_VALUE(c.properties.ref_doc_id) AS doc_id LIMIT {int(limit)}",
    ]
    out = []
    for i, query in enumerate(queries):
        try:
            rows = store.structured_query(query, param_map=params)
        except Exception as e:
            if i == 0:
                raise
            logger.info(f"[graph view(spanner)] relationships via chunk mentions not available: {e}")
            break
        out += [(_spanner_end(r, "a"), r.get("rel"), _spanner_end(r, "b"), r.get("doc_id"),
                 _spanner_end(r, "r")["props"]) for r in _rows(rows)]
    return out


def _li_rows(system, doc_ids, node_id, limit):
    store = system.graph_index.property_graph_store
    kind = store_type(system)
    if kind in _PARAM_CYPHER or kind == "arcadedb":
        return _li_cypher(store, kind, doc_ids, node_id, limit)
    if kind == "ladybug":
        return _li_ladybug(store, doc_ids, node_id, limit)
    if kind == "nebula":
        return _li_nebula(store, doc_ids, node_id, limit)
    if kind == "spanner":
        return _li_spanner(store, doc_ids, node_id, limit)
    raise NotImplementedError(f"the Graph tab does not support PG_GRAPH_DB={kind} yet")


def _lc_rows(system, doc_ids, node_id, limit):
    """LangChain graph backend: no doc id on relationships, so (as scope_filter.py does) the
    relationships between entities a scope document's source node MENTIONS. Cypher stores also
    give the entities' labels; every other store gives names only (one colour in the viewer)."""
    kind = store_type(system)
    adapter = getattr(system, "pg_adapter", None)
    graph = adapter.get_lc_graph() if adapter is not None else None
    if graph is None:
        return []
    if kind in _LC_CYPHER and not hasattr(getattr(adapter, "_store_adapter", None), "scoped_facts"):
        ids = _quoted(doc_ids)
        node = ""
        if node_id is not None:
            nid = _quoted([node_id])[1:-1]
            node = f"AND (coalesce(a.name, a.id) = {nid} OR coalesce(b.name, b.id) = {nid}) "
        try:
            rows = graph.query(
                f"MATCH (d)-[:MENTIONS]->(a) WHERE d.ref_doc_id IN {ids} OR d.doc_id IN {ids} "
                f"MATCH (d)-[:MENTIONS]->(b) MATCH (a)-[r]->(b) WHERE true {node}"
                "RETURN coalesce(a.name, a.id) AS a_id, labels(a) AS a_labels, "
                "type(r) AS rel, coalesce(b.name, b.id) AS b_id, labels(b) AS b_labels, "
                f"coalesce(d.ref_doc_id, d.doc_id) AS doc_id LIMIT {int(limit)}")
            if rows and isinstance(rows[0], (list, tuple)):  # FalkorDBGraph: rows as lists
                cols = ("a_id", "a_labels", "rel", "b_id", "b_labels", "doc_id")
                rows = [dict(zip(cols, r)) for r in rows]
            out = [(_end(r, "a"), r.get("rel"), _end(r, "b"), r.get("doc_id"), None) for r in _rows(rows)]
            if out:
                return out
        except Exception as e:  # labels() and friends vary by store: fall back to names only
            logger.info(f"[graph view({kind})] typed query failed, names only: {e}")
    from scope_filter import ScopedLCGraphRetriever
    facts = ScopedLCGraphRetriever(system, doc_ids)._rows()
    types = _lc_entity_types(system, kind, {v for s, _, o, _ in facts for v in (s, o)})
    out = [({"id": s, "labels": types.get(s)}, rel, {"id": o, "labels": types.get(o)}, d, None)
           for s, rel, o, d in facts]
    return [f for f in out if node_id is None or node_id in (f[0]["id"], f[2]["id"])][:limit]


def _lc_entity_types(system, kind: str, ids) -> Dict[str, List[str]]:
    """{entity id: [type]} for stores whose relationship rows carry no type: TigerGraph keeps it
    in the vertex's node_type attribute. Empty (one colour) for any other store or on failure."""
    if kind != "tigergraph" or not ids:
        return {}
    try:
        adapter = getattr(system, "pg_adapter", None)
        conn = getattr(adapter.get_lc_graph(), "conn", None) if adapter is not None else None
        if conn is None:
            return {}
        out: Dict[str, List[str]] = {}
        ids = sorted(str(i) for i in ids if i not in (None, ""))
        for i in range(0, len(ids), 200):
            for v in conn.getVerticesById("__Entity__", ids[i:i + 200]) or []:
                t = (v.get("attributes") or {}).get("node_type")
                if t:
                    out[str(v.get("v_id"))] = [t]
        return out
    except Exception as e:
        logger.info(f"[graph view(tigergraph)] entity types not available: {e}")
        return {}


def _chunk_rows(system, doc_ids: List[str], node_id: Optional[str], limit: int):
    """(chunk id, chunk text, entity end, doc id) for the chunks of ``doc_ids`` and the entities
    they MENTION. LlamaIndex: ``Chunk`` nodes with ``ref_doc_id``; LangChain: the source
    "Document" nodes (one per chunk). ``node_id`` = a chunk ("chunk:<id>") or an entity."""
    kind = store_type(system)
    chunk_id = node_id[len("chunk:"):] if node_id and node_id.startswith("chunk:") else None
    entity_id = node_id if node_id and chunk_id is None else None
    if is_langchain(system):
        if kind not in _LC_CYPHER:
            return []
        adapter = getattr(system, "pg_adapter", None)
        graph = adapter.get_lc_graph() if adapter is not None else None
        if graph is None:
            return []
        ids = _quoted(doc_ids)
        where = f"(d.ref_doc_id IN {ids} OR d.doc_id IN {ids})"
        if chunk_id is not None:
            where += f" AND d.id = {_quoted([chunk_id])[1:-1]}"
        if entity_id is not None:
            where += f" AND coalesce(e.name, e.id) = {_quoted([entity_id])[1:-1]}"
        rows = graph.query(
            f"MATCH (d)-[:MENTIONS]->(e) WHERE {where} "
            "RETURN d.id AS c_id, d.text AS c_text, coalesce(d.ref_doc_id, d.doc_id) AS doc_id, "
            f"coalesce(e.name, e.id) AS e_id, labels(e) AS e_labels LIMIT {int(limit)}")
    elif kind == "spanner":
        store = system.graph_index.property_graph_store
        where, params = "m.label = 'MENTIONS' AND JSON_VALUE(c.properties.ref_doc_id) IN UNNEST(@doc_ids)",             {"doc_ids": list(doc_ids)}
        if chunk_id is not None:
            where += " AND c.id = @chunk_id"
            params["chunk_id"] = chunk_id
        if entity_id is not None:
            where += " AND e.id = @node_id"
            params["node_id"] = entity_id
        rows = store.structured_query(
            f"MATCH (c)-[m]->(e) WHERE {where} RETURN c.id AS c_id, c.text AS c_text, "
            "JSON_VALUE(c.properties.ref_doc_id) AS doc_id, e.id AS e_id, e.name AS e_name, "
            f"e.label AS e_label, TO_JSON_STRING(e.properties) AS e_props LIMIT {int(limit)}", param_map=params)
        return [(r.get("c_id"), r.get("c_text"), _spanner_end(r, "e"), r.get("doc_id")) for r in _rows(rows)]
    else:
        if not (kind in _PARAM_CYPHER or kind == "arcadedb"):
            return []
        store = system.graph_index.property_graph_store
        if kind == "arcadedb":
            where = f"c.ref_doc_id IN {_quoted(doc_ids)}"
            if chunk_id is not None:
                where += f" AND c.id = {_quoted([chunk_id])[1:-1]}"
            if entity_id is not None:
                where += f" AND e.id = {_quoted([entity_id])[1:-1]}"
            match, params = "MATCH (c)-[:MENTIONS]->(e)", None
        else:
            where, params = "c.ref_doc_id IN $doc_ids", {"doc_ids": doc_ids}
            if chunk_id is not None:
                where += " AND c.id = $chunk_id"
                params["chunk_id"] = chunk_id
            if entity_id is not None:
                where += " AND e.id = $node_id"
                params["node_id"] = entity_id
            match = "MATCH (c:Chunk)-[:MENTIONS]->(e:__Entity__)"
        e_props = "e {.*, embedding: null}" if kind == "neo4j" else "properties(e)"
        query = (f"{match} WHERE {where} "
                 "RETURN c.id AS c_id, c.text AS c_text, c.ref_doc_id AS doc_id, "
                 f"e.id AS e_id, e.name AS e_name, labels(e) AS e_labels, {e_props} AS e_props "
                 f"LIMIT {int(limit)}")
        rows = store.structured_query(query, param_map=params) if params else store.structured_query(query)
    return [(r.get("c_id"), r.get("c_text"), _end(r, "e"), r.get("doc_id")) for r in _rows(rows)]


def _query(system, doc_ids: List[str], node_id: Optional[str], limit: int,
           include_chunks: bool = False) -> Dict[str, Any]:
    kind = store_type(system)
    graph = _Graph(limit)
    if not doc_ids or kind == "none":
        return graph.result(kind)
    scope = set(doc_ids)
    if not (node_id or "").startswith("chunk:"):  # a chunk has no facts of its own, only mentions
        rows = (_lc_rows if is_langchain(system) else _li_rows)(system, list(doc_ids), node_id, limit + 1)
        for a, rel, b, doc_id, rel_props in rows:
            if doc_id is None or _plain(doc_id) in scope:
                graph.add(a, rel, b, doc_id, rel_props)
    if include_chunks:
        try:
            for cid, text, entity, doc_id in _chunk_rows(system, list(doc_ids), node_id, limit + 1):
                if doc_id is None or _plain(doc_id) in scope:
                    graph.mention(cid, text, entity, doc_id)
        except Exception as e:  # chunks are extra: the facts still show
            logger.warning(f"[graph view({kind})] chunks not available: {e}")
    logger.info(f"[graph view({kind})] {len(graph.nodes)} node(s), {len(graph.edges)} edge(s) "
                f"from {len(scope)} document(s){' (truncated)' if graph.truncated else ''}")
    return graph.result(kind)


def subgraph(system, doc_ids: Iterable[str], limit: int = 500, include_chunks: bool = False) -> Dict[str, Any]:
    """Every relationship extracted from ``doc_ids`` (at most ``limit``) and its two entities;
    with ``include_chunks`` also the chunks and what they mention (another ``limit``)."""
    return _query(system, sorted(set(doc_ids)), None, max(1, min(int(limit), MAX_LIMIT)), include_chunks)


def neighbors(system, node_id: str, doc_ids: Iterable[str], limit: int = 100,
              include_chunks: bool = False) -> Dict[str, Any]:
    """The relationships touching ``node_id`` (an entity, or a "chunk:<id>") extracted from
    ``doc_ids``, and their other ends."""
    return _query(system, sorted(set(doc_ids)), str(node_id), max(1, min(int(limit), MAX_LIMIT)),
                  include_chunks)


def job_doc_ids(documents: Iterable[Any]) -> List[str]:
    """The stable doc ids of a processing job's documents (PROCESSING_STATUS 'documents')."""
    out: List[str] = []
    for d in documents or []:
        meta = getattr(d, "metadata", None) or {}
        did = meta.get("doc_id") or getattr(d, "doc_id", None) or getattr(d, "id_", None)
        if did and did not in out:
            out.append(str(did))
    return out
