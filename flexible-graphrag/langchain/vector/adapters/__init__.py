"""
langchain.vector.adapters
=========================

One module per LangChain vector store backend.  Each module defines an
adapter class that wraps the underlying LangChain VectorStore and exposes
the :class:`~adapters.vector.vector_store_adapter.VectorStoreAdapter` interface.

Modules
-------
qdrant_adapter         QdrantVectorAdapter
neo4j_adapter          Neo4jVectorAdapter
elasticsearch_adapter  ElasticsearchVectorAdapter
opensearch_adapter     OpenSearchVectorAdapter
chroma_adapter         ChromaVectorAdapter
milvus_adapter         MilvusVectorAdapter
weaviate_adapter       WeaviateVectorAdapter
pinecone_adapter       PineconeVectorAdapter
postgres_adapter       PostgresVectorAdapter
lancedb_adapter        LanceDBVectorAdapter
factory                build_lc_vector_store
"""
from .qdrant_adapter import QdrantVectorAdapter
from .neo4j_adapter import Neo4jVectorAdapter
from .elasticsearch_adapter import ElasticsearchVectorAdapter
from .opensearch_adapter import OpenSearchVectorAdapter
from .chroma_adapter import ChromaVectorAdapter
from .milvus_adapter import MilvusVectorAdapter
from .weaviate_adapter import WeaviateVectorAdapter
from .pinecone_adapter import PineconeVectorAdapter
from .postgres_adapter import PostgresVectorAdapter
from .lancedb_adapter import LanceDBVectorAdapter
from .factory import build_lc_vector_store

__all__ = [
    "QdrantVectorAdapter",
    "Neo4jVectorAdapter",
    "ElasticsearchVectorAdapter",
    "OpenSearchVectorAdapter",
    "ChromaVectorAdapter",
    "MilvusVectorAdapter",
    "WeaviateVectorAdapter",
    "PineconeVectorAdapter",
    "PostgresVectorAdapter",
    "LanceDBVectorAdapter",
    "build_lc_vector_store",
]
