"""
Integration tests — filesystem incremental updates.

Tests the full add / modify / delete cycle using the filesystem data source
and the /api/sync/* endpoints.

**Files under ``INTEGRATION_WATCH_DIR`` (see constants below)**

- **Seed (bulk ingest)**: ``SEED_FILE_NAME`` — written *before* ``POST /api/ingest`` + ``enable_sync`` so
  one document is indexed via the **same bulk ingest path** as registration (not only watchdog “add”).
- **Per-test (incremental add/change)**: ``incremental_add.txt``, ``incremental_modify.txt``,
  ``incremental_delete.txt``, ``multi_a.txt``, ``multi_b.txt`` — created by tests, deleted in ``finally``
  where applicable. Seed is removed in session teardown so the folder can end empty.

Requires:
  - Backend with incremental Postgres initialized; ``INTEGRATION_WATCH_DIR`` set to a dedicated folder.
  - Session fixture: seed file + ``POST /api/ingest`` with ``enable_sync: true`` (see ``_register_incremental_watch_via_ingest``).
  - With ``run_profile.py``, use ``--profile neo4j-llamaindex-incremental`` (integration profiles default ``ENABLE_INCREMENTAL_UPDATES=false`` for speed).

Run:
    pytest tests/integration/test_incremental.py -m incremental -s
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

import pytest

from tests.integration.api_client import APIClient
from tests.integration.env_helpers import normalized_integration_watch_dir

logger = logging.getLogger(__name__)

# True when INTEGRATION_WATCH_DIR is non-empty (same path the backend filesystem datasource monitors).
# Set in the shell or in repo / flexible-graphrag .env (loaded by tests/integration/conftest.py).
# Values wrapped in quotes in .env (INTEGRATION_WATCH_DIR="C:\\path") are normalized.
_watch = normalized_integration_watch_dir()
HAS_INTEGRATION_WATCH_DIR = bool(_watch)

# How long to wait for the incremental engine to pick up a filesystem change.
# Default 60 s: Windows watchdog fires every ~30 s, plus ingestion time.
SYNC_WAIT = int(os.getenv("INTEGRATION_SYNC_WAIT", "60"))

# Minimum number of search results we expect after indexing
MIN_RESULTS = 1

# Files written by the session fixture and bulk-ingested during registration.
# Each test that is NOT "add" operates on its pre-placed file — no implicit ADD step.
SEED_FILE_NAME   = "integration_seed_baseline.txt"
SEED_PHRASE      = "seed_baseline_flexible_graphrag_integration"

MODIFY_FILE_NAME = "incremental_modify.txt"
MODIFY_PHRASE    = "modify_baseline_phrase_qr5"   # unique phrase in the pre-placed file

DELETE_FILE_NAME = "incremental_delete.txt"
DELETE_PHRASE    = "delete_baseline_phrase_jk8"   # unique phrase in the pre-placed file


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    logger.info("Written: %s (%d bytes)", path, len(content))


def _delete_file(path: Path) -> None:
    path.unlink(missing_ok=True)
    logger.info("Deleted: %s", path)


def _wait_for_file_gone(path: Path, timeout: float = 20.0, poll: float = 0.5) -> None:
    """Block until *path* no longer exists AND is absent from its parent directory listing.

    On Windows, ``Path.unlink()`` can return before the deletion is reflected
    in directory listings used by the filesystem watcher.  We check BOTH
    ``path.exists()`` (stat-based) AND ``os.listdir`` (listing-based) so that
    the very first ``sync_now`` call sees the file as absent and triggers index
    deletion rather than skipping it as an unchanged existing file.

    After confirming the file is gone from OS listings, we sleep an extra second
    to let the Windows VFS cache settle before the server-side ``rglob`` scan runs.
    """
    deadline = time.time() + timeout
    parent = path.parent
    name_lower = path.name.lower()
    while time.time() < deadline:
        # Check stat first (fast path)
        if path.exists():
            time.sleep(poll)
            continue
        # Also check directory listing — Windows may cache the entry for a bit
        try:
            entries = {e.lower() for e in os.listdir(parent)}
        except OSError:
            entries = set()
        if name_lower not in entries:
            # Extra settling delay: rglob on the server side may use a different
            # kernel path than os.listdir; give the VFS cache ~1s to converge.
            time.sleep(1.0)
            return
        time.sleep(poll)
    # Log a warning but don't fail — _wait_for_no_results will handle the outcome
    logger.warning("_wait_for_file_gone: %s still visible in directory after %.1fs", path, timeout)


def _wait_for_results(
    client: APIClient,
    query: str,
    expected_term: str,
    max_wait: int = SYNC_WAIT,
    poll: float = 3.0,
) -> bool:
    """Poll search until expected_term appears or max_wait expires."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        # Trigger a manual sync then search
        try:
            client.sync_now()
        except Exception:
            pass
        results = client.search(query, top_k=5)
        logger.info(
            "_wait_for_results: got %d results for %r; snippets: %s",
            len(results.results),
            query,
            [r.get("content", "")[:60] for r in results.results],
        )
        for r in results.results:
            text = (r.get("content") or r.get("text") or "").lower()
            if expected_term.lower() in text:
                logger.info("Found %r in results after %.1fs", expected_term, max_wait - (deadline - time.time()))
                return True
        time.sleep(poll)
    return False


