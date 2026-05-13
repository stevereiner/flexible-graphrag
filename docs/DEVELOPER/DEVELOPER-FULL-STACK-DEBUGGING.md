# Full-Stack Debugging (Standalone Mode)

*Note: This debugging setup is for standalone backend and frontends (Scenario A or C), not for Full Stack in Docker (Scenario B).*

---

## VS Code Launch Configurations

The project includes a `sample-launch.json` file with VS Code debugging configurations for all three frontend options and the backend. Copy this file to `.vscode/launch.json` to use these configurations:

```bash
# From the project root
cp sample-launch.json .vscode/launch.json
# Windows
copy sample-launch.json .vscode\launch.json
```

### Key Configurations

1. **Full Stack with React and Python** — Debug both the React frontend and Python backend simultaneously
2. **Full Stack with Angular and Python** — Debug both the Angular frontend and Python backend simultaneously
3. **Full Stack with Vue and Python** — Debug both the Vue frontend and Python backend simultaneously

*Tip: When ending debugging, you will need to stop the Python backend and the frontend separately.*

Each configuration sets up the appropriate ports, source maps, and debugging tools for a seamless development experience. You may need to adjust the ports and paths in the `launch.json` file to match your specific setup.

---

## Backend Debugging

The Python backend (FastAPI) runs at `http://localhost:8000`. To debug:

1. Open the project in VS Code
2. Select the **"Python: FastAPI"** debug configuration
3. Set breakpoints in `main.py`, `backend.py`, `hybrid_system.py`, etc.
4. Start the debugger (F5)

### Log Level

Control log verbosity via the `LOG_LEVEL` environment variable in `.env`:

```bash
LOG_LEVEL=DEBUG   # verbose — all per-query logs
LOG_LEVEL=INFO    # default — startup messages only
LOG_LEVEL=WARNING # minimal
```

---

## Frontend Debugging

### React (Vite)

- Dev server: `http://localhost:5173` (or `5174` depending on port availability)
- VS Code uses the "Vite" debug configuration with `sourceMapPathOverrides`
- Browser DevTools → Sources tab for breakpoints in TypeScript source

### Angular

- Dev server: `http://localhost:4200`
- VS Code uses the "Chrome: Angular" debug configuration
- Angular CLI automatically generates source maps

### Vue (Vite)

- Dev server: `http://localhost:3000`
- VS Code uses the "Vite" debug configuration

---

## MCP Server Debugging

The MCP server can be run in HTTP mode for debugging with the MCP Inspector:

```bash
# Terminal 1: start the backend
flexible-graphrag

# Terminal 2: start MCP server in HTTP mode
flexible-graphrag-mcp --http --port 3001

# Terminal 3: launch MCP Inspector
npx @modelcontextprotocol/inspector
```

Open the URL printed in the console, set transport to **Streamable HTTP**, URL to `http://localhost:3001/mcp`, then click **Connect**.
