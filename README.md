**New!** - [KG Spaces Integration of Flexible GraphRAG in Alfresco ACA Client](https://github.com/stevereiner/kg-spaces-aca)

# Flexible GraphRAG

**Flexible GraphRAG** is a platform supporting document processing, knowledge graph auto-building, RAG and GraphRAG setup, hybrid search (fulltext, vector, graph) and AI Q&A query capabilities.

<p align="center">
  <a href="./screen-shots/react/chat-webpage.png">
    <img src="./screen-shots/react/chat-webpage.png" alt="Flexible GraphRAG AI chat tab with a web pages data source generated graph displayed in Neo4j" width="700">
  </a>
</p>

<p align="center"><em>Flexible GraphRAG AI chat tab with a web pages data source generated graph displayed in Neo4j</em></p>


## What It Is

A configurable hybrid search system that optionally combines vector similarity search, full-text search, and knowledge graph GraphRAG on documents processed from multiple data sources (file upload, cloud storage, enterprise repositories, web sources). Built with LlamaIndex which provides abstractions for allowing multiple vector, search graph databases, LLMs to be supported. Documents are parsed using either Docling (default) or LlamaParse (cloud API). It has both a FastAPI backend with REST endpoints and a Model Context Protocol (MCP) server for MCP clients like Claude Desktop, etc. Also has simple Angular, React, and Vue UI clients (which use the REST APIs of the FastAPI backend) for interacting with the system.


- **Hybrid Search**: Combines vector embeddings, BM25 full-text search, and graph traversal for comprehensive document retrieval
- **Knowledge Graph GraphRAG**: Extracts entities and relationships from documents to create graphs in graph databases for graph-based reasoning  
- **Configurable Architecture**: LlamaIndex provides abstractions for vector databases, graph databases, search engines, and LLM providers
- **Multi-Source Ingestion**: Processes documents from 13 data sources (file upload, cloud storage, enterprise repositories, web sources) with Docling or LlamaParse document parsing
- **FastAPI Server with REST API**: FastAPI server with REST API for document ingesting, hybrid search, and AI Q&A query
- **MCP Server**: MCP server that provides MCP Clients like Claude Desktop, etc. tools for document and text ingesting, hybrid search and AI Q&A query.
- **UI Clients**: Angular, React, and Vue UI clients support choosing the data source (filesystem, Alfresco, CMIS, etc.), ingesting documents, performing hybrid searches and AI Q&A Queries.
- **Docker Deployment Flexibility**: Supports both standalone and Docker deployment modes. Docker infrastructure provides modular database selection via docker-compose includes - vector, graph, and search databases can be included or excluded with a single comment. Choose between hybrid deployment (databases in Docker, backend and UIs standalone) or full containerization.

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
- **REST API Server**: Provides endpoints for document ingestion, search, and Q&A
- **Hybrid Search Engine**: Combines vector similarity, BM25, and graph traversal
- **Document Processing**: Advanced document conversion with Docling integration
- **Configurable Architecture**: Environment-based configuration for all components
- **Async Processing**: Background task processing with real-time progress updates

### MCP Server (`/flexible-graphrag-mcp`)  
- **Claude Desktop Integration**: Model Context Protocol server for AI assistant workflows
- **Dual Transport**: HTTP mode for debugging, stdio mode for Claude Desktop
- **Tool Suite**: 9 specialized tools for document processing, search, and system management
- **Multiple Installation**: pipx system installation or uvx no-install execution

### UI Clients (`/flexible-graphrag-ui`)
- **Angular Frontend**: Material Design with TypeScript
- **React Frontend**: Modern React with Vite and TypeScript  
- **Vue Frontend**: Vue 3 Composition API with Vuetify and TypeScript
- **Unified Features**: All clients support async processing, progress tracking, and cancellation

### Docker Infrastructure (`/docker`)
- **Modular Database Selection**: Include/exclude vector, graph, and search databases with single-line comments
- **Flexible Deployment**: Hybrid mode (databases in Docker, apps standalone) or full containerization
- **NGINX Reverse Proxy**: Unified access to all services with proper routing
- **Database Dashboards**: Integrated web interfaces for Kibana (Elasticsearch), OpenSearch Dashboards, Neo4j Browser, and Kuzu Explorer

## Data Sources

Flexible GraphRAG supports **13 different data sources** for ingesting documents into your knowledge base:

<p align="center">
  <a href="./screen-shots/react/data-sources-1.jpeg">
    <img src="./screen-shots/react/data-sources-1.jpeg" alt="Data Sources" width="700">
  </a>
</p>

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
8. **SharePoint** - Microsoft SharePoint document libraries
9. **Box** - Box.com cloud storage
10. **CMIS (Content Management Interoperability Services)** - Industry-standard content repository interface

### Web Sources
11. **Web Pages** - Extract content from web URLs
12. **Wikipedia** - Ingest Wikipedia articles by title or URL
13. **YouTube** - Process YouTube video transcripts

Each data source includes:
- **Configuration Forms**: Easy-to-use interfaces for credentials and settings
- **Progress Tracking**: Real-time per-file progress indicators
- **Flexible Authentication**: Support for various auth methods (API keys, OAuth, service accounts)

### Document Processing Options

All data sources support two document parser options:

**Docling (Default)**:
- Open-source, local processing
- Free with no API costs
- Built-in OCR for images and scanned documents
- Configured via: `DOCUMENT_PARSER=docling`

**LlamaParse**:
- Cloud-based API service with advanced AI
- Multimodal parsing with Claude Sonnet 3.5
- Three modes available:
  - `parse_page_without_llm` - 1 credit/page
  - `parse_page_with_llm` - 3 credits/page (default)
  - `parse_page_with_agent` - 10-90 credits/page
- Configured via: `DOCUMENT_PARSER=llamaparse` + `LLAMAPARSE_API_KEY`
- Get your API key from [LlamaCloud](https://cloud.llamaindex.ai/)

Both parsers support PDF, Office documents (DOCX, XLSX, PPTX), images, HTML, and more with intelligent format detection.

## Supported File Formats

The system processes **15+ document formats** through intelligent routing between Docling (advanced processing) and direct text handling:

### Document Formats (Docling Processing)
- **PDF**: `.pdf` - Advanced layout analysis, table extraction, formula recognition
- **Microsoft Office**: `.docx`, `.xlsx`, `.pptx` - Full structure preservation and content extraction
- **Web Formats**: `.html`, `.htm`, `.xhtml` - Markup structure analysis
- **Data Formats**: `.csv`, `.xml`, `.json` - Structured data processing
- **Documentation**: `.asciidoc`, `.adoc` - Technical documentation with markup preservation

### Image Formats (Docling OCR)
- **Standard Images**: `.png`, `.jpg`, `.jpeg` - OCR text extraction
- **Professional Images**: `.tiff`, `.tif`, `.bmp`, `.webp` - Layout-aware OCR processing

### Text Formats (Direct Processing)
- **Plain Text**: `.txt` - Direct ingestion for optimal chunking
- **Markdown**: `.md`, `.markdown` - Preserved formatting for technical documents

### Processing Intelligence
- **Adaptive Output**: Tables convert to markdown, text content to plain text for optimal entity extraction
- **Format Detection**: Automatic routing based on file extension and content analysis
- **Fallback Handling**: Graceful degradation for unsupported formats

## Database Configuration

Flexible GraphRAG uses three types of databases for its hybrid search capabilities. Each can be configured independently via environment variables.

### Search Databases (Full-Text Search)

**Configuration**: Set via `SEARCH_DB` and `SEARCH_DB_CONFIG` environment variables

- **BM25 (Built-in)**: Local file-based BM25 full-text search with TF-IDF ranking
  - Dashboard: None (file-based)
  - Configuration:
    ```bash
    SEARCH_DB=bm25
    SEARCH_DB_CONFIG={"persist_dir": "./bm25_index"}
    ```
  - Ideal for: Development, small datasets, simple deployments

- **Elasticsearch**: Enterprise search engine with advanced analyzers, faceted search, and real-time analytics
  - Dashboard: Kibana (http://localhost:5601) for search analytics, index management, and query debugging
  - Configuration:
    ```bash
    SEARCH_DB=elasticsearch
    SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}
    ```
  - Ideal for: Production workloads requiring sophisticated text processing

- **OpenSearch**: AWS-led open-source fork with native hybrid scoring (vector + BM25) and k-NN algorithms
  - Dashboard: OpenSearch Dashboards (http://localhost:5601) for cluster monitoring and search pipeline management
  - Configuration:
    ```bash
    SEARCH_DB=opensearch
    SEARCH_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search"}
    ```
  - Ideal for: Cost-effective alternative with strong community support

- **None**: Disable full-text search (vector search only)
  - Configuration:
    ```bash
    SEARCH_DB=none
    ```

### Vector Databases (Semantic Search)

**Configuration**: Set via `VECTOR_DB` and `VECTOR_DB_CONFIG` environment variables

#### ⚠️ Vector Dimension Compatibility

**CRITICAL**: When switching between different embedding models (e.g., OpenAI ↔ Ollama), you **MUST delete existing vector indexes** due to dimension incompatibility:

- **OpenAI**: 1536 dimensions (text-embedding-3-small) or 3072 dimensions (text-embedding-3-large)
- **Ollama**: 384 dimensions (all-minilm, default), 768 dimensions (nomic-embed-text), or 1024 dimensions (mxbai-embed-large)
- **Azure OpenAI**: Same as OpenAI (1536 or 3072 dimensions)

**See [VECTOR-DIMENSIONS.md](VECTOR-DIMENSIONS.md) for detailed cleanup instructions for each database.**

#### Supported Vector Databases

- **Neo4j**: Can be used as vector database with separate vector configuration
  - Dashboard: Neo4j Browser (http://localhost:7474) for Cypher queries and graph visualization
  - Configuration:
    ```bash
    VECTOR_DB=neo4j
    VECTOR_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "your_password", "index_name": "hybrid_search_vector"}
    ```

- **Qdrant**: Dedicated vector database with advanced filtering
  - Dashboard: Qdrant Web UI (http://localhost:6333/dashboard) for collection management
  - Configuration:
    ```bash
    VECTOR_DB=qdrant
    VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search"}
    ```

- **Elasticsearch**: Can be used as vector database with separate vector configuration
  - Dashboard: Kibana (http://localhost:5601) for index management and data visualization
  - Configuration:
    ```bash
    VECTOR_DB=elasticsearch
    VECTOR_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search_vectors"}
    ```

- **OpenSearch**: Can be used as vector database with separate vector configuration
  - Dashboard: OpenSearch Dashboards (http://localhost:5601) for cluster and index management
  - Configuration:
    ```bash
    VECTOR_DB=opensearch
    VECTOR_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search_vectors"}
    ```

- **Chroma**: Open-source vector database with dual deployment modes
  - Dashboard: Swagger UI (http://localhost:8001/docs/) for API testing and management (HTTP mode)
  - Configuration (Local Mode):
    ```bash
    VECTOR_DB=chroma
    VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}
    ```
  - Configuration (HTTP Mode):
    ```bash
    VECTOR_DB=chroma
    VECTOR_DB_CONFIG={"host": "localhost", "port": 8001, "collection_name": "hybrid_search"}
    ```

- **Milvus**: Cloud-native, scalable vector database for similarity search
  - Dashboard: Attu (http://localhost:3003) for cluster and collection management
  - Configuration:
    ```bash
    VECTOR_DB=milvus
    VECTOR_DB_CONFIG={"uri": "http://localhost:19530", "collection_name": "hybrid_search"}
    ```

- **Weaviate**: Vector search engine with semantic capabilities and data enrichment
  - Dashboard: Weaviate Console (http://localhost:8081/console) for schema and data management
  - Configuration:
    ```bash
    VECTOR_DB=weaviate
    VECTOR_DB_CONFIG={"url": "http://localhost:8081", "index_name": "HybridSearch"}
    ```

- **Pinecone**: Managed vector database service optimized for real-time applications
  - Dashboard: Pinecone Console (web-based) for index and namespace management
  - Local Info Dashboard: http://localhost:3004 (when using Docker)
  - Configuration:
    ```bash
    VECTOR_DB=pinecone
    VECTOR_DB_CONFIG={"api_key": "your_api_key", "region": "us-east-1", "cloud": "aws", "index_name": "hybrid-search"}
    ```

- **PostgreSQL**: Traditional database with pgvector extension for vector similarity search
  - Dashboard: pgAdmin (http://localhost:5050) for database management, vector queries, and similarity searches
  - Configuration:
    ```bash
    VECTOR_DB=postgres
    VECTOR_DB_CONFIG={"host": "localhost", "port": 5433, "database": "postgres", "username": "postgres", "password": "your_password"}
    ```

- **LanceDB**: Modern, lightweight vector database designed for high-performance ML applications
  - Dashboard: LanceDB Viewer (http://localhost:3005) for CRUD operations and data management
  - Configuration:
    ```bash
    VECTOR_DB=lancedb
    VECTOR_DB_CONFIG={"uri": "./lancedb", "table_name": "hybrid_search"}
    ```

#### RAG without GraphRAG

For simpler deployments without knowledge graph extraction, configure:
```bash
VECTOR_DB=qdrant  # Any vector store
SEARCH_DB=elasticsearch  # Any search engine
GRAPH_DB=none
ENABLE_KNOWLEDGE_GRAPH=false
```

**Results**:
- Vector similarity search (semantic)
- Full-text search (keyword-based)
- No graph traversal
- Faster processing (no graph extraction)

### Graph Databases (Knowledge Graph / GraphRAG)

**Configuration**: Set via `GRAPH_DB` and `GRAPH_DB_CONFIG` environment variables

- **Neo4j Property Graph**: Primary knowledge graph storage with Cypher querying
  - Dashboard: Neo4j Browser (http://localhost:7474) for graph exploration and query execution
  - Configuration:
    ```bash
    GRAPH_DB=neo4j
    GRAPH_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "your_password"}
    ```

- **Kuzu**: Embedded graph database built for query speed and scalability, optimized for handling complex analytical workloads on very large graph databases. Supports the property graph data model and the Cypher query language
  - Dashboard: Kuzu Explorer (http://localhost:8002) for graph visualization and Cypher queries
  - Configuration:
    ```bash
    GRAPH_DB=kuzu
    GRAPH_DB_CONFIG={"db_path": "./kuzu_db", "use_structured_schema": true, "use_vector_index": true}
    ```

- **FalkorDB**: "A super fast Graph Database uses GraphBLAS under the hood for its sparse adjacency matrix graph representation. Our goal is to provide the best Knowledge Graph for LLM (GraphRAG)."
  - Dashboard: FalkorDB Browser (http://localhost:3001) (Was moved from 3000 used by the flexible-graphrag Vue frontend)
  - Configuration:
    ```bash
    GRAPH_DB=falkordb
    GRAPH_DB_CONFIG={"url": "falkor://localhost:6379", "database": "falkor"}
    ```

- **ArcadeDB**: Multi-model database supporting graph, document, key-value, and search capabilities with SQL and Cypher query support
  - Dashboard: ArcadeDB Studio (http://localhost:2480) for graph visualization, SQL/Cypher queries, and database management
  - Configuration:
    ```bash
    GRAPH_DB=arcadedb
    GRAPH_DB_CONFIG={"host": "localhost", "port": 2480, "username": "root", "password": "password", "database": "flexible_graphrag", "query_language": "sql"}
    ```

- **MemGraph**: Real-time graph database with native support for streaming data and advanced graph algorithms
  - Dashboard: MemGraph Lab (http://localhost:3002) for graph visualization and Cypher queries
  - Configuration:
    ```bash
    GRAPH_DB=memgraph
    GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", "username": "", "password": ""}
    ```

- **NebulaGraph**: Distributed graph database designed for large-scale data with horizontal scalability
  - Dashboard: NebulaGraph Studio (http://localhost:7001) for graph exploration and nGQL queries
  - Configuration:
    ```bash
    GRAPH_DB=nebula
    GRAPH_DB_CONFIG={"space": "flexible_graphrag", "host": "localhost", "port": 9669, "username": "root", "password": "nebula"}
    ```

- **Amazon Neptune**: Fully managed graph database service supporting both property graph and RDF models
  - Dashboard: Graph-Explorer (http://localhost:3007) for visual graph exploration, or Neptune Workbench (AWS Console) for Jupyter-based queries
  - Configuration:
    ```bash
    GRAPH_DB=neptune
    GRAPH_DB_CONFIG={"host": "your-cluster.region.neptune.amazonaws.com", "port": 8182}
    ```

- **Amazon Neptune Analytics**: Serverless graph analytics engine for large-scale graph analysis with openCypher support
  - Dashboard: Graph-Explorer (http://localhost:3007) or Neptune Workbench (AWS Console)
  - Configuration:
    ```bash
    GRAPH_DB=neptune_analytics
    GRAPH_DB_CONFIG={"graph_identifier": "g-xxxxx", "region": "us-east-1"}
    ```

- **None**: Disable knowledge graph extraction for RAG-only mode
  - Configuration:
    ```bash
    GRAPH_DB=none
    ENABLE_KNOWLEDGE_GRAPH=false
    ```
  - Use when you want vector + full-text search without graph traversal

## LLM Configuration

**Configuration**: Set via `LLM_PROVIDER` and provider-specific environment variables

### LLM Providers

- **OpenAI**: GPT models with configurable endpoints
  - Configuration:
    ```bash
    USE_OPENAI=true
    LLM_PROVIDER=openai
    OPENAI_API_KEY=your_api_key_here
    OPENAI_MODEL=gpt-4o-mini
    OPENAI_EMBEDDING_MODEL=text-embedding-3-small
    ```
  - Models: gpt-4o-mini (default), gpt-4o, gpt-4-turbo, gpt-3.5-turbo
  - Embedding models: text-embedding-3-small (1536 dims, default), text-embedding-3-large (3072 dims)

- **Ollama**: Local LLM deployment for privacy and control
  - Configuration:
    ```bash
    USE_OPENAI=false
    LLM_PROVIDER=ollama
    OLLAMA_BASE_URL=http://localhost:11434
    OLLAMA_MODEL=llama3.2:latest
    OLLAMA_EMBEDDING_MODEL=all-minilm
    ```
  - Models: llama3.2:latest (default), llama3.1:8b, gpt-oss:20b, qwen2.5:latest
  - Embedding models: all-minilm (384 dims, default), nomic-embed-text (768 dims), mxbai-embed-large (1024 dims)

- **Azure OpenAI**: Enterprise OpenAI integration
  - Configuration: (**Untested - may require configuration code changes**)
    ```bash
    LLM_PROVIDER=azure
    AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
    AZURE_OPENAI_API_KEY=your_api_key_here
    AZURE_OPENAI_DEPLOYMENT=your_deployment_name
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT=your_embedding_deployment
    AZURE_OPENAI_API_VERSION=2024-02-15-preview
    ```

- **Anthropic Claude**: Claude models for complex reasoning
  - Configuration: (**Untested - may require configuration code changes**)
    ```bash
    LLM_PROVIDER=anthropic
    ANTHROPIC_API_KEY=your_api_key_here
    ANTHROPIC_MODEL=claude-3-sonnet-20240229
    ```

- **Google Gemini**: Google's latest language models
  - Configuration: (**Untested - may require configuration code changes**)
    ```bash
    LLM_PROVIDER=gemini
    GOOGLE_API_KEY=your_api_key_here
    GEMINI_MODEL=gemini-pro
    ```

### LLM Performance Recommendations

**General Performance with LlamaIndex: OpenAI vs Ollama**

Based on testing with OpenAI GPT-4o-mini and Ollama models (llama3.1:8b, llama3.2:latest, gpt-oss:20b), **OpenAI consistently outperforms Ollama models** in LlamaIndex operations.

### Ollama Configuration

When using Ollama as your LLM provider, you must configure system-wide environment variables before starting the Ollama service. These settings optimize performance and enable parallel processing.

**Key requirements**:
- Configure environment variables **system-wide** (not in Flexible GraphRAG `.env` file)
- `OLLAMA_NUM_PARALLEL=4` is **critical** for parallel document processing
- Always restart Ollama service after changing environment variables

See [docs/OLLAMA-CONFIGURATION.md](docs/OLLAMA-CONFIGURATION.md) for complete setup instructions, including:
- All environment variable configurations
- Platform-specific installation steps (Windows, Linux, macOS)
- Performance optimization guidelines
- Troubleshooting common issues



## MCP Tools for MCP Clients like Claude Desktop, etc.

The MCP server provides 9 specialized tools for document intelligence workflows:

| Tool | Purpose | Usage |
|------|---------|-------|
| `get_system_status()` | System health and configuration | Verify setup and database connections |
| `ingest_documents(data_source, paths)` | Bulk document processing | Process files/folders from filesystem, CMIS, Alfresco |
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

## Prerequisites

### Required
- Python 3.10+ (supports 3.10, 3.11, 3.12, 3.13)
- UV package manager
- Node.js 16+
- npm or yarn
- Neo4j graph database
- Ollama or OpenAI with API key (for LLM processing)

### Optional (depending on data source)
- CMIS-compliant repository (e.g., Alfresco) - only if using CMIS data source
- Alfresco repository - only if using Alfresco data source
- File system data source requires no additional setup

## Setup

### 🐳 Docker Deployment

Docker deployment offers two main approaches:

#### Option A: Databases in Docker, App Standalone (Hybrid)
**Best for**: Development, external content management systems, flexible deployment

```bash
# Deploy only databases you need
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag up -d

# Comment out services you don't need in docker-compose.yaml:
# - includes/neo4j.yaml          # Comment out if using your own Neo4j
# - includes/kuzu.yaml           # Comment out if not using Kuzu
# - includes/qdrant.yaml         # Comment out if using Neo4j, Elasticsearch, or OpenSearch for vectors  
# - includes/elasticsearch.yaml  # Comment out if not using Elasticsearch
# - includes/elasticsearch-dev.yaml  # Comment out if not using Elasticsearch
# - includes/kibana.yaml         # Comment out if not using Elasticsearch
# - includes/opensearch.yaml     # Comment out if not using
# - includes/alfresco.yaml       # Comment out if you want to use your own Alfresco install
# - includes/app-stack.yaml      # Remove comment if you want backend and UI in Docker
# - includes/proxy.yaml          # Remove comment if you want backend and UI in Docker
#   (Note: app-stack.yaml has env config in it to customize for vector, graph, search, LLM using)

# Run backend and UI clients outside Docker
cd flexible-graphrag
uv run start.py
```

**Use cases:**
- ✅ **File Upload**: Direct file upload through web interface
- ✅ **External CMIS/Alfresco**: Connect to existing content management systems
- ✅ **Development**: Easy debugging and hot-reloading
- ✅ **Mixed environments**: Databases in containers, apps on host

#### Option B: Full Stack in Docker (Complete)
**Best for**: Production deployment, isolated environments, containerized content sources

```bash
# Deploy everything including backend and UIs
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag up -d
```

**Features:**
- ✅ All databases pre-configured (Neo4j, Kuzu, Qdrant, Elasticsearch, OpenSearch, Alfresco)
- ✅ Backend + 3 UI clients (Angular, React, Vue) in containers
- ✅ NGINX reverse proxy with unified URLs
- ✅ Persistent data volumes
- ✅ Internal container networking

**Service URLs after startup:**
- **Angular UI**: http://localhost:8070/ui/angular/
- **React UI**: http://localhost:8070/ui/react/  
- **Vue UI**: http://localhost:8070/ui/vue/
- **Backend API**: http://localhost:8070/api/
- **Neo4j Browser**: http://localhost:7474/
- **Kuzu Explorer**: http://localhost:8002/

**Data Source Workflow:**
- ✅ **File Upload**: Upload files directly through the web interface (drag & drop or file selection dialog on click)
- ✅ **Alfresco/CMIS**: Connect to existing Alfresco systems or CMIS repositories

#### Stopping Services

To stop and remove all Docker services:

```bash
# Stop all services
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag down
```

**Common workflow for configuration changes:**
```bash
# Stop services, make changes, then restart
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag down
# Edit docker-compose.yaml or .env files as needed
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag up -d
```

#### Configuration

1. **Modular deployment**: Comment out services you don't need in `docker/docker-compose.yaml`

2. **Environment configuration** (for app-stack deployment): 
   - Environment variables are configured directly in `docker/includes/app-stack.yaml`
   - Database connections use `host.docker.internal` for container-to-container communication
   - Default configuration includes OpenAI/Ollama LLM settings and database connections

See [docker/README.md](./docker/README.md) for detailed Docker configuration.

### 🔧 Local Development Setup

#### Environment Configuration

**Create environment file** (cross-platform):
```bash
# Linux/macOS
cp flexible-graphrag/env-sample.txt flexible-graphrag/.env

# Windows Command Prompt  
copy flexible-graphrag\env-sample.txt flexible-graphrag\.env
```
Edit `.env` with your database credentials and API keys.

### Python Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd project-directory/flexible-graphrag
   ```

2. Create a virtual environment using UV and activate it:
   ```bash
   # From project root directory
   uv venv
   .\.venv\Scripts\Activate  # On Windows (works in both Command Prompt and PowerShell)
   # or
   source .venv/bin/activate  # on macOS/Linux
   ```

3. Install Python dependencies:
   ```bash
   # Navigate to flexible-graphrag directory and install requirements
   cd flexible-graphrag
   uv pip install -r requirements.txt
   ```

4. Create a `.env` file by copying the sample and customizing:
   ```bash
   # Copy sample environment file (use appropriate command for your platform)
   cp env-sample.txt .env  # Linux/macOS
   copy env-sample.txt .env  # Windows
   ```
   
   Edit `.env` with your specific configuration. See [docs/ENVIRONMENT-CONFIGURATION.md](docs/ENVIRONMENT-CONFIGURATION.md) for detailed setup guide.

### Frontend Setup

**Production Mode** (backend does not serve frontend):
- **Backend API**: http://localhost:8000 (FastAPI server only)
- **Frontend deployment**: Separate deployment (nginx, Apache, static hosting, etc.)
- Both standalone and Docker frontends point to backend at localhost:8000

**Development Mode** (frontend and backend run separately):
- **Backend API**: http://localhost:8000 (FastAPI server only)
- **Angular Dev**: http://localhost:4200 (ng serve)
- **React Dev**: http://localhost:5173 (npm run dev)  
- **Vue Dev**: http://localhost:5174 (npm run dev)

Choose one of the following frontend options to work with:

#### React Frontend

1. Navigate to the React frontend directory:
   ```bash
   cd flexible-graphrag-ui/frontend-react
   ```

2. Install Node.js dependencies:
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

2. Install Node.js dependencies:
   ```bash
   npm install
   ```

3. Start the development server (uses Angular CLI):
   ```bash
   npm start
   ```

The Angular frontend will be available at `http://localhost:4200`.

**Note**: If `ng build` gives budget errors, use `npm start` for development instead.

#### Vue Frontend

1. Navigate to the Vue frontend directory:
   ```bash
   cd flexible-graphrag-ui/frontend-vue
   ```

2. Install Node.js dependencies:
   ```bash
   npm install
   ```

3. Start the development server (uses Vite):
   ```bash
   npm run dev
   ```

The Vue frontend will be available at `http://localhost:3000`.

## Running the Application

### Start the Python Backend

From the project root directory:

```bash
cd flexible-graphrag
uv run start.py
```

The backend will be available at `http://localhost:8000`.

### Start Your Preferred Frontend

Follow the instructions in the Frontend Setup section for your chosen frontend framework.

### Frontend Deployment

#### Build Frontend
```bash
# Angular (may have budget warnings - safe to ignore for development)
cd flexible-graphrag-ui/frontend-angular
ng build

# React  
cd flexible-graphrag-ui/frontend-react
npm run build

# Vue
cd flexible-graphrag-ui/frontend-vue
npm run build
```

**Angular Build Notes**:
- Budget warnings are common in Angular and usually safe to ignore for development
- For production, consider optimizing bundle sizes or adjusting budget limits in `angular.json`
- Development mode: Use `npm start` to avoid build issues

#### Start Production Server
```bash
cd flexible-graphrag
uv run start.py
```

The backend provides:
- API endpoints under `/api/*`
- Independent operation focused on data processing and search
- Clean separation from frontend serving concerns

**Backend API Endpoints**:
- **API Base**: http://localhost:8000/api/
- **API Endpoints**: `/api/ingest`, `/api/search`, `/api/query`, `/api/status`, etc.
- **Health Check**: http://localhost:8000/api/health

**Frontend Deployment**:
- **Manual Deployment**: Deploy frontends independently using your preferred method (nginx, Apache, static hosting, etc.)
- **Frontend Configuration**: Both standalone and Docker frontends point to backend at `http://localhost:8000/api/`
- Each frontend can be built and deployed separately based on your needs

## Full-Stack Debugging

The project includes a `sample-launch.json` file with VS Code debugging configurations for all three frontend options and the backend. Copy this file to `.vscode/launch.json` to use these configurations.

Key debugging configurations include:

1. **Full Stack with React and Python**: Debug both the React frontend and Python backend simultaneously
2. **Full Stack with Angular and Python**: Debug both the Angular frontend and Python backend simultaneously
3. **Full Stack with Vue and Python**: Debug both the Vue frontend and Python backend simultaneously
4. Note when ending debugging, you will need to stop the Python backend and the frontend separately.

Each configuration sets up the appropriate ports, source maps, and debugging tools for a seamless development experience. You may need to adjust the ports and paths in the `launch.json` file to match your specific setup.

## Usage

The system provides a tabbed interface for document processing and querying. Follow these steps in order:

### 1. Sources Tab

Configure your data source and select files for processing:

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

### Technical Implementation

The system combines three retrieval methods for comprehensive hybrid search:

- **Vector Similarity Search**: Uses embeddings to find semantically similar content based on meaning rather than exact word matches
- **Full-Text Search**: Keyword-based search using:
  - **Search Engines**: Elasticsearch or OpenSearch (which implement BM25 algorithms)
  - **Built-in Option**: LlamaIndex local BM25 implementation for simpler deployments
- **Graph Traversal**: Leverages knowledge graphs to find related entities and relationships, enabling GraphRAG (Graph-enhanced Retrieval Augmented Generation) that can surface contextually relevant information through entity connections and semantic relationships

**How GraphRAG Works**: The system extracts entities (people, organizations, concepts) and relationships from documents, stores them in a graph database, then uses graph traversal during retrieval to find not just direct matches but also related information through entity connections. This enables more comprehensive answers that incorporate contextual relationships between concepts.

### Testing Cleanup

Between tests you can clean up data:
- **Vector Indexes**: See [docs/VECTOR-DIMENSIONS.md](docs/VECTOR-DIMENSIONS.md) for vector database cleanup instructions
- **Graph Data**: See [flexible-graphrag/README-neo4j.md](flexible-graphrag/README-neo4j.md) for graph-related cleanup commands
- **Neo4j**: Use on a test Neo4j database no one else is using 

## Project Structure

- `/flexible-graphrag`: Python FastAPI backend with LlamaIndex
  - `main.py`: FastAPI REST API server (clean, no MCP)
  - `backend.py`: Shared business logic core used by both API and MCP
  - `config.py`: Configurable settings for data sources, databases, and LLM providers
  - `hybrid_system.py`: Main hybrid search system using LlamaIndex
  - `document_processor.py`: Document processing with Docling integration
  - `factories.py`: Factory classes for LLM and database creation
  - `sources.py`: Data source connectors (filesystem, CMIS, Alfresco)
  - `requirements.txt`: FastAPI and LlamaIndex dependencies
  - `start.py`: Startup script for uvicorn
  - `install.py`: Installation helper script

- `/flexible-graphrag-mcp`: Standalone MCP server
  - `main.py`: HTTP-based MCP server (calls REST API)
  - `pyproject.toml`: MCP package definition with minimal dependencies
  - `README.md`: MCP server setup and installation instructions
  - **Lightweight**: Only 4 dependencies (fastmcp, nest-asyncio, httpx, python-dotenv)

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

- `/docs`: Documentation
  - `ARCHITECTURE.md`: Complete system architecture and component relationships
  - `DEPLOYMENT-CONFIGURATIONS.md`: Standalone, hybrid, and full Docker deployment guides
  - `ENVIRONMENT-CONFIGURATION.md`: Environment setup guide with database switching
  - `VECTOR-DIMENSIONS.md`: Vector database cleanup instructions
  - `SCHEMA-EXAMPLES.md`: Knowledge graph schema examples
  - `PERFORMANCE.md`: Performance benchmarks and optimization guides
  - `DEFAULT-USERNAMES-PASSWORDS.md`: Database credentials and dashboard access
  - `PORT-MAPPINGS.md`: Complete port reference for all services

- `/scripts`: Utility scripts
  - `create_opensearch_pipeline.py`: OpenSearch hybrid search pipeline setup
  - `setup-opensearch-pipeline.sh/.bat`: Cross-platform pipeline creation

- `/tests`: Test suite
  - `test_bm25_*.py`: BM25 configuration and integration tests
  - `conftest.py`: Test configuration and fixtures
  - `run_tests.py`: Test runner

## License

This project is licensed under the terms of the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
