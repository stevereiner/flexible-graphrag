# 🔐 Default Usernames and Passwords

This document provides default authentication credentials for all databases, dashboards, and web interfaces in the Flexible GraphRAG Docker Compose setup.

> ⚠️ **Security Warning**: These are development/testing credentials. **Change them for production use!**

## 🗂️ **All Databases & Services by Type**

Complete reference for all databases, dashboards, and web interfaces organized by functionality.

> 💡 **Legend**: 🟢 = Recently Added | 🔵 = Established

## 📊 **Graph Databases**

| Database | Dashboard URL | Username | Password | Port | Status |
|----------|---------------|----------|----------|------|--------|
| **Neo4j** | http://localhost:7474/ | `neo4j` | `password` | 7687 (Bolt) | 🔵 |
| **ArcadeDB** | http://localhost:2480/ | `root` | `playwithdata` | 2480/2424 | 🟢 |
| **MemGraph** | http://localhost:3002/ | *(none)* | *(none)* | 7688 (Bolt) | 🟢 |
| **NebulaGraph** | http://localhost:7001/ | `root` | `nebula` | 9669 | 🟢 |
| **Kuzu** | http://localhost:7000/ | *(none)* | *(none)* | *(embedded)* | 🔵 |
| **FalkorDB** | http://localhost:3001/ | *(none)* | *(none)* | 6379 (Redis) | 🔵 |
| **Neptune** | http://localhost:3007/ | *(AWS IAM)* | *(AWS IAM)* | *(cloud)* | 🟢 |

## 🎯 **Vector Databases**

| Database | Dashboard URL | Username | Password | Port | Status |
|----------|---------------|----------|----------|------|--------|
| **Qdrant** | http://localhost:6333/dashboard | *(none)* | *(none)* | 6333/6334 | 🔵 |
| **Chroma** | http://localhost:8001/docs/ | *(none)* | *(none)* | 8001 | 🟢 |
| **Milvus** | http://localhost:3003/ (Attu) | *(none)* | *(none)* | 19530 | 🟢 |
| **Weaviate** | http://localhost:8081/ | *(none)* | *(none)* | 8081/50051 | 🟢 |
| **LanceDB** | http://localhost:3005/ | *(none)* | *(none)* | *(embedded)* | 🟢 |
| **PostgreSQL+pgvector** | http://localhost:5050/ (pgAdmin) | `admin@flexible-graphrag.com` | `admin` | 5433 | 🟢 |
| **Pinecone** | http://localhost:3004/ (Info) | *(API Key)* | *(API Key)* | *(cloud)* | 🟢 |

## 🔍 **Search Engines**

| Service | Dashboard URL | Username | Password | Port | Status |
|---------|---------------|----------|----------|------|--------|
| **Elasticsearch** | http://localhost:9200/ | `elastic` | `changeme` | 9200/9300 | 🔵 |
| **Kibana** | http://localhost:5601/ | *(none)* | *(none)* | 5601 | 🔵 |
| **OpenSearch** | http://localhost:9201/ | *(none)* | *(none)* | 9201/9301 | 🔵 |
| **OpenSearch Dashboards** | http://localhost:5602/ | *(none)* | *(none)* | 5602 | 🔵 |

## 📁 **Content Management**

| Service | Dashboard URL | Username | Password | Port | Status |
|---------|---------------|----------|----------|------|--------|
| **Alfresco Share** | http://localhost:8080/share/ | `admin` | `admin` | 8080 | 🔵 |
| **Alfresco Repository** | http://localhost:8080/alfresco/ | `admin` | `admin` | 8080 | 🔵 |

## 🛠️ **Supporting Services**

| Service | Dashboard URL | Username | Password | Port | Status |
|---------|---------------|----------|----------|------|--------|
| **MinIO** (Milvus Storage) | http://localhost:9001/ | `minioadmin` | `minioadmin` | 9000/9001 | 🟢 |
| **PostgreSQL** (Alfresco) | localhost:5432 | `alfresco` | `alfresco` | 5432 | 🔵 |


