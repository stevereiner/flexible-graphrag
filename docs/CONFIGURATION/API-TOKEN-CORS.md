# API Token and CORS

Both are optional and off by default. The usual setup (the web UIs, the MCP server, Docker on your own
machine) needs neither.

## API token

```
API_TOKEN=<a long random value>
```

With it set, every `/api` request must send the token, as an `X-API-Token: <token>` header or as
`Authorization: Bearer <token>`. Otherwise the backend answers 401. Keep the value secret.

Not checked: `/api/health` (liveness checks), CORS preflight requests, and the sign-in pages the browser
opens itself (popup, vendor callback, handoff link), which can't carry a header.

Each caller then sends the same value:

| Caller | Setting |
| --- | --- |
| React UI, Vue UI | `VITE_API_TOKEN` in the UI's `.env` (built into the UI, so rebuild or restart its dev server) |
| MCP server | `FLEXIBLE_GRAPHRAG_API_TOKEN` in its environment / MCP client config |
| Another backend (federation) | `REMOTE_FG_API_TOKEN`, or `api_token` in `REMOTE_FG_BACKENDS` (see [Federated Backends](FEDERATED-BACKENDS.md)) |
| Desktop app, with a backend it didn't start | `api_token` in `desktop.json`, or `FLEXIBLE_GRAPHRAG_API_TOKEN` (see [Desktop App](../GETTING-STARTED/DESKTOP-APP.md#which-backend)) |
| Your own scripts | the `X-API-Token` header |

The Angular UI and KG Spaces don't send a token outside the desktop app, so don't set `API_TOKEN` on a
backend they use.

`VITE_API_TOKEN` is built into the UI's JavaScript, so anyone who can load the UI can read it. It keeps
other web pages and casual callers out, not someone who can open the UI itself.

**The desktop app** gives the backend it starts its own per-install token and sets `CORS_ORIGINS` to the
app. Don't set `API_TOKEN` in that backend's `.env` for the app.

### Ingest folders at runtime

With `API_TOKEN` set, `PUT /api/ingest-allowed-paths` can add folders that filesystem ingests may read,
without a restart (the desktop app uses this when you add a folder). Without a token it is refused: any
caller could otherwise allow `/` and read every file the backend can read. Otherwise list the folders in
`INGEST_ALLOWED_PATHS` (`uploads/` and `SOURCE_PATHS` are always allowed):

```
INGEST_ALLOWED_PATHS=["../sample-docs", "C:/Users/me/Documents/graphrag"]
```

`GET /api/ingest-allowed-paths` returns the allowed folders, as set and resolved.

## CORS origins

```
CORS_ORIGINS=http://localhost:5174,http://localhost:3000,http://localhost:4200
```

The origins a browser may call the API from: comma-separated or a JSON list. Unset, any origin may. Set it
when the backend is reachable from other machines, or to keep other web pages open in your browser from
calling a backend on `localhost`.

Common origins:

| UI | Origin |
| --- | --- |
| React dev server (also the desktop app in development) | `http://localhost:5174` |
| Vue dev server (also the desktop app in development) | `http://localhost:3000` |
| Angular dev server (also the desktop app in development) | `http://localhost:4200` |
| Desktop app (built), Windows | `http://tauri.localhost` |
| Desktop app (built), macOS / Linux | `tauri://localhost` |

Use the host and port you actually open the UI at (e.g. a Docker or reverse-proxy URL). The UI dev servers
proxy `/api` to `VITE_API_PROXY_TARGET` (default `http://localhost:8000`), so through the proxy the browser
doesn't make a cross-origin call. The MCP server and other non-browser callers aren't affected by CORS.

See also [SECURITY.md](https://github.com/stevereiner/flexible-graphrag/blob/main/SECURITY.md).
