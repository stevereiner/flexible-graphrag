"""graph_view.py (Graph tab): store rows -> {nodes, edges}. Pure unit tests, fake stores."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "flexible-graphrag"))

import graph_view  # noqa: E402


class FakeStore:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def structured_query(self, query, param_map=None):
        self.calls.append((query, param_map))
        return self.rows


def li_system(kind, rows):
    store = FakeStore(rows)
    system = SimpleNamespace(
        config=SimpleNamespace(pg_graph_db=kind),
        graph_index=SimpleNamespace(property_graph_store=store),
        pg_adapter=SimpleNamespace(is_langchain=lambda: False),
    )
    return system, store


def row(a, rel, b, doc, a_labels=("__Entity__", "PERSON"), b_labels=("__Entity__", "ORG"), r_props=None):
    return {"a_id": a, "a_name": a, "a_labels": list(a_labels), "a_props": {"name": a, "embedding": [0.1] * 64},
            "rel": rel, "r_props": r_props or {"doc_id": doc},
            "b_id": b, "b_name": b, "b_labels": list(b_labels), "b_props": {"name": b},
            "doc_id": doc}


def test_neo4j_subgraph_shape_types_and_no_embeddings():
    system, store = li_system("neo4j", [row("Ann", "WORKS_FOR", "Acme", "c:doc1"),
                                        row("Bob", "WORKS_FOR", "Acme", "c:doc1")])
    g = graph_view.subgraph(system, ["c:doc1"])
    assert g["store"] == "neo4j" and not g["truncated"]
    assert {n["id"] for n in g["nodes"]} == {"Ann", "Bob", "Acme"}
    types = {n["id"]: n["type"] for n in g["nodes"]}
    assert types == {"Ann": "PERSON", "Bob": "PERSON", "Acme": "ORG"}
    assert all("embedding" not in n["properties"] for n in g["nodes"])
    assert g["edges"][0]["doc_ids"] == ["c:doc1"]
    query, params = store.calls[0]
    assert params == {"doc_ids": ["c:doc1"]} and "$doc_ids" in query
    assert "{.*, embedding: null}" in query  # Neo4j leaves vectors in the store


def test_document_metadata_sent_once_not_on_every_element():
    meta = {"doc_id": "c:doc1", "file_name": "a.txt", "file_path": "/x/a.txt", "nuxeo_id": "n1",
            "source": "nuxeo", "job_id": "j", "triplet_source_id": "t"}
    r = row("Ann", "HAS_SKILL", "Python", "c:doc1", r_props=dict(meta, PROFICIENCY_LEVEL="expert"))
    r["a_props"] = dict(meta, name="Ann", id="Ann", role="lead")
    system, _ = li_system("neo4j", [r])
    g = graph_view.subgraph(system, ["c:doc1"])
    assert g["edges"][0]["properties"] == {"PROFICIENCY_LEVEL": "expert"}
    assert {n["id"]: n["properties"] for n in g["nodes"]}["Ann"] == {"role": "lead"}
    assert g["documents"] == {"c:doc1": {"file_name": "a.txt", "file_path": "/x/a.txt",
                                         "nuxeo_id": "n1", "source": "nuxeo"}}


def test_rows_outside_scope_and_structural_edges_dropped():
    system, _ = li_system("memgraph", [row("Ann", "WORKS_FOR", "Acme", "c:other"),
                                       row("Ann", "MENTIONS", "Acme", "c:doc1"),
                                       row("Ann", "KNOWS", "Bob", "c:doc1")])
    g = graph_view.subgraph(system, ["c:doc1"])
    assert [e["type"] for e in g["edges"]] == ["KNOWS"]


def test_same_fact_from_two_documents_is_one_edge_with_both_doc_ids():
    system, _ = li_system("neo4j", [row("Ann", "WORKS_FOR", "Acme", "c:doc1"),
                                    row("Ann", "WORKS_FOR", "Acme", "c:doc2")])
    g = graph_view.subgraph(system, ["c:doc1", "c:doc2"])
    assert len(g["edges"]) == 1 and g["edges"][0]["doc_ids"] == ["c:doc1", "c:doc2"]


def test_limit_truncates():
    rows = [row(f"P{i}", "KNOWS", f"Q{i}", "c:d") for i in range(10)]
    system, store = li_system("neo4j", rows)
    g = graph_view.subgraph(system, ["c:d"], limit=3)
    assert len(g["edges"]) == 3 and g["truncated"]
    assert "LIMIT 4" in store.calls[0][0]  # one more than asked, to know it was cut


def test_neighbors_passes_node_id_as_parameter():
    system, store = li_system("falkordb", [row("Ann", "KNOWS", "Bob", "c:d")])
    graph_view.neighbors(system, "Ann", ["c:d"])
    query, params = store.calls[0]
    assert params["node_id"] == "Ann" and "$node_id" in query


def test_arcadedb_quotes_ids_into_the_text():
    system, store = li_system("arcadedb", [])
    evil = "x' OR 1=1 //"
    graph_view.neighbors(system, evil, ["c:it's"])
    query, params = store.calls[0]
    assert params is None
    assert "'c:it\\'s'" in query and "'x\\' OR 1=1 //'" in query


def test_ladybug_type_from_label_column():
    system, _ = li_system("ladybug", [{"a_id": "1", "a_name": "Ann", "a_labels": "PERSON", "rel": "KNOWS",
                                       "b_id": "2", "b_name": "Bob", "b_labels": "PERSON", "doc_id": "c:d"}])
    g = graph_view.subgraph(system, ["c:d"])
    assert {n["label"]: n["type"] for n in g["nodes"]} == {"Ann": "PERSON", "Bob": "PERSON"}


def test_generic_labels_fall_back_to_entity():
    system, _ = li_system("neo4j", [row("Ann", "KNOWS", "Bob", "c:d", a_labels=("__Entity__", "__Node__"))])
    g = graph_view.subgraph(system, ["c:d"])
    assert {n["id"]: n["type"] for n in g["nodes"]}["Ann"] == "Entity"


def test_no_doc_ids_no_query():
    system, store = li_system("neo4j", [])
    assert graph_view.subgraph(system, [])["nodes"] == [] and store.calls == []


def test_capabilities():
    system, _ = li_system("neo4j", [])
    assert graph_view.capabilities(system)["subgraph"] is True
    system, _ = li_system("none", [])
    assert graph_view.capabilities(system)["subgraph"] is False
    system, _ = li_system("spanner", [])
    assert graph_view.capabilities(system)["subgraph"] is True


def test_job_doc_ids_prefers_stable_metadata_id():
    docs = [SimpleNamespace(metadata={"doc_id": "c:a"}, doc_id="uuid-1"),
            SimpleNamespace(metadata={}, doc_id="uuid-2"),
            SimpleNamespace(metadata={"doc_id": "c:a"}, doc_id="uuid-3")]
    assert graph_view.job_doc_ids(docs) == ["c:a", "uuid-2"]


class ChunkStore(FakeStore):
    """Answers the chunk query (MENTIONS) and the fact query differently."""

    def __init__(self, facts, chunks):
        super().__init__(facts)
        self.chunks = chunks

    def structured_query(self, query, param_map=None):
        self.calls.append((query, param_map))
        return self.chunks if ":MENTIONS]" in query else self.rows


def chunk_row(cid, text, entity, doc, labels=("__Entity__", "PERSON")):
    return {"c_id": cid, "c_text": text, "doc_id": doc, "e_id": entity, "e_name": entity,
            "e_labels": list(labels), "e_props": {"name": entity, "embedding": [0.1] * 64}}


def chunk_system(facts, chunks, kind="neo4j"):
    system, _ = li_system(kind, [])
    store = ChunkStore(facts, chunks)
    system.graph_index.property_graph_store = store
    return system, store


def test_chunks_only_when_asked():
    system, store = chunk_system([row("Ann", "KNOWS", "Bob", "c:d")], [chunk_row("k1", "Ann knows Bob.", "Ann", "c:d")])
    g = graph_view.subgraph(system, ["c:d"])
    # the fact query + the co-mentioned facts query; no chunk-node query
    assert all(n.get("kind") != "chunk" for n in g["nodes"])
    assert len(store.calls) == 2 and not any("c_text" in q for q, _ in store.calls)


def test_chunks_and_mentions():
    long_text = "Ann Lee knows Bob. " * 400
    system, store = chunk_system(
        [row("Ann", "KNOWS", "Bob", "c:d")],
        [chunk_row("k1", long_text, "Ann", "c:d"), chunk_row("k1", long_text, "Bob", "c:d"),
         chunk_row("k1", long_text, "Cy", "c:d"),  # only mentioned: no fact, still shown
         chunk_row("k9", "other doc", "Ann", "c:other")])
    g = graph_view.subgraph(system, ["c:d"], include_chunks=True)
    chunks = [n for n in g["nodes"] if n.get("kind") == "chunk"]
    assert [c["id"] for c in chunks] == ["chunk:k1"] and chunks[0]["type"] == "Chunk"
    assert chunks[0]["label"].startswith("Ann Lee knows Bob.") and len(chunks[0]["label"]) <= 40
    assert len(chunks[0]["properties"]["text"]) == graph_view.CHUNK_TEXT_MAX
    mentions = [e for e in g["edges"] if e.get("kind") == "mention"]
    assert {e["target"] for e in mentions} == {"Ann", "Bob", "Cy"}
    assert {n["id"] for n in g["nodes"]} == {"chunk:k1", "Ann", "Bob", "Cy"}
    assert all("embedding" not in n["properties"] for n in g["nodes"])
    query, params = store.calls[1]
    assert "c.ref_doc_id IN $doc_ids" in query and params == {"doc_ids": ["c:d"]}


def test_expand_a_chunk_asks_only_for_its_mentions():
    system, store = chunk_system([row("Ann", "KNOWS", "Bob", "c:d")], [chunk_row("k1", "t", "Ann", "c:d")])
    g = graph_view.neighbors(system, "chunk:k1", ["c:d"], include_chunks=True)
    assert len(store.calls) == 1  # no fact query for a chunk
    query, params = store.calls[0]
    assert params["chunk_id"] == "k1" and "c.id = $chunk_id" in query
    assert {e["type"] for e in g["edges"]} == {"MENTIONS"}


def test_chunk_failure_keeps_the_facts():
    system, store = chunk_system([row("Ann", "KNOWS", "Bob", "c:d")], [])

    def boom(query, param_map=None):
        if ":MENTIONS]" in query:
            raise RuntimeError("no Chunk label")
        return store.rows
    store.structured_query = boom
    g = graph_view.subgraph(system, ["c:d"], include_chunks=True)
    assert [e["type"] for e in g["edges"]] == ["KNOWS"]


def test_capabilities_chunks():
    system, _ = li_system("neo4j", [])
    assert graph_view.capabilities(system)["chunks"] is True
    system, _ = li_system("nebula", [])
    assert graph_view.capabilities(system)["chunks"] is False


def test_prune_keeps_doc_ids_when_documents_dropped():
    from job_retention import prune, public_view
    st = {"status": "completed", "updated_at": "2020-01-01T00:00:00+00:00",
          "documents": [SimpleNamespace(metadata={"doc_id": "c:a"})]}
    status = {"p1": st}
    import os
    os.environ["JOB_RETENTION_MINUTES"] = str(10 ** 8)
    try:
        prune(status)
    finally:
        os.environ.pop("JOB_RETENTION_MINUTES")
    assert "documents" not in st and st["doc_ids"] == ["c:a"]
    assert "doc_ids" not in public_view(st)
