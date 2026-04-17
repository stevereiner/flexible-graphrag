# Flexible GraphRAG MCP Server - Quick Usage Guide

## Prerequisites

✅ **Backend Server Running**: Ensure the FastAPI backend is running on port 8000:
```bash
cd flexible-graphrag
python main.py
# Should show: "Uvicorn running on http://0.0.0.0:8000"
```

✅ **Environment**: Virtual environment activated with all dependencies installed

## Quick Start Options

### Option 1: Claude Desktop (Recommended)

1. **Install the MCP server:**
   ```bash
   cd flexible-graphrag-mcp
   pipx install .
   ```

2. **Configure Claude Desktop:**
   - Copy the appropriate config to Claude Desktop:
     - **Windows**: `claude-desktop-configs/windows/pipx-config.json` → `%APPDATA%\Claude\claude_desktop_config.json`
     - **macOS**: `claude-desktop-configs/macos/pipx-config.json` → `~/Library/Application Support/Claude/claude_desktop_config.json`

3. **Test in Claude Desktop:**
   ```
   @flexible-graphrag Check system status
   ```

### Option 2: MCP Inspector (For Debugging)

1. **Install the MCP server:**
   ```bash
   cd flexible-graphrag-mcp
   pipx install .
   ```

2. **Choose transport mode:**
   
   **Option 2A: stdio (try first):**
   ```bash
   flexible-graphrag-mcp
   ```
   Use config: `mcp-inspector/pipx-stdio-config.json`
   
   **Option 2B: HTTP (if stdio has issues):**
   ```bash
   flexible-graphrag-mcp --http --port 3001
   ```
   Use config: `mcp-inspector/pipx-http-config.json`

### Option 3: No Installation (uvx)

#### For Claude Desktop:
```bash
uvx flexible-graphrag-mcp
```
Use config: `claude-desktop-configs/windows/uvx-config.json` or `claude-desktop-configs/macos/uvx-config.json`

#### For MCP Inspector:
**stdio (try first):**
```bash
uvx flexible-graphrag-mcp
```
Use config: `mcp-inspector/uvx-stdio-config.json`

**HTTP (if stdio has issues):**
```bash
uvx flexible-graphrag-mcp --http --port 3001
```
Use config: `mcp-inspector/uvx-http-config.json`

## Available Tools

| Tool | Description | Example Usage |
|------|-------------|---------------|
| `get_system_status()` | Check system health and configuration | System diagnostics |
| `ingest_documents()` | Process documents from 13 data sources (all support `skip_graph`; filesystem/Alfresco/CMIS use `paths`; Alfresco also supports `nodeDetails` list) | Bulk document ingestion |
| `ingest_text()` | Process custom text content | Quick text analysis |
| `search_documents()` | Hybrid search across all content | Find relevant documents |
| `query_documents()` | AI-powered Q&A over your documents | Ask questions about content |
| `test_with_sample()` | Quick test with sample Star Wars text | System verification |
| `check_processing_status()` | Monitor async operations | Track long-running tasks |
| `health_check()` | Verify backend connectivity | Connection diagnostics |

## Configuration Files Reference

```
flexible-graphrag-mcp/
├── claude-desktop-configs/
│   ├── windows/
│   │   ├── pipx-config.json     # Windows + pipx
│   │   └── uvx-config.json      # Windows + uvx
│   └── macos/
│       ├── pipx-config.json     # macOS + pipx
│       └── uvx-config.json      # macOS + uvx
└── mcp-inspector/
    ├── pipx-stdio-config.json   # MCP Inspector + pipx (stdio)
    ├── pipx-http-config.json    # MCP Inspector + pipx (HTTP)
    ├── uvx-stdio-config.json    # MCP Inspector + uvx (stdio)
    └── uvx-http-config.json     # MCP Inspector + uvx (HTTP)
```

## Key Features

### ✨ Async Processing
- Long operations return immediately with a `processing_id`
- Use `check_processing_status(processing_id)` to monitor progress
- Real-time progress updates with time estimates

### 🔍 HTTP Mode for Debugging
- Better compatibility with MCP Inspector than stdio
- Runs on port 3001 by default
- Supports custom ports: `--http --port 8080`

### 🌐 Multiple Data Sources
- **Filesystem**: Local files and directories (uses `paths` parameter)
- **Enterprise Repositories**: Alfresco (uses `paths` and also supports `nodeDetails` list for multi-select from ACA), CMIS (uses `paths`), SharePoint, Box (use config-specific parameters)
- **Web Sources**: Web pages, Wikipedia, YouTube
- **Cloud Storage**: Amazon S3, Google Cloud Storage, Azure Blob, OneDrive, Google Drive
- **Text**: Custom text content
- **Performance**: All sources support `skip_graph` on a per-ingest basis for faster performance (vector + search only)

### 🔧 Windows Compatibility
- Unicode encoding handled automatically
- Emoji and special character support
- No manual environment variable setup needed

## Troubleshooting

### Backend Connection Issues
```bash
# Test backend connectivity
curl http://localhost:8000/api/health
# Should return: {"status":"ok"}
```

### MCP Server Issues
```bash
# Test HTTP mode directly
cd flexible-graphrag-mcp
python main.py --http --port 3001
# Should show: "🌐 Running in HTTP mode on port 3001"
```

### Claude Desktop Issues
1. Restart Claude Desktop after config changes
2. Check logs for encoding errors
3. Verify config file paths are correct

## Quick Test Sequence

1. **Start backend**: `cd flexible-graphrag && python main.py`
2. **Start MCP server**: `flexible-graphrag-mcp --http --port 3001`
3. **Test connectivity**: `curl http://localhost:3001`
4. **Use in Claude**: `@flexible-graphrag Check system status`

## Environment Variables

The MCP server automatically uses:
- `FLEXIBLE_GRAPHRAG_URL` (default: `http://localhost:8000`)
- `PYTHONIOENCODING=utf-8` (Windows Unicode support)
- `PYTHONLEGACYWINDOWSSTDIO=1` (Windows console compatibility)

## Need Help?

- Check the full README.md for detailed installation instructions
- Use `python test-http-mode.py` to verify HTTP mode functionality
- Test installation with `./test-installation.ps1` (Windows) or `./test-installation.sh` (Unix/macOS)
