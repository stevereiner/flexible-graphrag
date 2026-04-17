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

### Docker `docker.env`

```bash
cd docker

# Linux/macOS
cp docker-env-sample.txt docker.env

# Windows
copy docker-env-sample.txt docker.env
```

Edit `docker.env` for Docker-specific network overrides (service hostnames, ports).

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

Follow [Getting Started — Backend](GETTING-STARTED.md#python-backend-installation) and [Frontend Setup](GETTING-STARTED.md#frontend-setup-standalone).

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
| `includes/milvus.yaml` | Milvus | http://localhost:9091 |
| `includes/weaviate.yaml` | Weaviate | http://localhost:8080 |
| `includes/chroma.yaml` | Chroma | — |
| `includes/postgres-pgvector.yaml` | PostgreSQL pgvector | http://localhost:5050 (pgAdmin) |
| `includes/lancedb.yaml` | LanceDB | — |

### Property Graph Databases

| Include File | Database | Dashboard |
|---|---|---|
| `includes/neo4j.yaml` | Neo4j | http://localhost:7474 |
| `includes/arcadedb.yaml` | ArcadeDB | http://localhost:2480 |
| `includes/falkordb.yaml` | FalkorDB | http://localhost:3000 |
| `includes/nebula.yaml` | NebulaGraph | http://localhost:7001 |

### Search Databases

| Include File | Database | Dashboard |
|---|---|---|
| `includes/elasticsearch-dev.yaml` | Elasticsearch | — |
| `includes/kibana-simple.yaml` | Kibana | http://localhost:5601 |
| `includes/opensearch.yaml` | OpenSearch | http://localhost:9201 |

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
