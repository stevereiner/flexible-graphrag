# Chroma Deployment Modes

Flexible GraphRAG supports two deployment modes for ChromaDB, providing flexibility for both development and production environments.

## Deployment Modes

### Local Mode (PersistentClient)

**Best For:** Development, testing, single-machine deployments, embedded applications

**Configuration:**
```bash
VECTOR_DB=chroma
VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}
```

**Features:**
- No server required
- File-based storage in local directory
- Zero network overhead
- Automatic persistence
- Ideal for development and prototyping

**Storage Location:**
- Default: `./chroma_db` in the application directory
- Customizable via `persist_directory` parameter

### HTTP Mode (HttpClient)

**Best For:** Multi-service architectures, remote access, production deployments, Docker environments

**Configuration:**
```bash
VECTOR_DB=chroma
VECTOR_DB_CONFIG={"host": "localhost", "port": 8001, "collection_name": "hybrid_search"}
```

**Features:**
- Requires ChromaDB server
- Remote access capabilities
- Multiple clients can connect
- RESTful API access
- Swagger UI available at http://localhost:8001/docs

**Server Setup:**

Using Docker:
```bash
docker run -d \
  --name chromadb \
  -p 8001:8000 \
  -v chroma_data:/chroma/chroma \
  chromadb/chroma:latest
```

Using Python:
```bash
pip install chromadb
chroma run --host localhost --port 8001
```

## Mode Detection

The factory automatically detects which mode to use based on the configuration:

- **HTTP Mode**: Triggered when `host` and `port` parameters are present
- **Local Mode**: Triggered when `persist_directory` parameter is present (or no mode-specific params)

## Configuration Examples

### Development (Local Mode)
```python
VECTOR_DB=chroma
VECTOR_DB_CONFIG={
    "persist_directory": "./chroma_db",
    "collection_name": "hybrid_search"
}
```

### Production (HTTP Mode - Docker)
```python
VECTOR_DB=chroma
VECTOR_DB_CONFIG={
    "host": "chromadb",  # Docker service name
    "port": 8000,        # Internal container port
    "collection_name": "hybrid_search"
}
```

### Production (HTTP Mode - External Server)
```python
VECTOR_DB=chroma
VECTOR_DB_CONFIG={
    "host": "chroma.example.com",
    "port": 8001,
    "collection_name": "hybrid_search"
}
```

## Switching Between Modes

### From Local to HTTP

1. **Start ChromaDB server:**
   ```bash
   docker run -d --name chromadb -p 8001:8000 chromadb/chroma
   ```

2. **Update configuration:**
   ```bash
   # Change from:
   VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}
   
   # To:
   VECTOR_DB_CONFIG={"host": "localhost", "port": 8001, "collection_name": "hybrid_search"}
   ```

3. **Optional: Migrate data** (if needed, manually load from local storage to server)

### From HTTP to Local

1. **Update configuration:**
   ```bash
   # Change from:
   VECTOR_DB_CONFIG={"host": "localhost", "port": 8001, "collection_name": "hybrid_search"}
   
   # To:
   VECTOR_DB_CONFIG={"persist_directory": "./chroma_db", "collection_name": "hybrid_search"}
   ```

2. **Stop ChromaDB server** (if not needed):
   ```bash
   docker stop chromadb
   ```

## Performance Considerations

### Local Mode
- **Pros:**
  - Fastest access (no network overhead)
  - Simplest setup
  - No server management
- **Cons:**
  - Single machine only
  - No remote access
  - Not suitable for distributed systems

### HTTP Mode
- **Pros:**
  - Remote access from multiple clients
  - Better for microservices
  - Centralized data management
  - Scalable architecture
- **Cons:**
  - Network latency
  - Server management required
  - Additional infrastructure

## API Access

### Local Mode
Only accessible via Python API within the same application:
```python
import chromadb
client = chromadb.PersistentClient(path="./chroma_db")
```

### HTTP Mode
Accessible via multiple interfaces:

**Python:**
```python
import chromadb
client = chromadb.HttpClient(host="localhost", port=8001)
```

**REST API:**
```bash
# List all collections
curl "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections"

# Get specific collection
curl "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections/hybrid_search"

# Delete specific collection
curl -X DELETE "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections/hybrid_search"
```

**API Structure:** `/api/v2/tenants/{tenant}/databases/{database}/collections/{collection_name}`

**Swagger UI:**
http://localhost:8001/docs

## Troubleshooting

### Local Mode Issues
- **Permission denied**: Check directory write permissions
- **Database locked**: Close other processes accessing the database
- **Disk space**: Verify sufficient storage for vector data

### HTTP Mode Issues
- **Connection refused**: Verify ChromaDB server is running
- **Timeout**: Check network connectivity and firewall rules
- **Authentication**: Ensure no authentication is configured (default Chroma has none)

## Migration Between Modes

There is no automatic migration between local and HTTP modes. If you need to preserve data:

1. Export from source mode:
   ```python
   import chromadb
   
   # Connect to source
   source_client = chromadb.PersistentClient(path="./chroma_db")
   collection = source_client.get_collection("hybrid_search")
   
   # Get all data
   results = collection.get(include=["embeddings", "documents", "metadatas"])
   ```

2. Import to target mode:
   ```python
   # Connect to target
   target_client = chromadb.HttpClient(host="localhost", port=8001)
   target_collection = target_client.get_or_create_collection("hybrid_search")
   
   # Add data
   target_collection.add(
       ids=results["ids"],
       embeddings=results["embeddings"],
       documents=results["documents"],
       metadatas=results["metadatas"]
   )
   ```

## Recommendations

- **Development**: Use Local Mode for fastest iteration
- **Testing**: Use Local Mode for isolated test environments
- **Production (Single Server)**: Use Local Mode if no remote access needed
- **Production (Distributed)**: Use HTTP Mode for microservices architecture
- **Production (High Availability)**: Consider managed vector database services (Pinecone, Qdrant Cloud, etc.)

## See Also

- [Vector Database Integration Guide](VECTOR-DATABASE-INTEGRATION.md)
- [Vector Dimension Compatibility Guide](VECTOR-DIMENSIONS.md)
- [Default Usernames and Passwords](DEFAULT-USERNAMES-PASSWORDS.md)
- [ChromaDB Official Documentation](https://docs.trychroma.com/)

