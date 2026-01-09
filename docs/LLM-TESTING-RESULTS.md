# LLM Testing Results

Comprehensive testing results for different LLM and embedding provider combinations with GraphRAG.

## Test Summary

| LLM Provider / Model | Graph Extraction | Search with Graph | AI Query with Graph | Notes |
|----------------------|------------------|-------------------|---------------------|-------|
| **OpenAI** (gpt-4o-mini, etc.) | ✅ Full entities/relationships | ✅ Works | ✅ Works | Recommended for full GraphRAG |
| **Azure OpenAI** (gpt-4o-mini) | ✅ Full entities/relationships | ✅ Works | ✅ Works | Same as OpenAI, enterprise hosting |
| **Google Gemini** (gemini-2.5-flash, gemini-3-pro-preview) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-08**: Async issues resolved |
| **Google Vertex AI** (gemini-2.5-flash) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-08**: Same as Gemini |
| **Groq** (gpt-oss-20b) | ⚠️ Chunk nodes only | ✅ Works | ✅ Works | Fast inference, limited extraction |
| **Fireworks AI** (gpt-oss-20b) | ⚠️ Chunk nodes only | ✅ Works | ✅ Works | Fine-tuning support, limited extraction |
| **Anthropic Claude** (sonnet-4-5, haiku-4-5) | ⚠️ Chunk nodes only | ✅ Works | ✅ Works | Known LlamaIndex limitation |
| **Amazon Bedrock** (gpt-oss-20b/120b, claude-sonnet, deepseek-r1, llama3.1/3.2/3.3, llama4) | ⚠️ Chunk nodes only | ✅ Works | ✅ Works | Cross-region profiles needed for most |
| **Ollama** (llama3.2, sciphi/triplex) | ❌ Fails ingestion | ❌ N/A | ❌ N/A | Regression from previous versions |

### Graph Database Compatibility

All graph databases (Neo4j, FalkorDB, ArcadeDB, Kuzu, MemGraph, etc.) show identical behavior patterns based on the LLM provider used, not the database choice:

- **OpenAI/Azure OpenAI**: Full graph extraction with entities and relationships works on all databases
- **Gemini/Vertex AI**: Full graph extraction works, but search/query operations fail when graph is enabled (all databases)
- **Other providers**: Create chunk nodes only across all graph databases

## Google Gemini Models

### Tested Models
- ✅ `gemini-2.5-flash` - Full graph building, search and query work
- ✅ `gemini-3-pro-preview` - Full graph building, search and query work
- ✅ `gemini-3-flash-preview` - Full graph building, search and query work

### Known Issues
- ✅ **Fixed 2026-01-08**: Graph search/query async event loop conflicts resolved
- Gemini creates full knowledge graphs with proper entities and relationships on all graph databases
- Search and AI query now work correctly with graph enabled
- **Limitation**: Google embeddings (`EMBEDDING_KIND=google`) require Gemini/Vertex AI LLM due to async SDK compatibility

## Google Vertex AI Models

### Tested Models
- ✅ `gemini-2.5-flash` - Full graph building, search error when graph enabled (same as Gemini)

### Configuration Notes
- Uses modern `google-genai` package with `GoogleGenAI` and `GoogleGenAIEmbedding` classes
- Requires `vertexai_config` parameter with project and location
- Cleaned up implementation - removed deprecated `llama-index-llms-vertex` and `llama-index-embeddings-vertex` packages
- Environment variables (`GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`) are set automatically by the code

### Known Issues
- ✅ **Fixed 2026-01-08**: Graph search/query async event loop conflicts resolved (same fix as Gemini)
- Vertex AI creates full knowledge graphs with proper entities and relationships on all graph databases
- Search and AI query now work correctly with graph enabled
- **Limitation**: Google embeddings (`EMBEDDING_KIND=vertex`) require Gemini/Vertex AI LLM due to async SDK compatibility

## Anthropic Claude Models

### Tested Models
- ✅ `claude-sonnet-4-5-20250929` - Graph building works (chunk nodes only), search and AI query work
- ✅ `claude-haiku-4-5-20251001` - Graph building works (chunk nodes only), search and AI query work

### Known Issues
- **Graph extraction limitation** - Claude only creates chunk nodes during graph building (no entities/relationships extracted) - known LlamaIndex limitation

## Groq Models

### Tested Models
- ✅ `gpt-oss-20b` - Graph building (chunk nodes only), search and AI query work

### Configuration Notes
- Ultra-fast LPU (Language Processing Unit) architecture for low-latency inference
- **DOES support timeout parameter** (inherits from OpenAILike base class)
- Cost-effective for high-volume workloads

