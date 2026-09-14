# Docker Environment Configuration Quick Guide

## Overview
Flexible GraphRAG uses a **two-layer environment configuration** system for Docker deployments that keeps your configuration DRY (Don't Repeat Yourself).

## The Problem This Solves
- **Standalone mode** needs `localhost` addresses (e.g., `bolt://localhost:7687`)
- **Docker mode** needs service names (e.g., `bolt://neo4j:7687`)
- Without this system, you'd need **two separate `.env` files** to maintain

## The Solution
**Single source of truth** with smart overrides!

```
flexible-graphrag/.env     ← Main config (localhost addresses)
       +
docker/.env          ← Docker overrides (service names)
       =
Perfect Docker deployment! 🎉
```

## Setup Steps

### 1. Main Configuration (Required)
```bash
# Navigate to backend directory
cd flexible-graphrag

# Linux/macOS  
cp env-sample.txt .env

# Windows Command Prompt
copy env-sample.txt .env

# Edit .env with:
# - LLM provider and API keys
# - Database passwords
# - All localhost addresses (for standalone use)

# Return to project root
cd ..
```

### 2. Docker Overrides (Required for Docker)
```bash
# Navigate to docker directory
cd docker

# Linux/macOS
cp docker-env-sample.txt .env

# Windows Command Prompt
copy docker-env-sample.txt .env

# No editing needed! This file already has the correct Docker service names.
```

### 3. Neptune Graph Explorer (Optional)
Only needed if using Neptune and want separate AWS credentials for Graph Explorer:

```bash
# If not already in docker directory:
# cd docker

# Linux/macOS
cp neptune-env-sample.txt neptune.env

# Windows Command Prompt
copy neptune-env-sample.txt neptune.env
```

## How It Works

### Loading Order

**Scope first**: these two files are `env_file:` entries on exactly **two services** —
`flexible-graphrag-backend` (`includes/app-stack.yaml`) and `flexible-graphrag-langflow`
(`includes/langflow.yaml`). Nothing else in `docker/includes/` reads them: not the
databases, not the Alfresco stack, not even the Angular/React/Vue UI containers (those take
a couple of literal `environment:` values). So `docker/.env` overrides addresses **for the
app stack**, not for the rest of the Compose stack. (Graph Explorer is the one other
`env_file` user, and it reads `neptune.env`.)

For those two services, Compose loads the files in order:

1️⃣ `flexible-graphrag/.env` loads first (per-store configs with localhost)
```bash
NEO4J_GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", ...}
QDRANT_VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, ...}
ELASTICSEARCH_SEARCH_DB_CONFIG={"url": "http://localhost:9200", ...}
```

2️⃣ `docker/.env` loads second (overrides matching per-store vars)
```bash
NEO4J_GRAPH_DB_CONFIG={"url": "bolt://host.docker.internal:7687", ...}      # hybrid
QDRANT_VECTOR_DB_CONFIG={"host": "host.docker.internal", "port": 6333, ...}  # hybrid
ELASTICSEARCH_SEARCH_DB_CONFIG={"url": "http://host.docker.internal:9200", ...}
```

Use the same `{TYPE}_GRAPH_DB_CONFIG`, `{TYPE}_VECTOR_DB_CONFIG`, and
`{TYPE}_SEARCH_DB_CONFIG` names as in `.env` — only the host/URL changes.
Generic unprefixed `GRAPH_DB_CONFIG` / `VECTOR_DB_CONFIG` / `SEARCH_DB_CONFIG`
are legacy; per-store vars take precedence.

### What Gets Overridden?
**Only network addresses!** Everything else stays the same:
- ✅ LLM provider → No change
- ✅ API keys → No change
- ✅ Passwords → No change
- ✅ Database selection → No change
- 🔄 Network addresses → Overridden for Docker

### Variables Compose substitutes into the YAML

`env_file:` on a **service** sets variables inside that container. Separately, Compose
resolves `${VAR}` placeholders **while reading the YAML** — the image tag on the backend,
vLLM's model, which search engine Alfresco indexes into, and so on. That substitution does
**not** use service `env_file:` entries.

It uses `docker/.env`, because Compose auto-loads any file literally named `.env` sitting
next to `docker-compose.yaml`. **That is the reason the Docker override file is named
`.env` and not `docker.env`** — the name is what makes the includes work with no extra
syntax:

```yaml
include:
   - includes/neo4j.yaml           # every include is a plain one-liner
   - includes/alfresco.yaml        # ${ALFRESCO_SEARCH_HOST} resolves from docker/.env
   #- includes/vllm.yaml           # ${VLLM_MODEL} likewise
```

Set `ALFRESCO_SEARCH_HOST=opensearch` in `docker/.env` and Compose picks it up.

**Precedence**, highest wins:

1. shell environment — `ALFRESCO_SEARCH_HOST=opensearch docker compose up -d`
2. `docker/.env`
3. the default written into the include — e.g. `${ALFRESCO_SEARCH_HOST:-alfresco-elasticsearch}`

⚠️ **`flexible-graphrag/.env` is not consulted for `${...}` substitution** — only
`docker/.env` and the shell. For a compose-only setting that is exactly right, and
`docker/.env` is where it belongs. But a few variables are read by *both* Compose and the
backend app (see the second table below); if the backend runs on the host while the
container runs in Docker (Scenario A), those need an entry in **both** files so the two
agree. In Scenario B the backend reads `docker/.env` as well, so one entry covers it.

Edits take effect on `docker compose up --force-recreate`, not on a live `.env` edit — a
running container keeps the values it started with.

`app-stack.yaml` and `langflow.yaml` list both files as a service-level `env_file:`
(`../../flexible-graphrag/.env` then `../.env`). That is the other mechanism, and it is what
actually puts the app settings inside those containers — Compose's `${...}` substitution
never does. `alfresco.yaml` and `vllm.yaml` have no `env_file:` at all and need none: their
placeholders come from `docker/.env`, and their containers are configured by explicit
`environment:` blocks.

**Compose-only** — set these in `docker/.env`; the backend app never reads them:

| Variable | Default | Used by |
|----------|---------|---------|
| `ALFRESCO_SEARCH_HOST` | `alfresco-elasticsearch` | Which engine Alfresco 26.2 indexes into — one of `alfresco-elasticsearch` (dedicated, 9202 — the default), `alfresco-opensearch` (dedicated, 9203), `elasticsearch` (shared, 9200) or `opensearch` (shared, 9201). The two dedicated values need the matching `includes/alfresco-elasticsearch.yaml` / `alfresco-opensearch.yaml`; the shared values need neither |
| `ALFRESCO_SEARCH_PORT` | `9200` | Container port of that engine (9200 for both Elasticsearch and OpenSearch images) |
| `FLEXIBLE_GRAPHRAG_VERSION` | `latest` | Image tag for the backend / UI / Langflow images |
| `HF_TOKEN` | *(empty)* | vLLM container — only needed for gated HuggingFace models |
| `VLLM_MAX_MODEL_LEN`, `VLLM_GPU_UTIL`, `VLLM_DTYPE`, `VLLM_MAX_NUM_SEQS` | see `includes/vllm.yaml` | vLLM container startup arguments |
| `LANCEDB_TABLE_NAME` | `hybrid_search` | LanceDB viewer container |
| `SURREALDB_USER`, `SURREALDB_PASSWORD` | `root`, `root` | SurrealDB container credentials |

**Read by Compose *and* by the backend app** (`config.py`) — put them in `docker/.env` for the
container, and in `flexible-graphrag/.env` as well whenever the backend runs on the host
(Scenario A), so the two agree. In Scenario B the backend reads `docker/.env` too, so one
entry is enough:

| Variable | Default | Why both |
|----------|---------|----------|
| `VLLM_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Compose passes it as the container's `--model`; the app sends requests for that same model name |
| `LANCEDB_URI` | `./lancedb` | Container mounts/serves it; the app opens the same database |
| `LADYBUG_DB_FILE` | `database.lbug` | Explorer container opens it; the app writes it |
| `ARANGODB_PASSWORD` | `testpass` | Container's root password; the app authenticates with it |

Any new `${...}` you add to an include file works automatically — no annotation needed, since
`docker/.env` is loaded for the whole project.

## Example Configurations

### Neo4j + Qdrant + Elasticsearch

**flexible-graphrag/.env:**
```bash
PG_GRAPH_DB=neo4j
NEO4J_GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}

