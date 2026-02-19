# PostgreSQL Setup Guide

This guide covers PostgreSQL usage in Flexible GraphRAG, including the pgvector vector store option, incremental updates state management, and pgAdmin configuration.

## Table of Contents

1. [Overview](#overview)
2. [Two PostgreSQL Instances](#two-postgresql-instances)
3. [Automatic Setup on First Start](#automatic-setup-on-first-start)
4. [pgVector Vector Store](#pgvector-vector-store)
5. [Incremental Updates State Management](#incremental-updates-state-management)
6. [pgAdmin Access](#pgadmin-access)
7. [Manual Database Operations](#manual-database-operations)
8. [Troubleshooting](#troubleshooting)

---

## Overview

Flexible GraphRAG can use PostgreSQL for two distinct purposes:

1. **Vector Storage** - Using the pgvector extension for embedding similarity search (optional, alternative to Qdrant/Milvus/etc)
2. **Incremental Updates** - State management for tracking document changes and synchronization status (optional feature)

Both can run in the same PostgreSQL container but use **separate databases** to keep concerns separated.

---

## Two PostgreSQL Instances

Flexible GraphRAG Docker setup includes **two separate PostgreSQL containers**:

### 1. Flexible GraphRAG PostgreSQL (Port 5433)

**Container**: `flexible-graphrag-postgres`  
**Image**: `pgvector/pgvector:pg16`  
**Port**: `5433` (to avoid conflict with Alfresco)

**Purpose**: Dual-purpose database for Flexible GraphRAG
- Vector storage with pgvector extension
- Incremental updates state management

**Databases**:
- `flexible_graphrag` - Vector embeddings (with pgvector extension)
- `flexible_graphrag_incremental` - State management tables

### 2. Alfresco PostgreSQL (Port 5432)

**Container**: `flexible-graphrag-postgres-1`  
**Image**: `postgres:16.5`  
**Port**: `5432` (standard PostgreSQL port)

**Purpose**: Alfresco content management system only
- Dedicated database for Alfresco repository
- Separate instance to avoid conflicts

**Why Separate?**
- Different PostgreSQL images (pgvector vs standard)
- Different port assignments
- Isolated resource allocation
- Independent lifecycle management

---

## Automatic Setup on First Start

When you run `docker compose up` for the first time, the PostgreSQL container automatically initializes:

### Initialization Process

The container executes scripts from `/docker-entrypoint-initdb.d/` in **alphabetical order**:

```
docker/postgres-init/
├── 01-init-pgvector.sql           ← Creates pgvector extension
├── 02-init-incremental.sql        ← Creates incremental database
└── 03-init-incremental-schema.sh  ← Creates state management tables
```

### What Gets Created Automatically

#### 1. **Vector Database** (`flexible_graphrag`)
```sql
-- Created by: 01-init-pgvector.sql
CREATE EXTENSION IF NOT EXISTS vector;
-- Result: pgvector extension enabled for similarity search
```

#### 2. **Incremental Database** (`flexible_graphrag_incremental`)
```sql
-- Created by: 02-init-incremental.sql
CREATE DATABASE flexible_graphrag_incremental;
-- Result: Separate database for state tracking
```

#### 3. **State Management Tables**
```sql
-- Created by: 03-init-incremental-schema.sh
CREATE TABLE datasource_config (
    config_id TEXT PRIMARY KEY,
    source_type TEXT,
    connection_params JSONB,
    ...
);

CREATE TABLE document_state (
    doc_id TEXT PRIMARY KEY,
    content_hash TEXT,
    modified_timestamp TIMESTAMPTZ,  -- Proper timestamp type
    vector_synced_at TIMESTAMPTZ,
    search_synced_at TIMESTAMPTZ,
    graph_synced_at TIMESTAMPTZ,
    ...
);
```

### One-Time Initialization

- Scripts **only run when data directory is empty** (first startup)
- Subsequent restarts skip initialization (data already exists)
- To re-initialize: Remove the `flexible-graphrag_postgres_data` volume

```bash
# Reset and reinitialize
docker compose -p flexible-graphrag down postgres-pgvector
docker volume rm flexible-graphrag_postgres_data
docker compose -p flexible-graphrag up -d postgres-pgvector
```

---

## pgVector Vector Store

### Overview

The pgvector extension enables PostgreSQL to store and search vector embeddings efficiently, making it a viable alternative to specialized vector databases.

### When to Use PostgreSQL as Vector Store

**✅ Good for:**
- Small to medium datasets (< 10 million vectors)
- When you want fewer moving parts (one database for everything)
- Development and testing environments
- When you already have PostgreSQL expertise

**❌ Consider alternatives for:**
- Very large datasets (> 10 million vectors)
- High-performance production workloads requiring sub-millisecond latency
- Distributed vector search across multiple nodes

### Configuration

#### 1. Enable PostgreSQL Vector Store

Edit `flexible-graphrag/.env`:

```bash
# Set vector database to postgres
VECTOR_DB=postgres

# Configure connection
VECTOR_DB_CONFIG={"host": "localhost", "port": 5433, "database": "flexible_graphrag", "username": "postgres", "password": "password", "table_name": "hybrid_search_vectors"}
```

#### 2. Connection Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `host` | `localhost` | Or Docker service name `postgres-pgvector` from within Docker |
| `port` | `5433` | Flexible GraphRAG PostgreSQL (not 5432 which is Alfresco) |
| `database` | `flexible_graphrag` | Database with pgvector extension |
| `username` | `postgres` | Default admin user |
| `password` | `password` | Default password (change in production!) |
| `table_name` | `hybrid_search_vectors` | Table for vector embeddings |

#### 3. Verify pgVector Extension

```bash
# Connect to database
docker exec -it flexible-graphrag-postgres psql -U postgres -d flexible_graphrag

# Check extension
flexible_graphrag=# \dx
                                      List of installed extensions
  Name   | Version |   Schema   |                        Description
---------+---------+------------+-----------------------------------------------------------
 plpgsql | 1.0     | pg_catalog | PL/pgSQL procedural language
 vector  | 0.8.0   | public     | vector data type and ivfflat and hnsw access methods
```

### How It Works

1. **Document Ingestion**: Embeddings are generated and stored in the `hybrid_search_vectors` table
2. **Vector Search**: Uses pgvector's indexing (HNSW or IVFFlat) for nearest neighbor search
3. **Hybrid Search**: Combined with Elasticsearch/OpenSearch for BM25 keyword search

### Performance Tuning

For production workloads, consider:

```sql
-- Create HNSW index for faster similarity search
CREATE INDEX ON hybrid_search_vectors 
USING hnsw (embedding vector_cosine_ops);

-- Tune PostgreSQL memory settings
shared_buffers = 4GB
effective_cache_size = 12GB
```

---

## Incremental Updates State Management

### Overview

The incremental updates system tracks document changes and synchronization status across multiple data sources, enabling automatic re-ingestion when content changes.

### Architecture

```
PostgreSQL (flexible_graphrag_incremental database)
├── datasource_config     → Configuration for each monitored source
└── document_state        → Per-document processing state
```

### Configuration

#### 1. Enable Incremental Updates

Edit `flexible-graphrag/.env`:

```bash
# Enable incremental updates
ENABLE_INCREMENTAL_UPDATES=true

# PostgreSQL connection for state tracking
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental
```

#### 2. Connection String Format

```
postgresql://[username]:[password]@[host]:[port]/[database]
```

- **username**: `postgres` (default)
- **password**: `password` (default, change in production!)
- **host**: `localhost` (or `postgres-pgvector` from Docker)
- **port**: `5433` (Flexible GraphRAG PostgreSQL)
- **database**: `flexible_graphrag_incremental` (state management)

### Database Schema

#### `datasource_config` Table

Stores configuration for each monitored data source:

```sql
CREATE TABLE datasource_config (
    config_id TEXT PRIMARY KEY,              -- Unique identifier
    project_id TEXT NOT NULL,                -- Project grouping
    source_type TEXT NOT NULL,               -- filesystem, s3, alfresco, etc.
    source_name TEXT NOT NULL,               -- Human-readable name
    connection_params JSONB NOT NULL,        -- Source-specific config
    refresh_interval_seconds INTEGER,        -- Polling interval
    enable_change_stream BOOLEAN,            -- Real-time monitoring
    skip_graph BOOLEAN,                      -- Skip graph extraction
    is_active BOOLEAN,                       -- Enable/disable source
    sync_status TEXT,                        -- idle, syncing, error
    last_sync_ordinal BIGINT,                -- Last processed timestamp
    last_sync_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### `document_state` Table

Tracks processing state for each document:

```sql
CREATE TABLE document_state (
    doc_id TEXT PRIMARY KEY,                 -- config_id:source_path
    config_id TEXT NOT NULL,                 -- Links to datasource_config
    source_path TEXT NOT NULL,               -- File path or identifier
    source_id TEXT,                          -- Source-specific ID
    ordinal BIGINT NOT NULL,                 -- Microsecond timestamp
    content_hash TEXT NOT NULL,              -- SHA-256 for change detection
    modified_timestamp TIMESTAMPTZ,          -- Source modification time
    vector_synced_at TIMESTAMPTZ,            -- Vector index sync time
    search_synced_at TIMESTAMPTZ,            -- Search index sync time
    graph_synced_at TIMESTAMPTZ,             -- Graph index sync time
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Change Detection Flow

1. **Detector** monitors source (filesystem, S3, Alfresco, etc.)
2. **Change detected** (new/modified/deleted file)
3. **State check** - Query `document_state` for existing hash
4. **Content comparison** - Compare hash to detect actual changes
5. **Sync tracking** - Update `vector_synced_at`, `search_synced_at`, `graph_synced_at`
6. **Re-ingestion** - Only process changed documents

### Supported Data Sources

| Source | Type | Real-time Support |
|--------|------|-------------------|
| Filesystem | Local files | ✅ Watchdog (inotify) |
| Amazon S3 | Cloud storage | ⏱️ Polling |
| Alfresco | CMS | ✅ ActiveMQ events |
| Google Drive | Cloud storage | ✅ Push notifications |
| OneDrive | Cloud storage | ✅ Microsoft Graph webhooks |
| SharePoint | CMS | ✅ Microsoft Graph webhooks |
| Azure Blob | Cloud storage | ⏱️ Polling |
| Google Cloud Storage | Cloud storage | ⏱️ Polling |
| Box | Cloud storage | ⏱️ Polling |

### Timestamp Migration

The schema uses proper `TIMESTAMPTZ` (timestamp with timezone) for all timestamp columns. If upgrading from an older version with `TEXT` timestamps:

```bash
# Apply migration
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental < flexible-graphrag/incremental_updates/migration_002_modified_timestamp_timestamptz.sql
```

---

## pgAdmin Access

### Automatic Server Registration

The PostgreSQL server is **automatically registered** in pgAdmin when you first start the containers. No manual "Add Server" configuration needed!

### Accessing pgAdmin

1. **Open pgAdmin**: http://localhost:5050

2. **Login** (one-time per session):
   - **Email**: `admin@flexible-graphrag.com`
   - **Password**: `admin`

3. **Connect to Server**:
   - Server appears automatically in left sidebar: "Flexible GraphRAG PostgreSQL"
   - Click on it
   - **Enter password**: `password`
   - ✅ **Check "Save password"** - Won't ask again

4. **Navigate databases**:
   ```
   Flexible GraphRAG PostgreSQL
   ├── Databases
   │   ├── flexible_graphrag              ← Vector store
   │   │   └── hybrid_search_vectors      ← Embeddings table
   │   └── flexible_graphrag_incremental  ← State management
   │       ├── datasource_config
   │       └── document_state
   ```

### How Auto-Registration Works

Configuration files are mounted into the pgAdmin container:

```yaml
# docker/includes/postgres-pgvector.yaml
volumes:
  - ../pgadmin-config/servers.json:/pgadmin4/servers.json  # Pre-register server
  - ../pgadmin-config/pgpass:/pgadmin4/pgpass              # Store credentials
```

**`servers.json`** defines the server:
```json
{
  "Servers": {
    "1": {
      "Name": "Flexible GraphRAG PostgreSQL",
      "Host": "postgres-pgvector",
      "Port": 5432,
      "MaintenanceDB": "postgres",
      "Username": "postgres"
    }
  }
}
```

### Credentials

**pgAdmin Login**:
- Email: `admin@flexible-graphrag.com`
- Password: `admin`

**PostgreSQL Connection**:
- Username: `postgres`
- Password: `password`

**⚠️ Production**: Change these default credentials!

### Persistent Configuration

All pgAdmin settings are stored in the `flexible-graphrag_pgadmin_data` Docker volume:
- Saved passwords
- Query history
- Preferences
- Custom configurations

To reset pgAdmin:
```bash
docker volume rm flexible-graphrag_pgadmin_data
docker compose -p flexible-graphrag up -d pgadmin
```

---

## Manual Database Operations

### Connect via Command Line

```bash
# Connect to vector database
docker exec -it flexible-graphrag-postgres psql -U postgres -d flexible_graphraf

# Connect to incremental database
docker exec -it flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental

# List all databases
docker exec flexible-graphrag-postgres psql -U postgres -c "\l"

# List tables in incremental database
docker exec flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental -c "\dt"
```

### View Table Structure

```bash
# Document state table schema
docker exec flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental -c "\d document_state"

# Vector table schema
docker exec flexible-graphrag-postgres psql -U postgres -d flexible_graphraf -c "\d hybrid_search_vectors"
```

### Query Examples

#### Check Incremental Updates Status

```sql
-- Count documents per data source
SELECT config_id, COUNT(*) as doc_count
FROM document_state
GROUP BY config_id;

-- Recently synced documents
SELECT doc_id, source_path, vector_synced_at, search_synced_at, graph_synced_at
FROM document_state
WHERE vector_synced_at > NOW() - INTERVAL '1 hour'
ORDER BY vector_synced_at DESC;

-- Documents pending sync
SELECT doc_id, source_path
FROM document_state
WHERE vector_synced_at IS NULL OR search_synced_at IS NULL OR graph_synced_at IS NULL;
```

#### Check Vector Store

```sql
-- Count embeddings
SELECT COUNT(*) FROM hybrid_search_vectors;

-- Sample embeddings
SELECT id, LEFT(text, 50) as text_preview, 
       array_length(embedding, 1) as embedding_dim
FROM hybrid_search_vectors
LIMIT 5;
```

### Backup and Restore

#### Backup

```bash
# Backup vector database
docker exec flexible-graphrag-postgres pg_dump -U postgres flexible_graphraf > backup_vectors.sql

# Backup incremental database
docker exec flexible-graphrag-postgres pg_dump -U postgres flexible_graphrag_incremental > backup_incremental.sql

# Backup both
docker exec flexible-graphrag-postgres pg_dumpall -U postgres > backup_all.sql
```

#### Restore

```bash
# Restore vector database
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphraf < backup_vectors.sql

# Restore incremental database
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental < backup_incremental.sql
```

---

## Troubleshooting

### PostgreSQL Container Won't Start

**Check logs**:
```bash
docker logs flexible-graphrag-postgres
```

**Common issues**:
- Port 5433 already in use → Check with `netstat -an | findstr :5433`
- Volume permissions → On Linux, check ownership of mounted directories
- Memory limits → Increase Docker memory allocation

### Databases Not Created Automatically

**Symptoms**: Empty database, tables don't exist

**Cause**: Volume already exists from previous installation

**Solution**:
```bash
# Remove volume and restart
docker compose -p flexible-graphrag down postgres-pgvector
docker volume rm flexible-graphrag_postgres_data
docker compose -p flexible-graphrag up -d postgres-pgvector
```

### pgVector Extension Missing

**Check**:
```bash
docker exec flexible-graphrag-postgres psql -U postgres -d flexible_graphraf -c "\dx"
```

**If missing**:
```sql
-- Manually install
CREATE EXTENSION IF NOT EXISTS vector;
```

### pgAdmin Can't Connect

**Symptoms**: "Could not connect to server"

**Solutions**:

1. **Check PostgreSQL is running**:
   ```bash
   docker ps | grep postgres
   ```

2. **Verify network connectivity**:
   ```bash
   docker exec flexible-graphrag-pgadmin ping postgres-pgvector
   ```

3. **Check credentials**:
   - Username: `postgres`
   - Password: `password`
   - Database: `postgres` (maintenance DB)

4. **Reset pgAdmin volume**:
   ```bash
   docker volume rm flexible-graphrag_pgadmin_data
   docker compose -p flexible-graphrag up -d pgadmin
   ```

### Incremental Updates Not Working

**Check connection**:
```bash
# From .env file
echo $POSTGRES_INCREMENTAL_URL

# Test connection
docker exec flexible-graphrag-postgres psql postgresql://postgres:password@localhost:5432/flexible_graphrag_incremental -c "SELECT COUNT(*) FROM datasource_config;"
```

**Verify schema**:
```bash
docker exec flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental -c "\dt"
```

Expected output:
```
               List of relations
 Schema |       Name        | Type  |  Owner   
--------+-------------------+-------+----------
 public | datasource_config | table | postgres
 public | document_state    | table | postgres
```

### Wrong Database/Port

**Remember**:
- **Flexible GraphRAG PostgreSQL**: Port `5433`, Image `pgvector/pgvector:pg16`
  - Container: `flexible-graphrag-postgres`
  - Vector DB: `flexible_graphraf`
  - Incremental DB: `flexible_graphrag_incremental`

- **Alfresco PostgreSQL**: Port `5432`, Image `postgres:16.5`
  - Container: `flexible-graphrag-postgres-1`
  - Alfresco DB: `alfresco`

Don't mix them up! They are completely separate instances.

---

## Security Considerations

### Default Credentials

**⚠️ Change these in production!**

```bash
# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password

# pgAdmin
PGADMIN_DEFAULT_EMAIL=admin@flexible-graphrag.com
PGADMIN_DEFAULT_PASSWORD=admin
```

### Production Recommendations

1. **Use strong passwords**
2. **Enable SSL/TLS** for PostgreSQL connections
3. **Restrict network access** (firewall rules)
4. **Regular backups** (automated)
5. **Monitor access logs**
6. **Update regularly** (security patches)

---

## Additional Resources

- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **pgvector GitHub**: https://github.com/pgvector/pgvector
- **pgAdmin Documentation**: https://www.pgadmin.org/docs/
- **Flexible GraphRAG Docs**: `docs/` directory

For questions or issues, check the main README or open a GitHub issue.
