"""One adapter per data source: writes the test layout into the source, changes it (edit, move,
rename, delete), and builds the source's ingest / ingest-status bodies.

Every run works in its own container, ``kg-autosync-<run>`` (a folder, prefix or drive folder),
so runs never see each other's leftovers. Inside it (paths are relative to the container):

    sel/   a.txt b.txt m.txt  Sub/c.txt  Sub/Deep/d.txt  Other/e.txt    the selection / sync folder
    out/   o.txt                                                       outside every sync
    rec/   r1.txt  Deep/r2.txt                                         recursive root (repositories)
    graphs/ g1.txt                                                     the graphs scenario

Settings come from the environment or flexible-graphrag/.env (the same ones the backend reads);
the harness never prints their values.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from harness import FG, env, env_json

LAYOUT = {
    "sel/a.txt": "file a: the beacon Corrin guards the northern pass.",
    "sel/b.txt": "file b: not selected.",
    "sel/m.txt": "file m: will be moved out of the sync.",
    "sel/Sub/c.txt": "file c: direct child of Sub.",
    "sel/Sub/Deep/d.txt": "file d: two levels down.",
    "sel/Other/e.txt": "file e: in Other.",
    "out/o.txt": "file o: outside every sync.",
    "rec/r1.txt": "file r1: recursive root.",
    "rec/Deep/r2.txt": "file r2: one level down.",
    "graphs/g1.txt": "file g1: Ada Lovelace worked with Charles Babbage on the Analytical Engine in London.",
}


class Source:
    """What a scenario needs from a data source."""
    name = ""                  # data_source
    tree_type = ""             # the source type segment of the OpenArch tree
    case_insensitive = False   # tree paths compared in lower case (filesystem)
    multiselect = False        # can ingest selected files + folders together
    recursive_option = False   # has a recursive switch (else a folder ingest is always recursive)
    row_actions = False        # item_actions (Processing tab rows)
    uploads = True             # can create new files
    folder_rename = True       # renaming a folder is followed
    single_row = True          # the Processing tab's one row is the whole datasource (not repositories / filesystem)
    timeout = 180              # seconds to wait for a change to be followed

    def __init__(self, run: str):
        self.run = run
        self.base = f"kg-autosync-{run}"

    # the layout --------------------------------------------------------------------------
    def setup(self, tag: str, folders_only: bool = False) -> None:
        for rel in sorted({r.rsplit("/", 1)[0] for r in LAYOUT}, key=len):
            self.mkdir(rel)
        for f in ("sel/Sub", "sel/Sub/Deep", "sel/Other", "rec/Deep"):
            self.mkdir(f)
        if not folders_only:
            for rel, text in LAYOUT.items():
                self.put(rel, f"{tag} {text}")

    def tree_key(self, folder: str) -> str:
        """What precedes a document's path below ``folder`` in its tree path."""
        return f"{self.base}/{folder}"

    # source operations (paths relative to the container) ------------------------------------
    def mkdir(self, rel: str) -> None: ...
    def put(self, rel: str, text: str) -> None: ...
    def delete(self, rel: str) -> None: ...
    def rename(self, rel: str, new_name: str) -> None: ...
    def move(self, rel: str, folder: str) -> None: ...
    def rename_folder(self, rel: str, new_name: str) -> None: ...
    def cleanup(self) -> None: ...

    # requests ----------------------------------------------------------------------------
    def config(self, folder: str, recursive: bool = True, select: Optional[List[str]] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def body(self, folder: str, recursive: bool = True, select: Optional[List[str]] = None,
             sync: bool = True, graph: bool = False, rdf: bool = False) -> Dict[str, Any]:
        b = {"data_source": self.name, "enable_sync": sync, "enabled_graph": graph, "enabled_rdf": rdf}
        b.update(self.config(folder, recursive, select))
        return b

    def status_body(self, rels: List[str], folder: str, recursive: bool = True) -> Dict[str, Any]:
        """Single-row sources: the whole datasource, named by its ingest fields."""
        return {"data_source": self.name, "items": [{"path": f"{self.base}/{folder}"}],
                "source": self.config(folder, recursive)}

    def row(self, rel: str, action: str, **kw) -> Dict[str, Any]:
        """Single-row sources: the datasource's one row (``rel``'s folder)."""
        return dict({"path": f"{self.base}/{_parent(rel) or rel}", "action": action}, **kw)

    def source_auth(self) -> Optional[Dict[str, Any]]:
        return None


def _parent(rel: str) -> str:
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


# ── filesystem ───────────────────────────────────────────────────────────────────────────────

class Filesystem(Source):
    name = tree_type = "filesystem"
    case_insensitive = True
    multiselect = True
    single_row = False
    timeout = 120

    def __init__(self, run: str):
        super().__init__(run)
        self.dir = Path(env("AUTOSYNC_FS_DIR") or Path(tempfile.gettempdir()) / "fg-autosync") / self.base

    def p(self, rel: str) -> Path:
        return self.dir / rel

    def tree_key(self, folder: str) -> str:
        # the tree keeps the path without the drive letter
        return str(self.p(folder)).replace("\\", "/").split(":", 1)[-1].strip("/")

    def mkdir(self, rel):
        self.p(rel).mkdir(parents=True, exist_ok=True)

    def put(self, rel, text):
        self.p(rel).parent.mkdir(parents=True, exist_ok=True)
        self.p(rel).write_text(text, encoding="utf-8")

    def delete(self, rel):
        self.p(rel).unlink()

    def rename(self, rel, new_name):
        self.p(rel).rename(self.p(rel).with_name(new_name))

    def move(self, rel, folder):
        shutil.move(str(self.p(rel)), str(self.p(folder) / Path(rel).name))

    def rename_folder(self, rel, new_name):
        self.p(rel).rename(self.p(rel).with_name(new_name))

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def config(self, folder, recursive=True, select=None):
        return {"paths": [str(self.p(r)) for r in (select or [folder])]}

    def status_body(self, rels, folder, recursive=True):
        return {"data_source": "filesystem", "recursive": True,
                "items": [{"path": str(self.p(r)), "is_folder": self.p(r).is_dir()} for r in rels]}


# ── Alfresco ─────────────────────────────────────────────────────────────────────────────────

class Alfresco(Source):
    name = tree_type = "alfresco"
    multiselect = recursive_option = row_actions = True
    single_row = False
    timeout = 120

    def __init__(self, run: str):
        super().__init__(run)
        self.url = (env("ALFRESCO_URL") or "http://localhost:8080").rstrip("/")
        self.auth = (env("ALFRESCO_USERNAME") or "admin", env("ALFRESCO_PASSWORD") or "admin")
        self.api = f"{self.url}/alfresco/api/-default-/public/alfresco/versions/1"
        self.root = env("AUTOSYNC_ALFRESCO_PARENT") or "Shared"
        self.base_rel = f"{self.root}/{self.base}"
        self.ids: Dict[str, str] = {}

    def path(self, rel: str) -> str:
        return f"/{self.base_rel}/{rel}".rstrip("/")

    def node(self, rel: str) -> Optional[Dict[str, Any]]:
        r = httpx.get(f"{self.api}/nodes/-root-", params={"relativePath": self.path(rel).lstrip("/")},
                      auth=self.auth, timeout=30)
        return r.json()["entry"] if r.status_code == 200 else None

    def id(self, rel: str) -> str:
        if rel not in self.ids:
            self.ids[rel] = self.node(rel)["id"]
        return self.ids[rel]

    def mkdir(self, rel):
        full = self.path(rel).lstrip("/")
        for i in range(len(self.root.split("/")) + 1, len(full.split("/")) + 1):
            part = "/".join(full.split("/")[:i])
            r = httpx.get(f"{self.api}/nodes/-root-", params={"relativePath": part}, auth=self.auth, timeout=30)
            if r.status_code == 200:
                continue
            parent, name = part.rsplit("/", 1)
            httpx.post(f"{self.api}/nodes/-root-/children", auth=self.auth, timeout=30,
                       json={"name": name, "nodeType": "cm:folder", "relativePath": parent}).raise_for_status()
        self.ids[rel] = self.node(rel)["id"]

    def put(self, rel, text):
        e = self.node(rel)
        if e:
            httpx.put(f"{self.api}/nodes/{e['id']}/content", auth=self.auth, content=text.encode(), timeout=30,
                      headers={"Content-Type": "text/plain"}).raise_for_status()
            self.ids[rel] = e["id"]
            return
        parent, name = self.path(rel).lstrip("/").rsplit("/", 1)
        r = httpx.post(f"{self.api}/nodes/-root-/children", auth=self.auth, timeout=30,
                       files={"filedata": (name, text.encode(), "text/plain")},
                       data={"name": name, "nodeType": "cm:content", "relativePath": parent})
        r.raise_for_status()
        self.ids[rel] = r.json()["entry"]["id"]

    def delete(self, rel):
        httpx.delete(f"{self.api}/nodes/{self.id(rel)}", params={"permanent": "true"}, auth=self.auth,
                     timeout=30).raise_for_status()

    def rename(self, rel, new_name):
        httpx.put(f"{self.api}/nodes/{self.id(rel)}", auth=self.auth, json={"name": new_name},
                  timeout=30).raise_for_status()
        self.ids[f"{_parent(rel)}/{new_name}".lstrip("/")] = self.ids.pop(rel)

    rename_folder = rename

    def move(self, rel, folder):
        httpx.post(f"{self.api}/nodes/{self.id(rel)}/move", auth=self.auth, timeout=30,
                   json={"targetParentId": self.id(folder)}).raise_for_status()
        self.ids[f"{folder}/{rel.rsplit('/', 1)[-1]}"] = self.ids.pop(rel)

    def cleanup(self):
        e = httpx.get(f"{self.api}/nodes/-root-", params={"relativePath": self.base_rel}, auth=self.auth, timeout=30)
        if e.status_code == 200:
            httpx.delete(f"{self.api}/nodes/{e.json()['entry']['id']}", params={"permanent": "true"},
                         auth=self.auth, timeout=60)

    def _cred(self) -> Dict[str, Any]:
        return {"url": self.url, "username": self.auth[0], "password": self.auth[1]}

    def config(self, folder, recursive=True, select=None):
        c = dict(self._cred(), path=self.path(folder), recursive=recursive)
        if select:
            c["nodeDetails"] = [{"id": self.id(r), "name": r.rsplit("/", 1)[-1], "path": self.path(r),
                                 "isFile": r.endswith(".txt"), "isFolder": not r.endswith(".txt")} for r in select]
        return {"alfresco_config": c}

    def status_body(self, rels, folder, recursive=True):
        return {"data_source": "alfresco", "url": self.url, "recursive": recursive,
                "items": [{"path": self.path(r), "id": self.id(r), "is_folder": not r.endswith(".txt")} for r in rels]}

    def row(self, rel: str, action: str, **kw) -> Dict[str, Any]:
        return dict({"path": self.path(rel), "id": self.id(rel), "is_folder": not rel.endswith(".txt"),
                     "action": action}, **kw)

    def source_auth(self):
        return {"alfresco": {"url": self.url, "auth_method": "basic", "username": self.auth[0], "password": self.auth[1]}}


# ── Nuxeo ────────────────────────────────────────────────────────────────────────────────────

class Nuxeo(Source):
    name = tree_type = "nuxeo"
    multiselect = recursive_option = row_actions = True
    single_row = False
    timeout = 120

    def __init__(self, run: str):
        super().__init__(run)
        self.url = (env("NUXEO_URL") or "http://localhost:8081/nuxeo").rstrip("/")
        self.auth = (env("NUXEO_USERNAME") or "Administrator", env("NUXEO_PASSWORD") or "Administrator")
        self.api = f"{self.url}/api/v1"
        self.root = env("AUTOSYNC_NUXEO_PARENT") or "default-domain/workspaces"
        self.base_rel = f"{self.root}/{self.base}"
        self.ids: Dict[str, str] = {}

    def path(self, rel: str) -> str:
        return f"/{self.base_rel}/{rel}".rstrip("/")

    def doc(self, path: str) -> Optional[Dict[str, Any]]:
        r = httpx.get(f"{self.api}/path{path}", auth=self.auth, timeout=30)
        return r.json() if r.status_code == 200 else None

    def id(self, rel: str) -> str:
        if rel not in self.ids:
            self.ids[rel] = self.doc(self.path(rel))["uid"]
        return self.ids[rel]

    def _create(self, parent_path: str, name: str, doc_type: str, props: Dict[str, Any]) -> str:
        r = httpx.post(f"{self.api}/path{parent_path}", auth=self.auth, timeout=30, json={
            "entity-type": "document", "name": name, "type": doc_type, "properties": dict({"dc:title": name}, **props)})
        r.raise_for_status()
        return r.json()["uid"]

    def mkdir(self, rel):
        parts = (self.base + "/" + rel).strip("/").split("/")
        cur = "/" + self.root
        for part in parts:
            nxt = f"{cur}/{part}"
            if not self.doc(nxt):
                self._create(cur, part, "Workspace" if nxt == f"/{self.base_rel}" and "workspaces" in self.root else "Folder", {})
            cur = nxt
        self.ids[rel] = self.doc(self.path(rel))["uid"]

    def _blob(self, name: str, text: str) -> Dict[str, str]:
        b = httpx.post(f"{self.api}/upload/", auth=self.auth, timeout=30).json()["batchId"]
        httpx.post(f"{self.api}/upload/{b}/0", auth=self.auth, content=text.encode(), timeout=30,
                   headers={"X-File-Name": name, "X-File-Type": "text/plain",
                            "Content-Type": "application/octet-stream"}).raise_for_status()
        return {"upload-batch": b, "upload-fileId": "0"}

    def put(self, rel, text):
        name = rel.rsplit("/", 1)[-1]
        d = self.doc(self.path(rel))
        if d:
            httpx.put(f"{self.api}/id/{d['uid']}", auth=self.auth, timeout=30, json={
                "entity-type": "document", "properties": {"file:content": self._blob(name, text)}}).raise_for_status()
            self.ids[rel] = d["uid"]
            return
        self.ids[rel] = self._create(self.path(_parent(rel)), name, "File", {"file:content": self._blob(name, text)})

    def _op(self, uid: str, op: str, params: Dict[str, Any]) -> None:
        httpx.post(f"{self.api}/id/{uid}/@op/{op}", auth=self.auth, timeout=30,
                   json={"params": params}).raise_for_status()

    def delete(self, rel):
        httpx.delete(f"{self.api}/id/{self.id(rel)}", auth=self.auth, timeout=30).raise_for_status()

    def rename(self, rel, new_name):
        uid = self.id(rel)
        self._op(uid, "Document.Move", {"target": self.id(_parent(rel)), "name": new_name})
        httpx.put(f"{self.api}/id/{uid}", auth=self.auth, timeout=30, json={
            "entity-type": "document", "properties": {"dc:title": new_name}}).raise_for_status()
        self.ids[f"{_parent(rel)}/{new_name}".lstrip("/")] = self.ids.pop(rel)

    rename_folder = rename

    def move(self, rel, folder):
        self._op(self.id(rel), "Document.Move", {"target": self.id(folder)})
        self.ids[f"{folder}/{rel.rsplit('/', 1)[-1]}"] = self.ids.pop(rel)

    def cleanup(self):
        d = self.doc(f"/{self.base_rel}")
        if d:
            httpx.delete(f"{self.api}/id/{d['uid']}", auth=self.auth, timeout=60)

    def _cred(self):
        return {"url": self.url, "username": self.auth[0], "password": self.auth[1]}

    def config(self, folder, recursive=True, select=None):
        c = dict(self._cred(), path=self.path(folder), recursive=recursive)
        if select:
            c["nodeDetails"] = [{"id": self.id(r), "name": r.rsplit("/", 1)[-1], "path": self.path(r),
                                 "isFile": r.endswith(".txt"), "isFolder": not r.endswith(".txt")} for r in select]
        return {"nuxeo_config": c}

    def status_body(self, rels, folder, recursive=True):
        return {"data_source": "nuxeo", "url": self.url, "recursive": recursive,
                "items": [{"path": self.path(r), "id": self.id(r), "is_folder": not r.endswith(".txt")} for r in rels]}

    def row(self, rel: str, action: str, **kw) -> Dict[str, Any]:
        return dict({"path": self.path(rel), "id": self.id(rel), "is_folder": not rel.endswith(".txt"),
                     "action": action}, **kw)

    def source_auth(self):
        return {"nuxeo": {"url": self.url, "auth_method": "basic", "username": self.auth[0], "password": self.auth[1]}}


# ── S3 ───────────────────────────────────────────────────────────────────────────────────────

class S3(Source):
    name = tree_type = "s3"
    folder_rename = False   # no folders: a "rename" is every object copied
    timeout = 180

    def __init__(self, run: str):
        super().__init__(run)
        import boto3
        c = env_json("S3_CONFIG")
        self.cfg = {
            "bucket_name": c.get("bucket_name") or c.get("bucket") or env("S3_BUCKET_NAME"),
            "access_key": c.get("access_key") or env("S3_ACCESS_KEY"),
            "secret_key": c.get("secret_key") or env("S3_SECRET_KEY"),
            "region_name": c.get("region_name") or env("S3_REGION_NAME"),
            "sqs_queue_url": c.get("sqs_queue_url") or env("S3_SQS_QUEUE_URL"),
        }
        self.bucket = self.cfg["bucket_name"]
        self.s3 = boto3.client("s3", aws_access_key_id=self.cfg["access_key"],
                               aws_secret_access_key=self.cfg["secret_key"], region_name=self.cfg["region_name"])

    def key(self, rel):
        return f"{self.base}/{rel}"

    def put(self, rel, text):
        self.s3.put_object(Bucket=self.bucket, Key=self.key(rel), Body=text.encode(), ContentType="text/plain")

    def delete(self, rel):
        self.s3.delete_object(Bucket=self.bucket, Key=self.key(rel))

    def _mv(self, src, dst):
        self.s3.copy_object(Bucket=self.bucket, Key=self.key(dst), CopySource={"Bucket": self.bucket, "Key": self.key(src)})
        self.delete(src)

    def rename(self, rel, new_name):
        self._mv(rel, f"{_parent(rel)}/{new_name}".lstrip("/"))

    def move(self, rel, folder):
        self._mv(rel, f"{folder}/{rel.rsplit('/', 1)[-1]}")

    def cleanup(self):
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=f"{self.base}/"):
            for o in page.get("Contents", []):
                self.s3.delete_object(Bucket=self.bucket, Key=o["Key"])

    def config(self, folder, recursive=True, select=None):
        return {"s3_config": dict(self.cfg, prefix=f"{self.key(folder)}/")}


