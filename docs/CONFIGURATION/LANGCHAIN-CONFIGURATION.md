# LangChain Configuration

This page covers environment variables and configuration for the LangChain integration. For architecture details and advanced usage, see [LangChain Integration](../ADVANCED/LANGCHAIN/LANGCHAIN-GRAPH-INTEGRATION.md) in the Advanced section.

---

## Installation

LangChain support is an optional extra. Install with:

```bash
# Core LangChain packages (RDF QA fusion retriever + property graph retrievers)
uv pip install -e ".[langchain]"

# Extended graph backends (ArangoDB, Spanner, AGE, Gremlin)
uv pip install -e ".[langchain,langchain-extras]"
```

This installs: `langchain`, `langchain-community`, `langchain-openai`, `langchain-anthropic`, `langchain-aws`, `langchain-ollama`, `langchain-google-genai`, `langchain-google-vertexai`, `langchain-groq`, `langchain-fireworks`, `langchain-neo4j`.

---

## RDF QA Fusion (`USE_LANGCHAIN_RDF`)

Enable SPARQL-based retrieval fused into the hybrid search pipeline:

```bash
USE_LANGCHAIN_RDF=true
RDF_STORE_TYPE=fuseki      # fuseki | graphdb | oxigraph
```

When enabled, the LangChain RDF retriever generates SPARQL queries from natural language and fuses results alongside vector, BM25, and graph results.

---

## Property Graph Retrievers (`USE_LANGCHAIN_PG`)

Enable LangChain property graph retrievers for Neo4j:

```bash
USE_LANGCHAIN_PG=true
```

Enables:
- **`TextToGraphQueryRetriever`** — converts natural language to Cypher/SPARQL for Neo4j
- **`GraphEntityVectorRetriever`** — entity vector similarity search in Neo4j
- **`GraphNeighborhoodRetriever`** — k-hop graph neighborhood expansion

---

## Synonym Expansion

Expand query keywords for broader retrieval coverage:

```bash
USE_SYNONYM_EXPANSION=true
SYNONYM_EXPANSION_LLM=openai   # uses configured LLM_PROVIDER by default
```

---

## Scope Tags

Control which retrievers are active in hybrid search:

```bash
# Comma-separated list of active retriever tags
RETRIEVER_SCOPE_TAGS=llamaindex_vector,llamaindex_search,llamaindex_pg_graph,langchain_rdf_graph
```

Available tags:
- `llamaindex_vector` — LlamaIndex vector retriever
- `llamaindex_search` — LlamaIndex BM25/ES/OpenSearch retriever
- `llamaindex_pg_graph` — LlamaIndex property graph retriever
- `langchain_pg_vector` — LangChain Neo4j entity vector retriever
- `langchain_rdf_graph` — LangChain RDF SPARQL retriever
- `langchain_pg_graph` — LangChain property graph (Cypher) retriever
- `langchain_pg_neighborhood` — LangChain k-hop neighborhood retriever
