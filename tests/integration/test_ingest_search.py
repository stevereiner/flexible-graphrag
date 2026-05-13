"""
Integration tests — ingest company-ontology-test.txt then run 1 hybrid search + 1 AI query.

  hybrid search : "who works for acme"    → expects known employee names
  ai query      : "how is acme organized" → expects department / org structure

Results are printed to the test log; text chunks are shortened to 2 lines / 120 chars.
Graph answers are shown in full (up to 300 chars).

Store-specific tests (run standalone via matrix --vector/--search/--pg/--rdf):
  test_vector_search_returns_results  — strict: must return results (VECTOR_DB != none)
  test_search_store_returns_results   — strict: must return results (SEARCH_DB != none)
  test_graph_search_no_crash          — lenient: no crash, log count (PG_GRAPH_DB != none,
                                         VECTOR_DB=none, SEARCH_DB=none)
  test_rdf_search_no_crash            — lenient: no crash, log count (RDF_GRAPH_DB != none,
                                         VECTOR_DB=none, SEARCH_DB=none)

Run directly:
    pytest tests/integration/test_ingest_search.py -m integration -s
Via runner:
    uv run tests/integration/run_profile.py --profile neo4j-langchain
Matrix (standalone vector):
    uv run tests/integration/run_matrix.py --vector all --search none --pg none --rdf none --backends llamaindex
Matrix (standalone search):
    uv run tests/integration/run_matrix.py --search all --vector none --pg none --rdf none --backends llamaindex
Matrix (standalone PG graph-only):
    uv run tests/integration/run_matrix.py --pg all --vector none --search none --rdf none --backends llamaindex
Matrix (standalone RDF):
    uv run tests/integration/run_matrix.py --rdf all --pg none --vector none --search none
"""
from __future__ import annotations

import logging
import os
import textwrap

import pytest

from tests.integration.api_client import APIClient, QueryResult, SearchResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Test queries
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_SEARCH_QUERY = "who works for acme"
COMPANY_SEARCH_TERMS = ["james", "linda", "marcus", "priya", "sarah"]

COMPANY_AI_QUERY     = "how is acme organized"
COMPANY_AI_TERMS     = ["engineering", "department", "sales", "management", "organized"]

# Sources that look like knowledge-graph answers (not raw text chunks)
_GRAPH_SOURCE_HINTS = ("property graph", "rdf graph", "knowledge graph",
                       "graph", "langchain_graph")


# ─────────────────────────────────────────────────────────────────────────────
# Logging helpers
# ─────────────────────────────────────────────────────────────────────────────

