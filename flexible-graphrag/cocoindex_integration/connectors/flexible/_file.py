"""Lazy, change-aware file handle for flexible-graphrag data sources.

``FlexibleFile`` is a CocoIndex :class:`~cocoindex.resources.file.FileLike`
implementation for the 10 detector-backed transports (filesystem, S3, GCS,
Azure Blob, Google Drive, OneDrive, SharePoint, Box, Alfresco).

Unlike the Phase-1 eager approach (list → download all bytes up front), a
``FlexibleFile`` carries only *metadata* (size, modified time, and a
content fingerprint = ``etag`` when the source provides one, else the
``ordinal``/mtime) after listing.  The raw bytes are fetched **lazily** —
only when ``read()`` is first called — via a per-source single-key
``read_file_bytes`` download callable.

CocoIndex uses ``FileLike.__coco_memo_state__`` to decide whether a file
changed between runs: it first compares ``modified_time``; only when that
differs does it fall back to the content fingerprint.  For detector-backed
sources this means unchanged files are never downloaded on a re-run.

Design
------
* ``FlexibleFilePath`` — a :class:`~cocoindex.resources.file.FilePath` whose
  "resolved path" is the source's stable key string (e.g.
  ``s3://bucket/key``, ``onedrive://<file_id>``, an absolute local path).
* ``FlexibleFile`` — holds the ``FlexibleFilePath``, the pre-listed
  :class:`FileMetadata`, and a ``download`` callable used lazily by
  ``_read_impl``.  The single-key ``download`` callable reuses the existing
  ``sources/`` reader machinery (no new SDK code).
"""

from __future__ import annotations

import asyncio as _asyncio
from datetime import datetime as _datetime, timezone as _timezone
from pathlib import PurePath as _PurePath
from typing import Awaitable as _Awaitable, Callable as _Callable, Optional as _Optional, Union as _Union

from cocoindex.resources import file as _file
from cocoindex.resources.file import FileMetadata as _FileMetadata

# A single-key download callable: given the source key, return raw bytes.
# May be sync (``bytes``) or async (``Awaitable[bytes]``).
DownloadFn = _Callable[[str], _Union[bytes, _Awaitable[bytes]]]


def _fingerprint_from(etag: _Optional[str], ordinal: _Optional[int]) -> _Optional[bytes]:
    """Return a content fingerprint: ``etag`` when present, else ``ordinal``.

    Returning ``None`` makes ``FileLike`` fall back to hashing the full
    content — which we avoid for detector-backed sources by always providing
    at least the ordinal.
    """
    if etag:
        return str(etag).encode("utf-8", errors="replace")
    if ordinal is not None:
        return f"ord:{ordinal}".encode("utf-8")
    return None


