"""
Pytest fixtures for Flexible GraphRAG integration tests.

The tests assume a running backend process.  Point them at it via:
    API_TEST_BASE_URL=http://localhost:8000   (default)

To run against a specific profile, use run_profile.py which starts the
backend with the right .env and then invokes pytest.
"""
from __future__ import annotations

import os
import sys
import logging
import shutil
import tempfile
from pathlib import Path

# Load repo .env before importing test modules so INTEGRATION_WATCH_DIR / API_TEST_*
# match the backend when set in flexible-graphrag/.env (shell export not required).
def _load_dotenv_for_integration() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(root / ".env", override=False)
    load_dotenv(root / "flexible-graphrag" / ".env", override=False)


_load_dotenv_for_integration()

import pytest

from tests.integration.env_helpers import normalized_integration_watch_dir

# Quiet noisy third-party loggers so only test-module messages appear in live log
import logging as _logging
for _noisy in ("httpx", "httpcore", "urllib3", "hpack", "h2", "asyncio"):
    _logging.getLogger(_noisy).setLevel(_logging.WARNING)

# Add flexible-graphrag to path (for any direct imports tests may need)
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "flexible-graphrag"))

from tests.integration.api_client import APIClient

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
SAMPLE_DOCS = REPO_ROOT / "sample-docs"

# Short document used for fast smoke tests (< 10 KB, single chunk)
FAST_DOC = SAMPLE_DOCS / "cmispress.txt"

# Ontology-rich document (multi-chunk, tests graph extraction)
FULL_DOC = SAMPLE_DOCS / "company-ontology-test.txt"


# ── Session-scoped client ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def api_url(request: pytest.FixtureRequest) -> str:
    opt = request.config.getoption("--base-url", default=None)
    if opt:
        return str(opt).rstrip("/")
    return os.getenv("API_TEST_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def client(api_url: str) -> APIClient:
    c = APIClient(base_url=api_url)
    if not c.wait_until_healthy(max_wait=30):
        pytest.skip(f"Backend at {api_url} is not reachable — start it first.")
    return c


# ── Document fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fast_doc_path() -> Path:
    if not FAST_DOC.exists():
        pytest.skip(f"Sample doc not found: {FAST_DOC}")
    return FAST_DOC


@pytest.fixture(scope="session")
def full_doc_path() -> Path:
    if not FULL_DOC.exists():
        pytest.skip(f"Sample doc not found: {FULL_DOC}")
    return FULL_DOC


@pytest.fixture(scope="session")
def folder_doc_path() -> Path | None:
    """Optional folder of multi-format documents to ingest.

    Set ``INTEGRATION_TEST_DIR`` to an absolute path of a directory
    (e.g. ``sample-docs/``) to enable folder-ingest tests.
    If not set, tests using this fixture are skipped.
    """
    d = os.getenv("INTEGRATION_TEST_DIR", "").strip()
    if not d:
        return None
    p = Path(d)
    if not p.is_dir():
        pytest.skip(f"INTEGRATION_TEST_DIR={d!r} is not a directory")
    return p


# ── Temporary filesystem watch directory ──────────────────────────────────────

@pytest.fixture
def watch_dir(tmp_path: Path) -> Path:
    """
    A temporary directory intended to be the filesystem data-source root
    for incremental-update tests.  Cleaned up automatically after each test.
    """
    d = tmp_path / "incremental_watch"
    d.mkdir()
    return d


@pytest.fixture
def populated_watch_dir(watch_dir: Path) -> Path:
    """watch_dir pre-loaded with the fast sample document."""
    shutil.copy(FAST_DOC, watch_dir / FAST_DOC.name)
    return watch_dir


# ── Profile marker helpers ─────────────────────────────────────────────────────

def pytest_report_header(config: pytest.Config) -> list[str] | None:
    """Show the matrix combo label (if set) and any watch-dir skip reason."""
    lines: list[str] = []

    label = os.environ.get("MATRIX_LABEL")
    if label:
        bar = "─" * 56
        lines += [bar, f"  Matrix combo:  {label}", bar]

    if not normalized_integration_watch_dir():
        lines.append(
            "INTEGRATION_WATCH_DIR: (not set) — TestFilesystemIncremental tests are skipped; "
            "set a dedicated dir (not sample-docs/). When set, test_incremental.py POSTs /api/ingest "
            "enable_sync=true once per session (tests/integration/README.md)."
        )

    return lines or None


def _store_active(env_var: str) -> bool:
    return os.getenv(env_var, "none").strip().lower() not in ("none", "", "false")


# Map marker name → env var that must be active for that test to run.
# Tests decorated with these markers are deselected at collection time (not
# collected at all) when the corresponding store env var is "none".
_STORE_MARKER_GUARD: dict[str, str] = {
    "vector":    "VECTOR_DB",
    "search_db": "SEARCH_DB",
    "graph":     "PG_GRAPH_DB",
    "rdf":       "RDF_GRAPH_DB",
}


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Deselect store-specific tests when their store env var is 'none'.

    This prevents them from showing up as skips in the summary when running
    a focused matrix combo (e.g. --vector all --search none --pg none --rdf none).
    """
    deselected: list[pytest.Item] = []
    kept: list[pytest.Item] = []
    for item in items:
        drop = False
        for marker_name, env_var in _STORE_MARKER_GUARD.items():
            if item.get_closest_marker(marker_name) and not _store_active(env_var):
                drop = True
                break
        (deselected if drop else kept).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: marks integration tests (live backend required)")
    config.addinivalue_line("markers", "e2e: marks end-to-end tests (live backend + stores required)")
    config.addinivalue_line(
        "markers",
        "slow: long wall-clock tests — does not mean 'without LLM' (ingest may still use LLM for extraction)",
    )
    config.addinivalue_line("markers", "graph: marks tests that require a running property graph store")
    config.addinivalue_line("markers", "rdf: marks tests that require a running RDF store")
    config.addinivalue_line("markers", "vector: marks tests that require a running vector store")
    config.addinivalue_line("markers", "search_db: marks tests that require a running fulltext search store (ES/OpenSearch/BM25)")
    config.addinivalue_line("markers", "incremental: marks tests that exercise incremental update logic")
    config.addinivalue_line(
        "markers",
        "ai_qa: POST /api/query chat Q&A — extra LLM call on top of whatever ingest already used",
    )
    config.addinivalue_line(
        "markers",
        "lc_pipe: marks tests that exercise CHUNKER_BACKEND=langchain (full LC post-reader pipeline)",
    )
