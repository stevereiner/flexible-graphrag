# Installation Guide - Observability Options

**Updated:** December 30, 2025

---

## Quick Install (RECOMMENDED)

### Option 1: DUAL Mode (Best of Both Worlds!) 🌟

```bash
# Install with both OpenInference + OpenLIT
pip install -e ".[observability-dual]"

# Enable DUAL mode
export OBSERVABILITY_BACKEND=both

# Run your app
python -m flexible-graphrag.main
```

**What you get:**
- ✅ Token metrics (from OpenLIT)
- ✅ Rich traces (from OpenInference)  
- ✅ Cost tracking (from OpenLIT)
- ✅ VectorDB metrics (from OpenLIT)
- ✅ Custom RAG metrics (graph extraction, etc.)

---

## Other Install Options

### Option 2: OpenInference Only (Default)

```bash
# Install with OpenInference
pip install -e ".[observability]"

# No env var needed (default mode)
python -m flexible-graphrag.main
```

**What you get:**
- ✅ Rich traces
- ✅ Custom RAG metrics
- ⚠️ Token metrics via spanmetrics (uncertain)

### Option 3: OpenLIT Only

```bash
# Install with OpenLIT
pip install -e ".[observability-openlit]"

# Set OpenLIT mode
export OBSERVABILITY_BACKEND=openlit

# Run your app
python -m flexible-graphrag.main
```

**What you get:**
- ✅ Token metrics (guaranteed!)
- ✅ Cost tracking
- ✅ VectorDB metrics
- ✅ Basic traces
- ✅ Custom RAG metrics

### Option 4: All Observability (Development)

```bash
# Install everything
pip install -e ".[observability-all]"

# Same as observability-dual
```

**Use for:** Testing different backends

---

## Installation Commands Summary

| Command | What Gets Installed | Mode | Use Case |
|---------|-------------------|------|----------|
| `pip install -e ".[observability]"` | OpenInference | Default | Minimal, traces-focused |
| `pip install -e ".[observability-openlit]"` | OpenLIT | OpenLIT only | Metrics-focused |
| `pip install -e ".[observability-dual]"` | Both | **DUAL (recommended)** | Best of both |
| `pip install -e ".[observability-all]"` | Both | All options | Development/testing |

---

## Verify Installation

### Check Installed Packages

```bash
# For OpenInference
pip list | grep openinference
# Should show: openinference-instrumentation-llama-index

# For OpenLIT
pip list | grep openlit
# Should show: openlit

# For OTEL
pip list | grep opentelemetry
# Should show: opentelemetry-exporter-otlp, opentelemetry-sdk, opentelemetry-api
```

### Check Application Logs

After starting your app, look for:

**OpenInference only:**
```
🚀 Setting up observability with backend: openinference
📡 Initializing OpenInference as OTLP producer...
✅ OpenInference instrumentation enabled
```

**OpenLIT only:**
```
🚀 Setting up observability with backend: openlit
📡 Initializing OpenLIT as OTLP producer...
✅ OpenLIT active - token metrics enabled!
```

**DUAL mode (RECOMMENDED):**
```
🚀 Setting up observability with backend: both
📡 Initializing OpenLIT as OTLP producer...
✅ OpenLIT active - token metrics enabled!
📡 Initializing OpenInference as additional OTLP producer...
✅ OpenInference instrumentation enabled
🎉 Observability setup complete - DUAL MODE
   📊 OpenLIT → Token metrics, costs, VectorDB metrics
   📊 OpenInference → Detailed traces
   📊 Custom metrics → Graph extraction, retrieval, etc.
   🎯 Best of both worlds!
```

---

## Environment Variables

```bash
# Choose observability backend (after installation)
export OBSERVABILITY_BACKEND=both          # DUAL mode (recommended!)
export OBSERVABILITY_BACKEND=openinference  # OpenInference only
export OBSERVABILITY_BACKEND=openlit        # OpenLIT only

# OTLP endpoint (optional, default: http://localhost:4318)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318

# Enable/disable (optional, default: true if packages installed)
export ENABLE_OBSERVABILITY=true

# Deployment environment (optional, default: production)
export DEPLOYMENT_ENV=production
```

