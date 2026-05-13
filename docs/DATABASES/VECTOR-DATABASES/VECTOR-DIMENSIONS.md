# Vector Dimension Compatibility Guide

This document explains critical vector dimension compatibility issues when switching between different embedding models in Flexible GraphRAG.

## ⚠️ Critical Issue: Vector Dimension Incompatibility

When switching between different LLM providers or embedding models, you **MUST delete existing vector indexes** because different models produce embeddings with different dimensions.

### Why This Matters

Vector databases create indexes optimized for specific dimensions. When you change embedding models, the new embeddings won't fit the existing index structure, causing errors like:

- `Dimension mismatch error`
- `Vector size incompatible with index`
- `Index dimension does not match embedding dimension`

## 📊 Embedding Dimensions by Provider

### OpenAI
- **text-embedding-3-large**: `3072` dimensions
- **text-embedding-3-small**: `1536` dimensions (default)
- **text-embedding-ada-002**: `1536` dimensions

### Ollama
- **all-minilm**: `384` dimensions (default)
- **nomic-embed-text**: `768` dimensions
- **mxbai-embed-large**: `1024` dimensions

### Azure OpenAI
- Same as OpenAI models: `1536` or `3072` dimensions

### Other Providers
- **Default fallback**: `1536` dimensions

## 🗂️ Vector Database Cleanup Instructions

### 🎯 **Best Databases for Easy Vector Deletion**

When frequently switching between embedding models (OpenAI ↔ Ollama), choose databases with user-friendly deletion:

| **Database** | **Deletion Method** | **Difficulty** | **Dashboard** |
|--------------|-------------------|----------------|---------------|
| **Qdrant** ✅ | One-click collection deletion | ⭐ Easy | Web UI |
| **Milvus** ✅ | Professional drop operations | ⭐⭐ Moderate | Attu Dashboard |
| **Weaviate** ✅ | Schema-based deletion | ⭐⭐ Moderate | Console |
| **Chroma** ⚠️ | HTTP mode: API deletion, Local mode: File cleanup | ⭐⭐ Moderate | Swagger API (HTTP) |
| **LanceDB** ⚠️ | File/table deletion | ⭐⭐ Moderate | Viewer + Files |
| **PostgreSQL** ❌ | SQL commands required | ⭐⭐⭐ Advanced | pgAdmin |
| **Pinecone** ⚠️ | Cloud console only | ⭐⭐ Moderate | Web Console |

**💡 Recommendation:** Use **Qdrant** or **Milvus** for the easiest vector cleanup when switching embedding models.

### Qdrant (Recommended for Easy Deletion)

**Using Qdrant Dashboard:**
1. Open Qdrant Dashboard: http://localhost:6333/dashboard
2. Go to "Collections" tab
3. Find `hybrid_search_vector` (or your collection name) in the collections list
4. Click the **3 dots (⋮)** menu next to the collection
5. Select **"Delete"**
6. Confirm the deletion

### Neo4j

**Using Neo4j Browser:**
1. Open Neo4j Browser: http://localhost:7474 (or your Neo4j port)
2. Login with your credentials
3. **Drop Vector Index:**
   - Run: `SHOW INDEXES`
   - Run: `DROP INDEX hybrid_search_vector IF EXISTS`
   - Run: `SHOW INDEXES` to verify cleanup

### Elasticsearch

**Using Kibana Dashboard:**
1. Open Kibana: http://localhost:5601 (if Kibana is running)
2. Choose **"Management"** from the main menu
3. Click **"Index Management"**
4. Select `hybrid_search_vector` from the indices list
5. Choose **"Manage index"** (blue button)
6. Choose **"Delete index"**
7. Confirm the deletion

**Alternative - Using Elasticsearch REST API:**
```bash
# Delete the vector index via curl
curl -X DELETE "http://localhost:9200/hybrid_search_vector"
```

### OpenSearch

**Using OpenSearch Dashboards:**
1. Open OpenSearch Dashboards: http://localhost:5601 (if running) or http://localhost:9201/_dashboards
2. Go to **"Index Management"** (in the main menu or under "Management")
3. Click on **"Indices"** tab
4. Find `hybrid_search_vector` in the indices list
5. Click the **checkbox** next to the index
6. Click **"Actions"** → **"Delete"**
7. Confirm the deletion by typing **"delete"**

