# Database Configuration

Flexible GraphRAG uses four database types for hybrid search. Each is selected by a picker env var and configured via a per-store JSON config.

| Database Type | Purpose | Picker Var | Count |
|---|---|---|---|
| Property Graph | Knowledge graph (GraphRAG), Cypher / SPARQL / Gremlin / GSQL | `PG_GRAPH_DB` | 15 stores (8 LI+LC, 1 LI-only, 6 LC-only) |
| RDF Graph | Knowledge graph (GraphRAG), SPARQL, ontology reasoning | `RDF_GRAPH_DB` | 4 stores |
| Vector | Semantic similarity | `VECTOR_DB` | 10 stores |
| Search (full-text) | BM25, keyword | `SEARCH_DB` | 3 stores |

*Note: RDF Ontologies are supported for both Property Graph and RDF Graph databases.*

## Framework Backends

Each pipeline stage can independently run on **LlamaIndex** (default) or **LangChain**:

```env
GRAPH_BACKEND=llamaindex        # llamaindex | langchain
VECTOR_BACKEND=llamaindex       # llamaindex | langchain
SEARCH_BACKEND=llamaindex       # llamaindex | langchain
CHUNKER_BACKEND=llamaindex      # llamaindex | langchain
KG_EXTRACTOR_BACKEND=llamaindex # llamaindex | langchain
RETRIEVAL_FUSION=llamaindex     # llamaindex | langchain
```

LangChain-only property graph stores (ArangoDB, Apache AGE, HugeGraph, SurrealDB, TigerGraph, Cosmos Gremlin) **auto-select** `GRAPH_BACKEND=langchain`. Spanner uses LlamaIndex only (`llama-index-spanner`; LangChain's `langchain-google-spanner` is incompatible with `langchain-core>=1.0`).

## Per-Store Configuration

Use `{TYPE}_*_DB_CONFIG` for per-store settings:

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
```

## Detailed Configuration Pages

- **[Property Graph Databases](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md)** — all 15 stores (8 both LI+LC, 1 LI-only, 6 LC-only), database and framework config, `skip_graph`
- **[RDF Graph Databases](../CONFIGURATION/CONFIG-RDF-STORES.md)** — Fuseki, GraphDB, Oxigraph, Neptune RDF; database and framework config, `skip_graph`
- **[Vector Databases](../CONFIGURATION/CONFIG-VECTOR-DATABASES.md)** — 10 stores, LI and LC backends, dimension compatibility
- **[Search Databases](../CONFIGURATION/CONFIG-SEARCH-DATABASES.md)** — BM25, Elasticsearch, OpenSearch; LI and LC backends
- **[LangChain Configuration](../CONFIGURATION/LANGCHAIN-CONFIGURATION.md)** — framework pickers, retriever toggles, synonym expansion, scope tags
- **[LangChain Architecture](../ADVANCED/LANGCHAIN/LANGCHAIN-GRAPH-INTEGRATION.md)** — full dual-framework architecture, retriever layers, source labels in results

## Per-Store Setup Guides

Detailed setup instructions for cloud-hosted and less common stores:

| Store | Guide |
|---|---|
| Amazon Neptune Database | [NEPTUNE-SETUP.md](GRAPH-DATABASES/NEPTUNE-SETUP.md) |
| Amazon Neptune Analytics | [NEPTUNE-SETUP.md](GRAPH-DATABASES/NEPTUNE-SETUP.md) |
| Azure Cosmos DB for Gremlin | [COSMOS-GREMLIN-SETUP.md](GRAPH-DATABASES/COSMOS-GREMLIN-SETUP.md) |
| Google Cloud Spanner Graph | [SPANNER-SETUP.md](GRAPH-DATABASES/SPANNER-SETUP.md) |
| NebulaGraph | [NEBULA-SETUP.md](GRAPH-DATABASES/NEBULA-SETUP.md) |
| NebulaGraph LangChain Schema | [NEBULA-LANGCHAIN-SETUP.md](GRAPH-DATABASES/NEBULA-LANGCHAIN-SETUP.md) |
| Neo4j | [README-neo4j.md](GRAPH-DATABASES/README-neo4j.md) |

## PostgreSQL

- **[PostgreSQL Setup](POSTGRES-SETUP.md)** — pgvector store (port 5433) and incremental state DB; pgAdmin at port 5050
