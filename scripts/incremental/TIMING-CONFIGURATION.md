# Incremental Updates Timing Configuration

This document explains the **two timing mechanisms** used by the incremental updates system and how to configure them.

---

## Two Timing Mechanisms

Flexible GraphRAG uses a **dual mechanism** for detecting changes:

### 1. Real-Time Event Streams (When Available)
- **What**: Immediate notifications from the datasource when files change
- **Speed**: Near-instant (seconds)
- **Examples**: Alfresco (ActiveMQ), S3 (SQS), Filesystem (watchdog), Azure Blob (change feed)
- **Debounce delay**: `watchdog_filesystem_seconds` (60 seconds default, filesystem only)

### 2. Periodic Polling (Fallback & Safety Net)
- **What**: Regular full scans to catch any missed changes
- **Speed**: Based on `refresh_interval_seconds` (5-60 minutes typical)
- **Examples**: Google Drive, Box, OneDrive/SharePoint polling
- **Purpose**: Ensures no changes are missed if event stream fails

**Important**: Even "real-time" datasources use periodic polling as a safety net!

---

## Configuration Parameters

### Per-Datasource Configuration

Each datasource configuration has two timing parameters:

| Parameter | Purpose | Default | Typical Range |
|-----------|---------|---------|---------------|
| `refresh_interval_seconds` | Periodic polling frequency | 3600 (1 hour) | 300-3600 (5 min - 1 hour) |
| `watchdog_filesystem_seconds` | Filesystem debounce delay | 60 (1 minute) | 10-300 (10 sec - 5 min) |

### System-Wide Configuration

In `orchestrator.py`:

| Parameter | Purpose | Default | Typical |
|-----------|---------|---------|---------|
| `initial_delay` | Wait before first periodic scan | 10 seconds | 120 seconds (production) |

---

## Default Values by Datasource Type

| Datasource | Real-Time Events | `refresh_interval_seconds` | `watchdog_filesystem_seconds` | Notes |
|------------|------------------|----------------------------|-------------------------------|-------|
| **Filesystem** | ✅ Yes (watchdog) | 3600 (1 hour) | 60 (1 minute) | Watchdog delay applies |
| **Amazon S3** | ✅ Yes (SQS) | 3600 (1 hour) | N/A | Events are instant |
| **Alfresco** | ✅ Yes (ActiveMQ) | 3600 (1 hour) | N/A | Events are instant |
| **Azure Blob** | ✅ Yes (change feed) | 3600 (1 hour) | N/A | Events are instant |
| **Google Cloud Storage** | ✅ Yes (Pub/Sub) | 3600 (1 hour) | N/A | Events are instant |
| **Google Drive** | ⚠️ Polling only | 300 (5 minutes) | N/A | No event stream |
| **Box** | ⚠️ Polling only | 300 (5 minutes) | N/A | No event stream |
| **OneDrive** | ⚠️ Polling only | 300 (5 minutes) | N/A | No event stream |
| **SharePoint** | ⚠️ Polling only | 300 (5 minutes) | N/A | No event stream |

---

## How to Configure

### Option 1: Environment Variable (System-Wide Default)

In `.env` file:

```bash
# Default refresh interval for all datasources (seconds)
INCREMENTAL_REFRESH_INTERVAL=3600  # 1 hour
```

This sets the default for new datasource configurations.

### Option 2: Per-Datasource via REST API

When creating/updating a datasource configuration:

```bash
POST /api/datasource/register

{
  "config_id": "googledrive_12345",
  "source_type": "google_drive",
  "source_name": "My Google Drive",
  "connection_params": { ... },
  "refresh_interval_seconds": 300,        # 5 minutes
  "watchdog_filesystem_seconds": 60,      # 1 minute (filesystem only)
  "enable_sync": true,
  "skip_graph": false
}
```

### Option 3: Update All Datasources via Script

Use the provided scripts to update all datasources at once:

**PowerShell:**
```powershell
# Set to 5 minutes for all datasources
.\scripts\incremental\set-refresh-interval.ps1 -Minutes 5

# Set to 1 hour
.\scripts\incremental\set-refresh-interval.ps1 -Hours 1
```

**Bash:**
```bash
# Set to 5 minutes for all datasources
./scripts/incremental/set-refresh-interval.sh --minutes 5

# Set to 1 hour
./scripts/incremental/set-refresh-interval.sh --hours 1
```

### Option 4: Update via SQL (Direct Database)

```sql
-- Update specific datasource
UPDATE datasource_config
SET refresh_interval_seconds = 300  -- 5 minutes
WHERE config_id = 'googledrive_12345';

-- Update all Google Drive datasources
UPDATE datasource_config
SET refresh_interval_seconds = 300
WHERE source_type = 'google_drive';

-- Update all datasources
UPDATE datasource_config
SET refresh_interval_seconds = 3600  -- 1 hour
WHERE is_active = true;
```

---

## Recommended Settings

### Development/Testing

Fast settings to see changes quickly:

| Setting | Value | Reason |
|---------|-------|--------|
| `refresh_interval_seconds` | **60** (1 minute) | Quick feedback |
| `watchdog_filesystem_seconds` | **10** (10 seconds) | Minimal delay |
| `initial_delay` (code) | **10** (10 seconds) | Fast startup |

**PowerShell:**
```powershell
.\scripts\incremental\set-refresh-interval.ps1 -Seconds 60
```

