# Framework Integration (LlamaIndex and LangChain)

This document describes how LlamaIndex and LangChain integrate with flexible-graphrag as full peer frameworks — covering graph, vector, search, chunking, KG extraction, and hybrid retrieval.

## Overview

LangChain is not just a retrieval add-on; it is a **first-class backend** for every pipeline stage. Each stage can run on either LlamaIndex or LangChain independently:

| Stage | LlamaIndex | LangChain |
|---|---|---|
| **Chunking** | `SentenceSplitter` | `RecursiveCharacterTextSplitter` (+ 5 other splitters) |
| **KG Extraction** | `SchemaLLMPathExtractor` / `DynamicLLMPathExtractor` | `LLMGraphTransformer` |
| **Property Graph ingestion** | `PropertyGraphIndex` | `add_graph_documents()` via LC graph store |
| **Property Graph retrieval** | `VectorContextRetriever` | `TextToGraphQueryRetriever` (Cypher/AQL/GSQL/SurrealQL) |
| **Vector ingestion** | `VectorStoreIndex` | LC vector store `add_documents()` |
| **Vector retrieval** | `VectorIndexRetriever` | `LangChainVectorStoreRetriever` |
| **Search ingestion** | ES/OpenSearch LI index | LC `add_documents()` |
| **Search retrieval** | LI BM25 / ES retriever | LC BM25 / ES / OpenSearch retriever |
| **Hybrid fusion** | `QueryFusionRetriever` | `EnsembleRetriever` (RRF) |

## Framework Configuration

```env
# -- Pipeline stage pickers ---------------------------
CHUNKER_BACKEND=llamaindex        # llamaindex | langchain
GRAPH_BACKEND=llamaindex          # llamaindex | langchain  (auto=langchain for LC-only stores)
VECTOR_BACKEND=llamaindex         # llamaindex | langchain
SEARCH_BACKEND=llamaindex         # llamaindex | langchain
KG_EXTRACTOR_BACKEND=llamaindex   # llamaindex | langchain
RETRIEVAL_FUSION=llamaindex       # llamaindex | langchain (EnsembleRetriever/RRF)

# -- LC-specific splitter (when CHUNKER_BACKEND=langchain) --
LC_SPLITTER_TYPE=recursive        # recursive | character | token | markdown | python | sentence_transformers
```

`GRAPH_BACKEND` is **auto-selected** to `langchain` when `PG_GRAPH_DB` is set to a LangChain-only store (ArangoDB, Apache AGE, HugeGraph, SurrealDB, TigerGraph, Cosmos Gremlin, Spanner).

## Full Architecture Diagram

```
                              User Query
                                   |
                   +---------------+-----------------+
                   |        Retrieval Fusion         |
                   |   (LI QueryFusion or            |
                   |    LC EnsembleRetriever)        |
                   +-+--+--+--+--+--+--+-------------+
                     |  |  |  |  |  |
     +---------------+  |  |  |  |  +------------------+
     |          +--------+  |  |  +----------+          |
     |          |           |  +------+      |          |
     |          |           |         |      |          |
  +--+------++--+---++------+--++-----+--++--+-----++---+------+
  | Vector  || Search|| Prop.   ||  RDF   || Neigh- || PG Vec. |
  | Retr.   ||  BM25/|| Graph   ||  Graph || borhood|| (Entity |
  | LI / LC ||  ES/OS|| LI / LC ||  SPARQL||  Cypher||  Vector)|
  +----+----++-------+| (text-  ||  (LC)  ||  (LC)  ||  (LC)   |
       |               | to-     |+--------++--------++--------+
       |               | query)  |     |          |        |
  Vector DB            +----+----+     |          +--------+
  (Qdrant, Milvus,          |      RDF Store       Neo4j
   Weaviate, etc.)     Property   (GraphDB,      (entity-level
                       Graph DB    Fuseki,        __Entity__
                       (Neo4j,     Oxigraph,      vector index)
                        ArangoDB,  Neptune RDF)
                        AGE, etc.)

                  +----------------------------+
                  |     Ingest Pipeline        |
                  +----------------------------+
                  |  LI readers (always)       |
                  |  -> Chunker (LI or LC)     |
                  |  -> Embedder (LI or LC)    |
                  |  -> KG Extractor (LI or LC)|
                  |  -> Vector store update    |
                  |  -> Search index update    |
                  |  -> Property graph update  |
                  |  -> RDF store update       |
                  +----------------------------+
```

