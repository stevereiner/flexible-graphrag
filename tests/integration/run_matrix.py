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

# CocoIndex pipeline with native Qdrant + Neo4j connectors
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --pipeline cocoindex --source-backend cocoindex --graph-backend cocoindex --vector-backend cocoindex

# CocoIndex pipeline — all compatible native PG stores (neo4j, falkordb, surrealdb)
uv run tests/integration/run_matrix.py --pg neo4j,falkordb,surrealdb --vector qdrant --pipeline cocoindex --graph-backend cocoindex --vector-backend cocoindex

# CocoIndex pipeline with flexible (LlamaIndex) storage backends
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --pipeline cocoindex --source-backend cocoindex

# CocoIndex chunker (uses CocoIndex RecursiveSplitter inside the pipeline)
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --pipeline cocoindex --chunker cocoindex

# Test both pipeline backends (default and cocoindex) on the same DB stack
# NOTE: "both" expands to [default, cocoindex]; --pipeline default means use .env value
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --pipeline both --graph-backend cocoindex --vector-backend cocoindex

# Langflow flows enabled (tests Langflow component injection)
# NOTE: Langflow and CocoIndex pipeline are mutually exclusive — do not set both.
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --langflow true

# Test all 4 CocoIndex native data sources (filesystem, s3, azure_blob, google_drive)
# Each source gets its own backend start + test run (4 jobs total).
# Credentials / configs for S3/Azure/GDrive must be set in .env.
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --pipeline cocoindex --source-backend cocoindex --graph-backend cocoindex --vector-backend cocoindex --data-source all

# Test a single CocoIndex native source (filesystem only)
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --pipeline cocoindex --source-backend cocoindex --graph-backend cocoindex --vector-backend cocoindex --data-source filesystem

# Test all 12 flexible data sources (one backend start per source → 12 jobs)
# Sources skip themselves at runtime if their env config (S3_CONFIG, BOX_CONFIG, etc.) is absent.
# Targets test_datasources.py automatically; per-source pytest -k filter applied per job.
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --data-source all

# Test specific flexible data sources (2 jobs: s3, azure_blob)
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --data-source s3,azure_blob

# Scoped Ask ("ask about this document") on every vector store / every graph store:
# no results from outside the scope, and the run removes its own documents afterwards
uv run tests/integration/run_matrix.py --vector all --search bm25 --scope
uv run tests/integration/run_matrix.py --pg all --backends both --scope

# Test filesystem with incremental updates (only filesystem is supported for incremental)
uv run tests/integration/run_matrix.py --vector qdrant --incremental --data-source filesystem

# Override graph backend independently from --backends (e.g. cocoindex graph with LI vector)
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --graph-backend cocoindex

# Override vector backend independently (e.g. cocoindex vector with LC graph)
uv run tests/integration/run_matrix.py --pg neo4j --vector qdrant --backends langchain --vector-backend cocoindex

# List available DB names and all dimension options
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
        # Cloud — uncomment when instances are available:
        # "neptune",             # AWS Neptune Database
        # "neptune_analytics",   # AWS Neptune Analytics
        # "spanner",             # Google Cloud Spanner Graph — free trial expired
                                   # (CreateSession 400). Emulator is SQL-only, not Graph.
    ],
    "langchain": [
        "neo4j", "arcadedb", "falkordb", "memgraph", "nebula", "tigergraph",
        "arangodb", "apache_age", "hugegraph", "surrealdb",
        "cosmos_gremlin",      # testable with local gremlin server
        "ladybug",             # Embedded — LI adapter reused via LangChain backend
        # Cloud — uncomment when instances / compatible packages are available:
        # "spanner",           # langchain-google-spanner requires langchain-core<1.0
        # "neptune",           # AWS Neptune PG (OpenCypher)
        # "neptune_analytics", # AWS Neptune Analytics
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
    # "neptune_rdf",   # AWS Neptune RDF/SPARQL (cloud) — uncomment when cluster is available
]

# DBs that must use the langchain vector backend regardless of --backends
_LANGCHAIN_ONLY_VECTOR = {"milvus", "weaviate", "lancedb", "pinecone"}

# -----------------------------------------------------------------------------
# Pipeline / source / framework backend dimension constants
# -----------------------------------------------------------------------------

# Valid values for --pipeline (maps to PIPELINE_BACKEND env var).
# "default" = use the built-in per-stage pipeline (CHUNKER_BACKEND / GRAPH_BACKEND /
# VECTOR_BACKEND etc.) — matches config.py Field("default", ...) sentinel.
# Any value other than "cocoindex" in config.py is treated as the default pipeline.
ALL_PIPELINE: list[str] = ["default", "cocoindex"]

# Valid values for --source-backend (maps to SOURCE_BACKEND env var)
ALL_SOURCE_BACKEND: list[str] = ["flexible", "cocoindex"]

# Valid values for --graph-backend / --vector-backend (independent of --backends)
ALL_FRAMEWORK_BACKEND: list[str] = ["llamaindex", "langchain", "cocoindex"]

# Valid values for --chunker (extends existing llamaindex | langchain with cocoindex)
ALL_CHUNKER: list[str] = ["llamaindex", "langchain", "cocoindex"]

