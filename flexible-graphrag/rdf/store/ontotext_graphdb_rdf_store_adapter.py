# flexible_graphrag/rdf_store_adapter.py (GraphDB part)

from typing import Optional, Dict, List, Any
from rdflib import Graph, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from .rdf_store_adapter import RDFStoreAdapter
import logging
import requests

class OntotextGraphDBAdapter(RDFStoreAdapter):
    """
    Ontotext GraphDB RDF Store Adapter.

    Exposes:
      - SPARQL query endpoint:  {base_url}/repositories/{repository}
      - SPARQL update endpoint: {base_url}/repositories/{repository}/statements

    GraphDB Workbench (web console) runs at:
      - http://localhost:7200/
    """

    def __init__(self, config: Dict[str, str]):
        """
        Config:
        {
          "base_url": "http://localhost:7200",
          "repository": "myrepo",
          "username": "admin",          # optional
          "password": "root"           # optional
        }
        """
        super().__init__(config)
        self.base_url = config["base_url"].rstrip("/")
        self.repository = config["repository"]
        self.username = config.get("username")
        self.password = config.get("password")

        self.query_endpoint = f"{self.base_url}/repositories/{self.repository}"
        self.update_endpoint = f"{self.base_url}/repositories/{self.repository}/statements"
        self.graph: Optional[Graph] = None

    def connect(self) -> Graph:
        """Connect to GraphDB via SPARQLUpdateStore, auto-creating the repository if needed."""
        self._ensure_repository_exists()
        store = SPARQLUpdateStore()
        store.open((self.query_endpoint, self.update_endpoint))
        self.graph = Graph(store)
        self.logger.info(f"Connected to GraphDB at {self.query_endpoint}")
        return self.graph

    def _ensure_repository_exists(self) -> None:
        """Create the GraphDB repository if it doesn't exist yet.

        Uses the GraphDB REST API (multipart/form-data with a Turtle config file)
        to create the repository with RDF 1.2 annotation support enabled.
        """
        check_url = f"{self.base_url}/rest/repositories/{self.repository}"
        auth = (self.username, self.password) if self.username and self.password else None

        try:
            resp = requests.get(check_url, auth=auth, timeout=10)
            if resp.status_code == 200:
                self.logger.debug("GraphDB repository '%s' already exists", self.repository)
                return
        except Exception as e:
            self.logger.warning("Could not check GraphDB repository existence: %s", e)
            return

        # Repository does not exist — create it via multipart/form-data POST
        self.logger.info(
            "GraphDB repository '%s' not found — creating it with RDF 1.2 support...",
            self.repository,
        )
        config_ttl = f"""@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rep:  <http://www.openrdf.org/config/repository#> .
@prefix sr:   <http://www.openrdf.org/config/repository/sail#> .
@prefix sail: <http://www.openrdf.org/config/sail#> .
@prefix graphdb: <http://www.ontotext.com/config/graphdb#> .

[] a rep:Repository ;
   rep:repositoryID "{self.repository}" ;
   rdfs:label "{self.repository}" ;
   rep:repositoryImpl [
       rep:repositoryType "graphdb:SailRepository" ;
       sr:sailImpl [
           sail:sailType "graphdb:Sail" ;
           graphdb:ruleset "rdfsplus-optimized" ;
           graphdb:enableRDFStarSupport "true" ;
           graphdb:entity-id-size "32" ;
           graphdb:entity-index-size "10000000" ;
           graphdb:enable-context-index "true" ;
           graphdb:enablePredicateList "true" ;
           graphdb:in-memory-literal-properties "true" ;
           graphdb:enable-literal-index "true" ;
           graphdb:base-URL "http://example.org/owlim#" ;
           graphdb:repository-type "file-repository" ;
           graphdb:storage-folder "storage" ;
       ]
   ] .
"""
        create_url = f"{self.base_url}/rest/repositories"
        try:
            resp = requests.post(
                create_url,
                files={"config": ("repo-config.ttl", config_ttl.encode("utf-8"), "text/turtle")},
                auth=auth,
                timeout=30,
            )
            resp.raise_for_status()
            self.logger.info(
                "GraphDB repository '%s' created successfully with RDF 1.2 support",
                self.repository,
            )
        except Exception as e:
            self.logger.error(
                "Failed to auto-create GraphDB repository '%s': %s. "
                "Create it manually in the Workbench: Setup -> Repositories -> Create, "
                "enable 'RDF-star support'.",
                self.repository, e,
            )

    def store_graph(self, graph: Graph, graph_uri: Optional[str] = None) -> None:
        """Store RDF graph in GraphDB using the /statements REST endpoint (plain Turtle)."""
        self._post_graph(graph, graph_uri, content_type="text/turtle; charset=UTF-8")

    def store_rdf_annotations(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        """Store a Turtle document (with optional relation-property annotations) in GraphDB.

        Accepts either:
          - a Turtle string (str) from KGToRDFConverter — preferred; may contain
            RDF 1.2 {| |} annotations, legacy << >> lines, or plain triples.
          - an rdflib.Graph — serialized as plain Turtle (no annotations).

        GraphDB accepts standard ``text/turtle`` for all annotation syntaxes.
        """
        self._post_graph(graph_or_turtle, graph_uri, content_type="text/turtle; charset=UTF-8")

    def _post_graph(
        self, graph_or_turtle, graph_uri: Optional[str], content_type: str
    ) -> None:
        """POST serialized graph to GraphDB /statements endpoint (append)."""
        if self.graph is None:
            self.connect()

        if isinstance(graph_or_turtle, str):
            ttl_data = graph_or_turtle
            triple_count = ttl_data.count(" .")
        else:
            try:
                ttl_data = graph_or_turtle.serialize(format="turtle")
            except Exception:
                ttl_data = graph_or_turtle.serialize(format="n3")
            triple_count = len(graph_or_turtle)

        headers = {"Content-Type": content_type}
        params: Dict[str, str] = {}
        if graph_uri:
            params["context"] = f"<{graph_uri}>"

        auth = None
        if self.username and self.password:
            auth = (self.username, self.password)

        self.logger.debug(
            "GraphDB store_rdf_annotations: posting %d chars to %s (graph_uri=%s)",
            len(ttl_data), self.update_endpoint, graph_uri,
        )
        if "ref_doc_id" in ttl_data:
            self.logger.debug("GraphDB store_rdf_annotations: Turtle CONTAINS ref_doc_id annotation")
        else:
            self.logger.debug("GraphDB store_rdf_annotations: Turtle does NOT contain ref_doc_id annotation")
        try:
            resp = requests.post(
                self.update_endpoint,
                data=ttl_data.encode("utf-8"),
                headers=headers,
                params=params,
                auth=auth,
                timeout=60,
            )
            resp.raise_for_status()
            self.logger.info(
                "Stored ~%d triples in GraphDB repository '%s'",
                triple_count, self.repository,
            )
        except Exception as e:
            self.logger.error(f"Failed to store graph in GraphDB: {e}")
            raise

    def delete_doc(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        """Delete all triples for a specific document from GraphDB via SPARQL UPDATE.

        Two-pass delete:
        1. Delete entity/plain triples whose subject has onto:ref_doc_id (entity nodes).
        2. Delete RDF-star reifier triples — GraphDB stores {| |} annotation reifiers
           as <urn:rdf4j:triple:BASE64> IRIs.  These are queryable as ordinary IRI
           subjects when filtered by STRSTARTS(..., "urn:rdf4j:triple:"), which is
           reliable standard SPARQL without requiring RDF-star triple-pattern syntax
           in the UPDATE clause (which GraphDB may not support in SPARQL UPDATE).
        Both passes sent as a single SPARQL Update with a semicolon separator.
        """
        onto_ns = "https://integratedsemantics.org/flexible-graphrag/ontology#"
        graph_clause = f"GRAPH <{graph_uri}>" if graph_uri else "GRAPH ?g"
        escaped = ref_doc_id.replace("\\", "\\\\").replace('"', '\\"')
        update_query = f"""PREFIX onto: <{onto_ns}>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

DELETE {{ {graph_clause} {{ ?s ?p ?o }} }}
WHERE  {{ {graph_clause} {{ ?s ?p ?o ; onto:ref_doc_id "{escaped}" }} }} ;

DELETE {{ {graph_clause} {{ ?reifier ?rp ?ro }} }}
WHERE  {{
  {graph_clause} {{
    ?reifier onto:ref_doc_id "{escaped}" .
    ?reifier ?rp ?ro .
    FILTER(isIRI(?reifier) && STRSTARTS(STR(?reifier), "urn:rdf4j:triple:"))
  }}
}}
"""
        sparql_update_endpoint = f"{self.base_url}/repositories/{self.repository}/statements"
        auth = (self.username, self.password) if self.username and self.password else None
        self.logger.debug("GraphDB delete_doc SPARQL:\n%s", update_query)
        try:
            resp = requests.post(
                sparql_update_endpoint,
                data={"update": update_query},
                auth=auth,
                timeout=60,
            )
            resp.raise_for_status()
            self.logger.info(
                "Deleted stale triples for ref_doc_id='%s' from GraphDB graph <%s>",
                ref_doc_id, graph_uri or "default",
            )
        except Exception as e:
            self.logger.warning(
                "Could not delete stale triples for ref_doc_id='%s' in GraphDB: %s - proceeding with append",
                ref_doc_id, e,
            )

    def query_sparql(self, query: str) -> List[Dict[str, Any]]:
        """Execute SPARQL SELECT/CONSTRUCT/DESCRIBE queries against GraphDB via direct HTTP."""
        try:
            auth = (self.username, self.password) if self.username and self.password else None
            resp = requests.post(
                self.query_endpoint,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
                auth=auth,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            vars_ = data.get("head", {}).get("vars", [])
            rows = []
            for binding in data.get("results", {}).get("bindings", []):
                row = {}
                for var in vars_:
                    val = binding.get(var, {})
                    row[var] = val.get("value", "") if val else ""
                rows.append(row)
            return rows
        except Exception as e:
            self.logger.error(f"GraphDB SPARQL query failed: {e}")
            raise

    def get_schema(self) -> Graph:
        """
        Extract basic ontology schema (classes and object properties) from GraphDB.
        """
        if self.graph is None:
            self.connect()

        schema_query = """
        PREFIX owl:  <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        CONSTRUCT {
          ?c a owl:Class ;
             rdfs:label ?clabel .
          ?p a owl:ObjectProperty ;
             rdfs:label ?plabel ;
             rdfs:domain ?domain ;
             rdfs:range  ?range .
        }
        WHERE {
          { ?c a owl:Class .
            OPTIONAL { ?c rdfs:label ?clabel }
          }
          UNION
          { ?p a owl:ObjectProperty .
            OPTIONAL { ?p rdfs:label ?plabel }
            OPTIONAL { ?p rdfs:domain ?domain }
            OPTIONAL { ?p rdfs:range  ?range }
          }
        }
        """
        schema_graph = Graph()
        res = self.graph.query(schema_query)
        schema_graph += res.graph
        return schema_graph
