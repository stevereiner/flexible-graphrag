# Framework Configuration (LlamaIndex and LangChain)

LangChain is a **full peer framework** alongside LlamaIndex. Every pipeline stage — chunking, KG extraction, property graph ingestion/retrieval, vector store, search store, and hybrid fusion — can independently use LangChain via env var pickers.

For architecture details, retriever layers, and source labeling, see [LangChain Architecture](../ADVANCED/LANGCHAIN/LANGCHAIN-GRAPH-INTEGRATION.md).

---

## Installation

```bash
# Core — all 13 LLM providers as native LC clients, Neo4j Cypher retrieval, RDF SPARQL QA fusion,
#        LC vector stores (Qdrant, ES, Chroma, Pinecone, pgvector, LanceDB, Milvus, Weaviate, OpenSearch),
#        LC search (BM25, ES, OpenSearch)
uv pip install -e ".[langchain]"

# Extended graph backends — ArangoDB, Apache AGE, HugeGraph, TigerGraph, Cosmos Gremlin, Spanner
uv pip install --override extras-overrides.txt -e ".[langchain,langchain-extras]"

# SurrealDB — isolated group (dependency conflicts with langchain-extras)
uv pip install -e ".[surrealdb-extras]"
```

`extras-overrides.txt` pins `requests`, `urllib3`, `rich`, `setuptools`, and `decorator` to prevent hugegraph-python's outdated deps from downgrading the environment.

---

## Framework Pickers

Each stage defaults to LlamaIndex and can be switched to LangChain independently:

```env
CHUNKER_BACKEND=llamaindex        # llamaindex | langchain
KG_EXTRACTOR_BACKEND=llamaindex   # llamaindex | langchain
GRAPH_BACKEND=llamaindex          # llamaindex | langchain (auto for LC-only stores)
VECTOR_BACKEND=llamaindex         # llamaindex | langchain
SEARCH_BACKEND=llamaindex         # llamaindex | langchain
RETRIEVAL_FUSION=llamaindex       # llamaindex (QueryFusionRetriever) | langchain (EnsembleRetriever/RRF)
```

---

## Chunker Backend

```env
CHUNKER_BACKEND=langchain
LC_SPLITTER_TYPE=recursive    # recursive | character | token | markdown | python | sentence_transformers
```

LC chunks are stashed as `system._last_lc_chunks` and passed directly to LC vector/search stores — no re-embedding.

---

## KG Extraction Backend

```env
KG_EXTRACTOR_BACKEND=langchain   # uses LLMGraphTransformer
```

If `KG_EXTRACTOR_BACKEND=langchain` and `GRAPH_BACKEND=langchain`, LC `GraphDocument` objects are written directly to the LC graph store. If `KG_EXTRACTOR_BACKEND=llamaindex` and `GRAPH_BACKEND=langchain`, LI triplets are converted automatically.

---

## Property Graph Backend

```env
GRAPH_BACKEND=langchain
PG_GRAPH_DB=arangodb    # or any other supported store — see CONFIG-PROPERTY-GRAPH.md
```

### Property Graph Retriever Toggles

**`TextToGraphQueryRetriever`** (NL → Cypher/AQL/GSQL/SurrealQL):
- **Auto-enabled** for all LC non-vector stores (ArangoDB, Apache AGE, HugeGraph, SurrealDB, TigerGraph, Cosmos Gremlin, Spanner) — it is their only graph retrieval path.
- **Auto-enabled** for Neo4j LC when `LANGCHAIN_PG_VECTOR_SEARCH=false` (default).
- **Suppressed** for Neo4j when `LANGCHAIN_PG_VECTOR_SEARCH=true` (vector + neighborhood takes over). Set `USE_LC_TEXT_TO_GRAPH=true` to add it back alongside vector retrieval.

```env
USE_LC_TEXT_TO_GRAPH=true   # only needed for Neo4j when LANGCHAIN_PG_VECTOR_SEARCH=true
```

**`GraphNeighborhoodRetriever`** (k-hop graph walk from seed entities; Neo4j only):

```env
USE_PG_NEIGHBORHOOD=true    # default true; auto-enabled when LANGCHAIN_PG_VECTOR_SEARCH=true
```

**`GraphEntityVectorRetriever`** (entity-level vector seeding; Neo4j only; opt-in):

```env
LANGCHAIN_PG_VECTOR_SEARCH=false  # default; set true to enable
```

`LANGCHAIN_PG_VECTOR_SEARCH=true` doubles query time (~50s vs ~25s) and auto-enables `USE_PG_NEIGHBORHOOD`. Only enable if you want entity-level Neo4j vector similarity seeding.

### LangChain-Only Property Graph Stores

These stores auto-select `GRAPH_BACKEND=langchain`:

| `PG_GRAPH_DB` | Database | <div style="min-width:240px">Config env var</div> |
|---|---|---|
| `arangodb` | ArangoDB | `ARANGODB_GRAPH_DB_CONFIG` |
| `apache_age` | Apache AGE | `APACHE_AGE_GRAPH_DB_CONFIG` |
| `cosmos_gremlin` | Azure Cosmos DB Gremlin | `COSMOS_GREMLIN_GRAPH_DB_CONFIG` |
| `hugegraph` | Apache HugeGraph | `HUGEGRAPH_GRAPH_DB_CONFIG` |
| `surrealdb` | SurrealDB | `SURREALDB_GRAPH_DB_CONFIG` |
| `tigergraph` | TigerGraph | `TIGERGRAPH_GRAPH_DB_CONFIG` |
| `spanner` | Google Cloud Spanner | `SPANNER_GRAPH_DB_CONFIG` |

---

## Vector Backend

```env
VECTOR_BACKEND=langchain
VECTOR_DB=milvus    # or weaviate, lancedb, chroma, pinecone, postgres, etc.
MILVUS_VECTOR_DB_CONFIG={"host": "localhost", "port": 19530}
```

---

## Search Backend

```env
SEARCH_BACKEND=langchain
SEARCH_DB=elasticsearch
ELASTICSEARCH_SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}
```

---

## RDF SPARQL Retrieval

```env
RDF_GRAPH_DB=fuseki   # fuseki | graphdb | oxigraph | neptune_rdf | none
```

When `RDF_GRAPH_DB` is not `none`, a LangChain SPARQL QA chain (`TextToGraphQueryRetriever` → SPARQL) is fused into hybrid search automatically. No `USE_LANGCHAIN_RDF` flag needed — RDF retrieval is always via LangChain.

---

## Synonym Expansion

Expand queries for broader retrieval coverage (opt-in — disabled by default). `SYNONYM_EXPLODER_SCOPE` is a comma-separated list of retriever tags that limits which retrievers receive the expanded queries:

```env
USE_SYNONYM_EXPLODER=false          # default; set true to enable
SYNONYM_EXPLODER_SCOPE=none         # e.g. llamaindex_search,langchain_search
```

When enabled, the LLM generates synonyms for query keywords; each synonym is used as an additional embedding query against the scoped retrievers.

---

## Retrieval Fusion

```env
RETRIEVAL_FUSION=llamaindex   # QueryFusionRetriever, mode=relative_score (default)
RETRIEVAL_FUSION=langchain    # EnsembleRetriever (RRF) — activates when ALL retrievers are LC-backed
```

`EnsembleRetriever` is in `langchain_classic.retrievers.ensemble`. Falls back silently to `QueryFusionRetriever` if any LI-native retriever is present.

---

## Source Labels in Results

Every search result shows which database it came from. This happens automatically — no configuration needed. See the Search Tab Guide (UI Guide → Tab 3) for examples.
