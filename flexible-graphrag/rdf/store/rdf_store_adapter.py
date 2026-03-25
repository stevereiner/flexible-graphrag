# flexible-graphrag/rdf_store_adapter.py

from typing import Optional, Dict, List, Any
from rdflib import Graph, URIRef, Namespace
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from abc import ABC, abstractmethod
import logging

class RDFStoreAdapter(ABC):
    """Abstract base for RDF store adapters"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def connect(self) -> Any:
        """Establish connection to RDF store"""
        pass
    
    @abstractmethod
    def store_graph(self, graph: Graph, graph_uri: Optional[str] = None) -> None:
        """Store RDF graph in the store (plain Turtle, no RDF-star)"""
        pass

    def store_rdf_annotations(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        """Store a Turtle document (with optional relation-property annotations) into the store.

        Accepts either a raw Turtle string (str) built by KGToRDFConverter, which
        may contain RDF 1.2 {| |} annotations, legacy << >> RDF-star lines, or plain
        triples depending on RDF_ANNOTATION_SYNTAX — or a plain rdflib.Graph.

        Subclasses override to support native ingestion via their HTTP endpoints.
        The default implementation handles plain Graph objects via store_graph().
        If a Turtle string is passed and the subclass does not override, annotations
        are dropped with a warning (rdflib 7.x cannot parse annotation syntax).
        """
        if isinstance(graph_or_turtle, str):
            import logging
            logging.getLogger(self.__class__.__name__).warning(
                "store_rdf_annotations received a Turtle string but this adapter "
                "does not override it. Relation-property annotations will be dropped."
            )
        else:
            self.store_graph(graph_or_turtle, graph_uri=graph_uri)

    def delete_doc(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        """Delete all triples belonging to a specific document from the store.

        Two-pass delete:
        1. Entity/plain triples whose subject has onto:ref_doc_id.
        2. Reifier annotation triples (blank-node or IRI reifiers) whose subject has
           onto:ref_doc_id — this catches RDF 1.2 {| |} and rdf_star << >> reifiers
           now that onto:ref_doc_id is always written into every annotation block.

        Subclasses should override for store-specific SPARQL UPDATE endpoints.
        The default implementation issues the update via query_sparql() which some
        adapters route to a read endpoint — override when needed.
        """
        onto_ns = "https://integratedsemantics.org/flexible-graphrag/ontology#"
        graph_clause = f"GRAPH <{graph_uri}>" if graph_uri else "GRAPH ?g"
        escaped = ref_doc_id.replace("\\", "\\\\").replace('"', '\\"')
        delete_query = f"""PREFIX onto: <{onto_ns}>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

DELETE {{ {graph_clause} {{ ?s ?p ?o }} }}
WHERE  {{ {graph_clause} {{ ?s ?p ?o ; onto:ref_doc_id "{escaped}" }} }} ;

DELETE {{ {graph_clause} {{ ?reifier ?rp ?ro }} }}
WHERE  {{
  {graph_clause} {{
    ?reifier onto:ref_doc_id "{escaped}" .
    ?reifier ?rp ?ro .
    FILTER(isBlank(?reifier) || (isIRI(?reifier) && STRSTARTS(STR(?reifier), "urn:")))
  }}
}}
"""
        try:
            self.query_sparql(delete_query)
            self.logger.info(
                "Deleted triples for ref_doc_id='%s' from graph <%s>",
                ref_doc_id, graph_uri or "default",
            )
        except Exception as e:
            self.logger.warning(
                "Could not delete stale triples for ref_doc_id='%s': %s - proceeding with append",
                ref_doc_id, e,
            )

    @abstractmethod
    def query_sparql(self, query: str) -> List[Dict]:
        """Execute SPARQL query"""
        pass
    
    @abstractmethod
    def get_schema(self) -> Graph:
        """Extract schema information"""
        pass


