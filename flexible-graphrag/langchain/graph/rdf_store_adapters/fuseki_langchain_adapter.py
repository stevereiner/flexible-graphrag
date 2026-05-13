"""
Apache Fuseki LangChain Adapter

Uses LangChain's RdfGraph (generic SPARQL endpoint wrapper) with
GraphSparqlQAChain to enable natural language querying against a
Fuseki/Jena triple store from the hybrid search fusion pipeline.

Fuseki exposes standard SPARQL 1.1 Query and Update endpoints, so
RdfGraph's "store" mode connects directly without any custom logic.
"""

from typing import Dict, List, Any, Optional
from rdflib import Graph
import logging

try:
    from langchain_community.graphs import RdfGraph
    from langchain_community.chains.graph_qa.sparql import GraphSparqlQAChain
    LANGCHAIN_AVAILABLE = True
except ImportError:
    RdfGraph = object  # fallback base so class definition doesn't crash
    LANGCHAIN_AVAILABLE = False
    logging.warning(
        "langchain-community not available for FusekiLangChainAdapter. "
        "Install with: uv pip install langchain langchain-community"
    )

from rdf.store.rdf_store_adapter import RDFStoreAdapter
from rdf.kg_to_rdf_converter import DEFAULT_BASE_NS, DEFAULT_ONTO_NS

_KG_NS     = DEFAULT_BASE_NS.rstrip("/") + "/"
_KG_URI    = DEFAULT_BASE_NS.rstrip("/")
_ONTO_NS   = DEFAULT_ONTO_NS.rstrip("#") + "#"
_COMMON_NS = _ONTO_NS.replace("ontology#", "common#")


