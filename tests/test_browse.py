"""Source browser backend (flexible-graphrag/browse/): dispatch, SharePoint / OneDrive listing over a
mocked Microsoft Graph, paging, and the guards (missing credentials, foreign page tokens)."""

import asyncio
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flexible-graphrag"))

import browse  # noqa: E402
from browse import BrowseError  # noqa: E402
from browse import msgraph as sp  # noqa: E402  (the Graph code SharePoint and OneDrive share)

CFG = {"client_id": "c", "client_secret": "s", "tenant_id": "t", "site_name": "kg"}
BOX_CFG = {"client_id": "c", "client_secret": "s", "user_id": "u"}  # app access (user): what Box is run with
OD_CFG = {"client_id": "c", "client_secret": "s", "tenant_id": "t", "user_principal_name": "ann@x.com"}
GRAPH = sp.GRAPH


def run(coro):
    return asyncio.run(coro)


def folder(id_, name, parent="/drive/root:"):
    return {"id": id_, "name": name, "folder": {"childCount": 1}, "parentReference": {"path": parent},
            "lastModifiedDateTime": "2026-11-01T10:00:00Z", "webUrl": f"https://x/{name}"}


def file(id_, name, parent="/drive/root:", size=10):
    return {"id": id_, "name": name, "size": size, "file": {"mimeType": "text/plain"},
            "parentReference": {"path": parent}}


@pytest.fixture
def graph(monkeypatch):
    """A fake Graph: routes -> JSON; records the requests."""
    routes = {}
    seen = []

    def handler(request: httpx.Request):
        url = str(request.url)
        seen.append(url)
        assert request.headers["authorization"] == "Bearer tok"
        for prefix, body in routes.items():
            if url.startswith(prefix):
                status, payload = body if isinstance(body, tuple) else (200, body)
                return httpx.Response(status, json=payload)
        return httpx.Response(404, json={"error": {"code": "itemNotFound", "message": "not found"}})

    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    async def token(_config, _label):
        return "tok"

    monkeypatch.setattr(sp.httpx, "AsyncClient", client)
    monkeypatch.setattr(sp, "access_token", token)
    routes[f"{GRAPH}/sites/root:/sites/kg"] = {"id": "site1"}
    return routes, seen


def test_unsupported_source():
    with pytest.raises(BrowseError) as e:
        run(browse.browse("ftp", {}, None, None, 10))
    assert e.value.status_code == 404
    assert {"sharepoint", "onedrive"} <= set(browse.supported_sources())


def test_missing_credentials():
    with pytest.raises(BrowseError) as e:
        run(sp.access_token({"client_id": "c", "tenant_id": " "}, "OneDrive"))
    assert "client_secret" in str(e.value) and "tenant_id" in str(e.value) and "OneDrive" in str(e.value)


def test_item_paths():
    assert sp.item(folder("1", "Reports")).path == "Reports"
    sub = sp.item(file("2", "a.txt", parent="/drives/b!x/root:/Reports/2024"))
    assert sub.path == "Reports/2024/a.txt" and sub.kind == "file" and sub.size == 10
    assert sp.item(folder("3", "F", parent="/drive/root:/Reports")).size is None
    # Graph percent-encodes parentReference.path
    assert sp.item(folder("4", "Sub", parent="/drive/root:/My%20Docs")).path == "My Docs/Sub"


def test_root_listing_resolves_site_and_sorts(graph):
    routes, seen = graph
    routes[f"{GRAPH}/sites/site1/drive/root/children"] = {
        "value": [file("f1", "b.txt"), folder("d2", "zeta"), folder("d1", "Alpha")]}
    result = run(browse.browse("sharepoint", CFG, None, None, 50))
    assert [i.name for i in result.items] == ["Alpha", "zeta", "b.txt"]
    assert result.next_page_token is None
    assert "$top=50" in seen[-1]


def test_child_listing_and_site_id(graph):
    routes, seen = graph
    routes[f"{GRAPH}/sites/given/drive/items/d1/children"] = {
        "value": [folder("d3", "Sub", parent="/drive/root:/Alpha")]}
    cfg = dict(CFG, site_id="given")
    result = run(browse.browse("sharepoint", cfg, {"id": "d1", "path": "Alpha"}, None, 200))
    assert [(i.path, i.kind) for i in result.items] == [("Alpha/Sub", "folder")]
    assert not any("root:/sites" in u for u in seen)  # site_id given: no lookup


