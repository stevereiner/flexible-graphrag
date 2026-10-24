"""Which documents a search result or an answer came from, by stable doc id.

Graph and RDF facts carry only a ``doc_id`` (no file name), and an answer is built from many
retrieved nodes. This module turns doc ids into what a UI shows and opens::

    {"doc_id", "name", "path", "source_type", "node_id", "open_url"}

Names come first from the retrieved chunks themselves (``file_name`` next to ``doc_id``), then
from the incremental registry (``document_state`` + ``datasource_config``, when
ENABLE_INCREMENTAL_UPDATES is on), and last from the doc id's own shape (a path's file name).

``node_id`` is the repository id for Alfresco / Nuxeo documents (``<config_id>:alfresco://<id>``),
which a host such as ACA opens in its own viewer. ``open_url`` is a plain link for every other UI:
for Alfresco, ACA's viewer (ACA at ``ALFRESCO_ACA_URL``, default ``<ALFRESCO_URL>/content-app``), or
Share's document page with ``ALFRESCO_VIEWER=share``, or ``ALFRESCO_OPEN_URL`` (a template with
``{node_id}``) for anything else; for Nuxeo, the Web UI's document page (Web UI at ``NUXEO_WEBUI_URL`` for
the ``NUXEO_URL`` server, where the browser reaches it, else ``<repository URL>/ui``); for a web page,
Wikipedia article or YouTube video, its URL from the chunk (a video at the segment's start).
"""
from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from typing import Any, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# The asking user's Alfresco Authorization header per server (lower-cased base URL), set for the
# question being answered (main.py): finds a document's folder for its ACA link when the backend
# has no Alfresco service account. Their own ticket, so only folders they may see are asked.
_asker_alfresco: ContextVar[Dict[str, str]] = ContextVar("asker_alfresco", default={})


def set_asker_alfresco(auth_by_server: Dict[str, str]) -> None:
    _asker_alfresco.set({k.rstrip("/").lower(): v for k, v in auth_by_server.items() if k and v})

_REPO_MARKS = ("alfresco", "nuxeo")

# main.py supplies the incremental registry's state manager (None while it is not running)
_registry_provider: Optional[Callable[[], Any]] = None


def set_registry_provider(provider: Callable[[], Any]) -> None:
    global _registry_provider
    _registry_provider = provider


def node_doc_ids(node: Any) -> List[str]:
    """The doc ids a retrieved node came from: its own, or the list an RDF answer carries."""
    from scope_filter import node_doc_id
    meta = getattr(getattr(node, "node", node), "metadata", None) or {}
    return list(dict.fromkeys(d for d in [node_doc_id(node), *(meta.get("doc_ids") or [])] if d))


# Sources whose chunks carry the document's own web address in ``url``: a web page, Wikipedia
# article or YouTube video, and a SharePoint / OneDrive file (its Graph webUrl -- SharePoint /
# OneDrive enforce the viewer's own permissions when it is opened)
_URL_SOURCES = ("web", "wikipedia", "youtube", "sharepoint", "onedrive")


def _seconds(label: str) -> int:
    """'1:02:03' (a YouTube segment's start) -> 3723; 0 when it is not one."""
    try:
        secs = 0
        for part in str(label).split(":"):
            secs = secs * 60 + int(part)
        return secs
    except ValueError:
        return 0