def _first_lines(text: str, n: int = 2, max_chars: int = 120) -> str:
    """Return the first *n* non-empty lines of *text*, capped at *max_chars*."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    snippet = " | ".join(lines[:n])
    return snippet[:max_chars] + ("…" if len(snippet) > max_chars else "")


def _is_graph_result(r: dict) -> bool:
    src = (r.get("source") or "").lower()
    return any(h in src for h in _GRAPH_SOURCE_HINTS)


def _log_search_results(result: SearchResult) -> None:
    """Log every result: source + score + content snippet.

    Text chunks   → first 2 lines, max 120 chars.
    Graph answers → up to 300 chars (they're already concise AI sentences).
    """
    logger.info("─── Hybrid search: %r  (%d results) ───", result.query, result.total)
    for i, r in enumerate(result.results, 1):
        src   = r.get("source") or r.get("metadata", {}).get("source") or "?"
        score = r.get("score", r.get("rank", "?"))
        text  = r.get("content") or r.get("text") or ""
        if _is_graph_result(r):
            # Graph QA answer — show more
            snippet = textwrap.shorten(text, width=300, placeholder=" …")
        else:
            # Text chunk — first 2 lines, 120 chars
            snippet = _first_lines(text, n=2, max_chars=120)
        logger.info("  [%d] %-45s  score=%-6s  %s", i, src, score, snippet)


def _log_query_answer(qr: QueryResult, question: str) -> None:
    logger.info("─── AI query: %r ───", question)
    logger.info("  Answer: %s", textwrap.shorten(qr.answer, width=400, placeholder=" …"))


# ─────────────────────────────────────────────────────────────────────────────
# Assertion helpers
# ─────────────────────────────────────────────────────────────────────────────

def _has_relevant_result(result: SearchResult, terms: list[str]) -> bool:
    for r in result.results:
        text = (r.get("content") or r.get("text") or "").lower()
        if any(t in text for t in terms):
            return True
    return False


def _answer_covers_topics(answer: str, keywords: list[str], *, min_matches: int = 1) -> bool:
    if not answer or not answer.strip():
        return False
    a = answer.lower()
    return sum(1 for k in keywords if k in a) >= min_matches


def _ingest_and_wait(client: APIClient, doc_path, *, max_wait: int, label: str) -> None:
    result = client.ingest_file(doc_path)
    assert result.processing_id, f"No processing_id from ingest ({label})"
    logger.info("Ingesting %s  ->  processing_id=%s", doc_path.name, result.processing_id)
    status = client.wait_for_completion(result.processing_id, max_wait=max_wait)
    assert status.status == "completed", f"Ingestion failed ({label}): {status}"
    logger.info("Ingestion complete: %s", label)


def _ingest_timeout() -> int:
    """Return the ingest timeout for the current LLM provider.

    Slow local providers (ollama, openai_like, vllm, litellm) can take
    10+ minutes for a multi-chunk document.  Allow overriding via
    INTEGRATION_INGEST_TIMEOUT env var.
    """
    override = os.getenv("INTEGRATION_INGEST_TIMEOUT")
    if override:
        return int(override)
    slow_providers = {"ollama", "openai_like", "vllm", "litellm"}
    if os.getenv("LLM_PROVIDER", "openai").lower() in slow_providers:
        return 900  # 15 min — local LLMs can be slow on large docs
    return 300  # 5 min — default for cloud providers


# ─────────────────────────────────────────────────────────────────────────────
# 1. Ingest
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_ingest_company_ontology_txt_completes(client: APIClient, full_doc_path):
    """Ingest sample-docs/company-ontology-test.txt (multi-chunk, graph-heavy)."""
    _ingest_and_wait(client, full_doc_path, max_wait=_ingest_timeout(), label="company-ontology-test.txt")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Hybrid search  (one call, log results, assert relevance + source)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_hybrid_search_who_works_for_acme(client: APIClient):
    """Hybrid search 'who works for acme': results must surface employee names and carry source."""
    result = client.search(COMPANY_SEARCH_QUERY, top_k=8)
    _log_search_results(result)

    assert result.total > 0, f"No results for: {COMPANY_SEARCH_QUERY!r}"
    assert _has_relevant_result(result, COMPANY_SEARCH_TERMS), (
        f"Expected one of {COMPANY_SEARCH_TERMS} in search results.\n"
        f"Snippets: {[r.get('content','')[:80] for r in result.results]}"
    )
    for r in result.results:
        src = r.get("source") or r.get("metadata", {}).get("source", "")
        assert src, f"Result missing 'source' field: {r}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. AI query  (one call, log answer, assert topics)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.ai_qa
def test_ai_query_how_is_acme_organized(client: APIClient):
    """POST /api/query 'how is acme organized': answer must mention org structure."""
    qr: QueryResult = client.query(COMPANY_AI_QUERY, top_k=10)
    _log_query_answer(qr, COMPANY_AI_QUERY)

    assert qr.status == "success", f"Unexpected status: {qr.raw}"
    assert qr.answer.strip(), "Empty answer from /api/query"
    assert _answer_covers_topics(qr.answer, COMPANY_AI_TERMS, min_matches=2), (
        f"Expected >= 2 of {COMPANY_AI_TERMS} in answer.\n"
        f"Got: {qr.answer[:600]!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Store-specific standalone search tests
#
# These are designed to run via run_matrix.py with a single active store and
# all others set to "none".  Use --test-path to target just this file.
#
# Strict (assert results > 0): vector store and search store are reliable
#   enough standalone to require results.
# Lenient (assert no crash, warn on 0): PG graph and RDF graph QA quality
#   varies by DB / LLM extraction — getting a result is a bonus, not crashing
#   is the bar.
# ─────────────────────────────────────────────────────────────────────────────

def _active(env_var: str) -> bool:
    """Return True when the env var names an active (non-none) store."""
    return os.getenv(env_var, "none").strip().lower() not in ("none", "", "false")



@pytest.mark.integration
@pytest.mark.vector
def test_vector_search_returns_results(client: APIClient):
    """Standalone vector store: search must return results (no search/graph to mask failures).

    Run via matrix:
        uv run tests/integration/run_matrix.py \\
            --vector all --search none --pg none --rdf none \\
            --backends llamaindex  [or langchain --fusion langchain] \\
            --test-path tests/integration/test_ingest_search.py
    """
    if not _active("VECTOR_DB"):
        pytest.skip("VECTOR_DB=none")
    vector_db = os.getenv("VECTOR_DB", "?")
    backend = os.getenv("VECTOR_BACKEND", "llamaindex")
    logger.info("vector store=%s backend=%s", vector_db, backend)

    result = client.search(COMPANY_SEARCH_QUERY, top_k=8)
    _log_search_results(result)

    assert result.total > 0, (
        f"Vector store '{vector_db}' ({backend}) returned 0 results for {COMPANY_SEARCH_QUERY!r}. "
        "Check that ingest completed and the vector store is reachable."
    )
    assert _has_relevant_result(result, COMPANY_SEARCH_TERMS), (
        f"Vector store '{vector_db}' results did not contain any of {COMPANY_SEARCH_TERMS}.\n"
        f"Snippets: {[r.get('content', '')[:80] for r in result.results]}"
    )
    logger.info("PASS  vector=%s  results=%d", vector_db, result.total)


@pytest.mark.integration
@pytest.mark.search_db
def test_search_store_returns_results(client: APIClient):
    """Standalone fulltext search store: search must return results.

    Run via matrix:
        uv run tests/integration/run_matrix.py \\
            --search all --vector none --pg none --rdf none \\
            --backends llamaindex  [or langchain --fusion langchain] \\
            --test-path tests/integration/test_ingest_search.py
    """
    if not _active("SEARCH_DB"):
        pytest.skip("SEARCH_DB=none")
    search_db = os.getenv("SEARCH_DB", "?")
    backend = os.getenv("SEARCH_BACKEND", "llamaindex")
    logger.info("search store=%s backend=%s", search_db, backend)

    result = client.search(COMPANY_SEARCH_QUERY, top_k=8)
    _log_search_results(result)

    assert result.total > 0, (
        f"Search store '{search_db}' ({backend}) returned 0 results for {COMPANY_SEARCH_QUERY!r}. "
        "Check that ingest completed and the search store is reachable."
    )
    assert _has_relevant_result(result, COMPANY_SEARCH_TERMS), (
        f"Search store '{search_db}' results did not contain any of {COMPANY_SEARCH_TERMS}.\n"
        f"Snippets: {[r.get('content', '')[:80] for r in result.results]}"
    )
    logger.info("PASS  search=%s  results=%d", search_db, result.total)


@pytest.mark.integration
@pytest.mark.graph
def test_graph_search_no_crash(client: APIClient):
    """Standalone PG graph (VECTOR_DB=none, SEARCH_DB=none): assert no crash, log result count.

    Graph-only QA quality varies by DB and LLM extraction — 0 results is a
    warning, not a failure.  A 500 error or exception IS a failure.

    Run via matrix:
        uv run tests/integration/run_matrix.py \\
            --pg all --vector none --search none --rdf none \\
            --backends llamaindex  [or langchain --fusion langchain] \\
            --test-path tests/integration/test_ingest_search.py
    """
    if not _active("PG_GRAPH_DB"):
        pytest.skip("PG_GRAPH_DB=none")
    pg_db = os.getenv("PG_GRAPH_DB", "?")
    backend = os.getenv("GRAPH_BACKEND", "llamaindex")
    logger.info("pg graph=%s backend=%s (vector=none search=none)", pg_db, backend)

    # No try/except — any HTTP error or exception fails the test (the "no crash" bar)
    result = client.search(COMPANY_SEARCH_QUERY, top_k=8)
    _log_search_results(result)

    if result.total == 0:
        logger.warning(
            "WARN  pg=%s (%s) returned 0 results — graph QA may need more extraction passes "
            "or a stronger LLM. Not a hard failure for graph-only mode.",
            pg_db, backend,
        )
    elif _has_relevant_result(result, COMPANY_SEARCH_TERMS):
        logger.info("PASS  pg=%s  results=%d  (relevant names found)", pg_db, result.total)
    else:
        logger.warning(
            "WARN  pg=%s  results=%d  but none of %s found — graph may need richer extraction.",
            pg_db, result.total, COMPANY_SEARCH_TERMS,
        )

    # Only hard-fail on 500 / exception (handled by client.search raising on non-2xx)
    # result.total == 0 is acceptable for graph-only mode
    assert result.total >= 0, "Unexpected negative result count"


@pytest.mark.integration
@pytest.mark.rdf
def test_rdf_search_no_crash(client: APIClient):
    """Standalone RDF store (VECTOR_DB=none, SEARCH_DB=none): assert no crash, log result count.

    Same lenient bar as test_graph_search_no_crash — SPARQL QA quality varies.

    Run via matrix:
        uv run tests/integration/run_matrix.py \\
            --rdf all --pg none --vector none --search none \\
            --test-path tests/integration/test_ingest_search.py
    """
    if not _active("RDF_GRAPH_DB"):
        pytest.skip("RDF_GRAPH_DB=none")
    rdf_db = os.getenv("RDF_GRAPH_DB", "?")
    logger.info("rdf store=%s (vector=none search=none pg=none)", rdf_db)

    result = client.search(COMPANY_SEARCH_QUERY, top_k=8)
    _log_search_results(result)

    if result.total == 0:
        logger.warning(
            "WARN  rdf=%s returned 0 results — SPARQL QA may need richer ontology or extraction. "
            "Not a hard failure for rdf-only mode.",
            rdf_db,
        )
    elif _has_relevant_result(result, COMPANY_SEARCH_TERMS):
        logger.info("PASS  rdf=%s  results=%d  (relevant names found)", rdf_db, result.total)
    else:
        logger.warning(
            "WARN  rdf=%s  results=%d  but none of %s found.",
            rdf_db, result.total, COMPANY_SEARCH_TERMS,
        )

    assert result.total >= 0, "Unexpected negative result count"
