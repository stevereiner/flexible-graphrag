# MCP Tools Reference

The MCP server provides **9 tools** for document ingestion, search, and AI Q&A.

## Available Tools

| Tool | What it does |
|---|---|
| `get_system_status()` | Verify setup and database connections |
| `ingest_documents()` | Process documents from any of the 13 data sources |
| `ingest_text(content, source_name)` | Ingest and analyze specific text content |
| `search_documents(query, top_k)` | Hybrid search — find relevant document excerpts |
| `query_documents(query, top_k)` | AI-powered Q&A over your document corpus |
| `test_with_sample()` | Quick system verification with built-in sample content |
| `check_processing_status(id)` | Track long-running async ingestion tasks |
| `get_python_info()` | Python environment diagnostics |
| `health_check()` | Verify backend API connectivity |

## `ingest_documents()` — All 13 Data Sources

| Source | Key Config Fields |
|---|---|
| `filesystem` | `paths` — list of file or directory paths |
| `alfresco` | `base_url`, `username`, `password`, `paths`; also `nodeDetails` for KG Spaces |
| `cmis` | `cmis_url`, `username`, `password`, `paths` |
| `s3` | `bucket`, `aws_access_key_id`, `aws_secret_access_key`, `region` |
| `azure_blob` | `connection_string`, `container_name` |
| `gcs` | `bucket_name`, `credentials_path` |
| `onedrive` | `client_id`, `client_secret`, `tenant_id` |
| `google_drive` | `credentials_path`, `folder_id` |
| `sharepoint` | `client_id`, `client_secret`, `tenant_id`, `site_url` |
| `box` | `client_id`, `client_secret`, `folder_id` |
| `web` | `urls` — list of web page URLs |
| `wikipedia` | `titles` — list of article titles |
| `youtube` | `urls` — list of YouTube video URLs |

All sources support `skip_graph: true` to skip knowledge graph extraction (vector + search only).
