# LLM Testing Results

Comprehensive testing results for different LLM and embedding provider combinations with GraphRAG.

## Test Summary

| LLM Provider / Model | Graph Extraction | Search with Graph | AI Query with Graph | Notes |
|----------------------|------------------|-------------------|---------------------|-------|
| **OpenAI** (gpt-4.1-mini recommended, gpt-4o-mini, etc.) | ✅ Full entities/relationships | ✅ Works | ✅ Works | `gpt-4.1-mini` recommended — zero 0-entity failures, 3-4x faster than gpt-4o-mini on multi-chunk docs (2026-03-20) |
| **Azure OpenAI** (gpt-4o-mini) | ✅ Full entities/relationships | ✅ Works | ✅ Works | Same as OpenAI, enterprise hosting |
| **Google Gemini** (gemini-3-flash-preview, gemini-3.1-pro-preview) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-03-15**: AFC disabled + `pydantic_program_mode=FUNCTION` required. Note: gemini-3-pro-preview deprecated |
| **Google Vertex AI** (gemini-2.5-flash) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-03-15**: Same fixes as Gemini. Note: `gemini-3-flash-preview` not available on Vertex AI |
| **Anthropic Claude** (sonnet-4-5, haiku-4-5) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-01-09**: Event loop fix restored extraction |
| **Ollama** (`gpt-oss:20b` recommended — see section below) | ✅ Full entities/relationships | ✅ Works | ✅ Works | Use `gpt-oss:20b` only; `llama3.1:8b`/`llama3.2:3b` not recommended |
| **Groq** (openai/gpt-oss-20b, llama-3.3-70b-versatile) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-03-17**: LlamaIndex assigned wrong context_window (3900) for Groq models causing `finish_reason: length`. Now fixed with correct context/max_tokens. Uses `DynamicLLMPathExtractor`. |
| **Fireworks AI** (gpt-oss-120b and others) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Fixed 2026-03-17**: `max_tokens` defaulted to 256 causing silent truncation. Now set to 32768. Uses `DynamicLLMPathExtractor`. |
| **Amazon Bedrock** (claude-sonnet, gpt-oss, deepseek-r1, llama3) | ✅ Full entities/relationships | ✅ Works | ✅ Works | Auto-switches to `DynamicLLMPathExtractor`; `use_ontology=True` + `DISABLE_PROPERTIES=true` confirmed working (33 nodes/59 rels, both docs) |
| **OpenAI-Like** (any OpenAI-compatible API — Ollama /v1, vLLM Docker) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Added 2026-03-19**: Auto-switches to `DynamicLLMPathExtractor`. Use for vLLM Docker (`localhost:8002`) or Ollama `/v1` endpoint. |
| **vLLM** (Docker container, any HuggingFace model) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Added 2026-03-19**: Use `LLM_PROVIDER=openai_like` pointing at vLLM Docker port 8002. `LLM_PROVIDER=vllm` (Python package) Linux/macOS only, untested. |
| **LiteLLM** (proxy for 100+ providers) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Added 2026-03-19**: Cloud models (gpt-4o-mini) use `SchemaLLMPathExtractor`; Ollama-backed models auto-switch to `DynamicLLMPathExtractor`. Proxy runs in WSL2 on Windows. |
| **OpenRouter** (unified API, 200+ models) | ✅ Full entities/relationships | ✅ Works | ✅ Works | **Added 2026-03-19**: Auto-switches to `DynamicLLMPathExtractor` (OpenRouter extends OpenAILike, tool-calling incompatible). Requires `context_window=128000` + `max_tokens=16384`. |

### Graph Database Compatibility

All graph databases (Neo4j, Ladybug, FalkorDB, ArcadeDB, MemGraph, etc.) show identical behavior patterns based on the LLM provider used, not the database choice:

- **OpenAI/Azure OpenAI**: Full graph extraction with entities and relationships works on all databases
- **Google Gemini**: Full graph extraction works with `use_ontology=True` (AFC disabled + `pydantic_program_mode=FUNCTION` fixes applied 2026-03-15)
- **Google Vertex AI**: Full graph extraction works — benchmarks run with `use_ontology=False`, needs retest with `use_ontology=True`
- **Anthropic Claude (direct)**: Full graph extraction works — benchmarks run with `use_ontology=False`, needs retest with `use_ontology=True`
- **Bedrock**: `DynamicLLMPathExtractor` confirmed working after LlamaIndex bug fixes — `use_ontology=True` + `DISABLE_PROPERTIES=true` gives best results (33 nodes/59 rels both docs)
- **Groq**: `DynamicLLMPathExtractor` confirmed working after context_window fix (2026-03-17) — 60 nodes/137 rels both docs in 14s
- **Fireworks**: `DynamicLLMPathExtractor` — max_tokens fix applied (2026-03-17); retest pending

## Google Gemini Models

### Tested Models
- ✅ `gemini-3-flash-preview` - Full graph building, search and query work (fast, recommended)
- ✅ `gemini-3.1-pro-preview` - Full graph building, search and query work (pro quality)
- ✅ `gemini-2.5-flash` - Full graph building, search and query work
- ⚠️ `gemini-3-pro-preview` - Full graph building, search and query work — **deprecated, use `gemini-3.1-pro-preview`**

### Embedding
- ✅ `gemini-embedding-2-preview` (768 dims) — current recommended Google embedding model
- ❌ `text-embedding-004` — deprecated 2026-01-14

### Known Issues
- ✅ **Fixed 2026-01-08**: Graph search/query async event loop conflicts resolved
- ✅ **Fixed 2026-03-14**: AFC (Automatic Function Calling) disabled in `factories.py` — AFC was intercepting `SchemaLLMPathExtractor` tool calls before Gemini could respond, causing 0 entities/relationships to be extracted. Log signature: `AFC is enabled with max remote calls: 10.` followed immediately by `Total: 0 entities, 0 relations`.
- ✅ **Fixed 2026-03-15**: `pydantic_program_mode=FUNCTION` now explicitly passed to `GoogleGenAI` — previously omitted, causing `DEFAULT` (JSON schema) mode which silently returned 0 entities in 5ms when `use_ontology=True`. Both fixes together are required for full entity/relationship extraction.
- Gemini creates full knowledge graphs with proper entities and relationships on all graph databases
- Search and AI query now work correctly with graph enabled

### Benchmark Results — `gemini-3-flash-preview`, SchemaLLMPathExtractor, `use_ontology=True`
**Hardware**: AMD 9950X3D, NVIDIA RTX 5090, 128GB RAM, Windows 11  
**Storage mode**: `ingestion_storage_mode=both` (Neo4j + GraphDB in single pass)  
**Embedding**: `gemini-embedding-2-preview` (768 dims)  
**Ontology**: `company_classes.ttl`, `company_properties.ttl`, `common_ontology.ttl`

| Doc | Neo4j Nodes | Neo4j Rels | GraphDB Rows | Time |
|-----|-------------|------------|--------------|------|
| `cmispress.txt` | 22 | 41 | 209 | 24.80s |
| Both docs total | 58 | 123 | 551 | +47.34s (`company-ontology-test.txt`) |

