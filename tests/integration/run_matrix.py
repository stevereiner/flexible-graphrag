"""
Matrix runner for flexible-graphrag integration tests.

Specify each dimension directly.  "all" expands to every known DB for that
dimension; "none" disables it; a comma-separated list selects a subset.
The runner executes one backend start + pytest run per combination.

Examples
--------
# neo4j PG  + every RDF backend  + qdrant vector  + elasticsearch search  (langchain / langchain-fusion)
uv run tests/integration/run_matrix.py --pg neo4j --rdf all --vector qdrant --search elasticsearch --backends langchain --fusion langchain

# All vector DBs, llamaindex backend (no graph, no search)
uv run tests/integration/run_matrix.py --vector all --backends llamaindex

# All vector DBs, both backends  (each DB × each backend = separate run)
uv run tests/integration/run_matrix.py --vector all --backends both

# PG-only: every langchain PG backend
uv run tests/integration/run_matrix.py --pg all --backends langchain

# PG + RDF combo: neo4j with every rdf store, langchain+lc-fusion
uv run tests/integration/run_matrix.py --pg neo4j --rdf all --backends langchain --fusion langchain

# Compare fusion strategies on the same stack
uv run tests/integration/run_matrix.py --pg neo4j --backends langchain --fusion both

# Show what would run without starting any backend
uv run tests/integration/run_matrix.py --pg neo4j --rdf fuseki --vector qdrant --dry-run

# Test apache_age with langchain backend
uv run tests/integration/run_matrix.py --pg apache_age --vector qdrant --backends langchain

# Test a specific LLM provider (API keys / URLs still from .env)
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --llm ollama
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --llm openai,gemini,anthropic

# Test a specific embedding provider
uv run tests/integration/run_matrix.py --vector qdrant --embedding ollama
uv run tests/integration/run_matrix.py --vector qdrant --embedding openai,ollama,google

# Test all LLM providers against neo4j+qdrant
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --llm all

# Test LLM × embedding combinations
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --llm openai,ollama --embedding openai,ollama

# vLLM (docker server mode) and openai_like
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --llm vllm
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --llm openai_like

# Pure LI run — lc_pipe tests auto-excluded; CHUNKER_BACKEND=llamaindex set automatically
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant

# Full LC run — CHUNKER_BACKEND=langchain set automatically; test_lc_pipeline.py auto-targeted
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --backends langchain

# Mixed: LC graph backend but LI chunker (uses --chunker to override the auto-derived value)
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --backends langchain --chunker llamaindex

# Mixed: LI graph backend but LC chunker (runs test_lc_pipeline.py)
uv run tests/integration/run_matrix.py --vector qdrant --chunker langchain

# Compare LI vs LC chunker on the same stack (two separate passes)
uv run tests/integration/run_matrix.py --vector qdrant --chunker both

# List available DB names per dimension
uv run tests/integration/run_matrix.py --list-dbs

# Clean stale data before each run (recommended when switching between --backends)
uv run tests/integration/run_matrix.py --vector all --backends llamaindex --clean
"""
from __future__ import annotations

import argparse
import itertools
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.integration.run_profile import (
    run_pytest,
    start_backend,
    stop_backend,
    _backend_log_path,
    API_URL,
)
from tests.integration.api_client import APIClient
from tests.integration.env_profiles import INTEGRATION_DEFAULT_OVERRIDES

BASE_ENV = REPO_ROOT / "flexible-graphrag" / ".env"

# -----------------------------------------------------------------------------
# All known DBs per dimension  (used when --dim all)
# -----------------------------------------------------------------------------

ALL_PG: dict[str, list[str]] = {
    "llamaindex": [
        "neo4j", "arcadedb", "falkordb", "memgraph", "nebula", "ladybug",
        "neptune",             # AWS Neptune Database  (cloud)
        "neptune_analytics",   # AWS Neptune Analytics (cloud)
        "spanner",             # Google Cloud Spanner (cloud)
    ],
    "langchain": [
        "neo4j", "arcadedb", "falkordb", "memgraph", "nebula", "tigergraph",
        "arangodb", "apache_age", "hugegraph", "surrealdb",
        "cosmos_gremlin",      # testable with local gremlin server
        "ladybug",             # Embedded — LI adapter reused via LangChain backend
        # "spanner",           # langchain-google-spanner requires langchain-core<1.0 — uncomment when a compatible release is available
        "neptune",             # AWS Neptune PG (OpenCypher) - cloud
        "neptune_analytics",   # AWS Neptune Analytics (cloud)
    ],
}
ALL_VECTOR: dict[str, list[str]] = {
    "llamaindex": ["qdrant", "elasticsearch", "opensearch", "postgres",
                   "chroma", "neo4j", "milvus", "weaviate", "lancedb", "pinecone"],
    "langchain":  ["qdrant", "elasticsearch", "opensearch", "postgres",
                   "chroma", "neo4j", "milvus", "weaviate", "lancedb", "pinecone"],
}
ALL_SEARCH: dict[str, list[str]] = {
    "llamaindex": ["bm25", "elasticsearch", "opensearch"],
    "langchain":  ["bm25", "elasticsearch", "opensearch"],
}
ALL_RDF: list[str] = [
    "fuseki", "graphdb", "oxigraph",
    "neptune_rdf",   # AWS Neptune RDF/SPARQL (cloud) — uncomment when cluster is available
]

# DBs that must use the langchain vector backend regardless of --backends
_LANGCHAIN_ONLY_VECTOR = {"milvus", "weaviate", "lancedb", "pinecone"}

# -----------------------------------------------------------------------------
# LLM provider overrides  (--llm)
# Only the selector + model are overridden — API keys, base URLs, etc. come from .env
# -----------------------------------------------------------------------------

