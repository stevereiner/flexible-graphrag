"""
LangChain Property Graph Adapters

These adapters provide access to additional property graph databases
via LangChain, complementing LlamaIndex's native support.

Databases supported:
- ArangoDB (multi-model: document, graph, key-value)
- Amazon Neptune Analytics (serverless property graph)
- Amazon Neptune Database (property graph mode)
- Apache AGE (PostgreSQL extension)
- Azure Cosmos DB for Gremlin
- Google Spanner Graph

All adapters follow the same pattern:
1. Use LangChain's native graph classes
2. Wrap with TextToGraphQueryRetriever for LlamaIndex integration
3. Support natural language to Cypher/Gremlin/OpenCypher translation
"""

from typing import Dict, Any, Optional
import logging

# ArangoDB
try:
    from langchain_arangodb import ArangoGraph, ArangoGraphQAChain
    ARANGODB_AVAILABLE = True
except ImportError:
    ARANGODB_AVAILABLE = False

# Amazon Neptune
try:
    from langchain_aws.graphs import NeptuneAnalyticsGraph, NeptuneGraph
    from langchain_aws.chains import create_neptune_opencypher_qa_chain
    NEPTUNE_AVAILABLE = True
except ImportError:
    NEPTUNE_AVAILABLE = False

# Apache AGE
try:
    from langchain_community.graphs import AGEGraph
    APACHE_AGE_AVAILABLE = True
except ImportError:
    APACHE_AGE_AVAILABLE = False

# Azure Cosmos DB
try:
    from langchain_community.graphs import CosmosDBGremlinGraph
    COSMOS_DB_AVAILABLE = True
except ImportError:
    COSMOS_DB_AVAILABLE = False

# Google Spanner Graph (Cloud Spanner)
try:
    from langchain_google_spanner import SpannerGraphStore
    SPANNER_AVAILABLE = True
except ImportError:
    SPANNER_AVAILABLE = False


class ArangoDBAdapter:
    """
    ArangoDB multi-model database adapter.
    
    ArangoDB combines:
    - Document store (JSON)
    - Graph database (edges between documents)
    - Key-value store
    - Full-text search
    
    Advantages:
    - Multi-model flexibility
    - AQL (ArangoDB Query Language) - SQL-like
    - Horizontal scaling (sharding)
    - Built-in search with ArangoSearch
    
    Configuration:
    {
        "url": "http://localhost:8529",
        "database": "flexible-graphrag",
        "username": "root",
        "password": "password",
        "graph_name": "knowledge_graph"  # ArangoDB named graph
    }
    
    References:
    - https://python.langchain.com/docs/integrations/graphs/arangodb
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not ARANGODB_AVAILABLE:
            raise ImportError("langchain-arangodb required. Install: pip install langchain-arangodb")
        
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.lc_graph = ArangoGraph(
            url=config["url"],
            database=config["database"],
            username=config["username"],
            password=config["password"],
            graph_name=config.get("graph_name", "knowledge_graph")
        )
        
        self.logger.info(f"Connected to ArangoDB at {config['url']}")
    
    def create_qa_chain(self, llm: Any):
        """Create AQL QA chain for natural language queries."""
        return ArangoGraphQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )
    
    def get_graph(self):
        """Get LangChain graph object for use with TextToGraphQueryRetriever."""
        return self.lc_graph


class NeptunePropertyGraphAdapter:
    """
    Amazon Neptune Database property graph adapter (OpenCypher).
    
    Neptune "OneGraph" architecture:
    - Same data accessible via SPARQL (RDF) or OpenCypher (property graph)
    - Choose query language based on use case
    - Unified storage, dual query interfaces
    
    Configuration:
    {
        "host": "my-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com",
        "port": 8182,
        "region": "us-east-1",
        "use_iam_auth": true,
        "use_https": true
    }
    
    References:
    - https://docs.aws.amazon.com/neptune/latest/userguide/access-graph-opencypher.html
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not NEPTUNE_AVAILABLE:
            raise ImportError("langchain-aws required. Install: pip install langchain-aws boto3")
        
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.lc_graph = NeptuneGraph(
            host=config["host"],
            port=config.get("port", 8182),
            use_iam_auth=config.get("use_iam_auth", False),
            region_name=config.get("region", "us-east-1"),
            use_https=config.get("use_https", True)
        )
        
        self.logger.info(f"Connected to Neptune property graph at {config['host']}")
    
    def create_qa_chain(self, llm: Any):
        """Create Neptune OpenCypher QA chain."""
        return create_neptune_opencypher_qa_chain(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            return_intermediate_steps=True
        )
    
    def get_graph(self):
        return self.lc_graph


