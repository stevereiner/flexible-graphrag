"""
Observability module for Flexible GraphRAG
Provides OpenTelemetry-based instrumentation for LlamaIndex RAG applications
"""

from .telemetry_setup import setup_observability, get_tracer, get_meter
from .custom_hooks import (
    trace_retrieval,
    trace_llm_call,
    trace_graph_extraction,
    trace_document_processing
)
from .metrics import RAGMetrics

__all__ = [
    'setup_observability',
    'get_tracer',
    'get_meter',
    'trace_retrieval',
    'trace_llm_call',
    'trace_graph_extraction',
    'trace_document_processing',
    'RAGMetrics'
]

