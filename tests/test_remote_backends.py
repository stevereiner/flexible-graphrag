"""Federation: a remote Flexible GraphRAG backend's results fused into this backend's search and
Q&A (remote_backends.py, REMOTE_FG_URL). The remote is an httpx mock transport answering
POST /api/search; this backend's own indexes are a fixed fake retriever, so no stores or LLM are
needed."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode

import remote_backends
from doc_refs import answer_sources
from query_engine import search

pytestmark = pytest.mark.unit

_REMOTE_ENV = ("REMOTE_FG_BACKENDS", "REMOTE_FG_URL", "REMOTE_FG_API_TOKEN", "REMOTE_FG_NAME", "REMOTE_FG_TIMEOUT")


@pytest.fixture(autouse=True)
def _no_remotes_from_dotenv(monkeypatch):
    """A test earlier in the run may load a real .env (load_dotenv): its REMOTE_FG_* would add
    real remotes here. Each test sets the ones it wants."""
    for name in _REMOTE_ENV:
        monkeypatch.delenv(name, raising=False)

LOCAL_TEXTS = [
    ("Acme's local notes say the launch moved to March.", "cfg:C:/notes/launch.txt", 0.9),
    ("A personal draft about budgets for the next quarter.", "cfg:C:/notes/budget.txt", 0.4),
]

REMOTE_RESULTS = [
    {"rank": 1, "content": "The team plan puts the Acme launch in the second quarter.", "score": 0.8,
     "source": "plan.pdf | Qdrant vector", "file_type": "", "file_name": "",
     "documents": [{"doc_id": "x:alfresco://n1", "name": "plan.pdf", "source_type": "alfresco",
                    "node_id": "n1", "open_url": "http://aca/#/n1"}]},
    {"rank": 2, "content": "Meeting minutes mention the Acme launch review.", "score": 0.3,
     "source": "minutes.docx | Elasticsearch search", "file_type": "", "file_name": "",
     "documents": [{"doc_id": "x:alfresco://n2", "name": "minutes.docx", "source_type": "alfresco",
                    "node_id": "n2", "open_url": "http://aca/#/n2"}]},
]


class FixedRetriever(BaseRetriever):
    def __init__(self, items):
        self._items = items
        super().__init__()

    def _retrieve(self, query_bundle):
        return [NodeWithScore(node=TextNode(text=t, metadata={"doc_id": d, "file_name": d.rsplit("/", 1)[-1]}),
                              score=s) for t, d, s in self._items]


class FailingRetriever(BaseRetriever):
    def _retrieve(self, query_bundle):
        raise AssertionError("this backend's own indexes should not be asked")


def fake_system(retriever):
    config = SimpleNamespace(vector_db="none", search_db="none", pg_graph_db="none", rdf_graph_db="none",
                             enable_knowledge_graph=False, vector_backend="llamaindex",
                             graph_backend="llamaindex",
                             # no score cut (SEARCH_MIN_RELATIVE_SCORE): these tests count results
                             search_min_relative_score=0.0)
    return SimpleNamespace(config=config, hybrid_retriever=retriever, vector_store=None, vector_index=None,
                           graph_index=None, pg_adapter=None, graph_intentionally_skipped=False,
                           _last_ingested_documents=[], _observability_enabled=False)


class Remote:
    """The remote backend: records each call, answers with REMOTE_RESULTS (or fails)."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def handler(self, request: httpx.Request):
        self.calls.append({"url": str(request.url), "headers": dict(request.headers),
                           "body": json.loads(request.content)})
        if self.fail:
            raise self.fail
        return httpx.Response(200, json={"success": True, "results": REMOTE_RESULTS})


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setenv("REMOTE_FG_URL", "https://team.example.com/")
    monkeypatch.setenv("REMOTE_FG_API_TOKEN", "team-token")
    monkeypatch.setenv("REMOTE_FG_NAME", "team")
    r = Remote()
    monkeypatch.setattr(remote_backends, "_transport", httpx.MockTransport(r.handler))
    remote_backends.begin_request()
    return r


