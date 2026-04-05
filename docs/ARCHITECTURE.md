# Flexible GraphRAG System Architecture

**Last Updated**: November 17, 2025

## Table of Contents
1. [System Overview](#system-overview)
2. [Backend Architecture](#backend-architecture)
3. [MCP Server Architecture](#mcp-server-architecture)
4. [Document Processing Pipeline](#document-processing-pipeline)
5. [Database Layer](#database-layer)
6. [Frontend Clients](#frontend-clients)
7. [Deployment Configurations](#deployment-configurations)

---

## System Overview

Flexible GraphRAG is a multi-layered document intelligence platform that supports:
- **13 data sources**: File upload, cloud storage (S3, GCS, Azure Blob, OneDrive, SharePoint, Box, Google Drive), repositories (CMIS, Alfresco), and web sources (Web pages, Wikipedia, YouTube)
- **Hybrid search**: Vector similarity, full-text search (BM25/Elasticsearch/OpenSearch), and graph traversal (GraphRAG)
- **Multiple interfaces**: REST API, MCP protocol for AI assistants, and web UIs (Angular, React, Vue)
- **Flexible databases**: 10 vector stores, 9 graph databases, 3 search engines

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     FLEXIBLE GRAPHRAG SYSTEM                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                    │
│  │   Angular    │  │    React     │  │     Vue      │                    │
│  │   Frontend   │  │   Frontend   │  │   Frontend   │                    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                    │
│         │                  │                  │                          │
│         └──────────────────┼──────────────────┘                          │
│                            │                                             │
│                   ┌────────▼──────────┐                                  │
│                   │                   │                                  │
│                   │  FastAPI Backend  │◄──── REST API (port 8000)        │
│                   │   (main.py)       │                                  │
│                   └────────┬──────────┘                                  │
│                            │                                             │
│  ┌──────────────────────────────────────────────────────┐                │
│  │       MCP Server (flexible-graphrag-mcp/)            │                │
│  │  ┌────────────────────────────────────────────────┐  │                │
│  │  │  main.py (HTTP mode) ◄──── MCP Protocol        │  │                │
│  │  │  - Calls backend via HTTP REST API             │  │                │
│  │  │  - Lightweight (4 dependencies)                │  │                │
│  │  │  - Works with Claude Desktop & MCP Inspector   │  │                │
│  │  └────────────────────────────────────────────────┘  │                │
│  └──────────────────────────────────────────────────────┘                │ 
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Backend Architecture

The backend consists of four key files that work together:

### Core Files Relationship

```
┌────────────────────────────────────────────────────────────────────────┐
│                      BACKEND LAYER                                     │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  start.py                                                              │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │ • Startup script                                         │          │
│  │ • Runs: uvicorn main:app --host 0.0.0.0 --port 8000      │          │
│  │ • Parameters: --loop asyncio (for nest_asyncio)          │          │
│  └───────────────────┬──────────────────────────────────────┘          │
│                      │                                                 │
│                      ▼                                                 │
│  main.py (FastAPI Application)                                         │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │ • REST API endpoints (/api/*)                            │          │
│  │ • Request validation (Pydantic models)                   │          │
│  │ • File upload handling                                   │          │
│  │ • Delegates to backend.py for business logic             │          │
│  └───────────────────┬──────────────────────────────────────┘          │
│                      │                                                 │
│                      ▼                                                 │
│  backend.py (Business Logic Core)                                      │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │ • FlexibleGraphRAGBackend class                          │          │
│  │ • Processing status management                           │          │
│  │ • Progress tracking & callbacks                          │          │
│  │ • Per-file progress simulation                           │          │
│  │ • Async document processing orchestration                │          │
│  │ • Used by BOTH FastAPI and MCP servers                   │          │
│  └───────────────────┬──────────────────────────────────────┘          │
│                      │                                                 │
│                      ▼                                                 │
│  hybrid_system.py (RAG Engine)                                         │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │ • HybridSearchSystem class                               │          │
│  │ • Document ingestion pipeline                            │          │
│  │ • Vector index creation (VectorStoreIndex)               │          │
│  │ • Knowledge graph extraction (PropertyGraphIndex)        │          │
│  │ • Hybrid retriever (vector + BM25 + graph)               │          │
│  │ • Query engine for Q&A                                   │          │
│  │ • Calls document_processor.py for parsing                │          │
│  └──────────────────────────────────────────────────────────┘          │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Relationships

1. **start.py** → **main.py**
   - Simple launcher that runs uvicorn with proper async loop settings
   - Command: `uv run start.py` or `uv run uvicorn main:app --host 0.0.0.0 --port 8000 --loop asyncio`

2. **main.py** → **backend.py**
   - FastAPI defines REST API endpoints
   - Delegates business logic to `FlexibleGraphRAGBackend` class
   - Handles HTTP request/response formatting
   - Manages file uploads and multipart data

3. **backend.py** → **hybrid_system.py**
   - Backend orchestrates the workflow
   - Manages progress tracking and status updates
   - Calls `HybridSearchSystem` for actual RAG operations
   - Handles async processing and cancellation

4. **hybrid_system.py** → **document_processor.py**
   - Core RAG engine that processes documents
   - Calls DocumentProcessor for parsing (Docling/LlamaParse)
   - Creates indexes and retrievers
   - Performs searches and Q&A queries

---

## MCP Server Architecture

### Current Implementation: HTTP Mode

**Production Status**: Active since August 9, 2025

The MCP server uses an **HTTP client pattern** to communicate with the backend, providing clean separation and minimal dependencies.

**Architecture Overview**:
- **Dependencies**: Only 4 packages (fastmcp, nest-asyncio, httpx, python-dotenv)
- **Communication**: HTTP REST API calls to backend
- **Deployment**: Independent from backend (separate venv)
- **Protocols**: Supports both stdio (Claude Desktop) and HTTP (MCP Inspector)

### MCP Server Dual Protocol

```
┌───────────────────────────────────────────────────────────┐
│              MCP SERVER (flexible-graphrag-mcp/)          │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  main.py (HTTP Mode MCP Server) - PRODUCTION              │
│  ┌───────────────────────────────────────────────────┐    │
│  │                                                   │    │
│  │  ┌──────────────────────────────────────────┐     │    │
│  │  │  stdio Mode (Default)                    │     │    │
│  │  │  - Claude Desktop uses this              │     │    │
│  │  │  - Command: flexible-graphrag-mcp        │     │    │
│  │  │  - Protocol: MCP over stdio              │     │    │
│  │  └────────────┬─────────────────────────────┘     │    │
│  │               │                                   │    │
│  │               │ MCP Protocol                      │    │
│  │               ▼                                   │    │
│  │  ┌──────────────────────────────────────────┐     │    │
│  │  │  9 MCP Tools:                            │     │    │
│  │  │  • get_system_status()                   │     │    │
│  │  │  • ingest_documents()                    │     │    │
│  │  │  • ingest_text()                         │     │    │
│  │  │  • search_documents()                    │     │    │
│  │  │  • query_documents()                     │     │    │
│  │  │  • test_with_sample()                    │     │    │
│  │  │  • check_processing_status()             │     │    │
│  │  │  • get_python_info()                     │     │    │
│  │  │  • health_check()                        │     │    │
│  │  └────────────┬─────────────────────────────┘     │    │
│  │               │                                   │    │
│  │               │ HTTP REST API                     │    │
│  │               ▼                                   │    │
│  │  ┌──────────────────────────────────────────┐     │    │
│  │  │  httpx.AsyncClient                       │     │    │
│  │  │  - Calls http://localhost:8000/api/*     │     │    │
│  │  │  - POST /api/ingest                      │     │    │
│  │  │  - POST /api/search                      │     │    │
│  │  │  - POST /api/query                       │     │    │
│  │  │  - GET /api/status                       │     │    │
│  │  └──────────────────────────────────────────┘     │    │
│  │                                                   │    │
│  │  ┌──────────────────────────────────────────┐     │    │
│  │  │  HTTP Mode (Optional - for debugging)    │     │    │
│  │  │  - MCP Inspector uses this               │     │    │
│  │  │  - Command: flexible-graphrag-mcp --http │     │    │
│  │  │  - Port: 3001 (default)                  │     │    │
│  │  │  - Protocol: MCP over HTTP               │     │    │
│  │  └──────────────────────────────────────────┘     │    │
│  └───────────────────────────────────────────────────┘    │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### Installation & Configuration

**pyproject.toml defines minimal dependencies**:
```toml
[project]
name = "flexible-graphrag-mcp"
version = "1.0.0"
dependencies = [
    "fastmcp",      # MCP protocol
    "nest-asyncio",  # Event loop patching
    "httpx",        # HTTP client
    "python-dotenv" # Environment variables
]

[project.scripts]
flexible-graphrag-mcp = "main:main"  # Entry point
```

**Installation methods**:
- `pipx install .` - System-wide installation (recommended)
- `uvx flexible-graphrag-mcp` - No installation needed (alternative)

**Claude Desktop config** (Windows):
```json
{
  "mcpServers": {
    "flexible-graphrag": {
      "command": "flexible-graphrag-mcp",
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONLEGACYWINDOWSSTDIO": "1"
      }
    }
  }
}
```

---

## Document Processing Pipeline

### Two-Parser System: Docling vs LlamaParse

```
┌────────────────────────────────────────────────────────────┐
│              DOCUMENT PROCESSING PIPELINE                  │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Input: Documents from 13 Data Sources                     │
│  ┌────────────────────────────────────────────────────┐    │
│  │ • File Upload (drag & drop)                        │    │
│  │ • Cloud: S3, GCS, Azure Blob, OneDrive,            │    │
│  │   SharePoint, Box, Google Drive                    │    │
│  │ • Repos: CMIS, Alfresco                            │    │
│  │ • Web: Web pages, Wikipedia, YouTube               │    │
│  └───────────────────┬────────────────────────────────┘    │
│                      │                                     │
│                      ▼                                     │
│  document_processor.py (DocumentProcessor class)           │
│  ┌────────────────────────────────────────────────────┐    │
│  │                                                    │    │
│  │  Parser Selection (DOCUMENT_PARSER env var)        │    │
│  │  ┌──────────────────────────────────────────┐      │    │
│  │  │ Format Detection:                        │      │    │
│  │  │ • Plain text (.txt, .md) → Direct        │      │    │
│  │  │ • Documents (.pdf, .docx, etc.) → Parser │      │    │
│  │  │ • Images (.png, .jpg) → OCR Parser       │      │    │
│  │  └───────────┬──────────────────────────────┘      │    │
│  │              │                                     │    │
│  │              ▼                                     │    │
│  │  ┌──────────────┐    ┌──────────────────┐          │    │
│  │  │   Docling    │ OR │   LlamaParse     │          │    │
│  │  │   Parser     │    │   Parser         │          │    │
│  │  │(Default/Free)│    │(Cloud/Premium)   │          │    │
│  │  └──────┬───────┘    └─────────┬────────┘          │    │
│  │         │                       │                  │    │
│  │         ▼                       ▼                  │    │
│  │  ┌──────────────────────────────────────────┐      │    │
│  │  │         Parsed Content                   │      │    │
│  │  │  • Text extraction                       │      │    │
│  │  │  • Table preservation (markdown)         │      │    │
│  │  │  • Layout analysis                       │      │    │
│  │  │  • Formula recognition                   │      │    │
│  │  └──────────────────┬───────────────────────┘      │    │
│  └────────────────────┼───────────────────────────────┘    │
│                       │                                    │
│                       ▼                                    │
│  LlamaIndex Ingestion Pipeline                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │ 1. Text chunking (SentenceSplitter)                │    │
│  │ 2. Embedding generation (OpenAI/Ollama)            │    │
│  │ 3. Knowledge graph extraction:                     │    │
│  │    • SimpleLLMPathExtractor (basic)                │    │
│  │    • SchemaLLMPathExtractor (with schema)          │    │
│  │    • DynamicLLMPathExtractor (LLM-guided)          │    │
│  └───────────────────┬────────────────────────────────┘    │
│                      │                                     │
│                      ▼                                     │
│  Output: Structured Data                                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │ • Document chunks with embeddings                  │    │
│  │ • Entities (Person, Organization, Technology...)   │    │
│  │ • Relationships (WORKS_FOR, DEVELOPS, MENTIONS...) │    │
│  │ • Metadata (source, page, section...)              │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Document Parser Configuration

**Parser Selection** (via `DOCUMENT_PARSER` environment variable):

```bash
# Docling (default) - Open-source, local processing
DOCUMENT_PARSER=docling

# LlamaParse - Cloud API service with advanced OCR
DOCUMENT_PARSER=llamaparse
LLAMAPARSE_API_KEY=llx-...
```

**LlamaParse Modes** (configurable via `LLAMAPARSE_MODE`):

```bash
# Mode 1: Without LLM (fastest, cheapest)
LLAMAPARSE_MODE=parse_page_without_llm     # 1 credit/page

# Mode 2: With LLM (default, balanced)
LLAMAPARSE_MODE=parse_page_with_llm        # 3 credits/page

# Mode 3: With Agent (premium quality)
LLAMAPARSE_MODE=parse_page_with_agent      # 10-90 credits/page
LLAMAPARSE_AGENT_MODEL=openai-gpt-4-1-mini # Required for agent mode
```

---

## Database Layer

### Complete Database Support Matrix

```
┌────────────────────────────────────────────────────────────┐
│                  DATABASE ABSTRACTION LAYER                │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Vector Stores (10 options)                                │
│  ┌────────────────────────────────────────────────────┐    │
│  │ • Neo4j (with vector index)                        │    │
│  │ • Qdrant (dedicated vector DB)                     │    │
│  │ • Elasticsearch (dual: vector + search)            │    │
│  │ • OpenSearch (dual: vector + search)               │    │
│  │ • Chroma (local/HTTP modes)                        │    │
│  │ • Milvus (cloud-native, scalable)                  │    │
│  │ • Weaviate (semantic search)                       │    │
│  │ • Pinecone (managed serverless)                    │    │
│  │ • PostgreSQL (with pgvector extension)             │    │
│  │ • LanceDB (modern embedded)                        │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  Graph Databases (9 options)                               │
│  ┌────────────────────────────────────────────────────┐    │
│  │ • Neo4j (property graph, Cypher)                   │    │
│  │ • Ladybug (embedded, Cypher)                       │    │
│  │ • FalkorDB (GraphBLAS, optimized for LLM)          │    │
│  │ • ArcadeDB (multi-model: graph/doc/KV/search)      │    │
│  │ • MemGraph (real-time, streaming)                  │    │
│  │ • NebulaGraph (distributed, large-scale)           │    │
│  │ • Neptune (AWS managed, property/RDF)              │    │
│  │ • Neptune Analytics (serverless analytics)         │    │
│  │ • None (disable knowledge graph)                   │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  Search Engines (3 options)                                │
│  ┌────────────────────────────────────────────────────┐    │
│  │ • BM25 (built-in, local, file-based)               │    │
│  │ • Elasticsearch (enterprise, advanced)             │    │
│  │ • OpenSearch (AWS fork, hybrid scoring)            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  LLM Providers (5 options)                                 │
│  ┌────────────────────────────────────────────────────┐    │
│  │ • OpenAI (GPT-4o, GPT-4o-mini)                     │    │
│  │ • Ollama (local: llama3.1, llama3.2, gpt-oss)      │    │
│  │ • Azure OpenAI (enterprise GPT models)             │    │
│  │ • Anthropic (Claude models)                        │    │
│  │ • Google Gemini (Gemini models)                    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  factories.py (Database Factory Pattern)                   │
│  ┌────────────────────────────────────────────────────┐    │
│  │ • create_llm() - LLM selection                     │    │
│  │ • create_embed_model() - Embedding selection       │    │
│  │ • create_vector_store() - Vector DB selection      │    │
│  │ • create_graph_store() - Graph DB selection        │    │
│  │ • create_text_search() - Search engine selection   │    │
│  │                                                    │    │
│  │ All configurable via environment variables:        │    │
│  │ • LLM_PROVIDER=openai/ollama/azure/...             │    │
│  │ • VECTOR_DB=neo4j/qdrant/elasticsearch/...         │    │
│  │ • GRAPH_DB=neo4j/ladybug/falkordb/arcadedb/...     │    │
│  │ • SEARCH_DB=bm25/elasticsearch/opensearch          │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### RAG without GraphRAG Mode

For simpler deployments without knowledge graph extraction:

```bash
# .env configuration
GRAPH_DB=none
ENABLE_KNOWLEDGE_GRAPH=false
VECTOR_DB=qdrant              # Any vector store
SEARCH_DB=elasticsearch        # Any search engine
```

**Results in**:
- * Vector similarity search (semantic)
- * Full-text search (keyword-based)
- * Graph traversal (disabled)
- * Faster processing (no graph extraction)

---

## Frontend Clients

### Three Framework Implementation

```
┌──────────────────────────────────────────────────────────────┐
│                    FRONTEND CLIENTS                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Angular Frontend (TypeScript + Material Design)             │
│  ┌────────────────────────────────────────────────────┐      │
│  │ • Port: 4200 (dev), 8070/ui/angular/ (Docker)      │      │
│  │ • Framework: Angular 15+ with CLI                  │      │
│  │ • UI Library: Angular Material                     │      │
│  │ • State: RxJS Observables                          │      │
│  │ • Build: Webpack via Angular CLI                   │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
│  React Frontend (TypeScript + Material-UI)                   │
│  ┌────────────────────────────────────────────────────┐      │
│  │ • Port: 5173 (dev), 8070/ui/react/ (Docker)        │      │
│  │ • Framework: React 18+ with Hooks                  │      │
│  │ • UI Library: Material-UI (MUI)                    │      │
│  │ • State: React Hooks (useState, useEffect)         │      │
│  │ • Build: Vite (fast HMR)                           │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
│  Vue Frontend (TypeScript + Vuetify)                         │
│  ┌────────────────────────────────────────────────────┐      │
│  │ • Port: 3000 (dev), 8070/ui/vue/ (Docker)          │      │
│  │ • Framework: Vue 3 with Composition API            │      │
│  │ • UI Library: Vuetify 3                            │      │
│  │ • State: Reactive refs (ref, computed, watch)      │      │
│  │ • Build: Vite (fast HMR)                           │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
│  Common Features (All Three Frameworks)                      │
│  ┌────────────────────────────────────────────────────┐      │
│  │ Tabbed Interface:                                  │      │
│  │  1. Sources Tab:                                   │      │
│  │     • Data source selection (13 options)           │      │
│  │     • File upload (drag & drop)                    │      │
│  │     • Configuration forms (cloud, repo, web)       │      │
│  │  2. Processing Tab:                                │      │
│  │     • File list with checkboxes                    │      │
│  │     • Per-file progress bars                       │      │
│  │     • Bulk operations (remove selected)            │      │
│  │     • Real-time status updates                     │      │
│  │  3. Search Tab:                                    │      │
│  │     • Hybrid Search (document excerpts)            │      │
│  │     • Q&A Query (AI-generated answers)             │      │
│  │  4. Chat Tab:                                      │      │
│  │     • Conversational interface                     │      │
│  │     • Message history                              │      │
│  │     • Clear history button                         │      │
│  │  5. Graph Tab (hidden):                            │      │
│  │     • Reserved for future visualization            │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
│  Backend Communication (All Clients)                         │
│  ┌────────────────────────────────────────────────────┐      │
│  │ • REST API: http://localhost:8000/api/*            │      │
│  │ • Async processing with polling                    │      │
│  │ • File upload: multipart/form-data                 │      │
│  │ • Progress tracking: /api/processing-status/{id}   │      │
│  │ • Cancellation: POST /api/cancel-processing/{id}   │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Deployment Configurations

Flexible GraphRAG supports three deployment configurations optimized for different use cases. See [DEPLOYMENT-CONFIGURATIONS.md](DEPLOYMENT-CONFIGURATIONS.md) for complete details.

### Configuration 1: Standalone Everything

**Best For**: Active development, learning, maximum debugging flexibility

```
┌─────────────────────────────────────────────────────────┐
│         STANDALONE CONFIGURATION                        │
├─────────────────────────────────────────────────────────┤
│  Frontend (Local) → Backend (Local) → Databases (Local) │
│                                                         │
│  Ports:                                                 │
│  • Frontend: 3000/4200/5173                             │
│  • Backend: 8000                                        │
│  • Neo4j: 7687, Qdrant: 6333, Elasticsearch: 9200       │
│                                                         │
│  Pros:                                                  │
│  * Hot reload (frontend & backend)                      │
│  * Direct filesystem access                             │
│  * Easy debugging                                       │
│  * No Docker overhead                                   │
│                                                         │
│  Cons:                                                  │
│  * Manual database installation                         │
│  * Inconsistent environments                            │
└─────────────────────────────────────────────────────────┘
```

**Setup**:
```bash
# Backend
cd flexible-graphrag
uv run start.py

# Frontend (choose one)
cd flexible-graphrag-ui/frontend-react
npm run dev
```

### Configuration 2: Databases in Docker (Hybrid) 🌟

**Best For**: Team development, database testing, recommended for most users

```
┌─────────────────────────────────────────────────────────┐
│         HYBRID CONFIGURATION (RECOMMENDED)              │
├─────────────────────────────────────────────────────────┤
│  Frontend (Local) → Backend (Local) → Databases (Docker)│
│                                                         │
│  Ports:                                                 │
│  • Frontend: 3000/4200/5173                             │
│  • Backend: 8000                                        │
│  • Databases: 7687, 6333, 9200, etc. (Docker exposed)   │
│                                                         │
│  Pros:                                                  │
│  * Hot reload (frontend & backend)                      │
│  * Direct filesystem access                             │
│  * Easy debugging                                       │
│  * Consistent database versions                         │
│  * Easy database switching                              │
│  * Simple cleanup (docker-compose down -v)              │
│                                                         │
│  Cons:                                                  │
│  * Docker required                                      │
└─────────────────────────────────────────────────────────┘
```

**Setup**:
```bash
# Start databases
cd flexible-graphrag/docker
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d

# Backend
cd flexible-graphrag
uv run start.py

# Frontend
cd flexible-graphrag-ui/frontend-react
npm run dev
```

**Selective Services**:
Edit `docker/docker-compose.yaml` to enable/disable services:
```yaml
includes:
  - path: includes/neo4j.yaml        # * Keep
  # - path: includes/ladybug-explorer.yaml  # optional Explorer UI
  - path: includes/qdrant.yaml       # * Keep
  # - path: includes/chroma.yaml     # * Comment out if not using
  - path: includes/elasticsearch.yaml # * Keep
```

### Configuration 3: Full Docker Deployment

**Best For**: Production, demos, CI/CD, team onboarding

```
┌─────────────────────────────────────────────────────────────┐
│         FULL DOCKER CONFIGURATION                           │
├─────────────────────────────────────────────────────────────┤
│  Nginx Proxy (8070)                                         │
│    ├─ /ui/angular/ → Frontend Container                     │
│    ├─ /ui/react/   → Frontend Container                     │
│    ├─ /ui/vue/     → Frontend Container                     │
│    └─ /api/*       → Backend Container → Database Containers│
│                                                             │
│  All services in Docker network                             │
│                                                             │
│  Pros:                                                      │
│  * Single command startup                                   │
│  * Complete production environment                          │
│  * Consistent across all machines                           │
│  * Easy demo deployment                                     │
│  * No local installation needed                             │
│                                                             │
│  Cons:                                                      │
│  * No hot reload (need rebuilds)                            │
│  * Harder debugging                                         │
└─────────────────────────────────────────────────────────────┘
```

**Setup**:
```bash
# Configure Docker environment
cd flexible-graphrag/docker
cp docker.env.sample docker.env
# Edit docker.env with host.docker.internal for database hosts

# Start everything
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d

# Access via nginx proxy
http://localhost:8070/ui/angular/
http://localhost:8070/ui/react/
http://localhost:8070/ui/vue/
```

**Key Configuration Differences**:

| Setting | Standalone/Hybrid | Full Docker |
|---------|------------------|-------------|
| Database Hosts | `localhost` | `host.docker.internal` |
| Ollama URL | `http://localhost:11434` | `http://host.docker.internal:11434` |
| Frontend API | `http://localhost:8000` | `http://backend:8000` (internal) |

### Choosing the Right Configuration

**Quick Decision Guide**:
- **Team development?** → Configuration 2 (Hybrid) 🌟
- **Production deployment?** → Configuration 3 (Full Docker)
- **Learning the system?** → Configuration 2 (Hybrid)
- **Testing database combinations?** → Configuration 2 (Hybrid)
- **Solo development?** → Configuration 1 or 2

**Migration Path**:
```
Standalone → Add Docker databases → Full Docker
   ↑                    ↓
   └─────────────────────┘
  Easy to switch back and forth
```

For complete setup instructions, environment variables, volume management, and troubleshooting, see [DEPLOYMENT-CONFIGURATIONS.md](DEPLOYMENT-CONFIGURATIONS.md).

---

## Complete System Flow

### End-to-End Document Processing

```
┌─────────────────────────────────────────────────────────────────┐
│                   COMPLETE SYSTEM FLOW                          │
└─────────────────────────────────────────────────────────────────┘

1. User uploads files via Frontend (Angular/React/Vue)
   │
   ▼
2. POST /api/upload → main.py → Saves to flexible-graphrag/uploads/
   │
   ▼
3. User clicks "Start Processing"
   │
   ▼
4. POST /api/ingest → main.py → backend.py
   │
   ▼
5. backend.py orchestrates:
   ├─► Creates processing_id
   ├─► Initializes per-file progress tracking
   ├─► Spawns async background task
   └─► Returns immediately with processing_id
   │
   ▼
6. Background task calls hybrid_system.py:
   ├─► document_processor.py parses files (Docling/LlamaParse)
   ├─► LlamaIndex SentenceSplitter chunks text
   ├─► LLM generates embeddings (OpenAI/Ollama)
   ├─► LLM extracts entities & relationships (knowledge graph)
   ├─► VectorStoreIndex → Vector database (Qdrant/Neo4j/...)
   ├─► PropertyGraphIndex → Graph database (Neo4j/Ladybug/...)
   └─► BM25/Elasticsearch → Search engine
   │
   ▼
7. Frontend polls GET /api/processing-status/{id}
   ├─► Shows per-file progress bars
   ├─► Updates status messages
   └─► Shows completion
   │
   ▼
8. User searches via Search Tab:
   ├─► POST /api/search → Hybrid Search
   │   ├─► Vector similarity (embeddings)
   │   ├─► BM25/Elasticsearch full-text
   │   └─► Graph traversal (if enabled)
   │
   └─► POST /api/query → Q&A Engine
       ├─► Retrieves relevant documents
       ├─► LLM generates answer
       └─► Returns synthesized response
```

---

## Configuration Files Overview

### Key Configuration Locations

```
flexible-graphrag/
├── .env                           # Main configuration
│   ├── LLM_PROVIDER=openai/ollama
│   ├── VECTOR_DB=qdrant/neo4j/...
│   ├── GRAPH_DB=neo4j/ladybug/...
│   ├── SEARCH_DB=elasticsearch/opensearch/bm25
│   ├── DOCUMENT_PARSER=docling/llamaparse
│   └── [Database credentials]
│
├── env-sample.txt                 # Configuration template
│
└── flexible-graphrag-mcp/
    ├── pyproject.toml             # MCP package definition
    └── claude-desktop-configs/    # Claude Desktop configs
        ├── windows/
        │   ├── pipx-config.json
        │   └── uvx-config.json
        └── macos/
            ├── pipx-config.json
            └── uvx-config.json
```

### Environment Variable Hierarchy

1. **LLM Configuration**
   - `LLM_PROVIDER`: openai, ollama, azure_openai, anthropic, gemini
   - `EMBEDDING_PROVIDER`: openai, ollama, azure_openai
   - Provider-specific: `OPENAI_API_KEY`, `OLLAMA_BASE_URL`, etc.

2. **Database Configuration**
   - `VECTOR_DB` + `VECTOR_DB_CONFIG` (JSON)
   - `GRAPH_DB` + `GRAPH_DB_CONFIG` (JSON)
   - `SEARCH_DB` + `SEARCH_DB_CONFIG` (JSON)

3. **Document Processing**
   - `DOCUMENT_PARSER`: docling (default), llamaparse
   - `LLAMAPARSE_MODE`: parse_page_with_llm (default), parse_page_without_llm, parse_page_with_agent
   - `LLAMAPARSE_API_KEY`: Required for LlamaParse

4. **Knowledge Graph**
   - `ENABLE_KNOWLEDGE_GRAPH`: true (default), false
   - `KG_EXTRACTOR_TYPE`: schema (default), simple, dynamic
   - `SCHEMA_NAME`: none, default, custom
   - `SCHEMAS`: JSON array of schemas

5. **Timeouts**
   - `OPENAI_TIMEOUT`: 120.0
   - `OLLAMA_TIMEOUT`: 300.0
   - `KG_EXTRACTION_TIMEOUT`: 3600

---

## Summary

The Flexible GraphRAG architecture demonstrates:

1. **Clean Separation of Concerns**
   - Backend core (`backend.py` + `hybrid_system.py`)
   - REST API layer (`main.py`)
   - MCP protocol layer (`main.py` in MCP directory)
   - Frontend clients (Angular, React, Vue)

2. **Database Flexibility**
   - 10 vector stores, 9 graph databases, 3 search engines
   - Easy switching via environment variables
   - Factory pattern abstracts database complexity

3. **Document Processing Excellence**
   - Two parsers: Docling (free, local) and LlamaParse (premium, cloud)
   - 13 data sources supported
   - Intelligent routing and format detection

4. **Production-Ready MCP Integration**
   - HTTP mode for minimal dependencies and clean separation
   - Works with Claude Desktop and MCP Inspector
   - Only 4 dependencies for lightweight deployment

5. **Flexible Deployment Options**
   - Standalone: Maximum development flexibility
   - Hybrid (Recommended): Databases in Docker, apps local
   - Full Docker: Complete production environment
   - See [DEPLOYMENT-CONFIGURATIONS.md](DEPLOYMENT-CONFIGURATIONS.md) for complete setup guides

6. **Modern Development Practices**
   - Async/await throughout
   - Type safety (Pydantic, TypeScript)
   - Comprehensive progress tracking
   - Cancellation support

This architecture supports everything from simple RAG (without graph) to full GraphRAG with multiple data sources, databases, and LLM providers, all configurable through environment variables.


