# Incremental Updates Management Scripts

This directory contains scripts for managing incremental updates and auto-sync functionality in Flexible GraphRAG.

> **📖 Understanding Timing**: See [TIMING-CONFIGURATION.md](./TIMING-CONFIGURATION.md) for a comprehensive guide to the dual timing mechanisms (real-time events + periodic polling) and how to configure them for different scenarios.

## Scripts

### set-refresh-interval (PowerShell, Bash, Batch)

Sets the refresh interval (polling frequency) for all datasources with auto-sync enabled.

**Files:**
- `set-refresh-interval.ps1` - PowerShell version (Windows)
- `set-refresh-interval.sh` - Bash version (Linux/macOS)
- `set-refresh-interval.bat` - Batch version (Windows)

**Features:**
- Support for hours, minutes, and seconds
- Can combine multiple time units
- Updates all configured datasources at once
- Shows updated datasource count

**Usage:**

PowerShell (Windows):
```powershell
# Set to 1 hour
.\set-refresh-interval.ps1 -Hours 1

# Set to 30 minutes
.\set-refresh-interval.ps1 -Minutes 30

# Set to 120 seconds
.\set-refresh-interval.ps1 -Seconds 120

# Combine: 1 hour, 30 minutes, 45 seconds (5445 seconds total)
.\set-refresh-interval.ps1 -Hours 1 -Minutes 30 -Seconds 45

# Custom API URL
.\set-refresh-interval.ps1 -Minutes 5 -ApiUrl "http://myserver:8000"
```

Bash (Linux/macOS):
```bash
# Set to 1 hour
./set-refresh-interval.sh --hours 1

# Set to 30 minutes
./set-refresh-interval.sh --minutes 30

# Set to 120 seconds
./set-refresh-interval.sh --seconds 120

# Combine: 1 hour, 30 minutes, 45 seconds
./set-refresh-interval.sh --hours 1 --minutes 30 --seconds 45

# Custom API URL
./set-refresh-interval.sh --minutes 5 --api-url "http://myserver:8000"

# Legacy mode (direct seconds)
./set-refresh-interval.sh 120
```

Batch (Windows):
```cmd
# Set to 120 seconds
set-refresh-interval.bat 120

# Custom API URL
set-refresh-interval.bat 120 http://myserver:8000
```

**Common Intervals:**
- **1 minute**: `--minutes 1` or `-Minutes 1` (60 seconds)
- **5 minutes**: `--minutes 5` or `-Minutes 5` (300 seconds)
- **15 minutes**: `--minutes 15` or `-Minutes 15` (900 seconds)
- **1 hour**: `--hours 1` or `-Hours 1` (3600 seconds)
- **2 hours**: `--hours 2` or `-Hours 2` (7200 seconds)

---

### sync-now (PowerShell, Bash, Batch)

Triggers an immediate synchronization for datasources with auto-sync enabled, bypassing the refresh interval.

**Files:**
- `sync-now.ps1` - PowerShell version (Windows)
- `sync-now.sh` - Bash version (Linux/macOS)
- `sync-now.bat` - Batch version (Windows)

**Features:**
- Trigger sync for all datasources or a specific one
- Useful for testing or forcing immediate updates
- Shows which datasources were triggered

**Usage:**

PowerShell (Windows):
```powershell
# Sync all datasources with auto-sync enabled
.\sync-now.ps1

# Sync specific datasource
.\sync-now.ps1 -ConfigId "alfresco_12345"

# Custom API URL
.\sync-now.ps1 -ConfigId "googledrive_67890" -ApiUrl "http://myserver:8000"
```

Bash (Linux/macOS):
```bash
# Sync all datasources with auto-sync enabled
./sync-now.sh

# Sync specific datasource
./sync-now.sh --config-id alfresco_12345

# Custom API URL
./sync-now.sh --config-id googledrive_67890 --api-url http://myserver:8000

# Legacy mode (config-id as first arg)
./sync-now.sh alfresco_12345
```

Batch (Windows):
```cmd
# Sync all datasources
sync-now.bat

# Sync specific datasource
sync-now.bat alfresco_12345

# Custom API URL
sync-now.bat googledrive_67890 http://myserver:8000
```

---

## API Endpoints

These scripts interact with the following FastAPI backend endpoints:

### Update Refresh Interval
```
POST /api/datasource/update-all-refresh-intervals?seconds={seconds}
```
Updates the `refresh_interval_seconds` for all datasource configurations.

**Response:**
```json
{
  "updated_count": 3,
  "configs": [
    {"config_id": "alfresco_12345", "source_type": "alfresco"},
    {"config_id": "googledrive_67890", "source_type": "google_drive"}
  ]
}
```

### Sync Now (All)
```
POST /api/datasource/sync-now-all
```
Triggers immediate sync for all datasources with `enable_sync=true`.

**Response:**
```json
{
  "triggered_count": 2,
  "configs": [
    {"config_id": "alfresco_12345", "source_type": "alfresco"},
    {"config_id": "googledrive_67890", "source_type": "google_drive"}
  ],
  "message": "Sync triggered for 2 datasource(s)"
}
```

### Sync Now (Specific)
```
POST /api/datasource/{config_id}/sync-now
```
Triggers immediate sync for a specific datasource.

**Response:**
```json
{
  "config_id": "alfresco_12345",
  "source_type": "alfresco",
  "message": "Sync triggered successfully"
}
```

---

## Requirements

**PowerShell scripts:**
- PowerShell 5.1+ (Windows) or PowerShell Core 7+ (cross-platform)
- `Invoke-RestMethod` cmdlet (built-in)

**Bash scripts:**
- curl (for HTTP requests)
- jq (optional, for pretty-printing JSON responses)

**Batch scripts:**
- curl (Windows 10+ includes curl.exe)

---

## Use Cases

### Testing Incremental Updates
```bash
# Set a short interval for testing (10 seconds)
./set-refresh-interval.sh --seconds 10

# Make changes to your datasource (edit files, upload documents, etc.)

# Wait for next poll or trigger immediately
./sync-now.sh

# Check logs to see changes detected
```

### Production Configuration
```bash
# Set reasonable production interval (2 hours)
./set-refresh-interval.sh --hours 2

# Or use minutes for more frequent updates (15 minutes)
./set-refresh-interval.sh --minutes 15
```

### Emergency Sync
```bash
# Force immediate sync without waiting for next poll
./sync-now.sh
```

---

## See Also

- [Incremental Updates README](../../flexible-graphrag/incremental_updates/README.md) - Main documentation
- [Additional Sources Setup](../../flexible-graphrag/incremental_updates/ADDITIONAL-SOURCES-SETUP.md) - Per-source configuration
- [Main README](../../README.md#incremental-updates--auto-sync) - Feature overview
