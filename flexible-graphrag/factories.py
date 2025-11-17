from typing import Dict, Any
import logging

from llama_index.llms.openai import OpenAI
from llama_index.llms.ollama import Ollama
from llama_index.llms.gemini import Gemini
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.anthropic import Anthropic
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.vector_stores.neo4jvector import Neo4jVectorStore
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.vector_stores.elasticsearch import ElasticsearchStore, AsyncBM25Strategy
from llama_index.vector_stores.opensearch import OpensearchVectorStore, OpensearchVectorClient
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.graph_stores.kuzu import KuzuPropertyGraphStore
from llama_index.graph_stores.falkordb import FalkorDBPropertyGraphStore
from llama_index.graph_stores.memgraph import MemgraphPropertyGraphStore
from llama_index.graph_stores.nebula.nebula_property_graph import (
    NebulaPropertyGraphStore,
)
from llama_index.graph_stores.neptune.analytics_property_graph import (
    NeptuneAnalyticsPropertyGraphStore,
)
from llama_index.graph_stores.neptune.database_property_graph import (
    NeptuneDatabasePropertyGraphStore,
)

from llama_index.graph_stores.arcadedb import ArcadeDBPropertyGraphStore

from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.storage.docstore import SimpleDocumentStore
from qdrant_client import QdrantClient, AsyncQdrantClient
import kuzu
import os

from config import LLMProvider, VectorDBType, GraphDBType, SearchDBType

# Import Neptune Analytics wrapper from separate module
from neptune_analytics_wrapper import NeptuneAnalyticsNoVectorWrapper

logger = logging.getLogger(__name__)


def get_embedding_dimension(llm_provider: LLMProvider, llm_config: Dict[str, Any]) -> int:
    """
    Get the embedding dimension based on LLM provider and specific model.
    Centralized function to avoid repeating logic across all database factories.
    """
    if llm_provider == LLMProvider.OPENAI:
        embedding_model = llm_config.get("embedding_model", "text-embedding-3-small")
        # OpenAI embedding dimensions by model
        if "text-embedding-3-large" in embedding_model:
            return 3072
        elif "text-embedding-3-small" in embedding_model:
            return 1536
        elif "text-embedding-ada-002" in embedding_model:
            return 1536
        else:
            return 1536  # Default for OpenAI
    
    elif llm_provider == LLMProvider.OLLAMA:
        embedding_model = llm_config.get("embedding_model", "mxbai-embed-large")
        # Ollama embedding dimensions by model
        if "mxbai-embed-large" in embedding_model:
            return 1024
        elif "nomic-embed-text" in embedding_model:
            return 768
        elif "all-minilm" in embedding_model:
            return 384
        else:
            return 1024  # Default for Ollama
    
    elif llm_provider == LLMProvider.AZURE_OPENAI:
        # Azure OpenAI uses same models as OpenAI
        embedding_model = llm_config.get("embedding_model", "text-embedding-3-small")
        if "text-embedding-3-large" in embedding_model:
            return 3072
        elif "text-embedding-3-small" in embedding_model:
            return 1536
        else:
            return 1536  # Default for Azure OpenAI
    
    else:
        # Default fallback for other providers
        logger.warning(f"Unknown embedding dimension for provider {llm_provider}, defaulting to 1536")
        return 1536

