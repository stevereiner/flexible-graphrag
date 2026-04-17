# Property Graph Database Configuration

**Configuration**: Set via `GRAPH_DB` and `GRAPH_DB_CONFIG` environment variables

## Neo4j (Recommended)

Primary knowledge graph storage with Cypher querying.

- Dashboard: Neo4j Browser (http://localhost:7474)

```bash
GRAPH_DB=neo4j
GRAPH_DB_CONFIG={"uri": "bolt://localhost:7687", "username": "neo4j", "password": "your_password"}
```

## ArcadeDB

Multi-model database supporting graph, document, key-value, and search capabilities.

- Dashboard: ArcadeDB Studio (http://localhost:2480)

```bash
GRAPH_DB=arcadedb
GRAPH_DB_CONFIG={"host": "localhost", "port": 2480, "username": "root", "password": "password", "database": "flexible_graphrag", "query_language": "sql"}
```

## FalkorDB

Super fast graph database using GraphBLAS for sparse adjacency matrix representation.

- Dashboard: FalkorDB Browser (http://localhost:3001)

```bash
GRAPH_DB=falkordb
GRAPH_DB_CONFIG={"url": "falkor://localhost:6379", "database": "falkor"}
```

## Ladybug

Embedded property graph database (Cypher, single `.lbug` file) with optional structured schema and HNSW vector index.

- Dashboard: Ladybug Explorer (http://localhost:7003, optional Docker)

```bash
GRAPH_DB=ladybug
GRAPH_DB_CONFIG={"db_dir": "./ladybug", "db_file": "database.lbug", "use_vector_index": true, "has_structured_schema": false, "strict_schema": false}
```

Individual env vars also supported: `LADYBUG_DB_DIR`, `LADYBUG_DB_FILE`, `LADYBUG_USE_VECTOR_INDEX`, `LADYBUG_STRUCTURED_SCHEMA`, `LADYBUG_STRICT_SCHEMA`

## MemGraph

Real-time graph database with native support for streaming data and advanced graph algorithms.

- Dashboard: MemGraph Lab (http://localhost:3002)

```bash
GRAPH_DB=memgraph
GRAPH_DB_CONFIG={"url": "bolt://localhost:7687", "username": "", "password": ""}
```

## NebulaGraph

Distributed graph database designed for large-scale data with horizontal scalability.

- Dashboard: NebulaGraph Studio (http://localhost:7001)

```bash
GRAPH_DB=nebula
GRAPH_DB_CONFIG={"space": "flexible_graphrag", "host": "localhost", "port": 9669, "username": "root", "password": "nebula"}
```

## Amazon Neptune

Fully managed graph database service supporting both property graph and RDF models.

- Dashboard: Graph-Explorer (http://localhost:3007) or Neptune Workbench (AWS Console)

```bash
GRAPH_DB=neptune
GRAPH_DB_CONFIG={"host": "your-cluster.region.neptune.amazonaws.com", "port": 8182}
```

## Amazon Neptune Analytics

Serverless graph analytics engine for large-scale graph analysis with openCypher support.

- Dashboard: Graph-Explorer (http://localhost:3007) or Neptune Workbench (AWS Console)

```bash
GRAPH_DB=neptune_analytics
GRAPH_DB_CONFIG={"graph_identifier": "g-xxxxx", "region": "us-east-1"}
```

## Disable Graph (RAG-only mode)

```bash
GRAPH_DB=none
ENABLE_KNOWLEDGE_GRAPH=false
```

See [Neo4j Guide](../DATABASES/GRAPH-DATABASES/README-neo4j.md) and [Knowledge Graph Extractors](../DATABASES/GRAPH-DATABASES/KNOWLEDGE-GRAPH-EXTRACTORS.md) for more details.
