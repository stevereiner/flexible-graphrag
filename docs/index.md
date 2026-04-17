---
hide:
  - toc
---

# Flexible GraphRAG

[![PyPI](https://img.shields.io/pypi/v/flexible-graphrag?label=flexible-graphrag&color=blue)](https://pypi.org/project/flexible-graphrag/)
[![Downloads](https://img.shields.io/pepy/dt/flexible-graphrag)](https://pepy.tech/project/flexible-graphrag)
[![PyPI MCP](https://img.shields.io/pypi/v/flexible-graphrag-mcp?label=flexible-graphrag-mcp&color=blue)](https://pypi.org/project/flexible-graphrag-mcp/)
[![Downloads MCP](https://img.shields.io/pepy/dt/flexible-graphrag-mcp)](https://pepy.tech/project/flexible-graphrag-mcp)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![Angular](https://img.shields.io/badge/Angular-19-DD0031?logo=angular&logoColor=white)](https://angular.dev/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)

**Flexible GraphRAG** is an open source platform supporting document processing (Docling or LlamaParse), knowledge graph auto-building, schemas, LlamaIndex LLMs, RAG and GraphRAG setup, hybrid search (fulltext, vector, graph), AI query, and AI chat capabilities. The backend uses Python, LlamaIndex, and FastAPI. Has Angular, React, and Vue TypeScript frontends. A MCP Server is also available. Currently supports 13 data sources, 10 vector databases, OpenSearch / Elasticsearch / BM25 search, 8 property graph databases, 3 RDF triple stores (Fuseki, GraphDB, Oxigraph), and Alfresco. These servers and their dashboards can be configured in a provided docker compose.

---

## What's New

- **RDF/Ontology Support**: Flexible GraphRAG now supports RDF-based ontologies for both property graph databases and RDF triple store databases (Graphwise Ontotext GraphDB, Fuseki, and Oxigraph). Document ingestion with KG extraction, auto incremental data source change detection, and UI search (hybrid search, AI query, and AI chat) are all supported with both database types.
- **Incremental Auto-Sync**: Flexible GraphRAG supports **automatic incremental updates** (Optional) from most data sources, keeping your Vector, Search and Graph databases synchronized in real-time or near real-time.
- **KG Spaces Integration**: [KG Spaces Integration of Flexible GraphRAG in Alfresco ACA Client](https://github.com/stevereiner/kg-spaces-aca) — integrates the Flexible GraphRAG Angular UI as an extension plugin within the Alfresco Content Application.

---

## Features

- **Hybrid Search**: A configurable hybrid search system that combines vector search, full-text search, and graph GraphRAG
- **Knowledge Graph GraphRAG**: Extracts entities and relationships from documents to auto create graphs in property graph databases for GraphRAG. Configuration for schemas to use or use as a starting point for LLM to expand on is supported.
- **RDF/Ontology Support**: Load OWL/RDFS ontologies to guide KG extraction into any property graph or RDF store; SPARQL 1.1 queries; RDF 1.2 triple annotations; full UI pipeline (ingest, hybrid search, AI query/chat, incremental auto-sync). See [RDF Graph Databases](DATABASES/RDF/RDF-STORE-USER-GUIDE.md).
- **8 Property Graph Databases**: Neo4j, ArcadeDB, FalkorDB, Ladybug, MemGraph, NebulaGraph, Amazon Neptune, and Amazon Neptune Analytics — with KG extraction, hybrid search, and AI query/chat
- **3 RDF Triple Stores**: Apache Jena Fuseki, Ontotext GraphDB, Oxigraph
- **10 Vector Databases**: Qdrant, Elasticsearch, OpenSearch, Neo4j, Chroma, Milvus, Weaviate, Pinecone, PostgreSQL pgvector, LanceDB — for semantic similarity search
- **3 Search Databases**: Elasticsearch, OpenSearch, BM25 (built-in) — for full-text search and hybrid ranking
- **LLM providers (KG extraction & chat)**: Ollama, OpenAI, Azure OpenAI, Google Gemini, Anthropic Claude, Google Vertex AI, Amazon Bedrock, Groq, Fireworks AI, OpenAI-compatible endpoints (`openai_like`), OpenRouter, LiteLLM proxy, and vLLM — configurable via `LLM_PROVIDER`; see [LLM & Embedding Config](LLM/LLM-EMBEDDING-CONFIG.md)
- **Embedding providers**: OpenAI, Ollama, Azure OpenAI, Google GenAI, Vertex AI, Bedrock, Fireworks, OpenAI-like (`EMBEDDING_KIND=openai_like`), and LiteLLM — see [LLM Configuration](LLM/LLM-EMBEDDING-CONFIG.md)
- **Configurable Architecture**: LlamaIndex provides abstractions for allowing multiple vector databases, property graph databases, RDF triple stores, search engines, and LLM providers to be supported
- **Multi-Source Ingestion**: Processes documents from 13 data sources (file upload, cloud storage, enterprise repositories, web sources) with Docling (default) or LlamaParse (cloud API) document parsing.
- **Observability**: Built-in OpenTelemetry instrumentation with automatic LlamaIndex tracing, Prometheus metrics, Jaeger traces, and Grafana dashboards for production monitoring
- **FastAPI Server with REST API**: Python based FastAPI server with REST APIs for document ingesting, hybrid search, AI query, and AI chat.
- **MCP Server**: MCP server providing Claude Desktop and other MCP clients with tools for document/text ingesting (all 13 data sources), hybrid search, and AI query. Uses FastAPI backend REST APIs.
- **UI Clients**: Angular, React, and Vue UI clients support choosing the data source (filesystem, Alfresco, CMIS, etc.), ingesting documents, performing hybrid searches, AI queries, and AI chat. The UI clients use the REST APIs of the FastAPI backend.
- **Docker Deployment Flexibility**: Supports both standalone and Docker deployment modes. Docker infrastructure provides modular database selection via docker-compose includes — vector, graph, search engines, and Alfresco can be included or excluded with a single comment. Choose between hybrid deployment (databases in Docker, backend and UIs standalone) or full containerization.

---

## System Components

### FastAPI Backend (`/flexible-graphrag`)

- **REST API Server**: Provides endpoints for document ingestion, search, and AI query/chat
- **Hybrid Search Engine**: Combines vector similarity (RAG), fulltext (BM25), and graph traversal (GraphRAG)
- **Document Processing**: Advanced document conversion with Docling and LlamaParse integration
- **Configurable Architecture**: Environment-based configuration for all components
- **Async Processing**: Background task processing with real-time progress updates

### MCP Server (`/flexible-graphrag-mcp`)

- **MCP Client support**: Model Context Protocol server for Claude Desktop and other MCP clients
- **Full API Parity**: Tools like `ingest_documents()` support all 13 data sources with source-specific configs: filesystem, repositories (Alfresco, SharePoint, Box, CMIS), cloud storage, web; `skip_graph` flag for all data sources; `paths` parameter for filesystem/Alfresco/CMIS; Alfresco also supports `nodeDetails` list (multi-select for KG Spaces)
- **Additional Tools**: `search_documents()`, `query_documents()`, `ingest_text()`, system diagnostics, and health checks
- **Dual Transport**: HTTP mode for debugging, stdio mode for production
- **Tool Suite**: 9 specialized tools for document processing, search, and system management
- **Multiple Installation**: pipx system installation or uvx no-install execution

### UI Clients (`/flexible-graphrag-ui`)

- **Angular Frontend**: Material Design with TypeScript
- **React Frontend**: Modern React with Vite and TypeScript
- **Vue Frontend**: Vue 3 Composition API with Vuetify and TypeScript
- **Unified Features**: All clients support the 4 tab views, async processing, progress tracking, and cancellation

### Docker Infrastructure (`/docker`)

- **Modular Database Selection**: Include/exclude vector, graph, and search engines, and Alfresco with single-line comments
- **Flexible Deployment**: Hybrid mode (databases in Docker, apps standalone) or full containerization
- **NGINX Reverse Proxy**: Unified access to all services with proper routing
- **Built-in Database Dashboards**: Most server dockers also provide built-in web interface dashboards (Neo4j browser, ArcadeDB, FalkorDB, OpenSearch, etc.)
- **Separate Dashboards**: Additional dashboard dockers are provided: including Kibana for Elasticsearch and optional Ladybug Explorer (see `docker/includes/ladybug-explorer.yaml`).

---

## Where to start

| | |
|---|---|
| **[Getting Started](GETTING-STARTED/GETTING-STARTED.md)** | Prerequisites, setup overview, Python backend, frontend setup |
| **[Docker Deployment](GETTING-STARTED/DOCKER-DEPLOYMENT.md)** | Modular docker-compose — pick your databases, start one command |
| **[Configuration](DATABASES/DATABASE-CONFIGURATION.md)** | Database configuration, schema examples, LangChain config |
| **[UI Guide](UI-GUIDE/UI-GUIDE.md)** | 4-tab interface: Sources → Processing → Search → Chat |
| **[Data Sources](DATA-SOURCES/OVERVIEW.md)** | 13 sources: S3, Azure Blob, GCS, OneDrive, Alfresco, CMIS, Wikipedia, YouTube … |
| **[Databases](DATABASES/GRAPH-DATABASES/README-neo4j.md)** | Property graph, RDF triple stores, vector databases, search databases |
| **[MCP Server](MCP/MCP-SERVER.md)** | 9 tools for Claude Desktop, Cursor, and other MCP clients |
| **[Developer](DEVELOPER/REST-API.md)** | REST API, MCP Tools, Observability, Testing & Debugging |
