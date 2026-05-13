"""
Oxigraph LangChain Adapter

Uses LangChain's RdfGraph (generic SPARQL endpoint wrapper) with
GraphSparqlQAChain to enable natural language querying against an
Oxigraph triple store from the hybrid search fusion pipeline.

Oxigraph's HTTP server (port 7878) exposes a standard SPARQL 1.1
query endpoint at /query, making it compatible with RdfGraph in
"store" mode without any custom transport logic.

Note: Only HTTP mode is supported here.  Embedded pyoxigraph is a
single-process store and not suitable for concurrent QA chain use.
"""

from typing import Dict, List, Any, Optional
from rdflib import Graph
import logging

try:
    from langchain_community.chains.graph_qa.sparql import GraphSparqlQAChain
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning(
        "langchain-community not available for OxigraphLangChainAdapter. "
        "Install with: pip install langchain-community"
    )

from rdf.store.rdf_store_adapter import RDFStoreAdapter
from .fuseki_langchain_adapter import _HttpSparqlGraph


class OxigraphLangChainAdapter(RDFStoreAdapter):
    """
    Oxigraph adapter using LangChain's RdfGraph for QA retrieval.

    Wraps the Oxigraph HTTP SPARQL query endpoint with LangChain's
    RdfGraph in "store" mode.  Natural language queries are translated
    to SPARQL by GraphSparqlQAChain and executed against the live store.

    Only HTTP mode is supported (Docker container at oxigraph_url).
    Embedded pyoxigraph is not suitable for concurrent access from a
    LangChain QA chain.

    Configuration::

        {
            "url": "http://localhost:7878",   # Oxigraph HTTP server
        }
    """

    def __init__(self, config: Dict[str, Any]):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain-community required for OxigraphLangChainAdapter. "
                "Install with: pip install langchain-community"
            )

        super().__init__(config)

        url = config.get("url") or config.get("store_path")
        if not url or url.startswith(".") or url.startswith("/"):
            raise ValueError(
                "OxigraphLangChainAdapter requires an HTTP URL "
                "(e.g. 'http://localhost:7878'). "
                "Embedded store paths are not supported for QA retrieval."
            )

        base = url.rstrip("/")
        # Oxigraph HTTP server exposes SPARQL 1.1 at /query
        self.query_endpoint = f"{base}/query"

        # Use _HttpSparqlGraph to avoid the immediate COUNT query in RdfGraph.__init__
        # that fails with a misleading error when the store is unreachable or empty.
        self.lc_graph = _HttpSparqlGraph(self.query_endpoint)
        self.lc_graph.load_schema()
        self.logger.info(
            "Connected to Oxigraph via LangChain (lazy) at %s",
            self.query_endpoint,
        )

    # ------------------------------------------------------------------
    # RDFStoreAdapter interface
    # ------------------------------------------------------------------

    def connect(self) -> Any:
        """Connection is handled in __init__."""
        return self.lc_graph

    def store_graph(self, graph: Graph, graph_uri: Optional[str] = None) -> None:
        """Not used here — writes go through OxigraphAdapter directly."""
        raise NotImplementedError(
            "OxigraphLangChainAdapter is read-only. "
            "Use OxigraphAdapter for writes."
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
            self.logger.error("Oxigraph SPARQL query failed: %s", e)
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
        """Create a GraphSparqlQAChain for natural-language queries on Oxigraph.

        Args:
            llm: Any LangChain chat model (ChatOpenAI, ChatAnthropic, etc.)

        Returns:
            GraphSparqlQAChain configured against the Oxigraph SPARQL endpoint.
        """
        return GraphSparqlQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            return_intermediate_steps=True,
            allow_dangerous_requests=True,
        )