_LLM_OVERRIDES: dict[str, dict] = {
    "openai":       {"LLM_PROVIDER": "openai",       "OPENAI_MODEL": "gpt-4.1-mini"},
    "ollama":       {"LLM_PROVIDER": "ollama",        "OLLAMA_MODEL": "gpt-oss:20b"},
    "gemini":       {"LLM_PROVIDER": "gemini",        "GEMINI_MODEL": "gemini-3-flash-preview"},
    "anthropic":    {"LLM_PROVIDER": "anthropic",     "ANTHROPIC_MODEL": "claude-sonnet-4-5-20250929"},
    "vertex_ai":    {"LLM_PROVIDER": "vertex_ai",     "VERTEX_AI_MODEL": "gemini-2.5-flash"},
    "bedrock":      {"LLM_PROVIDER": "bedrock",       "BEDROCK_MODEL": "us.anthropic.claude-sonnet-4-5-20250929-v1:0"},
    # NOTE: Groq free tier has very low TPM limits (6-8k) which are exceeded by the
    # query synthesis prompt (4 chunks × 2048 chars ≈ 10k tokens). Requires paid/Dev tier.
    # Dev tier upgrade: https://console.groq.com/settings/billing
    "groq":         {"LLM_PROVIDER": "groq",          "GROQ_MODEL": "llama-3.3-70b-versatile"},
    "fireworks":    {"LLM_PROVIDER": "fireworks",     "FIREWORKS_MODEL": "accounts/fireworks/models/gpt-oss-120b"},
    "openai_like":  {"LLM_PROVIDER": "openai_like"},
    "vllm":         {"LLM_PROVIDER": "vllm",          "VLLM_MODE": "server"},
    "litellm":      {"LLM_PROVIDER": "litellm", "LITELLM_MODEL": "gpt-4o-mini"},
    "openrouter":   {"LLM_PROVIDER": "openrouter"},
    "azure_openai": {"LLM_PROVIDER": "azure_openai",  "AZURE_OPENAI_MODEL": "gpt-4.1-mini"},
}

# -----------------------------------------------------------------------------
# Embedding provider overrides  (--embedding)
# Only EMBEDDING_KIND + the matching model var are overridden — dims, keys, URLs from .env
# -----------------------------------------------------------------------------

_EMBEDDING_OVERRIDES: dict[str, dict] = {
    "openai":       {"EMBEDDING_KIND": "openai",       "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small"},
    "ollama":       {"EMBEDDING_KIND": "ollama",       "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text"},
    "google":       {"EMBEDDING_KIND": "google",       "GOOGLE_EMBEDDING_MODEL": "gemini-embedding-2-preview"},
    "vertex":       {"EMBEDDING_KIND": "vertex",       "VERTEX_EMBEDDING_MODEL": "gemini-embedding-2-preview"},
    "azure":        {"EMBEDDING_KIND": "azure",        "AZURE_EMBEDDING_MODEL": "text-embedding-3-small"},
    "bedrock":      {"EMBEDDING_KIND": "bedrock",      "BEDROCK_EMBEDDING_MODEL": "amazon.titan-embed-text-v2:0"},
    "fireworks":    {"EMBEDDING_KIND": "fireworks",    "FIREWORKS_EMBEDDING_MODEL": "nomic-ai/nomic-embed-text-v1.5"},
    "openai_like":  {"EMBEDDING_KIND": "openai_like",  "OPENAI_LIKE_EMBEDDING_MODEL": "nomic-embed-text",
                     "OPENAI_LIKE_EMBEDDING_API_BASE": "http://localhost:11434/v1"},
    "litellm":      {"EMBEDDING_KIND": "litellm"},
}

# -----------------------------------------------------------------------------
# Per-DB override snippets
# -----------------------------------------------------------------------------

_PG_OVERRIDES: dict[str, dict] = {
    # Connection details come from .env — overrides set only the DB selector key.
    # This avoids _write_env commenting out the correct .env values.
    "neo4j":          {"PG_GRAPH_DB": "neo4j"},
    "falkordb":       {"PG_GRAPH_DB": "falkordb"},
    "memgraph":       {"PG_GRAPH_DB": "memgraph"},
    # LangChain backend needs bolt_port; LI backend uses HTTP (port 2480) and ignores bolt_port.
    # .env active config is the LI version (no bolt_port) — override here so LC tests work.
    "arcadedb":       {"PG_GRAPH_DB": "arcadedb",
                       "ARCADEDB_GRAPH_DB_CONFIG": '{"host":"localhost","port":2480,"bolt_port":7689,"username":"root","password":"playwithdata","database":"flexible_graphrag"}'},
    "arangodb":       {"PG_GRAPH_DB": "arangodb"},
    "apache_age":     {"PG_GRAPH_DB": "apache_age"},
    "hugegraph":      {"PG_GRAPH_DB": "hugegraph"},
    "surrealdb":      {"PG_GRAPH_DB": "surrealdb"},
    "cosmos_gremlin": {"PG_GRAPH_DB": "cosmos_gremlin"},
    "ladybug":        {"PG_GRAPH_DB": "ladybug",
                       "LADYBUG_DB_DIR": "./ladybug_matrix_test",
                       "LADYBUG_DB_FILE": "database.lbug",
                       "LADYBUG_GRAPH_DB_CONFIG": '{"db_dir": "./ladybug_matrix_test", "db_file": "database.lbug"}'},
    "nebula":         {"PG_GRAPH_DB": "nebula"},
    "tigergraph":     {"PG_GRAPH_DB": "tigergraph"},
    # Uses cloud Spanner from .env (SPANNER_GRAPH_DB_CONFIG). 
    "spanner":        {"PG_GRAPH_DB": "spanner"},
    # cloud:
    "neptune":            {"PG_GRAPH_DB": "neptune"},
    "neptune_analytics":  {"PG_GRAPH_DB": "neptune_analytics"},
}

