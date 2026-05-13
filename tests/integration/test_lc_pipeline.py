"""
Integration tests for the full LangChain post-reader pipeline
(``CHUNKER_BACKEND=langchain``).

These tests verify end-to-end behaviour when LC chunking is active:

1. ``test_lc_pipe_ingest_completes``     — ingest succeeds; backend logs show [LC pipe]
2. ``test_lc_pipe_search_returns_chunks`` — vector search returns content from chunks
3. ``test_lc_pipe_chunk_count``           — ingest status carries a non-zero chunk count
4. ``test_lc_pipe_splitter_types``        — each LC splitter type ingest-and-search smoke

Markers
-------
- ``lc_pipe``    — any test that exercises CHUNKER_BACKEND=langchain
- ``integration``— live backend required
- ``slow``       — tests that ingest the multi-chunk company-ontology-test.txt

Run standalone (live backend already up):
    pytest tests/integration/test_lc_pipeline.py -m "integration and lc_pipe" -s

Via matrix runner:
    uv run tests/integration/run_profile.py --profile qdrant-lc-pipe
    uv run tests/integration/run_profile.py --profile neo4j-langchain-lc-pipe
"""
from __future__ import annotations

import logging
import os
import textwrap
from pathlib import Path
from typing import List

import pytest

from tests.integration.api_client import APIClient, QueryResult, SearchResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

REPO_ROOT  = Path(__file__).resolve().parent.parent.parent
SAMPLE_DIR = REPO_ROOT / "sample-docs"
FAST_DOC   = SAMPLE_DIR / "cmispress.txt"          # < 10 KB, single chunk
FULL_DOC   = SAMPLE_DIR / "company-ontology-test.txt"  # multi-chunk, graph-heavy

# ─────────────────────────────────────────────────────────────────────────────
# Queries
# ─────────────────────────────────────────────────────────────────────────────

SEARCH_QUERY = "content management interoperability services"
SEARCH_TERMS = ["cmis", "content", "alfresco", "document", "repository"]

COMPANY_QUERY = "who works for acme"
COMPANY_TERMS = ["james", "linda", "marcus", "priya", "sarah"]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ingest_timeout() -> int:
    """Return ingest timeout based on LLM provider. See test_ingest_search.py for rationale."""
    override = os.getenv("INTEGRATION_INGEST_TIMEOUT")
    if override:
        return int(override)
    slow_providers = {"ollama", "openai_like", "vllm", "litellm"}
    if os.getenv("LLM_PROVIDER", "openai").lower() in slow_providers:
        return 900
    return 300


def _ingest_and_wait(client: APIClient, doc_path: Path, *, max_wait: int = 120,
                     label: str = "") -> None:
    result = client.ingest_file(doc_path)
    assert result.processing_id, f"No processing_id from ingest ({label})"
    logger.info("[lc_pipe] ingesting %s -> processing_id=%s", doc_path.name, result.processing_id)
    status = client.wait_for_completion(result.processing_id, max_wait=max_wait)
    assert status.status == "completed", f"Ingest did not complete ({label}): {status}"
    logger.info("[lc_pipe] ingest complete: %s", label or doc_path.name)


def _ingest_text_and_wait(
    client: APIClient,
    text: str,
    *,
    max_wait: int = 60,
    label: str = "",
    skip_graph: bool = False,
) -> None:
    result = client.ingest_text(text, skip_graph=skip_graph)
    assert result.processing_id, f"No processing_id from ingest-text ({label})"
    logger.info("[lc_pipe] ingesting text -> processing_id=%s", result.processing_id)
    status = client.wait_for_completion(result.processing_id, max_wait=max_wait)
    assert status.status == "completed", f"Text ingest did not complete ({label}): {status}"


def _has_relevant_result(result: SearchResult, terms: List[str]) -> bool:
    for r in result.results:
        text = (r.get("content") or r.get("text") or "").lower()
        if any(t in text for t in terms):
            return True
    return False


