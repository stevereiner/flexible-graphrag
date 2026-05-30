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
docker/docker.env          ← Docker overrides (service names)
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
cp docker-env-sample.txt docker.env

# Windows Command Prompt
copy docker-env-sample.txt docker.env

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
Docker Compose loads environment files in order:

1️⃣ `flexible-graphrag/.env` loads first (per-store configs with localhost)
```bash
NEO4J_GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", ...}
QDRANT_VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, ...}
ELASTICSEARCH_SEARCH_DB_CONFIG={"url": "http://localhost:9200", ...}
```

2️⃣ `docker/docker.env` loads second (overrides matching per-store vars)
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

**docker/docker.env** (Scenario A — hybrid, app on host):
```bash
NEO4J_GRAPH_DB_CONFIG={"url": "bolt://host.docker.internal:7687", "username": "neo4j", "password": "password"}
QDRANT_VECTOR_DB_CONFIG={"host": "host.docker.internal", "port": 6333, "collection_name": "hybrid_search_vector", "https": false}
ELASTICSEARCH_SEARCH_DB_CONFIG={"url": "http://host.docker.internal:9200", "index_name": "hybrid_search_fulltext"}
```

**docker/docker.env** (Scenario B — full stack in Docker):
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

**docker/docker.env:**
```bash
# No override needed - Neptune Analytics uses AWS endpoints, not localhost
```

## Git Ignore
Both environment files are git-ignored for security:
```
.gitignore includes:
├── docker/docker.env     ← Your Docker overrides
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
**Solution**: Make sure `docker/docker.env` overrides the **per-store** config vars
(`QDRANT_VECTOR_DB_CONFIG`, `NEO4J_GRAPH_DB_CONFIG`, etc.) with Docker service names
(`qdrant`, `neo4j`, ...) when running the full stack in Docker. Overriding only the
legacy generic `VECTOR_DB_CONFIG` is not enough if `.env` sets `QDRANT_VECTOR_DB_CONFIG`.

### Ontology files not found (USE_ONTOLOGY=true)
**Problem**: `../schemas/*.ttl` not found inside the backend container  
**Cause**: Ontology paths in `.env` are relative to the host cwd; Docker WORKDIR is `/app`
and `../schemas` points outside the container.  
**Solution**: `app-stack.yaml` mounts repo `schemas/` at `/app/schemas`. In
`docker/docker.env` (Scenario B) set `ONTOLOGY_DIR=schemas/`.

### Incremental updates can't reach PostgreSQL
**Problem**: `POSTGRES_INCREMENTAL_URL` uses `localhost:5433`  
**Cause**: Inside the backend container, `localhost` is the container itself, not Postgres.  
**Solution** (Scenario B):  
`POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@postgres-pgvector:5432/flexible_graphrag_incremental`  
Use port **5432** (container internal port), not 5433 (host mapping).

### Works in standalone but not Docker
**Problem**: Forgot to create `docker/docker.env`  
**Solution**: Copy `docker/docker-env-sample.txt` to `docker/docker.env`

### Works in Docker but not standalone
**Problem**: Main `.env` has Docker service names instead of localhost  
**Solution**: Use localhost addresses in `flexible-graphrag/.env`

## Related Documentation
- **docker/README.md** - Complete Docker deployment guide
- **docker/docker-env-sample.txt** - Template for Docker overrides
- **flexible-graphrag/env-sample.txt** - Main configuration template
- **docs/ENVIRONMENT-CONFIGURATION.md** - Detailed configuration guide

