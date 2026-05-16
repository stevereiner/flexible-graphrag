# Flexible GraphRAG

Flexible GraphRAG is an open source AI context platform supporting a document processing pipeline (Docling or LlamaParse), knowledge graph auto-building, ontologies, schemas, many LLM providers, GraphRAG and RAG, hybrid semantic search (fulltext, vector, property graph, RDF/SPARQL), AI query, and AI chat. The backend is Python with LlamaIndex and LangChain as peer frameworks. LlamaIndex is the default for each pipeline stage; LangChain can be selected per stage in environment configuration. The API is a REST FastAPI service. Angular, React, and Vue TypeScript frontends and an MCP server are included. The stack supports 13 data sources (9 with incremental auto-sync), 15 property graph databases, 4 RDF triple stores (Apache Jena Fuseki, Ontotext GraphDB, Oxigraph, Amazon Neptune RDF), 10 vector databases, OpenSearch / Elasticsearch / BM25 search, and Alfresco. Services and dashboards can be enabled with the provided Docker Compose layout.

**Quick install (PyPI):**

```bash
uv pip install flexible-graphrag
```

Then copy `env-sample.txt` to `.env`, set your LLM API key (e.g. `OPENAI_API_KEY=...`) and any other provider config, and run `flexible-graphrag` to start the API server. If you use ontology schemas, the `schemas/` directory lives at the repository root (one level above `flexible-graphrag/`), so `.env` paths use `../schemas/...` — matching `env-sample.txt`. For a PyPI install, copy `schemas/` to the parent of your working directory so the same paths apply. See the [RDF Ontology Examples and Configuration](https://stevereiner.github.io/flexible-graphrag/DATABASES/RDF/ontology_examples_and_config/) docs page for path options and examples. This gives you a LlamaIndex-only setup; for LangChain or mixed LlamaIndex/LangChain per-stage configuration see the **Prerequisites**, **Setup**, and **Framework Config** sections of the full README, or the [Framework Configuration](https://stevereiner.github.io/flexible-graphrag/CONFIGURATION/LANGCHAIN-CONFIGURATION/) docs page.

Optional dependency groups (`langchain`, RDF extras, observability, and more) are available. For Docker services, frontend installs, source checkout setup, and optional extras (which involve `extras-overrides.txt`), refer to the **Prerequisites** and **Setup** sections of the full README and documentation linked below.

- **Repository**: [github.com/stevereiner/flexible-graphrag](https://github.com/stevereiner/flexible-graphrag)
- **Full README**: [README.md on GitHub](https://github.com/stevereiner/flexible-graphrag/blob/main/README.md)
- **Documentation**: [stevereiner.github.io/flexible-graphrag](https://stevereiner.github.io/flexible-graphrag/)
