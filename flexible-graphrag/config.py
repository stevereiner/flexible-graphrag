from enum import Enum
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Optional, Dict, Any, Literal, Annotated
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

class PropertyGraphType(str, Enum):
    NONE = "none"  # Disable graph search
    NEO4J = "neo4j"
    LADYBUG = "ladybug"
    FALKORDB = "falkordb"
    ARCADEDB = "arcadedb"
    MEMGRAPH = "memgraph"
    NEBULA = "nebula"
    NEPTUNE = "neptune"
    NEPTUNE_ANALYTICS = "neptune_analytics"
    # LangChain-only property graph backends (no LlamaIndex store equivalent)
    ARANGODB = "arangodb"
    APACHE_AGE = "apache_age"
    COSMOS_GREMLIN = "cosmos_gremlin"
    SPANNER = "spanner"
    HUGEGRAPH = "hugegraph"
    TIGERGRAPH = "tigergraph"
    SURREALDB = "surrealdb"

# Backward-compat alias
GraphDBType = PropertyGraphType

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
    OPENAI_LIKE = "openai_like"   # Any OpenAI-compatible API (LM Studio, LocalAI, Llamafile, etc.)
    VLLM = "vllm"                 # vLLM server (high-performance local inference)
    LITELLM = "litellm"           # LiteLLM proxy (100+ providers via unified OpenAI-compatible API)
    OPENROUTER = "openrouter"     # OpenRouter (unified API for 200+ models)

class DocumentParser(str, Enum):
    DOCLING = "docling"
    LLAMAPARSE = "llamaparse"

class ObservabilityBackend(str, Enum):
    """Observability backend mode for telemetry producers"""
    OPENINFERENCE = "openinference"  # Default, trace-focused, requires spanmetrics for token metrics
    OPENLIT = "openlit"              # Token metrics + cost tracking built-in
    BOTH = "both"                    # DUAL mode (recommended!) - Best of both worlds

class RDFStoreType(str, Enum):
    """RDF store backend types (legacy — use RdfGraphType for new code)"""
    FUSEKI = "fuseki"
    GRAPHDB = "graphdb"
    ONTOTEXT = "ontotext"
    OXIGRAPH = "oxigraph"
    CUSTOM_SPARQL = "custom_sparql"

class RdfGraphType(str, Enum):
    """Selects exactly one RDF triple store for both ingestion and retrieval (or none)."""
    NONE = "none"
    FUSEKI = "fuseki"
    OXIGRAPH = "oxigraph"
    GRAPHDB = "graphdb"
    NEPTUNE_RDF = "neptune_rdf"

class OntologyFormat(str, Enum):
    """RDF ontology serialization formats"""
    TURTLE = "turtle"
    RDFXML = "rdfxml"
    NTRIPLES = "ntriples"
    NQUADS = "nquads"
    JSONLD = "jsonld"

