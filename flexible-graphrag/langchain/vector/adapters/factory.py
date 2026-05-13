"""Factory for LangChain vector store adapters.

Routes a ``VectorDBType`` + config dict to the correct
:class:`~langchain.vector.vector_store_adapter.LangChainVectorAdapter` subclass
and returns the **adapter** instance (not just the underlying raw store).

Each adapter subclass (QdrantVectorAdapter, etc.) overrides ``delete()`` with
backend-specific logic, so the adapter must be kept intact for deletion to work.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def build_lc_vector_store(db_type, config: Dict[str, Any], app_config=None):
    """Instantiate a LangChain vector store adapter for the given *db_type*.

    Parameters
    ----------
    db_type:
        A :class:`~config.VectorDBType` value.
    config:
        Backend-specific connection dict.
    app_config:
        Optional ``AppSettings`` object; used to build the embedding model.

    Returns
    -------
    :class:`~langchain.vector.vector_store_adapter.LangChainVectorAdapter` subclass
    instance.  The adapter exposes ``.get_store()`` (raw LC store), ``.delete()``,
    and ``.is_langchain()``.  Callers should use the adapter directly — do NOT
    call ``.get_store()`` and discard the wrapper, as that loses ``delete()`` overrides.
    """
    from config import VectorDBType
    from langchain.llm.embedding_factory import build_lc_embedding, get_lc_embedding_dimension

    lc_embedding = build_lc_embedding(app_config) if app_config else None

    # Pre-compute the embedding dimension so adapters that need to auto-create
    # their backing store (e.g. Qdrant) don't have to make an extra embed_query call.
    embed_dim = get_lc_embedding_dimension(app_config) if app_config else 0
    qdrant_config = {**config, "vector_size": embed_dim} if embed_dim else config

    if db_type == VectorDBType.QDRANT:
        from langchain.vector.adapters.qdrant_adapter import QdrantVectorAdapter
        return QdrantVectorAdapter(qdrant_config, embedding=lc_embedding)

    if db_type == VectorDBType.NEO4J:
        from langchain.vector.adapters.neo4j_adapter import Neo4jVectorAdapter
        return Neo4jVectorAdapter(config, embedding=lc_embedding)

    if db_type == VectorDBType.ELASTICSEARCH:
        from langchain.vector.adapters.elasticsearch_adapter import ElasticsearchVectorAdapter
        return ElasticsearchVectorAdapter(config, embedding=lc_embedding)

    if db_type == VectorDBType.OPENSEARCH:
        from langchain.vector.adapters.opensearch_adapter import OpenSearchVectorAdapter
        return OpenSearchVectorAdapter(config, embedding=lc_embedding)

    if db_type == VectorDBType.CHROMA:
        from langchain.vector.adapters.chroma_adapter import ChromaVectorAdapter
        return ChromaVectorAdapter(config, embedding=lc_embedding)

    if db_type == VectorDBType.MILVUS:
        from langchain.vector.adapters.milvus_adapter import MilvusVectorAdapter
        return MilvusVectorAdapter(config, embedding=lc_embedding)

    if db_type == VectorDBType.WEAVIATE:
        from langchain.vector.adapters.weaviate_adapter import WeaviateVectorAdapter
        return WeaviateVectorAdapter(config, embedding=lc_embedding)

    if db_type == VectorDBType.PINECONE:
        from langchain.vector.adapters.pinecone_adapter import PineconeVectorAdapter
        return PineconeVectorAdapter(config, embedding=lc_embedding)

    if db_type == VectorDBType.POSTGRES:
        from langchain.vector.adapters.postgres_adapter import PostgresVectorAdapter
        return PostgresVectorAdapter(config, embedding=lc_embedding)

    if db_type == VectorDBType.LANCEDB:
        from langchain.vector.adapters.lancedb_adapter import LanceDBVectorAdapter
        return LanceDBVectorAdapter(config, embedding=lc_embedding)

    raise NotImplementedError(
        f"LangChain vector adapter not implemented for db_type='{db_type}'. "
        "Use vector_backend='llamaindex' for this store type."
    )


__all__ = ["build_lc_vector_store"]
