"""langchain.graph.pg_store_adapter — LangChain property graph adapter.

Contains only the LangChain-backed implementation.
The ABC and factory live in :mod:`adapters.graph.pg_store_adapter`.
The LlamaIndex-backed implementation lives in :mod:`llamaindex.graph.pg_adapter`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from adapters.graph.pg_store_adapter import PropertyGraphStoreAdapter, nodes_to_graph_documents

logger = logging.getLogger(__name__)


def shared_delete_cypher(rid_prop: str = "ref_doc_id") -> List[str]:
    """Cypher (``$rid`` parameter) deleting one document's LangChain graph data without taking
    other documents' with it.

    A source node (one per chunk) MENTIONS the entities extracted from it; an entity is shared
    across documents but stamped with one document's id, so deleting every node stamped with
    the id would detach-delete entities, and the relationships, other documents still use.
    In order: this document's relationships no other document's source node supports (it
    MENTIONS both ends), then hand its entities another document mentions over to that
    document, then every node still stamped with the id (its source nodes, its own entities).
    """
    rid = f"coalesce(o.{rid_prop}, o.doc_id)"
    # A source node may carry only doc_id (LangChain Neo4jGraph writes the chunk's metadata as is)
    return [
        f"MATCH (d)-[:MENTIONS]->(a)-[r]->(b)<-[:MENTIONS]-(d) WHERE coalesce(d.{rid_prop}, d.doc_id) = $rid "
        "AND type(r) <> 'MENTIONS' "
        f"OPTIONAL MATCH (o)-[:MENTIONS]->(a), (o)-[:MENTIONS]->(b) WHERE {rid} <> $rid "
        "WITH r, count(o) AS n WHERE n = 0 DELETE r",
        f"MATCH (o)-[:MENTIONS]->(e) WHERE e.{rid_prop} = $rid AND {rid} <> $rid "
        f"WITH e, collect({rid})[0] AS heir SET e.{rid_prop} = heir, "
        "e.doc_id = CASE WHEN e.doc_id IS NULL THEN NULL ELSE heir END",
        f"MATCH (n) WHERE n.{rid_prop} = $rid OR (n.{rid_prop} IS NULL AND n.doc_id = $rid) DETACH DELETE n",
    ]


class LangChainPGAdapter(PropertyGraphStoreAdapter):
    """Wraps a LangChain graph object and ingests via ``add_graph_documents()``.

    Supported LangChain graph types include (but are not limited to):
    ``Neo4jGraph``, ``ArangoGraph``, ``AGEGraph``, ``CosmosDBGremlinGraph``,
    ``SpannerGraphStore``, ``NeptuneGraph``, ``NeptuneAnalyticsGraph``.

    Parameters
    ----------
    lc_graph:
        The raw LangChain graph object (e.g. ``Neo4jGraph``).
    store_adapter:
        The specific pg-store adapter that produced *lc_graph* (e.g.
        ``Neo4jAdapter``).  When present, ``normalize_entity_names()`` is
        delegated to it so each store can use its own query language.
    """

    def __init__(self, lc_graph, store_adapter=None, ref_doc_id_property: str = "ref_doc_id"):
        self._lc_graph = lc_graph
        self._store_adapter = store_adapter
        self._ref_doc_id_prop = ref_doc_id_property

    def add_nodes(self, nodes: List, triplets: Optional[List] = None) -> None:
        if self._lc_graph is None:
            logger.warning("LangChainPGAdapter: no graph configured, skipping add_nodes")
            return
        try:
            graph_docs = nodes_to_graph_documents(nodes, triplets)
            # Delegate to the store adapter's add_graph_documents override if present
            # (e.g. FalkorDB inlines properties to avoid parameterized-dict issues).
            if self._store_adapter is not None and hasattr(self._store_adapter, "add_graph_documents"):
                self._store_adapter.add_graph_documents(graph_docs)
            else:
                self._lc_graph.add_graph_documents(graph_docs)
            logger.info(f"LangChain graph: added {len(graph_docs)} graph documents")
        except Exception as exc:
            logger.error(f"LangChainPGAdapter.add_nodes failed: {exc}")
            raise

    def delete(self, ref_doc_id: str) -> None:
        if self._lc_graph is None:
            return
        # Delegate to the store adapter's delete() when present — allows each
        # backend (ArangoDB AQL, Gremlin, SurrealQL, etc.) to use its own
        # query language instead of the generic Cypher below.
        if self._store_adapter is not None and hasattr(self._store_adapter, "delete"):
            try:
                self._store_adapter.delete(ref_doc_id)
                return
            except Exception as exc:
                logger.warning(f"LangChain graph store_adapter delete failed for {ref_doc_id}: {exc}")
                return
        # Default: Cypher — works for Neo4j, FalkorDB, ArcadeDB, Neptune
        try:
            if hasattr(self._lc_graph, "query"):
                for cypher in shared_delete_cypher(self._ref_doc_id_prop):
                    self._lc_graph.query(cypher, params={"rid": ref_doc_id})
                logger.info(f"LangChain graph: deleted nodes for ref_doc_id={ref_doc_id}")
            else:
                logger.warning(
                    f"LangChainPGAdapter: graph type {type(self._lc_graph).__name__} "
                    "does not expose .query() — delete skipped"
                )
        except Exception as exc:
            logger.warning(f"LangChain graph delete failed for {ref_doc_id}: {exc}")

    def get_li_store(self):
        return None

    def get_lc_graph(self):
        return self._lc_graph

    def is_langchain(self) -> bool:
        return True

    def normalize_entity_names(self) -> None:
        """Delegate to the underlying store adapter if one is available."""
        if self._store_adapter is not None and hasattr(self._store_adapter, "normalize_entity_names"):
            self._store_adapter.normalize_entity_names()
        else:
            logger.debug(
                "LangChainPGAdapter.normalize_entity_names: no store adapter present "
                "(graph type=%s) — skipping",
                type(self._lc_graph).__name__,
            )


# ---------------------------------------------------------------------------
# Internal: build LangChain graph objects
# ---------------------------------------------------------------------------

def _build_lc_graph(db_type_str: str, config: Dict[str, Any], app_config=None):
    """Instantiate a LangChain graph object for the given *db_type_str*.

    Returns a ``(store_adapter, lc_graph)`` tuple so the caller can keep a
    reference to the specific adapter (for ``normalize_entity_names()`` etc.)
    as well as the raw graph object used internally by ``LangChainPGAdapter``.

    All stores are delegated to their individual adapter modules inside
    ``langchain.graph``.  The adapter's ``.get_graph()``
    method returns the raw LangChain graph object used by
    ``LangChainPGAdapter``.

    Ingestion support notes:
    - Full add_graph_documents: neo4j, memgraph, falkordb, arcadedb, arangodb, apache_age
    - Limited / retrieval-preferred: nebula, hugegraph, cosmos_gremlin, spanner
    - GSQL via REST++: tigergraph
    """
    from langchain.graph.pg_store_adapters import (
        create_property_graph_adapter,
    )
    adapter = create_property_graph_adapter(db_type_str, config, app_config=app_config)
    return adapter, adapter.get_graph()
