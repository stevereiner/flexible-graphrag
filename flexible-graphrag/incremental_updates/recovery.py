"""Catching up with what an event stream missed, in the periodic refresh.

The detectors with event streams (Alfresco, Nuxeo, S3, Box, Google Drive) ingest new and changed
files when their events arrive. A file whose event never came -- added or changed while the backend
was down, before the stream started, or whose ingest failed -- is still there at the next periodic
refresh, which used to leave it to the stream. The refresh now takes such a change itself once it has
seen it for RECOVERY_GRACE_SECONDS (INCREMENTAL_RECOVERY_GRACE_SECONDS, default 120): the stream has
had its chance by then. A change made before the detector's event stream went live (recorded by the
updater as ``detector._events_live_since``; never, when the sync has no event stream) can't come as an
event at all, so the refresh takes it at once. ``guard_in_flight`` keeps a stream ingest and a refresh ingest of the same
file from running at once.
"""
from __future__ import annotations

import functools
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Detectors whose event streams ingest new and changed files themselves
EVENT_DETECTORS = ('BoxDetector', 'GoogleDriveDetector', 'S3Detector', 'AlfrescoDetector', 'NuxeoDetector')

RECOVERY_GRACE_SECONDS = float(os.getenv("INCREMENTAL_RECOVERY_GRACE_SECONDS", "120"))

# The argument names that identify a file in the detectors' _process_via_backend
_KEY_ARGS = ("node_id", "uid", "file_id", "key", "object_name", "blob_path", "full_path")


def guard_in_flight(detector) -> None:
    """Make ``detector._process_via_backend`` skip a file it is already ingesting (by the file's
    id or path, its first argument): an event-stream ingest and a periodic-refresh one of the same
    file would otherwise both write it."""
    original = getattr(detector, "_process_via_backend", None)
    if original is None or getattr(detector, "_fg_in_flight_guarded", False):
        return
    in_flight = set()

    @functools.wraps(original)
    async def guarded(*args, **kwargs):
        key = args[0] if args else next((kwargs[k] for k in _KEY_ARGS if k in kwargs), None)
        if key is not None and key in in_flight:
            logger.info(f"{type(detector).__name__}: {key} is already being ingested -- skipping the second request")
            return None
        if key is not None:
            in_flight.add(key)
        try:
            return await original(*args, **kwargs)
        finally:
            in_flight.discard(key)

    detector._process_via_backend = guarded
    detector._fg_in_flight_guarded = True


