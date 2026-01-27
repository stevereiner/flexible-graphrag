# Docling GPU Configuration Guide

This guide explains how to configure Docling for GPU acceleration and save parsing results for inspection.

## Overview

Docling is the default open-source document parser in Flexible GraphRAG. It supports GPU acceleration for significantly faster processing of complex documents, especially those with tables and images.

**Recommended Package Manager**: This guide uses [`uv`](https://github.com/astral-sh/uv), a fast Python package manager. All `pip` commands can be replaced with `uv pip` for better performance.

## GPU vs CPU Performance

**GPU Benefits:**
- **5-10x faster** PDF processing with complex layouts
- Better performance on documents with many tables (like technical manuals)
- Faster OCR processing for scanned documents
- Recommended for production use with large document volumes

**When to use CPU:**
- GPU not available
- Small, simple documents (< 5 pages)
- Debugging GPU-related issues
- Development/testing with limited resources

## Configuration Options

### Environment File Setup

Before configuring options, create your `.env` file from the template:

```bash
# In the flexible-graphrag directory
cp env-sample.txt .env  # On Windows use: copy env-sample.txt .env
```

The `env-sample.txt` file contains all available configuration options with descriptions. Copy it to `.env` and modify as needed.

### 1. Device Selection (`DOCLING_DEVICE`)

Control which device Docling uses for processing using Docling's official `AcceleratorDevice` API:

```bash
# Auto-detect (default) - uses GPU if available, falls back to CPU
DOCLING_DEVICE=auto

# Force CPU-only (slower but always works)
DOCLING_DEVICE=cpu

# Force CUDA/GPU (requires CUDA-capable GPU and PyTorch with CUDA)
DOCLING_DEVICE=cuda

# Force Apple Metal (Mac with Apple Silicon only)
DOCLING_DEVICE=mps
```

**Recommendation**: Use `auto` for most cases. Docling will automatically detect and use GPU if available.

### 2. Save Parsing Results (`SAVE_PARSING_OUTPUT`)

Enable saving of intermediate parsing results to disk for inspection (works for both parsers):

```bash
# Enable saving parsing results
SAVE_PARSING_OUTPUT=true

# Disable saving (default)
SAVE_PARSING_OUTPUT=false
```

When enabled, the system will save parsing outputs to `./parsing_output/`:

**For Docling:**
- `{filename}_docling_markdown.md` - Markdown format with table structures preserved
- `{filename}_docling_plaintext.txt` - Plain text extraction for better entity recognition
- `{filename}_docling_metadata.json` - Processing metadata (file info, lengths, table detection, format used)

**For LlamaParse:**
- `{filename}_llamaparse_output.md` - Parsed markdown output (multiple chunks automatically combined)
- `{filename}_llamaparse_output.txt` - Plaintext version with markdown formatting stripped
- `{filename}_llamaparse_metadata.json` - Processing metadata (file info, chunk count, character count)

**Example output location:**
```
./parsing_output/
  ├── document1_docling_markdown.md
  ├── document1_docling_plaintext.txt
  ├── document1_docling_metadata.json
  ├── document2_llamaparse_output.md
  ├── document2_llamaparse_output.txt
  ├── document2_llamaparse_metadata.json
  └── technical_spec_docling_markdown.md
```

## GPU Setup Requirements

### Step 1: Check Your CUDA Version (NVIDIA GPUs Only)

If you have an NVIDIA GPU, first check your CUDA driver version:

**Windows/Linux:**
```bash
nvidia-smi
```

Look for the `CUDA Version` in the output header. Example:
```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 591.74       Driver Version: 591.74       CUDA Version: 13.1   |
+-----------------------------------------------------------------------------+
```

This shows your **maximum supported CUDA version** (13.1 in this example). You can install PyTorch for CUDA 13.0 or lower.

**What nvidia-smi shows:**
- **Driver Version**: Your NVIDIA driver version (e.g., 591.74)
- **CUDA Version**: Maximum CUDA toolkit version your driver supports
- **GPU Name**: Your GPU model (e.g., NVIDIA GeForce RTX 5090)
- **GPU Util**: Current GPU utilization percentage
- **Memory-Usage**: GPU memory in use / total available

### Step 2: Install PyTorch with GPU Support

Visit [PyTorch.org Get Started](https://pytorch.org/get-started/locally/) and select your configuration:

**Configuration Steps:**
1. **PyTorch Build**: Select "Stable (2.7.0)" or latest version
2. **Your OS**: Select Windows, Linux, or Mac
   - Selecting your OS will display platform-specific instructions (e.g., "Installing on Windows")
3. **Package**: Select "Pip"
4. **Language**: Select "Python"
5. **Compute Platform**: Select your CUDA version (e.g., CUDA 11.8, 12.6, 12.8, 13.0) or CPU
   - **Note**: Mac users will see "CUDA is not available on macOS, please use default package"

The website will generate an install command. **Prefix it with `uv`** for faster installation.

#### CUDA (NVIDIA GPUs)

On [PyTorch.org](https://pytorch.org/get-started/locally/), select your OS (Windows or Linux) to see platform-specific instructions. The page will display **"Installing on Windows"** or **"Installing on Linux"**.

**Current PyTorch offerings** (as of January 2026): CUDA 12.6, 12.8, and 13.0

**For CUDA 12.6:**
```bash
# Uninstall existing versions first (recommended)
uv pip uninstall torch torchvision

# PyTorch.org command
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# With uv (faster)
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

**For CUDA 12.8:**
```bash
uv pip uninstall torch torchvision
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

**For CUDA 13.0 (Latest - Windows/Linux):**
```bash
# First uninstall existing versions
uv pip uninstall torch torchvision

# Install CUDA 13.0 build
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130

# Windows only: Install Triton for Windows (enables full PyTorch compiler support)
uv pip install triton-windows
```

> **Note**: The `triton-windows` package is only needed on Windows for full PyTorch compiler support.

**For older CUDA 11.8 (if needed):**
```bash
uv pip uninstall torch torchvision
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

#### Triton for Windows (Optional but Recommended)

PyTorch's Torch Inductor compiler requires Triton. On Windows, install the Windows-specific package:

```bash
uv pip install triton-windows
```

**If you get a Triton error:**
```
torch._inductor.exc.TritonMissing: Cannot find a working triton installation.
```

**Solutions** (choose one):

1. **Install triton-windows** (recommended):
   ```bash
   uv pip install triton-windows
   ```

2. **Disable Torch Inductor** (workaround):
   Add to your `.env` file:
   ```bash
   TORCH_COMPILE_DISABLE=1
   ```
   This has minimal performance impact on Docling GPU processing.

#### Apple Silicon (Mac M1/M2/M3/M4)

**CUDA is not available on macOS**. When you select "Mac" in the OS selector on [PyTorch.org](https://pytorch.org/get-started/locally/), the page displays **"Installing on macOS"** and shows:

```bash
# PyTorch.org command (Mac - CPU/MPS only)
pip3 install torch torchvision
```

**Use `uv` for faster installation:**
```bash
# Install PyTorch (MPS support included)
uv pip install torch torchvision

# Set device to use Metal in .env
DOCLING_DEVICE=mps
```

#### CPU Only (No GPU)

If you don't have a GPU or prefer CPU processing:

```bash
# Uninstall GPU versions first
uv pip uninstall torch torchvision

# Install CPU-only PyTorch (smaller download, no CUDA)
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Force CPU device in .env
DOCLING_DEVICE=cpu
```

### Step 3: Verify Installation

**Check installed PyTorch version:**
```bash
uv pip list | grep torch
```

Expected output for CUDA 13.0:
```
torch           2.7.0+cu130
torchvision     0.22.0+cu130
```

**Verify GPU detection:**
```python
import torch
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check CUDA
if torch.cuda.is_available():
    logger.info(f"✓ CUDA available: {torch.cuda.get_device_name(0)}")
    logger.info(f"  CUDA version: {torch.version.cuda}")
    logger.info(f"  GPU count: {torch.cuda.device_count()}")
    logger.info(f"  Total memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
else:
    logger.info("✗ CUDA not available - will use CPU")

# Check MPS (Mac)
if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
    logger.info("✓ MPS (Apple Metal) available")
```

**Expected output for RTX 5090:**
```
✓ CUDA available: NVIDIA GeForce RTX 5090
  CUDA version: 13.0
  GPU count: 1
  Total memory: 34.19 GB
```

### 2. Test Docling Processing

Process a PDF with GPU acceleration:

```bash
# Enable GPU and save results in .env
DOCLING_DEVICE=cuda
SAVE_PARSING_OUTPUT=true
DOCUMENT_PARSER=docling

# Process the document
# Use your UI or REST API to upload and process a PDF
```

### 3. Compare CPU vs GPU Performance

You can benchmark the difference:

```bash
# Test with CPU
DOCLING_DEVICE=cpu
# (Process document and note the time)

# Test with GPU
DOCLING_DEVICE=cuda
# (Process same document and compare time)
```

## Troubleshooting

### "CUDA not available" Error

**Cause**: PyTorch installed without CUDA support

**Solution**: Reinstall PyTorch with CUDA:
```bash
# Uninstall existing versions
uv pip uninstall torch torchvision

# Reinstall with CUDA (replace cu130 with your CUDA version)
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
```

### "NVIDIA GeForce RTX XXXX with CUDA capability sm_XXX is not compatible"

**Cause**: Your GPU architecture is newer than what your PyTorch build supports.

**Example Error**:
```
UserWarning: NVIDIA GeForce RTX 5090 with CUDA capability sm_120 is not compatible 
with the current PyTorch installation. The current PyTorch install supports CUDA 
capabilities sm_50 sm_60 sm_61 sm_70 sm_75 sm_80 sm_86 sm_90.
```

**Solution**: Upgrade to a newer PyTorch build that supports your GPU:
```bash
# Check your CUDA version
nvidia-smi

# For RTX 5090 (Blackwell/sm_120), use CUDA 13.0
uv pip uninstall torch torchvision
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
```

### "Cannot find a working triton installation" (Windows)

**Cause**: Triton for Windows not installed.

**Solutions** (choose one):

1. **Install triton-windows** (recommended):
   ```bash
   uv pip install triton-windows
   ```

2. **Disable Torch Inductor** (workaround):
   Add to your `.env` file:
   ```bash
   TORCH_COMPILE_DISABLE=1
   ```
   This disables Torch Inductor compilation without affecting Docling GPU performance.

### "Out of memory" Error

**Cause**: GPU doesn't have enough memory for large documents

**Solutions**:
1. Force CPU processing: `DOCLING_DEVICE=cpu`
2. Process smaller batches
3. Close other GPU-intensive applications
4. Upgrade GPU memory

### Slow Processing Even with GPU

**Possible causes**:
1. GPU not actually being used (check logs)
2. Document is very large (100+ pages)
3. CUDA drivers outdated
4. Thermal throttling (GPU overheating)

**Debugging**:
```bash
# Check if GPU is being utilized
nvidia-smi  # On Linux/Windows

# Enable verbose logging
# Check logs for "CUDA available" message
```

### Files Not Saved to parsing_output

**Cause**: `SAVE_PARSING_OUTPUT` not set or permission issues

**Solutions**:
1. Verify setting in .env: `SAVE_PARSING_OUTPUT=true`
2. Check write permissions for ./parsing_output/
3. Check logs for error messages

## Configuration Examples

### Production Setup (GPU, No Saving)
```bash
DOCUMENT_PARSER=docling
DOCLING_DEVICE=auto
DOCLING_TIMEOUT=600
SAVE_PARSING_OUTPUT=false
```

### Development/Debugging Setup (CPU, Save Results)
```bash
DOCUMENT_PARSER=docling
DOCLING_DEVICE=cpu
DOCLING_TIMEOUT=300
SAVE_PARSING_OUTPUT=true
```

### High-Performance Setup (Force GPU, Extended Timeout)

First, create `.env` from template if you haven't already:
```bash
cp env-sample.txt .env  # On Windows use: copy env-sample.txt .env
```

Then add to `.env`:
```bash
DOCUMENT_PARSER=docling
DOCLING_DEVICE=cuda
DOCLING_TIMEOUT=900
SAVE_PARSING_OUTPUT=false

# Optional: Disable Torch Inductor if triton-windows not installed
# TORCH_COMPILE_DISABLE=1
```

### LlamaParse with Saved Output (for comparison)
```bash
DOCUMENT_PARSER=llamaparse
LLAMAPARSE_API_KEY=your-api-key
LLAMAPARSE_MODE=parse_page_with_llm
SAVE_PARSING_OUTPUT=true
```

## Performance Tips

1. **Package Manager**: Use `uv pip` instead of `pip` for 10-100x faster package installation
2. **GPU Selection**: Use `cuda` for NVIDIA GPUs, `mps` for Apple Silicon
3. **Batch Processing**: Process multiple documents in one session for better GPU utilization
4. **Timeout Settings**: Increase `DOCLING_TIMEOUT` for very large documents (100+ pages)
5. **Memory Management**: Close other GPU applications during processing
6. **Driver Updates**: Keep CUDA drivers and PyTorch updated for best performance
7. **Triton on Windows**: Install `triton-windows` for full PyTorch compiler support, or use `TORCH_COMPILE_DISABLE=1` if you encounter Triton errors

## Quick Reference: Installation Commands

### Check Your Setup
```bash
# Check CUDA version (NVIDIA GPUs)
nvidia-smi

# Check installed PyTorch
uv pip list | grep torch

# Verify GPU in Python
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

### Install PyTorch with UV

**NVIDIA GPU (CUDA 13.0 - Latest, Windows/Linux):**
```bash
uv pip uninstall torch torchvision
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130

# Windows only: For full PyTorch compiler support
uv pip install triton-windows
```

**NVIDIA GPU (CUDA 12.8):**
```bash
uv pip uninstall torch torchvision
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

**NVIDIA GPU (CUDA 12.6):**
```bash
uv pip uninstall torch torchvision
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

**Mac (Apple Silicon):**
```bash
uv pip install torch torchvision
```

**CPU Only:**
```bash
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### Environment Configuration

If you don't have a `.env` file yet, copy `env-sample.txt` to `.env`:
```bash
# In the flexible-graphrag directory
cp env-sample.txt .env  # On Windows use: copy env-sample.txt .env
```

Then add these settings to your `.env` file:
```bash
# GPU Configuration
DOCLING_DEVICE=auto  # or cuda, mps, cpu

# Optional: Disable Torch Inductor if triton-windows not installed
# TORCH_COMPILE_DISABLE=1

# Optional: Save parsing results
SAVE_PARSING_OUTPUT=true
```

## Related Documentation

**User Guides (docs/):**
- [TIMEOUT-CONFIGURATIONS.md](TIMEOUT-CONFIGURATIONS.md) - Timeout settings for Docling
- [LLM-EMBEDDING-CONFIG.md](LLM-EMBEDDING-CONFIG.md) - LLM and embedding configuration
- [ENVIRONMENT-CONFIGURATION.md](ENVIRONMENT-CONFIGURATION.md) - Full environment configuration

## Language Support

Docling supports multi-language documents including:
- English, German, French, Spanish, Italian
- Czech, Polish, Slovak
- Russian, Chinese, Japanese
- And many more...

Multi-language technical documents with tables and diagrams process well with Docling on GPU.
