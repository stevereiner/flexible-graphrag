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

### NLTK data for the LlamaIndex chunker (`NLTK_DATA`)

```env
#NLTK_DATA=./nltk_data          # optional: where SentenceSplitter finds NLTK's sentence tokenizer and stopwords
```

LlamaIndex's `SentenceSplitter` (`CHUNKER_BACKEND=llamaindex`, the default) uses NLTK data that ships inside the
llama-index-core package. When that package was installed with **uv** (which hardlinks installed files to its cache),
**nltk 3.10.4 and later refuse to open it**: `Security Violation [pathsec.open]: refusing multiply-linked file ...
nltk_cache\corpora\stopwords\english`.

So when `NLTK_DATA` is not set, the backend (and the Langflow components) make a plain copy of that data once, in the
user cache folder (`flexible-graphrag/nltk_data/<llama-index-core version>`), and use it. Nothing to configure. The
backend, Langflow flow mode and the CocoIndex pipeline (also `cocoindex update` from the command line) all do this.

Set `NLTK_DATA` only to use a folder of your own (a relative path is from the folder the backend starts in): an empty
folder is fine, the data is downloaded into it on first use (needs internet access once).

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

**Ingest and UI defaults** (v0.9.0+): three optional settings, `true` when not set.
`env-sample.txt` (graph database section) sets `DEFAULT_ENABLED_GRAPH=false` and `DEFAULT_ENABLED_RDF=false`, so
new rows start with search + vector only and a row's graphs are added when wanted; a REST or MCP ingest that
doesn't pass `enabled_graph` / `enabled_rdf` then builds no graphs either. The integration test harnesses set
both to `true` for their own backends.

| Setting | What it decides |
|---|---|
| `DEFAULT_ENABLED_GRAPH` | Whether an ingest that doesn't say (`enabled_graph` not given) builds the property graph (`PG_GRAPH_DB`); where the Processing tab's **Graph** column starts for new rows |
| `DEFAULT_ENABLED_RDF` | The same for the RDF graph (`RDF_GRAPH_DB`, `enabled_rdf`) and the **RDF** column |
| `DEFAULT_RECURSIVE` | Where the **Deep** checkbox of the Alfresco, Nuxeo and Box forms starts |

The UIs read them from `GET /api/ui-defaults` (see the
[auto-sync API reference](../DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/API-REFERENCE.md#ui-defaults)).

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
