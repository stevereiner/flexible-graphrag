"""
Ingestion entry points for Flexible GraphRAG.

  ingest_from_files  — ingest_documents(file_paths)
  ingest_from_text   — ingest_text(content)
  ingest_from_source — ingest_source_documents(documents)  pre-loaded from a data source
"""

from .factory import DataSourceFactory
from .manager import IngestionManager
from .ingest_from_files import ingest_documents
from .ingest_from_text import ingest_text
from .ingest_from_source import ingest_source_documents
from ._helpers import generate_completion_message

__all__ = [
    "DataSourceFactory",
    "IngestionManager",
    "ingest_documents",
    "ingest_text",
    "ingest_source_documents",
    "generate_completion_message",
]
