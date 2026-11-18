"""Box browse: the folders and files the form's Box credentials can see, as the ingest reads them
(sources/box.py: developer token, else CCG with user and / or enterprise id; BOX_CONFIG fills what the
form leaves out).

Box is id-based: the root is folder "0" (All Files), the ingest takes a folder id (``folder_id``) or
file ids (``box_file_ids``). ``path`` here is only for display ("Reports/2024", from the names
browsed through). Pages use Box's marker paging; the token is the opaque marker.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from browse import BrowseError, BrowseItem, BrowseResult

LABEL = "Box"
_FIELDS = ["id", "type", "name", "size", "modified_at"]
_MAX_LIMIT = 1000  # Box's own maximum per page


def _client(config: Dict[str, Any]):
    """The ingest's client for this config (UI names mapped as main.py maps them for the ingest)."""
    from sources.box import build_box_client, merge_env_config

    cfg = dict(config)
    if cfg.get("developer_token") and not cfg.get("access_token"):
        cfg["access_token"] = cfg.pop("developer_token")
    merge_env_config(cfg)
    token = (cfg.get("access_token") or cfg.get("developer_token") or "").strip()
    client_id, secret = (cfg.get("client_id") or "").strip(), (cfg.get("client_secret") or "").strip()
    enterprise, user = str(cfg.get("enterprise_id") or "").strip(), str(cfg.get("user_id") or "").strip()
    if not token and not (client_id and secret and (enterprise or user)):
        raise BrowseError("Box: fill in the app's client id / secret with a user or enterprise id "
                          "(or a developer token) first")
    return build_box_client(token, client_id, secret, enterprise, user)


def _error(e: Exception) -> BrowseError:
    """A Box SDK error as a BrowseError: sign-in failures 401, the rest by Box's status."""
    from box_sdk_gen.box.errors import BoxAPIError

    message = getattr(e, "message", None) or str(e).splitlines()[0]
    if isinstance(e, BoxAPIError):
        status = getattr(e.response_info, "status_code", None)
        url = getattr(e.request_info, "url", "") or ""
        if "oauth2/token" in url or status == 401:
            # the token endpoint's reason is in the body ({"error": "invalid_client",
            # "error_description": "The client credentials are invalid"}), not the message
            body = getattr(e.response_info, "body", None) or {}
            reason = (body.get("error_description") or body.get("error")) if isinstance(body, dict) else None
            return BrowseError(f"Box sign-in failed: {reason or message}", status_code=401)
        if status == 404:
            return BrowseError(f"Box: {message}", status_code=404)
        if status == 403:
            return BrowseError(f"Box: {message}", status_code=403)
        return BrowseError(f"Box: {message}", status_code=502)
    if "token" in message.lower():
        # the SDK's own auth errors ("Developer token has expired. Please provide a new one.")
        return BrowseError(f"Box sign-in failed: {message}", status_code=401)
    return BrowseError(f"Box: {message}", status_code=502)


def _item(entry, parent_path: str) -> Optional[BrowseItem]:
    kind = getattr(entry, "type", None)
    kind = getattr(kind, "value", kind)  # an SDK enum, or a plain string
    if kind not in ("file", "folder"):
        return None  # web links: nothing to ingest
    modified = getattr(entry, "modified_at", None)
    name = getattr(entry, "name", "") or str(entry.id)
    return BrowseItem(
        id=str(entry.id),
        name=name,
        path=f"{parent_path}/{name}".strip("/"),
        kind=kind,
        size=getattr(entry, "size", None) if kind == "file" else None,
        modified=modified.isoformat() if hasattr(modified, "isoformat") else modified,
    )


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    client = _client(config)
    folder_id = str((parent or {}).get("id") or "0")
    parent_path = (parent or {}).get("path") or ""

    def page():
        return client.folders.get_folder_items(
            folder_id, fields=_FIELDS, usemarker=True, marker=page_token or None,
            limit=min(page_size, _MAX_LIMIT))

    try:
        result = await asyncio.to_thread(page)
    except BrowseError:
        raise
    except Exception as e:
        raise _error(e)
    items = [i for i in (_item(e, parent_path) for e in (result.entries or [])) if i]
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    return BrowseResult(items=items, next_page_token=getattr(result, "next_marker", None) or None)