_RDF_OVERRIDES: dict[str, dict] = {
    "fuseki":      {"RDF_GRAPH_DB": "fuseki",
                    "FUSEKI_URL": "http://localhost:3030", "FUSEKI_DATASET": "flexible-graphrag",
                    "FUSEKI_USERNAME": "admin", "FUSEKI_PASSWORD": "admin"},
    "graphdb":     {"RDF_GRAPH_DB": "graphdb",
                    "GRAPHDB_URL": "http://localhost:7200", "GRAPHDB_REPOSITORY": "flexible-graphrag",
                    "GRAPHDB_USERNAME": "admin", "GRAPHDB_PASSWORD": "root"},
    "oxigraph":    {"RDF_GRAPH_DB": "oxigraph",
                    "OXIGRAPH_URL": "http://localhost:7878"},
    # Connection details (host, port, region, credentials) come from .env — only the
    # selector and auth-mode flags are overridden here.
    "neptune_rdf": {"RDF_GRAPH_DB": "neptune_rdf",
                    "NEPTUNE_RDF_USE_IAM_AUTH": "true",
                    "NEPTUNE_RDF_USE_HTTPS": "true"},
}

_VECTOR_OVERRIDES: dict[str, dict] = {
    "qdrant":        {"VECTOR_DB": "qdrant",
                      "QDRANT_VECTOR_DB_CONFIG": '{"host":"localhost","port":6333,"collection_name":"hybrid_search_vector","https":false}'},
    "elasticsearch": {"VECTOR_DB": "elasticsearch",
                      "ELASTICSEARCH_VECTOR_DB_CONFIG": '{"url":"http://localhost:9200","index_name":"flexible_graphrag_vectors"}'},
    "opensearch":    {"VECTOR_DB": "opensearch",
                      "OPENSEARCH_VECTOR_DB_CONFIG": '{"url":"http://localhost:9201","index_name":"flexible_graphrag_vectors"}'},
    "postgres":      {"VECTOR_DB": "postgres",
                      "POSTGRES_VECTOR_DB_CONFIG": '{"host":"localhost","port":5433,"username":"postgres","password":"password","database":"flexible_graphrag"}'},
    "chroma":        {"VECTOR_DB": "chroma",
                      "CHROMA_VECTOR_DB_CONFIG": '{"host":"localhost","port":8001,"collection_name":"hybrid_search_vector"}'},
    "milvus":        {"VECTOR_DB": "milvus",
                      "MILVUS_VECTOR_DB_CONFIG": '{"host":"localhost","port":19530,"collection_name":"hybrid_search_vector"}'},
    "weaviate":      {"VECTOR_DB": "weaviate",
                      "WEAVIATE_VECTOR_DB_CONFIG": '{"url":"http://localhost:8081","grpc_port":50051,"index_name":"HybridSearch","text_key":"content"}'},
    "lancedb":       {"VECTOR_DB": "lancedb",
                      "LANCEDB_VECTOR_DB_CONFIG": '{"uri":"./lancedb_matrix_test","table_name":"hybrid_search_vector"}'},
    "pinecone":      {"VECTOR_DB": "pinecone"},
    "neo4j":         {"VECTOR_DB": "neo4j",
                      "NEO4J_VECTOR_DB_CONFIG": '{"url":"bolt://localhost:7687","username":"neo4j","password":"password"}'},
}

_SEARCH_OVERRIDES: dict[str, dict] = {
    "bm25":          {"SEARCH_DB": "bm25", "BM25_PERSIST_DIR": "./test_bm25_matrix"},
    "elasticsearch": {"SEARCH_DB": "elasticsearch",
                      "ELASTICSEARCH_SEARCH_DB_CONFIG": '{"url":"http://localhost:9200","index_name":"flexible_graphrag_search"}'},
    "opensearch":    {"SEARCH_DB": "opensearch",
                      "OPENSEARCH_SEARCH_DB_CONFIG": '{"url":"http://localhost:9201","index_name":"flexible_graphrag_search"}'},
}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _resolve(val: str | None, all_list: list[str]) -> list[str]:
    """Expand "all" / "none" / comma list / single value into a Python list.

    Returns [] for "none" or None (dimension disabled).
    Returns [sentinel_NONE] never — disabled dims use empty list.
    """
    if not val or val.lower() == "none":
        return []
    if val.lower() == "all":
        return list(all_list)
    return [v.strip() for v in val.split(",") if v.strip()]


def _resolve_backends(val: str) -> list[str]:
    v = val.lower()
    if v == "both":
        return ["llamaindex", "langchain"]
    return [v]


def _resolve_fusions(val: str) -> list[str]:
    v = val.lower()
    if v == "both":
        return ["llamaindex", "langchain"]
    return [v]