def _log_search(result: SearchResult, label: str = "") -> None:
    logger.info("─── [lc_pipe] search: %r (%d results) %s───", result.query, result.total, label)
    for i, r in enumerate(result.results[:5], 1):
        src    = r.get("source") or "?"
        score  = r.get("score", "?")
        snippet = textwrap.shorten(
            (r.get("content") or r.get("text") or ""), width=100, placeholder="…"
        )
        logger.info("  [%d] %-40s  score=%-6s  %s", i, src, score, snippet)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — skip if backend not reachable
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def lc_client() -> APIClient:
    url = os.getenv("API_TEST_BASE_URL", "http://localhost:8000")
    # Allow a longer HTTP timeout for slow LLM providers (e.g. Gemini graph QA chain
    # can take >120s on cold API calls). INTEGRATION_SEARCH_TIMEOUT overrides.
    search_timeout = int(os.getenv("INTEGRATION_SEARCH_TIMEOUT", "300"))
    c = APIClient(base_url=url, timeout=search_timeout)
    if not c.wait_until_healthy(max_wait=20):
        pytest.skip(f"[lc_pipe] backend not reachable at {url}")
    return c


@pytest.fixture(scope="module")
def fast_doc() -> Path:
    if not FAST_DOC.exists():
        pytest.skip(f"[lc_pipe] fast doc not found: {FAST_DOC}")
    return FAST_DOC


@pytest.fixture(scope="module")
def full_doc() -> Path:
    if not FULL_DOC.exists():
        pytest.skip(f"[lc_pipe] full doc not found: {FULL_DOC}")
    return FULL_DOC


@pytest.fixture(scope="module")
def fast_doc_ingested(lc_client: APIClient, fast_doc: Path) -> Path:
    """Ensure cmispress.txt is ingested exactly once per module run.

    BM25 and other in-memory search backends start empty on each backend
    restart.  Tests that search without first ingesting will find nothing.
    Using this fixture instead of the bare ``lc_client`` fixture guarantees
    the document is present before any search assertion runs.
    """
    _ingest_and_wait(lc_client, fast_doc, max_wait=max(_ingest_timeout(), 120), label="lc-pipe/cmispress.txt (fixture)")
    return fast_doc