**Performance breakdown** (`company-ontology-test.txt`): Pipeline: 1.06s, Vector: 0.24s, Graph: 46.00s

### Sample Q&A Result
Query: *"Who works at Acme?"* — Returns names + roles + departments:
> Sarah Chen (Senior Software Engineer, Engineering), Marcus Rivera (Software Engineer, Engineering), Priya Patel (Software Engineer, Engineering), James Okafor (Head of Product, Product Management), Linda Torres (Account Executive, Sales)

## Google Vertex AI Models

### Tested Models
- ✅ `gemini-2.5-flash` - Full graph building, search and query work (confirmed 2026-03-15)
- ⚠️ `gemini-3-flash-preview` - Not available on Vertex AI (use `gemini-2.5-flash` instead)

### Configuration Notes
- Uses modern `google-genai` package with `GoogleGenAI` and `GoogleGenAIEmbedding` classes
- Requires `vertexai_config` parameter with project and location
- Cleaned up implementation - removed deprecated `llama-index-llms-vertex` and `llama-index-embeddings-vertex` packages
- Environment variables (`GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`) are set automatically by the code

### Known Issues
- ✅ **Fixed 2026-01-08**: Graph search/query async event loop conflicts resolved (same fix as Gemini)
- ✅ **Fixed 2026-03-15**: AFC disabled + `pydantic_program_mode=FUNCTION` explicitly passed — same root cause as Gemini (see Gemini Known Issues)
- Vertex AI creates full knowledge graphs with proper entities and relationships on all graph databases
- Search and AI query now work correctly with graph enabled

### Benchmark Results — `gemini-2.5-flash`, SchemaLLMPathExtractor, `use_ontology=False` ⚠️ needs retest with `use_ontology=True`
**Hardware**: AMD 9950X3D, NVIDIA RTX 5090, 128GB RAM, Windows 11  
**Storage mode**: `ingestion_storage_mode=both` (Neo4j + GraphDB in single pass)  
**Embedding**: `gemini-embedding-2-preview` via Vertex AI (768 dims)  
**Ontology**: `company_classes.ttl`, `company_properties.ttl`, `common_ontology.ttl` (loaded in store but `use_ontology=False` — ontology not used for extraction)

| Doc | Neo4j Nodes | Neo4j Rels | GraphDB Rows | Time |
|-----|-------------|------------|--------------|------|
| `cmispress.txt` | 26 | 45 | 245 | 26.01s |
| Both docs total | 61 | 124 | 582 | +34.65s (`company-ontology-test.txt`) |

**Performance breakdown** (`company-ontology-test.txt`): Pipeline: 1.07s, Vector: 0.52s, Graph: 33.02s

### Sample Q&A Result
Query: *"Who works at Acme?"* — Returns names only (vs. Gemini direct which returns names + roles + departments)

## Anthropic Claude Models

### Tested Models
- ✅ `claude-sonnet-4-5-20250929` - Full graph building with entities/relationships, search and AI query work
- ✅ `claude-haiku-4-5-20251001` - Full graph building with entities/relationships, search and AI query work

### Known Issues
- **Fixed 2026-01-09**: Event loop fix restored full entity/relationship extraction (was previously showing "chunk nodes only")
- Both models now create proper entities and relationships with the async event loop fix

### Benchmark Results — `claude-sonnet-4-5-20250929`, SchemaLLMPathExtractor, `use_ontology=False` ⚠️ needs retest with `use_ontology=True`
**Hardware**: AMD 9950X3D, NVIDIA RTX 5090, 128GB RAM, Windows 11  
**Storage mode**: `ingestion_storage_mode=both` (Neo4j + GraphDB in single pass)  
**Embedding**: `text-embedding-3-small` (OpenAI, 1536 dims)  
**Ontology**: `company_classes.ttl`, `company_properties.ttl`, `common_ontology.ttl` (loaded in store but `use_ontology=False` — ontology not used for extraction)

| Doc | Neo4j Nodes | Neo4j Rels | GraphDB Rows | Time |
|-----|-------------|------------|--------------|------|
| `cmispress.txt` | 26 | 45 | 245 | 21.00s |
| Both docs total | 53 | 116 | 503 | +13.76s (`company-ontology-test.txt`) |

### Sample Q&A Result
Query: *"Who works at Acme?"* — Returns names + roles + departments:
> Sarah Chen (Senior Software Engineer, Engineering), Marcus Rivera (Software Engineer, Engineering), Priya Patel (Software Engineer, Engineering), James Okafor (Head of Product, Product Management), Linda Torres (Account Executive, Sales)

## Groq Models

### Tested Models
- ✅ `openai/gpt-oss-20b` — Full graph extraction (60 nodes, 137 rels, both docs) — **Fixed 2026-03-17**
- ✅ `llama-3.3-70b-versatile` — Full graph extraction — same fix applies
- ✅ `openai/gpt-oss-120b` — Expected to work (same fix; untested)
- ✅ `llama-3.1-8b-instant` — Expected to work (same fix; untested)

### Benchmark — `llama-3.3-70b-versatile`, DynamicLLMPathExtractor, `use_ontology=False` (2026-03-17)

**Test conditions:** `DynamicLLMPathExtractor` (auto-switched from `schema`), `auto` extraction mode, `text-embedding-3-small` (1536-dim), Neo4j only, no ontology, no properties.

| Document | Time | Extracted | Neo4j display | Chunks |
|----------|------|-----------|---------------|--------|
| `cmispress.txt` (2480 chars) | **6.60s** | 40 entities, 20 rels | 24 nodes, 43 rels | 1 |
| `company-ontology-test.txt` (5618 chars, 2nd doc) | **7.56s** | 104 entities, 52 rels | +36 nodes, +94 rels | 2 |
| **Both docs combined (Neo4j)** | **14.16s** | — | **60 nodes, 137 rels** | 3 |

*Log source: `flexible-graphrag-api-20260317-030532.log`*

### Benchmark — `openai/gpt-oss-20b`, DynamicLLMPathExtractor, `use_ontology=True`, properties on, `function` mode (2026-03-17)

**Test conditions:** `DynamicLLMPathExtractor`, `function` extraction mode, `text-embedding-3-small`, Neo4j + GraphDB, ontology: 16 entity types / 22 relation types / 13 entity props / 4 relation props.

| Document | Time | Extracted | Neo4j display | Chunks |
|----------|------|-----------|---------------|--------|
| `cmispress.txt` (2480 chars) | **14.50s** | 40 entities, 20 rels | 23 nodes, 42 rels | 1 |
| `company-ontology-test.txt` (5618 chars, 2nd doc) | **15.84s** | 40 entities, 20 rels (14+26, capped) | +20 nodes, +39 rels | 2 |
| **Both docs combined (Neo4j)** | **30.34s** | — | **43 nodes, 81 rels** | 3 |

*Log source: `flexible-graphrag-api-20260317-053953.log`*

**Note:** Both runs had `DISABLE_PROPERTIES=true`. The ontology+properties run used `gpt-oss-20b` (different model) vs `llama-3.3-70b-versatile` in the no-ontology run, so the drop (43 vs 60 nodes, 81 vs 137 rels) reflects a combination of model difference, ontology constraints, and properties overhead. Next test: `gpt-oss-20b` with `use_ontology=True` + `DISABLE_PROPERTIES=true` to isolate the model vs ontology factors.

