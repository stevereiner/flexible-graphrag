# LLM and Embedding Configuration Guide

## Overview

Flexible GraphRAG allows you to configure **LLM providers** (for reasoning/generation) and **embedding providers** (for vector embeddings) **independently**. This enables powerful combinations like:

- **OpenAI LLM + Ollama embeddings** - Fast reasoning with local/private embeddings
- **Anthropic Claude + Ollama embeddings** - Advanced reasoning with cost-effective local embeddings
- **Gemini LLM + Google embeddings** - Native Google integration
- **Any LLM + Local embeddings** - Privacy-focused configurations

---

## Configuration Parameters

### LLM Configuration
- `LLM_PROVIDER`: The LLM provider for reasoning/generation
  - Options: `openai`, `ollama`, `gemini`, `anthropic`, `azure`

### Embedding Configuration (Independent)
- `EMBEDDING_KIND`: Type of embedding provider *(optional - defaults to LLM provider)*
  - Options: `openai`, `ollama`, `google`, `azure`
- `EMBEDDING_MODEL`: Specific model name
- `EMBEDDING_DIMENSION`: Explicit dimension override *(optional)*

---

## Provider Defaults

When `EMBEDDING_KIND` is **not specified**, embeddings automatically match the LLM provider:

| LLM Provider | Default Embedding | Model | Dimensions |
|--------------|------------------|-------|------------|
| **OpenAI** | OpenAI | text-embedding-3-small | 1536 |
| **Ollama** | Ollama | nomic-embed-text | 768 |
| **Gemini** | Google | text-embedding-004 | 1536 |
| **Anthropic** | Ollama | nomic-embed-text | 768 |
| **Azure OpenAI** | Azure OpenAI | text-embedding-3-small | 1536 |

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

### 10. Ollama LLM with Ollama Embeddings (Fully Local)

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

---

## Advanced Configurations

### Mix and Match Strategy

**Best for Production:**
```bash
# Fast reasoning + local embeddings
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_KIND=ollama
EMBEDDING_MODEL=nomic-embed-text
```

**Best for Privacy:**
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