class LLMFactory:
    """Factory for creating LLM instances based on configuration"""
    
    @staticmethod
    def create_llm(provider: LLMProvider, config: Dict[str, Any]):
        """Create LLM instance based on provider and configuration"""
        
        logger.info(f"Creating LLM with provider: {provider}")
        
        if provider == LLMProvider.OPENAI:
            return OpenAI(
                model=config.get("model", "gpt-4o-mini"),
                temperature=config.get("temperature", 0.1),
                api_key=config.get("api_key"),
                max_tokens=config.get("max_tokens", 4000),
                request_timeout=config.get("timeout", 120.0)
            )
        
        elif provider == LLMProvider.OLLAMA:
            model = config.get("model", "llama3.1:8b")
            base_url = config.get("base_url", "http://localhost:11434")
            timeout = config.get("timeout", 300.0)
            logger.info(f"Configuring Ollama LLM - Model: {model}, Base URL: {base_url}, Timeout: {timeout}s")
            return Ollama(
                model=model,
                base_url=base_url,
                temperature=config.get("temperature", 0.1),
                request_timeout=timeout
            )
        
        elif provider == LLMProvider.GEMINI:
            return Gemini(
                model=config.get("model", "models/gemini-1.5-flash"),
                api_key=config.get("api_key"),
                temperature=config.get("temperature", 0.1),
                request_timeout=config.get("timeout", 120.0)
            )
        
        elif provider == LLMProvider.AZURE_OPENAI:
            return AzureOpenAI(
                engine=config["engine"],
                model=config.get("model", "gpt-4"),
                temperature=config.get("temperature", 0.1),
                azure_endpoint=config["azure_endpoint"],
                api_key=config["api_key"],
                api_version=config.get("api_version", "2024-02-01"),
                request_timeout=config.get("timeout", 120.0)
            )
        
        elif provider == LLMProvider.ANTHROPIC:
            return Anthropic(
                model=config.get("model", "claude-3-5-sonnet-20241022"),
                api_key=config.get("api_key"),
                temperature=config.get("temperature", 0.1),
                request_timeout=config.get("timeout", 120.0)
            )
        
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    @staticmethod
    def create_embedding_model(provider: LLMProvider, config: Dict[str, Any]):
        """Create embedding model based on provider"""
        
        logger.info(f"Creating embedding model with provider: {provider}")
        
        if provider in [LLMProvider.OPENAI, LLMProvider.AZURE_OPENAI]:
            if provider == LLMProvider.AZURE_OPENAI:
                return AzureOpenAIEmbedding(
                    model=config.get("embedding_model", "text-embedding-3-small"),
                    azure_endpoint=config["azure_endpoint"],
                    api_key=config["api_key"],
                    api_version=config.get("api_version", "2024-02-01")
                )
            else:
                return OpenAIEmbedding(
                    model_name=config.get("embedding_model", "text-embedding-3-small"),
                    api_key=config.get("api_key")
                )
        
        elif provider == LLMProvider.OLLAMA:
            embedding_model = config.get("embedding_model", "mxbai-embed-large")
            base_url = config.get("base_url", "http://localhost:11434")
            logger.info(f"Configuring Ollama Embeddings - Model: {embedding_model}, Base URL: {base_url}")
            return OllamaEmbedding(
                model_name=embedding_model,
                base_url=base_url
            )
        
        else:
            # Default to OpenAI for other providers
            logger.warning(f"No embedding model implementation for {provider}, using OpenAI default")
            return OpenAIEmbedding(model_name="text-embedding-3-small")

