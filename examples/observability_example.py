#!/usr/bin/env python3
"""
Example script demonstrating custom observability instrumentation
for Flexible GraphRAG
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure environment before imports
os.environ["ENABLE_OBSERVABILITY"] = "true"
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"

from observability import setup_observability, get_tracer, get_rag_metrics
from observability.custom_hooks import trace_retrieval, trace_llm_call

# Initialize observability
print("Initializing observability...")
setup_observability(
    service_name="example-rag-app",
    otlp_endpoint="http://localhost:4318",
    enable_instrumentation=True
)
print("Observability initialized!")
print()
print("Access dashboards at:")
print("  - Grafana:    http://localhost:3009 (admin/admin)")
print("  - Jaeger:     http://localhost:16686")
print("  - Prometheus: http://localhost:9090")
print()

# Get metrics instance
metrics = get_rag_metrics()


# Example 1: Using decorators for automatic tracing
@trace_retrieval
def retrieve_documents(query: str, top_k: int = 5):
    """Example retrieval function with automatic tracing"""
    print(f"Retrieving documents for query: {query}")
    # Simulate retrieval
    import time
    time.sleep(0.1)
    
    # Record metrics
    metrics.record_retrieval(
        latency_ms=100,
        num_documents=top_k,
        top_score=0.95,
        attributes={"index": "example-index", "query_length": len(query)}
    )
    
    return [f"Doc {i}" for i in range(top_k)]


@trace_llm_call(model_name="gpt-4o-mini", provider="openai")
def generate_response(context: str, query: str):
    """Example LLM generation with automatic tracing"""
    print(f"Generating response for: {query}")
    # Simulate LLM call
    import time
    time.sleep(0.5)
    
    # Record metrics
    metrics.record_llm_call(
        latency_ms=500,
        prompt_tokens=100,
        completion_tokens=50,
        attributes={"model": "gpt-4o-mini", "temperature": 0.1}
    )
    
    return f"Response based on: {context}"


# Example 2: Using manual spans
def custom_operation_with_span():
    """Example of manual span creation for custom operations"""
    tracer = get_tracer(__name__)
    
    with tracer.start_as_current_span("custom-preprocessing") as span:
        span.set_attribute("operation.type", "preprocessing")
        span.set_attribute("operation.input_size", 1024)
        
        print("Performing custom preprocessing...")
        import time
        time.sleep(0.2)
        
        span.set_attribute("operation.output_size", 512)
        span.set_attribute("operation.status", "success")


# Example 3: Error recording
def operation_with_error_handling():
    """Example of error tracking in observability"""
    try:
        print("Simulating operation that might fail...")
        # Simulate random failure
        import random
        if random.random() < 0.3:
            raise ValueError("Simulated error")
        
        print("Operation succeeded!")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        # Record error metric
        metrics.record_error(
            error_type="ValueError",
            attributes={"operation": "example", "error": str(e)}
        )
        raise


# Run examples
if __name__ == "__main__":
    print("Running observability examples...")
    print("=" * 60)
    print()
    
    # Example 1: Traced retrieval
    print("1. Retrieving documents (with automatic tracing)...")
    docs = retrieve_documents("What is RAG?", top_k=3)
    print(f"   Retrieved: {docs}")
    print()
    
    # Example 2: Traced LLM call
    print("2. Generating response (with automatic tracing)...")
    response = generate_response("RAG combines retrieval and generation", "What is RAG?")
    print(f"   Response: {response}")
    print()
    
    # Example 3: Custom span
    print("3. Running custom operation (with manual span)...")
    custom_operation_with_span()
    print()
    
    # Example 4: Error handling
    print("4. Testing error handling (might fail)...")
    try:
        operation_with_error_handling()
    except:
        pass
    print()
    
    print("=" * 60)
    print("Examples complete!")
    print()
    print("Check your dashboards to see:")
    print("  - Traces in Jaeger: http://localhost:16686")
    print("    (Look for service 'example-rag-app')")
    print()
    print("  - Metrics in Prometheus: http://localhost:9090")
    print("    (Try queries like: rag_retrieval_latency_ms)")
    print()
    print("  - Grafana dashboard: http://localhost:3009")
    print("    (Navigate to 'RAG Observability' folder)")
    print()

