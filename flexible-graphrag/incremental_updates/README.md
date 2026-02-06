# Flexible GraphRAG - Incremental Update System

Automatically synchronizes vector, search, and graph indexes when documents change in monitored data sources.

## Overview

The Incremental Update System provides real-time and periodic synchronization of your knowledge base. When documents are added, modified, or deleted in your data sources, the system automatically updates all indexes without manual intervention.

**Key Benefits:**
- **Automatic Sync**: Changes propagate to indexes automatically
- **Real-time Updates**: Event-driven detection (when supported) for sub-second latency
- **Cost Efficient**: Skip unnecessary reprocessing with content hashing
- **Robust**: Handles failures gracefully with retry logic and partial sync recovery
- **Scalable**: Supports multiple data sources simultaneously

## Features

### Intelligent Change Detection

- **Ordinal-Based Versioning**: Monotonic timestamp tracking (microsecond precision) ensures correct ordering
- **Content Hash Optimization**: Skip reprocessing when only timestamps change
- **Per-Document Tracking**: Prevents concurrent processing conflicts
- **Multi-Target Coordination**: Independent sync state for Vector, Search, and Graph indexes

### Dual Update Mechanism

1. **Event-Driven Streams** (when supported) - Real-time change notifications for instant updates
2. **Periodic Polling** (configurable interval) - Comprehensive fallback that catches any missed changes

### Supported Data Sources

| Source | Change Detection | Status |
|--------|------------------|--------|
| **Filesystem** | Real-time OS events (watchdog) | ✅ Production |
| **Amazon S3** | SQS event notifications | ✅ Production |
| **Alfresco** | ActiveMQ events + Polling | ✅ Production |
| **Google Drive** | Changes API (polling) | ✅ Ready |
| **Azure Blob Storage** | Change feed iterator | ✅ Ready |
| **Google Cloud Storage** | Pub/Sub notifications | ✅ Ready |
| **Box** | Events API (polling) | ✅ Ready |
| **Microsoft Graph (SharePoint/OneDrive)** | Delta query (polling) | ✅ Ready |

## Architecture

```
┌─────────────────┐
│  Data Sources   │  Filesystem, S3, Alfresco, Google Drive, etc.
└────────┬────────┘
         │ Changes detected
         ▼
┌─────────────────┐
│  Change         │  Event streams + Periodic polling
│  Detectors      │  
└────────┬────────┘
         │ Events: CREATE, UPDATE, DELETE
         ▼
┌─────────────────┐
│  Incremental    │  Deduplication, batching, ordering
│  Update Engine  │
└────────┬────────┘
         │ Process changes
         ▼
┌─────────────────┐
│  Backend        │  Document processing (Docling/LlamaParse)
│  Pipeline       │  Chunking, embedding generation
└────────┬────────┘
         │ Update indexes
         ▼
┌─────────────────┐
│  Vector Search  │  Qdrant (vectors) + Elasticsearch (text)
│  Graph Indexes  │  Neo4j (knowledge graph)
└─────────────────┘
```

## Quick Links

- **[Quick Start Guide](./QUICKSTART.md)** - Get running in 5 minutes
- **[Setup Guide](./SETUP-GUIDE.md)** - Complete installation and configuration
- **[API Reference](./API-REFERENCE.md)** - REST API documentation
- **[S3 Setup Guide](./S3-SETUP.md)** - Configure S3 with event notifications

## How It Works

### 1. Monitor Data Sources

Each configured data source is monitored by a **Change Detector** that tracks:
- New files/documents (CREATE)
- Modified files/documents (UPDATE)
- Deleted files/documents (DELETE)

### 2. Detect Changes

Changes are detected through:

**Event Streams** (preferred):
- Filesystem: OS-level file system events
- S3: SQS notifications from S3 bucket events
- Alfresco: ActiveMQ message queue

**Periodic Polling** (fallback):
- List all files and compare with stored state
- Detect additions, modifications, and deletions
- Configurable interval (default: 5 minutes)

### 3. Process Changes

The **Incremental Update Engine**:
1. Deduplicates events (same file changed multiple times)
2. Orders by ordinal (timestamp) to prevent race conditions
3. Checks content hash to skip unnecessary reprocessing
4. Routes to appropriate handler (ADD/UPDATE/DELETE)

### 4. Update Indexes

