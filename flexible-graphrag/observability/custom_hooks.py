"""
Custom instrumentation hooks and decorators for RAG operations.

All decorators are framework-agnostic: they work for both LlamaIndex and LangChain
by using duck-typing to extract span attributes from whichever result shape is present.

Usage with framework tag:
    @trace_retrieval                             # LlamaIndex (default)
    @trace_retrieval(framework="langchain")      # LangChain

    @trace_llm_call(model_name="gpt-4o-mini", provider="openai")
    @trace_llm_call(model_name="gpt-4o-mini", provider="openai", framework="langchain")

    @trace_graph_extraction                      # LlamaIndex (default)
    @trace_graph_extraction(framework="langchain")

    @trace_document_processing                   # async or sync, either framework
"""

import asyncio
import time
import logging
from functools import wraps
from typing import Any, Callable, Optional

from opentelemetry import trace

logger = logging.getLogger(__name__)


def get_tracer():
    """Get the tracer for custom spans"""
    return trace.get_tracer(__name__)


# ---------------------------------------------------------------------------
# Internal helpers — framework-neutral result inspection
# ---------------------------------------------------------------------------

def _retrieval_result_attrs(results) -> dict:
    """
    Extract span attributes from a retrieval result list.

    Handles both:
    - LlamaIndex NodeWithScore: .score, .metadata (or .node.metadata)
    - LangChain Document: .page_content, .metadata  (no .score)
    """
    attrs = {}
    if not results or not isinstance(results, list):
        return attrs

    attrs["retrieval.num_documents"] = len(results)
    first = results[0]

    # Score — LlamaIndex NodeWithScore has .score
    if hasattr(first, "score") and first.score is not None:
        attrs["retrieval.top_score"] = float(first.score)

    # Metadata — LlamaIndex may nest it under .node, LangChain has it directly
    meta = (
        getattr(getattr(first, "node", first), "metadata", None)
        or getattr(first, "metadata", None)
        or {}
    )
    source = meta.get("source") or meta.get("file_name") or meta.get("file_path")
    if source:
        attrs["retrieval.source"] = str(source)[:200]

    return attrs


def _llm_token_attrs(response) -> dict:
    """
    Extract token-count span attributes from an LLM response.

    Handles both:
    - LlamaIndex Response: .metadata with 'prompt_tokens', 'completion_tokens', 'tokens_used'
    - LangChain AIMessage:  .usage_metadata with 'input_tokens', 'output_tokens', 'total_tokens'
    """
    attrs = {}
    if response is None:
        return attrs

    # LangChain AIMessage / BaseChatModel response
    um = getattr(response, "usage_metadata", None)
    if um and isinstance(um, dict):
        if "input_tokens" in um:
            attrs["llm.tokens_prompt"] = um["input_tokens"]
        if "output_tokens" in um:
            attrs["llm.tokens_completion"] = um["output_tokens"]
        if "total_tokens" in um:
            attrs["llm.tokens_total"] = um["total_tokens"]
        elif "input_tokens" in um and "output_tokens" in um:
            attrs["llm.tokens_total"] = um["input_tokens"] + um["output_tokens"]
        return attrs

    # LlamaIndex response / completion object
    meta = getattr(response, "metadata", None)
    if meta and isinstance(meta, dict):
        if "tokens_used" in meta:
            attrs["llm.tokens_total"] = meta["tokens_used"]
        if "prompt_tokens" in meta:
            attrs["llm.tokens_prompt"] = meta["prompt_tokens"]
        if "completion_tokens" in meta:
            attrs["llm.tokens_completion"] = meta["completion_tokens"]

    return attrs


