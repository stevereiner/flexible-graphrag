# REST API

The FastAPI backend exposes a REST API for all document ingestion, search, and AI query operations.

**Base URL**: `http://localhost:8000/api/`

## Interactive API Documentation

Both UIs are served by the running backend and let you try every endpoint directly in the browser.

| UI | URL | Notes |
|---|---|---|
| **Swagger UI** | http://localhost:8000/docs | Try endpoints, inspect schemas, submit requests |
| **ReDoc** | http://localhost:8000/redoc | Cleaner read-only reference view |

---

## Endpoints

### System

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check — verify backend is running |
| `/api/status` | GET | System status and configuration (databases, LLM, feature flags) |
| `/api/info` | GET | System information and package versions |
| `/api/python-info` | GET | Python environment diagnostics |

### Ingestion

| Endpoint | Method | Description |
|---|---|---|
| `/api/ingest` | POST | Ingest documents from a configured data source (`filesystem`, `s3`, `web`, `cmis`, `alfresco`, ...) |
| `/api/upload` | POST | Upload files directly for processing |
| `/api/ingest-text` | POST | Ingest raw text content |
| `/api/test-sample` | POST | Test the system with built-in sample content |
| `/api/cleanup-uploads` | POST | Remove temporarily uploaded files |

All three text ingestion endpoints (`/api/ingest`, `/api/ingest-text`, `/api/test-sample`) accept a `skip_graph` boolean to skip KG extraction and all graph writes for that document — vector and full-text stores are still updated.

### Async Processing

| Endpoint | Method | Description |
|---|---|---|
| `/api/processing-status/{id}` | GET | Poll status of an async ingestion operation |
| `/api/processing-events/{id}` | GET | Server-Sent Events stream for real-time progress |
| `/api/cancel-processing/{id}` | POST | Cancel an ongoing processing operation |

### Search & Query

| Endpoint | Method | Description |
|---|---|---|
| `/api/search` | POST | Hybrid search — returns ranked document excerpts from all configured stores |
| `/api/query` | POST | AI-powered Q&A — generates an answer from the document corpus |

### Graph

| Endpoint | Method | Description |
|---|---|---|
| `/api/graph` | GET | Graph database status and node/relationship counts. Returns live counts where supported (Neo4j full counts via Cypher; other LC-backed stores via `lc_graph.query()` when the store exposes a count query; remaining stores return status and dashboard URL) |
| `/api/graph/query` | POST | Execute a native graph query against the configured store |

`POST /api/graph/query` routes to the appropriate query language automatically based on the configured graph backend:

| Store | Language |
|---|---|
| Neo4j, Memgraph, FalkorDB, ArcadeDB, Ladybug, Apache AGE | Cypher |
| ArangoDB | AQL |
| SurrealDB | SurrealQL |
| Azure Cosmos DB for Gremlin | Gremlin |
| TigerGraph | GSQL |
| Neptune / Neptune Analytics | openCypher |
| Google Spanner | GQL |
| RDF-only (`PG_GRAPH_DB=none`) | SPARQL fallback |

Request body:

```json
{
  "query": "MATCH (p:Person)-[:WORKS_FOR]->(c:Company) RETURN p.name, c.name LIMIT 10",
  "language": "cypher",
  "params": {}
}
```

The `language` field is optional — the backend infers it from the configured store when omitted.

### RDF / Ontology

These endpoints are active when `RDF_GRAPH_DB` is set to `fuseki`, `graphdb`, `oxigraph`, or `neptune_rdf`.

| Endpoint | Method | Description |
|---|---|---|
| `/api/rdf/query/sparql` | POST | Execute a SPARQL SELECT query against the configured RDF store |
| `/api/rdf/ontology/info` | GET | Return loaded ontology entity and relation type lists |
| `/api/rdf/ontology/upload` | POST | Upload a new ontology file at runtime |
| `/api/rdf/rdf-store/list` | GET | List all registered RDF stores |
| `/api/rdf/rdf-store/connect` | POST | Register an additional RDF store at runtime |
| `/api/rdf/rdf-store/{name}` | DELETE | Deregister an RDF store |
| `/api/rdf/export/rdf` | POST | Export knowledge graph as RDF *(501 stub — not yet implemented; use direct HTTP export to the store instead)* |

---

## Example Requests

### Health Check

```bash
curl http://localhost:8000/api/health
```

### Ingest from Filesystem (folder)

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "filesystem",
    "config": {"path": "/path/to/docs"},
    "skip_graph": false
  }'
```

### Upload a File

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "files=@/path/to/document.pdf"
```

### Ingest Text Directly

```bash
curl -X POST http://localhost:8000/api/ingest-text \
  -H "Content-Type: application/json" \
  -d '{"content": "Acme Corp was founded in 2010 by John Smith.", "source_name": "company-info"}'
```

### Hybrid Search

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "knowledge graph extraction", "top_k": 5}'
```

### AI Q&A Query

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the main topics in the documents?", "top_k": 10}'
```

### Poll Processing Status

```bash
# Get the task ID from an async ingest response, then poll:
curl http://localhost:8000/api/processing-status/{task_id}

# Or stream real-time events:
curl -N http://localhost:8000/api/processing-events/{task_id}
```

### Native Graph Query (Cypher — Neo4j)

```bash
curl -X POST http://localhost:8000/api/graph/query \
  -H "Content-Type: application/json" \
  -d '{"query": "MATCH (p:Person)-[:WORKS_FOR]->(c:Company) RETURN p.name, c.name LIMIT 10"}'
```

### Native Graph Query (AQL — ArangoDB)

```bash
curl -X POST http://localhost:8000/api/graph/query \
  -H "Content-Type: application/json" \
  -d '{"query": "FOR v IN Person FILTER LOWER(v.name) CONTAINS \"acme\" RETURN v.name", "language": "aql"}'
```

### SPARQL Query (RDF store)

```bash
curl -X POST http://localhost:8000/api/rdf/query/sparql \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10"}'
```

---

## Async Ingestion Flow

Long-running ingestion operations (large files, many documents) return a `task_id` immediately:

```
POST /api/ingest  →  { "task_id": "abc123", "status": "processing" }
GET /api/processing-status/abc123  →  { "status": "running", "progress": 42 }
GET /api/processing-events/abc123  →  SSE stream with real-time progress updates
POST /api/cancel-processing/abc123  →  cancel if needed
```

---

## See Also

- [Architecture](../ADVANCED/ARCHITECTURE.md) — detailed API workflow and data flow diagrams
- [MCP Server](../MCP/MCP-TOOLS.md) — higher-level tools built on top of these endpoints
- [RDF Store User Guide](../DATABASES/RDF/RDF-STORE-USER-GUIDE.md) — RDF/SPARQL endpoint details
