# LLM and Embedding Configuration Guide

## Overview

Flexible GraphRAG allows you to configure **LLM providers** (for reasoning/generation) and **embedding providers** (for vector embeddings) **independently**. This enables powerful combinations like:

- **OpenAI LLM + Ollama embeddings** - Fast reasoning with local/private embeddings
- **Anthropic Claude + Ollama embeddings** - Advanced reasoning with cost-effective local embeddings
- **Gemini LLM + Google embeddings** - Native Google integration
- **Any LLM + Local embeddings** - Privacy-focused configurations

> **📊 For LLM testing results and GraphRAG compatibility information, see [LLM-TESTING-RESULTS.md](LLM-TESTING-RESULTS.md)**

---

## Configuration Parameters

### LLM Configuration
- `LLM_PROVIDER`: The LLM provider for reasoning/generation
  - Options: `openai`, `ollama`, `gemini`, `vertex_ai`, `anthropic`, `azure_openai`, `bedrock`, `groq`, `fireworks`, `openai_like`, `vllm`, `litellm`, `openrouter`

### Embedding Configuration (Independent)
- `EMBEDDING_KIND`: Type of embedding provider *(optional - defaults to LLM provider)*
  - Options: `openai`, `ollama`, `google`, `vertex`, `azure`, `bedrock`, `fireworks`, `openai_like`, `litellm`
- `EMBEDDING_MODEL`: Specific model name
- `EMBEDDING_DIMENSION`: Explicit dimension override *(optional)*

---

## Provider Defaults

When `EMBEDDING_KIND` is **not specified**, embeddings automatically match the LLM provider:

| LLM Provider | Default Embedding | Model | Dimensions |
|--------------|------------------|-------|------------|
| **OpenAI** | OpenAI | text-embedding-3-small | 1536 |
| **Ollama** | Ollama | nomic-embed-text | 768 |
| **Gemini** | Google | gemini-embedding-2-preview | 768 |
| **Vertex AI** | Vertex AI | gemini-embedding-2-preview | 768 |
| **Anthropic** | Ollama | nomic-embed-text | 768 |
| **Azure OpenAI** | Azure OpenAI | text-embedding-3-small | 1536 |
| **Bedrock** | Bedrock | amazon.titan-embed-text-v2:0 | 1024 |
| **Groq** | Ollama | nomic-embed-text | 768 |
| **Fireworks** | Fireworks | nomic-ai/nomic-embed-text-v1.5 | 768 |
| **openai_like** | OpenAI-Like | *(your model)* | set `EMBEDDING_DIMENSION` |
| **vllm** | OpenAI-Like | *(your model)* | set `EMBEDDING_DIMENSION` |
| **LiteLLM** | Ollama | nomic-embed-text | 768 |
| **OpenRouter** | OpenAI | text-embedding-3-small | 1536 |

---

## Configuration Examples

### 1. OpenAI LLM with OpenAI Embeddings (Default)

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4.1-mini   # Recommended — fastest, most consistent tool-call schema following
#OPENAI_MODEL=gpt-4o-mini   # Previous default — works well, occasional 0-entity on large chunks
# No EMBEDDING_KIND - uses OpenAI embeddings by default
# EMBEDDING_MODEL=text-embedding-3-small (1536 dims)
```

### 2. OpenAI LLM with Local Ollama Embeddings (Privacy + Cost Savings)

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4.1-mini   # Recommended

# Override to use local Ollama embeddings
EMBEDDING_KIND=ollama
EMBEDDING_MODEL=nomic-embed-text  # 768 dims - good balance (default)
# Alternative: all-minilm (384 dims, fastest) or mxbai-embed-large (1024 dims, highest quality)
```

**Benefits:**
- 🔒 **Privacy**: Documents never leave your system for embeddings
- 💰 **Cost**: No embedding API charges
- ⚡ **Speed**: Local embeddings, no network latency
- 🧠 **Quality**: Still get GPT-4 reasoning power

