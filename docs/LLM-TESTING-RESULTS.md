# LLM Testing Results

Comprehensive testing results for different LLM and embedding provider combinations with GraphRAG.

## Google Gemini Models

### Tested Models
- ✅ `gemini-2.5-flash` - Works with graph building, search graph issue
- ✅ `gemini-3-pro-preview` - Works with graph building  
- ❌ `gemini-3-flash-preview` - Takes forever on ingest, hangs during processing

### Known Issues
- **Graph Search incompatibility** - `llama-index-llms-google-genai` package has instrumentation conflicts that prevent graph search/retrieval operations (async event loop error: "Future attached to a different loop")
- Graph building (ingestion) works correctly
- Search operations fail with async instrumentation error when knowledge graph is enabled
- **Workaround**: Use Gemini with `GRAPH_DB=none` and `ENABLE_KNOWLEDGE_GRAPH=false` for vector + search only

## Anthropic Claude Models

### Tested Models
- ✅ `claude-sonnet-4-5-20250929` - Graph building works (chunk nodes only), search and AI query work
- ✅ `claude-haiku-4-5-20251001` - Graph building works (chunk nodes only), search and AI query work

### Known Issues
- **Graph extraction limitation** - Claude only creates chunk nodes during graph building (no entities/relationships extracted) - known LlamaIndex limitation

## Azure OpenAI

### Tested Models
- ✅ `gpt-4o-mini` - Full GraphRAG functionality (graph building with entities/relationships, search, AI query all work)

### Configuration Notes
- Requires `EMBEDDING_KIND=azure` when using Azure OpenAI LLM to use Azure-hosted embeddings
- Can also use `EMBEDDING_KIND=openai` with separate OpenAI API key

## Ollama Models

### Tested Models
- ⚠️ `sciphi/triplex` - Graph building creates chunk nodes only (no entities/relationships extracted despite being specifically designed for KG extraction)
- ❌ `llama3.2` - Fails during graph building with both `all-minilm` and `nomic-embed-text` embeddings (regression - previously worked)

### Known Issues
- Most Ollama models only create chunk nodes with no entity/relationship extraction, even when specifically designed for KG extraction
- Likely due to changes in Ollama and LlamaIndex


## Mixed Provider Configurations

Successfully tested combinations:
- ✅ Google Gemini LLM + OpenAI embeddings (2 separate API keys)
- ✅ Azure OpenAI LLM + Azure embeddings (same endpoint, uses `EMBEDDING_MODEL` as deployment name)
- ✅ Azure OpenAI LLM + OpenAI embeddings (fetches `OPENAI_API_KEY` from environment)
- ✅ OpenAI LLM + Azure embeddings (requires `EMBEDDING_MODEL` or `AZURE_EMBEDDING_DEPLOYMENT` for deployment name)
- ✅ OpenAI LLM + OpenAI embeddings (same API key)

## Recommendations

### For Full GraphRAG (entities + relationships):
- ✅ **OpenAI** (gpt-4o, gpt-4o-mini) - Best overall performance
- ✅ **Azure OpenAI** (gpt-4o-mini) - Enterprise deployment option

### For Graph Building + Vector/Search (with limitations):
- ⚠️ **Google Gemini** (gemini-2.0-flash, gemini-3-pro-preview)
  - Can build graphs with entities and relationships
  - Graph search fails due to instrumentation issues
  - Works for vector + fulltext search when `GRAPH_DB=none`
- ⚠️ **Anthropic Claude** (sonnet, haiku)
  - Can search with graph enabled
  - Graph building only creates chunk nodes (no entities/relationships extracted)

### Local Models (Ollama):
- ❌ **Not recommended for GraphRAG**
  - `llama3.2` - Previously worked but now fails to complete ingestion
  - `sciphi/triplex` - Fails to complete ingestion despite being designed for KG extraction
  - Likely due to smaller model capacity and recent changes in Ollama/LlamaIndex

