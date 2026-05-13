# Flexible GraphRAG — Integration & E2E Test Framework

Tests in this folder call the live **REST API** only (`http://localhost:8000` by default). They do **not** use the MCP server.

No mocks. No framework-level magic. Just HTTP requests and assertions.

### LLM usage (important)

Most integration runs still **use the LLM**:

- **Document ingestion with knowledge-graph extraction** (the default path) calls the LLM for entity/relation extraction. That happens in **`test_ingest_*`** and follow-on search tests in `test_ingest_search.py`.
- **`slow`** means **long wall-clock** work (bigger docs, polling, filesystem waits, or an **extra** LLM round). It does **not** mean “no LLM.”
- **`ai_qa`** marks tests that call **`POST /api/query`** — a **second** LLM pass (chat Q&A over retrieved context), on top of whatever ingest already spent.

To avoid LLM cost entirely you must run the backend with graph extraction disabled (or a no-LLM pipeline), which these integration tests are not written for.

---

## Architecture

```
tests/integration/
  api_client.py        REST helper (ingest, search, query, sync endpoints)
  env_profiles.py      All .env override profiles (one per backend combination)
  conftest.py          Pytest fixtures (client, watch_dir, sample docs)
  test_ingest_search.py    Tier 2: ingest a doc → search → assert
  test_incremental.py      Tier 3: add/modify/delete file → verify index changes
  run_profile.py       Start backend with a profile + run tests + stop
  run_all_profiles.py  Iterate all profiles sequentially (CI)
  results/             JSON result files from run_all_profiles.py
  envs/                Written .env files (generated, git-ignored)
```

### Pytest marker `integration` (auto-applied)

Only tests whose nodeid lives under **`tests/integration/`** get `@pytest.mark.integration` from `conftest.py`.

Unit tests in **`tests/test_bm25_integration.py`** are *not* live REST integration tests; the old rule matched any path containing the substring `integration` (filename + method names like `test_*_bm25_integration`), which was wrong. **`vector`** is not auto-applied by filename; use `-m vector` only if you add that marker explicitly to tests.

---

## Three-tier overview

| Tier | Where | What |
|------|-------|------|
| 1 — Unit | `tests/` (existing) | Config, factories, adapters — no running services |
| 2 — Integration | `tests/integration/` | Live backend + one store (ingest, search) |
| 2b — AI / Q&A | `tests/integration/test_ingest_search.py` | `POST /api/query` after ingest; checks grounded answers (`@pytest.mark.ai_qa`) |
| 3 — E2E / Incremental | `tests/integration/` | Filesystem add/modify/delete → incremental sync → verify |

---

## Sample docs vs incremental watch (two different paths)

There is **no** `FILESYSTEM_PATH` env var in this project. Filesystem roots are configured as **`SOURCE_PATHS`** in `flexible-graphrag/.env` (see `Settings.source_paths` in `config.py`).

| What | Where it is set | Role |
|------|-----------------|------|
| **`cmispress.txt` / `company-ontology-test.txt`** | Repo folder **`sample-docs/`** (read by pytest, sent via **`POST /api/upload`** + **`/api/ingest`**) | Used by **`test_ingest_search.py`**. These files stay **read-only** in the repo; tests do not edit them. |
| **`SOURCE_PATHS`** | **`flexible-graphrag/.env`** — e.g. `SOURCE_PATHS=["./sample-docs/cmispress.txt"]` | Optional defaults for **UI/MCP** filesystem ingest. **Not** required for the integration ingest tests (they upload from disk independently). |
| **`INTEGRATION_WATCH_DIR`** | Shell or `.env` (loaded by `tests/integration/conftest.py`) — e.g. `C:\newdev3\integ-watch` | **Separate** empty/dedicated folder for **`test_incremental.py`** (create/modify/delete files). **Must not** be `sample-docs/` — tests write and delete files there. |
| **Incremental backend config** | `test_incremental.py` session fixture | When **`INTEGRATION_WATCH_DIR`** is set, tests **`POST /api/ingest`** with **`enable_sync: true`** and that absolute path (same as UI). Requires incremental Postgres initialized. Use **`scripts/cleanup.py`** between runs if you reset state. |

---

## AI / Q&A tests (`/api/query`)

After documents are ingested, integration tests call **`POST /api/query`** (same as the UI “Ask” flow). They assert the JSON `status` is `success` and the `answer` mentions expected keywords from the sample docs (CMIS press release and company ontology text).

- **Fast doc** (`cmispress.txt`): `test_ai_query_about_cmis` — expects CMIS/content-related terms.
- **Full doc** (`company-ontology-test.txt`): parametrized `test_ai_query_answers_with_grounded_terms` — Acme / employees / departments.