### 3. Anthropic Claude with Local Ollama Embeddings (Default)

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
# No EMBEDDING_KIND - uses Ollama embeddings by default (local/private)
# EMBEDDING_MODEL=nomic-embed-text (768 dims)
```

**Note**: Anthropic defaults to **local Ollama embeddings** for privacy and cost savings.

### 4. Anthropic Claude with OpenAI Embeddings

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_key
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Override to use OpenAI embeddings
EMBEDDING_KIND=openai
OPENAI_API_KEY=your_openai_key
EMBEDDING_MODEL=text-embedding-3-small  # 1536 dims
```

### 5. Gemini LLM with Google Embeddings (Default Native)

```bash
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your_key
GEMINI_MODEL=gemini-3-flash-preview   # Recommended fast model
#GEMINI_MODEL=gemini-3.1-pro-preview  # Pro quality
# No EMBEDDING_KIND - uses Google embeddings by default
# EMBEDDING_MODEL=gemini-embedding-2-preview (768 dims, recommended)
# EMBEDDING_MODEL=gemini-embedding-001 (768 dims, stable GA alternative)
```

**Note**: `text-embedding-004` was deprecated 2026-01-14. Use `gemini-embedding-2-preview` (768 dims) or `gemini-embedding-001` (stable GA).

### 6. Gemini LLM with Custom Dimension Google Embeddings

```bash
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your_key
GEMINI_MODEL=gemini-3-flash-preview

# Use Google embeddings with explicit model/dimension
EMBEDDING_KIND=google
EMBEDDING_MODEL=gemini-embedding-2-preview  # 768 dims
EMBEDDING_DIMENSION=768
```

**Note**: Google embeddings support configurable dimensions: 768, 1536, or 3072.

### 7. Azure OpenAI LLM with Azure Embeddings (Default)

```bash
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=your_azure_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_ENGINE=gpt-4o-mini  # Your LLM deployment name
AZURE_OPENAI_MODEL=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview
# No EMBEDDING_KIND - uses Azure embeddings by default
# EMBEDDING_MODEL=text-embedding-3-small (deployment name, 1536 dims)
```

### 8. Azure OpenAI LLM with OpenAI Embeddings (Separate Keys)

```bash
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=your_azure_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_ENGINE=gpt-4o-mini
AZURE_OPENAI_MODEL=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# Use OpenAI embeddings instead of Azure
EMBEDDING_KIND=openai
OPENAI_API_KEY=your_openai_key
EMBEDDING_MODEL=text-embedding-3-small
```

### 9. OpenAI LLM with Azure Embeddings

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini

# Use Azure embeddings instead of OpenAI
EMBEDDING_KIND=azure
EMBEDDING_MODEL=text-embedding-3-small  # Used as deployment name
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
# AZURE_EMBEDDING_DEPLOYMENT=custom-name  # Optional: override deployment name
```

**Note**: Azure embeddings use `EMBEDDING_MODEL` as the deployment name by default. Use `AZURE_EMBEDDING_DEPLOYMENT` to specify a different deployment name.

### 11. Vertex AI LLM with Vertex Embeddings (Default Native)

```bash
LLM_PROVIDER=vertex_ai
VERTEX_AI_PROJECT=your-gcp-project-id
VERTEX_AI_LOCATION=us-central1
VERTEX_AI_MODEL=gemini-2.0-flash-001
VERTEX_AI_CREDENTIALS_PATH=/path/to/service-account-key.json  # Optional
# No EMBEDDING_KIND - uses Vertex AI embeddings by default
# EMBEDDING_MODEL=text-embedding-004 (768 dims)
```

**Note:** Uses `google-genai` package with `vertexai_config` for Vertex AI mode.

See: [LlamaIndex Vertex AI Support](https://developers.llamaindex.ai/python/examples/llm/google_genai/#vertex-ai-support)

### 12. Bedrock LLM with Bedrock Embeddings (Default)

**Note:** This uses the modern `llama-index-llms-bedrock-converse` package. The older `llama-index-llms-bedrock` package is deprecated and doesn't support structured prediction (needed for GraphRAG).

**LLM Configuration:**

```bash
LLM_PROVIDER=bedrock
BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_REGION=us-east-1
# Optional: explicit AWS credentials (uses default AWS chain if not provided)
# BEDROCK_ACCESS_KEY=your_access_key
# BEDROCK_SECRET_KEY=your_secret_key
```

**Embeddings Configuration (Separate):**

```bash
# No EMBEDDING_KIND specified - uses Bedrock embeddings by default
# Or explicitly set:
# EMBEDDING_KIND=bedrock
# EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
```

**All Models Work:**

All Bedrock models work with BedrockConverse, including:
- Amazon Nova (nova-pro-v1:0, nova-lite-v1:0, nova-micro-v1:0)
- Amazon Titan (titan-text-premier-v1:0, titan-text-express-v1)
- Anthropic Claude (claude-3-5-sonnet, claude-3-opus, claude-3-haiku)
- Meta Llama models
- Mistral AI models

**Available Models:**
- **Anthropic Claude**: claude-3-5-sonnet, claude-3-opus
- **Amazon Titan**: titan-text-express, titan-text-lite
- **AI21 Jurassic, Cohere Command, Meta Llama**

### 13. Groq LLM with Local Ollama Embeddings (Default)

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.3-70b-versatile  # Recommended for speed
# No EMBEDDING_KIND - uses Ollama embeddings by default (Groq doesn't provide embeddings)
# EMBEDDING_MODEL=nomic-embed-text (768 dims)
```

**Benefits:**
- ⚡ **Ultra-Fast**: Groq provides blazing fast inference
- 🔒 **Privacy**: Embeddings stay local with Ollama
- 💰 **Cost**: Free local embeddings

**Note**: Groq doesn't provide embeddings - system defaults to local Ollama for privacy.

### 14. Fireworks AI LLM with Fireworks Embeddings (Default)

```bash
LLM_PROVIDER=fireworks
FIREWORKS_API_KEY=your-fireworks-api-key
FIREWORKS_MODEL=accounts/fireworks/models/llama-v3p3-70b-instruct
# No EMBEDDING_KIND - uses Fireworks embeddings by default
# EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5 (768 dims)
```

**Available Models:**
- **Meta Llama**: llama-v3p3-70b-instruct (recommended), llama-v3p1-405b-instruct
- **Mixtral, Qwen, DeepSeek, and many more**

### 15. Mixed Provider Example: Groq LLM + Fireworks Embeddings

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.3-70b-versatile