def _build_overrides(
    pg: str | None,
    rdf: str | None,
    vector: str | None,
    search: str | None,
    backend: str,
    fusion: str,
    llm: str | None = None,
    embedding: str | None = None,
    chunker: str | None = None,
    ontology: str | None = None,
    doc_parser: str | None = None,
) -> dict[str, str]:
    """Assemble the env-var overrides for one combination."""
    overrides: dict[str, str] = {}

    has_pg  = bool(pg)
    has_rdf = bool(rdf)

    # -- PG graph --------------------------------------------------------------
    if has_pg:
        overrides.update(_PG_OVERRIDES[pg])
        overrides["GRAPH_BACKEND"] = backend
        if backend == "langchain":
            overrides["USE_LANGCHAIN_PG"] = "true"
        # ontology: explicit value overrides the default "true"
        overrides["USE_ONTOLOGY"] = ontology if ontology else "true"
    else:
        overrides["PG_GRAPH_DB"] = "none"

    # -- RDF graph -------------------------------------------------------------
    if has_rdf:
        overrides.update(_RDF_OVERRIDES[rdf])
    else:
        overrides["RDF_GRAPH_DB"] = "none"

    # -- Vector store ----------------------------------------------------------
    if vector:
        overrides.update(_VECTOR_OVERRIDES[vector])
        overrides["VECTOR_BACKEND"] = backend
    else:
        overrides["VECTOR_DB"] = "none"

    # -- Search store ----------------------------------------------------------
    if search:
        overrides.update(_SEARCH_OVERRIDES[search])
        overrides["SEARCH_BACKEND"] = backend
    else:
        overrides["SEARCH_DB"] = "none"

    # -- Ingestion mode --------------------------------------------------------
    if has_pg and has_rdf:
        overrides["INGESTION_STORAGE_MODE"] = "both"
    elif has_pg or has_rdf:
        overrides["INGESTION_STORAGE_MODE"] = "graph_and_vector"
    # else: no graph — leave base .env value

    # -- Knowledge graph extraction --------------------------------------------
    overrides["ENABLE_KNOWLEDGE_GRAPH"] = "true" if (has_pg or has_rdf) else "false"

    # -- Retrieval fusion ------------------------------------------------------
    overrides["RETRIEVAL_FUSION"] = fusion

    # -- Chunker backend -------------------------------------------------------
    if chunker:
        overrides["CHUNKER_BACKEND"] = chunker

    # -- LLM provider ----------------------------------------------------------
    if llm and llm in _LLM_OVERRIDES:
        overrides.update(_LLM_OVERRIDES[llm])

    # -- Embedding provider ----------------------------------------------------
    if embedding and embedding in _EMBEDDING_OVERRIDES:
        overrides.update(_EMBEDDING_OVERRIDES[embedding])

    # -- Document parser -------------------------------------------------------
    if doc_parser and doc_parser != "default":
        overrides["DOCUMENT_PARSER"] = doc_parser

    return overrides


def _label(pg, rdf, vector, search, backend, fusion, llm=None, embedding=None, chunker=None,
           ontology=None, doc_parser=None) -> str:
    dbs = []
    if pg:     dbs.append(f"pg:{pg}")
    if rdf:    dbs.append(f"rdf:{rdf}")
    if vector: dbs.append(f"vec:{vector}")
    if search: dbs.append(f"search:{search}")
    db_str = "  ".join(dbs) if dbs else "no-graph"
    suffix = f"  |  {backend}  |  fusion:{fusion}"
    if chunker:    suffix += f"  |  chunker:{chunker}"
    if llm:        suffix += f"  |  llm:{llm}"
    if embedding:  suffix += f"  |  emb:{embedding}"
    if ontology:   suffix += f"  |  ontology:{ontology}"
    if doc_parser: suffix += f"  |  parser:{doc_parser}"
    return f"{db_str}{suffix}"


def _write_env(overrides: dict[str, str], base_env: Path) -> Path:
    import tempfile
    lines: list[str] = []
    merged = {**INTEGRATION_DEFAULT_OVERRIDES, **overrides}
    if base_env.exists():
        for line in base_env.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            lines.append(f"# (matrix) {line}" if key in merged else line)
    lines += ["", "# -- matrix overrides --",
              *[f"{k}={v}" for k, v in merged.items()]]
    fd, tmp = tempfile.mkstemp(prefix="fgrag-matrix-", suffix=".env")
    os.close(fd)
    Path(tmp).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Path(tmp)


def _run_cleanup(overrides: dict, base_env: Path) -> None:
    """Run scripts/cleanup.py with the given overrides as environment variables.

    Only cleans the stores that are active in this combination (VECTOR_DB,
    PG_GRAPH_DB, SEARCH_DB, RDF_GRAPH_DB).  Errors are printed but non-fatal.
    """
    cleanup_script = REPO_ROOT / "scripts" / "cleanup.py"
    if not cleanup_script.exists():
        return

    env = {**os.environ}
    env.update(overrides)
    # base_env is not needed — we pass everything as env vars which take
    # precedence over load_dotenv() (which never overrides existing env vars)

    print("[matrix] Running cleanup.py ...")
    try:
        result = subprocess.run(
            [sys.executable, str(cleanup_script), "--matrix-clean"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT / "flexible-graphrag"),  # match backend CWD so relative paths (./lancedb_matrix_test etc.) resolve correctly
        )
        if result.returncode != 0:
            print(f"[matrix] cleanup.py exited {result.returncode}")
        # Print a condensed summary (only ERROR/WARNING lines)
        for line in result.stdout.splitlines():
            if any(kw in line for kw in ("ERROR", "WARN", "Cleaned", "Deleted", "Dropped", "Wipe")):
                print(f"  {line}")
    except subprocess.TimeoutExpired:
        print("[matrix] cleanup.py timed out (60s)")
    except Exception as exc:
        print(f"[matrix] cleanup.py exception: {exc}")


# -----------------------------------------------------------------------------
# Run one combination
# -----------------------------------------------------------------------------

