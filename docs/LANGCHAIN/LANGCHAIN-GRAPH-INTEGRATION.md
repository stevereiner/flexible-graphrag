# LangChain Graph Database Integration

This document describes the integration of LangChain's graph database support with flexible-graphrag, enabling enhanced natural language querying of RDF and property graph stores as part of hybrid retrieval.

## Overview

The LangChain integration provides:

1. **Natural Language to Query Translation**: Convert natural language questions to SPARQL or Cypher automatically
2. **Hybrid Retrieval**: Combine LangChain graph retrievers with existing vector, BM25, and property graph retrievers via `QueryFusionRetriever`
3. **Same LLM Configuration**: Uses whichever LLM is already configured — no separate LLM setup required
4. **Schema-Guided Generation**: Live predicate/type schema fetched from the store at startup; missing namespace prefixes auto-injected

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  User Query (Natural Language)               │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │   QueryFusionRetriever        │
         │   (LlamaIndex)                │
         └───┬────────┬────────┬─────┬───┘
             │        │        │     │
             │        │        │     └──────────────┐
             │        │        │                    │
     ┌───────┴──┐  ┌──┴────┐ ┌┴─────────┐  ┌───────┴──────────┐
     │ Vector   │  │ BM25  │ │Property  │  │ RDF Graph        │
     │Retriever │  │       │ │Graph     │  │ Retriever        │
     │          │  │       │ │Retriever │  │ (LangChain)      │
     └──────────┘  └───────┘ └──────────┘  └──────┬───────────┘
                                                   │
                                    ┌──────────────┴──────────┐
                                    │ LangChain QA Chain      │
                                    │ (NL → SPARQL/Cypher)    │
                                    └──────────┬──────────────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │ Graph Database      │
                                    │ (GraphDB, Fuseki,   │
                                    │  Oxigraph, Neo4j)   │
                                    └─────────────────────┘
```

## Supported Databases

### RDF Stores (SPARQL)

#### 1. Ontotext GraphDB
- **Status**: ✅ Fully Implemented and Tested
- **Deployment**: Docker
- **Features**:
  - Schema introspection with live predicate/type fetching
  - Missing PREFIX declarations auto-injected
  - Enterprise features (sharding, clustering, OWL reasoning)

**Configuration**:
```env
USE_LANGCHAIN_RDF=true
RDF_STORE_TYPE=graphdb
GRAPHDB_BASE_URL=http://localhost:7200
GRAPHDB_REPOSITORY=flexible-graphrag
GRAPHDB_USERNAME=admin
GRAPHDB_PASSWORD=admin
```

**Docker Setup**:
```bash
cd docker
docker-compose up -d graphdb
```

#### 2. Apache Jena Fuseki
- **Status**: ✅ Fully Implemented and Tested
- **Deployment**: Docker
- **Features**:
  - Full SPARQL 1.1 + SPARQL Update support
  - RDF 1.2 annotations (legacy `<< >>` Turtle-star syntax on export)
  - HTTP Basic Auth

**Configuration**:
```env
USE_LANGCHAIN_RDF=true
RDF_STORE_TYPE=fuseki
FUSEKI_ENABLED=true
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
```

#### 3. Oxigraph
- **Status**: ✅ Fully Implemented and Tested
- **Deployment**: Docker (lightweight, good for local dev)
- **Features**:
  - RDF 1.2 blank-node reifier syntax on export
  - SPARQL endpoint at `/query`; upload via `/store` (N-Quads, not Turtle)

**Configuration**:
```env
USE_LANGCHAIN_RDF=true
RDF_STORE_TYPE=oxigraph
OXIGRAPH_ENABLED=true
OXIGRAPH_URL=http://localhost:7878
```

#### 4. Amazon Neptune (RDF/SPARQL)
- **Status**: ⚠️ Implemented, untested
- **Deployment**: AWS Cloud
- **Features**:
  - IAM authentication support
  - VPC endpoint access

**Configuration**:
```env
USE_LANGCHAIN_RDF=true
RDF_STORE_TYPE=neptune_rdf
NEPTUNE_HOST=my-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com
NEPTUNE_PORT=8182
NEPTUNE_REGION=us-east-1
NEPTUNE_USE_IAM_AUTH=true
NEPTUNE_USE_HTTPS=true
```

### Property Graphs

#### 1. Neo4j
- **Status**: ✅ Retrieval working
- **Query Language**: Cypher
- **Notes**: Uses existing Neo4j connection from main config; no separate setup

#### 2. ArangoDB, Apache AGE, Azure Cosmos DB Gremlin, Google Cloud Spanner Graph
- **Status**: 🔲 Placeholder stubs — not yet implemented

## Usage

### Basic Setup

1. **Enable LangChain RDF retrieval** in `.env`:
```env
USE_LANGCHAIN_RDF=true
RDF_STORE_TYPE=graphdb  # or fuseki, oxigraph, neptune_rdf
RDF_RETRIEVAL_TOP_K=5
RDF_RETRIEVAL_WEIGHT=0.3
```

2. **Configure the store** (Fuseki example):
```env
FUSEKI_ENABLED=true
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
```

3. **Ingest documents** via the normal API — if `INGESTION_STORAGE_MODE=both` or `rdf_only`, triples are written to the RDF store automatically.

4. **Query** — hybrid search automatically includes the RDF retriever:
```python
response = system.query("Who works at Acme?")
```

### Advanced: Custom QA Chain

```python
from rdf.langchain_adapters.graphdb_langchain_adapter import GraphDBLangChainAdapter
from langchain_openai import ChatOpenAI

