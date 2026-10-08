"""Graph stores that keep a link from each fact to its document (scoped questions, removal)."""
import hashlib
import json
from types import SimpleNamespace

from langchain.graph.pg_store_adapters.cosmos_gremlin_adapter import CosmosDBGremlinAdapter
from langchain.graph.pg_store_adapters.surrealdb_adapter import SurrealDBAdapter


def _bare(cls, **attrs):
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def test_surrealdb_scoped_facts_read_every_relation_table():
    calls = []

    class Graph:
        relation_prefix = "relation_"
        get_schema = json.dumps({"nodes": ["graph_Org"], "edges": ["relation_WORKS_FOR", "relation_OWNS"]})

        def query(self, q, params=None):
            calls.append(params)
            if params["t"] == "relation_WORKS_FOR":
                return [{"subj": "Ann", "obj": "Acme", "doc_id": "d1"}]
            return []

    a = _bare(SurrealDBAdapter, lc_graph=Graph())
    assert a.scoped_facts(["d1"]) == [("Ann", "WORKS_FOR", "Acme", "d1")]
    assert [c["t"] for c in calls] == ["relation_WORKS_FOR", "relation_OWNS"]
    assert all(c["ids"] == ["d1"] for c in calls)


def test_surrealdb_write_stamps_the_document_id_on_relations():
    seen = []
    graph = SimpleNamespace(add_graph_documents=lambda docs, include_source=False: seen.extend(docs))
    a = _bare(SurrealDBAdapter, lc_graph=graph)
    node = SimpleNamespace(id="Ann", type="Person", properties={})
    rel = SimpleNamespace(properties={})
    doc = SimpleNamespace(nodes=[node], relationships=[rel],
                          source=SimpleNamespace(metadata={"ref_doc_id": "d1"}))
    a.add_graph_documents([doc], include_source=True)
    assert rel.properties == {"doc_id": "d1"}
    assert node.properties == {"name": "Ann", "type": "Person", "ref_doc_id": "d1"}


def test_gremlin_scoped_facts_map_hashed_ids_back():
    key = hashlib.sha1(b"c1:alfresco://n1").hexdigest()
    sent = []

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return SimpleNamespace(result=lambda: self.rows)

    client = SimpleNamespace(submit=lambda q: (sent.append(q), Result([{"s": "Ann", "r": "WORKS_FOR", "o": "Acme", "d": key}]))[1])
    a = _bare(CosmosDBGremlinAdapter, lc_graph=SimpleNamespace(client=client))
    assert a.scoped_facts(["c1:alfresco://n1"]) == [("Ann", "WORKS_FOR", "Acme", "c1:alfresco://n1")]
    assert key in sent[0] and "has('doc_id', within(" in sent[0]
