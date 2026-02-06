# Incremental Updates - Setup Guide

Complete installation and configuration guide for the Incremental Update System.

## Overview

The Incremental Update System automatically monitors data sources and keeps your vector, search, and graph indexes synchronized. This guide covers complete setup from scratch.

## Prerequisites

- **Flexible GraphRAG** backend installed and running
- **PostgreSQL** 12+ (can reuse existing postgres-pgvector service)
- **Docker** (recommended) or local PostgreSQL installation
- **Python** 3.12+ with backend dependencies installed

## Step 1: PostgreSQL Setup

### Option A: Docker (Recommended)

The Flexible GraphRAG `postgres-pgvector` service works perfectly for incremental updates.

**1. Verify Service Configuration**

Check `docker/docker-compose.yaml` includes:

```yaml
includes:
  - path: includes/postgres-pgvector.yaml
```

**2. Start Services**

```bash
cd docker
docker-compose -p flexible-graphrag up -d
```

**3. Access pgAdmin**

- URL: http://localhost:5050
- Email: admin@flexible-graphrag.com
- Password: admin

**4. Create Database**

In pgAdmin:
1. Right-click "Servers" → Create → Server
2. Name: "FlexibleGraphRAG"
3. Connection tab:
   - Host: postgres-pgvector (or localhost from outside Docker)
   - Port: 5433
   - Username: postgres
   - Password: password
4. Save
5. Right-click "Databases" → Create → Database
6. Database name: `flexible_graphrag_incremental`
7. Save

**5. Run Schema**

1. Open database `flexible_graphrag_incremental`
2. Tools → Query Tool
3. Open file: `incremental_updates/schema.sql`
4. Execute (F5)

### Option B: Local PostgreSQL

**1. Create Database**

```bash
createdb flexible_graphrag_incremental
```

**2. Run Schema**

```bash
cd flexible-graphrag/incremental_updates
psql -d flexible_graphrag_incremental -f schema.sql
```

## Step 2: Environment Configuration

Add to your `.env` file in the `flexible-graphrag` backend directory:

```bash
# === Incremental Updates Configuration ===

# Enable incremental updates
ENABLE_INCREMENTAL_UPDATES=true

# PostgreSQL connection for state management
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental

# Alternative: Reuse main GraphRAG database (not recommended)
# POSTGRES_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_main
```

**Connection String Format:**
```
postgresql://[user]:[password]@[host]:[port]/[database]
```

**Common Configurations:**

Docker Compose (from inside backend container):
```bash
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@postgres-pgvector:5432/flexible_graphrag_incremental
```

Docker Compose (from host machine):
```bash
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental
```

Local PostgreSQL:
```bash
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5432/flexible_graphrag_incremental
```

## Step 3: Start Backend

The incremental update system starts automatically when the backend starts (if `ENABLE_INCREMENTAL_UPDATES=true`).

```bash
cd flexible-graphrag
python main.py
```

**Expected Log Output:**

```
INFO: Backend initialized
INFO: ============================================================
INFO:   Flexible GraphRAG Incremental Update System
INFO: ============================================================
INFO: Starting orchestrator...
INFO: No data sources configured for auto-sync
INFO: Auto-sync is ready - add datasources via UI or API when needed
INFO: Monitoring for configuration changes...
```

## Step 4: Configure Data Sources

### Via Web UI (Recommended)

**For New Ingest with Sync Enabled:**

1. Open http://localhost:5000
2. Navigate to **Processing** tab
3. Select data source type (Filesystem, S3, Google Drive, etc.)
4. Fill in source-specific fields
5. **Important**: Check ✅ **"Enable automatic sync"**
6. Set sync interval (default: 300 seconds)
7. Optional: Check **"Skip Graph"** for faster syncs
8. Click **Process** or **Add Source**

**Result**: 
- Documents are ingested
- `datasource_config` entry created
- `document_state` records created for each document
- Monitoring starts automatically

### Via REST API

See [API-REFERENCE.md](./API-REFERENCE.md) for complete API documentation.

**Example - Enable sync during ingest:**

```http
POST /api/ingest
Content-Type: application/json

{
  "data_source": "filesystem",
  "paths": ["/data/documents"],
  "enable_sync": true,
  "skip_graph": true,
  "sync_config": {
    "source_name": "My Local Documents",
    "refresh_interval_seconds": 300,
    "enable_change_stream": true
  }
}
```

## Step 5: Verify Setup

### Check Backend Logs

After configuring a data source, you should see:

