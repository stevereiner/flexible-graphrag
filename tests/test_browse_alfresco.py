"""Alfresco source browser (flexible-graphrag/browse/alfresco.py) over a mocked Alfresco REST API:
listing, Company-Home-relative paths, skipCount paging, the auth header, guards and error mapping."""

import asyncio
import base64
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flexible-graphrag"))

import browse  # noqa: E402
from browse import BrowseError  # noqa: E402
from browse import alfresco as af  # noqa: E402

BASE = "http://acs:8080"
CFG = {"url": f"{BASE}/alfresco", "username": "u", "password": "p"}
NODES = f"{BASE}/alfresco/api/-default-/public/alfresco/versions/1/nodes"


def run(coro):
    return asyncio.run(coro)


def node(id_, name, folder, parent="/Company Home", size=None):
    # no "path": the browser doesn't ask for include=path (it can 500 on an undeployed model's aspect)
    e = {"id": id_, "name": name, "isFolder": folder, "isFile": not folder,
         "modifiedAt": "2026-11-01T10:00:00.000+0000"}
    if not folder:
        e["content"] = {"mimeType": "application/pdf", "sizeInBytes": size or 1}
    return {"entry": e}


@pytest.fixture
def acs(monkeypatch):
    """A fake Alfresco: node id -> children entries; records requests."""
    tree = {
        "-root-": [node("f-shared", "Shared", True), node("f-sites", "Sites", True),
                   {"entry": {"id": "l1", "name": "link", "isFolder": False, "isFile": False}}],
        "f-shared": [node("f-g", "GraphRAG", True, "/Company Home/Shared"),
                     node("d1", "a.pdf", False, "/Company Home/Shared", 7),
                     node("d2", "b.pdf", False, "/Company Home/Shared")],
    }
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        node_id = request.url.path.split("/nodes/")[1].split("/")[0]
        if request.headers.get("authorization") == "Basic bad":
            return httpx.Response(401, json={"error": {"briefSummary": "nope"}})
        if "include" in request.url.params:  # what a live ACS did with an undeployed model's aspect
            return httpx.Response(500, json={"error": {"briefSummary": "A namespace prefix is not registered"}})
        if node_id not in tree:
            return httpx.Response(404, json={"error": {"briefSummary": "gone"}})
        skip, limit = int(request.url.params["skipCount"]), int(request.url.params["maxItems"])
        rows = tree[node_id][skip:skip + limit]
        return httpx.Response(200, json={"list": {"entries": rows, "pagination": {
            "count": len(rows), "skipCount": skip, "maxItems": limit,
            "hasMoreItems": skip + limit < len(tree[node_id])}}})

    real = httpx.AsyncClient
    monkeypatch.setattr(af.httpx, "AsyncClient",
                        lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))
    return seen


def test_root_and_child_paths(acs):
    top = run(browse.browse("alfresco", CFG, None, None, 100))
    # Company-Home-relative paths (what the ingest's path takes); links left out
    assert [(i.id, i.kind, i.path) for i in top.items] == [("f-shared", "folder", "/Shared"),
                                                           ("f-sites", "folder", "/Sites")]
    assert acs[-1].url.path == "/alfresco/api/-default-/public/alfresco/versions/1/nodes/-root-/children"
    sub = run(browse.browse("alfresco", CFG, {"id": "f-shared", "path": "/Shared"}, None, 100))
    assert [(i.kind, i.path, i.size) for i in sub.items] == [
        ("folder", "/Shared/GraphRAG", None), ("file", "/Shared/a.pdf", 7), ("file", "/Shared/b.pdf", 1)]


def test_paging_by_skip_count(acs):
    first = run(browse.browse("alfresco", CFG, {"id": "f-shared"}, None, 2))
    assert len(first.items) == 2 and first.next_page_token == "2"
    second = run(browse.browse("alfresco", CFG, {"id": "f-shared"}, first.next_page_token, 2))
    assert [i.name for i in second.items] == ["b.pdf"] and second.next_page_token is None
    assert acs[-1].url.params["skipCount"] == "2"


def test_auth_headers(acs):
    run(browse.browse("alfresco", CFG, None, None, 10))
    assert acs[-1].headers["authorization"] == "Basic " + base64.b64encode(b"u:p").decode()
    # the sign-in's ticket (a ticket alone means ticket auth, as AlfrescoConfig)
    run(browse.browse("alfresco", {"url": BASE, "ticket": "TICKET_1"}, None, None, 10))
    assert acs[-1].headers["authorization"] == "Basic " + base64.b64encode(b"TICKET_1").decode()
    run(browse.browse("alfresco", {"url": BASE, "auth_method": "oauth2",
                                   "oauth2": {"access_token": "tok"}}, None, None, 10))
    assert acs[-1].headers["authorization"] == "Bearer tok"


def test_needs_url_and_credentials():
    with pytest.raises(BrowseError) as e:
        run(browse.browse("alfresco", {"url": BASE, "username": "u"}, None, None, 10))
    assert "password" in str(e.value)
    with pytest.raises(BrowseError) as e:
        run(browse.browse("alfresco", {"username": "u", "password": "p"}, None, None, 10))
    assert "URL" in str(e.value)
    with pytest.raises(BrowseError) as e:
        run(browse.browse("alfresco", {"url": BASE, "auth_method": "oauth2", "oauth2": {}}, None, None, 10))
    assert "OAuth2" in str(e.value)


def test_errors_map_status(acs, monkeypatch):
    with pytest.raises(BrowseError) as e:
        run(browse.browse("alfresco", CFG, {"id": "gone"}, None, 10))
    assert e.value.status_code == 404

    async def bad(_config):
        return "Basic bad"
    monkeypatch.setattr(af, "_authorization", bad)
    with pytest.raises(BrowseError) as e:
        run(browse.browse("alfresco", CFG, None, None, 10))
    assert e.value.status_code == 401 and "sign-in failed" in str(e.value)
    assert af._error(403, None).status_code == 403
    assert af._error(500, {"error": {"briefSummary": "boom"}}).status_code == 502


def test_unreachable(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("refused")
    real = httpx.AsyncClient
    monkeypatch.setattr(af.httpx, "AsyncClient",
                        lambda *a, **k: real(*a, transport=httpx.MockTransport(refuse), **k))
    with pytest.raises(BrowseError) as e:
        run(browse.browse("alfresco", CFG, None, None, 10))
    assert e.value.status_code == 502 and "could not reach" in str(e.value)