## Retriever Layer Architecture

Retrievers follow a **two-layer prefix convention**:

| Prefix | Layer | Base class | Purpose |
|---|---|---|---|
| `lc_` | 0 — pure LC | `langchain_core.BaseRetriever` | Passed directly to `EnsembleRetriever` |
| `li_` | 1 — LI wrapper | `llama_index.BaseRetriever` | Used with `QueryFusionRetriever`; `.as_lc_retriever()` for hybrid |

Bridge classes in `langchain/retriever_bridge.py`:
- `LItoLCRetriever` — wraps an LI retriever so LC ensemble can call it
- `LCBackedLIRetriever` — wraps an LC retriever into LI interface for `QueryFusionRetriever`

**Source labeling**: every result carries the database it came from (e.g. *"company-ontology.txt | Qdrant vector"*, *"company-ontology.txt | Ontotext GraphDB rdf graph"*). `LoggingRetriever._postprocess()` / `LCLoggingRetriever._tag_docs()` inject `_retriever_label` into node metadata; `query_engine.py` builds the display string.

## Property Graph Databases

### LangChain-Only Stores

These stores only work with `GRAPH_BACKEND=langchain` (auto-selected when `PG_GRAPH_DB` is set to one of these):

<table>
<colgroup>
  <col style="width:160px">
  <col>
  <col style="width:90px">
  <col style="width:130px">
  <col>
</colgroup>
<thead><tr>
  <th><code>PG_GRAPH_DB</code></th>
  <th>Database</th>
  <th>Docker Port</th>
  <th>Query Language</th>
  <th>Key Notes</th>
</tr></thead>
<tbody>
<tr><td><code>arangodb</code></td><td>ArangoDB</td><td>8529</td><td>AQL</td><td><code>ArangoGraph</code> + <code>GraphCypherQAChain</code></td></tr>
<tr><td><code>apache_age</code></td><td>Apache AGE</td><td>5434</td><td>Cypher</td><td><code>_AGEGraphFixed</code> dollar-quoting bypass; <code>_extract_return_aliases()</code></td></tr>
<tr><td><code>cosmos_gremlin</code></td><td>Azure Cosmos DB / TinkerPop</td><td>8182</td><td>Gremlin</td><td><code>GremlinGraph</code></td></tr>
<tr><td><code>hugegraph</code></td><td>Apache HugeGraph</td><td>8082</td><td>openCypher</td><td>Custom <code>add_graph_documents</code>; <code>_safe_id</code> replaces spaces; Hubble UI at 8085</td></tr>
<tr><td><code>surrealdb</code></td><td>SurrealDB</td><td>8010</td><td>SurrealQL</td><td><code>add_graph_documents</code> injects <code>name</code>/<code>type</code>; async client; Surrealist UI at 8011</td></tr>
<tr><td><code>tigergraph</code></td><td>TigerGraph Community</td><td>9002</td><td>GSQL</td><td><code>_ensure_graph()</code> auto-create; <code>nlqs_host</code> bypass; GraphStudio at 14240</td></tr>
<tr><td><code>spanner</code></td><td>Google Cloud Spanner</td><td>9010/9020</td><td>Spanner Graph (Cypher)</td><td>Emulator supported; <code>SPANNER_EMULATOR_HOST=localhost:9010</code></td></tr>
</tbody>
</table>