```
INFO: New datasource detected: My Local Documents
INFO: Creating detector for My Local Documents (type: filesystem)...
INFO: Detector created successfully
INFO: Injected backend, state_manager, config_id, and skip_graph into detector
INFO: Started 1 auto-sync updater(s)
```

### Check Database

**View datasource configurations:**

```sql
SELECT 
    config_id,
    source_name,
    source_type,
    is_active,
    sync_status,
    refresh_interval_seconds,
    enable_change_stream,
    last_sync_completed_at
FROM datasource_config;
```

**View tracked documents:**

```sql
SELECT 
    doc_id,
    source_path,
    ordinal,
    created_at
FROM document_state
ORDER BY created_at DESC
LIMIT 10;
```

**Expected Results:**
- One row in `datasource_config` with `is_active = true`
- One row per ingested document in `document_state`

### Test Change Detection

**For Filesystem:**
1. Add a new `.txt` file to monitored directory
2. Within seconds, check logs for: `EVENT: CREATE detected for filename.txt`
3. Verify document appears in vector store and search index

**For Cloud Sources (S3, Google Drive, etc.):**
1. Upload a file to monitored location
2. Wait for sync interval (or check event stream logs)
3. Verify document is processed and indexed

## Data Source Specific Setup

### Filesystem

**Requirements:**
- Local directory with read access
- `watchdog` package installed (included in requirements)

**Configuration:**
```json
{
  "data_source": "filesystem",
  "paths": ["/path/to/documents"],
  "enable_sync": true,
  "sync_config": {
    "source_name": "Local Documents",
    "enable_change_stream": true  // Real-time OS events
  }
}
```

**Features:**
- ✅ Real-time change detection (watchdog)
- ✅ Recursive directory monitoring
- ✅ Automatic file type detection

### Amazon S3

**Requirements:**
- AWS credentials with S3 read access
- Bucket name and optional prefix
- (Optional) SQS queue for event notifications

**Configuration:**
```json
{
  "data_source": "s3",
  "s3_config": {
    "bucket_name": "my-bucket",
    "prefix": "documents/",
    "sqs_queue_url": "https://sqs.region.amazonaws.com/account/queue"
  },
  "enable_sync": true,
  "sync_config": {
    "source_name": "S3 Documents",
    "enable_change_stream": true  // Requires SQS
  }
}
```

**Setup SQS Event Notifications:**
See [S3-SETUP.md](./S3-SETUP.md) for detailed AWS configuration.

### Google Drive

**Requirements:**
- Google Cloud project with Drive API enabled
- Service account with Drive access
- Folder ID to monitor

**Configuration:**
```json
{
  "data_source": "google_drive",
  "google_drive_config": {
    "credentials": "{...service account JSON...}",
    "folder_id": "1ABC...XYZ"
  },
  "enable_sync": true,
  "sync_config": {
    "source_name": "Google Drive Docs",
    "refresh_interval_seconds": 60  // Polling only (no event stream)
  }
}
```

### Alfresco

**Requirements:**
- Alfresco server with ActiveMQ enabled
- Alfresco credentials
- Site/folder path to monitor

**Configuration:**
```json
{
  "data_source": "alfresco",
  "alfresco_config": {
    "base_url": "http://alfresco:8080",
    "username": "admin",
    "password": "admin",
    "site_id": "my-site",
    "folder_path": "/documentLibrary/folder"
  },
  "enable_sync": true,
  "sync_config": {
    "source_name": "Alfresco Documents",
    "enable_change_stream": true  // Requires ActiveMQ
  }
}
```

## Configuration Options

### Refresh Interval

How often to check for changes (polling-based detection):

- **Default**: 300 seconds (5 minutes)
- **Minimum**: 10 seconds (careful with API rate limits)
- **Maximum**: 3600 seconds (1 hour)

```sql
UPDATE datasource_config 
SET refresh_interval_seconds = 60
WHERE source_name = 'My Documents';
```

### Enable Change Stream

Use event-driven detection instead of polling:

- **Filesystem**: Real-time OS events (watchdog) - instant detection
- **S3**: SQS notifications - 1-5 second latency
- **Alfresco**: ActiveMQ events - near real-time

```sql
UPDATE datasource_config 
SET enable_change_stream = true
WHERE source_name = 'My Documents';
```

**Restart backend** after changing this setting.

### Skip Graph

Skip knowledge graph extraction for faster syncs:

```sql
UPDATE datasource_config 
SET skip_graph = true
WHERE source_name = 'My Documents';
```

**Performance Impact:**
- With graph: ~10-60 seconds per document
- Without graph: ~2-10 seconds per document

## Monitoring and Maintenance

### Check Sync Status

