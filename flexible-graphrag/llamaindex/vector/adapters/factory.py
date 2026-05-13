"""llamaindex.vector.adapters.factory — dispatch to per-backend adapter classes."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from config import VectorDBType

logger = logging.getLogger(__name__)


def create_vector_store(db_type: VectorDBType, config: Dict[str, Any], embed_dim: Optional[int] = None):
    """Instantiate the right :class:`LlamaIndexVectorAdapter` subclass for *db_type*
    and return it. Returns ``None`` for ``VectorDBType.NONE``."""
    if db_type == VectorDBType.NONE:
        logger.info("Vector search disabled - no vector store created")
        return None

    if db_type == VectorDBType.QDRANT:
        from llamaindex.vector.adapters.qdrant_adapter import LlamaIndexQdrantAdapter
        return LlamaIndexQdrantAdapter(config, embed_dim)

    if db_type == VectorDBType.NEO4J:
        from llamaindex.vector.adapters.neo4j_adapter import LlamaIndexNeo4jVectorAdapter
        return LlamaIndexNeo4jVectorAdapter(config, embed_dim)

    if db_type == VectorDBType.ELASTICSEARCH:
        from llamaindex.vector.adapters.elasticsearch_adapter import LlamaIndexElasticsearchVectorAdapter
        return LlamaIndexElasticsearchVectorAdapter(config, embed_dim)

    if db_type == VectorDBType.OPENSEARCH:
        from llamaindex.vector.adapters.opensearch_adapter import LlamaIndexOpenSearchVectorAdapter
        return LlamaIndexOpenSearchVectorAdapter(config, embed_dim)

    if db_type == VectorDBType.CHROMA:
        from llamaindex.vector.adapters.chroma_adapter import LlamaIndexChromaAdapter
        return LlamaIndexChromaAdapter(config, embed_dim)

    if db_type == VectorDBType.MILVUS:
        from llamaindex.vector.adapters.milvus_adapter import LlamaIndexMilvusAdapter
        return LlamaIndexMilvusAdapter(config, embed_dim)

    if db_type == VectorDBType.WEAVIATE:
        from llamaindex.vector.adapters.weaviate_adapter import LlamaIndexWeaviateAdapter
        return LlamaIndexWeaviateAdapter(config, embed_dim)

    if db_type == VectorDBType.PINECONE:
        from llamaindex.vector.adapters.pinecone_adapter import LlamaIndexPineconeAdapter
        return LlamaIndexPineconeAdapter(config, embed_dim)

    if db_type == VectorDBType.POSTGRES:
        from llamaindex.vector.adapters.postgres_adapter import LlamaIndexPostgresVectorAdapter
        return LlamaIndexPostgresVectorAdapter(config, embed_dim)

    if db_type == VectorDBType.LANCEDB:
        from llamaindex.vector.adapters.lancedb_adapter import LlamaIndexLanceDBAdapter
        return LlamaIndexLanceDBAdapter(config, embed_dim)

    raise ValueError(f"Unsupported vector database: {db_type}")
