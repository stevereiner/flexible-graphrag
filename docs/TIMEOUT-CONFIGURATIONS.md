# Timeout Configurations

This document explains the different types of timeouts in Flexible GraphRAG and how to configure them properly.

## ⏱️ **Multiple Different Types of Timeouts**

Flexible GraphRAG has several different timeout configurations for different purposes. It's important to understand which timeout controls what part of the system.

### **1. LLM Request Timeouts**

Controls how long to wait for LLM API responses (OpenAI, Ollama, etc.)

**Used during**: Knowledge graph extraction, query answering, embeddings

```bash
# OpenAI timeout (default: 2 minutes)
OPENAI_TIMEOUT=120.0

# Ollama timeout (default: 5 minutes - higher for local processing)  
OLLAMA_TIMEOUT=300.0

# Azure OpenAI timeout
AZURE_OPENAI_TIMEOUT=120.0

# Anthropic timeout
ANTHROPIC_TIMEOUT=120.0

# Gemini timeout
GEMINI_TIMEOUT=120.0
```

### **2. Document Processing Timeouts**

Controls Docling document conversion timeouts

**Used during**: PDF/DOCX/etc. conversion to text before LLM processing

```bash
# DOCLING_TIMEOUT: Maximum time for processing a single document with Docling
# - Small files (< 1MB): Usually 5-30 seconds
# - Large PDFs (10MB+): May take 2-5 minutes 
# - Complex documents: Up to 5-10 minutes
# - Set higher for large documents or slower hardware
DOCLING_TIMEOUT=600  # Default: 10 minutes (600 seconds)

# DOCLING_CANCEL_CHECK_INTERVAL: How often to check for user cancellation during Docling
# - Lower values (0.1-0.5s): More responsive cancellation, slightly higher CPU
# - Higher values (1.0-2.0s): Less responsive but lower overhead  
# - This enables cancelling during single file processing
DOCLING_CANCEL_CHECK_INTERVAL=0.5  # Default: 0.5 seconds
```

**Note**: For GPU/device configuration and output saving options, see [DOC-PROCESSING/DOCLING-GPU-CONFIGURATION.md](DOC-PROCESSING/DOCLING-GPU-CONFIGURATION.md)

### **3. Knowledge Graph Extraction Timeouts**

Controls the lengthy process of extracting entities and relationships

**Used during**: Building knowledge graph from processed text chunks

```bash
# KG_EXTRACTION_TIMEOUT: Maximum time for knowledge graph extraction per document
# - Small documents (< 50 pages): Usually 5-15 minutes
# - Large documents (100+ pages): May take 30-60+ minutes
# - Complex technical documents: Up to 2+ hours
# - Set higher for complex documents or slower hardware/LLMs
KG_EXTRACTION_TIMEOUT=3600  # Default: 1 hour (3600 seconds)

# KG_PROGRESS_REPORTING: Enable detailed progress during KG extraction
# - Shows "Processing chunk X/Y" and entity/relationship counts
# - Helps users understand why large documents take time
KG_PROGRESS_REPORTING=true  # Default: enabled

# KG_BATCH_SIZE: Number of chunks to process together during KG extraction
# - Smaller batches (5-10): More frequent progress updates, better cancellation
# - Larger batches (20-50): More efficient but less granular progress
KG_BATCH_SIZE=10  # Default: 10 chunks per batch

# KG_CANCEL_CHECK_INTERVAL: How often to check for cancellation during KG extraction
# - Lower values (1.0-2.0s): More responsive but slightly higher overhead
# - Higher values (5.0-10s): Less responsive but more efficient
KG_CANCEL_CHECK_INTERVAL=2.0  # Default: 2 seconds
```

## 📝 **Important Notes**

### **Different Timeouts for Different Purposes**

- **LLM timeouts**: For single API calls to language models (1-5 minutes)
- **Docling timeouts**: For document conversion PDF → text (5-10 minutes) 
- **KG extraction timeouts**: For full knowledge graph building (30-60+ minutes)
- **UI timeouts**: Handled separately in frontend clients

### **Sequential Processing**

Files are processed sequentially (one after another) currently in the backend and this is reflected in the UI feedback. Each file completes fully before the next file begins processing.

### **Cancellation Support**

The system supports cancellation at multiple levels:
- **Document level**: Cancel during Docling conversion
- **Batch level**: Cancel during knowledge graph extraction 
- **User interface**: Cancel buttons in all UI clients

### **Recommendations**

- **Development**: Use shorter timeouts for faster feedback
- **Production**: Use longer timeouts for complex documents
- **Large documents**: Increase all timeouts proportionally
- **Slow hardware**: Increase timeouts and reduce batch sizes
- **Remote LLMs**: Consider network latency in LLM timeouts