# ── Azure Blob ───────────────────────────────────────────────────────────────────────────────

class Azure(Source):
    name = tree_type = "azure_blob"
    folder_rename = False
    timeout = 480   # change feed, else the periodic refresh

    def __init__(self, run: str):
        super().__init__(run)
        from azure.storage.blob import BlobServiceClient
        c = env_json("AZURE_BLOB_CONFIG")
        self.cfg = {k: c.get(k) for k in ("container_name", "account_url", "account_key", "account_name") if c.get(k)}
        self.cc = BlobServiceClient(account_url=c["account_url"], credential=c["account_key"]).get_container_client(
            c["container_name"])

    def key(self, rel):
        return f"{self.base}/{rel}"

    def put(self, rel, text):
        self.cc.upload_blob(self.key(rel), text.encode(), overwrite=True)

    def delete(self, rel):
        self.cc.delete_blob(self.key(rel))

    def _mv(self, src, dst):
        self.cc.upload_blob(self.key(dst), self.cc.download_blob(self.key(src)).readall(), overwrite=True)
        self.delete(src)

    def rename(self, rel, new_name):
        self._mv(rel, f"{_parent(rel)}/{new_name}".lstrip("/"))

    def move(self, rel, folder):
        self._mv(rel, f"{folder}/{rel.rsplit('/', 1)[-1]}")

    def cleanup(self):
        for b in self.cc.list_blobs(name_starts_with=f"{self.base}/"):
            self.cc.delete_blob(b.name)

    def config(self, folder, recursive=True, select=None):
        if select:   # one blob
            return {"azure_blob_config": dict(self.cfg, blob=self.key(select[0]))}
        return {"azure_blob_config": dict(self.cfg, prefix=f"{self.key(folder)}/")}


