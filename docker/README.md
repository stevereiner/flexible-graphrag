# Flexible GraphRAG Docker Deployment

This directory contains Docker Compose configuration for Flexible GraphRAG with modular database selection.

## 📖 Documentation Overview

This is a quick reference for Docker deployment. For detailed information, see:

- **[../README.md](../README.md)** - Main documentation with deployment scenarios (A, B, C, D, E) and complete setup instructions
- **[DOCKER-ENV-SETUP.md](DOCKER-ENV-SETUP.md)** - Environment configuration guide explaining the two-layer `.env` system
- **[docker.env](docker.env)** - Docker networking overrides with SCENARIO A and SCENARIO B configurations
- **[docker-env-sample.txt](docker-env-sample.txt)** - Template for docker.env with all database options
- **[../docs/PORT-MAPPINGS.md](../docs/PORT-MAPPINGS.md)** - Complete port reference for all services
- **[../docs/DEFAULT-USERNAMES-PASSWORDS.md](../docs/DEFAULT-USERNAMES-PASSWORDS.md)** - Database credentials and dashboard access

## 🏗️ Directory Structure

```
docker/
├── docker-compose.yaml         # Main compose file with modular includes
├── docker.env                  # Docker networking overrides (SCENARIO A/B)
├── docker-env-sample.txt       # Template for docker.env
├── neptune.env                 # Neptune Graph Explorer credentials (optional)
├── neptune-env-sample.txt      # Template for Neptune credentials
├── DOCKER-ENV-SETUP.md         # Environment configuration guide
├── README.md                   # This file
├── config/                     # Configuration files
│   └── kibana.yml              # Kibana configuration
├── lancedb-info/               # LanceDB info dashboard
│   └── index.html              # Static info page
├── nginx/                      # NGINX proxy configuration
│   └── nginx.conf              # Reverse proxy rules
├── pinecone-info/              # Pinecone info dashboard
│   └── index.html              # Static info page
├── postgres-init/              # PostgreSQL initialization scripts
│   └── 01-init-pgvector.sql    # pgvector extension setup
└── includes/                   # Modular service configurations
    ├── commons/                # Common/shared configurations
    │   └── base.yaml           # Base service definitions
    ├── neo4j.yaml              # Neo4j graph database
    ├── kuzu-explorer.yaml      # Kuzu Explorer web interface
    ├── kuzu-api.yaml           # Kuzu API server
    ├── falkordb.yaml           # FalkorDB graph database
    ├── arcadedb.yaml           # ArcadeDB multi-model database
    ├── memgraph.yaml           # MemGraph graph database
    ├── nebula.yaml             # NebulaGraph distributed graph database
    ├── neptune.yaml            # Amazon Neptune Graph Explorer
    ├── qdrant.yaml             # Qdrant vector database
    ├── chroma.yaml             # Chroma vector database
    ├── milvus.yaml             # Milvus vector database
    ├── weaviate.yaml           # Weaviate vector database
    ├── pinecone.yaml           # Pinecone info dashboard
    ├── postgres-pgvector.yaml  # PostgreSQL with pgvector extension
    ├── lancedb.yaml            # LanceDB embedded vector database
    ├── elasticsearch-dev.yaml  # Elasticsearch (security disabled)
    ├── kibana-simple.yaml      # Kibana dashboard
    ├── opensearch.yaml         # OpenSearch search engine + dashboards
    ├── alfresco.yaml           # Alfresco Community (full stack)
    ├── app-stack.yaml          # Flexible GraphRAG backend + UIs
    └── proxy.yaml              # NGINX reverse proxy
```

## 🚀 Quick Start

### 1. Configure Environment Files

**Main configuration** (required):
```bash
# Navigate to backend directory
cd ../flexible-graphrag

# Windows
copy env-sample.txt .env

# macOS/Linux  
cp env-sample.txt .env

# Edit .env with your LLM provider, API keys, and database passwords
# Return to project root
cd ..
```

**Docker overrides** (required for Docker deployment):
```bash
# Navigate to docker directory
cd docker

# Windows
copy docker-env-sample.txt docker.env

# macOS/Linux
cp docker-env-sample.txt docker.env

# See DOCKER-ENV-SETUP.md for details on the two-layer configuration system
```

### 2. Start Services

From the docker directory:

```bash
# Start with project name
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
```

**Common operations:**
```bash
# Stop services
docker-compose -f docker-compose.yaml -p flexible-graphrag down

# Stop and remove volumes (⚠️ deletes all data)
docker-compose -f docker-compose.yaml -p flexible-graphrag down -v

# View logs
docker-compose -f docker-compose.yaml -p flexible-graphrag logs -f

# Check status
docker-compose -f docker-compose.yaml -p flexible-graphrag ps
```

See [../README.md](../README.md) for complete deployment scenario details (A, B, C, D, E).

## 🔧 Selective Database Deployment

The main deployment scenarios (covered in detail in [../README.md](../README.md)):

**SCENARIO A (Default)**: Databases in Docker, app standalone - for development
- Uncomment: neo4j, qdrant, elasticsearch-dev, kibana-simple
- Comment out: app-stack, proxy
- Use `host.docker.internal` in docker.env

**SCENARIO B**: Full stack in Docker - for production
- Uncomment: neo4j, qdrant, elasticsearch-dev, kibana-simple, app-stack, proxy
- Use service names in docker.env