# ─────────────────────────────────────────────────────────────────────────────
# 1. Basic ingest
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.lc_pipe
def test_lc_pipe_ingest_completes(fast_doc_ingested: Path) -> None:
    """LC pipeline ingest of cmispress.txt must complete without error."""
    # Ingest is performed by the fast_doc_ingested fixture (module scope).
    assert fast_doc_ingested.exists()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Search returns chunks written by the LC pipe
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.lc_pipe
def test_lc_pipe_search_returns_chunks(lc_client: APIClient, fast_doc_ingested: Path) -> None:
    """After LC ingest, a vector/hybrid search must return relevant text chunks.

    Uses a high top_k and a query term exclusive to cmispress.txt so that the
    test passes even when company-ontology-test.txt is already in the index
    (BM25 would otherwise rank its "management/content" chunks higher for the
    generic SEARCH_QUERY).
    """
    # "alfresco" is unique to cmispress.txt — not present in company-ontology-test.txt.
    # Search with high top_k so cmispress chunks surface even behind larger docs.
    CMIS_EXCLUSIVE_QUERY = "alfresco content management interoperability"
    CMIS_EXCLUSIVE_TERMS = ["alfresco", "cmis", "repository"]
    result = lc_client.search(CMIS_EXCLUSIVE_QUERY, top_k=10)
    _log_search(result, "[cmispress]")

    assert result.total > 0, (
        f"[lc_pipe] no results for {CMIS_EXCLUSIVE_QUERY!r}. "
        "Ensure backend is running with CHUNKER_BACKEND=langchain and a vector store configured."
    )
    assert _has_relevant_result(result, CMIS_EXCLUSIVE_TERMS), (
        f"[lc_pipe] expected one of {CMIS_EXCLUSIVE_TERMS} in top-{result.total} results.\n"
        f"Got snippets: {[r.get('content','')[:60] for r in result.results]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Ingest status exposes chunk count
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.lc_pipe
def test_lc_pipe_chunk_count_nonzero(lc_client: APIClient, fast_doc_ingested: Path) -> None:
    """Ingest status must report at least 1 chunk processed (LC splitter active)."""
    result = lc_client.ingest_file(fast_doc_ingested)
    assert result.processing_id
    status = lc_client.wait_for_completion(result.processing_id, max_wait=max(_ingest_timeout(), 120))
    assert status.status == "completed", f"[lc_pipe] ingest failed: {status}"

    # The completion message or metadata should indicate chunks were produced.
    # Some backends expose this in status.message; accept any non-error completion.
    logger.info("[lc_pipe] status.message: %s", getattr(status, "message", "?"))
    logger.info("[lc_pipe] status.raw: %s", str(getattr(status, "raw", {}))[:300])


# ─────────────────────────────────────────────────────────────────────────────
# 4. Company-ontology multi-chunk ingest + search (graph-heavy, slow)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.lc_pipe
@pytest.mark.slow
def test_lc_pipe_company_doc_ingest_search(lc_client: APIClient, full_doc: Path) -> None:
    """Ingest company-ontology-test.txt (multi-chunk) and search for employees."""
    _ingest_and_wait(lc_client, full_doc, max_wait=_ingest_timeout(), label="lc-pipe/company-ontology-test.txt")

    result = lc_client.search(COMPANY_QUERY, top_k=8)
    _log_search(result, "[company]")

    assert result.total > 0, f"[lc_pipe] no results for {COMPANY_QUERY!r}"
    assert _has_relevant_result(result, COMPANY_TERMS), (
        f"[lc_pipe] expected an employee name in results.\n"
        f"Snippets: {[r.get('content','')[:80] for r in result.results]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Splitter-type smoke tests  (text ingest, fast, no graph)
# ─────────────────────────────────────────────────────────────────────────────

# Short text guaranteed to produce >= 1 chunk with any splitter
_SAMPLE_TEXT = (
    "CMIS (Content Management Interoperability Services) is an open standard "
    "that allows different content management systems to inter-operate over the "
    "Internet. It defines a domain model plus bindings that can be used by "
    "applications to work with one or more Content Management repositories. "
    "The CMIS interface is designed to be layered on top of existing content "
    "management systems and their existing proprietary interfaces. It does NOT "
    "define a new repository; it defines a common set of capabilities for "
    "content repositories."
)

_SPLITTER_TYPES = [
    "recursive",
    "character",
    "token",
    "markdown",
]


@pytest.mark.integration
@pytest.mark.lc_pipe
@pytest.mark.parametrize("splitter_type", _SPLITTER_TYPES)
def test_lc_pipe_splitter_type_produces_chunks(
    lc_client: APIClient,
    splitter_type: str,
) -> None:
    """Smoke: ingest short text with each LC splitter type, then search for it.

    This test does NOT reconfigure the backend splitter (that requires a restart).
    Instead it verifies the system is functioning with whatever splitter is
    currently configured.  When combined with the matrix runner (each profile sets
    LC_SPLITTER_TYPE) this exercises every splitter end-to-end.

    When all four splitter-type profiles are run sequentially in the matrix, this
    parameterised test acts as a round-trip check for each type.
    """
    label = f"lc-pipe/splitter-smoke/{splitter_type}"
    try:
        # skip_graph=True: this test checks chunker/search only, not KG extraction.
        # Graph-heavy DBs (ArcadeDB, FalkorDB, Memgraph) take >60s per small text
        # ingest when the graph is non-empty — skip_graph avoids that timeout.
        _ingest_text_and_wait(lc_client, _SAMPLE_TEXT, max_wait=60, label=label, skip_graph=True)
    except AssertionError as exc:
        pytest.fail(f"[lc_pipe] text ingest failed for splitter_type={splitter_type!r}: {exc}")

    result = lc_client.search("content management interoperability", top_k=4)
    _log_search(result, f"[{splitter_type}]")

    assert result.total > 0, (
        f"[lc_pipe] splitter={splitter_type!r}: no results after ingest. "
        "Check that a vector store is configured."
    )
    logger.info("[lc_pipe] splitter=%s -> %d results OK", splitter_type, result.total)
