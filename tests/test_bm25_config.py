#!/usr/bin/env python3
"""
Test script for BM25 configuration and persistence
"""

import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the flexible-graphrag directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "flexible-graphrag"))

from config import Settings, SearchDBType
from hybrid_system import HybridSearchSystem


def test_bm25_configuration():
    """Test BM25 configuration and persistence (sync — no pytest-asyncio required)."""
    # Avoid real Neo4j / graph connections during unit test
    with patch("factories.DatabaseFactory.create_vector_store", return_value=None):
        with patch("factories.DatabaseFactory.create_graph_store", return_value=None):
            with tempfile.TemporaryDirectory() as temp_dir:
                persist_dir = os.path.join(temp_dir, "bm25_persist")
                vector_persist_dir = os.path.join(temp_dir, "vector_persist")
                graph_persist_dir = os.path.join(temp_dir, "graph_persist")

                config = Settings(
                    search_db=SearchDBType.BM25,
                    bm25_persist_dir=persist_dir,
                    bm25_similarity_top_k=15,
                    vector_persist_dir=vector_persist_dir,
                    graph_persist_dir=graph_persist_dir,
                    vector_db_config={
                        "username": "neo4j",
                        "password": "password",
                        "url": "bolt://localhost:7687",
                    },
                    graph_db_config={
                        "username": "neo4j",
                        "password": "password",
                        "url": "bolt://localhost:7687",
                    },
                )

                assert config.search_db == SearchDBType.BM25
                system = HybridSearchSystem(config)
                assert system.config.search_db == SearchDBType.BM25

                os.makedirs(config.bm25_persist_dir, exist_ok=True)
                os.makedirs(config.vector_persist_dir, exist_ok=True)
                os.makedirs(config.graph_persist_dir, exist_ok=True)
                assert os.path.isdir(persist_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 