# Use Fireworks embeddings for fast cloud-based embedding
EMBEDDING_KIND=fireworks
FIREWORKS_API_KEY=your-fireworks-api-key
EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
```

**Benefits:**
- ⚡ **Speed**: Groq for ultra-fast LLM + Fireworks for fast embeddings
- 💰 **Cost**: Competitive pricing from both providers
- 🔧 **Flexible**: Mix providers based on strengths

### 16. Ollama LLM with Ollama Embeddings (Fully Local)

```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=gpt-oss:20b          # Recommended — only model that reliably extracts entities/relationships
#OLLAMA_MODEL=llama3.1:8b         # Not recommended — 5x slower, hangs on 2nd doc
#OLLAMA_MODEL=llama3.2:3b         # Not recommended — low entity count, hangs on 2nd doc
OLLAMA_BASE_URL=http://localhost:11434
# No EMBEDDING_KIND - uses Ollama embeddings by default
# EMBEDDING_MODEL=nomic-embed-text (768 dims) — use this, NOT all-minilm (256 token limit causes truncation)
```

**Benefits:**
- 🔒 **100% Local**: Everything runs on your machine
- 🌐 **Offline**: No internet required
- 💰 **Free**: No API costs
- 🔐 **Private**: Maximum data privacy

---

## Embedding Model Details

### OpenAI Embeddings
| Model | Dimensions | Use Case |
|-------|-----------|----------|
| text-embedding-3-small | 1536 | Balanced performance (default) |
| text-embedding-3-large | 3072 | Highest quality |
| text-embedding-ada-002 | 1536 | Legacy model |

### Ollama Embeddings
| Model | Parameters | Dimensions | Use Case |
|-------|-----------|-----------|----------|
| nomic-embed-text | 137M | 768 | **Recommended default** - best balance |
| all-minilm | 22M | 384 | Fastest, lowest memory |
| mxbai-embed-large | 334M | 1024 | Highest quality, slower |

**Installation**: Run `ollama pull <model-name>` to download models.

### Google Embeddings
| Model | Dimensions | Notes |
|-------|-----------|-------|
| text-embedding-004 | 768, 1536, 3072 | Configurable via `EMBEDDING_DIMENSION` (recommended) |
| text-embedding-001 | 768, 1536, 3072 | Deprecated - use text-embedding-004 |

### Azure OpenAI Embeddings
Same as OpenAI models (text-embedding-3-small, text-embedding-3-large). 

**Note**: Uses `EMBEDDING_MODEL` as deployment name by default. Override with `AZURE_EMBEDDING_DEPLOYMENT` if your deployment name differs from the model name.

### Vertex AI Embeddings
| Model | Dimensions | Notes |
|-------|-----------|-------|
| text-embedding-004 | 768 | **Recommended** - Latest multilingual model |
| text-multilingual-embedding-002 | 768 | Optimized for non-English |
| textembedding-gecko@003 | 768 | Legacy model |

**Note:** Uses `google-genai` package with `vertexai_config` for Vertex AI embeddings.

### Bedrock Embeddings
| Model | Dimensions | Notes |
|-------|-----------|-------|
| amazon.titan-embed-text-v2:0 | 1024 | **Recommended** - Latest with normalization |
| amazon.titan-embed-text-v1 | 1536 | Legacy Titan model |
| cohere.embed-english-v3 | 1024 | English-optimized |
| cohere.embed-multilingual-v3 | 1024 | Multilingual support |

### Fireworks Embeddings
| Model | Dimensions | Notes |
|-------|-----------|-------|
| nomic-ai/nomic-embed-text-v1.5 | 768 | **Recommended** - Latest Nomic model |
| nomic-ai/nomic-embed-text-v1 | 768 | Previous version |
| WhereIsAI/UAE-Large-V1 | 1024 | Multilingual support |

### OpenAI-Like Embeddings (`openai_like`)

Any model served via a `/v1/embeddings` endpoint. Common choices:

| Model | Dimensions | Notes |
|-------|-----------|-------|
| nomic-embed-text | 768 | Popular local model, good balance |
| BAAI/bge-m3 | 1024 | Multilingual, high quality |
| BAAI/bge-large-en-v1.5 | 1024 | English-focused, high quality |
| BAAI/bge-small-en-v1.5 | 384 | Fast, lightweight |
| all-MiniLM-L6-v2 | 384 | Very fast, lower quality |
| mxbai-embed-large | 1024 | High quality |

> Always set `EMBEDDING_DIMENSION` explicitly for models not in the auto-detect list.

### LiteLLM Embeddings (`litellm`)

LiteLLM can route to any embedding backend. The model name is whatever your LiteLLM proxy config defines. Common examples:

| LiteLLM model name | Backend | Dimensions |
|---|---|---|
| text-embedding-3-small | OpenAI | 1536 |
| text-embedding-3-large | OpenAI | 3072 |
| ollama/nomic-embed-text | Ollama | 768 |
| bedrock/amazon.titan-embed-text-v2:0 | Bedrock | 1024 |
| vertex_ai/text-embedding-004 | Vertex AI | 768 |

> Set `EMBEDDING_DIMENSION` if the model is not auto-detected.

---

## Advanced Configurations

### LLM Extraction Mode

`LLM_EXTRACTION_MODE` controls how LlamaIndex calls the LLM during knowledge graph extraction (entity/relation extraction). Set in `.env`:

```ini
LLM_EXTRACTION_MODE=function      # default — tool/function calling mode
#LLM_EXTRACTION_MODE=json_schema  # structured output / JSON schema mode (PydanticProgramMode.DEFAULT)
#LLM_EXTRACTION_MODE=auto         # let LlamaIndex decide (also maps to DEFAULT internally)
```

| Mode | Description | When to use |
|------|-------------|-------------|
| `function` | Tool/function calling (default) | Recommended for all providers. Avoids OpenAI `additionalProperties: false` structured output bug. |
| `json_schema` | JSON schema / structured output mode | Only if a specific model/server performs better without tool calling. |
| `auto` | LlamaIndex default (maps to `DEFAULT`/JSON schema internally) | Not recommended — same as `json_schema` but less explicit. |

**Provider-specific overrides** (in `.env`):
- `OPENAI_LIKE_FUNCTION_CALLING=true/false` — override for openai_like provider
- `LITELLM_FUNCTION_CALLING=true/false` — no effect currently (unused in code; `LLM_EXTRACTION_MODE` controls this globally)

**Notes:**
- Gemini/Vertex AI: `pydantic_program_mode=FUNCTION` is forced in code regardless of this setting (required to disable AFC)
- Ollama: does not use `pydantic_program_mode` — log line for resolved mode will not appear for Ollama (expected)
- Groq/Fireworks/Bedrock/OpenAI-Like/OpenRouter: auto-switch to `DynamicLLMPathExtractor` which uses `apredict()` (plain text), so this setting has no effect for those providers



### Mix and Match Strategy

**Best for Production (Fast + Private):**
```bash
# Ultra-fast Groq LLM + local embeddings
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.3-70b-versatile
EMBEDDING_KIND=ollama
EMBEDDING_MODEL=nomic-embed-text  # Local embeddings for privacy
```

**Best for Cloud Performance:**
```bash
# Fast Groq LLM + Fast Fireworks embeddings
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.3-70b-versatile
EMBEDDING_KIND=fireworks
FIREWORKS_API_KEY=your-fireworks-api-key
EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
```

**Best for Privacy (100% Local):**
```bash
# Everything local
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:3b
# Default Ollama embeddings (nomic-embed-text)
```

**Best for Quality:**
```bash
# Best models for both
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-large  # 3072 dims
```

**Best for Cost:**
```bash
# Free local LLM + embeddings
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:3b
# Default Ollama embeddings
```

**Best for Google Cloud Integration:**
```bash
# Native Vertex AI integration
LLM_PROVIDER=vertex_ai
VERTEX_AI_PROJECT=your-gcp-project-id
VERTEX_AI_MODEL=gemini-2.0-flash-001
# Default Vertex AI embeddings (text-embedding-004, 768 dims)
```

**Best for AWS Integration:**
```bash
# Native Bedrock integration
LLM_PROVIDER=bedrock
BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_REGION=us-east-1
# Default Bedrock embeddings (amazon.titan-embed-text-v2:0, 1024 dims)
```

### 17. OpenAI-Like LLM (any OpenAI-compatible API — including vLLM Docker)

Use for: Ollama `/v1` endpoint, vLLM Docker container, or any other OpenAI-compatible server.

```bash
LLM_PROVIDER=openai_like
OPENAI_LIKE_MODEL=local-model               # Model name as reported by your server
OPENAI_LIKE_API_BASE=http://localhost:PORT/v1
OPENAI_LIKE_API_KEY=local                   # Any string if auth not required
OPENAI_LIKE_CONTEXT_WINDOW=4096
OPENAI_LIKE_FUNCTION_CALLING=true           # Set false if model doesn't support tool calling
```

**Quick test with already-running Ollama** — Ollama exposes an OpenAI-compatible endpoint at `/v1`:
```bash
LLM_PROVIDER=openai_like
OPENAI_LIKE_MODEL=gpt-oss:20b              # any model tag already pulled in Ollama
OPENAI_LIKE_API_BASE=http://localhost:11434/v1
OPENAI_LIKE_API_KEY=ollama                 # any non-empty string — Ollama ignores it
OPENAI_LIKE_CONTEXT_WINDOW=8192
OPENAI_LIKE_FUNCTION_CALLING=false
```

**With local embeddings from the same server** (uses `OpenAILikeEmbedding`):
```bash
EMBEDDING_KIND=openai_like
EMBEDDING_MODEL=nomic-embed-text
OPENAI_LIKE_EMBEDDING_API_BASE=http://localhost:PORT/v1  # Can differ from LLM base
EMBEDDING_DIMENSION=768
```

**With OpenAI embeddings** (mix local LLM + cloud embeddings):
```bash
EMBEDDING_KIND=openai
OPENAI_API_KEY=your_openai_key
EMBEDDING_MODEL=text-embedding-3-small
```

### 18. vLLM (High-Performance Local Inference)

vLLM is a high-throughput inference engine with an OpenAI-compatible API. There are two ways to run it:

#### Option 1: Docker — all platforms (Windows, macOS, Linux) — recommended

Start the container (requires NVIDIA GPU):
```bash
docker compose -p flexible-graphrag -f docker/includes/vllm.yaml up -d
# or uncomment includes/vllm.yaml in docker/docker-compose.yaml
```

Connect the backend using `LLM_PROVIDER=openai_like`:
```bash
LLM_PROVIDER=openai_like
OPENAI_LIKE_MODEL=Qwen/Qwen2.5-7B-Instruct
OPENAI_LIKE_API_BASE=http://localhost:8002/v1
OPENAI_LIKE_API_KEY=fake
OPENAI_LIKE_CONTEXT_WINDOW=8192
OPENAI_LIKE_FUNCTION_CALLING=false
```

Optionally override container defaults (Docker Compose picks these up automatically from `.env`):
```bash
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct   # HuggingFace model ID (default: Qwen2.5-7B-Instruct)
VLLM_MAX_MODEL_LEN=8192               # max context length in tokens (default: 8192)
VLLM_GPU_UTIL=0.90                    # fraction of GPU VRAM to use, 0.0-1.0 (default: 0.90)
VLLM_DTYPE=auto                       # weight dtype: auto, float16, bfloat16 (default: auto)
VLLM_MAX_NUM_SEQS=16                  # max concurrent sequences (default: 16)
HF_TOKEN=                             # HuggingFace token — only needed for gated models (Llama etc.)
```

Recommended models (no HF token required):

| Model | VRAM | Notes |
|-------|------|-------|
| `Qwen/Qwen2.5-7B-Instruct` | ~15 GB | good general purpose |
| `Qwen/Qwen2.5-14B-Instruct` | ~28 GB | higher quality |
| `Qwen/Qwen2.5-32B-Instruct` | ~65 GB | best quality, fits RTX 5090 |
| `microsoft/Phi-4` | ~10 GB | fast, strong reasoning |

See `docker/includes/vllm.yaml` for port mapping and container configuration details.
See `docs/DOCKER-RESOURCE-CONFIGURATION.md` for WSL2/Docker memory sizing guidance.

#### Option 2: vLLM Python package — Linux / macOS (UNTESTED)

Not available on Windows. macOS support is experimental upstream.
Requires: `pip install vllm`

```bash
LLM_PROVIDER=vllm
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct
VLLM_MAX_MODEL_LEN=8192
VLLM_GPU_UTIL=0.90
```

**With vLLM serving an embedding model** (uses `OpenAILikeEmbedding`):
```bash
# Start a separate vLLM instance for embeddings:
# vllm serve BAAI/bge-m3 --port 8003
EMBEDDING_KIND=openai_like
EMBEDDING_MODEL=BAAI/bge-m3
OPENAI_LIKE_EMBEDDING_API_BASE=http://localhost:8003/v1
EMBEDDING_DIMENSION=1024
```

### 19. LiteLLM Proxy (100+ Providers)

LiteLLM provides a unified OpenAI-compatible proxy for 100+ LLM and embedding providers.

Install the proxy extra (the `litellm` package alone is not enough):
```powershell
pip install "litellm[proxy]"   # PowerShell / bash
pip install litellm[proxy]     # cmd (no quotes needed)
```

Start the proxy:
```bash
litellm --model ollama/gpt-oss:20b --port 4000   # Ollama backend (recommended for local testing)
litellm --model gpt-4o-mini --port 4000           # OpenAI backend
litellm --config litellm_config.yaml --port 4000  # Custom multi-model config
```

```bash
LLM_PROVIDER=litellm
LITELLM_MODEL=gpt-4o-mini             # Model as configured in LiteLLM
LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=local
```

**With LiteLLM embeddings** (uses `LiteLLMEmbedding`):
```bash
EMBEDDING_KIND=litellm
EMBEDDING_MODEL=text-embedding-3-small
LITELLM_EMBEDDING_API_BASE=http://localhost:4000  # Can be same or different proxy
LITELLM_API_KEY=local
```

**Benefits of LiteLLM:**
- 🔄 **Unified API**: Switch backends without changing app code
- 🔁 **Fallbacks**: Automatic failover between providers
- 📊 **Observability**: Built-in logging and cost tracking
- 🔐 **Key Management**: Centralized API key management

### 20. OpenRouter (200+ Models)

OpenRouter provides a single API key for 200+ models from OpenAI, Anthropic, Meta, Mistral, and more.

```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-your-key-here
OPENROUTER_MODEL=openai/gpt-4o-mini
# Other models: anthropic/claude-3-5-sonnet, meta-llama/llama-3.3-70b-instruct,
#               mistralai/mistral-large, google/gemini-2.0-flash, deepseek/deepseek-r1
```

**With OpenAI embeddings** (recommended - OpenRouter doesn't have its own embedding models):
```bash
EMBEDDING_KIND=openai
OPENAI_API_KEY=your_openai_key
EMBEDDING_MODEL=text-embedding-3-small
```

**Or with local Ollama embeddings** (no additional API key needed):
```bash
EMBEDDING_KIND=ollama
EMBEDDING_MODEL=nomic-embed-text
```

---

## OpenAI-Like Embedding Details

### `EMBEDDING_KIND=openai_like` — `OpenAILikeEmbedding` class

Use for any server that exposes a `/v1/embeddings` endpoint in OpenAI format:
- **LM Studio** — local model server with GUI
- **LocalAI** — drop-in OpenAI replacement, runs locally
- **vLLM** — when serving an embedding model
- **Llamafile** — single-file model executables
- **text-generation-webui** — with OpenAI extension enabled
- **Ollama** — via its OpenAI-compatible endpoint (`/v1`)

```bash
EMBEDDING_KIND=openai_like
EMBEDDING_MODEL=nomic-embed-text        # or BAAI/bge-m3, all-MiniLM-L6-v2, etc.
OPENAI_LIKE_EMBEDDING_API_BASE=http://localhost:11434/v1  # Ollama — or replace with your server's /v1 URL
OPENAI_LIKE_API_KEY=local               # Required field, any string if not enforced
EMBEDDING_DIMENSION=768                 # Required for nomic-embed-text; set explicitly
```

**Confirmed working (2026-03-20):** `nomic-embed-text` via Ollama at `http://localhost:11434/v1` with any LLM provider (tested: OpenAI gpt-4.1-mini, gpt-4o-mini).

