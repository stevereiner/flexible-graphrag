# Flexible GraphRAG

Python package for the [Flexible GraphRAG](https://github.com/stevereiner/flexible-graphrag) stack: document processing (Docling or LlamaParse), knowledge graphs, ontologies, many LLMs, GraphRAG and RAG, hybrid search (fulltext, vector, property graph, RDF/SPARQL), AI query, and AI chat. **LlamaIndex** and **LangChain** are peer frameworks (**LlamaIndex** defaults per pipeline stage). REST API via **FastAPI**; optional **MCP** server; Angular / React / Vue clients live in the monorepo.

Install: `uv pip install flexible-graphrag` (or `uv pip install -e .` from this directory). Optional stacks (**LangChain**, RDF extras, observability, Spanner, AGE, SurrealDB, Docling OCR, …) are **only** defined as **`[project.optional-dependencies]`** in **`pyproject.toml`** — not via a separate requirements-style file.

- **Repository**: [github.com/stevereiner/flexible-graphrag](https://github.com/stevereiner/flexible-graphrag)
- **Full README**: [README.md on GitHub](https://github.com/stevereiner/flexible-graphrag/blob/main/README.md)
- **Documentation**: [stevereiner.github.io/flexible-graphrag](https://stevereiner.github.io/flexible-graphrag/)
