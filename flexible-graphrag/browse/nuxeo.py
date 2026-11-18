"""Nuxeo browse: the documents under a Nuxeo path, one level at a time (REST ``@children``), as the
form's identity: basic (username / password), token (the sign-in's X-Authentication-Token; token
mode without a token = the username / password the backend would fetch one with), or OAuth2 with
an access token (sources/nuxeo_auth.nuxeo_headers).

The ingest takes a ``path`` or ``nodeDetails`` ([{id, name, path, isFile, isFolder}], several
documents and folders), so ``id`` is the document uid and ``path`` its repository path
("/default-domain/workspaces/GraphRAG"). Folderish documents are folders; proxies and trashed or
hidden documents are left out, as the ingest leaves them out. The page token is Nuxeo's
``currentPageIndex``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from browse import BrowseError, BrowseItem, BrowseResult

LABEL = "Nuxeo"
_MAX_PAGE = 1000
_HIDDEN = {"HiddenInNavigation", "SystemDocument"}


def _headers(config: Dict[str, Any]) -> Dict[str, str]:
    from sources.nuxeo_auth import nuxeo_headers

    method = (config.get("auth_method") or "basic").lower()
    oauth2 = config.get("oauth2") or {}
    token = (config.get("token") or "").strip()
    username, password = (config.get("username") or "").strip(), config.get("password") or ""
    if method == "oauth2":
        if not oauth2.get("access_token"):
            raise BrowseError("Nuxeo: browsing with OAuth2 needs an access token (or use basic / sign in)")
    elif not token and not (username and password):
        # token mode without a token: the backend would fetch one with these, so basic is the same user
        raise BrowseError("Nuxeo: fill in the username and password (or sign in) first")
    return nuxeo_headers("token" if method == "token" and token else method if method == "oauth2" else "basic",
                         username, password, token or None, oauth2)


def _path_url(base: str, path: str) -> str:
    return f"{base}/api/v1/path/{quote(path.strip('/'), safe='/')}"


def _children_url(base: str, uid: str) -> str:
    return f"{base}/api/v1/id/{quote(str(uid), safe='')}/@children"


def _error(status: int, path: str) -> BrowseError:
    if status in (301, 302, 303, 401):
        # a bad password gets a redirect to the login page, not always a 401
        return BrowseError("Nuxeo sign-in failed: the server refused the credentials (or the token was revoked)",
                           status_code=401)
    if status == 403:
        return BrowseError(f"Nuxeo: no permission to list {path or 'this folder'}", status_code=403)
    if status == 404:
        return BrowseError(f"Nuxeo: no document at {path or 'this id'} (moved or deleted?)", status_code=404)
    return BrowseError(f"Nuxeo: the server answered {status}", status_code=502)


def _item(entry: Dict[str, Any]) -> Optional[BrowseItem]:
    facets = set(entry.get("facets") or [])
    if entry.get("isProxy") or entry.get("isTrashed") or entry.get("isVersion") or facets & _HIDDEN:
        return None
    props = entry.get("properties") or {}
    path = entry.get("path") or ""
    name = entry.get("title") or props.get("dc:title") or path.rstrip("/").rsplit("/", 1)[-1] or entry.get("uid", "")
    folder = "Folderish" in facets
    content = props.get("file:content") if not folder else None
    content = content if isinstance(content, dict) else {}
    size = content.get("length")
    return BrowseItem(
        id=str(entry.get("uid")),
        name=name,
        path=path,
        kind="folder" if folder else "file",
        size=int(size) if size not in (None, "") else None,
        modified=entry.get("lastModified") or props.get("dc:modified"),
        mime_type=content.get("mime-type") or None,
    )


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    from sources.nuxeo_auth import nuxeo_base

    base = nuxeo_base(config.get("url") or "")
    if not base:
        raise BrowseError("Nuxeo: fill in the server URL first")
    headers = _headers(config)
    headers.update({"properties": "dublincore,file", "Accept": "application/json"})
    try:
        index = max(int(page_token or 0), 0)
    except ValueError:
        raise BrowseError("Nuxeo: bad page token")
    uid = (parent or {}).get("id")
    shown = (parent or {}).get("path") or ("" if uid else "/")

    async def get(client: httpx.AsyncClient, url: str, params=None) -> Dict[str, Any]:
        r = await client.get(url, headers=headers, params=params)
        if r.status_code != 200:
            raise _error(r.status_code, shown)
        try:
            return r.json()
        except ValueError:
            raise _error(401, shown)  # a login page instead of JSON: the credentials were not accepted

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False,
                                     verify=config.get("verify_ssl", True)) as client:
            if not uid:  # the root, or a path given without its id: its uid first
                uid = (await get(client, _path_url(base, shown or "/"))).get("uid")
                if not uid:
                    raise _error(404, shown)
            body = await get(client, _children_url(base, uid),
                             {"currentPageIndex": index, "pageSize": min(page_size, _MAX_PAGE)})
    except httpx.HTTPError as e:
        raise BrowseError(f"Nuxeo: could not reach {base} ({type(e).__name__})", status_code=502)
    items = [i for i in (_item(e) for e in body.get("entries") or []) if i]
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    more = bool(body.get("isNextPageAvailable"))
    return BrowseResult(items=items, next_page_token=str(index + 1) if more else None)
