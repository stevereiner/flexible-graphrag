# Google Cloud Spanner Graph Setup

## Prerequisites

- Google Cloud project with Cloud Spanner API enabled
- Spanner instance created in the GCP Console
- Spanner database created inside the instance
- Python package: `llama-index-spanner` (included in `.[spanner-extras]`)
- `google-cloud-spanner` (included in `.[spanner-extras]`)

**Note:** The Spanner emulator only supports SQL — it does not support Spanner Graph (property
graph queries). Use a real Spanner instance.

## Install

```bash
uv pip install --python venv-3.13/Scripts/python.exe \
    -e ".[langchain,langchain-extras,spanner-extras]" \
    --override extras-overrides.txt
uv pip uninstall --python venv-3.13/Scripts/python.exe llama-index
```

The `llama-index` meta-package is pulled in by `llama-index-spanner` and downgrades other
packages. Always uninstall it after installing `spanner-extras`.

## Create a Spanner Instance and Database

In the GCP Console:

1. **Cloud Spanner** → **Create Instance**
   - Choose instance ID, configuration (regional or multi-region), and compute capacity
2. **Create Database** inside the instance
   - Database dialect: **Google Standard SQL** (not PostgreSQL dialect)
   - Leave DDL statements blank — the adapter creates the schema automatically on first ingest

## Schema Auto-Creation

`SpannerPropertyGraphStore` (from `llama-index-spanner`) creates all Spanner tables and the
property graph definition automatically on the first `upsert_nodes` call during ingest.

**Do not** create the tables or `CREATE PROPERTY GRAPH` DDL manually. The library manages
creation order:

1. `CREATE TABLE {graph_name}_NODE (id STRING, label STRING, properties JSON, ...) PRIMARY KEY (id)`
2. `CREATE TABLE {graph_name}_EDGE (id STRING, dest_id STRING, ...) REFERENCES {graph_name}_NODE`
3. `CREATE PROPERTY GRAPH {graph_name} NODE TABLES ({graph_name}_NODE ...) EDGE TABLES ({graph_name}_EDGE ...)`

For the default `graph_name=knowledge_graph` these are `knowledge_graph_NODE` and
`knowledge_graph_EDGE`. The `DYNAMIC LABEL` / `DYNAMIC PROPERTIES` clauses allow all entity and
relation types to share the two base tables (schemaless mode).

## IAM Permissions

The service account or user needs:

| Role | Purpose |
|---|---|
| `roles/spanner.databaseUser` | Read/write data (sessions, queries, mutations) |
| `roles/spanner.databaseAdmin` | Create tables and property graph DDL on first ingest |

Grant via GCP Console (**IAM & Admin** → **IAM** → your service account → **Edit** → **Add role**)
or via `gcloud`:

```bash
# Data user role (read/write):
gcloud spanner databases add-iam-policy-binding <database-id> \
    --instance=<instance-id> \
    --project=<project-id> \
    --member="serviceAccount:<sa-email>" \
    --role="roles/spanner.databaseUser"

# Admin role (DDL — needed only on first ingest):
gcloud spanner databases add-iam-policy-binding <database-id> \
    --instance=<instance-id> \
    --project=<project-id> \
    --member="serviceAccount:<sa-email>" \
    --role="roles/spanner.databaseAdmin"
```

The service account email is the `client_email` field in your service account JSON key file.

## Authentication

Priority order:

1. `credentials_file` in `SPANNER_GRAPH_DB_CONFIG` — path to a service account JSON key file
2. `GOOGLE_APPLICATION_CREDENTIALS` environment variable
3. `flexible-graphrag/gcs.json` — auto-detected if the file exists next to the package root
4. Application Default Credentials (`gcloud auth application-default login` or GCE metadata)

## Configuration

```env
PG_GRAPH_DB=spanner

# Service account JSON key file:
SPANNER_GRAPH_DB_CONFIG={"project_id": "my-gcp-project", "instance_id": "my-instance", "database_id": "my-database", "graph_name": "knowledge_graph", "credentials_file": "./gcs.json"}

# Application Default Credentials (gcloud auth):
SPANNER_GRAPH_DB_CONFIG={"project_id": "my-gcp-project", "instance_id": "my-instance", "database_id": "my-database", "graph_name": "knowledge_graph"}
```

### Config Keys

| Key | Required | Description |
|---|---|---|
| `project_id` | Yes | GCP project ID |
| `instance_id` | Yes | Spanner instance ID |
| `database_id` | Yes | Spanner database ID |
| `graph_name` | No | Property graph name (default: `knowledge_graph`) |
| `credentials_file` | No | Path to service account JSON key file |
| `use_flexible_schema` | No | `true` (default) — `{graph_name}_NODE` / `{graph_name}_EDGE` tables with JSON properties (schemaless); `false` — one table per entity type |

## Framework Support

Spanner is **LI only** — uses `llama-index-spanner` (`SpannerPropertyGraphStore`).
`GRAPH_BACKEND=llamaindex` is the only supported backend.

The `langchain-google-spanner` package requires `langchain-core<1.0` which is incompatible
with `langchain>=1.0` used by this project. LC support will be added if a compatible version
is released.

## Cleanup

```bash
python scripts/cleanup.py
```

Cleanup deletes all rows from `{graph_name}_EDGE` then `{graph_name}_NODE` (foreign key order;
defaults to `knowledge_graph_EDGE` / `knowledge_graph_NODE`). If tables do not exist yet (no
ingest has run), the cleanup skips them silently. Requires `spanner.databaseUser` IAM role on
the database.