def test_configured_from_env(monkeypatch):
    monkeypatch.delenv("REMOTE_FG_URL", raising=False)
    assert remote_backends.configured() == []
    monkeypatch.setenv("REMOTE_FG_URL", "https://graphrag.corp.example.com/")
    monkeypatch.delenv("REMOTE_FG_NAME", raising=False)
    monkeypatch.delenv("REMOTE_FG_API_TOKEN", raising=False)
    monkeypatch.setenv("REMOTE_FG_TIMEOUT", "12")
    [r] = remote_backends.configured()
    assert (r.name, r.url, r.token, r.timeout) == ("graphrag.corp.example.com",
                                                   "https://graphrag.corp.example.com", None, 12.0)


def test_several_remotes_from_json(monkeypatch):
    monkeypatch.setenv("REMOTE_FG_BACKENDS", json.dumps([
        {"name": "b", "url": "http://localhost:8001/"},
        {"name": "c", "url": "https://c.example.com", "api_token": "c-token", "timeout": 15},
        {"name": "b", "url": "http://localhost:8002"},      # same name: told apart by host:port
        {"name": "dup", "url": "http://localhost:8001"},    # same URL as b: left out
    ]))
    monkeypatch.setenv("REMOTE_FG_URL", "https://team.example.com")
    monkeypatch.setenv("REMOTE_FG_NAME", "team")
    monkeypatch.setenv("REMOTE_FG_TIMEOUT", "40")
    monkeypatch.delenv("REMOTE_FG_API_TOKEN", raising=False)
    got = [(r.name, r.url, r.token, r.timeout) for r in remote_backends.configured()]
    assert got == [("b", "http://localhost:8001", None, 40.0),
                   ("c", "https://c.example.com", "c-token", 15.0),
                   ("b (localhost:8002)", "http://localhost:8002", None, 40.0),
                   ("team", "https://team.example.com", None, 40.0)]
    monkeypatch.setenv("REMOTE_FG_BACKENDS", "not json")
    assert [r.name for r in remote_backends.configured()] == ["team"]


def test_search_fuses_two_remotes(monkeypatch):
    monkeypatch.delenv("REMOTE_FG_URL", raising=False)
    monkeypatch.setenv("REMOTE_FG_BACKENDS", json.dumps([{"name": "b", "url": "http://b"}, {"name": "c", "url": "http://c"}]))
    hosts = []

    def handler(request: httpx.Request):
        host = request.url.host
        hosts.append(host)
        return httpx.Response(200, json={"success": True, "results": [
            {"content": f"Acme launch notes kept on backend {host}.", "score": 0.5, "source": f"{host}.txt"}]})
    monkeypatch.setattr(remote_backends, "_transport", httpx.MockTransport(handler))
    remote_backends.begin_request()
    results = asyncio.run(search(fake_system(FixedRetriever(LOCAL_TEXTS)), "launch?", top_k=10))
    assert sorted(hosts) == ["b", "c"]
    assert {r.get("backend") for r in results} == {None, "b", "c"}

    # picks of c's only: b isn't asked
    hosts.clear()
    remote_backends.begin_request(remote_sources={"c": [{"source": "filesystem"}]})
    asyncio.run(search(fake_system(FixedRetriever(LOCAL_TEXTS)), "launch?", top_k=10))
    assert hosts == ["c"]


def test_search_fuses_local_and_remote(remote):
    results = asyncio.run(search(fake_system(FixedRetriever(LOCAL_TEXTS)), "When is the Acme launch?", top_k=10))

    [call] = remote.calls
    assert call["url"] == "https://team.example.com/api/search"
    assert call["headers"]["x-fg-federated"] == "1"
    assert call["headers"]["x-api-token"] == "team-token"
    assert call["body"]["query"] == "When is the Acme launch?" and call["body"]["query_type"] == "hybrid"

    assert len(results) == 4
    from_team = [r for r in results if r.get("backend") == "team"]
    assert {r["source"] for r in from_team} == {"team: plan.pdf | Qdrant vector",
                                                "team: minutes.docx | Elasticsearch search"}
    assert all(d["backend"] == "team" for r in from_team for d in r["documents"])
    local = [r for r in results if "backend" not in r]
    assert {r["documents"][0]["doc_id"] for r in local} == {d for _, d, _ in LOCAL_TEXTS}
    # each side min-max scaled with equal weights: both sides' best results come first
    assert {results[0]["content"], results[1]["content"]} == {LOCAL_TEXTS[0][0], REMOTE_RESULTS[0]["content"]}