adapter = GraphDBLangChainAdapter({
    "base_url": "http://localhost:7200",
    "repository": "flexible-graphrag",
    "username": "admin",
    "password": "admin",
    "ontology_file": "./rdf/schemas/company_ontology.ttl"
})

llm = ChatOpenAI(model="gpt-4o-mini")
qa_chain = adapter.create_qa_chain(llm)

result = qa_chain({"query": "What departments exist at TechCorp?"})
print(result["result"])
print(result["generated_sparql"])
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_LANGCHAIN_RDF` | `false` | Enable LangChain RDF retrieval |
| `RDF_STORE_TYPE` | - | Store type: `graphdb`, `fuseki`, `oxigraph`, or `neptune_rdf` |
| `RDF_RETRIEVAL_TOP_K` | `5` | Number of results from RDF retriever |
| `RDF_RETRIEVAL_WEIGHT` | `0.3` | Weight in fusion (0.0-1.0) |
| `GRAPHDB_BASE_URL` | `http://localhost:7200` | GraphDB endpoint |
| `GRAPHDB_REPOSITORY` | `flexible-graphrag` | GraphDB repository name |
| `GRAPHDB_USERNAME` | `admin` | GraphDB username |
| `GRAPHDB_PASSWORD` | `admin` | GraphDB password |
| `FUSEKI_ENABLED` | `false` | Enable Fuseki store |
| `FUSEKI_BASE_URL` | `http://localhost:3030` | Fuseki endpoint |
| `FUSEKI_DATASET` | `flexible-graphrag` | Fuseki dataset name |
| `OXIGRAPH_ENABLED` | `false` | Enable Oxigraph store |
| `OXIGRAPH_URL` | `http://localhost:7878` | Oxigraph HTTP endpoint |
| `NEPTUNE_HOST` | - | Neptune cluster endpoint |
| `NEPTUNE_PORT` | `8182` | Neptune port |
| `NEPTUNE_REGION` | `us-east-1` | AWS region |
| `NEPTUNE_USE_IAM_AUTH` | `false` | Use IAM authentication |
| `NEPTUNE_USE_HTTPS` | `true` | Use HTTPS |

### Hybrid Retriever Weights

- **Low emphasis** (0.1-0.2): Primarily vector/text search with light graph augmentation
- **Medium emphasis** (0.3-0.5): Balanced hybrid approach (recommended)
- **High emphasis** (0.6-0.8): Graph-centric with vector/text support

## Architecture Decisions

### Why LangChain for Retrieval?

1. **Natural Language Query Translation**: QA chains provide NL→SPARQL/Cypher translation with schema awareness
2. **Error Correction**: Iterative refinement of generated queries based on database errors
3. **Separation of Concerns**: LlamaIndex handles ingestion/embedding; LangChain handles NL query generation

### Why Not LangChain for Ingestion?

1. **Performance**: RDFLib local construction → bulk REST upload is faster than SPARQL INSERT
2. **Flexibility**: LlamaIndex abstractions support multiple databases with the same code
3. **Incremental Updates**: LlamaIndex supports clean incremental updates with `ref_doc_id` tracking

## Troubleshooting

### GraphDB Connection Issues

**Error**: `ConnectionError: Failed to connect to GraphDB`

1. Check Docker: `docker ps | grep graphdb`
2. Check logs: `docker logs flexible-graphrag-graphdb-1`
3. Verify endpoint: `curl http://localhost:7200/repositories`
4. Check credentials in `.env`

### No RDF Results in Hybrid Search

1. Verify `USE_LANGCHAIN_RDF=true` in `.env`
2. Check RDF store has data — run `python scripts/rdf_cleanup.py list-docs`
3. Increase `RDF_RETRIEVAL_TOP_K` to 10+
4. Check startup logs for RDF retriever initialization errors

### Pydantic Schema Errors

**Error**: `Unable to generate pydantic-core schema`

1. Ensure `strict=False` in `OntologyGuidedExtractor`
2. Check LlamaIndex version: `pip list | grep llama-index-core`
3. Update if needed: `pip install -U llama-index-core`

## References

- [LangChain Graph Integrations](https://python.langchain.com/docs/integrations/graphs/)
- [Ontotext GraphDB Documentation](https://graphdb.ontotext.com/documentation/)
- [LlamaIndex Property Graph](https://docs.llamaindex.ai/en/stable/module_guides/indexing/lpg_index_guide/)
