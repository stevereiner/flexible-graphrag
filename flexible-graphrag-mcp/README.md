# Flexible GraphRAG MCP Server

Model Context Protocol (MCP) server for Flexible GraphRAG system with optimized configurations for Claude Desktop and MCP Inspector.

## Quick Start

### 1. Choose Your Platform & Method

| Platform | Recommended | Alternative | Why |
|----------|-------------|-------------|-----|
| **Windows** | `pipx` | `uvx` | Clean system install vs. no install needed |
| **macOS** | `pipx` | `uvx` | Clean system install vs. no install needed |

### 2. Install

#### pipx (Recommended)
```bash
cd flexible-graphrag-mcp
pipx install .
```

#### uvx (No installation)
```bash
# Auto-installs when first used
uvx flexible-graphrag-mcp
```

### 3. Configure Claude Desktop

Copy the appropriate config file to your Claude Desktop configuration:

#### Windows
- **Config location**: `%APPDATA%\Claude\claude_desktop_config.json`
- **pipx**: Use `claude-desktop-configs/windows/pipx-config.json`
- **uvx**: Use `claude-desktop-configs/windows/uvx-config.json`

#### macOS
- **Config location**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **pipx**: Use `claude-desktop-configs/macos/pipx-config.json`
- **uvx**: Use `claude-desktop-configs/macos/uvx-config.json`

### 4. Test Installation

Restart Claude Desktop and test:
```
@flexible-graphrag Check system status
```

## Configuration Files

### Claude Desktop Configs

```
claude-desktop-configs/
├── windows/
│   ├── pipx-config.json    # Windows + pipx
│   └── uvx-config.json     # Windows + uvx
└── macos/
    ├── pipx-config.json    # macOS + pipx
    └── uvx-config.json     # macOS + uvx

mcp-inspector/
├── pipx-stdio-config.json  # MCP Inspector + pipx (stdio - try first)
├── pipx-http-config.json   # MCP Inspector + pipx (HTTP - fallback)
├── uvx-stdio-config.json   # MCP Inspector + uvx (stdio - try first)
└── uvx-http-config.json    # MCP Inspector + uvx (HTTP - fallback)
```

### Key Differences

#### Windows Configs
- Include Unicode environment variables (`PYTHONIOENCODING`, `PYTHONLEGACYWINDOWSSTDIO`)
- Prevent Unicode encoding errors with emojis and special characters

#### macOS Configs  
- Clean and simple - no special environment variables needed
- Standard MCP protocol over stdio

#### MCP Inspector Configs
- **stdio configs**: Standard MCP protocol - try these first
- **http configs**: HTTP transport fallback if stdio has issues (like proxy problems)
- HTTP mode runs on port 3001 by default (configurable with `--port` argument)
- Platform-independent - works on Windows, macOS, and Linux

## Installation Methods

### pipx (Recommended)

**Advantages:**
- ✅ Clean system-level installation
- ✅ Isolated dependencies
- ✅ Simple `flexible-graphrag-mcp` command
- ✅ Automatic PATH management

**Installation:**
```bash
cd flexible-graphrag-mcp
pipx install .
```

**Update:**
```bash
pipx reinstall flexible-graphrag-mcp
```

### uvx (Alternative)

**Advantages:**
- ✅ No installation required
- ✅ Automatic dependency management
- ✅ Always runs latest version
- ✅ Great for testing

**Usage:**
```bash
uvx flexible-graphrag-mcp
```

## Prerequisites

### Backend Server Required
The MCP server communicates with the FastAPI backend, so you must have it running:

```bash
cd flexible-graphrag
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

### Environment Configuration
Ensure your `.env` file is properly configured in the main project directory:

```env
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=neo4j

# LLM Configuration
OPENAI_API_KEY=your-key
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
```

## HTTP Mode for MCP Inspector

For debugging with MCP Inspector, the server supports HTTP transport:

```bash
# Using pipx
flexible-graphrag-mcp --http --port 3001

# Using uvx  
uvx flexible-graphrag-mcp --http --port 3001

# Custom port
flexible-graphrag-mcp --http --port 8080
```

The HTTP mode is automatically configured in the `mcp-inspector/` config files and works better than stdio for debugging complex MCP interactions.

## Available Tools

- **`get_system_status()`** - System status and configuration
- **`ingest_documents()`** - Ingest documents from 13 data sources (all support `skip_graph`; filesystem/Alfresco/CMIS use `paths`; Alfresco also supports `nodeDetails` list)
- **`ingest_text(content, source_name)`** - Ingest custom text content
- **`search_documents(query, top_k)`** - Hybrid search for document retrieval
- **`query_documents(query, top_k)`** - AI-generated answers from documents
- **`test_with_sample()`** - Quick test with sample text
- **`check_processing_status(processing_id)`** - Check async operation status
- **`get_python_info()`** - Python environment information
- **`health_check()`** - Backend connectivity check

## Tool Details

### `ingest_documents`
Ingest documents from various sources into the knowledge graph.

**Parameters:**
- `data_source` (string, default: "filesystem"): Type of data source
  - Options: `filesystem`, `cmis`, `alfresco`, `web`, `wikipedia`, `youtube`, `s3`, `gcs`, `azure_blob`, `onedrive`, `sharepoint`, `box`, `google_drive`
- `paths` (string, optional): File path(s) to process (for filesystem, Alfresco, and CMIS sources)
  - Single path: `"/path/to/file.pdf"`
  - Multiple paths (JSON array): `["file1.pdf", "file2.docx"]`
- `skip_graph` (boolean, default: false): Skip knowledge graph extraction on a per-ingest basis for faster performance (vector + search only)
- `cmis_config` (string, optional): CMIS configuration as JSON string
- `alfresco_config` (string, optional): Alfresco configuration as JSON string (also supports `nodeDetails` list for multi-select)
- `web_config` (string, optional): Web page configuration as JSON string
- `wikipedia_config` (string, optional): Wikipedia configuration as JSON string
- `youtube_config` (string, optional): YouTube configuration as JSON string
- `s3_config` (string, optional): Amazon S3 configuration as JSON string
- `gcs_config` (string, optional): Google Cloud Storage configuration as JSON string
- `azure_blob_config` (string, optional): Azure Blob Storage configuration as JSON string
- `onedrive_config` (string, optional): Microsoft OneDrive configuration as JSON string
- `sharepoint_config` (string, optional): Microsoft SharePoint configuration as JSON string
- `box_config` (string, optional): Box configuration as JSON string
- `google_drive_config` (string, optional): Google Drive configuration as JSON string

**Example - Basic filesystem with skip_graph:**
```json
{
  "data_source": "filesystem",
  "paths": "[\"./sample-docs/cmispress.txt\", \"./sample-docs/space-station.txt\"]",
  "skip_graph": true
}
```

**Example - CMIS with single path:**
```json
{
  "data_source": "cmis",
  "paths": "[\"/Shared/GraphRAG/cmispress.txt\"]",
  "cmis_config": "{\"url\": \"https://cmis.example.com\", \"username\": \"admin\", \"password\": \"password\", \"folder_path\": \"/Shared/GraphRAG\"}"
}
```

**Example - Alfresco with single path:**
```json
{
  "data_source": "alfresco",
  "paths": "[\"/Shared/GraphRAG/space-station.txt\"]",
  "alfresco_config": "{\"url\": \"https://alfresco.example.com\", \"username\": \"admin\", \"password\": \"password\", \"path\": \"/Shared/GraphRAG\"}"
}
```

**Example - Alfresco with nodeDetails (multi-select from ACA):**
```json
{
  "data_source": "alfresco",
  "alfresco_config": "{\"url\": \"https://alfresco.example.com\", \"username\": \"admin\", \"password\": \"password\", \"nodeDetails\": [{\"id\": \"abc123\", \"name\": \"doc1.pdf\", \"path\": \"/Shared/GraphRAG/doc1.pdf\", \"isFile\": true, \"isFolder\": false}], \"recursive\": false}"
}
```

**Example - Amazon S3:**
```json
{
  "data_source": "s3",
  "s3_config": "{\"bucket_name\": \"my-bucket\", \"prefix\": \"documents/\", \"access_key\": \"AKIAIOSFODNN7EXAMPLE\", \"secret_key\": \"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\", \"region_name\": \"us-east-1\"}"
}
```

## Example Usage

### Basic Document Ingestion
```
@flexible-graphrag Please ingest documents from C:/Documents/research
```

### Fast Ingestion (Skip Graph)
```
@flexible-graphrag Ingest from ./sample-docs/ with skip_graph=true for faster processing (works with all data sources)
```

### Alfresco Multi-Select
```
@flexible-graphrag Ingest from Alfresco with this config: {"url": "https://alfresco.example.com", "username": "admin", "password": "password", "nodeDetails": [{"id": "abc123", "name": "report.pdf", "path": "/Shared/Reports/report.pdf", "isFile": true, "isFolder": false}]}
```

### Custom Text Processing
```
@flexible-graphrag Ingest this text: "Claude is an AI assistant created by Anthropic."
```

### Search and Q&A
```
@flexible-graphrag Search for "machine learning algorithms" in the documents
```

```
@flexible-graphrag What are the main conclusions from the research papers?
```

### Async Processing
```
@flexible-graphrag Check processing status for ID abc123
```

## Troubleshooting

### Common Issues

#### pipx Command Not Found
```bash
# Install pipx
python -m pip install --user pipx
pipx ensurepath
```

#### uvx Command Not Found
```bash
# Install uvx via uv
uv tool install uvx
```

#### Unicode Errors on Windows
- Windows configs include required environment variables automatically
- If issues persist, check that you're using the correct Windows config file

#### Backend Connection Error
- Ensure FastAPI backend is running on `localhost:8000`
- Check that `.env` file is properly configured
- Test backend directly: `curl http://localhost:8000/api/health`

#### Claude Desktop Not Recognizing Server
- Restart Claude Desktop after config changes
- Check config file path and JSON syntax
- Verify command exists: run `flexible-graphrag-mcp` or `uvx flexible-graphrag-mcp` in terminal

## Development

### Test Scripts
```bash
# Windows
.\test-installation.ps1

# macOS/Linux
./test-installation.sh
```

These scripts test both installation methods and help verify everything works correctly.

### Adding New Tools
1. Add tool function to `main.py` with `@mcp.tool()` decorator
2. Update tool list in README
3. Test with MCP Inspector for debugging

## MCP Inspector Integration

Use the configs in `mcp-inspector/` directory for debugging with the MCP Inspector tool. These work with both pipx and uvx installations and are platform-independent.