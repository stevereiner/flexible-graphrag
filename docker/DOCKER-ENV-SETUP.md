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
# Windows
copy flexible-graphrag\env-sample.txt flexible-graphrag\.env

# macOS/Linux  
cp flexible-graphrag/env-sample.txt flexible-graphrag/.env
```

**Edit** `flexible-graphrag/.env` with:
- ✅ LLM provider and API keys
- ✅ Database passwords
- ✅ All localhost addresses (for standalone use)

### 2. Docker Overrides (Required for Docker)
```bash
# Windows
copy docker\docker-env-sample.txt docker\docker.env

# macOS/Linux
cp docker/docker-env-sample.txt docker/docker.env
```

**No editing needed!** This file already has the correct Docker service names.

### 3. Neptune Graph Explorer (Optional)
Only needed if using Neptune and want separate AWS credentials for Graph Explorer:

```bash
# Windows
copy docker\neptune-env-sample.txt docker\neptune.env

# macOS/Linux
cp docker/neptune-env-sample.txt docker/neptune.env
```

## How It Works

### Loading Order
Docker Compose loads environment files in order:

1️⃣ `flexible-graphrag/.env` loads first
```bash
GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", ...}
VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, ...}
SEARCH_DB_CONFIG={"url": "http://localhost:9200", ...}
```

2️⃣ `docker/docker.env` loads second (overrides)
```bash
GRAPH_DB_CONFIG={"url": "bolt://host.docker.internal:7687", ...}      # ← Overrides!
VECTOR_DB_CONFIG={"host": "host.docker.internal", "port": 6333, ...}  # ← Overrides!
SEARCH_DB_CONFIG={"url": "http://host.docker.internal:9200", ...}  # ← Overrides!
```

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
GRAPH_DB=neo4j
GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}

VECTOR_DB=qdrant
VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search_vector", "https": false}

SEARCH_DB=elasticsearch
SEARCH_DB_CONFIG={"url": "http://localhost:9200", "index_name": "hybrid_search_fulltext"}
```

**docker/docker.env:**
```bash
GRAPH_DB_CONFIG={"url": "bolt://host.docker.internal:7687", "username": "neo4j", "password": "password"}
VECTOR_DB_CONFIG={"host": "host.docker.internal", "port": 6333, "collection_name": "hybrid_search_vector", "https": false}
SEARCH_DB_CONFIG={"url": "http://host.docker.internal:9200", "index_name": "hybrid_search_fulltext"}
```

### Neptune Analytics (AWS)

**flexible-graphrag/.env:**
```bash
GRAPH_DB=neptune_analytics
GRAPH_DB_CONFIG={"graph_identifier": "g-abc123", "region": "us-east-1", "access_key": "...", "secret_key": "..."}
```

**docker/docker.env:**
```bash
# No override needed - Neptune Analytics uses AWS endpoints, not localhost!
# Just keep the same configuration
GRAPH_DB_CONFIG={"graph_identifier": "g-abc123", "region": "us-east-1", "access_key": "...", "secret_key": "..."}
```

## Service Name Reference

| Database | Standalone (localhost) | Docker Override (host.docker.internal) |
|----------|----------------------|-----------------------------------------|
| **Graph Databases** |
| Neo4j | `bolt://localhost:7687` | `bolt://host.docker.internal:7687` |
| FalkorDB | `falkor://localhost:6379` | `falkor://host.docker.internal:6379` |
| ArcadeDB | `"host": "localhost"` | `"host": "host.docker.internal"` |
| MemGraph | `bolt://localhost:7688` | `bolt://host.docker.internal:7688` |
| NebulaGraph | `"address": "localhost"` | `"address": "host.docker.internal"` |
| Kuzu | `"db_path": "./kuzu_db/..."` | No change (file-based) |
| Neptune/Neptune Analytics | AWS endpoint | No change (configured in main .env) |
| Pinecone | Pinecone cloud | No change (configured in main .env) |
| **Vector Databases** |
| Qdrant | `"host": "localhost"` | `"host": "host.docker.internal"` |
| Elasticsearch | `http://localhost:9200` | `http://host.docker.internal:9200` |
| OpenSearch | `http://localhost:9201` | `http://host.docker.internal:9201` |
| Chroma | `"host": "localhost"` | `"host": "host.docker.internal"` |
| Milvus | `"host": "localhost"` | `"host": "host.docker.internal"` |
| Weaviate | `http://localhost:8080` | `http://host.docker.internal:8080` |
| PostgreSQL | `"host": "localhost"` | `"host": "host.docker.internal"` |
| LanceDB | `"uri": "./lancedb"` | No change (file-based) |
| Pinecone | Pinecone cloud | No change (configured in main .env) |
| **Search Databases** |
| Elasticsearch | `http://localhost:9200` | `http://host.docker.internal:9200` |
| OpenSearch | `http://localhost:9201` | `http://host.docker.internal:9201` |
| **LLM Providers** |
| Ollama | `http://localhost:11434` | `http://host.docker.internal:11434` |
| **Content Sources** |
| Alfresco | `http://localhost:8080` | `http://host.docker.internal:8080` |

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
**Solution**: Make sure `docker/docker.env` exists and uses service names (not localhost)

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