def _chunk_ref(meta: Dict[str, Any], doc_id: str = "") -> Dict[str, str]:
    """What a chunk's own metadata says about its document: its file name, and for a web page,
    Wikipedia article or YouTube video its URL (a video at the segment's start time)."""
    ref: Dict[str, str] = {}
    fn = meta.get("file_name") or meta.get("title")
    if fn and fn != "Unknown":
        ref["name"] = fn
    source, url = meta.get("source"), meta.get("url")
    if source == "wikipedia" and not url and str(doc_id).isdigit():
        # Articles loaded by LlamaIndex's WikipediaReader before 0.8.4 carry no URL or title;
        # their doc id is the page id
        url = f"https://{meta.get('language') or 'en'}.wikipedia.org/?curid={doc_id}"
        if not fn and meta.get("resolved_title"):
            ref["name"] = meta["resolved_title"]
    drive_id = meta.get("file_id") or meta.get("file id")  # LlamaIndex's reader: "file id"; stored: file_id
    if source == "google_drive" and drive_id:
        # Drive's own file page (Drive enforces the viewer's permissions when it is opened)
        ref["source_type"] = source
        ref["open_url"] = f"https://drive.google.com/file/d/{drive_id}/view"
        return ref
    if source == "gcs" and meta.get("bucket") and meta.get("file_path", "").startswith(f"{meta['bucket']}/"):
        # The object through Google's authenticated browser endpoint (signs the viewer in and
        # applies their bucket permissions)
        from urllib.parse import quote
        ref["source_type"] = source
        ref["open_url"] = f"https://storage.cloud.google.com/{quote(meta['file_path'], safe='/')}"
        return ref
    if source == "s3" and meta.get("bucket_name") and meta.get("s3_key"):
        # The object's page in the AWS console (signs the viewer in and applies their IAM access)
        from urllib.parse import quote
        ref["source_type"] = source
        ref["open_url"] = (f"https://console.aws.amazon.com/s3/object/{quote(meta['bucket_name'], safe='')}"
                           f"?region={quote(meta.get('region') or 'us-east-1', safe='')}"
                           f"&prefix={quote(meta['s3_key'], safe='')}")
        return ref
    if source == "box" and meta.get("box_file_id"):
        # Box keeps no web address on its chunks, but its file page is fixed by the file id (Box
        # enforces the viewer's own permissions when it is opened)
        url = f"https://app.box.com/file/{meta['box_file_id']}"
        ref["source_type"] = source
        ref["open_url"] = url
        return ref
    if source in _URL_SOURCES and url:
        ref["source_type"] = source
        ref["open_url"] = url
        if source == "youtube" and meta.get("video_id"):
            t = _seconds(meta.get("start_timestamp", ""))
            ref["open_url"] = f"https://www.youtube.com/watch?v={meta['video_id']}" + (f"&t={t}s" if t else "")
    return ref


def chunk_refs(nodes: Iterable[Any]) -> Dict[str, Dict[str, str]]:
    """doc_id -> what the retrieved chunks themselves say about that document (_chunk_ref)."""
    from scope_filter import node_doc_id
    out: Dict[str, Dict[str, str]] = {}
    for n in nodes:
        d = node_doc_id(n)
        ref = _chunk_ref(getattr(getattr(n, "node", n), "metadata", None) or {}, d or "")
        if d and ref:
            out.setdefault(d, ref)
    return out


def _split(doc_id: str):
    """(config_id, source_type, node_id) for a repository doc id, else (None, None, None).
    ``<config_id>:alfresco://<id>`` with the incremental registry; plain ``alfresco://<id>`` without
    it (ingest_from_source._assign_repository_doc_ids), where config_id is None."""
    for mark in _REPO_MARKS:
        sep = f":{mark}://"
        if sep in doc_id:
            config_id, node_id = doc_id.split(sep, 1)
            return config_id, mark, node_id
        if doc_id.startswith(f"{mark}://"):
            return None, mark, doc_id[len(mark) + 3:]
    return None, None, None


def _basename(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] if path else ""


def _from_doc_id(doc_id: str) -> Dict[str, Any]:
    """What the doc id alone says: a repository id, or a path whose last part is the name."""
    _, source_type, node_id = _split(doc_id)
    if source_type:
        return {"source_type": source_type, "node_id": node_id}
    # "<config uuid>:<path>" (filesystem, cloud) or a bare path; a bare uuid names nothing
    tail = doc_id.split(":", 1)[1] if len(doc_id) > 37 and doc_id[36:37] == ":" else doc_id
    name = _basename(tail) if ("/" in tail or "\\" in tail or "." in tail) else ""
    return {"name": name, "path": tail if name else ""}


