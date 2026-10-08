"""Unit tests for query-time permission filtering (permission_filter.py), with Alfresco mocked."""
import asyncio

import httpx
import pytest

import permission_filter as pf

pytestmark = pytest.mark.unit

READABLE = {"n1"}  # the mocked Alfresco lets the ticket read only node n1


def _mock_client(*args, **kwargs):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Basic ")
        node = request.url.path.rsplit("/", 1)[-1]
        if request.headers["Authorization"] == "Basic VElDS0VUX2JhZA==":  # TICKET_bad
            return httpx.Response(401)
        return httpx.Response(200 if node in READABLE else 403)
    kwargs.pop("timeout", None)
    return _RealClient(transport=httpx.MockTransport(handler))


_RealClient = httpx.AsyncClient


@pytest.fixture(autouse=True)
def mocked_alfresco(monkeypatch):
    pf._cache.clear()
    monkeypatch.setattr(httpx, "AsyncClient", _mock_client)


def test_node_id_and_rest_base():
    assert pf.alfresco_node_id("c1:alfresco://n1") == "n1"
    assert pf.alfresco_node_id("c1:/data/file.txt") is None
    assert pf._rest_base("http://localhost:8080/alfresco/") == "http://localhost:8080"
    assert pf._rest_base("http://localhost:8080") == "http://localhost:8080"


def test_keeps_readable_alfresco_docs_and_non_alfresco_docs():
    ids = ["c1:alfresco://n1", "c1:alfresco://n2", "c2:/data/notes.txt"]
    out = asyncio.run(pf.readable_doc_ids(ids, "TICKET_ok", lambda d: "http://localhost:8080/alfresco"))
    assert out == ["c1:alfresco://n1", "c2:/data/notes.txt"]


def test_refused_ticket_raises():
    with pytest.raises(PermissionError):
        asyncio.run(pf.readable_doc_ids(["c1:alfresco://n1"], "TICKET_bad", lambda d: "http://x"))


def test_no_repository_url_leaves_the_doc_out():
    out = asyncio.run(pf.readable_doc_ids(["c1:alfresco://n1"], "TICKET_ok", lambda d: None))
    assert out == []