These need a **working LLM** for `/api/query` (same as the UI Ask flow). They are marked `@pytest.mark.slow` and `@pytest.mark.ai_qa`.

```powershell
# Only POST /api/query tests (chat Q&A LLM)
pytest tests/integration/ -m "integration and ai_qa" -v

# Skip /api/query tests (still uses LLM during ingest if KG extraction is on)
pytest tests/integration/ -m "integration and not ai_qa" -v
```

---

## Quick start

There are two ways to run integration tests; pick one.

| Flow | When to use |
|------|-------------|
| **`run_profile.py`** | One shot: merges a profile into `.env`, **starts** uvicorn, runs pytest, **stops** the backend. No separate `start.py`. |
| **Manual backend** | You already have the API up (e.g. debugging) or want to run pytest repeatedly without restarting. |

### A — `run_profile.py` (starts and stops the backend for you)

From the **repo root** (`flexible-graphrag/` parent of `tests/`):

```powershell
# Neo4j via LlamaIndex — backend lifecycle is handled inside the script
uv run tests/integration/run_profile.py --profile neo4j-llamaindex

# Fuseki RDF store
uv run tests/integration/run_profile.py --profile fuseki-rdf

# BM25 smoke (minimal external services)
uv run tests/integration/run_profile.py --profile minimal-bm25

# List profiles
uv run tests/integration/run_profile.py --list

# Backend already running on port 8000 — only run pytest (same env as your shell)
uv run tests/integration/run_profile.py --profile neo4j-llamaindex --no-start

# Include filesystem incremental tests (watch dir + profile neo4j-llamaindex-incremental)
# PowerShell: use single quotes around the whole --test-args value
uv run tests/integration/run_profile.py --profile neo4j-llamaindex-incremental --test-args '-m "integration and incremental"'
```

By default, `run_profile.py` runs **`integration and not incremental`** so `test_incremental.py` is skipped (faster; no `INTEGRATION_WATCH_DIR` required). Override with `--test-args` as above when you want those tests.

Do **not** run `uv run start.py` in another terminal at the same time on the **same port** — either use `run_profile.py` alone, or start the backend yourself, not both.

**If health check times out:** Startup logs print to the same console (uvicorn + app). The API does not answer until FastAPI lifespan finishes (loads `HybridSearchSystem`, connects graph/vector DBs). Ensure services for the profile (e.g. Neo4j for `neo4j-llamaindex`) are up and port `API_TEST_PORT` (default 8000) is free. Use `--timeout 300` if cold-start is slow.

**Faster startup:** `build_env_file()` applies `ENABLE_INCREMENTAL_UPDATES=false` for every profile unless the profile overrides it — so `run_profile.py` stays fast even if your base `.env` has `true`. For **incremental** filesystem tests (`INTEGRATION_WATCH_DIR` + `test_incremental.py`), use `--profile neo4j-llamaindex-incremental` (Neo4j + `ENABLE_INCREMENTAL_UPDATES=true`). When incremental is on, lifespan initializes PostgreSQL incremental state and monitoring before `/api/health` responds.

### B — Manual `start.py`, then pytest

Use this when you want the server to stay up between test runs or attach a debugger.

```powershell
# Terminal 1 — repo root, start API (working directory must be flexible-graphrag/)
cd flexible-graphrag
uv run start.py

# Terminal 2 — repo root, hit the running backend
pytest tests/integration/ -m integration -v

# Shorter wall-clock run (skips large-doc ingest, /api/query tests, slow incremental tests)
pytest tests/integration/ -m "integration and not slow" -v
```

### Run all profiles in sequence (CI)

```powershell
# All profiles
uv run tests/integration/run_all_profiles.py

# Only fast, only vector backends
uv run tests/integration/run_all_profiles.py --include "*vector*" --only-fast

# Skip cloud-only stores
uv run tests/integration/run_all_profiles.py --exclude "*spanner*" "*gremlin*"
```

---

## Incremental update tests

The incremental tests write/modify/delete files under **`INTEGRATION_WATCH_DIR`** and
poll search until content appears or disappears. **`sample-docs/` is not used here**
(do not point `INTEGRATION_WATCH_DIR` at the repo sample-docs folder).

### Configure the watch directory

1. Create a dedicated directory (e.g. `C:\newdev3\integ-watch`) on the **same machine as the API** (or a path the API container can read).
2. Set **`INTEGRATION_WATCH_DIR`** to that path (shell or `.env` for pytest).
3. A session fixture writes **`integration_seed_baseline.txt`** into that folder, then calls **`POST /api/ingest`** with  
   `{"data_source": "filesystem", "paths": ["<absolute>"], "enable_sync": true}` so the seed is indexed in the **bulk registration** pass (separate from later per-test files added for incremental add/modify/delete). Teardown deletes the seed; per-test files are removed in each test’s `finally`.  
   **`SOURCE_PATHS`** in `.env` is unrelated.

