# DUAL OTLP Producers Guide

!!! warning "OpenLIT compatibility issue (as of openlit py-1.40.3)"
    Installing OpenLIT **downgrades `openai` from 2.30.0 to 1.109.1**, which may impact OpenAI functionality.
    Use a fresh virtual environment when experimenting with DUAL mode, and run `uv pip install -e .`
    again after you are done. OpenLIT provides **automatic LLM token metrics, cost tracking, and VectorDB metrics**
    that OpenInference does not — but these come at the cost of the openai version conflict.
    For normal development, use OpenInference only (the default).

---

## DUAL Mode Architecture

```
+------------------------------------------+
|   Flexible GraphRAG Application          |
|                                          |
|  +---------------+  +------------------+ |
|  | OpenInference |  |     OpenLIT      | |
|  |   (traces)    |  | (traces+metrics) | |
|  +------+--------+  +------+-----------+ |
+---------+---------------- +--------------+
          |                 |
          +--------+--------+
                   ↓
          +----------------+
          | OTEL Collector |
          |  (OTLP 4318)   |
          +--------+-------+
                   |
        +----------+----------+
        ↓                     ↓
   +---------+         +------------+
   |  Jaeger |         | Prometheus |
   |(traces) |         | (metrics)  |
   +---------+         +------+-----+
                              ↓
                       +-------------+
                       |   Grafana   |
                       +-------------+
```

**Benefits:**
- ✅ OpenInference: Detailed LlamaIndex traces
- ✅ OpenLIT: Token metrics, costs, VectorDB metrics
- ✅ Custom metrics: Graph extraction, retrieval
- ✅ **No conflicts** - they coexist perfectly!

---

## 🚀 Quick Setup (3 minutes!)

### Step 1: Install OpenLIT

```bash
pip install openlit
```

### Step 2: Enable DUAL Mode

**Option A: Environment Variable** (Recommended)
```bash
# In .env
OBSERVABILITY_BACKEND=both
```

**Option B: Docker Compose**
```yaml
services:
  flexible-graphrag:
    environment:
      - OBSERVABILITY_BACKEND=both
```

**Option C: Code** (if you call setup directly)
```python
setup_observability(backend="both")
```

### Step 3: Restart Application

```bash
# Your app will automatically initialize both backends
# Check logs for:
# 🚀 Setting up observability with backend: both
# ✅ OpenLIT active - token metrics enabled!
# ✅ OpenInference instrumentation enabled
# 🎉 Observability setup complete - DUAL MODE
```

That's it! 🎉

---

## 📊 What You Get

### From OpenLIT (Automatic!)

```promql
# Token metrics (GUARANTEED!)
gen_ai_usage_input_tokens_total{gen_ai_request_model="gpt-4"}
gen_ai_usage_output_tokens_total{gen_ai_request_model="gpt-4"}

# Request counts by model
gen_ai_total_requests{gen_ai_request_model="gpt-4"}

# Cost tracking (bonus!)
gen_ai_total_cost{gen_ai_request_model="gpt-4"}

# Latency histograms
gen_ai_request_duration_seconds_bucket{gen_ai_request_model="gpt-4"}

# VectorDB metrics (bonus!)
db_total_requests{db_system="neo4j"}
```

### From OpenInference (Still Active!)

```
# Detailed traces in Jaeger
- All LlamaIndex operations
- Rich span attributes
- Token counts as attributes
```

### From Your Custom Metrics (Still Work!)

```promql
# Graph extraction
rag_graph_entities_extracted_total
rag_graph_relations_extracted_total

# Search/retrieval
rag_retrieval_latency_ms
rag_retrieval_num_documents

# LLM operations
llm_generation_latency_ms
llm_requests_total
```

---

## 🎨 Grafana Dashboard Updates

### Update "Tokens Generated/sec" Panel

**Before (showing 0):**
```promql
sum(rate(llm_tokens_generated_total[5m]))
```

**After (works!):**
```promql
# Prompt + Completion tokens/sec from OpenLIT
sum(rate(gen_ai_usage_input_tokens_total[5m])) + 
sum(rate(gen_ai_usage_output_tokens_total[5m]))
```

### Add New Panels (Bonus!)

**Cost per Hour:**
```promql
sum(rate(gen_ai_total_cost[1h])) * 3600
```

**Requests by Model:**
```promql
sum by (gen_ai_request_model) (rate(gen_ai_total_requests[5m]))
```

**VectorDB Operations:**
```promql
sum by (db_system) (rate(db_total_requests[5m]))
```

### Or Import Pre-Built Dashboard

Visit: https://docs.openlit.io/latest/sdk/destinations/prometheus-jaeger#3-import-the-pre-built-dashboard

---

## 🔧 OTEL Collector (No Changes Needed!)

Your existing config works perfectly! Both OpenInference and OpenLIT send to the same OTLP endpoint.

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "0.0.0.0:4318"  # Both send here!
      grpc:
        endpoint: "0.0.0.0:4317"

# Spanmetrics still works but now optional
# OpenLIT sends token metrics directly!

service:
  pipelines:
    traces:
      receivers: [otlp]  # Receives from both!
      exporters: [otlp/jaeger, spanmetrics]
    
    metrics:
      receivers: [otlp, spanmetrics]  # Receives from both + spanmetrics!
      exporters: [prometheus]