# ── Box ──────────────────────────────────────────────────────────────────────────────────────

class Box(Source):
    name = tree_type = "box"
    timeout = 420   # events can lag ~5 min; the periodic refresh (5 min) then takes it
    API = "https://api.box.com/2.0"
    UP = "https://upload.box.com/api/2.0"

    def __init__(self, run: str):
        super().__init__(run)
        c = env_json("BOX_CONFIG")
        self.cfg = {k: c.get(k) for k in ("client_id", "client_secret", "user_id")}
        self.parent = c.get("folder_id")
        tok = httpx.post("https://api.box.com/oauth2/token", timeout=60, data={
            "grant_type": "client_credentials", "client_id": c["client_id"], "client_secret": c["client_secret"],
            "box_subject_type": "user", "box_subject_id": c["user_id"]}).json()["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}
        self.ids: Dict[str, str] = {}

    def setup(self, tag, folders_only=False):
        self.ids[""] = self._folder(self.base, self.parent)
        super().setup(tag, folders_only)

    def _folder(self, name, parent_id):
        r = httpx.post(f"{self.API}/folders", headers=self.h, json={"name": name, "parent": {"id": parent_id}}, timeout=60)
        if r.status_code == 409:
            return r.json()["context_info"]["conflicts"][0]["id"]
        r.raise_for_status()
        return r.json()["id"]

    def mkdir(self, rel):
        cur = ""
        for part in rel.split("/"):
            nxt = f"{cur}/{part}".lstrip("/")
            if nxt not in self.ids:
                self.ids[nxt] = self._folder(part, self.ids[cur])
            cur = nxt

    def put(self, rel, text):
        name = rel.rsplit("/", 1)[-1]
        fid = self.ids.get(rel)
        url, attrs = (f"{self.UP}/files/{fid}/content", {"name": name}) if fid else \
            (f"{self.UP}/files/content", {"name": name, "parent": {"id": self.ids[_parent(rel)]}})
        r = httpx.post(url, headers=self.h, data={"attributes": json.dumps(attrs)},
                       files={"file": (name, text.encode(), "text/plain")}, timeout=60)
        r.raise_for_status()
        self.ids[rel] = r.json()["entries"][0]["id"]

    def delete(self, rel):
        httpx.delete(f"{self.API}/files/{self.ids.pop(rel)}", headers=self.h, timeout=60).raise_for_status()

    def rename(self, rel, new_name):
        httpx.put(f"{self.API}/files/{self.ids[rel]}", headers=self.h, json={"name": new_name}, timeout=60).raise_for_status()
        self.ids[f"{_parent(rel)}/{new_name}".lstrip("/")] = self.ids.pop(rel)

    def move(self, rel, folder):
        httpx.put(f"{self.API}/files/{self.ids[rel]}", headers=self.h, json={"parent": {"id": self.ids[folder]}},
                  timeout=60).raise_for_status()
        self.ids[f"{folder}/{rel.rsplit('/', 1)[-1]}"] = self.ids.pop(rel)

    def rename_folder(self, rel, new_name):
        httpx.put(f"{self.API}/folders/{self.ids[rel]}", headers=self.h, json={"name": new_name}, timeout=60).raise_for_status()
        new = f"{_parent(rel)}/{new_name}".lstrip("/")
        self.ids = {(new + k[len(rel):] if k == rel or k.startswith(rel + "/") else k): v for k, v in self.ids.items()}

    def cleanup(self):
        if self.ids.get(""):
            httpx.delete(f"{self.API}/folders/{self.ids['']}", headers=self.h, params={"recursive": "true"}, timeout=60)

    def config(self, folder, recursive=True, select=None):
        return {"box_config": dict(self.cfg, folder_id=self.ids[folder])}


# ── SharePoint / OneDrive (Microsoft Graph) ──────────────────────────────────────────────────

class MsGraph(Source):
    timeout = 300
    G = "https://graph.microsoft.com/v1.0"

    def __init__(self, run: str, kind: str):
        super().__init__(run)
        import msal
        self.name = self.tree_type = kind
        self.cfg = env_json(f"{kind.upper()}_CONFIG")
        c = self.cfg
        app = msal.ConfidentialClientApplication(c["client_id"], client_credential=c["client_secret"],
                                                 authority=f"https://login.microsoftonline.com/{c['tenant_id']}")
        tok = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])["access_token"]
        self.h = {"Authorization": f"Bearer {tok}"}
        if kind == "sharepoint":
            host = httpx.get(f"{self.G}/sites/root", headers=self.h, timeout=60).json()["siteCollection"]["hostname"]
            site = httpx.get(f"{self.G}/sites/{host}:/sites/{c['site_name']}", headers=self.h, timeout=60).json()["id"]
            self.drive = f"{self.G}/sites/{site}/drive"
        else:
            self.drive = f"{self.G}/users/{c['user_principal_name']}/drive"

    def full(self, rel):
        return f"{self.base}/{rel}".rstrip("/")

    def item(self, rel) -> Optional[Dict[str, Any]]:
        r = httpx.get(f"{self.drive}/root:/{self.full(rel)}", headers=self.h, timeout=60)
        return r.json() if r.status_code == 200 else None

    def setup(self, tag, folders_only=False):
        if not self.item(""):
            httpx.post(f"{self.drive}/root/children", headers=self.h, timeout=60,
                       json={"name": self.base, "folder": {}}).raise_for_status()
        super().setup(tag, folders_only)

    def mkdir(self, rel):
        cur = ""
        for part in rel.split("/"):
            nxt = f"{cur}/{part}".lstrip("/")
            if not self.item(nxt):
                httpx.post(f"{self.drive}/root:/{self.full(cur)}:/children", headers=self.h, timeout=60,
                           json={"name": part, "folder": {}}).raise_for_status()
            cur = nxt

    def put(self, rel, text):
        httpx.put(f"{self.drive}/root:/{self.full(rel)}:/content", headers=dict(self.h, **{"Content-Type": "text/plain"}),
                  content=text.encode(), timeout=60).raise_for_status()

    def _patch(self, rel, body):
        httpx.patch(f"{self.drive}/items/{self.item(rel)['id']}", headers=self.h, json=body, timeout=60).raise_for_status()

    def delete(self, rel):
        httpx.delete(f"{self.drive}/items/{self.item(rel)['id']}", headers=self.h, timeout=60).raise_for_status()

    def rename(self, rel, new_name):
        self._patch(rel, {"name": new_name})

    rename_folder = rename

    def move(self, rel, folder):
        self._patch(rel, {"parentReference": {"id": self.item(folder)["id"]}})

    def cleanup(self):
        it = self.item("")
        if it:
            httpx.delete(f"{self.drive}/items/{it['id']}", headers=self.h, timeout=60)

    def config(self, folder, recursive=True, select=None):
        return {f"{self.name}_config": dict(self.cfg, folder_path=self.full(folder))}


