# Property Graph Database Configuration

## Database Selection

Set `PG_GRAPH_DB` to select the property graph backend. Use `{TYPE}_GRAPH_DB_CONFIG` (JSON blob) for per-store connection settings — this takes precedence over the generic `GRAPH_DB_CONFIG` fallback.

```env
PG_GRAPH_DB=neo4j              # See supported values below
NEO4J_GRAPH_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "password"}
```

**Framework backend** is selected separately:

```env
GRAPH_BACKEND=llamaindex       # llamaindex (default) | langchain
KG_EXTRACTOR_BACKEND=llamaindex  # llamaindex | langchain
```

LangChain-only stores (`arangodb`, `apache_age`, `hugegraph`, `surrealdb`, `tigergraph`, `cosmos_gremlin`) **automatically set** `GRAPH_BACKEND=langchain` — no explicit override needed. `spanner` uses LlamaIndex only (`llama-index-spanner`; `langchain-google-spanner` requires `langchain-core<1.0` and is incompatible).

---

## Property Graph Databases Supported on Both LlamaIndex and LangChain

These stores work with `GRAPH_BACKEND=llamaindex` (default) or `GRAPH_BACKEND=langchain`.

### Neo4j

Primary knowledge graph storage with Cypher querying.

- Dashboard: Neo4j Browser (http://localhost:7474)

```env
PG_GRAPH_DB=neo4j
NEO4J_GRAPH_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "password"}
```

### ArcadeDB

Multi-model database supporting graph, document, key-value, and search.

- Dashboard: ArcadeDB Studio (http://localhost:2480)

```env
PG_GRAPH_DB=arcadedb
ARCADEDB_GRAPH_DB_CONFIG={"host": "localhost", "port": 2480, "username": "root", "password": "password", "database": "flexible_graphrag"}
```

Embedded mode (in-process):
```env
ARCADEDB_MODE=embedded
ARCADEDB_DB_PATH=./arcadedb_data
ARCADEDB_EMBEDDED_SERVER=false
```

### FalkorDB

Super fast graph database using GraphBLAS.

- Dashboard: FalkorDB Browser (http://localhost:3001)

```env
PG_GRAPH_DB=falkordb
FALKORDB_GRAPH_DB_CONFIG={"url": "falkor://localhost:6379", "database": "falkor"}
```

### Ladybug

Embedded property graph database (Cypher, single `.lbug` file) with optional HNSW vector index.

- Dashboard: Ladybug Explorer (http://localhost:7003, optional Docker)

```env
PG_GRAPH_DB=ladybug
LADYBUG_GRAPH_DB_CONFIG={"db_dir": "./ladybug", "db_file": "database.lbug", "use_vector_index": true}
```

### Memgraph

Real-time graph database with native streaming and graph algorithm support.

- Dashboard: Memgraph Lab (http://localhost:3002)

```env
PG_GRAPH_DB=memgraph
MEMGRAPH_GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", "username": "", "password": ""}
```

### NebulaGraph

Distributed graph database for large-scale data.

- Dashboard: NebulaGraph Studio (http://localhost:7001)

```env
PG_GRAPH_DB=nebula
NEBULA_GRAPH_DB_CONFIG={"space": "flexible_graphrag", "host": "localhost", "port": 9669, "username": "root", "password": "nebula"}
```

### Amazon Neptune (Property Graph)

Fully managed AWS graph service — property graph mode.

- Dashboard: Graph-Explorer (http://localhost:3007) or Neptune Workbench (AWS Console)

```env
PG_GRAPH_DB=neptune
NEPTUNE_GRAPH_DB_CONFIG={"host": "your-cluster.region.neptune.amazonaws.com", "port": 8182}
```

### Amazon Neptune Analytics

Serverless graph analytics with openCypher.

```env
PG_GRAPH_DB=neptune_analytics
NEPTUNE_ANALYTICS_GRAPH_DB_CONFIG={"graph_identifier": "g-xxxxx", "region": "us-east-1"}
```

---

## Property Graph Databases Supported Only with LangChain

These 6 stores only work with `GRAPH_BACKEND=langchain` (auto-selected when `PG_GRAPH_DB` is set to one of these). They support ingestion via `add_graph_documents()` and NL→Cypher/AQL/GSQL/SurrealQL retrieval via a `TextToGraphQueryRetriever`.

### ArangoDB

Multi-model database with AQL graph traversal.

- Dashboard: ArangoDB Web UI (http://localhost:8529)
- Docker: `docker compose -f docker-compose.yaml -f includes/arangodb.yaml -p flexible-graphrag up -d arangodb`

```env
PG_GRAPH_DB=arangodb
ARANGODB_GRAPH_DB_CONFIG={"url": "http://localhost:8529", "database": "flexible_graphrag", "username": "root", "password": "password"}
```

### Apache AGE

PostgreSQL extension adding Cypher graph querying to Postgres.

- Port: 5434 (separate from the pgvector Postgres at 5433)
- Docker: `docker compose -f docker-compose.yaml -f includes/apache-age.yaml -p flexible-graphrag build apache-age && docker compose ... up -d apache-age`

```env
PG_GRAPH_DB=apache_age
APACHE_AGE_GRAPH_DB_CONFIG={"host": "localhost", "port": 5434, "database": "flexible_graphrag_age", "username": "flexible_graphrag", "password": "password", "graph_name": "knowledge_graph"}
```

### Azure Cosmos DB for Gremlin / TinkerPop

Gremlin-compatible graph traversal — works with both local Apache TinkerPop Gremlin Server and cloud Azure Cosmos DB for Gremlin.

- Local Docker: `docker compose ... -f includes/gremlin-server.yaml up -d gremlin-server` (port 8182)
- Cloud: Azure Cosmos DB for Gremlin — use `wss://` endpoint with primary key from Azure portal

Local (TinkerPop Gremlin Server):
```env
PG_GRAPH_DB=cosmos_gremlin
COSMOS_GREMLIN_GRAPH_DB_CONFIG={"url": "ws://localhost:8182/gremlin", "username": "/", "password": ""}
```

Cloud (Azure Cosmos DB for Gremlin):
```env
PG_GRAPH_DB=cosmos_gremlin
COSMOS_GREMLIN_GRAPH_DB_CONFIG={"url": "wss://my-cosmos.gremlin.cosmos.azure.com:443/", "username": "/dbs/graphdb/colls/knowledge_graph", "password": "your_primary_key==", "partition_key_property": "partitionKey", "partition_key_value": "graph"}
```

The `username` format for Cosmos DB is `/dbs/<database-name>/colls/<graph-container-name>`. The password is the primary key from Azure portal → your Cosmos DB account → Keys.

`partition_key_property` must match the partition key path set on your Cosmos DB graph container (e.g. container created with `/partitionKey` → use `"partitionKey"`). Default is `"partitionKey"`, auto-applied for any `cosmos.azure.com` URL.

`partition_key_value` is a fixed string written on every vertex. Using a fixed value keeps all graph data in one logical partition so traversals never cross partition boundaries. Do NOT use the entity type — that scatters vertices across partitions, forcing expensive cross-partition queries for most graph traversals. Default is `"graph"`.

### Apache HugeGraph

Distributed graph database with openCypher and Gremlin support.

- REST API: http://localhost:8082
- Hubble UI: http://localhost:8085
- Docker: `docker compose ... -f includes/hugegraph.yaml up -d hugegraph`
- Requires: `uv pip install --override extras-overrides.txt -e ".[langchain,langchain-extras]"` (includes `hugegraph-python>=1.5.0`)

```env
PG_GRAPH_DB=hugegraph
HUGEGRAPH_GRAPH_DB_CONFIG={"host": "localhost", "port": 8082, "database": "hugegraph", "username": "admin", "password": "password"}
```

### SurrealDB

Multi-model database with SurrealQL graph querying.

- REST/WebSocket: http://localhost:8010
- Surrealist UI: http://localhost:8011
- Docker: `docker compose ... -f includes/surrealdb.yaml up -d surrealdb`
- Requires: `uv pip install -e ".[surrealdb-extras]"` (isolated group — do NOT mix with `langchain-extras`)

```env
PG_GRAPH_DB=surrealdb
SURREALDB_GRAPH_DB_CONFIG={"url": "ws://localhost:8010/rpc", "namespace": "test", "database": "flexible_graphrag", "username": "root", "password": "root"}
```

### TigerGraph

Enterprise-grade distributed graph database with GSQL.

- RESTPP: http://localhost:9002
- GraphStudio UI: http://localhost:14240
- Docker: `docker compose ... -f includes/tigergraph.yaml up -d tigergraph`
- Requires: `uv pip install -e ".[langchain,langchain-extras]"` (includes `pyTigerGraph>=1.0.0`)

```env
PG_GRAPH_DB=tigergraph
TIGERGRAPH_GRAPH_DB_CONFIG={"host": "http://localhost", "port": 14240, "restpp_port": 9002, "database": "MyGraph", "username": "tigergraph", "password": "tigergraph"}
```

---

## Property Graph Databases Supported Only with LlamaIndex

These stores only work with `GRAPH_BACKEND=llamaindex` (default). The LangChain equivalents are either incompatible with current dependencies or not yet implemented.

### Google Cloud Spanner (Graph)

Fully managed relational + graph database with openCypher and Graph Query Language (GQL) support.

- **Cloud only** — requires a GCP project, Spanner instance, and database with Spanner Graph enabled
- **No emulator support**: the Google Cloud Spanner emulator supports SQL only, not Spanner Graph — use a real GCP Spanner instance
- Requires: `uv pip install -e ".[spanner-extras]" && uv pip uninstall llama-index` — `llama-index-spanner` pulls in the `llama-index` meta-package as a dependency; uninstall it immediately after to avoid version conflicts (the meta-package pins versions of `llama-index-*` component packages that can clash with the versions already required by this project)
- LC is not supported: `langchain-google-spanner` requires `langchain-core<1.0` (incompatible with `langchain>=1.0`). When a compatible release of `langchain-google-spanner` is published, Spanner will be promoted to "both LI+LC".

Authentication: set `credentials_file` for a service-account JSON key file, or rely on Application Default Credentials (`GOOGLE_APPLICATION_CREDENTIALS` env var or `gcloud auth application-default login`).

```env
PG_GRAPH_DB=spanner
SPANNER_GRAPH_DB_CONFIG={"project_id": "my-gcp-project", "instance_id": "my-spanner-instance", "database_id": "my-database", "graph_name": "knowledge_graph"}

# With service-account key file:
SPANNER_GRAPH_DB_CONFIG={"project_id": "my-gcp-project", "instance_id": "my-spanner-instance", "database_id": "my-database", "graph_name": "knowledge_graph", "credentials_file": "/path/to/sa-key.json"}
```

---

## Framework Configuration (Graph-Specific)

| <div style="min-width:230px">Variable</div> | Default | Description |
|---|---|---|
| `GRAPH_BACKEND` | `llamaindex` | `llamaindex` or `langchain` — ingestion + retrieval backend |
| `KG_EXTRACTOR_BACKEND` | `llamaindex` | `llamaindex` (`SchemaLLMPathExtractor`) or `langchain` (`LLMGraphTransformer`) |
| `USE_LC_TEXT_TO_GRAPH` | `false` | **Neo4j + `LANGCHAIN_PG_VECTOR_SEARCH=true` only**: add `TextToGraphQueryRetriever` back alongside vector+neighborhood. All other LC stores auto-enable text-to-graph (it is their only graph retrieval path). For Neo4j with `LANGCHAIN_PG_VECTOR_SEARCH=false` (default), text-to-graph is also auto-enabled. |
| `USE_PG_NEIGHBORHOOD` | `true` | Enable `GraphNeighborhoodRetriever` (k-hop graph walk from seed entities; **Neo4j only**; auto-enabled when `LANGCHAIN_PG_VECTOR_SEARCH=true`) |
| `LANGCHAIN_PG_VECTOR_SEARCH` | `false` | Enable `GraphEntityVectorRetriever` (Neo4j only; entity-level vector seeding; auto-enables `USE_PG_NEIGHBORHOOD`; suppresses text-to-graph unless `USE_LC_TEXT_TO_GRAPH=true`) |
| `ENABLE_KNOWLEDGE_GRAPH` | `true` | Set `false` to disable KG extraction globally (vector-only RAG) |

## Skipping or Disabling Graph Extraction

Both PG and RDF graph writes can be bypassed while leaving previously ingested graph data intact for search and Q&A.

**Global — `ENABLE_KNOWLEDGE_GRAPH=false`**: disables KG extraction and all graph writes on every ingest call. Previously ingested graph data is preserved and still used for hybrid search and AI Q&A.

```env
ENABLE_KNOWLEDGE_GRAPH=false
```

**Vector-only RAG** (no graph store at all):

```env
PG_GRAPH_DB=none
ENABLE_KNOWLEDGE_GRAPH=false
```

**Per-ingest — `skip_graph=true`**: skips KG extraction for one request only. Vector and full-text stores are still updated. Available from the UI ("Skip graph extraction" checkbox), REST API (`POST /api/ingest`, `/api/ingest-text`, `/api/test-sample`), MCP tools (`ingest_documents`, `ingest_text`, `test_with_sample`), and the Python API (`backend.ingest_documents(skip_graph=True)`, `backend.ingest_text(skip_graph=True)`). Also persisted per-datasource in the incremental sync config.

---

## Further Reading

- [LangChain Architecture](../ADVANCED/LANGCHAIN/LANGCHAIN-GRAPH-INTEGRATION.md) — full dual-framework architecture, retriever layer, source labels
- [Neo4j Guide](../DATABASES/GRAPH-DATABASES/README-neo4j.md)
- [Knowledge Graph Extractors](../DATABASES/GRAPH-DATABASES/KNOWLEDGE-GRAPH-EXTRACTORS.md)
- [Port Mappings](../ADVANCED/PORT-MAPPINGS.md)
