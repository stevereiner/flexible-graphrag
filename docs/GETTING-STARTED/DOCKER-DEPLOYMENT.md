# Docker Deployment

Docker deployment supports multiple scenarios. All scenarios require environment file setup first.

## Environment File Setup (Required for All Scenarios)

### Backend `.env`

```bash
cd flexible-graphrag

# Linux/macOS
cp env-sample.txt .env

# Windows
copy env-sample.txt .env
```

Edit `.env` with your LLM API keys, database credentials, and feature flags.
See [Environment Configuration](ENVIRONMENT-CONFIGURATION.md) for all options.

### Docker `docker/.env`

```bash
cd docker

# Linux/macOS
cp docker-env-sample.txt .env

# Windows
copy docker-env-sample.txt .env
```

Edit `docker/.env` for Docker-specific network overrides (service hostnames, ports).

### Why it is named `.env` and not `docker.env`

Docker Compose auto-loads any file literally named `.env` sitting next to
`docker-compose.yaml`. So `docker/.env` does double duty: the container overrides above, **and**
the `${...}` placeholders Compose resolves inside `docker/includes/*.yaml` —
`ALFRESCO_SEARCH_HOST`, `VLLM_MODEL`, `FLEXIBLE_GRAPHRAG_VERSION`. That is why every include is
a plain one-liner with no extra syntax.