def test_question_from_another_backend_stays_local(remote):
    remote_backends.begin_request(federated=True)
    results = asyncio.run(search(fake_system(FixedRetriever(LOCAL_TEXTS)), "launch?", top_k=10))
    assert remote.calls == []
    assert len(results) == 2 and all("backend" not in r for r in results)


def test_scope_or_picked_sources_stay_local(remote):
    remote_backends.begin_request(local_selection=True)
    results = asyncio.run(search(fake_system(FixedRetriever(LOCAL_TEXTS)), "launch?", top_k=10))
    assert remote.calls == [] and len(results) == 2


def test_a_remotes_picked_sources_go_to_it(remote):
    remote_backends.begin_request(remote_sources={"team": [{"source": "alfresco", "url": "http://acs:8080"}]})
    results = asyncio.run(search(fake_system(FixedRetriever(LOCAL_TEXTS)), "launch?", top_k=10))
    [call] = remote.calls
    assert call["body"]["sources"] == [{"source": "alfresco", "url": "http://acs:8080"}]
    assert {r.get("backend") for r in results} >= {"team"}


def test_only_this_backends_sources_picked_skips_the_remote(remote):
    remote_backends.begin_request(remote_sources={})  # picks, none of the remote's
    results = asyncio.run(search(fake_system(FixedRetriever(LOCAL_TEXTS)), "launch?", top_k=10))
    assert remote.calls == [] and len(results) == 2


def test_remote_sources_are_tagged_with_the_backend(monkeypatch):
    monkeypatch.setenv("REMOTE_FG_URL", "https://team.example.com")
    monkeypatch.setenv("REMOTE_FG_NAME", "team")
    monkeypatch.delenv("REMOTE_FG_API_TOKEN", raising=False)
    monkeypatch.setattr(remote_backends, "_transport", httpx.MockTransport(lambda r: httpx.Response(200, json={
        "available": True, "sources": [{"source": "alfresco", "label": "Alfresco", "url": "http://acs:8080",
                                        "documents": 3, "login_gated": True}]})))
    [s] = asyncio.run(remote_backends.remote_sources_available())
    assert (s["source"], s["backend"], s["documents"]) == ("alfresco", "team", 3)


def test_remote_down_gives_local_results_and_a_note(remote):
    remote.fail = httpx.ConnectError("connection refused")
    results = asyncio.run(search(fake_system(FixedRetriever(LOCAL_TEXTS)), "launch?", top_k=10))
    assert len(remote.calls) == 1
    assert len(results) == 2 and all("backend" not in r for r in results)
    assert remote_backends.notes() and "team" in remote_backends.notes()[0]


def test_nothing_here_still_asks_the_remote(remote):
    # scope_doc_ids == []: nothing of this backend's own the asker may read
    results = asyncio.run(search(fake_system(FailingRetriever()), "launch?", top_k=10, scope_doc_ids=[]))
    assert len(remote.calls) == 1
    assert [r["backend"] for r in results] == ["team", "team"]


def test_nothing_indexed_here_still_asks_the_remote(remote, monkeypatch):
    import retriever_setup

    def no_indexes(system, scope_doc_ids=None):
        raise ValueError("No retrievers ready yet. Please ingest documents first.")
    monkeypatch.setattr(retriever_setup, "setup_hybrid_retriever", no_indexes)
    results = asyncio.run(search(fake_system(None), "launch?", top_k=10))
    assert [r["backend"] for r in results] == ["team", "team"]