class _HttpSparqlGraph(RdfGraph):
    """
    Subclass of LangChain's RdfGraph that skips the connectivity check in
    __init__ and executes SPARQL queries via `requests` (not rdflib urllib).

    Two problems with the stock RdfGraph + rdflib.SPARQLStore approach:
    1. RdfGraph.__init__ calls len(self.graph) immediately → COUNT query fails
       when the store is unreachable or empty (before first ingest).
    2. rdflib.SPARQLStore uses urllib which does NOT support user:pass@ in URLs
       → getaddrinfo treats "admin:admin@localhost" as the hostname and fails.

    This subclass satisfies GraphSparqlQAChain's Pydantic isinstance validator
    while routing all queries through requests with proper Basic Auth.
    """

    def __init__(self, query_endpoint: str, username: str = "", password: str = ""):
        from urllib.parse import urlparse, urlunparse

        # Strip any embedded credentials from the URL and store separately.
        parsed = urlparse(query_endpoint)
        self._username = parsed.username or username or ""
        self._password = parsed.password or password or ""
        # Clean URL without credentials for use in requests calls.
        clean_netloc = parsed.hostname
        if parsed.port:
            clean_netloc = f"{clean_netloc}:{parsed.port}"
        self._clean_endpoint = urlunparse(parsed._replace(netloc=clean_netloc))

        # Bypass RdfGraph.__init__ — set the attributes it expects.
        self.query_endpoint = self._clean_endpoint
        self.update_endpoint = None
        self.standard = "rdf"
        self.local_copy = None
        self.mode = "store"
        # Provide a stub graph so code that accesses self.graph doesn't crash.
        import rdflib
        self.graph = rdflib.Graph()
        self.schema: str = ""

    def _sparql_select(self, sparql_query: str) -> List[Dict[str, Any]]:
        """Execute a SPARQL SELECT via HTTP, return list-of-dicts."""
        import requests as _requests
        auth = (_requests.auth.HTTPBasicAuth(self._username, self._password)
                if self._username else None)
        resp = _requests.get(
            self._clean_endpoint,
            params={"query": sparql_query},
            headers={"Accept": "application/sparql-results+json"},
            auth=auth,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        bindings = data.get("results", {}).get("bindings", [])
        rows = []
        for b in bindings:
            rows.append({k: v.get("value", "") for k, v in b.items()})
        return rows

    def query(self, sparql_query: str):
        """Execute SPARQL and return rows as a list of plain-string dicts."""
        return self._sparql_select(sparql_query)

    def load_schema(self) -> None:
        """Build schema by fetching live predicates from the named graph."""
        _log = logging.getLogger(__name__)
        _SKIP = frozenset(["rdf-syntax", "rdf-schema", "owl#", "purl.org/dc",
                           "/ontology#ref_doc_id", "/ontology#file_", "/ontology#modified",
                           "/ontology#source", "/ontology#conversion"])
        try:
            # Fetch distinct predicates actually in the named graph
            q = f"""SELECT DISTINCT ?p WHERE {{
  GRAPH <{_KG_URI}> {{ ?s ?p ?o }}
}} ORDER BY ?p"""
            rows = self._sparql_select(q)
            preds = [r["p"] for r in rows
                     if not any(skip in r.get("p", "") for skip in _SKIP)]

            # Fetch distinct rdf:type values (entity classes)
            q2 = f"""PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT DISTINCT ?t WHERE {{
  GRAPH <{_KG_URI}> {{ ?s rdf:type ?t }}
}} ORDER BY ?t"""
            type_rows = self._sparql_select(q2)
            types = [r["t"] for r in type_rows if "owl#" not in r.get("t","")]

            pred_lines = "\n".join(f"  <{p}>" for p in preds)
            type_lines = "\n".join(f"  <{t}>" for t in types)

            # Build a schema string that the LLM can use directly
            self.schema = (
                "# Namespaces\n"
                f"PREFIX kg:     <{_KG_NS}>\n"
                f"PREFIX onto:   <{_ONTO_NS}>\n"
                "PREFIX company: <http://example.org/company/>\n"
                f"PREFIX common:  <{_COMMON_NS}>\n"
                "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>\n"
                "\n"
                "# Entity classes in the store:\n"
                f"{type_lines}\n"
                "\n"
                "# Predicates actually in the store (use these EXACTLY):\n"
                f"{pred_lines}\n"
            )
            _log.info("Loaded schema: %d predicates, %d types", len(preds), len(types))
        except Exception as exc:
            _log.warning("Schema load skipped (store may be empty or unreachable): %s", exc)
            self.schema = ""

            self.schema = ""


class FusekiLangChainAdapter(RDFStoreAdapter):
    """
    Apache Fuseki adapter using LangChain's RdfGraph for QA retrieval.

    Wraps the Fuseki SPARQL query endpoint with LangChain's RdfGraph in
    "store" mode (read-only; all writes go through the native FusekiAdapter).
    Natural language queries are translated to SPARQL by GraphSparqlQAChain.

    Configuration::

        {
            "base_url": "http://localhost:3030",
            "dataset":  "flexible-graphrag",
            "username": "admin",   # optional
            "password": "admin",   # optional
        }
    """

    def __init__(self, config: Dict[str, Any]):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain-community required for FusekiLangChainAdapter. "
                "Install with: pip install langchain-community"
            )

        super().__init__(config)

        base_url = config["base_url"].rstrip("/")
        dataset = config["dataset"]
        username = config.get("username", "")
        password = config.get("password", "")

        clean_endpoint = f"{base_url}/{dataset}/sparql"

        # Pass credentials separately — _HttpSparqlGraph uses requests with
        # HTTPBasicAuth rather than embedding them in the URL (urllib does not
        # support user:pass@ and misreads it as the hostname).
        self.lc_graph = _HttpSparqlGraph(clean_endpoint, username=username, password=password)
        self.query_endpoint = self.lc_graph._clean_endpoint

        # Best-effort schema load; logged as warning if store is empty/unreachable.
        self.lc_graph.load_schema()
        self.logger.info(
            "Connected to Fuseki via LangChain (lazy) at %s",
            self.query_endpoint,
        )

    # ------------------------------------------------------------------
    # RDFStoreAdapter interface
    # ------------------------------------------------------------------

    def connect(self) -> Any:
        """Connection is handled in __init__."""
        return self.lc_graph

    def store_graph(self, graph: Graph, graph_uri: Optional[str] = None) -> None:
        """Not used here — writes go through FusekiAdapter directly."""
        raise NotImplementedError(
            "FusekiLangChainAdapter is read-only. "
            "Use FusekiAdapter for writes."
        )

    def query_sparql(self, query: str) -> List[Dict[str, Any]]:
        """Execute a SPARQL SELECT query via LangChain's RdfGraph."""
        try:
            results = self.lc_graph.query(query)
            if results and hasattr(results[0], "asdict"):
                return [
                    {str(var): str(val) for var, val in row.asdict().items()}
                    for row in results
                ]
            elif results:
                return [{"result": str(row)} for row in results]
            return []
        except Exception as e:
            self.logger.error("Fuseki SPARQL query failed: %s", e)
            raise

    def get_schema(self) -> Graph:
        """Return current schema as an rdflib.Graph."""
        g = Graph()
        schema_str = getattr(self.lc_graph, "schema", "") or ""
        if schema_str:
            try:
                g.parse(data=schema_str, format="turtle")
            except Exception:
                pass
        return g

    # ------------------------------------------------------------------
    # QA chain factory
    # ------------------------------------------------------------------

    def create_qa_chain(self, llm: Any):
        """Create a GraphSparqlQAChain for natural-language queries on Fuseki.

        Args:
            llm: Any LangChain chat model (ChatOpenAI, ChatAnthropic, etc.)

        Returns:
            GraphSparqlQAChain configured against the Fuseki SPARQL endpoint.
        """
        return GraphSparqlQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            return_intermediate_steps=True,
            allow_dangerous_requests=True,
        )
