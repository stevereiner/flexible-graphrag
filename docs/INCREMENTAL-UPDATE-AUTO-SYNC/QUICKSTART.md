# Quick Start Guide

Get incremental updates running in 5 minutes!

## Prerequisites

- Flexible GraphRAG backend running
- PostgreSQL database available
- At least one data source configured (filesystem, S3, Google Drive, etc.)

## Step 1: Database Setup (2 minutes)

### Option A: Use Existing PostgreSQL

If you have the `postgres-pgvector` service running (from main Flexible GraphRAG setup):

1. Create a new database in the same PostgreSQL instance:
   - Database name: `flexible_graphrag_incremental`
   - Port: Same as your PostgreSQL (usually 5433)

2. Run the schema:
   - Use the `schema.sql` file in the `incremental_updates` folder
   - Execute it against the new database

### Option B: Docker Compose (Recommended)

The `postgres-pgvector.yaml` service provides everything:
- PostgreSQL on port 5433
- pgAdmin at http://localhost:5050

1. Ensure it's uncommented in `docker/docker-compose.yaml`
2. Start services: `docker-compose up -d`
3. Access pgAdmin and create database `flexible_graphrag_incremental`
4. Run `schema.sql` via pgAdmin query tool

## Step 2: Configure Environment (1 minute)

Add to your `.env` file:

```bash
# PostgreSQL connection for incremental updates
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental

# Enable incremental updates
ENABLE_INCREMENTAL_UPDATES=true
```

**Note**: Replace `postgres:password` with your actual credentials.

## Step 3: Enable Sync via UI (2 minutes)

### For New Data Source

1. Open the web UI (http://localhost:5000)
2. Go to **Processing** tab → Click data source type (e.g., "Filesystem", "S3", "Google Drive")
3. Fill in source details:
   - Name: A descriptive name
   - Source-specific fields (path, bucket, folder ID, etc.)
4. **Enable Sync** section:
   - ✅ Enable automatic sync
   - Choose sync interval (default: 300 seconds)
   - Optional: Enable "Skip Graph" for faster syncs
5. Click **Process** or **Add Source**

### For Existing Data Source

If you already have documents ingested and want to enable sync:

1. Re-process through the UI with **"Enable Sync"** checkbox selected
2. This will:
   - Ingest documents (if not already present)
   - Create `datasource_config` entry
   - Create `document_state` records
   - Start monitoring for changes

## Step 4: Verify It's Working (1 minute)

### Check Backend Logs

You should see:

```
INFO: Incremental Update System starting...
INFO: Found 1 active data source(s) configured for auto-sync
INFO: Started 1 auto-sync updater(s)
INFO: Monitoring for configuration changes...
```

### Test Change Detection

**For Filesystem:**
1. Add a new `.txt` file to your monitored folder
2. Watch logs - should see: `EVENT: CREATE detected for filename.txt`
3. Check UI - document count should increase

**For S3:**
1. Upload a file to your monitored S3 bucket
2. If SQS configured: Change detected in 1-5 seconds
3. If polling only: Change detected within sync interval (5 minutes default)

**For Google Drive:**
1. Upload a file to your monitored folder
2. Within 60 seconds (default polling), should see: `EVENT: CREATE detected for filename.txt`

### Verify in Database

Using pgAdmin or psql:

```sql
-- Check datasource configuration
SELECT source_name, source_type, sync_status, last_sync_completed_at 
FROM datasource_config;

-- Check tracked documents
SELECT doc_id, source_path, ordinal 
FROM document_state 
ORDER BY ordinal DESC 
LIMIT 10;
```

## What Happens Next?

The system is now monitoring your data source and will automatically:

1. **Detect Changes**
   - CREATE: New files added
   - UPDATE: Existing files modified
   - DELETE: Files removed

2. **Process Changes**
   - Load document content
   - Process with DocumentProcessor (Docling/LlamaParse)
   - Generate embeddings
   - Update vector store (Qdrant)
   - Update search index (Elasticsearch)
   - Update knowledge graph (Neo4j) if enabled

3. **Track State**
   - Store document metadata in `document_state`
   - Update sync status in `datasource_config`
   - Skip reprocessing if only timestamp changed (content hash optimization)

## Common Issues

### No Changes Detected

**Problem**: Added file but nothing happens

**Solutions**:
- Check `is_active = true` in `datasource_config` table
- Verify backend logs show "Started N auto-sync updater(s)"
- For event-driven sources (S3, Filesystem), check event stream is enabled
- Try manual sync: `POST /api/incremental/sync/{config_id}`

### Documents Not Showing Up

**Problem**: Change detected but document not searchable

**Solutions**:
- Check backend logs for processing errors
- Verify vector store (Qdrant) and search index (Elasticsearch) are running
- Ensure data source credentials are correct
- Check `document_state` table - should have entry for the file

### Duplicate Processing

**Problem**: Same document processed multiple times

**Solutions**:
- Check only one datasource config exists for the location
- Verify `source_id` is populated in `document_state`
- Ensure detector initialization completed (check "Populated known_file_ids" in logs)

## Next Steps

- **[Setup Guide](./SETUP-GUIDE.md)** - Detailed configuration options
- **[API Reference](./API-REFERENCE.md)** - REST API for programmatic control
- **[S3 Setup](./S3-SETUP.md)** - Configure S3 with SQS event notifications for real-time updates
- **Diagnostic Queries**: Use `diagnostic_queries.sql` to inspect system state
- **Manual Sync**: Trigger on-demand sync via API or will be available in UI

## Advanced Configuration

### Adjust Sync Interval

Lower interval = faster change detection (but more frequent scans):

```sql
UPDATE datasource_config 
SET refresh_interval_seconds = 60  -- Check every 60 seconds
WHERE config_id = 'your-config-id';
```

### Skip Knowledge Graph

For faster syncs, skip graph extraction:

```sql
UPDATE datasource_config 
SET skip_graph = true
WHERE config_id = 'your-config-id';
```

Then restart the backend.

### Enable Event Stream

For sources that support it (S3 with SQS, Filesystem, Alfresco):

```sql
UPDATE datasource_config 
SET enable_change_stream = true
WHERE config_id = 'your-config-id';
```

This enables real-time change detection instead of periodic polling.

## Monitoring

### Check Sync Status

```sql
SELECT 
    source_name,
    sync_status,  -- 'idle', 'syncing', 'error'
    last_sync_completed_at,
    last_sync_error
FROM datasource_config;
```

### View Recent Changes

```sql
SELECT 
    doc_id,
    source_path,
    ordinal,
    content_hash,
    created_at
FROM document_state
ORDER BY ordinal DESC
LIMIT 20;
```

### Count Documents by Source

```sql
SELECT 
    dc.source_name,
    COUNT(*) as doc_count
FROM document_state ds
JOIN datasource_config dc ON ds.config_id = dc.config_id
GROUP BY dc.source_name;
```

## Support

For issues or questions:
1. Check backend logs for error messages
2. Review `diagnostic_queries.sql` for troubleshooting queries
3. See [Setup Guide](./SETUP-GUIDE.md) for detailed configuration
4. Check GitHub issues for known problems and solutions
