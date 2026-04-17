# Vector Database Configuration

**Configuration**: Set via `VECTOR_DB` and `VECTOR_DB_CONFIG` environment variables

## Vector Dimension Compatibility

!!! warning
    When switching between different embedding models (e.g., OpenAI ↔ Ollama), you **MUST delete existing vector indexes** due to dimension incompatibility:

    - **OpenAI**: 1536 dimensions (text-embedding-3-small) or 3072 dimensions (text-embedding-3-large)
    - **Ollama**: 384 dimensions (all-minilm, default), 768 dimensions (nomic-embed-text), or 1024 dimensions (mxbai-embed-large)
    - **Azure OpenAI**: Same as OpenAI (1536 or 3072 dimensions)

    See [Vector Dimensions](VECTOR-DATABASES/VECTOR-DIMENSIONS.md) for detailed cleanup instructions.

## RAG without GraphRAG

For faster document ingest (no graph extraction), configure vector + search only:

```bash
VECTOR_DB=qdrant  # Any vector store
SEARCH_DB=elasticsearch  # Any search engine
GRAPH_DB=none
ENABLE_KNOWLEDGE_GRAPH=false
```

## Supported Vector Databases

### Qdrant

Dedicated vector database with advanced filtering (recommended).

- Dashboard: Qdrant Web UI (http://localhost:6333/dashboard)

```bash
VECTOR_DB=qdrant
VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search"}
```

### Neo4j

Can be used as vector database with separate vector configuration.

- Dashboard: Neo4j Browser (http://localhost:7474)

```bash
VECTOR_DB=neo4j
VECTOR_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "your_password", "index_name": "hybrid_search_vector"}
```

### Elasticsearch

Can be used as vector database with separate vector configuration.

- Dashboard: Kibana (http://localhost:5601)

```bash
VECTOR_DB=elasticsearch
VECTOR_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search_vectors"}
```

### OpenSearch

Can be used as vector database with separate vector configuration.

- Dashboard: OpenSearch Dashboards (http://localhost:5601)

```bash
VECTOR_DB=opensearch
VECTOR_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search_vectors"}
```

### Chroma

Open-source vector database with dual deployment modes.

- Dashboard: Swagger UI (http://localhost:8001/docs/) (HTTP mode)

```bash
# Local Mode
VECTOR_DB=chroma
VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}

# HTTP Mode
VECTOR_DB=chroma
VECTOR_DB_CONFIG={"host": "localhost", "port": 8001, "collection_name": "hybrid_search"}
```

See [Chroma Deployment Modes](VECTOR-DATABASES/CHROMA-DEPLOYMENT-MODES.md) for details.

### Milvus

Cloud-native, scalable vector database for similarity search.

- Dashboard: Attu (http://localhost:3003)

```bash
VECTOR_DB=milvus
VECTOR_DB_CONFIG={"uri": "http://localhost:19530", "collection_name": "hybrid_search"}
```

### Weaviate

Vector search engine with semantic capabilities.

- Dashboard: Weaviate Console (http://localhost:8081/console)

```bash
VECTOR_DB=weaviate
VECTOR_DB_CONFIG={"url": "http://localhost:8081", "index_name": "HybridSearch"}
```

### Pinecone

Managed vector database service.

- Dashboard: Pinecone Console (web-based)

```bash
VECTOR_DB=pinecone
VECTOR_DB_CONFIG={"api_key": "your_api_key", "region": "us-east-1", "cloud": "aws", "index_name": "hybrid-search"}
```

### PostgreSQL pgvector

Traditional database with pgvector extension.

- Dashboard: pgAdmin (http://localhost:5050)

```bash
VECTOR_DB=postgres
VECTOR_DB_CONFIG={"host": "localhost", "port": 5433, "database": "postgres", "username": "postgres", "password": "your_password"}
```

### LanceDB

Modern, lightweight vector database for high-performance ML.

- Dashboard: LanceDB Viewer (http://localhost:3005)

```bash
VECTOR_DB=lancedb
VECTOR_DB_CONFIG={"uri": "./lancedb", "table_name": "hybrid_search"}
```

See [Vector Database Integration](VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) for more details.
