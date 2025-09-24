# Flexible GraphRAG

A configurable hybrid search system that combines full-text search, vector search, and GraphRAG across multiple data sources with LlamaIndex integration.

## 🚀 Features

- **Multiple Data Sources**: File system, CMIS, Alfresco, web pages, Wikipedia, YouTube, Amazon S3, Google Cloud Storage, Azure Blob Storage, OneDrive, SharePoint, Box, and Google Drive
- **Hybrid Search**: Vector similarity, BM25 full-text, and graph traversal
- **Configurable Backends**: Neo4j, Qdrant, Elasticsearch, OpenSearch support
- **Multiple LLM Providers**: OpenAI, Ollama, Gemini, Azure OpenAI, Anthropic
- **Advanced Document Processing**: Comprehensive file format support with intelligent processing
- **Schema Support**: Optional entity/relationship schema enforcement
- **FastAPI Backend**: REST API with configurable data sources

## 📄 Supported File Formats

This project supports a comprehensive range of document formats through intelligent processing:

### Document Formats (Processed with Docling)
- **PDF Documents**: `.pdf` - Advanced layout analysis with table and formula extraction
- **Microsoft Office (Modern)**: 
  - Word: `.docx` - Full document structure preservation
  - Excel: `.xlsx` - Spreadsheet data and table extraction
  - PowerPoint: `.pptx` - Slide content and layout analysis

### Text & Markup Formats
- **Plain Text**: `.txt` - Direct text processing (no Docling conversion)
- **Markdown**: `.md`, `.markdown` - Direct text processing (no Docling conversion)
- **Web Formats**: `.html`, `.htm`, `.xhtml` - Processed with Docling for structure
- **Data Formats**: `.csv`, `.xml`, `.json` - Processed with Docling for structured data
- **Documentation**: `.asciidoc`, `.adoc` - Processed with Docling for markup preservation

### Image Formats (Processed with Docling OCR)
- **Common Images**: `.png`, `.jpg`, `.jpeg` - Text extraction via OCR
- **Professional Images**: `.tiff`, `.tif`, `.bmp`, `.webp` - OCR with layout analysis

### Processing Intelligence
- **Adaptive Output**: Docling automatically converts to **markdown** when tables are detected, **plain text** for better entity extraction
- **Table Preservation**: Complex table structures maintained in markdown format
- **Formula Recognition**: Mathematical formulas and equations properly extracted
- **Layout Analysis**: Document structure, headers, and formatting preserved
- **OCR Integration**: Text extraction from images and scanned documents

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Sources  │    │   Processing    │    │   Search Types  │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ • File System   │───▶│ • Docling       │───▶│ • Vector Search │
│ • CMIS Repos    │    │ • LlamaIndex    │    │ • Graph Traversal│
│ • Alfresco      │    │ • Schema Extract│    │ • BM25 Full-text│
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                      ┌─────────▼─────────┐
                      │  Storage Backends │
                      ├───────────────────┤
                      │ • Neo4j (Vector+Graph)
                      │ • Kuzu (Graph)
                      │ • Qdrant (Vector)
                      │ • Elasticsearch (Vector+Text)
                      │ • OpenSearch (Vector+Text)
                      └───────────────────┘
```

## 🛠️ Installation

### Prerequisites

**Required:**
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Neo4j database running
- OpenAI API key or Ollama setup

**Optional (depending on data source):**
- CMIS repository (only if using CMIS data source)
- Alfresco repository (only if using Alfresco data source)
- File system data source requires no additional setup

### Quick Start

1. **Install dependencies**:
   ```bash
   cd flexible-graphrag
   uv run install.py
   ```

2. **Configure environment**:
   ```bash
   cp env-sample.txt .env
   # Edit .env with your database and API credentials
   ```

3. **Start the server**:
   ```bash
   uv run start.py
   ```
   Or for development:
   ```bash
   uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Access the backend API**:
   - **Backend API**: http://localhost:8000

## ⚙️ Configuration

The system is highly configurable through environment variables:

### Data Sources
- `DATA_SOURCE`: `filesystem`, `cmis`, or `alfresco`
- `SOURCE_PATHS`: JSON array of file/folder paths

### Databases
- `VECTOR_DB`: `neo4j`, `qdrant`, `elasticsearch`, `opensearch`
- `GRAPH_DB`: `neo4j`, `kuzu`
- `SEARCH_DB`: `elasticsearch`, `opensearch`

### LLM Providers
- `LLM_PROVIDER`: `openai`, `ollama`, `gemini`, `azure_openai`, `anthropic`

### ⚠️ Vector Dimension Compatibility
**CRITICAL**: When switching between different embedding models, you **MUST delete existing vector indexes** due to dimension incompatibility:

- **OpenAI**: 1536 dimensions (default) or 3072 dimensions (large models)
- **Ollama**: 1024 dimensions (default) or 768/384 dimensions (other models)
- **Azure OpenAI**: Same as OpenAI dimensions