**For ADD/UPDATE:**
- Load document from source
- Process with DocumentProcessor (Docling/LlamaParse)
- Generate embeddings
- Update vector store (Qdrant)
- Update search index (Elasticsearch)
- Extract entities and relationships for graph (Neo4j) if enabled

**For DELETE:**
- Remove from vector store by document ID
- Remove from search index by document ID
- Remove nodes/relationships from graph by document ID

### 5. Track State

**PostgreSQL** stores sync state:
- `datasource_config`: Data source configurations and sync status
- `document_state`: Per-document tracking (content hash, ordinal, source ID)

## Configuration

### Environment Variables

Set in your `.env` file:

```bash
# PostgreSQL for incremental updates state management
POSTGRES_INCREMENTAL_URL=postgresql://user:pass@localhost:5433/flexible_graphrag_incremental

# Enable incremental updates
ENABLE_INCREMENTAL_UPDATES=true
```

### Data Source Configuration

Configure via UI or REST API:

- **Source Name**: Human-readable identifier
- **Source Type**: filesystem, s3, alfresco, google_drive, etc.
- **Connection Parameters**: Source-specific (paths, credentials, buckets, etc.)
- **Refresh Interval**: Seconds between periodic scans (default: 300)
- **Enable Change Stream**: Use event-driven detection when available
- **Skip Graph**: Optionally skip knowledge graph extraction for faster syncs

## Management

### Via Web UI

1. Navigate to "Processing" or "Data Sources" tab
2. Enable sync when adding/editing a data source
3. View sync status and last sync time
4. Trigger manual sync on-demand

### Via REST API

See [API-REFERENCE.md](./API-REFERENCE.md) for complete documentation.

**Quick examples:**

Enable sync during ingest:
```json
POST /api/ingest
{
  "data_source": "filesystem",
  "paths": ["/data/documents"],
  "enable_sync": true,
  "skip_graph": true
}
```

Trigger manual sync:
```
POST /api/incremental/sync/{config_id}
```

## Performance

### Event-Driven vs Polling

| Metric | Event-Driven | Polling (5 min) |
|--------|--------------|-----------------|
| **Latency** | 1-5 seconds | 1-5 minutes |
| **API Calls** | ~1 per change | Full scan every interval |
| **Cost** | Very low | Moderate |
| **Scalability** | Excellent | Good |

### Content Hashing

When a file's timestamp changes but content is identical:
- **Without hashing**: Full reprocessing (~10-60 seconds per document)
- **With hashing**: Update ordinal only (~10ms per document)

**Result**: 100-1000x faster for timestamp-only changes

## Troubleshooting

### System Not Detecting Changes

1. Check backend logs for incremental system startup
2. Verify datasource is marked as `active` in PostgreSQL
3. Confirm `enable_change_stream` is true for event-driven sources
4. Check source-specific requirements (SQS for S3, ActiveMQ for Alfresco, etc.)

### Changes Detected But Not Applied

1. Check `document_state` table for records
2. Verify vector/search indexes are accessible
3. Look for errors in backend processing logs
4. Ensure correct credentials for data source

### Duplicate Processing

1. Verify `document_state` records have correct `source_id`
2. Check for multiple detectors monitoring same location
3. Ensure ordinal values are monotonically increasing

### Performance Issues

1. Reduce `refresh_interval` if polling too frequently
2. Enable `skip_graph` to skip knowledge graph extraction
3. Increase batch sizes in engine configuration
4. Use event-driven detection instead of polling

## Database Schema

Two main tables in PostgreSQL:

**datasource_config**: Stores data source configurations
- `config_id` (UUID, primary key)
- `source_name`, `source_type`
- `connection_params` (JSON)
- `is_active`, `sync_status`
- `refresh_interval_seconds`
- `enable_change_stream`, `skip_graph`

**document_state**: Tracks processed documents
- `doc_id` (primary key, format: `config_id:filename`)
- `config_id` (foreign key)
- `source_path` (filename or path)
- `content_hash` (for change detection)
- `ordinal` (microsecond timestamp)
- `source_id` (cloud file ID for DELETE operations)

See `schema.sql` for complete schema definition.

## Security

- Store credentials in environment variables, not in datasource configs
- Use read-only access for data sources when possible
- Restrict PostgreSQL access to backend only
- Enable SSL for PostgreSQL connections in production
- Use IAM roles for cloud services (S3, GCS, Azure) instead of static credentials

## License

See main project LICENSE file.
