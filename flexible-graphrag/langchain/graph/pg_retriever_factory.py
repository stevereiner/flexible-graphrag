"""
LangChain Property Graph Retriever Factory

Builds TextToGraphQueryRetriever and GraphEntityVectorRetriever from an AppSettings config object.
Extracted from HybridSearchSystem to keep hybrid_system.py lean.

Public API:
    build_langchain_pg_retriever(config) -> TextToGraphQueryRetriever | None
    build_langchain_pg_vector_retriever(config) -> GraphEntityVectorRetriever | None
    build_pg_neighborhood_retriever(config) -> GraphNeighborhoodRetriever | None
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from config import AppSettings

from langchain.llm.llm_factory import get_langchain_llm  # noqa: F401  re-exported for compat

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def build_langchain_pg_retriever(config: "AppSettings"):
    """Create a LangChain property-graph QA retriever for fusion.

    Activated when ``USE_LANGCHAIN_PG=true``.  The store type is set via
    ``LANGCHAIN_PG_STORE_TYPE``.

    Returns:
        TextToGraphQueryRetriever or None if not configured / failed.
    """
    use_langchain_pg = getattr(config, "use_langchain_pg", False)
    pg_store_type = getattr(config, "langchain_pg_store_type", None)

    if not use_langchain_pg or not pg_store_type:
        return None

    try:
        from langchain.graph.langchain_retriever_wrapper import TextToGraphQueryRetriever
        from langchain.graph.langchain_adapters.property_graph_adapters import create_property_graph_adapter

        pg_store_type = pg_store_type.lower()

        _FACTORY_STORES = {
            "arangodb", "neptune", "neptune_analytics",
            "apache_age", "cosmos_gremlin", "spanner",
        }
        _COMMUNITY_STORES = {
            "neo4j", "memgraph", "falkordb",
            "hugegraph", "nebula", "tigergraph", "arcadedb",
        }

        if pg_store_type in _FACTORY_STORES:
            adapter = create_property_graph_adapter(
                pg_store_type,
                build_pg_adapter_config(config, pg_store_type),
            )
            lc_graph = adapter.get_graph()
        elif pg_store_type in _COMMUNITY_STORES:
            lc_graph = create_community_pg_graph(config, pg_store_type)
        else:
            logger.warning(
                "Unsupported LANGCHAIN_PG_STORE_TYPE for LangChain PG retrieval: %s",
                pg_store_type,
            )
            return None

        retriever = TextToGraphQueryRetriever(
            langchain_graph=lc_graph,
            llm=get_langchain_llm(config),
            top_k=getattr(config, "rdf_retrieval_top_k", 5),
            include_intermediate_steps=True,
        )
        logger.info("Created LangChain PG retriever for store type: %s", pg_store_type)
        return retriever

    except ImportError as e:
        logger.warning("LangChain PG retrieval not available: %s", e)
        return None
    except Exception as e:
        logger.error("Failed to create LangChain PG retriever: %s", e, exc_info=True)
        return None




def build_langchain_pg_vector_retriever(config: "AppSettings", embed_model: Any = None):
    """Create a vector-similarity retriever backed by a Neo4j (or compatible)
    vector index, wrapped as a LlamaIndex BaseRetriever for fusion.

    Activated when ``USE_LANGCHAIN_PG=true`` and ``LANGCHAIN_PG_VECTOR_SEARCH=true``.
    Currently supports Neo4j; other stores can be added here as needed.

    The Neo4j ``entity`` vector index (on ``__Entity__[embedding]``) is created
    automatically by LlamaIndex during ingestion and is available even when
    only the LangChain PG path is used for retrieval.

    Args:
        config:      AppSettings instance.
        embed_model: LlamaIndex embedding model.  If None, tries to create one
                     from config (needed so Neo4jVector can embed queries).

    Returns:
        GraphEntityVectorRetriever or None.
    """
    use_langchain_pg = getattr(config, "use_langchain_pg", False)
    pg_vector_search = getattr(config, "langchain_pg_vector_search", False)
    # Use LANGCHAIN_PG_STORE_TYPE if set; fall back to GRAPH_DB only when it's a
    # real graph store (not "none" — which means no ingestion, not a store type).
    _graph_db = str(getattr(config, "graph_db", "") or "").lower()
    pg_store_type = (
        getattr(config, "langchain_pg_store_type", None) or (
            _graph_db if _graph_db not in ("", "none") else ""
        )
    ).lower()

    # Allow activation independently of use_langchain_pg — the entity vector index
    # exists in Neo4j as long as GRAPH_DB=neo4j ingestion ran, regardless of whether
    # the LangChain Cypher QA chain (USE_LANGCHAIN_PG) is active.
    if not pg_vector_search:
        return None

    if not pg_store_type:
        logger.debug("LangChain PG vector search: no store type resolved — set LANGCHAIN_PG_STORE_TYPE")
        return None

    if pg_store_type != "neo4j":
        logger.debug(
            "LangChain PG vector search is currently only supported for neo4j "
            "(store_type=%s) — skipping", pg_store_type,
        )
        return None

    try:
        from langchain.graph.neo4j_vector_retriever import GraphEntityVectorRetriever

        try:
            from langchain_neo4j import Neo4jVector
        except ImportError:
            from langchain_community.vectorstores import Neo4jVector

        graph_config: Dict[str, Any] = getattr(config, "graph_config", {}) or {}
        url      = graph_config.get("url", "bolt://localhost:7687")
        username = graph_config.get("username", "neo4j")
        password = graph_config.get("password", "password")
        database = graph_config.get("database", "neo4j")

        # Vector index name and node label/property — defaults match what
        # LlamaIndex creates during PropertyGraphIndex ingestion.
        index_name = getattr(config, "langchain_pg_vector_index", "entity")
        node_label = getattr(config, "langchain_pg_vector_node_label", "__Entity__")
        embedding_node_property = getattr(
            config, "langchain_pg_vector_embedding_property", "embedding"
        )
        text_node_property = getattr(
            config, "langchain_pg_vector_text_property", "name"
        )
        top_k = getattr(config, "rdf_retrieval_top_k", 5)

        # Build a LangChain embedding wrapper around the LlamaIndex embed_model
        # so Neo4jVector can embed queries using the same model as the rest of
        # the pipeline.
        if embed_model is None:
            from factories import LLMFactory
            embed_model = LLMFactory.create_embedding_model(
                config.llm_provider, config.llm_config, settings=config
            )

        lc_embeddings = _LlamaIndexEmbeddingAdapter(embed_model)

        neo4j_vector = Neo4jVector.from_existing_index(
            embedding=lc_embeddings,
            url=url,
            username=username,
            password=password,
            database=database,
            index_name=index_name,
            node_label=node_label,
            embedding_node_property=embedding_node_property,
            text_node_property=text_node_property,
        )

        retriever = GraphEntityVectorRetriever(
            neo4j_vector=neo4j_vector,
            embed_model=embed_model,
            top_k=top_k,
            text_property=text_node_property,
        )
        logger.info(
            "Created LangChain Neo4j vector retriever (index=%s, label=%s, top_k=%d)",
            index_name, node_label, top_k,
        )
        return retriever

    except ImportError as e:
        logger.warning("LangChain Neo4j vector retriever not available: %s", e)
        return None
    except Exception as e:
        logger.error(
            "Failed to create LangChain Neo4j vector retriever: %s", e, exc_info=True
        )
        return None


class _LlamaIndexEmbeddingAdapter:
    """Minimal LangChain Embeddings adapter wrapping a LlamaIndex embed_model.

    Neo4jVector requires a LangChain ``Embeddings`` object.  This adapter
    delegates to the LlamaIndex embed_model so both paths use the same model.
    """

    def __init__(self, embed_model: Any):
        self._model = embed_model

    def embed_documents(self, texts: "List[str]") -> "List[List[float]]":
        return [self._model.get_text_embedding(t) for t in texts]

    def embed_query(self, text: str) -> "List[float]":
        return self._model.get_text_embedding(text)

    # LangChain async interface (optional but avoids warnings)
    async def aembed_documents(self, texts: "List[str]") -> "List[List[float]]":
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> "List[float]":
        return self.embed_query(text)





# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def build_pg_adapter_config(config: "AppSettings", store_type: str) -> dict:
    """Build config dict for the property_graph_adapters factory."""
    cfg = config
    if store_type == "arangodb":
        return {
            "url": getattr(cfg, "arangodb_url", "http://localhost:8529"),
            "database": getattr(cfg, "arangodb_database", "flexible-graphrag"),
            "username": getattr(cfg, "arangodb_username", "root"),
            "password": getattr(cfg, "arangodb_password", ""),
            "graph_name": getattr(cfg, "arangodb_graph_name", "knowledge_graph"),
        }
    if store_type in ("neptune", "neptune_analytics"):
        base = {
            "host": getattr(cfg, "neptune_host", None),
            "port": getattr(cfg, "neptune_port", 8182),
            "region": getattr(cfg, "neptune_region", "us-east-1"),
            "use_iam_auth": getattr(cfg, "neptune_use_iam_auth", False),
            "use_https": getattr(cfg, "neptune_use_https", True),
        }
        if store_type == "neptune_analytics":
            base["graph_identifier"] = getattr(cfg, "neptune_analytics_graph_id", None)
        return base
    if store_type == "apache_age":
        return {
            "host": getattr(cfg, "age_host", "localhost"),
            "port": getattr(cfg, "age_port", 5432),
            "database": getattr(cfg, "age_database", "postgres"),
            "username": getattr(cfg, "age_username", "postgres"),
            "password": getattr(cfg, "age_password", ""),
            "graph_name": getattr(cfg, "age_graph_name", "knowledge_graph"),
        }
    if store_type == "cosmos_gremlin":
        return {
            "url": getattr(cfg, "cosmos_gremlin_url", None),
            "username": getattr(cfg, "cosmos_gremlin_username", None),
            "password": getattr(cfg, "cosmos_gremlin_password", None),
            "database": getattr(cfg, "cosmos_gremlin_database", "graphdb"),
            "collection": getattr(cfg, "cosmos_gremlin_collection", "graph"),
        }
    if store_type == "spanner":
        return {
            "project_id": getattr(cfg, "spanner_project_id", None),
            "instance_id": getattr(cfg, "spanner_instance_id", None),
            "database_id": getattr(cfg, "spanner_database_id", None),
        }
    return {}


def create_community_pg_graph(config: "AppSettings", store_type: str):
    """Instantiate a LangChain graph store object for community-supported stores.

    Tries dedicated first-party packages first, falls back to langchain_community.
    """
    graph_config: Dict[str, Any] = getattr(config, "graph_config", {}) or {}

    if store_type == "neo4j":
        try:
            from langchain_neo4j import Neo4jGraph
        except ImportError:
            from langchain_community.graphs import Neo4jGraph
        return Neo4jGraph(
            url=graph_config.get("url", "bolt://localhost:7687"),
            username=graph_config.get("username", "neo4j"),
            password=graph_config.get("password", "password"),
            database=graph_config.get("database", "neo4j"),
        )

    if store_type == "memgraph":
        try:
            from langchain_memgraph import MemgraphGraph
        except ImportError:
            from langchain_community.graphs import MemgraphGraph
        return MemgraphGraph(
            url=graph_config.get("url", "bolt://localhost:7687"),
            username=graph_config.get("username", ""),
            password=graph_config.get("password", ""),
        )

    if store_type == "arcadedb":
        from langchain_arcadedb import ArcadeDBGraph
        return ArcadeDBGraph(
            url=graph_config.get("url", "http://localhost:2480"),
            username=graph_config.get("username", "root"),
            password=graph_config.get("password", ""),
            database=graph_config.get("database", "flexible-graphrag"),
        )

    if store_type == "falkordb":
        from langchain_community.graphs import FalkorDBGraph
        return FalkorDBGraph(
            host=graph_config.get("host", "localhost"),
            port=int(graph_config.get("port", 6379)),
        )

    if store_type == "hugegraph":
        from langchain_community.graphs import HugeGraph
        return HugeGraph(
            username=graph_config.get("username", "admin"),
            password=graph_config.get("password", "password"),
            address=graph_config.get("host", "localhost"),
            port=int(graph_config.get("port", 8080)),
            graph=graph_config.get("database", "hugegraph"),
        )

    if store_type == "nebula":
        from langchain_community.graphs import NebulaGraph
        return NebulaGraph(
            space=graph_config.get("database", "knowledge_graph"),
            username=graph_config.get("username", "root"),
            password=graph_config.get("password", "nebula"),
            address=graph_config.get("host", "localhost"),
            port=int(graph_config.get("port", 9669)),
        )

    if store_type == "tigergraph":
        from langchain_community.graphs import TigerGraph
        return TigerGraph(
            conn={
                "host": graph_config.get("host", "http://localhost"),
                "graphname": graph_config.get("database", "MyGraph"),
                "username": graph_config.get("username", "tigergraph"),
                "password": graph_config.get("password", "tigergraph"),
            }
        )

    raise ValueError(f"Unknown community PG store type: {store_type}")


# ---------------------------------------------------------------------------
# Neighborhood retriever factory  (store-agnostic k-hop expansion)
# ---------------------------------------------------------------------------

def build_pg_neighborhood_retriever(
    config: "AppSettings",
    embed_model: Any = None,
    neo4j_vector: Any = None,
) -> "Optional[Any]":
    """Create a GraphNeighborhoodRetriever for the configured LangChain PG store.

    Activated when ``USE_LANGCHAIN_PG=true`` and ``USE_PG_NEIGHBORHOOD=true``.

    The retriever:
    1. Uses a vector similarity search (same ``neo4j_vector`` / PG vector index
       as ``build_langchain_pg_vector_retriever``) to find seed node IDs.
    2. Expands those seeds up to ``PG_NEIGHBORHOOD_HOPS`` hops in the graph.
    3. Returns the text/name of every reached node for fusion.

    Currently implemented for Neo4j (Bolt driver + Cypher).  Other stores can
    be added by mapping ``langchain_pg_store_type`` to their own
        ``neighbor_query_fn`` here, without touching ``GraphNeighborhoodRetriever``.

    Args:
        config:       AppSettings instance.
        embed_model:  LlamaIndex embedding model (needed if neo4j_vector is None).
        neo4j_vector: Pre-built LangChain Neo4jVector (reuse if already created).

    Returns:
        GraphNeighborhoodRetriever or None.
    """
    use_langchain_pg = getattr(config, "use_langchain_pg", False)
    use_neighborhood = getattr(config, "use_pg_neighborhood", False)
    _graph_db = str(getattr(config, "graph_db", "") or "").lower()
    pg_store_type = (
        getattr(config, "langchain_pg_store_type", None) or (
            _graph_db if _graph_db not in ("", "none") else ""
        )
    ).lower()

    if not use_neighborhood:
        return None

    if not pg_store_type:
        logger.debug("PG neighborhood retriever: no store type resolved — set LANGCHAIN_PG_STORE_TYPE")
        return None

    pg_vector_search = getattr(config, "langchain_pg_vector_search", False)
    if not pg_vector_search:
        logger.debug("PG neighborhood retriever requires LANGCHAIN_PG_VECTOR_SEARCH=true for seeding")
        return None

    try:
        from langchain.graph.neighborhood_retriever import GraphNeighborhoodRetriever

        hop_depth = int(getattr(config, "pg_neighborhood_hops", 2))
        top_k_seeds = int(getattr(config, "pg_neighborhood_top_k_seeds", 10))
        top_k = int(getattr(config, "rdf_retrieval_top_k", 5))

        # --- build seed_id_getter (vector similarity search) ----------------
        if neo4j_vector is None and pg_store_type == "neo4j":
            # Build the Neo4jVector on demand (reuse same index as vector retriever)
            if embed_model is None:
                from factories import LLMFactory
                embed_model = LLMFactory.create_embedding_model(
                    config.llm_provider, config.llm_config, settings=config
                )
            try:
                from langchain_neo4j import Neo4jVector
            except ImportError:
                from langchain_community.vectorstores import Neo4jVector

            graph_config: Dict[str, Any] = getattr(config, "graph_config", {}) or {}
            neo4j_vector = Neo4jVector.from_existing_index(
                embedding=_LlamaIndexEmbeddingAdapter(embed_model),
                url=graph_config.get("url", "bolt://localhost:7687"),
                username=graph_config.get("username", "neo4j"),
                password=graph_config.get("password", "password"),
                database=graph_config.get("database", "neo4j"),
                index_name=getattr(config, "langchain_pg_vector_index", "entity"),
                node_label=getattr(config, "langchain_pg_vector_node_label", "__Entity__"),
                embedding_node_property=getattr(
                    config, "langchain_pg_vector_embedding_property", "embedding"
                ),
                text_node_property=getattr(
                    config, "langchain_pg_vector_text_property", "name"
                ),
            )

        if neo4j_vector is not None:
            def _neo4j_seed_getter(query_bundle):
                try:
                    hits = neo4j_vector.similarity_search_with_score(
                        query_bundle.query_str, k=top_k_seeds
                    )
                    for doc, _score in hits:
                        nid = (doc.metadata or {}).get("node_id") or (doc.metadata or {}).get("id")
                        if nid:
                            yield str(nid)
                except Exception as exc:
                    logger.warning("GraphNeighborhoodRetriever seed getter error: %s", exc)

            seed_id_getter = _neo4j_seed_getter
        else:
            logger.warning(
                "USE_PG_NEIGHBORHOOD=true but no vector search available for store_type=%s — skipping",
                pg_store_type,
            )
            return None

        # --- build neighbor_query_fn (store-specific traversal) --------------
        if pg_store_type == "neo4j":
            graph_config = getattr(config, "graph_config", {}) or {}
            try:
                from neo4j import GraphDatabase as _Neo4jDriver
            except ImportError:
                logger.warning("neo4j driver not installed; USE_PG_NEIGHBORHOOD requires it")
                return None

            _driver = _Neo4jDriver.driver(
                graph_config.get("url", "bolt://localhost:7687"),
                auth=(
                    graph_config.get("username", "neo4j"),
                    graph_config.get("password", "password"),
                ),
            )

            def _neo4j_neighbor_query(seed_ids: List[str], hops: int):
                """Return (node_id, text, score) tuples for all neighbors within hops."""
                cypher = (
                    "MATCH (seed) WHERE seed.id IN $seed_ids OR seed.name IN $seed_ids "
                    f"CALL apoc.path.subgraphNodes(seed, {{maxLevel: {hops}}}) "
                    "YIELD node "
                    "WITH node, seed "
                    "WHERE node <> seed "
                    "RETURN coalesce(node.id, elementId(node)) AS node_id, "
                    "       coalesce(node.text, node.name, node.title, '') AS text, "
                    "       1.0 AS score"
                )
                # Fallback Cypher without APOC (variable-length path)
                cypher_no_apoc = (
                    "MATCH (seed)-[*1.." + str(hops) + "]-(neighbor) "
                    "WHERE seed.id IN $seed_ids OR seed.name IN $seed_ids "
                    "RETURN coalesce(neighbor.id, elementId(neighbor)) AS node_id, "
                    "       coalesce(neighbor.text, neighbor.name, neighbor.title, '') AS text, "
                    "       1.0 AS score "
                    "LIMIT 200"
                )
                with _driver.session() as session:
                    try:
                        rows = session.run(cypher, seed_ids=seed_ids).data()
                    except Exception:
                        rows = session.run(cypher_no_apoc, seed_ids=seed_ids).data()
                    for row in rows:
                        yield row["node_id"], row["text"], float(row.get("score", 1.0))

            neighbor_query_fn = _neo4j_neighbor_query

        else:
            logger.warning(
                "USE_PG_NEIGHBORHOOD=true but store_type=%s has no neighborhood "
                "query implementation yet — skipping", pg_store_type,
            )
            return None

        retriever = GraphNeighborhoodRetriever(
            seed_id_getter=seed_id_getter,
            neighbor_query_fn=neighbor_query_fn,
            hop_depth=hop_depth,
            top_k=top_k,
        )
        logger.info(
            "Created PG neighborhood retriever (store=%s, hops=%d, top_k_seeds=%d)",
            pg_store_type, hop_depth, top_k_seeds,
        )
        return retriever

    except ImportError as e:
        logger.warning("PG neighborhood retriever not available: %s", e)
        return None
    except Exception as e:
        logger.error("Failed to create PG neighborhood retriever: %s", e, exc_info=True)
        return None