def _wait_for_no_results(
    client: APIClient,
    query: str,
    absent_term: str,
    max_wait: int = SYNC_WAIT,
    poll: float = 3.0,
) -> bool:
    """Poll search until absent_term is gone from all results.

    On Windows the watchdog delete event can fire up to ~30 s after the file is
    unlinked (OS polling interval), and the resulting sync_now call may take
    several seconds to process other queued events (e.g. new-file ingestion).
    That means the last loop iteration's sync_now can push past the deadline
    before we get a chance to search.  A single final search after the loop
    catches this common edge-case without inflating the normal timeout.
    """
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            client.sync_now()
        except Exception:
            pass
        results = client.search(query, top_k=5)
        found = any(
            absent_term.lower() in (r.get("content") or r.get("text") or "").lower()
            for r in results.results
        )
        if not found:
            logger.info("Term %r no longer present after %.1fs", absent_term, max_wait - (deadline - time.time()))
            return True
        time.sleep(poll)
    # Final check: the last sync_now may have completed the deletion just as the
    # deadline expired (common on Windows with 30 s watchdog polling intervals).
    try:
        results = client.search(query, top_k=5)
        found = any(
            absent_term.lower() in (r.get("content") or r.get("text") or "").lower()
            for r in results.results
        )
        if not found:
            logger.info("Term %r gone on final post-deadline check (%.1fs elapsed)", absent_term, max_wait)
            return True
    except Exception:
        pass
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Session: register incremental filesystem datasource (same as UI enable_sync)
# ──────────────────────────────────────────────────────────────────────────────

REGISTER_MAX_WAIT = int(os.getenv("INTEGRATION_REGISTER_MAX_WAIT", "600"))


@pytest.fixture(scope="session", autouse=True)
def _register_incremental_watch_via_ingest(client: APIClient):
    """When INTEGRATION_WATCH_DIR is set: seed one file, then POST /api/ingest + enable_sync.

    The seed exists **before** bulk ingest so it is indexed via the registration ingest pass (distinct
    from later tests that rely on incremental sync after files are added under an already-registered watch).
    Teardown removes the seed so the watch folder can be empty at session end.
    """
    raw = normalized_integration_watch_dir()
    if not raw:
        yield
        return

    watch_root = Path(raw).resolve()
    watch_root.mkdir(parents=True, exist_ok=True)

    # Write all pre-placed files before registration so they are bulk-ingested.
    # Each test that is not "add" operates on its own pre-placed file — no implicit ADD step.
    seed_path   = watch_root / SEED_FILE_NAME
    modify_path = watch_root / MODIFY_FILE_NAME
    delete_path = watch_root / DELETE_FILE_NAME

    seed_path.write_text(
        f"Baseline seed document. Unique phrase: {SEED_PHRASE}.\n"
        "Indexed via bulk POST /api/ingest with enable_sync (registration pass).\n",
        encoding="utf-8",
    )
    modify_path.write_text(
        f"Document for modify test. Unique phrase: {MODIFY_PHRASE}.\n"
        "This file will be overwritten by test_modify_file_updates_index.\n",
        encoding="utf-8",
    )
    delete_path.write_text(
        f"Document for delete test. Unique phrase: {DELETE_PHRASE}.\n"
        "This file will be deleted by test_delete_file_removes_from_index.\n",
        encoding="utf-8",
    )
    logger.info("Wrote pre-placed files before registration ingest: %s, %s, %s",
                seed_path.name, modify_path.name, delete_path.name)

    watch = str(watch_root)
    logger.info(
        "Incremental tests: registering filesystem datasource via /api/ingest enable_sync=true: %s",
        watch,
    )
    result = client.ingest_filesystem_paths_with_sync([watch], enable_sync=True)
    assert result.processing_id, "No processing_id from /api/ingest (enable_sync registration)"
    status = client.wait_for_completion(result.processing_id, max_wait=REGISTER_MAX_WAIT)
    assert status.status == "completed", (
        f"Registration ingest did not complete: {status}. "
        "Check API logs; ensure incremental Postgres is up and paths exist on the API host."
    )
    logger.info("Incremental watch registration ingest completed: %s", status.message)

    # Wait until the watchdog is actually watching before letting tests write files.
    # The orchestrator detects new datasources on a polling interval (~30s), so tests
    # that write files immediately after registration miss the watchdog entirely.
    logger.info("Waiting for watchdog to start watching %s ...", watch)
    watching = client.wait_for_watching(min_updaters=1, max_wait=90, poll=2.0)
    if not watching:
        logger.warning("Watchdog did not start within 90s — tests may time out waiting for file events")
    else:
        logger.info("Watchdog active — proceeding with incremental tests")

    yield

    for _p in (seed_path, modify_path, delete_path):
        try:
            if _p.exists():
                _p.unlink()
                logger.info("Removed session pre-placed file: %s", _p.name)
        except OSError as exc:
            logger.warning("Could not remove %s: %s", _p.name, exc)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.incremental
