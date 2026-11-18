"""API token, CORS origins list parsing, runtime ingest folders, filesystem source id.

Pure unit tests (api_security.py, openarch/source_system.py) plus a small FastAPI app with the same
middleware order as main.py: no live backend, no databases.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "flexible-graphrag"))

from api_security import (  # noqa: E402
    RuntimeIngestPaths, parse_list, supplied_token, token_matches, token_required,
)


@pytest.mark.parametrize("path,method,expected", [
    ("/api/ingest", "POST", True),
    ("/api/search", "POST", True),
    ("/api/ingest-allowed-paths", "PUT", True),
    ("/api/auth/microsoft/result", "GET", True),       # hands out the sign-in token: needs ours
    ("/api/auth/box/handoff", "POST", True),
    ("/api/auth/box/handoff/result", "POST", True),
    ("/api/auth/alfresco/login", "POST", True),
    ("/api", "GET", True),
    ("/api/ingest", "OPTIONS", False),                 # CORS preflight
    ("/api/health", "GET", False),
    ("/api/auth/microsoft/popup", "GET", False),       # opened by the browser itself
    ("/api/auth/microsoft/callback", "POST", False),
    ("/api/auth/box/callback", "GET", False),
    ("/api/auth/box/handoff/abc123", "GET", False),
    ("/api/auth/box/handoff/abc123/continue", "GET", False),
    ("/", "GET", False),
    ("/docs", "GET", False),
    ("/apix", "GET", False),
])
def test_token_required(path, method, expected):
    assert token_required(path, method, "secret") is expected


def test_no_token_configured_checks_nothing():
    assert token_required("/api/ingest", "POST", None) is False
    assert token_required("/api/ingest", "POST", "") is False


def test_supplied_token_and_match():
    assert supplied_token({"x-api-token": " s3cret "}) == "s3cret"
    assert supplied_token({"authorization": "Bearer s3cret"}) == "s3cret"
    assert supplied_token({"authorization": "Basic abc"}) is None
    assert supplied_token({}) is None
    assert token_matches("s3cret", "s3cret")
    assert not token_matches("s3cre", "s3cret")
    assert not token_matches(None, "s3cret")
    assert not token_matches("", "s3cret")


def test_parse_list():
    assert parse_list(None) is None
    assert parse_list("") is None
    assert parse_list("http://a, http://b ,") == ["http://a", "http://b"]
    assert parse_list('["http://a", "tauri://localhost"]') == ["http://a", "tauri://localhost"]
    assert parse_list(["x"]) == ["x"]


def test_runtime_ingest_paths(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()
    store = RuntimeIngestPaths()
    kept, rejected = store.set([str(folder), str(folder), "relative/dir", str(tmp_path / "missing"), ""])
    assert kept == [str(folder.resolve())]
    assert rejected == ["relative/dir", str(tmp_path / "missing"), ""]
    assert store.get() == kept
    store.set([])
    assert store.get() == []


def test_runtime_paths_extend_the_ingest_check(tmp_path):
    """A runtime folder is honored by the same check /api/ingest uses (GHSA-2558-gvg9-whcx)."""
    from main import disallowed_ingest_paths
    folder = tmp_path / "vault"
    folder.mkdir()
    (folder / "a.md").write_text("x")
    store = RuntimeIngestPaths()
    store.set([str(folder)])
    assert disallowed_ingest_paths([str(folder / "a.md")], store.get()) == []
    assert disallowed_ingest_paths([str(tmp_path)], store.get()) == [str(tmp_path)]


def test_filesystem_source_id(monkeypatch):
    import socket
    from openarch.source_system import source_system_for
    monkeypatch.delenv("FILESYSTEM_SOURCE_ID", raising=False)
    assert source_system_for("filesystem", {}) == ("filesystem", socket.gethostname().lower())
    monkeypatch.setenv("FILESYSTEM_SOURCE_ID", " my-laptop-7f3a ")
    assert source_system_for("filesystem", {}) == ("filesystem", "my-laptop-7f3a")
    assert source_system_for("upload", {}) == ("filesystem", "my-laptop-7f3a")


def test_middleware_order_keeps_cors_headers_on_401():
    """Same order as main.py: token middleware first, CORS added after it (= outer layer)."""
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.middleware("http")
    async def _require_api_token(request: Request, call_next):
        if token_required(request.url.path, request.method, "s3cret") and not token_matches(
                supplied_token(request.headers), "s3cret"):
            return JSONResponse(status_code=401, content={"detail": "API token required"})
        return await call_next(request)

    app.add_middleware(CORSMiddleware, allow_origins=["http://tauri.localhost"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.post("/api/search")
    async def search():
        return {"ok": True}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    c = TestClient(app)
    origin = {"Origin": "http://tauri.localhost"}
    r = c.post("/api/search", headers=origin)
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == "http://tauri.localhost"
    assert c.post("/api/search", headers={**origin, "X-API-Token": "s3cret"}).json() == {"ok": True}
    pre = c.options("/api/search", headers={**origin, "Access-Control-Request-Method": "POST",
                                            "Access-Control-Request-Headers": "x-api-token"})
    assert pre.status_code == 200
    assert c.get("/api/health").status_code == 200
    # another origin gets no CORS grant, so its page can't read the answer
    other = c.post("/api/search", headers={"Origin": "http://evil.example", "X-API-Token": "s3cret"})
    assert "access-control-allow-origin" not in other.headers
