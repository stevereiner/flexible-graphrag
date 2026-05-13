# Vector Database Integration

Flexible GraphRAG supports 10 vector databases. All are supported with both the LlamaIndex and LangChain backends — set `VECTOR_BACKEND=llamaindex` or `VECTOR_BACKEND=langchain` to choose.

## Supported Vector Databases

| `VECTOR_DB` | Store | Port |
|---|---|---|
| `qdrant` | Qdrant | 6333 |
| `elasticsearch` | Elasticsearch | 9200 |
| `opensearch` | OpenSearch | 9201 |
| `chroma` | Chroma | 8001 |
| `milvus` | Milvus | 19530 |
| `weaviate` | Weaviate | 8081 |
| `pinecone` | Pinecone | cloud |
| `postgres` | PostgreSQL + pgvector | 5433 |
| `lancedb` | LanceDB | embedded |
| `neo4j` | Neo4j Vector | 7687 |

## Configuration

### Qdrant

- **Docker**: `docker/includes/qdrant.yaml`

```env
VECTOR_DB=qdrant
QDRANT_VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search"}
```

### Elasticsearch

- **Dashboard**: Kibana at http://localhost:5601
- **Docker**: `docker/includes/elasticsearch-dev.yaml` (dev) or `docker/includes/elasticsearch.yaml`

```env
VECTOR_DB=elasticsearch
ELASTICSEARCH_VECTOR_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search_vectors"}
```

### OpenSearch

- **Dashboard**: OpenSearch Dashboards at http://localhost:5601
- **Docker**: `docker/includes/opensearch.yaml`

```env
VECTOR_DB=opensearch
OPENSEARCH_VECTOR_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search_vectors"}
```

### Chroma

Two deployment modes — local file-based or remote HTTP server:

- **Dashboard**: Swagger API at http://localhost:8001/docs (HTTP mode only)
- **Docker**: `docker/includes/chroma.yaml`

```env
VECTOR_DB=chroma

# Local mode (file-based)
CHROMA_VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}

# HTTP mode (remote server)
CHROMA_VECTOR_DB_CONFIG={"host": "localhost", "port": 8001, "collection_name": "hybrid_search"}
```

### Milvus

- **Dashboard**: Attu at http://localhost:3003
- **Docker**: `docker/includes/milvus.yaml` (includes etcd, MinIO, Attu)
- **Ports**: 19530 (gRPC), 3003 (Attu), 9000/9001 (MinIO)

```env
VECTOR_DB=milvus
MILVUS_VECTOR_DB_CONFIG={"host": "localhost", "port": 19530, "collection_name": "hybrid_search", "username": "root", "password": "milvus"}
```

### Weaviate

- **Dashboard**: Weaviate Console at http://localhost:8081/console
- **Docker**: `docker/includes/weaviate.yaml`

```env
VECTOR_DB=weaviate
WEAVIATE_VECTOR_DB_CONFIG={"url": "http://localhost:8081", "index_name": "HybridSearch"}
```

### Pinecone

- **Dashboard**: Pinecone Console (web-based)
- **Docker**: `docker/includes/pinecone.yaml`
- **Requirements**: API key required

```env
VECTOR_DB=pinecone
PINECONE_VECTOR_DB_CONFIG={"api_key": "your_api_key", "region": "us-east-1", "cloud": "aws", "index_name": "hybrid-search", "metric": "cosine"}
```

### PostgreSQL + pgvector

- **Dashboard**: pgAdmin at http://localhost:5050
- **Docker**: `docker/includes/postgres-pgvector.yaml`
- **Ports**: 5433 (PostgreSQL), 5050 (pgAdmin)

```env
VECTOR_DB=postgres
POSTGRES_VECTOR_DB_CONFIG={"host": "localhost", "port": 5433, "database": "flexible_graphrag", "username": "flexible_graphrag", "password": "password"}
```

### LanceDB

- **Storage**: Local file-based (embedded)
- **Docker**: `docker/includes/lancedb.yaml`

```env
VECTOR_DB=lancedb
LANCEDB_VECTOR_DB_CONFIG={"uri": "./lancedb", "table_name": "hybrid_search"}
```

### Neo4j Vector

- **Dashboard**: Neo4j Browser at http://localhost:7474
- **Docker**: `docker/includes/neo4j.yaml`

```env
VECTOR_DB=neo4j
NEO4J_VECTOR_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "your_password", "index_name": "hybrid_search_vector"}
```

## Vector Dimension Compatibility

When switching embedding models, delete existing vector indexes — dimensions differ by provider:

- **OpenAI**: 1536 dimensions (text-embedding-3-small), 3072 dimensions (text-embedding-3-large)
- **Ollama**: 384 dimensions (all-minilm), 768 dimensions (nomic-embed-text), 1024 dimensions (mxbai-embed-large)
- **Azure OpenAI**: Same as OpenAI (1536 or 3072 dimensions)

See [Vector Dimensions](VECTOR-DIMENSIONS.md) for cleanup instructions.

## Dependencies

**LlamaIndex** vector store packages:

```
llama-index-vector-stores-qdrant       llama-index-vector-stores-elasticsearch
llama-index-vector-stores-opensearch   llama-index-vector-stores-chroma
llama-index-vector-stores-milvus       llama-index-vector-stores-weaviate
llama-index-vector-stores-pinecone     llama-index-vector-stores-postgres
llama-index-vector-stores-lancedb      llama-index-vector-stores-neo4jvector
```

**LangChain** vector store packages (via `.[langchain]` extras):

```
langchain-qdrant    langchain-elasticsearch   langchain-chroma
langchain-milvus    langchain-weaviate        langchain-pinecone
langchain-postgres  langchain-community       langchain-neo4j
```
