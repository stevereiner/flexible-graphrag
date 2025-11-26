# Deployment Configurations

**Last Updated**: November 25, 2025

## Table of Contents
1. [Overview](#overview)
2. [Configuration 1: Standalone Everything](#configuration-1-standalone-everything)
3. [Configuration 2: Databases in Docker](#configuration-2-databases-in-docker)
4. [Configuration 3: Full Docker Deployment](#configuration-3-full-docker-deployment)
5. [Configuration Comparison](#configuration-comparison)
6. [Choosing the Right Configuration](#choosing-the-right-configuration)

---

## Overview

Flexible GraphRAG supports three deployment configurations, each optimized for different use cases:

| Configuration | Backend | Databases | Frontend | Best For |
|--------------|---------|-----------|----------|----------|
| **Standalone** | Local | Local | Local | Development, testing |
| **Hybrid** | Local | Docker | Local | Development with isolation |
| **Full Docker** | Docker | Docker | Docker | Production, demos |

---

## Configuration 1: Standalone Everything

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│         CONFIGURATION 1: STANDALONE EVERYTHING          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────┐        │
│  │  Frontend (Local Process)                   │        │
│  │  Port: 3000/4200/5173                       │        │
│  │  • npm run dev                              │        │
│  │  • Hot reload enabled                       │        │
│  │  • Direct filesystem access                 │        │
│  └──────────────┬──────────────────────────────┘        │
│                 │ HTTP (localhost:8000)                 │
│                 ▼                                       │
│  ┌─────────────────────────────────────────────┐        │
│  │  Backend (Local Process)                    │        │
│  │  Port: 8000                                 │        │
│  │  • uv run start.py                          │        │
│  │  • Direct filesystem access                 │        │
│  │  • Easy debugging                           │        │
│  └──────────────┬──────────────────────────────┘        │
│                 │ Database Connections                  │
│                 ▼                                       │
│  ┌─────────────────────────────────────────────┐        │
│  │  Databases (Local Processes)                │        │
│  │  • Neo4j: localhost:7687                    │        │
│  │  • Qdrant: localhost:6333                   │        │
│  │  • Elasticsearch: localhost:9200            │        │
│  │  • All managed manually                     │        │
│  └─────────────────────────────────────────────┘        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Setup Instructions

**1. Install Databases Locally**

```bash
# Neo4j (example with Neo4j Desktop or server)
# Download from: https://neo4j.com/download/

# Qdrant
docker run -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage:z \
  qdrant/qdrant

# Elasticsearch
# Download from: https://www.elastic.co/downloads/elasticsearch

# Or use your preferred installation method
```

**2. Configure Backend**

```bash
cd flexible-graphrag
cp env-sample.txt .env

# Edit .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

VECTOR_DB=qdrant
VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search"}

GRAPH_DB=neo4j
GRAPH_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "your_password"}

SEARCH_DB=elasticsearch
SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}
```

**3. Start Backend**

```bash
cd flexible-graphrag
uv run start.py
# Backend runs on http://localhost:8000
```

**4. Start Frontend**

```bash
# React
cd flexible-graphrag-ui/frontend-react
npm install
npm run dev
# Runs on http://localhost:5173

# Vue
cd flexible-graphrag-ui/frontend-vue
npm install
npm run dev
# Runs on http://localhost:3000

# Angular
cd flexible-graphrag-ui/frontend-angular
npm install
npm start
# Runs on http://localhost:4200
```

### Pros & Cons

**Advantages**:
- ✅ Maximum development flexibility
- ✅ Hot reload for frontend and backend
- ✅ Easy debugging with full access to logs
- ✅ Direct filesystem access (for file upload)
- ✅ No Docker overhead
- ✅ Native IDE integration

**Disadvantages**:
- ❌ Manual database installation required
- ❌ Complex setup for new developers
- ❌ Inconsistent environments between developers
- ❌ Database version management
- ❌ Multiple processes to manage

**Best For**:
- Active development
- Testing new features
- Debugging issues
- Learning the system

---

## Configuration 2: Databases in Docker

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│       CONFIGURATION 2: DATABASES IN DOCKER (HYBRID)     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────┐        │
│  │  Frontend (Local Process)                   │        │
│  │  Port: 3000/4200/5173                       │        │
│  │  • npm run dev                              │        │
│  │  • Hot reload enabled                       │        │
│  │  • Direct filesystem access                 │        │
│  └──────────────┬─────────────────────────────┘         │
│                 │ HTTP (localhost:8000)                 │
│                 ▼                                       │
│  ┌─────────────────────────────────────────────┐        │
│  │  Backend (Local Process)                    │        │
│  │  Port: 8000                                 │        │
│  │  • uv run start.py                          │        │
│  │  • Direct filesystem access                 │        │
│  │  • Easy debugging                           │        │
│  └──────────────┬──────────────────────────────┘        │
│                 │ Docker Network                        │
│                 ▼                                       │
│  ┌────────────────────────────────────────────┐         │
│  │  Docker Containers (Databases)             │         │
│  │  ┌──────────────────────────────────────┐  │         │
│  │  │ Neo4j         (ports 7474, 7687)     │  │         │
│  │  │ Qdrant        (ports 6333, 6334)     │  │         │
│  │  │ Elasticsearch (ports 9200, 9300)     │  │         │
│  │  │ FalkorDB      (ports 6379, 3002)     │  │         │
│  │  │ Kuzu          (ports 7000, 7001)     │  │         │
│  │  │ OpenSearch    (ports 9201, 9600)     │  │         │
│  │  │ Chroma        (port 8001)            │  │         │
│  │  └──────────────────────────────────────┘  │         │
│  │  • Managed by docker-compose               │         │
│  │  • Persistent volumes                      │         │
│  │  • Easy reset/cleanup                      │         │
│  └────────────────────────────────────────────┘         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Setup Instructions

**1. Start Databases in Docker**

```bash
cd flexible-graphrag/docker

# Start all database services
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d

# Or start specific services only
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d \
  neo4j qdrant elasticsearch
```

**2. Configure Backend for Docker Databases**

```bash
cd flexible-graphrag
cp env-sample.txt .env

# Edit .env - use localhost (Docker exposes ports to host)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

VECTOR_DB=qdrant
VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search"}

GRAPH_DB=neo4j
GRAPH_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "flexible-graphrag"}

SEARCH_DB=elasticsearch
SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}
```

**3. Start Backend**

```bash
cd flexible-graphrag
uv run start.py
# Backend runs on http://localhost:8000
```

**4. Start Frontend**

```bash
# Same as Configuration 1
cd flexible-graphrag-ui/frontend-react
npm run dev
```

### Docker Service Management

**Selective Service Startup**:

Edit `docker/docker-compose.yaml` to comment out services you don't need:

```yaml
includes:
  # Graph Databases
  - path: includes/neo4j.yaml        # Keep
  # - path: includes/kuzu.yaml       # Comment out if not using
  # - path: includes/falkordb.yaml   # Comment out if not using
  
  # Vector Databases
  - path: includes/qdrant.yaml       # Keep
  # - path: includes/chroma.yaml     # Comment out if not using
  
  # Search Engines
  - path: includes/elasticsearch.yaml # Keep
  # - path: includes/opensearch.yaml # Comment out if not using
  
  # Content Sources
  # - path: includes/alfresco.yaml   # Comment out if not using
```

**Database Access Points**:

```bash
# Neo4j Browser
http://localhost:7474
# Username: neo4j, Password: flexible-graphrag

# Qdrant Dashboard
http://localhost:6333/dashboard

# Elasticsearch
http://localhost:9200

# Kibana (if enabled)
http://localhost:5601

# OpenSearch Dashboards (if enabled)
http://localhost:5602
```

### Pros & Cons

**Advantages**:
- ✅ Easy database management (docker-compose)
- ✅ Consistent database versions
- ✅ Easy reset/cleanup (docker-compose down -v)
- ✅ Frontend/backend hot reload
- ✅ Direct filesystem access
- ✅ Multiple database options easy to switch
- ✅ Isolated database environment
- ✅ Production-like database setup

**Disadvantages**:
- ❌ Docker required
- ❌ Some memory overhead from containers
- ❌ Backend/frontend still manual startup
- ⚠️ Docker networking considerations

**Best For**:
- **Recommended for most development** 🌟
- Team development
- Testing different database combinations
- Frequent database switching
- Learning with realistic setup

---

## Configuration 3: Full Docker Deployment

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│         CONFIGURATION 3: FULL DOCKER DEPLOYMENT                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Nginx Proxy (Container)                                 │   │
│  │  Port: 8070                                              │   │
│  │  Routes:                                                 │   │
│  │  • /api/*          → backend:8000                        │   │
│  │  • /ui/angular/*   → frontend-angular:80                 │   │
│  │  • /ui/react/*     → frontend-react:80                   │   │
│  │  • /ui/vue/*       → frontend-vue:80                     │   │
│  └──────────────┬───────────────────────────────────────────┘   │
│                 │ Docker Network (flexible-graphrag_default)    │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Frontend Containers                                     │   │
│  │  ┌───────────────────────────────────────────────────┐   │   │
│  │  │ Angular (nginx serving static)   internal:80      │   │   │
│  │  │ React   (nginx serving static)   internal:80      │   │   │
│  │  │ Vue     (nginx serving static)   internal:80      │   │   │
│  │  └───────────────────────────────────────────────────┘   │   │
│  └──────────────┬───────────────────────────────────────────┘   │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Backend Container                                       │   │
│  │  Internal Port: 8000                                     │   │
│  │  • FastAPI application                                   │   │
│  │  • Environment variables from docker.env                 │   │
│  │  • Connects to databases via Docker network              │   │
│  └──────────────┬───────────────────────────────────────────┘   │
│                 │ Docker Network                                │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Database Containers                                     │   │
│  │  ┌───────────────────────────────────────────────────┐   │   │
│  │  │ Neo4j         (host.docker.internal:7687)         │   │   │
│  │  │ Qdrant        (host.docker.internal:6333)         │   │   │
│  │  │ Elasticsearch (host.docker.internal:9200)         │   │   │
│  │  │ FalkorDB      (host.docker.internal:6379)         │   │   │
│  │  │ + Other database options                          │   │   │
│  │  └───────────────────────────────────────────────────┘   │   │
│  │  • Persistent volumes                                    │   │
│  │  • Exposed ports for direct access                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Setup Instructions

**1. Configure Backend Environment**

```bash
cd flexible-graphrag/docker
cp docker.env.sample docker.env

# Edit docker.env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434

VECTOR_DB=qdrant
VECTOR_DB_CONFIG={"host": "host.docker.internal", "port": 6333, "collection_name": "hybrid_search"}

GRAPH_DB=neo4j
GRAPH_DB_CONFIG={"uri": "bolt://host.docker.internal:7687", "username": "neo4j", "password": "flexible-graphrag"}

SEARCH_DB=elasticsearch
SEARCH_DB_CONFIG={"hosts": ["http://host.docker.internal:9200"], "index_name": "hybrid_search"}
```

**Note**: Use `host.docker.internal` for backend to connect to databases from within Docker container.

**2. Enable All Services**

Edit `docker/docker-compose.yaml`:

```yaml
includes:
  # Graph Databases
  - path: includes/neo4j.yaml
  
  # Vector Databases
  - path: includes/qdrant.yaml
  
  # Search Engines
  - path: includes/elasticsearch.yaml
  
  # Application Stack (backend + frontends + nginx)
  - path: includes/app-stack.yaml
  
  # Proxy (nginx routing)
  - path: includes/proxy.yaml
```

**3. Start Everything**

```bash
cd flexible-graphrag/docker

# Start all services
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d

# View logs
docker-compose -f docker-compose.yaml -p flexible-graphrag logs -f

# Check status
docker-compose -f docker-compose.yaml -p flexible-graphrag ps
```

**4. Access Application**

```bash
# Via Nginx Proxy (recommended)
http://localhost:8070/ui/angular/
http://localhost:8070/ui/react/
http://localhost:8070/ui/vue/
http://localhost:8070/api/status

# Direct Container Access (alternative)
http://localhost:4200/          # Angular
http://localhost:5174/          # React
http://localhost:3000/          # Vue
http://localhost:8000/api/      # Backend API

# Database Access
http://localhost:7474/          # Neo4j Browser
http://localhost:6333/dashboard # Qdrant Dashboard
http://localhost:9200/          # Elasticsearch
```

### Environment Variables

**Two-Layer Configuration**:

1. **flexible-graphrag/.env** - Main configuration (for standalone)
2. **docker/docker.env** - Docker-specific overrides

**Key Differences**:

| Setting | Standalone | Docker |
|---------|-----------|---------|
| Database hosts | `localhost` | `host.docker.internal` |
| Ollama URL | `http://localhost:11434` | `http://host.docker.internal:11434` |
| File uploads | Direct filesystem | Shared volumes |
| Frontend API | `http://localhost:8000` | `http://backend:8000` (internal) |

### Volume Mounts

**Persistent Data**:

```yaml
volumes:
  neo4j_data:        # Neo4j database
  qdrant_storage:    # Qdrant vectors
  kuzu_db:           # Kuzu database
  upload_data:       # Uploaded files
  # ... other database volumes
```

**Cleanup**:

```bash
# Stop and remove containers (keeps volumes)
docker-compose -f docker-compose.yaml -p flexible-graphrag down

# Stop and remove containers AND volumes (full cleanup)
docker-compose -f docker-compose.yaml -p flexible-graphrag down -v
```

### Pros & Cons

**Advantages**:
- ✅ Complete production-like environment
- ✅ Single command startup
- ✅ Consistent across all machines
- ✅ Easy demo deployment
- ✅ All services networked properly
- ✅ Nginx proxy for clean URLs
- ✅ No local database installation needed
- ✅ Easy horizontal scaling (future)

**Disadvantages**:
- ❌ No hot reload (need rebuilds)
- ❌ Slower iteration cycle
- ❌ More complex debugging
- ❌ Higher memory usage
- ❌ Docker build time
- ⚠️ **File upload limitation**: Filesystem data source doesn't work well (can't browse host filesystem from container)

**Best For**:
- Production deployments
- Demos and presentations
- Testing full stack
- CI/CD pipelines
- End-to-end testing
- Team onboarding

---

## Configuration Comparison

### Quick Reference Table

| Feature | Standalone | Hybrid (Databases in Docker) | Full Docker |
|---------|-----------|------------------------------|-------------|
| **Setup Complexity** | High (manual DBs) | Medium | Low (one command) |
| **Hot Reload** | ✅ Backend + Frontend | ✅ Backend + Frontend | ❌ Need rebuild |
| **Filesystem Access** | ✅ Full | ✅ Full | ⚠️ Limited |
| **Database Management** | Manual | Docker Compose | Docker Compose |
| **Debugging** | Easy | Easy | Harder |
| **Production-like** | ❌ | ✅ Mostly | ✅ Yes |
| **Team Consistency** | ❌ | ✅ DBs consistent | ✅ Everything consistent |
| **Memory Usage** | Low | Medium | High |
| **Startup Time** | Fast | Medium | Slow (builds) |
| **Best For** | Solo dev, learning | **Team dev (recommended)** | Production, demos |

### Port Mappings by Configuration

**Standalone**:
- Frontend: 3000/4200/5173 (local process)
- Backend: 8000 (local process)
- Databases: 6333, 7687, 9200, etc. (local or Docker)

**Hybrid (Databases in Docker)**:
- Frontend: 3000/4200/5173 (local process)
- Backend: 8000 (local process)
- Databases: 6333, 7687, 9200, etc. (Docker containers, exposed to host)

**Full Docker**:
- All UIs: 8070 (nginx proxy)
  - `/ui/angular/` → Angular
  - `/ui/react/` → React
  - `/ui/vue/` → Vue
- Backend: 8070/api/ (via proxy) or 8000 (direct)
- Databases: 6333, 7687, 9200, etc. (Docker containers, exposed to host)

---

## Choosing the Right Configuration

### Decision Flow

```
┌─────────────────────────────────────────────────────────┐
│          Which Configuration Should I Use?              │
└─────────────────────────────────────────────────────────┘

Are you deploying to production?
  ├─ YES → Use Configuration 3 (Full Docker)
  └─ NO  → Continue...

Do you need filesystem data source?
  ├─ YES → Use Configuration 1 or 2 (NOT Full Docker)
  └─ NO  → Continue...

Are you working in a team?
  ├─ YES → Use Configuration 2 (Databases in Docker) 🌟
  └─ NO  → Continue...

Do you want easy database switching/testing?
  ├─ YES → Use Configuration 2 (Databases in Docker)
  └─ NO  → Use Configuration 1 (Standalone)

Are you learning the system?
  └─ Start with Configuration 2, move to 1 if needed
```

### Recommendations by Use Case

**Active Development** 🔧
- **Best**: Configuration 2 (Hybrid)
- **Why**: Hot reload + consistent databases + easy switching

**Learning the System** 📚
- **Best**: Configuration 2 (Hybrid)
- **Why**: Realistic setup + easy cleanup + no manual DB installation

**Production Deployment** 🚀
- **Best**: Configuration 3 (Full Docker)
- **Why**: Complete isolation + easy scaling + consistent environment

**Debugging Issues** 🐛
- **Best**: Configuration 1 or 2
- **Why**: Full access to logs + easy breakpoint debugging

**Demos & Presentations** 🎬
- **Best**: Configuration 3 (Full Docker)
- **Why**: Single command startup + professional appearance

**Testing Database Combinations** 🧪
- **Best**: Configuration 2 (Hybrid)
- **Why**: Easy docker-compose service toggling + fast iteration

---

## Migration Between Configurations

### From Standalone → Hybrid

```bash
# 1. Stop local databases
# (keep backend/frontend running)

# 2. Start Docker databases
cd flexible-graphrag/docker
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d \
  neo4j qdrant elasticsearch

# 3. Update .env (if needed)
# No changes needed - still using localhost

# 4. Continue development
```

### From Hybrid → Full Docker

```bash
# 1. Commit any code changes

# 2. Configure docker.env
cd flexible-graphrag/docker
cp docker.env.sample docker.env
# Edit docker.env with host.docker.internal

# 3. Enable app-stack and proxy in docker-compose.yaml

# 4. Build and start
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d --build

# 5. Access via nginx proxy
# http://localhost:8070/ui/angular/
```

### From Full Docker → Hybrid

```bash
# 1. Stop frontend/backend containers
docker-compose -f docker-compose.yaml -p flexible-graphrag stop \
  backend frontend-angular frontend-react frontend-vue proxy

# 2. Keep database containers running

# 3. Update .env to use localhost

# 4. Start backend/frontend locally
cd flexible-graphrag
uv run start.py

cd flexible-graphrag-ui/frontend-react
npm run dev
```

---

## Summary

Choose your configuration based on your needs:

- **🏆 Recommended for Most**: Configuration 2 (Hybrid) - Best balance of convenience and functionality
- **🚀 For Production**: Configuration 3 (Full Docker) - Complete isolation and consistency  
- **🔧 For Solo Learning**: Configuration 1 (Standalone) - Maximum flexibility

All configurations support the full feature set of Flexible GraphRAG, including 13 data sources, multiple databases, and hybrid search capabilities. The main trade-offs are between convenience, debugging ease, and production readiness.

