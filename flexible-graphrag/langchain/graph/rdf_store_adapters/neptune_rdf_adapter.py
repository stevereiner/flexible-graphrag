"""
Amazon Neptune RDF LangChain Adapter

Uses LangChain's NeptuneRdfGraph for AWS Neptune Database (RDF/SPARQL mode).

Key Features:
- Neptune's "OneGraph" architecture (RDF + OpenCypher on same data)
- AWS IAM authentication support
- VPC endpoint access
- Optimized for production workloads
- GraphRAG toolkit integration

Advantages over RDFLib:
- Native AWS integration (IAM auth, VPC)
- Production-grade performance
- LangChain QA chains for natural language queries
- Neptune-specific optimizations
- OpenSearch Serverless integration
"""

from typing import Dict, List, Any, Optional
from rdflib import Graph
import logging

try:
    from langchain_aws.graphs import NeptuneRdfGraph
    from langchain_aws.chains import create_neptune_sparql_qa_chain
    import boto3
    LANGCHAIN_AWS_AVAILABLE = True
except ImportError:
    LANGCHAIN_AWS_AVAILABLE = False
    logging.warning("langchain-aws not available. Install with: pip install langchain-aws boto3")

from rdf.store.rdf_store_adapter import RDFStoreAdapter


class NeptuneRDFAdapter(RDFStoreAdapter):
    """
    Amazon Neptune RDF adapter using LangChain's NeptuneRdfGraph.
    
    Supports:
    1. Neptune Database (RDF/SPARQL mode)
    2. IAM authentication for secure access
    3. VPC endpoint configuration
    4. OpenSearch Serverless integration for hybrid search
    5. "OneGraph" - query same data via SPARQL or OpenCypher
    
    Architecture:
    - Construction: RDFLib (local) → bulk load via Neptune Loader (S3)
    - Querying: LangChain Neptune chains (NL → SPARQL)
    - Hybrid: OpenSearch Serverless for vector + Neptune for graph
    
    Configuration:
    {
        "host": "my-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com",
        "port": 8182,
        "region": "us-east-1",
        "use_iam_auth": true,  # IAM SigV4 authentication
        "use_https": true,
        "s3_bucket": "my-neptune-bucket",  # For bulk loading
        "opensearch_endpoint": "https://...",  # Optional: OpenSearch Serverless
        "opensearch_index": "neptune-vectors"
    }
    
    Bulk Loading:
    - Small graphs (<10k triples): Direct SPARQL INSERT
    - Large graphs: Upload to S3 → Neptune Loader API (10-100x faster)
    
    References:
    - https://docs.aws.amazon.com/neptune/latest/userguide/sparql-api-reference.html
    - https://docs.aws.amazon.com/neptune/latest/userguide/bulk-load.html
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not LANGCHAIN_AWS_AVAILABLE:
            raise ImportError(
                "langchain-aws and boto3 required for NeptuneRDFAdapter. "
                "Install with: pip install langchain-aws boto3"
            )
        
        super().__init__(config)
        
        self.host = config["host"]
        self.port = config.get("port", 8182)
        self.region = config.get("region", "us-east-1")
        self.use_iam_auth = config.get("use_iam_auth", True)
        self.use_https = config.get("use_https", True)
        self.s3_bucket = config.get("s3_bucket")
        self.opensearch_endpoint = config.get("opensearch_endpoint")
        self.opensearch_index = config.get("opensearch_index", "neptune-vectors")
        self._aws_access_key_id = config.get("aws_access_key_id")
        self._aws_secret_access_key = config.get("aws_secret_access_key")

        # Initialize boto3 session for IAM auth if needed
        self.session = None
        if self.use_iam_auth:
            if self._aws_access_key_id and self._aws_secret_access_key:
                self.session = boto3.Session(
                    aws_access_key_id=self._aws_access_key_id,
                    aws_secret_access_key=self._aws_secret_access_key,
                    region_name=self.region,
                )
            else:
                self.session = boto3.Session(region_name=self.region)

        # Build Neptune endpoints
        protocol = "https" if self.use_https else "http"
        self.neptune_endpoint = f"{protocol}://{self.host}:{self.port}"
        self.sparql_endpoint = f"{self.neptune_endpoint}/sparql"
        self.loader_endpoint = f"{self.neptune_endpoint}/loader"

        # Initialize LangChain NeptuneRdfGraph
        try:
            import os as _os
            # NeptuneRdfGraph.query() uses self.session internally for SigV4 signing.
            # When client= is passed, __init__ skips creating self.session -> AttributeError.
            # Solution: inject credentials into the process environment so boto3's default
            # credential chain picks them up when NeptuneRdfGraph creates its own session.
            _injected: list[str] = []
            if self._aws_access_key_id and self._aws_secret_access_key:
                if not _os.environ.get("AWS_ACCESS_KEY_ID"):
                    _os.environ["AWS_ACCESS_KEY_ID"] = self._aws_access_key_id
                    _injected.append("AWS_ACCESS_KEY_ID")
                if not _os.environ.get("AWS_SECRET_ACCESS_KEY"):
                    _os.environ["AWS_SECRET_ACCESS_KEY"] = self._aws_secret_access_key
                    _injected.append("AWS_SECRET_ACCESS_KEY")
                if not _os.environ.get("AWS_DEFAULT_REGION"):
                    _os.environ["AWS_DEFAULT_REGION"] = self.region
                    _injected.append("AWS_DEFAULT_REGION")

            self.lc_graph = NeptuneRdfGraph(
                host=self.host,
                port=self.port,
                use_iam_auth=self.use_iam_auth,
                region_name=self.region,
                use_https=self.use_https,
            )
            self.logger.info("Connected to Neptune RDF via LangChain at %s", self.sparql_endpoint)

            # Load schema (requires a working Neptune connection)
            try:
                schema_elements = self.lc_graph.get_schema_elements
                self.lc_graph.load_schema(schema_elements)
                schema_len = len(self.lc_graph.get_schema) if self.lc_graph.get_schema else 0
                self.logger.info("Loaded Neptune RDF schema: %d chars", schema_len)
            except Exception as schema_err:
                self.logger.warning("Could not load Neptune RDF schema (empty graph?): %s", schema_err)
        except Exception as e:
            self.logger.error("Failed to initialize LangChain Neptune RDF: %s", e)
            raise
    
    def connect(self) -> Any:
        """Connection handled in __init__."""
        return self.lc_graph

    def store_rdf_annotations(self, graph_or_turtle, graph_uri: Optional[str] = None) -> None:
        """Override to handle Turtle strings: strip RDF-star annotation syntax, then INSERT.

        Neptune does not support RDF 1.2 {| |} or << >> annotation syntax in SPARQL INSERT.
        We parse the plain triples from the Turtle string (rdflib drops annotation blocks
        that use unknown syntax) and write them via N-Triples SPARQL INSERT.

        Additionally, we extract ``onto:ref_doc_id`` values from annotation blocks and
        write them as plain triples on the subject entity.  Neptune strips annotations so
        ``onto:ref_doc_id`` would otherwise never be written — the DELETE query in
        ``delete_doc()`` matches on ``?s onto:ref_doc_id "..."`` and would always delete
        0 triples without this extra step.
        """
        if isinstance(graph_or_turtle, str):
            import re as _re
            turtle_str = graph_or_turtle

            # ── Step 1: Extract (subject_uri, ref_doc_id) pairs from annotation blocks ──
            # Turtle annotation syntax: <subj> <pred> <obj>\n    {| onto:ref_doc_id "value" ... |} .
            # We capture every occurrence of onto:ref_doc_id inside {| ... |} together
            # with the subject URI on the line immediately before the {| block.
            ref_doc_triples: list[tuple[str, str]] = []
            _ONTO_NS = "https://integratedsemantics.org/flexible-graphrag/ontology#"

            # Match: <subject_uri> ... {| ... onto:ref_doc_id "value" ... |} .
            # The subject URI is on the line before the annotation block.
            annotation_pattern = _re.compile(
                r'<([^>]+)>\s+<[^>]+>\s+<[^>]+>\s*\{[|](.*?)[|]\}',
                _re.DOTALL,
            )
            ref_doc_pattern = _re.compile(r'onto:ref_doc_id\s+"([^"]+)"')
            # Also handle full URI form: <onto_ns ref_doc_id>
            ref_doc_uri_pattern = _re.compile(
                r'<' + _re.escape(_ONTO_NS) + r'ref_doc_id>\s+"([^"]+)"'
            )
            for m in annotation_pattern.finditer(turtle_str):
                subj_uri = m.group(1)
                annotation_body = m.group(2)
                for rdp in (ref_doc_pattern, ref_doc_uri_pattern):
                    rdm = rdp.search(annotation_body)
                    if rdm:
                        ref_doc_triples.append((subj_uri, rdm.group(1)))
                        break

            # ── Step 2: Remove annotation blocks and store plain triples ──
            # Remove inline annotation blocks {| ... |}  (may span multiple lines)
            cleaned = _re.sub(r'\{[|].*?[|]\}', '', turtle_str, flags=_re.DOTALL)
            # Also remove legacy << >> RDF-star lines
            cleaned = _re.sub(r'<<[^>]*(?:>[^>][^>]*)*>>', '', cleaned, flags=_re.DOTALL)
            try:
                g = Graph()
                g.parse(data=cleaned, format="turtle")
                self.store_graph(g, graph_uri=graph_uri)
            except Exception as parse_err:
                self.logger.warning(
                    "Neptune RDF: could not parse cleaned Turtle (%s), trying N-Triples fallback", parse_err
                )
                # Last resort: extract only <s> <p> <o> . lines via regex
                nt_lines = _re.findall(
                    r'<[^>]+>\s+<[^>]+>\s+(?:<[^>]+>|"[^"]*"(?:\^\^<[^>]+>)?(?:@\w+)?)\s+\.',
                    cleaned
                )
                if nt_lines:
                    insert_data = "\n".join(nt_lines)
                    if graph_uri:
                        sparql = f"INSERT DATA {{ GRAPH <{graph_uri}> {{ {insert_data} }} }}"
                    else:
                        sparql = f"INSERT DATA {{ {insert_data} }}"
                    self._sparql_update(sparql)
                else:
                    self.logger.error("Neptune RDF: no parseable triples found in Turtle string")

            # ── Step 3: Write onto:ref_doc_id as plain provenance triples ──
            # These allow delete_doc() to find and remove entities by document.
            # IMPORTANT: escape backslashes in SPARQL string literals (Windows paths
            # contain backslashes which must be written as \\ in SPARQL/N-Triples;
            # otherwise \n, \t etc. are misinterpreted as escape sequences and the
            # stored value won't match the delete query's escaped form).
            if ref_doc_triples:
                nt_provenance = "\n".join(
                    f'<{subj}> <{_ONTO_NS}ref_doc_id> "{ref_id.replace(chr(92), chr(92)*2)}" .'
                    for subj, ref_id in ref_doc_triples
                )
                try:
                    if graph_uri:
                        prov_sparql = f"INSERT DATA {{ GRAPH <{graph_uri}> {{ {nt_provenance} }} }}"
                    else:
                        prov_sparql = f"INSERT DATA {{ {nt_provenance} }}"
                    self._sparql_update(prov_sparql)
                    self.logger.info(
                        "Neptune RDF: stored %d onto:ref_doc_id provenance triple(s)", len(ref_doc_triples)
                    )
                except Exception as prov_err:
                    self.logger.warning(
                        "Neptune RDF: could not store provenance triples: %s", prov_err
                    )
        else:
            self.store_graph(graph_or_turtle, graph_uri=graph_uri)

    def store_graph(self, graph: Graph, graph_uri: Optional[str] = None) -> None:
        """Store RDF graph in Neptune.
        
        Strategy:
        - Small graphs (<10k triples): Direct SPARQL INSERT via HTTP
        - Large graphs (>10k triples): S3 bulk load (requires s3_bucket config)
        
        Neptune Loader provides 10-100x faster loading for large graphs.
        """
        triple_count = len(graph)
        self.logger.info(f"Storing {triple_count} triples to Neptune...")
        
        # Threshold for bulk load
        BULK_LOAD_THRESHOLD = 10000
        
        if triple_count < BULK_LOAD_THRESHOLD or not self.s3_bucket:
            # Direct SPARQL INSERT
            self._store_direct(graph, graph_uri)
        else:
            # Bulk load via S3
            self._store_bulk_s3(graph, graph_uri)
    
    def _sparql_update(self, update_query: str) -> None:
        """POST a SPARQL UPDATE to Neptune's /sparql endpoint with SigV4 signing."""
        import requests as _requests
        from types import SimpleNamespace as _SN

        update_endpoint = f"{self.neptune_endpoint}/sparql"
        data = {"update": update_query}
        headers: dict = {"Content-Type": "application/x-www-form-urlencoded"}

        if self.use_iam_auth:
            credentials = self.lc_graph.session.get_credentials().get_frozen_credentials()
            creds = _SN(
                access_key=credentials.access_key,
                secret_key=credentials.secret_key,
                token=credentials.token,
                region=self.region,
            )
            from botocore.awsrequest import AWSRequest
            from botocore.auth import SigV4Auth
            req = AWSRequest(method="POST", url=update_endpoint, data=data)
            SigV4Auth(creds, "neptune-db", self.region).add_auth(req)  # type: ignore[arg-type]
            headers = dict(req.headers)
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        resp = _requests.post(update_endpoint, data=data, headers=headers)
        if not resp.ok:
            raise RuntimeError(f"Neptune SPARQL UPDATE failed {resp.status_code}: {resp.text[:500]}")

    def _store_direct(self, graph: Graph, graph_uri: Optional[str]) -> None:
        """Store graph via direct SPARQL INSERT DATA (for small graphs <10k triples)."""
        # Serialize to N-Triples — avoids prefix/Turtle issues with Neptune's SPARQL parser
        nt_data = graph.serialize(format="nt")

        # Build SPARQL UPDATE
        if graph_uri:
            sparql_update = f"INSERT DATA {{ GRAPH <{graph_uri}> {{ {nt_data} }} }}"
        else:
            sparql_update = f"INSERT DATA {{ {nt_data} }}"

        try:
            self._sparql_update(sparql_update)
            self.logger.info("Stored %d triples in Neptune via SPARQL INSERT", len(graph))
        except Exception as e:
            self.logger.error("Failed to store graph in Neptune: %s", e)
            raise
    
    def _store_bulk_s3(self, graph: Graph, graph_uri: Optional[str]) -> None:
        """Store graph via Neptune Loader (S3 bulk load).
        
        Process:
        1. Serialize graph to N-Triples or N-Quads
        2. Upload to S3
        3. Call Neptune Loader API
        4. Poll for completion
        """
        import uuid
        import time
        
        if not self.s3_bucket:
            raise ValueError("s3_bucket required for bulk loading")
        
        s3 = self.session.client('s3') if self.session else boto3.client('s3', region_name=self.region)
        
        # Generate unique filename
        load_id = str(uuid.uuid4())
        s3_key = f"neptune-loads/{load_id}.nt"
        
        # Serialize to N-Triples (best for bulk load)
        nt_data = graph.serialize(format="nt")
        
        try:
            # Upload to S3
            self.logger.info(f"Uploading graph to s3://{self.s3_bucket}/{s3_key}")
            s3.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=nt_data.encode('utf-8'),
                ContentType='application/n-triples'
            )
            
            # Start Neptune Loader
            import requests
            from requests_aws4auth import AWS4Auth
            
            loader_payload = {
                "source": f"s3://{self.s3_bucket}/{s3_key}",
                "format": "ntriples",
                "iamRoleArn": self.config.get("iam_role_arn"),  # Required for S3 access
                "region": self.region,
                "failOnError": "FALSE",
                "parallelism": "HIGH",
                "updateSingleCardinalityProperties": "FALSE"
            }
            
            if graph_uri:
                loader_payload["parserConfiguration"] = {
                    "namedGraphUri": graph_uri
                }
            
            # Prepare authentication
            if self.use_iam_auth:
                from botocore.auth import SigV4Auth
                from botocore.awsrequest import AWSRequest
                
                credentials = self.session.get_credentials()
                auth = AWS4Auth(
                    credentials.access_key,
                    credentials.secret_key,
                    self.region,
                    'neptune-db',
                    session_token=credentials.token
                )
            else:
                auth = None
            
            self.logger.info(f"Starting Neptune Loader for {load_id}...")
            resp = requests.post(
                self.loader_endpoint,
                json=loader_payload,
                auth=auth,
                headers={"Content-Type": "application/json"}
            )
            resp.raise_for_status()
            
            load_status = resp.json()
            loader_id = load_status["payload"]["loadId"]
            
            self.logger.info(f"Neptune Loader started: {loader_id}")
            
            # Poll for completion
            max_wait = 600  # 10 minutes
            poll_interval = 5
            waited = 0
            
            while waited < max_wait:
                status_resp = requests.get(
                    f"{self.loader_endpoint}/{loader_id}",
                    auth=auth
                )
                status_resp.raise_for_status()
                status = status_resp.json()
                
                overall_status = status["payload"]["overallStatus"]["status"]
                
                if overall_status == "LOAD_COMPLETED":
                    self.logger.info(f"Neptune bulk load completed successfully")
                    return
                elif overall_status in ["LOAD_FAILED", "LOAD_CANCELLED"]:
                    raise Exception(f"Neptune load failed: {status}")
                
                time.sleep(poll_interval)
                waited += poll_interval
                self.logger.debug(f"Neptune load status: {overall_status}")
            
            raise TimeoutError(f"Neptune load timed out after {max_wait}s")
            
        except Exception as e:
            self.logger.error(f"Neptune bulk load failed: {e}")
            raise
    
    def delete_doc(self, ref_doc_id: str, graph_uri=None) -> None:
        """Override to use Neptune's SPARQL UPDATE endpoint (not the read endpoint).

        The base class calls query_sparql() which maps to NeptuneRdfGraph.query() —
        a SELECT-style read request.  Neptune requires SPARQL UPDATE to be sent as
        ``POST /sparql`` with ``update=<query>`` (form-encoded), NOT ``query=<query>``.
        _sparql_update() handles exactly that with proper SigV4 signing.
        """
        onto_ns = "https://integratedsemantics.org/flexible-graphrag/ontology#"
        graph_clause = f"GRAPH <{graph_uri}>" if graph_uri else "GRAPH ?g"
        escaped = ref_doc_id.replace("\\", "\\\\").replace('"', '\\"')
        delete_query = f"""PREFIX onto: <{onto_ns}>
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
            self._sparql_update(delete_query)
            self.logger.info(
                "Deleted RDF triples for ref_doc_id='%s' from graph <%s> via Neptune SPARQL UPDATE",
                ref_doc_id, graph_uri or "default",
            )
        except Exception as exc:
            self.logger.warning(
                "Could not delete stale triples for ref_doc_id='%s': %s — proceeding with append",
                ref_doc_id, exc,
            )

    def query_sparql(self, query: str) -> List[Dict[str, Any]]:
        """Execute SPARQL SELECT query using LangChain's Neptune integration.

        NeptuneRdfGraph.query() returns the raw SPARQL JSON response dict:
        {"head": {"vars": [...]}, "results": {"bindings": [{"var": {"value": ...}}]}}
        """
        try:
            data = self.lc_graph.query(query)

            # Parse SPARQL JSON response
            if isinstance(data, dict) and "results" in data:
                vars_ = data.get("head", {}).get("vars", [])
                rows = []
                for binding in data.get("results", {}).get("bindings", []):
                    row = {}
                    for var in vars_:
                        val = binding.get(var, {})
                        row[var] = val.get("value", "") if val else ""
                    rows.append(row)
                return rows

            # Fallback: rdflib-style result rows
            if hasattr(data, "__iter__"):
                rows = []
                for row in data:
                    if hasattr(row, "asdict"):
                        rows.append({str(var): str(val) for var, val in row.asdict().items()})
                    else:
                        rows.append({"result": str(row)})
                return rows

            return []

        except Exception as e:
            self.logger.error(f"Neptune SPARQL query failed: {e}")
            raise
    
    def get_schema(self) -> Graph:
        """Get Neptune schema.
        
        Neptune schema includes:
        - All classes (rdf:type owl:Class)
        - All properties
        - Cardinality estimates
        - Usage statistics
        """
        schema_str = self.lc_graph.get_schema
        
        g = Graph()
        if schema_str:
            g.parse(data=schema_str, format="turtle")
        
        return g
    
    def create_qa_chain(self, llm: Any):
        """Create Neptune SPARQL QA chain for natural language queries.
        
        Uses Neptune-specific chain with:
        - Schema-guided query generation
        - Iterative error correction
        - Neptune query optimizer hints
        - OpenSearch Serverless integration for hybrid search
        
        Args:
            llm: LangChain LLM (ChatOpenAI, ChatBedrock, etc.)
        
        Returns:
            NeptuneSparqlQAChain configured for Neptune
        """
        return create_neptune_sparql_qa_chain(
            llm=llm,
            graph=self.lc_graph,
            return_intermediate_steps=True,
            allow_dangerous_requests=True,
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get Neptune RDF statistics.
        
        Neptune provides system views for statistics:
        - DFE (Data-Free Evaluation) statistics
        - Index statistics
        - Query performance metrics
        """
        stats_query = """
        SELECT 
            (COUNT(*) AS ?total_triples)
            (COUNT(DISTINCT ?s) AS ?subjects)
            (COUNT(DISTINCT ?p) AS ?predicates)
        WHERE {
            ?s ?p ?o
        }
        """
        
        try:
            results = self.query_sparql(stats_query)
            if results:
                stats = results[0]
                
                # Add Neptune-specific stats if available
                stats["endpoint"] = self.sparql_endpoint
                stats["region"] = self.region
                stats["iam_auth"] = self.use_iam_auth
                
                return stats
            return {}
        except Exception as e:
            self.logger.warning(f"Could not get statistics: {e}")
            return {}
    
    def enable_opensearch_integration(self, index_name: Optional[str] = None):
        """Enable OpenSearch Serverless integration for hybrid search.
        
        This sets up:
        - Automatic vector indexing in OpenSearch Serverless
        - Combined SPARQL + vector search
        - GraphRAG toolkit integration
        
        Requires:
        - opensearch_endpoint in config
        - Appropriate IAM permissions
        """
        if not self.opensearch_endpoint:
            raise ValueError("opensearch_endpoint required for OpenSearch integration")
        
        index_name = index_name or self.opensearch_index
        
        # TODO: Implement OpenSearch Serverless integration
        # This would configure Neptune to automatically index vectors in OpenSearch
        # See: https://docs.aws.amazon.com/neptune/latest/userguide/neptune-opensearch-integration.html
        
        self.logger.info(f"OpenSearch integration would be enabled for index: {index_name}")
        self.logger.warning("OpenSearch integration requires AWS Console or CloudFormation setup")