def _open_url(source_type: Optional[str], node_id: Optional[str], repo_url: str, parent_id: str = "",
              name: str = "") -> str:
    if not node_id:
        return ""
    if source_type == "alfresco":
        template = os.getenv("ALFRESCO_OPEN_URL", "")
        if template:
            return template.replace("{node_id}", node_id)
        from permission_filter import _rest_base  # "http://host:8080/alfresco" -> "http://host:8080"
        base = _rest_base(repo_url or os.getenv("ALFRESCO_URL", ""))
        if os.getenv("ALFRESCO_VIEWER", "aca").strip().lower() == "share":
            return f"{base}/share/page/document-details?nodeRef=workspace://SpacesStore/{node_id}" if base else ""
        # ACA is hash-routed and its viewer is the "viewer" outlet. Over the document's folder in
        # the Repository view (open to every user; Alfresco permissions apply), as ACA's own links
        # do, so closing the viewer lands in that folder with its breadcrumb; over search when the
        # folder is unknown -- a search for the file's name, since ACA's search page with no
        # term never finishes loading when the viewer is closed onto it.
        aca = os.getenv("ALFRESCO_ACA_URL", "").rstrip("/") or (f"{base}/content-app" if base else "")
        if not aca:
            return ""
        if parent_id:
            return (f"{aca}/#/repository/{parent_id}/(viewer:view/{node_id})"
                    f"?location=%2Frepository%2F{parent_id}")
        if name:
            from urllib.parse import quote
            term = quote(name, safe="")
            return f"{aca}/#/search;q={term}/(viewer:view/{node_id})"
        return f"{aca}/#/personal-files/(viewer:view/{node_id})"
    if source_type == "nuxeo":
        backend_url = os.getenv("NUXEO_URL", "")
        # The repository URL is where the BACKEND reaches Nuxeo (http://nuxeo:8080/nuxeo in Docker); a browser
        # may reach the same server elsewhere (through a proxy): NUXEO_WEBUI_URL, for the NUXEO_URL server
        webui = os.getenv("NUXEO_WEBUI_URL", "").rstrip("/")
        if webui:
            from sources.nuxeo_accounts import server_key
            if not repo_url or server_key(repo_url) == server_key(backend_url):
                return f"{webui}/#!/doc/{node_id}"
        base = (repo_url or backend_url).rstrip("/")
        return f"{base}/ui/#!/doc/{node_id}" if base else ""
    return ""


_PARENT_TTL = 600.0  # seconds a node's parent folder is reused
_parents: Dict[str, tuple] = {}  # node_id -> (fetched at, parent id or "")
_names: Dict[str, str] = {}  # node_id -> its name in Alfresco, from the same lookup


async def _alfresco_parents(nodes: Dict[str, str]) -> Dict[str, str]:
    """node_id -> its parent folder's id, for {node_id: repository base URL}. Asked of Alfresco
    with the backend's service account (ALFRESCO_SYNC_* or ALFRESCO_USERNAME/PASSWORD), in
    parallel, briefly cached; a node it cannot look up has no entry."""
    import asyncio
    import base64
    import time
    import httpx
    now = time.monotonic()
    out = {n: p for n, (t, p) in ((n, _parents.get(n, (0.0, ""))) for n in nodes) if p and now - t < _PARENT_TTL}
    todo = {n: b for n, b in nodes.items() if n not in out and b}
    user = os.getenv("ALFRESCO_SYNC_USERNAME") or os.getenv("ALFRESCO_USERNAME")
    password = os.getenv("ALFRESCO_SYNC_PASSWORD") or os.getenv("ALFRESCO_PASSWORD")
    service = ("Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
               if user and password is not None else "")
    asker = _asker_alfresco.get()
    # the service account, else the asking user's own sign-in on that server
    auth_for = lambda base: service or asker.get(base.rstrip("/").lower(), "")
    todo = {n: b for n, b in todo.items() if auth_for(b)}
    if not todo:
        return out

    async def one(client, node_id, base):
        try:
            r = await client.get(f"{base}/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}",
                                 params={"fields": "parentId,name"}, headers={"Authorization": auth_for(base)})
            if r.status_code == 200:
                entry = r.json().get("entry") or {}
                parent = entry.get("parentId") or ""
                _parents[node_id] = (now, parent)
                if entry.get("name"):
                    _names[node_id] = entry["name"]
                if parent:
                    out[node_id] = parent
        except Exception as e:  # only the link's landing place depends on it
            logger.debug(f"doc_refs: parent of {node_id} not found: {e}")

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await asyncio.gather(*(one(client, n, b) for n, b in todo.items()))
    except Exception as e:
        logger.warning(f"doc_refs: Alfresco parent lookup failed: {e}")
    return out


async def _registry_rows(doc_ids: List[str]) -> Dict[str, dict]:
    state_manager = _registry_provider() if _registry_provider else None
    if state_manager is None or not doc_ids:
        return {}
    try:
        rows = await state_manager.registry_rows(doc_ids)
    except Exception as e:  # the lookup only adds names; never fail a search over it
        logger.warning(f"doc_refs: document_state lookup failed: {e}")
        return {}
    out = {}
    for doc_id, r in rows.items():
        params = r.get("connection_params") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except ValueError:
                params = {}
        out[doc_id] = {"source_id": r.get("source_id"), "source_path": r.get("source_path") or "",
                       "source_type": r.get("source_type") or "", "url": params.get("url") or ""}
    return out


