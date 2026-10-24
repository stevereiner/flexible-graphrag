"""Unit tests for the OpenArch content repository target (openarch/), with a fake client."""
import io
import json
import re

import httpx

import pytest
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode
from llama_index.core.vector_stores.types import (
    FilterOperator, MetadataFilter, MetadataFilters, VectorStoreQuery, VectorStoreQueryMode,
)

from openarch import source_system as ss
from openarch.client import hxql_literal
from openarch.vector_store import OpenArchVectorStore, query_terms
from openarch.writer import DOC_IDS_KEY, METADATA_KEY, OpenArchDocumentWriter, embedding_type_name, parquet_bytes

pytestmark = pytest.mark.unit

CFG_A = "11111111-2222-3333-4444-555555555555"
CFG_B = "66666666-7777-8888-9999-000000000000"


class FakeClient:
    """Just enough of OpenArchClient: documents in a dict, HXQL answered by cin_id / sys_parentId."""

    url = "http://fake"
    repository = "default"

    def __init__(self):
        self.docs = {}
        self.calls = []
        self.embedding_hits = []
        self.folders = []

    def query(self, hxql, limit=100, offset=0, sync=True):
        self.calls.append(("query", hxql))
        m = re.search(r"cin_id = '([^']*)'", hxql)
        if m:
            found = [d for d in self.docs.values() if d.get("cin_id") == m.group(1).replace("\\\\", "\\")]
            return {"documents": found}
        m = re.search(r"sys_parentId = '([^']*)'", hxql)
        if m:
            return {"documents": [d for d in self.docs.values() if d.get("parent") == m.group(1)]}
        m = re.search(r"sys_id IN \((.*)\)", hxql)
        if m:
            ids = re.findall(r"'([^']*)'", m.group(1))
            return {"documents": [self.docs[i] for i in ids if i in self.docs]}
        return {"documents": []}

    def query_all(self, hxql, page_size=200, sync=True):
        return self.query(hxql)["documents"]

    def ensure_folders(self, path):
        self.folders.append(path)

    def create(self, parent_path, body):
        doc = dict(body, sys_id=f"id{len(self.docs) + 1}", sys_path=f"{parent_path}/{body['sys_name']}")
        self.docs[doc["sys_id"]] = doc
        return doc

    def create_child(self, parent_id, body):
        doc = dict(body, sys_id=f"id{len(self.docs) + 1}", parent=parent_id)
        self.docs[doc["sys_id"]] = doc
        return doc

    def update(self, doc_id, body, condition=None):
        self.calls.append(("update", doc_id, body))
        self.docs[doc_id].update(body)
        return self.docs[doc_id]

    def get(self, doc_id):
        return self.docs.get(doc_id)

    def delete(self, doc_id):
        self.calls.append(("delete", doc_id))
        return self.docs.pop(doc_id, None) is not None

    def upload(self, data, file_name, mime_type):
        self.calls.append(("upload", len(data)))
        return "upl-1"

    def query_embeddings(self, vector, limit=10, embedding_type="*", hxql=None, chunk_fts=None):
        self.calls.append(("embeddings", hxql, chunk_fts, limit))
        return list(self.embedding_hits)


def _chunk(text, ref, vec=(0.1, 0.2)):
    n = TextNode(text=text, embedding=list(vec), metadata={})
    n.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=ref)
    return n


# ----- source systems, identities, paths -----