### Configuration Notes
- Ultra-fast LPU (Language Processing Unit) architecture for low-latency inference
- All Groq models have 131,072 context window — LlamaIndex doesn't know Groq-specific models and defaults to 3900 tokens. flexible-graphrag overrides this automatically.
- **Auto-switches to `DynamicLLMPathExtractor`** — `SchemaLLMPathExtractor` broken in LlamaIndex 0.14.x (tool_choice conflict). `DynamicLLMPathExtractor` now works after context_window fix.
- `is_function_calling_model=False` is set on the extractor's LLM instance — `DynamicLLMPathExtractor` uses `apredict()` (plain text), not tool calls
- Search and AI query work correctly with graph enabled

### Known Issues
- ✅ **Fixed 2026-03-17**: `DynamicLLMPathExtractor` returned 0 entities. Root cause: LlamaIndex's `openai_modelname_to_contextsize()` does not know Groq models → falls back to `context_window=3900` → `max_tokens` is calculated as `3900 - input_tokens ≈ 0` → model hits token limit immediately → `finish_reason: length` → empty `content` → `apredict()` returns `''`. Fixed by passing correct `context_window` and `max_tokens` per model in `factories.py`.
- ❌ **Still broken**: `SchemaLLMPathExtractor` — `OpenAI.astructured_predict` injects `tool_choice="required"` which `FunctionCallingProgram.acall` strips → model returns plain text → silent 0 entities. Auto-switches to Dynamic.

## Fireworks AI Models

### Tested Models (serverless + function calling)
- ✅ `accounts/fireworks/models/gpt-oss-120b` — Full graph extraction confirmed — **Fixed 2026-03-17**
- ✅ `accounts/fireworks/models/deepseek-v3p2` — Expected to work (same fix; untested post-fix)
- ✅ `accounts/fireworks/models/minimax-m2p5` — Expected to work (same fix; untested post-fix)
- ✅ `accounts/fireworks/models/kimi-k2p5` — Expected to work (same fix; untested post-fix)
- ✅ `accounts/fireworks/models/qwen3-vl-30b-a3b-thinking` — Expected to work (same fix; untested post-fix)

### Benchmark — `accounts/fireworks/models/gpt-oss-120b`, DynamicLLMPathExtractor, `use_ontology=True`, properties on, `function` mode (2026-03-17)

**Test conditions:** `DynamicLLMPathExtractor` (auto-switched), `function` extraction mode, `text-embedding-3-small`, Neo4j + GraphDB, ontology: 16 entity types / 22 relation types / 13 entity props / 4 relation props, streaming mode (`_FireworksStreaming`), `max_tokens=16384`.

| Document | Time | Neo4j display | Chunks |
|----------|------|---------------|--------|
| `cmispress.txt` (2480 chars) | **21.34s** | 22 nodes, 41 rels | 1 |
| `company-ontology-test.txt` (5618 chars, 2nd doc) | **34.49s** | +25 nodes, +60 rels | 2 (parallel) |
| **Both docs combined (Neo4j)** | **55.83s** | **47 nodes, 101 rels** | 3 |

*Log source: `flexible-graphrag-api-20260317-075958.log`*

**Notes:**
- All chunks extract fully (40/20 and 30/15 entities/rels per chunk); `finish_reason=stop` throughout
- Run-to-run variance of ~20-30% in final Neo4j counts is normal LLM non-determinism at temperature=0.1

### Configuration Notes
- Supports wide model selection (Meta, Qwen, Mistral AI, DeepSeek, OpenAI GPT-OSS, Kimi, GLM, MiniMax)
- **Does NOT support timeout parameter** (overrides `__init__` without including timeout parameter)
- **Auto-switches to `DynamicLLMPathExtractor`** — `SchemaLLMPathExtractor` throws code exceptions
- All tested models support function calling on Fireworks serverless
- `_custom_is_function_calling=False` is set on the extractor's LLM instance so `apredict()` receives plain text responses instead of tool calls
- All models: 131,072 context window; non-streaming API caps `max_tokens` at 4096

### Known Issues
- ✅ **Fixed 2026-03-17**: `max_tokens=256` default caused silent truncation → 0 entities. Fixed by `_FireworksStreaming` subclass overriding `_achat` to use `stream=True` (bypasses non-streaming 4096 cap). Default `max_tokens=16384`.
- ❌ **Still broken**: `SchemaLLMPathExtractor` — throws code exceptions (tool schema incompatibility). Auto-switches to Dynamic.

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
- **Embeddings**: `amazon.titan-embed-text-v2:0` (1024 dims) works; `text-embedding-3-small` (OpenAI, 1536 dims) also usable with Bedrock LLM
- **Cross-region inference profiles**: Most models require "us." prefix (e.g., `us.anthropic.claude-*`, `us.meta.llama*`, `us.deepseek.*`, `us.amazon.nova-premier-*`)
- **No prefix needed**: OpenAI GPT-OSS models and `amazon.nova-pro-v1:0` use standard model IDs without "us." prefix
- **Auto-switches to `DynamicLLMPathExtractor`** — Bedrock Converse API rejects `SchemaLLMPathExtractor`'s tool schema (`toolConfig.toolChoice.any` not supported). `pydantic_program_mode=FUNCTION` is set but insufficient — it's a Converse API constraint.
- **No switching for simple**: If you configure `KG_EXTRACTOR_TYPE=simple`, your choice is used as-is

### Known Issues
- ✅ **Fixed 2026-01-21**: Auto-switch `schema` → `dynamic` for Bedrock (correct — Converse API limitation)
- ✅ **Fixed 2026-03-16**: `DynamicLLMPathExtractor` now works correctly — two LlamaIndex bugs fixed: (1) props `None`→`[]` coercion causing `_apredict_with_props` to be called with empty prompt sections; (2) `SafeFormatter` not resolving `{{`→`{` in prompt template, causing model to receive malformed JSON examples. Both fixed in `_make_dynamic_extractor()`.
- Search and AI query work correctly with graph enabled

### Benchmark Results — `us.anthropic.claude-sonnet-4-5-20250929-v1:0`, Dynamic extractor
**Hardware**: AMD 9950X3D, NVIDIA RTX 5090, 128GB RAM, Windows 11  
**Storage mode**: `ingestion_storage_mode=both` (Neo4j + GraphDB in single pass)

**Run 1 — Embedding: `amazon.titan-embed-text-v2:0` (Bedrock, 1024 dims), `use_ontology=False`**

| Doc | Neo4j Nodes | Neo4j Rels | GraphDB Rows | Time |
|-----|-------------|------------|--------------|------|
| `cmispress.txt` | 13 | 22 | — | 13.25s |

**Run 2 — Embedding: `text-embedding-3-small` (OpenAI, 1536 dims), `use_ontology=False`**

| Doc | Neo4j Nodes | Neo4j Rels | GraphDB Rows | Time |
|-----|-------------|------------|--------------|------|
| `cmispress.txt` | 12 | 21 | 109 | 8.81s |
| Both docs total | 38 | 68 | 346 | +10.17s (`company-ontology-test.txt`) |

