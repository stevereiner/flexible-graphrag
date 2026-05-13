"""
Chain builder modules — one per query language.

Each module exports a single ``build_*`` function with the signature::

    build_xxx(graph, llm, include_intermediate: bool, common: dict) -> Any

The ``common`` dict is already assembled by ``_build_qa_chain`` in
``lc_graph_retriever.py`` and contains::

    {"llm": llm, "graph": graph, "verbose": False,
     "return_intermediate_steps": include_intermediate,
     "allow_dangerous_requests": True}
"""

from ._sparql import build_sparql_neptune, build_sparql_graphdb, build_sparql_generic
from ._cypher import (
    build_opencypher_neptune,
    build_cypher_arcadedb,
    build_cypher_neo4j,
    build_cypher_memgraph,
    build_cypher_falkordb,
    build_cypher_age,
    build_cypher_generic,
    build_cypher_ladybug,
)
from ._gsql import build_gsql_tigergraph
from ._hugegraph import build_cypher_hugegraph
from ._nebula import build_cypher_nebula
from ._gremlin import build_gremlin_generic
from ._aql import build_aql_arangodb
from ._surql import build_surql_surrealdb

# Dispatch table: chain_key -> builder function
CHAIN_BUILDERS: dict = {
    "sparql_neptune":     build_sparql_neptune,
    "sparql_graphdb":     build_sparql_graphdb,
    "sparql_generic":     build_sparql_generic,
    "opencypher_neptune": build_opencypher_neptune,
    "cypher_arcadedb":    build_cypher_arcadedb,
    "cypher_neo4j":       build_cypher_neo4j,
    "cypher_memgraph":    build_cypher_memgraph,
    "cypher_falkordb":    build_cypher_falkordb,
    "cypher_age":         build_cypher_age,
    "cypher_generic":     build_cypher_generic,
    "gsql_tigergraph":    build_gsql_tigergraph,
    "cypher_hugegraph":   build_cypher_hugegraph,
    "cypher_nebula":      build_cypher_nebula,
    "gremlin_generic":    build_gremlin_generic,
    "aql_arangodb":       build_aql_arangodb,
    "surql_surrealdb":    build_surql_surrealdb,
    "cypher_ladybug":     build_cypher_ladybug,
}

__all__ = ["CHAIN_BUILDERS"]