### Supported with Both LlamaIndex and LangChain

These work with either `GRAPH_BACKEND=llamaindex` or `GRAPH_BACKEND=langchain`:

<table>
<colgroup>
  <col style="width:180px">
  <col style="width:230px">
  <col>
  <col>
</colgroup>
<thead><tr>
  <th><code>PG_GRAPH_DB</code></th>
  <th>LI Ingestion</th>
  <th>LC Retrieval</th>
  <th>Notes</th>
</tr></thead>
<tbody>
<tr><td><code>neo4j</code></td><td><code>PropertyGraphIndex</code></td><td><code>GraphCypherQAChain</code></td><td>Shared bolt connection</td></tr>
<tr><td><code>arcadedb</code></td><td><code>ArcadeDBPropertyGraphStore</code></td><td>Custom Cypher adapter</td><td>Remote + embedded modes</td></tr>
<tr><td><code>falkordb</code></td><td><code>FalkorDBPropertyGraphStore</code></td><td><code>FalkorDBGraph</code></td><td></td></tr>
<tr><td><code>memgraph</code></td><td><code>MemgraphPropertyGraphStore</code></td><td><code>MemgraphGraph</code></td><td></td></tr>
<tr><td><code>nebula</code></td><td><code>NebulaPropertyGraphStore</code></td><td><code>NebulaGraph</code></td><td>Dynamic schema patch for arbitrary props</td></tr>
<tr><td><code>neptune</code></td><td><code>NeptuneDatabase</code></td><td><code>NeptuneGraph</code></td><td>AWS cloud</td></tr>
<tr><td><code>neptune_analytics</code></td><td><code>NeptuneAnalytics</code></td><td><code>NeptuneAnalyticsGraph</code></td><td>AWS cloud</td></tr>
<tr><td><code>ladybug</code></td><td><code>LadybugPropertyGraphStore</code></td><td><code>LadybugGraph</code> (via <code>langchain-ladybug</code>)</td><td>Embedded</td></tr>
</tbody>
</table>

### LangChain PG Retrieval Components

When `GRAPH_BACKEND=langchain`, three retriever types are available:

1. **`TextToGraphQueryRetriever`** (`li_graph_qa_retriever.py` / `lc_graph_retriever.py`) — NL -> Cypher/AQL/GSQL/SurrealQL via LLM; uses per-store custom prompt templates
2. **`GraphNeighborhoodRetriever`** (`li_neighborhood_retriever.py`) — walks graph neighbors from seed entities; document text chunks score 2.0, entity stubs score 1.0
3. **`GraphEntityVectorRetriever`** (`langchain_retriever_wrapper.py`) — semantic entity lookup via Neo4j vector index (Neo4j only)

**Routing rules:**
- `TextToGraphQueryRetriever` is **auto-enabled** for all LC non-vector stores (ArangoDB, AGE, HugeGraph, SurrealDB, TigerGraph, Cosmos Gremlin, Spanner) and for Neo4j when `LANGCHAIN_PG_VECTOR_SEARCH=false` (default). It is suppressed for Neo4j when `LANGCHAIN_PG_VECTOR_SEARCH=true`; set `USE_LC_TEXT_TO_GRAPH=true` to re-enable it alongside vector retrieval.
- `GraphNeighborhoodRetriever` is Neo4j only and auto-enabled when `LANGCHAIN_PG_VECTOR_SEARCH=true`.
- `GraphEntityVectorRetriever` is Neo4j only and off by default; `LANGCHAIN_PG_VECTOR_SEARCH=true` also auto-enables `USE_PG_NEIGHBORHOOD`.

```env
USE_LC_TEXT_TO_GRAPH=true         # only needed for Neo4j when LANGCHAIN_PG_VECTOR_SEARCH=true
USE_PG_NEIGHBORHOOD=true          # default true; auto-enabled when LANGCHAIN_PG_VECTOR_SEARCH=true
LANGCHAIN_PG_VECTOR_SEARCH=false  # GraphEntityVectorRetriever (Neo4j only, default false)
```

