"""LangChain Google Cloud Spanner Graph adapter (langchain-google-spanner >= 0.10.0, LangChain 1.x)."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

# The Spanner client exports built-in metrics to Cloud Monitoring by default; outside GCE that
# logs "Failed to export metrics" errors on every request.
os.environ.setdefault("SPANNER_DISABLE_BUILTIN_METRICS", "true")

logger = logging.getLogger(__name__)

try:
    from langchain_google_spanner import SpannerGraphStore
    SPANNER_AVAILABLE = True
except ImportError:
    SpannerGraphStore = None  # type: ignore[assignment,misc]
    SPANNER_AVAILABLE = False

# The label of the chunk ("source") nodes this adapter writes
CHUNK_LABEL = "Document"


class SpannerGraphAdapter:
    """
    Google Cloud Spanner Graph adapter (GQL).

    Uses the flexible schema: one ``<graph>_NODE`` and one ``<graph>_EDGE`` table, created on
    first ingest, with the entity / relationship type in ``label`` and the other properties in
    a JSON ``properties`` column. ``SpannerGraphStore`` writes no source nodes, so this adapter
    writes one ``Document`` node per chunk and its ``MENTIONS`` edges to the chunk's entities:
    the Graph tab, scoped questions and the delete find a document's graph through them.

    Configuration (SPANNER_GRAPH_DB_CONFIG):
    {
        "project_id": "my-gcp-project",
        "instance_id": "my-spanner-instance",
        "database_id": "my-database",
        "graph_name": "knowledge_graph",
        "credentials_file": "./spanner-sa.json"
    }

    The LlamaIndex store uses the same table names for the same graph name: use a graph name of
    its own for the LangChain backend if both write to one database.

    References:
    - https://cloud.google.com/spanner/docs/graph/overview
    """

    def __init__(self, config: Dict[str, Any]):
        if not SPANNER_AVAILABLE:
            raise ImportError(
                "langchain-google-spanner >= 0.10.0 is required for the LangChain Spanner graph store. "
                "Install: uv pip install \"langchain-google-spanner>=0.10.0\""
            )
        from adapters.graph.spanner_graph import make_client

        self.config = config
        instance_id = config.get("instance_id") or config.get("instance")
        database_id = config.get("database_id") or config.get("database")
        if not instance_id or not database_id:
            raise ValueError("Spanner config requires 'instance_id' and 'database_id'")
        self.graph_name = config.get("graph_name") or config.get("graph") or "knowledge_graph"
        self.lc_graph = SpannerGraphStore(
            instance_id=instance_id,
            database_id=database_id,
            graph_name=self.graph_name,
            client=make_client(config),
            use_flexible_schema=True,
        )
        logger.info("Connected to Spanner Graph %s (instance %s, database %s)",
                    self.graph_name, instance_id, database_id)

    # ------------------------------------------------------------------ queries

    def _gql(self, gql: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        return self.lc_graph.query(f"GRAPH `{self.graph_name}`\n" + gql, params or {})

    def _tables(self):
        schema = self.lc_graph.schema
        node = next(iter(schema.node_tables.values())).base_table_name if schema.node_tables else None
        edge = next(iter(schema.edge_tables.values())).base_table_name if schema.edge_tables else None
        return node, edge

    # ------------------------------------------------------------------ writes

    def add_graph_documents(self, graph_documents: List[Any], include_source: bool = False, **kwargs) -> None:
        """Write the entities and relationships (SpannerGraphStore), then, with
        ``include_source``, each chunk as a ``Document`` node and its ``MENTIONS`` edges."""
        from langchain_community.graphs.graph_document import GraphDocument, Node, Relationship
        from hashlib import md5

        sources = []
        for doc in graph_documents:
            meta = (doc.source.metadata or {}) if getattr(doc, "source", None) is not None else {}
            rid = meta.get("ref_doc_id") or meta.get("doc_id") or ""
            if rid:
                for node in doc.nodes:
                    node.properties.setdefault("ref_doc_id", rid)
                for rel in doc.relationships:
                    rel.properties.setdefault("doc_id", rid)
            sources.append((doc, meta, rid))
        self.lc_graph.add_graph_documents(graph_documents)  # include_source is not supported by it

        if not include_source:
            return
        chunk_docs = []
        for doc, meta, rid in sources:
            if getattr(doc, "source", None) is None:
                continue
            text = doc.source.page_content or ""
            chunk = Node(id=str(meta.get("id") or md5(f"{rid}|{text}".encode("utf-8")).hexdigest()),
                         type=CHUNK_LABEL,
                         properties={k: v for k, v in (("text", text), ("ref_doc_id", rid), ("doc_id", rid),
                                                       ("file_name", meta.get("file_name")))
                                     if v not in (None, "")})
            ends = {(n.type, str(n.id)): n for n in doc.nodes}
            for rel in doc.relationships:
                for end in (rel.source, rel.target):
                    ends.setdefault((end.type, str(end.id)), end)
            chunk_docs.append(GraphDocument(
                nodes=[chunk],
                relationships=[Relationship(source=chunk, target=Node(id=n.id, type=n.type), type="MENTIONS")
                               for n in ends.values()],
                source=doc.source))
        if chunk_docs:
            self.lc_graph.add_graph_documents(chunk_docs)

    def delete(self, ref_doc_id: str) -> None:
        """Delete one document's graph data, leaving what other documents share
        (adapters.graph.spanner_graph.delete_document)."""
        from adapters.graph.spanner_graph import delete_document
        node_table, edge_table = self._tables()
        if node_table is None:
            return
        try:
            n = delete_document(self._gql, self.lc_graph.impl, node_table, edge_table, ref_doc_id, CHUNK_LABEL)
            logger.info("Spanner: deleted graph data of ref_doc_id=%s: %s", ref_doc_id, n)
        except Exception as exc:
            logger.warning("Spanner delete failed for ref_doc_id=%s: %s", ref_doc_id, exc)

    def scoped_facts(self, doc_ids: List[str]) -> List[tuple]:
        """(subject, relation, object, doc_id) of the given documents' graph."""
        from adapters.graph.spanner_graph import scoped_facts
        if self._tables()[0] is None:
            return []
        return scoped_facts(self._gql, doc_ids, CHUNK_LABEL)

    # ------------------------------------------------------------------ QA

    def create_qa_chain(self, llm: Any):
        """GQL QA chain for Spanner Graph (SpannerGraphQAChain)."""
        from langchain_google_spanner import SpannerGraphQAChain
        return SpannerGraphQAChain.from_llm(llm=llm, graph=self.lc_graph, verbose=False,
                                            allow_dangerous_requests=True)

    def get_graph(self):
        return self.lc_graph

    def normalize_entity_names(self) -> None:
        """No-op: an entity's id is its name (LangChain), and the flexible schema has no name column."""
        logger.debug("Spanner: entity names are their ids — normalize_entity_names skipped")


__all__ = ["SpannerGraphAdapter", "SPANNER_AVAILABLE"]
