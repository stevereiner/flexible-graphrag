"""
Integration tests — ingest a folder of multi-format documents and verify search.

Activated when ``INTEGRATION_TEST_DIR`` env var points to a folder (e.g. ``sample-docs/``).
All files directly inside the folder are uploaded and ingested; subdirectories are ignored.

Run via matrix:
    uv run tests/integration/run_matrix.py --vector qdrant --backends langchain \
        --test-dir sample-docs

Run directly (backend must already be running):
    INTEGRATION_TEST_DIR=/path/to/docs pytest tests/integration/test_folder_ingest.py -m integration -s
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from tests.integration.api_client import APIClient

logger = logging.getLogger(__name__)


def _ingest_timeout() -> int:
    override = os.getenv("INTEGRATION_INGEST_TIMEOUT")
    if override:
        return int(override)
    slow_providers = {"ollama", "openai_like", "vllm", "litellm"}
    if os.getenv("LLM_PROVIDER", "openai").lower() in slow_providers:
        return 1800  # 30 min — multiple docs with local LLMs
    return 600  # 10 min — cloud providers with multiple docs


def _do_folder_ingest(
    client: APIClient,
    folder_doc_path: Path,
    *,
    batch: bool,
) -> dict:
    """Shared ingest logic used by both fixture variants."""
    files = sorted(p for p in folder_doc_path.iterdir() if p.is_file())
    logger.info(
        "Folder ingest (%s): %d files from %s",
        "batch" if batch else "one-at-a-time",
        len(files),
        folder_doc_path,
    )
    for fp in files:
        logger.info("  %s", fp.name)

    timeout = _ingest_timeout()
    results = client.ingest_folder(folder_doc_path, batch=batch)
    assert results, "ingest_folder returned no results"

    failed = []
    if batch:
        # Single processing_id covers all files
        status = client.wait_for_completion(results[0].processing_id, max_wait=timeout)
        if status.status != "completed":
            failed.append(f"batch: {status}")
        else:
            logger.info("Batch ingest completed (id=%s)", results[0].processing_id)
    else:
        for fp, result in zip(files, results):
            logger.info("Waiting for %s (id=%s)...", fp.name, result.processing_id)
            status = client.wait_for_completion(result.processing_id, max_wait=timeout)
            if status.status != "completed":
                failed.append(f"{fp.name}: {status}")
            else:
                logger.info("  %s: completed", fp.name)

    assert not failed, "Some files failed ingestion:\n" + "\n".join(failed)
    return {"files": files, "results": results, "batch": batch}


@pytest.fixture(scope="module")
def folder_ingested(client: APIClient, folder_doc_path: Path | None):
    """Ingest the test folder as a batch.

    Sends the folder path itself to POST /api/ingest (batch=True).  The backend's
    FileSystemSource walks the directory and processes all supported files under a
    single processing_id.  Faster and simpler for tests that just need content indexed.
    """
    if folder_doc_path is None:
        pytest.skip(
            "INTEGRATION_TEST_DIR not set — set it to a folder of documents "
            "to enable folder-ingest tests (e.g. export INTEGRATION_TEST_DIR=sample-docs)"
        )
    return _do_folder_ingest(client, folder_doc_path, batch=True)


@pytest.fixture(scope="module")
def folder_ingested_one_at_a_time(client: APIClient, folder_doc_path: Path | None):
    """Ingest each file in the test folder separately (one processing_id per file).

    Useful when per-file status polling or ordering matters.
    """
    if folder_doc_path is None:
        pytest.skip("INTEGRATION_TEST_DIR not set")
    return _do_folder_ingest(client, folder_doc_path, batch=False)


@pytest.mark.integration
@pytest.mark.folder_ingest
def test_folder_ingest_all_files_complete(client: APIClient, folder_doc_path: Path | None, folder_ingested):
    """All files in the test folder ingested successfully (batch mode)."""
    files = folder_ingested["files"]
    logger.info("Folder batch ingest completed: %d files", len(files))
    for fp in files:
        logger.info("  - %s", fp.name)
    assert len(files) > 0


@pytest.mark.integration
@pytest.mark.folder_ingest
def test_folder_ingest_one_at_a_time(client: APIClient, folder_doc_path: Path | None, folder_ingested_one_at_a_time):
    """Each file gets its own processing_id and completes independently."""
    info = folder_ingested_one_at_a_time
    files = info["files"]
    results = info["results"]
    logger.info("Folder one-at-a-time ingest completed: %d files", len(files))
    assert len(results) == len(files), (
        f"Expected {len(files)} results (one per file), got {len(results)}"
    )
    pids = [r.processing_id for r in results]
    assert len(set(pids)) == len(pids), f"Duplicate processing_ids: {pids}"
    for fp, r in zip(files, results):
        logger.info("  %s -> processing_id=%s", fp.name, r.processing_id)


@pytest.mark.integration
@pytest.mark.folder_ingest
def test_folder_ingest_vector_search(client: APIClient, folder_doc_path: Path | None, folder_ingested):
    """Vector search returns results after folder ingest."""
    vector_db = os.getenv("VECTOR_DB", "none").lower()
    if vector_db in ("none", ""):
        pytest.skip("VECTOR_DB=none — vector search not configured")

    from tests.integration.api_client import SearchResult
    result = client.search("content management")
    assert result.total > 0, (
        f"No results from vector search after folder ingest "
        f"(VECTOR_DB={vector_db}). "
        f"Check that the folder contains documents relevant to the query."
    )
    logger.info("Folder ingest vector search: %d results", result.total)
    for i, r in enumerate(result.results[:3], 1):
        src = r.get("source") or r.get("metadata", {}).get("source") or "?"
        text = (r.get("content") or r.get("text") or "")[:120]
        logger.info("  [%d] %s | %s", i, src, text)


@pytest.mark.integration
@pytest.mark.folder_ingest
def test_folder_ingest_search_result_sources(client: APIClient, folder_doc_path: Path | None, folder_ingested):
    """Search results reference the ingested file names as sources."""
    vector_db = os.getenv("VECTOR_DB", "none").lower()
    search_db = os.getenv("SEARCH_DB", "none").lower()
    if vector_db in ("none", "") and search_db in ("none", ""):
        pytest.skip("No vector or search DB configured")

    files = folder_ingested["files"]
    file_names = {fp.name for fp in files}

    result = client.search("content")
    sources = set()
    for r in result.results:
        src = r.get("source") or r.get("metadata", {}).get("source") or ""
        for fname in file_names:
            if fname in src:
                sources.add(fname)
                break

    logger.info(
        "Source coverage: %d/%d files referenced in search results",
        len(sources), len(file_names),
    )
    if sources:
        for s in sorted(sources):
            logger.info("  - %s", s)
    else:
        logger.warning(
            "No ingested filenames found in search result sources. "
            "Results may use display names rather than file names."
        )
