"""
Ingestion modules for Flexible GraphRAG.

This package contains modular ingestion logic for different data sources.
"""

from .factory import DataSourceFactory
from .manager import IngestionManager

__all__ = [
    "DataSourceFactory",
    "IngestionManager"
]
