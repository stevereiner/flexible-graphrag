"""
Shared helpers for ingest entry points.

Used by ingest_from_files, ingest_from_text, and ingest_from_source.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def make_kg_extractor(system):
    """Create a KG extractor from system config (shared across all ingest paths)."""
    return system.schema_manager.create_extractor(
        system.llm,
        llm_provider=system.config.llm_provider,
        extractor_type=system.config.kg_extractor_type,
    )


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
    has_graph = str(config.pg_graph_db) != "none" and config.enable_knowledge_graph and not skip_graph
    has_search = str(config.search_db) != "none"
    has_rdf_graph = (
        str(getattr(config, "rdf_graph_db", "none")).lower() not in ("none", "")
        and config.enable_knowledge_graph
        and not skip_graph
    )

    db_name_map = {
        "opensearch": "OpenSearch",
        "elasticsearch": "Elasticsearch",
        "qdrant": "Qdrant",
        "chroma": "Chroma",
        "pinecone": "Pinecone",
        "weaviate": "Weaviate",
        "milvus": "Milvus",
        "neo4j": "Neo4j",
        "ladybug": "LadybugDB",
        "falkordb": "FalkorDB",
        "nebula": "NebulaGraph",
        "neptune": "Neptune",
        "neptune_analytics": "Neptune Analytics",
        "memgraph": "Memgraph",
        "arcadedb": "ArcadeDB",
        "arangodb": "ArangoDB",
        "apache_age": "Apache AGE",
        "cosmos_gremlin": "Azure Cosmos DB for Gremlin",
        "spanner": "Spanner Graph",
        "hugegraph": "HugeGraph",
        "tigergraph": "TigerGraph",
        "surrealdb": "SurrealDB",
        "fuseki": "Apache Jena Fuseki",
        "oxigraph": "Oxigraph",
        "graphdb": "Ontotext GraphDB",
        "bm25": "BM25",
    }

    def _db_label(key: str) -> str:
        return db_name_map.get(str(key).lower(), str(key).title())

    features = []
    if has_vector:
        features.append(f"{_db_label(config.vector_db)} vector")
    if has_search:
        features.append(f"{_db_label(config.search_db)} search")
    if has_graph:
        features.append(f"{_db_label(config.pg_graph_db)} property graph")
    if has_rdf_graph:
        features.append(f"{_db_label(config.rdf_graph_db)} rdf graph")

    if features:
        if len(features) == 1:
            feature_text = features[0]
        elif len(features) == 2:
            feature_text = f"{features[0]} and {features[1]}"
        else:
            feature_text = f"{', '.join(features[:-1])}, and {features[-1]}"
        return f"Successfully ingested {doc_count} document(s)! {feature_text} ready."
    return f"Successfully ingested {doc_count} document(s)!"
