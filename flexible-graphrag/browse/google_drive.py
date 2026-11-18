"""Google Drive browse: the folders and files the form's service account can see, as the ingest
reads them (sources/google_drive.py: ``credentials`` JSON pasted in the form, else a
``credentials_path`` key file; GoogleDriveReader with supportsAllDrives).

Drive is id-based: the ingest takes a folder id (``folder_id``, which wins) or file ids
(``file_ids``). ``path`` here is only for display (the names browsed through). A service account's
own "My Drive" is usually empty: what it reads is shared with it, so the root lists My Drive,
"Shared with me" and (first page) the shared drives it belongs to. Google Docs / Sheets / Slides
are listed (the ingest exports them to docx / xlsx / pptx); other Google-native types are not.
Pages use Drive's ``pageToken``.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from browse import BrowseError, BrowseItem, BrowseResult

LABEL = "Google Drive"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]  # GoogleDriveReader's own scope
FOLDER = "application/vnd.google-apps.folder"
# Google-native types the reader exports (GoogleDriveReader._mimetypes); other native types
# (forms, drawings, shortcuts, sites...) it cannot download
EXPORTED = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
}
_FIELDS = "nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink)"
_MAX_PAGE = 1000  # Drive's own maximum pageSize
_ID = re.compile(r"[A-Za-z0-9_-]+")  # Drive ids: also keeps the folder id out of the query's quoting


def _service_account_key(config: Dict[str, Any]) -> Dict[str, Any]:
    """The service account key the ingest would use: the pasted JSON, else the key file."""
    raw = config.get("credentials")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise BrowseError("Google Drive: the service account credentials are not valid JSON")
    path = (config.get("credentials_path") or "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                key = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise BrowseError(f"Google Drive: could not read credentials_path ({type(e).__name__})")
        if key.get("type") != "service_account":
            raise BrowseError("Google Drive: browsing needs a service account key (credentials_path is "
                              "an OAuth client file)")
        return key
    raise BrowseError("Google Drive: paste the service account credentials (JSON) first")


def _service(config: Dict[str, Any]):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    key = _service_account_key(config)
    try:
        creds = service_account.Credentials.from_service_account_info(key, scopes=SCOPES)
    except (ValueError, KeyError) as e:
        raise BrowseError(f"Google Drive: not a usable service account key ({e})")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _error(e: Exception) -> BrowseError:
    """A Google API / auth error as a BrowseError, by status."""
    from google.auth.exceptions import GoogleAuthError, RefreshError
    from googleapiclient.errors import HttpError

    if isinstance(e, HttpError):
        status = getattr(e.resp, "status", None)
        try:
            status = int(status)
        except (TypeError, ValueError):
            status = None
        reason = e._get_reason() if hasattr(e, "_get_reason") else str(e)
        if status == 401:
            return BrowseError(f"Google Drive sign-in failed: {reason}", status_code=401)
        if status == 404:
            return BrowseError(f"Google Drive: folder not found or not shared with the service account "
                               f"({reason})", status_code=404)
        if status == 403:
            return BrowseError(f"Google Drive: {reason}", status_code=403)
        return BrowseError(f"Google Drive: {reason}", status_code=502)
    if isinstance(e, (RefreshError, GoogleAuthError)):
        # the token exchange: a revoked / deleted key, a wrong private key
        return BrowseError(f"Google Drive sign-in failed: {str(e).splitlines()[0]}", status_code=401)
    return BrowseError(f"Google Drive: {str(e).splitlines()[0] if str(e) else type(e).__name__}",
                       status_code=502)


def _item(raw: Dict[str, Any], parent_path: str) -> Optional[BrowseItem]:
    mime = raw.get("mimeType") or ""
    is_folder = mime == FOLDER
    if mime.startswith("application/vnd.google-apps.") and not is_folder and mime not in EXPORTED:
        return None  # nothing the ingest can read
    name = raw.get("name") or raw["id"]
    size = raw.get("size")
    return BrowseItem(
        id=raw["id"],
        name=name,
        path=f"{parent_path}/{name}".strip("/"),
        kind="folder" if is_folder else "file",
        size=int(size) if size not in (None, "") and not is_folder else None,
        modified=raw.get("modifiedTime"),
        mime_type=None if is_folder else mime,
        web_url=raw.get("webViewLink"),
    )


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    service = _service(config)
    folder_id = (parent or {}).get("id")
    parent_path = (parent or {}).get("path") or ""
    if folder_id:
        if not _ID.fullmatch(str(folder_id)):
            raise BrowseError("Google Drive: not a Drive folder id", status_code=400)
        q = f"'{folder_id}' in parents and trashed = false"
    else:
        q = "('root' in parents or sharedWithMe = true) and trashed = false"

    def page():
        result = service.files().list(
            q=q, fields=_FIELDS, pageSize=min(page_size, _MAX_PAGE), pageToken=page_token or None,
            includeItemsFromAllDrives=True, supportsAllDrives=True, orderBy="folder,name_natural",
        ).execute()
        drives: List[Dict[str, Any]] = []
        if not folder_id and not page_token:
            drives = service.drives().list(pageSize=100, fields="drives(id, name)").execute().get("drives", [])
        return result, drives

    try:
        result, drives = await asyncio.to_thread(page)
    except BrowseError:
        raise
    except Exception as e:
        raise _error(e)
    # a shared drive's id is its root folder's id: the ingest takes it as a folder_id
    items = [BrowseItem(id=d["id"], name=d.get("name") or d["id"], path=d.get("name") or d["id"], kind="folder")
             for d in drives]
    items += [i for i in (_item(f, parent_path) for f in result.get("files", [])) if i]
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    return BrowseResult(items=items, next_page_token=result.get("nextPageToken") or None)
