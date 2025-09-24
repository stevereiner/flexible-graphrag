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

class GraphDBType(str, Enum):
    NONE = "none"  # Disable graph search
    NEO4J = "neo4j"
    KUZU = "kuzu"
    FALKORDB = "falkordb"

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

class Settings(BaseSettings):
    # Data source configuration
    data_source: DataSourceType = DataSourceType.FILESYSTEM
    source_paths: Optional[List[str]] = Field(None, description="Files or folders; CMIS/Alfresco config in env")
    
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
    
    # Kuzu-specific configuration
    kuzu_use_vector_index: bool = Field(False, description="Enable Kuzu's built-in vector index (disabled by default)")
    
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
                    "model": os.getenv("GEMINI_MODEL", "models/gemini-1.5-flash"),
                    "api_key": os.getenv("GEMINI_API_KEY"),
                    "temperature": float(os.getenv("GEMINI_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("GEMINI_TIMEOUT", "120.0"))
                }
        
        # Set default database configs if not provided
        if not self.vector_db_config:
            if self.vector_db == VectorDBType.NEO4J:
                self.vector_db_config = {
                    "username": os.getenv("NEO4J_USER", "neo4j"),
                    "password": os.getenv("NEO4J_PASSWORD", "password"),
                    "url": os.getenv("NEO4J_URI", "bolt://localhost:7687"),  # Standard Neo4j port
                    "database": os.getenv("NEO4J_DATABASE", "neo4j"),
                    "index_name": os.getenv("NEO4J_VECTOR_INDEX", "hybrid_search_vector"),
                    "embed_dim": 1536 if self.llm_provider == LLMProvider.OPENAI else 1024
                }
            elif self.vector_db == VectorDBType.QDRANT:
                self.vector_db_config = {
                    "host": os.getenv("QDRANT_HOST", "localhost"),
                    "port": int(os.getenv("QDRANT_PORT", "6333")),
                    "api_key": os.getenv("QDRANT_API_KEY"),
                    "collection_name": os.getenv("QDRANT_COLLECTION", "hybrid_search"),
                    "https": os.getenv("QDRANT_HTTPS", "false").lower() == "true",
                    "embed_dim": 1536 if self.llm_provider == LLMProvider.OPENAI else 1024  # Ollama compatibility
                }
            elif self.vector_db == VectorDBType.OPENSEARCH:
                self.vector_db_config = {
                    "url": os.getenv("OPENSEARCH_URL", "http://localhost:9201"),
                    "index_name": os.getenv("OPENSEARCH_INDEX", "hybrid_search_vector"),
                    "username": os.getenv("OPENSEARCH_USERNAME"),
                    "password": os.getenv("OPENSEARCH_PASSWORD"),
                    "embed_dim": 1536 if self.llm_provider == LLMProvider.OPENAI else 1024,  # Ollama compatibility
                    "embedding_field": "embedding",
                    "text_field": "content",
                    "search_pipeline": "hybrid-search-pipeline"
                }
        
        if not self.graph_db_config:
            if self.graph_db == GraphDBType.NEO4J:
                self.graph_db_config = {
                    "username": os.getenv("NEO4J_USER", "neo4j"),
                    "password": os.getenv("NEO4J_PASSWORD", "password"),
                    "url": os.getenv("NEO4J_URI", "bolt://localhost:7689"),  # Updated default port
                    "database": os.getenv("NEO4J_DATABASE", "neo4j")
                }
        
        if not self.search_db_config:
            if self.search_db == SearchDBType.OPENSEARCH:
                self.search_db_config = {
                    "url": os.getenv("OPENSEARCH_URL", "http://localhost:9201"),
                    "index_name": os.getenv("OPENSEARCH_INDEX", "hybrid_search_fulltext"),
                    "username": os.getenv("OPENSEARCH_USERNAME"),
                    "password": os.getenv("OPENSEARCH_PASSWORD"),
                    "embed_dim": 1536 if self.llm_provider == LLMProvider.OPENAI else 1024,  # Ollama compatibility
                    "embedding_field": "embedding",
                    "text_field": "content"
                }
            elif self.search_db == SearchDBType.ELASTICSEARCH:
                self.search_db_config = {
                    "url": os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
                    "index_name": os.getenv("ELASTICSEARCH_INDEX", "hybrid_search_fulltext"),
                    "username": os.getenv("ELASTICSEARCH_USERNAME"),
                    "password": os.getenv("ELASTICSEARCH_PASSWORD"),
                    "embed_dim": 1536 if self.llm_provider == LLMProvider.OPENAI else 1024  # Ollama compatibility
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