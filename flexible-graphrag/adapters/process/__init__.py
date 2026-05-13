"""adapters.process — ABCs and factories for chunking and KG extraction."""
from .chunker_adapter import ChunkerAdapter, build_chunker_adapter
from .kg_extractor_adapter import KGExtractorAdapter, build_kg_extractor_adapter

__all__ = [
    "ChunkerAdapter",
    "build_chunker_adapter",
    "KGExtractorAdapter",
    "build_kg_extractor_adapter",
]
