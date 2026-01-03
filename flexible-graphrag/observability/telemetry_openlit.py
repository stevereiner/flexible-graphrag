"""
Alternative OpenTelemetry setup using OpenLIT for comprehensive LLM observability.
This is an ALTERNATIVE to the default OpenInference setup in telemetry_setup.py.

To use OpenLIT instead of OpenInference:
1. pip install openlit
2. Set OBSERVABILITY_BACKEND=openlit in .env
3. Restart the application

OpenLIT provides:
- Automatic token metrics (gen_ai_usage_input_tokens_total, gen_ai_usage_output_tokens_total)
- LLM request metrics (gen_ai_total_requests, gen_ai_request_duration_seconds)
- Cost tracking (gen_ai_total_cost)
- VectorDB metrics (db_total_requests)
- Pre-built Grafana dashboards

References:
- https://docs.openlit.io/latest/sdk/integrations/llama-index
- https://grafana.com/blog/a-complete-guide-to-llm-observability-with-opentelemetry-and-grafana-cloud/
- https://github.com/openlit/openlit
"""

import os
import logging
from typing import Optional

try:
    import openlit
    OPENLIT_AVAILABLE = True
except ImportError:
    OPENLIT_AVAILABLE = False

logger = logging.getLogger(__name__)

def setup_observability_openlit(
    service_name: str = "flexible-graphrag",
    otlp_endpoint: Optional[str] = None,
    environment: str = "production",
    service_version: str = "1.0.0",
) -> bool:
    """
    Initialize OpenLIT for comprehensive LLM observability.
    
    OpenLIT auto-instruments LlamaIndex and exports:
    - Traces to Jaeger (via OTLP)
    - Metrics to Prometheus (via OTLP)
    
    Metrics provided:
    - gen_ai_total_requests{gen_ai_request_model="gpt-4"}
    - gen_ai_usage_input_tokens_total{gen_ai_request_model="gpt-4"}
    - gen_ai_usage_output_tokens_total{gen_ai_request_model="gpt-4"}
    - gen_ai_total_cost{gen_ai_request_model="gpt-4"}
    - gen_ai_request_duration_seconds_bucket{gen_ai_request_model="gpt-4"}
    - db_total_requests{db_system="neo4j"}
    
    Args:
        service_name: Name of your service (default: flexible-graphrag)
        otlp_endpoint: OTLP collector endpoint (default: http://localhost:4318)
        environment: Deployment environment (e.g., production, development)
        service_version: Version of the service
        
    Returns:
        bool: True if OpenLIT was successfully initialized
    """
    if not OPENLIT_AVAILABLE:
        logger.error("OpenLIT not installed. Install with: pip install openlit")
        return False
    
    # Read configuration from environment if not provided
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    
    logger.info(f"Setting up OpenLIT observability for service: {service_name}")
    logger.info(f"OTLP endpoint: {otlp_endpoint}")
    logger.info(f"Environment: {environment}")
    
    try:
        # Initialize OpenLIT
        # This auto-instruments LlamaIndex and sends telemetry to OTLP endpoint
        openlit.init(
            otlp_endpoint=otlp_endpoint,
            environment=environment,
            application_name=service_name,
            # Optional: disable specific features if needed
            # disable_metrics=False,
            # disable_tracing=False,
        )
        
        logger.info("✅ OpenLIT instrumentation enabled")
        logger.info("   - LlamaIndex auto-instrumented")
        logger.info("   - Token metrics enabled (gen_ai_usage_*_tokens_total)")
        logger.info("   - Cost tracking enabled (gen_ai_total_cost)")
        logger.info("   - VectorDB metrics enabled (db_total_requests)")
        
        # Initialize custom RAG metrics (for graph extraction counts, etc.)
        try:
            from .metrics import get_rag_metrics
            get_rag_metrics()  # Creates the global instance
            logger.info("   - Custom RAG metrics initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize custom RAG metrics: {e}")
        
        logger.info("🎉 OpenLIT observability setup complete!")
        logger.info("   Next: Import pre-built Grafana dashboard from:")
        logger.info("   https://docs.openlit.io/latest/sdk/destinations/prometheus-jaeger#3-import-the-pre-built-dashboard")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenLIT: {e}")
        return False


def get_openlit_dashboard_info():
    """
    Returns information about the OpenLIT pre-built Grafana dashboard.
    """
    return {
        "dashboard_url": "https://docs.openlit.io/latest/sdk/destinations/prometheus-jaeger#3-import-the-pre-built-dashboard",
        "metrics": [
            "gen_ai_total_requests - Total LLM requests",
            "gen_ai_usage_input_tokens_total - Prompt tokens",
            "gen_ai_usage_output_tokens_total - Completion tokens",
            "gen_ai_total_cost - LLM API costs",
            "gen_ai_request_duration_seconds - Latency histograms",
            "db_total_requests - VectorDB operations",
        ],
        "grafana_queries": {
            "tokens_per_sec": "sum(rate(gen_ai_usage_input_tokens_total[5m])) + sum(rate(gen_ai_usage_output_tokens_total[5m]))",
            "prompt_tokens_per_sec": "sum(rate(gen_ai_usage_input_tokens_total[5m]))",
            "completion_tokens_per_sec": "sum(rate(gen_ai_usage_output_tokens_total[5m]))",
            "requests_per_sec": "sum(rate(gen_ai_total_requests[5m]))",
            "p95_latency": "histogram_quantile(0.95, sum(rate(gen_ai_request_duration_seconds_bucket[5m])) by (le))",
            "cost_per_hour": "sum(rate(gen_ai_total_cost[1h])) * 3600",
        }
    }


# Example usage for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test OpenLIT setup
    success = setup_observability_openlit(
        service_name="flexible-graphrag-test",
        otlp_endpoint="http://localhost:4318",
        environment="development"
    )
    
    if success:
        print("\n✅ OpenLIT is ready!")
        print("\nDashboard info:")
        info = get_openlit_dashboard_info()
        print(f"  Dashboard: {info['dashboard_url']}")
        print("\nAvailable metrics:")
        for metric in info['metrics']:
            print(f"  - {metric}")
        print("\nExample Grafana queries:")
        for name, query in info['grafana_queries'].items():
            print(f"  {name}: {query}")
    else:
        print("\n❌ OpenLIT setup failed")

