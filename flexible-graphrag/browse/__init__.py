"""Browse a data source one folder level at a time: what the UIs' source browser shows, so a user
picks a folder instead of typing its path or id (POST /api/browse).

Each source has a small module here with ``async def browse(config, parent, page_token,
page_size) -> BrowseResult``. ``config`` is the same as the source's ingest config (its
credentials and fixed root: site, bucket, url...), so browse sees what the ingest will read.
``parent`` None = the source's root. One level, paged, never recursive.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

# data_source -> module in this package (build order: planning/source-browser-plan.md)
_MODULES = {
    "sharepoint": "browse.sharepoint",
    "onedrive": "browse.onedrive",
    "box": "browse.box",
    "cmis": "browse.cmis",
    "s3": "browse.s3",
    "gcs": "browse.gcs",
    "google_drive": "browse.google_drive",
    "azure_blob": "browse.azure_blob",
    "alfresco": "browse.alfresco",
    "nuxeo": "browse.nuxeo",
}


class BrowseError(Exception):
    """A browse that can't be answered: bad credentials, missing fields, a folder that is gone."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class BrowseItem(BaseModel):
    id: str
    name: str
    # the source's own path ("/Reports/2024"), "" when it has none (id-only sources)
    path: str = ""
    kind: str  # "folder" | "file"
    size: Optional[int] = None
    modified: Optional[str] = None  # ISO 8601
    mime_type: Optional[str] = None
    web_url: Optional[str] = None


class BrowseResult(BaseModel):
    items: List[BrowseItem]
    next_page_token: Optional[str] = None


def supported_sources() -> List[str]:
    return list(_MODULES)


async def browse(data_source: str, config: Dict[str, Any], parent: Optional[Dict[str, Any]],
                 page_token: Optional[str], page_size: int) -> BrowseResult:
    name = _MODULES.get(data_source)
    if not name:
        raise BrowseError(f"Browsing {data_source} is not supported", status_code=404)
    module = importlib.import_module(name)
    return await module.browse(config or {}, parent or None, page_token, page_size)
