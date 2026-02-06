# Flexible GraphRAG Scripts

This directory contains utility scripts for managing various aspects of Flexible GraphRAG.

## Subdirectories

### incremental/
Scripts for managing incremental updates and auto-sync functionality. See [incremental/README.md](./incremental/README.md) for details.

- **set-refresh-interval** - Set polling interval for auto-sync datasources (supports hours, minutes, seconds)
- **sync-now** - Trigger immediate synchronization for datasources

## Scripts

### create_opensearch_pipeline.py

A Python script that creates and manages OpenSearch search pipelines for hybrid search functionality.

**Features:**
- Creates or updates OpenSearch search pipelines
- Configurable vector/text weight ratios
- SSL support for secure connections
- Authentication support
- Pipeline verification
- Uses standard REST API calls (no special client dependencies)

**Usage:**

```bash
# Basic usage (50/50 vector/text weights)
python scripts/create_opensearch_pipeline.py

# Custom weights (70% vector, 30% text)
python scripts/create_opensearch_pipeline.py --vector-weight 0.7 --text-weight 0.3

# Different host/port with authentication
python scripts/create_opensearch_pipeline.py --host opensearch.example.com --port 9200 --username admin --password secret

# Force update without confirmation
python scripts/create_opensearch_pipeline.py --force-update

# SSL connection
python scripts/create_opensearch_pipeline.py --ssl --host secure-opensearch.example.com --port 443
```

**Parameters:**
- `--host`: OpenSearch host (default: localhost)
- `--port`: OpenSearch port (default: 9201)
- `--username`: OpenSearch username (optional)
- `--password`: OpenSearch password (optional)
- `--pipeline-name`: Pipeline name (default: hybrid-search-pipeline)
- `--vector-weight`: Vector search weight (default: 0.5)
- `--text-weight`: Text search weight (default: 0.5)
- `--force-update`: Update without confirmation
- `--ssl`: Use SSL connection

**Requirements:**
- Python 3.6+
- `requests` library (included in Python standard library)

### setup-opensearch-pipeline.sh / setup-opensearch-pipeline.bat

Shell scripts that create the hybrid search pipeline using curl commands.

**Usage:**

Linux/macOS:
```bash
./scripts/setup-opensearch-pipeline.sh
```

Windows:
```cmd
scripts\setup-opensearch-pipeline.bat
```

**Configuration:**
Both scripts use default configuration:
- Host: localhost:9201
- Pipeline: hybrid-search-pipeline
- Weights: [0.3, 0.7] (30% vector, 70% text - keyword focused)

## Pipeline Configuration

The scripts create a search pipeline with:
- **Normalization**: min_max technique
- **Combination**: harmonic_mean technique
- **Weights**: Configurable vector/text balance

**Weight Examples:**
- `[0.3, 0.7]`: 30% vector, 70% text (keyword focus)
- `[0.5, 0.5]`: 50% vector, 50% text (balanced)
- `[0.7, 0.3]`: 70% vector, 30% text (semantic focus)

## Integration

The created pipeline integrates with the Flexible GraphRAG system when using:
- `VECTOR_DB=opensearch`
- `SEARCH_DB=opensearch`

The system will automatically use the `hybrid-search-pipeline` for hybrid search queries.

---

## Legacy Scripts (Top-level)

The following scripts exist at the top level of the scripts directory for backward compatibility:

### set-refresh-interval.ps1 / set-refresh-interval.sh

**Note:** These are legacy versions. For enhanced functionality including hours/minutes/seconds support and sync-now capabilities, use the scripts in the [incremental/](./incremental/) subdirectory.

**Legacy Usage:**
```bash
# PowerShell
.\set-refresh-interval.ps1 -Seconds 60

# Bash
./set-refresh-interval.sh 60
```

**Migration:** Consider using the new scripts in `scripts/incremental/` which support:
- Hours, minutes, and seconds (can be combined)
- Batch file version for Windows
- Better output formatting
- Additional sync-now functionality