## RDF / SPARQL Stores

RDF stores are always accessed via LangChain SPARQL chains (controlled by `RDF_GRAPH_DB`):

<table>
<colgroup>
  <col style="width:150px">
  <col style="width:50px">
  <col style="width:230px">
  <col>
</colgroup>
<thead><tr>
  <th><code>RDF_GRAPH_DB</code></th>
  <th>Port</th>
  <th>Adapter</th>
  <th>Chain Type</th>
</tr></thead>
<tbody>
<tr><td><code>graphdb</code></td><td>7200</td><td><code>GraphDBLangChainAdapter</code></td><td><code>_GraphDBQAChain</code> (custom <code>OntotextGraphDBQAChain</code> subclass)</td></tr>
<tr><td><code>fuseki</code></td><td>3030</td><td><code>FusekiLangChainAdapter</code></td><td><code>_GenericSparqlQAChain</code> (<code>GraphSparqlQAChain</code> subclass)</td></tr>
<tr><td><code>oxigraph</code></td><td>7878</td><td><code>OxigraphLangChainAdapter</code></td><td><code>_GenericSparqlQAChain</code></td></tr>
<tr><td><code>neptune_rdf</code></td><td>8182</td><td><code>NeptuneRDFAdapter</code></td><td><code>_GenericSparqlQAChain</code></td></tr>
</tbody>
</table>

All adapters share:
- `_ensure_sparql_prefixes()` — auto-injects missing `PREFIX` declarations (kg:, onto:, company:, common:, rdfs:, rdf:, xsd:, owl:)
- Live schema introspection at startup (predicates + types fetched via `SELECT DISTINCT ?p / ?t`)
- SPARQL broad-fallback retry: on 0 rows, extracts shortest entity keyword and retries bi-directional UNION

## Vector Stores

Set `VECTOR_DB` to pick the store; set `VECTOR_BACKEND=langchain` to use LC adapters:

<table>
<colgroup>
  <col style="width:140px">
  <col style="width:200px">
  <col style="width:200px">
  <col>
</colgroup>
<thead><tr>
  <th><code>VECTOR_DB</code></th>
  <th>LI Adapter</th>
  <th>LC Adapter</th>
  <th>Notes</th>
</tr></thead>
<tbody>
<tr><td><code>qdrant</code></td><td><code>QdrantVectorStore</code></td><td><code>QdrantVectorStore</code> (LC)</td><td>Default recommended</td></tr>
<tr><td><code>elasticsearch</code></td><td><code>ElasticsearchStore</code></td><td><code>ElasticsearchStore</code> (LC)</td><td></td></tr>
<tr><td><code>opensearch</code></td><td><code>OpensearchVectorClient</code></td><td>LC OpenSearch adapter</td><td></td></tr>
<tr><td><code>milvus</code></td><td><code>MilvusVectorStore</code></td><td><code>Milvus</code> (LC)</td><td>gRPC host/port; <code>auto_id=True</code></td></tr>
<tr><td><code>weaviate</code></td><td><code>WeaviateVectorStore</code></td><td><code>WeaviateVectorStore</code> (LC)</td><td>Sync client in FastAPI; <code>Filter.by_property</code> delete</td></tr>
<tr><td><code>chroma</code></td><td><code>ChromaVectorStore</code></td><td><code>Chroma</code> (LC)</td><td>HTTP client or persist mode</td></tr>
<tr><td><code>pinecone</code></td><td><code>PineconeVectorStore</code></td><td><code>PineconeVectorStore</code> (LC)</td><td>Cloud index</td></tr>
<tr><td><code>postgres</code></td><td><code>PGVectorStore</code></td><td><code>PGVector</code> (LC)</td><td><code>langchain_pg_collection</code>/<code>embedding</code> tables</td></tr>
<tr><td><code>lancedb</code></td><td><code>LanceDBVectorStore</code></td><td><code>LanceDB</code> (LC)</td><td><code>uri</code>/<code>table_name</code> new API; <code>inspect.signature</code> detection</td></tr>
<tr><td><code>neo4j</code></td><td><code>Neo4jVectorStore</code></td><td><code>Neo4jVector</code> (LC)</td><td>Embedded in graph store</td></tr>
</tbody>
</table>

