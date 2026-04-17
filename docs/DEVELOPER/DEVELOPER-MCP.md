# MCP Developer Setup

Test and debug the MCP server using MCP Inspector with 3 terminals.

---

## 3-Terminal Setup

### Terminal 1 — Start the Backend

```bash
uv venv venv-3.13 --python 3.13
venv-3.13\Scripts\Activate   # Windows
source venv-3.13/bin/activate  # Linux/macOS
uv pip install flexible-graphrag
flexible-graphrag
```

Backend runs at `http://localhost:8000`. Keep this terminal running.

---

### Terminal 2 — Start the MCP Server (HTTP mode)

```bash
uv venv venv-mcp --python 3.13
venv-mcp\Scripts\Activate   # Windows
source venv-mcp/bin/activate  # Linux/macOS
uv pip install flexible-graphrag-mcp
flexible-graphrag-mcp --http --port 3002
```

MCP server runs at `http://localhost:3002`. Keep this terminal running.

---

### Terminal 3 — MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Open the URL shown in the console (the token is pre-filled). Configure:

- **Transport**: Streamable HTTP
- **URL**: `http://localhost:3002/mcp`

Click **Connect** — you can now browse and test all 9 tools interactively.

---

## Available Tools

| Tool | Description |
|---|---|
| `get_system_status()` | Verify setup — check all database connections and config |
| `ingest_documents()` | Process documents from any of the 13 data sources |
| `ingest_text(content, source_name)` | Ingest and analyze specific text content |
| `search_documents(query, top_k)` | Hybrid search — returns ranked excerpts with scores |
| `query_documents(query, top_k)` | AI Q&A — generates an answer from your document corpus |
| `test_with_sample()` | Quick system test using built-in Star Wars sample text |
| `check_processing_status(id)` | Poll status of a long-running async ingestion task |
| `get_python_info()` | Python environment and dependency diagnostics |
| `health_check()` | Verify backend API is reachable at `localhost:8000` |

### `ingest_documents()` — Data Source Config

| Source | Key Config Fields |
|---|---|
| `filesystem` | `paths` — list of file or directory paths |
| `alfresco` | `base_url`, `username`, `password`, `paths`; also `nodeDetails` for KG Spaces |
| `cmis` | `cmis_url`, `username`, `password`, `paths` |
| `s3` | `bucket`, `aws_access_key_id`, `aws_secret_access_key`, `region` |
| `azure_blob` | `connection_string`, `container_name` |
| `gcs` | `bucket_name`, `credentials_path` |
| `onedrive` | `client_id`, `client_secret`, `tenant_id` |
| `google_drive` | `credentials_path`, `folder_id` |
| `sharepoint` | `client_id`, `client_secret`, `tenant_id`, `site_url` |
| `box` | `client_id`, `client_secret`, `folder_id` |
| `web` | `urls` — list of web page URLs |
| `wikipedia` | `titles` — list of article titles |
| `youtube` | `urls` — list of YouTube video URLs |

All sources support `skip_graph: true` to skip KG extraction (vector + search only).

---

## Claude Desktop Setup

Add to `claude_desktop_config.json` (stdio transport — no HTTP server needed for Claude):

=== "uvx (recommended)"

    ```json
    {
      "mcpServers": {
        "flexible-graphrag": {
          "command": "uvx",
          "args": ["flexible-graphrag-mcp"],
          "env": {
            "FLEXIBLE_GRAPHRAG_API_BASE": "http://localhost:8000"
          }
        }
      }
    }
    ```

=== "pipx"

    ```bash
    pipx install flexible-graphrag-mcp
    ```

    ```json
    {
      "mcpServers": {
        "flexible-graphrag": {
          "command": "flexible-graphrag-mcp",
          "env": {
            "FLEXIBLE_GRAPHRAG_API_BASE": "http://localhost:8000"
          }
        }
      }
    }
    ```

Config file locations:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

!!! tip
    Claude Desktop uses **stdio** transport — it launches the MCP server process directly. Terminal 2 (HTTP mode) is only needed for MCP Inspector testing.

Restart Claude Desktop after saving the config, then test with:

```
@flexible-graphrag Check system status
```

---

## Cursor Setup

In Cursor settings → MCP, add:

```json
{
  "mcpServers": {
    "flexible-graphrag": {
      "command": "uvx",
      "args": ["flexible-graphrag-mcp"],
      "env": {
        "FLEXIBLE_GRAPHRAG_API_BASE": "http://localhost:8000"
      }
    }
  }
}
```

---

## Troubleshooting

**Backend not reachable:**

```bash
curl http://localhost:8000/api/health
# Expected: {"status":"ok"}
```

**MCP server not responding:**

```bash
curl http://localhost:3002
```

**Claude Desktop not connecting:**

1. Restart Claude Desktop after any config change
2. Check the config file path is correct for your OS
3. Verify the backend is running (`curl http://localhost:8000/api/health`)