**Note (Run 2)**: `use_ontology=False` with `SCHEMA_NAME=default` still uses LlamaIndex's built-in internal node/relation type schema for `DynamicLLMPathExtractor` — it provides entity and relation type guidance (e.g. PERSON, ORGANIZATION, LOCATION, WORKS_FOR etc.) from LlamaIndex's `SAMPLE_SCHEMA` defaults. This is why Run 2 gives high counts — it has type guidance without any ontology file overhead.

**Run 3 — Embedding: `text-embedding-3-small`, `use_ontology=False`, `DISABLE_PROPERTIES=true` (2026-03-16, after LlamaIndex bug fixes)**

| Doc | Neo4j Nodes | Neo4j Rels | GraphDB Rows | Time |
|-----|-------------|------------|--------------|------|
| `cmispress.txt` | 10 | 17 | 89 | ~6s |

**Note (Run 3)**: Lower than Run 2 — this run had a single doc without the second doc's additive Neo4j dedup benefit. Double-brace prompt fix confirmed working. Log: `flexible-graphrag-api-20260316-013826.log`

**Run 4 — `use_ontology=True`, `DISABLE_PROPERTIES=true`, `text-embedding-3-small` (2026-03-16, after LlamaIndex bug fixes)**

| Doc | Extracted Entities | Extracted Rels | Neo4j Nodes | Neo4j Rels | GraphDB Rows | Time |
|-----|-------------------|----------------|-------------|------------|--------------|------|
| `cmispress.txt` | 18 | 9 | 11 | 19 | 99 | ~5s |
| `company-ontology-test.txt` | 34 (2 chunks) | 17 | +22 | +40 | 197 | ~6s |
| **Both docs total** | **52** | **26** | **33** | **59** | **296** | |

**Note (Run 4)**: `use_ontology=True` + `DISABLE_PROPERTIES=true` gives 33 nodes/59 rels — slightly lower than `use_ontology=False` Run 2 (38/68) because the company ontology types are more specific/restrictive than LlamaIndex's broad built-in schema (PERSON, ORG, LOCATION etc.). The ontology gives domain-correct typed labels (EMPLOYEE, COMPANY, DOCUMENT) while the built-in schema gives higher raw counts with generic labels. Trade-off: ontology = more accurate types, built-in schema = higher raw counts. Log: `flexible-graphrag-api-20260316-020217.log`

**Run 5 — `use_ontology=True`, `DISABLE_PROPERTIES=false` (properties enabled), `text-embedding-3-small` (2026-03-16)**

| Doc | Extracted Entities | Extracted Rels | Neo4j Nodes | Neo4j Rels | GraphDB Rows | Time |
|-----|-------------------|----------------|-------------|------------|--------------|------|
| `cmispress.txt` | 10 | 5 | 8 | 12 | 68 | ~9s |
| `company-ontology-test.txt` | 10 (2 chunks) | 5 | +8 | +12 | 71 | ~7s |
| **Both docs total** | **20** | **10** | **16** | **24** | **139** | |

**Note (Run 5)**: Enabling ontology properties (`DISABLE_PROPERTIES=false`) gives *worse* results than disabling them (16 nodes/24 rels vs. 33 nodes/59 rels in Run 4). The `_apredict_with_props` prompt adds property constraints that reduce the model's extraction breadth — Claude focuses on filling property fields rather than finding all entity/relation pairs. **Recommendation: use `DISABLE_PROPERTIES=true` with `use_ontology=True` for best Bedrock results.** Log: `flexible-graphrag-api-20260316-031613.log`

### Bedrock Recommended Configuration
```
USE_ONTOLOGY=true
DISABLE_PROPERTIES=true
BEDROCK_MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0
EMBEDDING_KIND=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```
Expected: ~33 nodes / 59 rels / ~296 RDF triples for both standard test docs.

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
| **Groq (llama-3.3-70b-versatile)** | ✅ Full graph + search | ✅ Full graph + search | ✅ Full graph + search | **Fixed 2026-03-17**: context_window + max_tokens |
| **Gemini** | ✅ Graph + Search | ✅ Graph + Search | ✅ Graph + Search | **Fixed 2026-01-08** |
| **Vertex AI** | ✅ Graph + Search | ✅ Graph + Search | ✅ Graph + Search | **Fixed 2026-01-08** |

**Conclusion**: Graph database choice doesn't affect LLM compatibility - the pattern is determined by LLM provider's integration with LlamaIndex PropertyGraph.

## OpenAI Models

### Tested Models
- ✅ `gpt-4.1-mini` — **Recommended** — Full graph extraction, fastest and most consistent of all tested providers (2026-03-20)
- ✅ `gpt-4o-mini` — Full graph extraction with entities/relationships, search and AI query work
- ✅ `gpt-4o` — Full graph extraction (untested in benchmark but expected equivalent to gpt-4o-mini)

### gpt-4.1-mini — Detailed Benchmark (2026-03-20) ⭐ Best OpenAI result

**Test conditions:** `SchemaLLMPathExtractor` + `function` mode (tool calling), `nomic-embed-text` via Ollama openai_like embedding (768-dim), `use_ontology=True`. Ontology: 3 files → 16 entity types, 22 relation types. Hardware: AMD 9950X3D, NVIDIA RTX 5090, 128 GB RAM, Windows 11.

| Document | Time | Pipeline | Graph | Node 0 entities | Node 1 entities | Neo4j Nodes | Neo4j Rels |
|----------|------|----------|-------|-----------------|-----------------|-------------|------------|
| `cmispress.txt` (2480 chars) | **17.76s** | 2.25s | 14.59s | 40 | — | 21 | 40 |
| `company-ontology-test.txt` (5618 chars, 2nd doc) | **20.36s** | 2.52s | 17.56s | 40 | 40 | +26 | +74 |
| **Both docs combined (Neo4j)** | **38s** | — | — | — | — | **47** | **114** |

*Log source: `flexible-graphrag-api-20260320-012112.log`*

**Why gpt-4.1-mini outperforms gpt-4o-mini:**
- **Zero 0-entity failures** — both chunks of company-ontology-test.txt returned exactly 40 entities each. gpt-4o-mini regularly returns 0 entities on the large 3782-char chunk (non-determinism with complex tool-call schema)
- **3-4x faster** on the 2-chunk doc — 20s vs gpt-4o-mini's 47-93s range
- Better tool-call schema following for large ontology prompts (13 entity props + 4 relation props)

### gpt-4o-mini — Detailed Benchmark (2026-03-14)

**Test conditions:** `SchemaLLMPathExtractor` + `function` mode (tool calling), `text-embedding-3-small` (1536-dim), `OLLAMA_CONTEXT_LENGTH` n/a, `ingestion_storage_mode=both` — Neo4j and GraphDB RDF store written in the **same single ingestion pass**. Ontology: 3 files → 16 entity types, 22 relation types. Hardware: AMD 9950X3D, NVIDIA RTX 5090, 128 GB RAM, Windows 11.

