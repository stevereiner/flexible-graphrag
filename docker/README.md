# Docker Compose Configuration

This directory contains the Docker Compose configuration for Flexible GraphRAG.

## Main Compose File

| File | Purpose | Usage |
|------|---------|-------|
| `docker-compose.yaml` | **Modular deployment** with configurable services | `docker-compose -f docker/docker-compose.yaml -p flexible-graphrag up -d` |

## Modular Service Definitions

The `includes/` directory contains individual service definitions:

| Service | File | Description |
|---------|------|-------------|
| **Databases** |
| Neo4j | `includes/neo4j.yaml` | Graph database with APOC & GDS |
| Kuzu | `includes/kuzu.yaml` | Embedded graph DB + web explorer |
| FalkorDB | `includes/falkordb.yaml` | Production graph DB with browser (ports 6379, 3001) |
| MemGraph | `includes/memgraph.yaml` | Real-time graph database with Lab dashboard (ports 7688, 3002) |
| ArcadeDB | `includes/arcadedb.yaml` | Multi-model database with graph capabilities (ports 2480, 2424) |
| Qdrant | `includes/qdrant.yaml` | Vector database |
| Elasticsearch | `includes/elasticsearch.yaml` | Search engine |
| Kibana | `includes/kibana.yaml` | Elasticsearch dashboard & visualization |
| OpenSearch | `includes/opensearch.yaml` | Alternative search + dashboards |
| **Content Management** |
| Alfresco | `includes/alfresco.yaml` | Full Alfresco Community stack |
| **Application** |
| App Stack | `includes/app-stack.yaml` | Backend + Angular/React/Vue UIs |
| Proxy | `includes/proxy.yaml` | NGINX reverse proxy |

## Quick Start

**Note**: All docker-compose commands use `-p flexible-graphrag` to set a consistent project name, which helps organize containers and prevents conflicts with other Docker projects.

1. **Configure environment**:
   ```bash
   # From project root
   cp flexible-graphrag/env-sample.txt flexible-graphrag/.env
   # Edit .env with your database and API settings
   ```

2. **Deploy**:
   ```bash
   # Deploy with all configured services
   docker-compose -f docker/docker-compose.yaml -p flexible-graphrag up -d
   ```

3. **Environment variables and volumes**:
   ```bash
   # Create required directories for data persistence
   mkdir -p docker-data/{neo4j,kuzu,qdrant,elasticsearch,opensearch,alfresco}
   
   # Set environment variables if needed
   export COMPOSE_PROJECT_NAME=flexible-graphrag
   ```

4. **Stop deployment**:
   ```bash
   docker-compose -f docker/docker-compose.yaml -p flexible-graphrag down
   ```

## Customization

The single `docker-compose.yaml` file uses modular includes, making it easy to enable or disable services as needed.

### Disable Services
Edit `docker-compose.yaml` and comment out services you don't need:

```yaml
include:
  - includes/neo4j.yaml          # ✅ Keep this
  # - includes/kuzu.yaml         # ❌ Disable Kuzu
  - includes/qdrant.yaml         # ✅ Keep this
  # - includes/elasticsearch.yaml # ❌ Disable Elasticsearch
```

### Override Settings
Copy and customize:
```bash
cp ../docker-compose.override.yaml.example docker-compose.override.yaml
# Edit with your custom settings
```

## Service URLs

After deployment with full stack (docker-compose.yaml), access services at:

- **Angular UI**: http://localhost:8070/ui/angular/
- **React UI**: http://localhost:8070/ui/react/
- **Vue UI**: http://localhost:8070/ui/vue/
- **Backend API**: http://localhost:8070/api/
- **Neo4j Browser**: http://localhost:7474/
- **Kuzu Explorer**: http://localhost:8002/
- **FalkorDB Browser**: http://localhost:3001/
- **MemGraph Lab**: http://localhost:3002/
- **ArcadeDB Studio**: http://localhost:2480/
- **Qdrant Dashboard**: http://localhost:6333/dashboard
- **Elasticsearch**: http://localhost:9200/
- **Kibana Dashboard**: http://localhost:5601/
- **OpenSearch**: http://localhost:9201/
- **OpenSearch Dashboards**: http://localhost:5602/
- **Alfresco Share**: http://localhost:8080/share/

## OpenSearch Pipeline Setup

For advanced OpenSearch hybrid search, configure the search pipeline:

```bash
# Using the included Python script
cd scripts
python create_opensearch_pipeline.py

# Or manually via curl:
curl -X PUT "localhost:9201/_search/pipeline/hybrid-search-pipeline" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Hybrid search pipeline for vector and text search",
    "processors": [
      {
        "normalization-processor": {
          "normalization": {
            "technique": "min_max"
          },
          "combination": {
            "technique": "harmonic_mean",
            "parameters": {
              "weights": [0.3, 0.7]
            }
          }
        }
      }
    ]
  }'
```

The pipeline enables native OpenSearch hybrid search with proper score fusion between vector and text results.

## Data Persistence

All data is stored in Docker volumes that survive container restarts:
- `neo4j_data`, `neo4j_logs`
- `kuzu_data`
- `qdrant_data`
- `elasticsearch_data`, `opensearch_data`
- `alfresco_data`, `alfresco_db_data`