```sql
SELECT 
    source_name,
    sync_status,
    last_sync_completed_at,
    last_sync_error,
    last_sync_ordinal
FROM datasource_config
WHERE is_active = true;
```

**Sync Status Values:**
- `idle`: Waiting for next interval or event
- `syncing`: Currently processing changes
- `error`: Last sync failed (check `last_sync_error`)

### Trigger Manual Sync

Force an immediate sync via REST API:

```http
POST /api/incremental/sync/{config_id}
```

Returns immediately, sync runs in background.

### View Diagnostic Information

Use the queries in `diagnostic_queries.sql`:

```sql
-- Recent document changes
SELECT 
    doc_id,
    source_path,
    ordinal,
    content_hash,
    created_at,
    updated_at
FROM document_state
ORDER BY updated_at DESC
LIMIT 20;

-- Documents by data source
SELECT 
    dc.source_name,
    COUNT(ds.doc_id) as document_count,
    MAX(ds.updated_at) as last_update
FROM datasource_config dc
LEFT JOIN document_state ds ON dc.config_id = ds.config_id
GROUP BY dc.source_name;
```

## Troubleshooting

### Backend Not Starting

**Error**: `asyncpg.exceptions.InvalidCatalogNameError: database "flexible_graphrag_incremental" does not exist`

**Solution**: Create the database first (Step 1)

### No Changes Detected

**Symptoms**: Files added but not processed

**Check:**
1. Is datasource active? `SELECT is_active FROM datasource_config;`
2. Backend logs show "Started N auto-sync updater(s)"?
3. For event streams: Is `enable_change_stream = true`?
4. For S3: Is SQS queue configured and accessible?

**Solutions:**
- Ensure `is_active = true` in database
- Restart backend to pick up configuration changes
- Check data source credentials and permissions
- Verify event stream setup (SQS, ActiveMQ, etc.)

### Duplicate Processing

**Symptoms**: Same document indexed multiple times

**Check:**
1. `source_id` populated in `document_state`?
2. Multiple datasources monitoring same location?
3. Detector initialization logs show "Populated known_file_ids"?

**Solutions:**
- Re-ingest with `enable_sync=true` to populate `source_id`
- Remove duplicate datasource configurations
- Restart backend to reset detector state

### Performance Issues

**Symptoms**: Slow change detection or processing

**Optimization:**
1. Enable event streams instead of polling
2. Increase `refresh_interval_seconds` if polling
3. Enable `skip_graph = true` to skip graph extraction
4. Check vector/search/graph services are responding quickly

## Security Best Practices

1. **Credentials**
   - Store in environment variables, not in datasource configs
   - Use IAM roles for cloud services (S3, GCS, Azure)
   - Never commit credentials to version control

2. **Database Access**
   - Restrict PostgreSQL access to backend only
   - Use strong passwords
   - Enable SSL for production: `?sslmode=require`

3. **Data Source Permissions**
   - Use read-only access when possible
   - Limit scope to specific folders/buckets
   - Regular credential rotation

4. **Network Security**
   - Run PostgreSQL on private network
   - Use VPN or SSH tunnel for remote access
   - Firewall rules to restrict database access

## Backup and Recovery

### Backup PostgreSQL Database

```bash
pg_dump -h localhost -p 5433 -U postgres flexible_graphrag_incremental > backup.sql
```

### Restore from Backup

```bash
psql -h localhost -p 5433 -U postgres flexible_graphrag_incremental < backup.sql
```

### Reset and Re-sync

To start fresh:

1. Stop backend
2. Clear tables: `TRUNCATE document_state, datasource_config CASCADE;`
3. Re-ingest with `enable_sync=true`
4. Start backend

## Advanced Configuration

### Custom PostgreSQL Connection Pooling

Modify in backend code if needed:

```python
# state_manager.py
self.pool = await asyncpg.create_pool(
    postgres_url,
    min_size=5,        # Minimum connections
    max_size=20,       # Maximum connections
    timeout=30,        # Connection timeout
    command_timeout=60 # Query timeout
)
```

### Adjust Detector Behavior

Edit detector configuration in `detectors/` folder:
- Change polling intervals
- Modify batch sizes
- Adjust error retry logic
- Custom file filtering

## Next Steps

- **[Quick Start](./QUICKSTART.md)** - Test basic functionality
- **[API Reference](./API-REFERENCE.md)** - Programmatic control
- **[S3 Setup](./S3-SETUP.md)** - Configure S3 event notifications
- **Diagnostic Queries**: Explore `diagnostic_queries.sql` and `datasource-queries.sql`
