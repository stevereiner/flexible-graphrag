"""adapters.graph.rdf_store_adapter — RdfGraphStoreAdapter ABC, concrete wrappers, and factory.

The three concrete adapters (Fuseki, Oxigraph, GraphDB) wrap the existing
framework-neutral rdf.store.* implementations.  They live here (rather than
in langchain/) because they are not LangChain-specific — they expose a
LangChain graph lazily only for SPARQL QA retrieval, but ingestion goes
through the raw store adapters.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from config import AppSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------

class RdfGraphStoreAdapter(ABC):
    """Unified interface for RDF graph stores."""

    @abstractmethod
    def store(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        """Store an rdflib Graph or Turtle string."""

    @abstractmethod
    def delete(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        """Delete all triples associated with *ref_doc_id*."""

    @abstractmethod
    def get_lc_graph(self) -> Optional[Any]:
        """Return the LangChain graph object for SPARQL QA chains (or None)."""

    @abstractmethod
    def get_store_adapter(self):
        """Return the underlying low-level RDFStoreAdapter instance."""

    @property
    @abstractmethod
    def store_type(self) -> str:
        """``'fuseki'``, ``'oxigraph'``, or ``'graphdb'``."""


# ---------------------------------------------------------------------------
# Fuseki
# ---------------------------------------------------------------------------

class FusekiGraphAdapter(RdfGraphStoreAdapter):
    """Thin wrapper over :class:`rdf.store.FusekiAdapter`."""

    def __init__(self, config: Dict[str, Any]):
        from rdf.store.fuseki_rdf_store_adapter import FusekiAdapter
        self._adapter = FusekiAdapter(config)
        self._lc_graph = None

    def store(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        self._adapter.store_rdf_annotations(graph_or_turtle, graph_uri=graph_uri)

    def delete(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        self._adapter.delete_doc(ref_doc_id, graph_uri=graph_uri)

    def get_lc_graph(self):
        if self._lc_graph is not None:
            return self._lc_graph
        try:
            from langchain.graph.rdf_store_adapters.fuseki_langchain_adapter import FusekiLangChainAdapter
            self._lc_graph = FusekiLangChainAdapter(self._adapter.config).lc_graph
        except Exception as exc:
            logger.debug(f"FusekiGraphAdapter: could not build LangChain graph: {exc}")
        return self._lc_graph

    def get_store_adapter(self):
        return self._adapter

    @property
    def store_type(self) -> str:
        return "fuseki"


# ---------------------------------------------------------------------------
# Oxigraph
# ---------------------------------------------------------------------------

class OxigraphGraphAdapter(RdfGraphStoreAdapter):
    """Thin wrapper over :class:`rdf.store.OxigraphAdapter`."""

    def __init__(self, config: Dict[str, Any]):
        from rdf.store.oxigraph_rdf_store_adapter import OxigraphAdapter
        self._adapter = OxigraphAdapter(config)
        self._lc_graph = None

    def store(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        self._adapter.store_rdf_annotations(graph_or_turtle, graph_uri=graph_uri)

    def delete(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        self._adapter.delete_doc(ref_doc_id, graph_uri=graph_uri)

    def get_lc_graph(self):
        if self._lc_graph is not None:
            return self._lc_graph
        try:
            from langchain.graph.rdf_store_adapters.oxigraph_langchain_adapter import OxigraphLangChainAdapter
            self._lc_graph = OxigraphLangChainAdapter(self._adapter.config).lc_graph
        except Exception as exc:
            logger.debug(f"OxigraphGraphAdapter: could not build LangChain graph: {exc}")
        return self._lc_graph

    def get_store_adapter(self):
        return self._adapter

    @property
    def store_type(self) -> str:
        return "oxigraph"


# ---------------------------------------------------------------------------
# Ontotext GraphDB
# ---------------------------------------------------------------------------

class OntotextGraphAdapter(RdfGraphStoreAdapter):
    """Thin wrapper over :class:`rdf.store.OntotextGraphDBAdapter`."""

    def __init__(self, config: Dict[str, Any]):
        from rdf.store.ontotext_graphdb_rdf_store_adapter import OntotextGraphDBAdapter
        self._adapter = OntotextGraphDBAdapter(config)
        self._lc_graph = None

    def store(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        self._adapter.store_rdf_annotations(graph_or_turtle, graph_uri=graph_uri)

    def delete(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        self._adapter.delete_doc(ref_doc_id, graph_uri=graph_uri)

    def get_lc_graph(self):
        if self._lc_graph is not None:
            return self._lc_graph
        try:
            from langchain.graph.rdf_store_adapters.graphdb_langchain_adapter import GraphDBLangChainAdapter
            self._lc_graph = GraphDBLangChainAdapter(self._adapter.config).lc_graph
        except Exception as exc:
            logger.debug(f"OntotextGraphAdapter: could not build LangChain graph: {exc}")
        return self._lc_graph

    def get_store_adapter(self):
        return self._adapter

    @property
    def store_type(self) -> str:
        return "graphdb"


# ---------------------------------------------------------------------------
# Amazon Neptune RDF/SPARQL
# ---------------------------------------------------------------------------

class NeptuneRdfGraphAdapter(RdfGraphStoreAdapter):
    """Adapter for Amazon Neptune in RDF/SPARQL mode.

    Ingestion uses direct SPARQL INSERT via langchain_aws.graphs.NeptuneRdfGraph.
    Retrieval uses create_neptune_sparql_qa_chain (LangChain NL → SPARQL).
    """

    def __init__(self, config: Dict[str, Any]):
        from langchain.graph.rdf_store_adapters.neptune_rdf_adapter import NeptuneRDFAdapter
        self._adapter = NeptuneRDFAdapter(config)
        # NeptuneRDFAdapter already holds lc_graph
        self._lc_graph = self._adapter.lc_graph

    def store(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        # Delegate to store_rdf_annotations so Neptune gets provenance triples
        # (onto:ref_doc_id) alongside the plain entity/relation triples.
        # store_graph() strips annotation blocks and loses the ref_doc_id provenance
        # needed for delete(); store_rdf_annotations() preserves them.
        self._adapter.store_rdf_annotations(graph_or_turtle, graph_uri=graph_uri)

    def delete(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        # Neptune SPARQL DELETE WHERE for this ref_doc_id
        graph_clause = f"GRAPH <{graph_uri}>" if graph_uri else ""
        onto_prefix = "https://integratedsemantics.org/flexible-graphrag/ontology#"
        escaped = ref_doc_id.replace("\\", "\\\\").replace('"', '\\"')
        sparql = (
            f"PREFIX onto: <{onto_prefix}>\n"
            f"DELETE WHERE {{ {graph_clause} {{ ?s onto:ref_doc_id \"{escaped}\" . ?s ?p ?o }} }}"
        )
        try:
            self._adapter._sparql_update(sparql)
            logger.debug("NeptuneRdfGraphAdapter: deleted triples for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("NeptuneRdfGraphAdapter: delete failed for %s: %s", ref_doc_id, exc)

    def get_lc_graph(self):
        return self._lc_graph

    def get_store_adapter(self):
        return self._adapter

    @property
    def store_type(self) -> str:
        return "neptune_rdf"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_rdf_store_adapter(config: "AppSettings") -> Optional[RdfGraphStoreAdapter]:
    """Build a :class:`RdfGraphStoreAdapter` from ``config.rdf_graph_db``.

    Returns ``None`` when ``rdf_graph_db`` is ``RdfGraphType.NONE`` or not set.
    """
    rdf_graph_db = getattr(config, "rdf_graph_db", None)
    if rdf_graph_db is None:
        return None

    rdf_type_str = str(rdf_graph_db).lower().replace("rdfgraphtype.", "")
    if rdf_type_str in ("none", ""):
        return None

    rdf_store_config = config.get_rdf_store_config()
    if not rdf_store_config:
        return None

    # get_rdf_store_config() returns {"name": ..., "type": ..., "config": {...}}
    # The concrete adapters expect only the inner flat config dict.
    inner_config = rdf_store_config.get("config", rdf_store_config)

    # For GraphDB, resolve ontology file from AppSettings so get_lc_graph() can
    # build GraphDBLangChainAdapter with the local ontology (avoids a CONSTRUCT
    # query against GraphDB which returns nothing when ontology isn't in the store).
    if rdf_type_str == "graphdb":
        try:
            from rdf.ontology_manager import resolve_user_config_path as _resolve_path
            import os as _os, glob as _glob
            ontology_file = None
            ontology_dir = getattr(config, "ontology_dir", None)
            ontology_paths = getattr(config, "ontology_paths", None)
            ontology_path = getattr(config, "ontology_path", None)
            if ontology_dir:
                _dir = _resolve_path(ontology_dir)
                ttl_files = sorted(_glob.glob(_os.path.join(_dir, "*.ttl")))
                if ttl_files:
                    ontology_file = ttl_files[0]
            elif ontology_paths:
                first = ontology_paths.split(",")[0].strip()
                if first:
                    ontology_file = _resolve_path(first)
            elif ontology_path:
                ontology_file = _resolve_path(ontology_path)
            if ontology_file:
                inner_config = dict(inner_config)
                inner_config["ontology_file"] = ontology_file
                logger.debug("GraphDB adapter: ontology_file resolved to %s", ontology_file)
        except Exception as _exc:
            logger.debug("GraphDB adapter: could not resolve ontology file: %s", _exc)

    if rdf_type_str == "fuseki":
        logger.info("RDF adapter: Fuseki")
        return FusekiGraphAdapter(inner_config)
    elif rdf_type_str == "oxigraph":
        logger.info("RDF adapter: Oxigraph")
        return OxigraphGraphAdapter(inner_config)
    elif rdf_type_str == "graphdb":
        logger.info("RDF adapter: Ontotext GraphDB")
        return OntotextGraphAdapter(inner_config)
    elif rdf_type_str == "neptune_rdf":
        logger.info("RDF adapter: Amazon Neptune (SPARQL/RDF)")
        return NeptuneRdfGraphAdapter(inner_config)
    else:
        logger.warning("Unknown rdf_graph_db value '%s', no RDF adapter created", rdf_type_str)
        return None
