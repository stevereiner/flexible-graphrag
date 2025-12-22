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

# Copy pyproject.toml and uv.toml first for better caching
COPY pyproject.toml uv.toml ./

# Method 1: Install using pyproject.toml (CURRENT - modern approach)
# This installs the package in editable mode with all dependencies
RUN uv pip install --system -e .

# Method 2: Install using requirements.txt (OLD - commented out)
# Uncomment the lines below and comment out the pyproject.toml method above
# if you want to use the legacy requirements.txt approach
# COPY requirements.txt .
# RUN uv pip install --system -r requirements.txt

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
