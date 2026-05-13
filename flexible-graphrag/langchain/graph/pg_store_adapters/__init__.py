"""
langchain.graph.pg_store_adapters
=====================================================

One module per LangChain property-graph store. Each module defines a single
adapter class with two methods:

    ``get_graph()``           -> raw LangChain graph object (used by LangChainPGAdapter)
    ``create_qa_chain(llm)``  -> a QA chain for text-to-query retrieval

Modules
-------
neo4j_adapter          Neo4jAdapter
arangodb_adapter       ArangoDBAdapter
neptune_pg_adapter     NeptunePropertyGraphAdapter, NeptuneAnalyticsAdapter
apache_age_adapter     ApacheAGEAdapter
cosmos_gremlin_adapter CosmosDBGremlinAdapter
spanner_adapter        SpannerGraphAdapter
surrealdb_adapter      SurrealDBAdapter
memgraph_adapter       MemgraphAdapter
falkordb_adapter       FalkorDBAdapter
arcadedb_lc_adapter    ArcadeDBLangChainAdapter
nebula_adapter         NebulaGraphAdapter
hugegraph_adapter      HugeGraphAdapter
tigergraph_adapter     TigerGraphAdapter
ladybug_adapter        LangChainLadybugAdapter
factory                create_property_graph_adapter, _ADAPTER_REGISTRY
"""
from .neo4j_adapter import Neo4jAdapter
from .arangodb_adapter import ArangoDBAdapter
from .neptune_pg_adapter import NeptunePropertyGraphAdapter, NeptuneAnalyticsAdapter
from .cosmos_gremlin_adapter import CosmosDBGremlinAdapter
from .spanner_adapter import SpannerGraphAdapter
from .surrealdb_adapter import SurrealDBAdapter
from .memgraph_adapter import MemgraphAdapter
from .falkordb_adapter import FalkorDBAdapter
from .arcadedb_lc_adapter import ArcadeDBLangChainAdapter
from .nebula_adapter import NebulaGraphAdapter
from .hugegraph_adapter import HugeGraphAdapter
from .tigergraph_adapter import TigerGraphAdapter
from .ladybug_adapter import LangChainLadybugAdapter
from .factory import _ADAPTER_REGISTRY, create_property_graph_adapter, _build_vector_index_config

# Backward-compat alias used in older code
ArcadeDBAdapter = ArcadeDBLangChainAdapter

# apache-age-python uses antlr4-python3-runtime which is broken on Python 3.14
# (ord() called on int in ATNDeserializer). Guard the import so that users who
# are NOT running Apache AGE can still start the backend normally.
try:
    from .apache_age_adapter import ApacheAGEAdapter
    _apache_age_available = True
except Exception:
    _apache_age_available = False
    ApacheAGEAdapter = None  # type: ignore[assignment,misc]

__all__ = [
    "Neo4jAdapter",
    "ArangoDBAdapter",
    "NeptunePropertyGraphAdapter",
    "NeptuneAnalyticsAdapter",
    "ApacheAGEAdapter",
    "CosmosDBGremlinAdapter",
    "SpannerGraphAdapter",
    "SurrealDBAdapter",
    "MemgraphAdapter",
    "FalkorDBAdapter",
    "ArcadeDBLangChainAdapter",
    "ArcadeDBAdapter",
    "NebulaGraphAdapter",
    "HugeGraphAdapter",
    "TigerGraphAdapter",
    "LangChainLadybugAdapter",
    "_ADAPTER_REGISTRY",
    "create_property_graph_adapter",
    "_build_vector_index_config",
]
