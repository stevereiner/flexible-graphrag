# LLM Testing Results

Comprehensive testing results for different LLM and embedding provider combinations with GraphRAG.

## Test Summary

| LLM Provider / Model | Graph Extraction | Search with Graph | AI Query with Graph | Notes |
|----------------------|------------------|-------------------|---------------------|-------|
| **OpenAI** (gpt-4o-mini, etc.) | ✅ Full entities/relationships | ✅ Works | ✅ Works | Recommended for full GraphRAG |
| **Azure OpenAI** (gpt-4o-mini) | ✅ Full entities/relationships | ✅ Works | ✅ Works | Same as OpenAI, enterprise hosting |
| **Google Gemini** (gemini-2.5-flash, gemini-3-pro-preview) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-08**: Async issues resolved |
| **Google Vertex AI** (gemini-2.5-flash) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-08**: Same as Gemini |
| **Anthropic Claude** (sonnet-4-5, haiku-4-5) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-09**: Event loop fix restored extraction |
| **Ollama** (llama3.1:8b, llama3.2:3b, gpt-oss:20b) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-09**: Event loop fix restored functionality |
| **Groq** (openai/gpt-oss-20b) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-20**: SimpleLLMPathExtractor auto-used |
| **Fireworks AI** (llama4-maverick, deepseek-v3p2, gpt-oss) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-20**: SimpleLLMPathExtractor auto-used |
| **Amazon Bedrock** (claude-sonnet, gpt-oss, deepseek-r1, llama3) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-20**: SimpleLLMPathExtractor auto-used |

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

## Anthropic Claude Models

### Tested Models
- ✅ `claude-sonnet-4-5-20250929` - Full graph building with entities/relationships, search and AI query work
- ✅ `claude-haiku-4-5-20251001` - Full graph building with entities/relationships, search and AI query work

### Known Issues
- **Fixed 2026-01-09**: Event loop fix restored full entity/relationship extraction (was previously showing "chunk nodes only")
- Both models now create proper entities and relationships with the async event loop fix

## Groq Models

### Tested Models
- ✅ `openai/gpt-oss-20b` - Full graph with entities and relationships

### Configuration Notes
- Ultra-fast LPU (Language Processing Unit) architecture for low-latency inference
- **DOES support timeout parameter** (inherits from OpenAILike base class)
- Cost-effective for high-volume workloads
- **Automatic extractor switching**: When `KG_EXTRACTOR_TYPE=schema` is configured, the system automatically switches to `DynamicLLMPathExtractor` due to LlamaIndex SchemaLLMPathExtractor limitations with Groq
- **No switching for simple/dynamic**: If you configure `KG_EXTRACTOR_TYPE=simple` or `dynamic`, your choice is used as-is

### Known Issues
- ✅ **Fixed 2026-01-21**: System automatically switches from `schema` to `dynamic` extractor for Groq, which works correctly for both initial and incremental document ingestion
- `SchemaLLMPathExtractor` has tool calling limitations with Groq's LlamaIndex integration - system automatically switches to dynamic extractor when schema is configured
- If you manually configure `KG_EXTRACTOR_TYPE=simple` or `dynamic`, your configuration is respected
- Search and AI query work correctly with graph enabled

## Fireworks AI Models

### Tested Models
- ✅ `accounts/fireworks/models/llama4-maverick-instruct-basic` - Full graph with entities and relationships
- ✅ `accounts/fireworks/models/deepseek-v3p2` - Full graph with entities and relationships
- ✅ `accounts/fireworks/models/gpt-oss-120b` - Full graph with entities and relationships
- ✅ `accounts/fireworks/models/gpt-oss-20b` - Full graph with entities and relationships

### Configuration Notes
- Supports fine-tuning and wide model selection (Meta, Qwen, Mistral AI, DeepSeek, OpenAI GPT-OSS, Kimi, GLM, MiniMax)
- Embeddings work well (`nomic-ai/nomic-embed-text-v1.5`)
- **Does NOT support timeout parameter** (overrides `__init__` without including timeout parameter)
- **Automatic extractor switching**: When `KG_EXTRACTOR_TYPE=schema` is configured, the system automatically switches to `DynamicLLMPathExtractor` due to LlamaIndex SchemaLLMPathExtractor limitations with Fireworks
- **No switching for simple/dynamic**: If you configure `KG_EXTRACTOR_TYPE=simple` or `dynamic`, your choice is used as-is

### Known Issues
- ✅ **Fixed 2026-01-21**: System automatically switches from `schema` to `dynamic` extractor for Fireworks, which works correctly for both initial and incremental document ingestion
- `SchemaLLMPathExtractor` has tool calling limitations with Fireworks' LlamaIndex integration - system automatically switches to dynamic extractor when schema is configured
- If you manually configure `KG_EXTRACTOR_TYPE=simple` or `dynamic`, your configuration is respected
- Search and AI query work correctly with graph enabled

