# MCP Server — Quickstart

The `flexible-graphrag-mcp` package is a standalone MCP server that connects Claude Desktop, Cursor, and other MCP clients to the Flexible GraphRAG backend.

---

## Step 1 — Install the MCP server

=== "uvx (no install needed)"

    ```bash
    # uvx downloads and runs automatically — nothing to pre-install
    uvx flexible-graphrag-mcp
    ```

=== "pipx (persistent install)"

    ```bash
    pipx install flexible-graphrag-mcp
    ```

=== "pip / uv"

    ```bash
    pip install flexible-graphrag-mcp
    # or
    uv pip install flexible-graphrag-mcp
    ```

---

## Step 2 — Start the backend

The backend must be running before MCP clients can connect.

```bash
uv venv venv-3.13 --python 3.13
venv-3.13\Scripts\Activate   # Windows
source venv-3.13/bin/activate  # Linux/macOS
uv pip install flexible-graphrag
flexible-graphrag
```

Backend runs at `http://localhost:8000`.

---

## Step 3 — Connect Claude Desktop

Add to `claude_desktop_config.json`:

=== "uvx (no install)"

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

Restart Claude Desktop after saving the config.

---

## Client Support

| Client | Transport | Notes |
|---|---|---|
| Claude Desktop | stdio | Add to `claude_desktop_config.json` |
| Cursor | stdio | Add to MCP settings |
| MCP Inspector | HTTP (Streamable) | See [Developer MCP Setup](../DEVELOPER/DEVELOPER-MCP.md) |
| Any MCP client | stdio or HTTP | Standard MCP protocol |

See [MCP Tools](MCP-TOOLS.md) for the full list of available tools.