def test_source_system_from_job_config(monkeypatch):
    monkeypatch.setattr(ss, "alfresco_repository_id", lambda config: "repo-uuid")
    assert ss.source_system_for("alfresco", {"alfresco_config": {"url": "http://Alf:8080/alfresco"}}) == ("alfresco", "repo-uuid")
    monkeypatch.setattr(ss, "alfresco_repository_id", lambda config: None)  # Discovery unavailable
    assert ss.source_system_for("alfresco", {"alfresco_config": {"url": "http://Alf:8080/alfresco"}}) == ("alfresco", "alf-8080")
    # several Nuxeo servers: host-port, or each config's own source_id
    assert ss.source_system_for("nuxeo", {"nuxeo_config": {"url": "http://nx1:8081/nuxeo"}}) == ("nuxeo", "nx1-8081")
    assert ss.source_system_for("nuxeo", {"nuxeo_config": {"url": "http://nx2/nuxeo", "source_id": "prod"}}) == ("nuxeo", "prod")
    assert ss.source_system_for("s3", {"s3_config": {"bucket_name": "docs"}}) == ("s3", "docs")
    assert ss.source_system_for("upload", {})[0] == "filesystem"
    assert ss.source_folder("alfresco", "repo-uuid") == "alfresco/repo-uuid"


def test_named_servers_from_openarch_source_ids(monkeypatch):
    monkeypatch.setenv("OPENARCH_SOURCE_IDS", json.dumps({
        "nuxeo-repo-1": "http://localhost:8081/nuxeo",
        "nuxeo-repo-2": ["http://nx2/nuxeo", "http://localhost:8082/nuxeo"]}))
    monkeypatch.setattr(ss, "alfresco_repository_id", lambda config: "repo-uuid")
    assert ss.source_system_for("nuxeo", {"nuxeo_config": {"url": "http://LOCALHOST:8081/nuxeo/"}}) == ("nuxeo", "nuxeo-repo-1")
    assert ss.source_system_for("nuxeo", {"nuxeo_config": {"url": "http://nx2:80/nuxeo"}}) == ("nuxeo", "nuxeo-repo-2")
    assert ss.source_system_for("nuxeo", {"nuxeo_config": {"url": "http://localhost:8082/nuxeo"}}) == ("nuxeo", "nuxeo-repo-2")
    assert ss.source_system_for("nuxeo", {"nuxeo_config": {"url": "http://other:8081/nuxeo"}}) == ("nuxeo", "other-8081")
    # a request's own source_id still wins
    assert ss.source_system_for("nuxeo", {"nuxeo_config": {"url": "http://localhost:8081/nuxeo", "source_id": "x"}}) == ("nuxeo", "x")


def test_document_identity_strips_the_data_source_config_id():
    assert ss.document_identity(f"{CFG_A}:alfresco://n1", {}) == "alfresco://n1"
    assert ss.is_data_source_doc_id(f"{CFG_A}:alfresco://n1")
    assert not ss.is_data_source_doc_id("random-id")
    assert ss.document_identity("random-id", {"stable_file_path": "nuxeo://u1"}) == "nuxeo://u1"


def test_document_path_adds_the_name_to_a_folder_path():
    meta = {"file_path": "/Shared/GraphRAG", "file_name": "a.pdf"}
    assert ss.document_path("alfresco", "alfresco://n1", meta) == ["Shared", "GraphRAG", "a.pdf"]
    assert ss.document_path("alfresco", "alfresco://n1", {"file_path": "/Shared/a.pdf", "file_name": "a.pdf"}) == ["Shared", "a.pdf"]
    assert ss.document_path("filesystem", "x", {"file_path": r"C:\data\b.txt", "file_name": "b.txt"}) == ["c", "data", "b.txt"]
    assert ss.document_path("web", "https://h/x/y", {"url": "https://h/x/y"}) == ["x", "y"]


def test_document_path_of_a_renamed_nuxeo_document_is_its_own_path():
    # a renamed Nuxeo document keeps its file's original name: the path is still the document's own
    meta = {"file_path": "/default-domain/workspaces/w/Sub/c2.txt", "file_name": "c.txt"}
    assert ss.document_path("nuxeo", "nuxeo://u1", meta) == ["default-domain", "workspaces", "w", "Sub", "c2.txt"]


def test_a_flattened_blob_name_is_not_added_as_another_level():
    # Azure's reader names kg-matrix/a.txt "kg-matrix-a.txt"
    meta = {"file_path": "graphrag-datasource-1/kg-matrix/a.txt", "container_name": "graphrag-datasource-1",
            "file_name": "kg-matrix-a.txt"}
    assert ss.document_path("azure_blob", "x", meta) == ["kg-matrix", "a.txt"]


