# Environment Configuration Guide

This document explains how to configure Flexible GraphRAG using environment variables and configuration files.

## 📁 **Configuration Files**

### **Primary Configuration**
- **`.env`** - Your main configuration file (copy from `flexible-graphrag/env-sample.txt`)
- **`flexible-graphrag/env-sample.txt`** - Template with all options and examples

### **Frontend Configuration**
- **Angular**: Uses `PROCESS_FOLDER_PATH` 
- **React/Vue**: Uses `VITE_PROCESS_FOLDER_PATH`
- See `docs/SOURCE-PATH-EXAMPLES.md` for details

## 🏗️ **5-Section Configuration Structure**

The `env-sample.txt` follows a logical 5-section structure:

### **Section 1: Graph Database Configuration**
- Graph database selection (`GRAPH_DB`)
- Knowledge graph extraction settings (`ENABLE_KNOWLEDGE_GRAPH`)
- Schema configuration (`SCHEMA_NAME`, `SCHEMAS`)
- Graph database connection configs (`GRAPH_DB_CONFIG`)

### **Section 2: Vector Database Configuration**  
- Vector database selection (`VECTOR_DB`)
- Vector database connection configs (`VECTOR_DB_CONFIG`)
- Index/collection names for vector storage

### **Section 3: Search Database Configuration**
- Search database selection (`SEARCH_DB`)
- Search database connection configs (`SEARCH_DB_CONFIG`) 
- Index names for fulltext search

### **Section 4: LLM Configuration**
- LLM provider selection (`LLM_PROVIDER`)
- Provider-specific settings (OpenAI, Ollama, Azure, etc.)
- API keys and model configurations
- Timeout settings

### **Section 5: Content Sources Configuration**
- CMIS and Alfresco settings for document sources
- Authentication credentials

## 🔧 **Database Configuration Patterns**

### **Selection Variables**
These control which backend to use:
```bash
VECTOR_DB=neo4j        # neo4j, qdrant, elasticsearch, opensearch, none
SEARCH_DB=elasticsearch # elasticsearch, opensearch, bm25, none  
GRAPH_DB=neo4j         # neo4j, kuzu, falkordb, arcadedb, memgraph, nebula, neptune, neptune_analytics, none
```

### **Connection Configuration**
Each database type has a `*_DB_CONFIG` JSON configuration:
```bash
# Vector database connections
VECTOR_DB_CONFIG={"host": "localhost", "port": 6333, "collection_name": "hybrid_search_vector"}

# Search database connections  
SEARCH_DB_CONFIG={"url": "http://localhost:9200", "index_name": "hybrid_search_fulltext"}

# Graph database connections
GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", "username": "neo4j", "password": "password"}
```

### **Individual Database Settings**
Traditional environment variables for specific databases:
```bash
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_USERNAME=
ELASTICSEARCH_PASSWORD=

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=
```

## 🎯 **Easy Database Switching**

The configuration is designed for easy switching:

```bash
# Current setup: OpenAI + Qdrant + Elasticsearch + Neo4j
LLM_PROVIDER=openai
VECTOR_DB=qdrant
SEARCH_DB=elasticsearch  
GRAPH_DB=neo4j

# Switch to: Ollama + Neo4j (all-in-one)
LLM_PROVIDER=ollama
VECTOR_DB=neo4j
SEARCH_DB=elasticsearch
GRAPH_DB=neo4j

# Switch to: OpenAI + Kuzu + OpenSearch
LLM_PROVIDER=openai  
VECTOR_DB=opensearch
SEARCH_DB=opensearch
GRAPH_DB=kuzu
```

## 📝 **Configuration Best Practices**

### **Development Setup**
1. **Start simple**: Use Neo4j for both vector and graph storage
2. **Use defaults**: Copy `env-sample.txt` to `.env` and adjust API keys
3. **Test locally**: Use localhost connections before cloud deployment

### **Production Setup**
1. **Separate concerns**: Use specialized databases (Qdrant for vectors, Elasticsearch for search)
2. **Secure connections**: Use proper authentication and HTTPS where supported
3. **Performance tuning**: Adjust timeout values and batch sizes

### **Schema Configuration**
1. **Start with default**: Use `SCHEMA_NAME=default` for comprehensive extraction
2. **Customize gradually**: Create domain-specific schemas as needed
3. **Test thoroughly**: Compare different schema approaches on your content

## 🔗 **Related Documentation**

- **Source paths**: `docs/SOURCE-PATH-EXAMPLES.md`
- **Schema examples**: `docs/SCHEMA-EXAMPLES.md`
- **Timeout configuration**: `docs/TIMEOUT-CONFIGURATIONS.md`
- **Neo4j URLs**: `docs/Neo4j-URLs.md`
- **Vector dimensions**: `docs/VECTOR-DIMENSIONS.md`

## 🚀 **Quick Start**

1. **Copy template**: `cp flexible-graphrag/env-sample.txt .env`
2. **Set API key**: Add your OpenAI API key to `OPENAI_API_KEY`
3. **Choose databases**: Uncomment your preferred database options
4. **Update connections**: Modify database URLs/credentials as needed
5. **Test configuration**: Run a small test to verify everything works

The modular 5-section structure makes it easy to understand and modify any part of the configuration without affecting others.
