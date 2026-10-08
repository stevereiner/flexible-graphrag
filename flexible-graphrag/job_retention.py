"""How long PROCESSING_STATUS keeps jobs, and what the status endpoints return.

PROCESSING_STATUS (backend.py) is in-memory and grows with every ingest and auto sync run. A
job's ``documents`` -- the full text of everything it ingested -- is only needed by the code
that writes its document_state rows right after it finishes (post_ingestion_state, the sync
detectors). So:

* the status endpoints never return ``documents`` (:func:`public_view`);
* a finished job's documents are dropped once nothing still needs them (:func:`prune`);
* finished jobs are forgotten after ``JOB_RETENTION_MINUTES`` (default 60), and past
  ``JOB_RETENTION_MAX`` (default 200) the oldest finished ones go first. Running jobs stay.

:func:`prune` runs lazily, whenever the job list or a job's status is asked for and when a job
starts -- no background task.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

FINISHED = ("completed", "failed", "cancelled")
# Entry fields only the backend uses: never sent to clients
INTERNAL = ("documents",)
# A writer of document_state rows gives up after ten minutes (post_ingestion_state)
STATE_WRITER_LIMIT = timedelta(minutes=10)
# The sync detectors read a run's documents right after it finishes
SYNC_READ_GRACE = timedelta(minutes=1)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _finished_at(st: Dict[str, Any]) -> Optional[datetime]:
    if st.get("status") not in FINISHED:
        return None
    try:
        t = datetime.fromisoformat(str(st.get("updated_at") or st.get("started_at")).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return t if t.tzinfo else t.astimezone(timezone.utc)


def state_pending(st: Dict[str, Any], now: datetime) -> bool:
    """A finished job whose document_state rows are still being written from its documents."""
    done = _finished_at(st)
    if done is None:
        return False
    if st.get("records_state") and not st.get("state_recorded"):
        return now - done < STATE_WRITER_LIMIT
    return now - done < SYNC_READ_GRACE and "documents" in st


def public_view(st: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in st.items() if k not in INTERNAL}


def _parent(pid: str, st: Dict[str, Any]) -> str:
    return st.get("pass_of") or pid


def clear_finished(status: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """Forget finished jobs (with their passes), except those whose rows are still being written."""
    now = datetime.now(timezone.utc)
    done = {pid for pid, st in list(status.items())
            if not st.get("pass_of") and _finished_at(st) and not state_pending(st, now)}
    for pid, st in list(status.items()):
        if _parent(pid, st) in done:
            status.pop(pid, None)
    kept = sum(1 for st in status.values() if not st.get("pass_of"))
    return {"cleared": len(done), "kept": kept}


def prune(status: Dict[str, Dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc)
    ttl = timedelta(minutes=_env_int("JOB_RETENTION_MINUTES", 60))
    cap = _env_int("JOB_RETENTION_MAX", 200)

    finished = []
    for pid, st in list(status.items()):
        done = _finished_at(st)
        if done is None:
            continue
        if "documents" in st and not state_pending(st, now):
            st.pop("documents", None)
        if not st.get("pass_of"):
            finished.append((done, pid))

    finished.sort()
    expired = {pid for done, pid in finished
               if now - done > ttl and not state_pending(status[pid], now)}
    over = [pid for _, pid in finished if pid not in expired]
    for pid in over[:max(0, len(over) - cap)]:
        if not state_pending(status[pid], now):
            expired.add(pid)
    if expired:
        for pid, st in list(status.items()):
            if _parent(pid, st) in expired:
                status.pop(pid, None)
