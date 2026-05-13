# Prerequisites

## Required

- Python 3.12, 3.13, or 3.14
- [UV package manager](https://docs.astral.sh/uv/) — for dependency management
- Node.js 22.x + npm — for UI clients
- At least one search database: Elasticsearch or OpenSearch (or BM25, built-in)
- At least one vector database: Qdrant (recommended) or another supported vector DB
- At least one property graph database: Neo4j (recommended) — unless using vector-only RAG
- OpenAI API key (recommended) or Ollama running locally

!!! tip
    The `docker/docker-compose.yaml` can provide all databases as Docker containers — no manual installs needed.

## Install

```bash
cd flexible-graphrag
uv pip install -e .
```

## Optional (depending on features)

- **LangChain integration** — RDF QA fusion retriever and property graph retrievers:
  ```bash
  uv pip install -e ".[langchain]"
  ```
- **ArcadeDB embedded mode** — in-process ArcadeDB with bundled JVM (no separate Java needed):
  ```bash
  uv pip install arcadedb>=26.3.2
  ```
- **Enterprise Repositories**: Alfresco, SharePoint, Box, CMIS-compliant repository
- **Cloud Storage**: Amazon S3, Google Cloud Storage, Google Drive, Azure Blob, Microsoft OneDrive
