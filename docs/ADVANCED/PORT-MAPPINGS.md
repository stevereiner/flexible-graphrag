# Port Mappings for Flexible GraphRAG Services

This document provides a comprehensive overview of all port assignments to avoid conflicts between services.

## Port Conflict Resolution

The following port conflicts were identified and resolved for new vector databases:

| **Original Port** | **Conflicted With** | **New Port** | **Service** | **Reason** |
|-------------------|---------------------|--------------|-------------|------------|
| 8000 | Backend API | **8001** | Chroma | Moved to 800x range for consistency |
| 3000 | Vue Frontend | **3003** | Milvus Attu | Avoid conflict with Vue UI |
| 8080 | Alfresco Proxy | **8086** | Weaviate | Moved off 8080 (Alfresco Traefik), then off 8081 (Nuxeo) |
| 8080 | Alfresco Proxy | **8081** | Nuxeo | Nuxeo's own deployment default; kept so its docs match |
| 5432 | Alfresco PostgreSQL | **5433** | PostgreSQL+pgvector | Avoid conflict with Alfresco database |
| 7001 | - | **7001** | NebulaGraph Studio | Default studio dashboard port |

## Complete Port Mapping

### Core Application Services
| **Service** | **Port** | **Purpose** | **URL** |
|-------------|----------|-------------|---------|
| Backend API | 8000 | FastAPI backend | http://localhost:8000 |
| **Docs Dev Server** | **8008** | **Zensical local preview** | **http://localhost:8008** |
| **vLLM** | **8002** | **OpenAI-compatible inference server** | **http://localhost:8002/v1** |
| **LiteLLM Proxy** | **4000** | **OpenAI-compatible proxy (100+ providers)** | **http://localhost:4000** |
| Vue Frontend | 3000 | Vue.js UI | http://localhost:3000 |
| Angular Frontend | 4200 | Angular UI | http://localhost:4200 |
| React Frontend | 5174 | React UI | http://localhost:5174 |
| Nginx Proxy | 8070 | Reverse proxy for all UIs | http://localhost:8070 |

### Observability Services
| **Service** | **Port(s)** | **Purpose** | **Dashboard URL** |
|-------------|-------------|-------------|-------------------|
| **OTLP Collector** | **4317, 4318, 8888, 8889** | Receives traces/metrics (gRPC, HTTP, Prometheus metrics) | - |
| **Jaeger** | **16686, 14250** | Distributed tracing UI | http://localhost:16686 |
| **Prometheus** | **9090** | Metrics collection | http://localhost:9090 |
| **Grafana** | **3009** | Dashboards and visualization | http://localhost:3009 |

### Graph Databases
| **Service** | **Port(s)** | **Purpose** | **Dashboard URL** |
|-------------|-------------|-------------|-------------------|
| Neo4j | 7474, 7687 | Graph database | http://localhost:7474 |
| Ladybug Explorer | 7003 | Ladybug web UI (optional compose include) | http://localhost:7003 |
| FalkorDB | 6379, 3001 | Graph database + browser | http://localhost:3001 |
| ArcadeDB | 2480, 2424, **7689** | Graph database + studio + Bolt (LC adapter) | http://localhost:2480 |
| MemGraph | 7688, 3002 | Graph database + lab | http://localhost:3002 |
| **NebulaGraph** | **9669, 7001** | **Distributed graph database + studio** | **http://localhost:7001** |
| **Neptune Graph Explorer** | **3007** | Neptune dashboard | http://localhost:3007 |
| **ArangoDB** | **8529** | **LangChain-only PG; web UI at same port** | **http://localhost:8529** |
| **Apache AGE** | **5434** | **LangChain-only PG (PostgreSQL+Cypher)** | psql / pgAdmin |
| **HugeGraph** | **8082, 8085** | **LangChain-only PG + Hubble UI** | **http://localhost:8085** |
| **SurrealDB** | **8010, 8011** | **LangChain-only multi-model PG + Surrealist UI** | http://localhost:8011 |
| **TigerGraph** | **9002, 14240** | **LangChain-only analytics PG; RESTPP API + GraphStudio UI** | **http://localhost:14240** |
| **Spanner Emulator** | **9010, 9020** | **LangChain-only; gRPC + HTTP** | REST at http://localhost:9020 |
| **Gremlin Server** | **8182** | **TinkerPop Gremlin (Cosmos Gremlin local sub)** | ws://localhost:8182/gremlin |

