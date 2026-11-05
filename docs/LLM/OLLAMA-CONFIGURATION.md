# Ollama Environment Configuration

## Overview

When using Ollama as your LLM provider (instead of OpenAI), you need to configure system-wide environment variables **before starting the Ollama service**. These settings optimize performance, enable parallel processing, and help manage resource constraints.

## Environment Variables

Configure these environment variables on your system (not in the Flexible GraphRAG `.env` file):

### Context Length

```bash
OLLAMA_CONTEXT_LENGTH=8192
```

**Configuration Options**:
- **4096**: Minimum for limited resources
- **8192**: Recommended default
- **16384**: For improved speed and extraction quality

**Important Notes**:
- This is only Ollama's *default*, used when a request doesn't say. The Ollama desktop app's
  **Context length** slider overrides `OLLAMA_CONTEXT_LENGTH` (Ollama's `server.log` startup line
  shows the value in effect).
- **Flexible GraphRAG sends its own context with every request:** `OLLAMA_CONTEXT_WINDOW` in its
  `.env` (default `8192`). That value is the one that counts for Flexible GraphRAG, whatever the
  slider says. Before this setting, LlamaIndex sent the model's maximum (32k for `qwen2.5:14b`,
  128k for `gpt-oss:20b`), which pushed models partly onto the CPU.
- The full 128k possible context window for llama3.2:3b requires 16.4GB of RAM for the key-value (KV) cache alone, plus ~3GB for model weights
- The 128K token context window allows processing ~96,240 words of text in a single interaction
- By default, inference engines (llama.cpp, transformers, Ollama) store both model weights and KV cache in GPU VRAM when available (fastest)
- If GPU VRAM is insufficient, the KV cache falls back to system RAM with potential speed penalty

### Debug Logging

```bash
OLLAMA_DEBUG=1
```

**Values**:
- `1`: Enable debug logging
- `0`: Disable debug logging

**Log Locations**:
- **Windows**: `C:\Users\<username>\AppData\Local\Ollama\server.log`
- **Linux/macOS**: Check Ollama documentation for your platform

**Use Cases**:
- Checking GPU memory availability
- Identifying CPU fallback behavior
- Troubleshooting performance issues

### Model Persistence

```bash
OLLAMA_KEEP_ALIVE=30m
```

Keeps models loaded in memory for faster subsequent requests. Adjust time based on your usage patterns and available memory.

### Maximum Loaded Models

```bash
OLLAMA_MAX_LOADED_MODELS=4
```

**Values**:
- `0`: No limit (loads as many as needed)
- `4`: Recommended for most systems
- Adjust based on your available memory

### Model Storage Directory

```bash
# Windows example
OLLAMA_MODELS=C:\Users\<username>\.ollama\models

# Linux/macOS example
OLLAMA_MODELS=/home/<username>/.ollama/models
```

Usually set automatically by Ollama, but can be customized for specific storage locations.

### Parallel Request Handling

```bash
OLLAMA_NUM_PARALLEL=4
```

**⚠️ CRITICAL SETTING**:
- Required for Flexible GraphRAG parallel file processing
- Prevents processing errors during parallel document ingestion
- Allows Ollama to handle multiple concurrent requests
- Must match or exceed the number of worker threads used by the system

## Installation Steps

### Windows

1. Open **System Properties** → **Advanced** → **Environment Variables**
2. Under **System variables** (not User variables), click **New**
3. Add each variable name and value
4. Click **OK** to save
5. Restart the Ollama service:
   ```cmd
   net stop Ollama
   net start Ollama
   ```

### Linux/macOS

1. Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):
   ```bash
   export OLLAMA_CONTEXT_LENGTH=8192
   export OLLAMA_DEBUG=1
   export OLLAMA_KEEP_ALIVE=30m
   export OLLAMA_MAX_LOADED_MODELS=4
   export OLLAMA_NUM_PARALLEL=4
   ```

2. Reload your shell configuration:
   ```bash
   source ~/.bashrc  # or ~/.zshrc
   ```

3. Restart Ollama service:
   ```bash
   systemctl restart ollama  # On Linux with systemd
   # or
   brew services restart ollama  # On macOS with Homebrew
   ```

## Verification

After configuration, verify the settings are active:

1. Check Ollama is running:
   ```bash
   ollama list
   ```

2. Test with a simple request:
   ```bash
   ollama run llama3.2:3b "Hello"
   ```

3. Check debug logs (if `OLLAMA_DEBUG=1`):
   - **Windows**: `C:\Users\<username>\AppData\Local\Ollama\server.log`
   - Look for configuration values and GPU/CPU usage information

4. After the first AI query or ingest with a graph, check where the LLM runs:
   ```
   ollama ps
   NAME                        ID              SIZE      PROCESSOR    CONTEXT    UNTIL
   gpt-oss:20b                 17052f91a42e    12 GB     100% GPU     8192       29 minutes from now
   mxbai-embed-large:latest    468836162de7    624 MB    100% GPU     512        29 minutes from now
   ```
   - The LLM must be listed: Ollama loads it only on the first LLM call. Before that (for example
     after an ingest without a graph) only the embedding model shows, which says nothing about the
     LLM.
   - **PROCESSOR** should say `100% GPU` for the LLM. A split such as `35%/65% CPU/GPU` means part of the
     model runs on the CPU, and each LLM call can take minutes.
   - **CONTEXT** should match `OLLAMA_CONTEXT_WINDOW` (default 8192).
   - **SIZE** grows with the context × `OLLAMA_NUM_PARALLEL`.