def test_no_remote_configured_is_unchanged(monkeypatch):
    monkeypatch.delenv("REMOTE_FG_URL", raising=False)
    remote_backends.begin_request()
    assert remote_backends.with_remotes(None) is None
    local = FixedRetriever(LOCAL_TEXTS)
    assert remote_backends.with_remotes(local) is local
    results = asyncio.run(search(fake_system(local), "launch?", top_k=10))
    assert len(results) == 2


def test_graph_only_backend_keeps_the_remotes_lowest_result(remote):
    # graph-only mode drops zero-score results as graph noise; fusion scales the remote's lowest
    # result to 0.0, and that is a real document of the remote's, not noise
    system = fake_system(FixedRetriever([("Acme employs Jane Doe as its CEO.", "cfg:g1", 0.7)]))
    system.config.pg_graph_db = "neo4j"
    system.config.enable_knowledge_graph = True
    results = asyncio.run(search(system, "who works for acme", top_k=10))
    assert sorted(r["content"] for r in results if r.get("backend") == "team") == sorted(
        r["content"] for r in REMOTE_RESULTS)


def test_score_cut_keeps_the_remotes_results(remote):
    # SEARCH_MIN_RELATIVE_SCORE drops this backend's weak results; a remote cut its own already,
    # and fusion puts its weakest at 0.0, so remote results are not cut here
    system = fake_system(FixedRetriever(LOCAL_TEXTS))
    system.config.search_min_relative_score = 0.5
    results = asyncio.run(search(system, "launch?", top_k=10))
    assert sorted(r["content"] for r in results if r.get("backend") == "team") == sorted(
        r["content"] for r in REMOTE_RESULTS)
    assert [r["content"] for r in results if "backend" not in r] == [LOCAL_TEXTS[0][0]]


def test_remote_auth_providers_are_tagged_with_the_backend(monkeypatch):
    monkeypatch.setenv("REMOTE_FG_URL", "https://team.example.com")
    monkeypatch.setenv("REMOTE_FG_NAME", "team")
    monkeypatch.setenv("REMOTE_FG_API_TOKEN", "team-token")
    seen = []

    def handler(request: httpx.Request):
        seen.append((str(request.url), request.headers.get("x-fg-federated"), request.headers.get("x-api-token")))
        return httpx.Response(200, json={"required": True, "providers": [
            {"source": "alfresco", "label": "Alfresco", "url": "http://localhost:8080", "required": True,
             "documents": 3, "methods": ["basic"]}]})
    monkeypatch.setattr(remote_backends, "_transport", httpx.MockTransport(handler))
    [p] = asyncio.run(remote_backends.remote_auth_providers())
    assert seen == [("https://team.example.com/api/auth/requirements", "1", "team-token")]
    assert (p["source"], p["url"], p["backend"], p["required"]) == ("alfresco", "http://localhost:8080", "team", True)

    # a remote that doesn't answer adds no sign-ins (and fails nothing)
    monkeypatch.setattr(remote_backends, "_transport", httpx.MockTransport(lambda r: httpx.Response(503)))
    assert asyncio.run(remote_backends.remote_auth_providers()) == []


def test_answer_sources_lists_both_backends(remote):
    retriever = remote_backends.with_remotes(FixedRetriever(LOCAL_TEXTS))
    nodes = asyncio.run(retriever.aretrieve("launch?"))
    sources = asyncio.run(answer_sources(nodes))
    names = [s["name"] for s in sources]
    assert set(names) == {"launch.txt", "budget.txt", "plan.pdf", "minutes.docx"}
    assert next(s for s in sources if s["name"] == "plan.pdf")["backend"] == "team"
    # the remote's hidden bookkeeping stays out of the LLM's view of a chunk
    remote_node = next(n for n in nodes if n.node.metadata.get(remote_backends.REMOTE_KEY))
    from llama_index.core.schema import MetadataMode
    llm_view = remote_node.node.get_content(metadata_mode=MetadataMode.LLM)
    assert "team: plan.pdf" in llm_view or "team: minutes.docx" in llm_view
    assert "open_url" not in llm_view