### Vector Databases
| **Service** | **Port(s)** | **Purpose** | **Dashboard URL** |
|-------------|-------------|-------------|-------------------|
| Qdrant | 6333, 6334 | Vector database | http://localhost:6333/dashboard |
| **Chroma** | **8001** | Vector database | http://localhost:8001 |
| **Milvus** | **19530, 3003, 9000, 9001** | Vector database + Attu + MinIO | http://localhost:3003 |
| **Weaviate** | **8086** | Vector search engine | http://localhost:8086/console |
| **PostgreSQL+pgvector** | **5433, 5050** | Vector database + pgAdmin | http://localhost:5050 |

### Search Databases
| **Service** | **Port(s)** | **Purpose** | **Dashboard URL** |
|-------------|-------------|-------------|-------------------|
| Elasticsearch | 9200 (9300 internal) | Search engine | - |
| Kibana | 5601 | Elasticsearch dashboard | http://localhost:5601 |
| OpenSearch | 9201 (9301 internal) | Search engine | - |
| OpenSearch Dashboards | 5602 | OpenSearch dashboard | http://localhost:5602 |

**Transport ports (9300/9301) note**: The inter-node transport ports are **not exposed to the host** — these are single-node deployments with no peer nodes, and the app connects only over HTTP (9200/9201). On Windows this also **avoids a hard failure**: 9300 and 9301 fall inside a Hyper-V/WinNAT-reserved range (commonly `9248-9347`), so binding them yields `bind: An attempt was made to access a socket in a way forbidden by its access permissions`. The container still binds 9300/9301 internally for Elasticsearch/OpenSearch's own use. Alfresco's own search engine (9202/9203, see below) follows the same rule. Check current reservations with `netsh interface ipv4 show excludedportrange protocol=tcp`.

### Content Management (Alfresco Community)
| **Service** | **Port(s)** | **Purpose** | **Dashboard URL** |
|-------------|-------------|-------------|-------------------|
| **Alfresco Proxy (Traefik)** | **8080, 8888** | **Main proxy + dashboard** | **http://localhost:8080** |
| Transform Core AIO | 8090 | Document transformation | http://localhost:8090/ready |
| Alfresco PostgreSQL | 5432 | Alfresco database | - |
| Alfresco Elasticsearch | 9202 | Search index — replaced Solr in ACS 26.2 (`includes/alfresco-elasticsearch.yaml`, the default) | - |
| Alfresco Kibana *(optional, off by default)* | 5603 | Dashboard over that index | http://localhost:5603 |
| Alfresco OpenSearch | 9203 | Search index — alternative to the above (`includes/alfresco-opensearch.yaml`) | - |
| Alfresco OpenSearch Dashboards *(optional, off by default)* | 5604 | Dashboard over that index | http://localhost:5604 |

**Sharing the search engine**: 9202/9203 and 5603/5604 only apply when one of the `alfresco-*search` includes gives Alfresco its own engine. Leave both out and set `ALFRESCO_SEARCH_HOST=elasticsearch` (9200) or `=opensearch` (9201) in `docker/.env`, and Alfresco indexes into the engine the rest of Flexible GraphRAG uses — no extra ports, and the existing Kibana (5601) / OpenSearch Dashboards (5602) covers the Alfresco index too.
| **Alfresco ActiveMQ Web Console** | **8161** | Message queue web console | http://localhost:8161 |
| **Alfresco ActiveMQ STOMP** | **8613** (or 61613) | Real-time event monitoring | - |
| **Alfresco ActiveMQ OpenWire** | **8616** (or 61616) | Internal messaging protocol | - |

