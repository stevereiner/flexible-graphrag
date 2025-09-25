#!/usr/bin/env python3
"""
Basic tests to verify test structure and imports work correctly
"""

import sys
import os
from pathlib import Path

# Add the flexible-graphrag directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "flexible-graphrag"))

def test_imports():
    """Test that all required modules can be imported"""
    
    # Test config imports
    from config import Settings, SearchDBType, VectorDBType, GraphDBType
    assert Settings is not None
    assert SearchDBType.BM25 == "bm25"
    assert VectorDBType.NEO4J == "neo4j"
    assert VectorDBType.CHROMA == "chroma"
    assert VectorDBType.MILVUS == "milvus"
    assert VectorDBType.WEAVIATE == "weaviate"
    assert VectorDBType.PINECONE == "pinecone"
    assert VectorDBType.POSTGRES == "postgres"
    assert VectorDBType.LANCEDB == "lancedb"
    assert GraphDBType.NEO4J == "neo4j"
    assert GraphDBType.FALKORDB == "falkordb"
    assert GraphDBType.MEMGRAPH == "memgraph"
    assert GraphDBType.NEBULA == "nebula"
    assert GraphDBType.NEPTUNE == "neptune"
    assert GraphDBType.NEPTUNE_ANALYTICS == "neptune_analytics"
    
    # Test factory imports
    from factories import DatabaseFactory, LLMFactory
    assert DatabaseFactory is not None
    assert LLMFactory is not None
    
    # Test hybrid system imports
    from hybrid_system import HybridSearchSystem
    assert HybridSearchSystem is not None

def test_basic_configuration():
    """Test basic configuration creation"""
    from config import Settings, SearchDBType
    
    config = Settings()
    assert config.search_db == SearchDBType.BM25
    assert config.bm25_similarity_top_k == 10

def test_search_db_types():
    """Test all search database types"""
    from config import SearchDBType
    
    # Test all search types exist
    assert SearchDBType.BM25 == "bm25"
    assert SearchDBType.ELASTICSEARCH == "elasticsearch"
    assert SearchDBType.OPENSEARCH == "opensearch"
    
    # Test they are different
    assert SearchDBType.BM25 != SearchDBType.ELASTICSEARCH
    assert SearchDBType.BM25 != SearchDBType.OPENSEARCH
    assert SearchDBType.ELASTICSEARCH != SearchDBType.OPENSEARCH

def test_persistence_config():
    """Test persistence configuration options"""
    from config import Settings
    
    config = Settings(
        bm25_persist_dir="/tmp/bm25",
        vector_persist_dir="/tmp/vector",
        graph_persist_dir="/tmp/graph"
    )
    
    assert config.bm25_persist_dir == "/tmp/bm25"
    assert config.vector_persist_dir == "/tmp/vector"
    assert config.graph_persist_dir == "/tmp/graph"

def test_falkordb_factory():
    """Test FalkorDB graph store factory creation"""
    from config import GraphDBType
    from factories import DatabaseFactory
    
    # Test that FalkorDB enum exists
    assert GraphDBType.FALKORDB == "falkordb"
    
    # Test factory method exists and handles FalkorDB type
    # Note: We don't actually create the store since it requires a running FalkorDB instance
    # Just verify the enum and factory method can handle the type
    try:
        # This should not raise an "Unsupported graph database" error for FALKORDB
        # It might raise other errors (like connection errors) which is expected without a running instance
        config = {"url": "falkor://localhost:6379"}
        DatabaseFactory.create_graph_store(GraphDBType.FALKORDB, config)
    except ValueError as e:
        if "Unsupported graph database" in str(e):
            raise AssertionError("FalkorDB should be supported by factory")
        # Other errors (like connection errors) are expected without running FalkorDB
        pass
    except Exception:
        # Connection or import errors are expected without running FalkorDB instance
        pass