**Auto-detected dimensions** (no need to set `EMBEDDING_DIMENSION`):
| Model pattern | Dimensions |
|---|---|
| `nomic*` | 768 |
| `bge*` | 1024 |
| `*3-small*` or `*ada*` | 1536 |
| `*3-large*` | 3072 |
| Other | 1536 (default, set explicitly) |

**Key variable**: `OPENAI_LIKE_EMBEDDING_API_BASE` is **independent** of `OPENAI_LIKE_API_BASE` (LLM). You can run LLM and embeddings on different ports or servers.

---

## LiteLLM Embedding Details

### `EMBEDDING_KIND=litellm` — `LiteLLMEmbedding` class

Routes embedding requests through a LiteLLM proxy. The proxy can be configured to use any backend:

```bash
EMBEDDING_KIND=litellm
EMBEDDING_MODEL=text-embedding-3-small  # Model name as configured in your LiteLLM proxy
LITELLM_EMBEDDING_API_BASE=http://localhost:4000/v1  # Must include /v1 suffix
LITELLM_API_KEY=local
```

**Confirmed working (2026-03-19):** `text-embedding-3-small` via LiteLLM proxy (`localhost:4000/v1`) — proxy adds zero measurable overhead vs direct `EMBEDDING_KIND=openai`.

