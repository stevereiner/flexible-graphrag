"""Google Drive browse (flexible-graphrag/browse/google_drive.py) over a fake Drive v3 service: the
root (My Drive + shared with me + shared drives), folders first, paging, what is left out, the
credentials guard and error mapping."""

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flexible-graphrag"))

import browse  # noqa: E402
from browse import BrowseError  # noqa: E402
from browse import google_drive as gd  # noqa: E402

CFG = {"credentials": json.dumps({"type": "service_account"})}


def run(coro):
    return asyncio.run(coro)


class _Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class _Files:
    """files().list over folder id -> pages of raw files; the page token is the page index."""

    def __init__(self, tree):
        self.tree, self.calls = tree, []

    def list(self, q, fields, pageSize, pageToken, includeItemsFromAllDrives, supportsAllDrives, orderBy):
        self.calls.append({"q": q, "pageSize": pageSize, "pageToken": pageToken,
                           "allDrives": includeItemsFromAllDrives and supportsAllDrives})
        key = q.split("'")[1] if q.startswith("'") else "ROOT"
        pages = self.tree[key]
        index = int(pageToken or 0)

        def result():
            out = {"files": pages[index]}
            if index + 1 < len(pages):
                out["nextPageToken"] = str(index + 1)
            return out
        return _Req(result)


class _Drives:
    def __init__(self, drives):
        self.drives, self.calls = drives, 0

    def list(self, pageSize, fields):
        self.calls += 1
        return _Req(lambda: {"drives": self.drives})


class _Service:
    def __init__(self, tree, drives):
        self._files, self._drives = _Files(tree), _Drives(drives)

    def files(self):
        return self._files

    def drives(self):
        return self._drives


def f(id_, name, mime="application/pdf", size="10"):
    return {"id": id_, "name": name, "mimeType": mime, "size": size, "modifiedTime": "2026-11-01T10:00:00.000Z",
            "webViewLink": f"https://drive.google.com/{id_}"}


def folder(id_, name):
    return {"id": id_, "name": name, "mimeType": gd.FOLDER}


@pytest.fixture
def drive(monkeypatch):
    service = _Service({
        "ROOT": [[f("f1", "zeta.pdf"), folder("d1", "Reports")], [folder("d2", "Archive")]],
        "d1": [[f("f2", "notes", "application/vnd.google-apps.document", size=None),
                f("f3", "survey", "application/vnd.google-apps.form", size=None),
                f("f4", "link", "application/vnd.google-apps.shortcut", size=None),
                folder("d3", "2024")]],
    }, drives=[{"id": "0AShared", "name": "Team"}])
    monkeypatch.setattr(gd, "_service", lambda config: service)
    return service


def test_root_lists_my_drive_shared_with_me_and_shared_drives(drive):
    top = run(browse.browse("google_drive", CFG, None, None, 100))
    assert [(i.id, i.kind) for i in top.items] == [("d1", "folder"), ("0AShared", "folder"), ("f1", "file")]
    assert top.next_page_token == "1"
    call = drive.files().calls[-1]
    assert "sharedWithMe" in call["q"] and "'root' in parents" in call["q"] and call["allDrives"]
    pdf = next(i for i in top.items if i.id == "f1")
    assert pdf.size == 10 and pdf.mime_type == "application/pdf" and pdf.web_url.endswith("f1")


def test_paging_lists_shared_drives_only_once(drive):
    second = run(browse.browse("google_drive", CFG, None, "1", 100))
    assert [i.name for i in second.items] == ["Archive"] and second.next_page_token is None
    assert drive.drives().calls == 0 and drive.files().calls[-1]["pageToken"] == "1"


def test_folder_keeps_exported_google_docs_only(drive):
    sub = run(browse.browse("google_drive", CFG, {"id": "d1", "path": "Reports"}, None, 5000))
    # a Google Doc is exported by the ingest (docx); forms / shortcuts can't be read
    assert [(i.id, i.path, i.kind) for i in sub.items] == [
        ("d3", "Reports/2024", "folder"), ("f2", "Reports/notes", "file")]
    assert drive.files().calls[-1]["q"] == "'d1' in parents and trashed = false"
    assert drive.files().calls[-1]["pageSize"] == 1000  # Drive's own maximum


def test_folder_id_is_checked_before_it_goes_in_the_query(drive):
    with pytest.raises(BrowseError) as e:
        run(browse.browse("google_drive", CFG, {"id": "x' or name contains '"}, None, 10))
    assert e.value.status_code == 400


def test_needs_service_account_credentials(tmp_path):
    with pytest.raises(BrowseError) as e:
        gd._service_account_key({})
    assert "service account credentials" in str(e.value)
    with pytest.raises(BrowseError) as e:
        gd._service_account_key({"credentials": "{not json"})
    assert "not valid JSON" in str(e.value)
    oauth = tmp_path / "client.json"
    oauth.write_text(json.dumps({"installed": {"client_id": "x"}}))
    with pytest.raises(BrowseError) as e:
        gd._service_account_key({"credentials_path": str(oauth)})
    assert "service account key" in str(e.value)
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps({"type": "service_account", "client_email": "a@b"}))
    assert gd._service_account_key({"credentials_path": str(sa)})["client_email"] == "a@b"
    # the pasted JSON wins over the key file, as in the ingest
    assert gd._service_account_key({"credentials": json.dumps({"type": "service_account", "k": 1}),
                                    "credentials_path": str(sa)})["k"] == 1


def test_errors_map_status():
    import httplib2
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    def http(status):
        return HttpError(httplib2.Response({"status": status}), b'{"error": {"message": "m"}}')
    assert gd._error(http(404)).status_code == 404
    assert gd._error(http(403)).status_code == 403
    assert gd._error(http(401)).status_code == 401
    assert gd._error(http(500)).status_code == 502
    assert gd._error(RefreshError("invalid_grant: Invalid JWT Signature.")).status_code == 401