def _to_datetime(value: _Union[str, int, float, _datetime, None]) -> _datetime:
    """Best-effort coercion of a listing modified-time into a ``datetime``."""
    if isinstance(value, _datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return _datetime.fromtimestamp(float(value))
        except (OverflowError, OSError, ValueError):
            return _datetime.fromtimestamp(0)
    if isinstance(value, str) and value:
        # Try ISO-8601 first (handles trailing Z).
        try:
            return _datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    # Unknown / empty — use epoch so change detection still works via fingerprint.
    return _datetime.fromtimestamp(0, tz=_timezone.utc).replace(tzinfo=None)


def _iso_modified(value: _Union[str, int, float, _datetime, None]) -> str:
    """A listing modified-time as ISO-8601 ("" when absent). A string that does not parse
    as a date is kept as-is rather than dropped."""
    if value is None or value == "":
        return ""
    if isinstance(value, _datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return _to_datetime(value).isoformat()
    try:
        return _datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
    except ValueError:
        return str(value)


class FlexibleFilePath(_file.FilePath[str]):
    """A :class:`FilePath` whose resolved value is the source's stable key.

    The stable key is the CocoIndex change-detection identity for the file
    (e.g. ``s3://bucket/key``).  ``resolve()`` returns it verbatim.
    """

    __slots__ = ()

    def __init__(self, key: str) -> None:
        super().__init__(None, _PurePath(key))

    def resolve(self) -> str:
        return str(self._path)

    def _with_path(self, path: _PurePath) -> "FlexibleFilePath":
        return type(self)(str(path))


class FlexibleFile(_file.FileLike[str]):
    """Lazy file handle for a detector-backed flexible-graphrag source.

    Parameters
    ----------
    key:
        Stable source key (CocoIndex change-detection identity).
    download:
        Single-key download callable — ``download(download_key) -> bytes``
        (sync or async).  Reuses the ``sources/`` reader machinery.
    download_key:
        The argument passed to ``download`` (often the object key/blob
        name/file_id, which may differ from the full stable ``key``).
    size:
        File size in bytes from the listing (``0`` if unknown).
    modified:
        Last-modified time from the listing (ISO string / epoch / datetime).
    etag:
        Backend content fingerprint (S3/GCS/Azure ETag) if available.
    ordinal:
        Fallback change token (e.g. mtime nanoseconds) when no ETag exists.
    reader_metadata:
        Full reader/placeholder metadata dict captured at list time
        (bucket, prefix, region, container, human path, …).  Carried through
        to the pipeline so downstream stores get the same enrichment as the
        standard get_documents() path.  Not part of the memo state.
    """

    __slots__ = (
        "_download", "_download_key", "_reader_metadata",
        "_file_name", "_display_path", "_file_type", "_source_type", "_modified_at",
    )

    def __init__(
        self,
        key: str,
        *,
        download: DownloadFn,
        download_key: _Optional[str] = None,
        size: int = 0,
        modified: _Union[str, int, float, _datetime, None] = None,
        etag: _Optional[str] = None,
        ordinal: _Optional[int] = None,
        reader_metadata: _Optional[dict] = None,
        file_name: _Optional[str] = None,
        display_path: _Optional[str] = None,
        file_type: str = "",
        source_type: str = "",
    ) -> None:
        metadata = _FileMetadata(
            size=int(size or 0),
            modified_time=_to_datetime(modified),
            content_fingerprint=_fingerprint_from(etag, ordinal),
        )
        super().__init__(FlexibleFilePath(key), _metadata=metadata)
        self._download = download
        self._download_key = download_key if download_key is not None else key
        self._reader_metadata = dict(reader_metadata) if reader_metadata else {}
        # Display / provenance fields threaded into the pipeline (not memoised —
        # they derive from the stable key so they never change the memo state).
        self._file_name = file_name or _PurePath(key).name
        self._display_path = display_path or key
        self._file_type = file_type
        self._source_type = source_type
        # Keep the listing's modified value, as ISO-8601. str(datetime) gives
        # "2026-09-30 22:18:43.533000+00:00" (space, not "T"), which an Elasticsearch /
        # OpenSearch index mapped by the default pipeline -- whose modified_at IS ISO --
        # rejects as a strict date, failing the whole batch.
        self._modified_at = _iso_modified(modified)

    @property
    def reader_metadata(self) -> dict:
        """Reader/placeholder metadata captured at list time (not memoised)."""
        return self._reader_metadata

    @property
    def display_file_name(self) -> str:
        """Human-readable filename for provenance / UI display."""
        return self._file_name

    @property
    def display_path(self) -> str:
        """Human-readable path (bucket/key, container/blob, absolute path, …)."""
        return self._display_path

    @property
    def file_type(self) -> str:
        """Extension without the leading dot (``pdf``, ``txt``, …)."""
        return self._file_type

    @property
    def source_type(self) -> str:
        """The datasource kind string (``s3``, ``azure_blob``, …)."""
        return self._source_type

    @property
    def modified_at(self) -> str:
        """Raw last-modified value from the listing (ISO string / epoch / '')."""
        return self._modified_at

    async def _fetch_metadata(self) -> _FileMetadata:
        # Metadata is always supplied at construction from the detector listing,
        # so this lazy path should not normally run.  Return a minimal record.
        return _FileMetadata(size=0, modified_time=_to_datetime(None))

    async def _read_impl(self, size: int = -1) -> bytes:
        """Fetch the raw bytes lazily via the single-key download callable."""
        if _asyncio.iscoroutinefunction(self._download):
            data = await self._download(self._download_key)
        else:
            # Run sync reader I/O off the event loop so we don't block.
            data = await _asyncio.to_thread(self._download, self._download_key)
            if _asyncio.iscoroutine(data):
                data = await data
        data = data or b""
        if size is not None and size >= 0:
            return data[:size]
        return data
