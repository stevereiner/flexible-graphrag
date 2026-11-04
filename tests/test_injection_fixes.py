"""Regression tests for the October 2026 security reports.

- GHSA-2558-gvg9-whcx: /api/ingest filesystem ``paths`` must stay inside allowed folders
- GHSA-g8hp-rhg7-hff5 (+ 8w73-f3gx-g6f8, 77xm-r959-mgxf): Memgraph label injection
- GHSA-3c56-jj76-gvhm: Apache AGE label injection + fixed $cypher$ dollar-quote tag
- GHSA-mv9c-5phh-p8xr: ArcadeDB stamp loop label injection
- GHSA-8w73-f3gx-g6f8: Ladybug unquoted labels
- GHSA-pq9f-7m69-2739: Nebula VID escaping in the incremental delete path
- GHSA-fpmj-f9vr-5gh3: RDF numeric literal branches

Pure unit tests: no live backend, no databases.
"""
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "flexible-graphrag"))

from langchain.graph.pg_store_adapters._graph_docs import (  # noqa: E402
    bare_ident,
    cypher_ident,
    sanitize_graph_types,
)

CYPHER_PAYLOAD = "Entity` {id: $id}) CREATE (:Injected {marker: 'X'}) //"
NEWLINE_PAYLOAD = "E`)\nMATCH(x)DETACH\nDELETE\nx//"


def _bare(cls, **attrs):
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _node(id_, type_, **props):
    return SimpleNamespace(id=id_, type=type_, properties=dict(props))


def _doc(nodes, rels=(), source=None):
    return SimpleNamespace(nodes=list(nodes), relationships=list(rels), source=source)


# ── shared helpers ───────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("payload", [CYPHER_PAYLOAD, NEWLINE_PAYLOAD, "`", " ` "])
def test_cypher_ident_has_no_backtick(payload):
    out = cypher_ident(payload)
    assert "`" not in out and out


@pytest.mark.unit
def test_cypher_ident_keeps_ordinary_labels():
    assert cypher_ident("Person") == "Person"
    assert cypher_ident("Programming Language") == "Programming Language"
    assert cypher_ident(None) == "Entity"


@pytest.mark.unit
@pytest.mark.parametrize("payload", [CYPHER_PAYLOAD, NEWLINE_PAYLOAD, "A B;DROP", "x)-[:R]->(y"])
def test_bare_ident_is_word_chars_only(payload):
    assert re.fullmatch(r"\w+", bare_ident(payload))


@pytest.mark.unit
def test_bare_ident_keeps_ordinary_labels():
    assert bare_ident("Person") == "Person"
    assert bare_ident("WORKS_FOR") == "WORKS_FOR"
    assert bare_ident("__Entity__") == "__Entity__"
    assert bare_ident("3D") == "_3D"
    assert bare_ident("```") == "Entity"


@pytest.mark.unit
def test_sanitize_graph_types_covers_endpoints():
    a, b = _node("a", CYPHER_PAYLOAD), _node("b", "Org`x")
    rel = SimpleNamespace(source=a, target=_node("b", "Org`x"), type="R`) DETACH DELETE x //", properties={})
    doc = _doc([a, b], [rel])
    sanitize_graph_types([doc])
    for t in (a.type, b.type, rel.type, rel.source.type, rel.target.type):
        assert "`" not in t


# ── Memgraph ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("payload", [CYPHER_PAYLOAD, NEWLINE_PAYLOAD])
def test_memgraph_labels_cannot_break_out(payload):
    from langchain.graph.pg_store_adapters.memgraph_adapter import MemgraphAdapter

    queries = []
    graph = SimpleNamespace(query=lambda q, params=None: queries.append(q), refresh_schema=lambda: None)
    a = _bare(MemgraphAdapter, lc_graph=graph)
    src, tgt = _node("s", payload), _node("t", payload)
    rel = SimpleNamespace(source=src, target=tgt, type=payload, properties={})
    a.add_graph_documents([_doc([src, tgt], [rel])])

    lbl = r"`[^`]*`"
    node_q = rf"MERGE \(n:{lbl} \{{id: \$id\}}\) SET n \+= \$props RETURN distinct 'done' AS result"
    rel_q = (rf"MATCH \(a:{lbl} \{{id: \$src_id\}}\), \(b:{lbl} \{{id: \$tgt_id\}}\) "
             rf"MERGE \(a\)-\[r:{lbl}\]->\(b\) SET r \+= \$props RETURN distinct 'done' AS result")
    assert len(queries) == 3
    # the whole payload stays inside one quoted label: the query keeps its exact shape
    assert re.fullmatch(node_q, queries[0], re.S) and re.fullmatch(node_q, queries[1], re.S)
    assert re.fullmatch(rel_q, queries[2], re.S)


# ── Apache AGE ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_age_dollar_quote_tag_not_in_statement():
    pytest.importorskip("psycopg")
    from langchain.graph.pg_store_adapters.apache_age_adapter import _dollar_quote

    body = "MERGE (n:`X` {id: \"a$cypher$) AS (v agtype); DROP TABLE t; --\"})"
    quoted = _dollar_quote(body)
    tag = quoted[: quoted.index("$", 1) + 1]
    assert tag != "$cypher$"
    assert quoted == tag + body + tag
    assert body.count(tag) == 0


