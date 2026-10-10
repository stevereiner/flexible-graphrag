"""Unit tests for naming the documents results and answers came from (doc_refs.py)."""
import asyncio

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

import doc_refs
from doc_refs import answer_sources, describe, node_doc_ids

pytestmark = pytest.mark.unit

ALF = "9e71b86c-b11a-54f4-8216-382e5351547a:alfresco://c0f6"
FS = "81f57ceb-c824-510b-a603-1c2422d2b1d5:C:\\docs\\space-station.txt"


def _n(meta, score=1.0):
    return NodeWithScore(node=TextNode(text="t", metadata=meta), score=score)


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, sql, ids):
        return [r for r in self.rows if r["doc_id"] in ids]


class _Pool:
    def __init__(self, rows):
        self.conn = _Conn(rows)

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


@pytest.fixture(autouse=True)
def _no_registry(monkeypatch):
    monkeypatch.setattr(doc_refs, "_pool_provider", None)

    async def no_parents(nodes):  # never call a live Alfresco from unit tests
        return {}
    monkeypatch.setattr(doc_refs, "_alfresco_parents", no_parents)
    for var in ("ALFRESCO_OPEN_URL", "ALFRESCO_VIEWER", "ALFRESCO_ACA_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ALFRESCO_URL", "http://localhost:8080")


def test_node_doc_ids_own_id_first_then_rdf_list():
    assert node_doc_ids(_n({"doc_id": "a", "doc_ids": ["b", "a"]})) == ["a", "b"]
    assert node_doc_ids(_n({"doc_ids": ["b"]})) == ["b"]
    assert node_doc_ids(_n({})) == []


def test_describe_from_doc_id_alone():
    refs = asyncio.run(describe([ALF, FS]))
    assert refs[ALF]["source_type"] == "alfresco" and refs[ALF]["node_id"] == "c0f6"
    assert refs[ALF]["open_url"] == "http://localhost:8080/content-app/#/search/(viewer:view/c0f6)"
    assert refs[FS]["name"] == "space-station.txt" and refs[FS]["open_url"] == ""


def test_describe_uses_registry_then_known_names(monkeypatch):
    rows = [{"doc_id": ALF, "source_id": "c0f6", "source_path": "/Shared/GraphRAG/cmispress.txt",
             "source_type": "alfresco", "connection_params": '{"url": "http://alf:8080/"}'}]
    monkeypatch.setattr(doc_refs, "_pool_provider", lambda: _Pool(rows))
    ref = asyncio.run(describe([ALF]))[ALF]
    assert (ref["name"], ref["path"]) == ("cmispress.txt", "/Shared/GraphRAG/cmispress.txt")
    assert ref["open_url"] == "http://alf:8080/content-app/#/search/(viewer:view/c0f6)"
    assert asyncio.run(describe([ALF], {ALF: {"name": "Renamed.txt"}}))[ALF]["name"] == "Renamed.txt"


def test_wikipedia_from_llamaindex_reader_links_by_page_id():
    # WikipediaReader documents: id_ = page id, no url / title / file_name
    n = _n({"doc_id": "48795986", "source": "wikipedia", "language": "en", "resolved_title": "OpenAI"})
    out = asyncio.run(answer_sources([n]))
    assert (out[0]["name"], out[0]["open_url"]) == ("OpenAI", "https://en.wikipedia.org/?curid=48795986")


def test_web_wikipedia_youtube_link_to_their_url():
    web = _n({"doc_id": "w", "source": "web", "url": "https://ex.com/a", "file_name": "a.txt"}, 0.9)
    wiki = _n({"doc_id": "k", "source": "wikipedia", "url": "https://en.wikipedia.org/wiki/X",
               "file_name": "X.txt"}, 0.8)
    yt = _n({"doc_id": "y", "source": "youtube", "url": "https://youtu.be/abc", "video_id": "abc",
             "start_timestamp": "0:05:00", "file_name": "abc_0-05-00.txt"}, 0.7)
    up = _n({"doc_id": "u", "source": "upload", "url": "x", "file_name": "u.pdf"}, 0.6)
    out = {s["name"]: s["open_url"] for s in asyncio.run(answer_sources([web, wiki, yt, up]))}
    assert out == {"a.txt": "https://ex.com/a", "X.txt": "https://en.wikipedia.org/wiki/X",
                   "abc_0-05-00.txt": "https://www.youtube.com/watch?v=abc&t=300s", "u.pdf": ""}