**ActiveMQ Port Notes**:
- **Standard ports**: 61613 (STOMP), 61616 (OpenWire) - Use these on Linux/macOS or non-Windows systems
- **Windows alternative ports**: 8613 (STOMP), 8616 (OpenWire) - Use these on Windows if you encounter port binding errors
- **Why the alternatives?**: Windows reserves ports 49152-65535 as "dynamic/ephemeral ports" for outgoing connections. After Windows updates or Docker Desktop upgrades, these ports can conflict with Windows' dynamic port allocation, causing "access forbidden" errors
- **Existing Alfresco installations**: If you have an existing external Alfresco with standard ports, keep using 61613/61616 and configure `ALFRESCO_STOMP_PORT=61613` in your `.env` file

**Note**: Alfresco uses Traefik as a reverse proxy. All Alfresco services (Repository, Share, Content App, Control Center) are accessible through port 8080:
- **Repository**: http://localhost:8080/alfresco
- **Share**: http://localhost:8080/share  
- **Content App**: http://localhost:8080/content-app
- **Control Center**: http://localhost:8080/control-center or http://localhost:8080/admin
- **Traefik Dashboard**: http://localhost:8888

### Content Management (Nuxeo)

Nuxeo runs from its **own** compose stack (`nuxeo-deployment/`), not from
`docker/docker-compose.yaml` — but its ports share the host with this project's,
so they are listed here.

| **Service** | **Port(s)** | **Purpose** | **Dashboard URL** |
|-------------|-------------|-------------|-------------------|
| **Nuxeo Repository** | **8081** | REST API + Web UI | http://localhost:8081/nuxeo |
| **Nuxeo Kafka** | **9092** | Audit stream (drives change detection) | - |
| **Nuxeo Kafka UI** | **8092** | Topic browser | http://localhost:8092 |
| **Nuxeo PostgreSQL** | *(internal)* | Repository database | - |

**8081 is Nuxeo's own deployment default**, which is why Weaviate moved to 8086
rather than Nuxeo moving: keeping 8081 means `nuxeo-deployment`'s `.env`, the
Nuxeo documentation and `docs/DATA-SOURCES/README-nuxeo.md` all agree without
per-machine edits.

Set the port in `nuxeo-deployment/.env` (`NUXEO_HTTP_PORT`, `NUXEO_URL`,
`NUXEO_API_URL`) and match it in `flexible-graphrag/.env` (`NUXEO_URL`) if you
do change it.

### Cloud/Managed Services
| **Service** | **Port(s)** | **Type** | **Dashboard URL** |
|-------------|-------------|----------|-------------------|
| **Pinecone Info** | **3004** | Info dashboard | http://localhost:3004 |
| **LanceDB Viewer** | **3005** | Web dashboard | http://localhost:3005 |
| **LanceDB Info** | **3006** | Backup info | http://localhost:3006 |

## Port Range Allocation

### Reserved Ranges
- **3000-3099**: Frontend UIs and database dashboards
- **5000-5999**: Databases and admin interfaces  
- **6000-6999**: Specialized databases (Qdrant, FalkorDB)
- **7000-7999**: Graph databases and APIs
- **8000-8099**: Core services and vector databases
- **9000-9999**: Search engines and storage

### Available Ports
The following ports are currently available for future services:
- **3009-3099**: Additional dashboards
- **5051-5431**: Database services
- **6000-6332, 6335-6378**: Specialized services
- **7003-7473, 7475-7686, 7690-7999**: Graph services (7003 = Ladybug Explorer; 7689 = ArcadeDB Bolt)
- **8003-8069, 8071-8079, 8082-8084, 8087-8089, 8091-8159, 8162-8612, 8614-8615, 8617-8999**: Application services (8008 = Docs dev server)
- **9002-9199, 9203-9300, 9302-9999**: Search and storage services

**Note**: Ports 8613 and 8616 are now reserved for Alfresco ActiveMQ on Windows systems. Port 8083 was freed when ACS 26.2 dropped Solr; Alfresco's search index now uses 9202 (Elasticsearch) or 9203 (OpenSearch), or a shared engine on 9200/9201.

## Configuration Updates

### Environment Variables
Update your `.env` file with the new port mappings:

```bash
# Chroma
CHROMA_URL=http://localhost:8001

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
ATTU_URL=http://localhost:3003

# Weaviate  
WEAVIATE_URL=http://localhost:8086

# PostgreSQL+pgvector
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
PGADMIN_URL=http://localhost:5050
```

