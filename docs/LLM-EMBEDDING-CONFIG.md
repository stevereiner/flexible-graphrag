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
  - Options: `openai`, `ollama`, `gemini`, `vertex_ai`, `anthropic`, `azure_openai`, `bedrock`, `groq`, `fireworks`

### Embedding Configuration (Independent)
- `EMBEDDING_KIND`: Type of embedding provider *(optional - defaults to LLM provider)*
  - Options: `openai`, `ollama`, `google`, `vertex`, `azure`, `bedrock`, `fireworks`
- `EMBEDDING_MODEL`: Specific model name
- `EMBEDDING_DIMENSION`: Explicit dimension override *(optional)*

---

## Provider Defaults

When `EMBEDDING_KIND` is **not specified**, embeddings automatically match the LLM provider:

| LLM Provider | Default Embedding | Model | Dimensions |
|--------------|------------------|-------|------------|
| **OpenAI** | OpenAI | text-embedding-3-small | 1536 |
| **Ollama** | Ollama | nomic-embed-text | 768 |
| **Gemini** | Google | text-embedding-004 | 768 |
| **Vertex AI** | Vertex AI | text-embedding-004 | 768 |
| **Anthropic** | Ollama | nomic-embed-text | 768 |
| **Azure OpenAI** | Azure OpenAI | text-embedding-3-small | 1536 |
| **Bedrock** | Bedrock | amazon.titan-embed-text-v2:0 | 1024 |
| **Groq** | Ollama | nomic-embed-text | 768 |
| **Fireworks** | Fireworks | nomic-ai/nomic-embed-text-v1.5 | 768 |

---

## Configuration Examples

### 1. OpenAI LLM with OpenAI Embeddings (Default)

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o-mini
# No EMBEDDING_KIND - uses OpenAI embeddings by default
# EMBEDDING_MODEL=text-embedding-3-small (1536 dims)
```

### 2. OpenAI LLM with Local Ollama Embeddings (Privacy + Cost Savings)

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o-mini

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
GEMINI_MODEL=gemini-2.0-flash
# No EMBEDDING_KIND - uses Google embeddings by default
# EMBEDDING_MODEL=text-embedding-004 (1536 dims)
```

**Note**: Google deprecated `text-embedding-001`. Use `text-embedding-004` instead.

### 6. Gemini LLM with Custom Dimension Google Embeddings

```bash
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your_key
GEMINI_MODEL=gemini-2.0-flash

# Use Google embeddings with custom dimension
EMBEDDING_KIND=google
EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIMENSION=768  # Override default 1536 (supports 768, 1536, or 3072)
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
OLLAMA_MODEL=llama3.2:3b
OLLAMA_BASE_URL=http://localhost:11434
# No EMBEDDING_KIND - uses Ollama embeddings by default
# EMBEDDING_MODEL=nomic-embed-text (768 dims)
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

---

## Advanced Configurations

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

- [Vector Database Dimensions](VECTOR-DIMENSIONS.md)
- [Performance Benchmarks](PERFORMANCE.md)
- [Ollama Configuration](OLLAMA-CONFIGURATION.md)