**General principle**: Comment/uncomment services in `docker-compose.yaml` based on your needs. Only include:
- The graph, vector, and search databases you're actually using
- app-stack and proxy only if running backend/UIs in Docker (SCENARIO B)

For alternative databases, uncomment the appropriate include file:
- Graph databases: kuzu-explorer, falkordb, arcadedb, memgraph, nebula, neptune
- Vector databases: chroma, milvus, weaviate, pinecone, postgres-pgvector, lancedb
- Search engines: opensearch (alternative to Elasticsearch)
- Content sources: alfresco

## 🔄 Data Persistence

All database data is stored in named Docker volumes that persist across container restarts:

**Graph databases:**
- `neo4j_data` - Neo4j graph data
- `kuzu_data` - Kuzu graph data
- `falkordb_data` - FalkorDB data
- `arcadedb_data` - ArcadeDB data
- `memgraph_data` - MemGraph data
- `nebula_data` - NebulaGraph data

**Vector databases:**
- `qdrant_data` - Qdrant vector data
- `chroma_data` - Chroma vector data
- `milvus_data` - Milvus vector data
- `weaviate_data` - Weaviate vector data
- `postgres_data` - PostgreSQL pgvector data
- `lancedb_data` - LanceDB data

**Search engines:**
- `elasticsearch_data` - Elasticsearch indices
- `opensearch_data` - OpenSearch indices

**Content management:**
- `alfresco_data` - Alfresco content store
- `alfresco_db_data` - Alfresco PostgreSQL data

## 🔌 External LLM Access

For external Ollama access from Docker containers:

```bash
# Make sure Ollama is running on host
ollama serve

# Configure in docker.env (already configured by default)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Note: Ollama typically runs on the host machine, not in a Docker container.

## 🛠️ Development

### Building Custom Images

```bash
# Backend only
docker-compose -f docker-compose.yaml build flexible-graphrag-backend

# Specific UI
docker-compose -f docker-compose.yaml build flexible-graphrag-ui-react

# All services
docker-compose -f docker-compose.yaml build
```

### Logs and Debugging

```bash
# All services
docker-compose -f docker-compose.yaml -p flexible-graphrag logs -f

# Specific service
docker-compose -f docker-compose.yaml -p flexible-graphrag logs -f flexible-graphrag-backend

# Database logs
docker-compose -f docker-compose.yaml -p flexible-graphrag logs -f neo4j
```

### Health Checks

All services include health checks. Check status:

```bash
docker-compose -f docker-compose.yaml -p flexible-graphrag ps
```

## 🧹 Cleanup

```bash
# Stop services
docker-compose -f docker-compose.yaml -p flexible-graphrag down

# Remove volumes (⚠️ deletes all data)
docker-compose -f docker-compose.yaml -p flexible-graphrag down -v

# Remove images
docker-compose -f docker-compose.yaml -p flexible-graphrag down --rmi all
```

## 🚨 Troubleshooting

### Common Issues

1. **Port conflicts**: Check [../docs/PORT-MAPPINGS.md](../docs/PORT-MAPPINGS.md) and modify port mappings in individual YAML files if needed
2. **Memory issues**: Increase Docker memory limits (Settings → Resources) or reduce the number of services
3. **Permission errors**: Check volume mount permissions, especially on Linux
4. **Network connectivity**: Services use the default network `flexible-graphrag_default`
5. **Connection refused**: Ensure `docker/docker.env` exists and uses correct addresses for your scenario

### Resource Requirements

**Minimum requirements (basic setup - Neo4j + Qdrant + Elasticsearch):**
- RAM: 8GB
- Disk: 20GB free space
- Docker: 20.10+, Compose V2

**Recommended for full stack (multiple databases + backend + UIs):**
- RAM: 16GB+
- Disk: 50GB+ free space
- CPU: 4+ cores

**Note**: Running multiple vector or graph databases simultaneously increases resource requirements proportionally.

## 📚 MCP Server Integration

The Docker setup works seamlessly with the MCP server for Claude Desktop integration, other MCP clients, etc.

1. Install MCP server: `uvx flexible-graphrag-mcp`
2. Configure to point to:
   - **SCENARIO A (standalone)**: `http://localhost:8000`
   - **SCENARIO B (Docker)**: `http://localhost:8070/api/`
3. All database services are accessible through the unified API

See [../flexible-graphrag-mcp/README.md](../flexible-graphrag-mcp/README.md) for complete MCP server documentation.

## 📖 Additional Resources

- **Main README**: [../README.md](../README.md) - Complete deployment scenarios and setup
- **Environment Setup**: [DOCKER-ENV-SETUP.md](DOCKER-ENV-SETUP.md) - Two-layer configuration system
- **Port Mappings**: [../docs/PORT-MAPPINGS.md](../docs/PORT-MAPPINGS.md) - All service ports
- **Credentials**: [../docs/DEFAULT-USERNAMES-PASSWORDS.md](../docs/DEFAULT-USERNAMES-PASSWORDS.md) - Default passwords
- **Deployment Options**: [../docs/DEPLOYMENT-CONFIGURATIONS.md](../docs/DEPLOYMENT-CONFIGURATIONS.md) - Detailed scenarios
- **Architecture**: [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) - System architecture overview

This modular approach allows you to run exactly what you need while maintaining easy access to all Flexible GraphRAG features.
