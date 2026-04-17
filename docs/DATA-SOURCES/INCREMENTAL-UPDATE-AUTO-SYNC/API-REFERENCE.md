# Incremental Updates - API Reference

Complete REST API documentation for managing incremental sync operations.

## Base URL

```
http://localhost:8000
```

All endpoints are prefixed with `/api`.

## Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/ingest` | POST | Ingest documents with optional sync enablement |
| `/api/sync/datasources` | GET | List all datasources |
| `/api/sync/datasources/{config_id}/interval` | PATCH | Update refresh interval |
| `/api/sync/datasources/{config_id}/disable` | PATCH | Disable datasource |
| `/api/sync/datasources/{config_id}/enable` | PATCH | Enable datasource |
| `/api/sync/sync-now/{config_id}` | POST | Trigger manual sync (single source) |
| `/api/sync/sync-now` | POST | Trigger manual sync (all sources) |
| `/api/sync/start-monitoring` | POST | Start incremental monitoring |
| `/api/sync/disable-all` | POST | Disable all datasources |
| `/api/sync/enable-all` | POST | Enable all datasources |
| `/api/sync/interval` | PATCH | Update global sync interval |
| `/api/sync/status` | GET | Get system status |

## Ingest with Sync

### Enable Sync During Ingest

Ingest documents and enable automatic synchronization in one operation.

**Endpoint:** `POST /api/ingest`

**Request Body:**

```json
{
  "data_source": "filesystem",
  "paths": ["/data/documents"],
  "enable_sync": true,
  "skip_graph": true,
  "sync_config": {
    "source_name": "My Documents",
    "refresh_interval_seconds": 300,
    "enable_change_stream": true
  }
}
```

**Parameters:**

- `data_source` (string, required): Source type (`filesystem`, `s3`, `google_drive`, etc.)
- `paths` (array, required for filesystem): Paths to monitor
- `enable_sync` (boolean): Enable automatic sync (default: `false`)
- `skip_graph` (boolean): Skip knowledge graph extraction (default: `false`)
- `sync_config` (object, optional): Sync configuration
  - `source_name` (string): Human-readable name
  - `refresh_interval_seconds` (integer): Seconds between scans (default: 300)
  - `enable_change_stream` (boolean): Use event-driven detection (default: `false`)

**Response:**

```json
{
  "status": "started",
  "message": "Document processing started",
  "processing_id": "abc123",
  "sync_enabled": true,
  "config_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Example - Filesystem:**

```json
{
  "data_source": "filesystem",
  "paths": ["/data/documents"],
  "enable_sync": true,
  "skip_graph": true,
  "sync_config": {
    "source_name": "Local Docs",
    "refresh_interval_seconds": 300,
    "enable_change_stream": true
  }
}
```

**Example - S3:**

```json
{
  "data_source": "s3",
  "s3_config": {
    "bucket_name": "my-bucket",
    "prefix": "documents/",
    "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123456789/my-queue"
  },
  "enable_sync": true,
  "skip_graph": true,
  "sync_config": {
    "source_name": "S3 Documents",
    "enable_change_stream": true
  }
}
```

**Example - Google Drive:**

```json
{
  "data_source": "google_drive",
  "google_drive_config": {
    "credentials": "{...service account JSON...}",
    "folder_id": "1ABC...XYZ"
  },
  "enable_sync": true,
  "skip_graph": false,
  "sync_config": {
    "source_name": "Drive Folder",
    "refresh_interval_seconds": 60
  }
}
```

## Datasource Management

### List All Datasources

Get all configured datasources for incremental sync.

**Endpoint:** `GET /api/sync/datasources`

**Response:**

```json
{
  "status": "success",
  "datasources": [
    {
      "config_id": "550e8400-e29b-41d4-a716-446655440000",
      "source_name": "My Documents",
      "source_type": "filesystem",
      "is_active": true,
      "sync_status": "idle",
      "last_sync_completed_at": "2026-01-24T10:30:00Z",
      "last_sync_ordinal": 1737716400000000,
      "refresh_interval_seconds": 300,
      "enable_change_stream": true,
      "skip_graph": true,
      "connection_params": {
        "paths": ["/data/documents"]
      }
    }
  ]
}
```

### Get Single Datasource

**Note:** This endpoint does not currently exist. Datasource details can be retrieved using `GET /api/sync/datasources` (list all) and filtering by `config_id` on the client side.

### Create Datasource

**Note:** Datasources are currently created via the `/api/ingest` endpoint with `enable_sync: true`. Direct POST/PUT/DELETE operations for datasources are not yet implemented.

To create a new monitored datasource, use:

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "filesystem",
    "paths": ["/data/new-docs"],
    "enable_sync": true,
    "skip_graph": true,
    "sync_config": {
      "source_name": "New Documents",
      "refresh_interval_seconds": 300
    }
  }'
```

