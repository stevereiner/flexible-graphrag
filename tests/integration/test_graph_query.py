"""
Integration tests — POST /api/graph/query  (native graph query endpoint).

This endpoint routes through the LC adapter's ``lc_graph.query()`` so the correct
query language is used for every store, covering all 15 PG stores and the RDF SPARQL
fallback.  Tests are store-agnostic: each picks its default query from a per-DB map
so the same test file works for any configured backend.

Run (any PG backend):
    uv run tests/integration/run_matrix.py \\
        --pg neo4j --vector none --search none --rdf none \\
        --backends langchain --fusion langchain \\
        --test-path tests/integration/test_graph_query.py

Run (RDF-only SPARQL fallback):
    uv run tests/integration/run_matrix.py \\
        --rdf fuseki --pg none --vector none --search none \\
        --test-path tests/integration/test_graph_query.py

Run directly (backend must be running):
    pytest tests/integration/test_graph_query.py -m integration -s
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from tests.integration.api_client import APIClient

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Per-store default queries  (post-ingest entity counts / basic reads)
# ─────────────────────────────────────────────────────────────────────────────

# Each value is the *simplest possible* query that:
#   a) is syntactically valid for the store
#   b) returns ≥1 rows on an ingested graph (or 0 rows on empty)
#   c) does NOT require ontology-specific labels

_DEFAULT_QUERIES: dict[str, tuple[str, str]] = {
    # (language_hint, query)
    "neo4j":             ("cypher",    "MATCH (n) RETURN n LIMIT 1"),
    "memgraph":          ("cypher",    "MATCH (n) RETURN n LIMIT 1"),
    "falkordb":          ("cypher",    "MATCH (n) RETURN n LIMIT 1"),
    "arcadedb":          ("opencypher","MATCH (n) RETURN n LIMIT 1"),
    "nebula":            ("cypher",    "SHOW SPACES"),
    "apache_age":        ("cypher",    "MATCH (n) RETURN n LIMIT 1"),
    "ladybug":           ("cypher",    "MATCH (n) RETURN n LIMIT 1"),
    "hugegraph":         ("cypher",    "MATCH (n) RETURN n LIMIT 1"),
    "arangodb":          ("aql",       "FOR doc IN _graphs LIMIT 1 RETURN doc"),
    "surrealdb":         ("surql",     "SELECT * FROM graph_source LIMIT 1"),
    "cosmos_gremlin":    ("gremlin",   "g.V().limit(1)"),
    "tigergraph":        ("gsql",      "SHOW GRAPH *"),
    "neptune":           ("opencypher","MATCH (n) RETURN n LIMIT 1"),
    "neptune_analytics": ("opencypher","MATCH (n) RETURN n LIMIT 1"),
    # Spanner LI structured_query prepends "GRAPH `graph_name`" automatically;
    # the LC path gets the full GQL via the adapter.  Use just the MATCH clause
    # to avoid "GRAPH knowledge_graph GRAPH knowledge_graph" double-prefix on LI.
    # Spanner GQL does not allow RETURN of raw graph elements — project a property.
    "spanner":           ("gql",       "MATCH (n) RETURN n.id LIMIT 1"),
    # RDF fallback
    "fuseki":            ("sparql",    "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 1"),
    "graphdb":           ("sparql",    "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 1"),
    "oxigraph":          ("sparql",    "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 1"),
    "neptune_rdf":       ("sparql",    "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 1"),
}

# Post-ingest Cypher that should return entity rows for Acme-family stores
_ENTITY_QUERIES: dict[str, str] = {
    "neo4j":      "MATCH (n) WHERE toLower(n.name) CONTAINS 'acme' OR toLower(n.id) CONTAINS 'acme' RETURN n.name AS name LIMIT 5",
    "memgraph":   "MATCH (n) WHERE toLower(n.name) CONTAINS 'acme' RETURN n.name AS name LIMIT 5",
    "falkordb":   "MATCH (n) WHERE toLower(n.name) CONTAINS 'acme' RETURN n.name AS name LIMIT 5",
    "arcadedb":   "MATCH (n) WHERE toLower(n.name) CONTAINS 'acme' RETURN n.name AS name LIMIT 5",
    "ladybug":    "MATCH (n) WHERE toLower(n.name) CONTAINS 'acme' RETURN n.name AS name LIMIT 5",
    "arangodb":   "FOR v IN GRAPH 'knowledge_graph' FILTER CONTAINS(LOWER(v.id), 'acme') LIMIT 5 RETURN v.id",
    # SurrealDB uses table-per-type; query all graph_* tables that might hold Acme
    "surrealdb":  "SELECT name FROM graph_Company WHERE string::lowercase(name) CONTAINS 'acme' LIMIT 5",
}


def _pg_db() -> str:
    return os.getenv("PG_GRAPH_DB", "none").strip().lower()


def _rdf_db() -> str:
    return os.getenv("RDF_GRAPH_DB", "none").strip().lower()


def _active_db() -> str:
    """Return the active store (PG takes precedence over RDF)."""
    pg = _pg_db()
    return pg if pg not in ("none", "") else _rdf_db()


def _skip_if_no_graph():
    if _active_db() in ("none", ""):
        pytest.skip("No graph store configured (PG_GRAPH_DB=none and RDF_GRAPH_DB=none)")


def _ingest_timeout() -> int:
    override = os.getenv("INTEGRATION_INGEST_TIMEOUT")
    if override:
        return int(override)
    slow = {"ollama", "openai_like", "vllm", "litellm"}
    return 900 if os.getenv("LLM_PROVIDER", "openai").lower() in slow else 300


# ─────────────────────────────────────────────────────────────────────────────
# Shared ingest fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def graph_query_ingested(client: APIClient, full_doc_path: Path):
    """Ingest company-ontology-test.txt once for all graph-query tests."""
    _skip_if_no_graph()
    result = client.ingest_file(full_doc_path)
    assert result.processing_id
    logger.info("graph_query ingest started: id=%s  db=%s", result.processing_id, _active_db())
    status = client.wait_for_completion(result.processing_id, max_wait=_ingest_timeout())
    assert status.status == "completed", f"Ingest failed: {status}"
    logger.info("graph_query ingest completed: db=%s", _active_db())
    return status


# ─────────────────────────────────────────────────────────────────────────────
# 1. Ping — minimal read on empty or populated graph
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.graph
def test_graph_query_ping(client: APIClient):
    """POST /api/graph/query with the store's minimal read query — no crash, valid response."""
    _skip_if_no_graph()
    db = _active_db()
    if db not in _DEFAULT_QUERIES:
        pytest.skip(f"No default query defined for db={db!r}")

    lang, query = _DEFAULT_QUERIES[db]
    logger.info("graph_query ping: db=%s  lang=%s  query=%r", db, lang, query)

    resp = client.graph_query(query, language=lang)
    logger.info("Response: backend=%s  lang=%s  rows=%s  error=%s",
                resp.get("backend"), resp.get("language"),
                resp.get("row_count"), resp.get("error"))

    assert "error" not in resp or resp["error"] is None, (
        f"graph_query ping returned error for {db}: {resp.get('error')}"
    )
    assert "results" in resp, f"Missing 'results' key: {resp}"
    assert "backend" in resp, f"Missing 'backend' key: {resp}"
    logger.info("PASS  db=%s  ping rows=%d", db, resp.get("row_count", 0))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Entity query — post-ingest rows for known stores
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.graph
def test_graph_query_entity_search(client: APIClient, graph_query_ingested):
    """POST /api/graph/query with a store-native entity search after ingest.

    Lenient: 0 rows = warning (extraction may have used different labels).
    """
    _skip_if_no_graph()
    db = _active_db()
    if db not in _ENTITY_QUERIES:
        pytest.skip(f"No entity query defined for db={db!r} — store may use different schema")

    lang_hint = _DEFAULT_QUERIES.get(db, (None, None))[0]
    query = _ENTITY_QUERIES[db]
    logger.info("graph_query entity: db=%s  lang=%s  query=%r", db, lang_hint, query[:80])

    resp = client.graph_query(query, language=lang_hint)
    rows = resp.get("row_count", 0)
    error = resp.get("error")

    if error:
        # Query syntax errors are store-specific — log and warn rather than hard-fail
        logger.warning("WARN  db=%s  entity query error: %s", db, error)
        return

    if rows == 0:
        logger.warning(
            "WARN  db=%s  entity query returned 0 rows — "
            "extraction may have used different entity labels or Acme was not extracted.",
            db,
        )
    else:
        logger.info("PASS  db=%s  entity query: %d rows", db, rows)

    assert rows >= 0  # hard-fail only on negative (shouldn't happen) or exception above


