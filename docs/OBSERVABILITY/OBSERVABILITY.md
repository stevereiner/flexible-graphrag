# Observability for Flexible GraphRAG

Comprehensive OpenTelemetry-based observability for LlamaIndex RAG applications with traces, metrics, and visualization.

## Overview

Flexible GraphRAG includes built-in support for production-grade observability using open-source tools:

- **OpenTelemetry**: Industry-standard instrumentation framework
- **OpenInference**: Automatic LlamaIndex operation tracing
- **Jaeger**: Distributed tracing visualization
- **Prometheus**: Metrics collection and storage
- **Grafana**: Beautiful dashboards and visualization

## Quick Start

### 1. Enable Observability

Install observability dependencies (optional):

```bash
# Using uv (recommended)
cd flexible-graphrag
uv pip install -e ".[observability]"

# Or using pip
pip install -e ".[observability]"

# Or install individually
pip install openinference-instrumentation-llama-index opentelemetry-exporter-otlp opentelemetry-sdk opentelemetry-api
```

Edit your `.env` file:

```bash
# Enable observability
ENABLE_OBSERVABILITY=true

# OTLP endpoint (default: http://localhost:4318)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# Service metadata
OTEL_SERVICE_NAME=flexible-graphrag
OTEL_SERVICE_VERSION=1.0.0

# Enable automatic LlamaIndex instrumentation
ENABLE_LLAMA_INDEX_INSTRUMENTATION=true
```

### 2. Start Observability Stack

Using Docker Compose:

```bash
cd docker
# Uncomment observability.yaml in docker-compose.yaml first
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
```

Make sure `observability.yaml` is uncommented in `docker-compose.yaml`:

```yaml
include:
  - includes/observability.yaml
```

Or use the quick start script:

```bash
cd docker
./start-observability.sh  # or start-observability.bat on Windows
```

### 3. Access Dashboards

Once running, access the following UIs:

- **Grafana**: http://localhost:3009 (admin/admin)
  - Pre-configured dashboards for RAG metrics
  - Visualization of all metrics and traces
  
- **Jaeger**: http://localhost:16686
  - Distributed tracing for all operations
  - See complete request flows
  
- **Prometheus**: http://localhost:9090
  - Raw metrics exploration
  - PromQL query interface

<p align="center">
  <a href="../../screen-shots/observability/observability-grafana-prometheus-jaeger-ui.png">
    <img src="../../screen-shots/observability/observability-grafana-prometheus-jaeger-ui.png" alt="Observability Stack: Grafana, Prometheus, and Jaeger" width="700">
  </a>
</p>

### 4. Start Your Application

The application will automatically send traces and metrics to the OTLP collector:

```bash
cd flexible-graphrag
uv run start.py
```

## What Gets Monitored

### Automatic Instrumentation (via OpenInference)

When `ENABLE_LLAMA_INDEX_INSTRUMENTATION=true`, all LlamaIndex operations are automatically traced:

- Document loading and chunking
- Embedding generation
- Vector similarity search
- LLM completions
- Graph query execution
- Retrieval operations

### Custom Metrics

The following RAG-specific metrics are collected:

#### Retrieval Metrics
- `rag.retrieval.latency_ms` - Document retrieval time
- `rag.retrieval.num_documents` - Number of documents retrieved
- `rag.retrieval.relevance_score` - Relevance scores

#### LLM Metrics
- `llm.generation.latency_ms` - LLM response time
- `llm.tokens.generated` - Tokens generated
- `llm.tokens.prompt` - Prompt tokens used
- `llm.requests.total` - Total LLM requests

#### Graph Extraction Metrics
- `rag.graph.extraction_latency_ms` - Knowledge graph extraction time
- `rag.graph.entities_extracted` - Entities extracted
- `rag.graph.relations_extracted` - Relations extracted

#### Document Processing Metrics
- `rag.document.processing_latency_ms` - Document processing time
- `rag.document.processed_total` - Documents processed
- `rag.document.chunks_created` - Chunks created

#### Vector Indexing Metrics
- `rag.vector.indexing_latency_ms` - Vector indexing time
- `rag.vector.indexed_total` - Vectors indexed

#### Error Metrics
- `rag.errors.total` - Total errors
- `rag.errors.by_type` - Errors by type

## Architecture

```
┌─────────────────────────┐
│  Flexible GraphRAG App  │
│  (with OpenTelemetry)   │
└───────────┬─────────────┘
            │ OTLP (HTTP/gRPC)
            ▼
┌─────────────────────────┐
│  OTLP Collector         │
│  (receives & processes) │
└──────┬──────────┬───────┘
       │          │
       │          │
   ┌───▼──┐   ┌──▼────┐
   │Jaeger│   │Prometheus│
   │(traces)  │(metrics)│
   └──────┘   └───┬────┘
                  │
              ┌───▼────┐
              │Grafana │
              │(dashboards)
              └────────┘
```

## Advanced Usage

### Custom Instrumentation

Use decorators to add custom tracing to your code:

```python
from observability import trace_retrieval, trace_llm_call, trace_graph_extraction

@trace_retrieval
def my_custom_retrieval(query: str, top_k: int = 5):
    # Your retrieval logic
    results = index.as_retriever(similarity_top_k=top_k).retrieve(query)
    return results

@trace_llm_call(model_name="gpt-4o-mini", provider="openai")
def my_custom_generation(context: str, query: str):
    llm = OpenAI(model="gpt-4o-mini")
    response = llm.complete(f"Context: {context}\n\nQuestion: {query}")
    return response

@trace_graph_extraction
def extract_custom_entities(documents):
    # Your extraction logic
    return entities
```

### Manual Metrics Recording

Record custom metrics:

```python
from observability.metrics import get_rag_metrics

metrics = get_rag_metrics()

# Record retrieval
metrics.record_retrieval(
    latency_ms=123.4,
    num_documents=5,
    top_score=0.95,
    attributes={"index": "my-index"}
)

# Record LLM call
metrics.record_llm_call(
    latency_ms=567.8,
    prompt_tokens=100,
    completion_tokens=50,
    attributes={"model": "gpt-4o-mini"}
)

# Record graph extraction
metrics.record_graph_extraction(
    latency_ms=2345.6,
    num_entities=25,
    num_relations=40,
    attributes={"extractor": "schema"}
)
```

### Custom Spans

Create custom spans for detailed tracing:

```python
from observability.telemetry_setup import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("my-custom-operation") as span:
    span.set_attribute("operation.type", "custom")
    span.set_attribute("operation.input_size", len(input_data))
    
    # Your operation logic
    result = do_something()
    
    span.set_attribute("operation.output_size", len(result))
```

## Prometheus Queries

Useful PromQL queries for monitoring:

```promql
# Average retrieval latency (last 5 minutes)
avg_over_time(rag_retrieval_latency_ms[5m])

# P99 retrieval latency
histogram_quantile(0.99, rate(rag_retrieval_latency_ms_bucket[5m]))

# P95 LLM generation latency
histogram_quantile(0.95, rate(llm_generation_latency_ms_bucket[5m]))

# Total tokens generated per minute
sum(rate(llm_tokens_generated[1m])) * 60

# Error rate
rate(rag_errors_total[5m]) / rate(rag_retrieval_latency_ms_count[5m])

# Documents processed per second
sum(rate(rag_document_processed_total[5m]))

# Average documents retrieved
avg_over_time(rag_retrieval_num_documents[5m])

# Graph extraction rate
rate(rag_graph_entities_extracted[5m])
```

## Grafana Dashboards

Pre-configured dashboards are automatically provisioned:

### RAG Metrics Dashboard

Located at: **Dashboards → RAG Observability → Flexible GraphRAG - RAG Metrics**

Panels include:
- Document Retrieval Latency (P95, P99)
- LLM Generation Latency (P95, P99)
- LLM Requests/sec
- Tokens Generated/sec
- Documents Processed/sec
- Error Rate
- Average Documents Retrieved
- Knowledge Graph Extraction Latency
- **Knowledge Graph Extraction Rate** - Shows `rate()` of entities/relations during active ingestion (0 when idle)
- **Total Entities Extracted** - Cumulative entity count across all ingestions
- **Total Relations Extracted** - Cumulative relation count across all ingestions

**Note**: Rate panels show per-second extraction activity (0 when idle), while Total panels show cumulative counts since system start.

## Alternative Backends

### Option A: Local Stack (Default)

Prometheus + Grafana + Jaeger - Complete control, included in Docker setup.

### Option B: SigNoz (All-in-One)

Self-hosted observability platform with built-in dashboards:

```bash
git clone https://github.com/SigNoz/signoz.git
cd signoz/deploy
docker-compose up -d
```

Update `.env`:
```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

Access: http://localhost:3301

### Option C: Langfuse (LLM-Specific)

Open-source LLM observability platform:

```bash
docker run -d \
  -p 3000:3000 \
  -e DATABASE_URL="postgresql://user:password@postgres:5432/langfuse" \
  -e NEXTAUTH_SECRET="your-secret" \
  langfuse/langfuse:latest
```

Update `.env`:
```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:3000/api/public/ingestion/otel
```

## Production Checklist

- [ ] Observability enabled in production `.env`
- [ ] OTLP collector endpoint configured correctly
- [ ] Batch span processor configured (default: 10s, 1024 batch size)
- [ ] Memory limiter set appropriately (default: 512 MiB)
- [ ] Grafana alerts configured:
  - Retrieval latency > 2s
  - Generation latency > 10s
  - Error rate > 1%
  - Token costs trending upward
- [ ] Sampling configured for high-traffic (if needed)
- [ ] Storage retention policy set (Prometheus/Jaeger)
- [ ] Dashboards shared with team
- [ ] On-call rotation has access to dashboards

## Troubleshooting

### No traces appearing in Jaeger

1. Check OTLP collector is running: `docker ps | grep otel-collector`
2. Check collector logs: `docker logs flexible-graphrag-otel-collector`
3. Verify endpoint in `.env`: `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`
4. Ensure `ENABLE_OBSERVABILITY=true` in `.env`

### No metrics in Prometheus

1. Check Prometheus is scraping OTLP collector: http://localhost:9090/targets
2. Verify collector metrics endpoint: http://localhost:8889/metrics
3. Check Prometheus config: `docker/otel/prometheus.yml`

### Grafana dashboards not showing data

1. Verify Prometheus datasource: Grafana → Configuration → Data Sources
2. Check Prometheus has data: http://localhost:9090/graph
3. Verify dashboard queries match metric names
4. Check time range (default: last 15 minutes)

### High overhead

1. Reduce batch size in `otel-collector-config.yaml`
2. Increase batch timeout (trade latency for efficiency)
3. Disable automatic instrumentation: `ENABLE_LLAMA_INDEX_INSTRUMENTATION=false`
4. Use manual instrumentation for critical paths only

## References

- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [OpenInference for LlamaIndex](https://github.com/Arize-ai/openinference)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)