def test_paging(graph):
    routes, _ = graph
    next_link = f"{GRAPH}/sites/site1/drive/root/children?$skiptoken=abc"
    routes[next_link] = {"value": [folder("d9", "Last")]}
    routes[f"{GRAPH}/sites/site1/drive/root/children?$top"] = {
        "value": [folder("d1", "First")], "@odata.nextLink": next_link}
    first = run(browse.browse("sharepoint", CFG, None, None, 1))
    assert first.next_page_token == next_link
    second = run(browse.browse("sharepoint", CFG, None, first.next_page_token, 1))
    assert [i.name for i in second.items] == ["Last"]


def test_foreign_page_token_refused(graph):
    with pytest.raises(BrowseError):
        run(browse.browse("sharepoint", CFG, None, "https://evil.example/steal", 10))


def test_site_name_search_fallback(graph):
    routes, _ = graph
    routes.pop(f"{GRAPH}/sites/root:/sites/kg")
    routes[f"{GRAPH}/sites?search=kg"] = {"value": [{"id": "other", "name": "kg2"}, {"id": "s2", "name": "KG"}]}
    routes[f"{GRAPH}/sites/s2/drive/root/children"] = {"value": []}
    assert run(browse.browse("sharepoint", CFG, None, None, 10)).items == []


def test_onedrive_lists_the_users_drive(graph):
    routes, seen = graph
    routes[f"{GRAPH}/users/ann@x.com/drive/root/children"] = {
        "value": [file("f1", "a.txt"), folder("d1", "Documents")]}
    routes[f"{GRAPH}/users/ann@x.com/drive/items/d1/children"] = {
        "value": [folder("d2", "Reports", parent="/drive/root:/Documents")]}
    top = run(browse.browse("onedrive", OD_CFG, None, None, 100))
    assert [(i.name, i.kind) for i in top.items] == [("Documents", "folder"), ("a.txt", "file")]
    sub = run(browse.browse("onedrive", OD_CFG, {"id": "d1", "path": "Documents"}, None, 100))
    assert [i.path for i in sub.items] == ["Documents/Reports"]
    assert not any("/sites" in u for u in seen)


def test_onedrive_needs_the_user():
    with pytest.raises(BrowseError) as e:
        run(browse.browse("onedrive", dict(OD_CFG, user_principal_name=" "), None, None, 10))
    assert "user principal name" in str(e.value)


class _BoxEntry:
    def __init__(self, id_, name, kind, size=None):
        self.id, self.name, self.type, self.size = id_, name, kind, size
        self.modified_at = None


class _BoxFolders:
    """folders.get_folder_items over a dict folder id -> pages of entries (marker = page index)."""

    def __init__(self, tree):
        self.tree, self.calls = tree, []

    def get_folder_items(self, folder_id, fields=None, usemarker=None, marker=None, limit=None):
        self.calls.append((folder_id, marker, limit, usemarker))
        pages = self.tree[folder_id]
        index = int(marker or 0)
        nxt = str(index + 1) if index + 1 < len(pages) else None
        return type("Items", (), {"entries": pages[index], "next_marker": nxt})()


@pytest.fixture
def box(monkeypatch):
    from browse import box as bx
    folders = _BoxFolders({
        "0": [[_BoxEntry("10", "zeta.txt", "file", 5), _BoxEntry("11", "Docs", "folder")],
              [_BoxEntry("12", "link", "web_link")]],
        "11": [[_BoxEntry("13", "a.pdf", "file", 7)]],
    })
    seen = []

    def client(config):
        seen.append(config)
        return type("Client", (), {"folders": folders})()
    monkeypatch.setattr(bx, "_client", client)
    return folders, seen


def test_box_lists_folders_first_and_pages_by_marker(box):
    folders, _ = box
    first = run(browse.browse("box", BOX_CFG, None, None, 2))
    assert [(i.id, i.kind, i.path) for i in first.items] == [("11", "folder", "Docs"), ("10", "file", "zeta.txt")]
    assert first.next_page_token == "1" and folders.calls[-1] == ("0", None, 2, True)
    second = run(browse.browse("box", BOX_CFG, None, first.next_page_token, 2))
    assert second.items == [] and second.next_page_token is None  # web links: nothing to ingest


def test_box_child_paths_are_display_paths(box):
    sub = run(browse.browse("box", BOX_CFG, {"id": "11", "path": "Docs"}, None, 5000))
    assert [(i.id, i.path, i.size) for i in sub.items] == [("13", "Docs/a.pdf", 7)]
    assert box[0].calls[-1][2] == 1000  # Box's own page maximum


