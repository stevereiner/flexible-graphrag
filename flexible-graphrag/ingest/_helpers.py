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


async def warmup_hybrid_retriever(system) -> None:
    """Prime retrievers after ingest so the first client search is not empty.

    Some backends (Qdrant gRPC, FalkorDB, SurrealDB LC graph) pay a cold-start
    cost on the first ``aretrieve`` call.  A lightweight warmup query here
    avoids flaky first-search failures in integration tests and after ingest.
    """
    from llama_index.core.schema import QueryBundle
    from retriever_setup import setup_hybrid_retriever

    if not system.hybrid_retriever:
        setup_hybrid_retriever(system)
    if not system.hybrid_retriever:
        return
    try:
        await system.hybrid_retriever.aretrieve(QueryBundle(query_str="warmup"))
        logger.debug("Hybrid retriever warmup query completed")
    except Exception as exc:
        logger.debug("Hybrid retriever warmup failed (non-fatal): %s", exc)


DB_NAME_MAP = {
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


def db_label(key: str) -> str:
    """Display name of a configured store type, e.g. "neo4j" -> "Neo4j"."""
    return DB_NAME_MAP.get(str(key).lower(), str(key).title())


def store_labels(config, targets) -> list:
    """The configured stores behind delete targets ("vector", "search", "graph"), named like the
    completion message: ["Qdrant vector", "Elasticsearch search", "Neo4j property graph",
    "Ontotext GraphDB rdf graph"]. A store set to "none" is left out."""
    def on(name: str) -> bool:
        value = getattr(config, name, None)
        return str(getattr(value, "value", value) or "none").lower() not in ("none", "")
    targets = set(targets)
    vdb = str(getattr(getattr(config, "vector_db", None), "value", getattr(config, "vector_db", "")))
    sdb = str(getattr(getattr(config, "search_db", None), "value", getattr(config, "search_db", "")))
    labels = []
    if {"vector", "search"} <= targets and vdb.lower() == sdb.lower() == "opensearch":
        labels.append("OpenSearch hybrid search+vector")
    else:
        if "vector" in targets and on("vector_db"):
            labels.append(f"{db_label(vdb)} vector")
        if "search" in targets and on("search_db"):
            labels.append(f"{db_label(sdb)} search")
    if "graph" in targets:
        if on("pg_graph_db"):
            labels.append(f"{db_label(getattr(config, 'pg_graph_db'))} property graph")
        if on("rdf_graph_db"):
            labels.append(f"{db_label(getattr(config, 'rdf_graph_db'))} rdf graph")
    return labels


def generate_completion_message(config, doc_count: int, skip_graph: bool = False) -> str:
    """Generate dynamic completion message based on enabled features.

    Args:
        config: AppSettings instance
        doc_count: Number of documents ingested
        skip_graph: If True, graph was skipped for this ingest
    """
    has_vector = str(config.vector_db) != "none"
    has_graph = str(config.pg_graph_db) != "none" and config.enable_knowledge_graph and not skip_graph
    # OpenSearch hybrid mode: both VECTOR_DB and SEARCH_DB are opensearch.
    # The search index is never written to; one vector index serves both KNN + BM25.
    # Show a combined "hybrid search+vector" label instead of two separate entries.
    _os_hybrid = (
        str(config.vector_db).lower() == "opensearch"
        and str(config.search_db).lower() == "opensearch"
    )
    has_search = str(config.search_db) != "none" and not _os_hybrid
    has_rdf_graph = (
        str(getattr(config, "rdf_graph_db", "none")).lower() not in ("none", "")
        and config.enable_knowledge_graph
        and not skip_graph
    )


    _db_label = db_label

    features = []
    if _os_hybrid:
        features.append("OpenSearch hybrid search+vector")
    elif has_vector:
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
