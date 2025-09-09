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
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.storage.docstore import SimpleDocumentStore
from qdrant_client import QdrantClient, AsyncQdrantClient
import kuzu
import os

from config import LLMProvider, VectorDBType, GraphDBType, SearchDBType

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
            
            # Determine if structured schema should be used based on configuration
            has_schema = schema_config is not None and schema_config.get("validation_schema") is not None
            use_structured_schema = has_schema
            
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
                # SchemaLLMPathExtractor - Kuzu requires unstructured schema even with SchemaLLMPathExtractor
                # The schema entities/relations will still be used by the extractor for guidance
                use_structured_schema = False  # Always False for Kuzu to avoid "Table Entity does not exist" error
                relationship_schema = None     # Don't pass relationship_schema to avoid validation conflicts
                
                # ORIGINAL CODE (commented out to fix Kuzu "Table Entity does not exist" error):
                # if schema_config and schema_config.get('validation_schema'):
                #     use_structured_schema = True
                #     relationship_schema = process_validation_schema(schema_config['validation_schema'])
                #     logger.info(f"Using SchemaLLMPathExtractor with user-configured schema: {len(relationship_schema) if relationship_schema else 0} relationships")
                # else:
                #     # Fallback to SAMPLE_SCHEMA for SchemaLLMPathExtractor
                #     logger.info("No user schema - using SAMPLE_SCHEMA for SchemaLLMPathExtractor")
                #     from config import SAMPLE_SCHEMA
                #     use_structured_schema = True
                #     relationship_schema = process_validation_schema(SAMPLE_SCHEMA.get("validation_schema"))
                #     logger.info(f"Using SAMPLE_SCHEMA with {len(relationship_schema) if relationship_schema else 0} relationship rules")
                
                if schema_config and schema_config.get('validation_schema'):
                    logger.info(f"Using SchemaLLMPathExtractor with user-configured schema (unstructured mode for Kuzu)")
                else:
                    # Fallback to SAMPLE_SCHEMA for SchemaLLMPathExtractor
                    logger.info("Using SchemaLLMPathExtractor with SAMPLE_SCHEMA (unstructured mode for Kuzu)")
                    from config import SAMPLE_SCHEMA
            
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
            
            # Get vector index configuration (default True for better text2cypher and GraphRAG performance)
            use_kuzu_vector_index = getattr(app_config, 'kuzu_use_vector_index', True)
            logger.info(f"Kuzu vector index enabled: {use_kuzu_vector_index}")
            
            # Log final configuration
            logger.info(f"Final Kuzu configuration: use_structured_schema={use_structured_schema}, relationship_schema_count={len(relationship_schema) if relationship_schema else 0}")
            
            # Create KuzuPropertyGraphStore with unified configuration
            graph_store = KuzuPropertyGraphStore(
                kuzu_db,
                has_structured_schema=use_structured_schema,
                use_vector_index=use_kuzu_vector_index,
                embed_model=embed_model,
                relationship_schema=relationship_schema if use_structured_schema else None
            )
            
            # Schema will be initialized right before PropertyGraphIndex creation for better timing
            
            return graph_store
        
        elif db_type == GraphDBType.FALKORDB:
            url = config.get("url", "falkor://localhost:6379")
            logger.info(f"Creating FalkorDB graph store - URL: {url}")
            
            return FalkorDBPropertyGraphStore(
                url=url,
                username=config.get("username"),
                password=config.get("password")
            )
        
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