"""Azure Blob source browser (flexible-graphrag/browse/azure_blob.py) over a fake ContainerClient:
prefixes as folders, directory placeholders left out, continuation paging, guards, error mapping."""

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flexible-graphrag"))

import browse  # noqa: E402
from browse import BrowseError  # noqa: E402
from browse import azure_blob as ab  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class _Prefix:
    def __init__(self, name):
        self.name = name


def _blob(name, size=3, metadata=None):
    return SimpleNamespace(name=name, size=size, metadata=metadata or {}, last_modified=None,
                           content_settings=SimpleNamespace(content_type="text/plain"))


class _Pages:
    def __init__(self, rows, size, token):
        self.rows, self.size, self.start = rows, size, int(token or 0)
        self.continuation_token = None

    def __iter__(self):
        return self

    def __next__(self):
        chunk = self.rows[self.start:self.start + self.size]
        more = self.start + self.size < len(self.rows)
        self.continuation_token = str(self.start + self.size) if more else None
        return iter(chunk)


class _Container:
    """walk_blobs(delimiter="/") over a flat blob list, in name order (prefixes merged in)."""

    container_name = "kg"

    def __init__(self, blobs):
        self.blobs, self.calls = blobs, []

    def walk_blobs(self, name_starts_with=None, delimiter="/", include=None, results_per_page=None):
        prefix = name_starts_with or ""
        self.calls.append((prefix, results_per_page, include))
        rows, seen = [], set()
        for b in sorted(self.blobs, key=lambda b: b.name):
            if not b.name.startswith(prefix):
                continue
            rest = b.name[len(prefix):]
            if delimiter in rest:
                sub = prefix + rest.split(delimiter, 1)[0] + delimiter
                if sub not in seen:
                    seen.add(sub)
                    rows.append(_Prefix(sub))
            else:
                rows.append(b)
        outer = self

        class _Paged:
            def by_page(self, continuation_token=None):
                outer.calls[-1] += (continuation_token,)
                return _Pages(rows, results_per_page, continuation_token)
        return _Paged()


@pytest.fixture
def container(monkeypatch):
    import azure.storage.blob as blob_module
    fake = _Container([
        _blob("readme.txt"), _blob("docs/a.pdf"), _blob("docs/2024/b.pdf"), _blob("zeta/c.txt"),
        _blob("docs/2024", size=0, metadata={"hdi_isfolder": "true"}),  # Storage Explorer folder marker
    ])
    monkeypatch.setattr(blob_module, "BlobPrefix", _Prefix)
    monkeypatch.setattr(ab, "_container", lambda config: fake)
    return fake


CFG = {"container_name": "kg", "account_url": "https://acct.blob.core.windows.net", "account_key": "a2V5"}


def test_registered():
    assert "azure_blob" in browse.supported_sources()


def test_prefixes_are_folders(container):
    top = run(browse.browse("azure_blob", CFG, None, None, 100))
    assert [(i.kind, i.id, i.name) for i in top.items] == [
        ("folder", "docs/", "docs"), ("folder", "zeta/", "zeta"), ("file", "readme.txt", "readme.txt")]
    sub = run(browse.browse("azure_blob", CFG, {"id": "docs/", "path": "docs/"}, None, 100))
    # the hdi_isfolder marker blob is left out; paths are what `prefix` / `blob` take
    assert [(i.kind, i.path) for i in sub.items] == [("folder", "docs/2024/"), ("file", "docs/a.pdf")]
    run(browse.browse("azure_blob", CFG, {"id": "docs"}, None, 100))
    assert container.calls[-1][0] == "docs/"  # a folder is opened by its prefix
    assert container.calls[-1][2] == ["metadata"]


def test_pages_by_continuation_token(container):
    first = run(browse.browse("azure_blob", CFG, None, None, 2))
    assert first.next_page_token == "2" and container.calls[-1][1] == 2
    second = run(browse.browse("azure_blob", CFG, None, first.next_page_token, 100000))
    # the service pages in name order (docs/, readme.txt | zeta/); each page is sorted folders first
    assert [i.name for i in first.items] == ["docs", "readme.txt"]
    assert [i.name for i in second.items] == ["zeta"] and second.next_page_token is None
    assert container.calls[-1][1] == 5000 and container.calls[-1][3] == "2"


def test_needs_container_and_credentials():
    with pytest.raises(BrowseError) as e:
        ab._container({"account_url": "https://a.blob.core.windows.net", "account_key": "k"})
    assert "container" in str(e.value)
    with pytest.raises(BrowseError) as e:
        ab._container({"container_name": "kg", "account_url": "https://a.blob.core.windows.net"})
    assert "account key" in str(e.value)
    with pytest.raises(BrowseError) as e:
        ab._container({"container_name": "kg", "connection_string": "not-a-connection-string"})
    assert e.value.status_code == 400


def test_errors_map_status():
    from azure.core.exceptions import (ClientAuthenticationError, HttpResponseError, ResourceNotFoundError,
                                       ServiceRequestError)

    assert ab._error(ClientAuthenticationError("bad key"), "kg").status_code == 401
    assert ab._error(ResourceNotFoundError("gone"), "kg").status_code == 404
    forbidden = HttpResponseError("denied")
    forbidden.status_code = 403
    assert ab._error(forbidden, "kg").status_code == 403
    assert ab._error(ServiceRequestError("dns"), "kg").status_code == 502
