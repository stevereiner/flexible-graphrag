# Testing & Cleanup

Between tests you can clean up data using the cleanup script or per-database commands.

---

## cleanup.py — One-Step Cleanup

The `cleanup.py` script clears vector, graph, and search indexes in a single command. Run it from the `flexible-graphrag` directory:

```bash
cd flexible-graphrag
python cleanup.py
```

This will clear all configured databases (vector, property graph, search) in one step.

---

## Vector Database Cleanup

When switching embedding models, you must delete existing vector indexes due to dimension incompatibility. See [Vector Dimensions](../DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md) for per-database cleanup instructions.

---

## Graph Database Cleanup

For graph-related cleanup commands, see [Neo4j Setup](../DATABASES/GRAPH-DATABASES/README-neo4j.md).

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

To reset incremental update state, you can clear the PostgreSQL `document_state` table:

```sql
-- Connect to flexible_graphrag_incremental database
TRUNCATE TABLE document_state;
TRUNCATE TABLE datasource_config;
```

Or use pgAdmin at http://localhost:5050 (master password: `admin`, server password: `password`).