**See [../VECTOR-DIMENSIONS.md](../VECTOR-DIMENSIONS.md) for detailed cleanup instructions.**

See `env-sample.txt` for complete configuration options.

## 📡 API Endpoints

### Core Operations
- `POST /api/ingest`: Ingest documents from configured data source
- `POST /api/search`: Hybrid search returning ranked results
- `POST /api/query`: Q&A with AI-generated answers
- `GET /api/status`: System status and configuration

### Testing
- `POST /api/test-sample`: Quick test with sample text
- `GET /api/python-info`: Python environment info

## 🔍 Usage Examples

### 1. Document Ingestion

#### File System (supports 12+ file formats)
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "filesystem",
    "paths": ["./documents", "./reports/quarterly.pdf", "./data/spreadsheet.xlsx"]
  }'
```

#### CMIS Repository
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "cmis",
    "cmis_config": {
      "url": "http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom",
      "username": "admin",
      "password": "admin",
      "folder_path": "/Sites/example/documentLibrary"
    }
  }'
```

#### Alfresco Repository
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "alfresco",
    "alfresco_config": {
      "url": "http://localhost:8080/alfresco",
      "username": "admin", 
      "password": "admin",
      "path": "/Sites/example/documentLibrary"
    }
  }'
```

#### Web Pages
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "web",
    "web_config": {
      "url": "https://example.com/article"
    }
  }'
```

#### Wikipedia Articles
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "wikipedia",
    "wikipedia_config": {
      "query": "Artificial Intelligence",
      "language": "en",
      "max_docs": 1
    }
  }'
```

#### YouTube Videos
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "youtube",
    "youtube_config": {
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "chunk_size_seconds": 60
    }
  }'
```

#### Amazon S3
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "s3",
    "s3_config": {
      "bucket": "my-bucket",
      "key": "documents/",
      "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
      "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
      "region_name": "us-east-1"
    }
  }'
```

#### Google Cloud Storage
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "gcs",
    "gcs_config": {
      "bucket": "my-documents-bucket",
      "key": "documents/",
      "project_id": "my-project"
    }
  }'
```

#### Azure Blob Storage
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "azure_blob",
    "azure_blob_config": {
      "container_name": "documents",
      "account_name": "mystorageaccount",
      "account_key": "your-account-key"
    }
  }'
```

#### Microsoft OneDrive
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "onedrive",
    "onedrive_config": {
      "client_id": "your-client-id",
      "client_secret": "your-client-secret",
      "tenant_id": "your-tenant-id",
      "folder_path": "/Documents"
    }
  }'
```

#### Microsoft SharePoint
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "sharepoint",
    "sharepoint_config": {
      "client_id": "your-client-id",
      "client_secret": "your-client-secret",
      "tenant_id": "your-tenant-id",
      "sharepoint_site_name": "your-site-name",
      "sharepoint_folder_path": "/Shared Documents"
    }
  }'
```

#### Box
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "box",
    "box_config": {
      "access_token": "your-access-token",
      "box_folder_id": "0"
    }
  }'
```

#### Google Drive
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "google_drive",
    "google_drive_config": {
      "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "credentials_path": "path/to/credentials.json"
    }
  }'
```

### 2. Hybrid Search
```bash
curl -X POST "http://localhost:8000/api/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning algorithms",
    "top_k": 5
  }'
```

### 3. Q&A Query
```bash
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the main findings in the research papers?",
    "top_k": 10
  }'
```

## 🎯 Key Features

1. **LlamaIndex Integration**: Uses LlamaIndex ecosystem for flexible RAG
2. **Configurable Architecture**: Multiple database and LLM provider support
3. **Advanced Document Processing**: Docling for superior PDF/DOCX conversion
4. **Hybrid Search**: Combines vector, graph, and full-text search
5. **Schema Flexibility**: Optional entity/relationship schema enforcement
6. **Modern Stack**: Updated dependencies and patterns

## 🧪 Development

### Project Structure
```
flexible-graphrag/
├── config.py              # Configuration and settings
├── document_processor.py  # Docling integration
├── factories.py          # LLM and database factories
├── hybrid_system.py      # Main search system
├── sources.py            # Data source connectors
├── backend.py            # Shared business logic core
├── main.py              # FastAPI application
├── start.py             # Startup script
└── requirements.txt     # Dependencies
```

## 🔧 Troubleshooting

### Common Issues

1. **Neo4j Connection**: Ensure Neo4j is running on bolt://localhost:7687
2. **Missing API Keys**: Check your .env file for required API keys
3. **BM25 Search**: BM25 is built into LlamaIndex - use BM25 search configuration for full-text search
4. **Memory**: Large documents may require increased memory limits

## 🚢 Next Steps

You can now:
1. **Install**: `uv run install.py`
2. **Configure**: Copy and edit `env-sample.txt` to `.env`
3. **Start**: `uv run start.py` or `uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
4. **Use**: Open http://localhost:8000 and start ingesting documents!

The system will work with just Neo4j and OpenAI/Ollama - BM25 search is built into LlamaIndex for full-text search capabilities.