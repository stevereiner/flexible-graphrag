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

def build_langchain_pg_retriever(config: "AppSettings", source_files=None, lc_graph=None):
    """Create a LangChain property-graph text-to-query retriever for fusion.

    Activated when ``USE_LANGCHAIN_PG=true`` OR ``USE_LC_TEXT_TO_GRAPH=true``.
    The store type is resolved from ``LANGCHAIN_PG_STORE_TYPE`` or ``PG_GRAPH_DB``.

    Args:
        source_files: Optional list of ingested file names to attach to each
            result node for source attribution in the UI.
        lc_graph:     Optional already-opened LangChain graph object to reuse.
            When provided, adapter creation is skipped entirely.  Useful for
            embedded stores (Ladybug/Kùzu) where opening a second ``Database``
            handle to the same path is unsafe.

    Returns:
        TextToGraphQueryRetriever or None if not configured / failed.
    """
    use_langchain_pg = getattr(config, "use_langchain_pg", False)
    use_lc_text_to_graph = getattr(config, "use_lc_text_to_graph", False)

    if not use_langchain_pg and not use_lc_text_to_graph:
        logger.debug(
            "build_langchain_pg_retriever: skip (use_langchain_pg=%s use_lc_text_to_graph=%s)",
            use_langchain_pg,
            use_lc_text_to_graph,
        )
        return None

    pg_store_type = getattr(config, "langchain_pg_store_type", None)
    if not pg_store_type:
        # fall back to the LlamaIndex PG store type
        _pg_db = getattr(config, "pg_graph_db", None)
        if _pg_db is not None:
            pg_store_type = str(_pg_db).lower().split(".")[-1]  # handle PropertyGraphType enum
    if not pg_store_type or pg_store_type in ("none", ""):
        logger.debug(
            "build_langchain_pg_retriever: skip (no pg_store_type resolvable from config)"
        )
        return None

    try:
        from langchain.graph.retrievers.li_graph_query_retriever import TextToGraphQueryRetriever
        from langchain.graph.pg_store_adapters import create_property_graph_adapter

        pg_store_type = pg_store_type.lower()

        _FACTORY_STORES = {
            "arangodb", "neptune", "neptune_analytics",
            "apache_age", "cosmos_gremlin", "spanner", "surrealdb",
            # Embedded stores — prefer the pre-opened lc_graph when passed in,
            # but can also open a fresh connection from the factory.
            "ladybug",
        }
        _COMMUNITY_STORES = {
            "neo4j", "memgraph", "falkordb",
            "hugegraph", "nebula", "tigergraph", "arcadedb",
        }

        if lc_graph is not None:
            # Reuse already-opened graph (avoids second DB connection for embedded stores).
            logger.debug(
                "build_langchain_pg_retriever: reusing existing lc_graph (%s) for store=%s",
                type(lc_graph).__name__,
                pg_store_type,
            )
        elif pg_store_type in _FACTORY_STORES:
            adapter = create_property_graph_adapter(
                pg_store_type,
                build_pg_adapter_config(config, pg_store_type),
                app_config=config,
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
            include_intermediate_steps=getattr(config, "langchain_pg_intermediate_steps", True),
            source_files=source_files or [],
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
    _graph_db = str(getattr(config, "pg_graph_db", "") or "").lower()
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
        from langchain.graph.retrievers.li_neo4j_vector_retriever import GraphEntityVectorRetriever

        try:
            from langchain_neo4j import Neo4jVector
        except ImportError:
            from langchain_community.vectorstores import Neo4jVector

        graph_config: Dict[str, Any] = getattr(config, "graph_db_config", {}) or {}
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
        msg = str(e).lower()
        if "vector index" in msg and ("does not exist" in msg or "not found" in msg or "spelled" in msg):
            logger.warning(
                "LangChain Neo4j vector retriever: index %r not found in Neo4j. "
                "This is expected when GRAPH_BACKEND=langchain was used for ingestion "
                "(LLMGraphTransformer does not create a vector index). "
                "Set LANGCHAIN_PG_VECTOR_SEARCH=false to suppress this warning, "
                "or re-ingest with GRAPH_BACKEND=llamaindex to populate the index.",
                index_name,
            )
        else:
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
        _gc = getattr(cfg, "graph_db_config", {}) or {}
        return {
            "url":        getattr(cfg, "arangodb_url",        None) or _gc.get("url",        "http://localhost:8529"),
            "database":   getattr(cfg, "arangodb_database",   None) or _gc.get("database",   "flexible-graphrag"),
            "username":   getattr(cfg, "arangodb_username",   None) or _gc.get("username",   "root"),
            "password":   getattr(cfg, "arangodb_password",   None) or _gc.get("password",   ""),
            "graph_name": getattr(cfg, "arangodb_graph_name", None) or _gc.get("graph_name", "knowledge_graph"),
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
        _gc = getattr(cfg, "graph_db_config", {}) or {}
        return {
            "host":            _gc.get("host",            getattr(cfg, "age_host",              "localhost")),
            "port":            _gc.get("port",            getattr(cfg, "age_port",              5434)),
            "database":        _gc.get("database",        getattr(cfg, "age_database",          "flexible_graphrag_age")),
            "username":        _gc.get("username",        getattr(cfg, "age_username",          "postgres")),
            "password":        _gc.get("password",        getattr(cfg, "age_password",          "password")),
            "graph_name":      _gc.get("graph_name",      getattr(cfg, "age_graph_name",        "knowledge_graph")),
            "collection_name": _gc.get("collection_name", getattr(cfg, "age_vector_collection", "langchain_age_vectors")),
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

    if store_type == "surrealdb":
        # Prefer graph_db_config (populated from SURREALDB_GRAPH_DB_CONFIG JSON blob)
        # over the individual attribute fallbacks which default to port 8000.
        gdc = getattr(cfg, "graph_db_config", None) or {}
        return {
            "url": gdc.get("url") or getattr(cfg, "surrealdb_url", "ws://localhost:8010/rpc"),
            "namespace": gdc.get("namespace") or getattr(cfg, "surrealdb_namespace", "test"),
            "database": gdc.get("database") or getattr(cfg, "surrealdb_database", "flexible_graphrag"),
            "username": gdc.get("username") or getattr(cfg, "surrealdb_username", "root"),
            "password": gdc.get("password") or getattr(cfg, "surrealdb_password", "root"),
        }

    return {}


def create_community_pg_graph(config: "AppSettings", store_type: str):
    """Instantiate a LangChain graph store object for the given *store_type*.

    Delegates to :func:`create_property_graph_adapter` — the single source of
    truth for all LangChain graph constructors (one file per store type).
    """
    from langchain.graph.pg_store_adapters import (
        create_property_graph_adapter,
    )

    # graph_db_config is the AppSettings field populated from NEO4J_GRAPH_DB_CONFIG
    # (or the equivalent per-store var).  "graph_config" does not exist on AppSettings.
    graph_config: Dict[str, Any] = getattr(config, "graph_db_config", {}) or {}

    try:
        return create_property_graph_adapter(
            store_type, graph_config, app_config=config
        ).get_graph()
    except ValueError as e:
        if "Unknown" in str(e) or "not supported" in str(e).lower():
            raise ValueError(f"Unknown community PG store type: {store_type!r}") from e
        raise


# ---------------------------------------------------------------------------
# Neighborhood retriever factory  (store-agnostic k-hop expansion)
# ---------------------------------------------------------------------------

def build_pg_neighborhood_retriever(
    config: "AppSettings",
    embed_model: Any = None,
    neo4j_vector: Any = None,
    use_neighborhood: Optional[bool] = None,
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
    # use_neighborhood param overrides config (used when auto-enabled by retriever_setup)
    _use_neighborhood = use_neighborhood if use_neighborhood is not None else getattr(config, "use_pg_neighborhood", False)
    _graph_db = str(getattr(config, "pg_graph_db", "") or "").lower()
    pg_store_type = (
        getattr(config, "langchain_pg_store_type", None) or (
            _graph_db if _graph_db not in ("", "none") else ""
        )
    ).lower()

    if not _use_neighborhood:
        return None

    if not pg_store_type:
        logger.debug("PG neighborhood retriever: no store type resolved — set LANGCHAIN_PG_STORE_TYPE")
        return None

    pg_vector_search = getattr(config, "langchain_pg_vector_search", False)
    if not pg_vector_search:
        logger.debug("PG neighborhood retriever requires LANGCHAIN_PG_VECTOR_SEARCH=true for seeding")
        return None

    try:
        from langchain.graph.retrievers.li_neighborhood_retriever import GraphNeighborhoodRetriever

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

            graph_config: Dict[str, Any] = getattr(config, "graph_db_config", {}) or {}
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
            # Pre-warm the similarity-search path so the first async retrieval
            # call doesn't block the event loop on connection setup.
            try:
                neo4j_vector.similarity_search_with_score("warmup", k=1)
                logger.debug("Neo4j neighborhood vector store: similarity-search warm-up complete")
            except Exception as _we:
                logger.debug("Neo4j neighborhood vector warm-up skipped: %s", _we)

            def _neo4j_seed_getter(query_bundle):
                try:
                    hits = neo4j_vector.similarity_search_with_score(
                        query_bundle.query_str, k=top_k_seeds
                    )
                    for doc, _score in hits:
                        # Neo4jVector may return the entity name in metadata["id"]
                        # or metadata["node_id"], OR just as page_content (which IS
                        # the id value when text_node_property="id").  Fall through
                        # all options so the neighbor Cypher can match seed.id.
                        nid = (
                            (doc.metadata or {}).get("node_id")
                            or (doc.metadata or {}).get("id")
                            or doc.page_content  # page_content = id/name value
                        )
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
            graph_config = getattr(config, "graph_db_config", {}) or {}
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
            # Pre-warm the Bolt connection pool so the first retrieval call does
            # not pay the TCP + handshake + auth cost and block the async event loop.
            try:
                with _driver.session() as _ws:
                    _ws.run("RETURN 1").consume()
                logger.debug("Neo4j neighborhood driver: Bolt connection warm-up complete")
            except Exception as _we:
                logger.debug("Neo4j neighborhood driver warm-up skipped: %s", _we)

            def _neo4j_neighbor_query(seed_ids: List[str], hops: int):
                """Return (node_id, text, score) tuples for all neighbors within hops.

                Prioritises Document nodes — those WITHOUT the ``__Entity__`` label
                that carry a ``text`` property written by
                ``add_graph_documents(include_source=True)``.  Those nodes get
                score=1.0 and entity-name stubs get score=0.6.

                Scores are capped at 1.0 so that ``QueryFusionRetriever`` with
                ``mode="relative_score"`` is not anchored to a 2.0 max, which
                would squash all vector/search scores down to near-zero.
                """
                cypher = (
                    "MATCH (seed) WHERE seed.id IN $seed_ids OR seed.name IN $seed_ids "
                    f"CALL apoc.path.subgraphNodes(seed, {{maxLevel: {hops}}}) "
                    "YIELD node "
                    "WITH node, seed "
                    "WHERE node <> seed "
                    "WITH node, "
                    # Document nodes (add_graph_documents include_source=True) have no
                    # __Entity__ label and store chunk text in the `text` property.
                    # Entity nodes have __Entity__ label; use name/id as display text.
                    "     CASE "
                    "       WHEN NOT '__Entity__' IN labels(node) AND node.text IS NOT NULL "
                    "         THEN node.text "
                    "       ELSE coalesce(node.name, node.id, '') "
                    "     END AS text, "
                    "     CASE "
                    "       WHEN NOT '__Entity__' IN labels(node) AND node.text IS NOT NULL "
                    "         THEN 1.0 "
                    "       ELSE 0.6 "
                    "     END AS score "
                    "RETURN coalesce(node.id, elementId(node)) AS node_id, text, score, "
                    "       coalesce(node.file_name, '') AS file_name, "
                    "       coalesce(node.file_type, '') AS file_type"
                )
                # Fallback Cypher without APOC (variable-length path)
                cypher_no_apoc = (
                    "MATCH (seed)-[*1.." + str(hops) + "]-(neighbor) "
                    "WHERE seed.id IN $seed_ids OR seed.name IN $seed_ids "
                    "WITH neighbor, "
                    "     CASE "
                    "       WHEN NOT '__Entity__' IN labels(neighbor) AND neighbor.text IS NOT NULL "
                    "         THEN neighbor.text "
                    "       ELSE coalesce(neighbor.name, neighbor.id, '') "
                    "     END AS text, "
                    "     CASE "
                    "       WHEN NOT '__Entity__' IN labels(neighbor) AND neighbor.text IS NOT NULL "
                    "         THEN 1.0 "
                    "       ELSE 0.6 "
                    "     END AS score "
                    "RETURN coalesce(neighbor.id, elementId(neighbor)) AS node_id, text, score, "
                    "       coalesce(neighbor.file_name, '') AS file_name, "
                    "       coalesce(neighbor.file_type, '') AS file_type "
                    "LIMIT 200"
                )
                with _driver.session() as session:
                    try:
                        rows = session.run(cypher, seed_ids=seed_ids).data()
                    except Exception:
                        rows = session.run(cypher_no_apoc, seed_ids=seed_ids).data()
                    for row in rows:
                        meta = {}
                        if row.get("file_name"):
                            meta["file_name"] = row["file_name"]
                        if row.get("file_type"):
                            meta["file_type"] = row["file_type"]
                        yield row["node_id"], row["text"], float(row.get("score", 1.0)), meta

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
