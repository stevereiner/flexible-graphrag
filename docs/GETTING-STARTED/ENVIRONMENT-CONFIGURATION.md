# Environment Configuration Guide

This document explains how to configure Flexible GraphRAG using environment variables and configuration files.

## Configuration Files

| File | Purpose |
|---|---|
| `.env` | Your main configuration file — copy from `flexible-graphrag/env-sample.txt` |
| `flexible-graphrag/env-sample.txt` | Template with all options and inline examples |

## env-sample.txt Structure

The configuration file opens with **DB selection** and **framework config**, followed by per-service settings:

### Section 1: DB Selection

```env
PG_GRAPH_DB=neo4j               # Property graph: neo4j | arcadedb | falkordb | ladybug | memgraph |
                                 #   nebula | neptune | neptune_analytics | arangodb | apache_age |
                                 #   cosmos_gremlin | hugegraph | surrealdb | tigergraph | spanner | none
RDF_GRAPH_DB=none               # RDF store: fuseki | oxigraph | graphdb | neptune_rdf | none
VECTOR_DB=qdrant                # Vector: qdrant | elasticsearch | opensearch | chroma | milvus |
                                 #   weaviate | pinecone | postgres | lancedb | neo4j | none
SEARCH_DB=elasticsearch         # Search: bm25 | elasticsearch | opensearch | none
```

### Section 2: Framework Config

```env
CHUNKER_BACKEND=llamaindex      # llamaindex | langchain
GRAPH_BACKEND=llamaindex        # llamaindex | langchain (auto for LC-only stores)
VECTOR_BACKEND=llamaindex       # llamaindex | langchain
SEARCH_BACKEND=llamaindex       # llamaindex | langchain
KG_EXTRACTOR_BACKEND=llamaindex # llamaindex | langchain
RETRIEVAL_FUSION=llamaindex     # llamaindex | langchain (EnsembleRetriever/RRF)
```

### Sections 3+: Service-specific settings (LLM, embeddings, graph DBs, vector DBs, etc.)

---

## Database Configuration Patterns

### Per-Store Config (Recommended)

Use `{TYPE}_*_DB_CONFIG` — takes precedence over generic fallbacks:

```env
# Property graph
PG_GRAPH_DB=neo4j
NEO4J_GRAPH_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "password"}

# Vector
VECTOR_DB=qdrant
QDRANT_VECTOR_DB_CONFIG={"host": "localhost", "port": 6333}

# Search
SEARCH_DB=elasticsearch
ELASTICSEARCH_SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}

# RDF
RDF_GRAPH_DB=fuseki
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
```

### Individual Variables (Legacy)

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
ELASTICSEARCH_URL=http://localhost:9200
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

---

## Easy Database Switching

```env
# Current: OpenAI + Qdrant + Elasticsearch + Neo4j
LLM_PROVIDER=openai
VECTOR_DB=qdrant
SEARCH_DB=elasticsearch
PG_GRAPH_DB=neo4j

# Switch to: Ollama + Milvus (LC backend) + OpenSearch + ArangoDB (LC-only)
LLM_PROVIDER=ollama
VECTOR_DB=milvus
VECTOR_BACKEND=langchain
SEARCH_DB=opensearch
PG_GRAPH_DB=arangodb
# GRAPH_BACKEND auto-set to langchain for arangodb
```

---

## Configuration Best Practices

**Development:** Start with the defaults — Neo4j for graph, Qdrant for vector, Elasticsearch for search.

**Vector-only RAG** (no KG extraction, faster ingest):
```env
PG_GRAPH_DB=none
ENABLE_KNOWLEDGE_GRAPH=false
VECTOR_DB=qdrant
```

---

## Related Documentation

- [Property Graph Configuration](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md) — all 15 stores, LC-only stores, framework config
- [Vector Configuration](../CONFIGURATION/CONFIG-VECTOR-DATABASES.md) — 10 stores, dimension compatibility
- [Search Configuration](../CONFIGURATION/CONFIG-SEARCH-DATABASES.md) — BM25, ES, OpenSearch; LC backends
- [LangChain Configuration](../CONFIGURATION/LANGCHAIN-CONFIGURATION.md) — full dual-framework config, scope tags, synonym expansion
- [LLM & Embedding Config](../LLM/LLM-EMBEDDING-CONFIG.md) — all 13 LLM providers + embedding providers
- [Schema Examples](../CONFIGURATION/SCHEMA-EXAMPLES.md) — ontology-guided extraction examples
- [Source Paths](../DATA-SOURCES/SOURCE-PATH-EXAMPLES.md) — filesystem, cloud, repository path formats
- [Port Mappings](../ADVANCED/PORT-MAPPINGS.md) — all service ports to avoid conflicts
