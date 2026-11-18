"""GCS browse: the "folders" and objects of one bucket, with the credentials the ingest uses
(sources/gcs.py: the form's service-account JSON, else ``service_account_key_path``, else Google's
application-default credentials, as GCSReader falls back).

GCS has no folders: a folder is a prefix under ``delimiter="/"``. The UI's ingest config carries the
bucket plus one ``prefix``, and GCSReader lists a prefix as a directory, so only folders are picked
here (``id`` = ``path`` = the prefix, "docs/2024/"). One object would need the reader's ``key``,
which GCSConfig doesn't take from the UI. Pages use the API's page token.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Optional

from browse import BrowseError, BrowseItem, BrowseResult

LABEL = "GCS"
_MAX_RESULTS = 1000  # the JSON API's own maximum per page


def _client_and_bucket(config: Dict[str, Any]):
    from google.cloud import storage

    bucket = str(config.get("bucket_name") or config.get("bucket") or "").strip()
    if not bucket:
        raise BrowseError("GCS: fill in the bucket name first")
    raw = config.get("credentials") or ""
    key_path = str(config.get("service_account_key_path") or "").strip()
    if isinstance(raw, dict):
        info = raw
    elif str(raw).strip():
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            raise BrowseError("GCS: the service account credentials are not valid JSON")
    else:
        info = None
    try:
        if info:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_info(info)
            return storage.Client(credentials=creds, project=info.get("project_id")), bucket
        if key_path:
            if not os.path.isfile(key_path):
                raise BrowseError(f"GCS: the service account key file '{key_path}' was not found "
                                  f"(relative paths are from the backend's folder)")
            return storage.Client.from_service_account_json(key_path), bucket
        return storage.Client(), bucket  # application-default credentials
    except BrowseError:
        raise
    except Exception as e:
        raise _error(e, bucket)


def _error(e: Exception, bucket: str) -> BrowseError:
    from google.api_core import exceptions as gexc
    from google.auth import exceptions as aexc

    message = getattr(e, "message", None) or (str(e).splitlines()[0] if str(e) else type(e).__name__)
    if isinstance(e, BrowseError):
        return e
    if isinstance(e, getattr(aexc, "MalformedError", ())):  # a service account JSON missing fields
        return BrowseError(f"GCS: the service account credentials are not usable ({message})", status_code=400)
    if isinstance(e, (aexc.RefreshError, aexc.DefaultCredentialsError, gexc.Unauthorized)):
        return BrowseError(f"GCS sign-in failed: {message}", status_code=401)
    if isinstance(e, gexc.NotFound):
        return BrowseError(f"GCS: no bucket named '{bucket}'", status_code=404)
    if isinstance(e, gexc.Forbidden):
        return BrowseError(f"GCS: no permission to list bucket '{bucket}' ({message})", status_code=403)
    if isinstance(e, gexc.BadRequest):
        return BrowseError(f"GCS: {message}", status_code=400)
    if isinstance(e, (ValueError, KeyError)):  # a service account JSON missing fields
        return BrowseError(f"GCS: the service account credentials are not usable ({message})", status_code=400)
    return BrowseError(f"GCS: {message}", status_code=502)


def _name(prefix_or_key: str) -> str:
    return prefix_or_key.rstrip("/").rsplit("/", 1)[-1]


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    client, bucket = _client_and_bucket(config)
    prefix = (parent or {}).get("id") or ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"  # a folder is opened by its prefix

    def page():
        it = client.list_blobs(bucket, prefix=prefix or None, delimiter="/",
                               page_size=min(page_size, _MAX_RESULTS), page_token=page_token or None)
        first = next(it.pages, None)
        if first is None:
            return [], [], None
        blobs = list(first)
        return sorted(first.prefixes), blobs, it.next_page_token

    try:
        prefixes, blobs, next_token = await asyncio.to_thread(page)
    except Exception as e:
        raise _error(e, bucket)
    items = [BrowseItem(id=p, name=_name(p), path=p, kind="folder") for p in prefixes]
    for blob in blobs:
        name = blob.name
        if name == prefix or name.endswith("/"):
            continue  # "folder" placeholder objects (console-created)
        updated = getattr(blob, "updated", None)
        items.append(BrowseItem(id=name, name=_name(name), path=name, kind="file", size=blob.size,
                                modified=updated.isoformat() if hasattr(updated, "isoformat") else updated,
                                mime_type=getattr(blob, "content_type", None)))
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    return BrowseResult(items=items, next_page_token=next_token or None)