def test_youtube_segments_go_under_their_video():
    from openarch.source_system import document_path
    meta = {"video_id": "dQw4w9WgXcQ", "start_timestamp": "00:01:00", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    assert document_path("youtube", "youtube://dQw4w9WgXcQ/00:01:00", meta) == ["dQw4w9WgXcQ", "00-01-00"]


def test_bucket_or_container_is_not_repeated_under_its_system_folder():
    from openarch.source_system import document_path
    meta = {"file_path": "graphrag-datasource-1/docs/a.txt", "container_name": "graphrag-datasource-1", "file_name": "a.txt"}
    assert document_path("azure_blob", "graphrag-datasource-1/docs/a.txt", meta) == ["docs", "a.txt"]
    meta = {"file_path": "bucket-1/x/b.pdf", "bucket": "bucket-1", "file_name": "b.pdf"}   # GCS: "bucket"
    assert document_path("gcs", "bucket-1/x/b.pdf", meta) == ["x", "b.pdf"]


def test_hxql_quoting():
    assert hxql_literal("it's") == "'it\\'s'"
    assert hxql_literal("c:\\data") == "'c:\\\\data'"


def test_query_terms_drop_stop_words_and_short_words():
    assert query_terms("When was the space station launched? the ISS") == ["space", "station", "launched", "iss"]


def test_embedding_type_name():
    assert embedding_type_name("openai", "text-embedding-3-small", 1024) == "fg-openai-text-embedding-3-small-1024"
    assert embedding_type_name(None, "ai/mxbai-embed-large", None) == "fg-ai-mxbai-embed-large"


def test_parquet_has_the_columns_openarch_reads():
    import pyarrow.parquet as pq
    table = pq.read_table(io.BytesIO(parquet_bytes([_chunk("one", "d"), TextNode(text="no vector")], "t")))
    assert table.column_names == ["id", "type", "vector", "text", "blobref", "location"]
    assert table.num_rows == 1
    assert json.loads(table.column("location")[0].as_py()) == {"text": {"paragraph": 0}}


# ----- writes and membership -----

def _writer(client):
    return OpenArchDocumentWriter(client, "fg-test-1024", "/sources")


def test_write_creates_under_the_source_system_and_attaches_embeddings():
    client = FakeClient()
    meta = {"file_name": "a.pdf", "file_path": "/Shared/a.pdf", "content_type": "application/pdf"}
    oa_id = _writer(client).write(f"{CFG_A}:alfresco://n1", "full text", meta, [_chunk("c", "x")],
                                  source=("alfresco", "alf-8080"))
    doc = client.docs[oa_id]
    assert doc["sys_path"] == "/sources/alfresco/alf-8080/Shared/a.pdf"
    assert doc["cin_sourceId"] == "alfresco:alf-8080" and doc["cin_id"] == "alfresco://n1"
    assert set(doc["sys_mixinTypes"]) == {"CinRemote", "SysHasEmbeddings"}
    props = doc["cin_ingestProperties"]
    assert props["fg_extractedText"] == "full text"
    assert sorted(doc["cin_ingestPropertyNames"]) == sorted(props)
    child = next(d for d in client.docs.values() if d.get("parent") == oa_id)
    assert child["sys_name"] == "_e_fg-test-1024" and child["sysemb_embeddings"] == {"uploadId": "upl-1"}


def test_two_data_sources_share_one_document_until_the_last_removes_it():
    client = FakeClient()
    w = _writer(client)
    meta = {"file_name": "a.pdf", "file_path": "/Shared/a.pdf"}
    first = w.write(f"{CFG_A}:alfresco://n1", "t", meta, [_chunk("c", "x")], source=("alfresco", "alf"))
    second = w.write(f"{CFG_B}:alfresco://n1", "t2", meta, [_chunk("c", "x")], source=("alfresco", "alf"))
    assert first == second
    assert client.docs[first]["cin_ingestProperties"][DOC_IDS_KEY].split("\n") == [
        f"{CFG_A}:alfresco://n1", f"{CFG_B}:alfresco://n1"]
    # the embeddings child is replaced, not duplicated
    assert len([d for d in client.docs.values() if d.get("parent") == first]) == 1

    assert w.remove(f"{CFG_A}:alfresco://n1")
    assert client.docs[first]["cin_ingestProperties"][DOC_IDS_KEY] == f"{CFG_B}:alfresco://n1"
    assert w.remove(f"{CFG_B}:alfresco://n1")
    assert first not in client.docs and not client.docs  # child deleted too


def test_removing_the_content_keeps_a_document_that_holds_data_source_state():
    client = FakeClient()
    w = _writer(client)
    oa = w.write(f"{CFG_A}:alfresco://n1", "t", {"file_name": "a.pdf", "file_path": "/Shared/a.pdf"},
                 [_chunk("c", "x")], source=("alfresco", "alf"))
    client.docs[oa]["fg_docstate_docIds"] = [f"{CFG_A}:alfresco://n1"]  # its state (openarch/registry.py)
    client.docs[oa]["cin_ingestProperties"]["source_type"] = "alfresco"
    assert w.remove(f"{CFG_A}:alfresco://n1")
    props = client.docs[oa]["cin_ingestProperties"]
    assert DOC_IDS_KEY not in props and "fg_extractedText" not in props and props["source_type"] == "alfresco"
    assert not [d for d in client.docs.values() if d.get("parent") == oa]  # chunks gone


def test_an_ad_hoc_id_does_not_accumulate():
    client = FakeClient()
    w = _writer(client)
    meta = {"file_name": "b.txt", "file_path": "/tmp/b.txt", "stable_file_path": "fs://b"}
    oa = w.write("random-1", "t", meta, [], source=("filesystem", "h"))
    w.write("random-2", "t", meta, [], source=("filesystem", "h"))
    assert client.docs[oa]["cin_ingestProperties"][DOC_IDS_KEY] == "random-2"


# ----- queries -----

def _store(client):
    store = OpenArchVectorStore.__new__(OpenArchVectorStore)
    OpenArchVectorStore.__init__(store, client, "fg-test-1024")
    return store


def _parent(client, doc_ids, meta_doc_id):
    client.docs["p1"] = {"sys_id": "p1", "sys_path": "/sources/x/a.pdf", "cin_ingestProperties": {
        DOC_IDS_KEY: "\n".join(doc_ids), METADATA_KEY: json.dumps({"file_name": "a.pdf", "doc_id": meta_doc_id})}}


def test_scope_filter_becomes_a_cin_id_condition_and_names_the_scoped_doc_id():
    client = FakeClient()
    a, b = f"{CFG_A}:alfresco://n1", f"{CFG_B}:alfresco://n1"
    _parent(client, [a, b], a)
    client.embedding_hits = [{"sysembed_id": "c1", "sysembed_docId": "p1", "sysembed_text": "x", "sysembed_score": 0.9}]
    filters = MetadataFilters(filters=[MetadataFilter(key="doc_id", value=[b], operator=FilterOperator.IN)])
    result = _store(client).query(VectorStoreQuery(query_embedding=[0.1], similarity_top_k=5, filters=filters,
                                                   mode=VectorStoreQueryMode.HYBRID, query_str="revenue growth"))
    kind, hxql, chunk_fts, _ = client.calls[0]
    # only this store's tree (several instances can share a repository), then the scope
    assert hxql == "SELECT * FROM SysFile WHERE sys_path STARTSWITH '/fg-sources/' AND cin_id IN ('alfresco://n1')"
    assert chunk_fts == "revenue growth"
    node = result.nodes[0]
    assert node.metadata["doc_id"] == b and node.ref_doc_id == b
    assert node.metadata["file_name"] == "a.pdf" and result.similarities == [0.9]


def test_keyword_mode_filters_on_sys_fulltext_and_ranks_by_matched_terms():
    client = FakeClient()
    _parent(client, ["d"], "d")
    client.embedding_hits = [
        {"sysembed_id": "c1", "sysembed_docId": "p1", "sysembed_text": "costs fell", "sysembed_score": 0.9},
        {"sysembed_id": "c2", "sysembed_docId": "p1", "sysembed_text": "logistics costs fell", "sysembed_score": 0.1},
        {"sysembed_id": "c3", "sysembed_docId": "p1", "sysembed_text": "unrelated", "sysembed_score": 0.8},
    ]
    result = _store(client).query(VectorStoreQuery(query_embedding=[0.1], similarity_top_k=2, query_str="logistics costs",
                                                   mode=VectorStoreQueryMode.TEXT_SEARCH))
    hxql = client.calls[0][1]
    assert "sys_fulltext = 'logistics' OR sys_fulltext = 'costs'" in hxql
    assert [n.node_id for n in result.nodes] == ["c2", "c1"]


def test_openarch_counts_as_the_vector_and_search_store():
    from types import SimpleNamespace
    from incremental_updates.removal import configured_stores
    from ingest._helpers import generate_completion_message, store_labels
    settings = SimpleNamespace(enable_openarch=True, vector_db="none", search_db="none",
                               pg_graph_db="neo4j", rdf_graph_db="none", enable_knowledge_graph=True)
    assert configured_stores(settings) == {"vector": True, "search": True, "graph": True, "rdf": False}
    assert store_labels(settings, ["vector", "search"]) == ["OpenArch hybrid search+vector"]
    assert "OpenArch hybrid search+vector" in generate_completion_message(settings, 2)


class TreeClient:
    """A repository tree for remove_ingested: documents keyed by id, with parent and type."""

    def __init__(self, docs):
        self.docs = {d["sys_id"]: d for d in docs}

    def get_by_path(self, path):
        return next((d for d in self.docs.values() if d.get("sys_path") == path), None)

    def _ancestors(self, d):
        while d.get("parent"):
            d = self.docs[d["parent"]]
            yield d["sys_id"]

    def query_all(self, hxql, **kw):
        return self.query(hxql)["documents"]

    def query(self, hxql, limit=100, **kw):
        kind = re.search(r"FROM (\w+)", hxql).group(1)
        docs = [d for d in self.docs.values() if kind == "SysContent" or d["type"] == kind]
        m = re.search(r"sys_ancestorIds = '([^']*)'", hxql)
        if m:
            docs = [d for d in docs if m.group(1) in self._ancestors(d)]
        m = re.search(r"sys_parentId = '([^']*)'", hxql)
        if m:
            docs = [d for d in docs if d.get("parent") == m.group(1)]
        return {"documents": docs[:limit]}

    def delete(self, doc_id):
        return self.docs.pop(doc_id, None) is not None


def test_cleanup_removes_only_what_flexible_graphrag_ingested():
    from openarch.integration import remove_ingested
    client = TreeClient([
        {"sys_id": "root", "type": "SysFolder", "sys_path": "/sources"},
        {"sys_id": "alf", "type": "SysFolder", "sys_path": "/sources/alf", "parent": "root"},
        {"sys_id": "d1", "type": "SysFile", "sys_path": "/sources/alf/a", "parent": "alf",
         "cin_ingestProperties": {DOC_IDS_KEY: "x"}},
        {"sys_id": "e1", "type": "SysEmbeddings", "parent": "d1"},
        {"sys_id": "other", "type": "SysFolder", "sys_path": "/sources/other", "parent": "root"},
        {"sys_id": "keep", "type": "SysFile", "sys_path": "/sources/other/k", "parent": "other"},
    ])
    assert remove_ingested(client, "/sources") == {"documents": 1, "folders": 1}
    assert set(client.docs) == {"root", "other", "keep"}  # the folder of the kept file stays


def test_empty_scope_returns_nothing_without_a_query():
    client = FakeClient()
    filters = MetadataFilters(filters=[MetadataFilter(key="doc_id", value=[], operator=FilterOperator.IN)])
    result = _store(client).query(VectorStoreQuery(query_embedding=[0.1], filters=filters))
    assert result.nodes == [] and not client.calls


def test_a_moved_or_renamed_source_object_moves_its_document():
    from openarch.client import OpenArchError
    from openarch.writer import place_source_document

    class Client:
        """OpenArch's behaviour: a move keeps the name, a copy (with its children) takes one, a
        name taken in the folder is a 409."""

        def __init__(self):
            self.n = 0
            self.docs = {"d1": {"sys_id": "d1", "sys_path": "/root/alfresco/r/Shared/M/a.txt", "cin_id": "alfresco://n1"},
                         "e1": {"sys_id": "e1", "sys_path": "/root/alfresco/r/Shared/M/a.txt/_e_x", "parent": "d1"}}

        def ensure_folders(self, path):
            pass

        def get_by_path(self, path):
            return {"sys_id": "F:" + path, "sys_path": path}

        def _place(self, doc_id, folder, name):
            path = folder + "/" + name
            if any(d["sys_path"] == path for d in self.docs.values()):
                raise OpenArchError(httpx.Response(409, request=httpx.Request("POST", "http://fake/move")))
            return path

        takes_name = False  # a stock OpenArch's move ignores a name

        def move(self, doc_id, parent_id, name=None):
            d = self.docs[doc_id]
            keep = d["sys_path"].rsplit("/", 1)[1]
            d["sys_path"] = self._place(doc_id, parent_id[2:], name if name and self.takes_name else keep)
            return dict(d)

        def copy(self, doc_id, parent_id, name):
            path = self._place(doc_id, parent_id[2:], name)
            self.n += 1
            new_id = f"c{self.n}"
            self.docs[new_id] = dict(self.docs[doc_id], sys_id=new_id, sys_path=path)
            for child in [c for c in self.docs.values() if c.get("parent") == doc_id]:
                self.docs[new_id + child["sys_id"]] = dict(child, sys_id=new_id + child["sys_id"], parent=new_id)
            return dict(self.docs[new_id])

        def get(self, doc_id):
            return dict(self.docs[doc_id]) if doc_id in self.docs else None

        def query_all(self, hxql):
            parent = re.search(r"sys_parentId = '([^']*)'", hxql).group(1)
            return [d for d in self.docs.values() if d.get("parent") == parent]

        def delete(self, doc_id):
            return self.docs.pop(doc_id, None) is not None

    c = Client()
    doc = dict(c.docs["d1"])
    assert place_source_document(c, "/root", "alfresco", "r", ["Shared", "M", "a.txt"], doc) == doc  # in place
    moved = place_source_document(c, "/root", "alfresco", "r", ["Shared", "M", "Other", "a.txt"], doc)
    assert moved["sys_id"] == "d1" and moved["sys_path"] == "/root/alfresco/r/Shared/M/Other/a.txt"  # a move keeps it
    renamed = place_source_document(c, "/root", "alfresco", "r", ["Shared", "M", "a-renamed.txt"], moved)
    assert renamed["sys_path"] == "/root/alfresco/r/Shared/M/a-renamed.txt" and renamed["sys_id"] != "d1"
    assert "d1" not in c.docs and "e1" not in c.docs                                 # the old one is gone...
    assert [d["parent"] for d in c.docs.values() if "parent" in d] == [renamed["sys_id"]]  # ...its chunks copied
    c.docs["x"] = {"sys_id": "x", "sys_path": "/root/alfresco/r/Shared/M/b.txt"}   # another object's name
    clash = place_source_document(c, "/root", "alfresco", "r", ["Shared", "M", "b.txt"], renamed)
    assert clash["sys_path"].startswith("/root/alfresco/r/Shared/M/b~") and clash["sys_path"].endswith(".txt")

    # an OpenArch whose move takes a name renames in place: the same document
    c.takes_name = True
    again = place_source_document(c, "/root", "alfresco", "r", ["Shared", "M", "Other", "z.txt"], clash)
    assert again["sys_id"] == clash["sys_id"] and again["sys_path"] == "/root/alfresco/r/Shared/M/Other/z.txt"
