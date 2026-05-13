"""
Environment profile registry for integration tests.

Each profile is a dict of env-var overrides layered on top of a base env.
``build_env_file`` also applies ``INTEGRATION_DEFAULT_OVERRIDES`` first (e.g.
``ENABLE_INCREMENTAL_UPDATES=false`` for fast startup); profile keys win.

The helper functions write a temporary .env file and return its path, which
the run_profile.py launcher uses to start the backend.

Usage (from run_profile.py):
    env_path = build_env_file("neo4j-llamaindex", base_env="flexible-graphrag/.env")
    subprocess.Popen(["uv", "run", "start.py"], env=load_env(env_path))
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

# ──────────────────────────────────────────────────────────────────────────────
# Profile definitions
# Each dict contains only the OVERRIDES — keys absent here keep their
# value from the base .env (or the OS environment).
#
# INGESTION_STORAGE_MODE: official docs list property_graph | rdf_only | both
# (docs/RDF/INGESTION-AND-STORAGE-MODES.md). Do not use informal values like
# "vector_only" here — they read as VECTOR_DB semantics and confuse BM25-only profiles.
# ──────────────────────────────────────────────────────────────────────────────

PROFILES: dict[str, dict[str, str]] = {
    # ── LlamaIndex property graph backends ──────────────────────────────────
    "neo4j-llamaindex": {
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "llamaindex",
        "USE_ONTOLOGY": "true",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "falkordb-llamaindex": {
        "PG_GRAPH_DB": "falkordb",
        "GRAPH_BACKEND": "llamaindex",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "FALKORDB_HOST": "localhost",
        "FALKORDB_PORT": "6379",
        "FALKORDB_URL": "falkor://localhost:6379",
        # Named blob takes precedence over any GRAPH_DB_CONFIG set in the base .env
        "FALKORDB_GRAPH_DB_CONFIG": '{"url": "falkor://localhost:6379", "database": "falkor"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "memgraph-llamaindex": {
        "PG_GRAPH_DB": "memgraph",
        "GRAPH_BACKEND": "llamaindex",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "MEMGRAPH_URL": "bolt://localhost:7688",
        "MEMGRAPH_USERNAME": "",
        "MEMGRAPH_PASSWORD": "",
        "MEMGRAPH_GRAPH_DB_CONFIG": (
            '{"url": "bolt://localhost:7688", "username": "", "password": "", "database": "memgraph"}'
        ),
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "arcadedb-llamaindex": {
        "PG_GRAPH_DB": "arcadedb",
        "GRAPH_BACKEND": "llamaindex",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "ARCADEDB_HOST": "localhost",
        "ARCADEDB_PORT": "2480",
        "ARCADEDB_DATABASE": "flexible_graphrag",
        "ARCADEDB_USERNAME": "root",
        "ARCADEDB_PASSWORD": "playwithdata",
        "ARCADEDB_GRAPH_DB_CONFIG": (
            '{"host": "localhost", "port": 2480, "username": "root", "password": "playwithdata", '
            '"database": "flexible_graphrag", "include_basic_schema": true}'
        ),
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },

    # ── LangChain property graph backends ───────────────────────────────────
    # USE_LANGCHAIN_PG and LANGCHAIN_PG_STORE_TYPE are auto-set by config.py when
    # GRAPH_BACKEND=langchain; they are included here only for extra explicitness.
    "neo4j-langchain": {
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "langchain",
        "USE_LANGCHAIN_PG": "true",
        "LANGCHAIN_PG_STORE_TYPE": "neo4j",
        "USE_ONTOLOGY": "true",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "arangodb-langchain": {
        "PG_GRAPH_DB": "arangodb",
        "GRAPH_BACKEND": "langchain",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "ARANGODB_GRAPH_DB_CONFIG": '{"url": "http://localhost:8529", "database": "flexible-graphrag", "username": "root", "password": "testpass", "graph_name": "knowledge_graph"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "apache-age-langchain": {
        "PG_GRAPH_DB": "apache_age",
        "GRAPH_BACKEND": "langchain",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        # AGE postgres: POSTGRES_USER=postgres, POSTGRES_PASSWORD=password, POSTGRES_DB=flexible_graphrag_age
        # Graph name set by age-init/02-init-graph.sql: knowledge_graph
        "APACHE_AGE_GRAPH_DB_CONFIG": '{"host": "localhost", "port": 5434, "database": "flexible_graphrag_age", "username": "postgres", "password": "password", "graph_name": "knowledge_graph"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "hugegraph-langchain": {
        "PG_GRAPH_DB": "hugegraph",
        "GRAPH_BACKEND": "langchain",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        # HugeGraph default credentials: admin/password
        "HUGEGRAPH_GRAPH_DB_CONFIG": '{"host": "localhost", "port": 8082, "username": "admin", "password": "password", "database": "hugegraph"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "surrealdb-langchain": {
        "PG_GRAPH_DB": "surrealdb",
        "GRAPH_BACKEND": "langchain",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        # SurrealDB Docker: --user=root --pass=root; default namespace=test, db=flexible_graphrag
        "SURREALDB_GRAPH_DB_CONFIG": '{"url": "ws://localhost:8010/rpc", "namespace": "test", "database": "flexible_graphrag", "username": "root", "password": "root"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "gremlin-langchain": {
        "PG_GRAPH_DB": "cosmos_gremlin",
        "GRAPH_BACKEND": "langchain",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "COSMOS_GREMLIN_GRAPH_DB_CONFIG": '{"url": "ws://localhost:8182/gremlin", "username": "/dbs/graphrag/colls/graphrag", "password": ""}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },

    # ── RDF graph backends ───────────────────────────────────────────────────
    "fuseki-rdf": {
        "RDF_GRAPH_DB": "fuseki",
        "FUSEKI_URL": "http://localhost:3030",
        "FUSEKI_DATASET": "flexible-graphrag",
        "FUSEKI_USERNAME": "admin",
        "FUSEKI_PASSWORD": "admin",
        "INGESTION_STORAGE_MODE": "graph_and_vector",    },
    "oxigraph-rdf": {
        "RDF_GRAPH_DB": "oxigraph",
        "OXIGRAPH_URL": "http://localhost:7878",
        "INGESTION_STORAGE_MODE": "graph_and_vector",    },
    "graphdb-rdf": {
        "RDF_GRAPH_DB": "graphdb",
        "GRAPHDB_URL": "http://localhost:7200",
        "GRAPHDB_REPOSITORY": "flexible-graphrag",
        "GRAPHDB_USERNAME": "admin",
        "GRAPHDB_PASSWORD": "root",
        "INGESTION_STORAGE_MODE": "graph_and_vector",    },

    # ── Vector store backends (PG off; embeddings + chunks) ─────────────────
    "qdrant-vector": {
        "VECTOR_DB": "qdrant",
        "QDRANT_VECTOR_DB_CONFIG": '{"host": "localhost", "port": 6333, "collection_name": "hybrid_search_vector", "https": false}',
        "PG_GRAPH_DB": "none",
    },
    "elasticsearch-vector": {
        "VECTOR_DB": "elasticsearch",
        "ELASTICSEARCH_VECTOR_DB_CONFIG": '{"url": "http://localhost:9200", "index_name": "flexible_graphrag_vectors"}',
        "PG_GRAPH_DB": "none",
    },
    "postgres-vector": {
        "VECTOR_DB": "postgres",
        "POSTGRES_VECTOR_DB_CONFIG": '{"host": "localhost", "port": 5433, "username": "postgres", "password": "password", "database": "flexible_graphrag"}',
        "PG_GRAPH_DB": "none",
    },
    "chroma-vector": {
        "VECTOR_DB": "chroma",
        "CHROMA_VECTOR_DB_CONFIG": '{"host": "localhost", "port": 8001, "collection_name": "hybrid_search_vector"}',
        "PG_GRAPH_DB": "none",
    },
    "opensearch-vector": {
        "VECTOR_DB": "opensearch",
        "VECTOR_BACKEND": "llamaindex",
        "OPENSEARCH_VECTOR_DB_CONFIG": '{"url": "http://localhost:9201", "index_name": "flexible_graphrag_vectors"}',
        "PG_GRAPH_DB": "none",
    },
    "opensearch-vector-langchain": {
        "VECTOR_DB": "opensearch",
        "VECTOR_BACKEND": "langchain",
        "OPENSEARCH_VECTOR_DB_CONFIG": '{"url": "http://localhost:9201", "index_name": "flexible_graphrag_vectors"}',
        "PG_GRAPH_DB": "none",
    },
    "milvus-vector": {
        "VECTOR_DB": "milvus",
        "VECTOR_BACKEND": "langchain",
        "MILVUS_VECTOR_DB_CONFIG": '{"host": "localhost", "port": 19530, "collection_name": "hybrid_search_vector"}',
        "PG_GRAPH_DB": "none",
    },
    "weaviate-vector": {
        "VECTOR_DB": "weaviate",
        "VECTOR_BACKEND": "langchain",
        "WEAVIATE_VECTOR_DB_CONFIG": '{"url": "http://localhost:8081", "grpc_port": 50051, "index_name": "HybridSearch", "text_key": "content"}',
        "PG_GRAPH_DB": "none",
    },
    "lancedb-vector": {
        "VECTOR_DB": "lancedb",
        "VECTOR_BACKEND": "langchain",
        "LANCEDB_VECTOR_DB_CONFIG": '{"uri": "./lancedb_integration_test", "table_name": "hybrid_search_vector"}',
        "PG_GRAPH_DB": "none",
    },

    # ── Search backends ──────────────────────────────────────────────────────
    "elasticsearch-search": {
        "SEARCH_DB": "elasticsearch",
        "ELASTICSEARCH_SEARCH_DB_CONFIG": '{"url": "http://localhost:9200", "index_name": "flexible_graphrag_search"}',
        "SEARCH_BACKEND": "llamaindex",
    },
    "elasticsearch-search-langchain": {
        "SEARCH_DB": "elasticsearch",
        "ELASTICSEARCH_SEARCH_DB_CONFIG": '{"url": "http://localhost:9200", "index_name": "flexible_graphrag_search"}',
        "SEARCH_BACKEND": "langchain",
    },
    "opensearch-search": {
        "SEARCH_DB": "opensearch",
        "OPENSEARCH_SEARCH_DB_CONFIG": '{"url": "http://localhost:9201", "index_name": "flexible_graphrag_search"}',
        "SEARCH_BACKEND": "llamaindex",
    },
    "opensearch-search-langchain": {
        "SEARCH_DB": "opensearch",
        "OPENSEARCH_SEARCH_DB_CONFIG": '{"url": "http://localhost:9201", "index_name": "flexible_graphrag_search"}',
        "SEARCH_BACKEND": "langchain",
    },
    "bm25-llamaindex": {
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
        "BM25_PERSIST_DIR": "./test_bm25_persist",
    },
    "bm25-langchain": {
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "langchain",
        "BM25_PERSIST_DIR": "./test_bm25_persist",
    },

    # ── Mixed pipelines (PG + RDF simultaneously) ───────────────────────────
    # LlamaIndex PG + Fuseki RDF  (original combo)
    "neo4j-fuseki-both": {
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "llamaindex",
        "RDF_GRAPH_DB": "fuseki",
        "INGESTION_STORAGE_MODE": "both",        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "FUSEKI_URL": "http://localhost:3030",
        "FUSEKI_DATASET": "flexible-graphrag",
        "FUSEKI_USERNAME": "admin",
        "FUSEKI_PASSWORD": "admin",
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    # LangChain PG + Fuseki RDF, EnsembleRetriever fusion
    "neo4j-fuseki-langchain": {
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "langchain",
        "USE_LANGCHAIN_PG": "true",
        "RDF_GRAPH_DB": "fuseki",
        "INGESTION_STORAGE_MODE": "both",        "RETRIEVAL_FUSION": "langchain",
        "LANGCHAIN_PG_INTERMEDIATE_STEPS": "true",
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "FUSEKI_URL": "http://localhost:3030",
        "FUSEKI_DATASET": "flexible-graphrag",
        "FUSEKI_USERNAME": "admin",
        "FUSEKI_PASSWORD": "admin",
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    # LangChain PG + GraphDB RDF
    "neo4j-graphdb-langchain": {
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "langchain",
        "USE_LANGCHAIN_PG": "true",
        "RDF_GRAPH_DB": "graphdb",
        "INGESTION_STORAGE_MODE": "both",        "RETRIEVAL_FUSION": "langchain",
        "LANGCHAIN_PG_INTERMEDIATE_STEPS": "true",
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "GRAPHDB_URL": "http://localhost:7200",
        "GRAPHDB_REPOSITORY": "flexible-graphrag",
        "GRAPHDB_USERNAME": "admin",
        "GRAPHDB_PASSWORD": "root",
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    # LangChain PG + Oxigraph RDF
    "neo4j-oxigraph-langchain": {
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "langchain",
        "USE_LANGCHAIN_PG": "true",
        "RDF_GRAPH_DB": "oxigraph",
        "INGESTION_STORAGE_MODE": "both",        "RETRIEVAL_FUSION": "langchain",
        "LANGCHAIN_PG_INTERMEDIATE_STEPS": "true",
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "OXIGRAPH_URL": "http://localhost:7878",
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },

    # ── Retrieval fusion variants (neo4j-langchain base, different fusion settings) ──
    "neo4j-langchain-llamaindex-fusion": {
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "langchain",
        "USE_LANGCHAIN_PG": "true",
        "USE_ONTOLOGY": "true",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "RETRIEVAL_FUSION": "llamaindex",     # QueryFusionRetriever (default)
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    "neo4j-langchain-lc-fusion": {
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "langchain",
        "USE_LANGCHAIN_PG": "true",
        "USE_ONTOLOGY": "true",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "RETRIEVAL_FUSION": "langchain",      # EnsembleRetriever (RRF)
        "LANGCHAIN_PG_INTERMEDIATE_STEPS": "true",
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },

    # ── Minimal BM25 CI smoke (no PG, no vector DB — BM25 + docstore; not "vector-only") ─
    "minimal-bm25": {
        "PG_GRAPH_DB": "none",
        "VECTOR_DB": "none",
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
        "USE_ONTOLOGY": "false",
        "LLM_PROVIDER": "openai",
        # Omit INGESTION_STORAGE_MODE: docs use property_graph | rdf_only | both — not "vector_only".
    },

    # ── Full LC post-reader pipeline (CHUNKER_BACKEND=langchain) ─────────────
    # Vector store only — fastest LC-pipe smoke test (no graph, no search)
    "qdrant-lc-pipe": {
        "CHUNKER_BACKEND": "langchain",
        "LC_SPLITTER_TYPE": "recursive",
        "VECTOR_DB": "qdrant",
        "QDRANT_VECTOR_DB_CONFIG": '{"host": "localhost", "port": 6333, "collection_name": "lc_pipe_test", "https": false}',
        "PG_GRAPH_DB": "none",
    },
    # LC chunker + Neo4j (LC) + Qdrant + LC fusion — the flagship full-LC profile
    "neo4j-langchain-lc-pipe": {
        "CHUNKER_BACKEND": "langchain",
        "LC_SPLITTER_TYPE": "recursive",
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "langchain",
        "USE_LANGCHAIN_PG": "true",
        "USE_ONTOLOGY": "true",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "RETRIEVAL_FUSION": "langchain",
        "LANGCHAIN_PG_INTERMEDIATE_STEPS": "true",
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "llamaindex",
    },
    # LC chunker + LlamaIndex Neo4j (for testing LC-split -> LI-embed fallback)
    "neo4j-llamaindex-lc-pipe": {
        "CHUNKER_BACKEND": "langchain",
        "LC_SPLITTER_TYPE": "recursive",
        "PG_GRAPH_DB": "neo4j",
        "GRAPH_BACKEND": "llamaindex",
        "USE_ONTOLOGY": "true",
        "INGESTION_STORAGE_MODE": "graph_and_vector",
        "NEO4J_GRAPH_DB_CONFIG": '{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}',
    },
    # LC chunker with character splitter — splitter-type matrix variant
    "qdrant-lc-pipe-character": {
        "CHUNKER_BACKEND": "langchain",
        "LC_SPLITTER_TYPE": "character",
        "VECTOR_DB": "qdrant",
        "QDRANT_VECTOR_DB_CONFIG": '{"host": "localhost", "port": 6333, "collection_name": "lc_pipe_char", "https": false}',
        "PG_GRAPH_DB": "none",
    },
    # LC chunker with token splitter (tiktoken-based)
    "qdrant-lc-pipe-token": {
        "CHUNKER_BACKEND": "langchain",
        "LC_SPLITTER_TYPE": "token",
        "VECTOR_DB": "qdrant",
        "QDRANT_VECTOR_DB_CONFIG": '{"host": "localhost", "port": 6333, "collection_name": "lc_pipe_token", "https": false}',
        "PG_GRAPH_DB": "none",
    },
    # LC chunker with markdown splitter — useful for .md doc ingestion
    "qdrant-lc-pipe-markdown": {
        "CHUNKER_BACKEND": "langchain",
        "LC_SPLITTER_TYPE": "markdown",
        "VECTOR_DB": "qdrant",
        "QDRANT_VECTOR_DB_CONFIG": '{"host": "localhost", "port": 6333, "collection_name": "lc_pipe_md", "https": false}',
        "PG_GRAPH_DB": "none",
    },
    # LC chunker + Elasticsearch (LC) — tests LC search fast path
    "elasticsearch-lc-pipe": {
        "CHUNKER_BACKEND": "langchain",
        "LC_SPLITTER_TYPE": "recursive",
        "VECTOR_DB": "elasticsearch",
        "ELASTICSEARCH_VECTOR_DB_CONFIG": '{"url": "http://localhost:9200", "index_name": "lc_pipe_vectors"}',
        "SEARCH_DB": "elasticsearch",
        "SEARCH_BACKEND": "langchain",
        "ELASTICSEARCH_SEARCH_DB_CONFIG": '{"url": "http://localhost:9200", "index_name": "lc_pipe_search"}',
        "PG_GRAPH_DB": "none",
    },
    # Minimal LC-pipe smoke — BM25 only (no vector DB, no graph)
    "minimal-lc-pipe-bm25": {
        "CHUNKER_BACKEND": "langchain",
        "LC_SPLITTER_TYPE": "recursive",
        "PG_GRAPH_DB": "none",
        "VECTOR_DB": "none",
        "SEARCH_DB": "bm25",
        "SEARCH_BACKEND": "langchain",
        "USE_ONTOLOGY": "false",
    },
}

# Applied before profile-specific overrides (profile values win).
# Keeps integration runs fast: no incremental Postgres/monitoring in lifespan unless a profile sets true.
INTEGRATION_DEFAULT_OVERRIDES: dict[str, str] = {
    "ENABLE_INCREMENTAL_UPDATES": "false",
}

# Same as neo4j-llamaindex but re-enables incremental updates for tests/integration/test_incremental.py.
PROFILES["neo4j-llamaindex-incremental"] = {
    **PROFILES["neo4j-llamaindex"],
    "ENABLE_INCREMENTAL_UPDATES": "true",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def list_profiles() -> list[str]:
    return sorted(PROFILES.keys())


def build_env_file(
    profile_name: str,
    base_env: str | Path | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """
    Merge profile overrides on top of a base .env file and write the result
    to output_path (defaults to a temp file under /tmp or %TEMP%).

    Returns the path to the written file.
    """
    import tempfile

    overrides = {**INTEGRATION_DEFAULT_OVERRIDES, **PROFILES[profile_name]}

    lines: list[str] = []

    # Read base env if provided
    if base_env:
        base_path = Path(base_env)
        if base_path.exists():
            with base_path.open(encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        lines.append(line.rstrip())
                        continue
                    key = stripped.split("=", 1)[0].strip()
                    if key in overrides:
                        # replaced below
                        lines.append(f"# (overridden by profile '{profile_name}') {line.rstrip()}")
                    else:
                        lines.append(line.rstrip())

    # Append overrides section
    lines.append("")
    lines.append(f"# ── Profile: {profile_name} ──")
    for k, v in overrides.items():
        lines.append(f"{k}={v}")

    content = "\n".join(lines) + "\n"

    if output_path is None:
        fd, tmp = tempfile.mkstemp(prefix=f"fgrag-{profile_name}-", suffix=".env")
        os.close(fd)
        output_path = tmp

    Path(output_path).write_text(content, encoding="utf-8")
    return Path(output_path)


def load_env_dict(env_file: str | Path) -> dict[str, str]:
    """Parse a .env file into a dict (inline comments and quoting match python-dotenv)."""
    raw = dotenv_values(env_file)
    return {k: v for k, v in raw.items() if v is not None}