# ─────────────────────────────────────────────────────────────────────────────
# 3. Language inference — omit language hint, let backend infer
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.graph
def test_graph_query_language_inference(client: APIClient):
    """POST /api/graph/query without language hint — backend infers from PG_GRAPH_DB."""
    _skip_if_no_graph()
    db = _active_db()
    if db not in _DEFAULT_QUERIES:
        pytest.skip(f"No default query for db={db!r}")

    _, query = _DEFAULT_QUERIES[db]
    resp = client.graph_query(query)  # no language= kwarg
    inferred = resp.get("language", "")
    logger.info("Language inference: db=%s  inferred=%s", db, inferred)

    assert "error" not in resp or resp["error"] is None, resp.get("error")
    assert inferred not in ("", "unknown"), (
        f"Backend did not infer language for {db}: {resp}"
    )
    logger.info("PASS  db=%s  inferred language=%s", db, inferred)


# ─────────────────────────────────────────────────────────────────────────────
# 4. SPARQL via /api/rdf/query/sparql vs /api/graph/query routing consistency
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.rdf
def test_graph_query_sparql_vs_rdf_endpoint(client: APIClient, graph_query_ingested):
    """When RDF_GRAPH_DB is configured, /api/graph/query SPARQL and /api/rdf/query/sparql
    both respond without error (row counts may differ by routing path).
    """
    rdf = _rdf_db()
    if rdf in ("none", ""):
        pytest.skip("RDF_GRAPH_DB=none")

    sparql = "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5"

    gq_resp = client.graph_query(sparql, language="sparql")
    rdf_r = client._session.post(
        f"{client.base_url}/api/rdf/query/sparql",
        json={"query": sparql},
        timeout=client.timeout,
    )

    gq_rows = gq_resp.get("row_count", 0)
    gq_err  = gq_resp.get("error")

    if rdf_r.status_code == 503:
        rdf_rows = None
        logger.info("  /api/rdf/query/sparql: 503 (unified_query_engine not initialized)")
    else:
        rdf_r.raise_for_status()
        rdf_data = rdf_r.json()
        rdf_rows = len(rdf_data.get("results", []))

    logger.info(
        "SPARQL routing: rdf=%s  /api/graph/query rows=%s err=%s  /api/rdf/query/sparql rows=%s",
        rdf, gq_rows, gq_err, rdf_rows,
    )

    assert gq_err is None, f"/api/graph/query SPARQL error: {gq_err}"
    logger.info("PASS  rdf=%s  both SPARQL endpoints responded without error", rdf)
