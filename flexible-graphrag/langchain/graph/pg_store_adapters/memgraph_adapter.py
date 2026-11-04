"""LangChain Memgraph in-memory graph database adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict

from ._graph_docs import cypher_ident

logger = logging.getLogger(__name__)

try:
    from langchain_memgraph import MemgraphGraph
    MEMGRAPH_AVAILABLE = True
except ImportError:
    try:
        from langchain_community.graphs import MemgraphGraph  # type: ignore
        MEMGRAPH_AVAILABLE = True
    except ImportError:
        MEMGRAPH_AVAILABLE = False


class MemgraphAdapter:
    """
    Memgraph in-memory graph database adapter.

    Uses Cypher query language; compatible with Neo4j Cypher.
    High-performance streaming graph analytics.

    Configuration:
    {
        "url": "bolt://localhost:7688",
        "username": "",
        "password": ""
    }

    References:
    - https://memgraph.com/docs
    - https://python.langchain.com/docs/integrations/graphs/memgraph
    """

    def __init__(self, config: Dict[str, Any]):
        if not MEMGRAPH_AVAILABLE:
            raise ImportError(
                "langchain-memgraph or langchain-community required. "
                "Install: pip install langchain-memgraph"
            )

        self.config = config
        self.lc_graph = MemgraphGraph(
            url=config.get("url", "bolt://localhost:7688"),
            username=config.get("username", ""),
            password=config.get("password", ""),
        )
        logger.info("Connected to Memgraph at %s", config.get("url", "bolt://localhost:7688"))

    def create_qa_chain(self, llm: Any):
        """Create Cypher QA chain for Memgraph."""
        try:
            from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
        except ImportError:
            from langchain.chains import GraphCypherQAChain  # type: ignore
        return GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    def get_graph(self):
        return self.lc_graph

    def add_graph_documents(self, graph_documents, include_source: bool = False, **kwargs) -> None:
        """Write graph documents to Memgraph using standard Cypher MERGE.

        The default LangChain MemgraphGraph.add_graph_documents calls
        ``CALL merge.node(...)`` and ``CALL merge.relationship(...)`` which are
        MAGE procedures not present in the base Memgraph image.  This override
        uses standard Cypher MERGE / SET so no MAGE installation is required.
        Bolt protocol handles dict parameters correctly (unlike FalkorDB).

        Types are LLM-extracted from document content and Cypher can't parameterize
        a label, so each one goes through cypher_ident (GHSA-g8hp-rhg7-hff5).
        """
        for document in graph_documents:
            for node in document.nodes:
                props = dict(node.properties or {})
                props["id"] = node.id
                props.setdefault("name", node.id)
                self.lc_graph.query(
                    f"MERGE (n:`{cypher_ident(node.type, 'Entity')}` {{id: $id}}) SET n += $props "
                    "RETURN distinct 'done' AS result",
                    params={"id": node.id, "props": props},
                )

            for rel in document.relationships:
                rel_type = cypher_ident(rel.type.replace(" ", "_").upper(), "RELATED_TO")
                self.lc_graph.query(
                    f"MATCH (a:`{cypher_ident(rel.source.type, 'Entity')}` {{id: $src_id}}), "
                    f"(b:`{cypher_ident(rel.target.type, 'Entity')}` {{id: $tgt_id}}) "
                    f"MERGE (a)-[r:`{rel_type}`]->(b) SET r += $props "
                    "RETURN distinct 'done' AS result",
                    params={
                        "src_id": rel.source.id,
                        "tgt_id": rel.target.id,
                        "props": rel.properties or {},
                    },
                )

        try:
            self.lc_graph.refresh_schema()
        except Exception as exc:
            logger.debug("Memgraph refresh_schema after add_graph_documents: %s", exc)

    def delete(self, ref_doc_id: str) -> None:
        """Delete all nodes tagged with *ref_doc_id* from Memgraph using Cypher.

        Memgraph supports parameterized Cypher queries.  We use DETACH DELETE
        so that all incident edges are removed automatically.
        """
        try:
            self.lc_graph.query(
                "MATCH (n) WHERE n.ref_doc_id = $rid DETACH DELETE n",
                params={"rid": ref_doc_id},
            )
            logger.info("Memgraph: deleted nodes for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("Memgraph delete failed for ref_doc_id=%s: %s", ref_doc_id, exc)

    def normalize_entity_names(self) -> None:
        """SET name = id on all nodes that have id but no name.

        LangChain ingestion stores entity names in the ``id`` property.  Our
        add_graph_documents override does not add the ``__Entity__`` label, so
        the standard __Entity__-scoped query would miss all nodes.  Matching
        all nodes is safe — it only sets name where it is not already present.
        """
        try:
            self.lc_graph.query(
                "MATCH (n) WHERE n.name IS NULL AND n.id IS NOT NULL "
                "SET n.name = n.id"
            )
            logger.debug("Memgraph: normalized entity names (id -> name)")
        except Exception as exc:
            logger.warning("Memgraph normalize_entity_names failed: %s", exc)


__all__ = ["MemgraphAdapter", "MEMGRAPH_AVAILABLE"]
