# Database Configuration

Flexible GraphRAG uses three types of databases for its hybrid search capabilities. Each can be configured independently via environment variables.

| Database Type | Purpose | Env Var |
|---|---|---|
| Search (full-text) | BM25, Elasticsearch, OpenSearch | `SEARCH_DB` |
| Vector (semantic) | Qdrant, Chroma, Milvus, pgvector, and 6 more | `VECTOR_DB` |
| Property Graph (GraphRAG) | Neo4j, ArcadeDB, FalkorDB, Ladybug, and 4 more | `GRAPH_DB` |
| RDF Triple Store (ontology) | Fuseki, GraphDB, Oxigraph | `*_ENABLED` |

Select a database type for detailed configuration:

- **[Search Databases](../CONFIGURATION/CONFIG-SEARCH-DATABASES.md)** — BM25, Elasticsearch, OpenSearch
- **[Vector Databases](../CONFIGURATION/CONFIG-VECTOR-DATABASES.md)** — 10 supported databases, dimension compatibility notes
- **[Property Graph Databases](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md)** — 8 supported databases with KG extraction
- **[RDF Graph Databases](../CONFIGURATION/CONFIG-RDF-STORES.md)** — Fuseki, GraphDB, Oxigraph; ontology paths; storage modes
