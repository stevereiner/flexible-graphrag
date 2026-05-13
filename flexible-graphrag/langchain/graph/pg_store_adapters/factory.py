"""Factory for instantiating LangChain property-graph store adapters.

Keeps the registry and creation logic out of ``__init__.py``.

Public API
----------
``create_property_graph_adapter(db_type, config, app_config=None)``
    Instantiate an adapter by name.  Pass ``app_config`` (full AppSettings) to
    enable eager vector-index DDL on stores that support it (currently Neo4j).

``_build_vector_index_config(app_config)``
    Helper — extract the ``vector_index_config`` dict from AppSettings.
"""
from __future__ import annotations

from typing import Any, Dict

# Adapter modules are imported lazily inside create_property_graph_adapter() so
# that heavy or Python-version-sensitive third-party SDKs (e.g. apache-age-python
# / antlr4 on Python 3.14, langchain-surrealdb, llama-index-spanner) do not crash
# the entire process at startup when the user has selected a different DB backend.
#
# _ADAPTER_REGISTRY maps db_type strings to (module, class_name) tuples.
_ADAPTER_REGISTRY: Dict[str, tuple[str, str]] = {
    "neo4j":             (".neo4j_adapter",          "Neo4jAdapter"),
    "arangodb":          (".arangodb_adapter",        "ArangoDBAdapter"),
    "neptune":           (".neptune_pg_adapter",      "NeptunePropertyGraphAdapter"),
    "neptune_analytics": (".neptune_pg_adapter",      "NeptuneAnalyticsAdapter"),
    "apache_age":        (".apache_age_adapter",      "ApacheAGEAdapter"),
    "cosmos_gremlin":    (".cosmos_gremlin_adapter",  "CosmosDBGremlinAdapter"),
    "spanner":           (".spanner_adapter",         "SpannerGraphAdapter"),
    "surrealdb":         (".surrealdb_adapter",       "SurrealDBAdapter"),
    "memgraph":          (".memgraph_adapter",        "MemgraphAdapter"),
    "falkordb":          (".falkordb_adapter",        "FalkorDBAdapter"),
    "arcadedb":          (".arcadedb_lc_adapter",     "ArcadeDBLangChainAdapter"),
    "nebula":            (".nebula_adapter",          "NebulaGraphAdapter"),
    "hugegraph":         (".hugegraph_adapter",       "HugeGraphAdapter"),
    "tigergraph":        (".tigergraph_adapter",      "TigerGraphAdapter"),
    "ladybug":           (".ladybug_adapter",         "LangChainLadybugAdapter"),
}


def _load_adapter_class(db_type: str) -> type:
    """Import and return the adapter class for *db_type* on first use."""
    import importlib
    module_path, class_name = _ADAPTER_REGISTRY[db_type]
    # module_path is relative (starts with '.'), resolve against this package
    package = __name__.rsplit(".", 1)[0]
    try:
        module = importlib.import_module(module_path, package=package)
    except Exception as exc:
        raise ImportError(
            f"Cannot load adapter for PG_GRAPH_DB={db_type!r}: {exc}\n"
            f"  apache_age requires apache-age-python / antlr4-python3-runtime==4.9.3 "
            f"which has a known incompatibility with Python 3.14+ "
            f"(ord() called on int in ATNDeserializer). "
            f"Use Python 3.13 or switch to a different PG_GRAPH_DB."
            if db_type == "apache_age" else
            f"Cannot load adapter for PG_GRAPH_DB={db_type!r}: {exc}"
        ) from exc
    return getattr(module, class_name)


def create_property_graph_adapter(
    db_type: str,
    config: Dict[str, Any],
    app_config: Any = None,
):
    """Instantiate a property graph adapter by *db_type* name.

    Args:
        db_type:    Identifier string, e.g. ``'neo4j'``, ``'arangodb'``.
        config:     Database-specific configuration dict (connection details).
        app_config: Optional full ``AppSettings`` instance.  When supplied and
                    ``langchain_pg_vector_search=True``, the Neo4j adapter runs
                    ``CREATE VECTOR INDEX IF NOT EXISTS`` on construction so the
                    index is ready before any ingestion writes nodes.

    Returns:
        Adapter instance with ``.get_graph()`` and ``.create_qa_chain()`` methods.
    """
    if db_type not in _ADAPTER_REGISTRY:
        raise ValueError(
            f"Unknown property graph type: {db_type!r}. "
            f"Choose from: {sorted(_ADAPTER_REGISTRY)}"
        )
    adapter_cls = _load_adapter_class(db_type)

    # Neo4j supports eager vector-index DDL when app_config is provided.
    if db_type == "neo4j" and app_config is not None:
        vic = _build_vector_index_config(app_config)
        if vic:
            return adapter_cls(config, vector_index_config=vic)

    return adapter_cls(config)


def _build_vector_index_config(app_config: Any) -> Dict[str, Any]:
    """Return a ``vector_index_config`` dict from AppSettings, or ``{}`` if not needed."""
    if not getattr(app_config, "langchain_pg_vector_search", False):
        return {}
    return {
        "index_name":         getattr(app_config, "langchain_pg_vector_index", "entity"),
        "node_label":         getattr(app_config, "langchain_pg_vector_node_label", "__Entity__"),
        "embedding_property": getattr(app_config, "langchain_pg_vector_embedding_property", "embedding"),
        "dimensions":         getattr(app_config, "embedding_dimension", 1536) or 1536,
    }


__all__ = [
    "_ADAPTER_REGISTRY",
    "create_property_graph_adapter",
    "_build_vector_index_config",
]