def test_aca_link_opens_over_the_documents_folder(monkeypatch):
    seen = {}

    async def parents(nodes):
        seen.update(nodes)
        return {"c0f6": "f01d"}
    monkeypatch.setattr(doc_refs, "_alfresco_parents", parents)
    ref = asyncio.run(describe([ALF]))[ALF]
    assert seen == {"c0f6": "http://localhost:8080"} and ref["parent_id"] == "f01d"
    assert ref["open_url"] == ("http://localhost:8080/content-app/#/repository/f01d/(viewer:view/c0f6)"
                               "?location=%2Frepository%2Ff01d")


def test_alfresco_url_with_alfresco_suffix(monkeypatch):
    # a datasource saved as http://host:8080/alfresco: links and the folder lookup use the host
    seen = {}

    async def parents(nodes):
        seen.update(nodes)
        return {"c0f6": "f01d"}
    monkeypatch.setattr(doc_refs, "_alfresco_parents", parents)
    rows = [{"doc_id": ALF, "source_id": "c0f6", "source_path": "/Shared/a.txt", "source_type": "alfresco",
             "connection_params": '{"url": "http://alf:8080/alfresco/"}'}]
    monkeypatch.setattr(doc_refs, "_pool_provider", lambda: _Pool(rows))
    ref = asyncio.run(describe([ALF]))[ALF]
    assert seen == {"c0f6": "http://alf:8080"}
    assert ref["open_url"].startswith("http://alf:8080/content-app/#/repository/f01d/")


def test_alfresco_viewer_switch(monkeypatch):
    monkeypatch.setenv("ALFRESCO_ACA_URL", "http://localhost:4200/")
    assert asyncio.run(describe([ALF]))[ALF]["open_url"] == "http://localhost:4200/#/search/(viewer:view/c0f6)"
    monkeypatch.setenv("ALFRESCO_VIEWER", "share")
    assert asyncio.run(describe([ALF]))[ALF]["open_url"].endswith(
        "/share/page/document-details?nodeRef=workspace://SpacesStore/c0f6")


def test_open_url_template_and_nuxeo(monkeypatch):
    monkeypatch.setenv("ALFRESCO_OPEN_URL", "http://aca/#/view/{node_id}")
    assert asyncio.run(describe([ALF]))[ALF]["open_url"] == "http://aca/#/view/c0f6"
    monkeypatch.setenv("NUXEO_URL", "http://nx:8081/nuxeo")
    nx = "cfg:nuxeo://uid-1"
    assert asyncio.run(describe([nx]))[nx]["open_url"] == "http://nx:8081/nuxeo/ui/#!/doc/uid-1"


def test_answer_sources_one_per_document_best_first():
    nodes = [_n({"doc_id": FS, "file_name": "space-station.txt"}, 0.4),
             _n({"doc_id": ALF, "file_name": "cmispress.txt"}, 0.9),
             _n({"doc_id": FS}, 0.6)]
    out = asyncio.run(answer_sources(nodes))
    assert [s["name"] for s in out] == ["cmispress.txt", "space-station.txt"]


def test_answer_sources_without_doc_ids_falls_back_to_file_names():
    out = asyncio.run(answer_sources([_n({"file_name": "a.txt"}), _n({"file_name": "a.txt"})]))
    assert [s["name"] for s in out] == ["a.txt"]
    assert asyncio.run(answer_sources(None)) == []
