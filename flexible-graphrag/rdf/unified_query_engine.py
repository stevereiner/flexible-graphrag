# flexible-graphrag/unified_query_engine.py

from enum import Enum
from typing import Union, List, Dict, Any, Optional
from dataclasses import dataclass
import logging

class QueryType(Enum):
    SPARQL = "sparql"
    CYPHER = "cypher"
    NATURAL_LANGUAGE = "natural_language"

@dataclass
class QueryResult:
    query_type: QueryType
    backend: str  # "neo4j", "fuseki", "sparql_endpoint", etc.
    raw_results: Any
    formatted_results: List[Dict[str, Any]]

class UnifiedQueryEngine:
    """Route queries to appropriate backend (property graph or RDF store)"""
    
    def __init__(self, property_graph_index=None, rdf_stores: Dict[str, Any] = None):
        """
        Args:
            property_graph_index: LlamaIndex PropertyGraphIndex
            rdf_stores: Dict mapping store names to RDF store adapters
        """
        self.property_graph_index = property_graph_index
        self.rdf_stores = rdf_stores or {}
        self.logger = logging.getLogger(__name__)
    
    def query(
        self,
        query_text: str,
        query_type: QueryType = QueryType.NATURAL_LANGUAGE,
        target_backend: Optional[str] = None
    ) -> QueryResult:
        """
        Execute query against appropriate backend
        
        Args:
            query_text: Query text (SPARQL, Cypher, or natural language)
            query_type: Type of query
            target_backend: Specific backend to target (optional)
        
        Returns:
            QueryResult with formatted results
        """
        
        if query_type == QueryType.SPARQL:
            return self._execute_sparql(query_text, target_backend)
        elif query_type == QueryType.CYPHER:
            return self._execute_cypher(query_text, target_backend)
        elif query_type == QueryType.NATURAL_LANGUAGE:
            return self._execute_natural_language(query_text, target_backend)
    
    def _execute_sparql(self, query: str, target_backend: Optional[str] = None) -> QueryResult:
        """Execute SPARQL query against RDF store or wrapped property graph"""
        
        # If target specified, use that RDF store
        if target_backend and target_backend in self.rdf_stores:
            store = self.rdf_stores[target_backend]
            results = store.query_sparql(query)
            return QueryResult(
                query_type=QueryType.SPARQL,
                backend=target_backend,
                raw_results=results,
                formatted_results=results
            )
        
        # Otherwise, try property graph SPARQL wrapper
        if self.property_graph_index:
            from .sparql_property_graph_wrapper import PropertyGraphSPARQLWrapper
            wrapper = PropertyGraphSPARQLWrapper(
                self.property_graph_index.property_graph_store
            )
            results = wrapper.query_sparql(query)
            return QueryResult(
                query_type=QueryType.SPARQL,
                backend="property_graph_rdf_wrapper",
                raw_results=results,
                formatted_results=results
            )
        
        raise ValueError("No SPARQL endpoint available")
    
    def _execute_cypher(self, query: str, target_backend: Optional[str] = None) -> QueryResult:
        """Execute Cypher query against property graph"""
        
        if not self.property_graph_index:
            raise ValueError("PropertyGraphIndex required for Cypher queries")
        
        results = self.property_graph_index.property_graph_store.structured_query(query)
        
        return QueryResult(
            query_type=QueryType.CYPHER,
            backend=target_backend or "property_graph",
            raw_results=results,
            formatted_results=results
        )
    
    def _execute_natural_language(self, query_text: str, target_backend: Optional[str] = None) -> QueryResult:
        """Execute natural language query using LLM-based query engine"""
        
        results = []
        
        if self.property_graph_index:
            # Use LlamaIndex query engine (TextToCypher + graph/vector retrievers)
            query_engine = self.property_graph_index.as_query_engine()
            response = query_engine.query(query_text)
            results.append({
                "backend": "property_graph",
                "response": str(response)
            })
        
        if self.rdf_stores and (not target_backend or target_backend != "property_graph"):
            # TODO: Use LLM to generate SPARQL; placeholder now
            sparql_query = self._llm_generate_sparql(query_text)
            for store_name, store in self.rdf_stores.items():
                if not target_backend or store_name == target_backend:
                    try:
                        store_results = store.query_sparql(sparql_query)
                        results.append({
                            "backend": store_name,
                            "sparql_query": sparql_query,
                            "results": store_results
                        })
                    except Exception as e:
                        self.logger.warning(f"SPARQL query failed against {store_name}: {e}")
        
        return QueryResult(
            query_type=QueryType.NATURAL_LANGUAGE,
            backend=target_backend or "hybrid",
            raw_results=results,
            formatted_results=results
        )
    
    def _llm_generate_sparql(self, query_text: str) -> str:
        """Use LLM to generate SPARQL from natural language query"""
        # Implementation would use LLM chain to generate SPARQL
        raise NotImplementedError("LLM-based SPARQL generation in progress")