## 🔄 **Dual-Purpose Databases**

Several databases can serve **multiple roles** in your Flexible GraphRAG setup:

| Database | Primary Role | Secondary Role | Configuration |
|----------|--------------|----------------|---------------|
| **Neo4j** | Graph Database | Vector Database | Use same credentials for both roles |
| **Elasticsearch** | Search Engine | Vector Database | Use same credentials for both roles |
| **OpenSearch** | Search Engine | Vector Database | Use same credentials for both roles |


## 🔑 **Detailed Authentication & Features**

### 📊 **Graph Database Details**

#### **Neo4j** 🔵
- **Browser**: http://localhost:7474/
- **Bolt**: bolt://localhost:7687
- **Username**: `neo4j` | **Password**: `password`
- **Features**: APOC, Graph Data Science (GDS), Cypher queries, **Vector indexing**
- **Dual Purpose**: Can also serve as Vector Database
- **Container**: `flexible-graphrag-neo4j`

#### **ArcadeDB** 🟢
- **Studio**: http://localhost:2480/
- **API**: http://localhost:2480/api/v1/
- **Username**: `root` | **Password**: `playwithdata`
- **Features**: Multi-model (Graph + Document + Vector + Search)
- **Container**: `flexible-graphrag-arcadedb`

#### **MemGraph** 🟢
- **Lab**: http://localhost:3002/
- **Bolt**: bolt://localhost:7688
- **Authentication**: None required
- **Features**: Real-time graph analytics, Cypher queries
- **Containers**: `flexible-graphrag-memgraph`, `flexible-graphrag-memgraph-lab`
- **Note**: Requires both MemGraph database and MemGraph Lab services

#### **NebulaGraph** 🟢
- **Studio**: http://localhost:7001/
- **Studio Connection**: `nebula-graphd:9669` (use Docker hostname, not localhost)
- **Username**: `root` | **Password**: `nebula`
- **Features**: Distributed graph processing, nGQL queries
- **Containers**: `nebula-metad`, `nebula-storaged`, `nebula-graphd`, `nebula-studio`
- **Note**: Studio requires Docker internal hostname `nebula-graphd`, not `localhost`

#### **Kuzu** 🔵
- **Explorer**: http://localhost:7000/
- **Database**: `./kuzu_db` (embedded)
- **Authentication**: None required
- **Features**: Analytical graph processing, Cypher queries
- **Container**: `flexible-graphrag-kuzu-explorer`

#### **FalkorDB** 🔵
- **Browser**: http://localhost:3001/
- **Redis**: redis://localhost:6379
- **Authentication**: None required
- **Features**: Redis-based graph operations
- **Container**: `flexible-graphrag-falkordb`

#### **Neptune** 🟢
- **Graph Explorer**: http://localhost:3007/
- **Service**: AWS Neptune (cloud-only)
- **Authentication**: AWS IAM credentials required
- **Features**: Managed graph database service
- **Container**: `flexible-graphrag-graph-explorer` (dashboard only)

### 🎯 **Vector Database Details**

#### **Qdrant** 🔵
- **Dashboard**: http://localhost:6333/dashboard
- **API**: http://localhost:6333/
- **Authentication**: None required
- **Features**: High-performance vector similarity search
- **Container**: `flexible-graphrag-qdrant`

#### **Chroma** 🟢
- **API**: http://localhost:8001/api/v2/heartbeat
- **Version**: http://localhost:8001/api/v2/version
- **Swagger UI**: http://localhost:8001/docs/ (REST API documentation)
- **Authentication**: None required
- **Features**: AI-native embedding database
- **Container**: `flexible-graphrag-chroma`
- **Note**: Uses v2 API - test with `curl http://localhost:8001/api/v2/heartbeat`

