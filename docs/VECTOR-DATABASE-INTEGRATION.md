# Vector Database Integration Guide

This document describes the comprehensive vector database support in Flexible GraphRAG, including the six new databases added based on [LlamaIndex vector store integrations](https://github.com/run-llama/llama_index/tree/main/llama-index-integrations/vector_stores).

## Supported Vector Databases

### Existing Databases
1. **Neo4j Vector** - Native vector storage in Neo4j with APOC support
2. **Qdrant** - Dedicated vector database with advanced filtering
3. **Elasticsearch** - Full-text and vector search capabilities
4. **OpenSearch** - Open-source Elasticsearch alternative

### Newly Added Databases
5. **Chroma** - Open-source vector database with local persistence
6. **Milvus** - Cloud-native, scalable vector database for similarity search
7. **Weaviate** - Vector search engine with semantic capabilities and data enrichment
8. **Pinecone** - Managed vector database service optimized for real-time applications
9. **PostgreSQL** - Traditional database with pgvector extension for vector similarity search
10. **LanceDB** - Modern, lightweight vector database designed for high-performance ML applications

## Configuration Examples

### Chroma (Local Persistence)
```bash
VECTOR_DB=chroma
VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}
```

### Milvus (Scalable)
```bash
VECTOR_DB=milvus
VECTOR_DB_CONFIG={"host": "localhost", "port": 19530, "collection_name": "hybrid_search", "username": "root", "password": "milvus"}
```

### Weaviate (Semantic Search)
```bash
VECTOR_DB=weaviate
VECTOR_DB_CONFIG={"url": "http://localhost:8080", "class_name": "HybridSearch", "api_key": "your_api_key"}
```

### Pinecone (Managed Service)
```bash
VECTOR_DB=pinecone
VECTOR_DB_CONFIG={"api_key": "your_pinecone_api_key", "environment": "us-east1-gcp", "index_name": "hybrid-search", "namespace": "default"}
```

### PostgreSQL (with pgvector)
```bash
VECTOR_DB=postgres
VECTOR_DB_CONFIG={"host": "localhost", "port": 5432, "database": "postgres", "username": "postgres", "password": "password", "table_name": "hybrid_search_vectors"}
```

### LanceDB (Modern Embedded)
```bash
VECTOR_DB=lancedb
VECTOR_DB_CONFIG={"uri": "./lancedb", "table_name": "hybrid_search", "vector_column_name": "vector", "text_column_name": "text"}
```

## Docker Support

Docker configurations are provided for databases that support containerized deployment:

- **Chroma**: `docker/includes/chroma.yaml` - Single container with persistent storage
- **Milvus**: `docker/includes/milvus.yaml` - Multi-container setup with etcd, MinIO, and Attu dashboard
- **Weaviate**: `docker/includes/weaviate.yaml` - Single container with module support
- **PostgreSQL**: `docker/includes/postgres-pgvector.yaml` - PostgreSQL with pgvector extension and pgAdmin

### Usage
```bash
# Include specific vector database in your docker-compose.yaml
include:
  - docker/includes/chroma.yaml
  - docker/includes/milvus.yaml
  - docker/includes/weaviate.yaml
  - docker/includes/postgres-pgvector.yaml
```

## Database-Specific Features

### Chroma
- **Type**: Local embedded database
- **Strengths**: Simple setup, local persistence, good for development
- **Dashboard**: File-based storage with Python API
- **Port**: 8001 (when using server mode)

### Milvus
- **Type**: Distributed vector database
- **Strengths**: High scalability, cloud-native, enterprise features
- **Dashboard**: Attu (http://localhost:3003)
- **Ports**: 19530 (Milvus), 3003 (Attu), 9000/9001 (MinIO)

### Weaviate
- **Type**: Vector search engine
- **Strengths**: Semantic search, data enrichment, GraphQL API
- **Dashboard**: Weaviate Console (http://localhost:8081/console)
- **Port**: 8081

### Pinecone
- **Type**: Managed cloud service
- **Strengths**: Fully managed, real-time updates, global availability
- **Dashboard**: Pinecone Console (web-based)
- **Requirements**: API key and environment

### PostgreSQL + pgvector
- **Type**: Traditional RDBMS with vector extension
- **Strengths**: ACID compliance, familiar SQL, existing PostgreSQL expertise
- **Dashboard**: pgAdmin (http://localhost:5050)
- **Ports**: 5433 (PostgreSQL), 5050 (pgAdmin)

### LanceDB
- **Type**: Modern embedded database
- **Strengths**: High performance, columnar storage, zero-copy operations
- **Dashboard**: Python API for management
- **Storage**: Local file-based

## Implementation Details

### Factory Pattern
All vector databases are implemented using the factory pattern in `factories.py`:
- Consistent interface across all databases
- Automatic configuration handling
- Error handling for missing dependencies

### Configuration Management
- Environment variable support for all parameters
- Default values for common configurations
- Embedding dimension auto-detection based on LLM provider

### Testing
Basic factory tests are included in `tests/test_basic.py`:
- Enum validation
- Factory method existence
- Configuration parameter handling
- Graceful handling of missing dependencies

## Migration Guide

### From Existing Databases
1. Update your `.env` file with the new `VECTOR_DB` value
2. Configure `VECTOR_DB_CONFIG` with appropriate parameters
3. Install required dependencies: `uv pip install -r requirements.txt`
4. Restart the application

### Vector Dimension Compatibility
**CRITICAL**: When switching between vector databases, ensure you clean up existing indexes due to embedding dimension differences:
- **OpenAI**: 1536 dimensions (text-embedding-3-small)
- **Ollama**: 1024 dimensions (mxbai-embed-large)

See [VECTOR-DIMENSIONS.md](VECTOR-DIMENSIONS.md) for cleanup instructions.

## Dependencies

The following packages are automatically installed:
- `llama-index-vector-stores-chroma`
- `llama-index-vector-stores-milvus`
- `llama-index-vector-stores-weaviate`
- `llama-index-vector-stores-pinecone`
- `llama-index-vector-stores-postgres`
- `llama-index-vector-stores-lancedb`
- `chromadb`
- `pymilvus`
- `weaviate-client`
- `pinecone-client`
- `psycopg2-binary`
- `lancedb`

## Troubleshooting

### Common Issues
1. **Import Errors**: Ensure all dependencies are installed with `uv pip install -r requirements.txt`
2. **Connection Errors**: Verify database services are running and accessible
3. **Dimension Mismatch**: Clean up existing indexes when switching embedding models
4. **API Key Issues**: Verify credentials for managed services (Pinecone, Weaviate Cloud)

### Performance Considerations
- **Local Databases**: Chroma, LanceDB - Good for development and small datasets
- **Scalable Databases**: Milvus, Weaviate - Better for production and large datasets
- **Managed Services**: Pinecone - Best for production without infrastructure management
- **Traditional RDBMS**: PostgreSQL - Good when you need ACID compliance and SQL familiarity

## Future Enhancements

Potential future additions based on LlamaIndex ecosystem:
- Faiss integration for CPU-optimized similarity search
- Redis vector search capabilities
- Azure Cognitive Search integration
- Additional cloud provider vector services

For the most up-to-date list of supported vector stores, see the [LlamaIndex vector stores documentation](https://github.com/run-llama/llama_index/tree/main/llama-index-integrations/vector_stores).