# Valid values for --langflow (maps to ENABLE_LANGFLOW_FLOWS env var)
ALL_LANGFLOW: list[str] = ["false", "true"]

# PG stores that have native CocoIndex connectors (informational — not enforced)
_COCO_NATIVE_PG = {"neo4j", "falkordb", "surrealdb"}
# Vector stores that have native CocoIndex connectors (informational — not enforced)
_COCO_NATIVE_VECTOR = {"qdrant", "lancedb", "postgres"}

# -----------------------------------------------------------------------------
# Data source dimension constants  (--data-source)
# -----------------------------------------------------------------------------

# CocoIndex native data sources — controlled by DATA_SOURCE env var
_COCO_NATIVE_SOURCES: list[str] = ["filesystem", "s3", "azure_blob", "google_drive"]
# All 13 flexible data sources (match DATA_SOURCE env var values).
# "filesystem" uses the standard test_ingest_search.py suite (no dedicated test_datasources.py test).
# "alfresco" prefix-matches both test_alfresco_ingest and test_alfresco_ingest_with_sync.
_FLEXIBLE_SOURCES: list[str] = [
    "filesystem", "web", "wikipedia", "youtube", "alfresco", "nuxeo", "cmis",
    "s3", "box", "azure_blob", "onedrive", "sharepoint", "google_drive", "gcs",
]
# Optional per-source test file (default: test_datasources.py when --data-source is set).
_FLEXIBLE_DS_TEST_PATH: dict[str, str] = {
    "filesystem": "tests/integration/test_ingest_search.py",
}
# Maps a flexible source name → pytest -k fragment (test function name).
_FLEXIBLE_DS_TEST: dict[str, str] = {
    "filesystem":   "test_ingest_company_ontology_txt_completes",
    "web":          "test_web_ingest",
    "wikipedia":    "test_wikipedia_ingest",
    "youtube":      "test_youtube_ingest",
    "alfresco":     "test_alfresco_ingest and not test_alfresco_ingest_with_sync",
    "nuxeo":        "test_nuxeo_ingest and not test_nuxeo_ingest_with_sync",
    "cmis":         "test_cmis_ingest",
    "s3":           "test_s3_ingest",
    "box":          "test_box_ingest",
    "azure_blob":   "test_azure_blob_ingest",
    "onedrive":     "test_onedrive_ingest",
    "sharepoint":   "test_sharepoint_ingest",
    "google_drive": "test_google_drive_ingest",
    "gcs":          "test_gcs_ingest",
}
# Maps a CocoIndex native source → pytest -k fragment for test_cocoindex.py.
# File-upload tests (fast/full doc ingest, reingest) only make sense for the
# "filesystem" (upload) source.  Cloud sources (s3/azure_blob/google_drive) run
# the smoke + source-reporting tests only — the ingest tests skip automatically
# inside _skip_if_cloud_source(), so we just run a lightweight subset explicitly.
_COCO_DS_TEST: dict[str, str] = {
    # "" = run all test_cocoindex.py tests; the tests themselves skip gracefully when
    # credentials or required config are absent.
    "filesystem":   "",  # upload path fully tested; bridge copies files to WATCH_DIR
    "google_drive": "",  # full suite — test_cocoindex.py skips if GOOGLE_DRIVE_CONFIG absent
    "s3":           "test_cocoindex_backend_info or test_cocoindex_health_ok or test_cocoindex_source_backend_reported or test_cocoindex_ingest_text",
    "azure_blob":   "test_cocoindex_backend_info or test_cocoindex_health_ok or test_cocoindex_source_backend_reported or test_cocoindex_ingest_text",
}
ALL_DATA_SOURCE: list[str] = sorted(set(_COCO_NATIVE_SOURCES + _FLEXIBLE_SOURCES))

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
    "google":       {"EMBEDDING_KIND": "google",       "GOOGLE_EMBEDDING_MODEL": "gemini-embedding-001"},
    "vertex":       {"EMBEDDING_KIND": "vertex",       "VERTEX_EMBEDDING_MODEL": "gemini-embedding-001"},
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
    # Cloud Spanner Graph from .env (SPANNER_GRAPH_DB_CONFIG). Emulator is SQL-only
    # (not Spanner Graph) — keep using cloud config when re-enabling in ALL_PG.
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
                      "ELASTICSEARCH_VECTOR_DB_CONFIG": '{"url":"http://localhost:9200","index_name":"hybrid_search_vector"}'},
    "opensearch":    {"VECTOR_DB": "opensearch",
                      "OPENSEARCH_VECTOR_DB_CONFIG": '{"url":"http://localhost:9201","index_name":"hybrid_search_vector"}'},
    "postgres":      {"VECTOR_DB": "postgres",
                      "POSTGRES_VECTOR_DB_CONFIG": '{"host":"localhost","port":5433,"username":"postgres","password":"password","database":"flexible_graphrag","table_name":"hybrid_search_vectors"}'},
    "chroma":        {"VECTOR_DB": "chroma",
                      "CHROMA_VECTOR_DB_CONFIG": '{"host":"localhost","port":8001,"collection_name":"hybrid_search_vector"}'},
    "milvus":        {"VECTOR_DB": "milvus",
                      "MILVUS_VECTOR_DB_CONFIG": '{"host":"localhost","port":19530,"collection_name":"hybrid_search_vector"}'},
    # 8086, not 8081 — 8081 is Nuxeo (docker/includes/weaviate.yaml).  A stale
    # 8081 here reaches Nuxeo instead and fails as
    # "Meta endpoint! Unexpected status code: 404".
    "weaviate":      {"VECTOR_DB": "weaviate",
                      "WEAVIATE_VECTOR_DB_CONFIG": '{"url":"http://localhost:8086","grpc_port":50051,"index_name":"HybridSearch","text_key":"content"}'},
    "lancedb":       {"VECTOR_DB": "lancedb",
                      "LANCEDB_VECTOR_DB_CONFIG": '{"uri":"./lancedb_matrix_test","table_name":"hybrid_search_vector"}'},
    "pinecone":      {"VECTOR_DB": "pinecone"},
    "neo4j":         {"VECTOR_DB": "neo4j",
                      "NEO4J_VECTOR_DB_CONFIG": '{"url":"bolt://localhost:7687","username":"neo4j","password":"password"}'},
}