### Docker Compose
When including vector database services, use the updated configurations:

```yaml
include:
  - docker/includes/chroma.yaml      # Port 8001
  - docker/includes/milvus.yaml      # Ports 19530, 3003, 9000, 9001
  - docker/includes/weaviate.yaml    # Port 8086
  - docker/includes/postgres-pgvector.yaml  # Ports 5433, 5050
```

## Troubleshooting Port Conflicts

### Check Port Usage
```bash
# Windows
netstat -an | findstr :8001
netstat -an | findstr :3003
netstat -an | findstr :8081
netstat -an | findstr :5433
netstat -an | findstr :8613  # ActiveMQ STOMP
netstat -an | findstr :8616  # ActiveMQ OpenWire

# Linux/macOS
lsof -i :8001
lsof -i :3003
lsof -i :8081
lsof -i :5433
lsof -i :61613  # ActiveMQ STOMP (standard port)
lsof -i :61616  # ActiveMQ OpenWire (standard port)
```

### Common Conflicts
1. **Port 8000**: If backend conflicts with Chroma, change backend to 8002
2. **Port 3000**: If Vue conflicts with Milvus Attu, change Vue to 3004
3. **Port 8080**: If Alfresco Traefik proxy conflicts with Weaviate, both are now separated
4. **Port 5432**: If Alfresco PostgreSQL conflicts with pgvector PostgreSQL, both use different ports
5. **Port 7001**: NebulaGraph Studio uses this port
6. **Port 8090**: Transform Core AIO uses this port for document transformation services
7. **Service name conflicts**: Alfresco's services are all `alfresco-`prefixed — `alfresco-postgres` (vs this project's `postgres-pgvector`), `alfresco-proxy` (Traefik, vs this project's NGINX `proxy`) and `alfresco-elasticsearch` / `alfresco-opensearch` (vs this project's `elasticsearch`/`opensearch`)
8. **Windows dynamic port range (49152-65535)**: Ports 61613 and 61616 may conflict on Windows - see below

### Windows Dynamic Port Conflicts

**What are dynamic ports?**
Windows reserves a range of ports (49152-65535) called "dynamic" or "ephemeral" ports for temporary outgoing network connections. When your computer makes an outgoing connection (like visiting a website), Windows randomly picks a port from this range for that connection.

**Why does this cause problems?**
- Docker tries to bind to specific ports (like 61613, 61616)
- Windows may have already reserved these ports for dynamic allocation
- After Windows updates or Docker Desktop upgrades (especially 4.60+), the conflict enforcement became stricter
- You'll see errors like: `bind: An attempt was made to access a socket in a way forbidden by its access permissions`

**Solutions**:

**Option 1: Use alternative ports (Recommended for Windows)**
```yaml
# docker/includes/alfresco.yaml
ports:
  - "8613:61613"  # STOMP - host port 8613 instead of 61613
  - "8616:61616"  # OpenWire - host port 8616 instead of 61616
```
Then configure in `.env`:
```bash
ALFRESCO_STOMP_PORT=8613
```

**Option 2: Exclude ports from Windows dynamic range (Advanced)**
Run PowerShell as Administrator:
```powershell
# Exclude ports 61613-61616 from dynamic allocation
netsh interface ipv4 add excludedportrange protocol=tcp startport=61613 numberofports=4

# Restart Docker Desktop after running this command
```

**Option 3: Check dynamic port range**
```powershell
# View current dynamic port range
netsh interface ipv4 show dynamicportrange tcp

# View excluded (reserved) ports
netsh interface ipv4 show excludedportrange protocol=tcp
```

### Resolution Strategy
1. **Identify conflict**: Use port checking commands above
2. **Update configuration**: Modify the appropriate YAML file
3. **Update documentation**: Update this file and service-specific docs
4. **Test connectivity**: Verify all services start without conflicts
5. **Update client configurations**: Ensure frontends use correct URLs

## Best Practices

1. **Document all port changes** in this file
2. **Use consistent port ranges** for similar services
3. **Avoid common ports** (80, 443, 3000, 8000, 8080) when possible
4. **Test port availability** before assigning
5. **Update all references** (docs, configs, environment files)
6. **Consider future expansion** when choosing port ranges
