# MCP Tools Reference

The MCP server provides **9 tools** for document ingestion, search, and AI Q&A.

## Available Tools

| Tool | What it does |
|---|---|
| `get_system_status()` | Verify setup and database connections |
| `ingest_documents(data_source, skip_graph, ...)` | Process documents from any of the 13 data sources |
| `ingest_text(content, source_name, skip_graph)` | Ingest and analyze specific text content; `skip_graph=True` skips KG extraction |
| `search_documents(query, top_k)` | Hybrid search — find relevant document excerpts |
| `query_documents(query, top_k)` | AI-powered Q&A over your document corpus |
| `test_with_sample(skip_graph)` | Quick system verification with built-in sample content; `skip_graph=True` for vector-only |
| `check_processing_status(id)` | Track long-running async ingestion tasks |
| `get_python_info()` | Python environment diagnostics |
| `health_check()` | Verify backend API connectivity |

## `ingest_documents()` — Arguments

<table>
<colgroup>
  <col style="width:165px">
  <col style="width:55px">
  <col style="width:110px">
  <col>
</colgroup>
<thead><tr>
  <th>Argument</th><th>Type</th><th>Default</th><th>Description</th>
</tr></thead>
<tbody>
<tr><td><code>data_source</code></td><td><code>str</code></td><td><code>"filesystem"</code></td><td>Source type — see Data Source JSON Config Strings table below</td></tr>
<tr><td><code>paths</code></td><td><code>str</code></td><td><code>None</code></td><td><strong><code>filesystem</code> only</strong> — file/directory paths; JSON array <code>["p1","p2"]</code>, comma-separated, or single path</td></tr>
<tr><td><code>skip_graph</code></td><td><code>bool</code></td><td><code>false</code></td><td>Skip KG extraction and graph store writes; chunk + embed + vector/search only</td></tr>
<tr><td><code>enable_sync</code></td><td><code>bool</code></td><td><code>false</code></td><td>Enable automatic change detection and incremental updates for the source</td></tr>
<tr><td><code>&lt;source&gt;_config</code></td><td><code>str</code></td><td><code>None</code></td><td>JSON config string for non-filesystem sources (e.g. <code>alfresco_config</code>, <code>s3_config</code>) — see table below</td></tr>
</tbody>
</table>

!!! note
    `filesystem` uses the `paths` argument, not a JSON config string. All other sources pass their
    connection details as a JSON string in the corresponding `<source>_config` argument.

## Data Source JSON Config Strings

<table>
<colgroup>
  <col style="width:125px">
  <col style="width:195px">
  <col>
</colgroup>
<thead><tr>
  <th><code>data_source</code></th><th>Config Argument</th><th>JSON Fields</th>
</tr></thead>
<tbody>
<tr><td><code>filesystem</code></td><td><code>paths</code> (not JSON)</td><td>File/directory path(s) — no config string needed</td></tr>
<tr><td><code>alfresco</code></td><td><code>alfresco_config</code></td><td><code>{"base_url": "...", "username": "...", "password": "...", "paths": [...], "nodeDetails": {...}}</code></td></tr>
<tr><td><code>cmis</code></td><td><code>cmis_config</code></td><td><code>{"cmis_url": "...", "username": "...", "password": "...", "paths": [...]}</code></td></tr>
<tr><td><code>s3</code></td><td><code>s3_config</code></td><td><code>{"bucket": "...", "aws_access_key_id": "...", "aws_secret_access_key": "...", "region": "..."}</code></td></tr>
<tr><td><code>azure_blob</code></td><td><code>azure_blob_config</code></td><td><code>{"connection_string": "...", "container_name": "..."}</code></td></tr>
<tr><td><code>gcs</code></td><td><code>gcs_config</code></td><td><code>{"bucket_name": "...", "credentials_path": "..."}</code></td></tr>
<tr><td><code>onedrive</code></td><td><code>onedrive_config</code></td><td><code>{"client_id": "...", "client_secret": "...", "tenant_id": "..."}</code></td></tr>
<tr><td><code>google_drive</code></td><td><code>google_drive_config</code></td><td><code>{"credentials_path": "...", "folder_id": "..."}</code></td></tr>
<tr><td><code>sharepoint</code></td><td><code>sharepoint_config</code></td><td><code>{"client_id": "...", "client_secret": "...", "tenant_id": "...", "site_url": "..."}</code></td></tr>
<tr><td><code>box</code></td><td><code>box_config</code></td><td><code>{"client_id": "...", "client_secret": "...", "folder_id": "..."}</code></td></tr>
<tr><td><code>web</code></td><td><code>web_config</code></td><td><code>{"urls": ["https://...", "https://..."]}</code></td></tr>
<tr><td><code>wikipedia</code></td><td><code>wikipedia_config</code></td><td><code>{"titles": ["Article Title", "..."]}</code></td></tr>
<tr><td><code>youtube</code></td><td><code>youtube_config</code></td><td><code>{"urls": ["https://youtube.com/watch?v=...", "..."]}</code></td></tr>
</tbody>
</table>

## `skip_graph` — All Ingest Tools

`skip_graph=True` is available on all three ingest tools:

```python
ingest_documents(data_source="filesystem", paths=["/docs"], skip_graph=True)
ingest_text(content="...", source_name="doc.txt", skip_graph=True)
test_with_sample(skip_graph=True)
```

When set, the document is chunked, embedded, and stored in vector + search indexes but KG extraction and property graph / RDF store writes are skipped. Useful for fast bulk ingest when graph queries are not needed.