## Amazon Bedrock Models

### Tested Models

**Full Graph Extraction:**
- ✅ `us.anthropic.claude-sonnet-4-5-20250929-v1:0` - Full graph with entities and relationships
- ✅ `openai.gpt-oss-20b-1:0` - Full graph with entities and relationships
- ✅ `openai.gpt-oss-120b-1:0` - Full graph with entities and relationships
- ✅ `us.deepseek.r1-v1:0` - Full graph with entities and relationships
- ✅ `us.meta.llama3-3-70b-instruct-v1:0` - Full graph with entities and relationships

**Needs Retesting (Previously Crashed with SchemaLLMPathExtractor):**
- ⚠️ `amazon.nova-pro-v1:0` - Previously: ModelErrorException: invalid ToolUse sequence (needs retest with SimpleLLMPathExtractor)
- ⚠️ `us.amazon.nova-premier-v1:0` - Previously: ModelErrorException: invalid ToolUse sequence (needs retest with SimpleLLMPathExtractor)
- ⚠️ `us.meta.llama3-1-70b-instruct-v1:0` - Previously: ValidationException: toolConfig.toolChoice.any not supported (needs retest with SimpleLLMPathExtractor)
- ⚠️ `us.meta.llama3-2-90b-instruct-v1:0` - Previously: ValidationException: toolConfig.toolChoice.any not supported (needs retest with SimpleLLMPathExtractor)
- ⚠️ `us.meta.llama4-maverick-17b-instruct-v1:0` - Previously: ValidationException: toolConfig.toolChoice.any not supported (needs retest with SimpleLLMPathExtractor)
- ⚠️ `us.meta.llama4-scout-17b-instruct-v1:0` - Previously: ValidationException: toolConfig.toolChoice.any not supported (needs retest with SimpleLLMPathExtractor)

### Configuration Notes
- Successfully switched from deprecated `llama-index-llms-bedrock` to modern `llama-index-llms-bedrock-converse` package
- **Authentication**: Uses AWS IAM admin credentials (NOT Bedrock API keys)
- **Embeddings work perfectly**: `amazon.titan-embed-text-v2:0` tested successfully with OpenAI and Bedrock LLMs
- **Cross-region inference profiles**: Most models require "us." prefix (e.g., `us.anthropic.claude-*`, `us.meta.llama*`, `us.deepseek.*`, `us.amazon.nova-premier-*`)
- **No prefix needed**: OpenAI GPT-OSS models and `amazon.nova-pro-v1:0` use standard model IDs without "us." prefix
- **Automatic extractor switching**: When `KG_EXTRACTOR_TYPE=schema` is configured, the system automatically switches to `DynamicLLMPathExtractor` due to LlamaIndex SchemaLLMPathExtractor limitations with Bedrock
- **No switching for simple/dynamic**: If you configure `KG_EXTRACTOR_TYPE=simple` or `dynamic`, your choice is used as-is

### Known Issues
- ✅ **Fixed 2026-01-21**: System automatically switches from `schema` to `dynamic` extractor for Bedrock, which works correctly for both initial and incremental document ingestion
- `SchemaLLMPathExtractor` has tool calling limitations with Bedrock-Converse' LlamaIndex integration - system automatically switches to dynamic extractor when schema is configured
- If you manually configure `KG_EXTRACTOR_TYPE=simple` or `dynamic`, your configuration is respected
- **Nova and Llama 3.1/3.2/4 models need retesting** - Previous crashes were with SchemaLLMPathExtractor's tool calling. Now that the system automatically switches to DynamicLLMPathExtractor (which has better tool calling support), these models may work correctly
- Search and AI query work correctly with graph enabled


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
- ✅ `llama3.1:8b` - Full graph building with entities/relationships, good performance
- ✅ `llama3.2:3b` - Full graph building with entities/relationships, faster than 3.1
- ✅ `gpt-oss:20b` - Full graph building with entities/relationships, slower but functional
- ❌ `sciphi/triplex` - Extracts 0 entities/relationships, extremely slow, not usable

### Configuration Notes
- Local deployment with privacy and cost benefits
- **SchemaLLMPathExtractor** (default) works correctly with Ollama
- **DynamicLLMPathExtractor may only create text node chunks** - not recommended for Ollama

