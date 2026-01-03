"""
Core OpenTelemetry setup for Flexible GraphRAG
Supports two observability backends:
1. OpenInference (default) - Trace-focused, requires spanmetrics connector for token metrics
2. OpenLIT (optional) - Metrics + traces, includes token metrics out-of-the-box

To switch backends, set OBSERVABILITY_BACKEND environment variable:
- OBSERVABILITY_BACKEND=openinference (default)
- OBSERVABILITY_BACKEND=openlit (alternative with built-in token metrics)
"""

import os
import logging
from typing import Optional
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry import trace, metrics

try:
    from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
    OPENINFERENCE_AVAILABLE = True
except ImportError:
    OPENINFERENCE_AVAILABLE = False

try:
    from .telemetry_openlit import setup_observability_openlit, OPENLIT_AVAILABLE
except ImportError:
    OPENLIT_AVAILABLE = False
    setup_observability_openlit = None

logger = logging.getLogger(__name__)

# Global providers
_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None
_instrumentor: Optional['LlamaIndexInstrumentor'] = None

def setup_observability(
    service_name: str = "flexible-graphrag",
    otlp_endpoint: Optional[str] = None,
    enable_metrics: bool = True,
    enable_instrumentation: bool = True,
    service_version: str = "1.0.0",
    service_namespace: str = "llm-apps",
    backend: Optional[str] = None
) -> TracerProvider:
    """
    Initialize OpenTelemetry instrumentation for LlamaIndex
    
    Supports three modes:
    1. OpenInference only (default) - Captures traces, requires spanmetrics for token metrics
    2. OpenLIT only - Captures traces + metrics including tokens directly
    3. BOTH (recommended!) - OpenInference + OpenLIT as dual OTLP producers
    
    Args:
        service_name: Name of your service
        otlp_endpoint: OTLP collector endpoint (default: http://localhost:4318)
        enable_metrics: Enable Prometheus metrics export
        enable_instrumentation: Enable automatic LlamaIndex instrumentation
        service_version: Version of the service
        service_namespace: Namespace for the service
        backend: Backend mode ('openinference', 'openlit', 'both', default from env)
        
    Returns:
        TracerProvider instance
    """
    global _tracer_provider, _meter_provider, _instrumentor
    
    # Determine which backend to use
    if backend is None:
        backend = os.getenv("OBSERVABILITY_BACKEND", "openinference").lower()
    
    # Read configuration from environment if not provided
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    
    logger.info(f"🚀 Setting up observability with backend: {backend}")
    
    # Initialize OpenLIT if requested (or if mode is 'both')
    openlit_initialized = False
    if backend in ["openlit", "both"]:
        if OPENLIT_AVAILABLE and setup_observability_openlit is not None:
            logger.info("📡 Initializing OpenLIT as OTLP producer...")
            success = setup_observability_openlit(
                service_name=service_name,
                otlp_endpoint=otlp_endpoint,
                environment=os.getenv("DEPLOYMENT_ENV", "production"),
                service_version=service_version
            )
            if success:
                openlit_initialized = True
                logger.info("✅ OpenLIT active - token metrics enabled!")
                if backend == "openlit":
                    # OpenLIT-only mode, skip OpenInference setup
                    logger.info("   Mode: OpenLIT only (no OpenInference)")
                    return None
            else:
                logger.warning("⚠️ OpenLIT initialization failed")
                if backend == "openlit":
                    logger.warning("   Falling back to OpenInference")
        else:
            logger.warning("⚠️ OpenLIT not available (pip install openlit)")
            if backend == "openlit":
                logger.warning("   Falling back to OpenInference")
    
    # Continue with OpenInference setup (default, fallback, or dual mode)
    if backend == "both" and openlit_initialized:
        logger.info("📡 Initializing OpenInference as additional OTLP producer...")
        logger.info("   Mode: DUAL (OpenInference + OpenLIT)")
    else:
        logger.info("📡 Initializing OpenInference as OTLP producer...")
        logger.info("   Mode: OpenInference only")
    
    # Read configuration from environment if not provided
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    
    logger.info(f"Setting up observability for service: {service_name}")
    logger.info(f"OTLP endpoint: {otlp_endpoint}")
    
    # Create resource with service metadata
    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
        "service.namespace": service_namespace,
    })
    
    # Setup traces
    trace_exporter = OTLPSpanExporter(
        endpoint=f"{otlp_endpoint}/v1/traces",
        timeout=30
    )
    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(_tracer_provider)
    
    logger.info("Trace provider configured")
    
    # Setup metrics
    if enable_metrics:
        metrics_exporter = OTLPMetricExporter(
            endpoint=f"{otlp_endpoint}/v1/metrics",
            timeout=30
        )
        metric_reader = PeriodicExportingMetricReader(metrics_exporter)
        _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(_meter_provider)
        logger.info("Metrics provider configured")
    
    # Instrument LlamaIndex - MUST be called before any LlamaIndex operations
    if enable_instrumentation and OPENINFERENCE_AVAILABLE:
        try:
            _instrumentor = LlamaIndexInstrumentor()
            _instrumentor.instrument(tracer_provider=_tracer_provider)
            logger.info("✅ OpenInference instrumentation enabled")
        except Exception as e:
            logger.warning(f"Failed to instrument LlamaIndex: {e}")
    elif enable_instrumentation and not OPENINFERENCE_AVAILABLE:
        logger.warning("OpenInference instrumentation not available. Install: pip install openinference-instrumentation-llama-index")
    
    # Initialize RAG metrics early to ensure they're ready before first use
    try:
        from .metrics import get_rag_metrics
        get_rag_metrics()  # Creates the global instance
        logger.info("✅ Custom RAG metrics initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize RAG metrics: {e}")
    
    # Summary
    if backend == "both" and openlit_initialized:
        logger.info("🎉 Observability setup complete - DUAL MODE")
        logger.info("   📊 OpenLIT → Token metrics, costs, VectorDB metrics")
        logger.info("   📊 OpenInference → Detailed traces")
        logger.info("   📊 Custom metrics → Graph extraction, retrieval, etc.")
        logger.info("   🎯 Best of both worlds!")
    else:
        logger.info("🎉 Observability setup complete")
    
    return _tracer_provider


def get_tracer(name: str = __name__):
    """Get a tracer for custom instrumentation"""
    return trace.get_tracer(name)


def get_meter(name: str = __name__):
    """Get a meter for custom metrics"""
    return metrics.get_meter(name)


def shutdown_observability():
    """Shutdown observability providers gracefully"""
    global _tracer_provider, _meter_provider, _instrumentor
    
    logger.info("Shutting down observability...")
    
    if _instrumentor is not None:
        try:
            _instrumentor.uninstrument()
        except Exception as e:
            logger.warning(f"Error uninstrumenting LlamaIndex: {e}")
    
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down tracer provider: {e}")
    
    if _meter_provider is not None:
        try:
            _meter_provider.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down meter provider: {e}")
    
    logger.info("Observability shutdown complete")