## Troubleshooting

### Issue: Processing Errors with Multiple Files

**Symptom**: Errors when processing multiple documents simultaneously

**Solution**: Ensure `OLLAMA_NUM_PARALLEL=4` is set system-wide and Ollama service has been restarted

### Issue: Slow Performance

**Symptoms**:
- Document processing takes much longer than expected
- High CPU usage but low GPU usage

**Possible Causes**:
1. **GPU VRAM exhausted**: Context window too large for available VRAM
2. **CPU fallback**: Model running on CPU instead of GPU

**Check**: run `ollama ps` after the first AI query or graph ingest, once the LLM is listed (not
just the embedding model). The **PROCESSOR** column should say `100% GPU` for it.
A split such as `35%/65% CPU/GPU` means part of the model runs on the CPU, which can make one LLM
call take minutes. **CONTEXT** shows the context in use: it should match `OLLAMA_CONTEXT_WINDOW`.

**Solutions**:
1. Lower `OLLAMA_CONTEXT_WINDOW` in the Flexible GraphRAG `.env` (memory for it is reserved
   `OLLAMA_NUM_PARALLEL` times), or lower `OLLAMA_NUM_PARALLEL`
2. Check debug logs for GPU memory issues
3. Close other GPU-intensive applications, and unload models Ollama still holds from earlier
   requests (`ollama ps`, then `ollama stop <model>`): with `OLLAMA_KEEP_ALIVE=30m` and
   `OLLAMA_MAX_LOADED_MODELS=4` they stay in GPU memory, and Ollama's `server.log` shows less
   `available` VRAM when the next model loads. **Docker Model Runner** (Docker Desktop's own local
   model server on port 12434) holds GPU memory the same way. The Content Lake app deployment
   requires it, for `ai/mxbai-embed-large` and an Olmo 3 7B or Qwen 2.5 chat model, so when both
   stacks run on one machine, add up `ollama ps` and `docker model ps`. Free Model Runner's models
   with `docker model unload`
4. Consider a smaller model that fits in your GPU memory

### Issue: "Out of Memory" Errors

**Solution**:
1. Reduce `OLLAMA_CONTEXT_WINDOW` (Flexible GraphRAG `.env`)
2. Reduce `OLLAMA_MAX_LOADED_MODELS`
3. Ensure adequate system RAM (16GB+ recommended)

## Performance Considerations

### Model Selection

Two recommended models; either is fine:

- **gpt-oss:20b** (OpenAI): 12 GB at 8192 context × 4 parallel. The cleanest graph on text outside
  the ontology. A reasoning model, so its time varies between runs
- **qwen2.5:14b** (Alibaba, Qwen team): 15 GB. The most entities and relationships on documents the
  ontology fits; sometimes extracts file metadata (path, file type) as entities

Not recommended for KG extraction:

- **llama3.1:8b** (Meta): fast, but poor on text outside the ontology (metadata as entities, no types)
- **llama3.2:3b** (Meta): no entity typing, and stalls on some documents

See [LLM Testing Results](LLM-TESTING-RESULTS.md#ollama-models) for the numbers.

### Resource Requirements

| Component | Minimum | Recommended | Optimal |
|-----------|---------|-------------|---------|
| System RAM | 8GB | 16GB | 32GB+ |
| GPU VRAM | 4GB | 8GB | 12GB+ |
| Context Length | 4096 | 8192 | 16384 |

### Parallel Processing

- `OLLAMA_NUM_PARALLEL=4` enables 4 concurrent requests
- Higher values require more memory but improve throughput
- Match this value to your available resources
- Keep Flexible GraphRAG's `KG_EXTRACTION_WORKERS` (concurrent KG extraction LLM calls, set in its `.env`) at its default `4`, in line with `OLLAMA_NUM_PARALLEL`. The 8-16 that speeds up KG extraction with cloud LLMs only queues up requests in Ollama. See [Extraction Concurrency](../DATABASES/GRAPH-DATABASES/KNOWLEDGE-GRAPH-EXTRACTORS.md#extraction-concurrency-kg_extraction_workers)

## Additional Resources

- [Ollama Documentation](https://github.com/ollama/ollama/blob/main/docs/faq.md)
- [LlamaIndex Ollama Integration](https://docs.llamaindex.ai/en/stable/examples/llm/ollama.html)
- [Flexible GraphRAG Performance Documentation](../ADVANCED/PERFORMANCE.md)

## Summary

**Key Points**:
1. ✓ Set environment variables **system-wide** (not in Flexible GraphRAG `.env`)
2. ✓ `OLLAMA_NUM_PARALLEL=4` is **critical** for parallel processing
3. ✓ Always **restart Ollama service** after changing environment variables
4. ✓ Use `OLLAMA_DEBUG=1` to troubleshoot performance issues
5. ✓ Adjust `OLLAMA_CONTEXT_WINDOW` (Flexible GraphRAG `.env`) based on available GPU memory;
   `ollama ps` should show `100% GPU`

These settings ensure optimal Ollama performance with Flexible GraphRAG's parallel document processing capabilities.

