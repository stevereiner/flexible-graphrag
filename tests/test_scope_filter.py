"""Unit tests for answering from one document or folder only (scope_filter.py)."""
import asyncio

import pytest
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from scope_filter import ScopedRetriever, _words, li_retriever_scope_kwargs, node_doc_id

pytestmark = pytest.mark.unit

IDS = ["c1:alfresco://n1", "c1:alfresco://n2"]


def _node(doc_id=None, ref=None):
    n = TextNode(text="t", metadata={"doc_id": doc_id} if doc_id else {})
    if ref:
        from llama_index.core.schema import NodeRelationship, RelatedNodeInfo
        n.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=ref)
    return NodeWithScore(node=n, score=1.0)


def test_node_doc_id_prefers_ref_doc_id_then_metadata():
    assert node_doc_id(_node(ref="c1:alfresco://n1")) == "c1:alfresco://n1"
    assert node_doc_id(_node(doc_id="c1:alfresco://n2")) == "c1:alfresco://n2"
    assert node_doc_id(_node()) is None


class _Fixed(BaseRetriever):
    def __init__(self, nodes):
        self._nodes = nodes
        super().__init__()

    def _retrieve(self, query_bundle):
        return list(self._nodes)


def test_scoped_retriever_drops_out_of_scope_and_unattributed_nodes():
    inner = _Fixed([_node(doc_id=IDS[0]), _node(doc_id="c9:alfresco://other"), _node()])
    kept = ScopedRetriever(inner, IDS).retrieve(QueryBundle("q"))
    assert [node_doc_id(n) for n in kept] == [IDS[0]]
    kept = asyncio.run(ScopedRetriever(inner, IDS).aretrieve(QueryBundle("q")))
    assert len(kept) == 1


def test_in_store_filter_kwargs_per_store():
    es = li_retriever_scope_kwargs("elasticsearch", IDS)
    assert es == {"vector_store_kwargs": {"es_filter": [{"terms": {"metadata.doc_id": sorted(IDS)}}]}}
    for store in ("qdrant", "opensearch", "chroma", "postgres", "neo4j"):
        f = li_retriever_scope_kwargs(store, IDS)["filters"].filters[0]
        assert (f.key, sorted(f.value), f.operator.value) == ("doc_id", sorted(IDS), "in")
    assert li_retriever_scope_kwargs("bm25", IDS) == {}  # BM25: a scoped index instead


def test_words_drops_stopwords_and_short_tokens():
    assert _words("Who works for Acme, Inc?") == {"works", "acme", "inc"}


def test_langchain_vector_filters_per_store():
    from scope_filter import lc_vector_scope_kwargs
    ids = ["c1:alfresco://b", "c1:alfresco://a'x"]
    assert lc_vector_scope_kwargs("milvus", ids) == {"expr": 'doc_id in ["c1:alfresco://a\'x", "c1:alfresco://b"]'}
    assert lc_vector_scope_kwargs("lancedb", ids) == {
        "filter": "metadata.doc_id IN ('c1:alfresco://a''x', 'c1:alfresco://b')"}
    for store in ("chroma", "postgres", "neo4j", "pinecone"):
        assert lc_vector_scope_kwargs(store, ids) == {"filter": {"doc_id": {"$in": sorted(ids)}}}
    q = lc_vector_scope_kwargs("qdrant", ids)["filter"]
    assert q.must[0].key == "metadata.doc_id" and sorted(q.must[0].match.any) == sorted(ids)
    assert lc_vector_scope_kwargs("weaviate", ids)["filters"] is not None
    assert lc_vector_scope_kwargs("elasticsearch", ids) == {
        "filter": [{"terms": {"metadata.doc_id.keyword": sorted(ids)}}]}
    assert lc_vector_scope_kwargs("opensearch", ids) == {
        "search_type": "script_scoring", "pre_filter": {"terms": {"metadata.doc_id.keyword": sorted(ids)}}}
    assert lc_vector_scope_kwargs("bm25", ids) == {}


def test_scoped_bm25_indexes_only_the_scope():
    from types import SimpleNamespace
    from scope_filter import scoped_bm25_retriever
    a = TextNode(text="space station orbit", metadata={"doc_id": "d1"})
    b = TextNode(text="cmis content management standard", metadata={"doc_id": "d2"})
    store = SimpleNamespace(_docstore=SimpleNamespace(docs={"a": a, "b": b}))
    r = scoped_bm25_retriever(SimpleNamespace(search_store=store), ["d2"], top_k=5)
    got = r.retrieve("space station cmis")
    assert [n.node.metadata["doc_id"] for n in got] == ["d2"]
    assert scoped_bm25_retriever(SimpleNamespace(search_store=store), ["d9"]) is None


def test_scoped_lc_graph_rows_from_cypher_stores():
    from types import SimpleNamespace
    from scope_filter import ScopedLCGraphRetriever

    class Graph:
        def __init__(self, first, second=None):
            self.calls, self._answers = [], [first, second or []]

        def query(self, q, params=None):
            self.calls.append(q)
            return self._answers[len(self.calls) - 1]

    def system(store, graph):
        adapter = SimpleNamespace(get_lc_graph=lambda: graph)
        return SimpleNamespace(config=SimpleNamespace(pg_graph_db=store), pg_adapter=adapter)

    # Apache AGE: agtype strings come back JSON-quoted
    age = Graph([{"subj": '"Alfresco"', "rel": '"CREATED"', "obj": '"CMIS"', "doc_id": '"d1"'}])
    got = ScopedLCGraphRetriever(system("apache_age", age), ["d1"]).retrieve("who created cmis")
    assert [n.node.text for n in got] == ["Alfresco -> CREATED -> CMIS"]
    assert "MENTIONS" in age.calls[0]
    # FalkorDB: positional rows; no source nodes -> the entity-stamp fallback query runs
    falkor = Graph([], [["Alfresco", "CREATED", "CMIS", "d1"], ["X", "R", "Y", "d9"]])
    got = ScopedLCGraphRetriever(system("falkordb", falkor), ["d1"]).retrieve("cmis")
    assert [n.node.metadata["doc_id"] for n in got] == ["d1"] and len(falkor.calls) == 2
    # A store with no document link gives no facts, and an error gives none either
    assert ScopedLCGraphRetriever(system("cosmos_gremlin", Graph([])), ["d1"]).retrieve("x") == []

    class Broken:
        def query(self, q, params=None):
            raise RuntimeError("down")
    assert ScopedLCGraphRetriever(system("neo4j", Broken()), ["d1"]).retrieve("x") == []
