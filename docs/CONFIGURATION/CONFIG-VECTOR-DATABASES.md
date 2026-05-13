# Vector Database Configuration

## Database Selection

Set `VECTOR_DB` to select the store:

```env
VECTOR_DB=qdrant    # qdrant | elasticsearch | opensearch | chroma | milvus | weaviate | pinecone | postgres | lancedb | neo4j | none
```

## Framework Selection

Set `VECTOR_BACKEND` to choose the framework. All stores are supported with both:

```env
VECTOR_BACKEND=llamaindex   # or langchain
```

## Vector Dimension Compatibility

When switching between different embedding models you **must delete existing vector indexes** due to dimension incompatibility.

- **OpenAI**: 1536 dimensions (text-embedding-3-small) or 3072 dimensions (text-embedding-3-large)
- **Ollama**: 384 dimensions (all-minilm), 768 dimensions (nomic-embed-text), 1024 dimensions (mxbai-embed-large)
- **Azure OpenAI**: Same as OpenAI (1536 or 3072 dimensions)

See [Vector Dimensions](../DATABASES/VECTOR-DATABASES/VECTOR-DIMENSIONS.md) for cleanup instructions.

## RAG without GraphRAG

For faster document ingest (no graph extraction), configure vector + search only:

```env
VECTOR_DB=qdrant
SEARCH_DB=elasticsearch
PG_GRAPH_DB=none
ENABLE_KNOWLEDGE_GRAPH=false
```

## Supported Vector Databases

### Qdrant

Dedicated vector database with advanced filtering (recommended).

- Dashboard: Qdrant Web UI (http://localhost:6333/dashboard)

```env
VECTOR_DB=qdrant
```

### Elasticsearch

Can be used as vector database alongside or independently of Elasticsearch search.

- Dashboard: Kibana (http://localhost:5601)

```env
VECTOR_DB=elasticsearch
```

### OpenSearch

Can be used as vector database alongside or independently of OpenSearch search.

- Dashboard: OpenSearch Dashboards (http://localhost:5601)

```env
VECTOR_DB=opensearch
```

### Chroma

Open-source vector database with local (persist) and HTTP server deployment modes.

- Dashboard: Swagger UI (http://localhost:8001/docs/) (HTTP mode)

```env
VECTOR_DB=chroma
```

See [Chroma Deployment Modes](../DATABASES/VECTOR-DATABASES/CHROMA-DEPLOYMENT-MODES.md) for details.

### Milvus

Cloud-native, scalable vector database for similarity search.

- Dashboard: Attu (http://localhost:3003)

```env
VECTOR_DB=milvus
```

### Weaviate

Vector search engine with semantic capabilities.

- Dashboard: Weaviate Console (http://localhost:8081/console)

```env
VECTOR_DB=weaviate
```

### Pinecone

Managed cloud vector database service.

- Dashboard: Pinecone Console (web-based)

```env
VECTOR_DB=pinecone
```

### PostgreSQL pgvector

PostgreSQL with the pgvector extension — standalone container at port 5433, separate from the Alfresco Postgres (5432) and Apache AGE (5434) containers.

- Dashboard: pgAdmin (http://localhost:5050)

```env
VECTOR_DB=postgres
```

### LanceDB

Embedded vector database for local ML workloads, no external server required.

```env
VECTOR_DB=lancedb
```

### Neo4j

Neo4j graph store used as a vector database via its native vector index.

- Dashboard: Neo4j Browser (http://localhost:7474)

```env
VECTOR_DB=neo4j
```

See [Vector Database Integration](../DATABASES/VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) for more details.
