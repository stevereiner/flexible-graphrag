# Testing & Cleanup

Between tests you can clean up data using the cleanup script or per-database commands.

---

## cleanup.py — Complete Reference

> **WARNING: All cleanup operations are irreversible. Data cannot be recovered once deleted.**
> Run cleanup only when you intend to re-ingest from scratch or switch to a different database backend.

The `cleanup.py` script lives in `scripts/` and is run from the `flexible-graphrag/` directory:

```bash
cd flexible-graphrag
python ../scripts/cleanup.py [flags]
```

**Stop the backend first, and start it again after cleanup** (the same for the backend container in Docker:
`docker compose ... stop flexible-graphrag-backend`, then `start`). The backend sets up the graph stores' indexes when
it starts, e.g. Neo4j's `entity` vector index, and cleanup drops them: run under a running backend, searches then fail
until it restarts (`There is no such vector schema index: entity`).

### Full cleanup (all stores)

```bash
python ../scripts/cleanup.py
```

Prompts for confirmation then wipes **everything**: PostgreSQL incremental tables and CocoIndex monitoring tables (`cocoindex_ingest_log`, `cocoindex_run_log`), vector store, search store, property graph store, RDF stores, what was put into OpenArch (when `ENABLE_OPENARCH` or `INCREMENTAL_STATE_STORE=openarch` is set), CocoIndex LMDB state, and log files.

To skip the prompt:

```bash
python ../scripts/cleanup.py --yes
```

> **Use with care.** Full cleanup deletes all ingested documents, embeddings, graph nodes,
> relationships, and incremental-update state. You must re-ingest all documents afterward.

### Selective cleanup (one or more stores)

Selective flags skip the confirmation prompt and touch only the specified store(s):

| Flag | What is deleted |
|------|----------------|
| `--graph` | Property graph store only (Neo4j / SurrealDB / ArcadeDB / etc.) |
| `--vector` | Vector store only (Qdrant / LanceDB / Milvus / etc.) |
| `--search` | Search store only (Elasticsearch / OpenSearch / BM25) |
| `--rdf` | RDF triple stores only (Fuseki / GraphDB / Oxigraph) |
| `--openarch` | What was put into OpenArch only: the documents under `OPENARCH_ROOT_PATH` (`ENABLE_OPENARCH`), and with `INCREMENTAL_STATE_STORE=openarch` the data sources and their document state |
| `--postgres` | PostgreSQL incremental-update tables (`document_state`, `datasource_config`) and CocoIndex monitoring tables (`cocoindex_ingest_log`, `cocoindex_run_log`) |
| `--cocoindex` | CocoIndex LMDB pipeline state + source staging directory only |
| `--logs` | Log files (`*.log`) in `flexible-graphrag/` only |

Flags can be combined freely:

```bash
# Re-ingest graph only — keep vector embeddings
python ../scripts/cleanup.py --graph

# Re-ingest everything except incremental state
python ../scripts/cleanup.py --graph --vector --search --rdf --cocoindex --logs

# Switch graph backend (wipe graph + CocoIndex state, keep embeddings)
python ../scripts/cleanup.py --graph --cocoindex

# Wipe vector + graph for a full re-ingest (keep postgres incremental state)
python ../scripts/cleanup.py --graph --vector
```

### Automated / CI mode

```bash
python ../scripts/cleanup.py --matrix-clean
```

Non-interactive mode for the integration test matrix runner. Cleans vector, search, graph, RDF,
OpenArch (when set up, as `--openarch`) and CocoIndex stores without prompting. If
`ENABLE_INCREMENTAL_UPDATES=true` is set in the environment, also clears the PostgreSQL
incremental tables.

### Integration tests

The live integration tests are described in
[tests/integration/README.md](https://github.com/stevereiner/flexible-graphrag/blob/main/tests/integration/README.md):
store profiles (`run_profile.py`, `run_all_profiles.py`), store combinations (`run_matrix.py`;
`--state-store openarch` runs them with the incremental registry in OpenArch, under its own
`/fg-matrix-sources` and `/fg-matrix-datasources` roots), scoped Ask (`run_matrix.py --scope`),
and, new in v0.9.0, the auto-sync matrix
([tests/integration/autosync/README.md](https://github.com/stevereiner/flexible-graphrag/blob/main/tests/integration/autosync/README.md)):
live auto-sync checks per data source on the OpenArch state store (multiselect, recursive, add /
edit / delete / move / rename, Auto Sync off rows, periodic refresh, graph removal), run with
`tests/integration/autosync/run_autosync.py`. The vector, search and graph stores they use are
those in `.env`, so run `cleanup.py` afterwards.

### Common workflows

| Scenario | Command |
|----------|---------|
| Switching graph database backend | `--graph --cocoindex` |
| Switching embedding model (dimension change) | `--vector` |
| Re-ingesting a single store after a bug fix | `--graph` or `--vector` |
| Full reset before a demo | `--yes` (full cleanup) |
| Clearing stuck CocoIndex pipeline state | `--cocoindex` |
| Resetting incremental sync state | `--postgres` |

---

## Vector Database Cleanup

When switching embedding models, you must delete existing vector indexes due to dimension incompatibility. See [Vector Dimensions](../DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md) for per-database cleanup instructions.

---

## Graph Database Cleanup

For SurrealDB-specific queries and cleanup, see [SurrealDB Guide](../DATABASES/GRAPH-DATABASES/SURREALDB-GUIDE.md).
For Neo4j-specific commands, see [Neo4j Setup](../DATABASES/GRAPH-DATABASES/README-neo4j.md).

### ArcadeDB Cleanup

The `cleanup.py` script includes ArcadeDB-specific handling — it directly connects via `arcadedb_python`, queries schema types, and issues `DELETE FROM <type>` statements (avoiding index-already-exists errors from the LlamaIndex factory).

---

## RDF Store Cleanup

Use `scripts/rdf_cleanup.py` to manage RDF store data:

```bash
# List ingested documents and triple counts
python scripts/rdf_cleanup.py list-docs

# Show total triple count in named graph
python scripts/rdf_cleanup.py count

# Delete all triples for a specific document
python scripts/rdf_cleanup.py clear-doc <ref_doc_id>

# Wipe entire named graph (with confirmation)
python scripts/rdf_cleanup.py clear-all --yes

# Target a specific store
python scripts/rdf_cleanup.py list-docs --fuseki
python scripts/rdf_cleanup.py list-docs --graphdb
python scripts/rdf_cleanup.py list-docs --oxigraph
```

---

## BM25 Index Cleanup

The BM25 index is file-based. Delete the directory configured in `SEARCH_DB_CONFIG`:

```bash
# Default location
rm -rf ./bm25_index
```

---

## Incremental State Cleanup

To reset incremental update state, you can clear the PostgreSQL tables directly:

```sql
-- Connect to flexible_graphrag_incremental database
TRUNCATE TABLE document_state;
TRUNCATE TABLE datasource_config;

-- CocoIndex monitoring tables (if CocoIndex integration is enabled)
TRUNCATE TABLE cocoindex_ingest_log;
TRUNCATE TABLE cocoindex_run_log;
```

Or use the cleanup script: `python ../scripts/cleanup.py --postgres`

Or use pgAdmin at http://localhost:5050 (no master password; server password: `password`).
