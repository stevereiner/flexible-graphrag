"""Alfresco browse: the folders and documents of an Alfresco repository over its public REST API,
signed in as the ingest signs in (sources/alfresco_auth.alfresco_authorization: username / password,
the sign-in's ticket, or OAuth2).

The ingest takes a ``path`` (a folder, or one document) relative to Company Home ("/Shared/GraphRAG",
no "/Company Home"), or ``nodeDetails`` (files and folders by node id, ``path`` their common parent).
So ``id`` here is the node id and ``path`` that Company-Home-relative path. The root is ``-root-``
(Company Home); pages use ``skipCount`` / ``maxItems``, and the token is the skip count.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from browse import BrowseError, BrowseItem, BrowseResult

LABEL = "Alfresco"
_NODES = "/alfresco/api/-default-/public/alfresco/versions/1/nodes"


async def _authorization(config: Dict[str, Any]) -> str:
    """The Authorization header the ingest would use for this config (OAuth2 may fetch a token)."""
    from sources.alfresco_auth import alfresco_authorization

    username, ticket = config.get("username") or "", config.get("ticket") or ""
    method = (config.get("auth_method") or "basic").lower()
    if ticket and not username and method == "basic":
        method = "ticket"  # as AlfrescoConfig: a ticket alone means ticket auth
    oauth2 = config.get("oauth2") or {}
    if method == "oauth2":
        if not (oauth2.get("access_token") or (oauth2.get("client_id") and oauth2.get("client_secret"))):
            raise BrowseError("Alfresco: fill in the OAuth2 client id and secret (or an access token) first")
    elif not ticket and not (username.strip() and config.get("password")):
        raise BrowseError("Alfresco: fill in the username and password (or sign in) first")
    try:
        header = await asyncio.to_thread(
            alfresco_authorization, _rest_base(config), method, username, config.get("password") or "",
            ticket or None, oauth2 or None)
    except Exception as e:  # PermissionError, or the OAuth2 token endpoint failing
        raise BrowseError(f"Alfresco sign-in failed: {str(e).splitlines()[0] if str(e) else type(e).__name__}",
                          status_code=401)
    if not header:
        raise BrowseError("Alfresco: fill in the username and password (or sign in) first")
    return header


def _rest_base(config: Dict[str, Any]) -> str:
    from sources.alfresco_auth import _rest_base as rest_base

    url = rest_base(config.get("url") or "")
    if not url:
        raise BrowseError("Alfresco: fill in the base URL first")
    return url


def _error(status: int, body: Any) -> BrowseError:
    message = ""
    if isinstance(body, dict):
        message = (body.get("error") or {}).get("briefSummary") or ""
    if status == 401:
        return BrowseError("Alfresco sign-in failed: the server refused the username or password "
                           "(or the sign-in has expired)", status_code=401)
    if status == 403:
        return BrowseError("Alfresco: no permission to list this folder", status_code=403)
    if status == 404:
        return BrowseError("Alfresco: folder not found (moved or deleted?)", status_code=404)
    return BrowseError(f"Alfresco: the server answered {status}{': ' + message if message else ''}",
                       status_code=502)


def _item(entry: Dict[str, Any], parent_path: str) -> Optional[BrowseItem]:
    if entry.get("isFolder"):
        kind = "folder"
    elif entry.get("isFile"):
        kind = "file"
    else:
        return None  # links and other node types
    name = entry.get("name") or entry.get("id") or ""
    content = entry.get("content") or {}
    return BrowseItem(
        id=str(entry.get("id")),
        name=name,
        path=f"{parent_path.rstrip('/')}/{name}",
        kind=kind,
        size=content.get("sizeInBytes") if kind == "file" else None,
        modified=entry.get("modifiedAt"),
        mime_type=content.get("mimeType") if kind == "file" else None,
    )


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    base = _rest_base(config)
    auth = await _authorization(config)
    node_id = (parent or {}).get("id") or "-root-"
    try:
        skip = max(int(page_token or 0), 0)
    except ValueError:
        raise BrowseError("Alfresco: bad page token")
    # No include=path: it renders every ancestor with its aspects, and one aspect of a model no
    # longer deployed (e.g. contentlake's) fails the whole listing with a 500 ("A namespace prefix
    # is not registered"). Paths are built from the parent's path instead (the browser passes it).
    params = {"skipCount": skip, "maxItems": page_size, "orderBy": "isFolder DESC,name ASC"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{base}{_NODES}/{node_id}/children", params=params,
                                 headers={"Authorization": auth, "Accept": "application/json"})
    except httpx.HTTPError as e:
        raise BrowseError(f"Alfresco: could not reach {base} ({type(e).__name__})", status_code=502)
    if r.status_code != 200:
        try:
            body = r.json()
        except ValueError:
            body = None
        raise _error(r.status_code, body)
    data = r.json().get("list") or {}
    parent_path = (parent or {}).get("path") or "/"
    items = [i for i in (_item(e.get("entry") or {}, parent_path) for e in data.get("entries") or []) if i]
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    paging = data.get("pagination") or {}
    count = paging.get("count", len(data.get("entries") or []))
    more = bool(paging.get("hasMoreItems")) and count > 0
    return BrowseResult(items=items, next_page_token=str(skip + count) if more else None)
