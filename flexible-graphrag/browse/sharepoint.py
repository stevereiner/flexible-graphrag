"""SharePoint browse: the folders and files of the site's document library, through Microsoft Graph
(browse/msgraph.py), with the form's app credentials, as the ingest reads them.

The library is the site's default drive (``/sites/{id}/drive``), the one the ingest's by-id
downloads use (sources/sharepoint.py). A folder's ``path`` ("Reports/2024") is what
SharePointReader's ``sharepoint_folder_path`` takes (``root:/{path}``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from browse import BrowseError, BrowseResult
from browse.msgraph import GRAPH, get, list_drive

LABEL = "SharePoint"


async def _site_id(client: httpx.AsyncClient, config: Dict[str, Any]) -> str:
    """The configured site_id, else site_name resolved as the ingest does (sources/sharepoint.py)."""
    site_id = (config.get("site_id") or "").strip()
    if site_id:
        return site_id
    name = (config.get("site_name") or "").strip()
    if not name:
        raise BrowseError("SharePoint: fill in the site name first")
    try:
        site = await get(client, f"{GRAPH}/sites/root:/sites/{quote(name)}", LABEL)
        if site.get("id"):
            return site["id"]
    except BrowseError:
        pass
    sites = await get(client, f"{GRAPH}/sites?search={quote(name)}", LABEL)
    for s in sites.get("value", []):
        if (s.get("name") or "").lower() == name.lower():
            return s["id"]
    raise BrowseError(f"SharePoint: no site named {name!r}", status_code=404)


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    async def drive_url(client: httpx.AsyncClient) -> str:
        return f"{GRAPH}/sites/{quote(await _site_id(client, config))}/drive"

    return await list_drive(config, LABEL, drive_url, parent, page_token, page_size)