@pytest.mark.unit
def test_age_failed_write_rolls_back():
    pytest.importorskip("langchain_age")
    from langchain.graph.pg_store_adapters.apache_age_adapter import _AGEGraphFixed

    events = []

    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, args=None):
            if sql.startswith("SELECT * FROM cypher"):
                raise RuntimeError("label name is invalid")

    conn = SimpleNamespace(cursor=Cur, commit=lambda: events.append("commit"),
                           rollback=lambda: events.append("rollback"))
    g = _bare(_AGEGraphFixed, _conn=conn, graph_name="g")
    with pytest.raises(RuntimeError):
        g._run_write("MERGE (n:Bad)")
    assert events == ["rollback"]


# ── Gremlin / Cosmos ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_gremlin_property_keys_are_escaped():
    pytest.importorskip("gremlin_python")
    from langchain_community.graphs.gremlin_graph import GremlinGraph
    from langchain_community.graphs.graph_document import Node, Relationship
    from langchain.graph.pg_store_adapters.cosmos_gremlin_adapter import CosmosDBGremlinAdapter

    lc = SimpleNamespace(build_vertex_query=lambda n: GremlinGraph.build_vertex_query(None, n),
                         build_edge_query=lambda r: GremlinGraph.build_edge_query(None, r))
    a = _bare(CosmosDBGremlinAdapter, lc_graph=lc)
    a._install_escape_patch()

    key = "k', 'v').addV('Injected').property('m"
    v = lc.build_vertex_query(Node(id="a", type="Person", properties={key: "x"}))
    e = lc.build_edge_query(Relationship(source=Node(id="a", type="P"), target=Node(id="b", type="P"),
                                         type="KNOWS", properties={key: "y"}))
    for q in (v, e):
        # every unescaped quote pairs up: no string ends early
        assert len(re.findall(r"(?<!\\)'", q)) % 2 == 0
        assert ".addV('Injected')" not in q


# ── ArcadeDB ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_arcadedb_stamp_query_uses_clean_label():
    from langchain.graph.pg_store_adapters import arcadedb_lc_adapter as mod

    assert "`" not in mod.cypher_ident(NEWLINE_PAYLOAD)
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "MATCH (n:`{_vtype}`" not in src
    assert "sanitize_graph_types(graph_documents)" in src


# ── Nebula incremental delete ────────────────────────────────────────────────

@pytest.mark.unit
def test_nebula_delete_escapes_backslash_in_vids():
    from incremental_updates.engine import IncrementalUpdateEngine

    issued = []

    class Store:
        def structured_query(self, q):
            issued.append(q)
            if q.startswith("MATCH ()-[r:"):
                return [{"s": "Acme\\", "d": 'x"y', "k": 0}]
            if q.startswith("MATCH (e) WHERE"):
                return [{"i": "Acme\\"}]
            return []

    engine = _bare(IncrementalUpdateEngine, config=SimpleNamespace(pg_graph_db="nebula"), hybrid_system=None)
    index = SimpleNamespace(property_graph_store=Store(), delete_ref_doc=lambda **kw: None)
    assert engine._nebula_graph_delete("doc1", index) is True

    deletes = [q for q in issued if q.startswith("DELETE")]
    assert 'DELETE EDGE `Relation__` "Acme\\\\" -> "x\\"y" @0;' in deletes
    assert 'DELETE VERTEX "Acme\\\\" WITH EDGE;' in deletes


# ── RDF converter ────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("declared", ["integer", "decimal"])
def test_rdf_numeric_branch_escapes_string_values(declared):
    pytest.importorskip("rdflib")
    from rdflib.namespace import XSD
    from rdf.kg_to_rdf_converter import _turtle_literal

    payload = '5"^^<xsd:integer> . <evil/s> <evil/p> "pwned'
    out = _turtle_literal(payload, pred_key="AGE", xsd_type_map={"AGE": str(XSD[declared])})
    # exactly one literal: the only unescaped quotes are the opening and closing ones
    unescaped = re.findall(r'(?<!\\)"', out)
    assert len(unescaped) == 2
    assert out.startswith('"') and "<evil/s>" in out  # still there, but inside the literal


@pytest.mark.unit
def test_rdf_numeric_branch_unchanged_for_numbers():
    pytest.importorskip("rdflib")
    from rdflib.namespace import XSD
    from rdf.kg_to_rdf_converter import _turtle_literal

    assert _turtle_literal(42) == f'"42"^^<{XSD.integer}>'
    assert _turtle_literal(1.5) == f'"1.5"^^<{XSD.decimal}>'


# ── /api/ingest filesystem paths ─────────────────────────────────────────────

@pytest.mark.unit
def test_ingest_paths_outside_allowed_roots_are_refused(tmp_path):
    from main import disallowed_ingest_paths

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "ok.txt").write_text("ok")
    docs = tmp_path / "docs"
    docs.mkdir()
    secret = tmp_path / "outside" / "secret.json"
    secret.parent.mkdir()
    secret.write_text("{}")

    roots = [str(uploads), str(docs)]
    assert disallowed_ingest_paths([str(uploads / "ok.txt"), str(docs)], roots) == []
    assert disallowed_ingest_paths([f'"{uploads / "ok.txt"}"'], roots) == []  # UI-style quoting

    hostile = [
        str(secret),
        str(secret.parent),
        str(uploads / ".." / "outside" / "secret.json"),
        "/etc",
        "C:/Windows/System32",
        "",
        "uploads\x00/../x",
    ]
    assert disallowed_ingest_paths(hostile, roots) == hostile


@pytest.mark.unit
def test_ingest_paths_with_no_roots_refuse_everything(tmp_path):
    from main import disallowed_ingest_paths

    assert disallowed_ingest_paths([str(tmp_path)], []) == [str(tmp_path)]
