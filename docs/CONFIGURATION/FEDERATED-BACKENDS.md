# Federated Backends

Search, AI query and AI chat on one Flexible GraphRAG backend can also ask other Flexible GraphRAG
backends and fuse their results with its own. For example: a personal backend (a laptop or the
[Desktop App](../GETTING-STARTED/DESKTOP-APP.md)) that keeps its files and indexes local, plus a team
backend, plus a company one. Off by default.

Only the question goes out, along with the asker's own source sign-ins (so the remote can check what
they may read). This backend's documents are never sent.

## Configuration

One remote:

```
REMOTE_FG_URL=https://graphrag.example.com
REMOTE_FG_API_TOKEN=          # the remote's API_TOKEN, if it has one
REMOTE_FG_NAME=team           # shown on its results; default: the URL's host name
REMOTE_FG_TIMEOUT=60          # seconds
```

Several: a JSON list on one line, each `{name, url, api_token?, timeout?}`:

```
REMOTE_FG_BACKENDS=[{"name": "team", "url": "http://team-host:8000"}, {"name": "company", "url": "https://graphrag.example.com", "api_token": "..."}]
```

`REMOTE_FG_URL`, when also set, is one more. Names must differ: they tell results and picked sources apart.
Restart the backend after changing these.

## How it works

- Each remote is asked in parallel through its `POST /api/search` (hybrid), so it runs its own full
  retrieval (vector, search, graph) and its own permission checks.
- Its ranked results are fused with this backend's own (each side scaled, equal weights), then
  duplicates are removed. AI query and chat then answer from the fused results.
- A remote's results and answer sources carry its name: labelled `<name>: ...` and with `"backend": "<name>"`.
- A remote that fails or takes longer than its timeout is skipped, and the other results still come back;
  the API response then has `notices` naming it, and the backend log says why.
- A question that came from another backend is answered from that backend's own indexes only, so backends
  can't loop (A → B → A).

## Sources and sign-ins

- The UIs' source picker lists the remotes' sources too, e.g. "Alfresco · team"
  (`GET /api/sources/available`).
- Picked sources go only to the backend that has them. With picks, only the remotes that have some are
  asked, and this backend answers only when some of its own are picked.
- A question limited to a scope (a folder or document of this backend) is not sent to remotes.
- The sign-ins the remotes need appear in the sign-in list (`GET /api/auth/requirements`).

## Securing a remote

A backend that others reach over a network should have an `API_TOKEN`; give the same value to its callers
as `api_token` / `REMOTE_FG_API_TOKEN`. See [API Token and CORS](API-TOKEN-CORS.md).

## Trying it on one machine

Run two or three backends on different ports, each in its own folder with its own `.env` and stores (e.g.
ports 8000, 8001, 8002). The port is set in the environment, not in `.env` (it is read before `.env` is
loaded):

```
set FLEXIBLE_GRAPHRAG_PORT=8001
flexible-graphrag
```

Different stores per backend: e.g. the [Docker-Free Setup](../GETTING-STARTED/DOCKER-FREE-SETUP.md) in each
folder, or different Docker stores. On the first one:

```
REMOTE_FG_BACKENDS=[{"name": "b", "url": "http://localhost:8001"}, {"name": "c", "url": "http://localhost:8002"}]
```

Ingest different documents into each, then search or ask on the first: the results show which backend each
came from.

The MCP server's `search_documents` and `query_documents` use the same endpoints, so they get fused results
too.