### Update Datasource

Use the specific PATCH endpoints below to update datasource properties:

- **Update refresh interval:** `PATCH /api/sync/datasources/{config_id}/interval`
- **Disable datasource:** `PATCH /api/sync/datasources/{config_id}/disable`
- **Enable datasource:** `PATCH /api/sync/datasources/{config_id}/enable`

### Delete Datasource

**Note:** Direct DELETE operation is not currently implemented. To stop a datasource from syncing, use the disable endpoint:

```bash
curl -X PATCH http://localhost:8000/api/sync/datasources/{config_id}/disable
```

## Datasource Operations

### Update Refresh Interval

Update the periodic refresh interval for a datasource.

**Endpoint:** `PATCH /api/sync/datasources/{config_id}/interval`

**Query Parameters:**

- `interval_seconds` (integer): Direct seconds value (takes precedence)
- `hours` (integer): Number of hours (combined with minutes/seconds)
- `minutes` (integer): Number of minutes (combined with hours/seconds) 
- `seconds` (integer): Number of seconds (combined with hours/minutes)

**Examples:**

```bash
# Set to 1 hour using seconds
curl -X PATCH "http://localhost:8000/api/sync/datasources/550e8400-.../interval?interval_seconds=3600"

# Set to 1 hour using hours parameter
curl -X PATCH "http://localhost:8000/api/sync/datasources/550e8400-.../interval?hours=1"

# Set to 2.5 hours
curl -X PATCH "http://localhost:8000/api/sync/datasources/550e8400-.../interval?hours=2&minutes=30"

# Disable periodic sync (set to 0)
curl -X PATCH "http://localhost:8000/api/sync/datasources/550e8400-.../interval?interval_seconds=0"
```

**Response:**