class QueryRoutingMode(str, Enum):
    """Query routing strategy for hybrid systems"""
    PROPERTY_GRAPH = "property_graph"
    SPARQL = "sparql"
    HYBRID = "hybrid"
    AUTO = "auto"

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
    pg_graph_db: PropertyGraphType = PropertyGraphType.NEO4J
    search_db: SearchDBType = SearchDBType.BM25  # Built-in BM25 from LlamaIndex (default)
    
    # LLM configuration
    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_config: Dict[str, Any] = {}
    
    # Embedding configuration (independent of LLM provider)
    embedding_kind: Optional[str] = Field(None, description="Embedding provider: openai, ollama, google, azure")
    embedding_model: Optional[str] = Field(None, description="Embedding model name")
    embedding_dimension: Optional[int] = Field(None, description="Embedding dimension (for configurable models)")
    
    # Schema system
    schema_name: str = Field("default", description="Name of schema to use: 'default' (internal), 'sample' (project), or custom name")
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
    llm_extraction_mode: str = Field(
        "function",
        description=(
            "How LlamaIndex calls the LLM for structured KG extraction. "
            "'function' (default) — tool/function calling mode (most reliable for property extraction). "
            "'json_schema' — structured output / JSON schema mode (PydanticProgramMode.DEFAULT). "
            "'auto' — let LlamaIndex decide per provider (also maps to DEFAULT)."
        ),
    )
    
    # RDF Retrieval Configuration (LangChain Integration)
    # use_langchain_rdf and rdf_store_type removed — use rdf_graph_db instead
    rdf_retrieval_weight: float = Field(0.3, description="Weight for RDF retrieval results in fusion (0.0-1.0)")
    rdf_retrieval_top_k: int = Field(5, description="Number of results to return from RDF retriever")

    # ------------------------------------------------------------------
    # Backend selection — controls which framework handles each subsystem
    # ------------------------------------------------------------------
    # graph_backend:    'llamaindex' (default) | 'langchain'
    # vector_backend:   'llamaindex' (default) | 'langchain'
    # search_backend:   'llamaindex' (default) | 'langchain'
    # llm_backend:      'llamaindex' (default) | 'langchain' | 'both'
    # embedding_backend:'llamaindex' (default) | 'langchain' | 'both'
    # chunker_backend:  'llamaindex' (default) | 'langchain'
    # kg_extractor_backend: 'llamaindex' (default) | 'langchain'
    #
    # 'both' for llm_backend/embedding_backend instantiates native instances of
    # each so mixed pipelines (e.g. LI vector + LC property graph) get the right
    # model type without bridge adapters.
    graph_backend: str = Field("llamaindex", description="Property graph backend: llamaindex | langchain")
    vector_backend: str = Field("llamaindex", description="Vector store backend: llamaindex | langchain")
    search_backend: str = Field("llamaindex", description="Search store backend: llamaindex | langchain")
    llm_backend: str = Field("llamaindex", description="LLM backend: llamaindex | langchain | both")
    embedding_backend: str = Field("llamaindex", description="Embedding backend: llamaindex | langchain | both")
    chunker_backend: str = Field("llamaindex", description="Chunker backend: llamaindex | langchain")
    lc_splitter_type: str = Field(
        "recursive",
        description=(
            "LangChain splitter type (only used when CHUNKER_BACKEND=langchain). "
            "Options: recursive | character | token | markdown | python | sentence_transformers"
        ),
    )
    kg_extractor_backend: str = Field("llamaindex", description="KG extractor backend: llamaindex | langchain")

    # LangChain Property Graph Store Configuration
    # When use_langchain_pg=true the LangChain PG store is used for the graph
    # retriever slot in the fusion pipeline INSTEAD of the LlamaIndex graph_index.
    # Only one of the two is active at a time (use_langchain_pg takes precedence).
    use_langchain_pg: bool = Field(False, description="Use a LangChain property graph store instead of LlamaIndex graph_index for the graph retriever in hybrid fusion")
    langchain_pg_store_type: Optional[str] = Field(
        None,
        description=(
            "LangChain property graph store type when use_langchain_pg=true. "
            "Options: neo4j | memgraph | ladybug | falkordb | arangodb | "
            "neptune | neptune_analytics | apache_age | cosmos_gremlin | "
            "hugegraph | nebula | tigergraph | arcadedb | spanner"
        ),
    )
    langchain_pg_vector_search: Optional[bool] = Field(
        None,
        description=(
            "Run a vector-similarity search against the graph store's entity vector index "
            "and include results in fusion. Defaults to false for all stores. "
            "Set LANGCHAIN_PG_VECTOR_SEARCH=true to enable explicitly."
        ),
    )
    langchain_pg_vector_index: str = Field(
        "entity",
        description="Name of the Neo4j vector index to query when langchain_pg_vector_search=true. "
                    "Default 'entity' matches the index LlamaIndex creates on __Entity__[embedding].",
    )
    langchain_pg_intermediate_steps: bool = Field(
        False,
        description=(
            "Hybrid search returns up to three result types per active graph: "
            "(1) text chunks — always, from VECTOR_DB/SEARCH_DB; "
            "(2) AI answer   — always, the LLM answer generated from graph context; "
            "(3) graph input — optional (this flag): the raw text the LLM received "
            "as context from the Cypher/SPARQL query (result rows fed into the LLM prompt). "
            "When both PG and RDF graphs are active, types 2 and 3 each appear once per graph "
            "(up to 5 result nodes total). "
            "false = types 1+2 only (default). true = types 1+2+3."
        ),
    )
    langchain_pg_vector_node_label: str = Field(
        "__Entity__",
        description="Node label for the vector index (default: __Entity__).",
    )
    langchain_pg_vector_embedding_property: str = Field(
        "embedding",
        description="Node property storing the embedding vector (default: embedding).",
    )
    langchain_pg_vector_text_property: str = Field(
        "name",
        description="Node property to use as returned text in vector search results (default: name).",
    )

    # ------------------------------------------------------------------
    # LangChain PG neighborhood retriever (k-hop graph expansion)
    # ------------------------------------------------------------------
    use_pg_neighborhood: bool = Field(
        False,
        description=(
            "When use_langchain_pg=true, also expand from vector-similarity seed nodes "
            "up to pg_neighborhood_hops hops in the property graph and include neighbors "
            "in fusion.  Mirrors LlamaIndex VectorContextRetriever for LangChain-only stores."
        ),
    )
    pg_neighborhood_hops: int = Field(
        2,
        description="Maximum relationship hops for PG neighborhood expansion (default: 2).",
    )
    pg_neighborhood_top_k_seeds: int = Field(
        10,
        description="Number of vector similarity hits used as seeds for neighborhood expansion.",
    )

    # ------------------------------------------------------------------
    # LangChain text-to-query (Cypher / SPARQL / SurrealQL) opt-in flag
    # ------------------------------------------------------------------
    use_lc_text_to_graph: bool = Field(
        False,
        description=(
            "When graph_backend=langchain and the store has built-in vector support "
            "(neo4j, arcadedb, falkordb, ladybug, arangodb, surrealdb), the default graph "
            "retriever is GraphEntityVectorRetriever (better quality than text-to-query). "
            "Set USE_LC_TEXT_TO_GRAPH=true to additionally enable TextToGraphQueryRetriever "
            "alongside vector retrieval. "
            "For stores WITHOUT vector support (apache_age, hugegraph, nebula, tigergraph, "
            "cosmos_gremlin, neptune) and all RDF stores, TextToGraphQueryRetriever is always "
            "active regardless of this flag."
        ),
    )

    # ------------------------------------------------------------------
    # Synonym exploder (LLM-based query rewriter for hybrid retrieval)
    # ------------------------------------------------------------------
    use_synonym_exploder: bool = Field(
        False,
        description=(
            "Wrap the hybrid retriever with an LLM-based synonym/keyword expander. "
            "The LLM generates up to synonym_exploder_max_keywords related keywords "
            "which are appended to the query (^ separated, same as LLMSynonymRetriever). "
            "synonym_exploder_scope controls which retrievers see the enriched query."
        ),
    )
    synonym_exploder_max_keywords: int = Field(
        8,
        description="Maximum number of synonym keywords the LLM should generate per query.",
    )
    synonym_exploder_scope: str = Field(
        "none",
        description=(
            "Comma-separated list of retriever types that receive the synonym-enriched query. "
            "Special values: 'all' (wrap entire fusion retriever, one LLM call), 'none' (disable). "
            "Best used for KEYWORD/BM25 search backends where exact token matching means "
            "'Acme staff' and 'Acme employees' are different queries. "
            "Vector retrievers (LI and LC) use embedding similarity — the model already handles "
            "synonyms implicitly, so adding explicit expansion multiplies calls with little gain. "
            "LI PropertyGraph also does vector seeding internally — same reasoning. "
            "Per-retriever tokens: "
            "  llamaindex_search    — LlamaIndex BM25 / Elasticsearch / OpenSearch (RECOMMENDED). "
            "  langchain_search     — LangChain Elasticsearch / OpenSearch (RECOMMENDED). "
            "  llamaindex_vector    — LlamaIndex VectorStoreIndex (not recommended — embedding handles it). "
            "  langchain_vector     — LangChain vector store (not recommended — same reason). "
            "  llamaindex_pg_graph  — LlamaIndex PropertyGraph VectorContextRetriever (not recommended). "
            "  langchain_pg_vector  — LangChain PG vector retriever (langchain_pg_vector_search). "
            "  langchain_rdf_graph  — LangChain RDF/SPARQL retriever (avoid — one LLM call per synonym). "
            "  langchain_pg_graph   — LangChain Cypher QA retriever (avoid — same reason). "
            "  langchain_pg_neighborhood — PG neighborhood k-hop retriever. "
        ),
    )

    # ------------------------------------------------------------------
    # Retrieval fusion framework
    # ------------------------------------------------------------------
    retrieval_fusion: str = Field(
        "llamaindex",
        description=(
            "Fusion framework used to combine results from multiple retrievers. "
            "'llamaindex' (default) — LlamaIndex QueryFusionRetriever (relative_score mode, works with any mix of LI/LC retrievers). "
            "'langchain'           — LangChain EnsembleRetriever (RRF, only when ALL active retrievers are LC-native). "
            "Falls back to 'llamaindex' automatically when LI-native retrievers are present."
        ),
    )

    # Neptune RDF configuration for retrieval
    neptune_host: Optional[str] = Field(None, description="Amazon Neptune cluster endpoint")
    neptune_port: int = Field(8182, description="Neptune port (default: 8182)")
    neptune_region: str = Field("us-east-1", description="AWS region for Neptune")
    neptune_use_iam_auth: bool = Field(False, description="Use IAM authentication for Neptune")
    neptune_use_https: bool = Field(True, description="Use HTTPS for Neptune connection")
    
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
    max_triplets_per_chunk: int = 20
    max_paths_per_chunk: int = 20
    
    # Document processing timeouts (in seconds) - DIFFERENT from LLM timeouts
    docling_timeout: int = Field(600, description="Timeout for single document Docling conversion in seconds (default: 10 minutes) - separate from LLM request timeouts")
    docling_cancel_check_interval: float = Field(0.5, description="How often to check for cancellation during Docling processing in seconds - enables mid-file cancellation")
    docling_device: str = Field("auto", description="Device for Docling processing: 'auto' (default - GPU if available), 'cpu', 'cuda', 'mps' (Mac)")
    docling_ocr: bool = Field(False, description="Enable OCR in Docling for scanned documents/images (default: False). Requires OCR backend installed.")
    docling_ocr_engine: str = Field("auto", description=(
        "OCR engine when DOCLING_OCR=true: "
        "'auto' (docling picks best installed engine), "
        "'rapidocr' (in docling-slim[standard], no extra needed), "
        "'easyocr' (install docling-ocr-easyocr extra), "
        "'tesseract_cli' (recommended on Windows — system Tesseract only, no tesserocr wheel build), "
        "'tesserocr' (pip compiles bindings; fragile on Windows; Linux needs libtesseract-dev etc.), "
        "'ocrmac' (macOS only, install docling-ocr-ocrmac extra)"
    ))
    save_parsing_output: bool = Field(False, description="Save intermediate parsing results (markdown/text) from both Docling and LlamaParse to files for inspection")
    parser_format_for_extraction: str = Field("auto", description="Format to use for knowledge graph extraction: 'auto' (markdown if tables, else plaintext), 'markdown' (always), 'plaintext' (always)")
    
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

        # Kind-specific embedding model takes priority over generic EMBEDDING_MODEL
        # e.g. OPENAI_EMBEDDING_MODEL=text-embedding-3-small when EMBEDDING_KIND=openai
        _emb_kind = (self.embedding_kind or "").lower()
        _emb_kind_env_map = {
            "openai":      "OPENAI_EMBEDDING_MODEL",
            "ollama":      "OLLAMA_EMBEDDING_MODEL",
            "google":      "GOOGLE_EMBEDDING_MODEL",
            "vertex":      "VERTEX_EMBEDDING_MODEL",
            "azure":       "AZURE_EMBEDDING_MODEL",
            "bedrock":     "BEDROCK_EMBEDDING_MODEL",
            "fireworks":   "FIREWORKS_EMBEDDING_MODEL",
            "openai_like": "OPENAI_LIKE_EMBEDDING_MODEL",
            "litellm":     "LITELLM_EMBEDDING_MODEL",
        }
        _emb_kind_var = _emb_kind_env_map.get(_emb_kind)
        if _emb_kind_var and os.getenv(_emb_kind_var):
            self.embedding_model = os.getenv(_emb_kind_var)
        
        # Set default LLM config based on provider if not provided
        if not self.llm_config:
            if self.llm_provider == LLMProvider.OPENAI:
                self.llm_config = {
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
                    "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.1")),
                    "max_tokens": 4000,
                    "timeout": float(os.getenv("OPENAI_TIMEOUT", "120.0")),
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.OLLAMA:
                self.llm_config = {
                    "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
                    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                    "embedding_model": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
                    "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("OLLAMA_TIMEOUT", "900.0")),  # 15 minutes for graph extraction
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.AZURE_OPENAI:
                self.llm_config = {
                    "engine": os.getenv("AZURE_OPENAI_ENGINE"),
                    "model": os.getenv("AZURE_OPENAI_MODEL", "gpt-4"),
                    "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                    "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                    "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                    "temperature": float(os.getenv("AZURE_OPENAI_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("AZURE_OPENAI_TIMEOUT", "120.0")),
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.ANTHROPIC:
                self.llm_config = {
                    "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
                    "api_key": os.getenv("ANTHROPIC_API_KEY"),
                    "temperature": float(os.getenv("ANTHROPIC_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("ANTHROPIC_TIMEOUT", "120.0")),
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.GEMINI:
                self.llm_config = {
                    "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    "api_key": os.getenv("GEMINI_API_KEY"),
                    "temperature": float(os.getenv("GEMINI_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("GEMINI_TIMEOUT", "120.0")),
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
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
                    "timeout": float(os.getenv("VERTEX_AI_TIMEOUT", "120.0")),
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
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
                    "context_size": int(os.getenv("BEDROCK_CONTEXT_SIZE", "0")) if os.getenv("BEDROCK_CONTEXT_SIZE") else None,
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.GROQ:
                self.llm_config = {
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "api_key": os.getenv("GROQ_API_KEY"),
                    "temperature": float(os.getenv("GROQ_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("GROQ_TIMEOUT", "120.0")),
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.FIREWORKS:
                self.llm_config = {
                    "model": os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
                    "api_key": os.getenv("FIREWORKS_API_KEY"),
                    "temperature": float(os.getenv("FIREWORKS_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("FIREWORKS_TIMEOUT", "120.0")),
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.OPENAI_LIKE:
                # Generic OpenAI-compatible API: LM Studio, LocalAI, Llamafile, Jan, Tabby, etc.
                # is_function_calling_model defaults to True - set OPENAI_LIKE_FUNCTION_CALLING=false
                # if your server/model doesn't support tool calling
                self.llm_config = {
                    "model": os.getenv("OPENAI_LIKE_MODEL", "local-model"),
                    "api_base": os.getenv("OPENAI_LIKE_API_BASE", "http://localhost:8000/v1"),
                    "api_key": os.getenv("OPENAI_LIKE_API_KEY", "local"),
                    "temperature": float(os.getenv("OPENAI_LIKE_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("OPENAI_LIKE_TIMEOUT", "120.0")),
                    "context_window": int(os.getenv("OPENAI_LIKE_CONTEXT_WINDOW", "4096")),
                    "is_function_calling_model": os.getenv("OPENAI_LIKE_FUNCTION_CALLING", "true").lower() == "true",
                    "is_chat_model": os.getenv("OPENAI_LIKE_CHAT_MODEL", "true").lower() == "true",
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.VLLM:
                # vLLM — two modes selected via VLLM_MODE:
                #   "server" (default) — OpenAI-compatible HTTP server (Docker or standalone vllm serve)
                #                        Uses VLLM_API_BASE (full /v1 URL) → OpenAILike path
                #   "inprocess"        — in-process Python package (Linux/macOS only; pip install vllm)
                #                        Uses VLLM_API_URL (bare URL, no /v1) → Vllm class path
                _vllm_mode = os.getenv("VLLM_MODE", "server").lower()
                self.llm_config = {
                    "vllm_mode": _vllm_mode,
                    "model": os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
                    "api_base": os.getenv("VLLM_API_BASE", "http://localhost:8002/v1"),
                    "api_key": os.getenv("VLLM_API_KEY", "local"),
                    "temperature": float(os.getenv("VLLM_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("VLLM_TIMEOUT", "120.0")),
                    "context_window": int(os.getenv("VLLM_CONTEXT_WINDOW", "8192")),
                    "is_function_calling_model": os.getenv("VLLM_FUNCTION_CALLING", "false").lower() == "true",
                    "is_chat_model": os.getenv("VLLM_CHAT_MODEL", "true").lower() == "true",
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                    # in-process path only (VLLM_MODE=inprocess)
                    "api_url": os.getenv("VLLM_API_URL", "http://localhost:8002"),
                    "max_new_tokens": int(os.getenv("VLLM_MAX_NEW_TOKENS", "2048")),
                }
            elif self.llm_provider == LLMProvider.LITELLM:
                # LiteLLM proxy - unified OpenAI-compatible API for 100+ providers
                # Run: litellm --model ollama/llama3 (starts proxy on port 4000)
                self.llm_config = {
                    "model": os.getenv("LITELLM_MODEL", "gpt-4o-mini"),
                    "api_base": os.getenv("LITELLM_API_BASE", "http://localhost:4000/v1"),
                    "api_key": os.getenv("LITELLM_API_KEY", "local"),
                    "temperature": float(os.getenv("LITELLM_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("LITELLM_TIMEOUT", "120.0")),
                    "context_window": int(os.getenv("LITELLM_CONTEXT_WINDOW", "4096")),
                    "is_function_calling_model": os.getenv("LITELLM_FUNCTION_CALLING", "true").lower() == "true",
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }
            elif self.llm_provider == LLMProvider.OPENROUTER:
                # OpenRouter - unified API for 200+ models (GPT-4, Claude, Llama, Mistral, etc.)
                # Get API key from https://openrouter.ai/keys
                self.llm_config = {
                    "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
                    "api_key": os.getenv("OPENROUTER_API_KEY"),
                    "temperature": float(os.getenv("OPENROUTER_TEMPERATURE", "0.1")),
                    "timeout": float(os.getenv("OPENROUTER_TIMEOUT", "120.0")),
                    "context_window": int(os.getenv("OPENROUTER_CONTEXT_WINDOW", "128000")),
                    "max_tokens": int(os.getenv("OPENROUTER_MAX_TOKENS", "16384")),
                    "extraction_mode": os.getenv("LLM_EXTRACTION_MODE", "function"),
                }

        # Set default database configs if not provided
        # Per-store config takes precedence: {TYPE}_VECTOR_DB_CONFIG > VECTOR_DB_CONFIG > individual vars
        # (Pydantic loads VECTOR_DB_CONFIG before __init__, so we must re-check unconditionally)
        _vtype = str(getattr(self.vector_db, 'value', self.vector_db) or "").upper()
        _named_vec = _vtype and os.getenv(f"{_vtype}_VECTOR_DB_CONFIG")
        if _named_vec:
            try:
                self.vector_db_config = json.loads(_named_vec)
            except (json.JSONDecodeError, ValueError):
                pass
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
                    "text_field": "content"
                    # "search_pipeline": "hybrid-search-pipeline"  # Optional - must be created via scripts/create_opensearch_pipeline.py
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
        
        # Per-store config takes precedence: {TYPE}_GRAPH_DB_CONFIG > GRAPH_DB_CONFIG > individual vars
        _gtype = str(getattr(self.pg_graph_db, 'value', self.pg_graph_db) or "").upper()
        _named_graph = _gtype and os.getenv(f"{_gtype}_GRAPH_DB_CONFIG")
        if _named_graph:
            try:
                self.graph_db_config = json.loads(_named_graph)
            except (json.JSONDecodeError, ValueError):
                pass
        if not self.graph_db_config:
            if self.pg_graph_db == PropertyGraphType.NEO4J:
                self.graph_db_config = {
                    "username": os.getenv("NEO4J_USER", "neo4j"),
                    "password": os.getenv("NEO4J_PASSWORD", "password"),
                    "url": os.getenv("NEO4J_URI", "bolt://localhost:7687"),  # Standard Neo4j Bolt port
                    "database": os.getenv("NEO4J_DATABASE", "neo4j")
                }
            elif self.pg_graph_db == PropertyGraphType.LADYBUG:
                self.graph_db_config = {
                    "db_dir": os.getenv("LADYBUG_DB_DIR", "./ladybug"),
                    "db_file": os.getenv("LADYBUG_DB_FILE", "database.lbug"),
                    "use_vector_index": os.getenv("LADYBUG_USE_VECTOR_INDEX", "true").lower() == "true",
                    "has_structured_schema": os.getenv("LADYBUG_STRUCTURED_SCHEMA", "false").lower() == "true",
                    "strict_schema": os.getenv("LADYBUG_STRICT_SCHEMA", "false").lower() == "true",
                }
            elif self.pg_graph_db == PropertyGraphType.FALKORDB:
                self.graph_db_config = {
                    "url": os.getenv("FALKORDB_URL", "falkor://localhost:6379"),
                    "username": os.getenv("FALKORDB_USERNAME"),
                    "password": os.getenv("FALKORDB_PASSWORD"),
                    "database": os.getenv("FALKORDB_DATABASE", "falkor"),
                }
            elif self.pg_graph_db == PropertyGraphType.ARCADEDB:
                self.graph_db_config = {
                    "mode": os.getenv("ARCADEDB_MODE", "remote"),
                    "host": os.getenv("ARCADEDB_HOST", "localhost"),
                    "port": int(os.getenv("ARCADEDB_PORT", "2480")),
                    "username": os.getenv("ARCADEDB_USERNAME", "root"),
                    "password": os.getenv("ARCADEDB_PASSWORD", "playwithdata"),
                    "database": os.getenv("ARCADEDB_DATABASE", "flexible_graphrag"),
                    "include_basic_schema": os.getenv("ARCADEDB_INCLUDE_BASIC_SCHEMA", "true").lower() == "true",
                    # Embedded mode settings (used when ARCADEDB_MODE=embedded)
                    "db_path": os.getenv("ARCADEDB_DB_PATH", "./arcadedb_data"),
                    "embedded_server": os.getenv("ARCADEDB_EMBEDDED_SERVER", "false").lower() == "true",
                    "embedded_server_port": int(os.getenv("ARCADEDB_EMBEDDED_SERVER_PORT", "2482")),
                    "embedded_server_password": os.getenv("ARCADEDB_EMBEDDED_SERVER_PASSWORD"),
                }
            elif self.pg_graph_db == PropertyGraphType.MEMGRAPH:
                self.graph_db_config = {
                    "username": os.getenv("MEMGRAPH_USERNAME", ""),
                    "password": os.getenv("MEMGRAPH_PASSWORD", ""),
                    "url": os.getenv("MEMGRAPH_URL", "bolt://localhost:7688")
                }
            elif self.pg_graph_db == PropertyGraphType.NEBULA:
                self.graph_db_config = {
                    "space": os.getenv("NEBULA_SPACE", "flexible_graphrag"),
                    "overwrite": os.getenv("NEBULA_OVERWRITE", "true").lower() == "true",
                    "address": os.getenv("NEBULA_ADDRESS", "localhost"),
                    "port": int(os.getenv("NEBULA_PORT", "9669")),
                    "username": os.getenv("NEBULA_USERNAME", "root"),
                    "password": os.getenv("NEBULA_PASSWORD", "nebula")
                }
            elif self.pg_graph_db == PropertyGraphType.NEPTUNE:
                self.graph_db_config = {
                    "host": os.getenv("NEPTUNE_HOST"),
                    "port": int(os.getenv("NEPTUNE_PORT", "8182"))
                }
            elif self.pg_graph_db == PropertyGraphType.NEPTUNE_ANALYTICS:
                self.graph_db_config = {
                    "graph_identifier": os.getenv("NEPTUNE_ANALYTICS_GRAPH_ID")
                }
            # LangChain-only property graph stores
            elif self.pg_graph_db == PropertyGraphType.ARANGODB:
                self.graph_db_config = {
                    "url": os.getenv("ARANGODB_URL", "http://localhost:8529"),
                    "dbname": os.getenv("ARANGODB_DATABASE", "flexible_graphrag"),
                    "username": os.getenv("ARANGODB_USERNAME", "root"),
                    "password": os.getenv("ARANGODB_PASSWORD", ""),
                }
            elif self.pg_graph_db == PropertyGraphType.APACHE_AGE:
                self.graph_db_config = {
                    "host":            os.getenv("AGE_HOST", "localhost"),
                    "port":            int(os.getenv("AGE_PORT", "5434")),
                    "database":        os.getenv("AGE_DATABASE", "flexible_graphrag_age"),
                    "username":        os.getenv("AGE_USERNAME", "postgres"),
                    "password":        os.getenv("AGE_PASSWORD", "password"),
                    "graph_name":      os.getenv("AGE_GRAPH", "knowledge_graph"),
                    "collection_name": os.getenv("AGE_VECTOR_COLLECTION", "langchain_age_vectors"),
                    "search_type":     os.getenv("AGE_SEARCH_TYPE", "hybrid"),
                }
            elif self.pg_graph_db == PropertyGraphType.COSMOS_GREMLIN:
                self.graph_db_config = {
                    "endpoint": os.getenv("COSMOS_ENDPOINT"),
                    "key": os.getenv("COSMOS_KEY"),
                    "database": os.getenv("COSMOS_DATABASE", "flexible_graphrag"),
                    "container": os.getenv("COSMOS_CONTAINER", "graph"),
                }
            elif self.pg_graph_db == PropertyGraphType.SPANNER:
                self.graph_db_config = {
                    "project_id": os.getenv("SPANNER_PROJECT"),
                    "instance_id": os.getenv("SPANNER_INSTANCE"),
                    "database_id": os.getenv("SPANNER_DATABASE", "flexible-graphrag"),
                    "graph_name": os.getenv("SPANNER_GRAPH", "knowledge_graph"),
                    "credentials_file": os.getenv("SPANNER_CREDENTIALS_FILE"),
                }
            elif self.pg_graph_db == PropertyGraphType.HUGEGRAPH:
                self.graph_db_config = {
                    "host": os.getenv("HUGEGRAPH_HOST", "localhost"),
                    "port": int(os.getenv("HUGEGRAPH_PORT", "8082")),
                    "username": os.getenv("HUGEGRAPH_USERNAME", "admin"),
                    "password": os.getenv("HUGEGRAPH_PASSWORD", "password"),
                    "database": os.getenv("HUGEGRAPH_GRAPH", "hugegraph"),
                }
            elif self.pg_graph_db == PropertyGraphType.TIGERGRAPH:
                self.graph_db_config = {
                    "host": os.getenv("TIGERGRAPH_HOST", "localhost"),
                    "port": int(os.getenv("TIGERGRAPH_PORT", "14240")),
                    "username": os.getenv("TIGERGRAPH_USERNAME", "tigergraph"),
                    "password": os.getenv("TIGERGRAPH_PASSWORD", ""),
                    "graph_name": os.getenv("TIGERGRAPH_GRAPH", "flexible_graphrag"),
                }
            elif self.pg_graph_db == PropertyGraphType.SURREALDB:
                self.graph_db_config = {
                    "url": os.getenv("SURREALDB_URL", "ws://localhost:8010/rpc"),
                    "username": os.getenv("SURREALDB_USERNAME", "root"),
                    "password": os.getenv("SURREALDB_PASSWORD", "root"),
                    "namespace": os.getenv("SURREALDB_NAMESPACE", "test"),
                    "database": os.getenv("SURREALDB_DATABASE", "flexible_graphrag"),
                }
        
        # Per-store config takes precedence: {TYPE}_SEARCH_DB_CONFIG > SEARCH_DB_CONFIG > individual vars
        _stype = str(getattr(self.search_db, 'value', self.search_db) or "").upper()
        _named_search = _stype and os.getenv(f"{_stype}_SEARCH_DB_CONFIG")
        if _named_search:
            try:
                self.search_db_config = json.loads(_named_search)
            except (json.JSONDecodeError, ValueError):
                pass
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

        # --- Sync LangChain property-graph fusion flags (GRAPH_BACKEND, USE_LANGCHAIN_PG, LANGCHAIN_PG_STORE_TYPE)
        _db_type_str = (
            self.pg_graph_db.value if isinstance(self.pg_graph_db, PropertyGraphType)
            else str(self.pg_graph_db or "")
        ).lower()

        # LI-only stores: force llamaindex regardless of GRAPH_BACKEND setting.
        # (e.g. spanner — langchain-google-spanner requires langchain-core<1.0)
        from adapters.graph.pg_store_adapter import LI_ONLY_PG_STORES
        if _db_type_str in LI_ONLY_PG_STORES:
            if (self.graph_backend or "llamaindex").strip().lower() == "langchain":
                import logging as _li_log
                _li_log.getLogger(__name__).warning(
                    "GRAPH_BACKEND=langchain ignored for PG_GRAPH_DB=%s "
                    "(LI-only store) — using llamaindex",
                    _db_type_str,
                )
            self.graph_backend = "llamaindex"
            self.use_langchain_pg = False

        _gb = (self.graph_backend or "llamaindex").strip().lower()
        if _gb == "langchain":
            self.use_langchain_pg = True
        elif self.use_langchain_pg:
            self.graph_backend = "langchain"
        if self.use_langchain_pg and not self.langchain_pg_store_type:
            _pg = self.pg_graph_db
            if _pg is not None and _pg != PropertyGraphType.NONE:
                self.langchain_pg_store_type = (
                    _pg.value if isinstance(_pg, PropertyGraphType) else str(_pg)
                ).lower()

        # Default to False when not explicitly set by the user.
        if self.langchain_pg_vector_search is None:
            self.langchain_pg_vector_search = False
        import logging as _logging
        _cfg_log = _logging.getLogger(__name__)
        _cfg_log.debug(
            "Property graph fusion flags: graph_backend=%s use_langchain_pg=%s "
            "langchain_pg_store_type=%s pg_graph_db=%s",
            self.graph_backend,
            self.use_langchain_pg,
            self.langchain_pg_store_type,
            self.pg_graph_db,
        )
        if self.use_langchain_pg:
            _cfg_log.debug(
                "LangChain property graph retrieval enabled: graph_backend=%s "
                "use_langchain_pg=%s langchain_pg_store_type=%s",
                self.graph_backend,
                self.use_langchain_pg,
                self.langchain_pg_store_type,
            )
    
    def get_active_schema(self) -> Optional[Dict[str, Any]]:
        """Get the currently active schema based on schema_name
        
        Returns:
            None - Use LlamaIndex internal schema
            Dict - Use specified schema (SAMPLE_SCHEMA or custom)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Getting active schema for schema_name: '{self.schema_name}'")
        schemas_list = self.schemas or []
        logger.debug(f"Available schemas: {len(schemas_list)} schemas loaded")
        for i, schema_def in enumerate(schemas_list):
            logger.debug(f"  Schema {i}: name='{schema_def.get('name')}', has_schema={bool(schema_def.get('schema'))}")
        
        # Handle unset/empty schema name - use internal schema
        if not self.schema_name or self.schema_name.strip() == "":
            logger.debug("Schema name empty/unset — no explicit schema; ontology or extractor defaults apply")
            return None
        
        # Handle explicit "none" - use internal schema
        if self.schema_name.lower() == "none":
            logger.debug("Schema name='none' — no explicit schema; ontology or extractor defaults apply")
            return None
        
        # Handle "default" - use internal schema
        if self.schema_name == "default":
            logger.debug("Schema name='default' — no explicit schema; ontology or extractor defaults apply")
            return None
        
        # Handle "sample" - use project's SAMPLE_SCHEMA
        if self.schema_name == "sample":
            logger.info("Schema name is 'sample' - returning SAMPLE_SCHEMA")
            return SAMPLE_SCHEMA
        
        # Look for custom named schema in schemas array
        for schema_def in schemas_list:
            if schema_def.get("name") == self.schema_name:
                schema_data = schema_def.get("schema", {})
                logger.info(f"Found custom schema '{self.schema_name}' with {len(schema_data)} keys")
                return schema_data
        
        # If named schema not found, log warning and return None (fallback to internal)
        logger.warning(f"Schema '{self.schema_name}' not found in schemas array. Available schemas: {[s.get('name') for s in schemas_list]}")
        logger.warning("Falling back to internal LlamaIndex schema")
        return None

    @property
    def schema_config(self) -> Optional[Dict[str, Any]]:
        """Alias for get_active_schema() for backward compatibility"""
        return self.get_active_schema()

    # ===========================
    # RDF and Ontology Configuration
    # ===========================
    
    # Ontology configuration
    use_ontology: bool = Field(default=False, description="Enable ontology-driven extraction")
    ontology_path: Optional[str] = Field(None, description="Single ontology file path (e.g., ../schemas/company_ontology.ttl relative to process cwd). Use ontology_dir or ontology_paths for multiple files.")
    ontology_dir: Optional[str] = Field(None, description="Directory of ontology files — all .ttl/.rdf/.owl/.n3/.nt files are loaded and merged. Takes precedence over ontology_path.")
    ontology_paths: Optional[str] = Field(None, description="Comma-separated list of ontology file paths. Takes precedence over ontology_path but not ontology_dir.")
    ontology_format: OntologyFormat = Field(default=OntologyFormat.TURTLE, description="Default RDF ontology serialization format (used for ontology_path and ontology_paths; directory loading auto-detects by extension)")
    strict_schema_validation: bool = Field(default=False, description="strict=True: only extract entity/relation types defined in the schema (Pydantic-enforced via Literal type). strict=False: schema guides extraction but LLM may also produce types outside the schema.")
    disable_properties: bool = Field(default=False, description="Disable entity and relation properties extraction (default: False - properties enabled for all providers including OpenAI via function calling mode)")
    
    # RDF store configuration (stored as strings, validated to lists)
    rdf_enabled_stores: Optional[str] = Field(default=None, description="Comma-separated list of enabled RDF stores (legacy; use rdf_graph_db)")
    rdf_stores: Optional[str] = Field(default=None, description="RDF store configurations as JSON (legacy; use rdf_graph_db + individual connection fields)")
    default_rdf_backend: Optional[str] = Field(default=None, description="Default RDF backend (legacy)")
    
    # RDF_GRAPH_DB: selects exactly one RDF store for both ingestion and retrieval (or none)
    # Controls both what gets written during ingestion and which QA chain is used for retrieval.
    # Combined with pg_graph_db: pg_graph_db=neo4j + rdf_graph_db=fuseki writes to both.
    rdf_graph_db: RdfGraphType = Field(default=RdfGraphType.NONE, description="RDF store for ingestion + retrieval: none | fuseki | oxigraph | graphdb")
    
    # Standalone RDF store configurations (connection details for the store selected by rdf_graph_db)
    # Fuseki
    fuseki_base_url: str = Field(default="http://localhost:3030", description="Fuseki base URL")
    fuseki_dataset: str = Field(default="flexible-graphrag", description="Fuseki dataset name")
    fuseki_username: Optional[str] = Field(default=None, description="Fuseki username (required when auth is enabled)")
    fuseki_password: Optional[str] = Field(default=None, description="Fuseki password")
    
    # GraphDB / Ontotext
    graphdb_base_url: str = Field(default="http://localhost:7200", description="GraphDB base URL")
    graphdb_repository: str = Field(default="flexible-graphrag", description="GraphDB repository name")
    graphdb_username: Optional[str] = Field(default="admin", description="GraphDB username")
    graphdb_password: Optional[str] = Field(default="admin", description="GraphDB password")
    
    # Oxigraph
    oxigraph_store_path: Optional[str] = Field(default=None, description="Oxigraph embedded store directory path (pyoxigraph). Use only when NOT running the Docker container. Mutually exclusive with oxigraph_url.")
    oxigraph_url: Optional[str] = Field(default=None, description="Oxigraph HTTP server URL (e.g. http://localhost:7878). Preferred over oxigraph_store_path — no file locking issues.")

    # Amazon Neptune RDF/SPARQL (used when RDF_GRAPH_DB=neptune_rdf)
    neptune_rdf_host: Optional[str] = Field(default=None, description="Neptune cluster endpoint hostname (without protocol/port)")
    neptune_rdf_port: int = Field(default=8182, description="Neptune SPARQL port")
    neptune_rdf_region: str = Field(default="us-east-1", description="AWS region for Neptune RDF")
    neptune_rdf_use_iam_auth: bool = Field(default=True, description="Use AWS IAM SigV4 auth for Neptune SPARQL")
    neptune_rdf_use_https: bool = Field(default=True, description="Use HTTPS for Neptune SPARQL endpoint")
    neptune_rdf_aws_access_key_id: Optional[str] = Field(default=None, description="AWS access key for Neptune RDF (uses env credentials if not set)")
    neptune_rdf_aws_secret_access_key: Optional[str] = Field(default=None, description="AWS secret key for Neptune RDF (uses env credentials if not set)")

    # Query routing configuration
    query_routing_default: QueryRoutingMode = Field(default=QueryRoutingMode.HYBRID, description="Default query routing strategy")
    support_sparql: bool = Field(default=True, description="Enable SPARQL query support")
    support_cypher: bool = Field(default=True, description="Enable Cypher query support")
    
    # RDF export configuration
    enable_rdf_export: bool = Field(default=False, description="Enable RDF export API endpoints")
    rdf_export_format: OntologyFormat = Field(default=OntologyFormat.TURTLE, description="Default RDF export format")
    auto_export_to_rdf: bool = Field(default=False, description="Automatically export to RDF stores after ingestion")
    rdf_base_namespace: str = Field(default="https://integratedsemantics.org/flexible-graphrag/kg/", description="Base namespace for entity instance URIs in RDF export (e.g. https://integratedsemantics.org/flexible-graphrag/kg/). Set RDF_BASE_NAMESPACE in .env to override.")
    rdf_ontology_namespace: str = Field(default="https://integratedsemantics.org/flexible-graphrag/ontology#", description="Namespace for ontology types and relation predicates in RDF export (e.g. https://integratedsemantics.org/flexible-graphrag/ontology#). Set RDF_ONTOLOGY_NAMESPACE in .env to override.")
    rdf_annotation_syntax: str = Field(default="rdf_1.2", description="How to encode relation properties in RDF output. 'rdf_1.2' = RDF 1.2 inline {| |} annotation syntax (recommended, requires Fuseki 5 / Jena 5, GraphDB 10+, Oxigraph 0.4+). 'rdf_star' = legacy << >> annotation lines (same stores, older syntax). 'flat' = plain compound-predicate triples, works with any SPARQL 1.1 store.")
    
    @field_validator('rdf_enabled_stores', mode='after')
    @classmethod
    def parse_rdf_enabled_stores(cls, v):
        """Parse comma-separated RDF store names (legacy field)"""
        if v is None or v == '':
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.split(',') if s.strip()]
        if isinstance(v, list):
            return v
        return []

    @field_validator('rdf_stores', mode='after')
    @classmethod
    def parse_rdf_stores(cls, v):
        """Parse RDF store configurations from JSON string or list (legacy field)"""
        if v is None or v == '':
            return []
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to parse RDF_STORES as JSON: {v}")
                return []
        if isinstance(v, list):
            return v
        return []

    def get_rdf_store_config(self) -> Optional[Dict[str, Any]]:
        """Get connection config for the single selected RDF store (rdf_graph_db).

        Returns None when rdf_graph_db == 'none'.
        Replaces the old get_rdf_store_configs() which returned a list.
        """
        rdf_db = str(self.rdf_graph_db)
        if rdf_db == "none":
            return None
        if rdf_db == "fuseki":
            cfg: Dict[str, Any] = {
                "base_url": self.fuseki_base_url,
                "dataset": self.fuseki_dataset,
            }
            if self.fuseki_username:
                cfg["username"] = self.fuseki_username
            if self.fuseki_password:
                cfg["password"] = self.fuseki_password
            return {"name": "fuseki", "type": "fuseki", "config": cfg}
        if rdf_db == "graphdb":
            return {
                "name": "graphdb",
                "type": "graphdb",
                "config": {
                    "base_url": self.graphdb_base_url,
                    "repository": self.graphdb_repository,
                    "username": self.graphdb_username,
                    "password": self.graphdb_password,
                },
            }
        if rdf_db == "oxigraph":
            oxigraph_cfg: Dict[str, Any] = {}
            if self.oxigraph_url:
                oxigraph_cfg["url"] = self.oxigraph_url
            elif self.oxigraph_store_path:
                oxigraph_cfg["store_path"] = self.oxigraph_store_path
            else:
                oxigraph_cfg["url"] = "http://localhost:7878"
            return {"name": "oxigraph", "type": "oxigraph", "config": oxigraph_cfg}
        if rdf_db == "neptune_rdf":
            if not self.neptune_rdf_host:
                raise ValueError(
                    "NEPTUNE_RDF_HOST is required when RDF_GRAPH_DB=neptune_rdf"
                )
            neptune_rdf_cfg: Dict[str, Any] = {
                "host": self.neptune_rdf_host,
                "port": self.neptune_rdf_port,
                "region": self.neptune_rdf_region,
                "use_iam_auth": self.neptune_rdf_use_iam_auth,
                "use_https": self.neptune_rdf_use_https,
            }
            if self.neptune_rdf_aws_access_key_id:
                neptune_rdf_cfg["aws_access_key_id"] = self.neptune_rdf_aws_access_key_id
            if self.neptune_rdf_aws_secret_access_key:
                neptune_rdf_cfg["aws_secret_access_key"] = self.neptune_rdf_aws_secret_access_key
            return {"name": "neptune_rdf", "type": "neptune_rdf", "config": neptune_rdf_cfg}
        return None

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "use_enum_values": True,
        "extra": "allow",
        "env_parse_none_str": "null"  # Parse 'null' string as None instead of trying JSON
    }

# Sample schema configuration - comprehensive schema with permissive validation for maximum flexibility
SAMPLE_SCHEMA = {
    "entities": ["PERSON", "ORGANIZATION", "LOCATION", "PLACE", "TECHNOLOGY", "PROJECT"],
    "relations": ["WORKS_FOR", "LOCATED_IN", "USES", "COLLABORATES_WITH", "DEVELOPS", "HAS", "PART_OF", "WORKED_ON", "WORKED_WITH", "WORKED_AT"],
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
    "properties": {
        # Properties for PERSON entities
        "PERSON": {
            "name": "str",
            "email": "str",
            "phone": "str",
            "title": "str",
            "age": "int",
            "hire_date": "str"
        },
        # Properties for ORGANIZATION entities
        "ORGANIZATION": {
            "name": "str",
            "industry": "str",
            "founded_year": "int",
            "employee_count": "int",
            "revenue": "float",
            "website": "str"
        },
        # Properties for PROJECT entities
        "PROJECT": {
            "name": "str",
            "description": "str",
            "budget": "float",
            "start_date": "str",
            "end_date": "str",
            "status": "str"
        },
        # Properties for TECHNOLOGY entities
        "TECHNOLOGY": {
            "name": "str",
            "version": "str",
            "release_date": "str",
            "license": "str"
        },
        # Properties for LOCATION entities
        "LOCATION": {
            "name": "str",
            "country": "str",
            "region": "str",
            "latitude": "float",
            "longitude": "float"
        },
        # Properties for PLACE entities
        "PLACE": {
            "name": "str",
            "address": "str",
            "city": "str",
            "postal_code": "str"
        }
    },
    "relation_properties": {
        # Properties for WORKS_FOR relationship
        "WORKS_FOR": {
            "role": "str",
            "start_date": "str",
            "employment_type": "str"  # Full-time, Part-time, Contract, etc.
        },
        # Properties for WORKED_AT relationship
        "WORKED_AT": {
            "role": "str",
            "start_date": "str",
            "end_date": "str",
            "duration_years": "float"
        },
        # Properties for WORKED_ON relationship
        "WORKED_ON": {
            "contribution_percentage": "float",
            "start_date": "str",
            "end_date": "str"
        },
        # Properties for COLLABORATES_WITH relationship
        "COLLABORATES_WITH": {
            "since": "str",
            "project_count": "int"
        },
        # Properties for USES relationship  
        "USES": {
            "proficiency_level": "str",  # Beginner, Intermediate, Advanced, Expert
            "years_experience": "float"
        },
        # Properties for DEVELOPS relationship
        "DEVELOPS": {
            "role": "str",  # Lead, Contributor, Maintainer
            "since": "str"
        }
    },
    "strict": False,
    "max_triplets_per_chunk": 20
}

# Legacy LlamaIndex documentation schema samples (too restrictive - commented out)
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

# Note: legacy per-store schema splits removed - system now always uses user's configured schema
# Property graph stores share the same schema configuration (SAMPLE_SCHEMA by default)