def _run_one(label: str, overrides: dict, base_env: Path, *,
             job_num: int, total: int,
             test_path: str, timeout: int, dry_run: bool,
             clean: bool = False,
             pytest_k: str = "",
             pytest_env: dict[str, str] | None = None,
             exitfirst: bool = False) -> dict:
    width = 64
    header = f"  [{job_num}/{total}]  {label}  "
    bar = "=" * max(0, width - len(header))
    print(f"\n{'=' * width}")
    print(f"{header}{bar}")
    print(f"{'=' * width}")

    if dry_run:
        print("[matrix] DRY RUN — skipped")
        return {"label": label, "rc": -1, "skipped": True}

    env_file = _write_env(overrides, base_env)
    proc = None
    try:
        if clean:
            _run_cleanup(overrides, base_env)
        log_path = _backend_log_path(label)
        print(f"[matrix] Backend log -> {log_path.name}")
        proc = start_backend(env_file, log_path=log_path)
        client = APIClient(base_url=API_URL)
        if not client.wait_until_healthy(max_wait=timeout):
            print(f"[matrix] ERROR: backend not healthy in {timeout}s — see {log_path}",
                  file=sys.stderr)
            return {"label": label, "rc": 2, "error": "startup_timeout"}
        # incremental tests need explicit marker — DEFAULT_MARKER excludes them
        inc_marker = "integration and incremental" if pytest_env and "INTEGRATION_WATCH_DIR" in pytest_env else None
        rc = run_pytest(
            test_path,
            label=label,
            extra_env=pytest_env,
            marker=inc_marker,
            pytest_k=pytest_k,
            exitfirst=exitfirst,
        )
        tag = "PASS" if rc == 0 else "FAIL"
        print(f"\n[matrix] {tag}  {label}")
        return {"label": label, "rc": rc}
    finally:
        if proc:
            stop_backend(proc)
        env_file.unlink(missing_ok=True)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Matrix runner: combine PG, RDF, vector, search, backend, fusion dimensions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--pg",       default="none",
                   help="PG graph DB(s): none | all | neo4j | neo4j,falkordb | ...")
    p.add_argument("--rdf",      default="none",
                   help="RDF graph DB(s): none | all | fuseki | fuseki,graphdb | neptune_rdf | ...")
    p.add_argument("--vector",   default="none",
                   help="Vector store(s): none | all | qdrant | qdrant,elasticsearch | ...")
    p.add_argument("--search",   default="none",
                   help="Search store(s): none | all | bm25 | elasticsearch | ...")
    p.add_argument("--backends", default="llamaindex",
                   help="Framework backend(s): llamaindex | langchain | both  (default: llamaindex)")
    p.add_argument("--fusion",   default=None,
                   help="RETRIEVAL_FUSION: llamaindex | langchain | both  "
                        "(default: matches --backends — langchain when backends=langchain, else llamaindex)")
    p.add_argument("--incremental", action="store_true",
                   help="Run incremental tests: sets ENABLE_INCREMENTAL_UPDATES=true, uses "
                        "INTEGRATION_WATCH_DIR from .env, and targets test_incremental.py. "
                        "Overrides --test-path. Use --inc-ops to select specific operations.")
    p.add_argument("--inc-ops", default="",
                   help="Comma-separated incremental operations to test when --incremental is set. "
                        "Valid ops: ingest, add, modify, delete, multiple, sync  (default: all except modify). "
                        "'ingest' = bulk /api/ingest registration path (distinct from watchdog add path). "
                        "'add'    = watchdog-detected new file → incremental engine add path. "
                        "Examples: --inc-ops ingest   --inc-ops ingest,add   --inc-ops add,delete  "
                        "          --inc-ops ingest,add,modify,delete")
    p.add_argument("--inc-clean", action="store_true",
                   help="Wipe ALL files from INTEGRATION_WATCH_DIR before starting. "
                        "Without this, only known test temp files are purged and any "
                        "docs you pre-placed in the watch dir are kept (and bulk-ingested "
                        "alongside the generated seed during registration).")
    p.add_argument("--exclude", default="",
                   help="Comma-separated DB names to skip across all dimensions "
                        "(e.g. --exclude neptune_analytics,tigergraph). "
                        "Applied after --pg/--rdf/--vector/--search expansion.")
    p.add_argument("--list-dbs", action="store_true",
                   help="Print available DB names per dimension and exit")
    p.add_argument("--base-env", default=str(BASE_ENV),
                   help=f"Base .env file (default: {BASE_ENV})")
    p.add_argument("--test-path", default="tests/integration/",
                   help="Pytest path (default: tests/integration/)")
    p.add_argument("--timeout",  type=int, default=120,
                   help="Seconds to wait for backend healthy (default: 120)")
    p.add_argument("--dry-run",  action="store_true",
                   help="Print jobs without running any backend")
    p.add_argument("--clean",    action="store_true",
                   help="Run cleanup.py before each backend start to remove stale data")
    p.add_argument("--fail-fast", action="store_true",
                   help="Stop on first failure")
    p.add_argument("-k", dest="pytest_k", default="",
                   help="Passed to pytest -k to filter tests (e.g. -k test_graph_search_no_crash)")
    p.add_argument("--llm", default=None,
                   help="LLM provider(s) to test: none | all | openai | ollama,gemini | ... "
                        f"Known: {', '.join(_LLM_OVERRIDES)}. "
                        "Only the selector + model are overridden — API keys/URLs come from .env.")
    p.add_argument("--embedding", default=None,
                   help="Embedding provider(s) to test: none | all | openai | ollama,google | ... "
                        f"Known: {', '.join(_EMBEDDING_OVERRIDES)}. "
                        "Only EMBEDDING_KIND + model var are overridden — dims/keys/URLs from .env.")
    p.add_argument("--chunker", default=None,
                   help="Chunker backend(s): llamaindex | langchain | both  "
                        "(default: None — uses .env value, no override). "
                        "When 'langchain' and --test-path is default, auto-targets test_lc_pipeline.py. "
                        "Use 'both' to run the same stack with each chunker in separate passes.")
    p.add_argument("--test-dir", default=None,
                   help="Path to a folder of multi-format documents to ingest and test. "
                        "Sets INTEGRATION_TEST_DIR env var so conftest.py exposes "
                        "the folder_doc_path fixture and tests can upload all files in it. "
                        "Example: --test-dir sample-docs  --test-dir /path/to/pdfs")
    p.add_argument("--ontology", default=None,
                   help="USE_ONTOLOGY override: true | false | both  "
                        "(default: None — always sets true when a PG store is active). "
                        "Use 'both' to run the same stack with each setting in separate passes.")
    p.add_argument("--doc-parser", default=None,
                   help="Document parser override: docling | llamaparse | default | both  "
                        "(default: None — uses .env value). "
                        "Sets DOCUMENT_PARSER env var. Use 'both' to run each parser in separate passes.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_dbs:
        print("PG backends:")
        print(f"  llamaindex: {', '.join(ALL_PG['llamaindex'])}")
        print(f"  langchain:  {', '.join(ALL_PG['langchain'])}")
        print("RDF backends:", ", ".join(ALL_RDF))
        print("Vector stores:")
        print(f"  llamaindex: {', '.join(ALL_VECTOR['llamaindex'])}")
        print(f"  langchain:  {', '.join(ALL_VECTOR['langchain'])}")
        print("Search stores:")
        print(f"  llamaindex: {', '.join(ALL_SEARCH['llamaindex'])}")
        print(f"  langchain:  {', '.join(ALL_SEARCH['langchain'])}")
        print("LLM providers:", ", ".join(_LLM_OVERRIDES))
        print("Embedding providers:", ", ".join(_EMBEDDING_OVERRIDES))
        print("Chunker backends: llamaindex, langchain")
        return 0

    backends = _resolve_backends(args.backends)

    # --fusion default: match the backend.
    # When --backends both and no explicit --fusion, pair each backend with its own fusion
    # (llamaindex→llamaindex, langchain→langchain) rather than full cartesian product.
    fusion_arg = args.fusion
    if fusion_arg is None:
        b = args.backends.lower()
        if b == "langchain":
            fusion_arg = "langchain"
        else:
            fusion_arg = "llamaindex"
    fusions = _resolve_fusions(fusion_arg)

    # backend→fusion pairing: zip backends with matching fusions when defaults apply
    # so --backends both gives (li,li) + (lc,lc) not all 4 combos.
    explicit_fusion = args.fusion is not None
    def _backend_fusion_pairs() -> list[tuple[str, str]]:
        if explicit_fusion or len(backends) == 1 or len(fusions) == 1:
            return list(itertools.product(backends, fusions))
        # both backends, no explicit fusion → pair each backend with its natural fusion
        return [(b, "langchain" if b == "langchain" else "llamaindex") for b in backends]

    base_env = Path(args.base_env)

    # --incremental: override test-path and enable incremental updates.
    # Uses INTEGRATION_WATCH_DIR from .env (or shell env) — no temp dir created.
    incremental_watch_dir: str | None = None
    if args.incremental:
        from tests.integration.env_helpers import normalized_integration_watch_dir as _nwd
        from dotenv import dotenv_values as _dv
        # Read watch dir from base .env if not already in shell env
        _raw = _nwd() or _dv(str(base_env)).get("INTEGRATION_WATCH_DIR", "") or ""
        _env_watch = os.path.normpath(_raw.strip().strip('"\'').strip())
        if not _env_watch:
            print("[matrix] ERROR: --incremental requires INTEGRATION_WATCH_DIR to be set in .env or shell.")
            return 1
        incremental_watch_dir = _env_watch
        _watch_path = Path(incremental_watch_dir)
        _watch_path.mkdir(parents=True, exist_ok=True)

        # --inc-clean: wipe ALL files for a guaranteed clean slate.
        # Otherwise purge only the known stale test filenames.
        if getattr(args, "inc_clean", False):
            _all_files = [f for f in _watch_path.iterdir() if f.is_file()]
            for _f in _all_files:
                _f.unlink()
            if _all_files:
                print(f"[matrix] --inc-clean: removed {len(_all_files)} file(s) from {_watch_path}")
            else:
                print(f"[matrix] --inc-clean: watch dir already empty")
        else:
            # Only purge per-test temp files that tests create themselves.
            # incremental_modify.txt and incremental_delete.txt are pre-placed by the
            # session fixture — do NOT purge them here; the fixture recreates them.
            # integration_seed_baseline.txt is also recreated by the fixture.
            _stale_patterns = [
                "incremental_add.txt", "multi_a.txt", "multi_b.txt",
                "integration_seed_baseline.txt",
                "incremental_modify.txt", "incremental_delete.txt",
            ]
            for _p in _stale_patterns:
                _f = _watch_path / _p
                if _f.exists():
                    _f.unlink()
                    print(f"[matrix] --incremental: removed stale watch-dir file: {_f.name}")
        args.test_path = "tests/integration/test_incremental.py"
        print(f"[matrix] --incremental: INTEGRATION_WATCH_DIR={incremental_watch_dir}")
        print(f"[matrix] --incremental: test_path=tests/integration/test_incremental.py")

        # --inc-ops: build a pytest -k expression that selects only the requested
        # operations.  Map op name → substring of the test function name.
        # "modify" is normally @pytest.mark.skip; we override that with --inc-ops.
        _INC_OP_MAP = {
            # ingest  = initial bulk /api/ingest path (registration pass, seed doc)
            # add     = watchdog-detected new file → incremental engine add path
            # These are distinct code paths; test them separately or together.
            "ingest":   "test_seed",      # bulk ingest / registration code path
            "add":      "test_add",       # incremental engine add code path
            "modify":   "test_modify",    # incremental engine modify (opt-in)
            "delete":   "test_delete",    # incremental engine delete
            "multiple": "test_multiple",  # multiple files indexed independently
            "sync":     "TestSync",       # /api/sync/* endpoint tests
        }
        _inc_ops_raw = (args.inc_ops or "").strip()
        if _inc_ops_raw:
            _ops = [o.strip().lower() for o in _inc_ops_raw.split(",") if o.strip()]
            _unknown = [o for o in _ops if o not in _INC_OP_MAP]
            if _unknown:
                print(f"[matrix] WARNING: unknown --inc-ops value(s): {_unknown}. "
                      f"Valid: {list(_INC_OP_MAP)}")
            _k_parts = [_INC_OP_MAP[o] for o in _ops if o in _INC_OP_MAP]
            if _k_parts:
                # Combine with any user-supplied -k using 'and (…)'
                _inc_k = " or ".join(_k_parts)
                if args.pytest_k:
                    args.pytest_k = f"({args.pytest_k}) and ({_inc_k})"
                else:
                    args.pytest_k = _inc_k
                print(f"[matrix] --inc-ops {_inc_ops_raw!r}: pytest -k {args.pytest_k!r}")
                # If "modify" is requested, inject the override marker so pytest
                # runs the normally-skipped test_modify_file_updates_index.
                if "modify" in _ops:
                    # --run-modify is checked in test_incremental.py to unskip
                    os.environ["INCREMENTAL_RUN_MODIFY"] = "1"
                    print("[matrix] --inc-ops modify: setting INCREMENTAL_RUN_MODIFY=1 to unskip modify test")

        # Incremental tests search for unique random phrases in raw document text.
        # Incremental tests search for unique phrases — need at least one full-text
        # or vector store configured or all searches return 0 results.
        # Auto-inject qdrant only when neither vector nor search store is specified.
        if args.vector == "none" and args.search == "none":
            args.vector = "qdrant"
            print("[matrix] --incremental: no --vector or --search specified; "
                  "auto-adding qdrant so phrase searches succeed.")

    # --exclude: set of DB names to skip across all dimensions
    excluded: set[str] = {x.strip() for x in args.exclude.split(",") if x.strip()}
    if excluded:
        print(f"[matrix] --exclude: {', '.join(sorted(excluded))}")

    # Expand per-dimension lists (backend-dependent for pg/vector/search)
    # We resolve "all" lazily per backend so milvus/weaviate appear only in langchain
    def pg_list(be):
        return [x for x in _resolve(args.pg, ALL_PG.get(be, [])) if x not in excluded]

    def vector_list(be):
        return [x for x in _resolve(args.vector, ALL_VECTOR.get(be, [])) if x not in excluded]

    def search_list(be):
        return [x for x in _resolve(args.search, ALL_SEARCH.get(be, [])) if x not in excluded]

    rdf_list = [x for x in _resolve(args.rdf, ALL_RDF) if x not in excluded]

    # LLM / embedding dimensions — None means "don't override, use .env as-is"
    llm_list = _resolve(args.llm, list(_LLM_OVERRIDES)) if args.llm else [None]
    embedding_list = _resolve(args.embedding, list(_EMBEDDING_OVERRIDES)) if args.embedding else [None]

    # Ontology dimension — None means "use matrix default (true when PG active)"
    _ontology_arg = getattr(args, "ontology", None)
    if _ontology_arg and _ontology_arg.lower() == "both":
        ontology_list: list[str | None] = ["true", "false"]
    elif _ontology_arg and _ontology_arg.lower() in ("true", "false"):
        ontology_list = [_ontology_arg.lower()]
    else:
        ontology_list = [None]  # default: matrix sets true when PG active

    # Document parser dimension — None means "use .env value"
    _parser_arg = getattr(args, "doc_parser", None)
    if _parser_arg and _parser_arg.lower() == "both":
        doc_parser_list: list[str | None] = ["docling", "llamaparse"]
    elif _parser_arg and _parser_arg.lower() in ("docling", "llamaparse", "default"):
        doc_parser_list = [_parser_arg.lower()]
    else:
        doc_parser_list = [None]  # use .env value

    # Chunker backend:
    #   --backends llamaindex → CHUNKER_BACKEND=llamaindex always; lc_pipe tests excluded
    #   --backends langchain  → CHUNKER_BACKEND=langchain always; lc_pipe tests included
    #   --backends both       → each backend gets its natural chunker (li→li, lc→lc)
    #   --chunker <val>       → explicit override for mixed testing (takes precedence)
    chunker_list: list[str | None]
    _explicit_chunker = bool(args.chunker)
    if _explicit_chunker:
        _chunker_val = args.chunker.lower()
        if _chunker_val == "both":
            chunker_list = ["llamaindex", "langchain"]
        elif _chunker_val in ("llamaindex", "langchain"):
            chunker_list = [_chunker_val]
        else:
            print(f"[matrix] ERROR: --chunker must be llamaindex | langchain | both, got {args.chunker!r}")
            return 1
    else:
        # Derive from --backends: each backend carries its natural chunker.
        # Stored per backend in the loop below; use sentinel None here so the
        # cartesian product still works — we override per-job in the loop.
        chunker_list = [None]

    # Test-path auto-selection (only when not overridden by user or --incremental):
    # --backends langchain (or --chunker langchain) → target test_lc_pipeline.py
    # --backends llamaindex                         → exclude lc_pipe marker via -k
    _DEFAULT_TEST_PATH = "tests/integration/"
    _using_lc_chunker = (
        _explicit_chunker and "langchain" in chunker_list
    ) or (
        not _explicit_chunker and "langchain" in backends
    )
    if not args.incremental and args.test_path == _DEFAULT_TEST_PATH:
        if _using_lc_chunker and not any(b == "llamaindex" for b in backends):
            # Pure LC backend run → only run lc_pipe tests (incremental still excluded)
            args.test_path = "tests/integration/test_lc_pipeline.py"
            print(f"[matrix] --backends langchain: auto-targeting {args.test_path}")
        else:
            # LI run (or mixed): exclude lc_pipe tests + incremental tests
            # lc_pipe needs CHUNKER_BACKEND=langchain; incremental needs --incremental flag
            _excludes = ["not incremental", "not datasource", "not folder_ingest"]
            if not _using_lc_chunker:
                _excludes.append("not lc_pipe")
            _exclude_expr = " and ".join(_excludes)
            if args.pytest_k:
                args.pytest_k = f"({args.pytest_k}) and ({_exclude_expr})"
            else:
                args.pytest_k = _exclude_expr
            print(f"[matrix] auto-excluding tests not applicable to this run (-k {args.pytest_k!r})")

    # Build all combinations
    jobs: list[tuple[str, dict]] = []
    seen_labels: set[str] = set()

    for backend, fusion in _backend_fusion_pairs():
        pgs     = pg_list(backend) or [None]
        rdfs    = rdf_list or [None]
        vectors = vector_list(backend) or [None]
        searches = search_list(backend) or [None]

        for pg, rdf, vector, search, llm, embedding, chunker, ontology, doc_parser in itertools.product(
                pgs, rdfs, vectors, searches, llm_list, embedding_list, chunker_list,
                ontology_list, doc_parser_list):
            # Skip: nothing active at all
            if not pg and not rdf and not vector and not search:
                continue

            # When no explicit --chunker, derive from backend (li→li, lc→lc)
            effective_chunker = chunker if _explicit_chunker else backend

            label = _label(pg, rdf, vector, search, backend, fusion, llm, embedding,
                           effective_chunker if _explicit_chunker else None,
                           ontology, doc_parser)
            if label in seen_labels:
                continue
            seen_labels.add(label)

            overrides = _build_overrides(pg, rdf, vector, search, backend, fusion, llm, embedding,
                                         effective_chunker, ontology, doc_parser)
            if incremental_watch_dir:
                overrides["ENABLE_INCREMENTAL_UPDATES"] = "true"
                overrides["INTEGRATION_WATCH_DIR"] = incremental_watch_dir
            jobs.append((label, overrides))

    if not jobs:
        print("[matrix] No jobs (all dimensions are 'none'). "
              "Specify at least one of --pg / --rdf / --vector / --search.")
        return 1

    print(f"[matrix] {len(jobs)} job(s):")
    for lbl, _ in jobs:
        print(f"  {lbl}")

    if args.dry_run:
        return 0

    results: list[dict] = []
    t0 = time.time()
    for idx, (label, overrides) in enumerate(jobs, 1):
        # Always propagate DB/LLM/embedding keys that tests read directly via
        # os.getenv() (e.g. _ingest_timeout(), _skip_graph_for_lc_pipe()).
        # These are written to the backend .env but NOT inherited by pytest.
        _PYTEST_PROPAGATE = {"LLM_PROVIDER", "EMBEDDING_KIND", "PG_GRAPH_DB",
                             "VECTOR_DB", "SEARCH_DB", "RDF_GRAPH_DB", "CHUNKER_BACKEND"}
        pytest_env: dict[str, str] = {
            k: v for k, v in overrides.items() if k in _PYTEST_PROPAGATE
        }
        # For cloud LLM providers that have variable API latency (Gemini, Anthropic,
        # Bedrock, Vertex AI, Groq, Fireworks) the graph QA chain LLM call can exceed
        # the default 120s HTTP read timeout.  Propagate a longer search timeout.
        _cloud_llm_providers = {"gemini", "vertex_ai", "anthropic", "bedrock",
                                "groq", "fireworks", "openrouter"}
        _llm_prov = overrides.get("LLM_PROVIDER", "").lower()
        if _llm_prov in _cloud_llm_providers and "INTEGRATION_SEARCH_TIMEOUT" not in pytest_env:
            pytest_env["INTEGRATION_SEARCH_TIMEOUT"] = "300"
        if incremental_watch_dir:
            pytest_env.update({
                "INTEGRATION_WATCH_DIR": incremental_watch_dir,
                "ENABLE_INCREMENTAL_UPDATES": "true",
            })
            # Propagate INCREMENTAL_RUN_MODIFY into the pytest subprocess so the
            # @pytest.mark.skipif condition reads the correct value.
            if os.environ.get("INCREMENTAL_RUN_MODIFY"):
                pytest_env["INCREMENTAL_RUN_MODIFY"] = "1"
        # Propagate --test-dir so folder-ingest tests can use folder_doc_path fixture.
        if args.test_dir:
            pytest_env["INTEGRATION_TEST_DIR"] = str(Path(args.test_dir).resolve())
        res = _run_one(label, overrides, base_env,
                       job_num=idx, total=len(jobs),
                       test_path=args.test_path,
                       timeout=args.timeout,
                       dry_run=False,
                       clean=args.clean,
                       pytest_k=args.pytest_k,
                       pytest_env=pytest_env,
                       exitfirst=args.fail_fast)
        results.append(res)
        if args.fail_fast and res.get("rc", 0) not in (0, -1):
            print(f"[matrix] --fail-fast: stopping after first failure")
            break

    elapsed = time.time() - t0
    passed = sum(1 for r in results if r.get("rc") == 0)
    failed = sum(1 for r in results if r.get("rc", 0) not in (0, -1))
    skipped = sum(1 for r in results if r.get("skipped"))

    print(f"\n{'='*64}")
    print(f"[matrix] Results ({elapsed:.0f}s):")
    for r in results:
        rc = r.get("rc", -1)
        tag = "SKIP" if r.get("skipped") else ("PASS" if rc == 0 else "FAIL")
        print(f"  {tag:4s}  {r['label']}")
    print(f"\n  {passed} passed, {failed} failed, {skipped} skipped")

    if incremental_watch_dir:
        print(f"[matrix] Watch dir preserved (inspect or reuse): {incremental_watch_dir}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
