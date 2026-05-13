# Installation Guide - Observability Options

## Install Options

### Option 1: DUAL Mode (OpenLIT + OpenInference)

```bash
# Install with both OpenInference (LlamaIndex + LangChain) + OpenLIT
uv pip install -e ".[observability-dual]"

# Enable DUAL mode
export OBSERVABILITY_BACKEND=both

# Run your app
python -m flexible-graphrag.main
```

**What you get:**
- Token metrics (from OpenLIT)
- Rich traces for LlamaIndex + LangChain (from OpenInference)
- Cost tracking (from OpenLIT)
- VectorDB metrics (from OpenLIT)
- Custom RAG metrics (graph extraction, etc.)

---

## Other Install Options

### Option 2: OpenInference Only (Default — recommended for normal development)

```bash
# Install with OpenInference (covers both LlamaIndex and LangChain)
uv pip install -e ".[observability]"

# No env var needed (default mode)
python -m flexible-graphrag.main
```

**What you get:**
- Rich traces for LlamaIndex and LangChain
- Custom RAG metrics
- Token metrics via spanmetrics

### Option 3: OpenLIT Only

```bash
# Install with OpenLIT
uv pip install -e ".[observability-openlit]"

# Set OpenLIT mode
export OBSERVABILITY_BACKEND=openlit

# Run your app
python -m flexible-graphrag.main
```

**What you get:**
- Token metrics (guaranteed)
- Cost tracking
- VectorDB metrics
- Basic traces
- Custom RAG metrics

### Option 4: All Observability (Development)

```bash
# Install everything
uv pip install -e ".[observability-all]"

# Same as observability-dual
```

**Use for:** Testing different backends

---

## Installation Commands Summary

| Command | What Gets Installed | Mode | Use Case |
|---------|-------------------|------|----------|
| `uv pip install -e ".[observability]"` | OpenInference (LlamaIndex + LangChain) | Default | Traces-focused |
| `uv pip install -e ".[observability-openlit]"` | OpenLIT | OpenLIT only | Metrics-focused |
| `uv pip install -e ".[observability-dual]"` | Both | DUAL | Token metrics + rich traces |
| `uv pip install -e ".[observability-all]"` | Both | All options | Development/testing |

---

## Verify Installation

### Check Installed Packages

```bash
# For OpenInference
uv pip show openinference-instrumentation-llama-index openinference-instrumentation-langchain
# Should show both packages

# For OpenLIT
uv pip show openlit
# Should show: openlit

# For OTEL
uv pip list | grep opentelemetry
# Should show: opentelemetry-exporter-otlp, opentelemetry-sdk, opentelemetry-api
```

### Check Application Logs

After starting your app, look for:

**OpenInference only:**
```
Setting up observability with backend: openinference
Initializing OpenInference as OTLP producer...
OpenInference LlamaIndex instrumentation enabled
OpenInference LangChain instrumentation enabled
```

**OpenLIT only:**
```
Setting up observability with backend: openlit
Initializing OpenLIT as OTLP producer...
OpenLIT active - token metrics enabled!
```

**DUAL mode:**
```
Setting up observability with backend: both
Initializing OpenLIT as OTLP producer...
OpenLIT active - token metrics enabled!
Initializing OpenInference as additional OTLP producer...
OpenInference LlamaIndex instrumentation enabled
OpenInference LangChain instrumentation enabled
Observability setup complete - DUAL MODE
   OpenLIT -> Token metrics, costs, VectorDB metrics
   OpenInference -> Detailed traces (LlamaIndex + LangChain)
   Custom metrics -> Graph extraction, retrieval, etc.
```

---

## Environment Variables

```bash
# Choose observability backend (after installation)
export OBSERVABILITY_BACKEND=both          # DUAL mode
export OBSERVABILITY_BACKEND=openinference  # OpenInference only (default — recommended)
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
      # Enable DUAL mode (see OpenLIT warning in Installation guide)
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

# Install with DUAL observability (see OpenLIT warning in Installation guide)
RUN pip install -e ".[observability-dual]"

# Or for minimal:
# RUN pip install -e ".[observability]"

CMD ["python", "-m", "flexible-graphrag.main"]
```

---

## Upgrading from OpenInference to DUAL Mode

If you already have OpenInference installed:

```bash
# Just add OpenLIT (>=1.41.2 no longer downgrades openai)
uv pip install "openlit>=1.41.2"

# Or reinstall with dual extras
uv pip install -e ".[observability-dual]"

# Enable DUAL mode
export OBSERVABILITY_BACKEND=both

# Restart app
# Token metrics will work immediately!
```

No uninstall needed — they coexist at the package level.

---

## Troubleshooting

### Import Error: No module named 'openlit'

**Problem:** OpenLIT not installed

**Solution:**
```bash
uv pip install "openlit>=1.41.2"
# Or
uv pip install -e ".[observability-dual]"
```

### Import Error: No module named 'openinference'

**Problem:** OpenInference not installed

**Solution:**
```bash
uv pip install openinference-instrumentation-llama-index openinference-instrumentation-langchain
# Or
uv pip install -e ".[observability-dual]"
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

## Summary

### Quick Start — OpenInference (default, recommended for normal development)

```bash
# 1. Install with OpenInference (LlamaIndex + LangChain)
uv pip install -e ".[observability]"

# 2. Start app (no env var needed — OpenInference is the default)
python -m flexible-graphrag.main

# 3. Import Grafana dashboard
# docker/otel/dashboards/flexible-graphrag-complete-dashboard.json
```

### DUAL Mode — if you need token metrics and cost tracking

```bash
# 1. Install with DUAL mode
uv pip install -e ".[observability-dual]"

# 2. Enable DUAL mode
export OBSERVABILITY_BACKEND=both

# 3. Start app
python -m flexible-graphrag.main

# 4. Import Grafana dashboard
# docker/otel/dashboards/flexible-graphrag-complete-dashboard.json
```

**OpenLIT adds:** automatic LLM token metrics, cost tracking per request, and VectorDB operation metrics.

---

**Status:** Installation options fully documented and ready to use.


