# Ollama Environment Configuration

**Last Updated**: November 26, 2025

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

**Solutions**:
1. Reduce `OLLAMA_CONTEXT_LENGTH` to 4096
2. Check debug logs for GPU memory issues
3. Close other GPU-intensive applications
4. Consider using a smaller model (e.g., llama3.2:3b instead of gpt-oss:20b)

### Issue: "Out of Memory" Errors

**Solution**:
1. Reduce `OLLAMA_CONTEXT_LENGTH`
2. Reduce `OLLAMA_MAX_LOADED_MODELS`
3. Ensure adequate system RAM (16GB+ recommended)

## Performance Considerations

### Model Selection

- **llama3.2:3b**: Lightweight, fast, good for testing
- **llama3.1:8b**: Balanced performance and quality
- **gpt-oss:20b**: Higher quality, requires more resources

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

## Additional Resources

- [Ollama Documentation](https://github.com/ollama/ollama/blob/main/docs/faq.md)
- [LlamaIndex Ollama Integration](https://docs.llamaindex.ai/en/stable/examples/llm/ollama.html)
- [Flexible GraphRAG Performance Documentation](PERFORMANCE.md)

## Summary

**Key Points**:
1. ✓ Set environment variables **system-wide** (not in Flexible GraphRAG `.env`)
2. ✓ `OLLAMA_NUM_PARALLEL=4` is **critical** for parallel processing
3. ✓ Always **restart Ollama service** after changing environment variables
4. ✓ Use `OLLAMA_DEBUG=1` to troubleshoot performance issues
5. ✓ Adjust `OLLAMA_CONTEXT_LENGTH` based on available resources

These settings ensure optimal Ollama performance with Flexible GraphRAG's parallel document processing capabilities.

