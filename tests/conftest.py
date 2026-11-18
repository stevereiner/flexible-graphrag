"""
Pytest configuration for Flexible-GraphRAG tests
"""

import sys
import os
from pathlib import Path

# Add the flexible-graphrag directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "flexible-graphrag"))

import pytest

# Importing main.py runs load_dotenv(), which copies this machine's flexible-graphrag/.env into
# os.environ for the rest of the run: a later test of a default (SEARCH_DB=bm25) then sees that
# .env's value instead (SEARCH_DB=none), and REMOTE_FG_* adds real remote backends. Each test starts
# with those keys as they were before the run (unit tests don't depend on this machine's .env).
try:
    from dotenv import dotenv_values

    _DOTENV_KEYS = set(dotenv_values(Path(__file__).parent.parent / "flexible-graphrag" / ".env"))
except Exception:  # no python-dotenv, no .env
    _DOTENV_KEYS = set()
_ENV_BEFORE_RUN = {k: os.environ.get(k) for k in _DOTENV_KEYS}


@pytest.fixture(autouse=True)
def _dotenv_keys_as_before_run():
    for key, value in _ENV_BEFORE_RUN.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    yield

# Test configuration
def pytest_addoption(parser):
    parser.addoption(
        "--base-url",
        action="store",
        default=None,
        help="Base URL for API integration tests (overrides API_TEST_BASE_URL).",
    )


def pytest_configure(config):
    """Configure pytest for Flexible-GraphRAG tests"""
    config.addinivalue_line("markers", "bm25: marks tests as BM25 related")
    config.addinivalue_line("markers", "integration: marks integration tests (live backend required)")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "e2e: marks end-to-end tests (live backend + stores required)")
    config.addinivalue_line(
        "markers",
        "slow: long wall-clock tests (large ingest, waits, extra LLM rounds) — NOT 'no LLM'",
    )
    config.addinivalue_line("markers", "graph: marks tests that require a running property graph store")
    config.addinivalue_line("markers", "rdf: marks tests that require a running RDF store")
    config.addinivalue_line("markers", "vector: marks tests that require a running vector store")
    config.addinivalue_line("markers", "incremental: marks tests that exercise incremental update logic")
    config.addinivalue_line(
        "markers",
        "ai_qa: tests that call POST /api/query (chat Q&A LLM) — distinct from LLM used during KG ingest",
    )

def _nodeid_under_tests_integration_dir(nodeid: str) -> bool:
    """True only for tests in tests/integration/ (not test_*_integration.py elsewhere)."""
    n = nodeid.replace("\\", "/").lower()
    return "/tests/integration/" in n or n.startswith("tests/integration/")


def _integration_file_priority(file_path: str) -> int:
    """Order integration modules: ingest/search before incremental (default collect is alphabetical)."""
    pl = file_path.replace("\\", "/").lower()
    if "/test_ingest_search.py" in pl:
        return 0
    if "/test_incremental.py" in pl:
        return 1
    return 2


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their names; fix integration module order."""
    import pytest
    for item in items:
        if "bm25" in item.nodeid.lower():
            item.add_marker(pytest.mark.bm25)
        # Do NOT use `"integration" in nodeid` — it matches test_bm25_integration.py and
        # test_*_bm25_integration method names. Only the tests/integration/ package counts.
        if _nodeid_under_tests_integration_dir(item.nodeid):
            item.add_marker(pytest.mark.integration)
        if "unit" in item.nodeid.lower():
            item.add_marker(pytest.mark.unit)
        if "incremental" in item.nodeid.lower():
            item.add_marker(pytest.mark.incremental)
        if "ai_query" in item.nodeid.lower() or "test_ai_query" in item.nodeid.lower():
            item.add_marker(pytest.mark.ai_qa)

    # Alphabetical filename puts test_incremental.py before test_ingest_search.py, so incremental
    # tests ran first against an empty index. Reorder by file only (preserve order within each file).
    non_integration = [it for it in items if not _nodeid_under_tests_integration_dir(it.nodeid)]
    integration = [it for it in items if _nodeid_under_tests_integration_dir(it.nodeid)]
    if integration:
        from collections import defaultdict

        by_file: dict[str, list] = defaultdict(list)
        for it in integration:
            fn = it.nodeid.split("::", 1)[0]
            by_file[fn].append(it)
        sorted_files = sorted(by_file.keys(), key=_integration_file_priority)
        integration_sorted = [it for fp in sorted_files for it in by_file[fp]]
        items[:] = non_integration + integration_sorted