_SEARCH_OVERRIDES: dict[str, dict] = {
    "bm25":          {"SEARCH_DB": "bm25", "BM25_PERSIST_DIR": "./test_bm25_matrix"},
    "elasticsearch": {"SEARCH_DB": "elasticsearch",
                      "ELASTICSEARCH_SEARCH_DB_CONFIG": '{"url":"http://localhost:9200","index_name":"hybrid_search_fulltext"}'},
    "opensearch":    {"SEARCH_DB": "opensearch",
                      "OPENSEARCH_SEARCH_DB_CONFIG": '{"url":"http://localhost:9201","index_name":"hybrid_search_fulltext"}'},
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
    pipeline: str | None = None,
    source_backend: str | None = None,
    langflow: str | None = None,
    graph_backend: str | None = None,
    vector_backend: str | None = None,
    data_source: str | None = None,
    search_backend: str | None = None,
) -> dict[str, str]:
    """Assemble the env-var overrides for one combination."""
    overrides: dict[str, str] = {}

    has_pg  = bool(pg)
    has_rdf = bool(rdf)

    # -- Pipeline backend (CocoIndex vs default per-stage pipeline) -----------
    # config.py Field("default", ...) — any value other than "cocoindex" means
    # the normal per-stage pipeline.  Matrix jobs must not inherit
    # PIPELINE_BACKEND=cocoindex from a developer .env unless --pipeline
    # cocoindex (or chunker=cocoindex) is explicitly requested.
    if pipeline and pipeline not in ("default", ""):
        overrides["PIPELINE_BACKEND"] = pipeline
    elif chunker != "cocoindex":
        overrides["PIPELINE_BACKEND"] = "default"

    # -- Source backend (cocoindex native vs flexible detector-backed) ---------
    if source_backend:
        overrides["SOURCE_BACKEND"] = source_backend

    # -- Data source (DATA_SOURCE env var) ------------------------------------
    if data_source:
        overrides["DATA_SOURCE"] = data_source
        # Filesystem source needs WATCH_DIR so the CocoIndex bridge and flexible
        # filesystem source know where to copy / scan files.  Use ../cocoindex-docs
        # (relative to the backend's working dir = flexible-graphrag/) which is the
        # CLI convention; the bridge auto-creates the directory on startup.
        if data_source == "filesystem":
            overrides.setdefault("WATCH_DIR", "../cocoindex-docs")
        elif data_source == "cmis":
            # Scope the CocoIndex startup sync to the same folder the test uses.
            # Without this the bridge defaults to folder_path="/" and crawls the
            # entire Alfresco repo at startup instead of just /Shared/GraphRAG.
            overrides.setdefault("CMIS_FOLDER_PATH", "/Shared/GraphRAG")
        elif data_source == "alfresco":
            # Same reasoning as CMIS above — default path "/" crawls everything.
            # AlfrescoSource reads config.get("path", "/") and backend.py reads
            # ALFRESCO_PATH for the env-var fallback config.
            overrides.setdefault("ALFRESCO_PATH", "/Shared/GraphRAG")

    # -- Langflow flows --------------------------------------------------------
    if langflow is not None:
        overrides["ENABLE_LANGFLOW_FLOWS"] = langflow

    # -- PG graph --------------------------------------------------------------
    if has_pg:
        overrides.update(_PG_OVERRIDES[pg])
        # graph_backend overrides --backends for graph only
        effective_graph_be = graph_backend if graph_backend else backend
        overrides["GRAPH_BACKEND"] = effective_graph_be
        if effective_graph_be == "langchain":
            overrides["USE_LANGCHAIN_PG"] = "true"
        # ontology: explicit value overrides the default "true"
        overrides["USE_ONTOLOGY"] = ontology if ontology else "true"
    else:
        overrides["PG_GRAPH_DB"] = "none"
        if graph_backend:
            overrides["GRAPH_BACKEND"] = graph_backend

    # -- RDF graph -------------------------------------------------------------
    if has_rdf:
        overrides.update(_RDF_OVERRIDES[rdf])
    else:
        overrides["RDF_GRAPH_DB"] = "none"

    # -- Vector store ----------------------------------------------------------
    if vector:
        overrides.update(_VECTOR_OVERRIDES[vector])
        # vector_backend overrides --backends for vector only
        overrides["VECTOR_BACKEND"] = vector_backend if vector_backend else backend
    else:
        overrides["VECTOR_DB"] = "none"
        if vector_backend:
            overrides["VECTOR_BACKEND"] = vector_backend

    # -- Search store ----------------------------------------------------------
    if search:
        overrides.update(_SEARCH_OVERRIDES[search])
        # search_backend overrides --backends for search only (mirrors graph_backend / vector_backend)
        overrides["SEARCH_BACKEND"] = search_backend if search_backend else backend
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

    # -- Chunker backend (llamaindex | langchain | cocoindex) ------------------
    if chunker:
        overrides["CHUNKER_BACKEND"] = chunker
        # CocoIndex chunker only works inside the CocoIndex pipeline
        if chunker == "cocoindex" and "PIPELINE_BACKEND" not in overrides:
            overrides["PIPELINE_BACKEND"] = "cocoindex"

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
           ontology=None, doc_parser=None, pipeline=None, source_backend=None,
           langflow=None, graph_backend=None, vector_backend=None, data_source=None,
           search_backend=None) -> str:
    dbs = []
    if pg:     dbs.append(f"pg:{pg}")
    if rdf:    dbs.append(f"rdf:{rdf}")
    if vector: dbs.append(f"vec:{vector}")
    if search: dbs.append(f"search:{search}")
    db_str = "  ".join(dbs) if dbs else "no-graph"
    # Note: backend / fusion are test-internal conveniences (--backends shorthand); only
    # show fusion since it IS a real config knob (RETRIEVAL_FUSION). The backend shorthand
    # itself is already visible through the individual graph-be / vec-be / search-be labels.
    suffix = f"  |  fusion:{fusion}"
    if pipeline:        suffix += f"  |  pipeline:{pipeline}"
    if source_backend:  suffix += f"  |  src:{source_backend}"
    if data_source:     suffix += f"  |  ds:{data_source}"
    if graph_backend:   suffix += f"  |  graph-be:{graph_backend}"
    if vector_backend:  suffix += f"  |  vec-be:{vector_backend}"
    if search_backend:  suffix += f"  |  search-be:{search_backend}"
    if chunker:         suffix += f"  |  chunker:{chunker}"
    if langflow:        suffix += f"  |  langflow:{langflow}"
    if llm:             suffix += f"  |  llm:{llm}"
    if embedding:       suffix += f"  |  emb:{embedding}"
    if ontology:        suffix += f"  |  ontology:{ontology}"
    if doc_parser:      suffix += f"  |  parser:{doc_parser}"
    return f"{db_str}{suffix}"


