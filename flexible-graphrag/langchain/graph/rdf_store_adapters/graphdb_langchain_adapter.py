"""
Ontotext GraphDB LangChain Adapter

Uses LangChain's OntotextGraphDBGraph for enhanced capabilities:
- Automatic ontology loading via CONSTRUCT queries or local files
- Optimized schema introspection
- Natural language to SPARQL translation
- Iterative error correction

Advantages over raw RDFLib:
- LangChain QA chains for natural language queries
- Better error handling with iterative correction
- Automatic PREFIX management
- Schema-guided query generation
"""

from typing import Dict, List, Any, Optional
from rdflib import Graph
import os
import logging

try:
    from langchain_community.graphs import OntotextGraphDBGraph
    from langchain_community.chains.graph_qa.sparql import GraphSparqlQAChain
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning("langchain-community not available. Install with: uv pip install langchain langchain-community")

from rdf.store.rdf_store_adapter import RDFStoreAdapter
from rdf.kg_to_rdf_converter import DEFAULT_BASE_NS, DEFAULT_ONTO_NS

_KG_NS     = DEFAULT_BASE_NS.rstrip("/") + "/"
_KG_URI    = DEFAULT_BASE_NS.rstrip("/")
_ONTO_NS   = DEFAULT_ONTO_NS.rstrip("#") + "#"
_COMMON_NS = _ONTO_NS.replace("ontology#", "common#")


