# Databases

All supported database types — property graph, RDF triple stores, vector, search, and PostgreSQL.

## Property Graph Databases (`PG_GRAPH_DB`)

15 stores supported. Set `GRAPH_BACKEND=llamaindex|langchain` to choose the framework.

**LlamaIndex + LangChain** (`GRAPH_BACKEND=llamaindex` or `GRAPH_BACKEND=langchain`):
- [Neo4j](../DATABASES/GRAPH-DATABASES/README-neo4j.md) — Cypher, recommended default
- [ArcadeDB](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#arcadedb) — multi-model, remote + embedded
- [FalkorDB](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#falkordb) — GraphBLAS
- [Ladybug](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#ladybug) — embedded, single-file
- [Memgraph](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#memgraph) — streaming graph
- [NebulaGraph](../DATABASES/GRAPH-DATABASES/NEBULA-SETUP.md) — distributed
- [Amazon Neptune](../DATABASES/GRAPH-DATABASES/NEPTUNE-SETUP.md) — AWS managed (property graph)
- Amazon Neptune Analytics — serverless graph analytics

**LangChain-only** (auto-selects `GRAPH_BACKEND=langchain`):
- [ArangoDB](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#arangodb) — AQL; port 8529
- [Apache AGE](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#apache-age) — PostgreSQL + Cypher; port 5434
- [Azure Cosmos DB Gremlin](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md) — Gremlin; local via TinkerPop at port 8182
- [Apache HugeGraph](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#apache-hugegraph) — openCypher; port 8082
- [SurrealDB](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#surrealdb) — SurrealQL; port 8010
- [TigerGraph](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#tigergraph) — GSQL; port 9002/14240
- [Google Cloud Spanner](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md#google-cloud-spanner-graph) — openCypher; emulator at 9010/9020

Full config reference: [Property Graph Configuration](../CONFIGURATION/CONFIG-PROPERTY-GRAPH.md)

## RDF Triple Stores (`RDF_GRAPH_DB`)

SPARQL-based triple stores with OWL ontology support:

- [Apache Jena Fuseki](../DATABASES/RDF/RDF-STORE-USER-GUIDE.md) — port 3030
- [Ontotext GraphDB](../DATABASES/RDF/RDF-STORE-USER-GUIDE.md) — port 7200
- [Oxigraph](../DATABASES/RDF/RDF-STORE-USER-GUIDE.md) — port 7878, lightweight
- Amazon Neptune RDF — AWS managed SPARQL

RDF retrieval is always via LangChain SPARQL QA chains fused into hybrid search.

Full config reference: [RDF Store Configuration](../CONFIGURATION/CONFIG-RDF-STORES.md)

## Vector Databases (`VECTOR_DB`)

10 stores supported with both LlamaIndex and LangChain backends (`VECTOR_BACKEND=llamaindex|langchain`):

| Store | Port | Notes |
|---|---|---|
| [Qdrant](../DATABASES/VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) | 6333 | Recommended default |
| [Elasticsearch](../DATABASES/VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) | 9200 | Vector + BM25 combined |
| [OpenSearch](../DATABASES/VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) | 9201 | AWS-led ES fork |
| [Chroma](../DATABASES/VECTOR-DATABASES/CHROMA-DEPLOYMENT-MODES.md) | 8000 | Local / HTTP server modes |
| [Milvus](../DATABASES/VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) | 19530 | Distributed, gRPC |
| [Weaviate](../DATABASES/VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) | 8080 | Vector + BM25 hybrid |
| [Pinecone](../DATABASES/VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) | cloud | Serverless cloud index |
| [pgvector](../DATABASES/POSTGRES-SETUP.md) | 5433 | PostgreSQL vector extension |
| [LanceDB](../DATABASES/VECTOR-DATABASES/VECTOR-DATABASE-INTEGRATION.md) | embedded | Local file-based |
| [Neo4j](../DATABASES/GRAPH-DATABASES/README-neo4j.md) | 7687 | Embedded in graph store |

Full config reference: [Vector Configuration](../CONFIGURATION/CONFIG-VECTOR-DATABASES.md)

## Search Databases (`SEARCH_DB`)

3 stores supported with both LlamaIndex and LangChain backends (`SEARCH_BACKEND=llamaindex|langchain`):

| Store | Port | Notes |
|---|---|---|
| [Elasticsearch](../DATABASES/SEARCH-DATABASES.md) | 9200 | Full-text BM25 |
| [OpenSearch](../DATABASES/SEARCH-DATABASES.md) | 9201 | Full-text BM25 |
| [BM25](../DATABASES/SEARCH-DATABASES.md) | — | In-memory, no server required |

Full config reference: [Search Configuration](../CONFIGURATION/CONFIG-SEARCH-DATABASES.md)

## PostgreSQL

Two separate Postgres containers — do not confuse them:

| Container | Port | Purpose |
|---|---|---|
| `postgres-pgvector` | 5433 | pgvector vector store + incremental update state |
| `apache-age` | 5434 | Apache AGE property graph (separate DB) |

- [PostgreSQL Setup](../DATABASES/POSTGRES-SETUP.md) — pgvector + pgAdmin (port 5050) + incremental schema
