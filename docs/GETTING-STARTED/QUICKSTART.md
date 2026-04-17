# Quickstart

Get Flexible GraphRAG running in 5 minutes with Docker and a PyPI install.

## Step 1 — Start databases with Docker

```bash
cd docker
cp docker-env-sample.txt docker.env   # Linux/macOS
copy docker-env-sample.txt docker.env  # Windows

# Start Neo4j + Qdrant + Elasticsearch (default minimal set)
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
```

Default services started:

| Service | URL |
|---|---|
| Neo4j Browser | http://localhost:7474 |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Elasticsearch | http://localhost:9200 |
| Kibana | http://localhost:5601 |

## Step 2 — Install the backend

=== "PyPI install (quickest)"

    ```bash
    uv venv venv-3.13 --python 3.13
    venv-3.13\Scripts\Activate   # Windows
    source venv-3.13/bin/activate  # Linux/macOS

    uv pip install flexible-graphrag
    ```

=== "Source install (needed for cleanup.py)"

    ```bash
    git clone https://github.com/stevereiner/flexible-graphrag
    cd flexible-graphrag/flexible-graphrag
    uv venv venv-3.13 --python 3.13
    venv-3.13\Scripts\Activate   # Windows
    source venv-3.13/bin/activate  # Linux/macOS
    uv pip install -e .
    ```

    See [Getting Started — Source Install](GETTING-STARTED.md#option-b----install-from-source-editable) for full details.

## Step 3 — Configure environment

```bash
# Download env-sample.txt from the repo, or copy it if you cloned
copy env-sample.txt .env   # Windows
cp env-sample.txt .env     # Linux/macOS
```

!!! tip "An API key is required unless you use Ollama (local)"
    The default provider is **OpenAI** — set `OPENAI_API_KEY` from [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
    To use a different provider, set `LLM_PROVIDER` and its corresponding key instead.
    Ollama runs locally and needs no API key.

Edit `.env` — set your LLM provider and its API key:

```bash
# OpenAI (default)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...         # Required — get from platform.openai.com/api-keys
OPENAI_MODEL=gpt-4.1-mini

# Anthropic Claude
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini
# LLM_PROVIDER=gemini
# GEMINI_API_KEY=...

# Ollama (local — no API key needed)
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=gpt-oss:20b
```

**If using ontologies**, copy the schemas directory next to your `.env`:

```bash
# The schemas dir lives at the repo root — copy it to your working directory
cp -r /path/to/flexible-graphrag/schemas ./schemas   # Linux/macOS
xcopy /E /I path\to\flexible-graphrag\schemas schemas # Windows
```

Then set ontology paths in `.env` using `.` (current dir), not `..`:

```bash
ONTOLOGY_PATHS=./schemas/company_classes.ttl,./schemas/company_properties.ttl,./schemas/common_ontology.ttl
```

## Step 4 — Start the backend

```bash
flexible-graphrag
```

Backend is now available at **http://localhost:8000**.
Swagger UI: **http://localhost:8000/docs**

## Step 5 — Launch a UI (optional)

```bash
# React (recommended for first-time use)
cd flexible-graphrag-ui/frontend-react
npm install && npm run dev
```

Open **http://localhost:5174** in your browser.

## Step 6 — Ingest a document

In the UI:

1. **Sources tab** → Select "File Upload" → drag and drop a PDF or TXT file
2. **Processing tab** → Click "START PROCESSING" → wait for the progress bar
3. **Search tab** → Type a question → click "SEARCH" or "ASK"
4. **Chat tab** → Have a conversation with your documents

## What Happens Under the Hood

```
Document → Docling (parse) → Chunks → Embeddings → Qdrant (vector)
                                     ↓
                              LLM Extraction → Neo4j (knowledge graph)
                                     ↓
                          Elasticsearch (full-text BM25 index)
```

Hybrid search combines all three — vector similarity + BM25 + graph traversal.

## Cleaning Up Between Tests

Run from the repo root (requires source install — see Step 2 above):

```bash
# Windows (from repo root)
python ..\scripts\cleanup.py

# Linux/macOS (from repo root)
python ../scripts/cleanup.py
```

!!! note
    `cleanup.py` uses internal modules and must be run with a source install (`uv pip install -e .`).
    If you only have the PyPI install, clean up via each database's dashboard instead.

## Next Steps

- [Docker Deployment](DOCKER-DEPLOYMENT.md) — full Docker scenarios
- [Environment Configuration](ENVIRONMENT-CONFIGURATION.md) — all `.env` settings
- [LLM Configuration](../LLM/LLM-EMBEDDING-CONFIG.md) — configure providers
- [UI Guide](../UI-GUIDE/UI-GUIDE.md) — detailed UI walkthrough
