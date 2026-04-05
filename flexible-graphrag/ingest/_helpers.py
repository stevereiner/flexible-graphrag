"""
Shared helpers for ingest entry points.

Used by ingest_from_files, ingest_from_text, and ingest_from_source.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def _check_cancellation(processing_id: str) -> bool:
    """Return True if processing_id has been cancelled."""
    if processing_id:
        from backend import PROCESSING_STATUS
        return (
            processing_id in PROCESSING_STATUS and
            PROCESSING_STATUS[processing_id]["status"] == "cancelled"
        )
    return False


def _get_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def generate_completion_message(config, doc_count: int, skip_graph: bool = False) -> str:
    """Generate dynamic completion message based on enabled features.

    Args:
        config: AppSettings instance
        doc_count: Number of documents ingested
        skip_graph: If True, graph was skipped for this ingest
    """
    has_vector = str(config.vector_db) != "none"
    has_graph = str(config.graph_db) != "none" and config.enable_knowledge_graph and not skip_graph
    has_search = str(config.search_db) != "none"

    db_name_map = {
        "opensearch": "OpenSearch",
        "elasticsearch": "Elasticsearch",
        "qdrant": "Qdrant",
        "chroma": "Chroma",
        "pinecone": "Pinecone",
        "weaviate": "Weaviate",
        "milvus": "Milvus",
        "neo4j": "Neo4j",
        "ladybug": "Ladybug",
        "falkordb": "FalkorDB",
        "nebula": "NebulaGraph",
        "neptune": "Neptune",
        "memgraph": "Memgraph",
        "arcadedb": "ArcadeDB",
        "bm25": "BM25",
    }

    features = []
    if has_vector:
        vector_db = str(config.vector_db).lower()
        features.append(f"{db_name_map.get(vector_db, vector_db.title())} vector index")
    if has_search:
        search_db = str(config.search_db).lower()
        features.append(f"{db_name_map.get(search_db, search_db.title())} search")
    if has_graph:
        graph_db = str(config.graph_db).lower()
        features.append(f"{db_name_map.get(graph_db, graph_db.title())} knowledge graph")

    if features:
        if len(features) == 1:
            feature_text = features[0]
        elif len(features) == 2:
            feature_text = f"{features[0]} and {features[1]}"
        else:
            feature_text = f"{', '.join(features[:-1])}, and {features[-1]}"
        return f"Successfully ingested {doc_count} document(s)! {feature_text} ready."
    return f"Successfully ingested {doc_count} document(s)!"