| Document | Time | Pipeline | Graph | Extracted | RDF built | GraphDB stored | Neo4j display | Chunks |
|----------|------|----------|-------|-----------|-----------|----------------|---------------|--------|
| `company-ontology-test.txt` (5618 chars) | **39.68s** | 5.03s | 33.76s | 74 ent (34+40), 37 rel (17+20) | 283 triples (+10 annot.) | ~67 | 26 nodes, 71 rels | 2 |
| `cmispress.txt` (2480 chars, 2nd doc) | **17.35s** | 1.15s | 15.96s | 38 ent, 19 rel | 171 triples (+1 annot.) | ~51 | +18 nodes, +36 rels | 1 |
| **Both docs combined (Neo4j)** | **57s** | — | — | — | — | — | **44 nodes, 107 rels** | 3 |
| **Both docs combined (GraphDB)** | — | — | — | — | — | **~118 stored / 481 rows** | — | |

*Log source: `flexible-graphrag-api-20260314-124435.log`*

### Configuration Notes
- Embedding: `text-embedding-3-small` (1536 dimensions) — OpenAI default
- `SchemaLLMPathExtractor strict=False` (schema + open) — uses ontology but allows additional types
- Notable: gpt-4o-mini extracted LATITUDE/LONGITUDE properties on location entities (e.g. Austin: 30.2672, -97.7431)

### Search & Q&A Test Results (2026-03-14, same session, both docs ingested)

| Mode | Query | Time | Results | Notes |
|------|-------|------|---------|-------|
| Hybrid search | "who was first with cmis" | 1.85s | 3 (deduped from 4) | Consistent across 2 runs |
| Hybrid search | "who was first with cmis" | 1.46s | 3 (deduped from 4) | 2nd run, same results |
| Q&A | "who was first with cmis" | 2.64s | 162-char answer | Answer generated successfully |
| Q&A | "who works at acme" | 2.69s | 109-char answer | Answer generated successfully |
| Hybrid search | "who works at acme" | 0.82s | 2 (deduped from 3) | 1 result filtered by score |

Search and Q&A both confirmed working with OpenAI gpt-4o-mini + Neo4j graph + Elasticsearch + Qdrant stack.

## Azure OpenAI

### Tested Models
- ✅ `gpt-4o-mini` - Full GraphRAG functionality (graph building with entities/relationships, search, AI query all work)

### gpt-4o-mini — Detailed Benchmark (2026-03-14)

**Test conditions:** `SchemaLLMPathExtractor` + `function` mode (tool calling), `AzureOpenAIEmbedding` `text-embedding-3-small` (1536-dim), `ingestion_storage_mode=both` — Neo4j and GraphDB RDF store written in the **same single ingestion pass**. Ontology: 3 files → 16 entity types, 22 relation types. Hardware: AMD 9950X3D, NVIDIA RTX 5090, 128 GB RAM, Windows 11.

| Document | Time | Pipeline | Graph | Extracted | RDF built | GraphDB stored | Neo4j display | Chunks |
|----------|------|----------|-------|-----------|-----------|----------------|---------------|--------|
| `company-ontology-test.txt` (5618 chars) | **15.04s** | 2.06s | 12.12s | 74 ent (36+38), 37 rel (18+19) | 244 triples (+5 annot.) | ~59 | 23 nodes, 64 rels | 2 |
| `cmispress.txt` (2480 chars, 2nd doc) | **128.79s** | 0.34s | 128.20s | 38 ent, 19 rel | 144 triples (+1 annot.) | ~48 | +15 nodes, +33 rels | 1 |
| **Both docs combined (Neo4j)** | **144s** | — | — | — | — | — | **38 nodes, 97 rels** | 3 |
| **Both docs combined (GraphDB)** | — | — | — | — | — | **~107 stored / 401 rows** | — | |

*Log source: `flexible-graphrag-api-20260314-134207.log`*

**Note on cmispress.txt 128s:** The graph phase took 128.20s despite only extracting 1 chunk. Log line 439 shows `Retrying request to /chat/completions in 0.422565 seconds` — Azure OpenAI rate-limited or had a transient error mid-extraction, causing ~2 minutes of retry waiting. The actual extraction (38 entities, 19 rels) and graph insert (1.1s) are fast; this is Azure throttling, not a pipeline issue.

Also noted: Azure OpenAI `embedding_kind` warning — `No embedding_kind specified, defaulting to 1536`. Set `EMBEDDING_KIND=azure` in `.env` to suppress.

### Search & Q&A Test Results (2026-03-14, same session, both docs ingested)

| Mode | Query | Time | Results | Notes |
|------|-------|------|---------|-------|
| Hybrid search | "who was first with cmis" | 0.95s | 3 (deduped from 4) | |
| Q&A | "who was first with cmis" | 1.88s | 184-char answer | |
| Q&A | "who works for acme" | 1.68s | 119-char answer | |
| Hybrid search | "who works for acme" | 0.55s | 3 (deduped from 4, 1 score-filtered) | |

Search and Q&A confirmed working with Azure OpenAI gpt-4o-mini.

### Configuration Notes
- Requires `EMBEDDING_KIND=azure` to use Azure-hosted embeddings and suppress dimension warning
- Can also use `EMBEDDING_KIND=openai` with separate OpenAI API key

## Ollama Models

### Tested Models

| Model | Status | Notes |
|-------|--------|-------|
| `gpt-oss:20b` | ✅ **RECOMMENDED** | Best speed/quality balance — use this |
| `llama3.1:8b` | ❌ **NOT RECOMMENDED** | Very slow; second doc in same session hangs |
| `llama3.2:3b` | ❌ **NOT RECOMMENDED** | Stalls at 8192 context on GPU; falls back to 4096 — low entity count |
| `sciphi/triplex` | ❌ Not usable | Extracts 0 entities/relationships, extremely slow |

### gpt-oss:20b — Detailed Benchmarks (2026-03-14)

**Common conditions:** `gpt-oss:20b`, `nomic-embed-text` embeddings, `OLLAMA_CONTEXT_LENGTH=8192`, `OLLAMA_NUM_PARALLEL=4`, `ingestion_storage_mode=both` — Neo4j and GraphDB RDF store written in the **same single ingestion pass**. Ontology: 3 files (`company_classes.ttl`, `company_properties.ttl`, `common_ontology.ttl`) → 16 entity types, 22 relation types. Hardware: AMD 9950X3D, NVIDIA RTX 5090, 128 GB RAM, Windows 11.

#### `KG_EXTRACTOR_TYPE=function` (SchemaLLMPathExtractor, function/tool calling mode)

| Document | Time | Pipeline | Graph | Neo4j Nodes | Neo4j Rels | GraphDB RDF | Chunks |
|----------|------|----------|-------|-------------|------------|-------------|--------|
| `company-ontology-test.txt` (5618 chars) | 45s | — | — | 35 | 96 | — | 2 |
| `cmispress.txt` (2nd doc, same session) | 13s | — | — | +32 | +46 | — | 1 |
| **Both docs combined** | **58s** | — | — | **67** | **142** | **675 rows** | 3 |

#### `KG_EXTRACTOR_TYPE=dynamic` (DynamicLLMPathExtractor, ontology-guided)

| Document | Time | Pipeline | Graph | Extracted entities | Extracted rels | RDF triples built | GraphDB stored | Chunks |
|----------|------|----------|-------|--------------------|----------------|-------------------|----------------|--------|
| `company-ontology-test.txt` (5618 chars) | **65.86s** | 2.53s | 62.12s | 54 (14+40) | 27 (7+20) | 180 | ~23 | 2 |
| `cmispress.txt` (2480 chars, 2nd doc) | **45.53s** | 2.03s | 43.25s | 40 | 20 | 178 (+4 annot.) | ~55 | 1 |
| **Both docs combined (Neo4j)** | **111s** | — | — | — | — | — | — | 3 |
| **Both docs combined (Neo4j display)** | — | — | — | **38 nodes** | **88 rels** | — | — | |
| **Both docs combined (GraphDB)** | — | — | — | — | — | — | **366 rows** | |

*Log source: `flexible-graphrag-api-20260314-103941.log`*

**Extractor comparison — `company-ontology-test.txt` alone:**

| Extractor | Time | Neo4j nodes | Neo4j rels | GraphDB rows |
|-----------|------|-------------|------------|--------------|
| `function` (SchemaLLMPathExtractor) | 45s | 35 | 96 | — |
| `dynamic` (DynamicLLMPathExtractor) | 66s | 19 | 50 | 180 |

`function` mode is faster and produces more Neo4j relationships. `dynamic` mode is slower but uses ontology guidance for entity typing and also produces RDF annotation triples.

### llama3.1:8b — Why Not Recommended

- ~240s per document (5x slower than `gpt-oss:20b`) on the same hardware (AMD 9950X3D, RTX 5090, 128 GB RAM)
- Second document in the same session frequently hangs (likely `OLLAMA_NUM_PARALLEL=4` contention)
- Higher raw entity count than `gpt-oss:20b` in some tests, but speed/reliability tradeoff is not worth it

### llama3.2:3b — Why Not Recommended

- `OLLAMA_CONTEXT_LENGTH=8192`: stalls indefinitely on GPU
- `OLLAMA_CONTEXT_LENGTH=4096`: works but produces low entity counts; got more entities from `company-ontology-test.txt` than `cmispress.txt` (shorter doc extracted less)
- Too small for complex SchemaLLMPathExtractor prompts with ontology schemas
- Second doc in same session hangs

### Configuration Notes

- Local deployment — no API cost, full data privacy
- Both `SchemaLLMPathExtractor` (function mode) and `DynamicLLMPathExtractor` (dynamic mode) work correctly with `gpt-oss:20b`
- Embedding: use `nomic-embed-text` (8192-token context); avoid `all-minilm` (256-token limit silently truncates)

### Recommended Ollama Config

```
OLLAMA_MODEL=gpt-oss:20b
OLLAMA_CONTEXT_LENGTH=8192
OLLAMA_KEEP_ALIVE=1440m
OLLAMA_MAX_LOADED_MODELS=2
OLLAMA_NUM_PARALLEL=4
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### Known Issues

- ✅ **Fixed 2026-01-09**: Async event loop fix restored full Ollama functionality
- `sciphi/triplex` still fails to extract entities/relationships despite being designed for KG extraction
- `llama3.1:8b` and `llama3.2:3b` technically functional but not recommended — see table above


## OpenAI-Like Models

### Overview
Use `LLM_PROVIDER=openai_like` for any OpenAI-compatible HTTP API — vLLM Docker, Ollama `/v1` endpoint, LM Studio, LocalAI, Llamafile, etc.

### Configuration
```ini
LLM_PROVIDER=openai_like
OPENAI_LIKE_API_BASE=http://localhost:8002/v1   # vLLM Docker
# or
OPENAI_LIKE_API_BASE=http://localhost:11434/v1  # Ollama /v1 endpoint
OPENAI_LIKE_MODEL=Qwen/Qwen2.5-7B-Instruct     # or gpt-oss:20b for Ollama
OPENAI_LIKE_API_KEY=local
```

### Known Issues / Fixes
- ✅ **Fixed 2026-03-19**: Added to `switch_to_dynamic_providers` — SchemaLLMPathExtractor returns 0 entities (tool_choice conflict same as Groq). Auto-switches to DynamicLLMPathExtractor.

### Benchmark — `gpt-oss:20b` via Ollama /v1, DynamicLLMPathExtractor, `use_ontology=True` (2026-03-19)
**Embedding**: `text-embedding-3-small` (OpenAI, 1536 dims)

| Doc | Neo4j Nodes | Neo4j Rels | Time |
|-----|-------------|------------|------|
| `cmispress.txt` | 22 | 41 | — |
| Both docs total | 39 | 81 | — |

*Log source: `flexible-graphrag-api-20260317-092343.log`*

### vLLM Docker Benchmark — `Qwen/Qwen2.5-7B-Instruct`, DynamicLLMPathExtractor, `use_ontology=True` (2026-03-18)
**Setup**: vLLM Docker on port 8002, `LLM_PROVIDER=openai_like`, WSL2 `memory=48GB`  
**Embedding**: `text-embedding-3-small` (OpenAI, 1536 dims)

| Doc | Neo4j Nodes | Neo4j Rels | Time |
|-----|-------------|------------|------|
| `cmispress.txt` | 31 | 48 | 20.33s |
| Both docs total | 88 | 217 | 46.44s |

*Log source: `flexible-graphrag-api-20260318-194621.log`*  
**Note**: WSL2 `.wslconfig` with `memory=48GB` required — default 8GB caused KV cache exhaustion and 0 entities on one chunk.

---

## vLLM

### Overview
Two options:
1. **Docker** (all platforms, recommended): Add `docker/includes/vllm.yaml` to docker-compose, use `LLM_PROVIDER=openai_like` pointing at port 8002
2. **Python package** (Linux/macOS only, untested): `LLM_PROVIDER=vllm` with `uv pip install vllm`

### Configuration (Docker — recommended)
```ini
LLM_PROVIDER=openai_like
OPENAI_LIKE_API_BASE=http://localhost:8002/v1
OPENAI_LIKE_MODEL=Qwen/Qwen2.5-7B-Instruct
```
See `docs/LLM/LLM-EMBEDDING-CONFIG.md` Section 18 for full Docker setup.

### Notes
- vLLM Docker port: 8002 (host) → 8000 (container)
- Default model: `Qwen/Qwen2.5-7B-Instruct` (configurable via `VLLM_MODEL` env var)
- Windows: requires WSL2 with sufficient memory allocation (`memory=48GB` in `.wslconfig` for 128GB RAM systems)
- See `docs/DOCKER-RESOURCE-CONFIGURATION.md` for WSL2/macOS/Linux sizing guide

---

## LiteLLM

### Overview
`LLM_PROVIDER=litellm` — routes through LiteLLM proxy (100+ providers). On Windows, run the proxy in WSL2 to bypass security software (Norton etc.) that blocks `litellm.exe`.

### Configuration
```ini
LLM_PROVIDER=litellm
LITELLM_MODEL=gpt-4o-mini            # or ollama/gpt-oss:20b
LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=local
LITELLM_TIMEOUT=300.0                # critical — prevents silent hang on 2-chunk docs
```

Proxy startup (WSL2 Ubuntu):
```bash
OPENAI_API_KEY="sk-..." litellm --config /mnt/c/newdev3/flexible-graphrag/flexible-graphrag/litellm_config.yaml --port 4000
```

### Known Issues / Fixes
- ✅ **Fixed 2026-03-19**: `LITELLM_API_BASE` must include `/v1` suffix
- ✅ **Fixed 2026-03-19**: `LITELLM_EMBEDDING_API_BASE` must include `/v1` suffix
- ✅ **Fixed 2026-03-19**: `litellm.drop_params=True` set in `factories.py` — strips `parallel_tool_calls` for Ollama-backed models
- ✅ **Fixed 2026-03-19**: `LITELLM_TIMEOUT=300.0` — default timeout caused silent hang on 2-chunk docs (proxy drops response without error)
- ✅ **Fixed 2026-03-19**: Ollama-backed models (`ollama/*` prefix) auto-switch to DynamicLLMPathExtractor

### Extractor Routing
- Cloud models (gpt-4o-mini, etc.): **SchemaLLMPathExtractor** — LiteLLM is FunctionCallingLLM subclass
- Ollama-backed models (`LITELLM_MODEL=ollama/gpt-oss:20b`): **DynamicLLMPathExtractor** (auto-switched via `llm.model.startswith("ollama/")` check)

### Benchmark — gpt-4o-mini via proxy, SchemaLLMPathExtractor, `use_ontology=True` (2026-03-19)
**Embedding**: `text-embedding-3-small` via LiteLLM proxy (1536 dims)

| Doc | Neo4j Nodes | Neo4j Rels | Time |
|-----|-------------|------------|------|
| `cmispress.txt` | 18–21 | 33–39 | 16–38s |
| Both docs total | 38–48 | 87–115 | 47–93s |

*Note*: Range reflects two runs with different embedding configs (Run 1: OpenAI direct embedding; Run 2: LiteLLM proxy embedding — identical results, proxy adds no overhead)

### Benchmark — gpt-oss:20b via Ollama, DynamicLLMPathExtractor, `use_ontology=True` (2026-03-19)
**Embedding**: `text-embedding-3-small` (OpenAI direct, 1536 dims)

| Doc | Neo4j Nodes | Neo4j Rels | Time |
|-----|-------------|------------|------|
| `cmispress.txt` | 30 | 53 | 30.53s |
| Both docs total | 47 | 93 | +78.59s |

*Note*: Slower than direct `LLM_PROVIDER=ollama` (58s total vs 109s) due to LiteLLM in-process overhead. Use `LLM_PROVIDER=ollama` directly for Ollama models.

### LiteLLM Sweet Spot
- **Best use case**: Cloud providers (OpenAI, Anthropic, etc.) routed through WSL2 proxy to bypass Windows security software
- **Not recommended**: Ollama LLM + Ollama embedding both via LiteLLM — contention for Ollama's generation slot causes hangs

---

## OpenRouter

### Overview
`LLM_PROVIDER=openrouter` — unified cloud API routing to OpenAI, Anthropic, Meta, Mistral, and 200+ models.

### Configuration
```ini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_CONTEXT_WINDOW=128000     # required — default too small → truncated output → 6 entities
OPENROUTER_MAX_TOKENS=16384          # required
```

### Known Issues / Fixes
- ✅ **Fixed 2026-03-19**: Added to `switch_to_dynamic_providers` — OpenRouter extends OpenAILike with `is_function_calling_model=False`; SchemaLLMPathExtractor returns 0 entities instantly (genuine tool-calling incompatibility confirmed after credits added)
- ✅ **Fixed 2026-03-19**: `context_window=128000` + `max_tokens=16384` added to `config.py` + `factories.py` — default was too small causing output truncation (6 entities in ~6s)
- Account must have credits: https://openrouter.ai/settings/credits

### Benchmark — openai/gpt-4o-mini, DynamicLLMPathExtractor, `use_ontology=True` (2026-03-19)
**Embedding**: `text-embedding-3-small` (OpenAI direct, 1536 dims)

| Doc | Neo4j Nodes | Neo4j Rels | Time |
|-----|-------------|------------|------|
| `cmispress.txt` | 19 | 35 | 21.08s |
| Both docs total | 46 | 106 | +39.61s |

*Log source: `flexible-graphrag-api-20260319-031556.log`*  
*Note*: Fast cloud routing — comparable to LiteLLM gpt-4o-mini (48/115) with similar speed profile.

---



Successfully tested combinations:
- ✅ Google Gemini LLM + Google embeddings - **Recommended for Gemini users**
- ✅ Google Gemini LLM + OpenAI embeddings (2 separate API keys)
- ✅ Azure OpenAI LLM + Azure embeddings (same endpoint, uses `EMBEDDING_MODEL` as deployment name)
- ✅ Azure OpenAI LLM + OpenAI embeddings (fetches `OPENAI_API_KEY` from environment)
- ✅ OpenAI LLM + Azure embeddings (requires `EMBEDDING_MODEL` or `AZURE_EMBEDDING_DEPLOYMENT` for deployment name)
- ✅ OpenAI LLM + OpenAI embeddings (same API key)
- ✅ OpenAI LLM + Google embeddings (mixed provider, tested and working)
- ✅ Ollama LLM + Ollama embeddings (local deployment)
- ✅ LiteLLM LLM (gpt-4o-mini via proxy) + LiteLLM embeddings (text-embedding-3-small via proxy) — **Added 2026-03-19**; both route through WSL2 LiteLLM proxy. Requires `/v1` suffix on `LITELLM_EMBEDDING_API_BASE`.
- ✅ OpenAI LLM (direct) + LiteLLM embeddings (text-embedding-3-small via proxy) — **Added 2026-03-19**; proxy adds no meaningful overhead for embeddings vs direct OpenAI.
- ✅ OpenAI-Like LLM (vLLM Docker / Ollama /v1) + OpenAI embeddings — standard mix, works fine
- ✅ OpenAI LLM (gpt-4o-mini, gpt-4.1-mini) + OpenAI-Like embeddings (`nomic-embed-text` via Ollama /v1) — **Confirmed 2026-03-20**; best cost/privacy combo: cloud LLM + free local embeddings. Set `EMBEDDING_DIMENSION=768`.
- ✅ Any LLM provider + OpenAI-Like embeddings — `EMBEDDING_KIND=openai_like` is provider-agnostic; works alongside any LLM
- ⚠️ LiteLLM LLM (ollama/gpt-oss:20b direct) + LiteLLM embeddings (ollama/nomic-embed-text direct) — **NOT RECOMMENDED**: both compete for Ollama's single generation slot; LLM extraction hangs. Use `LLM_PROVIDER=ollama` directly instead.

### OpenAI-Like Embedding Notes (2026-03-19/20)
- `EMBEDDING_KIND=openai_like` uses `OpenAILikeEmbedding` class — any server with a `/v1/embeddings` endpoint
- Tested: `nomic-embed-text` via Ollama at `http://localhost:11434/v1` (768 dims) — confirmed working
- `EMBEDDING_DIMENSION=768` **must be set explicitly** (no auto-detection for openai_like endpoints)
- Works with **any LLM provider** — tested with OpenAI gpt-4o-mini and gpt-4.1-mini
- Config:
  ```
  EMBEDDING_KIND=openai_like
  EMBEDDING_MODEL=nomic-embed-text
  OPENAI_LIKE_EMBEDDING_API_BASE=http://localhost:11434/v1
  OPENAI_LIKE_API_KEY=local
  EMBEDDING_DIMENSION=768
  ```
- Log shows `OpenAILikeEmbedding` in IngestionPipeline transformations confirming correct class

### LiteLLM Embedding Notes (2026-03-19)
- `EMBEDDING_KIND=litellm` routes embeddings through the LiteLLM proxy
- `LITELLM_EMBEDDING_API_BASE` must include `/v1` suffix (e.g. `http://localhost:4000/v1`)
- For Ollama embeddings direct (no proxy): `LITELLM_EMBEDDING_API_BASE=http://localhost:11434` — but avoid combining with Ollama LLM via LiteLLM (contention)
- `text-embedding-3-small` and `ollama/nomic-embed-text` must be listed in `litellm_config.yaml` model_list when using proxy routing
- Proxy adds zero measurable overhead vs direct `EMBEDDING_KIND=openai` for the same model

## Recommendations

### For Full GraphRAG (entities + relationships):
- ✅ **OpenAI** (`gpt-4.1-mini` recommended, gpt-4o-mini, gpt-4o) - Best overall performance, works with all graph databases, SchemaLLMPathExtractor (default). `gpt-4.1-mini` is fastest and most consistent for multi-chunk docs (zero 0-entity failures, 3-4x faster than gpt-4o-mini).
- ✅ **Azure OpenAI** (gpt-4o-mini) - Enterprise deployment option, same capabilities as OpenAI, SchemaLLMPathExtractor (default)
- ✅ **Google Gemini** (gemini-3-flash-preview, gemini-3.1-pro-preview) - Full graph extraction, SchemaLLMPathExtractor (default)
- ✅ **Google Vertex AI** (gemini-2.5-flash) - Same as Gemini, SchemaLLMPathExtractor (default)
- ✅ **Anthropic Claude** (sonnet-4-5, haiku-4-5) - Full graph extraction, SchemaLLMPathExtractor (default)
- ✅ **Ollama** (`gpt-oss:20b` only) - Local deployment, `SchemaLLMPathExtractor` + function mode; `llama3.1:8b`/`llama3.2:3b` not recommended
- ✅ **Groq** (gpt-oss-20b, llama-3.3-70b-versatile) - Fast LPU inference, DynamicLLMPathExtractor (auto-switched; SchemaLLMPathExtractor broken due to tool_choice conflict). **Fixed 2026-03-17.**
- ✅ **Fireworks AI** (gpt-oss-120b, deepseek-v3, etc.) - Full graph extraction, DynamicLLMPathExtractor (streaming mode required). **Fixed 2026-03-17.**
- ✅ **Amazon Bedrock** (claude-sonnet, gpt-oss, deepseek-r1, llama3) - AWS integration, DynamicLLMPathExtractor; `use_ontology=True` + `DISABLE_PROPERTIES=true` recommended
- ✅ **OpenAI-Like** (vLLM Docker port 8002, Ollama /v1, any OpenAI-compatible API) - DynamicLLMPathExtractor (auto-switched). **Added 2026-03-19.**
- ✅ **LiteLLM** (proxy, 100+ providers) - Cloud models use SchemaLLMPathExtractor; Ollama-backed models auto-switch to Dynamic. Proxy runs in WSL2 on Windows. **Added 2026-03-19.**
- ✅ **OpenRouter** (cloud unified API, 200+ models) - DynamicLLMPathExtractor (auto-switched). Requires `OPENROUTER_CONTEXT_WINDOW=128000` + `OPENROUTER_MAX_TOKENS=16384`. **Added 2026-03-19.**

**Note**: The extractor type can be configured via `KG_EXTRACTOR_TYPE` environment variable (options: `schema`, `simple`, `dynamic`). Due to LlamaIndex integration issues, the configuration is auto-overridden for certain providers: Bedrock, Groq, Fireworks, OpenAI-Like, and OpenRouter all auto-switch `schema`→`dynamic`. LiteLLM auto-switches only when `LITELLM_MODEL` starts with `ollama/`.

### For Graph Building + Vector/Search:
All providers listed above work correctly with full database stacks (vector + search + graph)

### For Graph-Only Mode (No Vector/Search):
- ✅ **Neo4j + OpenAI** - Fully functional graph-based retrieval
- ✅ **FalkorDB + OpenAI** - Fully functional graph-based retrieval
- ❌ **ArcadeDB + OpenAI** - Graph creation works, but retrieval requires external vector/search databases

### Extractor Information:
- **SchemaLLMPathExtractor** (default): Uses predefined schema with strict entity/relationship types. Default for OpenAI, Azure, Gemini, Vertex, Claude, Ollama, and LiteLLM (cloud models).
- **DynamicLLMPathExtractor**: Starts with an ontology but allows LLM to expand it. Auto-used for Groq, Fireworks, Bedrock, OpenAI-Like, OpenRouter, and LiteLLM (ollama/* models). Also configurable via `KG_EXTRACTOR_TYPE=dynamic`.
- **SimpleLLMPathExtractor**: Allows LLM to discover entities/relationships without schema. Available via `KG_EXTRACTOR_TYPE=simple`; not auto-assigned to any provider currently.

### LLM Extraction Mode
`LLM_EXTRACTION_MODE` controls how the LLM is called during extraction (`function`, `json_schema`, `auto`). Default is `function` (tool calling) — recommended for all providers. See `docs/LLM/LLM-EMBEDDING-CONFIG.md` Advanced Configurations section for full details.

- `function` (default): tool/function calling — most reliable, avoids OpenAI structured output bugs
- `json_schema`: JSON schema / structured output mode
- `auto`: maps to DEFAULT internally (same as json_schema)

Note: providers that auto-switch to `DynamicLLMPathExtractor` (Groq, Fireworks, Bedrock, OpenAI-Like, OpenRouter) are unaffected — Dynamic uses `apredict()` (plain text), not tool calls.

### Local Models (Ollama):
- ✅ **Only recommended model: `gpt-oss:20b`** (2026-03-14 benchmark, function mode, both stores)
  - 45s for `company-ontology-test.txt` → 35 Neo4j nodes, 96 rels
  - 13s for `cmispress.txt` (2nd doc) → cumulative 67 nodes, 142 rels, 675 GraphDB RDF rows
  - Use `SchemaLLMPathExtractor` + `nomic-embed-text` + `OLLAMA_CONTEXT_LENGTH=8192`
  - `ingestion_storage_mode=both` confirmed: Neo4j + RDF store in one pass
- ❌ **Not recommended**
  - `llama3.1:8b` — ~240s/doc (5x slower), second doc hangs — not worth it
  - `llama3.2:3b` — stalls at 8192 context on GPU; falls back to 4096, low entity count — not usable for schema extraction
  - `sciphi/triplex` — extracts 0 entities/relationships, extremely slow