async def describe(doc_ids: Iterable[str], known: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Dict[str, Any]]:
    """doc_id -> {doc_id, name, path, source_type, node_id, parent_id, open_url} for each doc id.
    ``known`` is what the retrieved chunks say (chunk_refs); it wins over the registry."""
    ids = list(dict.fromkeys(d for d in doc_ids if d))
    known = known or {}
    rows = await _registry_rows(ids)
    out: Dict[str, Dict[str, Any]] = {}
    for d in ids:
        ref = {"doc_id": d, "name": "", "path": "", "source_type": "", "node_id": "", "parent_id": "",
               "open_url": ""}
        ref.update({k: v for k, v in _from_doc_id(d).items() if v})
        row = rows.get(d)
        if row:
            ref["path"] = row["source_path"] or ref["path"]
            ref["name"] = _basename(row["source_path"]) or ref["name"]
            ref["source_type"] = row["source_type"] or ref["source_type"]
            if ref["source_type"] in _REPO_MARKS:
                ref["node_id"] = row["source_id"] or ref["node_id"]
        ref["repo_url"] = (row or {}).get("url", "")
        ref.update(known.get(d, {}))
        out[d] = ref
    # A copy nothing names (one the registry has no row for, e.g. another data source's, met through a
    # graph fact that carries no file name): the name of another copy of the same document here
    named = {(r["source_type"], r["node_id"]): r for r in out.values() if r["node_id"] and r["name"]}
    for ref in out.values():
        if not ref["name"] and ref["node_id"] and (ref["source_type"], ref["node_id"]) in named:
            other = named[(ref["source_type"], ref["node_id"])]
            ref["name"], ref["path"] = other["name"], ref["path"] or other["path"]
    # Alfresco documents: their folder, for ACA links that open over it (and for a host such as
    # KG Spaces that builds its own)
    from permission_filter import _rest_base  # a datasource URL may end in /alfresco
    alfresco = {r["node_id"]: _rest_base(r["repo_url"] or os.getenv("ALFRESCO_URL", ""))
                for r in out.values() if r["source_type"] == "alfresco" and r["node_id"]}
    parents = await _alfresco_parents(alfresco) if alfresco else {}
    for ref in out.values():
        if not ref["name"]:
            # an Alfresco document: its name in Alfresco (same lookup as its folder); else its id
            alfresco_name = _names.get(ref["node_id"], "") if ref["source_type"] == "alfresco" else ""
            ref["name"] = alfresco_name or ref["node_id"] or ref["doc_id"]
        repo_url = ref.pop("repo_url", "")
        ref["parent_id"] = parents.get(ref["node_id"], "") if ref["source_type"] == "alfresco" else ""
        if not ref["open_url"]:
            ref["open_url"] = _open_url(ref["source_type"], ref["node_id"], repo_url, ref["parent_id"], ref["name"])
    return out


async def answer_sources(source_nodes: Iterable[Any], limit: int = 10) -> List[Dict[str, Any]]:
    """The documents an answer was built from, best first, one entry per document."""
    nodes = list(source_nodes or [])
    order: Dict[str, float] = {}
    for n in nodes:
        for d in node_doc_ids(n):
            order[d] = max(order.get(d, float("-inf")), float(getattr(n, "score", 0.0) or 0.0))
    if not order:
        # nodes without doc ids (e.g. a plain ingest's chunks): what their metadata says
        refs: Dict[str, Dict[str, Any]] = {}
        for n in nodes:
            ref = _chunk_ref(getattr(getattr(n, "node", n), "metadata", None) or {})
            if ref.get("name"):
                refs.setdefault(ref["name"], {"doc_id": "", "path": "", "source_type": "", "node_id": "",
                                              "parent_id": "", "open_url": "", **ref})
        return list(refs.values())[:limit]
    ranked = sorted(order, key=order.get, reverse=True)[:limit]
    refs = await describe(ranked, chunk_refs(nodes))
    # One entry per source object: a repository document two data sources hold (two copies, two doc
    # ids) is listed once, at its best rank, named by whichever copy knows its name
    out: List[Dict[str, Any]] = []
    seen: Dict[tuple, Dict[str, Any]] = {}
    for d in ranked:
        ref = refs[d]
        key = (ref["source_type"], ref["node_id"]) if ref["node_id"] else None
        first = seen.get(key) if key else None
        if first is None:
            if key:
                seen[key] = ref
            out.append(ref)
        elif first["name"] in (first["node_id"], first["doc_id"]) and ref["name"] not in (ref["node_id"], ref["doc_id"]):
            first["name"], first["path"] = ref["name"], ref["path"] or first["path"]
    return out