class GraphDBLangChainAdapter(RDFStoreAdapter):
    """
    Ontotext GraphDB adapter using LangChain's OntotextGraphDBGraph.
    
    This adapter combines:
    1. LangChain's OntotextGraphDBGraph for querying and natural language support
    2. Direct REST API for efficient bulk loading (store_graph)
    3. RDFLib for local graph manipulation
    
    Architecture follows OntoCast pattern:
    - Construction: RDFLib (local) → bulk load via REST
    - Querying: LangChain (natural language → SPARQL)
    
    Configuration:
    {
        "base_url": "http://localhost:7200",
        "repository": "flexible-graphrag",
        "username": "admin",
        "password": "admin",
        "ontology_file": "./rdf/schemas/company_ontology.ttl",  # Optional
        "ontology_construct_query": "CONSTRUCT {?s ?p ?o} WHERE {?s ?p ?o}"  # Alternative to file
    }
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain-community required for GraphDBLangChainAdapter. "
                "Install with: pip install langchain-community rdflib"
            )
        
        super().__init__(config)
        
        self.base_url = config["base_url"].rstrip("/")
        self.repository = config["repository"]
        self.username = config.get("username")
        self.password = config.get("password")
        
        # Set credentials in environment (LangChain reads from env)
        if self.username:
            os.environ["GRAPHDB_USERNAME"] = self.username
        if self.password:
            os.environ["GRAPHDB_PASSWORD"] = self.password
        
        # Endpoints
        self.query_endpoint = f"{self.base_url}/repositories/{self.repository}"
        self.update_endpoint = f"{self.query_endpoint}/statements"
        
        # Initialize LangChain graph
        # Choose ontology loading method
        ontology_file = config.get("ontology_file")
        ontology_query = config.get("ontology_construct_query")
        
        if not ontology_file and not ontology_query:
            # Default: load schema from the named graph where ingested data lives.
            # Search across all named graphs (FROM NAMED ... / GRAPH ?g) so this
            # works regardless of which named graph the data was loaded into.
            ontology_query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

            CONSTRUCT {
                ?class a owl:Class ;
                       rdfs:label ?classLabel .
                ?prop a owl:ObjectProperty ;
                      rdfs:label ?propLabel ;
                      rdfs:domain ?domain ;
                      rdfs:range ?range .
                ?dprop a owl:DatatypeProperty ;
                       rdfs:label ?dpropLabel ;
                       rdfs:domain ?ddomain ;
                       rdfs:range ?drange .
            }
            WHERE {
                GRAPH ?g {
                    {
                        ?class a owl:Class .
                        OPTIONAL { ?class rdfs:label ?classLabel }
                    }
                    UNION
                    {
                        ?prop a owl:ObjectProperty .
                        OPTIONAL { ?prop rdfs:label ?propLabel }
                        OPTIONAL { ?prop rdfs:domain ?domain }
                        OPTIONAL { ?prop rdfs:range ?range }
                    }
                    UNION
                    {
                        ?dprop a owl:DatatypeProperty .
                        OPTIONAL { ?dprop rdfs:label ?dpropLabel }
                        OPTIONAL { ?dprop rdfs:domain ?ddomain }
                        OPTIONAL { ?dprop rdfs:range ?drange }
                    }
                }
            }
            """

        try:
            self.lc_graph = OntotextGraphDBGraph(
                query_endpoint=self.query_endpoint,
                query_ontology=ontology_query if not ontology_file else None,
                local_file=ontology_file,
                local_file_format=config.get("ontology_format", "turtle") if ontology_file else None
            )
            self.logger.info("Connected to GraphDB via LangChain at %s", self.query_endpoint)
            self._patch_schema_with_instance_ns()
            self.logger.info("Loaded schema: %d chars", len(self.lc_graph.get_schema))
        except ValueError as e:
            if "Missing graph" in str(e) and not ontology_file:
                # Named graph has no OWL schema — fall back to a minimal stub schema
                # so OntotextGraphDBGraph can still be constructed and used for QA.
                self.logger.warning(
                    "GraphDB CONSTRUCT query returned no schema triples "
                    "(ontology not in a named graph?). "
                    "Falling back to minimal stub schema for QA chain. "
                    "Set ONTOLOGY_PATHS or ONTOLOGY_FILE to load schema from a local file."
                )
                import tempfile, os as _os
                _stub = (
                    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
                    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                    f"<{_ONTO_NS}Entity> a owl:Class ; rdfs:label \"Entity\" .\n"
                )
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".ttl", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(_stub)
                    _stub_path = tmp.name
                try:
                    self.lc_graph = OntotextGraphDBGraph(
                        query_endpoint=self.query_endpoint,
                        local_file=_stub_path,
                        local_file_format="turtle",
                    )
                finally:
                    _os.unlink(_stub_path)
                self._patch_schema_with_instance_ns()
                self.logger.info("GraphDB LangChain adapter initialised with stub schema")
            else:
                self.logger.error("Failed to initialize LangChain GraphDB: %s", e)
                raise
        except Exception as e:
            self.logger.error("Failed to initialize LangChain GraphDB: %s", e)
            raise
    
    def _patch_schema_with_instance_ns(self) -> None:
        """Prepend instance-namespace and query-pattern guidance to the schema.

        OntotextGraphDBGraph.schema is the Turtle string the QA chain injects
        verbatim into the LLM prompt.  Without guidance the LLM generates URIs
        like company:acme (ontology prefix for instances) or kg:acme (short slug)
        when the real URI is kg:acme_corporation.

        Strategy: tell the LLM to always use rdfs:label for entity lookup instead
        of guessing slugs, and show the exact predicates actually present in the
        store by querying GraphDB.
        """
        from rdf.kg_to_rdf_converter import DEFAULT_BASE_NS, DEFAULT_ONTO_NS
        kg_ns  = DEFAULT_BASE_NS.rstrip("/") + "/"
        onto_ns = DEFAULT_ONTO_NS.rstrip("#") + "#"

        # Fetch the actual predicates present in the named graph
        live_predicates = self._fetch_live_predicates(kg_ns, onto_ns)
        pred_examples = "\n".join(f"#   <{p}>" for p in live_predicates) if live_predicates else "#   (none found yet — ingest documents first)"

        preamble = (
            f"@prefix kg:   <{kg_ns}> .\n"
            f"@prefix onto: <{onto_ns}> .\n"
            f"\n"
            f"# === CRITICAL QUERY RULES ===\n"
            f"# 1. ALL data is in named graph <{kg_ns.rstrip('/')}>\n"
            f"#    ALWAYS wrap WHERE clause: GRAPH <{kg_ns.rstrip('/')}> {{ ... }}\n"
            f"# 2. Find entities by rdfs:label, NOT by guessing URI slugs:\n"
            f"#    ?x rdfs:label ?name  FILTER(CONTAINS(LCASE(?name), 'keyword'))\n"
            f"# 3. FORBIDDEN: Do NOT use any predicate that is NOT in the list below.\n"
            f"#    The ontology schema may define predicates not yet stored in this graph.\n"
            f"#    If no listed predicate fits the question, use the BROAD FALLBACK below.\n"
            f"#\n"
            f"# === PREDICATES ACTUALLY IN THE STORE ===\n"
            f"{pred_examples}\n"
            f"#\n"
            f"# === EXAMPLE 1: Who works for Acme? ===\n"
            f"# SELECT ?person ?label WHERE {{\n"
            f"#   GRAPH <{kg_ns.rstrip('/')}> {{\n"
            f"#     ?company rdfs:label ?cname  FILTER(CONTAINS(LCASE(?cname), 'acme')) .\n"
            f"#     ?person  ?rel  ?company .\n"
            f"#     ?person  rdfs:label ?label .\n"
            f"#   }}\n"
            f"# }}\n"
            f"#\n"
            f"# === EXAMPLE 2: How is Acme organized? (departments may use PART_OF not HAS_DEPARTMENT) ===\n"
            f"# First try company:has_department; if it returns 0 rows, try employee paths:\n"
            f"# SELECT DISTINCT ?deptLabel ?personLabel WHERE {{\n"
            f"#   GRAPH <{kg_ns.rstrip('/')}> {{\n"
            f"#     ?company rdfs:label ?cname FILTER(CONTAINS(LCASE(?cname), 'acme')) .\n"
            f"#     {{\n"
            f"#       ?dept company:part_of ?company .\n"
            f"#       ?dept rdfs:label ?deptLabel .\n"
            f"#       OPTIONAL {{ ?person company:works_for ?company .\n"
            f"#                  ?person company:works_in_department ?dept .\n"
            f"#                  ?person rdfs:label ?personLabel }}\n"
            f"#     }} UNION {{\n"
            f"#       ?company company:has_department ?dept .\n"
            f"#       ?dept rdfs:label ?deptLabel .\n"
            f"#     }}\n"
            f"#   }}\n"
            f"# }}\n"
            f"#\n"
            f"# === BROAD FALLBACK (when no specific predicate fits) ===\n"
            f"# Use this when the question asks about a keyword and you are unsure\n"
            f"# which predicate to use — find ALL entities related to that keyword:\n"
            f"# SELECT DISTINCT ?entity ?label WHERE {{\n"
            f"#   GRAPH <{kg_ns.rstrip('/')}> {{\n"
            f"#     ?entity ?pred ?related .\n"
            f"#     ?related rdfs:label ?relLabel FILTER(CONTAINS(LCASE(?relLabel), 'keyword')) .\n"
            f"#     OPTIONAL {{ ?entity rdfs:label ?label }}\n"
            f"#   }}\n"
            f"# }}\n"
            f"\n"
        )
        if hasattr(self.lc_graph, "schema"):
            self.lc_graph.schema = preamble + self.lc_graph.schema
            self.logger.info(
                "Patched schema: kg: prefix + %d live predicates", len(live_predicates)
            )

    def _fetch_live_predicates(self, kg_ns: str, onto_ns: str) -> list:
        """Query GraphDB for the distinct semantic predicates in the named graph.

        Excludes rdf/rdfs/owl builtins and onto: provenance predicates so only
        domain predicates (company:, common:, etc.) are shown to the LLM.
        """
        graph_uri = kg_ns.rstrip("/")
        sparql = f"""
SELECT DISTINCT ?p WHERE {{
  GRAPH <{graph_uri}> {{
    ?s ?p ?o
    FILTER(
      !STRSTARTS(STR(?p), 'http://www.w3.org/') &&
      !STRSTARTS(STR(?p), '{onto_ns}')
    )
  }}
}} LIMIT 60
"""
        try:
            results = self.lc_graph.query(sparql)
            return [str(row[0]) for row in results if row[0]]
        except Exception as e:
            self.logger.warning("Could not fetch live predicates: %s", e)
            return []

    def connect(self) -> Any:
        """Connection handled in __init__."""
        return self.lc_graph
    
    def store_graph(self, graph: Graph, graph_uri: Optional[str] = None) -> None:
        """Store RDF graph using direct REST API (faster than SPARQL for bulk).
        
        Uses direct HTTP POST to /statements endpoint for optimal performance.
        This is faster than SPARQL INSERT for large graphs.
        """
        import requests
        
        ttl_data = graph.serialize(format="turtle")
        headers = {"Content-Type": "text/turtle; charset=UTF-8"}
        params = {}
        
        if graph_uri:
            params["context"] = f"<{graph_uri}>"
        
        auth = None
        if self.username and self.password:
            auth = (self.username, self.password)
        
        try:
            resp = requests.post(
                self.update_endpoint,
                data=ttl_data.encode("utf-8"),
                headers=headers,
                params=params,
                auth=auth,
                timeout=120  # Longer timeout for large graphs
            )
            resp.raise_for_status()
            self.logger.info(f"Stored {len(graph)} triples in GraphDB repository '{self.repository}'")
        except Exception as e:
            self.logger.error(f"Failed to store graph in GraphDB: {e}")
            raise
    
    def query_sparql(self, query: str) -> List[Dict[str, Any]]:
        """Execute SPARQL query using LangChain's optimized method.
        
        LangChain handles:
        - Proper PREFIX management
        - Result parsing
        - Error handling
        """
        try:
            results = self.lc_graph.query(query)
            
            # Convert RDFLib ResultRow to dict
            if results and hasattr(results[0], 'asdict'):
                return [
                    {str(var): str(val) for var, val in row.asdict().items()}
                    for row in results
                ]
            elif results:
                # Fallback for different result formats
                return [{"result": str(row)} for row in results]
            else:
                return []
                
        except Exception as e:
            self.logger.error(f"GraphDB SPARQL query failed: {e}")
            raise
    
    def get_schema(self) -> Graph:
        """Get schema from LangChain (already loaded from ontology).
        
        LangChain's OntotextGraphDBGraph loads schema during initialization
        via CONSTRUCT query or local file, providing optimized schema access.
        """
        schema_str = self.lc_graph.get_schema
        
        # Parse Turtle to RDFLib Graph
        g = Graph()
        if schema_str:
            g.parse(data=schema_str, format="turtle")
        
        return g
    
    def create_qa_chain(self, llm: Any):
        """Create LangChain GraphSparqlQAChain for natural language queries.
        
        This enables:
        - Natural language → SPARQL translation
        - Schema-guided query generation
        - Iterative error correction
        - Context-aware responses
        
        Args:
            llm: LangChain LLM (ChatOpenAI, ChatAnthropic, etc.)
        
        Returns:
            GraphSparqlQAChain configured for GraphDB
        """
        return GraphSparqlQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            return_intermediate_steps=True,
            allow_dangerous_requests=True,
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get GraphDB repository statistics.
        
        Returns basic stats about the repository using SPARQL.
        """
        stats_query = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        
        SELECT 
            (COUNT(*) AS ?total_triples)
            (COUNT(DISTINCT ?s) AS ?subjects)
            (COUNT(DISTINCT ?p) AS ?predicates)
            (COUNT(DISTINCT ?o) AS ?objects)
        WHERE {
            ?s ?p ?o
        }
        """
        
        try:
            results = self.query_sparql(stats_query)
            if results:
                return results[0]
            return {}
        except Exception as e:
            self.logger.warning(f"Could not get statistics: {e}")
            return {}