**Critical**: `LITELLM_EMBEDDING_API_BASE` must include `/v1` — without it, requests fail with `400: Invalid model name`.

**Key variable**: `LITELLM_EMBEDDING_API_BASE` is **independent** of `LITELLM_API_BASE` (LLM). You can point LLM and embeddings at different LiteLLM proxy instances or configs.

**Example LiteLLM proxy config** (`litellm_config.yaml`) routing embeddings to Ollama:
```yaml
model_list:
  - model_name: text-embedding-3-small
    litellm_params:
      model: ollama/nomic-embed-text
      api_base: http://localhost:11434
```

---

## Troubleshooting

### Dimension Mismatch Errors

If you switch embedding providers, you may need to clear your vector database:

```bash
# See docs/VECTOR-DIMENSIONS.md for cleanup instructions
```

### Missing Package Errors

**Google Embeddings:**
```bash
pip install llama-index-embeddings-google-genai
```

**Ollama Embeddings:**
```bash
# Pull the embedding model
ollama pull nomic-embed-text
```

**OpenAI-Like Embeddings:**
```bash
pip install llama-index-embeddings-openai-like
```

**LiteLLM Embeddings:**
```bash
pip install llama-index-embeddings-litellm
```

**vLLM LLM:**
```bash
pip install llama-index-llms-vllm
```