**Alternative - Using OpenSearch REST API:**
```bash
# Delete the vector index via curl
curl -X DELETE "http://localhost:9201/hybrid_search_vector"
```

### Chroma (File System or HTTP API Cleanup)

Chroma supports two deployment modes with different cleanup approaches:

**Local Mode (PersistentClient) - File System Cleanup:**
```bash
# Delete Chroma directory (contains all vector data)
rm -rf ./chroma_db

# Or on Windows
rmdir /s /q .\chroma_db

# Or on Windows PowerShell
Remove-Item -Path .\chroma_db -Recurse -Force

# Verify cleanup
ls -la  # Should not show chroma_db directory
```

**HTTP Mode (HttpClient) - Using curl or Swagger API:**
```bash
# List all collections
curl "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections"

# Delete specific collection
curl -X DELETE "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections/hybrid_search"
```

Via Swagger UI (http://localhost:8001/docs):
1. Find the **DELETE** endpoint for collections
2. Enter tenant: `default_tenant`
3. Enter database: `default_database`
4. Enter collection: `hybrid_search`
5. Execute

**Alternative - Using Python API (for both modes):**
```python
import chromadb

# For Local Mode (PersistentClient)
client = chromadb.PersistentClient(path="./chroma_db")

# For HTTP Mode (HttpClient)
# client = chromadb.HttpClient(host="localhost", port=8001)

# Delete collection
client.delete_collection("hybrid_search")

# Verify
print(client.list_collections())  # Should not include hybrid_search
```

### Milvus (Professional Dashboard)

**Via Milvus Attu Dashboard (http://localhost:3003):**
1. Open **Attu Dashboard** at `http://localhost:3003`
2. Navigate to **Collections** page
3. Find your collection (typically `hybrid_search`)
4. Click the **"Drop"** button next to the collection
5. Confirm the deletion by typing the collection name
6. Click **"Drop Collection"** to confirm

**Alternative - Using Milvus CLI:**
```bash
# Connect to Milvus and drop collection
curl -X DELETE "http://localhost:19530/v1/collection" \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "hybrid_search"}'
```

### Weaviate (Schema Management)

**Via Weaviate Console (http://localhost:8081/console):**
1. Open **Weaviate Console** at `http://localhost:8081/console`
2. Navigate to **Schema** section
3. Find your class (typically `HybridSearch` or `Documents`)
4. Click **"Delete Class"** button
5. Confirm deletion - this removes all vectors in the class

**Alternative - Using Weaviate API:**
```bash
# Delete entire class (removes all vectors)
curl -X DELETE "http://localhost:8081/v1/schema/HybridSearch"
```

### PostgreSQL+pgvector (SQL-Based)

**Via pgAdmin (http://localhost:5050):**
1. Open **pgAdmin** at `http://localhost:5050`
2. Login with `admin@flexible-graphrag.com` / `admin`
3. Connect to PostgreSQL server (`postgres:5432`)
4. Navigate to **Tables** in the database
5. Find your vector table (e.g., `hybrid_search_vectors`)
6. **Right-click** → **Delete/Drop** → **Cascade**
7. Confirm deletion

**Alternative - Using SQL Commands:**
```sql
-- Delete all vectors from table
DELETE FROM hybrid_search_vectors;

-- Or drop entire table
DROP TABLE IF EXISTS hybrid_search_vectors CASCADE;

-- Verify cleanup
\dt  -- List tables to confirm deletion
```

**Reference:** [n8n Community - Deleting pgvector content](https://community.n8n.io/t/how-do-i-delete-content-of-postgres-pgvector-database/145666)

### Pinecone (Cloud Console)

**Via Pinecone Console (https://app.pinecone.io):**
1. Log in to **Pinecone Console** at `https://app.pinecone.io`
2. Navigate to **Indexes** page from left navigation
3. Find your index (typically `hybrid-search`)
4. Click the **three vertical dots (•••)** to the right of index name
5. Select **"Delete"** from dropdown menu
6. **Confirm deletion** in the dialog box
7. **⚠️ Warning:** This is permanent and irreversible!

**Note:** Pinecone is a managed service - no local deletion needed.

### LanceDB (File-Based Cleanup)

**Via LanceDB Viewer (http://localhost:3005):**
1. Open **LanceDB Viewer** at `http://localhost:3005`
2. Navigate to **Tables** section
3. Find your table (typically `hybrid_search`)
4. Click **"Delete Table"** button
5. Confirm deletion

**Alternative - File System Cleanup:**
```bash
# Delete LanceDB directory (contains all vector data)
rm -rf ./lancedb

# Or on Windows
rmdir /s /q .\lancedb

# Verify cleanup
ls -la  # Should not show lancedb directory
```

### Neo4j (Vector Index Cleanup)

## 🔄 Safe Migration Process

When switching embedding models, follow this process:

### 1. Backup Important Data (Optional)
```bash
# Export any important data before deletion
# (Implementation depends on your database)
```

### 2. Update Configuration
```bash
# Edit your .env file
LLM_PROVIDER=ollama  # Changing from openai to ollama
EMBEDDING_MODEL=all-minilm  # 384 dimensions
```

### 3. Clean Vector Database
Choose the appropriate cleanup method from above based on your vector database.

### 4. Restart Services
```bash
# Restart your application
cd flexible-graphrag
uv run start.py
```

### 5. Re-ingest Documents
```bash
# Re-process your documents with the new embedding model
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{"data_source": "filesystem", "paths": ["./your_documents"]}'
```

## 🚨 Common Error Messages

### Qdrant
```
Vector dimension mismatch: expected 1536, got 384
```

### Neo4j
```
Vector index dimension (1536) does not match embedding dimension (384)
```

### Elasticsearch/OpenSearch
```
mapper_parsing_exception: dimension mismatch
```

## 📋 Configuration Detection

The system automatically detects embedding dimensions in `flexible-graphrag/factories.py`:

```python
def get_embedding_dimension(llm_provider: LLMProvider, llm_config: Dict[str, Any]) -> int:
    if llm_provider == LLMProvider.OPENAI:
        return 1536  # or 3072 for large models
    elif llm_provider == LLMProvider.OLLAMA:
        return 384  # default for all-minilm
    # ... other providers
```

The dimension is automatically applied to vector database configurations in `config.py`:

```python
"embed_dim": 1536 if self.llm_provider == LLMProvider.OPENAI else 384
```


## Ollama + Ladybug + vector store

When using **Ollama** embeddings with **Ladybug** (`GRAPH_DB=ladybug`) and a separate **VECTOR_DB** (for example Qdrant), use one embedding model end-to-end and set `EMBEDDING_DIMENSION` to match (for example 384 for `all-minilm`, 768 for `nomic-embed-text`). If you change embedding models or dimensions, clear the vector index data and remove or recreate the Ladybug `.lbug` file before re-ingesting.

Ladybug can store vectors on chunk nodes when `LADYBUG_USE_VECTOR_INDEX=true`; those vectors must use the same embedding model and dimension as your configured `VECTOR_DB`.

## Best Practices

1. **Plan Your Embedding Model**: Choose your embedding model before ingesting large document collections
2. **Test with Small Data**: Verify compatibility with a small test dataset first
3. **Document Your Configuration**: Keep track of which embedding model you're using
4. **Backup Strategy**: Consider backup procedures if you need to preserve processed data
5. **Environment Separation**: Use different databases/collections for different embedding models
6. **Consistent Naming**: Use explicit collection/database names to avoid defaults mismatches
7. **Ollama + Ladybug**: Align embedding dimensions across Ladybug and `VECTOR_DB` before large ingests

## Verification

After switching models and cleaning databases, verify the setup:

```bash
# Test with a small document
curl -X POST "http://localhost:8000/api/test-sample" \
  -H "Content-Type: application/json" \
  -d '{}'

# Check system status
curl "http://localhost:8000/api/status"
```

## 📚 Related Documentation

- [Overview](../../index.md) - Full system setup
- [Neo4j Cleanup](../GRAPH-DATABASES/README-neo4j.md) - Detailed Neo4j cleanup procedures
- [Docker Setup](../../HOME/HOME-DOCKER.md) - Container-based deployment
- [Configuration Guide](../../GETTING-STARTED/ENVIRONMENT-CONFIGURATION.md) - Environment configuration