def test_modular_data_sources():
    """Test that modular data sources can be imported and created"""
    from ingest.factory import DataSourceFactory
    from sources.base import BaseDataSource
    from sources.cmis import CmisSource
    from sources.alfresco import AlfrescoSource
    
    # Test factory exists and has the expected sources
    factory = DataSourceFactory()
    supported_types = factory.get_supported_types()
    
    assert "cmis" in supported_types
    assert "alfresco" in supported_types
    assert "filesystem" in supported_types
    
    # Test that CMIS and Alfresco sources inherit from BaseDataSource
    assert issubclass(CmisSource, BaseDataSource)
    assert issubclass(AlfrescoSource, BaseDataSource)
    
    # Test that both sources have the required methods
    assert hasattr(CmisSource, 'get_documents')
    assert hasattr(CmisSource, 'get_documents_with_progress')
    assert hasattr(CmisSource, 'validate_config')
    
    assert hasattr(AlfrescoSource, 'get_documents')
    assert hasattr(AlfrescoSource, 'get_documents_with_progress')
    assert hasattr(AlfrescoSource, 'validate_config')

def test_old_sources_still_exist():
    """Test that old data sources in sources.py still exist for backward compatibility"""
    # Import from the legacy sources.py file
    import importlib.util
    import os
    sources_file = os.path.join(os.path.dirname(__file__), '..', 'flexible-graphrag', 'sources.py')
    spec = importlib.util.spec_from_file_location("legacy_sources", sources_file)
    legacy_sources = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy_sources)
    
    # Test that old sources still exist (for backward compatibility)
    FileSystemSource = legacy_sources.FileSystemSource
    CmisSource = legacy_sources.CmisSource
    AlfrescoSource = legacy_sources.AlfrescoSource
    
    # Test basic methods exist
    assert hasattr(FileSystemSource, 'list_files')
    assert hasattr(CmisSource, 'list_files')
    assert hasattr(AlfrescoSource, 'list_files')

def test_arcadedb_factory():
    """Test ArcadeDB graph store factory creation"""
    from config import GraphDBType
    from factories import DatabaseFactory
    
    # Test that ArcadeDB enum exists
    assert GraphDBType.ARCADEDB == "arcadedb"
    
    # Test factory method exists and handles ArcadeDB type
    # Note: We don't actually create the store since it requires a running ArcadeDB instance
    # Just verify the enum and factory method can handle the type
    try:
        # This should not raise an "Unsupported graph database" error for ARCADEDB
        # It might raise other errors (like connection errors) which is expected without a running instance
        config = {
            "host": "localhost",
            "port": 2480,
            "username": "root",
            "password": "playwithdata",
            "database": "flexible_graphrag",
            "include_basic_schema": True
        }
        DatabaseFactory.create_graph_store(GraphDBType.ARCADEDB, config)
    except ValueError as e:
        if "Unsupported graph database" in str(e):
            raise AssertionError("ArcadeDB should be supported by factory")
        # Other errors (like connection errors) are expected without running ArcadeDB
        pass
    except Exception:
        # Connection or import errors are expected without running ArcadeDB instance
        pass

def test_memgraph_factory():
    """Test MemGraph graph store factory creation"""
    from config import GraphDBType
    from factories import DatabaseFactory
    
    # Test that MemGraph enum exists
    assert GraphDBType.MEMGRAPH == "memgraph"
    
    # Test factory method exists and handles MemGraph type
    try:
        config = {
            "url": "bolt://localhost:7687",
            "username": "",
            "password": ""
        }
        DatabaseFactory.create_graph_store(GraphDBType.MEMGRAPH, config)
    except ValueError as e:
        if "Unsupported graph database" in str(e):
            raise AssertionError("MemGraph should be supported by factory")
        # Other errors (like connection errors) are expected without running MemGraph
        pass
    except Exception:
        # Connection or import errors are expected without running MemGraph instance
        pass

def test_nebula_factory():
    """Test NebulaGraph graph store factory creation"""
    from config import GraphDBType
    from factories import DatabaseFactory
    
    # Test that Nebula enum exists
    assert GraphDBType.NEBULA == "nebula"
    
    # Test factory method exists and handles Nebula type
    try:
        config = {
            "space_name": "flexible_graphrag",
            "address": "localhost",
            "port": 9669,
            "username": "root",
            "password": "nebula"
        }
        DatabaseFactory.create_graph_store(GraphDBType.NEBULA, config)
    except ValueError as e:
        if "Unsupported graph database" in str(e):
            raise AssertionError("NebulaGraph should be supported by factory")
        # Other errors (like connection errors) are expected without running Nebula
        pass
    except Exception:
        # Connection or import errors are expected without running Nebula instance
        pass

