from typing import Optional, Dict, List, Any
from rdflib import Graph
from .rdf_store_adapter import RDFStoreAdapter
import logging
import requests as http_requests


class OxigraphAdapter(RDFStoreAdapter):
    """
    Oxigraph RDF Store Adapter — supports two modes:

    1. HTTP mode (preferred): connects to the Oxigraph Docker container via HTTP
       Graph Store Protocol (same as Fuseki).  No file locking, no corruption risk.
       Config: { "url": "http://localhost:7878" }

    2. Embedded mode: uses pyoxigraph directly with a local file store.
       Only suitable for single-process use — file lock prevents concurrent access.
       Config: { "store_path": "./data/oxigraph_store" }

    The Docker container (ghcr.io/oxigraph/oxigraph) runs an HTTP server on port 7878
    and supports RDF 1.2 annotation syntax natively.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Config (pick one):
        {
          "url":        "http://localhost:7878",    # HTTP mode — preferred
          "store_path": "./data/oxigraph_store",    # embedded mode — single process only
        }
        """
        super().__init__(config)
        self.url = config.get("url")
        self.store_path = config.get("store_path")
        self.store = None  # pyoxigraph Store (embedded mode only)

        if self.url:
            self.url = self.url.rstrip("/")
            self._mode = "http"
        elif self.store_path:
            self._mode = "embedded"
        else:
            # Default to HTTP localhost
            self.url = "http://localhost:7878"
            self._mode = "http"

    # ------------------------------------------------------------------
    # RDFStoreAdapter interface
    # ------------------------------------------------------------------

    def connect(self):
        """Connect / open the store.  HTTP mode is a no-op (stateless)."""
        if self._mode == "http":
            self.logger.info("Oxigraph HTTP mode: %s", self.url)
            return self.url
        return self._connect_embedded()

    def store_graph(self, graph: Graph, graph_uri: Optional[str] = None) -> None:
        """Store an rdflib.Graph (plain triples, no annotations)."""
        if self._mode == "http":
            turtle = graph.serialize(format="turtle")
            nquads_data = self._turtle_to_nquads(turtle, graph_uri)
            self._http_put_nquads(nquads_data)
        else:
            self._embedded_store_graph(graph, graph_uri)

    def store_rdf_annotations(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        """Store a Turtle document (with optional relation-property annotations).

        HTTP mode: Oxigraph's HTTP server only supports Turtle 1.1 via text/turtle,
        which silently drops RDF 1.2 {| |} annotation blocks.  To preserve all
        triples and reifiers we parse the annotated Turtle with pyoxigraph (which
        uses the same Rust core as the server and fully supports RDF 1.2), then
        re-serialise as N-Quads and PUT that to /store.  N-Quads is line-by-line
        and fully supported by the GSP endpoint.

        Embedded mode: pass Turtle bytes to pyoxigraph Store.load() directly —
        the embedded store supports RDF 1.2 natively.
        """
        if self._mode == "http":
            if isinstance(graph_or_turtle, str):
                turtle_data = graph_or_turtle
            else:
                turtle_data = graph_or_turtle.serialize(format="turtle")
            nquads_data = self._turtle_to_nquads(turtle_data, graph_uri)
            # PUT to /store without ?graph= param — N-Quads carries the graph URI inline
            self._http_put_nquads(nquads_data)
        else:
            self._embedded_store_rdfstar(graph_or_turtle, graph_uri)

    def _turtle_to_nquads(self, turtle_str: str, graph_uri: Optional[str]) -> bytes:
        """Parse annotated Turtle with pyoxigraph and serialise as N-Quads.

        pyoxigraph's Rust parser handles RDF 1.2 {| |} syntax natively.
        The resulting quads are written with the given graph_uri as the named
        graph, so the output is a complete N-Quads dataset.

        pyoxigraph API: load(input, format=RdfFormat.X) / dump(format=RdfFormat.X)
        — uses RdfFormat enum, NOT mime_type strings.
        """
        try:
            from pyoxigraph import Store, NamedNode, DefaultGraph, RdfFormat
            tmp = Store()
            graph_node = NamedNode(graph_uri) if graph_uri else DefaultGraph()
            tmp.load(
                turtle_str.encode("utf-8"),
                format=RdfFormat.TURTLE,
                to_graph=graph_node,
            )
            return tmp.dump(format=RdfFormat.N_QUADS)
        except Exception as e:
            self.logger.warning(
                "pyoxigraph RDF 1.2 parse failed (%s) — falling back to plain text/turtle", e
            )
            return turtle_str.encode("utf-8")

    def _http_put_nquads(self, nquads_data: bytes) -> None:
        """POST N-Quads dataset to Oxigraph /store (no ?graph= param — graph URI is inline)."""
        try:
            resp = http_requests.post(
                f"{self.url}/store",
                data=nquads_data,
                headers={"Content-Type": "application/n-quads"},
                timeout=60,
            )
            resp.raise_for_status()
            self.logger.info("Stored RDF data in Oxigraph HTTP store (N-Quads)")
        except Exception as e:
            self.logger.error("Failed to store graph in Oxigraph HTTP: %s", e)
            raise

    def _graph_exists(self, graph_uri: str) -> bool:
        """Return True if the named graph exists and contains at least one triple."""
        if not graph_uri:
            return True
        ask = f"ASK {{ GRAPH <{graph_uri}> {{ ?s ?p ?o }} }}"
        try:
            resp = http_requests.get(
                f"{self.url}/query",
                params={"query": ask},
                headers={"Accept": "application/sparql-results+json"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("boolean", False)
        except Exception:
            return False

    def delete_doc(self, ref_doc_id: str, graph_uri: Optional[str] = None) -> None:
        """Delete all triples for a specific document from Oxigraph via SPARQL UPDATE.

        Three-pass delete:
        1. Entity triples whose subject has onto:ref_doc_id.
        2. RDF 1.2 blank-node reifier triples (Oxigraph stores {| |} as blank-node
           reifiers: _:b rdf:reifies <<( s p o )>> ; prop val). Reachable as ordinary
           blank-node subjects.
        3. RDF 1.2 triple-pattern pass using <<( )>> syntax for any reifiers stored
           as triple-terms rather than blank nodes (belt-and-suspenders).
        Skips silently if the named graph does not exist yet.
        """
        if self._mode == "http" and graph_uri and not self._graph_exists(graph_uri):
            self.logger.info(
                "Oxigraph graph <%s> does not exist - nothing to delete for ref_doc_id='%s'",
                graph_uri, ref_doc_id,
            )
            return
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
        try:
            resp = http_requests.post(
                f"{self.url}/update",
                data={"update": update_query},
                timeout=60,
            )
            resp.raise_for_status()
            self.logger.info(
                "Deleted stale triples for ref_doc_id='%s' from Oxigraph graph <%s>",
                ref_doc_id, graph_uri or "default",
            )
        except Exception as e:
            self.logger.warning(
                "Could not delete stale triples for ref_doc_id='%s' in Oxigraph: %s - proceeding with append",
                ref_doc_id, e,
            )

    def query_sparql(self, query: str) -> List[Dict[str, Any]]:
        """Execute SPARQL query against Oxigraph."""
        if self._mode == "http":
            return self._http_query(query)
        return self._embedded_query(query)

    def get_schema(self) -> Graph:
        """Extract basic schema from Oxigraph."""
        schema_query = """
        PREFIX owl:  <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        CONSTRUCT {
          ?c a owl:Class ; rdfs:label ?clabel .
          ?p a owl:ObjectProperty ; rdfs:label ?plabel ;
             rdfs:domain ?domain ; rdfs:range ?range .
        }
        WHERE {
          { ?c a owl:Class . OPTIONAL { ?c rdfs:label ?clabel } }
          UNION
          { ?p a owl:ObjectProperty .
            OPTIONAL { ?p rdfs:label ?plabel }
            OPTIONAL { ?p rdfs:domain ?domain }
            OPTIONAL { ?p rdfs:range  ?range }
          }
        }
        """
        from rdflib import Graph as RDFGraph
        schema_graph = RDFGraph()
        if self._mode == "http":
            # CONSTRUCT returns RDF, not JSON bindings — request Turtle and parse it
            try:
                resp = http_requests.get(
                    f"{self.url}/query",
                    params={"query": schema_query},
                    headers={"Accept": "text/turtle"},
                    timeout=30,
                )
                resp.raise_for_status()
                schema_graph.parse(data=resp.text, format="turtle")
            except Exception as e:
                self.logger.error("Oxigraph schema query failed: %s", e)
        else:
            if self.store is None:
                self._connect_embedded()
            for quad in self.store.query(schema_query):
                s, p, o, g = quad
                schema_graph.add((s, p, o))
        return schema_graph

    # ------------------------------------------------------------------
    # HTTP mode helpers
    # ------------------------------------------------------------------

    def _http_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute SPARQL query against Oxigraph HTTP endpoint."""
        try:
            resp = http_requests.get(
                f"{self.url}/query",
                params={"query": query},
                headers={"Accept": "application/sparql-results+json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            bindings = data.get("results", {}).get("bindings", [])
            return [
                {k: v["value"] for k, v in row.items()}
                for row in bindings
            ]
        except Exception as e:
            self.logger.error("Oxigraph SPARQL query failed: %s", e)
            raise

    # ------------------------------------------------------------------
    # Embedded mode helpers
    # ------------------------------------------------------------------

    def _connect_embedded(self):
        """Open pyoxigraph embedded Store, auto-recovering from corruption."""
        try:
            from pyoxigraph import Store
        except ImportError as e:
            self.logger.error("pyoxigraph not installed. Run: pip install oxigraph")
            raise e

        if self.store_path:
            from pathlib import Path
            Path(self.store_path).mkdir(parents=True, exist_ok=True)

        try:
            self.store = Store(self.store_path)
        except Exception as e:
            err = str(e).lower()
            if self.store_path and ("corrupt" in err or "current" in err or "lock" in err):
                self.logger.warning(
                    "Oxigraph store at '%s' is unusable (%s) — wiping and recreating.",
                    self.store_path, e,
                )
                import shutil
                from pathlib import Path
                shutil.rmtree(self.store_path, ignore_errors=True)
                Path(self.store_path).mkdir(parents=True, exist_ok=True)
                self.store = Store(self.store_path)
                self.logger.info("Oxigraph store recreated at '%s'", self.store_path)
            else:
                raise

        self.logger.info("Connected to Oxigraph embedded store at %s", self.store_path)
        return self.store

    def _embedded_store_graph(self, graph: Graph, graph_uri: Optional[str]) -> None:
        if self.store is None:
            self._connect_embedded()
        from pyoxigraph import NamedNode, BlankNode, Literal as OxLiteral, Triple, Quad
        from rdflib import URIRef, BNode, Literal as RDFLiteral

        ctx = NamedNode(graph_uri) if graph_uri else None

        def _to_ox(term):
            if isinstance(term, URIRef):
                return NamedNode(str(term))
            if isinstance(term, BNode):
                return BlankNode(str(term))
            if isinstance(term, RDFLiteral):
                if term.language:
                    return OxLiteral(str(term), language=term.language)
                if term.datatype:
                    return OxLiteral(str(term), datatype=NamedNode(str(term.datatype)))
                return OxLiteral(str(term))
            return NamedNode(str(term))

        count = 0
        for s, p, o in graph:
            self.store.add(Quad(_to_ox(s), _to_ox(p), _to_ox(o), ctx))
            count += 1
        self.logger.info("Stored %d triples in Oxigraph embedded store", count)

    def _embedded_store_rdfstar(self, graph_or_turtle, graph_uri: Optional[str]) -> None:
        if self.store is None:
            self._connect_embedded()
        if isinstance(graph_or_turtle, str):
            import io
            from pyoxigraph import NamedNode
            turtle_bytes = graph_or_turtle.encode("utf-8")
            graph_uri_node = NamedNode(graph_uri) if graph_uri else None
            self.store.load(io.BytesIO(turtle_bytes), mime_type="text/turtle", to_graph=graph_uri_node)
            self.logger.info("Stored RDF annotations in Oxigraph embedded store (%s)", graph_uri or "default")
        else:
            self._embedded_store_graph(graph_or_turtle, graph_uri)

    def _embedded_query(self, query: str) -> List[Dict[str, Any]]:
        if self.store is None:
            self._connect_embedded()
        results = self.store.query(query)
        out: List[Dict[str, Any]] = []
        for row in results:
            if isinstance(row, dict):
                out.append({str(k): str(v) for k, v in row.items()})
            else:
                s, p, o, g = row
                out.append({"s": str(s), "p": str(p), "o": str(o), "g": str(g)})
        return out
