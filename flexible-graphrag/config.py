from enum import Enum
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Optional, Dict, Any, Literal
import os
import json

class DataSourceType(str, Enum):
    FILESYSTEM = "filesystem"
    CMIS = "cmis"
    ALFRESCO = "alfresco"
    UPLOAD = "upload"
    WEB = "web"
    WIKIPEDIA = "wikipedia"
    YOUTUBE = "youtube"
    S3 = "s3"
    GCS = "gcs"
    AZURE_BLOB = "azure_blob"
    ONEDRIVE = "onedrive"
    SHAREPOINT = "sharepoint"
    BOX = "box"
    GOOGLE_DRIVE = "google_drive"

class VectorDBType(str, Enum):
    NONE = "none"  # Disable vector search
    QDRANT = "qdrant"
    NEO4J = "neo4j"
    ELASTICSEARCH = "elasticsearch"
    OPENSEARCH = "opensearch"
    CHROMA = "chroma"
    MILVUS = "milvus"
    WEAVIATE = "weaviate"
    PINECONE = "pinecone"
    POSTGRES = "postgres"
    LANCEDB = "lancedb"

class GraphDBType(str, Enum):
    NONE = "none"  # Disable graph search
    NEO4J = "neo4j"
    KUZU = "kuzu"
    FALKORDB = "falkordb"
    ARCADEDB = "arcadedb"
    MEMGRAPH = "memgraph"
    NEBULA = "nebula"
    NEPTUNE = "neptune"
    NEPTUNE_ANALYTICS = "neptune_analytics"

class SearchDBType(str, Enum):
    NONE = "none"  # Disable fulltext search
    BM25 = "bm25"  # Built-in BM25 from LlamaIndex (default)
    ELASTICSEARCH = "elasticsearch"
    OPENSEARCH = "opensearch"

class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    GEMINI = "gemini"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    VERTEX_AI = "vertex_ai"
    BEDROCK = "bedrock"
    GROQ = "groq"
    FIREWORKS = "fireworks"

class DocumentParser(str, Enum):
    DOCLING = "docling"
    LLAMAPARSE = "llamaparse"

class ObservabilityBackend(str, Enum):
    """Observability backend mode for telemetry producers"""
    OPENINFERENCE = "openinference"  # Default, trace-focused, requires spanmetrics for token metrics
    OPENLIT = "openlit"              # Token metrics + cost tracking built-in
    BOTH = "both"                    # DUAL mode (recommended!) - Best of both worlds

