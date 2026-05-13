"""adapters.graph.pg_store_adapter — PropertyGraphStoreAdapter ABC and factory.

The ABC defines the contract; concrete implementations live in:
  llamaindex.graph.pg_adapter  — LlamaIndexPGAdapter
  langchain.graph.pg_store_adapter — LangChainPGAdapter
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GraphDocument converter (needs langchain-community; kept here as it is
# framework-bridging utility, not tied to either implementation)
# ---------------------------------------------------------------------------

def nodes_to_graph_documents(nodes, triplets=None):
    """Convert LlamaIndex nodes (+ optional triplet list) to LangChain GraphDocuments."""
    try:
        from langchain_core.documents import Document
        from langchain_community.graphs.graph_document import (
            GraphDocument,
            Node as GNode,
            Relationship as GRel,
        )
    except ImportError as exc:
        raise ImportError(
            "langchain-core and langchain-community are required for nodes_to_graph_documents. "
            "Install: pip install langchain-core langchain-community"
        ) from exc

    graph_docs: List[GraphDocument] = []
    for node in nodes:
        text = getattr(node, "text", "") or ""
        metadata = getattr(node, "metadata", {}) or {}
        source_doc = Document(page_content=text, metadata=metadata)
        g_nodes: List[GNode] = []
        g_rels: List[GRel] = []
        if triplets:
            seen_nodes: Dict[str, GNode] = {}
            for subj, rel, obj in triplets:
                if subj not in seen_nodes:
                    seen_nodes[subj] = GNode(id=subj, type="Entity")
                if obj not in seen_nodes:
                    seen_nodes[obj] = GNode(id=obj, type="Entity")
                g_rels.append(GRel(
                    source=seen_nodes[subj],
                    target=seen_nodes[obj],
                    type=rel.upper().replace(" ", "_"),
                ))
            g_nodes = list(seen_nodes.values())
        graph_docs.append(GraphDocument(nodes=g_nodes, relationships=g_rels, source=source_doc))
    return graph_docs


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------

class PropertyGraphStoreAdapter(ABC):
    """Unified interface for property graph stores (LlamaIndex or LangChain backend)."""

    @abstractmethod
    def add_nodes(self, nodes: List, triplets: Optional[List] = None) -> None:
        """Ingest nodes (and optional triplets) into the graph store."""

    @abstractmethod
    def delete(self, ref_doc_id: str) -> None:
        """Delete all graph data associated with *ref_doc_id*."""

    @abstractmethod
    def get_li_store(self) -> Optional[Any]:
        """Return the underlying LlamaIndex PropertyGraphStore (or None)."""

    @abstractmethod
    def get_lc_graph(self) -> Optional[Any]:
        """Return the underlying LangChain graph object (or None)."""

    @abstractmethod
    def is_langchain(self) -> bool:
        """True if this adapter uses a LangChain store for ingestion."""

    def normalize_entity_names(self) -> None:
        """Post-ingestion normalisation: copy the entity ``id`` field into ``name``.

        LangChain's ``LLMGraphTransformer`` populates ``__Entity__.id`` but
        QA chains often filter on ``n.name``.  Each concrete adapter overrides
        this to run the appropriate query for its store's query language.

        The default implementation is a no-op so stores that cannot perform
        this normalisation (e.g. Gremlin-only servers) do not raise errors.
        """


# Stores that have no LlamaIndex PropertyGraphStore — always use LangChain adapter.
LC_ONLY_PG_STORES: frozenset = frozenset({
    "arangodb", "apache_age", "cosmos_gremlin",
    "hugegraph", "tigergraph", "surrealdb",
})

# Stores that have no LangChain PropertyGraphStore — always use LlamaIndex adapter.
# (langchain-google-spanner requires langchain-core<1.0; incompatible with langchain>=1.0)
LI_ONLY_PG_STORES: frozenset = frozenset({
    "spanner",
})

# Stores with a built-in vector index — GraphEntityVectorRetriever is the preferred
# graph retriever. TextToGraphQueryRetriever (text-to-query) is opt-in via USE_LC_TEXT_TO_GRAPH.
# NOTE: Only add stores here when LC vector retrieval is actually implemented in
# pg_retriever_factory.build_langchain_pg_vector_retriever.
VECTOR_CAPABLE_PG_STORES: frozenset = frozenset({
    # Stores whose LangChain adapter supports entity-level vector search:
    # __Entity__[embedding] index queried by build_langchain_pg_vector_retriever /
    # GraphEntityVectorRetriever.  Adding a store here enables LANGCHAIN_PG_VECTOR_SEARCH
    # and the optional neighborhood retriever.
    "neo4j",      # __Entity__[embedding] index (LlamaIndex / LangChain Neo4jVector)
    # --- Stores with chunk-level vector (not entity-level, handled separately) ---
    # falkordb — uses FalkorDB's native Chunk-node vector index; activated by
    #            LANGCHAIN_PG_VECTOR_SEARCH=true in retriever_setup.py.
    #            Do NOT add falkordb here — build_langchain_pg_vector_retriever is not
    #            implemented for its __Entity__ nodes.
    # --- Stores with vector capability not yet wired into build_langchain_pg_vector_retriever ---
    # "arcadedb"  — has built-in LSM vector index; LC __Entity__ retrieval not yet implemented
    # "arangodb"  — ArangoVector (langchain-arangodb) supports vector search over vertex docs;
    #               implementable but not yet done (uses ArangoVector, not Neo4jVector pattern)
    # "surrealdb" — vector support exists but __Entity__[embedding] path not implemented
    # "surrealdb" — SurrealDB vector similarity, pending LC implementation
})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_pg_store_adapter(
    db_type_str: str,
    config: Dict[str, Any],
    schema_config: Optional[Dict[str, Any]] = None,
    has_separate_vector_store: bool = False,
    llm_provider=None,
    llm_config: Optional[Dict[str, Any]] = None,
    app_config=None,
    graph_backend: str = "llamaindex",
) -> PropertyGraphStoreAdapter:
    """Create a :class:`PropertyGraphStoreAdapter` for *db_type_str*.

    Parameters
    ----------
    db_type_str:
        Lower-case database type name (e.g. ``"neo4j"``, ``"arangodb"``).
    config:
        Database connection configuration dict.
    graph_backend:
        ``"llamaindex"`` (default) or ``"langchain"``.
    """
    from langchain.graph.pg_store_adapter import LangChainPGAdapter, _build_lc_graph
    from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

    backend = (graph_backend or "llamaindex").lower()

    from adapters.graph.pg_store_adapter import LC_ONLY_PG_STORES

    if db_type_str in LC_ONLY_PG_STORES or backend == "langchain":
        store_adapter, lc_graph = _build_lc_graph(db_type_str, config, app_config)
        return LangChainPGAdapter(lc_graph, store_adapter=store_adapter)

    from config import PropertyGraphType
    try:
        pg_type = PropertyGraphType(db_type_str)
    except ValueError:
        raise ValueError(f"Unknown PropertyGraphType: '{db_type_str}'")

    from llamaindex.graph.graph_store_factory import create_graph_store
    return create_graph_store(
        pg_type, config, schema_config, has_separate_vector_store,
        llm_provider, llm_config, app_config,
    )
