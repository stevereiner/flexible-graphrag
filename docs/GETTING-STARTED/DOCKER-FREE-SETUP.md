# Docker-Free Setup

A lighter configuration with no Docker and no database servers: every store is embedded in the backend
process and kept in files in the folder the backend runs in. It suits a laptop, a quick trial, or the
[Desktop App](DESKTOP-APP.md).

| Part | Docker-free choice | Setting |
| --- | --- | --- |
| Vector store | LanceDB, or Chroma in local file mode | `VECTOR_DB=lancedb` or `chroma` |
| Full-text search | BM25 (in-process index) | `SEARCH_DB=bm25` |
| Property graph | LadybugDB, or ArcadeDB embedded | `PG_GRAPH_DB=ladybug` or `arcadedb` |
| RDF store | none | `RDF_GRAPH_DB=none` |
| Auto-sync state store | SQLite | `INCREMENTAL_STATE_STORE=sqlite` |
| Document parser | Docling or LiteParse (local), or LlamaParse (cloud service, API key) | `DOCUMENT_PARSER=docling`, `liteparse` or `llamaparse` |
| LLM and embeddings | a cloud provider (API key), or Ollama installed locally | `LLM_PROVIDER`, `EMBEDDING_KIND` |

## `.env`

Start from `env-sample.txt` and change these lines (the per-store config lines are already in the sample):

```
VECTOR_DB=lancedb
SEARCH_DB=bm25
PG_GRAPH_DB=ladybug
RDF_GRAPH_DB=none

LANCEDB_VECTOR_DB_CONFIG={"uri": "./lancedb", "table_name": "hybrid_search", "vector_column_name": "vector", "text_column_name": "text"}
LADYBUG_GRAPH_DB_CONFIG={"db_dir": "./ladybug", "db_file": "database.lbug", "use_vector_index": false, "has_structured_schema": true, "strict_schema": false}
# keeps the BM25 index on disk across restarts
BM25_PERSIST_DIR=./bm25_index

# auto sync, with the state in a SQLite file instead of PostgreSQL
ENABLE_INCREMENTAL_UPDATES=true
INCREMENTAL_STATE_STORE=sqlite
SQLITE_INCREMENTAL_PATH=./flexible_graphrag_incremental.db
```

The alternatives:

```
# Chroma in local file mode (instead of LanceDB)
VECTOR_DB=chroma
CHROMA_VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}

# ArcadeDB embedded (instead of LadybugDB): first uv pip install "arcadedb-embedded>=26.3.2"
# (it brings its own JVM: no Java install needed)
PG_GRAPH_DB=arcadedb
ARCADEDB_GRAPH_DB_CONFIG={"mode": "embedded", "db_path": "./arcadedb_data", "database": "flexible_graphrag", "include_basic_schema": true}
```

ArcadeDB embedded runs inside the backend process, with the LlamaIndex graph backend (the default
`GRAPH_BACKEND=llamaindex`). Add `"embedded_server": true, "embedded_server_port": 2482,
"embedded_server_password": "..."` to also serve ArcadeDB's HTTP API on that port while the backend
runs.

Then set the LLM as usual, e.g. `LLM_PROVIDER=openai` with `OPENAI_API_KEY`, or `LLM_PROVIDER=ollama` and
`EMBEDDING_KIND=ollama` with Ollama running locally (see [Ollama Configuration](../LLM/OLLAMA-CONFIGURATION.md)).
Leave out `ENABLE_INCREMENTAL_UPDATES` if you don't need auto sync.

Any of the 3 document parsers works here. Docling (the default) and LiteParse run locally; LlamaParse is
LlamaIndex's cloud service, so it needs no Docker either: `DOCUMENT_PARSER=llamaparse` with
`LLAMA_CLOUD_API_KEY` (and optionally `LLAMAPARSE_MODE`).

Relative paths are relative to the folder the backend runs in (`flexible-graphrag/` in a checkout, or the
install folder for a PyPI install).

## Notes

- **One process at a time.** The embedded stores are files opened by the backend. Don't run a second
  backend, or a Langflow server running the flows' own code, on the same files at the same time.
- **SQLite** keeps the same tables as the PostgreSQL state store (data source configs and document state).
  See [Incremental Auto-Sync](../DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/README.md). The CocoIndex
  pipeline (`PIPELINE_BACKEND=cocoindex`) still needs PostgreSQL.
- **RDF:** Oxigraph also has an embedded mode (`RDF_GRAPH_DB=oxigraph` with `OXIGRAPH_STORE_PATH` instead of
  `OXIGRAPH_URL`), for a single process only.
- **Dashboards** such as the Ladybug Explorer are optional Docker services; the stores work without them.
- **Cleanup:** `scripts/cleanup.py` clears the LanceDB table or the local Chroma collection, the BM25 index,
  the LadybugDB graph and the SQLite state file (see
  [Testing & Cleanup](../DEVELOPER/DEVELOPER-TESTING-CLEANUP.md)). It clears ArcadeDB only as a server: for
  ArcadeDB embedded, delete its `db_path` folder (`./arcadedb_data`) with the backend stopped.

## Moving to servers later

Each part can be switched on its own, to a server run with its Docker service (see
[Docker Deployment](DOCKER-DEPLOYMENT.md)), for example:

- **Search:** OpenSearch or Elasticsearch (`SEARCH_DB=opensearch` or `elasticsearch`), which can also be the
  vector store (`VECTOR_DB=opensearch` or `elasticsearch`);
- **Vector store:** e.g. Qdrant (`VECTOR_DB=qdrant`), or Chroma in HTTP client mode;
- **Property graph:** Neo4j (`PG_GRAPH_DB=neo4j`), ArcadeDB as a server (`PG_GRAPH_DB=arcadedb` with the
  remote `ARCADEDB_GRAPH_DB_CONFIG`, `host` and `port`), or FalkorDB (`PG_GRAPH_DB=falkordb`);
- **Auto-sync state store:** PostgreSQL (the default), or OpenArch (`INCREMENTAL_STATE_STORE=openarch`).

Switching a store doesn't copy what is in the old one; ingest again.