**LiteLLM LLM:**
```bash
pip install llama-index-llms-litellm
```

**OpenRouter LLM:**
```bash
pip install llama-index-llms-openrouter
```

> All of the above are included in `requirements.txt` and as optional dependencies in `pyproject.toml`.

---

## Performance Considerations

### Speed Comparison (Embeddings)
1. **Ollama all-minilm** - Fastest (384 dims)
2. **Ollama nomic-embed-text** - Good balance (768 dims) ✅ Recommended
3. **OpenAI text-embedding-3-small** - Cloud API (1536 dims)
4. **Ollama mxbai-embed-large** - Highest quality (1024 dims)
5. **OpenAI text-embedding-3-large** - Highest quality cloud (3072 dims)

### Cost Comparison
- **Ollama**: Free (local processing)
- **OpenAI**: ~$0.00002 per 1K tokens (embeddings)
- **Google**: Varies by usage
- **Azure**: Similar to OpenAI

### Privacy Comparison
- **Ollama**: 🔒 100% Local - Maximum privacy
- **OpenAI/Google/Azure**: ☁️ Cloud-based - Data sent to provider

---

## See Also

- [Vector Database Dimensions](../VECTOR-DATABASES/VECTOR-DIMENSIONS.md)
- [Performance Benchmarks](../PERFORMANCE.md)
- [Ollama Configuration](OLLAMA-CONFIGURATION.md)