def test_box_needs_credentials(monkeypatch):
    from browse import box as bx
    monkeypatch.delenv("BOX_CONFIG", raising=False)
    with pytest.raises(BrowseError) as e:
        bx._client({"client_id": "c", "client_secret": "s"})  # CCG without user / enterprise id
    assert "user or enterprise id" in str(e.value)


class _CmisObj:
    def __init__(self, id_, name, base, path=None, size=None, children=()):
        self.properties = {"cmis:objectId": id_, "cmis:name": name, "cmis:baseTypeId": base}
        if path:
            self.properties["cmis:path"] = path
        if size is not None:
            self.properties["cmis:contentStreamLength"] = size
            self.properties["cmis:contentStreamMimeType"] = "application/pdf"
        self.children, self.calls = list(children), []

    def getObjectId(self):
        return self.properties["cmis:objectId"]

    def getChildren(self, maxItems=None, skipCount=None):
        self.calls.append((maxItems, skipCount))
        rows = self.children[skipCount:skipCount + maxItems]
        more = skipCount + maxItems < len(self.children)
        return type("RS", (), {"getResults": lambda s: rows, "hasNext": lambda s: more})()


@pytest.fixture
def cmis(monkeypatch):
    from browse import cmis as cm
    sites = _CmisObj("f-sites", "Sites", "cmis:folder", "/Sites", children=[
        _CmisObj("d1;1.0", "z.pdf", "cmis:document", size=9),
        _CmisObj("f-kg", "kg", "cmis:folder", "/Sites/kg"),
        _CmisObj("p1", "policy", "cmis:policy"),
    ])
    root = _CmisObj("f-root", "", "cmis:folder", "/", children=[sites, _CmisObj("f-dd", "Data Dictionary",
                                                                            "cmis:folder", "/Data Dictionary")])
    objects = {o.getObjectId(): o for o in (root, sites)}
    repo = type("Repo", (), {"getRootFolder": lambda s: root, "getObject": lambda s, i: objects[i]})()
    seen = []
    monkeypatch.setattr(cm, "_repository", lambda config: seen.append(config) or repo)
    return root, sites, seen


CMIS_CFG = {"url": "http://x/atom", "username": "u", "password": "p"}


def test_cmis_root_and_child_paths(cmis):
    top = run(browse.browse("cmis", CMIS_CFG, None, None, 100))
    assert [(i.name, i.path) for i in top.items] == [("Data Dictionary", "/Data Dictionary"), ("Sites", "/Sites")]
    sub = run(browse.browse("cmis", CMIS_CFG, {"id": "f-sites", "path": "/Sites"}, None, 100))
    # folders first; a document's path is its folder's + name (what folder_path takes); policies left out
    assert [(i.id, i.kind, i.path, i.size) for i in sub.items] == [
        ("f-kg", "folder", "/Sites/kg", None), ("d1;1.0", "file", "/Sites/z.pdf", 9)]


def test_cmis_pages_by_skip_count(cmis):
    _, sites, _ = cmis
    first = run(browse.browse("cmis", CMIS_CFG, {"id": "f-sites"}, None, 2))
    assert first.next_page_token == "2" and sites.calls[-1] == (2, 0)
    second = run(browse.browse("cmis", CMIS_CFG, {"id": "f-sites"}, first.next_page_token, 2))
    assert second.items == [] and second.next_page_token is None and sites.calls[-1] == (2, 2)


def test_cmis_needs_url_and_sign_in():
    from browse import cmis as cm
    with pytest.raises(BrowseError) as e:
        cm._repository({"url": "http://x/atom", "username": "u"})
    assert "password" in str(e.value)
    with pytest.raises(BrowseError) as e:
        cm._repository({"username": "u", "password": "p"})
    assert "URL" in str(e.value)


def test_cmis_errors_map_status():
    from browse import cmis as cm
    from cmislib.exceptions import ObjectNotFoundException, PermissionDeniedException
    assert cm._error(PermissionDeniedException(401, "u", "x"), "u").status_code == 401
    assert cm._error(PermissionDeniedException(403, "u", "x"), "u").status_code == 403
    assert cm._error(ObjectNotFoundException(404, "u", "x"), "u").status_code == 404


