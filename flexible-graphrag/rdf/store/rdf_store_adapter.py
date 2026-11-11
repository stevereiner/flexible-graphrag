# flexible-graphrag/rdf_store_adapter.py

from typing import Optional, Dict, List, Any
from rdflib import Graph, URIRef, Namespace
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from abc import ABC, abstractmethod
import logging

ONTO_NS = "https://integratedsemantics.org/flexible-graphrag/ontology#"


def shared_delete_update(ref_doc_id: str, graph_uri: Optional[str], reifiers: bool = False,
                         annotations: bool = True) -> str:
    """SPARQL Update that takes one document out of the RDF store, keeping what other documents
    share with it.

    Every entity, and every relation annotation, carries one onto:ref_doc_id stamp per document
    it came from (KGToRDFConverter). Its operations run in order:
    1. Relations only this document has: the relation triple and its annotations.
    2. Entities only this document has: all their triples.
    3. What other documents still have: just this document's stamp.

    Where a relation's {| |} annotations go depends on the store:
    * ``reifiers=False`` -- GraphDB, Fuseki (Jena 5.1): on the quoted triple itself
      (``<< s p o >> onto:ref_doc_id "d"``), one subject for every document's annotation.
    * ``reifiers=True`` -- Oxigraph 0.5 (RDF 1.2): each {| |} block is its own reifier,
      ``_:r rdf:reifies <<( s p o )>> ; onto:ref_doc_id "d"``.
    * ``annotations=False`` -- Neptune: no RDF-star, the annotations are dropped (relations
      carry no stamp) and step 1 is skipped; a relation goes with its subject entity.
    """
    g = f"GRAPH <{graph_uri}>" if graph_uri else "GRAPH ?g"
    d = '"' + ref_doc_id.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def stamped(s: str, var: str = "?d") -> str:
        return f"{s} onto:ref_doc_id {var} . FILTER(STR({var}) = {d})"

    def no_other(s: str) -> str:
        """no other document's stamp on ``s``"""
        return f"FILTER NOT EXISTS {{ {s} onto:ref_doc_id ?other . FILTER(STR(?other) != {d}) }}"

    if not annotations:
        relations = ""
    elif reifiers:
        fact = "<<( ?s ?p ?o )>>"
        relations = f"""DELETE {{ {g} {{ ?s ?p ?o . ?r ?rp ?rv }} }}
WHERE  {{ {g} {{
  ?mine rdf:reifies {fact} . {stamped("?mine")}
  FILTER NOT EXISTS {{ ?theirs rdf:reifies {fact} ; onto:ref_doc_id ?other . FILTER(STR(?other) != {d}) }}
  ?r rdf:reifies {fact} ; ?rp ?rv
}} }} ;

DELETE {{ {g} {{ ?r ?rp ?rv }} }}
WHERE  {{ {g} {{
  ?r rdf:reifies ?t . {stamped("?r")}
  {no_other("?r")}
  ?r ?rp ?rv
}} }} ;"""
    else:
        relations = f"""DELETE {{ {g} {{ ?s ?p ?o . << ?s ?p ?o >> ?ap ?av }} }}
WHERE  {{ {g} {{
  {stamped("<< ?s ?p ?o >>")}
  {no_other("<< ?s ?p ?o >>")}
  << ?s ?p ?o >> ?ap ?av
}} }} ;"""

    return f"""PREFIX onto: <{ONTO_NS}>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

{relations}

DELETE {{ {g} {{ ?e ?ep ?ev }} }}
WHERE  {{ {g} {{
  {stamped("?e")}
  {no_other("?e")}
  ?e ?ep ?ev
}} }} ;

DELETE {{ {g} {{ ?x onto:ref_doc_id ?d }} }}
WHERE  {{ {g} {{ {stamped("?x")} }} }}
"""


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
        """Take a document out of the store, keeping what other documents share with it
        (shared_delete_update).

        Subclasses should override for store-specific SPARQL UPDATE endpoints.
        The default implementation issues the update via query_sparql() which some
        adapters route to a read endpoint — override when needed.
        """
        delete_query = shared_delete_update(ref_doc_id, graph_uri)
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