---

## Docker Compose Setup

If using Docker Compose, update your service:

```yaml
# docker-compose.yml
services:
  flexible-graphrag:
    build:
      context: ./flexible-graphrag
      dockerfile: Dockerfile
    environment:
      # Enable DUAL mode
      - OBSERVABILITY_BACKEND=both
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
      - ENABLE_OBSERVABILITY=true
    depends_on:
      - otel-collector
      - prometheus
      - jaeger
```

Update your Dockerfile:

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY . .

# Install with DUAL observability (RECOMMENDED!)
RUN pip install -e ".[observability-dual]"

# Or for minimal:
# RUN pip install -e ".[observability]"

CMD ["python", "-m", "flexible-graphrag.main"]
```

---

## Upgrading from OpenInference to DUAL Mode

If you already have OpenInference installed:

```bash
# Just add OpenLIT
pip install openlit

# Or reinstall with dual extras
pip install -e ".[observability-dual]"

# Enable DUAL mode
export OBSERVABILITY_BACKEND=both

# Restart app
# Token metrics will work immediately!
```

No uninstall needed - they coexist perfectly!

---

## Troubleshooting

### Import Error: No module named 'openlit'

**Problem:** OpenLIT not installed

**Solution:**
```bash
pip install openlit
# Or
pip install -e ".[observability-dual]"
```

### Import Error: No module named 'openinference'

**Problem:** OpenInference not installed

**Solution:**
```bash
pip install openinference-instrumentation-llama-index
# Or
pip install -e ".[observability-dual]"
```

### Observability not starting

**Check 1: Are packages installed?**
```bash
pip list | grep -E "openlit|openinference"
```

**Check 2: Is OTEL Collector running?**
```bash
docker-compose ps otel-collector
# Should show "Up"
```

**Check 3: Check app logs**
```bash
# Should see "Setting up observability..."
# If not, check ENABLE_OBSERVABILITY env var
```

### Wrong backend is active

**Problem:** Expected DUAL mode but only one backend started

**Solution:**
```bash
# Verify env var
echo $OBSERVABILITY_BACKEND
# Should be "both"

# If not set:
export OBSERVABILITY_BACKEND=both

# Restart app
```

---

## Requirements File Alternative

If you prefer `requirements.txt` over extras:

```bash
# For DUAL mode, add to requirements.txt:
openinference-instrumentation-llama-index
openlit
opentelemetry-exporter-otlp
opentelemetry-sdk
opentelemetry-api

# Then install:
pip install -r requirements.txt
```

---

## Poetry Alternative

If using Poetry:

```bash
# Add to pyproject.toml [tool.poetry.dependencies]:
openinference-instrumentation-llama-index = { version = "*", optional = true }
openlit = { version = "*", optional = true }
opentelemetry-exporter-otlp = { version = "*", optional = true }
opentelemetry-sdk = { version = "*", optional = true }
opentelemetry-api = { version = "*", optional = true }

# [tool.poetry.extras]
observability-dual = [
    "openinference-instrumentation-llama-index",
    "openlit",
    "opentelemetry-exporter-otlp",
    "opentelemetry-sdk",
    "opentelemetry-api",
]

# Install:
poetry install --extras observability-dual
```

---

## Summary

### Quick Start (RECOMMENDED)

```bash
# 1. Install with DUAL mode
pip install -e ".[observability-dual]"

# 2. Enable DUAL mode
export OBSERVABILITY_BACKEND=both

# 3. Start app
python -m flexible-graphrag.main

# 4. Import Grafana dashboard
# docker/otel/dashboards/flexible-graphrag-complete-dashboard.json

# Done! Token metrics work! 🎉
```

**Why DUAL mode?**
- ✅ Guaranteed token metrics
- ✅ Rich detailed traces
- ✅ Cost tracking
- ✅ All custom metrics
- ✅ No conflicts
- ✅ Easy to setup

---

**Status:** Installation options fully documented and ready to use! 📦


