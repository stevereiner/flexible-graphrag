# flexible-graphrag/sparql_ontology_loader.py

from rdflib import Graph, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLStore
from typing import Optional
import logging

class SPARQLOntologyLoader:
    """Load ontology schema from SPARQL endpoints without materializing entire dataset"""
    
    def __init__(self, query_endpoint: str, update_endpoint: Optional[str] = None):
        """
        Args:
            query_endpoint: SPARQL query endpoint URL
            update_endpoint: SPARQL update endpoint URL (optional)
        """
        self.query_endpoint = query_endpoint
        self.update_endpoint = update_endpoint
        self.graph: Optional[Graph] = None
    
    def load_schema_only(self) -> Graph:
        """
        Load only schema information (classes and properties) from SPARQL endpoint
        without materializing the entire dataset
        """
        self.graph = Graph()
        
        # Query 1: Get all class definitions
        class_query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        
        CONSTRUCT {
            ?class a owl:Class ;
                rdfs:label ?label ;
                rdfs:comment ?comment .
        }
        WHERE {
            ?class a owl:Class .
            OPTIONAL { ?class rdfs:label ?label . FILTER(LANG(?label) = "en") }
            OPTIONAL { ?class rdfs:comment ?comment . FILTER(LANG(?comment) = "en") }
        }
        LIMIT 1000
        """
        
        # Query 2: Get all object property definitions with domain/range
        property_query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        
        CONSTRUCT {
            ?prop a owl:ObjectProperty ;
                rdfs:label ?label ;
                rdfs:domain ?domain ;
                rdfs:range ?range .
        }
        WHERE {
            ?prop a owl:ObjectProperty .
            OPTIONAL { ?prop rdfs:label ?label . FILTER(LANG(?label) = "en") }
            OPTIONAL { ?prop rdfs:domain ?domain }
            OPTIONAL { ?prop rdfs:range ?range }
        }
        LIMIT 1000
        """
        
        try:
            store = SPARQLStore(endpoint=self.query_endpoint)
            graph_classes = Graph(store)
            graph_classes.parse(classesQuery=class_query, format="json")
            
            graph_props = Graph(store)
            graph_props.parse(propertiesQuery=property_query, format="json")
            
            self.graph += graph_classes
            self.graph += graph_props
            
            return self.graph
        
        except Exception as e:
            logging.error(f"Failed to load schema from {self.query_endpoint}: {e}")
            raise
    
    def connect_to_store(self) -> Graph:
        """Create a persistent connection to SPARQL endpoint for querying"""
        from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
        
        store = SPARQLUpdateStore()
        store.open((self.query_endpoint, self.update_endpoint or self.query_endpoint))
        
        graph = Graph(store)
        return graph
