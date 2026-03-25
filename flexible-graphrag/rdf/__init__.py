"""
flexible-graphrag RDF and Ontology Support Module

This module provides:
- Ontology-driven knowledge graph extraction using RDF schemas
- Support for multiple RDF store backends (Fuseki, GraphDB, Oxigraph)
- SPARQL query interface for both RDF stores and property graphs
- Unified query engine for routing between property graphs and RDF stores
"""

from .ontology_manager import OntologyManager, OntologyEntity, OntologyRelation
from .store.rdf_store_adapter import RDFStoreAdapter
from .store.rdf_store_factory import RDFStoreFactory
from .store.fuseki_rdf_store_adapter import FusekiAdapter
from .store.ontotext_graphdb_rdf_store_adapter import OntotextGraphDBAdapter
from .store.oxigraph_rdf_store_adapter import OxigraphAdapter
from .unified_query_engine import UnifiedQueryEngine, QueryType, QueryResult
from .sparql_property_graph_wrapper import PropertyGraphSPARQLWrapper

__all__ = [
    # Ontology Management
    "OntologyManager",
    "OntologyEntity",
    "OntologyRelation",
    
    # RDF Store Adapters
    "RDFStoreAdapter",
    "RDFStoreFactory",
    "FusekiAdapter",
    "OntotextGraphDBAdapter",
    "OxigraphAdapter",
    
    # Query Engine
    "UnifiedQueryEngine",
    "QueryType",
    "QueryResult",
    "PropertyGraphSPARQLWrapper",
]