```json
{
  "status": "success",
  "message": "Updated refresh interval to 3600 seconds",
  "config_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Notes:**
- Minimum interval is 60 seconds (or 0 to disable)
- If using time units (hours/minutes/seconds), at least one must be provided
- `interval_seconds` takes precedence over time unit parameters

### Disable Datasource

Disable automatic syncing for a specific datasource.

**Endpoint:** `PATCH /api/sync/datasources/{config_id}/disable`

**Response:**

```json
{
  "status": "success",
  "message": "Disabled datasource 550e8400-...",
  "config_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Enable Datasource

Enable automatic syncing for a specific datasource.

**Endpoint:** `PATCH /api/sync/datasources/{config_id}/enable`

**Response:**

```json
{
  "status": "success",
  "message": "Enabled datasource 550e8400-...",
  "config_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Disable All Datasources

Disable automatic syncing for all datasources.

**Endpoint:** `POST /api/sync/disable-all`

**Response:**

```json
{
  "status": "success",
  "message": "Disabled 3 datasource(s)",
  "disabled_count": 3,
  "note": "Datasources will stop syncing. Use /api/sync/enable-all to re-enable."
}
```

### Enable All Datasources

Enable automatic syncing for all datasources.

**Endpoint:** `POST /api/sync/enable-all`

**Response:**

```json
{
  "status": "success",
  "message": "Enabled 2 datasource(s)",
  "enabled_count": 2
}
```

## Manual Sync Operations

### Sync Single Datasource

Trigger immediate sync for a specific datasource.

**Endpoint:** `POST /api/sync/sync-now/{config_id}`

**Response:**

```json
{
  "status": "success",
  "message": "Sync completed for My Documents",
  "config_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Use Cases:**
- Force immediate sync without waiting for interval
- Test change detection after configuration changes
- Recover from errors

### Sync All Datasources

Trigger immediate sync for all active datasources **sequentially**.

**Endpoint:** `POST /api/sync/sync-now`

**Response:**

```json
{
  "status": "success",
  "message": "Synced 3 datasource(s)",
  "results": [
    {
      "config_id": "550e8400-e29b-41d4-a716-446655440000",
      "source_name": "My Documents",
      "status": "success"
    },
    {
      "config_id": "660e8400-e29b-41d4-a716-446655440000",
      "source_name": "S3 Bucket",
      "status": "success"
    }
  ]
}
```

**Note:** Syncs run sequentially to avoid overwhelming the system.

## Status and Monitoring

### Get System Status

Get overall incremental sync system status.

**Endpoint:** `GET /api/sync/status`

**Response:**

```json
{
  "status": "active",
  "initialized": true,
  "monitoring": true,
  "active_updaters": 2,
  "total_datasources": 2,
  "active_datasources": 2
}
```

**Status Values:**
- `active`: System running normally and monitoring active
- `initialized`: System initialized but monitoring not started
- `disabled`: Incremental system not configured

**Note:** Individual datasource status can be retrieved from the `datasources` array in the `GET /api/sync/datasources` response. There is no separate single-datasource status endpoint.

## Start Monitoring

Manually start the orchestrator monitoring (useful for debug/recovery).

**Endpoint:** `POST /api/sync/start-monitoring`

**Response:**

```json
{
  "status": "success",
  "message": "Monitoring started",
  "active_updaters": 2
}
```

**Use Cases:**
- Start monitoring after system initialization
- Restart monitoring if it stopped for some reason
- Recovery after errors

## Data Source Specific Configuration

### Filesystem

```json
{
  "source_type": "filesystem",
  "connection_params": {
    "paths": ["/data/documents", "/data/reports"]
  },
  "enable_change_stream": true  // Real-time OS events
}
```

### Amazon S3

```json
{
  "source_type": "s3",
  "connection_params": {
    "bucket_name": "my-bucket",
    "prefix": "documents/",
    "sqs_queue_url": "https://sqs.region.amazonaws.com/account/queue",
    "region_name": "us-east-1"
  },
  "enable_change_stream": true  // Requires SQS
}
```

### Google Drive

```json
{
  "source_type": "google_drive",
  "connection_params": {
    "credentials": "{...service account JSON...}",
    "folder_id": "1ABC...XYZ",
    "recursive": true
  },
  "enable_change_stream": false  // Polling only
}
```

### Alfresco

```json
{
  "source_type": "alfresco",
  "connection_params": {
    "base_url": "http://alfresco:8080",
    "username": "admin",
    "password": "admin",
    "site_id": "my-site",
    "folder_path": "/documentLibrary/documents"
  },
  "enable_change_stream": true  // Requires ActiveMQ
}
```

### Box

```json
{
  "source_type": "box",
  "connection_params": {
    "client_id": "...",
    "client_secret": "...",
    "enterprise_id": "...",
    "folder_id": "0"
  },
  "enable_change_stream": false  // Polling only
}
```

### Microsoft Graph (SharePoint/OneDrive)

```json
{
  "source_type": "msgraph",
  "connection_params": {
    "client_id": "...",
    "client_secret": "...",
    "tenant_id": "...",
    "site_id": "...",
    "drive_id": "...",
    "folder_path": "/Documents"
  },
  "enable_change_stream": false  // Polling only
}
```

### Google Cloud Storage

```json
{
  "source_type": "gcs",
  "connection_params": {
    "bucket_name": "my-bucket",
    "prefix": "documents/",
    "credentials": "{...service account JSON...}",
    "topic_name": "projects/my-project/topics/gcs-changes"
  },
  "enable_change_stream": true  // Requires Pub/Sub
}
```

### Azure Blob Storage

```json
{
  "source_type": "azure_blob",
  "connection_params": {
    "connection_string": "...",
    "container_name": "documents",
    "prefix": "folder/"
  },
  "enable_change_stream": true  // Uses change feed
}
```

## Error Responses

### Standard Error Format

```json
{
  "status": "error",
  "message": "Error description",
  "error_code": "ERROR_CODE"
}
```

### Common Error Codes

**400 Bad Request:**
- Missing required parameters
- Invalid datasource type
- Invalid configuration

**404 Not Found:**
- Datasource config_id not found
- System not initialized

**500 Internal Server Error:**
- Database connection failed
- Sync operation failed
- System error

## Best Practices

### 1. Always Enable Sync During Initial Ingest

```json
{
  "data_source": "filesystem",
  "paths": ["/data"],
  "enable_sync": true  // ✅ Enable from the start
}
```

This ensures:
- `datasource_config` is created
- `document_state` records are created for all documents
- Change detection starts immediately

### 2. Use Appropriate Refresh Intervals

```json
{
  "refresh_interval_seconds": 60   // ❌ Too frequent (high API usage)
  "refresh_interval_seconds": 300  // ✅ Good default (5 minutes)
  "refresh_interval_seconds": 3600 // ✅ OK for slow-changing sources
}
```

### 3. Enable Event Streams When Available

```json
{
  "enable_change_stream": true  // ✅ Real-time updates (S3, Filesystem, Alfresco)
}
```

Benefits:
- 1-5 second latency vs 1-5 minute latency
- 60x fewer API calls
- Better scalability

### 4. Skip Graph for Large Document Sets

```json
{
  "skip_graph": true  // ✅ Faster syncs (5-10x speedup)
}
```

Graph extraction is expensive. Skip it for:
- Large document collections
- Frequently changing documents
- When graph features aren't needed

### 5. Monitor Sync Status

Regular health checks:

```bash
# Check overall system
curl http://localhost:8000/api/sync/status

# Check specific datasource
curl http://localhost:8000/api/sync/status/{config_id}
```

### 6. Handle Errors Gracefully

When sync fails:
1. Check `last_sync_error` in status response
2. Review backend logs for details
3. Fix configuration or permissions
4. Trigger manual sync to retry

## Rate Limits and Performance

### API Rate Limits

No hard rate limits, but recommended:
- Manual sync: Max 1 request per second per datasource
- Status checks: Max 10 requests per second
- Datasource CRUD: Max 5 requests per second

### Performance Considerations

**Sync Duration:**
- Small changes (1-10 docs): 1-30 seconds
- Medium changes (10-100 docs): 30 seconds - 5 minutes
- Large changes (100+ docs): 5-30 minutes

**Factors:**
- Document size and complexity
- Number of documents
- `skip_graph` setting (5-10x speedup when enabled)
- Network latency to data source
- Vector/search/graph service performance

## Security

### Authentication

Currently no authentication required (designed for internal use).

For production:
- Deploy behind reverse proxy with authentication
- Use API gateway with rate limiting
- Implement token-based auth

### Credentials

**Never** store credentials in API requests or datasource configs directly:

❌ Bad:
```json
{
  "connection_params": {
    "password": "mypassword123"
  }
}
```

✅ Good - Store in environment variables:
```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

Then reference in connection_params (backend reads from env).

## Examples

### Complete Workflow: Filesystem

```bash
# 1. Ingest with sync enabled
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "filesystem",
    "paths": ["/data/documents"],
    "enable_sync": true,
    "sync_config": {
      "source_name": "Local Docs",
      "enable_change_stream": true
    }
  }'

# Response: { "config_id": "550e8400-..." }

# 2. Check status
curl http://localhost:8000/api/sync/status/550e8400-...

# 3. Trigger manual sync
curl -X POST http://localhost:8000/api/sync/sync-now/550e8400-...

# 4. List all datasources
curl http://localhost:8000/api/sync/datasources
```

### Complete Workflow: S3 with SQS

```bash
# 1. Ingest with sync and SQS
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "data_source": "s3",
    "s3_config": {
      "bucket_name": "my-bucket",
      "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123/queue"
    },
    "enable_sync": true,
    "skip_graph": true,
    "sync_config": {
      "source_name": "S3 Docs",
      "enable_change_stream": true
    }
  }'

# 2. Monitor system
curl http://localhost:8000/api/sync/status

# 3. Check specific datasource
curl http://localhost:8000/api/sync/datasources/{config_id}
```

## Troubleshooting

### Sync Not Triggering

**Check:**
```bash
# List all datasources and check the specific one
curl http://localhost:8000/api/sync/datasources
```

**Look for:**
- `is_active: false` → Use PATCH `/api/sync/datasources/{config_id}/enable` to enable
- `sync_status: error` → Check backend logs for error details
- `last_sync_at: null` → Never synced, try manual sync with POST `/api/sync/sync-now/{config_id}`

### Changes Not Detected

**For event-driven sources:**
- Verify `enable_change_stream: true`
- Check event source is configured (SQS, ActiveMQ, etc.)
- Review backend logs for event stream errors

**For polling sources:**
- Check `refresh_interval_seconds` isn't too high
- Trigger manual sync to test immediately
- Verify data source credentials and permissions

### Performance Issues

**Try:**
- Enable `skip_graph: true`
- Increase `refresh_interval_seconds`
- Use event-driven detection instead of polling
- Check vector/search/graph services are healthy