### Known Issues
- **Fixed 2026-01-09**: Async event loop fix restored full Ollama functionality for llama3.1, llama3.2, and gpt-oss models
- `sciphi/triplex` still fails to extract entities/relationships despite being specifically designed for KG extraction
- When using DynamicLLMPathExtractor with Ollama, graphs may only contain text node chunks without entities/relationships
- Recommend using `llama3.1:8b` or `llama3.2:3b` for local GraphRAG with Ollama


## Mixed Provider Configurations

Successfully tested combinations:
- ✅ Google Gemini LLM + Google embeddings - **Recommended for Gemini users**
- ✅ Google Gemini LLM + OpenAI embeddings (2 separate API keys)
- ✅ Azure OpenAI LLM + Azure embeddings (same endpoint, uses `EMBEDDING_MODEL` as deployment name)
- ✅ Azure OpenAI LLM + OpenAI embeddings (fetches `OPENAI_API_KEY` from environment)
- ✅ OpenAI LLM + Azure embeddings (requires `EMBEDDING_MODEL` or `AZURE_EMBEDDING_DEPLOYMENT` for deployment name)
- ✅ OpenAI LLM + OpenAI embeddings (same API key)
- ✅ OpenAI LLM + Google embeddings (mixed provider, tested and working)
- ✅ Ollama LLM + Ollama embeddings (local deployment)

## Recommendations

### For Full GraphRAG (entities + relationships):
- ✅ **OpenAI** (gpt-4o, gpt-4o-mini) - Best overall performance, works with all graph databases, SchemaLLMPathExtractor (default)
- ✅ **Azure OpenAI** (gpt-4o-mini) - Enterprise deployment option, same capabilities as OpenAI, SchemaLLMPathExtractor (default)
- ✅ **Google Gemini** (gemini-2.5-flash, gemini-3-pro-preview) - Full graph extraction, SchemaLLMPathExtractor (default)
- ✅ **Google Vertex AI** (gemini-2.5-flash) - Same as Gemini, SchemaLLMPathExtractor (default)
- ✅ **Anthropic Claude** (sonnet-4-5, haiku-4-5) - Full graph extraction, SchemaLLMPathExtractor (default)
- ✅ **Ollama** (llama3.1:8b, llama3.2:3b, gpt-oss:20b) - Local deployment, SchemaLLMPathExtractor (default)
- ✅ **Groq** (gpt-oss-20b) - Fast LPU inference, SimpleLLMPathExtractor (auto-used due to LlamaIndex issues)
- ✅ **Fireworks AI** (llama4-maverick, deepseek-v3p2, gpt-oss) - Wide model selection, SimpleLLMPathExtractor (auto-used due to LlamaIndex issues)
- ✅ **Amazon Bedrock** (claude-sonnet, gpt-oss, deepseek-r1, llama3) - AWS integration, SimpleLLMPathExtractor (auto-used due to LlamaIndex issues)

**Note**: The extractor type can be configured via `KG_EXTRACTOR_TYPE` environment variable (options: `schema`, `simple`, `dynamic`). However, due to LlamaIndex integration issues with SchemaLLMPathExtractor for Bedrock, Groq, and Fireworks, the configuration is ignored and SimpleLLMPathExtractor is automatically used for these providers.

### For Graph Building + Vector/Search:
All providers listed above work correctly with full database stacks (vector + search + graph)

### For Graph-Only Mode (No Vector/Search):
- ✅ **Neo4j + OpenAI** - Fully functional graph-based retrieval
- ✅ **FalkorDB + OpenAI** - Fully functional graph-based retrieval
- ❌ **ArcadeDB + OpenAI** - Graph creation works, but retrieval requires external vector/search databases

### Extractor Information:
- **SchemaLLMPathExtractor** (default): Uses predefined schema with strict entity/relationship types. Provides better typing when it works. Default for OpenAI, Azure, Gemini, Vertex, Claude, and Ollama.
- **SimpleLLMPathExtractor**: Allows LLM to discover entities/relationships without strict schema. More flexible but less structured typing. Automatically used for Groq, Fireworks, and Bedrock due to SchemaLLMPathExtractor tool calling bugs in their LlamaIndex integrations.
- **DynamicLLMPathExtractor**: Starts with an ontology but allows LLM to expand it. Configurable but not recommended for Ollama (may only create text node chunks).

### Local Models (Ollama):
- ✅ **Recommended for local GraphRAG** - **Fixed 2026-01-09**
  - `llama3.1:8b` - Works, creates proper entities/relationships, good performance
  - `llama3.2:3b` - Works, creates proper entities/relationships, faster than 3.1
  - `gpt-oss:20b` - Works, creates proper entities/relationships, slower but functional
  - Event loop fixes restored full Ollama functionality
- ❌ **Not recommended**
  - `sciphi/triplex` - Extracts 0 entities/relationships, extremely slow, not usable despite being designed for KG extraction

