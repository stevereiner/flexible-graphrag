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
    assert GraphDBType.NEO4J == "neo4j"
    assert GraphDBType.FALKORDB == "falkordb"
    
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

if __name__ == "__main__":
    # Run basic tests
    test_imports()
    test_basic_configuration()
    test_search_db_types()
    test_persistence_config()
    test_falkordb_factory()
    test_modular_data_sources()
    test_old_sources_still_exist()
    print("All basic tests passed!") 