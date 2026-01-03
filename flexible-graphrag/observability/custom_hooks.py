"""
Custom instrumentation hooks and decorators for RAG operations
"""

import time
import logging
from functools import wraps
from typing import Any, Callable
from opentelemetry import trace

logger = logging.getLogger(__name__)

def get_tracer():
    """Get the tracer for custom spans"""
    return trace.get_tracer(__name__)


def trace_retrieval(func: Callable) -> Callable:
    """
    Decorator to trace document retrieval with custom attributes
    
    Usage:
        @trace_retrieval
        def retrieve_documents(query: str, top_k: int = 5):
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        tracer = get_tracer()
        with tracer.start_as_current_span("rag.retrieval") as span:
            start = time.time()
            
            # Add function metadata
            span.set_attribute("retrieval.method", func.__name__)
            if args:
                span.set_attribute("retrieval.query", str(args[0])[:200])  # First 200 chars
            if 'top_k' in kwargs:
                span.set_attribute("retrieval.top_k", kwargs['top_k'])
            
            try:
                # Execute retrieval
                results = func(*args, **kwargs)
                
                # Record metrics
                latency_ms = (time.time() - start) * 1000
                span.set_attribute("retrieval.latency_ms", latency_ms)
                
                # Add result metadata
                if results:
                    if isinstance(results, list):
                        span.set_attribute("retrieval.num_documents", len(results))
                        if hasattr(results[0], 'score'):
                            span.set_attribute("retrieval.top_score", results[0].score)
                        if hasattr(results[0], 'metadata'):
                            source = results[0].metadata.get('source', 'unknown')
                            span.set_attribute("retrieval.source", source)
                
                span.set_attribute("retrieval.status", "success")
                return results
                
            except Exception as e:
                span.set_attribute("retrieval.status", "error")
                span.set_attribute("retrieval.error", str(e))
                span.record_exception(e)
                raise
    
    return wrapper


def trace_llm_call(model_name: str = None, provider: str = None):
    """
    Decorator to trace LLM calls with token counting
    
    Usage:
        @trace_llm_call(model_name="gpt-4o-mini", provider="openai")
        def generate_response(context: str, query: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span("rag.llm_call") as span:
                # Add LLM metadata
                if model_name:
                    span.set_attribute("llm.model", model_name)
                if provider:
                    span.set_attribute("llm.provider", provider)
                span.set_attribute("llm.method", func.__name__)
                
                start = time.time()
                
                try:
                    # Execute LLM call
                    response = func(*args, **kwargs)
                    
                    # Record latency
                    latency_ms = (time.time() - start) * 1000
                    span.set_attribute("llm.latency_ms", latency_ms)
                    
                    # Record token usage if available
                    if hasattr(response, 'metadata'):
                        metadata = response.metadata
                        if 'tokens_used' in metadata:
                            span.set_attribute("llm.tokens_total", metadata['tokens_used'])
                        if 'prompt_tokens' in metadata:
                            span.set_attribute("llm.tokens_prompt", metadata['prompt_tokens'])
                        if 'completion_tokens' in metadata:
                            span.set_attribute("llm.tokens_completion", metadata['completion_tokens'])
                    
                    span.set_attribute("llm.status", "success")
                    return response
                    
                except Exception as e:
                    span.set_attribute("llm.status", "error")
                    span.set_attribute("llm.error", str(e))
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator


def trace_graph_extraction(func: Callable) -> Callable:
    """
    Decorator to trace knowledge graph extraction
    
    Usage:
        @trace_graph_extraction
        def extract_entities_and_relations(documents):
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        tracer = get_tracer()
        with tracer.start_as_current_span("rag.graph_extraction") as span:
            start = time.time()
            
            span.set_attribute("extraction.method", func.__name__)
            
            # Track document count if available
            if args and hasattr(args[0], '__len__'):
                span.set_attribute("extraction.num_documents", len(args[0]))
            
            try:
                # Execute extraction
                result = func(*args, **kwargs)
                
                # Record metrics
                latency_ms = (time.time() - start) * 1000
                span.set_attribute("extraction.latency_ms", latency_ms)
                
                # Track extraction results if available
                if hasattr(result, 'entities'):
                    span.set_attribute("extraction.num_entities", len(result.entities))
                if hasattr(result, 'relations'):
                    span.set_attribute("extraction.num_relations", len(result.relations))
                
                span.set_attribute("extraction.status", "success")
                return result
                
            except Exception as e:
                span.set_attribute("extraction.status", "error")
                span.set_attribute("extraction.error", str(e))
                span.record_exception(e)
                raise
    
    return wrapper


def trace_document_processing(func: Callable) -> Callable:
    """
    Decorator to trace document processing (Docling/LlamaParse)
    
    Usage:
        @trace_document_processing
        async def process_documents(file_paths):
            ...
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        tracer = get_tracer()
        with tracer.start_as_current_span("rag.document_processing") as span:
            start = time.time()
            
            span.set_attribute("processing.method", func.__name__)
            
            # Track file count if available
            if args and hasattr(args[0], '__len__'):
                span.set_attribute("processing.num_files", len(args[0]))
            
            try:
                # Execute processing
                result = await func(*args, **kwargs)
                
                # Record metrics
                latency_ms = (time.time() - start) * 1000
                span.set_attribute("processing.latency_ms", latency_ms)
                
                # Track processing results
                if isinstance(result, list):
                    span.set_attribute("processing.num_chunks", len(result))
                
                span.set_attribute("processing.status", "success")
                return result
                
            except Exception as e:
                span.set_attribute("processing.status", "error")
                span.set_attribute("processing.error", str(e))
                span.record_exception(e)
                raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        tracer = get_tracer()
        with tracer.start_as_current_span("rag.document_processing") as span:
            start = time.time()
            
            span.set_attribute("processing.method", func.__name__)
            
            # Track file count if available
            if args and hasattr(args[0], '__len__'):
                span.set_attribute("processing.num_files", len(args[0]))
            
            try:
                # Execute processing
                result = func(*args, **kwargs)
                
                # Record metrics
                latency_ms = (time.time() - start) * 1000
                span.set_attribute("processing.latency_ms", latency_ms)
                
                # Track processing results
                if isinstance(result, list):
                    span.set_attribute("processing.num_chunks", len(result))
                
                span.set_attribute("processing.status", "success")
                return result
                
            except Exception as e:
                span.set_attribute("processing.status", "error")
                span.set_attribute("processing.error", str(e))
                span.record_exception(e)
                raise
    
    # Return appropriate wrapper based on whether function is async
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper

