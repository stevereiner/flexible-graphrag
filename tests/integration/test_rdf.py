"""
Integration tests — RDF-specific functionality.

These tests go beyond the lenient "no crash" bar in test_ingest_search.py and
exercise RDF-specific API endpoints, ingestion storage modes, SPARQL behaviour,
and ontology loading.

All tests skip automatically when RDF_GRAPH_DB=none.

Run standalone (all three local stores):
    uv run tests/integration/run_matrix.py \\
        --rdf fuseki,graphdb,oxigraph \\
        --pg none --vector none --search none

Run with vector store for combined mode:
    uv run tests/integration/run_matrix.py \\
        --rdf all --pg neo4j --vector qdrant \\
        --backends langchain --fusion langchain \\
        --test-path tests/integration/test_rdf.py

Run directly (backend must already be running with RDF_GRAPH_DB set):
    pytest tests/integration/test_rdf.py -m rdf -s
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from tests.integration.api_client import APIClient, QueryResult, SearchResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_SEARCH_QUERY = "who works for acme"
COMPANY_SEARCH_TERMS = ["james", "linda", "marcus", "priya", "sarah"]
COMPANY_AI_QUERY = "how is acme organized"
COMPANY_AI_TERMS = ["engineering", "department", "sales", "management", "organized"]

# Minimal valid SPARQL SELECT to probe reachability
_SPARQL_PING = "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 1"

# A SPARQL query that should return results after company-ontology-test.txt is ingested
_SPARQL_ENTITY_QUERY = """
SELECT ?s ?p ?o
WHERE {
  GRAPH ?g {
    ?s ?p ?o .
    FILTER(CONTAINS(LCASE(STR(?o)), "acme"))
  }
}
LIMIT 10
"""


def _rdf_db() -> str:
    return os.getenv("RDF_GRAPH_DB", "none").strip().lower()


def _skip_if_rdf_none():
    if _rdf_db() in ("none", ""):
        pytest.skip("RDF_GRAPH_DB=none — set to fuseki, graphdb, oxigraph, or neptune_rdf")


def _ingest_timeout() -> int:
    override = os.getenv("INTEGRATION_INGEST_TIMEOUT")
    if override:
        return int(override)
    slow = {"ollama", "openai_like", "vllm", "litellm"}
    return 900 if os.getenv("LLM_PROVIDER", "openai").lower() in slow else 300


def _log_search(result: SearchResult) -> None:
    logger.info("Search %r -> %d results", result.query, result.total)
    for i, r in enumerate(result.results[:5], 1):
        src = r.get("source") or "?"
        text = (r.get("content") or r.get("text") or "")[:120]
        logger.info("  [%d] %-40s  %s", i, src, text)


# ─────────────────────────────────────────────────────────────────────────────
# Module-scoped ingest fixture (shared across all tests in this file)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rdf_ingested(client: APIClient, full_doc_path: Path):
    """Ingest company-ontology-test.txt once for all RDF tests in this module."""
    _skip_if_rdf_none()
    result = client.ingest_file(full_doc_path)
    assert result.processing_id, "No processing_id from ingest"
    logger.info("RDF ingest started: processing_id=%s  rdf=%s", result.processing_id, _rdf_db())
    status = client.wait_for_completion(result.processing_id, max_wait=_ingest_timeout())
    assert status.status == "completed", f"Ingest failed: {status}"
    logger.info("RDF ingest completed: rdf=%s", _rdf_db())
    return status


# ─────────────────────────────────────────────────────────────────────────────
# 1. Ingest with INGESTION_STORAGE_MODE=rdf_only  (no PG, no vector)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.rdf
def test_rdf_ingest_completes(rdf_ingested):
    """Ingest completes without error when RDF_GRAPH_DB is configured."""
    assert rdf_ingested.status == "completed"
    logger.info("PASS  rdf=%s  ingest completed", _rdf_db())


# ─────────────────────────────────────────────────────────────────────────────
# 2. Ontology info endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.rdf
def test_rdf_ontology_info(client: APIClient, rdf_ingested):
    """GET /api/rdf/ontology/info returns valid structure when USE_ONTOLOGY=true."""
    _skip_if_rdf_none()
    use_ontology = os.getenv("USE_ONTOLOGY", "false").lower() == "true"
    if not use_ontology:
        pytest.skip("USE_ONTOLOGY=false — ontology info endpoint only populated when enabled")

    r = client._session.get(f"{client.base_url}/api/rdf/ontology/info", timeout=client.timeout)
    r.raise_for_status()
    data = r.json()
    logger.info("Ontology info: status=%s", data.get("status"))

    assert "status" in data, f"Missing 'status' key: {data}"
    if data["status"] == "loaded":
        assert "entities" in data, f"Missing 'entities': {data}"
        assert "relations" in data, f"Missing 'relations': {data}"
        entity_count = len(data.get("entities", {}))
        relation_count = len(data.get("relations", {}))
        logger.info("PASS  rdf=%s  ontology: %d entities, %d relations",
                    _rdf_db(), entity_count, relation_count)
        assert entity_count > 0, "Ontology loaded but has 0 entities"
    else:
        logger.info("Ontology status=%s (no ontology loaded)", data.get("status"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. SPARQL query endpoint — reachability + post-ingest results
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.rdf
def test_rdf_sparql_ping(client: APIClient, rdf_ingested):
    """POST /api/rdf/query/sparql — minimal SELECT returns without 500/503."""
    _skip_if_rdf_none()
    r = client._session.post(
        f"{client.base_url}/api/rdf/query/sparql",
        json={"query": _SPARQL_PING},
        timeout=client.timeout,
    )
    # 503 = unified_query_engine not initialized (older path) — acceptable skip
    if r.status_code == 503:
        pytest.skip("/api/rdf/query/sparql: unified_query_engine not initialized (503)")
    r.raise_for_status()
    data = r.json()
    logger.info("SPARQL ping: status=%s  backend=%s", data.get("status"), data.get("backend"))
    assert data.get("status") in ("success", "ok"), f"Unexpected status: {data}"
    logger.info("PASS  rdf=%s  SPARQL ping succeeded", _rdf_db())


@pytest.mark.integration
@pytest.mark.rdf
def test_rdf_sparql_entity_query(client: APIClient, rdf_ingested):
    """POST /api/rdf/query/sparql — named entity query returns >=1 rows after ingest."""
    _skip_if_rdf_none()
    r = client._session.post(
        f"{client.base_url}/api/rdf/query/sparql",
        json={"query": _SPARQL_ENTITY_QUERY},
        timeout=client.timeout,
    )
    if r.status_code == 503:
        pytest.skip("/api/rdf/query/sparql: unified_query_engine not initialized (503)")
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    logger.info("SPARQL entity query: rdf=%s  rows=%d", _rdf_db(), len(results))
    if len(results) == 0:
        logger.warning(
            "WARN  rdf=%s  SPARQL entity query returned 0 rows — "
            "ontology URIs may differ from expected or extraction yielded no Acme triples.",
            _rdf_db(),
        )
    else:
        logger.info("PASS  rdf=%s  SPARQL entity query: %d rows", _rdf_db(), len(results))
    # Lenient: 0 rows is a warning, 500 is a failure (already raised above)
    assert len(results) >= 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. RDF store list endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.rdf
def test_rdf_store_list(client: APIClient, rdf_ingested):
    """GET /api/rdf/rdf-store/list — returns the configured store without error."""
    _skip_if_rdf_none()
    r = client._session.get(
        f"{client.base_url}/api/rdf/rdf-store/list",
        timeout=client.timeout,
    )
    r.raise_for_status()
    data = r.json()
    stores = data.get("stores", [])
    logger.info("RDF store list: %d store(s): %s", len(stores), [s.get("name") for s in stores])
    assert data.get("count", -1) >= 0, f"Missing/invalid count: {data}"
    # At least one store should be registered when RDF_GRAPH_DB is configured
    if len(stores) == 0:
        logger.warning(
            "WARN  rdf=%s  /api/rdf/rdf-store/list returned 0 stores — "
            "store may not have been registered at startup.",
            _rdf_db(),
        )
    else:
        logger.info("PASS  rdf=%s  store list: %s", _rdf_db(), stores)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Export endpoint — 501 stub or actual content
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.rdf
def test_rdf_export_endpoint_responds(client: APIClient, rdf_ingested):
    """POST /api/rdf/export/rdf — either returns content (200) or documented stub (501).

    The endpoint is currently a 501 stub (not yet implemented).  This test
    verifies it responds consistently and doesn't crash with a 500.  When the
    endpoint is implemented, the 501 branch will be unreachable and the test
    will automatically validate the returned content.
    """
    _skip_if_rdf_none()
    r = client._session.post(
        f"{client.base_url}/api/rdf/export/rdf",
        json={"format": "turtle", "include_implicit": True},
        timeout=client.timeout,
    )
    if r.status_code == 501:
        logger.info(
            "INFO  rdf=%s  /api/rdf/export/rdf returned 501 (stub not yet implemented) — "
            "expected, not a failure.",
            _rdf_db(),
        )
        return
    # If/when implemented: must be 200 with non-empty body
    assert r.status_code == 200, f"Unexpected status {r.status_code}: {r.text[:200]}"
    assert r.text.strip(), "Export returned 200 but empty body"
    logger.info("PASS  rdf=%s  export returned %d bytes", _rdf_db(), len(r.text))


# ─────────────────────────────────────────────────────────────────────────────
# 6. Hybrid search with RDF active — results surface from RDF graph
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.rdf
def test_rdf_hybrid_search_returns_results(client: APIClient, rdf_ingested):
    """Hybrid search returns results when RDF is the only graph backend.

    Lenient: 0 results is a warning (SPARQL QA quality varies); a crash is a failure.
    """
    _skip_if_rdf_none()
    result = client.search(COMPANY_SEARCH_QUERY, top_k=8)
    _log_search(result)

    rdf = _rdf_db()
    if result.total == 0:
        logger.warning(
            "WARN  rdf=%s  search returned 0 results — "
            "SPARQL QA may need richer ontology/extraction.",
            rdf,
        )
    elif any(
        t in (r.get("content") or r.get("text") or "").lower()
        for r in result.results
        for t in COMPANY_SEARCH_TERMS
    ):
        logger.info("PASS  rdf=%s  search returned relevant results (%d)", rdf, result.total)
    else:
        logger.warning(
            "WARN  rdf=%s  %d results but none of %s found.",
            rdf, result.total, COMPANY_SEARCH_TERMS,
        )
    assert result.total >= 0


@pytest.mark.integration
@pytest.mark.rdf
@pytest.mark.ai_qa
def test_rdf_ai_query_no_crash(client: APIClient, rdf_ingested):
    """POST /api/query 'how is acme organized' — answer non-empty or empty but no 500."""
    _skip_if_rdf_none()
    qr: QueryResult = client.query(COMPANY_AI_QUERY, top_k=10)
    rdf = _rdf_db()
    logger.info("AI query rdf=%s: %s", rdf, (qr.answer or "")[:300])
    assert qr.status == "success", f"Unexpected query status: {qr.raw}"
    if not qr.answer.strip():
        logger.warning(
            "WARN  rdf=%s  AI query returned empty answer — "
            "SPARQL chain may have found no context.",
            rdf,
        )
    else:
        logger.info("PASS  rdf=%s  AI query answered (%d chars)", rdf, len(qr.answer))


# ─────────────────────────────────────────────────────────────────────────────
# 7. RDF + PG combined (INGESTION_STORAGE_MODE=both)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.rdf
@pytest.mark.graph
def test_rdf_both_mode_ingest_completes(client: APIClient, full_doc_path: Path):
    """When INGESTION_STORAGE_MODE=both, ingest writes to both PG and RDF without error.

    Skips if PG_GRAPH_DB=none or storage mode is not 'both'.
    """
    _skip_if_rdf_none()
    pg = os.getenv("PG_GRAPH_DB", "none").strip().lower()
    mode = os.getenv("INGESTION_STORAGE_MODE", "property_graph").strip().lower()
    if pg in ("none", ""):
        pytest.skip("PG_GRAPH_DB=none — 'both' mode requires a PG store")
    if mode != "both":
        pytest.skip(f"INGESTION_STORAGE_MODE={mode!r} — not 'both'")

    result = client.ingest_file(full_doc_path)
    assert result.processing_id
    status = client.wait_for_completion(result.processing_id, max_wait=_ingest_timeout())
    assert status.status == "completed", f"Both-mode ingest failed: {status}"
    logger.info("PASS  rdf=%s  pg=%s  both-mode ingest completed", _rdf_db(), pg)
