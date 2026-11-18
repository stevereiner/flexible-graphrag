"""OneDrive browse: the folders and files of a user's OneDrive, through Microsoft Graph
(browse/msgraph.py), with the form's app credentials, as the ingest reads them.

The drive is ``/users/{user_principal_name}/drive``, the one OneDriveReader reads. A folder's
``path`` ("Documents/Reports") is what its ``folder_path`` takes (``root:/{path}``); a file's ``id``
is what ``file_ids`` takes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

from browse import BrowseError, BrowseResult
from browse.msgraph import GRAPH, list_drive

LABEL = "OneDrive"


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    user = (config.get("user_principal_name") or "").strip()
    if not user and not page_token:
        raise BrowseError("OneDrive: fill in the user principal name first")

    async def drive_url(_client) -> str:
        return f"{GRAPH}/users/{quote(user, safe='@')}/drive"

    return await list_drive(config, LABEL, drive_url, parent, page_token, page_size)