class NeptuneAnalyticsAdapter:
    """
    Amazon Neptune Analytics serverless graph adapter.
    
    Neptune Analytics:
    - Serverless (no cluster management)
    - Optimized for analytics workloads
    - OpenCypher query language
    - Pay-per-query pricing
    - Graph algorithms built-in
    
    Configuration:
    {
        "graph_identifier": "g-abcdef12345",
        "region": "us-east-1"
    }
    
    References:
    - https://docs.aws.amazon.com/neptune-analytics/latest/userguide/
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not NEPTUNE_AVAILABLE:
            raise ImportError("langchain-aws required. Install: pip install langchain-aws boto3")
        
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.lc_graph = NeptuneAnalyticsGraph(
            graph_identifier=config["graph_identifier"],
            region_name=config.get("region", "us-east-1")
        )
        
        self.logger.info(f"Connected to Neptune Analytics graph {config['graph_identifier']}")
    
    def create_qa_chain(self, llm: Any):
        """Create Neptune Analytics OpenCypher QA chain."""
        return create_neptune_opencypher_qa_chain(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            return_intermediate_steps=True
        )
    
    def get_graph(self):
        return self.lc_graph


class ApacheAGEAdapter:
    """
    Apache AGE (A Graph Extension) PostgreSQL adapter.
    
    AGE extends PostgreSQL with:
    - Property graph model
    - Cypher query language
    - Leverages PostgreSQL's ACID guarantees
    - Combines relational + graph queries
    
    Configuration:
    {
        "host": "localhost",
        "port": 5432,
        "database": "flexiblegraphrag",
        "username": "postgres",
        "password": "password",
        "graph_name": "knowledge_graph"
    }
    
    References:
    - https://age.apache.org/
    - https://python.langchain.com/docs/integrations/graphs/apache_age
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not APACHE_AGE_AVAILABLE:
            raise ImportError("langchain-community required. Install: pip install langchain-community psycopg2-binary")
        
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Build connection URL
        conn_url = (
            f"postgresql://{config['username']}:{config['password']}"
            f"@{config['host']}:{config.get('port', 5432)}/{config['database']}"
        )
        
        self.lc_graph = AGEGraph(
            graph_name=config.get("graph_name", "knowledge_graph"),
            conf={"database_url": conn_url}
        )
        
        self.logger.info(f"Connected to Apache AGE at {config['host']}")
    
    def create_qa_chain(self, llm: Any):
        """Create Cypher QA chain for AGE."""
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain

        return GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )
    
    def get_graph(self):
        return self.lc_graph


class CosmosDBGremlinAdapter:
    """
    Azure Cosmos DB for Gremlin adapter.
    
    Cosmos DB Gremlin:
    - Serverless or provisioned throughput
    - Global distribution
    - Apache TinkerPop Gremlin API
    - Multi-model (document + graph)
    
    Configuration:
    {
        "url": "wss://my-cosmos.gremlin.cosmos.azure.com:443/",
        "username": "/dbs/mydb/colls/mygraph",
        "password": "primary_key",
        "database": "mydb",
        "collection": "mygraph"
    }
    
    References:
    - https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not COSMOS_DB_AVAILABLE:
            raise ImportError("langchain-community required. Install: pip install langchain-community gremlinpython")
        
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.lc_graph = CosmosDBGremlinGraph(
            url=config["url"],
            username=config["username"],
            password=config["password"],
            database=config.get("database", "graphdb"),
            collection=config.get("collection", "graph")
        )
        
        self.logger.info(f"Connected to Azure Cosmos DB Gremlin at {config['url']}")
    
    def create_qa_chain(self, llm: Any):
        """Create Gremlin QA chain for Cosmos DB."""
        from langchain_community.chains.graph_qa.gremlin import GremlinQAChain

        return GremlinQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )
    
    def get_graph(self):
        return self.lc_graph


class SpannerGraphAdapter:
    """
    Google Cloud Spanner Graph adapter.
    
    Spanner Graph:
    - Globally distributed
    - Strong consistency
    - SQL + graph queries (GQL - Graph Query Language)
    - Horizontal scalability
    
    Configuration:
    {
        "project_id": "my-gcp-project",
        "instance_id": "my-spanner-instance",
        "database_id": "my-database",
        "credentials_path": "/path/to/service-account.json"  # Optional
    }
    
    References:
    - https://cloud.google.com/spanner/docs/graph/overview
    """
    
    def __init__(self, config: Dict[str, Any]):
        if not SPANNER_AVAILABLE:
            raise ImportError("langchain-google-spanner required. Install: pip install langchain-google-spanner")
        
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Set credentials if provided
        credentials_path = config.get("credentials_path")
        if credentials_path:
            import os
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        self.lc_graph = SpannerGraphStore(
            project_id=config["project_id"],
            instance_id=config["instance_id"],
            database_id=config["database_id"]
        )
        
        self.logger.info(f"Connected to Spanner Graph in project {config['project_id']}")
    
    def create_qa_chain(self, llm: Any):
        """Create GQL QA chain for Spanner.
        
        Note: Spanner uses GQL (Graph Query Language), which is similar to Cypher
        but with some differences. LangChain may not have native support yet.
        """
        # TODO: Check if LangChain has native Spanner GQL QA chain
        # For now, use generic approach
        self.logger.warning("Spanner GQL QA chain may require custom implementation")
        
        # Fallback to generic pattern
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain

        return GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )
    
    def get_graph(self):
        return self.lc_graph


# Factory function for easy adapter creation
def create_property_graph_adapter(db_type: str, config: Dict[str, Any]):
    """
    Factory to create property graph adapters.
    
    Args:
        db_type: One of 'arangodb', 'neptune', 'neptune_analytics', 
                'apache_age', 'cosmos_gremlin', 'spanner'
        config: Database-specific configuration
    
    Returns:
        Adapter instance
    
    Example:
        >>> adapter = create_property_graph_adapter('arangodb', {
        ...     'url': 'http://localhost:8529',
        ...     'database': 'test',
        ...     'username': 'root',
        ...     'password': 'password'
        ... })
        >>> lc_graph = adapter.get_graph()
    """
    adapters = {
        'arangodb': ArangoDBAdapter,
        'neptune': NeptunePropertyGraphAdapter,
        'neptune_analytics': NeptuneAnalyticsAdapter,
        'apache_age': ApacheAGEAdapter,
        'cosmos_gremlin': CosmosDBGremlinAdapter,
        'spanner': SpannerGraphAdapter,
    }
    
    if db_type not in adapters:
        raise ValueError(f"Unknown property graph type: {db_type}. Choose from: {list(adapters.keys())}")
    
    return adapters[db_type](config)
