"""adapters.vector — VectorStoreAdapter ABC and build_vector_adapter factory."""
from .vector_store_adapter import VectorStoreAdapter, build_vector_adapter

__all__ = ["VectorStoreAdapter", "build_vector_adapter"]
