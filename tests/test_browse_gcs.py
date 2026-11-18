"""GCS source browser (flexible-graphrag/browse/gcs.py) over a fake storage client: prefixes as
folders, placeholder objects left out, page tokens, the bucket / credentials guards, error mapping."""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flexible-graphrag"))

import browse  # noqa: E402
from browse import BrowseError  # noqa: E402
from browse import gcs as bg  # noqa: E402

CFG = {"bucket_name": "kg", "credentials": '{"type": "service_account"}'}


def run(coro):
    return asyncio.run(coro)


class _Blob:
    def __init__(self, name, size=3):
        self.name, self.size, self.updated, self.content_type = name, size, None, "text/plain"


class _Page(list):
    def __init__(self, blobs, prefixes):
        super().__init__(blobs)
        self.prefixes = set(prefixes)


class _Client:
    """list_blobs over a flat name list, with delimiter / page_size / page_token (an index)."""

    def __init__(self, names):
        self.names, self.calls = sorted(names), []

    def list_blobs(self, bucket, prefix=None, delimiter=None, page_size=None, page_token=None):
        self.calls.append((bucket, prefix, page_size, page_token))
        prefix = prefix or ""
        rows = []
        for n in self.names:
            if not n.startswith(prefix):
                continue
            rest = n[len(prefix):]
            if delimiter in rest[:-1] or (rest.endswith("/") and rest):
                sub = prefix + rest.split(delimiter, 1)[0] + delimiter
                if not rows or rows[-1] != ("p", sub):
                    rows.append(("p", sub))
            else:
                rows.append(("o", n))
        start = int(page_token or 0)
        chunk = rows[start:start + page_size]
        more = start + page_size < len(rows)
        page = _Page([_Blob(v) for t, v in chunk if t == "o"], [v for t, v in chunk if t == "p"])
        return type("It", (), {"pages": iter([page]), "next_page_token": str(start + page_size) if more else None})()


@pytest.fixture
def gcs(monkeypatch):
    fake = _Client(["readme.txt", "docs/", "docs/a.pdf", "docs/2024/b.pdf", "zeta/c.txt"])
    monkeypatch.setattr(bg, "_client_and_bucket", lambda config: (fake, "kg"))
    return fake


def test_folders_are_prefixes(gcs):
    top = run(browse.browse("gcs", CFG, None, None, 100))
    assert [(i.kind, i.id, i.name) for i in top.items] == [
        ("folder", "docs/", "docs"), ("folder", "zeta/", "zeta"), ("file", "readme.txt", "readme.txt")]
    assert gcs.calls[-1][1] is None  # the bucket root: no prefix
    sub = run(browse.browse("gcs", CFG, {"id": "docs/", "path": "docs/"}, None, 100))
    # the "docs/" placeholder object is left out; folder paths are what `prefix` takes
    assert [(i.kind, i.path) for i in sub.items] == [("folder", "docs/2024/"), ("file", "docs/a.pdf")]
    run(browse.browse("gcs", CFG, {"id": "docs"}, None, 100))
    assert gcs.calls[-1][1] == "docs/"  # a folder is opened by its prefix


def test_pages_by_token(gcs):
    first = run(browse.browse("gcs", CFG, None, None, 2))
    assert first.next_page_token == "2" and gcs.calls[-1] == ("kg", None, 2, None)
    second = run(browse.browse("gcs", CFG, None, first.next_page_token, 5000))
    assert [i.name for i in second.items] == ["zeta"] and second.next_page_token is None
    assert gcs.calls[-1] == ("kg", None, 1000, "2")  # the API's own page maximum


def test_needs_bucket_and_valid_json():
    with pytest.raises(BrowseError) as e:
        bg._client_and_bucket({"bucket_name": " ", "credentials": "{}"})
    assert "bucket" in str(e.value)
    with pytest.raises(BrowseError) as e:
        bg._client_and_bucket({"bucket_name": "kg", "credentials": "{not json"})
    assert "not valid JSON" in str(e.value)
    with pytest.raises(BrowseError) as e:  # a key without its fields
        bg._client_and_bucket({"bucket_name": "kg", "credentials": '{"type": "service_account"}'})
    assert e.value.status_code == 400


def test_errors_map_status():
    from google.api_core import exceptions as gexc
    from google.auth.exceptions import RefreshError
    assert bg._error(RefreshError("invalid_grant"), "kg").status_code == 401
    assert bg._error(gexc.NotFound("x"), "kg").status_code == 404
    assert bg._error(gexc.Forbidden("x"), "kg").status_code == 403
    assert bg._error(gexc.BadRequest("x"), "kg").status_code == 400
    assert bg._error(gexc.InternalServerError("x"), "kg").status_code == 502