**Bash:**
```bash
./scripts/incremental/set-refresh-interval.sh --seconds 60
```

### Production - Real-Time Datasources

For datasources with event streams (S3, Alfresco, Filesystem, Azure, GCS):

| Setting | Value | Reason |
|---------|-------|--------|
| `refresh_interval_seconds` | **3600** (1 hour) | Safety net, infrequent |
| `watchdog_filesystem_seconds` | **60** (1 minute) | Debounce multiple edits |
| `initial_delay` (code) | **120** (2 minutes) | Avoid startup conflicts |

**PowerShell:**
```powershell
.\scripts\incremental\set-refresh-interval.ps1 -Hours 1
```

**Bash:**
```bash
./scripts/incremental/set-refresh-interval.sh --hours 1
```

### Production - Polling Datasources

For datasources without event streams (Google Drive, Box, OneDrive, SharePoint):

| Setting | Value | Reason |
|---------|-------|--------|
| `refresh_interval_seconds` | **300** (5 minutes) | Balance freshness & API usage |
| `watchdog_filesystem_seconds` | N/A | Not applicable |
| `initial_delay` (code) | **120** (2 minutes) | Avoid startup conflicts |

**PowerShell:**
```powershell
.\scripts\incremental\set-refresh-interval.ps1 -Minutes 5
```

**Bash:**
```bash
./scripts/incremental/set-refresh-interval.sh --minutes 5
```

### Production - Low Activity

For datasources that rarely change:

| Setting | Value | Reason |
|---------|-------|--------|
| `refresh_interval_seconds` | **7200** (2 hours) | Reduce overhead |
| `watchdog_filesystem_seconds` | **300** (5 minutes) | Batch multiple changes |

**PowerShell:**
```powershell
.\scripts\incremental\set-refresh-interval.ps1 -Hours 2
```

**Bash:**
```bash
./scripts/incremental/set-refresh-interval.sh --hours 2
```

---

## Understanding the Interaction

### Example: Filesystem with Real-Time Events

1. **User edits file** → Watchdog detects change instantly
2. **Debounce**: System waits `watchdog_filesystem_seconds` (60s) to batch edits
3. **Processing**: File is processed after debounce period
4. **Safety Net**: Every `refresh_interval_seconds` (3600s), full scan runs to catch any missed changes

### Example: Google Drive with Polling Only

1. **User edits file** → No immediate notification
2. **Wait**: System polls every `refresh_interval_seconds` (300s)
3. **Detection**: Next poll detects change based on modifiedTime
4. **Processing**: File is processed immediately after detection

---

## API Endpoints for Configuration

### Get Datasource Configuration
```bash
GET /api/datasource/{config_id}
```

Response includes current timing settings:
```json
{
  "config_id": "googledrive_12345",
  "source_type": "google_drive",
  "refresh_interval_seconds": 300,
  "watchdog_filesystem_seconds": 60
}
```

### Update All Refresh Intervals
```bash
POST /api/datasource/update-all-refresh-intervals?seconds=300
```

Response:
```json
{
  "updated_count": 5,
  "configs": [
    {"config_id": "googledrive_12345", "source_type": "google_drive"},
    {"config_id": "alfresco_67890", "source_type": "alfresco"}
  ]
}
```

---

## Troubleshooting

### Changes Not Detected

**Problem**: Changes aren't showing up

**Solutions**:
1. **Check sync is enabled**: Verify `enable_sync=true` in datasource config
2. **Check polling interval**: If too long, reduce `refresh_interval_seconds`
3. **Trigger manual sync**: Use `./scripts/incremental/sync-now.sh`
4. **Check logs**: Look for "SYNC: Starting periodic refresh" messages

### Too Many API Calls

**Problem**: High API usage or rate limiting

**Solutions**:
1. **Increase polling interval**: Set `refresh_interval_seconds` to 1800 (30 min) or higher
2. **Use event streams**: Configure real-time events instead of polling (S3 SQS, Alfresco ActiveMQ, etc.)
3. **Reduce datasource count**: Consolidate multiple configs if possible

### Filesystem Changes Delayed

**Problem**: File changes take too long to process

**Solutions**:
1. **Reduce debounce**: Lower `watchdog_filesystem_seconds` from 60 to 10-30 seconds
2. **Trigger manual sync**: Use `./scripts/incremental/sync-now.sh`
3. **Check logs**: Verify watchdog events are detected

---

## Summary Table

| You Want | Setting | Typical Value | Script Example |
|----------|---------|---------------|----------------|
| **Fast testing** | `refresh_interval_seconds` | 60 | `--seconds 60` |
| **Balanced production (polling)** | `refresh_interval_seconds` | 300 | `--minutes 5` |
| **Balanced production (events)** | `refresh_interval_seconds` | 3600 | `--hours 1` |
| **Low-activity sources** | `refresh_interval_seconds` | 7200 | `--hours 2` |
| **Filesystem debounce (fast)** | `watchdog_filesystem_seconds` | 10 | Set via API |
| **Filesystem debounce (batch)** | `watchdog_filesystem_seconds` | 60 | Set via API (default) |

---

## See Also

- [Incremental Updates Scripts](./README.md) - Script usage
- [Incremental Updates Main README](../../flexible-graphrag/incremental_updates/README.md) - Architecture
- [API Reference](../../flexible-graphrag/incremental_updates/API-REFERENCE.md) - Full API docs
