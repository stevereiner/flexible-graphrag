"""
Processing modules for Flexible GraphRAG.

This package contains document processing, chunking, and KG extraction logic.
"""

from .document_processor import DocumentProcessor, get_parser_type_from_env
from .node_pipeline import build_ingestion_pipeline
from .kg_extractor import run_kg_extractors_on_nodes, count_extracted_entities_and_relations

__all__ = [
    "DocumentProcessor",
    "get_parser_type_from_env",
    "build_ingestion_pipeline",
    "count_extracted_entities_and_relations",
    "run_kg_extractors_on_nodes",
]