Per-store config: `{TYPE}_VECTOR_DB_CONFIG={"host":...}` (e.g. `QDRANT_VECTOR_DB_CONFIG`, `MILVUS_VECTOR_DB_CONFIG`)

## Search / BM25 Stores

Set `SEARCH_DB`; set `SEARCH_BACKEND=langchain` for LC adapters:

| `SEARCH_DB` | LI | LC |
|---|---|---|
| `bm25` | LI `BM25Retriever` | LC `BM25Retriever` (in-memory) |
| `elasticsearch` | LI ES client | `ElasticsearchStore` BM25 |
| `opensearch` | LI OS client | LC OpenSearch BM25 |

Per-store config: `{TYPE}_SEARCH_DB_CONFIG={"host":...}`

## Chunker Backends

```env
CHUNKER_BACKEND=llamaindex   # SentenceSplitter (default)
CHUNKER_BACKEND=langchain    # LC text splitter (LC_SPLITTER_TYPE selects which)

LC_SPLITTER_TYPE=recursive   # RecursiveCharacterTextSplitter
LC_SPLITTER_TYPE=character   # CharacterTextSplitter
LC_SPLITTER_TYPE=token       # TokenTextSplitter
LC_SPLITTER_TYPE=markdown    # MarkdownTextSplitter
LC_SPLITTER_TYPE=python      # PythonCodeTextSplitter
LC_SPLITTER_TYPE=sentence_transformers  # HuggingFace sentence-transformers splitter
```

LC chunks are stashed as `system._last_lc_chunks` and passed directly to LC vector/search stores — no re-embedding.

## KG Extraction Backends

```env
KG_EXTRACTOR_BACKEND=llamaindex   # SchemaLLMPathExtractor (default) / DynamicLLMPathExtractor
KG_EXTRACTOR_BACKEND=langchain    # LLMGraphTransformer
```

If `KG_EXTRACTOR_BACKEND=langchain` and `GRAPH_BACKEND=langchain`, LC `GraphDocument` objects are written directly to the LC graph store via `add_graph_documents()`. If `KG_EXTRACTOR_BACKEND=llamaindex` and `GRAPH_BACKEND=langchain`, the LI triplets are converted to `GraphDocument` via `aingest_li_to_lc_graph()`.

## `skip_graph` Parameter

Pass `skip_graph=true` on a per-ingest call to skip KG extraction and all graph store writes (both property graph and RDF) for that document only. Vector and full-text stores are still updated. Available from the UI, REST API (`POST /api/ingest`, `/api/ingest-text`, `/api/test-sample`), MCP tools (`ingest_documents`, `ingest_text`, `test_with_sample`), and the Python API (`backend.ingest_documents(skip_graph=True)`, `backend.ingest_text(skip_graph=True)`). Also persisted per-datasource in the incremental sync config.

To disable graph extraction globally on every ingest: set `ENABLE_KNOWLEDGE_GRAPH=false` in `.env`. Previously ingested graph data is not deleted in either case — hybrid search and AI Q&A continue to return results from earlier extractions.

## Retrieval Fusion

```env
RETRIEVAL_FUSION=llamaindex   # QueryFusionRetriever, mode=relative_score (default)
RETRIEVAL_FUSION=langchain    # EnsembleRetriever (RRF); only activates when ALL retrievers are LC-backed
```

`EnsembleRetriever` lives in `langchain_classic.retrievers.ensemble`. Falls back silently to `QueryFusionRetriever` if any LI-native retriever is present.

> **Note**: The local `flexible-graphrag/langchain/` package folder shadows the pip-installed `langchain` package. Always use `langchain_classic` / `langchain_core` for the real LangChain packages inside the codebase.

## Configuration Reference — Framework Env Vars

<table>
<colgroup>
  <col style="width:260px">
  <col style="width:120px">
  <col>
</colgroup>
<thead><tr>
  <th>Variable</th>
  <th>Default</th>
  <th>Values</th>
</tr></thead>
<tbody>
<tr><td><code>CHUNKER_BACKEND</code></td><td><code>llamaindex</code></td><td><code>llamaindex</code>, <code>langchain</code></td></tr>
<tr><td><code>LC_SPLITTER_TYPE</code></td><td><code>recursive</code></td><td><code>recursive</code>, <code>character</code>, <code>token</code>, <code>markdown</code>, <code>python</code>, <code>sentence_transformers</code></td></tr>
<tr><td><code>GRAPH_BACKEND</code></td><td><code>llamaindex</code></td><td><code>llamaindex</code>, <code>langchain</code> (auto for LC-only stores)</td></tr>
<tr><td><code>VECTOR_BACKEND</code></td><td><code>llamaindex</code></td><td><code>llamaindex</code>, <code>langchain</code></td></tr>
<tr><td><code>SEARCH_BACKEND</code></td><td><code>llamaindex</code></td><td><code>llamaindex</code>, <code>langchain</code></td></tr>
<tr><td><code>KG_EXTRACTOR_BACKEND</code></td><td><code>llamaindex</code></td><td><code>llamaindex</code>, <code>langchain</code></td></tr>
<tr><td><code>RETRIEVAL_FUSION</code></td><td><code>llamaindex</code></td><td><code>llamaindex</code>, <code>langchain</code></td></tr>
<tr><td><code>USE_LC_TEXT_TO_GRAPH</code></td><td><code>false</code></td><td>For Neo4j + <code>LANGCHAIN_PG_VECTOR_SEARCH=true</code> only: re-add <code>TextToGraphQueryRetriever</code> alongside vector+neighborhood. Auto-enabled for all other LC stores and for Neo4j with <code>LANGCHAIN_PG_VECTOR_SEARCH=false</code>.</td></tr>
<tr><td><code>USE_PG_NEIGHBORHOOD</code></td><td><code>true</code></td><td><code>GraphNeighborhoodRetriever</code> — k-hop walk (Neo4j only); auto-enabled when <code>LANGCHAIN_PG_VECTOR_SEARCH=true</code></td></tr>
<tr><td><code>LANGCHAIN_PG_VECTOR_SEARCH</code></td><td><code>false</code></td><td><code>GraphEntityVectorRetriever</code> — entity vector seeding (Neo4j only); auto-enables <code>USE_PG_NEIGHBORHOOD</code>; suppresses text-to-query unless <code>USE_LC_TEXT_TO_GRAPH=true</code></td></tr>
<tr><td><code>USE_SYNONYM_EXPLODER</code></td><td><code>false</code></td><td>Expand query with LLM-generated synonyms (opt-in)</td></tr>
<tr><td><code>SYNONYM_EXPLODER_SCOPE</code></td><td><code>none</code></td><td>Comma-separated retriever tags to apply synonym expansion</td></tr>
</tbody>
</table>

## References

- [LangChain Graph Integrations](https://python.langchain.com/docs/integrations/graphs/)
- [LangChain Vector Stores](https://python.langchain.com/docs/integrations/vectorstores/)
- [LlamaIndex Property Graph Guide](https://docs.llamaindex.ai/en/stable/module_guides/indexing/lpg_index_guide/)
- [RDF Store User Guide](../../DATABASES/RDF/RDF-STORE-USER-GUIDE.md)
- [Port Mappings](../PORT-MAPPINGS.md)
