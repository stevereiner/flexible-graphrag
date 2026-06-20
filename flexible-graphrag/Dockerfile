# Base Image Options:
# 
# IMPORTANT: Image size mainly impacts:
# - Docker image distribution/download time (pushing/pulling from registry)
# - Storage space on disk
# - Initial docker build time (first time only)
# 
# Image size does NOT significantly impact:
# - Development workflow or startup speed after first build
# - Runtime performance (all options perform the same once running)
# - Docker container start time (negligible difference)
# 
# Option 1: python:3.12 (CURRENT - ~1GB, most compatible)
# - Full Debian-based image with gcc, g++, make, python-dev pre-installed
# - Required for building C extensions (pystemmer, etc.) on all platforms
# - Fixes build failures on both Linux and macOS (especially Apple Silicon)
# - Final image size: ~1GB
# - Guaranteed compatibility
FROM python:3.12

# Option 2: python:3.12-slim (~200MB smaller but requires build tools)
# Uncomment below and comment out python:3.12 above to use slim
# - Debian-based but minimal, needs build tools installed manually
# - Base image: ~150MB, final image: ~800MB (after adding build tools + dependencies)
# - Saves ~200MB compared to full image
# - Use this if you're distributing images and want smaller downloads
# - Note: Requires installing build-essential for C extensions to compile
# FROM python:3.12-slim
# RUN apt-get update && apt-get install -y \
#     gcc g++ make python3-dev \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

# Option 3: python:3.12-alpine (~50MB base, smallest but compatibility issues)
# Uncomment below and comment out python:3.12 above to use Alpine
# - Alpine uses musl libc instead of glibc, which causes compatibility issues
# - Base image: ~50MB, final image: ~200-300MB
# - Many Python packages with C extensions fail to build on Alpine
# - Python 3.13-alpine would NOT help - the musl libc issue exists in all Alpine versions
# - Not recommended for projects with complex dependencies like this one
# FROM python:3.12-alpine
# RUN apk add --no-cache \
#     gcc musl-dev python3-dev \
#     libffi-dev openssl-dev \
#     curl \
#     && rm -rf /var/cache/apk/*

WORKDIR /app

# Install system dependencies (for Option 1: python:3.12)
# Only curl needed since build tools are already included
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Note: If using Option 2 (slim), uncomment the gcc/g++/make/python3-dev lines in Option 2 above
# Note: If using Option 3 (alpine), use the apk commands in Option 3 above instead of apt-get

# Install uv for faster package installation
RUN pip install uv

# Copy dependency files first for better layer caching.
# extras-overrides.txt must be present before install so --override can reference it.
COPY pyproject.toml uv.toml extras-overrides.txt ./

# Optional extras to install alongside base dependencies.
# extras-overrides.txt suppresses advisory-only transitive downgrades from langchain-extras
# (fsspec<2025, pgvector<0.4, requests/urllib3/rich pins from hugegraph-python, etc.)
# so langchain-extras is safe to include by default.
#
# Note: rapidocr is bundled with docling-slim[standard] (a base dependency), so basic
# OCR for scanned PDFs works out of the box without any docling-ocr-* extra.
#
# Override at build time:
#   docker build --build-arg EXTRAS="langchain,langchain-extras,rdf,observability" .
#   docker build --build-arg EXTRAS="" .   (base dependencies only)
#
# Excluded from default:
#   docling-ocr-easyocr/tesserocr  — alternative OCR engines needing extra system libs
#   docling-ocr-ocrmac              — macOS only
#   surrealdb-extras, age-extras, spanner-extras — niche integrations
ARG EXTRAS="langchain,langchain-extras,rdf,observability"

RUN if [ -n "$EXTRAS" ]; then \
        uv pip install --override extras-overrides.txt --system -e ".[$EXTRAS]"; \
    else \
        uv pip install --system -e .; \
    fi

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads sample_docs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application with standard asyncio loop (uvloop conflicts with nest_asyncio)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]