**🎯 Chroma Dashboard Status:**
- **Chroma UI** ❌: CORS connection issues ("failed to fetch")
- **ChromaDB Admin** ❌: CORS connection issues ("failed to fetch")  
- **Vector Admin** ❌: CORS connection issues ("failed to fetch")
- **Built-in Swagger UI** ⚠️: http://localhost:8001/docs/ - Works but complex (REST API testing only)

**Result**: No simple web dashboard currently working for Chroma due to CORS restrictions.

#### **Universal Vector Database Dashboard Option**
#### **Vector Admin** (Universal Dashboard) ⚠️
- **Repository**: [Mintplex-Labs/vector-admin](https://github.com/Mintplex-Labs/vector-admin)
- **Status**: ⚠️ **No longer actively maintained** by Mintplex Labs
- **Supports**: Pinecone, Chroma, Qdrant, Weaviate, and more
- **Features**: Universal tool suite for vector database management
- **Docker**: `docker run -p 3010:3001 mintplexlabs/vectoradmin`
- **Connection**: Point to your local databases (e.g., `http://host.docker.internal:8001` for Chroma)
- **API Keys**: Has optional fields for API keys but doesn't require them for local databases
- **Note**: Use with caution - may have compatibility issues with newer database versions

#### **ChromaDB Admin** (Chroma-Specific) ✅
- **Repository**: [flanker/chromadb-admin](https://github.com/flanker/chromadb-admin)
- **Status**: ✅ **Actively maintained** (231 stars, MIT license)
- **Supports**: ChromaDB only
- **Features**: Dedicated admin UI for Chroma embedding database
- **Docker**: `docker run -p 3008:3001 fengzhichao/chromadb-admin`
- **Connection**: Use `http://host.docker.internal:8001` to connect to local Chroma


#### **Milvus** 🟢
- **Attu Dashboard**: http://localhost:3003/
- **API**: localhost:19530
- **MinIO Console**: http://localhost:9001/ (`minioadmin`/`minioadmin`)
- **Authentication**: None required
- **Features**: Cloud-native vector database with Attu management
- **Containers**: `milvus`, `attu`, `etcd`, `minio`

#### **Weaviate** 🟢
- **API**: http://localhost:8081/ (REST), localhost:50051 (gRPC)
- **Web UI**: API only (no web interface)
- **Authentication**: Anonymous access enabled
- **Features**: Vector database with semantic search, high-speed gRPC API
- **Container**: `flexible-graphrag-weaviate`

#### **LanceDB** 🟢
- **Viewer**: http://localhost:3005/ (SvelteKit dashboard)
- **Info Page**: http://localhost:3006/ (backup)
- **Database**: `./lancedb` (embedded)
- **Authentication**: None required
- **Features**: Embedded vector DB with CRUD operations
- **Containers**: `lancedb-viewer`, `lancedb-info`

#### **PostgreSQL + pgvector** 🟢
- **pgAdmin**: http://localhost:5050/
- **Database**: postgresql://localhost:5433/flexible_graphrag
- **pgAdmin Email**: `admin@flexible-graphrag.com`
- **pgAdmin Password**: `admin`
- **DB Username**: `postgres` | **DB Password**: `password`
- **Features**: SQL database with vector similarity search
- **Containers**: `postgres`, `pgadmin`

#### **Pinecone** 🟢
- **Info Dashboard**: http://localhost:3004/
- **Official Console**: https://app.pinecone.io/
- **Service**: Pinecone (cloud-only)
- **Authentication**: API key required
- **Features**: Managed vector database service
- **Container**: `flexible-graphrag-pinecone-info` (info page only)

### 🔍 **Search Engine Details**

#### **Elasticsearch** 🔵
- **API**: http://localhost:9200/
- **Username**: `elastic` | **Password**: `changeme`
- **Security**: Disabled in development mode
- **Features**: Full-text search and analytics, **Vector indexing**
- **Dual Purpose**: Can also serve as Vector Database
- **Container**: `flexible-graphrag-elasticsearch`

#### **Kibana** 🔵
- **Dashboard**: http://localhost:5601/
- **Authentication**: None required (dev mode)
- **Features**: Elasticsearch visualization and management
- **Container**: `flexible-graphrag-kibana`

#### **OpenSearch** 🔵
- **API**: http://localhost:9201/
- **Dashboards**: http://localhost:5602/
- **Authentication**: Security disabled
- **Features**: Open-source search and analytics, **Vector indexing**
- **Dual Purpose**: Can also serve as Vector Database
- **Containers**: `opensearch`, `opensearch-dashboards`

### 📁 **Content Management Details**

#### **Alfresco Community Edition** 🔵
- **Share**: http://localhost:8080/share/
- **Repository**: http://localhost:8080/alfresco/
- **Username**: `admin` | **Password**: `admin`
- **Features**: Enterprise content management
- **Containers**: Multiple (alfresco, share, postgres, solr6, etc.)

## 🚀 **Quick Start Guide**

### Start All Services:
```bash
# Start the complete database stack
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag up -d

# Check status of all services
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag ps

# View logs for specific service
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag logs -f [service-name]
```

### 📊 **Test Graph Databases:**
```bash
# Neo4j Browser
open http://localhost:7474/
# Login: neo4j/password

# ArcadeDB Studio
open http://localhost:2480/
# Login: root/playwithdata

# MemGraph Lab
open http://localhost:3002/

# NebulaGraph Studio
open http://localhost:7001/
# Connection: Host=nebula-graphd, Port=9669, User=root, Password=nebula

# Kuzu Explorer
open http://localhost:7000/

# FalkorDB Browser
open http://localhost:3001/

# Neptune Graph Explorer
open http://localhost:3007/
```

### 🎯 **Test Vector Databases:**
```bash
# Qdrant Dashboard
open http://localhost:6333/dashboard

# Chroma (Swagger UI + API test)
open http://localhost:8001/docs/
curl http://localhost:8001/api/v2/heartbeat

# Milvus Attu Dashboard
open http://localhost:3003/

# Weaviate (API test)
curl http://localhost:8081/v1/meta

# LanceDB Viewer
open http://localhost:3005/

# PostgreSQL+pgvector (pgAdmin)
open http://localhost:5050/
# Login: admin@flexible-graphrag.com/admin

# Pinecone Info Page
open http://localhost:3004/
```

### 🔍 **Test Search Engines:**
```bash
# Elasticsearch + Kibana
curl http://localhost:9200/_cluster/health
open http://localhost:5601/

# OpenSearch + Dashboards
curl http://localhost:9201/_cluster/health
open http://localhost:5602/
```

### 📁 **Test Content Management:**
```bash
# Alfresco Share + Repository
open http://localhost:8080/share/
open http://localhost:8080/alfresco/
# Login: admin/admin
```

## ⚙️ **Configuration Examples by Type**

### 📊 **Graph Database Configurations:**
```bash
# Neo4j (with authentication) - Graph Database
GRAPH_DB=neo4j
GRAPH_DB_CONFIG='{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}'

# Neo4j as Vector Database (dual-purpose)
VECTOR_DB=neo4j
VECTOR_DB_CONFIG='{"url": "bolt://localhost:7687", "username": "neo4j", "password": "password", "index_name": "hybrid_search_vector"}'

# ArcadeDB (multi-model with authentication)
GRAPH_DB=arcadedb
GRAPH_DB_CONFIG='{"host": "localhost", "port": 2480, "username": "root", "password": "playwithdata", "database": "flexible_graphrag"}'

# MemGraph (no authentication)
GRAPH_DB=memgraph
GRAPH_DB_CONFIG='{"url": "bolt://localhost:7688", "username": "", "password": ""}'

# NebulaGraph (distributed with authentication)
GRAPH_DB=nebula
GRAPH_DB_CONFIG='{"space_name": "flexible_graphrag", "address": "localhost", "port": 9669, "username": "root", "password": "nebula"}'

# Kuzu (embedded, no authentication)
GRAPH_DB=kuzu
GRAPH_DB_CONFIG='{"db_path": "./kuzu_db"}'

# FalkorDB (Redis-based, no authentication)
GRAPH_DB=falkordb
GRAPH_DB_CONFIG='{"url": "falkor://localhost:6379"}'
```

### 🎯 **Vector Database Configurations:**
```bash
# Qdrant (no authentication)
VECTOR_DB=qdrant
VECTOR_DB_CONFIG='{"url": "http://localhost:6333", "collection_name": "hybrid_search"}'

# Chroma (no authentication)
VECTOR_DB=chroma
VECTOR_DB_CONFIG='{"host": "localhost", "port": 8001, "collection_name": "hybrid_search"}'

# Milvus (no authentication)
VECTOR_DB=milvus
VECTOR_DB_CONFIG='{"host": "localhost", "port": 19530, "collection_name": "hybrid_search"}'

# Weaviate (no authentication)
VECTOR_DB=weaviate
VECTOR_DB_CONFIG='{"url": "http://localhost:8081", "index_name": "HybridSearch"}'

# LanceDB (embedded, no authentication)
VECTOR_DB=lancedb
VECTOR_DB_CONFIG='{"uri": "./lancedb", "table_name": "hybrid_search"}'

# PostgreSQL+pgvector (with authentication)
VECTOR_DB=pgvector
VECTOR_DB_CONFIG='{"host": "localhost", "port": 5433, "database": "flexible_graphrag", "username": "postgres", "password": "password"}'

# Pinecone (cloud service, API key required)
VECTOR_DB=pinecone
VECTOR_DB_CONFIG='{"api_key": "your_api_key", "environment": "us-east1-gcp", "index_name": "hybrid-search"}'
```

### 🔍 **Search Engine Configurations:**
```bash
# Elasticsearch (with authentication) - Search Engine
SEARCH_DB=elasticsearch
SEARCH_DB_CONFIG='{"url": "http://localhost:9200", "username": "elastic", "password": "changeme", "index_name": "hybrid_search"}'

# Elasticsearch as Vector Database (dual-purpose)
VECTOR_DB=elasticsearch
VECTOR_DB_CONFIG='{"url": "http://localhost:9200", "username": "elastic", "password": "changeme", "index_name": "hybrid_search_vector"}'

# OpenSearch (no authentication in dev mode) - Search Engine
SEARCH_DB=opensearch
SEARCH_DB_CONFIG='{"url": "http://localhost:9201", "index_name": "hybrid_search"}'

# OpenSearch as Vector Database (dual-purpose)
VECTOR_DB=opensearch
VECTOR_DB_CONFIG='{"url": "http://localhost:9201", "index_name": "hybrid_search_vector"}'
```

### 📁 **Content Source Configurations:**
```bash
# Alfresco (with authentication)
ALFRESCO_URL=http://localhost:8080/alfresco
ALFRESCO_USERNAME=admin
ALFRESCO_PASSWORD=admin
ALFRESCO_PATH=/Shared/GraphRAG

# CMIS (Alfresco-based)
CMIS_URL=http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom
CMIS_USERNAME=admin
CMIS_PASSWORD=admin
```

## 🚀 Quick Access Dashboard URLs

| Service | URL | Status |
|---------|-----|--------|
| **Angular UI** | http://localhost:8070/ui/angular/ | 🟢 Ready |
| **React UI** | http://localhost:8070/ui/react/ | 🟢 Ready |
| **Vue UI** | http://localhost:8070/ui/vue/ | 🟢 Ready |
| **Backend API** | http://localhost:8070/api/ | 🟢 Ready |

## 📊 Graph Databases

### Neo4j Graph Database
- **Browser URL**: http://localhost:7474/
- **Bolt URL**: bolt://localhost:7687
- **Username**: `neo4j`
- **Password**: `password`
- **Features**: APOC, Graph Data Science (GDS)
- **Container**: `flexible-graphrag-neo4j`

### ArcadeDB Multi-Model Database
- **Studio URL**: http://localhost:2480/
- **API URL**: http://localhost:2480/api/v1/
- **Username**: `root`
- **Password**: `playwithdata`
- **Features**: Graph, Document, Vector, Search capabilities
- **Container**: `flexible-graphrag-arcadedb`

### MemGraph Real-time Graph Database
- **Lab Dashboard**: http://localhost:3002/
- **Bolt URL**: bolt://localhost:7688
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: Real-time graph processing
- **Container**: `flexible-graphrag-memgraph`

### NebulaGraph Distributed Graph Database
- **Studio URL**: http://localhost:7001/
- **Graph URL**: localhost:9669
- **Username**: `root`
- **Password**: `nebula`
- **Features**: Distributed graph processing
- **Containers**: `nebula-metad`, `nebula-storaged`, `nebula-graphd`, `nebula-studio`

### FalkorDB Production Graph Database
- **Browser URL**: http://localhost:3001/
- **Redis URL**: redis://localhost:6379
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: Redis-based graph database
- **Container**: `flexible-graphrag-falkordb`

### Kuzu Embedded Graph Database
- **Explorer URL**: http://localhost:7000/
- **Database Path**: `./kuzu_db`
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: Embedded analytical graph database
- **Container**: `flexible-graphrag-kuzu-explorer`

### Amazon Neptune (Cloud Service)
- **Graph Explorer**: http://localhost:3007/
- **Service**: AWS Neptune (cloud-only)
- **Authentication**: AWS IAM credentials required
- **Features**: Managed graph database service
- **Container**: `flexible-graphrag-graph-explorer` (dashboard only)

## 🎯 Vector Databases

### Qdrant Vector Database
- **Dashboard URL**: http://localhost:6333/dashboard
- **API URL**: http://localhost:6333/
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: High-performance vector similarity search
- **Container**: `flexible-graphrag-qdrant`

### Chroma Vector Database
- **API URL**: http://localhost:8001/
- **Web UI**: *(API only - no web interface)*
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: AI-native open-source embedding database
- **Container**: `flexible-graphrag-chroma`

### Milvus Vector Database
- **Attu Dashboard**: http://localhost:3003/
- **API URL**: localhost:19530
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: Cloud-native vector database
- **Containers**: `milvus`, `attu`, `etcd`, `minio`

### Weaviate Vector Database
- **API URL**: http://localhost:8081/
- **Web UI**: *(API only - no web interface)*
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: Vector database with semantic search
- **Container**: `flexible-graphrag-weaviate`

### LanceDB Embedded Vector Database
- **Viewer Dashboard**: http://localhost:3005/
- **Info Page**: http://localhost:3006/
- **Database Path**: `./lancedb`
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: Embedded vector database with CRUD operations
- **Containers**: `lancedb-viewer`, `lancedb-info`

### PostgreSQL + pgvector
- **pgAdmin URL**: http://localhost:5050/
- **Database URL**: postgresql://localhost:5433/flexible_graphrag
- **pgAdmin Email**: `admin@flexible-graphrag.com`
- **pgAdmin Password**: `admin`
- **DB Username**: `postgres`
- **DB Password**: `password`
- **Features**: PostgreSQL with vector similarity search
- **Containers**: `postgres`, `pgadmin`

### Pinecone (Cloud Service)
- **Info Dashboard**: http://localhost:3004/
- **Official Console**: https://app.pinecone.io/
- **Service**: Pinecone (cloud-only)
- **Authentication**: API key required
- **Features**: Managed vector database service
- **Container**: `flexible-graphrag-pinecone-info` (info page only)

## 🔍 Search Engines

### Elasticsearch
- **API URL**: http://localhost:9200/
- **Username**: `elastic`
- **Password**: `changeme`
- **Security**: Disabled in development mode
- **Features**: Full-text search and analytics
- **Container**: `flexible-graphrag-elasticsearch`

### Kibana (Elasticsearch Dashboard)
- **Dashboard URL**: http://localhost:5601/
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: Elasticsearch visualization and management
- **Container**: `flexible-graphrag-kibana`

### OpenSearch
- **API URL**: http://localhost:9201/
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Security**: Disabled in development mode
- **Features**: Open-source search and analytics
- **Container**: `flexible-graphrag-opensearch`

### OpenSearch Dashboards
- **Dashboard URL**: http://localhost:5602/
- **Username**: *(no authentication)*
- **Password**: *(no authentication)*
- **Features**: OpenSearch visualization and management
- **Container**: `flexible-graphrag-opensearch-dashboards`

## 📁 Content Management

### Alfresco Community Edition
- **Share URL**: http://localhost:8080/share/
- **Repository URL**: http://localhost:8080/alfresco/
- **Username**: `admin`
- **Password**: `admin`
- **Features**: Enterprise content management
- **Containers**: Multiple (alfresco, share, postgres, solr6, etc.)

## 🛠️ Supporting Services

### MinIO (Milvus Object Storage)
- **Console URL**: http://localhost:9001/
- **API URL**: http://localhost:9000/
- **Username**: `minioadmin`
- **Password**: `minioadmin`
- **Features**: S3-compatible object storage
- **Container**: `flexible-graphrag-milvus-minio`

### PostgreSQL (Alfresco Database)
- **Host**: localhost:5432
- **Database**: `alfresco`
- **Username**: `alfresco`
- **Password**: `alfresco`
- **Features**: Alfresco content repository database
- **Container**: `flexible-graphrag-alfresco-postgres`

## 🔧 Configuration Examples

### Environment Variables
```bash
# Graph Databases
GRAPH_DB=neo4j
GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}

# Vector Databases  
VECTOR_DB=qdrant
VECTOR_DB_CONFIG={"url": "http://localhost:6333", "collection_name": "hybrid_search"}

# Search Engines
SEARCH_DB=elasticsearch
SEARCH_DB_CONFIG={"url": "http://localhost:9200", "index_name": "hybrid_search"}

# Content Sources
ALFRESCO_URL=http://localhost:8080/alfresco
ALFRESCO_USERNAME=admin
ALFRESCO_PASSWORD=admin
```

### Docker Compose Commands
```bash
# Start all services
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag up -d

# Start specific services
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag up -d neo4j qdrant elasticsearch

# Stop all services
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag down

# View logs
docker-compose -f docker/docker-compose.yaml -p flexible-graphrag logs -f [service-name]
```

## 🔒 Security Recommendations

### For Production Deployment:

1. **Change Default Passwords**:
   ```bash
   # Neo4j
   NEO4J_AUTH=neo4j/your_secure_password
   
   # ArcadeDB
   JAVA_OPTS=-Darcadedb.server.rootPassword=your_secure_password
   
   # PostgreSQL
   POSTGRES_PASSWORD=your_secure_password
   ```

2. **Enable Authentication**:
   - Enable Elasticsearch security (`xpack.security.enabled=true`)
   - Configure Weaviate authentication
   - Set up proper IAM for cloud services (Neptune, Pinecone)

3. **Network Security**:
   - Use Docker networks instead of host networking
   - Configure firewalls and security groups
   - Use TLS/SSL for external connections

4. **Access Control**:
   - Implement role-based access control (RBAC)
   - Use API keys for service-to-service communication
   - Regular credential rotation

## 📚 Additional Resources

- [Docker Compose Configuration](../docker/README.md)
- [Environment Configuration](./ENVIRONMENT-CONFIGURATION.md)
- [Vector Database Integration](./VECTOR-DATABASE-INTEGRATION.md)
- [Port Mappings](./PORT-MAPPINGS.md)

---

> 💡 **Tip**: Use `docker-compose ps` to see which services are currently running and their status.
