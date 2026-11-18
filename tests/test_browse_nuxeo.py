"""Nuxeo source browser (flexible-graphrag/browse/nuxeo.py) over a mocked Nuxeo REST API: root and
child listing, paging by currentPageIndex, the auth headers, the guards and error mapping."""

import asyncio
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flexible-graphrag"))

import browse  # noqa: E402
from browse import BrowseError  # noqa: E402
from browse import nuxeo as nx  # noqa: E402

BASE = "http://nx:8081/nuxeo"
CFG = {"url": BASE + "/", "auth_method": "basic", "username": "u", "password": "p"}


def run(coro):
    return asyncio.run(coro)


def doc(uid, path, folder=False, **extra):
    d = {"uid": uid, "path": path, "title": path.rsplit("/", 1)[-1], "facets": ["Folderish"] if folder else [],
         "lastModified": "2026-11-01T10:00:00.000Z", "isProxy": False, "isTrashed": False}
    if not folder:
        d["properties"] = {"file:content": {"length": "12", "mime-type": "application/pdf"}}
    d.update(extra)
    return d


@pytest.fixture
def nuxeo(monkeypatch):
    """A fake Nuxeo: (path -> (status, json)); records requests."""
    routes, seen = {}, []

    def handler(request: httpx.Request):
        seen.append(request)
        key = request.url.path
        if key in routes:
            status, body = routes[key]
            return httpx.Response(status, json=body) if body is not None else httpx.Response(status)
        return httpx.Response(404, json={"message": "not found"})

    real = httpx.AsyncClient
    monkeypatch.setattr(nx.httpx, "AsyncClient",
                        lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))
    routes["/nuxeo/api/v1/path/"] = (200, {"uid": "root", "path": "/"})
    routes["/nuxeo/api/v1/id/root/@children"] = (200, {"isNextPageAvailable": False, "entries": [
        doc("dd", "/default-domain", folder=True)]})
    return routes, seen


def test_root_resolves_its_uid_then_lists(nuxeo):
    routes, seen = nuxeo
    top = run(browse.browse("nuxeo", CFG, None, None, 50))
    assert [(i.id, i.path, i.kind) for i in top.items] == [("dd", "/default-domain", "folder")]
    assert [r.url.path for r in seen] == ["/nuxeo/api/v1/path/", "/nuxeo/api/v1/id/root/@children"]
    assert seen[-1].url.params["pageSize"] == "50" and seen[-1].headers["properties"] == "dublincore,file"
    assert seen[-1].headers["authorization"].startswith("Basic ")


def test_children_folders_first_hidden_left_out(nuxeo):
    routes, _ = nuxeo
    routes["/nuxeo/api/v1/id/ws/@children"] = (200, {"isNextPageAvailable": False, "entries": [
        doc("f1", "/default-domain/workspaces/GraphRAG/z.pdf"),
        doc("s1", "/default-domain/workspaces/GraphRAG/Sub", folder=True),
        doc("t1", "/default-domain/workspaces/GraphRAG/gone.pdf", isTrashed=True),
        doc("p1", "/default-domain/workspaces/GraphRAG/proxy.pdf", isProxy=True),
        doc("h1", "/default-domain/workspaces/GraphRAG/.hidden", facets=["HiddenInNavigation"]),
    ]})
    sub = run(browse.browse("nuxeo", CFG, {"id": "ws", "path": "/default-domain/workspaces/GraphRAG"}, None, 50))
    assert [(i.id, i.kind, i.size, i.mime_type) for i in sub.items] == [
        ("s1", "folder", None, None), ("f1", "file", 12, "application/pdf")]
    assert sub.items[1].path == "/default-domain/workspaces/GraphRAG/z.pdf"


def test_paging_by_page_index(nuxeo):
    routes, seen = nuxeo
    routes["/nuxeo/api/v1/id/ws/@children"] = (200, {"isNextPageAvailable": True, "entries": [doc("a", "/w/a")]})
    first = run(browse.browse("nuxeo", CFG, {"id": "ws"}, None, 1))
    assert first.next_page_token == "1" and seen[-1].url.params["currentPageIndex"] == "0"
    routes["/nuxeo/api/v1/id/ws/@children"] = (200, {"isNextPageAvailable": False, "entries": [doc("b", "/w/b")]})
    second = run(browse.browse("nuxeo", CFG, {"id": "ws"}, first.next_page_token, 5000))
    assert second.next_page_token is None and seen[-1].url.params["currentPageIndex"] == "1"
    assert seen[-1].url.params["pageSize"] == "1000"


def test_sign_in_token_header(nuxeo):
    _, seen = nuxeo
    run(browse.browse("nuxeo", {"url": BASE, "auth_method": "token", "token": "tok", "username": "ann"},
                      None, None, 10))
    assert seen[-1].headers["x-authentication-token"] == "tok" and "authorization" not in seen[-1].headers


def test_token_mode_without_token_uses_the_password(nuxeo):
    _, seen = nuxeo
    run(browse.browse("nuxeo", dict(CFG, auth_method="token"), None, None, 10))
    assert seen[-1].headers["authorization"].startswith("Basic ")


def test_oauth2_bearer(nuxeo):
    _, seen = nuxeo
    run(browse.browse("nuxeo", {"url": BASE, "auth_method": "oauth2", "oauth2": {"access_token": "at"}},
                      None, None, 10))
    assert seen[-1].headers["authorization"] == "Bearer at"


def test_guards():
    with pytest.raises(BrowseError) as e:
        run(browse.browse("nuxeo", {"url": BASE, "username": "u"}, None, None, 10))
    assert "password" in str(e.value)
    with pytest.raises(BrowseError) as e:
        run(browse.browse("nuxeo", {"url": BASE, "auth_method": "oauth2", "oauth2": {"client_id": "c"}},
                          None, None, 10))
    assert "access token" in str(e.value)
    with pytest.raises(BrowseError) as e:
        run(browse.browse("nuxeo", {"username": "u", "password": "p"}, None, None, 10))
    assert "URL" in str(e.value)


@pytest.mark.parametrize("status,expected", [(401, 401), (302, 401), (403, 403), (404, 404), (500, 502)])
def test_errors_map_status(nuxeo, status, expected):
    routes, _ = nuxeo
    routes["/nuxeo/api/v1/id/ws/@children"] = (status, None)
    with pytest.raises(BrowseError) as e:
        run(browse.browse("nuxeo", CFG, {"id": "ws", "path": "/w"}, None, 10))
    assert e.value.status_code == expected


def test_login_page_instead_of_json_is_a_sign_in_failure(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(nx.httpx, "AsyncClient", lambda *a, **k: real(
        *a, transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>login</html>")), **k))
    with pytest.raises(BrowseError) as e:
        run(browse.browse("nuxeo", CFG, {"id": "ws"}, None, 10))
    assert e.value.status_code == 401


def test_unreachable(monkeypatch):
    real = httpx.AsyncClient

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)
    monkeypatch.setattr(nx.httpx, "AsyncClient",
                        lambda *a, **k: real(*a, transport=httpx.MockTransport(refuse), **k))
    with pytest.raises(BrowseError) as e:
        run(browse.browse("nuxeo", CFG, None, None, 10))
    assert e.value.status_code == 502 and "could not reach" in str(e.value)
