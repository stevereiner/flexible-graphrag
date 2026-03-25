from typing import Optional, Dict, List, Any
from rdflib import Graph, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore
from .rdf_store_adapter import RDFStoreAdapter
import logging
import requests
from urllib.parse import quote


class FusekiAdapter(RDFStoreAdapter):
    """Apache Fuseki RDF Store Adapter"""

    def __init__(self, config: Dict[str, str]):
        """
        Config expects:
        {
            "base_url":  "http://localhost:3030",
            "dataset":   "mydata",
            "username":  "admin",   # optional, required when Fuseki auth is enabled
            "password":  "admin"    # optional
        }
        """
        super().__init__(config)
        self.base_url = config["base_url"].rstrip("/")
        self.dataset = config["dataset"]
        self.username = config.get("username")
        self.password = config.get("password")
        self.auth = (self.username, self.password) if self.username and self.password else None
        self.query_endpoint = f"{self.base_url}/{self.dataset}/query"
        self.update_endpoint = f"{self.base_url}/{self.dataset}/update"
        self.graph = None
        self._dataset_ensured = False

    # ------------------------------------------------------------------
    # Dataset management
    # ------------------------------------------------------------------

    def _ensure_dataset_exists(self) -> None:
        """Create the Fuseki dataset via the admin API if it does not exist."""
        if self._dataset_ensured:
            return
        admin_url = f"{self.base_url}/$/datasets"
        try:
            # Check whether the dataset already exists
            resp = requests.get(
                f"{admin_url}/{self.dataset}",
                auth=self.auth,
                timeout=10,
            )
            if resp.status_code == 200:
                self._dataset_ensured = True
                return
            if resp.status_code != 404:
                self.logger.warning(
                    "Unexpected status checking Fuseki dataset: %s", resp.status_code
                )

            # Create a persistent (TDB2) dataset
            resp = requests.post(
                admin_url,
                data={"dbName": self.dataset, "dbType": "tdb2"},
                auth=self.auth,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                self.logger.info("Created Fuseki dataset '%s'", self.dataset)
                self._dataset_ensured = True
            else:
                self.logger.warning(
                    "Could not create Fuseki dataset '%s': %s %s",
                    self.dataset, resp.status_code, resp.text,
                )
        except Exception as e:
            self.logger.warning("Could not ensure Fuseki dataset exists: %s", e)

    # ------------------------------------------------------------------
    # RDFStoreAdapter interface
    # ------------------------------------------------------------------

    def connect(self) -> Graph:
        """Connect to Fuseki SPARQL endpoint."""
        self._ensure_dataset_exists()
        # SPARQLUpdateStore auth: pass credentials in the endpoint URLs or via
        # the requests session.  setCredentials() was removed in rdflib 6+;
        # we embed credentials directly in the endpoint URLs instead.
        if self.auth:
            from urllib.parse import urlparse, urlunparse
            def _inject_auth(url: str, user: str, pwd: str) -> str:
                p = urlparse(url)
                return urlunparse(p._replace(netloc=f"{user}:{pwd}@{p.netloc}"))
            query_ep = _inject_auth(self.query_endpoint, self.username, self.password)
            update_ep = _inject_auth(self.update_endpoint, self.username, self.password)
        else:
            query_ep, update_ep = self.query_endpoint, self.update_endpoint
        store = SPARQLUpdateStore()
        store.open((query_ep, update_ep))
        self.graph = Graph(store)
        self.logger.info("Connected to Fuseki: %s/%s", self.base_url, self.dataset)
        return self.graph

    def store_graph(self, graph: Graph, graph_uri: Optional[str] = None) -> None:
        """Store RDF graph in Fuseki via HTTP POST (plain Turtle, appends to graph)."""
        self._ensure_dataset_exists()
        self._http_post_graph(graph, graph_uri, content_type="text/turtle;charset=utf-8")

    def store_rdf_annotations(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        """Store a Turtle document (with optional relation-property annotations) in Fuseki.

        Accepts either:
          - a Turtle string (str) from KGToRDFConverter — preferred; may contain
            RDF 1.2 {| |} annotations, legacy << >> lines, or plain triples.
          - an rdflib.Graph — serialized as plain Turtle (no annotations).

        Apache Jena 5 handles all annotation syntaxes under the standard
        ``text/turtle`` MIME type.
        """
        self._ensure_dataset_exists()
        self._http_post_graph(graph_or_turtle, graph_uri, content_type="text/turtle;charset=utf-8")

    def _http_post_graph(
        self, graph_or_turtle, graph_uri: Optional[str], content_type: str
    ) -> None:
        """POST a serialized graph to the Fuseki GSP (Graph Store Protocol) endpoint."""
        data_endpoint = f"{self.base_url}/{self.dataset}/data"
        params: Dict[str, str] = {}
        if graph_uri:
            params["graph"] = graph_uri

        if isinstance(graph_or_turtle, str):
            turtle_data = graph_or_turtle
        else:
            try:
                turtle_data = graph_or_turtle.serialize(format="turtle")
            except Exception:
                turtle_data = graph_or_turtle.serialize(format="n3")

        try:
            resp = requests.post(
                data_endpoint,
                data=turtle_data.encode("utf-8"),
                headers={"Content-Type": content_type},
                params=params,
                auth=self.auth,
                timeout=60,
            )
            resp.raise_for_status()
            triple_count = (
                turtle_data.count(" .")
                if isinstance(graph_or_turtle, str)
                else len(graph_or_turtle)
            )
            self.logger.info(
                "Stored ~%d triples in Fuseki '%s' graph via HTTP POST",
                triple_count, graph_uri or "default",
            )
        except Exception as e:
            self.logger.error("Failed to store graph in Fuseki: %s", e)
            raise

    def query_sparql(self, query: str) -> List[Dict]:
        """Execute SPARQL query against Fuseki."""
        if self.graph is None:
            self.connect()
        try:
            results = self.graph.query(query)
            return [
                {str(var): str(value) for var, value in row.asdict().items()}
                for row in results
            ]
        except Exception as e:
            self.logger.error("SPARQL query failed: %s", e)
            raise

    def delete_doc(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        """Delete all triples for a specific document from Fuseki via SPARQL UPDATE.

        Three-pass delete:
        1. Entity triples whose subject has onto:ref_doc_id.
        2. RDF 1.2 blank-node reifier triples (Fuseki/Jena stores {| |} as blank-node
           reifiers: _:b rdf:reifies <<( s p o )>> ; prop val). These are reachable
           as ordinary blank-node subjects in standard SPARQL.
        3. RDF-star triple-pattern pass using Jena's << >> syntax for any reifiers
           stored as triple IRIs rather than blank nodes (belt-and-suspenders).
        """
        self._ensure_dataset_exists()
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
    FILTER(isBlank(?reifier) || (isIRI(?reifier) && STRSTARTS(STR(?reifier), "urn:")))
  }}
}}
"""
        update_endpoint = f"{self.base_url}/{self.dataset}/update"
        try:
            resp = requests.post(
                update_endpoint,
                data=update_query.encode("utf-8"),
                headers={"Content-Type": "application/sparql-update"},
                auth=self.auth,
                timeout=60,
            )
            if resp.status_code == 405:
                resp = requests.post(
                    update_endpoint,
                    data={"update": update_query},
                    auth=self.auth,
                    timeout=60,
                )
            resp.raise_for_status()
            self.logger.info(
                "Deleted stale triples for ref_doc_id='%s' from Fuseki graph <%s>",
                ref_doc_id, graph_uri or "default",
            )
        except Exception as e:
            self.logger.warning(
                "Could not delete stale triples for ref_doc_id='%s' in Fuseki: %s - proceeding with append",
                ref_doc_id, e,
            )

    def get_schema(self) -> Graph:
        """Get ontology schema from Fuseki."""
        schema_query = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        CONSTRUCT {
            ?class a owl:Class ; rdfs:label ?label .
            ?prop a owl:ObjectProperty ; rdfs:label ?label ; rdfs:domain ?domain ; rdfs:range ?range .
        }
        WHERE {
            { ?class a owl:Class . OPTIONAL { ?class rdfs:label ?label } }
            UNION
            { ?prop a owl:ObjectProperty .
              OPTIONAL { ?prop rdfs:label ?label }
              OPTIONAL { ?prop rdfs:domain ?domain }
              OPTIONAL { ?prop rdfs:range ?range }
            }
        }
        """
        if self.graph is None:
            self.connect()
        schema_graph = Graph()
        schema_graph += self.graph.query(schema_query).graph
        return schema_graph