class _S3:
    """list_objects_v2 over a flat key list, with Delimiter / MaxKeys / ContinuationToken (an index)."""

    def __init__(self, keys):
        self.keys, self.calls = sorted(keys), []

    def list_objects_v2(self, Bucket, Prefix, Delimiter, MaxKeys, ContinuationToken=None):
        self.calls.append((Prefix, MaxKeys, ContinuationToken))
        rows = []  # (sort key, kind, value), as S3 merges prefixes and objects in key order
        for k in self.keys:
            if not k.startswith(Prefix):
                continue
            rest = k[len(Prefix):]
            if Delimiter in rest[:-1] or (rest.endswith("/") and rest):
                sub = Prefix + rest.split(Delimiter, 1)[0] + Delimiter
                if not rows or rows[-1][2] != sub:
                    rows.append((sub, "p", sub))
            else:
                rows.append((k, "o", k))
        start = int(ContinuationToken or 0)
        chunk, more = rows[start:start + MaxKeys], start + MaxKeys < len(rows)
        out = {"CommonPrefixes": [{"Prefix": v} for _, t, v in chunk if t == "p"],
               "Contents": [{"Key": v, "Size": 3} for _, t, v in chunk if t == "o"], "IsTruncated": more}
        if more:
            out["NextContinuationToken"] = str(start + MaxKeys)
        return out


@pytest.fixture
def s3(monkeypatch):
    from browse import s3 as bs
    fake = _S3(["readme.txt", "docs/", "docs/a.pdf", "docs/2024/b.pdf", "zeta/c.txt"])
    monkeypatch.setattr(bs, "_client_and_bucket", lambda config: (fake, "kg"))
    return fake


S3_CFG = {"bucket_name": "kg", "access_key": "a", "secret_key": "s", "region_name": "us-east-2"}


def test_s3_folders_are_prefixes(s3):
    top = run(browse.browse("s3", S3_CFG, None, None, 100))
    assert [(i.kind, i.id, i.name) for i in top.items] == [
        ("folder", "docs/", "docs"), ("folder", "zeta/", "zeta"), ("file", "readme.txt", "readme.txt")]
    sub = run(browse.browse("s3", S3_CFG, {"id": "docs/", "path": "docs/"}, None, 100))
    # the console's "docs/" placeholder object is left out; paths are what `prefix` takes
    assert [(i.kind, i.path) for i in sub.items] == [("folder", "docs/2024/"), ("file", "docs/a.pdf")]
    run(browse.browse("s3", S3_CFG, {"id": "docs"}, None, 100))
    assert s3.calls[-1][0] == "docs/"  # a folder is opened by its prefix


def test_s3_pages_by_continuation_token(s3):
    first = run(browse.browse("s3", S3_CFG, None, None, 2))
    assert first.next_page_token == "2" and s3.calls[-1] == ("", 2, None)
    second = run(browse.browse("s3", S3_CFG, None, first.next_page_token, 5000))
    assert [i.name for i in second.items] == ["zeta"] and second.next_page_token is None
    assert s3.calls[-1] == ("", 1000, "2")  # S3's own page maximum


def test_s3_needs_the_bucket(monkeypatch):
    from browse import s3 as bs
    monkeypatch.delenv("S3_BUCKET_NAME", raising=False)
    with pytest.raises(BrowseError) as e:
        bs._client_and_bucket({"bucket_name": " ", "access_key": "a"})
    assert "bucket" in str(e.value)


def test_s3_errors_map_status():
    from botocore.exceptions import ClientError, NoCredentialsError
    from browse import s3 as bs

    def err(code):
        return ClientError({"Error": {"Code": code, "Message": "m"}}, "ListObjectsV2")
    assert bs._error(err("InvalidAccessKeyId"), "kg").status_code == 401
    assert bs._error(err("NoSuchBucket"), "kg").status_code == 404
    assert bs._error(err("AccessDenied"), "kg").status_code == 403
    assert "region" in str(bs._error(err("PermanentRedirect"), "kg"))
    assert bs._error(NoCredentialsError(), "kg").status_code == 401


def test_graph_error_maps_status(graph):
    routes, _ = graph
    routes[f"{GRAPH}/sites/site1/drive/items/gone/children"] = (404, {"error": {"message": "Item not found"}})
    with pytest.raises(BrowseError) as e:
        run(browse.browse("sharepoint", CFG, {"id": "gone"}, None, 10))
    assert e.value.status_code == 404 and "Item not found" in str(e.value)