class Settings(BaseSettings):
    # Data source configuration
    data_source: DataSourceType = DataSourceType.FILESYSTEM
    source_paths: Optional[List[str]] = Field(None, description="Files or folders; CMIS/Alfresco config in env")
    
    # Document parser configuration
    document_parser: DocumentParser = DocumentParser.DOCLING
    llamaparse_api_key: Optional[str] = Field(None, description="LlamaParse API key (from env LLAMAPARSE_API_KEY if not set)")
    
    # Sample text configuration
    sample_text: str = Field(
        default="""The son of Duke Leto Atreides and the Lady Jessica, Paul is the heir of House Atreides,
an aristocratic family that rules the planet Caladan, the rainy planet, since 10191.""",
        description="Default sample text for testing"
    )
    
    @field_validator('source_paths', mode='before')
    @classmethod
    def parse_source_paths(cls, v):
        if isinstance(v, str):
            try:
                # Try to parse as JSON
                return json.loads(v)
            except json.JSONDecodeError:
                # If JSON parsing fails, treat as single path
                return [v]
        return v
    
    # Database configurations
    vector_db: VectorDBType = VectorDBType.NEO4J
    graph_db: GraphDBType = GraphDBType.NEO4J
    search_db: SearchDBType = SearchDBType.BM25  # Built-in BM25 from LlamaIndex (default)
    
    # LLM configuration
    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_config: Dict[str, Any] = {}
    
    # Embedding configuration (independent of LLM provider)
    embedding_kind: Optional[str] = Field(None, description="Embedding provider: openai, ollama, google, azure")
    embedding_model: Optional[str] = Field(None, description="Embedding model name")
    embedding_dimension: Optional[int] = Field(None, description="Embedding dimension (for configurable models)")
    
    # Schema system
    schema_name: str = Field("default", description="Name of schema to use: 'none', 'default', or custom name")
    schemas: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Array of named schemas")
    
    @field_validator('schemas', mode='before')
    @classmethod
    def parse_schemas(cls, v):
        if isinstance(v, str):
            try:
                # Try to parse as JSON
                parsed = json.loads(v)
                return parsed
            except json.JSONDecodeError as e:
                # If JSON parsing fails, log the error and return empty list
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to parse SCHEMAS JSON: {e}. Value was: {v[:100]}...")
                return []
        elif v is None:
            return []
        return v
    
    # Knowledge graph extraction control
    enable_knowledge_graph: bool = Field(True, description="Enable knowledge graph extraction for graph functionality")
    kg_extractor_type: str = Field("schema", description="Type of KG extractor: 'simple', 'schema', or 'dynamic'")
    
    # Observability configuration
    enable_observability: bool = Field(False, description="Enable OpenTelemetry observability (traces/metrics)")
    observability_backend: ObservabilityBackend = Field(
        ObservabilityBackend.BOTH,
        description="Observability backend: openinference (traces), openlit (metrics+costs), or both (recommended)"
    )
    otel_exporter_otlp_endpoint: str = Field("http://localhost:4318", description="OTLP exporter endpoint for traces and metrics")
    otel_service_name: str = Field("flexible-graphrag", description="Service name for observability traces")
    otel_service_version: str = Field("1.0.0", description="Service version for observability")
    otel_service_namespace: str = Field("llm-apps", description="Service namespace for observability")
    enable_llama_index_instrumentation: bool = Field(True, description="Enable automatic LlamaIndex instrumentation")
    
    
    # Database connection parameters
    vector_db_config: Dict[str, Any] = {}
    graph_db_config: Dict[str, Any] = {}
    search_db_config: Dict[str, Any] = {}
    
    # BM25 specific configuration
    bm25_persist_dir: Optional[str] = Field(None, description="Directory to persist BM25 index")
    bm25_similarity_top_k: int = Field(10, description="Number of top results for BM25 search")
    
    # Persistence configuration
    vector_persist_dir: Optional[str] = Field(None, description="Directory to persist vector index")
    graph_persist_dir: Optional[str] = Field(None, description="Directory to persist graph index")
    
    # Processing parameters
    chunk_size: int = 1024
    chunk_overlap: int = 128
    max_triplets_per_chunk: int = 100
    max_paths_per_chunk: int = 100
    
    # Document processing timeouts (in seconds) - DIFFERENT from LLM timeouts
    docling_timeout: int = Field(300, description="Timeout for single document Docling conversion in seconds (default: 5 minutes) - separate from LLM request timeouts")
    docling_cancel_check_interval: float = Field(0.5, description="How often to check for cancellation during Docling processing in seconds - enables mid-file cancellation")
    
    # Knowledge graph extraction timeouts and progress
    kg_extraction_timeout: int = Field(3600, description="Timeout for knowledge graph extraction per document in seconds (default: 1 hour for large documents)")
    kg_progress_reporting: bool = Field(True, description="Enable detailed progress reporting during knowledge graph extraction")
    kg_batch_size: int = Field(20, description="Number of chunks to process in each batch during KG extraction - increased for better Ollama parallel processing")
    kg_cancel_check_interval: float = Field(2.0, description="How often to check for cancellation during KG extraction in seconds")
    
    
    # Environment-based defaults
    def __init__(self, **data):
        super().__init__(**data)
        
        # Set LlamaParse API key from environment if not provided
        if not self.llamaparse_api_key:
            self.llamaparse_api_key = os.getenv("LLAMAPARSE_API_KEY")
        
        # Set default LLM config based on provider if not provided
        if not self.llm_config:
            if self.llm_provider == LLMProvider.OPENAI:
                self.llm_config = {
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
                    "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.1")),
                    "max_tokens": 4000,
                    "timeout": float(os.getenv("OPENAI_TIMEOUT", "120.0"))
                }
            elif self.llm_provider == LLMProvider.OLLAMA:
                self.llm_config = {
                    "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
                    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                    "embedding_model": os.getenv("EMBEDDING_MODEL", "all-minilm"),
                    "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("OLLAMA_TIMEOUT", "300.0"))  # Higher default for local processing
                }
            elif self.llm_provider == LLMProvider.AZURE_OPENAI:
                self.llm_config = {
                    "engine": os.getenv("AZURE_OPENAI_ENGINE"),
                    "model": os.getenv("AZURE_OPENAI_MODEL", "gpt-4"),
                    "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                    "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                    "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                    "temperature": float(os.getenv("AZURE_OPENAI_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("AZURE_OPENAI_TIMEOUT", "120.0"))
                }
            elif self.llm_provider == LLMProvider.ANTHROPIC:
                self.llm_config = {
                    "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
                    "api_key": os.getenv("ANTHROPIC_API_KEY"),
                    "temperature": float(os.getenv("ANTHROPIC_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("ANTHROPIC_TIMEOUT", "120.0"))
                }
            elif self.llm_provider == LLMProvider.GEMINI:
                self.llm_config = {
                    "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    "api_key": os.getenv("GEMINI_API_KEY"),
                    "temperature": float(os.getenv("GEMINI_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("GEMINI_TIMEOUT", "120.0"))
                }
            elif self.llm_provider == LLMProvider.VERTEX_AI:
                self.llm_config = {
                    "model": os.getenv("VERTEX_AI_MODEL", "gemini-2.0-flash-001"),
                    "project": os.getenv("VERTEX_AI_PROJECT"),
                    "location": os.getenv("VERTEX_AI_LOCATION", "us-central1"),
                    "credentials_path": os.getenv("VERTEX_AI_CREDENTIALS_PATH"),
                    "use_google_genai": os.getenv("VERTEX_AI_USE_GOOGLE_GENAI", "false").lower() == "true",
                    "api_key": os.getenv("VERTEX_AI_API_KEY"),  # Optional, for google-genai approach
                    "temperature": float(os.getenv("VERTEX_AI_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("VERTEX_AI_TIMEOUT", "120.0"))
                }
            elif self.llm_provider == LLMProvider.BEDROCK:
                self.llm_config = {
                    "model": os.getenv("BEDROCK_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
                    "region_name": os.getenv("BEDROCK_REGION", "us-east-1"),
                    "aws_access_key_id": os.getenv("BEDROCK_ACCESS_KEY"),
                    "aws_secret_access_key": os.getenv("BEDROCK_SECRET_KEY"),
                    "aws_session_token": os.getenv("BEDROCK_SESSION_TOKEN"),
                    "profile_name": os.getenv("BEDROCK_PROFILE_NAME"),
                    "temperature": float(os.getenv("BEDROCK_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("BEDROCK_TIMEOUT", "120.0")),
                    "context_size": int(os.getenv("BEDROCK_CONTEXT_SIZE", "0")) if os.getenv("BEDROCK_CONTEXT_SIZE") else None
                }
            elif self.llm_provider == LLMProvider.GROQ:
                self.llm_config = {
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "api_key": os.getenv("GROQ_API_KEY"),
                    "temperature": float(os.getenv("GROQ_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("GROQ_TIMEOUT", "120.0"))
                }
            elif self.llm_provider == LLMProvider.FIREWORKS:
                self.llm_config = {
                    "model": os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
                    "api_key": os.getenv("FIREWORKS_API_KEY"),
                    "temperature": float(os.getenv("FIREWORKS_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("FIREWORKS_TIMEOUT", "120.0"))
                }
        
        # Set default database configs if not provided
        if not self.vector_db_config:
            if self.vector_db == VectorDBType.NEO4J:
                self.vector_db_config = {
                    "username": os.getenv("NEO4J_USER", "neo4j"),
                    "password": os.getenv("NEO4J_PASSWORD", "password"),
                    "url": os.getenv("NEO4J_URI", "bolt://localhost:7687"),  # Standard Neo4j port
                    "database": os.getenv("NEO4J_DATABASE", "neo4j"),
                    "index_name": os.getenv("NEO4J_VECTOR_INDEX", "hybrid_search_vector")
                }
            elif self.vector_db == VectorDBType.QDRANT:
                self.vector_db_config = {
                    "host": os.getenv("QDRANT_HOST", "localhost"),
                    "port": int(os.getenv("QDRANT_PORT", "6333")),
                    "api_key": os.getenv("QDRANT_API_KEY"),
                    "collection_name": os.getenv("QDRANT_COLLECTION", "hybrid_search"),
                    "https": os.getenv("QDRANT_HTTPS", "false").lower() == "true"
                }
            elif self.vector_db == VectorDBType.OPENSEARCH:
                self.vector_db_config = {
                    "url": os.getenv("OPENSEARCH_URL", "http://localhost:9201"),
                    "index_name": os.getenv("OPENSEARCH_INDEX", "hybrid_search_vector"),
                    "username": os.getenv("OPENSEARCH_USERNAME"),
                    "password": os.getenv("OPENSEARCH_PASSWORD"),
                    "embedding_field": "embedding",
                    "text_field": "content",
                    "search_pipeline": "hybrid-search-pipeline"
                }
            elif self.vector_db == VectorDBType.CHROMA:
                self.vector_db_config = {
                    "persist_directory": os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"),
                    "collection_name": os.getenv("CHROMA_COLLECTION", "hybrid_search")
                }
            elif self.vector_db == VectorDBType.MILVUS:
                self.vector_db_config = {
                    "host": os.getenv("MILVUS_HOST", "localhost"),
                    "port": int(os.getenv("MILVUS_PORT", "19530")),
                    "collection_name": os.getenv("MILVUS_COLLECTION", "hybrid_search"),
                    "username": os.getenv("MILVUS_USERNAME"),
                    "password": os.getenv("MILVUS_PASSWORD"),
                    "use_secure": os.getenv("MILVUS_USE_SECURE", "false").lower() == "true"
                }
            elif self.vector_db == VectorDBType.WEAVIATE:
                self.vector_db_config = {
                    "url": os.getenv("WEAVIATE_URL", "http://localhost:8081"),
                    "index_name": os.getenv("WEAVIATE_INDEX_NAME", "HybridSearch"),  # Must start with capital letter
                    "api_key": os.getenv("WEAVIATE_API_KEY"),
                    "text_key": os.getenv("WEAVIATE_TEXT_KEY", "content")
                }
            elif self.vector_db == VectorDBType.PINECONE:
                self.vector_db_config = {
                    "api_key": os.getenv("PINECONE_API_KEY"),
                    "environment": os.getenv("PINECONE_ENVIRONMENT"),
                    "index_name": os.getenv("PINECONE_INDEX", "hybrid-search"),
                    "namespace": os.getenv("PINECONE_NAMESPACE"),
                    "metric": os.getenv("PINECONE_METRIC", "cosine")
                }
            elif self.vector_db == VectorDBType.POSTGRES:
                self.vector_db_config = {
                    "host": os.getenv("POSTGRES_HOST", "localhost"),
                    "port": int(os.getenv("POSTGRES_PORT", "5433")),
                    "database": os.getenv("POSTGRES_DATABASE", "postgres"),
                    "username": os.getenv("POSTGRES_USERNAME", "postgres"),
                    "password": os.getenv("POSTGRES_PASSWORD"),
                    "table_name": os.getenv("POSTGRES_TABLE", "hybrid_search_vectors"),
                    "connection_string": os.getenv("POSTGRES_CONNECTION_STRING")
                }
            elif self.vector_db == VectorDBType.LANCEDB:
                self.vector_db_config = {
                    "uri": os.getenv("LANCEDB_URI", "./lancedb"),
                    "table_name": os.getenv("LANCEDB_TABLE", "hybrid_search"),
                    "vector_column_name": os.getenv("LANCEDB_VECTOR_COLUMN", "vector"),
                    "text_column_name": os.getenv("LANCEDB_TEXT_COLUMN", "text")
                }
        
        if not self.graph_db_config:
            if self.graph_db == GraphDBType.NEO4J:
                self.graph_db_config = {
                    "username": os.getenv("NEO4J_USER", "neo4j"),
                    "password": os.getenv("NEO4J_PASSWORD", "password"),
                    "url": os.getenv("NEO4J_URI", "bolt://localhost:7689"),  # Updated default port
                    "database": os.getenv("NEO4J_DATABASE", "neo4j")
                }
            elif self.graph_db == GraphDBType.KUZU:
                self.graph_db_config = {
                    "db_path": os.getenv("KUZU_DB_PATH", "./kuzu_db")
                }
            elif self.graph_db == GraphDBType.FALKORDB:
                self.graph_db_config = {
                    "url": os.getenv("FALKORDB_URL", "falkor://localhost:6379"),
                    "username": os.getenv("FALKORDB_USERNAME"),
                    "password": os.getenv("FALKORDB_PASSWORD")
                }
            elif self.graph_db == GraphDBType.ARCADEDB:
                self.graph_db_config = {
                    "host": os.getenv("ARCADEDB_HOST", "localhost"),
                    "port": int(os.getenv("ARCADEDB_PORT", "2480")),
                    "username": os.getenv("ARCADEDB_USERNAME", "root"),
                    "password": os.getenv("ARCADEDB_PASSWORD", "playwithdata"),
                    "database": os.getenv("ARCADEDB_DATABASE", "flexible_graphrag"),
                    "include_basic_schema": os.getenv("ARCADEDB_INCLUDE_BASIC_SCHEMA", "true").lower() == "true"
                }
            elif self.graph_db == GraphDBType.MEMGRAPH:
                self.graph_db_config = {
                    "username": os.getenv("MEMGRAPH_USERNAME", ""),
                    "password": os.getenv("MEMGRAPH_PASSWORD", ""),
                    "url": os.getenv("MEMGRAPH_URL", "bolt://localhost:7688")
                }
            elif self.graph_db == GraphDBType.NEBULA:
                self.graph_db_config = {
                    "space": os.getenv("NEBULA_SPACE", "flexible_graphrag"),
                    "overwrite": os.getenv("NEBULA_OVERWRITE", "true").lower() == "true",
                    "address": os.getenv("NEBULA_ADDRESS", "localhost"),
                    "port": int(os.getenv("NEBULA_PORT", "9669")),
                    "username": os.getenv("NEBULA_USERNAME", "root"),
                    "password": os.getenv("NEBULA_PASSWORD", "nebula")
                }
            elif self.graph_db == GraphDBType.NEPTUNE:
                self.graph_db_config = {
                    "host": os.getenv("NEPTUNE_HOST"),
                    "port": int(os.getenv("NEPTUNE_PORT", "8182"))
                }
            elif self.graph_db == GraphDBType.NEPTUNE_ANALYTICS:
                self.graph_db_config = {
                    "graph_identifier": os.getenv("NEPTUNE_ANALYTICS_GRAPH_ID")
                }
        
        if not self.search_db_config:
            if self.search_db == SearchDBType.OPENSEARCH:
                self.search_db_config = {
                    "url": os.getenv("OPENSEARCH_URL", "http://localhost:9201"),
                    "index_name": os.getenv("OPENSEARCH_INDEX", "hybrid_search_fulltext"),
                    "username": os.getenv("OPENSEARCH_USERNAME"),
                    "password": os.getenv("OPENSEARCH_PASSWORD"),
                    "embedding_field": "embedding",
                    "text_field": "content"
                }
            elif self.search_db == SearchDBType.ELASTICSEARCH:
                self.search_db_config = {
                    "url": os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
                    "index_name": os.getenv("ELASTICSEARCH_INDEX", "hybrid_search_fulltext"),
                    "username": os.getenv("ELASTICSEARCH_USERNAME"),
                    "password": os.getenv("ELASTICSEARCH_PASSWORD")
                }
    
    def get_active_schema(self) -> Optional[Dict[str, Any]]:
        """Get the currently active schema based on schema_name"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Getting active schema for schema_name: '{self.schema_name}'")
        schemas_list = self.schemas or []
        logger.info(f"Available schemas: {len(schemas_list)} schemas loaded")
        for i, schema_def in enumerate(schemas_list):
            logger.info(f"  Schema {i}: name='{schema_def.get('name')}', has_schema={bool(schema_def.get('schema'))}")
        
        if self.schema_name == "none":
            logger.info("Schema name is 'none' - returning None")
            return None
        elif self.schema_name == "default":
            logger.info("Schema name is 'default' - returning SAMPLE_SCHEMA")
            return SAMPLE_SCHEMA
        else:
            # Look for named schema in schemas array
            for schema_def in schemas_list:
                if schema_def.get("name") == self.schema_name:
                    schema_data = schema_def.get("schema", {})
                    logger.info(f"Found schema '{self.schema_name}' with {len(schema_data)} keys")
                    return schema_data
            
            # If named schema not found, log warning and return None
            logger.warning(f"Schema '{self.schema_name}' not found in schemas array. Available schemas: {[s.get('name') for s in schemas_list]}")
            return None

    @property
    def schema_config(self) -> Optional[Dict[str, Any]]:
        """Alias for get_active_schema() for backward compatibility"""
        return self.get_active_schema()

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "use_enum_values": True,
        "extra": "allow"
    }

# Sample schema configuration - comprehensive schema with permissive validation for maximum flexibility
SAMPLE_SCHEMA = {
    "entities": Literal["PERSON", "ORGANIZATION", "LOCATION", "PLACE", "TECHNOLOGY", "PROJECT"],
    "relations": Literal["WORKS_FOR", "LOCATED_IN", "USES", "COLLABORATES_WITH", "DEVELOPS", "HAS", "PART_OF", "WORKED_ON", "WORKED_WITH", "WORKED_AT"],
    "validation_schema": [
        # Person relationships
        ("PERSON", "WORKS_FOR", "ORGANIZATION"),
        ("PERSON", "WORKED_AT", "ORGANIZATION"),
        ("PERSON", "WORKED_WITH", "PERSON"),
        ("PERSON", "WORKED_ON", "PROJECT"),
        ("PERSON", "WORKED_ON", "TECHNOLOGY"),
        ("PERSON", "COLLABORATES_WITH", "PERSON"),
        ("PERSON", "PART_OF", "ORGANIZATION"),
        ("PERSON", "LOCATED_IN", "LOCATION"),
        ("PERSON", "LOCATED_IN", "PLACE"),
        ("PERSON", "HAS", "TECHNOLOGY"),
        ("PERSON", "USES", "TECHNOLOGY"),
        ("PERSON", "DEVELOPS", "PROJECT"),
        ("PERSON", "DEVELOPS", "TECHNOLOGY"),
        # Organization relationships
        ("ORGANIZATION", "COLLABORATES_WITH", "ORGANIZATION"),
        ("ORGANIZATION", "WORKED_WITH", "ORGANIZATION"),
        ("ORGANIZATION", "WORKED_ON", "PROJECT"),
        ("ORGANIZATION", "WORKED_ON", "TECHNOLOGY"),
        ("ORGANIZATION", "DEVELOPS", "PROJECT"),
        ("ORGANIZATION", "DEVELOPS", "TECHNOLOGY"),
        ("ORGANIZATION", "USES", "TECHNOLOGY"),
        ("ORGANIZATION", "HAS", "PERSON"),
        ("ORGANIZATION", "HAS", "TECHNOLOGY"),
        ("ORGANIZATION", "HAS", "PROJECT"),
        ("ORGANIZATION", "PART_OF", "ORGANIZATION"),
        ("ORGANIZATION", "LOCATED_IN", "LOCATION"),
        ("ORGANIZATION", "LOCATED_IN", "PLACE"),
        # Technology relationships
        ("TECHNOLOGY", "USES", "TECHNOLOGY"),
        ("TECHNOLOGY", "PART_OF", "TECHNOLOGY"),
        ("TECHNOLOGY", "PART_OF", "PROJECT"),
        # Project relationships
        ("PROJECT", "USES", "TECHNOLOGY"),
        ("PROJECT", "HAS", "TECHNOLOGY"),
        ("PROJECT", "PART_OF", "ORGANIZATION"),
        # Location relationships
        ("LOCATION", "HAS", "ORGANIZATION"),
        ("LOCATION", "HAS", "PERSON"),
        ("PLACE", "HAS", "ORGANIZATION"),
        ("PLACE", "HAS", "PERSON")
    ],
    "strict": False,
    "max_triplets_per_chunk": 100
}

# LlamaIndex Kuzu documentation schema (too restrictive - commented out)
# SAMPLE_SCHEMA = {
#     "entities": Literal["PERSON", "PLACE", "ORGANIZATION"],
#     "relations": Literal["HAS", "PART_OF", "WORKED_ON", "WORKED_WITH", "WORKED_AT"],
#     "validation_schema": [
#         ("ORGANIZATION", "HAS", "PERSON"),
#         ("PERSON", "WORKED_AT", "ORGANIZATION"),
#         ("PERSON", "WORKED_WITH", "PERSON"),
#         ("PERSON", "PART_OF", "ORGANIZATION"),
#         ("ORGANIZATION", "WORKED_ON", "ORGANIZATION"),
#         ("PERSON", "WORKED_ON", "ORGANIZATION")
#     ],
#     "strict": True
# }

# Previous schema with noisy DOCUMENT MENTIONS (commented out for reference)
# SAMPLE_SCHEMA = {
#     "entities": Literal["PERSON", "ORGANIZATION", "LOCATION", "TECHNOLOGY", "PROJECT", "DOCUMENT"],
#     "relations": Literal["WORKS_FOR", "LOCATED_IN", "USES", "COLLABORATES_WITH", "DEVELOPS", "MENTIONS"],
#     "validation_schema": [
#         ("PERSON", "WORKS_FOR", "ORGANIZATION"),
#         ("PERSON", "LOCATED_IN", "LOCATION"),
#         ("ORGANIZATION", "USES", "TECHNOLOGY"),
#         ("PERSON", "COLLABORATES_WITH", "PERSON"),
#         ("ORGANIZATION", "DEVELOPS", "PROJECT"),
#         ("DOCUMENT", "MENTIONS", "PERSON"),
#         ("DOCUMENT", "MENTIONS", "ORGANIZATION"),
#         ("DOCUMENT", "MENTIONS", "TECHNOLOGY")
#     ],
#     "strict": False,
#     "max_triplets_per_chunk": 15
# }

# Note: KUZU_SCHEMA removed - system now always uses user's configured schema
# Both Neo4j and Kuzu will use the same schema configuration (SAMPLE_SCHEMA by default)