"""CMIS browse: the folders and documents of a CMIS repository (AtomPub binding), signed in as the
ingest signs in (sources/cmis.py: username / password, or an Alfresco ticket / Nuxeo token from the
CMIS sign-in, sources/cmis_auth.py).

CMIS is path-based: the ingest takes one ``folder_path`` ("/Sites/kg/documentLibrary"), which may
also name a single document. ``path`` here is that repository path; ``id`` is the object id, used to
open a folder. Pages use CMIS's ``maxItems`` / ``skipCount``; the token is the skip count.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from browse import BrowseError, BrowseItem, BrowseResult

LABEL = "CMIS"
_KINDS = {"cmis:folder": "folder", "cmis:document": "file"}  # items, policies, relationships: left out


def _repository(config: Dict[str, Any]):
    """The default repository, signed in as the ingest would (blocking: run in a thread)."""
    from cmislib import CmisClient
    from sources.cmis_auth import split_credential

    url = (config.get("url") or "").strip()
    username, password = config.get("username") or "", config.get("password") or ""
    adapter, credential = split_credential(config)
    if not url:
        raise BrowseError("CMIS: fill in the repository URL first")
    if not credential and not (username.strip() and password):
        raise BrowseError("CMIS: fill in the username and password (or sign in) first")
    client = CmisClient(url, username, password)
    if adapter is not None and credential:
        adapter.cmislib_session(client, credential)
    return client.getDefaultRepository()


def _error(e: Exception, url: str) -> BrowseError:
    """A cmislib / requests error as a BrowseError, by the server's status."""
    import requests
    from cmislib.exceptions import CmisException

    if isinstance(e, CmisException):
        status = e.status if isinstance(e.status, int) else None
        if status == 401:
            return BrowseError("CMIS sign-in failed: the server refused the username or password "
                               "(or the sign-in has expired)", status_code=401)
        if status == 403:
            return BrowseError("CMIS: no permission to list this folder", status_code=403)
        if status == 404:
            return BrowseError("CMIS: folder not found (moved or deleted?)", status_code=404)
        return BrowseError(f"CMIS: the server answered {status or 'with an error'}", status_code=502)
    if isinstance(e, requests.exceptions.RequestException):
        return BrowseError(f"CMIS: could not reach {url} ({type(e).__name__})", status_code=502)
    if isinstance(e, AssertionError):  # cmislib: an object with no children link (not a folder)
        return BrowseError("CMIS: not a folder", status_code=400)
    return BrowseError(f"CMIS: {str(e).splitlines()[0] if str(e) else type(e).__name__}", status_code=502)


def _item(obj, parent_path: str) -> Optional[BrowseItem]:
    props = obj.properties
    kind = _KINDS.get(props.get("cmis:baseTypeId"))
    if not kind:
        return None
    name = props.get("cmis:name") or ""
    path = props.get("cmis:path") if kind == "folder" else None
    modified = props.get("cmis:lastModificationDate")
    size = props.get("cmis:contentStreamLength") if kind == "file" else None
    return BrowseItem(
        id=str(props.get("cmis:objectId") or obj.getObjectId()),
        name=name,
        path=path or f"{parent_path.rstrip('/')}/{name}",
        kind=kind,
        size=int(size) if size not in (None, "") else None,
        modified=modified.isoformat() if hasattr(modified, "isoformat") else modified,
        mime_type=props.get("cmis:contentStreamMimeType") if kind == "file" else None,
    )


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    folder_id = (parent or {}).get("id")
    try:
        skip = max(int(page_token or 0), 0)
    except ValueError:
        raise BrowseError("CMIS: bad page token")

    def page():
        repo = _repository(config)
        folder = repo.getObject(folder_id) if folder_id else repo.getRootFolder()
        parent_path = folder.properties.get("cmis:path") or (parent or {}).get("path") or "/"
        result = folder.getChildren(maxItems=page_size, skipCount=skip)
        children = list(result.getResults())
        return parent_path, children, result.hasNext()

    try:
        parent_path, children, more = await asyncio.to_thread(page)
    except BrowseError:
        raise
    except Exception as e:
        raise _error(e, (config.get("url") or "").strip())
    items = [i for i in (_item(c, parent_path) for c in children) if i]
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    return BrowseResult(items=items, next_page_token=str(skip + len(children)) if more and children else None)