`flexible-graphrag/.env` is **not** consulted for those placeholders — only `docker/.env` and
the shell. A handful of variables are read by both Compose and the backend app; if the backend
runs on the host (Scenario A) set those in both files. See
[docker/DOCKER-ENV-SETUP.md](https://github.com/stevereiner/flexible-graphrag/blob/main/docker/DOCKER-ENV-SETUP.md)
for the full list and the precedence rules.

---

## Scenario A — Databases in Docker, App Standalone (Recommended for Development)

Run databases in containers; run the backend and UI locally for easy debugging and hot-reload.

### Configure `docker-compose.yaml`

Keep these **uncommented** (default):

```yaml
- includes/neo4j.yaml
- includes/qdrant.yaml
- includes/elasticsearch-dev.yaml
- includes/kibana-simple.yaml
```

Keep these **commented out**:

```yaml
# - includes/app-stack.yaml    # Must be commented for Scenario A
# - includes/proxy.yaml        # Must be commented for Scenario A
```

### Start Databases

```bash
# From the docker directory
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
```

### Run Backend and UI Locally

Follow [Getting Started — Backend](PYTHON-BACKEND.md) and [Frontend Setup](FRONTEND-SETUP.md#standalone-installation).

---

## Scenario B — Full Stack in Docker

Everything runs in containers including the backend and UI, served via NGINX.

### Configure `docker-compose.yaml`

Uncomment all of these:

```yaml
- includes/neo4j.yaml
- includes/qdrant.yaml
- includes/elasticsearch-dev.yaml
- includes/kibana-simple.yaml
- includes/app-stack.yaml    # Backend + UI
- includes/proxy.yaml        # NGINX reverse proxy
```

### Build and Start

```bash
cd docker
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d --build
```

### Access Points

| Service | URL |
|---|---|
| Flexible GraphRAG UI | http://localhost (via NGINX) |
| Backend API | http://localhost/api |
| Neo4j Browser | http://localhost:7474 |
| Kibana | http://localhost:5601 |

---

## Modular Database Selection

Comment or uncomment includes in `docker-compose.yaml` to choose your stack:

### Vector Databases

| Include File | Database | Dashboard |
|---|---|---|
| `includes/qdrant.yaml` | Qdrant | http://localhost:6333/dashboard |
| `includes/elasticsearch-dev.yaml` | Elasticsearch (also as vector) | — (Kibana: http://localhost:5601) |
| `includes/opensearch.yaml` | OpenSearch (also as vector) | `includes/opensearch-dashboards.yaml` → http://localhost:5602 |
| `includes/milvus.yaml` | Milvus | http://localhost:9091 |
| `includes/weaviate.yaml` | Weaviate | http://localhost:8080 |
| `includes/chroma.yaml` | Chroma | — |
| `includes/postgres-pgvector.yaml` | PostgreSQL pgvector | http://localhost:5050 (pgAdmin) |
| `includes/lancedb.yaml` | LanceDB | — |
| `includes/neo4j.yaml` | Neo4j (also as vector) | http://localhost:7474 |

Pinecone is a cloud service — no Docker include required.

### Property Graph Databases

**LlamaIndex + LangChain (both frameworks):**

| Include File | Database | Dashboard |
|---|---|---|
| `includes/neo4j.yaml` | Neo4j | http://localhost:7474 |
| `includes/arcadedb.yaml` | ArcadeDB | http://localhost:2480 |
| `includes/falkordb.yaml` | FalkorDB | http://localhost:3001 |
| `includes/memgraph.yaml` | Memgraph | http://localhost:3002 |
| `includes/nebula.yaml` | NebulaGraph | http://localhost:7001 |
| `includes/ladybug-explorer.yaml` | Ladybug Explorer (UI only) | http://localhost:7003 |

Amazon Neptune and Neptune Analytics are cloud services — no Docker include required.

**LangChain-only property graph databases:**

| Include File | Database | Dashboard |
|---|---|---|
| `includes/arangodb.yaml` | ArangoDB | http://localhost:8529 |
| `includes/apache-age.yaml` | Apache AGE (PostgreSQL + Cypher) | — |
| `includes/hugegraph.yaml` | Apache HugeGraph | http://localhost:8085 (Hubble) |
| `includes/surrealdb.yaml` | SurrealDB + Surrealist UI | http://localhost:8011 |
| `includes/tigergraph.yaml` | TigerGraph | http://localhost:14240 (GraphStudio) |
| `includes/gremlin-server.yaml` | Gremlin Server (Cosmos Gremlin local) | — |

### Search Databases

| Include File | Database | Dashboard |
|---|---|---|
| `includes/elasticsearch-dev.yaml` | Elasticsearch | — |
| `includes/kibana-simple.yaml` | Kibana | http://localhost:5601 |
| `includes/opensearch.yaml` | OpenSearch | `includes/opensearch-dashboards.yaml` → http://localhost:5602 |

### Content Management

| Include File | Service | Dashboard |
|---|---|---|
| `includes/alfresco.yaml` | Alfresco Community 26.2 (repo, Share, ACA, Control Center, ActiveMQ, transform) | http://localhost:8080 |
| `includes/alfresco-elasticsearch.yaml` | Elasticsearch for Alfresco (9202) — the default | `includes/alfresco-kibana.yaml` → http://localhost:5603 |
| `includes/alfresco-opensearch.yaml` | OpenSearch for Alfresco (9203) — alternative; also set `ALFRESCO_SEARCH_HOST=alfresco-opensearch` | `includes/alfresco-opensearch-dashboards.yaml` → http://localhost:5604 |
| `includes/keycloak.yaml` | Keycloak OIDC IdP for Alfresco OAuth2 | http://localhost:8091 |

ACS 26.2 dropped Solr; the repository indexes into Elasticsearch or OpenSearch via a
`batch-indexing` service. Enable ONE of the two includes above to run an engine dedicated to
Alfresco, or neither and set
`ALFRESCO_SEARCH_HOST=elasticsearch` (or `=opensearch`) in `.env` to index into the engine this
project already runs, sharing its Kibana / OpenSearch Dashboards as well.

### RDF Triple Stores

```yaml
# Uncomment in docker-compose.yaml:
# - includes/jena-fuseki.yaml        # Fuseki at http://localhost:3030
# - includes/ontotext-graphdb.yaml   # GraphDB at http://localhost:7200
# - includes/oxigraph.yaml           # Oxigraph at http://localhost:7878
```

### Observability

```yaml
# - includes/observability.yaml   # Prometheus + Jaeger + Grafana
```

See [Observability](../DEVELOPER/OBSERVABILITY/OBSERVABILITY.md) for setup details.

---

## Stopping and Cleanup

```bash
# Stop all containers (keep volumes)
docker-compose -f docker-compose.yaml -p flexible-graphrag down

# Stop and remove volumes (wipes all data)
docker-compose -f docker-compose.yaml -p flexible-graphrag down -v
```

## Resource Configuration

See [Docker Resource Configuration](../ADVANCED/DOCKER-RESOURCE-CONFIGURATION.md) for WSL2 memory settings, macOS resource limits, and production sizing guidance.

## Default Credentials

See [Default Usernames & Passwords](../ADVANCED/DEFAULT-USERNAMES-PASSWORDS.md) for all service credentials.