Optional: **`INTEGRATION_REGISTER_MAX_WAIT`** (default `600`) — seconds to wait for that registration ingest to finish.

```powershell
$env:INTEGRATION_WATCH_DIR = "C:\newdev3\integ-watch"
pytest tests/integration/test_incremental.py -m incremental -s
```

Between full runs you can use **`scripts/cleanup.py`** to reset Postgres / vector / graph / search state as you already do.

If you use only the pytest **`watch_dir`** temp folder without **`INTEGRATION_WATCH_DIR`**, the class is skipped; **prefer a stable directory + env var**.

### Tuning the sync wait time

```powershell
# Default is 30s; increase for slower machines
$env:INTEGRATION_SYNC_WAIT = "60"
pytest tests/integration/test_incremental.py -m incremental -s
```

---

## Available profiles

| Profile | PG Graph | RDF | Vector | Notes |
|---------|----------|-----|--------|-------|
| `neo4j-llamaindex` | Neo4j (LI) | — | default | Standard LlamaIndex pipeline |
| `neo4j-langchain` | Neo4j (LC) | — | default | LangChain graph store |
| `falkordb-llamaindex` | FalkorDB (LI) | — | default | |
| `memgraph-llamaindex` | Memgraph (LI) | — | default | |
| `arcadedb-llamaindex` | ArcadeDB (LI) | — | default | |
| `arangodb-langchain` | ArangoDB (LC) | — | default | LC-only store |
| `apache-age-langchain` | Apache AGE (LC) | — | default | LC-only (Postgres+Cypher) |
| `hugegraph-langchain` | HugeGraph (LC) | — | default | LC-only store |
| `surrealdb-langchain` | SurrealDB (LC) | — | default | LC-only store |
| `gremlin-langchain` | Gremlin (LC) | — | default | TinkerPop local or Cosmos cloud |
| `fuseki-rdf` | — | Fuseki | default | RDF + LangChain QA |
| `oxigraph-rdf` | — | Oxigraph | default | |
| `graphdb-rdf` | — | GraphDB | default | |
| `qdrant-vector` | — | — | Qdrant | vector-only |
| `elasticsearch-vector` | — | — | ES | vector-only |
| `postgres-vector` | — | — | pgvector | vector-only |
| `chroma-vector` | — | — | Chroma | vector-only |
| `elasticsearch-search` | — | — | — | BM25/hybrid search |
| `opensearch-search` | — | — | — | |
| `bm25-llamaindex` | — | — | — | In-memory BM25 (LlamaIndex) |
| `bm25-langchain` | — | — | — | In-memory BM25 (LangChain) |
| `neo4j-fuseki-both` | Neo4j | Fuseki | default | Simultaneous PG + RDF |
| `minimal-bm25` | — | — | — | Fastest smoke test, no external stores |

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_TEST_BASE_URL` | `http://localhost:8000` | Backend URL for all tests |
| `API_TEST_PORT` | `8000` | Port used by run_profile.py |
| `INTEGRATION_WATCH_DIR` | *(unset)* | Dedicated dir for incremental tests — **not** `sample-docs/` |
| `INTEGRATION_SYNC_WAIT` | `30` | Seconds to wait for incremental sync |
| `INTEGRATION_REGISTER_MAX_WAIT` | `600` | Seconds for session `/api/ingest` + `enable_sync` registration to finish |
| `API_TEST_AI_TIMEOUT` | `max(default client timeout, 180)` | HTTP timeout (seconds) for `POST /api/query` (LLM can be slow) |

---

## Docker — start the stores you need

```powershell
# Neo4j
docker compose -p flexible-graphrag --profile neo4j up -d neo4j

# ArangoDB
docker compose -p flexible-graphrag -f docker/includes/arangodb.yaml up -d

# Apache AGE
docker compose -p flexible-graphrag -f docker/includes/apache-age.yaml up -d

# HugeGraph
docker compose -p flexible-graphrag -f docker/includes/hugegraph.yaml up -d

# SurrealDB
docker compose -p flexible-graphrag -f docker/includes/surrealdb.yaml up -d

# Gremlin Server (TinkerPop — Cosmos Gremlin substitute)
docker compose -p flexible-graphrag -f docker/includes/gremlin-server.yaml up -d

# Spanner Emulator
docker compose -p flexible-graphrag -f docker/includes/spanner-emulator.yaml up -d

# Fuseki
docker compose -p flexible-graphrag -f docker/includes/fuseki.yaml up -d
```