_SCOPE_REGISTRY_URL = "postgresql://postgres:password@localhost:5433/fg_scope_matrix"


def _ensure_database(url: str) -> None:
    """Create the PostgreSQL database in ``url`` when it does not exist (--scope registry)."""
    import asyncio
    from urllib.parse import urlparse, urlunparse

    import asyncpg

    name = urlparse(url).path.lstrip("/")
    admin = urlunparse(urlparse(url)._replace(path="/postgres"))

    async def run() -> None:
        conn = await asyncpg.connect(admin)
        try:
            if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
                await conn.execute(f'CREATE DATABASE "{name}"')
                print(f"[matrix] --scope: created registry database {name}")
        finally:
            await conn.close()

    asyncio.run(run())


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
    # base_env is not needed — env vars take precedence over load_dotenv()
    # (which never overrides existing env vars).

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
            if any(kw in line for kw in ("ERROR", "WARN", "Cleaned", "Deleted", "Dropped", "Wipe", "TIMING")):
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
             per_job_pytest_k: str = "",
             per_job_test_path: str | None = None,
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

    effective_test_path = per_job_test_path or test_path
    # Merge global -k filter with per-job filter (e.g. specific datasource test)
    effective_k = pytest_k
    if per_job_pytest_k:
        effective_k = (
            f"({effective_k}) and ({per_job_pytest_k})" if effective_k else per_job_pytest_k
        )

    env_file = _write_env(overrides, base_env)
    proc = None
    try:
        log_path = _backend_log_path(label)
        client = APIClient(base_url=API_URL)
        # When Langflow tests are requested the user typically runs their own backend
        # (with ENABLE_LANGFLOW_FLOWS=true and flows already bound).  Starting a second
        # backend process here would:
        #   a) fail to bind port 8000 (conflict), AND
        #   b) run initialize_flows() first — deleting the running backend's LangFlow
        #      flow IDs before dying — which invalidates every subsequent flow call.
        # Guard: if the backend is already healthy, skip the start AND skip --clean so
        # that the running backend's live indexes are not wiped out from under it.
        _pre_existing = client.wait_until_healthy(max_wait=3)
        if _pre_existing:
            print(f"[matrix] Pre-existing backend detected at {API_URL} — skipping start"
                  f"{' and --clean' if clean else ''} (use the running instance; stop it manually when done)")
        else:
            if clean:
                _run_cleanup(overrides, base_env)
            print(f"[matrix] Backend log -> {log_path.name}")
            proc = start_backend(env_file, log_path=log_path)
            if not client.wait_until_healthy(max_wait=timeout):
                print(f"[matrix] ERROR: backend not healthy in {timeout}s — see {log_path}",
                      file=sys.stderr)
                return {"label": label, "rc": 2, "error": "startup_timeout"}
        # incremental tests need explicit marker — DEFAULT_MARKER excludes them
        inc_marker = "integration and incremental" if pytest_env and "INTEGRATION_WATCH_DIR" in pytest_env else None
        rc = run_pytest(
            effective_test_path,
            label=label,
            extra_env=pytest_env,
            marker=inc_marker,
            pytest_k=effective_k,
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
    p.add_argument("--scope", action="store_true",
                   help="Run the scoped-Ask tests (test_scope.py) per combination: two Alfresco "
                        "documents ingested, questions scoped to one, nothing from the other may "
                        "come back; the test removes its documents itself. Turns on the "
                        "incremental registry (scoping resolves documents through it) on its own "
                        "database: SCOPE_TEST_INCREMENTAL_URL (default "
                        f"{_SCOPE_REGISTRY_URL}), created when missing. Overrides --test-path.")
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
                   help="Chunker backend(s): llamaindex | langchain | cocoindex | both  "
                        "(default: None — uses .env value, no override). "
                        "When 'langchain' and --test-path is default, auto-targets test_lc_pipeline.py. "
                        "cocoindex uses CocoIndex RecursiveSplitter; implies PIPELINE_BACKEND=cocoindex. "
                        "Use 'both' to run the same stack with each chunker in separate passes.")
    p.add_argument("--pipeline", default=None,
                   help="Pipeline backend(s): default | cocoindex | both  "
                        "(sets PIPELINE_BACKEND). 'default' = built-in per-stage pipeline "
                        "(CHUNKER_BACKEND / GRAPH_BACKEND / VECTOR_BACKEND etc., matches "
                        "config.py sentinel). 'cocoindex' enables the CocoIndex bridge "
                        "inside the FastAPI server — tests still run against the HTTP API. "
                        "NOTE: CocoIndex and Langflow (--langflow true) are mutually exclusive; "
                        "do not combine them.")
    p.add_argument("--source-backend", default=None,
                   help="Source backend(s): flexible | cocoindex | both  "
                        "(sets SOURCE_BACKEND). 'cocoindex' uses CocoIndex native connectors "
                        "for data ingestion; 'flexible' uses detector-backed adapters.")
    p.add_argument("--data-source", default=None,
                   help="Data source(s) to test per job (sets DATA_SOURCE). "
                        "One backend start per source. 'all' expands based on --source-backend: "
                        "cocoindex → filesystem,s3,azure_blob,google_drive; "
                        f"flexible → {','.join(_FLEXIBLE_SOURCES)}. "
                        "With --source-backend cocoindex (or --pipeline cocoindex): targets "
                        "test_cocoindex.py — each job runs the full suite with that DATA_SOURCE. "
                        "With --source-backend flexible (default): targets test_datasources.py "
                        "and filters to the matching test function per source. "
                        "With --incremental: only 'filesystem' is supported. "
                        f"CocoIndex native: {', '.join(_COCO_NATIVE_SOURCES)}. "
                        f"Flexible: {', '.join(_FLEXIBLE_SOURCES)}.")
    p.add_argument("--langflow", default=None,
                   help="Enable Langflow flows: false (default) | true | both  "
                        "(sets ENABLE_LANGFLOW_FLOWS). Targets test_langflow.py when 'true'.")
    p.add_argument("--graph-backend", default=None,
                   help="GRAPH_BACKEND override (independent of --backends): "
                        "llamaindex | langchain | cocoindex | both  "
                        "Overrides only GRAPH_BACKEND; VECTOR_BACKEND and SEARCH_BACKEND "
                        "still derive from --backends unless --vector-backend is also set. "
                        "Native CocoIndex PG connectors: neo4j, falkordb, surrealdb.")
    p.add_argument("--vector-backend", default=None,
                   help="VECTOR_BACKEND override (independent of --backends): "
                        "llamaindex | langchain | cocoindex | both  "
                        "Overrides only VECTOR_BACKEND. "
                        "Native CocoIndex vector connectors: qdrant, lancedb, postgres.")
    p.add_argument("--search-backend", default=None,
                   help="SEARCH_BACKEND override (independent of --backends): "
                        "llamaindex | langchain | both  "
                        "Overrides only SEARCH_BACKEND; GRAPH_BACKEND and VECTOR_BACKEND "
                        "still derive from --backends unless also explicitly set.")
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
        print("  cocoindex (native):  neo4j, falkordb, surrealdb")
        print("RDF backends:", ", ".join(ALL_RDF))
        print("Vector stores:")
        print(f"  llamaindex: {', '.join(ALL_VECTOR['llamaindex'])}")
        print(f"  langchain:  {', '.join(ALL_VECTOR['langchain'])}")
        print("  cocoindex (native):  qdrant, lancedb, postgres")
        print("Search stores:")
        print(f"  llamaindex: {', '.join(ALL_SEARCH['llamaindex'])}")
        print(f"  langchain:  {', '.join(ALL_SEARCH['langchain'])}")
        print("LLM providers:", ", ".join(_LLM_OVERRIDES))
        print("Embedding providers:", ", ".join(_EMBEDDING_OVERRIDES))
        print(f"Chunker backends (--chunker):        {', '.join(ALL_CHUNKER)}")
        print(f"Pipeline backends (--pipeline):      {', '.join(ALL_PIPELINE)}")
        print(f"Source backends (--source-backend):  {', '.join(ALL_SOURCE_BACKEND)}")
        print(f"Graph backends (--graph-backend):    {', '.join(ALL_FRAMEWORK_BACKEND)}")
        print(f"Vector backends (--vector-backend):  {', '.join(ALL_FRAMEWORK_BACKEND)}")
        print(f"Search backends (--search-backend):  llamaindex, langchain")
        print(f"Langflow (--langflow):               {', '.join(ALL_LANGFLOW)}")
        print(f"Data sources (--data-source):")
        print(f"  cocoindex native: {', '.join(_COCO_NATIVE_SOURCES)}")
        print(f"  flexible:         {', '.join(_FLEXIBLE_SOURCES)}")
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

    # --scope: scoped-Ask tests, incremental registry on (its own database)
    scope_registry_url: str | None = None
    if args.scope:
        scope_registry_url = os.environ.get("SCOPE_TEST_INCREMENTAL_URL", _SCOPE_REGISTRY_URL)
        if not args.dry_run:
            _ensure_database(scope_registry_url)
        args.test_path = "tests/integration/test_scope.py"
        print(f"[matrix] --scope: test_path={args.test_path}, registry={scope_registry_url}")

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

    # Chunker backend (llamaindex | langchain | cocoindex | both):
    #   --backends llamaindex → CHUNKER_BACKEND=llamaindex always; lc_pipe tests excluded
    #   --backends langchain  → CHUNKER_BACKEND=langchain always; lc_pipe tests included
    #   --backends both       → each backend gets its natural chunker (li→li, lc→lc)
    #   --chunker <val>       → explicit override for mixed testing (takes precedence)
    #   --chunker cocoindex   → CHUNKER_BACKEND=cocoindex; implies PIPELINE_BACKEND=cocoindex
    chunker_list: list[str | None]
    _explicit_chunker = bool(args.chunker)
    if _explicit_chunker:
        _chunker_val = args.chunker.lower()
        if _chunker_val == "both":
            chunker_list = ["llamaindex", "langchain"]
        elif _chunker_val in ALL_CHUNKER:
            chunker_list = [_chunker_val]
        else:
            print(f"[matrix] ERROR: --chunker must be {' | '.join(ALL_CHUNKER)} | both, "
                  f"got {args.chunker!r}")
            return 1
    else:
        # Derive from --backends: each backend carries its natural chunker.
        # Stored per backend in the loop below; use sentinel None here so the
        # cartesian product still works — we override per-job in the loop.
        chunker_list = [None]

    # Pipeline backend dimension — None means "force default (not cocoindex)"
    _pipeline_arg = getattr(args, "pipeline", None)
    if _pipeline_arg and _pipeline_arg.lower() == "both":
        pipeline_list: list[str | None] = ["default", "cocoindex"]
    elif _pipeline_arg and _pipeline_arg.lower() in ALL_PIPELINE:
        pipeline_list = [_pipeline_arg.lower()]
    else:
        pipeline_list = [None]  # no override — use .env value

    # Source backend dimension
    _src_arg = getattr(args, "source_backend", None)
    if _src_arg and _src_arg.lower() == "both":
        source_backend_list: list[str | None] = ["flexible", "cocoindex"]
    elif _src_arg and _src_arg.lower() in ALL_SOURCE_BACKEND:
        source_backend_list = [_src_arg.lower()]
    else:
        source_backend_list = [None]  # no override

    # Langflow dimension
    _langflow_arg = getattr(args, "langflow", None)
    if _langflow_arg and _langflow_arg.lower() == "both":
        langflow_list: list[str | None] = ["false", "true"]
    elif _langflow_arg and _langflow_arg.lower() in ALL_LANGFLOW:
        langflow_list = [_langflow_arg.lower()]
    else:
        langflow_list = [None]  # no override

    # Graph backend override dimension
    _gb_arg = getattr(args, "graph_backend", None)
    if _gb_arg and _gb_arg.lower() == "both":
        graph_backend_list: list[str | None] = ["llamaindex", "langchain"]
    elif _gb_arg and _gb_arg.lower() in ALL_FRAMEWORK_BACKEND:
        graph_backend_list = [_gb_arg.lower()]
    else:
        graph_backend_list = [None]  # derive from --backends

    # Vector backend override dimension
    _vb_arg = getattr(args, "vector_backend", None)
    if _vb_arg and _vb_arg.lower() == "both":
        vector_backend_list: list[str | None] = ["llamaindex", "langchain"]
    elif _vb_arg and _vb_arg.lower() in ALL_FRAMEWORK_BACKEND:
        vector_backend_list = [_vb_arg.lower()]
    else:
        vector_backend_list = [None]  # derive from --backends

    # Search backend override dimension
    _sb_arg = getattr(args, "search_backend", None)
    if _sb_arg and _sb_arg.lower() == "both":
        search_backend_list: list[str | None] = ["llamaindex", "langchain"]
    elif _sb_arg and _sb_arg.lower() in ("llamaindex", "langchain"):
        search_backend_list = [_sb_arg.lower()]
    else:
        search_backend_list = [None]  # derive from --backends

    # Data source dimension — one job per source, each starting its own backend
    # 'all' expands to the set appropriate for the active --source-backend:
    #   cocoindex → _COCO_NATIVE_SOURCES; flexible/default → _FLEXIBLE_SOURCES
    _ds_arg = getattr(args, "data_source", None)
    _ds_is_coco_sb = bool(
        source_backend_list and all(sb in (None, "cocoindex") for sb in source_backend_list)
        and any(sb == "cocoindex" for sb in source_backend_list)
    )
    data_source_list: list[str | None]
    if _ds_arg:
        _ds_val = _ds_arg.lower()
        if _ds_val == "all":
            data_source_list = list(_COCO_NATIVE_SOURCES) if _ds_is_coco_sb else list(_FLEXIBLE_SOURCES)
        elif "," in _ds_val:
            data_source_list = [s.strip() for s in _ds_val.split(",") if s.strip()]
        elif _ds_val in ALL_DATA_SOURCE:
            data_source_list = [_ds_val]
        else:
            print(f"[matrix] ERROR: --data-source {_ds_arg!r} not recognised. "
                  f"Valid: {', '.join(ALL_DATA_SOURCE)} | all")
            return 1
        # Warn when --incremental is set with non-filesystem sources
        if args.incremental:
            non_fs = [ds for ds in data_source_list if ds != "filesystem"]
            if non_fs:
                print(f"[matrix] WARNING: --incremental only supports 'filesystem'; "
                      f"skipping non-filesystem sources: {', '.join(non_fs)}")
                data_source_list = [ds for ds in data_source_list if ds == "filesystem"]
                if not data_source_list:
                    print("[matrix] ERROR: no valid data sources remain after filtering for --incremental.")
                    return 1
    else:
        data_source_list = [None]  # no DATA_SOURCE override

    # Test-path auto-selection (only when not overridden by user or --incremental):
    # --backends langchain (or --chunker langchain)  → target test_lc_pipeline.py
    # --langflow true                                → target test_langflow.py
    # --pipeline cocoindex + native coco backends    → target test_cocoindex.py
    # --pipeline cocoindex + flexible LI/LC backends → keep flex tests (ingest/search,
    #   datasources, lc_pipe) — same suites as default pipeline, different orchestrator
    # --data-source + flexible source-backend        → target test_datasources.py
    # --backends llamaindex                          → exclude lc_pipe marker via -k
    _DEFAULT_TEST_PATH = "tests/integration/"
    _using_lc_chunker = (
        _explicit_chunker and "langchain" in chunker_list
    ) or (
        not _explicit_chunker and "langchain" in backends
    )
    _using_langflow = bool(_langflow_arg and "true" in langflow_list)
    _using_cocoindex_pipeline = bool(pipeline_list and "cocoindex" in pipeline_list)
    # Native CocoIndex targets/sources (coco full-suite steps 1-3). Flexible stores
    # under PIPELINE_BACKEND=cocoindex must NOT force test_cocoindex.py.
    _using_native_coco = bool(
        _using_cocoindex_pipeline
        and (
            _ds_is_coco_sb
            or any(sb == "cocoindex" for sb in source_backend_list if sb)
            or any(gb == "cocoindex" for gb in graph_backend_list if gb)
            or any(vb == "cocoindex" for vb in vector_backend_list if vb)
        )
    )
    _using_data_source = bool(_ds_arg)
    # Flexible datasource run: --data-source set, not native-coco source backend,
    # AND at least one source has a dedicated test in test_datasources.py.
    # PIPELINE_BACKEND=cocoindex is allowed — flexible sources still use these tests.
    _using_flexible_ds = (
        _using_data_source
        and not _using_native_coco
        and not _ds_is_coco_sb
        and any(_FLEXIBLE_DS_TEST.get(ds, "") for ds in data_source_list if ds)
    )

    if not args.incremental and not args.scope and args.test_path == _DEFAULT_TEST_PATH:
        if _using_langflow and not _using_lc_chunker and not _using_native_coco:
            args.test_path = "tests/integration/test_langflow.py"
            print(f"[matrix] --langflow true: auto-targeting {args.test_path}")
        elif _using_native_coco and not _using_lc_chunker and not _using_langflow:
            args.test_path = "tests/integration/test_cocoindex.py"
            print(f"[matrix] --pipeline cocoindex (native backends): auto-targeting {args.test_path}")
        elif _using_flexible_ds and not _using_lc_chunker and not _using_langflow:
            args.test_path = "tests/integration/test_datasources.py"
            print(f"[matrix] --data-source (flexible): auto-targeting {args.test_path}")
        elif _using_lc_chunker and not any(b == "llamaindex" for b in backends):
            # Pure LC backend run → only run lc_pipe tests (incremental still excluded)
            args.test_path = "tests/integration/test_lc_pipeline.py"
            print(f"[matrix] --backends langchain: auto-targeting {args.test_path}")
        else:
            # LI run (or mixed): exclude lc_pipe tests + incremental tests
            # lc_pipe needs CHUNKER_BACKEND=langchain; incremental needs --incremental flag
            _excludes = ["not incremental", "not datasource", "not folder_ingest",
                         "not langflow", "not cocoindex"]
            if not _using_lc_chunker:
                _excludes.append("not lc_pipe")
            _exclude_expr = " and ".join(_excludes)
            if args.pytest_k:
                args.pytest_k = f"({args.pytest_k}) and ({_exclude_expr})"
            else:
                args.pytest_k = _exclude_expr
            print(f"[matrix] auto-excluding tests not applicable to this run (-k {args.pytest_k!r})")

    # Build all combinations
    jobs: list[tuple[str, dict, str, str | None]] = []  # (label, overrides, per_job_pytest_k, per_job_test_path)
    seen_labels: set[str] = set()

    for backend, fusion in _backend_fusion_pairs():
        pgs     = pg_list(backend) or [None]
        rdfs    = rdf_list or [None]
        vectors = vector_list(backend) or [None]
        searches = search_list(backend) or [None]

        for (pg, rdf, vector, search, llm, embedding, chunker,
             ontology, doc_parser, pipeline, source_backend, langflow,
             graph_backend, vector_backend, search_backend, data_source) in itertools.product(
                pgs, rdfs, vectors, searches,
                llm_list, embedding_list, chunker_list,
                ontology_list, doc_parser_list,
                pipeline_list, source_backend_list, langflow_list,
                graph_backend_list, vector_backend_list, search_backend_list, data_source_list):
            # Skip: nothing active at all
            if not pg and not rdf and not vector and not search:
                continue

            # When no explicit --chunker, derive from pipeline/backend:
            #   - CocoIndex pipeline  → chunker=cocoindex (uses CocoIndex's own splitter)
            #   - all other pipelines → chunker=llamaindex (LI SentenceSplitter, always safe)
            # An explicit --chunker flag always wins.
            if _explicit_chunker:
                effective_chunker = chunker
            elif pipeline == "cocoindex":
                effective_chunker = "cocoindex"
            else:
                effective_chunker = "llamaindex"

            label = _label(pg, rdf, vector, search, backend, fusion, llm, embedding,
                           effective_chunker if _explicit_chunker else None,
                           ontology, doc_parser,
                           pipeline, source_backend, langflow,
                           graph_backend, vector_backend, data_source,
                           search_backend)
            if label in seen_labels:
                continue
            seen_labels.add(label)

            overrides = _build_overrides(
                pg, rdf, vector, search, backend, fusion, llm, embedding,
                effective_chunker, ontology, doc_parser,
                pipeline, source_backend, langflow, graph_backend, vector_backend,
                data_source, search_backend,
            )
            if incremental_watch_dir:
                overrides["ENABLE_INCREMENTAL_UPDATES"] = "true"
            if scope_registry_url:
                overrides["ENABLE_INCREMENTAL_UPDATES"] = "true"
                overrides["POSTGRES_INCREMENTAL_URL"] = scope_registry_url
                overrides["INTEGRATION_WATCH_DIR"] = incremental_watch_dir

            # Per-job pytest filter: restrict to the matching test function so each
            # job tests exactly one data source (avoids running all N tests per job).
            per_job_pytest_k = ""
            per_job_test_path: str | None = None
            if data_source:
                if _ds_is_coco_sb:
                    # CocoIndex native source — target test_cocoindex.py with a
                    # source-specific -k filter (cloud sources run smoke tests only).
                    per_job_pytest_k = _COCO_DS_TEST.get(data_source, "")
                else:
                    # Flexible (LlamaIndex/LangChain) source — target the matching
                    # test function in test_datasources.py (or test_ingest_search.py).
                    per_job_pytest_k = _FLEXIBLE_DS_TEST.get(data_source, "")
                    per_job_test_path = _FLEXIBLE_DS_TEST_PATH.get(data_source)

            jobs.append((label, overrides, per_job_pytest_k, per_job_test_path))

    if not jobs:
        print("[matrix] No jobs (all dimensions are 'none'). "
              "Specify at least one of --pg / --rdf / --vector / --search.")
        return 1

    print(f"[matrix] {len(jobs)} job(s):")
    for lbl, _, _, _ in jobs:
        print(f"  {lbl}")

    if args.dry_run:
        return 0

    results: list[dict] = []
    t0 = time.time()
    for idx, (label, overrides, per_job_pytest_k, per_job_test_path) in enumerate(jobs, 1):
        # Always propagate DB/LLM/embedding keys that tests read directly via
        # os.getenv() (e.g. _ingest_timeout(), _skip_graph_for_lc_pipe()).
        # These are written to the backend .env but NOT inherited by pytest.
        _PYTEST_PROPAGATE = {
            "LLM_PROVIDER", "EMBEDDING_KIND",
            "PG_GRAPH_DB", "VECTOR_DB", "SEARCH_DB", "RDF_GRAPH_DB",
            "CHUNKER_BACKEND", "GRAPH_BACKEND", "VECTOR_BACKEND", "SEARCH_BACKEND",
            # CocoIndex + Langflow flags read by test modules via os.getenv()
            "PIPELINE_BACKEND", "SOURCE_BACKEND", "ENABLE_LANGFLOW_FLOWS",
            # Data source — read by datasource tests to adjust skip/assert logic
            "DATA_SOURCE",
        }
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
                       per_job_pytest_k=per_job_pytest_k,
                       per_job_test_path=per_job_test_path,
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