# ── Google Drive ─────────────────────────────────────────────────────────────────────────────

class GoogleDrive(Source):
    """The test service account can make folders and edit / move the test folder's (user-owned)
    files, but not upload new ones: the scenario moves one existing file around and puts it back."""
    name = tree_type = "google_drive"
    uploads = False
    timeout = 300

    def __init__(self, run: str):
        super().__init__(run)
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        self.cfg = env_json("GOOGLE_DRIVE_CONFIG")
        creds_path = Path(self.cfg["credentials_path"])
        if not creds_path.is_absolute():
            creds_path = FG / creds_path
        creds = service_account.Credentials.from_service_account_file(
            str(creds_path), scopes=["https://www.googleapis.com/auth/drive"])
        self.svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.home = self.cfg["folder_id"]
        self.file_name = env("AUTOSYNC_DRIVE_FILE") or "company-ontology-test.txt"
        self.ids: Dict[str, str] = {}
        self.file_id: Optional[str] = None
        self.original: Optional[bytes] = None

    def setup(self, tag, folders_only=True):
        self.ids[""] = self._folder(self.base, self.home)
        for rel in ("sel", "sel/Sub", "sel/Sub/Deep"):
            self.ids[rel] = self._folder(rel.rsplit("/", 1)[-1], self.ids[_parent(rel)])
        found = self.svc.files().list(q=f"'{self.home}' in parents and name='{self.file_name}' and trashed=false",
                                      fields="files(id)", supportsAllDrives=True,
                                      includeItemsFromAllDrives=True).execute()["files"]
        if not found:
            raise RuntimeError(f"{self.file_name} is not in the Google Drive test folder")
        self.file_id = found[0]["id"]
        self.original = self.svc.files().get_media(fileId=self.file_id, supportsAllDrives=True).execute()
        self.move_file("sel/Sub/Deep")

    def _folder(self, name, parent):
        return self.svc.files().create(body={"name": name, "mimeType": "application/vnd.google-apps.folder",
                                             "parents": [parent]}, fields="id", supportsAllDrives=True).execute()["id"]

    def move_file(self, folder: Optional[str]):
        target = self.ids[folder] if folder is not None else self.home
        cur = self.svc.files().get(fileId=self.file_id, fields="parents", supportsAllDrives=True).execute()["parents"]
        self.svc.files().update(fileId=self.file_id, addParents=target, removeParents=",".join(cur),
                                supportsAllDrives=True).execute()

    def edit(self, marker: str):
        from googleapiclient.http import MediaIoBaseUpload
        self.svc.files().update(fileId=self.file_id, supportsAllDrives=True, media_body=MediaIoBaseUpload(
            io.BytesIO(self.original + f"\nEdited {marker}.".encode()), mimetype="text/plain")).execute()

    def cleanup(self):
        from googleapiclient.http import MediaIoBaseUpload
        if self.file_id and self.original is not None:
            self.svc.files().update(fileId=self.file_id, supportsAllDrives=True, media_body=MediaIoBaseUpload(
                io.BytesIO(self.original), mimetype="text/plain")).execute()
            parents = self.svc.files().get(fileId=self.file_id, fields="parents", supportsAllDrives=True).execute()["parents"]
            if self.home not in parents:
                self.move_file(None)
        if self.ids.get(""):
            self.svc.files().delete(fileId=self.ids[""], supportsAllDrives=True).execute()

    def config(self, folder, recursive=True, select=None):
        return {"google_drive_config": {"folder_id": self.ids[folder], "credentials_path": self.cfg["credentials_path"]}}


SOURCES = {
    "filesystem": Filesystem, "alfresco": Alfresco, "nuxeo": Nuxeo, "s3": S3, "azure_blob": Azure, "box": Box,
    "sharepoint": lambda run: MsGraph(run, "sharepoint"), "onedrive": lambda run: MsGraph(run, "onedrive"),
    "google_drive": GoogleDrive,
}