### Known Issues
- **Graph extraction limitation** - Creates only chunk nodes during graph building (no entities/relationships extracted) - same behavior as Bedrock and Fireworks with non-OpenAI models
- Search and AI query work correctly with graph enabled

## Fireworks AI Models

### Tested Models
- ✅ `gpt-oss-20b` - Graph building (chunk nodes only), search and AI query work

### Configuration Notes
- Supports fine-tuning and wide model selection (Meta, Qwen, Mistral AI, DeepSeek, OpenAI GPT-OSS, Kimi, GLM, MiniMax)
- Embeddings work well (`nomic-ai/nomic-embed-text-v1.5`)
- **Does NOT support timeout parameter** (overrides `__init__` without including timeout parameter)

### Known Issues
- **Graph extraction limitation** - Creates only chunk nodes during graph building (no entities/relationships extracted)
- Inherits from OpenAI class but blocks timeout parameter

## Amazon Bedrock Models

### Tested Models

**Partial Success (search/AI query work, graph=chunk only):**
- ✅ `openai.gpt-oss-20b-1:0` - Chunk nodes only
- ✅ `openai.gpt-oss-120b-1:0` - Chunk nodes only
- ✅ `us.anthropic.claude-sonnet-4-5-20250929-v1:0` - Chunk nodes only (requires "us." cross-region inference profile)
- ✅ `us.deepseek.r1-v1:0` - Chunk nodes only (requires "us." cross-region inference profile)
- ✅ `us.meta.llama3-3-70b-instruct-v1:0` - Chunk nodes only (requires "us." cross-region inference profile)

**Model Crashes:**
- ❌ `amazon.nova-pro-v1:0` - ModelErrorException: invalid ToolUse sequence
- ❌ `us.amazon.nova-premier-v1:0` - ModelErrorException: invalid ToolUse sequence
- ❌ `us.meta.llama3-1-70b-instruct-v1:0` - ValidationException: toolConfig.toolChoice.any not supported
- ❌ `us.meta.llama3-2-90b-instruct-v1:0` - ValidationException: toolConfig.toolChoice.any not supported
- ❌ `us.meta.llama4-maverick-17b-instruct-v1:0` - ValidationException: toolConfig.toolChoice.any not supported
- ❌ `us.meta.llama4-scout-17b-instruct-v1:0` - ValidationException: toolConfig.toolChoice.any not supported

### Configuration Notes
- Successfully switched from deprecated `llama-index-llms-bedrock` to modern `llama-index-llms-bedrock-converse` package
- **Authentication**: Uses AWS IAM admin credentials (NOT Bedrock API keys)
- **Embeddings work perfectly**: `amazon.titan-embed-text-v2:0` tested successfully with OpenAI and Bedrock LLMs
- **Cross-region inference profiles**: Most models require "us." prefix (e.g., `us.anthropic.claude-*`, `us.meta.llama*`, `us.deepseek.*`, `us.amazon.nova-premier-*`)
- **No prefix needed**: OpenAI GPT-OSS models and `amazon.nova-pro-v1:0` use standard model IDs without "us." prefix

### Known Issues
- **Graph extraction limitation** - Non-OpenAI models create only chunk nodes (no entities/relationships)
- **Root cause**: BedrockConverse sends `toolConfig.toolChoice.any` which most models reject
- Nova models (Pro and Premier) have invalid ToolUse sequence errors
- Meta Llama models don't support tool choice configuration


## Graph Database Testing Results

All graph databases show identical behavior based on LLM provider, not database choice:

### Graph-Only Mode Testing (No Vector/Search Databases)

Testing with OpenAI LLM, graph database only (no Elasticsearch, no Qdrant):

| Graph Database | Graph Creation | Search | AI Query | Notes |
|----------------|----------------|--------|----------|-------|
| **Neo4j** | ✅ Full graph | ✅ Works (high scores, structured results) | ✅ Works | Recommended |
| **FalkorDB** | ✅ Full graph | ✅ Works (high scores, structured results) | ✅ Works | Fully functional |
| **ArcadeDB** | ✅ Full graph | ❌ No results | ❌ Empty response | Needs vector support update |

**Key Findings:**
- **Neo4j and FalkorDB** work perfectly in graph-only mode with OpenAI, providing high-confidence search results (0.791 scores) with extracted relationship triplets and source text
- **ArcadeDB** creates full graphs but cannot perform graph-based retrieval without external vector/search databases
- **TODO**: Update ArcadeDB LlamaIndex PropertyGraphStore integration to leverage ArcadeDB's native vector support capabilities

### Multi-Database Graph Compatibility

Testing with OpenAI + full database stack (vector + search + graph):