def test_neptune_factory():
    """Test Neptune graph store factory creation"""
    from config import GraphDBType
    from factories import DatabaseFactory
    
    # Test that Neptune enum exists
    assert GraphDBType.NEPTUNE == "neptune"
    
    # Test factory method exists and handles Neptune type
    try:
        config = {
            "endpoint": "test-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com",
            "port": 8182,
            "region": "us-east-1",
            "access_key": "test_access_key",
            "secret_key": "test_secret_key"
        }
        DatabaseFactory.create_graph_store(GraphDBType.NEPTUNE, config)
    except ValueError as e:
        if "Unsupported graph database" in str(e):
            raise AssertionError("Neptune should be supported by factory")
        # Other errors (like connection errors) are expected without running Neptune
        pass
    except Exception:
        # Connection or import errors are expected without running Neptune instance
        pass

def test_neptune_factory_validation():
    """Test Neptune factory parameter validation"""
    from config import GraphDBType
    from factories import DatabaseFactory
    
    # Test missing endpoint
    try:
        config = {
            "port": 8182,
            "region": "us-east-1",
            "access_key": "test_access_key",
            "secret_key": "test_secret_key"
        }
        DatabaseFactory.create_graph_store(GraphDBType.NEPTUNE, config)
        assert False, "Should have raised ValueError for missing endpoint"
    except ValueError as e:
        assert "Neptune endpoint is required" in str(e)
    
    # Test missing credentials
    try:
        config = {
            "endpoint": "test-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com",
            "port": 8182,
            "region": "us-east-1"
        }
        DatabaseFactory.create_graph_store(GraphDBType.NEPTUNE, config)
        assert False, "Should have raised ValueError for missing credentials"
    except ValueError as e:
        assert "Neptune access_key and secret_key are required" in str(e)

def test_neptune_analytics_factory():
    """Test Neptune Analytics graph store factory creation"""
    from config import GraphDBType
    from factories import DatabaseFactory
    
    # Test that Neptune Analytics enum exists
    assert GraphDBType.NEPTUNE_ANALYTICS == "neptune_analytics"
    
    # Test factory method exists and handles Neptune Analytics type
    try:
        config = {
            "graph_identifier": "test-graph-id",
            "region": "us-east-1"
        }
        DatabaseFactory.create_graph_store(GraphDBType.NEPTUNE_ANALYTICS, config)
    except ValueError as e:
        if "Unsupported graph database" in str(e):
            raise AssertionError("Neptune Analytics should be supported by factory")
        # Other errors (like connection errors) are expected without running Neptune Analytics
        pass
    except Exception:
        # Connection or import errors are expected without running Neptune Analytics instance
        pass

def test_neptune_analytics_factory_validation():
    """Test Neptune Analytics factory parameter validation"""
    from config import GraphDBType
    from factories import DatabaseFactory
    
    # Test missing graph_identifier
    try:
        config = {
            "region": "us-east-1"
        }
        DatabaseFactory.create_graph_store(GraphDBType.NEPTUNE_ANALYTICS, config)
        assert False, "Should have raised ValueError for missing graph_identifier"
    except ValueError as e:
        assert "Neptune Analytics graph_identifier is required" in str(e)

def test_chroma_factory():
    """Test Chroma vector store factory creation"""
    from config import VectorDBType
    from factories import DatabaseFactory
    
    # Test that Chroma enum exists
    assert VectorDBType.CHROMA == "chroma"
    
    # Test factory method exists and handles Chroma type
    try:
        config = {
            "persist_directory": "./test_chroma_db",
            "collection_name": "test_collection"
        }
        DatabaseFactory.create_vector_store(VectorDBType.CHROMA, config)
    except ValueError as e:
        if "Unsupported vector database" in str(e):
            raise AssertionError("Chroma should be supported by factory")
        # Other errors (like import errors) are expected without chromadb installed
        pass
    except Exception:
        # Import or other errors are expected without chromadb package
        pass

def test_milvus_factory():
    """Test Milvus vector store factory creation"""
    from config import VectorDBType
    from factories import DatabaseFactory
    
    # Test that Milvus enum exists
    assert VectorDBType.MILVUS == "milvus"
    
    # Test factory method exists and handles Milvus type
    try:
        config = {
            "host": "localhost",
            "port": 19530,
            "collection_name": "test_collection",
            "dim": 1536
        }
        DatabaseFactory.create_vector_store(VectorDBType.MILVUS, config)
    except ValueError as e:
        if "Unsupported vector database" in str(e):
            raise AssertionError("Milvus should be supported by factory")
        # Other errors (like connection errors) are expected without running Milvus
        pass
    except Exception:
        # Connection or import errors are expected without running Milvus instance
        pass

