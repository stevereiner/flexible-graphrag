from datetime import datetime, timedelta

import job_retention as jr


def _at(minutes_ago: float) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).isoformat()


def test_public_view_leaves_out_documents():
    st = {"status": "processing", "progress": 40, "documents": ["full text"]}
    assert jr.public_view(st) == {"status": "processing", "progress": 40}
    assert "documents" in st  # the backend's copy is untouched


def test_prune_drops_documents_once_nothing_needs_them():
    status = {
        "running": {"status": "processing", "updated_at": _at(30), "documents": ["x"]},
        "recorded": {"status": "completed", "updated_at": _at(2), "records_state": True,
                     "state_recorded": True, "documents": ["x"]},
        "writing": {"status": "completed", "updated_at": _at(2), "records_state": True, "documents": ["x"]},
        "sync_just_done": {"status": "completed", "updated_at": _at(0.2), "documents": ["x"]},
        "sync_done": {"status": "completed", "updated_at": _at(5), "documents": ["x"]},
    }
    jr.prune(status)
    has_docs = {pid for pid, st in status.items() if "documents" in st}
    assert has_docs == {"running", "writing", "sync_just_done"}


def test_prune_forgets_old_and_excess_finished_jobs(monkeypatch):
    monkeypatch.setenv("JOB_RETENTION_MINUTES", "60")
    monkeypatch.setenv("JOB_RETENTION_MAX", "2")
    status = {
        "old": {"status": "completed", "updated_at": _at(90)},
        "old-1": {"status": "completed", "updated_at": _at(90), "pass_of": "old"},
        "running_long": {"status": "processing", "updated_at": _at(500)},
        "a": {"status": "completed", "updated_at": _at(30)},
        "b": {"status": "failed", "updated_at": _at(20)},
        "c": {"status": "completed", "updated_at": _at(10)},
    }
    jr.prune(status)
    # "old" expired (with its pass), "a" was the oldest past the cap of 2; running jobs stay
    assert set(status) == {"running_long", "b", "c"}


def test_clear_finished_keeps_running_and_pending_rows():
    status = {
        "done": {"status": "completed", "updated_at": _at(1)},
        "done-1": {"status": "completed", "updated_at": _at(1), "pass_of": "done"},
        "run": {"status": "processing", "updated_at": _at(1)},
        "writing": {"status": "completed", "updated_at": _at(1), "records_state": True, "documents": ["x"]},
        "incremental_s3_my-report_pdf": {"status": "completed", "updated_at": _at(5)},
    }
    assert jr.clear_finished(status) == {"cleared": 2, "kept": 2}
    assert set(status) == {"run", "writing"}