def as_datetime(value: Any) -> Optional[datetime]:
    """A source's modification time as an aware datetime: a datetime, an ISO 8601 string (also
    with a space, or a ``+0000`` offset), or epoch seconds / milliseconds. None when it is none
    of these."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return as_datetime(float(text))
    text = text.replace("Z", "+00:00")
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)  # +0000 -> +00:00
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def source_changed(metadata, state) -> bool:
    """Whether the source has a newer version than the one recorded: its modification time is
    later than the recorded one (by more than a second; by a day when only a date was recorded);
    or, for a listing without modification times (S3's ordinal is its LastModified), its ordinal is
    later. False when that can't be told, so a refresh never re-ingests files just because their
    times are written differently."""
    new = as_datetime(getattr(metadata, "modified_timestamp", None))
    raw_old = getattr(state, "modified_timestamp", None)
    old = as_datetime(raw_old)
    if new and old:
        if isinstance(raw_old, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_old.strip()):
            # a date without a time (what an API ingest records for GCS and Azure: last_modified_date):
            # newer only on a later day, else every such file would look changed once
            return new.date() > old.date()
        return new - old > timedelta(seconds=1)
    if getattr(metadata, "modified_timestamp", None) is None and metadata.ordinal and getattr(state, "ordinal", None):
        return metadata.ordinal - state.ordinal > 1_000_000
    return False


def comparable_path(path: str) -> str:
    """A repository path to compare with another: no surrounding slashes, no /Company Home."""
    text = str(path).replace("\\", "/").strip().strip("/")
    if text.lower().startswith("company home/"):
        text = text[len("company home/"):]
    return text


def source_moved(detector, metadata, state) -> bool:
    """Whether a file is listed at another path than the one recorded (Alfresco, Nuxeo): it, or a
    folder above it inside the sync's roots, was moved or renamed. A folder's move or rename brings
    an event for the folder only, and leaves its files' modification times as they were."""
    name = type(detector).__name__
    if name == "AlfrescoDetector":
        listed = metadata.path
    elif name in ("NuxeoDetector", "MicrosoftGraphDetector", "BoxDetector"):
        listed = (getattr(metadata, "extra", None) or {}).get("file_path")
    else:
        return False
    recorded = getattr(state, "source_path", None)
    return bool(listed and recorded) and comparable_path(listed) != comparable_path(recorded)


def moved_out(state, current_path: str) -> bool:
    """Whether a document a sync tracks, whose event came from outside the sync's folders, was
    moved out of them -- not one whose auto sync was turned off (kept, but no longer followed; it
    may be outside the roots without having moved), and only when its path really changed."""
    if state is None or getattr(state, "auto_sync", None) is False:
        return False
    recorded = getattr(state, "source_path", None)
    return bool(recorded and current_path) and comparable_path(recorded) != comparable_path(current_path)


def predates_stream(detector, metadata) -> bool:
    """Whether a file's change was made before the detector's event stream went live (or the sync
    has no event stream), so no event will bring it."""
    live_since = getattr(detector, "_events_live_since", None)
    if live_since is None:
        return False
    modified = as_datetime(getattr(metadata, "modified_timestamp", None))
    if modified is None and type(detector).__name__ == "S3Detector" and metadata.ordinal:
        modified = datetime.fromtimestamp(metadata.ordinal / 1_000_000, tz=timezone.utc)  # LastModified
    return modified is not None and modified < live_since


class RecoveryTracker:
    """When a missed change has been waiting long enough: the first periodic refresh that sees it
    notes it, a refresh at least ``grace`` seconds later takes it."""

    def __init__(self, grace: float = RECOVERY_GRACE_SECONDS):
        self.grace = grace
        self._first_seen: Dict[Tuple, float] = {}

    def ready(self, key: Tuple) -> bool:
        now = time.monotonic()
        first = self._first_seen.setdefault(key, now)
        if now - first >= self.grace:
            self._first_seen.pop(key, None)
            return True
        return False

    def forget(self, key: Tuple) -> None:
        self._first_seen.pop(key, None)


def process_args(detector, metadata) -> Optional[tuple]:
    """The arguments of ``detector._process_via_backend`` for a file of its listing, or None for a
    detector this does not know."""
    name = type(detector).__name__
    extra = getattr(metadata, "extra", None) or {}
    path = metadata.path or ""
    if name == "GoogleDriveDetector":
        file_id = extra.get("file_id") or path
        return (file_id, extra.get("file_name") or file_id)
    if name == "BoxDetector":
        file_id = extra.get("file_id")
        return (file_id, path or file_id) if file_id else None
    if name == "S3Detector":
        bucket = getattr(detector, "bucket", "") or ""
        key = path[len(bucket) + 1:] if bucket and path.startswith(bucket + "/") else path
        return (key,)
    if name == "AlfrescoDetector":
        node_id = extra.get("node_id")
        return (node_id, os.path.basename(path), path) if node_id else None
    if name == "MicrosoftGraphDetector":
        file_id = extra.get("file_id")
        if not file_id:
            return None
        file_name = extra.get("file_name") or os.path.basename(extra.get("file_path") or "") or file_id
        return (file_id, file_name, extra.get("file_path") or f"/{file_name}", extra.get("folder_path") or "/")
    if name == "NuxeoDetector":
        uid = extra.get("node_id")
        return (uid, extra.get("name") or uid, extra.get("file_path") or path) if uid else None
    return None
