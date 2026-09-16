[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/stevereiner-flexible-graphrag-badge.png)](https://mseep.ai/app/stevereiner-flexible-graphrag)

# Flexible GraphRAG

[![PyPI - flexible-graphrag](https://img.shields.io/pypi/v/flexible-graphrag?label=flexible-graphrag&color=blue)](https://pypi.org/project/flexible-graphrag/)
[![Downloads - flexible-graphrag](https://img.shields.io/pepy/dt/flexible-graphrag)](https://pepy.tech/project/flexible-graphrag)
[![PyPI - flexible-graphrag-mcp](https://img.shields.io/pypi/v/flexible-graphrag-mcp?label=flexible-graphrag-mcp&color=blue)](https://pypi.org/project/flexible-graphrag-mcp/)
[![Downloads - flexible-graphrag-mcp](https://img.shields.io/pepy/dt/flexible-graphrag-mcp)](https://pepy.tech/project/flexible-graphrag-mcp)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![Angular](https://img.shields.io/badge/Angular-19-DD0031?logo=angular&logoColor=white)](https://angular.dev/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/stevereiner/flexible-graphrag)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://stevereiner.github.io/flexible-graphrag/)

<p align="center">
  <a href="./screen-shots/langflow/langflow-sharepoint-graphdb-neo4j.png">
    <img src="./screen-shots/langflow/langflow-sharepoint-graphdb-neo4j.png" alt="Flexible GraphRAG in Langflow pipeline mode: a SharePoint auto-sync source using Microsoft Graph delta queries, a PDF parsed by LiteParse, and one ingest populating Qdrant vector, Elasticsearch search, Neo4j property graph, and Graphwise GraphDB RDF at the same time, with the processing tab showing initial sync status and AI chat answering questions from an ontology-mode knowledge graph" width="900">
  </a>
</p>

<p align="center"><em>Langflow pipeline mode — a SharePoint auto-sync data source (MS Graph delta query) ingesting and targeting Qdrant vector, Elasticsearch, Neo4j, and Graphwise Ontotext GraphDB, with ontology-mode, AI chat drawing context from all four.</em></p>

<p align="center">
  <a href="./images/flexible-graphrag-v0.8.0-architecture.png">
    <img src="./images/flexible-graphrag-v0.8.0-architecture.png" alt="Flexible GraphRAG v0.8.0 architecture: default, CocoIndex, and Langflow ingest pipelines sharing the same data sources, database targets, UI, and REST / MCP APIs" width="900">
  </a>
</p>

<p align="center"><em>Can use 1 of 3 ingest pipelines with same configured data sources and database targets, with same UI and same REST / MCP APIs</em></p>

**Flexible GraphRAG** is an open source AI context platform supporting a document processing pipeline (Docling, LlamaParse, or LiteParse), knowledge graph auto-building, ontologies, schemas, many LLM providers, GraphRAG and RAG, hybrid semantic search (fulltext, vector, property graph, RDF/SPARQL), AI query, and AI chat. The backend is **Python** with **LlamaIndex** and **LangChain** as peer frameworks. **LlamaIndex** is the default for each pipeline stage; **LangChain** can be selected per stage in environment configuration. The API is a REST **FastAPI** service. **Angular**, **React**, and **Vue** TypeScript frontends and an **MCP** server are included. The stack supports 14 data sources (10 with incremental auto-sync), 15 property graph databases, 4 RDF triple stores (Apache Jena Fuseki, Ontotext GraphDB, Oxigraph, Amazon Neptune RDF), 10 vector databases, OpenSearch / Elasticsearch / BM25 search, Alfresco, and Nuxeo. Databases and dashboards can be enabled with the provided Docker Compose layout. Optionally, the ingest pipeline, hybrid search, and AI query can run through customizable **Langflow** visual flows (12 custom Langflow components). As a further option, ingest can run on a **CocoIndex** (Rust engine) pipeline that reuses the same sources, targets, parsers and KG extractors, adding step-level memoization and automatic delete reconciliation.  

**New 8/18/26 — v0.8.0 release:** Optional **CocoIndex integration** — Rust-backed [CocoIndex](https://github.com/cocoindex-io/cocoindex) pipeline mixed with Flexible GraphRAG sources (incl. detectors), functions, and targets (more PG/vector/RDF/search); same UI/REST/MCP. Standalone `app.py` also supported. Now with **custom KG extractors** (bring your own, or fall back to the built-in one per document) and **entity resolution**. New **meeting-notes example** ([`examples/cocoindex/meeting_notes_graph_any/`](examples/cocoindex/meeting_notes_graph_any/README.md)) — a CocoIndex example ported to run against any configured graph store and source. See [CocoIndex Integration](#cocoindex-integration).

**New 8/8/26 — v0.7.2 release:** **Nuxeo** added as a data source — all 3 UIs (React/Vue/Angular) plus REST/MCP, with basic / token / OAuth2 auth and real-time incremental sync via the Nuxeo audit event stream (Kafka). **Alfresco OAuth2 and ticket** authentication added across the source, all 3 UIs, initial ingest, and real-time sync. **Alfresco Community 26.1** Docker upgrade. The **MCP server** gained optional OAuth2 on its transport (bearer token via your IdP) and moved to **FastMCP 3**. Requires `python-alfresco-api >= 1.2.1`.

**New 7/20/26 — v0.7.1 release:** Document processing now supports **LiteParse** in addition to the previous **Docling** and **LlamaParse** support. Langflow integration ships with fixes and an optional **Langflow Docker** image bundling the 12 "Flexible" components. **MS Graph delta query** support was added for more efficient incremental updating with SharePoint and OneDrive data sources.

**New 7/5/26:** Optional **Langflow visual flows** — the app can run its ingest pipeline, hybrid search, and AI query through customizable [Langflow](https://www.langflow.org/) flows (12 custom Flexible GraphRAG components), using your existing `.env` config. See [Langflow Integration](docs/GETTING-STARTED/LANGFLOW-INTEGRATION.md).

**New 5/6/26:** 15 property graph databases total: 8 supported on both LlamaIndex and LangChain, 1 LI-only (Google Cloud Spanner Graph), 6 LC-only (ArangoDB, Apache AGE, Azure Cosmos DB for Gremlin, Apache HugeGraph, SurrealDB, TigerGraph). AWS Neptune RDF/SPARQL added. All 10 vector databases, all 3 search engines, and all LLM/embedding providers work with both LlamaIndex and LangChain. Every pipeline stage (chunking, KG extraction, graph write, vector write, search write, and retrieval fusion) can be configured independently. (Data source reading is LlamaIndex only; RDF stores use framework-independent adapters with LangChain Text-to-SPARQL retrieval.)

**New:** Flexible GraphRAG now supports RDF-based ontologies for both property graph databases and RDF triple store databases (Graphwise Ontotext GraphDB, Fuseki, and Oxigraph). Document ingestion with KG extraction, auto incremental data source change detection, and UI search (hybrid search, AI query, and AI chat) are all supported with both database types.

**New:** Flexible GraphRAG supports **automatic incremental updates** (Optional) from most data sources, keeping your Vector, Search and Graph databases synchronized in real-time or near real-time.

**New:** [KG Spaces Integration of Flexible GraphRAG in Alfresco ACA Client](https://github.com/stevereiner/kg-spaces-aca)

**New in v0.6.0:** Version 0.6.0 broadened framework and database choice: **LangChain** is a full peer to **LlamaIndex** (per-stage env pickers for chunking, vector, search, property graph, KG extraction, fusion). **15** property graph backends: **8** on both frameworks, **Google Cloud Spanner** (LlamaIndex-only), **6** LangChain-only (ArangoDB, Apache AGE, Azure Cosmos DB for Gremlin, HugeGraph, SurrealDB, TigerGraph). **RDF** includes **Apache Jena Fuseki**, **Ontotext GraphDB**, **Oxigraph**, and **Amazon Neptune RDF**. Incremental delete, LangChain adapters, and cleanup paths were extended across stores.

## Features

- **Hybrid Search**: Configurable hybrid search combining vector search, full-text search, property-graph GraphRAG, and SPARQL against RDF stores.
- **Knowledge Graph GraphRAG**: Extracts entities and relationships from documents to build graphs in property graph databases and RDF stores. Optional schemas and ontologies guide extraction or act as a starting point for the LLM to extend.
- **RDF/Ontology Support**: Load OWL/RDFS ontologies to guide KG extraction into any property graph or RDF store; SPARQL 1.1 queries; RDF 1.2 triple annotations; full UI pipeline (ingest, hybrid search, AI query/chat, incremental auto-sync). See [Ontology and RDF Support](#ontology-and-rdf-support) below.
- **15 Property Graph Databases**: 8 on both LI+LC (Neo4j, ArcadeDB, FalkorDB, Ladybug, Memgraph, NebulaGraph, Amazon Neptune, Neptune Analytics), 1 LI-only (Google Cloud Spanner), 6 LC-only (ArangoDB, Apache AGE, Cosmos Gremlin, HugeGraph, SurrealDB, TigerGraph) — with KG extraction, hybrid search, and AI query/chat
- **4 RDF Triple Stores**: Apache Jena Fuseki, Ontotext GraphDB, Oxigraph, Amazon Neptune RDF.
- **10 Vector Databases**: Qdrant, Elasticsearch, OpenSearch, Neo4j, Chroma, Milvus, Weaviate, Pinecone, PostgreSQL pgvector, LanceDB — for semantic similarity search
- **3 Search Databases**: Elasticsearch, OpenSearch, BM25 (built-in) — for full-text search and hybrid ranking
- **LLM providers (KG extraction & chat)**: Ollama, OpenAI, Azure OpenAI, Google Gemini, Anthropic Claude, Google Vertex AI, Amazon Bedrock, Groq, Fireworks AI, OpenAI-compatible endpoints (`openai_like`), OpenRouter, LiteLLM proxy, and vLLM — configurable via `LLM_PROVIDER`; see [Supported LLM Providers](#supported-llm-providers)
- **Embedding providers**: OpenAI, Ollama, Azure OpenAI, Google GenAI, Vertex AI, Bedrock, Fireworks, OpenAI-like (`EMBEDDING_KIND=openai_like`), and LiteLLM — see [LLM Configuration](#llm-configuration)
- **Dual-framework pipeline**: **LlamaIndex** and **LangChain** are first-class choices for chunking, vector and search adapters, property graphs, KG extraction, RDF text-to-SPARQL retrieval, and hybrid fusion—each stage can be set independently (**LlamaIndex** defaults). See [Framework Configuration](#framework-configuration).
- **Multi-Source Ingestion**: Processes documents from 14 data sources (10 with incremental auto sync): (file upload, cloud storage, enterprise repositories, web sources) with Docling (default), LlamaParse (cloud API), or LiteParse (local, lightweight) document parsing.
- **Observability**: Built-in OpenTelemetry instrumentation with automatic LlamaIndex tracing, Prometheus metrics, Jaeger traces, and Grafana dashboards for production monitoring
- **FastAPI Server with REST API**: Python based FastAPI server with REST APIs for document ingesting, hybrid search, AI query, and AI chat.
- **MCP Server**: MCP server providing Claude Desktop and other MCP clients with tools for document/text ingesting (all 14 data sources with 10 supporting incremental auto sync), hybrid search, and AI query. Uses FastAPI backend REST APIs. 
- **UI Clients**: Angular, React, and Vue UI clients support choosing the data source (filesystem, Alfresco, CMIS, etc.), ingesting documents, performing hybrid searches, AI queries, and AI chat. The UI clients use the REST APIs of the FastAPI backend.
- **Docker Deployment Flexibility**: Supports both standalone and Docker deployment modes. Docker infrastructure provides modular database selection via docker-compose includes - vector, graph, search engines, and Alfresco can be included or excluded with a single comment. Choose between hybrid deployment (databases in Docker, backend and UIs standalone) or full containerization.
- **Langflow Visual Flows (optional)**: Run the ingest pipeline, hybrid search, and AI query through customizable [Langflow](https://www.langflow.org/) flows built from 12 custom Flexible GraphRAG components — the same backend machinery (all database, LLM, and framework `.env` config applies), orchestrated visually. See [Langflow Integration](docs/GETTING-STARTED/LANGFLOW-INTEGRATION.md).
- **CocoIndex Integration (optional)**: Optional Rust-backed [CocoIndex](https://github.com/cocoindex-io/cocoindex) ingest (`PIPELINE_BACKEND=cocoindex`) mixing CocoIndex connectors with Flexible GraphRAG sources (incl. event detectors), parsers, chunkers, embeddings, LI/LC KG extractors, and broader targets (all 15 PG + 10 vector + RDF + search) — same UI / REST / MCP. Mutually exclusive with `ENABLE_INCREMENTAL_UPDATES=true` and `ENABLE_LANGFLOW_FLOWS=true`. Standalone `app.py` also supported. See [CocoIndex Integration](#cocoindex-integration).

## Frontend Screenshots

### Angular Frontend - Tabbed Interface

<details>
<summary>Click to view Angular UI screenshots (Light Theme)</summary>

| Sources Tab | Processing Tab | Search Tab | Chat Tab |
|-------------|----------------|------------|----------|
| [![Angular Sources](./screen-shots/angular/angular-sources.png)](./screen-shots/angular/angular-sources.png) | [![Angular Processing](./screen-shots/angular/angular-processing.png)](./screen-shots/angular/angular-processing.png) | [![Angular Search](./screen-shots/angular/angular-search.png)](./screen-shots/angular/angular-search.png) | [![Angular Chat](./screen-shots/angular/angular-chat.png)](./screen-shots/angular/angular-chat.png) |

</details>

### React Frontend - Tabbed Interface

<details open>
<summary>Click to view React UI screenshots (Dark Theme)</summary>

| Sources Tab | Processing Tab | Search Tab | Chat Tab |
|-------------|----------------|------------|----------|
| [![React Sources](./screen-shots/react/react-sources.png)](./screen-shots/react/react-sources.png) | [![React Processing](./screen-shots/react/react-processing.png)](./screen-shots/react/react-processing.png) | [![React Search](./screen-shots/react/react-search-hybrid-search.png)](./screen-shots/react/react-search-hybrid-search.png) | [![React Chat](./screen-shots/react/react-chat-using.png)](./screen-shots/react/react-chat-using.png) |

</details>

<details>
<summary>Click to view React UI screenshots (Light Theme)</summary>

| Sources Tab | Processing Tab | Search Tab | Chat Tab |
|-------------|----------------|------------|----------|
| [![React Sources Light](./screen-shots/react/react-sources-light.png)](./screen-shots/react/react-sources-light.png) | [![React Processing Light](./screen-shots/react/react-processing-light.png)](./screen-shots/react/react-processing-light.png) | [![React Search Light](./screen-shots/react/react-search-hybrid-search-light.png)](./screen-shots/react/react-search-hybrid-search-light.png) | [![React Chat Light](./screen-shots/react/react-chat-using-light.png)](./screen-shots/react/react-chat-using-light.png) |

</details>

### Vue Frontend - Tabbed Interface

<details>
<summary>Click to view Vue UI screenshots (Light Theme)</summary>

| Sources Tab | Processing Tab | Search Tab | Chat Tab |
|-------------|----------------|------------|----------|
| [![Vue Sources](./screen-shots/vue/vue-sources.png)](./screen-shots/vue/vue-sources.png) | [![Vue Processing](./screen-shots/vue/vue-processing.png)](./screen-shots/vue/vue-processing.png) | [![Vue Search](./screen-shots/vue/vue-search.png)](./screen-shots/vue/vue-search.png) | [![Vue Chat](./screen-shots/vue/vue-chat.png)](./screen-shots/vue/vue-chat.png) |

</details>

## System Components

### FastAPI Backend (`/flexible-graphrag`)
- **REST API Server**: Provides endpoints for document ingestion, search, and AI query/chat
- **Hybrid Search Engine**: Combines vector similarity (RAG), fulltext (BM25), and graph traversal (GraphRAG)
- **Document Processing**: Advanced document conversion with Docling, LlamaParse, and LiteParse integration
- **Configurable Architecture**: Environment-based configuration for all components
- **Async Processing**: Background task processing with real-time progress updates

### MCP Server (`/flexible-graphrag-mcp`)  
- **MCP Client support**: Model Context Protocol server for Claude Desktop and other MCP clients
- **Full API Parity**: Tools like `ingest_documents()` support all 14 data sources with source-specific configs: filesystem, repositories (Alfresco, SharePoint, Box, CMIS, Nuxeo), cloud storage, web; `skip_graph` flag for all data sources; `paths` parameter for filesystem/Alfresco/CMIS; Alfresco also supports `nodeDetails` list (multi-select for KG Spaces)
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

## Data Sources

Flexible GraphRAG supports **14 different data sources** for ingesting documents into your knowledge base (Nuxeo missing from older screenshots):

<p align="center">
  <a href="./screen-shots/react/data-sources-1.jpeg">
    <img src="./screen-shots/react/data-sources-1.jpeg" alt="Data Sources" width="700">
  </a>
</p>

<p align="center">
  <a href="./screen-shots/auto-sync/auto-sync.png">
    <img src="./screen-shots/auto-sync/auto-sync.png" alt="Flexible GraphRAG data sources, processing tab, auto-sync document states in Postgres, Neo4j" width="700">
  </a>
</p>

<p align="center"><em>Flexible GraphRAG data sources, processing tab, auto-sync document states in Postgres (default pipeline, with auto incremental update system enabled), Neo4j shown (Qdrant, Elasticsearch not shown)</em></p>

### File & Upload Sources
1. **File Upload** - Direct file upload through web interface with drag & drop support


### Cloud Storage Sources
2. **Amazon S3** - AWS S3 bucket integration
3. **Google Cloud Storage (GCS)** - Google Cloud storage buckets
4. **Azure Blob Storage** - Microsoft Azure blob containers
5. **OneDrive** - Microsoft OneDrive personal/business storage
6. **Google Drive** - Google Drive file storage

### Enterprise Repository Sources
7. **Alfresco** - Alfresco ECM/content repository with two integration options:
   - **[KG Spaces ACA Extension](https://github.com/stevereiner/kg-spaces-aca)** - Integrates the Flexible GraphRAG Angular UI as an extension plugin within the Alfresco Content Application (ACA), enabling multi-select document/folder ingestion with nodeIds directly from the Alfresco interface
   - **Flexible GraphRAG Alfresco Data Source** - Direct integration using Alfresco paths (e.g., /Shared/GraphRAG, /Company Home/Shared/GraphRAG, or /Shared/GraphRAG/cmispress.txt)
8. **Nuxeo** - Nuxeo content repository (File and Note documents); basic / token (X-Authentication-Token) / OAuth2 auth, path or node selection, and real-time incremental sync via the Nuxeo audit event stream (Kafka)
9. **SharePoint** - Microsoft SharePoint document libraries
10. **Box** - Box.com cloud storage
11. **CMIS (Content Management Interoperability Services)** - Industry-standard content repository interface

### Web Sources
12. **Web Pages** - Extract content from web URLs
13. **Wikipedia** - Ingest Wikipedia articles by title or URL
14. **YouTube** - Process YouTube video transcripts

Each data source includes:
- **Configuration Forms**: Easy-to-use interfaces for credentials and settings
- **Progress Tracking**: Real-time per-file progress indicators
- **Flexible Authentication**: Support for various auth methods (API keys, OAuth, service accounts)

### Incremental Updates & Auto-Sync

**NEW!** Flexible GraphRAG supports **automatic incremental updates** (Optional) from most data sources, keeping your Vector, Search and Graph databases synchronized in real-time or near real-time:

| Data Source | Auto-Sync Support | Detection Method | Status | Notes |
|-------------|-------------------|------------------|--------|-------|
| **Alfresco** | ✅ Real-time | Apache ActiveMQ | Ready | |
| **Nuxeo** | ✅ Real-time | Nuxeo audit stream (Kafka) | Ready | |
| **Amazon S3** | ✅ Real-time | SQS event notifications | Ready | |
| **Azure Blob Storage** | ✅ Real-time | Change feed | Ready | |
| **Google Cloud Storage** | ✅ Real-time | Pub/Sub notifications | Ready | |
| **Google Drive** | ✅ Near real-time | Changes API (polling) | Ready | |
| **OneDrive** | ✅ Near real-time | MS Graph delta query | Ready | |
| **SharePoint** | ✅ Near real-time | MS Graph delta query | Ready | |
| **Box** | ✅ Near real-time | Events API (polling) | Ready | |
| **Local Filesystem** | ✅ Real-time | OS events (watchdog) | Ready | REST API and MCP Server only |
| **File Upload UI, CMIS, Web Pages, Wikipedia, YouTube** | ➖ Not supported | - | - | No support for incremental updates |

**Features**:
- **Modification Date Tracking**: Uses file modification timestamps (ordinal) to detect changes
- **Content Hash Optimization**: Skips reprocessing when file modification date changed but content hasn't
- **Dual Mechanism**: Event-driven streams (real-time) + periodic polling fallback
- **LlamaIndex Integration**: Uses proper abstractions for all databases
- **UI, REST API, MCP Server**: Setting up an auto update data source location can be done thru the 3 UIs, with the REST API, or with the MCP server

**Setup Requirements**:

Enable incremental updates in your `.env` file:
```bash
ENABLE_INCREMENTAL_UPDATES=true

# PostgreSQL database for state management
# By default, uses the pgvector database from docker-compose.yaml
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/postgres
```

**Note**: The incremental updates system uses PostgreSQL to track document state. The `docker-compose.yaml` includes a pgvector container that can be used both as a vector database option and for incremental updates state management. The database connection creates the necessary tables automatically on first use.

**Usage**: 
- Check the **"Enable auto change sync"** checkbox in the Processing tab when configuring your data source
- For **S3**: Also provide the "SQS Queue URL" for event notifications
- For **GCS**: Also provide the "Pub/Sub Subscription Name" for real-time updates

**PostgreSQL for State Management**:

The `docker/includes/postgres-pgvector.yaml` sets up two databases automatically on first start: `flexible_graphrag` (for optional pgvector vector storage) and `flexible_graphrag_incremental` (for incremental update state management, with its schema created automatically). pgAdmin is also configured at http://localhost:5050 with both databases pre-registered — just enter the master password `admin` when prompted, then use `password` for the server connection and save it. See [docs/DATABASES/POSTGRES-SETUP.md](docs/DATABASES/POSTGRES-SETUP.md) for details.

**Documentation**:
- System overview: [`docs/DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/README.md`](docs/DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/README.md)
- Quick start: [`docs/DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/QUICKSTART.md`](docs/DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/QUICKSTART.md)
- Detailed setup: [`docs/DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/SETUP-GUIDE.md`](docs/DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/SETUP-GUIDE.md)
- API reference: [`docs/DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/API-REFERENCE.md`](docs/DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/API-REFERENCE.md)
- PostgreSQL setup: [`docs/DATABASES/POSTGRES-SETUP.md`](docs/DATABASES/POSTGRES-SETUP.md)

**Scripts**:
- `scripts/incremental/sync-now.sh|.ps1|.bat` - Trigger immediate synchronization
- `scripts/incremental/set-refresh-interval.sh|.ps1|.bat` - Configure polling interval
- `scripts/incremental/TIMING-CONFIGURATION.md` - Timing configuration details
- `scripts/incremental/README.md` - Script usage documentation

### Document Processing Options

All data sources support three document parser options (full per-parser format matrix in [Supported File Formats](docs/DATA-SOURCES/DOC-PROCESSING/SUPPORTED-FILE-FORMATS.md)):

**Docling (Default)**:
- Open-source, local processing
- Free with no API costs
- **GPU acceleration** supported (CUDA/Apple Silicon) for 5-10x faster processing
- Built-in OCR for scanned documents and images — `DOCLING_OCR=true` + `DOCLING_OCR_ENGINE=auto|rapidocr|easyocr|tesseract_cli|tesserocr|ocrmac`
- Multi-language support (English, German, French, Spanish, Czech, Russian, Chinese, Japanese, etc.)
- Configured via: `DOCUMENT_PARSER=docling`
- `DOCLING_DEVICE=auto|cpu|cuda|mps` — control GPU vs CPU processing
- `SAVE_PARSING_OUTPUT=true` — save intermediate parsing results for inspection (works for all three parsers)
- `PARSER_FORMAT_FOR_EXTRACTION=auto|markdown|plaintext` — control format used for knowledge graph extraction
- See [Docling GPU + OCR Configuration Guide](docs/DATA-SOURCES/DOC-PROCESSING/DOCLING-GPU-CONFIGURATION.md) for setup details | [Quick Reference](docs/DATA-SOURCES/DOC-PROCESSING/DOCLING-GPU-CONFIGURATION.md#quick-reference-installation-commands)

**LlamaParse**:
- Cloud-based API service with advanced AI
- Multimodal parsing with Claude Sonnet 3.5
- Three modes available:
  - `parse_page_without_llm` - 1 credit/page
  - `parse_page_with_llm` - 3 credits/page (default)
  - `parse_page_with_agent` - 10-90 credits/page
- Configured via: `DOCUMENT_PARSER=llamaparse` + `LLAMAPARSE_API_KEY`
- Get your API key from [LlamaCloud](https://cloud.llamaindex.ai/)
- **New**: `SAVE_PARSING_OUTPUT=true` - Save parsed output and metadata for inspection
- **New**: `PARSER_FORMAT_FOR_EXTRACTION=auto|markdown|plaintext` - Control format used for knowledge graph extraction

**LiteParse**:
- Open-source, local processing (Rust/PyO3) — free, no API key
- Natively parses PDFs with bundled Tesseract OCR; `.txt`/`.md` read directly
- Office formats need **LibreOffice**, images need **ImageMagick** — see [Supported File Formats](docs/DATA-SOURCES/DOC-PROCESSING/SUPPORTED-FILE-FORMATS.md#liteparse-free-local-lightweight)
- Optional complexity-based routing of scanned/complex docs to Docling or LlamaParse via `LITEPARSE_COMPLEX_ROUTING`
- Configured via: `DOCUMENT_PARSER=liteparse`; install `uv pip install liteparse`
- Supports `SAVE_PARSING_OUTPUT` and `PARSER_FORMAT_FOR_EXTRACTION` like the other parsers

## Supported File Formats

Flexible GraphRAG processes **documents, images, and audio** across its three parsers:

- **Documents:** PDF (`.pdf`); Microsoft Office + legacy (`.docx`/`.xlsx`/`.pptx`, `.doc`/`.xls`/`.ppt`); web (`.html`/`.htm`/`.xhtml`); data (`.csv`/`.tsv`/`.json`/`.xml`); documentation (`.md`/`.markdown`/`.asciidoc`/`.rtf`/`.txt`/`.epub`)
- **Images:** `.png`/`.jpg`/`.jpeg`/`.gif`/`.bmp`/`.webp`/`.tiff`/`.tif`
- **Audio:** `.wav`/`.mp3`/`.mp4`/`.m4a` (speech recognition / transcription)

Capabilities vary by parser — **Docling** and **LlamaParse** handle all of the above natively (advanced layout/table/formula analysis, configurable OCR, VLM/multimodal, ASR); **LiteParse** parses PDFs natively and needs LibreOffice for Office formats / ImageMagick for images. Both markdown and plaintext are saved, and the best is auto-selected for knowledge-graph extraction, embeddings, and search (markdown for tables, plaintext for text-heavy docs; override with `PARSER_FORMAT_FOR_EXTRACTION`).

**Full per-parser matrix, OCR/VLM options, and output formats: [Supported File Formats](docs/DATA-SOURCES/DOC-PROCESSING/SUPPORTED-FILE-FORMATS.md).**

## Database Configuration

Flexible GraphRAG uses three types of databases for its hybrid search capabilities. Each can be configured independently via environment variables.

### Search Databases (Full-Text Search)

Set `SEARCH_DB` to select the store and `SEARCH_BACKEND=llamaindex` or `langchain` for the framework.

- **BM25 (Built-in)**: Local in-memory BM25 full-text search with TF-IDF ranking
  - Dashboard: None (file-based)
  - Configuration:
    ```bash
    SEARCH_DB=bm25
    BM25_SEARCH_DB_CONFIG={"persist_dir": "./bm25_index"}
    ```

- **Elasticsearch**: Enterprise search engine with advanced analyzers, faceted search, and real-time analytics
  - Dashboard: Kibana (http://localhost:5601)
  - Configuration:
    ```bash
    SEARCH_DB=elasticsearch
    ELASTICSEARCH_SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}
    ```

- **OpenSearch**: AWS-led open-source fork with native hybrid scoring (vector + BM25) and k-NN algorithms
  - Dashboard: OpenSearch Dashboards (http://localhost:5601)
  - Configuration:
    ```bash
    SEARCH_DB=opensearch
    OPENSEARCH_SEARCH_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search"}
    ```

- **None**: Disable full-text search (vector search only)
  - Configuration:
    ```bash
    SEARCH_DB=none
    ```

### Vector Databases (Semantic Search)

Set `VECTOR_DB` to select the store and `VECTOR_BACKEND=llamaindex` or `langchain` for the framework.

When switching embedding models, delete existing vector indexes — dimensions differ by provider. See [docs/DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md](docs/DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md) for cleanup instructions.

#### Supported Vector Databases

- **Neo4j**: Can be used as vector database with separate vector configuration
  - Dashboard: Neo4j Browser (http://localhost:7474)
  - Configuration:
    ```bash
    VECTOR_DB=neo4j
    NEO4J_VECTOR_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "your_password", "index_name": "hybrid_search_vector"}
    ```

- **Qdrant**: Dedicated vector database with advanced filtering
  - Dashboard: Qdrant Web UI (http://localhost:6333/dashboard)
  - Configuration:
    ```bash
    VECTOR_DB=qdrant
    QDRANT_VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search"}
    ```

- **Elasticsearch**: Can be used as vector database with separate vector configuration
  - Dashboard: Kibana (http://localhost:5601)
  - Configuration:
    ```bash
    VECTOR_DB=elasticsearch
    ELASTICSEARCH_VECTOR_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search_vectors"}
    ```

- **OpenSearch**: Can be used as vector database with separate vector configuration
  - Dashboard: OpenSearch Dashboards (http://localhost:5601)
  - Configuration:
    ```bash
    VECTOR_DB=opensearch
    OPENSEARCH_VECTOR_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search_vectors"}
    ```

- **Chroma**: Open-source vector database with dual deployment modes
  - Dashboard: Swagger UI (http://localhost:8001/docs/) (HTTP mode)
  - Configuration (Local Mode):
    ```bash
    VECTOR_DB=chroma
    CHROMA_VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}
    ```
  - Configuration (HTTP Mode):
    ```bash
    VECTOR_DB=chroma
    CHROMA_VECTOR_DB_CONFIG={"host": "localhost", "port": 8001, "collection_name": "hybrid_search"}
    ```

- **Milvus**: Cloud-native, scalable vector database for similarity search
  - Dashboard: Attu (http://localhost:3003)
  - Configuration:
    ```bash
    VECTOR_DB=milvus
    MILVUS_VECTOR_DB_CONFIG={"host": "localhost", "port": 19530, "collection_name": "hybrid_search"}
    ```

- **Weaviate**: Vector search engine with semantic capabilities and data enrichment
  - Dashboard: Weaviate Console (http://localhost:8086/console)
  - Configuration:
    ```bash
    VECTOR_DB=weaviate
    WEAVIATE_VECTOR_DB_CONFIG={"url": "http://localhost:8086", "index_name": "HybridSearch"}
    ```

- **Pinecone**: Managed vector database service optimized for real-time applications
  - Dashboard: Pinecone Console (web-based)
  - Configuration:
    ```bash
    VECTOR_DB=pinecone
    PINECONE_VECTOR_DB_CONFIG={"api_key": "your_api_key", "region": "us-east-1", "cloud": "aws", "index_name": "hybrid-search"}
    ```

- **PostgreSQL**: Traditional database with pgvector extension for vector similarity search
  - Dashboard: pgAdmin (http://localhost:5050)
  - Configuration:
    ```bash
    VECTOR_DB=postgres
    POSTGRES_VECTOR_DB_CONFIG={"host": "localhost", "port": 5433, "database": "postgres", "username": "postgres", "password": "your_password"}
    ```

- **LanceDB**: Modern, lightweight vector database designed for high-performance ML applications
  - Dashboard: LanceDB Viewer (http://localhost:3005)
  - Configuration:
    ```bash
    VECTOR_DB=lancedb
    LANCEDB_VECTOR_DB_CONFIG={"uri": "./lancedb", "table_name": "hybrid_search"}
    ```

#### RAG without GraphRAG

For faster document ingest processing (no graph extraction), and hybrid search with only full text + vector, configure:
```bash
VECTOR_DB=qdrant       # Any vector store
SEARCH_DB=elasticsearch  # Any search engine
PG_GRAPH_DB=none
```


### Property Graph Databases (Knowledge Graph / GraphRAG)

Set `PG_GRAPH_DB` to select the store and `GRAPH_BACKEND=llamaindex` or `langchain` for the framework where both are supported. **LangChain-only** stores (ArangoDB, Apache AGE, HugeGraph, SurrealDB, TigerGraph, Cosmos Gremlin) route property-graph ingestion and retrieval through LangChain adapters regardless of other env defaults. **LlamaIndex-only** stores (Spanner): when `PG_GRAPH_DB=spanner`, startup forces `GRAPH_BACKEND=llamaindex` and ignores `GRAPH_BACKEND=langchain`.

- **Neo4j Property Graph**: Primary knowledge graph storage with Cypher querying
  - Dashboard: Neo4j Browser (http://localhost:7474)
  - Configuration:
    ```bash
    PG_GRAPH_DB=neo4j
    NEO4J_GRAPH_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "your_password"}
    ```

- **ArcadeDB**: Multi-model database supporting graph, document, key-value, and search with SQL and Cypher
  - Dashboard: ArcadeDB Studio (http://localhost:2480)
  - Configuration:
    ```bash
    PG_GRAPH_DB=arcadedb
    ARCADEDB_GRAPH_DB_CONFIG={"host": "localhost", "port": 2480, "username": "root", "password": "password", "database": "flexible_graphrag", "query_language": "sql"}
    ```

- **FalkorDB**: High-performance graph database using GraphBLAS; purpose-built for LLM / GraphRAG
  - Dashboard: FalkorDB Browser (http://localhost:3001)
  - Configuration:
    ```bash
    PG_GRAPH_DB=falkordb
    FALKORDB_GRAPH_DB_CONFIG={"url": "falkor://localhost:6379", "database": "falkor"}
    ```

- **Ladybug**: Embedded property graph database (Cypher, single `.lbug` file) with optional structured schema and HNSW vector index on chunks; Explorer UI via Docker (port 7003)
  - Configuration:
    ```bash
    PG_GRAPH_DB=ladybug
    LADYBUG_GRAPH_DB_CONFIG={"db_dir": "./ladybug", "db_file": "database.lbug", "use_vector_index": true, "has_structured_schema": false, "strict_schema": false}
    ```

- **MemGraph**: Real-time graph database with streaming support and advanced graph algorithms
  - Dashboard: MemGraph Lab (http://localhost:3002)
  - Configuration:
    ```bash
    PG_GRAPH_DB=memgraph
    MEMGRAPH_GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", "username": "", "password": ""}
    ```

- **NebulaGraph**: Distributed graph database for large-scale data with horizontal scalability
  - Dashboard: NebulaGraph Studio (http://localhost:7001)
  - Configuration:
    ```bash
    PG_GRAPH_DB=nebula
    NEBULA_GRAPH_DB_CONFIG={"space": "flexible_graphrag", "host": "localhost", "port": 9669, "username": "root", "password": "nebula"}
    ```

- **Amazon Neptune**: Fully managed graph database service supporting property graph and RDF models
  - Dashboard: Graph-Explorer (http://localhost:3007) or Neptune Workbench (AWS Console)
  - Configuration:
    ```bash
    PG_GRAPH_DB=neptune
    NEPTUNE_GRAPH_DB_CONFIG={"host": "your-cluster.region.neptune.amazonaws.com", "port": 8182}
    ```

- **Amazon Neptune Analytics**: Serverless graph analytics with openCypher support
  - Dashboard: Graph-Explorer (http://localhost:3007) or Neptune Workbench (AWS Console)
  - Configuration:
    ```bash
    PG_GRAPH_DB=neptune_analytics
    NEPTUNE_ANALYTICS_GRAPH_DB_CONFIG={"graph_identifier": "g-xxxxx", "region": "us-east-1"}
    ```

- **Google Cloud Spanner Graph** *(LlamaIndex only)*: Managed relational + property graph (GQL). Uses `llama-index-spanner` — install with `uv pip install -e ".[spanner-extras]"` then `uv pip uninstall llama-index` (see [Optional](#optional) under Prerequisites). LangChain is not supported for this store (`langchain-google-spanner` pins incompatible `langchain-core`).
  - Setup: [docs/DATABASES/GRAPH-DATABASES/SPANNER-SETUP.md](docs/DATABASES/GRAPH-DATABASES/SPANNER-SETUP.md)
  - Configuration:
    ```bash
    PG_GRAPH_DB=spanner
    # GRAPH_BACKEND=llamaindex is forced for Spanner (LlamaIndex-only); langchain is ignored
    SPANNER_GRAPH_DB_CONFIG={"project_id": "my-gcp-project", "instance_id": "my-spanner-instance", "database_id": "my-database", "graph_name": "knowledge_graph", "credentials_file": "./gcs.json"}
    ```

- **ArangoDB** *(LangChain only)*: Multi-model database with AQL graph queries
  - Dashboard: ArangoDB Web UI (http://localhost:8529)
  - Configuration:
    ```bash
    PG_GRAPH_DB=arangodb
    ARANGODB_GRAPH_DB_CONFIG={"url": "http://localhost:8529", "database": "flexible_graphrag", "username": "root", "password": "password"}
    ```

- **Apache AGE** *(LangChain only)*: PostgreSQL extension for graph data via Cypher
  - Dashboard: pgAdmin (http://localhost:5050)
  - Configuration:
    ```bash
    PG_GRAPH_DB=apache_age
    APACHE_AGE_GRAPH_DB_CONFIG={"host": "localhost", "port": 5434, "database": "flexible_graphrag_age", "username": "postgres", "password": "password", "graph_name": "knowledge_graph"}
    ```

- **HugeGraph** *(LangChain only)*: Distributed graph database with Gremlin and openCypher
  - Dashboard: HugeGraph Hubble (http://localhost:8085)
  - Configuration:
    ```bash
    PG_GRAPH_DB=hugegraph
    HUGEGRAPH_GRAPH_DB_CONFIG={"host": "localhost", "port": 8082, "database": "hugegraph"}
    ```

- **SurrealDB** *(LangChain only)*: Multi-model database with SurrealQL graph queries
  - Dashboard: Surrealist (http://localhost:8011)
  - Configuration:
    ```bash
    PG_GRAPH_DB=surrealdb
    SURREALDB_GRAPH_DB_CONFIG={"url": "ws://localhost:8010/rpc", "namespace": "test", "database": "flexible_graphrag", "username": "root", "password": "root"}
    ```

- **TigerGraph** *(LangChain only)*: Distributed graph database with GSQL
  - Dashboard: GraphStudio (http://localhost:14240)
  - Configuration:
    ```bash
    PG_GRAPH_DB=tigergraph
    TIGERGRAPH_GRAPH_DB_CONFIG={"host": "http://localhost", "port": 14240, "restpp_port": 9002, "database": "MyGraph", "username": "tigergraph", "password": "tigergraph"}
    ```

- **Cosmos Gremlin** *(LangChain only)*: Azure Cosmos DB for Gremlin API
  - Configuration:
    ```bash
    PG_GRAPH_DB=cosmos_gremlin
    COSMOS_GREMLIN_GRAPH_DB_CONFIG={"url": "ws://localhost:8182/gremlin"}
    ```

- **None**: Disable knowledge graph extraction for RAG-only mode
  - Configuration:
    ```bash
    PG_GRAPH_DB=none
    ```

## Ontology and RDF Support

Flexible GraphRAG supports RDF/RDFS/OWL ontologies to guide knowledge graph extraction, with optional RDF graph store backends. Ontology-guided extraction works with **any** configured store — property graph, RDF graph store, or both.

- Load OWL/RDFS ontologies (`owl:Class`, `owl:ObjectProperty`, `owl:DatatypeProperty`, `rdfs:domain`, `rdfs:range`) to constrain entity/relation extraction; OWL is supported but not required
- Works with all 15 property graph databases — no RDF store required to use ontology-guided extraction
- Full pipeline for all 4 RDF graph stores: UI document ingest → KG extraction → RDF storage; auto incremental sync; Hybrid Search and AI Query/Chat fuse RDF store results alongside vector, BM25, and property graph results
- SPARQL 1.1 queries; RDF 1.2 triple terms and relation annotations (`{| |}` syntax); XSD-typed literals from OWL `DatatypeProperty` ranges

**RDF Graph Store Configuration** — set `RDF_GRAPH_DB` to select the store (all four support RDF 1.2 triple terms; Neptune is AWS-managed—no local compose include):

- **Apache Jena Fuseki** — SPARQL 1.1 server; dashboard: http://localhost:3030
  ```bash
  RDF_GRAPH_DB=fuseki
  FUSEKI_BASE_URL=http://localhost:3030
  FUSEKI_DATASET=flexible-graphrag
  ```

- **Ontotext GraphDB** — enterprise RDF store with OWL reasoning; dashboard: http://localhost:7200
  ```bash
  RDF_GRAPH_DB=graphdb
  GRAPHDB_BASE_URL=http://localhost:7200
  GRAPHDB_REPOSITORY=flexible-graphrag
  GRAPHDB_USERNAME=admin
  GRAPHDB_PASSWORD=admin
  ```

- **Oxigraph** — lightweight local store, native RDF 1.2; dashboard: http://localhost:7878
  ```bash
  RDF_GRAPH_DB=oxigraph
  OXIGRAPH_URL=http://localhost:7878
  ```

- **Amazon Neptune RDF** — managed SPARQL 1.1 on Neptune (same cluster can host property graph and RDF; IAM SigV4 auth). See [Neptune RDF setup](docs/DATABASES/GRAPH-DATABASES/NEPTUNE-SETUP.md).
  ```bash
  RDF_GRAPH_DB=neptune_rdf
  NEPTUNE_RDF_HOST=db-neptune-1.cluster-xxxxxxxxxxxx.us-east-1.neptune.amazonaws.com
  NEPTUNE_RDF_PORT=8182
  NEPTUNE_RDF_REGION=us-east-1
  NEPTUNE_RDF_USE_IAM_AUTH=true
  NEPTUNE_RDF_USE_HTTPS=true
  # Optional explicit keys (else default AWS credential chain):
  # NEPTUNE_RDF_AWS_ACCESS_KEY_ID=
  # NEPTUNE_RDF_AWS_SECRET_ACCESS_KEY=
  ```

- **None** — disable RDF graph store:
  ```bash
  RDF_GRAPH_DB=none
  ```

**Docker Setup:** Uncomment local RDF store includes in `docker-compose.yaml` (Fuseki, GraphDB, Oxigraph):
```yaml
includes:
  # - includes/jena-fuseki.yaml
  # - includes/ontotext-graphdb.yaml
  # - includes/oxigraph.yaml
```

**Complete Documentation:** [docs/DATABASES/RDF/RDF-ONTOLOGY-SUPPORT.md](docs/DATABASES/RDF/RDF-ONTOLOGY-SUPPORT.md) | [docs/DATABASES/RDF/RDF-STORE-USER-GUIDE.md](docs/DATABASES/RDF/RDF-STORE-USER-GUIDE.md)

## Framework Configuration

Every pipeline stage can independently run on LlamaIndex or LangChain via env var pickers:

| Variable | Options | Description |
|---|---|---|
| `GRAPH_BACKEND` | `llamaindex` \| `langchain` | Property graph store and KG retrieval |
| `VECTOR_BACKEND` | `llamaindex` \| `langchain` | Vector store adapter |
| `SEARCH_BACKEND` | `llamaindex` \| `langchain` | Full-text search adapter |
| `CHUNKER_BACKEND` | `llamaindex` \| `langchain` | Document chunking / splitting |
| `KG_EXTRACTOR_BACKEND` | `llamaindex` \| `langchain` | KG extraction from chunks |
| `RETRIEVAL_FUSION` | `llamaindex` \| `langchain` | Result fusion across retrievers |

LangChain-only graph stores (ArangoDB, Apache AGE, HugeGraph, SurrealDB, TigerGraph, Cosmos Gremlin) auto-select `GRAPH_BACKEND=langchain`. LlamaIndex-only Spanner (`PG_GRAPH_DB=spanner`) forces `GRAPH_BACKEND=llamaindex` at startup and ignores `GRAPH_BACKEND=langchain` (no LangChain adapter).

**Complete Documentation:** [docs/ADVANCED/LANGCHAIN/LANGCHAIN-GRAPH-INTEGRATION.md](docs/ADVANCED/LANGCHAIN/LANGCHAIN-GRAPH-INTEGRATION.md)

## LLM and Embedding Configuration

Set via `LLM_PROVIDER` and provider-specific environment variables.

### Supported LLM Providers

1. **OpenAI** - gpt-4o-mini (default), gpt-4o, gpt-4.1-mini, gpt-5-mini, etc.
2. **Ollama** - Local deployment (llama3.2, llama3.1, qwen2.5, gpt-oss, etc.)
3. **Azure OpenAI** - Azure-hosted OpenAI models
4. **Google Gemini** - gemini-2.5-flash, gemini-3-flash-preview, gemini-3.1-pro-preview, etc.
5. **Anthropic Claude** - claude-sonnet-4-5, claude-haiku-4-5, etc.
6. **Google Vertex AI** - Google Cloud-hosted Vertex AI Platform Gemini models
7. **Amazon Bedrock** - Amazon Nova, Titan, Anthropic Claude, Meta Llama, Mistral AI, etc.
8. **Groq** - Fast low-cost LPU inference, low latency: OpenAI GPT-OSS, Meta Llama (4, 3.3, 3.1), Qwen3, Kimi, etc.
9. **Fireworks AI** - More choices, fine-tuning: Meta, Qwen, Mistral AI, DeepSeek, OpenAI GPT-OSS, Kimi, GLM, MiniMax, etc.
10. **OpenAI-Compatible** (`openai_like`) - Any OpenAI-compatible endpoint (LM Studio, LocalAI, Llamafile, vLLM, etc.)
11. **OpenRouter** - 200+ models via unified API (openai/gpt-4o-mini, anthropic/claude, meta-llama, etc.)
12. **LiteLLM Proxy** - 100+ providers via LiteLLM proxy; sample config in `scripts/litellm_config.yaml`
13. **vLLM** - High-performance local inference server (Linux/macOS; use `openai_like` on Windows)

### LLM Provider Configuration

See [docs/LLM/LLM-EMBEDDING-CONFIG.md](docs/LLM/LLM-EMBEDDING-CONFIG.md) for all 13 providers with detailed configuration examples.

**OpenAI** (recommended):
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o-mini
```

**Ollama** (local):
```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:latest
```

**Azure OpenAI**:
```bash
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_ENGINE=gpt-4o-mini
```

### Embedding Configuration

Set `EMBEDDING_KIND` to choose the embedding provider — independent of the LLM provider. All 13 LLM providers are also supported as embedding providers. See [docs/LLM/LLM-EMBEDDING-CONFIG.md](docs/LLM/LLM-EMBEDDING-CONFIG.md) for all providers and options.

**OpenAI**:
```bash
EMBEDDING_KIND=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=your_api_key
```

**Ollama** (local):
```bash
EMBEDDING_KIND=ollama
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434
```

**Azure OpenAI**:
```bash
EMBEDDING_KIND=azure_openai
AZURE_EMBEDDING_MODEL=text-embedding-3-small
AZURE_EMBEDDING_DEPLOYMENT=your_deployment_name
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
```

**Common embedding dimensions:**
- OpenAI: 1536 (text-embedding-3-small), 3072 (text-embedding-3-large)
- Ollama: 384 (all-minilm), 768 (nomic-embed-text), 1024 (mxbai-embed-large)
- Google: 768 (gemini-embedding-2-preview)
- Bedrock: 1024 (amazon.titan-embed-text-v2:0)

When switching embedding models, delete existing vector indexes. See [docs/DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md](docs/DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md) for cleanup instructions.

### Ollama Configuration

When using Ollama, configure system-wide environment variables before starting the Ollama service:

**Key requirements**:
- Configure environment variables **system-wide** (not in Flexible GraphRAG `.env` file)
- `OLLAMA_NUM_PARALLEL=4` for optimal performance (or 1-2 if resource constrained)
- Always restart Ollama service after changing environment variables

See [docs/LLM/OLLAMA-CONFIGURATION.md](docs/LLM/OLLAMA-CONFIGURATION.md) for complete setup instructions including platform-specific steps and performance optimization.



## Prerequisites

### Required
- Python 3.12, 3.13, or 3.14 (as specified in `pyproject.toml`)
- UV package manager (for dependency management)
- Node.js 22.x (for UI clients)
- npm (package manager)
- Search database: Elasticsearch or OpenSearch
- Vector database: Qdrant (or other supported vector databases)
- Property graph database: Neo4j (or other supported property graph databases) - unless using vector-only RAG
- OpenAI with API key (recommended) or Ollama (for LLM processing)

**Note**: The `docker/docker-compose.yaml` file can provide all these databases via Docker containers.

### Install

```bash
cd flexible-graphrag
uv pip install -e .
```

### Optional (see flexible-graphrag/pyproject.toml for all options)
- **LangChain 1.x integration** — Optional peer stack alongside LlamaIndex (extras pin **`langchain>=1.0`** and the LangChain **1.x** line, not legacy 0.3):
  - `uv pip install -e ".[langchain]"` — core LC extras: property graph stores via `langchain-community` where supported, 10 vector stores, 3 search stores, RDF SPARQL retrieval, native LC LLM/embedding clients for all 13 providers, KG extraction via `langchain-experimental`, retrieval fusion
  - `uv pip install --override extras-overrides.txt -e ".[langchain,langchain-extras]"` — adds Neo4j (LC), PostgreSQL pgvector, ArcadeDB, ArangoDB, Cosmos Gremlin, HugeGraph, TigerGraph, and related dependencies (see `pyproject.toml` group `langchain-extras`)
  - **Apache AGE** — property graph via LangChain needs the separate **`age-extras`** group (BAEM1N `langchain-age` driver):
    ```bash
    uv pip install --override extras-overrides.txt -e ".[langchain,langchain-extras,age-extras]"
    python scripts/patch_langchain_age.py
    ```
    Run `patch_langchain_age.py` on **Python 3.14+** (required); on 3.12/3.13 it is harmless.
  - `uv pip install -e ".[spanner-extras]"` — adds LI-only Spanner support via `llama-index-spanner`. **Note:** `llama-index-spanner` declares `llama-index` (the meta-package) as a dependency, which `uv` will install. Uninstall it immediately after: `uv pip uninstall llama-index` — having both `llama-index` and `llama-index-core` installed simultaneously can cause version conflicts, as the meta-package pins versions of `llama-index-*` component packages that can clash with the versions already required by this project
  - SurrealDB — two-step install required (resolver conflict):
    ```bash
    uv pip install -e ".[surrealdb-extras]"
    uv pip install "surrealdb>=2.0" "langchain-core>=1.3"
    ```
- **ArcadeDB embedded mode** (`uv pip install arcadedb-embedded>=26.3.2`) — runs ArcadeDB in-process; includes a bundled JVM, no separate Java install needed; latest release: 26.3.2
- **Enterprise Repositories**:
  - Alfresco repository - only if using Alfresco data source
  - SharePoint - requires SharePoint access
  - Box - requires Box Business account (3 users minimum), API keys
  - CMIS-compliant repository (e.g., Alfresco) - only if using CMIS data source
- **Cloud Storage** (requires accounts and API keys/credentials):
  - Amazon S3 - requires AWS account and access keys
  - Google Cloud Storage - requires GCP account and service account credentials
  - Google Drive - requires Google Cloud account and OAuth credentials or service account
  - Azure Blob Storage - requires Azure account and connection string or account keys
  - Microsoft OneDrive - requires OneDrive for Business (not personal OneDrive)
  - **Note**: SharePoint and OneDrive for Business are also available with a M365 Developer Program sandbox (with full Visual Studio annual subscription, not monthly).
- **File Upload** (no account required):
  - Web interface with file dialog (drag & drop or click to select)
- **Web Sources** (no account required):
  - Web pages, Wikipedia, YouTube - no accounts needed

## Setup

### 🐳 Docker Deployment

Docker deployment offers multiple scenarios. Before deploying any scenario, set up your environment files:

**Environment File Setup (Required for All Scenarios):**

1. **Backend Configuration** (`.env`):
   ```bash
   # Navigate to backend directory
   cd flexible-graphrag
   
   # Linux/macOS
   cp env-sample.txt .env
   
   # Windows Command Prompt
   copy env-sample.txt .env
   
   # Edit .env with your database credentials, API keys, and settings
   # Then return to project root
   cd ..
   ```

2. **Docker Configuration** (`docker/.env`):
   ```bash
   # Navigate to docker directory
   cd docker
   
   # Linux/macOS
   cp docker-env-sample.txt .env
   
   # Windows Command Prompt
   copy docker-env-sample.txt .env
   
   # Edit docker/.env for Docker-specific overrides (network addresses, service names)
   # Stay in docker directory for next steps
   ```

---

#### Scenario A: Databases in Docker, App Standalone (Hybrid)

**Configuration Setup:**
```bash
# If not already in docker directory from previous step:
# cd docker

# Edit docker-compose.yaml to uncomment/comment services as needed
# Scenario A setup in docker-compose.yaml:
# Keep these services uncommented (default setup):
  - includes/neo4j.yaml
  - includes/qdrant.yaml
  - includes/elasticsearch-dev.yaml
  - includes/kibana-simple.yaml

# Keep these services commented out:
# - includes/app-stack.yaml       # Must be commented out for Scenario A
# - includes/proxy.yaml           # Must be commented out for Scenario A
# - All other services remain commented unless you want a different vector database, 
#   graph database, OpenSearch for search, or Alfresco included
```

**Deploy Services:**
```bash
# From the docker directory
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
```

#### Scenario B: Full Stack in Docker (Complete)

**Configuration Setup:**
```bash
# If not already in docker directory from previous step:
# cd docker

# Edit docker-compose.yaml to uncomment/comment services as needed
# Scenario B setup in docker-compose.yaml:
# Keep these services uncommented:
  - includes/neo4j.yaml
  - includes/qdrant.yaml
  - includes/elasticsearch-dev.yaml
  - includes/kibana-simple.yaml
  - includes/app-stack.yaml       # Backend and UI in Docker
  - includes/proxy.yaml           # NGINX reverse proxy

# Keep other services commented out unless you want a different vector database,
# graph database, OpenSearch for search, or Alfresco included
```

**Deploy Services:**
```bash
# From the docker directory
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
```

**Scenario B Service URLs:**
- **Angular UI**: http://localhost:8070/ui/angular/
- **React UI**: http://localhost:8070/ui/react/  
- **Vue UI**: http://localhost:8070/ui/vue/
- **Backend API**: http://localhost:8070/api/

#### Other Deployment Scenarios

**Scenario C: Fully Standalone** - Not using docker-compose at all
- Standalone backend, standalone UIs, all databases running separately
- Configure all database connections in `flexible-graphrag/.env`

**Scenario D: Backend/UIs in Docker, Databases External**
- Using docker-compose for backend and UIs (app-stack + proxy)
- Some or all databases running separately (same docker-compose, other local Docker, cloud/remote servers)
- Configure database connections in `docker/.env`: Backend in Docker reads this file
  - For databases in same docker-compose: Use service names (e.g., `neo4j:7687`, `qdrant:6333`)
  - For databases in other local Docker containers: Use `host.docker.internal:PORT`
  - For remote/cloud databases: Use actual hostnames/IPs

**Scenario E: Mixed Docker/Standalone**
- Standalone backend and UIs
- Running some databases in Docker (local) and some outside (cloud, external servers)
- Configure all database connections in `flexible-graphrag/.env`: Use `host.docker.internal:PORT` for locally-running Docker databases, use actual hostnames/IPs for remote Docker or non-Docker databases

#### Docker Control and Configuration

**Managing Docker services:**

```bash
# Navigate to docker directory (if not already there)
cd docker

# Create and start services (recreates if configuration changed)
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d

# Stop services (keeps containers)
docker-compose -f docker-compose.yaml -p flexible-graphrag stop

# Start stopped services
docker-compose -f docker-compose.yaml -p flexible-graphrag start

# Stop and remove services
docker-compose -f docker-compose.yaml -p flexible-graphrag down

# View logs
docker-compose -f docker-compose.yaml -p flexible-graphrag logs -f

# Restart after configuration changes
docker-compose -f docker-compose.yaml -p flexible-graphrag down
# Edit docker-compose.yaml, docker/.env, or includes/app-stack.yaml as needed
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
```

**Configuration:**
- **Modular deployment**: Comment/uncomment services in `docker/docker-compose.yaml`
- **Backend configuration** (Scenario B): Backend uses `flexible-graphrag/.env` with `docker/.env` for Docker-specific overrides (like using service names instead of localhost). No configuration needed in `app-stack.yaml`

See [docker/README.md](./docker/README.md) for detailed Docker configuration.

### 🔧 Local Development Setup (Scenario A)

**Note**: Skip this entire section if using Scenario B (Full Stack in Docker).

#### Environment Configuration

**Create environment file** (cross-platform):
```bash
# Linux/macOS
cp flexible-graphrag/env-sample.txt flexible-graphrag/.env

# Windows Command Prompt  
copy flexible-graphrag\env-sample.txt flexible-graphrag\.env
```
Edit `.env` with your database credentials and API keys.

### Python Backend Setup (Standalone)

#### Option A — Install from PyPI package (Quickstart)

```bash
# 1. Create and activate a virtual environment
uv venv venv-3.13 --python 3.13
venv-3.13\Scripts\Activate   # Windows
source venv-3.13/bin/activate  # Linux/macOS

# 2. Install flexible-graphrag
uv pip install flexible-graphrag

# 3. Optionally install ArcadeDB embedded mode support (includes bundled JVM, no Java install needed)
uv pip install arcadedb-embedded>=26.3.2

# 3a. Optional dependency groups, for example:
uv pip install "flexible-graphrag[langchain]"
# Other extras ([langchain-extras], [age-extras], overrides): see source README, Prerequisites > Optional.

# 4. Create .env from the sample (copy from the source repo or download env-sample.txt)
copy env-sample.txt .env   # Windows
cp env-sample.txt .env     # Linux/macOS
# Edit .env with your LLM API keys and database settings

# 5. Start your databases (docker compose or standalone)
docker compose -f docker/docker-compose.yml up -d

# 6. Run the backend
flexible-graphrag
# or: uv run start.py
```

#### Option B — Install from source (editable)

1. Navigate to the backend directory:
   ```bash
   cd flexible-graphrag
   ```

2. Create and activate a virtual environment, then install in editable mode:
   ```bash
   uv venv venv-3.13 --python 3.13
   venv-3.13\Scripts\Activate   # Windows
   source venv-3.13/bin/activate  # Linux/macOS
   uv pip install -e .

   # see flexible-graphrag/pyproject.toml for all options
   # --- Optional: dependency groups from pyproject.toml [project.optional-dependencies] ---
   # LangChain (peer framework; use overrides when combining with langchain-extras)
   uv pip install -e ".[langchain]"
   uv pip install --override extras-overrides.txt -e ".[langchain,langchain-extras]"
   uv pip install --override extras-overrides.txt -e ".[langchain,langchain-extras,age-extras]"
   python scripts/patch_langchain_age.py
   uv pip install --override extras-overrides.txt -e ".[surrealdb-extras]"
   uv pip install "surrealdb>=2.0" "langchain-core>=1.3"
   uv pip install --override extras-overrides.txt -e ".[spanner-extras]"
   uv pip uninstall llama-index

   # RDF extras (base install already includes rdflib/pyoxigraph; use these if you need the named groups)
   uv pip install -e ".[rdf]"
   uv pip install -e ".[rdf-full]"

   # Observability
   uv pip install -e ".[observability]"
   uv pip install -e ".[observability-openlit]"
   uv pip install -e ".[observability-dual]"

   # Development tests / tooling
   uv pip install -e ".[dev]"

   # Docling OCR backends (see DOCLING_OCR in env-sample)
   uv pip install -e ".[docling-ocr-easyocr]"
   uv pip install -e ".[docling-ocr-tesserocr]"
   uv pip install -e ".[docling-ocr-ocrmac]"   # macOS only

   # Embedded ArcadeDB (not a bracket extra; bundled JVM)
   uv pip install arcadedb-embedded>=26.3.2
   ```

   **uv-managed venv** (alternative): change `managed = false` to `managed = true` in `pyproject.toml` `[tool.uv]` section, then just run `uv pip install -e .`.

   Notes: run only the optional lines you need. For **`age-extras`**, run **`patch_langchain_age.py`** on **Python 3.14+** (safe on 3.12/3.13). For **`surrealdb-extras`**, keep the follow-up **`surrealdb` / `langchain-core`** upgrades. For **`spanner-extras`**, **`uv pip uninstall llama-index`** removes the meta-package pulled in by **`llama-index-spanner`**. See **### Optional** under **Prerequisites** for context.

   **Windows Note**: If installation fails with "Microsoft Visual C++ 14.0 or greater is required" error, install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (required for compiling Docling dependencies). Select "Desktop development with C++" during installation.

3. Create a `.env` file by copying the sample and customizing:
   ```bash
   cp env-sample.txt .env   # Linux/macOS
   copy env-sample.txt .env  # Windows
   ```

   Edit `.env` with your specific configuration. See [docs/GETTING-STARTED/ENVIRONMENT-CONFIGURATION.md](docs/GETTING-STARTED/ENVIRONMENT-CONFIGURATION.md) for detailed setup guide.

**Note**: The system requires Python 3.12, 3.13, or 3.14 as specified in `pyproject.toml` (requires-python = ">=3.12,<3.15"). Python 3.12 and 3.13 are fully tested. Python 3.14 works with the patches applied automatically in `main.py` at startup. Virtual environment management is controlled by `managed = false` in `pyproject.toml` `[tool.uv]` section (you control venv creation and naming).

4. Start the backend:
   ```bash
   flexible-graphrag        # after uv pip install flexible-graphrag
   # or: uv run start.py   # with source
   ```

The backend will be available at `http://localhost:8000`.

### Frontend Setup (Standalone)

**Standalone backend and frontend URLs:**
- **Backend API**: http://localhost:8000 (FastAPI server)
- **Angular**: http://localhost:4200 (npm start)
- **React**: http://localhost:5174 (npm run dev)  
- **Vue**: http://localhost:3000 (npm run dev)

Choose one of the following frontend options to work with:

#### React Frontend

1. Navigate to the React frontend directory:
   ```bash
   cd flexible-graphrag-ui/frontend-react
   ```

2. Install Node.js dependencies (first time only):
   ```bash
   npm install
   ```

3. Start the development server (uses Vite):
   ```bash
   npm run dev
   ```

The React frontend will be available at `http://localhost:5174`.

#### Angular Frontend

1. Navigate to the Angular frontend directory:
   ```bash
   cd flexible-graphrag-ui/frontend-angular
   ```

2. Install Node.js dependencies (first time only):
   ```bash
   npm install
   ```

3. Start the development server (uses Angular CLI):
   ```bash
   npm start
   ```

The Angular frontend will be available at `http://localhost:4200`.

#### Vue Frontend

1. Navigate to the Vue frontend directory:
   ```bash
   cd flexible-graphrag-ui/frontend-vue
   ```

2. Install Node.js dependencies (first time only):
   ```bash
   npm install
   ```

3. Start the development server (uses Vite):
   ```bash
   npm run dev
   ```

The Vue frontend will be available at `http://localhost:3000`.

## UI Usage

The system provides a tabbed interface for document processing and querying. Follow these steps in order. See [docs/UI-GUIDE/UI-GUIDE.md](docs/UI-GUIDE/UI-GUIDE.md) for full details.

### 1. Sources Tab

Configure your data source and select files for processing. The system supports **14 data sources**:

**Detailed Configuration:**

#### File Upload Data Source
- **Select**: "File Upload" from the data source dropdown
- **Add Files**: 
  - **Drag & Drop**: Drag files directly onto the upload area
  - **Click to Select**: Click the upload area to open file selection dialog (supports multi-select)
  - **Note**: If you drag & drop new files after selecting via dialog, only the dragged files will be used
- **Supported Formats**: PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, CSV, PNG, JPG, and more
- **Next Step**: Click "CONFIGURE PROCESSING →" to proceed to Processing tab

#### Alfresco Repository
- **Select**: "Alfresco Repository" from the data source dropdown
- **Configure**:
  - Alfresco Base URL (e.g., `http://localhost:8080/alfresco`)
  - Username and password
  - Path (e.g., `/Sites/example/documentLibrary`)
- **Next Step**: Click "CONFIGURE PROCESSING →" to proceed to Processing tab

#### CMIS Repository
- **Select**: "CMIS Repository" from the data source dropdown
- **Configure**: 
  - CMIS Repository URL (e.g., `http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom`)
  - Username and password
  - Folder path (e.g., `/Sites/example/documentLibrary`)
- **Next Step**: Click "CONFIGURE PROCESSING →" to proceed to Processing tab

**All Data Sources** (13 available):
- **Web Sources**: Web Page, Wikipedia, YouTube
- **Cloud Storage**: Amazon S3, Google Cloud Storage, Azure Blob Storage, Google Drive, Microsoft OneDrive
- **Enterprise Repositories**: Alfresco, Microsoft SharePoint, Box, CMIS

See the [Data Sources](#data-sources) section for complete details on all 14 sources.

### 2. Processing Tab

Process your selected documents and monitor progress:

- **Start Processing**: Click "START PROCESSING" to begin document ingestion
- **Monitor Progress**: View real-time progress bars for each file
- **File Management**: 
  - Use checkboxes to select files
  - Click "REMOVE SELECTED (N)" to remove selected files from the list
  - **Note**: This removes files from the processing queue, not from your system
- **Processing Pipeline**: Documents are processed through Docling conversion, vector indexing, and knowledge graph creation

### 3. Search Tab

Perform searches on your processed documents:

#### Hybrid Search
- **Purpose**: Find and rank the most relevant document excerpts
- **Usage**: Enter search terms or phrases (e.g., "machine learning algorithms", "financial projections")
- **Action**: Click "SEARCH" button
- **Results**: Ranked list of document excerpts with relevance scores and source information
- **Best for**: Research, fact-checking, finding specific information across documents

#### Q&A Query
- **Purpose**: Get AI-generated answers to natural language questions
- **Usage**: Enter natural language questions (e.g., "What are the main findings in the research papers?")
- **Action**: Click "ASK" button
- **Results**: AI-generated narrative answers that synthesize information from multiple documents
- **Best for**: Summarization, analysis, getting overviews of complex topics

### 4. Chat Tab

Interactive conversational interface for document Q&A:

- **Chat Interface**: 
  - **Your Questions**: Displayed on the right side vertically
  - **AI Answers**: Displayed on the left side vertically
- **Usage**: Type questions and press Enter or click send
- **Conversation History**: All questions and answers are preserved in the chat history
- **Clear History**: Click "CLEAR HISTORY" button to start a new conversation
- **Best for**: Iterative questioning, follow-up queries, conversational document exploration

### Testing Cleanup

Between tests you can clean up data:
- **Run `cleanup.py`**: Clears vector, graph, and search indexes in one step — run from the `flexible-graphrag` directory
- **Vector Indexes**: See [docs/DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md](docs/DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md) for vector database cleanup instructions
- **Graph Data**: See [docs/DATABASES/GRAPH-DATABASES/README-neo4j.md](docs/DATABASES/GRAPH-DATABASES/README-neo4j.md) for graph-related cleanup commands

## Langflow Visual Flows (Optional)

Flexible GraphRAG ships **12 custom Langflow components** (implemented in **Python**) and four ready-made flows (ingest, search, AI query, and a combined query flow for the Langflow Playground). With `ENABLE_LANGFLOW_FLOWS=true`, the app runs its **ingest pipeline, hybrid search, and AI query through those visual flows** instead of calling the system directly — the flows execute the **same backend machinery** driven by your existing `.env` (all database, LLM/embedding, chunking, KG, RDF, and LlamaIndex/LangChain settings apply unchanged), so the pipeline becomes a flow you can customize. You can also just drag the components onto the Langflow canvas to build your own flows.

The main requirement is a **separate venv for Langflow** — Langflow runs the flows' Python component code in its own process, and the backend app calls the **Langflow REST API** to run the two flows.

**1. Langflow venv** — create it on **any Python 3.14 except 3.14.0** (3.14.4 and 3.14.5 both work), or 3.13. Use an explicit patch version: `uv venv --python 3.14.4` (or greater) — plain `uv venv --python 3.14` resolves to **3.14.0**, which has an OpenSSL bug that makes Langflow abort on startup. Then install Langflow and the backend (LlamaIndex + fuller LangChain), and run Langflow **from the `flexible-graphrag` backend dir**:

```powershell
# --system-certs handles an SSL-inspecting corporate proxy.
# On uv < 0.11 the flag is --native-tls (newer uv deprecates that name).
uv pip install --system-certs langflow==1.11.2
uv pip install --system-certs --override extras-overrides.txt -e ".[langchain,langchain-extras]"
# (No PyJWT restore step needed: flexible-graphrag installs plain `nuxeo` +
#  `authlib` + `pyjwt[crypto]`, never `nuxeo[oauth2]`, so nothing evicts PyJWT.)
# Run from the flexible-graphrag backend dir. PYTHONPATH must point at it so this repo's bundled
# `langchain` package wins over the real one (search / AI query need it):
$env:PYTHONPATH = (Get-Location).Path
langflow run --port 7860 --log-level WARNING --log-file langflow.log
```

Wait for Langflow to **fully start** — after the purple "Welcome to Langflow" box it prints `Launching Langflow...`; it's ready once that finishes. Then create an API key in the Langflow UI: **Settings → Langflow API Keys → Add New** (copy it — shown once).

**2. Backend venv** — set `ENABLE_LANGFLOW_FLOWS=true`, `LANGFLOW_URL=http://localhost:7860`, and `LANGFLOW_API_KEY=<the key from the UI>` in `.env`, then start the app as usual. (A no-API-key local shortcut and the underlying `LANGFLOW_SECRET_KEY` are covered in the docs' Authentication section.)

**Docker Compose alternative** — instead of the two-venv setup above, the compose stack runs the **backend in Docker** alongside an optional **Langflow container** (with the 12 components already bundled), which you enable by flipping `ENABLE_LANGFLOW_FLOWS: "true"` and uncommenting the Langflow include. Covered in detail in the doc link below.

For the full setup (both the two-venv and Docker Compose paths), configuration reference, flow customization, and the 12-component developer reference, see **[Langflow Integration](docs/GETTING-STARTED/LANGFLOW-INTEGRATION.md)** and **[Langflow Components](docs/DEVELOPER/DEVELOPER-LANGFLOW-COMPONENTS.md)**.

## MCP Server Setup (Quickstart)

The MCP server (`flexible-graphrag-mcp`) is a lightweight standalone package that connects MCP clients (Claude Desktop, Cursor, etc.) to the Flexible GraphRAG backend via its REST API.

For full details see [`flexible-graphrag-mcp/README.md`](flexible-graphrag-mcp/README.md) and [`flexible-graphrag-mcp/QUICK-USAGE-GUIDE.md`](flexible-graphrag-mcp/QUICK-USAGE-GUIDE.md). For the full list of available MCP tools see [MCP Tools for Claude Desktop and Other MCP Clients](#mcp-tools-for-claude-desktop-and-other-mcp-clients) below.

### Steps

1. **First terminal — install and run the flexible-graphrag backend** (see [Python Backend Setup](#python-backend-setup-standalone) above) — it must be running on `http://localhost:8000`.

2. **Second terminal — install and start the MCP server** in HTTP mode:
   ```bash
   uv venv venv-mcp --python 3.13
   venv-mcp\Scripts\Activate   # Windows
   source venv-mcp/bin/activate  # Linux/macOS
   uv pip install flexible-graphrag-mcp
   flexible-graphrag-mcp --http --port 3001
   ```

3. **Third terminal — test with MCP Inspector**:
   ```bash
   npx @modelcontextprotocol/inspector
   ```
   Open the URL printed in the console (token pre-filled), set transport to **Streamable HTTP**, URL to `http://localhost:3001/mcp`, then click **Connect**.

4. **Use with Claude Desktop and other MCP clients** — see [`flexible-graphrag-mcp/README.md`](flexible-graphrag-mcp/README.md) for stdio transport config and client-specific setup.

## MCP Tools for Claude Desktop and Other MCP Clients

The MCP server provides 9 specialized tools for document intelligence workflows:

| Tool | Purpose | Usage |
|------|---------|-------|
| `get_system_status()` | System health and configuration | Verify setup and database connections |
| `ingest_documents()` | Bulk document processing | All sources support `skip_graph`; filesystem/Alfresco/CMIS use `paths`; Alfresco also supports `nodeDetails` list (14 sources have their own config: filesystem, repositories (Alfresco, SharePoint, Box, CMIS, Nuxeo), cloud storage, web) |
| `ingest_text(content, source_name)` | Custom text analysis | Analyze specific text content |
| `search_documents(query, top_k)` | Hybrid document retrieval | Find relevant document excerpts |
| `query_documents(query, top_k)` | AI-powered Q&A | Generate answers from document corpus |
| `test_with_sample()` | System verification | Quick test with sample content |
| `check_processing_status(id)` | Async operation monitoring | Track long-running ingestion tasks |
| `get_python_info()` | Environment diagnostics | Debug Python environment issues |
| `health_check()` | Backend connectivity | Verify API server connection |

### Client Support
- **Claude Desktop and other MCP clients**: Native MCP integration with stdio transport
- **MCP Inspector**: HTTP transport for debugging and development
- **Multiple Installation**: pipx (system-wide) or uvx (no-install) options

## CocoIndex Integration

Flexible GraphRAG optionally uses a [CocoIndex](https://github.com/cocoindex-io/cocoindex)
pipeline (Rust engine) that **mixes CocoIndex and Flexible GraphRAG (LlamaIndex /
LangChain) sources, processing functions, and database targets** — while keeping the
same FastAPI REST/MCP/UI surface. Langflow "Flexible" components are separate from this.

### Two incremental modes

Do not enable more than one of these orchestrators at once (startup skips / force-disables conflicts).

| | Default pipeline + auto-incremental | CocoIndex pipeline |
|---|---|---|
| **`ENABLE_INCREMENTAL_UPDATES`** | `true` | `false` (ignored / skipped if set — FG incremental uses `hybrid_system`, not CocoIndex) |
| **`PIPELINE_BACKEND`** | default (not `cocoindex`) | `cocoindex` |
| **`ENABLE_LANGFLOW_FLOWS`** | optional (`true` for Langflow flow mode on the default pipeline) | `false` (ignored / force-disabled — CocoIndex not supported in Langflow flows) |
| **Multi-source configs** | `datasource_config` rows (UI / MCP / REST) | Same — `datasource_config` rows (UI / MCP / REST) |
| **Change events** | Event detectors emit ADD / MODIFY / DELETE | Same detectors for flexible data sources |
| **File / doc tracking** | Postgres `document_state` rows | No `document_state` — CocoIndex LMDB + reconciler |
| **Who drives the pipeline** | FG incremental engine re-ingests via `hybrid_system` (default LI/LC pipeline) | CocoIndex bridge owns ingest + change processing (LMDB step memoization) |

**What you can mix in a CocoIndex pipeline:**

| Category | CocoIndex | Flexible GraphRAG |
|---|---|---|
| **Sources** | Native: `localfs`, S3, Azure Blob, Google Drive | 13 sources (9 with event detectors / auto-sync): filesystem, Alfresco, S3, Azure Blob, GCS, OneDrive, SharePoint, Google Drive, Box, CMIS, web, Wikipedia, YouTube |
| **Document-processor function** | — | One `parse_document` function: Docling, LlamaParse, or LiteParse |
| **Chunker / splitter functions** | `split_with_cocoindex` (`CHUNKER_BACKEND=cocoindex`) | `split_with_llamaindex` / `split_with_langchain` (`CHUNKER_BACKEND=llamaindex` / `langchain`) |
| **Embedding providers** | `COCOINDEX_EMBEDDING_KIND=sentence_transformer` or `litellm` (in-process; no LiteLLM proxy) | All FG kinds via `EMBEDDING_KIND` (or other `COCOINDEX_EMBEDDING_KIND` values): OpenAI, Ollama, Azure, Google, Vertex, Bedrock, Fireworks, OpenAI-like, LiteLLM |
| **LLM providers** | — | Same `LLM_PROVIDER` list for **KG extraction** and **AI query / chat**. Hybrid search is retrieval (vector / BM25 / graph); an LLM is used only when a text-to-query graph retriever is in the fusion mix. Framework for KG: `KG_EXTRACTOR_BACKEND=llamaindex` → LI LLM + extractors; `langchain` → LC LLM + `LLMGraphTransformer` |
| **KG extraction functions** | Not used — CocoIndex’s own extractors do not produce multi-label Neo4j-style entity graphs | LlamaIndex Schema / Dynamic / Simple path extractors; LangChain `LLMGraphTransformer` — ontology-guided multi-label graphs for both CocoIndex native and Flexible (LI/LC) property-graph backends |
| **Vector targets** | Native: Qdrant, LanceDB, Postgres (pgvector) | All 10 vector stores via adapters |
| **Property graph targets** | Native: Neo4j, FalkorDB, SurrealDB | All 15 property graph databases via adapters |
| **RDF targets** | — | 4 RDF triple stores (Fuseki, GraphDB, Oxigraph, Neptune RDF) |
| **Search targets** | — | 3 search stores (Elasticsearch, OpenSearch, BM25) |

**Why use it (mixed pipeline):**

- **Broader Flexible GraphRAG stack in a CocoIndex flow** — more sources (incl. event detectors), more property-graph and vector databases, plus RDF, search, and the existing UI / REST / MCP — not only CocoIndex’s native connectors.
- **Rust engine** — CocoIndex’s core is Rust; orchestration and reconciler are built for high-throughput incremental transforms.
- **Incremental cost control (both modes)** — with the **default** pipeline + `ENABLE_INCREMENTAL_UPDATES` / event detectors, unchanged files never re-enter ingest. With **CocoIndex**, detectors still gate file-level work, and LMDB also memoizes parse / embed / KG by step input so unchanged chunks skip those calls if content is re-seen.
- **Field-specific sources and targets (custom code)** — CocoIndex can map individual source fields and write field-level target rows with custom transforms; the default FG mixed pipeline stays document-oriented.
- **Granularity** — FG detectors are **file / document** level (ADD / MODIFY / DELETE). CocoIndex step memoization is **chunk / content** level inside the pipeline. Page / section / field units need custom CocoIndex coding — not the default FG shape.
- **Standalone** — same `cocoindex_integration/pipeline/app.py` can run outside the FastAPI server for custom mixed apps.

**To enable:** add `PIPELINE_BACKEND=cocoindex` to `.env` and install with
`uv pip install -e ".[cocoindex]"`. All REST/MCP/UI endpoints remain unchanged.

**Worked example:** [`examples/cocoindex/meeting_notes_graph_any/`](examples/cocoindex/meeting_notes_graph_any/README.md)
ports CocoIndex's own `meeting_notes_graph_neo4j` example to run against **any** of the 15
property graph databases and **any** of the 10 auto-sync data sources. It shows a custom
`KGExtractor` (with untagged documents delegated back to the built-in extractor), entity
resolution, and three ways to run the same extractor — a short app, the standard pipeline, and
the server for UI-driven use.

See [CocoIndex Integration](docs/GETTING-STARTED/COCOINDEX-INTEGRATION.md) and
[CocoIndex Configuration](docs/CONFIGURATION/CONFIG-COCOINDEX.md) for details, or the
[CocoIndex Developer Guide](docs/DEVELOPER/DEVELOPER-COCOINDEX.md) to build on it.

---

## Backend REST API

The FastAPI backend provides the following REST API endpoints:

**Base URL**: `http://localhost:8000/api/`

**System**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Health check — verify backend is running |
| `/api/status` | GET | System status and configuration (databases, LLM, feature flags) |
| `/api/info` | GET | System information and package versions |
| `/api/python-info` | GET | Python environment diagnostics |

**Ingestion**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ingest` | POST | Ingest documents from a data source (`filesystem`, `s3`, `web`, `cmis`, ...) |
| `/api/upload` | POST | Upload files directly for processing |
| `/api/ingest-text` | POST | Ingest raw text content |
| `/api/test-sample` | POST | Test the system with built-in sample content |
| `/api/cleanup-uploads` | POST | Remove temporarily uploaded files |

**Async Processing**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/processing-status/{id}` | GET | Poll status of an async ingestion operation |
| `/api/processing-events/{id}` | GET | Server-Sent Events stream for real-time progress |
| `/api/cancel-processing/{id}` | POST | Cancel an ongoing processing operation |

**Search & Query**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/search` | POST | Hybrid search — returns ranked document excerpts |
| `/api/query` | POST | AI-powered Q&A — generates an answer from the document corpus |

**Graph**

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/graph` | GET | Graph database status and node/relationship counts (Neo4j: live Cypher counts; other LC-backed stores: counts via `lc_graph.query()` where supported; remaining stores: status + dashboard URL) |
| `/api/graph/query` | POST | Execute a native graph query against the configured store — Cypher (Neo4j, Memgraph, FalkorDB, ArcadeDB, Ladybug, Apache AGE), AQL (ArangoDB), SurrealQL (SurrealDB), Gremlin (Cosmos), GSQL (TigerGraph), openCypher (Neptune/Analytics), GQL (Spanner), SPARQL fallback for RDF-only |

**RDF / Ontology** *(when `RDF_GRAPH_DB` is configured)*

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/rdf/query/sparql` | POST | Execute a SPARQL query against the configured RDF store |
| `/api/rdf/ontology/info` | GET | Return loaded ontology entity and relation type lists |
| `/api/rdf/ontology/upload` | POST | Upload a new ontology file at runtime |
| `/api/rdf/rdf-store/list` | GET | List registered RDF stores |
| `/api/rdf/rdf-store/connect` | POST | Register an additional RDF store at runtime |
| `/api/rdf/rdf-store/{name}` | DELETE | Deregister an RDF store |
| `/api/rdf/export/rdf` | POST | Export knowledge graph as RDF *(501 stub — not yet implemented)* |

**Interactive API Documentation** (requires running backend):

| UI | URL | Notes |
|---|---|---|
| **Swagger UI** | http://localhost:8000/docs | Try endpoints, inspect schemas, submit requests |
| **ReDoc** | http://localhost:8000/redoc | Cleaner read-only reference view |

See [docs/DEVELOPER/REST-API.md](docs/DEVELOPER/REST-API.md) for the full endpoint reference with request/response examples.

## Full-Stack Debugging (Standalone Mode)

VS Code launch configurations, backend/frontend debugging, log levels, and MCP Inspector setup — see [docs/DEVELOPER/DEVELOPER-FULL-STACK-DEBUGGING.md](docs/DEVELOPER/DEVELOPER-FULL-STACK-DEBUGGING.md).

## Observability and Monitoring

Flexible GraphRAG includes comprehensive observability features for production monitoring:

- **OpenTelemetry Integration**: Industry-standard instrumentation with automatic LlamaIndex tracing
- **Distributed Tracing**: Jaeger UI for visualizing complete request flows
- **Metrics Collection**: Prometheus for RAG-specific metrics (retrieval/LLM latency, token usage, entity/relation counts)
- **Visualization**: Grafana dashboards with pre-configured RAG metrics panels
- **Dual Mode Support**: OpenInference (LlamaIndex) + OpenLIT (optional) as dual OTLP producers
- **Custom Instrumentation**: Decorators for adding tracing to custom code

### Quick Start

1. Install observability dependencies (optional):
   ```bash
   cd flexible-graphrag
   uv pip install -e ".[observability-dual]"  # OpenInference (LlamaIndex + LangChain) + OpenLIT (recommended)
   # Or combine with dev tools: uv pip install -e ".[observability-dual,dev]"
   ```

2. Enable in `.env`:
   ```bash
   ENABLE_OBSERVABILITY=true
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
   OBSERVABILITY_BACKEND=both  # openinference, openlit, or both (recommended)
   ```

3. Start observability stack:
   ```bash
   cd docker
   # Uncomment observability.yaml in docker-compose.yaml first
   docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
   ```

4. Access dashboards:
   - **Grafana**: http://localhost:3009 (admin/admin) - RAG metrics dashboards
   - **Jaeger**: http://localhost:16686 - Distributed tracing
   - **Prometheus**: http://localhost:9090 - Raw metrics

<p align="center">
  <a href="./screen-shots/observability/observability-grafana-prometheus-jaeger-ui.png">
    <img src="./screen-shots/observability/observability-grafana-prometheus-jaeger-ui.png" alt="Observability Dashboard" width="700">
  </a>
</p>

See [docs/DEVELOPER/OBSERVABILITY/OBSERVABILITY.md](docs/DEVELOPER/OBSERVABILITY/OBSERVABILITY.md) for complete setup, custom instrumentation, and production best practices.

## Project Structure

- `/flexible-graphrag`: Python FastAPI backend
  - `main.py`: FastAPI REST API server
  - `backend.py`: Shared business logic used by both API and MCP
  - `config.py`: Configurable settings for data sources, databases, and LLM providers
  - `factories.py`: Factory classes for LLM and database creation
  - `hybrid_system.py`: Main hybrid search and ingestion system
  - `post_ingestion_state.py`: Post-ingestion document state tracking
  - `query_engine.py`: Query engine with result deduplication and re-scoring
  - `retriever_setup.py`: Retriever assembly — vector, search, graph, RDF, synonym expansion
  - `schema_manager.py`: Database schema management
  - `adapters/`: Framework-neutral ABCs and factories for all subsystems
    - `adapters/graph/`: Property graph and RDF store adapter ABCs
    - `adapters/llm/`: LLM and embedding adapter ABCs (`BothLLMAdapter`, `BothEmbeddingAdapter`)
    - `adapters/process/`: Chunker and KG extractor ABCs and `build_*` factories
    - `adapters/search/`: Search store adapter ABC
    - `adapters/vector/`: Vector store adapter ABC
  - `cocoindex_integration/`: Optional CocoIndex pipeline backend — mixes CocoIndex source/target connectors, functions, and splitters with Flexible GraphRAG sources, targets, and functions (document processor + LlamaIndex/LangChain chunker-splitters); can also be run standalone outside of the FastAPI server
    - `bridge.py`: FastAPI ↔ CocoIndex bridge; `ingest_source()` for all 13 UI datasources
    - `retriever_bridge.py`: read-only vector/graph retrievers when `*_BACKEND=cocoindex`
    - `surreal_chain.py`: CocoIndex SurrealDB QA chain (flat CocoIndex schema)
    - `functions/`: `@coco.fn` building blocks — doc parsing, chunking, embedding, KG extraction (all memoized)
    - `connectors/flexible/`: lazy `FlexibleMapView(LiveMapView)` for 9 detector-backed sources; `FlexibleDataSource` for non-file sources
    - `connectors/cocoindex/`: native CocoIndex connectors (Qdrant, Neo4j, LanceDB, Postgres, S3, GCS, Google Drive)
    - `pipeline/`: `app.py` entry point, `flexible_app.py`, `run.py`, `bootstrap.py`, `state.py`, `providers.py`, `selectors.py`
  - `incremental_updates/`: Auto-sync engine — detectors, orchestrator, state manager for real-time/near-real-time source sync
  - `ingest/`: Modular ingestion steps — `ingest_from_files`, `ingest_from_text`, `ingest_from_source`, `run_chunk_pipeline`, `update_pg_graph`, `update_rdf_graph`, `update_vector`, `update_search`
  - `langflow_components/`: 12 custom Langflow components (Python) in `flexible_graphrag/` + shared run-cache helper `_fg_shared.py`; `flow_service.py` (backend) drives them over the Langflow REST API
  - `langchain/`: LangChain peer framework — graph, vector, search, chunking, KG extraction, retrieval
    - `langchain/graph/pg_store_adapters/`: 15 property graph store adapters (one file per store)
    - `langchain/graph/rdf_store_adapters/`: 4 RDF/SPARQL store adapters (Fuseki, GraphDB, Oxigraph, Neptune)
    - `langchain/graph/retrievers/`: `li_`/`lc_` two-layer retriever classes — text-to-query, neighborhood, vector, logging, synonym
    - `langchain/llm/`: LangChain LLM + embedding factories for all 13 providers
    - `langchain/process/`: `LangChainChunkerAdapter` (6 splitter types), `LangChainKGExtractorAdapter`
    - `langchain/search/adapters/`: BM25, Elasticsearch, OpenSearch search adapters
    - `langchain/vector/adapters/`: 10 vector store adapters
  - `llamaindex/`: LlamaIndex peer framework — graph, vector, search, chunking, KG extraction
    - `llamaindex/graph/adapters/`: LlamaIndex property graph store adapters (Neo4j, ArcadeDB, FalkorDB, Memgraph, Nebula, Neptune, etc.)
    - `llamaindex/llm/`: LlamaIndex LLM + embedding factories for all 13 providers
    - `llamaindex/process/`: `LlamaIndexChunkerAdapter`, `LlamaIndexKGExtractorAdapter`
    - `llamaindex/search/adapters/`: Elasticsearch, OpenSearch search adapters
    - `llamaindex/vector/adapters/`: Qdrant, Elasticsearch, OpenSearch, pgvector, Chroma, and others
  - `observability/`: OpenTelemetry instrumentation, Prometheus metrics, tracing setup
  - `process/`: Core document processing — `document_processor.py` (Docling/LlamaParse/LiteParse), `kg_extractor.py`, `node_pipeline.py`
  - `rdf/`: RDF/ontology support — ontology manager, KG-to-RDF converter, SPARQL tools, bundled schemas (`rdf/schemas/`)
    - `rdf/store/`: RDF store adapters — Fuseki, GraphDB, Oxigraph, store factory
  - `sources/`: Data source connectors — filesystem, CMIS/Alfresco, Azure Blob, S3, GCS, OneDrive, SharePoint, Google Drive, Box, web, Wikipedia, YouTube, etc.
  - `stores/`: Index managers — `index_manager.py`, `rdf_manager.py`
  - `pyproject.toml`: Modern Python package definition (PEP 517/518)
  - `uv.toml`: UV package manager configuration
  - `start.py`: Startup script (`flexible-graphrag` console entry point)
  - `install.py`: Installation helper script

- `/flows`: Bundled Langflow flow JSONs the app uploads in flow mode — `fg_ingestion_flow.json`, `fg_search_flow.json`, `fg_aiquery_flow.json`, `fg_query_flow.json` (see `README.md` there)

- `/flexible-graphrag-mcp`: Standalone MCP server
  - `main.py`: HTTP-based MCP server (calls REST API)
  - `pyproject.toml`: MCP package definition with minimal dependencies
  - `README.md`: MCP server setup and installation instructions
  - `QUICK-USAGE-GUIDE.md`: Quick usage guide
  - **Lightweight**: Only 3 dependencies (fastmcp, httpx, python-dotenv)

- `/flexible-graphrag-ui`: Frontend applications
  - `/frontend-react`: React + TypeScript frontend (built with Vite)
    - `/src`: Source code
    - `vite.config.ts`: Vite configuration
    - `tsconfig.json`: TypeScript configuration
    - `package.json`: Node.js dependencies and scripts

  - `/frontend-angular`: Angular + TypeScript frontend (built with Angular CLI)
    - `/src`: Source code
    - `angular.json`: Angular configuration
    - `tsconfig.json`: TypeScript configuration
    - `package.json`: Node.js dependencies and scripts

  - `/frontend-vue`: Vue + TypeScript frontend (built with Vite)
    - `/src`: Source code
    - `vite.config.ts`: Vite configuration
    - `tsconfig.json`: TypeScript configuration
    - `package.json`: Node.js dependencies and scripts

- `/docker`: Docker infrastructure
  - `docker-compose.yaml`: Main compose file with modular includes
  - `/includes`: Modular database and service configurations
  - `/nginx`: Reverse proxy configuration
  - `README.md`: Docker deployment documentation

- `/docs`: Documentation ([Zensical](https://zensical.org/) site; nav in `zensical.toml`) — organized into these sections:
  - `index.md`: Documentation home / overview
  - `HOME/`: Section landing pages (overview, getting started, docker, configuration, UI, data sources, databases, MCP, developer)
  - `GETTING-STARTED/`: Quickstart, prerequisites, setup overview, Python backend, frontend setup, Docker deployment, environment configuration, **Langflow Integration**, **CocoIndex Integration**
  - `CONFIGURATION/`: Search / vector / property-graph / RDF database config, schema examples, Framework (LangChain/LlamaIndex) configuration, **CocoIndex Configuration**
  - `UI-GUIDE/`: UI screenshots and per-tab guides (Sources, Processing, Hybrid Search, AI Chat)
  - `DATA-SOURCES/`: Data source setup (S3, Azure Blob, GCS, CMIS, path examples); `DOC-PROCESSING/` (file formats, Docling GPU/OCR, parser output); `INCREMENTAL-UPDATE-AUTO-SYNC/`
  - `LLM/`: LLM & embedding configuration, testing results, Ollama
  - `DATABASES/`: Database configuration, PostgreSQL; `GRAPH-DATABASES/`, `RDF/`, `VECTOR-DATABASES/`
  - `MCP/`: MCP server quickstart, MCP tools, usage guide
  - `DEVELOPER/`: REST API, MCP developer setup, **Langflow Components**, **CocoIndex Developer Guide**, testing & cleanup, full-stack debugging, documentation system; `OBSERVABILITY/`
  - `ADVANCED/`: Architecture, deployment configurations, Docker resource config, port mappings, timeouts, default usernames/passwords; `LANGCHAIN/` (framework integration)

- `/scripts`: Utility scripts
  - `create_opensearch_pipeline.py`: OpenSearch hybrid search pipeline setup
  - `setup-opensearch-pipeline.sh/.bat`: Cross-platform pipeline creation
  - `rdf_cleanup.py`: RDF store CLI tool — list-docs, count, clear-doc, clear-all
  - `litellm_config.yaml`: Sample LiteLLM proxy config (copy to your LiteLLM install dir)
  - `/incremental`: Incremental updates control scripts
    - `sync-now.sh/.ps1/.bat`: Trigger immediate synchronization
    - `set-refresh-interval.sh/.ps1/.bat`: Configure polling interval
    - `README.md`: Script usage documentation

- `/tests`: Test suite
  - `test_bm25_*.py`: BM25 configuration and integration tests
  - `conftest.py`: Test configuration and fixtures
  - `run_tests.py`: Test runner

- `/examples`: Standalone usage examples (not re-tested)
  - `observability_example.py`: OpenTelemetry / observability integration example
  - `/rdf`: RDF/ontology examples
    - `sparql_examples.py`: Sample SPARQL queries for all three stores
    - `unified_query_engine_examples.py`: `UnifiedQueryEngine` usage examples
    - `store_index_example.py`: Build a LlamaIndex from an RDF store
    - `ontology_guided_ingestion_example.py`: `OntologyAwarePropertyGraphBuilder` usage
    - `ingest_with_ontology.py`: Ontology-guided ingestion example class
    - `rdf_export_import_examples.py`: RDF export/import patterns
    - `config_rdf_stores.py`: RDF store config reference snippets
  - `/cocoindex`: CocoIndex pipeline examples
    - `/meeting_notes_graph_any`: CocoIndex's `meeting_notes_graph_neo4j` ported to run against any configured graph store and data source
      - `extractor.py`: the meeting-notes extraction as a registered `KGExtractor`
      - `mini_app.py`: short CocoIndex app — source, custom extraction, property graph
      - `pipeline_app.py`: the standard flexible-graphrag pipeline with this extractor plugged in
      - `run_backend.py`: starts the app server configured for this example, so the UI can drive it
      - `example_config.py`: settings shared by the runners
      - `meeting_notes.py`: extraction schema, prompt, section splitter, `.env` loading
      - `meeting_notes_ontology.ttl`: the Meeting/Person/Task graph in RDF, for the RDF retriever
      - `/sample_notes`: the notes the example ingests

## License

This project is licensed under the terms of the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