def _graph_extraction_attrs(result) -> dict:
    """
    Extract span attributes from a graph extraction result.

    Handles both:
    - LlamaIndex: result.entities, result.relations
    - LangChain:  list of GraphDocument with .nodes, .relationships
    """
    attrs = {}
    if result is None:
        return attrs

    # LlamaIndex extractor output
    if hasattr(result, "entities"):
        attrs["extraction.num_entities"] = len(result.entities)
    if hasattr(result, "relations"):
        attrs["extraction.num_relations"] = len(result.relations)

    # LangChain LLMGraphTransformer returns List[GraphDocument]
    if isinstance(result, list) and result:
        first = result[0]
        if hasattr(first, "nodes") and hasattr(first, "relationships"):
            nodes = sum(len(getattr(d, "nodes", [])) for d in result)
            rels = sum(len(getattr(d, "relationships", [])) for d in result)
            attrs["extraction.num_entities"] = nodes
            attrs["extraction.num_relations"] = rels

    return attrs


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def trace_retrieval(func: Optional[Callable] = None, *, framework: str = "llamaindex"):
    """
    Decorator to trace document retrieval with custom attributes.

    Works both with and without arguments:
        @trace_retrieval
        @trace_retrieval(framework="langchain")

    Span name: rag.retrieval
    Attributes: genai.framework, retrieval.method, retrieval.query,
                retrieval.top_k, retrieval.latency_ms, retrieval.num_documents,
                retrieval.top_score, retrieval.source, retrieval.status
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span("rag.retrieval") as span:
                span.set_attribute("genai.framework", framework)
                span.set_attribute("retrieval.method", fn.__name__)

                if args:
                    span.set_attribute("retrieval.query", str(args[0])[:200])
                if "top_k" in kwargs:
                    span.set_attribute("retrieval.top_k", kwargs["top_k"])

                start = time.time()
                try:
                    results = fn(*args, **kwargs)
                    span.set_attribute("retrieval.latency_ms", (time.time() - start) * 1000)
                    for k, v in _retrieval_result_attrs(results).items():
                        span.set_attribute(k, v)
                    span.set_attribute("retrieval.status", "success")
                    return results
                except Exception as e:
                    span.set_attribute("retrieval.status", "error")
                    span.set_attribute("retrieval.error", str(e))
                    span.record_exception(e)
                    raise

        return wrapper

    # Support both @trace_retrieval and @trace_retrieval(framework="langchain")
    if func is not None:
        return decorator(func)
    return decorator


def trace_llm_call(model_name: Optional[str] = None, provider: Optional[str] = None,
                   framework: str = "llamaindex"):
    """
    Decorator to trace LLM calls with token counting.

    Works for both LlamaIndex and LangChain responses.

    Usage:
        @trace_llm_call(model_name="gpt-4o-mini", provider="openai")
        @trace_llm_call(model_name="gpt-4o-mini", provider="openai", framework="langchain")

    Span name: rag.llm_call
    Attributes: genai.framework, llm.model, llm.provider, llm.method,
                llm.latency_ms, llm.tokens_prompt, llm.tokens_completion,
                llm.tokens_total, llm.status
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span("rag.llm_call") as span:
                span.set_attribute("genai.framework", framework)
                span.set_attribute("llm.method", func.__name__)
                if model_name:
                    span.set_attribute("llm.model", model_name)
                if provider:
                    span.set_attribute("llm.provider", provider)

                start = time.time()
                try:
                    response = func(*args, **kwargs)
                    span.set_attribute("llm.latency_ms", (time.time() - start) * 1000)
                    for k, v in _llm_token_attrs(response).items():
                        span.set_attribute(k, v)
                    span.set_attribute("llm.status", "success")
                    return response
                except Exception as e:
                    span.set_attribute("llm.status", "error")
                    span.set_attribute("llm.error", str(e))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


def trace_graph_extraction(func: Optional[Callable] = None, *, framework: str = "llamaindex"):
    """
    Decorator to trace knowledge graph extraction.

    Works both with and without arguments:
        @trace_graph_extraction
        @trace_graph_extraction(framework="langchain")

    Handles LlamaIndex extractor output (.entities / .relations) and
    LangChain LLMGraphTransformer output (List[GraphDocument]).

    Span name: rag.graph_extraction
    Attributes: genai.framework, extraction.method, extraction.num_documents,
                extraction.latency_ms, extraction.num_entities,
                extraction.num_relations, extraction.status
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span("rag.graph_extraction") as span:
                span.set_attribute("genai.framework", framework)
                span.set_attribute("extraction.method", fn.__name__)

                if args and hasattr(args[0], "__len__"):
                    span.set_attribute("extraction.num_documents", len(args[0]))

                start = time.time()
                try:
                    result = fn(*args, **kwargs)
                    span.set_attribute("extraction.latency_ms", (time.time() - start) * 1000)
                    for k, v in _graph_extraction_attrs(result).items():
                        span.set_attribute(k, v)
                    span.set_attribute("extraction.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("extraction.status", "error")
                    span.set_attribute("extraction.error", str(e))
                    span.record_exception(e)
                    raise

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def trace_document_processing(func: Optional[Callable] = None, *, framework: str = "llamaindex"):
    """
    Decorator to trace document processing (Docling/LlamaParse/LangChain loaders).

    Works both with and without arguments, and handles async and sync functions:
        @trace_document_processing
        @trace_document_processing(framework="langchain")

    Span name: rag.document_processing
    Attributes: genai.framework, processing.method, processing.num_files,
                processing.latency_ms, processing.num_chunks, processing.status
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span("rag.document_processing") as span:
                span.set_attribute("genai.framework", framework)
                span.set_attribute("processing.method", fn.__name__)
                if args and hasattr(args[0], "__len__"):
                    span.set_attribute("processing.num_files", len(args[0]))

                start = time.time()
                try:
                    result = await fn(*args, **kwargs)
                    span.set_attribute("processing.latency_ms", (time.time() - start) * 1000)
                    if isinstance(result, list):
                        span.set_attribute("processing.num_chunks", len(result))
                    span.set_attribute("processing.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("processing.status", "error")
                    span.set_attribute("processing.error", str(e))
                    span.record_exception(e)
                    raise

        @wraps(fn)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span("rag.document_processing") as span:
                span.set_attribute("genai.framework", framework)
                span.set_attribute("processing.method", fn.__name__)
                if args and hasattr(args[0], "__len__"):
                    span.set_attribute("processing.num_files", len(args[0]))

                start = time.time()
                try:
                    result = fn(*args, **kwargs)
                    span.set_attribute("processing.latency_ms", (time.time() - start) * 1000)
                    if isinstance(result, list):
                        span.set_attribute("processing.num_chunks", len(result))
                    span.set_attribute("processing.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("processing.status", "error")
                    span.set_attribute("processing.error", str(e))
                    span.record_exception(e)
                    raise

        return async_wrapper if asyncio.iscoroutinefunction(fn) else sync_wrapper

    # Support both @trace_document_processing and @trace_document_processing(framework=...)
    if func is not None:
        return decorator(func)
    return decorator