```

---

## ✅ Verification Steps

### 1. Check Application Logs

```bash
# Should see:
🚀 Setting up observability with backend: both
📡 Initializing OpenLIT as OTLP producer...
✅ OpenLIT active - token metrics enabled!
📡 Initializing OpenInference as additional OTLP producer...
✅ OpenInference instrumentation enabled
✅ Custom RAG metrics initialized
🎉 Observability setup complete - DUAL MODE
   📊 OpenLIT → Token metrics, costs, VectorDB metrics
   📊 OpenInference → Detailed traces
   📊 Custom metrics → Graph extraction, retrieval, etc.
   🎯 Best of both worlds!
```

### 2. Check Prometheus Metrics

Visit http://localhost:9090 and search for:

**OpenLIT metrics:**
- `gen_ai_usage_input_tokens_total` ✅
- `gen_ai_usage_output_tokens_total` ✅
- `gen_ai_total_requests` ✅
- `gen_ai_total_cost` ✅

**Custom metrics (still work):**
- `rag_graph_entities_extracted_total` ✅
- `rag_graph_relations_extracted_total` ✅

**Spanmetrics (bonus from OpenInference):**
- `calls_total` ✅
- `duration_milliseconds_bucket` ✅

### 3. Check Jaeger Traces

Visit http://localhost:16686

**Should see traces from:**
- OpenInference (llama_index.* spans)
- OpenLIT (gen_ai.* spans)

Both coexist! 🎉

---

## 🤔 FAQ

### Q: Won't this create duplicate data?

**A:** No! They send **complementary** data:
- **OpenLIT:** Focuses on LLM-specific metrics (tokens, costs)
- **OpenInference:** Focuses on detailed traces
- **No conflicts** - different metric names and purposes

### Q: Is this inefficient?

**A:** Negligible overhead:
- Both are lightweight OpenTelemetry producers
- OTLP protocol is efficient
- Collector handles deduplication if needed
- **Benefits far outweigh minimal overhead**

### Q: Can I disable one later?

**A:** Yes! Just change the env var:
```bash
OBSERVABILITY_BACKEND=openinference  # OpenInference only
OBSERVABILITY_BACKEND=openlit        # OpenLIT only
OBSERVABILITY_BACKEND=both           # Both
```

### Q: Do I still need spanmetrics?

**A:** **Optional** now! OpenLIT already provides token metrics directly.

But keep it for now - it provides additional call count and latency metrics that complement the data.

---

## Comparison: Single vs DUAL Mode

| Metric/Feature | OpenInference Only | OpenLIT Only | DUAL Mode |
|----------------|-------------------|--------------|-----------|
| Token metrics | Need spanmetrics | Direct | Direct |
| Detailed traces | Rich | Good | Rich |
| Cost tracking | No | Yes | Yes |
| VectorDB metrics | No | Yes | Yes |
| Custom metrics | Yes | Yes | Yes |
| Setup complexity | Medium | Low | Low |
| openai version | Unaffected | Downgrades to 1.109.1 | Downgrades to 1.109.1 |

---

## 📈 Real-World Benefits

### Scenario 1: Debugging Performance Issues
- **OpenInference traces:** See exactly where slowdown occurs
- **OpenLIT metrics:** Confirm if it's LLM latency or token volume
- **Custom metrics:** Check if graph extraction is the bottleneck

### Scenario 2: Cost Optimization
- **OpenLIT costs:** Track spend by model in Grafana
- **OpenLIT tokens:** Identify expensive queries
- **OpenInference traces:** Find unnecessary LLM calls in code

### Scenario 3: Production Monitoring
- **OpenLIT dashboard:** High-level LLM health (tokens/sec, cost/hour, errors)
- **Custom metrics:** RAG-specific KPIs (entities extracted, retrieval latency)
- **OpenInference traces:** Deep dive when issues occur

---

## 🚀 Migration Path

### If You're Currently Using OpenInference

```bash
# Just add OpenLIT!
pip install openlit
export OBSERVABILITY_BACKEND=both
# Restart - instant token metrics!
```

### If You're Currently Using OpenLIT

```bash
# OpenInference should already be installed
# Just enable both mode
export OBSERVABILITY_BACKEND=both
# Restart - get richer traces!
```

### If You're Starting Fresh

```bash
pip install openlit openinference-instrumentation-llama-index
export OBSERVABILITY_BACKEND=both
# Perfect from day 1!
```

---

## 📚 References

- [OpenLIT with OTEL Collector](https://docs.openlit.io/latest/sdk/destinations/otelcol) - "OpenLIT just becomes another OTLP producer"
- [OpenLIT + Prometheus + Jaeger](https://docs.openlit.io/latest/sdk/destinations/prometheus-jaeger)
- [Grafana LLM Observability Guide](https://grafana.com/blog/a-complete-guide-to-llm-observability-with-opentelemetry-and-grafana-cloud/)
- [OpenInference Semantic Conventions](https://arize-ai.github.io/openinference/spec/semantic_conventions.html)

---

## Summary

DUAL mode combines OpenInference traces with OpenLIT token/cost metrics. The trade-off is that OpenLIT downgrades `openai` to 1.109.1 — use a fresh virtual environment if you need this combination.

**DUAL mode provides:**

1. Token metrics (from OpenLIT)
2. Rich traces (from OpenInference)
3. Cost tracking (from OpenLIT)
4. Custom metrics (unchanged)
5. VectorDB operation metrics (from OpenLIT)

**To enable:**
```bash
pip install openlit
export OBSERVABILITY_BACKEND=both
# Restart app — check Prometheus for gen_ai_usage_*_tokens_total
```

---

**Status:** DUAL mode implemented and available.