def test_weaviate_factory():
    """Test Weaviate vector store factory creation"""
    from config import VectorDBType
    from factories import DatabaseFactory
    
    # Test that Weaviate enum exists
    assert VectorDBType.WEAVIATE == "weaviate"
    
    # Test factory method exists and handles Weaviate type
    try:
        config = {
            "url": "http://localhost:8080",
            "class_name": "TestClass"
        }
        DatabaseFactory.create_vector_store(VectorDBType.WEAVIATE, config)
    except ValueError as e:
        if "Unsupported vector database" in str(e):
            raise AssertionError("Weaviate should be supported by factory")
        # Other errors (like connection errors) are expected without running Weaviate
        pass
    except Exception:
        # Connection or import errors are expected without running Weaviate instance
        pass

def test_pinecone_factory():
    """Test Pinecone vector store factory creation"""
    from config import VectorDBType
    from factories import DatabaseFactory
    
    # Test that Pinecone enum exists
    assert VectorDBType.PINECONE == "pinecone"
    
    # Test factory method exists and handles Pinecone type
    try:
        config = {
            "api_key": "test-api-key",
            "environment": "us-east1-gcp",
            "index_name": "test-index",
            "dim": 1536
        }
        DatabaseFactory.create_vector_store(VectorDBType.PINECONE, config)
    except ValueError as e:
        if "Unsupported vector database" in str(e):
            raise AssertionError("Pinecone should be supported by factory")
        # Other errors (like API errors) are expected with test credentials
        pass
    except Exception:
        # API or import errors are expected without valid Pinecone credentials
        pass

def test_postgres_factory():
    """Test PostgreSQL vector store factory creation"""
    from config import VectorDBType
    from factories import DatabaseFactory
    
    # Test that PostgreSQL enum exists
    assert VectorDBType.POSTGRES == "postgres"
    
    # Test factory method exists and handles PostgreSQL type
    try:
        config = {
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "username": "postgres",
            "password": "password",
            "table_name": "test_vectors",
            "embed_dim": 1536
        }
        DatabaseFactory.create_vector_store(VectorDBType.POSTGRES, config)
    except ValueError as e:
        if "Unsupported vector database" in str(e):
            raise AssertionError("PostgreSQL should be supported by factory")
        # Other errors (like connection errors) are expected without running PostgreSQL
        pass
    except Exception:
        # Connection or import errors are expected without running PostgreSQL instance
        pass

def test_lancedb_factory():
    """Test LanceDB vector store factory creation"""
    from config import VectorDBType
    from factories import DatabaseFactory
    
    # Test that LanceDB enum exists
    assert VectorDBType.LANCEDB == "lancedb"
    
    # Test factory method exists and handles LanceDB type
    try:
        config = {
            "uri": "./test_lancedb",
            "table_name": "test_table",
            "vector_column_name": "vector",
            "text_column_name": "text"
        }
        DatabaseFactory.create_vector_store(VectorDBType.LANCEDB, config)
    except ValueError as e:
        if "Unsupported vector database" in str(e):
            raise AssertionError("LanceDB should be supported by factory")
        # Other errors (like import errors) are expected without lancedb installed
        pass
    except Exception:
        # Import or other errors are expected without lancedb package
        pass

if __name__ == "__main__":
    # Run basic tests
    test_imports()
    test_basic_configuration()
    test_search_db_types()
    test_persistence_config()
    test_falkordb_factory()
    test_modular_data_sources()
    test_old_sources_still_exist()
    test_arcadedb_factory()
    test_memgraph_factory()
    test_nebula_factory()
    test_neptune_factory()
    test_neptune_factory_validation()
    test_neptune_analytics_factory()
    test_neptune_analytics_factory_validation()
    test_chroma_factory()
    test_milvus_factory()
    test_weaviate_factory()
    test_pinecone_factory()
    test_postgres_factory()
    test_lancedb_factory()
    print("All basic tests passed!") 