@pytest.mark.skipif(
    not HAS_INTEGRATION_WATCH_DIR,
    reason=(
        "Set INTEGRATION_WATCH_DIR to a dedicated directory (not sample-docs/). "
        "A session fixture will POST /api/ingest with enable_sync=true. See tests/integration/README.md."
    ),
)
class TestFilesystemIncremental:
    """
    Exercise add/modify/delete under INTEGRATION_WATCH_DIR (not sample-docs/ — tests mutate files).
    When INTEGRATION_WATCH_DIR is set, ``_register_incremental_watch_via_ingest`` runs first
    so the incremental engine monitors that path.
    """

    @pytest.fixture(autouse=True)
    def _resolve_dir(self, watch_dir: Path) -> None:
        env_dir = normalized_integration_watch_dir()
        self.dir: Path = Path(env_dir) if env_dir else watch_dir

    # ── INITIAL INGEST (seed / bulk registration pass) ────────────────────────

    @pytest.mark.slow
    def test_seed_is_indexed(self, client: APIClient):
        """Verify the seed file written before registration is searchable.

        The session fixture writes ``integration_seed_baseline.txt`` into the watch dir
        *before* ``POST /api/ingest enable_sync=true``, indexing it via the bulk ingest
        path (not the incremental add path).  Passing this test confirms initial ingest
        works end-to-end — a distinct code path from watchdog-triggered adds.
        """
        found = _wait_for_results(client, SEED_PHRASE, SEED_PHRASE, max_wait=SYNC_WAIT)
        assert found, (
            f"Seed phrase {SEED_PHRASE!r} not found after {SYNC_WAIT}s. "
            "Check that the bulk ingest completed and the vector/search store is reachable."
        )

    # ── ADD ───────────────────────────────────────────────────────────────────

    @pytest.mark.slow
    def test_add_file_is_indexed(self, client: APIClient):
        """Add a new file → verify search returns it; delete it → verify search no longer returns it."""
        unique_phrase = "zephyr_incremental_add_test_xq9"
        doc_path = self.dir / "incremental_add.txt"
        # Remove any leftover from a previous run before writing fresh content.
        if doc_path.exists():
            doc_path.unlink()
            _wait_for_file_gone(doc_path, timeout=20)
        _write_file(doc_path, f"This document contains the phrase: {unique_phrase}.\n"
                               "It was created by the incremental add test.\n"
                               "Alfresco is a content management system used for document storage.")
        try:
            # ADD: phrase must appear in search.
            found = _wait_for_results(client, unique_phrase, unique_phrase, max_wait=SYNC_WAIT)
            assert found, (
                f"ADD: {unique_phrase!r} not found after {SYNC_WAIT}s."
            )
        finally:
            _delete_file(doc_path)

    # ── MODIFY ────────────────────────────────────────────────────────────────

    @pytest.mark.slow
    @pytest.mark.skipif(
        not os.environ.get("INCREMENTAL_RUN_MODIFY"),
        reason=(
            "Modify test is opt-in: pass --inc-ops modify (or set INCREMENTAL_RUN_MODIFY=1) "
            "to enable. Skipped by default because MODIFY=DELETE+ADD can leave engine state "
            "that contaminates a subsequent delete test when both run in the same session."
        ),
    )
    def test_modify_file_updates_index(self, client: APIClient):
        """Overwrite an already-indexed file (watchdog MODIFY) → new content appears.

        ``incremental_modify.txt`` is written by the session fixture and bulk-ingested
        during registration.  This test overwrites it with new content — a pure MODIFY
        event — and verifies the updated content is searchable.
        """
        new_phrase = "new_content_phrase_xyz789"
        doc_path = self.dir / MODIFY_FILE_NAME

        # Confirm the pre-placed content is already indexed before modifying.
        pre_found = _wait_for_results(client, MODIFY_PHRASE, MODIFY_PHRASE, max_wait=SYNC_WAIT)
        assert pre_found, (
            f"Pre-placed content {MODIFY_PHRASE!r} not found — "
            "registration ingest may not have completed."
        )

        # MODIFY — overwrite with new content and wait for re-ingestion.
        time.sleep(2)  # ensure mtime differs so watchdog detects the change
        _write_file(doc_path, f"Updated content: {new_phrase}. "
                               "This document was modified by the incremental update test.")
        # New content must appear.
        found_new = _wait_for_results(client, new_phrase, new_phrase, max_wait=SYNC_WAIT)
        assert found_new, f"MODIFY: {new_phrase!r} not found after overwriting file."
        # Old content must be gone (old doc deleted as part of modify).
        old_gone = _wait_for_no_results(client, MODIFY_PHRASE, MODIFY_PHRASE, max_wait=SYNC_WAIT)
        assert old_gone, f"MODIFY: original phrase {MODIFY_PHRASE!r} still in search after modify — old doc not removed."
        # Note: file is left on disk — session teardown removes it.

    # ── DELETE ────────────────────────────────────────────────────────────────

    @pytest.mark.slow
    def test_delete_file_removes_from_index(self, client: APIClient):
        """Delete an already-indexed file (watchdog DELETE) → content disappears.

        ``incremental_delete.txt`` is written by the session fixture and bulk-ingested
        during registration.  This test deletes it — a pure DELETE event — and verifies
        the content is no longer searchable.
        """
        doc_path = self.dir / DELETE_FILE_NAME

        # Confirm the pre-placed content is already indexed before deleting.
        pre_found = _wait_for_results(client, DELETE_PHRASE, DELETE_PHRASE, max_wait=SYNC_WAIT)
        assert pre_found, (
            f"Pre-placed content {DELETE_PHRASE!r} not found — "
            "registration ingest may not have completed."
        )

        # DELETE — remove the file and wait for it to disappear from the index.
        _delete_file(doc_path)
        _wait_for_file_gone(doc_path, timeout=20)
        gone = _wait_for_no_results(client, DELETE_PHRASE, DELETE_PHRASE, max_wait=SYNC_WAIT)
        assert gone, (
            f"Content {DELETE_PHRASE!r} still present {SYNC_WAIT}s after file deletion."
        )

    # ── Multi-file ────────────────────────────────────────────────────────────

    def test_multiple_files_indexed_independently(self, client: APIClient):
        """Add two distinct files; each should be searchable independently."""
        phrase_a = "delta_file_alpha_phrase_01"
        phrase_b = "delta_file_beta_phrase_02"
        path_a = self.dir / "multi_a.txt"
        path_b = self.dir / "multi_b.txt"

        _write_file(path_a, f"Document A content: {phrase_a}.")
        _write_file(path_b, f"Document B content: {phrase_b}.")

        try:
            assert _wait_for_results(client, phrase_a, phrase_a, max_wait=SYNC_WAIT)
            assert _wait_for_results(client, phrase_b, phrase_b, max_wait=SYNC_WAIT)
        finally:
            _delete_file(path_a)
            _delete_file(path_b)


@pytest.mark.integration
class TestSyncEndpoints:
    """Lightweight sync API checks. If INTEGRATION_WATCH_DIR is set, session registration runs first."""

    def test_sync_status_endpoint(self, client: APIClient):
        """Verify /api/sync/status returns a sensible response."""
        status = client.sync_status()
        assert isinstance(status, dict), f"Expected dict, got: {type(status)}"