class DatabaseFactory:
    """Factory for creating database connections"""
    
    @staticmethod
    def create_vector_store(db_type: VectorDBType, config: Dict[str, Any], llm_provider: LLMProvider = None, llm_config: Dict[str, Any] = None):
        """Create vector store based on database type"""
        
        logger.info(f"Creating vector store with type: {db_type}")
        
        # Get embedding dimension from centralized function
        embed_dim = config.get("embed_dim")
        if embed_dim is None and llm_provider and llm_config:
            embed_dim = get_embedding_dimension(llm_provider, llm_config)
            logger.info(f"Detected embedding dimension: {embed_dim} for provider: {llm_provider}")
        elif embed_dim is None:
            embed_dim = 1536  # Fallback default
            logger.warning(f"No embedding dimension detected, using fallback: {embed_dim}")
        
        if db_type == VectorDBType.NONE:
            logger.info("Vector search disabled - no vector store created")
            return None
        
        elif db_type == VectorDBType.QDRANT:
            client = QdrantClient(
                host=config.get("host", "localhost"),
                port=config.get("port", 6333),
                api_key=config.get("api_key"),
                https=config.get("https", False),  # Default to HTTP for local instances
                check_compatibility=False  # Skip version compatibility check
            )
            aclient = AsyncQdrantClient(
                host=config.get("host", "localhost"),
                port=config.get("port", 6333),
                api_key=config.get("api_key"),
                https=config.get("https", False),  # Default to HTTP for local instances
                check_compatibility=False  # Skip version compatibility check
            )
            collection_name = config.get("collection_name", "hybrid_search")
            logger.info(f"Creating Qdrant vector store - Collection: {collection_name}, Embed dim: {embed_dim}")
            
            return QdrantVectorStore(
                client=client,
                aclient=aclient,
                collection_name=collection_name
            )
        
        elif db_type == VectorDBType.NEO4J:
            url = config.get("url", "bolt://localhost:7687")
            index_name = config.get("index_name", "hybrid_search_vector")
            logger.info(f"Creating Neo4j vector store - URL: {url}, Index: {index_name}, Embed dim: {embed_dim}")
            
            return Neo4jVectorStore(
                username=config.get("username", "neo4j"),
                password=config["password"],
                url=url,
                embedding_dimension=embed_dim,
                database=config.get("database", "neo4j"),
                index_name=index_name
            )
        
        elif db_type == VectorDBType.ELASTICSEARCH:
            from llama_index.vector_stores.elasticsearch import AsyncDenseVectorStrategy
            
            index_name = config.get("index_name", "hybrid_search_vector")
            es_url = config.get("url", "http://localhost:9200")
            logger.info(f"Creating Elasticsearch vector store - Index: {index_name}, URL: {es_url}, Embed dim: {embed_dim}")
            
            return ElasticsearchStore(
                index_name=index_name,
                es_url=es_url,
                es_user=config.get("username"),
                es_password=config.get("password"),
                retrieval_strategy=AsyncDenseVectorStrategy()  # Pure vector search (fix query parsing issue)
            )
        
        elif db_type == VectorDBType.OPENSEARCH:
            from llama_index.vector_stores.opensearch import OpensearchVectorClient
            
            # Create OpenSearch vector client with hybrid search pipeline
            logger.info(f"Creating OpenSearch vector store with embedding dimension: {embed_dim}")
            
            client = OpensearchVectorClient(
                endpoint=config.get("url", "http://localhost:9201"),
                index=config.get("index_name", "hybrid_search_vector"),
                dim=embed_dim,
                embedding_field=config.get("embedding_field", "embedding"),
                text_field=config.get("text_field", "content"),
                search_pipeline=config.get("search_pipeline", "hybrid-search-pipeline"),  # Enable hybrid search pipeline
                http_auth=(config.get("username"), config.get("password")) if config.get("username") else None
            )
            
            return OpensearchVectorStore(client)
        
        elif db_type == VectorDBType.CHROMA:
            from llama_index.vector_stores.chroma import ChromaVectorStore
            import chromadb
            
            collection_name = config.get("collection_name", "hybrid_search")
            
            # Check if HTTP client configuration is provided
            host = config.get("host")
            port = config.get("port")
            
            if host and port:
                # HTTP Client mode - connect to remote ChromaDB server
                logger.info(f"Creating Chroma vector store (HTTP) - Host: {host}:{port}, Collection: {collection_name}, Embed dim: {embed_dim}")
                chroma_client = chromadb.HttpClient(host=host, port=port)
            else:
                # Persistent Client mode - local file-based storage (default)
                persist_directory = config.get("persist_directory", "./chroma_db")
                logger.info(f"Creating Chroma vector store (Local) - Collection: {collection_name}, Persist dir: {persist_directory}, Embed dim: {embed_dim}")
                chroma_client = chromadb.PersistentClient(path=persist_directory)
            
            chroma_collection = chroma_client.get_or_create_collection(collection_name)
            
            return ChromaVectorStore(chroma_collection=chroma_collection)
        
        elif db_type == VectorDBType.MILVUS:
            from llama_index.vector_stores.milvus import MilvusVectorStore
            
            host = config.get("host", "localhost")
            port = config.get("port", 19530)
            collection_name = config.get("collection_name", "hybrid_search")
            
            # Use URI format for proper connection to Milvus server
            uri = f"http://{host}:{port}"
            logger.info(f"Creating Milvus vector store - URI: {uri}, Collection: {collection_name}, Embed dim: {embed_dim}")
            
            return MilvusVectorStore(
                uri=uri,
                collection_name=collection_name,
                dim=embed_dim,
                user=config.get("username"),
                password=config.get("password"),
                token=config.get("token"),  # For cloud Milvus
                overwrite=config.get("overwrite", False)
            )
        
        elif db_type == VectorDBType.WEAVIATE:
            from llama_index.vector_stores.weaviate import WeaviateVectorStore
            import weaviate
            
            url = config.get("url", "http://localhost:8081")
            index_name = config.get("index_name", "HybridSearch")  # Must start with capital letter
            logger.info(f"Creating Weaviate vector store - URL: {url}, Index: {index_name}, Embed dim: {embed_dim}")
            
            # Create Weaviate client using v4 API
            if config.get("api_key"):
                # For authenticated instances, use connect_to_custom (REST-only)
                from weaviate.classes.init import Auth, AdditionalConfig, Timeout
                client = weaviate.connect_to_custom(
                    http_host=url.replace("http://", "").replace("https://", "").replace(":8081", ""),
                    http_port=8081,
                    http_secure=False,
                    grpc_host="localhost",  # Required parameter but won't be used
                    grpc_port=50051,       # Required parameter but won't be used  
                    grpc_secure=False,
                    skip_init_checks=True,  # Skip all health checks - REST-only mode
                    additional_config=AdditionalConfig(
                        timeout=Timeout(init=60, query=60, insert=180)
                    ),
                    auth_credentials=Auth.api_key(config.get("api_key")),
                    headers=config.get("additional_headers", {})
                )
            else:
                # For local unauthenticated instances (REST-only)
                from weaviate.classes.init import AdditionalConfig, Timeout
                client = weaviate.connect_to_custom(
                    http_host=url.replace("http://", "").replace("https://", "").replace(":8081", ""),
                    http_port=8081,
                    http_secure=False,
                    grpc_host="localhost",  # Required parameter but won't be used
                    grpc_port=50051,       # Required parameter but won't be used
                    grpc_secure=False,
                    skip_init_checks=True,  # Skip all health checks - REST-only mode
                    additional_config=AdditionalConfig(
                        timeout=Timeout(init=60, query=60, insert=180)
                    ),
                    headers=config.get("additional_headers", {})
                )
            
            return WeaviateVectorStore(
                weaviate_client=client,
                index_name=index_name,
                text_key=config.get("text_key", "content")
            )
        
        elif db_type == VectorDBType.PINECONE:
            from llama_index.vector_stores.pinecone import PineconeVectorStore
            from pinecone import Pinecone, ServerlessSpec
            
            api_key = config.get("api_key")
            region = config.get("region", "us-east-1")
            cloud = config.get("cloud", "aws")
            index_name = config.get("index_name", "hybrid-search")
            metric = config.get("metric", "cosine")
            
            logger.info(f"Creating Pinecone vector store - Index: {index_name}, Cloud: {cloud}, Region: {region}, Metric: {metric}, Embed dim: {embed_dim}")
            
            if not api_key:
                raise ValueError("Pinecone API key is required")
            
            # Initialize Pinecone client
            pc = Pinecone(api_key=api_key)
            
            # Create or get index
            existing_indexes = [index.name for index in pc.list_indexes()]
            if index_name not in existing_indexes:
                logger.info(f"Creating new Pinecone index: {index_name} with dimension: {embed_dim}")
                pc.create_index(
                    name=index_name,
                    dimension=embed_dim,  # Auto-detected from embedding model
                    metric=metric,
                    spec=ServerlessSpec(cloud=cloud, region=region)
                )
            else:
                logger.info(f"Using existing Pinecone index: {index_name}")
            
            pinecone_index = pc.Index(index_name)
            
            return PineconeVectorStore(
                pinecone_index=pinecone_index,
                namespace=config.get("namespace")
            )
        
        elif db_type == VectorDBType.POSTGRES:
            from llama_index.vector_stores.postgres import PGVectorStore
            
            connection_string = config.get("connection_string")
            if not connection_string:
                # Build connection string from components
                host = config.get("host", "localhost")
                port = config.get("port", 5432)
                database = config.get("database", "postgres")
                username = config.get("username", "postgres")
                password = config.get("password")
                connection_string = f"postgresql://{username}:{password}@{host}:{port}/{database}"
            
            table_name = config.get("table_name", "hybrid_search_vectors")
            logger.info(f"Creating PostgreSQL vector store - Table: {table_name}, Embed dim: {embed_dim}")
            
            return PGVectorStore.from_params(
                database=config.get("database", "postgres"),
                host=config.get("host", "localhost"),
                password=config.get("password"),
                port=config.get("port", 5432),
                user=config.get("username", "postgres"),
                table_name=table_name,
                embed_dim=embed_dim
            )
        
        elif db_type == VectorDBType.LANCEDB:
            from llama_index.vector_stores.lancedb import LanceDBVectorStore
            import lancedb
            
            uri = config.get("uri", "./lancedb")
            table_name = config.get("table_name", "hybrid_search")
            logger.info(f"Creating LanceDB vector store - URI: {uri}, Table: {table_name}, Embed dim: {embed_dim}")
            
            # Connect to LanceDB
            db = lancedb.connect(uri)
            
            return LanceDBVectorStore(
                uri=uri,
                table_name=table_name,
                vector_column_name=config.get("vector_column_name", "vector"),
                text_column_name=config.get("text_column_name", "text")
            )
        
        else:
            raise ValueError(f"Unsupported vector database: {db_type}")
    
    @staticmethod
    def create_graph_store(db_type: GraphDBType, config: Dict[str, Any], schema_config: Dict[str, Any] = None, has_separate_vector_store: bool = False, llm_provider: LLMProvider = None, llm_config: Dict[str, Any] = None, app_config=None):
        """Create graph store based on database type"""
        
        logger.info(f"Creating graph store with type: {db_type}")
        
        if db_type == GraphDBType.NONE:
            logger.info("Graph search disabled - no graph store created")
            return None
        
        elif db_type == GraphDBType.NEO4J:
            return Neo4jPropertyGraphStore(
                username=config.get("username", "neo4j"),
                password=config["password"],
                url=config.get("url", "bolt://localhost:7687"),
                database=config.get("database", "neo4j"),
                refresh_schema=False  # Disable APOC schema refresh to avoid apoc.meta.data calls
            )
        
        elif db_type == GraphDBType.KUZU:
            
            db_path = config.get("db_path", "./kuzu_db")
            
            # For development/testing: ensure clean schema by recreating database
            # This prevents "Table Entity does not exist" errors when switching models or schemas
            import os
            import shutil
            if os.path.exists(db_path):
                try:
                    shutil.rmtree(db_path)
                    logger.info(f"Cleaned existing Kuzu database at {db_path} for fresh schema")
                except Exception as e:
                    logger.warning(f"Could not clean Kuzu database: {e}")
            
            kuzu_db = kuzu.Database(db_path)
            
            # Get Kuzu-specific configuration from GRAPH_DB_CONFIG
            use_structured_schema = config.get("use_structured_schema", False)  # Default to False
            use_vector_index = config.get("use_vector_index", False)  # Default to False
            
            logger.info(f"Kuzu configuration from GRAPH_DB_CONFIG: use_structured_schema={use_structured_schema}, use_vector_index={use_vector_index}")
            
            # Helper function to process validation schema
            def process_validation_schema(validation_data):
                if isinstance(validation_data, dict) and "relationships" in validation_data:
                    return validation_data["relationships"]
                elif isinstance(validation_data, list):
                    # Convert JSON arrays to tuples for Kuzu compatibility
                    relationship_schema = []
                    for item in validation_data:
                        if isinstance(item, list) and len(item) == 3:
                            relationship_schema.append(tuple(item))
                        elif isinstance(item, tuple):
                            relationship_schema.append(item)
                        else:
                            logger.warning(f"Invalid relationship schema item: {item}. Expected [source, relation, target] format.")
                    return relationship_schema
                return None

            # Configure Kuzu based on extractor type from app_config
            extractor_type = getattr(app_config, 'kg_extractor_type', 'schema')
            logger.info(f"Configuring Kuzu for extractor type: {extractor_type}")
            logger.info(f"Schema config received: {schema_config}")
            
            # Determine schema configuration based on extractor type
            if extractor_type == 'simple':
                # SimpleLLMPathExtractor - no schema needed
                use_structured_schema = False
                relationship_schema = None
                logger.info("Using SimpleLLMPathExtractor - no structured schema")
            elif extractor_type == 'dynamic':
                # DynamicLLMPathExtractor - always use unstructured schema for dynamic table creation
                use_structured_schema = False
                relationship_schema = None
                if schema_config and schema_config.get('validation_schema'):
                    # Full validation schema provided - but still use unstructured for dynamic creation
                    entities = schema_config.get('entities', [])
                    relations = schema_config.get('relations', [])
                    logger.info(f"Using DynamicLLMPathExtractor with validation schema guidance: {len(entities) if entities else 0} entities, {len(relations) if relations else 0} relations (unstructured schema)")
                elif schema_config and (schema_config.get('entities') or schema_config.get('relations')):
                    # Starting entities/relations provided - use unstructured schema for flexibility
                    entities = schema_config.get('entities', [])
                    relations = schema_config.get('relations', [])
                    logger.info(f"Using DynamicLLMPathExtractor with starting guidance: {len(entities) if entities else 0} entities, {len(relations) if relations else 0} relations (unstructured schema)")
                else:
                    # No schema guidance - full LLM freedom with unstructured schema
                    logger.info("Using DynamicLLMPathExtractor with no starting schema (full LLM freedom, unstructured schema)")
            else:  # 'schema' or default
                # SchemaLLMPathExtractor - schema handling based on use_structured_schema config
                relationship_schema = None
                
                if use_structured_schema and schema_config and schema_config.get('validation_schema'):
                    logger.info(f"Using SchemaLLMPathExtractor with user-configured schema (structured extraction enabled)")
                    relationship_schema = process_validation_schema(schema_config['validation_schema'])
                    logger.info(f"Processed {len(relationship_schema) if relationship_schema else 0} relationship rules for structured schema")
                elif use_structured_schema:
                    # Use SAMPLE_SCHEMA for SchemaLLMPathExtractor with full structured validation
                    logger.info("Using SchemaLLMPathExtractor with SAMPLE_SCHEMA (structured extraction enabled)")
                    from config import SAMPLE_SCHEMA
                    relationship_schema = process_validation_schema(SAMPLE_SCHEMA.get("validation_schema"))
                    logger.info(f"Using SAMPLE_SCHEMA with {len(relationship_schema) if relationship_schema else 0} relationship rules")
                else:
                    logger.info("Using SchemaLLMPathExtractor without structured schema (unstructured mode)")
            
            # Use the proper embedding model based on LLM provider
            if llm_provider and llm_config:
                embed_model = LLMFactory.create_embedding_model(llm_provider, llm_config)
                provider_name = llm_provider.value if hasattr(llm_provider, 'value') else str(llm_provider)
                logger.info(f"Embedding model: {provider_name}")
            else:
                # Fallback to OpenAI if no provider specified
                from llama_index.embeddings.openai import OpenAIEmbedding
                embed_model = OpenAIEmbedding(model_name="text-embedding-3-small")
                logger.warning("No LLM provider specified for Kuzu, falling back to OpenAI embeddings")
            
            # Log final configuration
            logger.info(f"Final Kuzu configuration: use_structured_schema={use_structured_schema}, use_vector_index={use_vector_index}, relationship_schema_count={len(relationship_schema) if relationship_schema else 0}")
            
            # Create KuzuPropertyGraphStore with configuration from GRAPH_DB_CONFIG
            graph_store = KuzuPropertyGraphStore(
                kuzu_db,
                has_structured_schema=use_structured_schema,
                use_vector_index=use_vector_index,
                embed_model=embed_model,
                relationship_schema=relationship_schema if use_structured_schema else None
            )
            
            # Schema will be initialized right before PropertyGraphIndex creation for better timing
            
            return graph_store
        
        elif db_type == GraphDBType.FALKORDB:
            url = config.get("url", "falkor://localhost:6379")
            database = config.get("database", "falkor")
            logger.info(f"Creating FalkorDB graph store - URL: {url} database: {database}")

            
            # Use standard FalkorDB store (indexes are the key optimization)
            graph_store = FalkorDBPropertyGraphStore(
                url=url,
                database=database,
                refresh_schema=False,  # Disable expensive schema refresh on init
                sanitize_query_output=True
            )
            
            # Create indexes for better performance
            try:
                logger.info("Creating FalkorDB indexes for optimization...")
                # Index on entity names for faster lookups
                graph_store.client.query("CREATE INDEX FOR (e:__Entity__) ON (e.name)")
                # Index on entity IDs
                graph_store.client.query("CREATE INDEX FOR (e:__Entity__) ON (e.id)")
                # Index on chunks
                graph_store.client.query("CREATE INDEX FOR (c:Chunk) ON (c.id)")
                logger.info("FalkorDB indexes created successfully")
            except Exception as e:
                logger.warning(f"Index creation failed (may already exist): {e}")
            
            return graph_store
        
        elif db_type == GraphDBType.ARCADEDB:
            host = config.get("host", "localhost")
            port = config.get("port", 2480)
            username = config.get("username", "root")
            password = config.get("password", "playwithdata")
            database = config.get("database", "flexible_graphrag")
            include_basic_schema = config.get("include_basic_schema", True)
            
            # Get embedding dimension from centralized function
            embed_dim = config.get("embed_dim")
            if embed_dim is None and llm_provider and llm_config:
                embed_dim = get_embedding_dimension(llm_provider, llm_config)
                logger.info(f"Detected embedding dimension for ArcadeDB: {embed_dim} for provider: {llm_provider}")
            elif embed_dim is None:
                embed_dim = 1536  # Fallback default
                logger.warning(f"No embedding dimension detected for ArcadeDB, using fallback: {embed_dim}")
            
            logger.info(f"Creating ArcadeDB graph store - Host: {host}:{port}, Database: {database}, Include basic schema: {include_basic_schema}, Embed dim: {embed_dim}")
            
            return ArcadeDBPropertyGraphStore(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                embedding_dimension=embed_dim,
                include_basic_schema=include_basic_schema
            )
        
        elif db_type == GraphDBType.MEMGRAPH:
            username = config.get("username", "")
            password = config.get("password", "")
            url = config.get("url", "bolt://localhost:7688")  # Default MemGraph port
            database = config.get("database", "memgraph")
            
            logger.info(f"Creating MemGraph graph store - URL: {url}, Database: {database}")
            logger.info("Using MemGraph-specific configuration to avoid relationship naming issues")
            
            return MemgraphPropertyGraphStore(
                username=username,
                password=password,
                url=url,
                database=database,
                refresh_schema=False  # Bypass schema validation to avoid naming conflicts
            )
        
        elif db_type == GraphDBType.NEBULA:
            # Handle both 'space' and 'space_name' for backward compatibility
            space = config.get("space") or config.get("space_name", "flexible_graphrag")
            overwrite = config.get("overwrite", True)
            
            # Connection parameters using correct parameter names
            username = config.get("username", "root")
            password = config.get("password", "nebula")
            # Build URL from address and port, or use provided URL
            if "url" in config:
                url = config["url"]
            else:
                address = config.get("address", "localhost")
                port = config.get("port", 9669)
                url = f"nebula://{address}:{port}"
            
            # Custom props schema including all required columns for LlamaIndex
            # Based on the error, LlamaIndex tries to insert these specific properties
            CUSTOM_PROPS_SCHEMA = "`source` STRING, `conversion_method` STRING, `file_type` STRING, `file_name` STRING, `_node_content` STRING, `_node_type` STRING, `document_id` STRING, `doc_id` STRING, `ref_doc_id` STRING, `triplet_source_id` STRING, `file_path` STRING, `file_size` INT, `creation_date` STRING, `last_modified_date` STRING"
            
            logger.info(f"Creating NebulaGraph graph store - Space: {space}, URL: {url}, Overwrite: {overwrite}")
            logger.info("Using custom props schema to include all required LlamaIndex properties")
            logger.info(f"Props schema: {CUSTOM_PROPS_SCHEMA}")
            
            return NebulaPropertyGraphStore(
                space=space,
                username=username,
                password=password,
                url=url,
                overwrite=overwrite,
                props_schema=CUSTOM_PROPS_SCHEMA
            )
        
        elif db_type == GraphDBType.NEPTUNE:
            import boto3
            from botocore.config import Config
            from botocore import UNSIGNED
            
            host = config.get("host")
            port = config.get("port", 8182)
            
            # AWS Credentials - support both explicit credentials and profile-based
            access_key = config.get("access_key")
            secret_key = config.get("secret_key")
            region = config.get("region")
            credentials_profile_name = config.get("credentials_profile_name")
            
            sign = config.get("sign", True)  # Default to True for SigV4 signing
            use_https = config.get("use_https", True)  # Default to True for HTTPS
            
            if not host:
                raise ValueError("Neptune host is required (format: <GRAPH NAME>.<CLUSTER ID>.<REGION>.neptune.amazonaws.com)")
            
            logger.info(f"Creating Neptune graph store - Host: {host}:{port}")
            
            # Create boto3 client with explicit credentials if provided
            client = None
            if access_key and secret_key:
                logger.info(f"Using explicit AWS credentials with region: {region}")
                
                # Create session with explicit credentials
                session = boto3.Session(
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name=region
                )
                
                # Create client parameters
                client_params = {}
                if region:
                    client_params["region_name"] = region
                
                protocol = "https" if use_https else "http"
                client_params["endpoint_url"] = f"{protocol}://{host}:{port}"
                
                # Create Neptune client
                if sign:
                    client = session.client("neptunedata", **client_params)
                else:
                    client = session.client(
                        "neptunedata",
                        **client_params,
                        config=Config(signature_version=UNSIGNED),
                    )
            elif credentials_profile_name:
                logger.info(f"Using AWS credentials profile: {credentials_profile_name}")
            elif region:
                logger.info(f"Using default AWS credentials with region: {region}")
            else:
                logger.info("Using default AWS credentials and region")
            
            return NeptuneDatabasePropertyGraphStore(
                host=host,
                port=port,
                client=client,  # Pass pre-configured client if we created one
                credentials_profile_name=credentials_profile_name if not client else None,
                region_name=region if not client else None,
                sign=sign,
                use_https=use_https
            )
        elif db_type == GraphDBType.NEPTUNE_ANALYTICS:
            import boto3
            from botocore.config import Config
            
            graph_identifier = config.get("graph_identifier")
            
            # AWS Credentials - support both explicit credentials and profile-based
            access_key = config.get("access_key")
            secret_key = config.get("secret_key")
            region = config.get("region")
            credentials_profile_name = config.get("credentials_profile_name")
            
            if not graph_identifier:
                raise ValueError("Neptune Analytics graph_identifier is required")
            
            logger.info(f"Creating Neptune Analytics graph store - Graph ID: {graph_identifier}, Region: {region}")
            # Debug logging (commented out to avoid exposing credentials in logs)
            # logger.info(f"Neptune Analytics raw config received: {config}")
            # logger.info(f"Neptune Analytics config keys: {list(config.keys())}")
            # logger.info(f"Neptune Analytics: access_key present: {bool(access_key)}, secret_key present: {bool(secret_key)}")
            
            # WORKAROUND: Due to a bug in LlamaIndex Neptune Analytics client creation
            # (line 143 in neptune.py: client = client instead of client = provided_client)
            # we cannot pass a pre-configured client. Instead, we set environment variables
            # and let Neptune Analytics create its own client.
            
            # IMPORTANT: Neptune Analytics has vector query limitations in LlamaIndex
            # We disable vector operations and use it purely as a graph store
            logger.warning("Neptune Analytics: Vector operations disabled due to LlamaIndex limitations. Using separate vector store is recommended.")
            
            if access_key and secret_key:
                logger.info(f"Using explicit AWS credentials with region: {region}")
                
                # WORKAROUND for LlamaIndex bug: Set credentials as environment variables
                # The bug at neptune.py line 143 prevents passing a client directly
                # So we must set env vars for boto3.Session() to pick up
                import os
                os.environ['AWS_ACCESS_KEY_ID'] = access_key
                os.environ['AWS_SECRET_ACCESS_KEY'] = secret_key
                if region:
                    os.environ['AWS_DEFAULT_REGION'] = region
                
                logger.info(f"Neptune Analytics: Set AWS credentials in environment for region: {region}")
                # Debug logging (commented out to avoid exposing credentials)
                # logger.info(f"Neptune Analytics: AWS_ACCESS_KEY_ID = {access_key[:10]}... (length: {len(access_key)})")
                
                try:
                    # Don't pass client (bug prevents it from working)
                    # Don't pass credentials_profile_name (let it be None to use env vars)
                    graph_store = NeptuneAnalyticsPropertyGraphStore(
                        graph_identifier=graph_identifier,
                        region_name=region
                    )
                    logger.info("Neptune Analytics: PropertyGraphStore created successfully")
                except Exception as e:
                    logger.error(f"Neptune Analytics: Failed to create PropertyGraphStore: {e}")
                    logger.error(f"Neptune Analytics: This may indicate boto3 cannot access environment variables")
                    raise
            elif credentials_profile_name:
                logger.info(f"Using AWS credentials profile: {credentials_profile_name}")
                graph_store = NeptuneAnalyticsPropertyGraphStore(
                    graph_identifier=graph_identifier,
                    credentials_profile_name=credentials_profile_name,
                    region_name=region
                )
            else:
                logger.info(f"Using default AWS credentials with region: {region}")
                graph_store = NeptuneAnalyticsPropertyGraphStore(
                    graph_identifier=graph_identifier,
                    region_name=region
                )
            
            wrapped_store = NeptuneAnalyticsNoVectorWrapper(graph_store)
            wrapped_store.supports_vector_queries = False
            
            logger.info("Neptune Analytics: Vector queries disabled - use separate VECTOR_DB for embeddings")
            logger.info(f"Neptune Analytics: Returning wrapper object of type: {type(wrapped_store)}")
            logger.info(f"Neptune Analytics: Wrapper has upsert_nodes: {hasattr(wrapped_store, 'upsert_nodes')}")
            logger.info(f"Neptune Analytics: Wrapper has vector_query: {hasattr(wrapped_store, 'vector_query')}")
            logger.info(f"Neptune Analytics: Wrapper supports_vector_queries = {wrapped_store.supports_vector_queries}")
            
            return wrapped_store
        
        else:
            raise ValueError(f"Unsupported graph database: {db_type}")
    
    @staticmethod
    def create_search_store(db_type: SearchDBType, config: Dict[str, Any], vector_db_type: VectorDBType = None, llm_provider: LLMProvider = None, llm_config: Dict[str, Any] = None):
        """Create search store for full-text search"""
        
        logger.info(f"Creating search store with type: {db_type}")
        
        # Get embedding dimension from centralized function
        embed_dim = config.get("embed_dim")
        if embed_dim is None and llm_provider and llm_config:
            embed_dim = get_embedding_dimension(llm_provider, llm_config)
            logger.info(f"Detected embedding dimension for search store: {embed_dim} for provider: {llm_provider}")
        elif embed_dim is None:
            embed_dim = 1536  # Fallback default
            logger.warning(f"No embedding dimension detected for search store, using fallback: {embed_dim}")
        
        if db_type == SearchDBType.NONE:
            logger.info("Full-text search disabled - no search store created")
            return None
        
        elif db_type == SearchDBType.BM25:
            # BM25 is handled differently - it's a retriever, not a store
            # We'll return None and handle it in the hybrid system
            logger.info("BM25 search selected - will be handled by BM25Retriever")
            return None
        
        elif db_type == SearchDBType.ELASTICSEARCH:
            from llama_index.vector_stores.elasticsearch import AsyncBM25Strategy
            
            index_name = config.get("index_name", "hybrid_search_fulltext")
            es_url = config.get("url", "http://localhost:9200")
            logger.info(f"Creating Elasticsearch search store - Index: {index_name}, URL: {es_url}, Embed dim: {embed_dim}")
            
            return ElasticsearchStore(
                index_name=index_name,
                es_url=es_url,
                es_user=config.get("username"),
                es_password=config.get("password"),
                retrieval_strategy=AsyncBM25Strategy()  # Explicit BM25 for keyword-only search
            )
        
        elif db_type == SearchDBType.OPENSEARCH:
            # Only create OpenSearch search store if vector DB is NOT OpenSearch (to avoid hybrid mode conflicts)
            if vector_db_type == VectorDBType.OPENSEARCH:
                logger.info("OpenSearch search store skipped - vector DB is also OpenSearch (using native hybrid search)")
                return None
            
            # Create OpenSearch vector store for fulltext-only search
            from llama_index.vector_stores.opensearch import OpensearchVectorStore, OpensearchVectorClient
            
            # Create OpenSearch vector client for fulltext search
            logger.info(f"Creating OpenSearch search store with embedding dimension: {embed_dim}")
            
            client = OpensearchVectorClient(
                endpoint=config.get("url", "http://localhost:9201"),
                index=config.get("index_name", "hybrid_search_fulltext"),
                dim=embed_dim,
                embedding_field=config.get("embedding_field", "embedding"),
                text_field=config.get("text_field", "content"),
                http_auth=(config.get("username"), config.get("password")) if config.get("username") else None
            )
            
            logger.info("OpenSearch search store created for fulltext-only search (VectorStoreQueryMode.TEXT_SEARCH)")
            return OpensearchVectorStore(client)
        
        else:
            raise ValueError(f"Unsupported search database: {db_type}")
    
    @staticmethod
    def create_bm25_retriever(docstore, config: Dict[str, Any] = None):
        """Create BM25 retriever with optional persistence"""
        
        logger.info("Creating BM25 retriever")
        
        if config is None:
            config = {}
        
        # Create BM25 retriever
        bm25_retriever = BM25Retriever.from_defaults(
            docstore=docstore,
            similarity_top_k=config.get("similarity_top_k", 10)
        )
        
        # Handle persistence if configured
        persist_dir = config.get("persist_dir")
        if persist_dir:
            # Ensure directory exists
            os.makedirs(persist_dir, exist_ok=True)
            logger.info(f"BM25 index will be persisted to: {persist_dir}")
            
            # The BM25Retriever uses the docstore which is already configured for persistence
            # The docstore will handle the actual persistence when the vector index is persisted
        
        return bm25_retriever