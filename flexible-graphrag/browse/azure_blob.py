"""Azure Blob browse: the "folders" and blobs of one container, signed in as the ingest signs in
(sources/azure_blob.py: a connection string, else the account URL + account key).

Blob storage has no folders: a folder is a name prefix under ``delimiter="/"``. The ingest takes
the container plus either ``prefix`` (a folder, "docs/reports/") or ``blob`` (one blob's full name,
"docs/a.pdf"), so ``id`` and ``path`` are both that prefix / name. Pages use the SDK's continuation
token.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from browse import BrowseError, BrowseItem, BrowseResult

LABEL = "Azure Blob"
_MAX_RESULTS = 5000  # the service's own maximum per page


def _container(config: Dict[str, Any]):
    from azure.storage.blob import ContainerClient

    container = (config.get("container_name") or "").strip()
    if not container:
        raise BrowseError("Azure Blob: fill in the container name first")
    connection_string = (config.get("connection_string") or "").strip()
    account_url = (config.get("account_url") or "").strip()
    account_key = (config.get("account_key") or "").strip()
    try:
        if connection_string:
            return ContainerClient.from_connection_string(connection_string, container)
        if account_url and account_key:
            return ContainerClient(account_url, container, credential=account_key)
    except ValueError as e:  # a malformed connection string / URL
        raise BrowseError(f"Azure Blob: {e}")
    raise BrowseError("Azure Blob: fill in the account URL and account key (or a connection string) first")


def _error(e: Exception, container: str) -> BrowseError:
    from azure.core.exceptions import (ClientAuthenticationError, HttpResponseError, ResourceNotFoundError,
                                       ServiceRequestError)

    message = (getattr(e, "message", None) or str(e) or type(e).__name__).splitlines()[0]
    if isinstance(e, ClientAuthenticationError):
        return BrowseError(f"Azure Blob sign-in failed: {message}", status_code=401)
    if isinstance(e, ResourceNotFoundError):
        return BrowseError(f"Azure Blob: no container named '{container}'", status_code=404)
    if isinstance(e, HttpResponseError) and e.status_code == 403:
        return BrowseError(f"Azure Blob: no permission to list container '{container}' ({message})",
                           status_code=403)
    if isinstance(e, ServiceRequestError):
        return BrowseError(f"Azure Blob: could not reach the storage account ({message})", status_code=502)
    if isinstance(e, ValueError):  # e.g. an account key that is not base64
        return BrowseError(f"Azure Blob: {message}", status_code=400)
    return BrowseError(f"Azure Blob: {message}", status_code=502)


def _name(prefix_or_blob: str) -> str:
    return prefix_or_blob.rstrip("/").rsplit("/", 1)[-1]


def _is_directory_marker(blob, prefix: str) -> bool:
    """The placeholder blobs tools create for a folder: "dir/" itself, or (hierarchical
    namespace / Storage Explorer) an empty blob with metadata hdi_isfolder=true."""
    name = blob.name or ""
    if name == prefix or name.endswith("/"):
        return True
    return str((getattr(blob, "metadata", None) or {}).get("hdi_isfolder", "")).lower() == "true"


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    from azure.storage.blob import BlobPrefix

    client = _container(config)
    container = client.container_name
    prefix = (parent or {}).get("id") or ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"  # a folder is opened by its prefix

    def page():
        pages = client.walk_blobs(name_starts_with=prefix or None, delimiter="/", include=["metadata"],
                                  results_per_page=min(page_size, _MAX_RESULTS)).by_page(
            continuation_token=page_token or None)
        try:
            entries = list(next(pages))
        except StopIteration:
            entries = []
        return entries, pages.continuation_token

    try:
        entries, next_token = await asyncio.to_thread(page)
    except BrowseError:
        raise
    except Exception as e:
        raise _error(e, container)
    items = []
    for entry in entries:
        if isinstance(entry, BlobPrefix):
            items.append(BrowseItem(id=entry.name, name=_name(entry.name), path=entry.name, kind="folder"))
        elif not _is_directory_marker(entry, prefix):
            modified = getattr(entry, "last_modified", None)
            settings = getattr(entry, "content_settings", None)
            items.append(BrowseItem(
                id=entry.name, name=_name(entry.name), path=entry.name, kind="file",
                size=getattr(entry, "size", None),
                modified=modified.isoformat() if hasattr(modified, "isoformat") else modified,
                mime_type=getattr(settings, "content_type", None) if settings else None))
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    return BrowseResult(items=items, next_page_token=next_token or None)
