# REST API

The FastAPI backend exposes a REST API for all document ingestion, search, and AI query operations.

**Base URL**: `http://localhost:8000/api/`

## Interactive API Documentation

- **Swagger UI**: http://localhost:8000/docs — try endpoints directly in the browser
- **ReDoc**: http://localhost:8000/redoc — clean reference documentation

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
| `/api/ingest` | POST | Ingest documents from a configured data source |
| `/api/upload` | POST | Upload files directly for processing |
| `/api/ingest-text` | POST | Ingest custom text content |
| `/api/test-sample` | POST | Test the system with built-in sample content |

### Async Processing

| Endpoint | Method | Description |
|---|---|---|
| `/api/processing-status/{id}` | GET | Check status of an async ingestion operation |
| `/api/processing-events/{id}` | GET | Server-Sent Events stream for real-time progress |
| `/api/cancel-processing/{id}` | POST | Cancel an ongoing processing operation |
| `/api/cleanup-uploads` | POST | Clean up temporarily uploaded files |

### Search & Query

| Endpoint | Method | Description |
|---|---|---|
| `/api/search` | POST | Hybrid search — returns ranked document excerpts |
| `/api/query` | POST | AI-powered Q&A — generates an answer from documents |

### Graph

| Endpoint | Method | Description |
|---|---|---|
| `/api/graph` | GET | Graph data for visualization (nodes and relationships) |

---

## Example Requests

### Health Check

```bash
curl http://localhost:8000/api/health
```

### Ingest a File Upload

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "files=@/path/to/document.pdf"
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

### Ingest Text Directly

```bash
curl -X POST http://localhost:8000/api/ingest-text \
  -H "Content-Type: application/json" \
  -d '{"content": "Acme Corp was founded in 2010 by John Smith.", "source_name": "company-info"}'
```

### Poll Processing Status

```bash
# Get the task ID from an async ingest response, then poll:
curl http://localhost:8000/api/processing-status/{task_id}

# Or stream real-time events:
curl -N http://localhost:8000/api/processing-events/{task_id}
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
- [MCP Server](../MCP/MCP-SERVER.md) — higher-level tools built on top of these endpoints
- [Swagger UI](http://localhost:8000/docs) — interactive documentation (requires running backend)
