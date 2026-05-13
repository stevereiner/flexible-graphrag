"""langchain.vector — LangChain vector store implementations.

Structure
---------
lc_vector_retriever     LCVectorRetriever (Layer 0, pure LC)
                        LangChainVectorStoreRetriever (Layer 1, LI wrapper)
vector_store_adapter    LangChainVectorAdapter (base)
retriever               LangChainVectorRetriever (LlamaIndex BaseRetriever)
adapters/
  qdrant_adapter        QdrantVectorAdapter
  neo4j_adapter         Neo4jVectorAdapter
  elasticsearch_adapter ElasticsearchVectorAdapter
  opensearch_adapter    OpenSearchVectorAdapter
  chroma_adapter        ChromaVectorAdapter
  milvus_adapter        MilvusVectorAdapter
  weaviate_adapter      WeaviateVectorAdapter
  pinecone_adapter      PineconeVectorAdapter
  postgres_adapter      PostgresVectorAdapter
  lancedb_adapter       LanceDBVectorAdapter
  factory               build_lc_vector_store
"""
from .lc_vector_retriever import LCVectorRetriever
from .li_vector_retriever import LangChainVectorStoreRetriever
from .vector_store_adapter import LangChainVectorAdapter
from .retriever import LangChainVectorRetriever
from .adapters.factory import build_lc_vector_store
from .adapters import (
    QdrantVectorAdapter,
    Neo4jVectorAdapter,
    ElasticsearchVectorAdapter,
    OpenSearchVectorAdapter,
    ChromaVectorAdapter,
    MilvusVectorAdapter,
    WeaviateVectorAdapter,
    PineconeVectorAdapter,
    PostgresVectorAdapter,
    LanceDBVectorAdapter,
)
from adapters.vector.vector_store_adapter import VectorStoreAdapter

__all__ = [
    # base
    "VectorStoreAdapter",
    "LangChainVectorAdapter",
    # per-backend adapters
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
    # retrievers (Layer 0 + Layer 1)
    "LCVectorRetriever",
    "LangChainVectorStoreRetriever",
    "LangChainVectorRetriever",
    # factory
    "build_lc_vector_store",
]
