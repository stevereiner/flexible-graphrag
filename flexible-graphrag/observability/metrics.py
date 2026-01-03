"""
RAG-specific metrics definitions using OpenTelemetry
"""

import logging
from typing import Optional
from opentelemetry import metrics

logger = logging.getLogger(__name__)


class RAGMetrics:
    """Centralized metrics for RAG operations"""
    
    def __init__(self, meter_name: str = "flexible-graphrag"):
        """Initialize RAG metrics"""
        self.meter = metrics.get_meter(meter_name)
        
        # Retrieval metrics
        self.retrieval_latency = self.meter.create_histogram(
            "rag.retrieval.latency_ms",
            description="Document retrieval latency in milliseconds"
        )
        
        self.retrieval_documents = self.meter.create_histogram(
            "rag.retrieval.num_documents",
            description="Number of documents retrieved"
        )
        
        self.retrieval_score = self.meter.create_histogram(
            "rag.retrieval.relevance_score",
            description="Relevance scores of retrieved documents"
        )
        
        # LLM metrics
        self.generation_latency = self.meter.create_histogram(
            "llm.generation.latency_ms",
            description="LLM response generation time in milliseconds"
        )
        
        self.tokens_generated = self.meter.create_counter(
            "llm.tokens.generated",
            description="Total tokens generated"
        )
        
        self.tokens_prompt = self.meter.create_counter(
            "llm.tokens.prompt",
            description="Total prompt tokens"
        )
        
        self.llm_requests = self.meter.create_counter(
            "llm.requests.total",
            description="Total LLM requests"
        )
        
        # Graph extraction metrics
        self.graph_extraction_latency = self.meter.create_histogram(
            "rag.graph.extraction_latency_ms",
            description="Knowledge graph extraction time in milliseconds"
        )
        
        self.entities_extracted = self.meter.create_counter(
            "rag.graph.entities_extracted",
            description="Total entities extracted from documents"
        )
        
        self.relations_extracted = self.meter.create_counter(
            "rag.graph.relations_extracted",
            description="Total relations/relationships extracted from documents"
        )
        
        # Document processing metrics
        self.document_processing_latency = self.meter.create_histogram(
            "rag.document.processing_latency_ms",
            description="Document processing time (Docling/LlamaParse) in milliseconds"
        )
        
        self.documents_processed = self.meter.create_counter(
            "rag.document.processed_total",
            description="Total documents processed"
        )
        
        self.chunks_created = self.meter.create_counter(
            "rag.document.chunks_created",
            description="Total chunks created from documents"
        )
        
        # Vector indexing metrics
        self.vector_indexing_latency = self.meter.create_histogram(
            "rag.vector.indexing_latency_ms",
            description="Vector indexing time in milliseconds"
        )
        
        self.vectors_indexed = self.meter.create_counter(
            "rag.vector.indexed_total",
            description="Total vectors indexed"
        )
        
        # Error metrics
        self.errors_total = self.meter.create_counter(
            "rag.errors.total",
            description="Total errors in RAG pipeline"
        )
        
        self.errors_by_type = self.meter.create_counter(
            "rag.errors.by_type",
            description="Errors categorized by type"
        )
        
        logger.info("RAG metrics initialized")
    
    def record_retrieval(self, latency_ms: float, num_documents: int, 
                        top_score: Optional[float] = None, attributes: Optional[dict] = None):
        """Record retrieval metrics"""
        attrs = attributes or {}
        self.retrieval_latency.record(latency_ms, attrs)
        self.retrieval_documents.record(num_documents, attrs)
        if top_score is not None:
            self.retrieval_score.record(top_score, attrs)
    
    def record_llm_call(self, latency_ms: float, prompt_tokens: int = 0, 
                       completion_tokens: int = 0, attributes: Optional[dict] = None):
        """Record LLM call metrics"""
        attrs = attributes or {}
        self.generation_latency.record(latency_ms, attrs)
        self.tokens_prompt.add(prompt_tokens, attrs)
        self.tokens_generated.add(completion_tokens, attrs)
        self.llm_requests.add(1, attrs)
    
    def record_graph_extraction(self, latency_ms: float, num_entities: int = 0,
                               num_relations: int = 0, attributes: Optional[dict] = None):
        """Record graph extraction metrics (timing and entity/relation counts)"""
        attrs = attributes or {}
        self.graph_extraction_latency.record(latency_ms, attrs)
        if num_entities > 0:
            self.entities_extracted.add(num_entities, attrs)
        if num_relations > 0:
            self.relations_extracted.add(num_relations, attrs)
    
    def record_document_processing(self, latency_ms: float, num_chunks: int = 0,
                                  attributes: Optional[dict] = None):
        """Record document processing metrics"""
        attrs = attributes or {}
        self.document_processing_latency.record(latency_ms, attrs)
        self.documents_processed.add(1, attrs)
        self.chunks_created.add(num_chunks, attrs)
    
    def record_vector_indexing(self, latency_ms: float, num_vectors: int = 0,
                              attributes: Optional[dict] = None):
        """Record vector indexing metrics"""
        attrs = attributes or {}
        self.vector_indexing_latency.record(latency_ms, attrs)
        self.vectors_indexed.add(num_vectors, attrs)
    
    def record_error(self, error_type: str, attributes: Optional[dict] = None):
        """Record error metrics"""
        attrs = attributes or {}
        self.errors_total.add(1, attrs)
        self.errors_by_type.add(1, {**attrs, "error_type": error_type})


# Global metrics instance
_rag_metrics: Optional[RAGMetrics] = None


def get_rag_metrics() -> RAGMetrics:
    """Get or create the global RAG metrics instance"""
    global _rag_metrics
    if _rag_metrics is None:
        _rag_metrics = RAGMetrics()
    return _rag_metrics