VECTOR_DB=qdrant
QDRANT_VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search_vector", "https": false}

SEARCH_DB=elasticsearch
ELASTICSEARCH_SEARCH_DB_CONFIG={"url": "http://localhost:9200", "index_name": "hybrid_search_fulltext"}
```

**docker/.env** (Scenario A — hybrid, app on host):
```bash
NEO4J_GRAPH_DB_CONFIG={"url": "bolt://host.docker.internal:7687", "username": "neo4j", "password": "password"}
QDRANT_VECTOR_DB_CONFIG={"host": "host.docker.internal", "port": 6333, "collection_name": "hybrid_search_vector", "https": false}
ELASTICSEARCH_SEARCH_DB_CONFIG={"url": "http://host.docker.internal:9200", "index_name": "hybrid_search_fulltext"}
```

**docker/.env** (Scenario B — full stack in Docker):
```bash
NEO4J_GRAPH_DB_CONFIG={"url": "bolt://neo4j:7687", "username": "neo4j", "password": "password"}
QDRANT_VECTOR_DB_CONFIG={"host": "qdrant", "port": 6333, "collection_name": "hybrid_search_vector", "https": false}
ELASTICSEARCH_SEARCH_DB_CONFIG={"url": "http://elasticsearch:9200", "index_name": "hybrid_search_fulltext"}
```

### Neptune Analytics (AWS)

**flexible-graphrag/.env:**
```bash
PG_GRAPH_DB=neptune_analytics
NEPTUNE_ANALYTICS_GRAPH_DB_CONFIG={"graph_identifier": "g-abc123", "region": "us-east-1", "access_key": "...", "secret_key": "..."}
```

**docker/.env:**
```bash
# No override needed - Neptune Analytics uses AWS endpoints, not localhost
```

## Git Ignore
These environment files are git-ignored for security:
```
.gitignore includes:
├── docker/.env     ← Your Docker overrides (app containers)
├── docker/.env           ← Compose ${...} variables, if you create one
└── docker/neptune.env    ← Your Neptune credentials
```

## Benefits

✅ **Single source of truth**: One `.env` file for all settings  
✅ **Works both modes**: Standalone and Docker from same config  
✅ **Easy switching**: Change modes without editing main config  
✅ **Secure**: Credentials stay in git-ignored files  
✅ **Simple**: Just copy template files, no complex setup  
✅ **Flexible**: Override only what you need for Docker  

## Troubleshooting

### "Connection refused" errors in Docker
**Problem**: Backend can't connect to databases  
**Solution**: Make sure `docker/.env` overrides the **per-store** config vars
(`QDRANT_VECTOR_DB_CONFIG`, `NEO4J_GRAPH_DB_CONFIG`, etc.) with Docker service names
(`qdrant`, `neo4j`, ...) when running the full stack in Docker. Overriding only the
legacy generic `VECTOR_DB_CONFIG` is not enough if `.env` sets `QDRANT_VECTOR_DB_CONFIG`.

### Ontology files not found (USE_ONTOLOGY=true)
**Problem**: `../schemas/*.ttl` not found inside the backend container  
**Cause**: Ontology paths in `.env` are relative to the host cwd; Docker WORKDIR is `/app`
and `../schemas` points outside the container.  
**Solution**: `app-stack.yaml` mounts repo `schemas/` at `/app/schemas`. In
`docker/.env` (Scenario B) set `ONTOLOGY_DIR=schemas/`.

### Incremental updates can't reach PostgreSQL
**Problem**: `POSTGRES_INCREMENTAL_URL` uses `localhost:5433`  
**Cause**: Inside the backend container, `localhost` is the container itself, not Postgres.  
**Solution** (Scenario B):  
`POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@postgres-pgvector:5432/flexible_graphrag_incremental`  
Use port **5432** (container internal port), not 5433 (host mapping).

### Works in standalone but not Docker
**Problem**: Forgot to create `docker/.env`  
**Solution**: Copy `docker/docker-env-sample.txt` to `docker/.env`

### Works in Docker but not standalone
**Problem**: Main `.env` has Docker service names instead of localhost  
**Solution**: Use localhost addresses in `flexible-graphrag/.env`

## Related Documentation
- **docker/README.md** - Complete Docker deployment guide
- **docker/docker-env-sample.txt** - Template for Docker overrides
- **flexible-graphrag/env-sample.txt** - Main configuration template
- **docs/ENVIRONMENT-CONFIGURATION.md** - Detailed configuration guide

