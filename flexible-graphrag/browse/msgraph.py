"""Microsoft Graph drive listing shared by the SharePoint and OneDrive browsers: an app token from the
form's credentials (client id / secret / tenant, as the ingest uses), one folder level of a drive,
paged by Graph's ``@odata.nextLink``.

An item's ``path`` is relative to the drive's root ("Reports/2024"): what the readers' folder paths
take (``root:/{path}``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote, unquote

import httpx

from browse import BrowseError, BrowseItem, BrowseResult

GRAPH = "https://graph.microsoft.com/v1.0"
_SELECT = "id,name,size,lastModifiedDateTime,folder,file,webUrl,parentReference"


async def access_token(config: Dict[str, Any], label: str) -> str:
    missing = [k for k in ("client_id", "client_secret", "tenant_id") if not (config.get(k) or "").strip()]
    if missing:
        raise BrowseError(f"{label}: fill in {', '.join(missing)} first")
    from azure.core.exceptions import ClientAuthenticationError
    from azure.identity.aio import ClientSecretCredential

    credential = ClientSecretCredential(
        tenant_id=config["tenant_id"].strip(),
        client_id=config["client_id"].strip(),
        client_secret=config["client_secret"].strip(),
    )
    try:
        token = await credential.get_token("https://graph.microsoft.com/.default")
        return token.token
    except ClientAuthenticationError as e:
        # the first line is the useful part (AADSTS code + reason)
        raise BrowseError(f"{label} sign-in failed: {str(e).splitlines()[0]}", status_code=401)
    finally:
        await credential.close()


async def get(client: httpx.AsyncClient, url: str, label: str) -> Dict[str, Any]:
    r = await client.get(url)
    if r.status_code == 200:
        return r.json()
    try:
        err = r.json().get("error", {})
        detail = err.get("message") or err.get("code") or r.text
    except ValueError:
        detail = r.text
    status = 404 if r.status_code == 404 else 403 if r.status_code in (401, 403) else 502
    raise BrowseError(f"{label}: {detail}", status_code=status)


def item(raw: Dict[str, Any]) -> BrowseItem:
    # parentReference.path: "/drive/root:/Reports" (or "/drives/{id}/root:"), percent-encoded;
    # keep what follows root:
    parent_path = (raw.get("parentReference") or {}).get("path") or ""
    parent_path = unquote(parent_path.split("root:", 1)[1]) if "root:" in parent_path else ""
    path = f"{parent_path.strip('/')}/{raw['name']}".strip("/")
    is_folder = "folder" in raw
    return BrowseItem(
        id=raw["id"],
        name=raw["name"],
        path=path,
        kind="folder" if is_folder else "file",
        size=None if is_folder else raw.get("size"),
        modified=raw.get("lastModifiedDateTime"),
        mime_type=(raw.get("file") or {}).get("mimeType"),
        web_url=raw.get("webUrl"),
    )


async def list_drive(config: Dict[str, Any], label: str, drive_url, parent: Optional[Dict[str, Any]],
                     page_token: Optional[str], page_size: int) -> BrowseResult:
    """One level of a drive. ``drive_url(client)``: the drive's Graph URL ("{GRAPH}/sites/{id}/drive"),
    awaited only for a first page (a page token already holds the whole URL)."""
    token = await access_token(config, label)
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30) as client:
        if page_token:
            # Graph's own @odata.nextLink: only ever sent back to Graph (it gets our bearer token)
            if not page_token.startswith(f"{GRAPH}/"):
                raise BrowseError(f"{label}: bad page token")
            url = page_token
        else:
            parent_id = (parent or {}).get("id")
            where = f"items/{quote(parent_id, safe='')}" if parent_id else "root"
            url = f"{await drive_url(client)}/{where}/children?$top={page_size}&$select={_SELECT}"
        data = await get(client, url, label)
    items = [item(raw) for raw in data.get("value", [])]
    # folders first, then by name (Graph's own order is by name only)
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    return BrowseResult(items=items, next_page_token=data.get("@odata.nextLink"))