| LLM Provider | Neo4j | FalkorDB | ArcadeDB | Result |
|--------------|-------|----------|----------|--------|
| **OpenAI** | ✅ Full graph + search | ✅ Full graph + search | ✅ Full graph + search | All work identically |
| **Azure OpenAI** | ✅ Full graph + search | ✅ Full graph + search | ✅ Full graph + search | All work identically |
| **Groq (gpt-oss)** | ⚠️ Chunk only | ⚠️ Chunk only | ⚠️ Chunk only | Database doesn't matter |
| **Gemini** | ✅ Graph + Search | ✅ Graph + Search | ✅ Graph + Search | **Fixed 2026-01-08** |
| **Vertex AI** | ✅ Graph + Search | ✅ Graph + Search | ✅ Graph + Search | **Fixed 2026-01-08** |

**Conclusion**: Graph database choice doesn't affect LLM compatibility - the pattern is determined by LLM provider's integration with LlamaIndex PropertyGraph.

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
- ✅ Google Gemini LLM + Google embeddings - **Recommended for Gemini users**
- ✅ Google Gemini LLM + OpenAI embeddings (2 separate API keys)
- ✅ Azure OpenAI LLM + Azure embeddings (same endpoint, uses `EMBEDDING_MODEL` as deployment name)
- ✅ Azure OpenAI LLM + OpenAI embeddings (fetches `OPENAI_API_KEY` from environment)
- ✅ OpenAI LLM + Azure embeddings (requires `EMBEDDING_MODEL` or `AZURE_EMBEDDING_DEPLOYMENT` for deployment name)
- ✅ OpenAI LLM + OpenAI embeddings (same API key)
- ❌ OpenAI LLM + Google embeddings - **Not supported due to async SDK incompatibility**
- ❌ Ollama LLM + Google embeddings - **Not supported due to async SDK incompatibility**

**Note**: Google/Vertex embeddings use async SDK and only work with Gemini/Vertex AI LLMs. System validates configuration at startup and prevents incompatible combinations.

## Recommendations

### For Full GraphRAG (entities + relationships):
- ✅ **OpenAI** (gpt-4o, gpt-4o-mini) - Best overall performance, works with all graph databases
- ✅ **Azure OpenAI** (gpt-4o-mini) - Enterprise deployment option, same capabilities as OpenAI

### For Graph Building + Vector/Search:
- ✅ **Google Gemini** (gemini-2.5-flash, gemini-3-pro-preview) - **Fixed 2026-01-08**
  - Full graph extraction with entities and relationships on all graph databases
  - Search and AI query work correctly with graph enabled
  - **Note**: Google embeddings require Gemini/Vertex AI LLM (async compatibility)
- ✅ **Google Vertex AI** (gemini-2.5-flash) - **Fixed 2026-01-08**
  - Same as Gemini: full graph extraction, search/query work with graph enabled
  - **Note**: Google embeddings require Gemini/Vertex AI LLM (async compatibility)
- ⚠️ **Anthropic Claude** (sonnet, haiku)
  - Can search with graph enabled
  - Graph building only creates chunk nodes (no entities/relationships extracted) across all databases
- ⚠️ **Groq** (llama-3.3-70b-versatile, gpt-oss-20b)
  - Fast inference with LPU architecture
  - Graph building only creates chunk nodes across all databases
  - Search and AI query work correctly
- ⚠️ **Fireworks AI** (gpt-oss-20b)
  - Fine-tuning support and wide model selection
  - Graph building only creates chunk nodes across all databases
  - Search and AI query work correctly
- ⚠️ **Amazon Bedrock** (non-Nova models)
  - Most models create chunk nodes only
  - Search and AI query work correctly
  - Embeddings (Titan) work excellently with any LLM provider

### For Graph-Only Mode (No Vector/Search):
- ✅ **Neo4j + OpenAI** - Fully functional graph-based retrieval
- ✅ **FalkorDB + OpenAI** - Fully functional graph-based retrieval
- ❌ **ArcadeDB + OpenAI** - Graph creation works, but retrieval requires external vector/search databases

### Cross-Provider Consistency:
- **GPT-OSS 20B** behaves identically on Bedrock, Fireworks, and Groq (all chunk nodes only)
- Proves it's model architecture + LlamaIndex integration quality, NOT provider infrastructure
- Graph database choice (Neo4j/FalkorDB/ArcadeDB/Kuzu/MemGraph) doesn't affect LLM compatibility patterns

### Local Models (Ollama):
- ❌ **Not recommended for GraphRAG**
  - `llama3.2` - Previously worked but now fails to complete ingestion
  - `sciphi/triplex` - Fails to complete ingestion despite being designed for KG extraction
  - Likely due to smaller model capacity and recent changes in Ollama/LlamaIndex

