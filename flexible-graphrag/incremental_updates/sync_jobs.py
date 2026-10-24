"""Auto sync runs on the Processing tab's Jobs list (GET /api/processing-status).

A sync run is a backend ingest with a processing id starting ``incremental_`` (one per document,
made by each detector). This module gives those entries what the list shows for them:

* ``data_source`` and ``label`` (the document's path) -- an /api/ingest job gets them from the
  request (main._label_job); a sync run had none;
* ``sync_action``: ``add``, ``update`` or ``delete``. The engine runs the ADD half of an update
  under :func:`updating`; anything else reaching the backend is an add;
* a fresh entry per run: a detector reuses one id per document, so a later run would overwrite
  the earlier one -- the finished entry is kept under a new id instead (without its documents);
* an entry for a delete (:func:`record_delete`), which never goes through the backend.
"""

from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

SYNC_PREFIX = "incremental_"
FINISHED = ("completed", "failed", "cancelled")


def processing_id(kind: str, key: str) -> str:
    """A sync run's processing id for one document: ``incremental_<kind>_`` and a readable tail of
    ``key`` (its path or id) plus a hash of all of it. One per document, never shared: a truncated
    key alone gave every object under one prefix (S3, Azure, GCS) or one drive's item ids
    (Microsoft Graph, Box) the same id, so concurrent runs overwrote each other's status and
    their document_state was never written."""
    import hashlib
    import re
    tail = re.sub(r"[^A-Za-z0-9]+", "_", str(key)).strip("_")[-16:]
    digest = hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:10]
    return f"{SYNC_PREFIX}{kind}_{tail}_{digest}"

_action: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("fg_sync_action", default=None)


@contextmanager
def updating() -> Iterator[None]:
    """Mark backend runs started inside as the ADD half of an update."""
    token = _action.set("update")
    try:
        yield
    finally:
        _action.reset(token)


def is_sync_run(processing_id: Optional[str]) -> bool:
    return bool(processing_id) and str(processing_id).startswith(SYNC_PREFIX)


def label_for(paths: Optional[List[str]], kwargs: Dict[str, Any]) -> Optional[str]:
    """The document a sync run is for: a repository path from its source config, else its path."""
    for key, cfg in kwargs.items():
        if not key.endswith("_config") or not isinstance(cfg, dict):
            continue
        for nd in cfg.get("nodeDetails") or []:
            if isinstance(nd, dict) and (nd.get("path") or nd.get("name")):
                return nd.get("path") or nd.get("name")
        for field in ("key", "blob", "object_name", "file_path", "path"):
            if cfg.get(field):
                return str(cfg[field])
    return str(paths[0]) if paths else None


def begin(processing_id: str, data_source: Optional[str], label: Optional[str]) -> None:
    """At the start of a sync run (backend._process_documents_async)."""
    from backend import PROCESSING_STATUS

    old = PROCESSING_STATUS.get(processing_id)
    if old and old.get("status") in FINISHED:
        # Keep the earlier run on the list; its documents were only needed while it ran
        PROCESSING_STATUS[f"{processing_id}_{int(time.time() * 1000)}"] = {
            k: v for k, v in old.items() if k != "documents"}
        del PROCESSING_STATUS[processing_id]
    entry = PROCESSING_STATUS.setdefault(processing_id, {})
    entry.update({
        "data_source": data_source,
        "label": label,
        "sync_action": _action.get() or "add",
        "started_at": datetime.now().isoformat(),
    })


def record_delete(data_source: Optional[str], path: Optional[str]) -> None:
    """A document deleted in the repository and removed from the stores by its sync."""
    from backend import PROCESSING_STATUS

    now = datetime.now().isoformat()
    name = (path or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "document"
    pid = f"{SYNC_PREFIX}del_{int(time.time() * 1000)}"
    PROCESSING_STATUS[pid] = {
        "processing_id": pid,
        "status": "completed",
        "progress": 100,
        "message": f"Removed {name} from the stores (deleted in the repository).",
        "data_source": data_source,
        "label": path,
        "sync_action": "delete",
        "started_at": now,
        "updated_at": now,
    }
