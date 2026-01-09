from llama_index.core import VectorStoreIndex, PropertyGraphIndex, StorageContext, Settings, QueryBundle
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.extractors import KeywordExtractor, SummaryExtractor
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor, SimpleLLMPathExtractor, DynamicLLMPathExtractor
from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY
from llama_index.core.schema import BaseNode
from typing import List, Dict, Any, Union
from pathlib import Path
import logging
import asyncio

from config import Settings as AppSettings, SAMPLE_SCHEMA, SearchDBType, VectorDBType, LLMProvider
from document_processor import DocumentProcessor
from factories import LLMFactory, DatabaseFactory

# Import observability for graph extraction tracing and metrics
try:
    from observability import get_tracer
    from observability.metrics import get_rag_metrics
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    get_tracer = None
    get_rag_metrics = None

logger = logging.getLogger(__name__)


def count_extracted_entities_and_relations(nodes: List[BaseNode]) -> tuple[int, int]:
    """
    Count entities and relations from node metadata after extraction.
    
    This follows Method 1 from LlamaIndex best practices: examining node metadata
    before insertion into the graph store to get accurate extraction counts.
    
    Args:
        nodes: List of nodes after kg_extractors have processed them
        
    Returns:
        Tuple of (entity_count, relation_count)
    """
    entity_count = 0
    relation_count = 0
    
    for node in nodes:
        # Get entities from this node (stored in metadata by extractors)
        entities = node.metadata.get(KG_NODES_KEY, [])
        entity_count += len(entities)
        
        # Get relations from this node (stored in metadata by extractors)
        relations = node.metadata.get(KG_RELATIONS_KEY, [])
        relation_count += len(relations)
    
    return entity_count, relation_count


class SchemaManager:
    """Manages schema definitions for entity and relationship extraction"""
    
    def __init__(self, schema_config: Dict[str, Any] = None, app_config=None):
        self.schema_config = schema_config or {}
        self.app_config = app_config
    
    def create_extractor(self, llm, use_schema: bool = True, llm_provider=None, extractor_type: str = "schema"):
        """Create knowledge graph extractor with optional schema enforcement
        
        Args:
            extractor_type: "simple", "schema", or "dynamic"
        """
        
        # Use 4 workers for all LLM providers - Ollama parallel processing now properly configured
        workers = 4
        
        # Log LLM provider for debugging
        from config import LLMProvider
        is_ollama = (llm_provider == LLMProvider.OLLAMA) if llm_provider else False
        logger.info(f"LLM Provider Detection: {llm_provider} -> is_ollama={is_ollama} -> workers={workers}")
        if is_ollama:
            logger.info(f"OLLAMA PARALLEL PROCESSING: Using {workers} workers with OLLAMA_NUM_PARALLEL=4 configuration")
        
        # Get configurable values
        max_triplets = getattr(self.app_config, 'max_triplets_per_chunk', 100) if self.app_config else 100
        max_paths = getattr(self.app_config, 'max_paths_per_chunk', 100) if self.app_config else 100
        
        # Handle dynamic extractor type
        if extractor_type == "dynamic":
            logger.info("Using DynamicLLMPathExtractor for flexible relationship discovery")
            logger.info(f"Using max_triplets_per_chunk={max_triplets}")
            # DynamicLLMPathExtractor can work with or without initial schema guidance
            if self.schema_config:
                logger.info("Providing initial ontology guidance to DynamicLLMPathExtractor")
                # With initial ontology - provide starting guidance but allow expansion
                return DynamicLLMPathExtractor(
                    llm=llm,
                    max_triplets_per_chunk=max_triplets,
                    num_workers=workers,
                    allowed_entity_types=self.schema_config.get("entities", []),
                    allowed_relation_types=self.schema_config.get("relations", [])
                )
            else:
                logger.info("Using DynamicLLMPathExtractor without initial ontology - full LLM freedom")
                # Without initial ontology - complete freedom to infer schema
                return DynamicLLMPathExtractor(
                    llm=llm,
                    max_triplets_per_chunk=max_triplets,
                    num_workers=workers
                )
        
        # Use schema if explicitly requested
        if not use_schema:
            logger.info(f"Using SimpleLLMPathExtractor with max_paths_per_chunk={max_paths}")
            return SimpleLLMPathExtractor(
                llm=llm,
                max_paths_per_chunk=max_paths,
                num_workers=workers
            )
        
        # Always use user's configured schema - no special Kuzu schema
        schema_to_use = self.schema_config
        if schema_to_use:
            logger.info("Using user-configured schema for knowledge graph extraction")
            logger.info(f"Schema entities: {schema_to_use.get('entities', 'None')}")
            logger.info(f"Schema relations: {schema_to_use.get('relations', 'None')}")
            validation_schema = schema_to_use.get('validation_schema', 'None')
            logger.info(f"Schema validation_schema: {validation_schema}")
            logger.info(f"Schema validation_schema type: {type(validation_schema)}")
            if isinstance(validation_schema, list) and len(validation_schema) > 0:
                logger.info(f"First validation rule: {validation_schema[0]}")

        
        if not schema_to_use:
            logger.info(f"Using SimpleLLMPathExtractor (no schema) with max_paths_per_chunk={max_paths}")
            return SimpleLLMPathExtractor(
                llm=llm,
                max_paths_per_chunk=max_paths,
                num_workers=workers
            )
        
        # Create schema-guided extractor
        logger.info(f"Using SchemaLLMPathExtractor with max_triplets_per_chunk={max_triplets}")
        return SchemaLLMPathExtractor(
            llm=llm,
            possible_entities=schema_to_use.get("entities", []),
            possible_relations=schema_to_use.get("relations", []),
            kg_validation_schema=schema_to_use.get("validation_schema"),
            strict=schema_to_use.get("strict", True),
            max_triplets_per_chunk=max_triplets,
            num_workers=workers
        )

class HybridSearchSystem:
    """Configurable hybrid search system with full-text, vector, and graph search"""
    
    def __init__(self, config: AppSettings):
        self.config = config
        
        # CRITICAL: Validate LLM + Embedding compatibility
        # Google embeddings (async SDK) only work with Gemini/Vertex AI LLMs (also async)
        # Mixing async embeddings with sync LLMs causes "attached to different loop" errors during search
        embedding_kind = getattr(config, 'embedding_kind', None)
        if embedding_kind in ['google', 'vertex'] and config.llm_provider not in [LLMProvider.GEMINI, LLMProvider.VERTEX_AI]:
            logger.error("=" * 80)
            logger.error("INCOMPATIBLE CONFIGURATION DETECTED!")
            logger.error(f"LLM Provider: {config.llm_provider}")
            logger.error(f"Embedding Kind: {embedding_kind}")
            logger.error("")
            logger.error("Google/Vertex embeddings use async SDK and ONLY work with Gemini/Vertex LLMs.")
            logger.error("Mixing async embeddings with non-Gemini LLMs causes event loop conflicts during search.")
            logger.error("")
            logger.error("Supported combinations:")
            logger.error("  OK: Gemini LLM + Google embeddings")
            logger.error("  OK: OpenAI LLM + OpenAI embeddings")
            logger.error("  OK: Ollama LLM + Ollama embeddings")
            logger.error("  FAIL: OpenAI/Ollama/etc LLM + Google embeddings")
            logger.error("")
            logger.error("Please change EMBEDDING_KIND to match your LLM provider or use Gemini LLM.")
            logger.error("=" * 80)
            raise ValueError(f"Incompatible configuration: {config.llm_provider} LLM with {embedding_kind} embeddings. "
                           f"Google/Vertex embeddings require Gemini/Vertex AI LLM due to async SDK requirements.")
        
        # Initialize DocumentProcessor with configured parser type
        # Handle both Enum and string values
        if hasattr(config, 'document_parser'):
            parser_type = config.document_parser.value if hasattr(config.document_parser, 'value') else str(config.document_parser)
        else:
            parser_type = "docling"
        self.document_processor = DocumentProcessor(config, parser_type=parser_type)
        
        # Log schema configuration
        active_schema = config.get_active_schema()
        if active_schema:
            # Handle both list and Literal type annotations safely
            entities = active_schema.get('entities', [])
            relations = active_schema.get('relations', [])
            
            # Convert Literal types to lists for counting
            try:
                entity_count = len(entities) if hasattr(entities, '__len__') and not hasattr(entities, '__args__') else len(getattr(entities, '__args__', []))
                relation_count = len(relations) if hasattr(relations, '__len__') and not hasattr(relations, '__args__') else len(getattr(relations, '__args__', []))
                logger.info(f"Schema Configuration: Using '{config.schema_name}' schema with {entity_count} entity types and {relation_count} relation types")
            except (TypeError, AttributeError):
                logger.info(f"Schema Configuration: Using '{config.schema_name}' schema")
            
            # Log the actual values safely
            try:
                entity_list = list(entities) if hasattr(entities, '__iter__') and not hasattr(entities, '__args__') else list(getattr(entities, '__args__', []))
                relation_list = list(relations) if hasattr(relations, '__iter__') and not hasattr(relations, '__args__') else list(getattr(relations, '__args__', []))
                logger.info(f"Schema Entities: {entity_list}")
                logger.info(f"Schema Relations: {relation_list}")
            except (TypeError, AttributeError):
                logger.info(f"Schema Entities: {entities}")
                logger.info(f"Schema Relations: {relations}")
        else:
            logger.info(f"Schema Configuration: Using '{config.schema_name}' (no schema - simple extraction)")
        
        self.schema_manager = SchemaManager(active_schema, config)
        
        # Initialize LLM and embedding models with enhanced logging
        logger.info(f"=== LLM CONFIGURATION ===")
        # Handle both enum and string values safely
        provider_name = getattr(config.llm_provider, 'value', config.llm_provider)
        logger.info(f"LLM Provider: {provider_name}")
        
        self.llm = LLMFactory.create_llm(config.llm_provider, config.llm_config)
        self.embed_model = LLMFactory.create_embedding_model(config.llm_provider, config.llm_config, settings=config)
        
        # Enhanced LLM configuration logging
        if hasattr(self.llm, 'model'):
            logger.info(f"LLM Model: {self.llm.model}")
        if hasattr(self.llm, 'base_url'):
            logger.info(f"LLM Base URL: {self.llm.base_url}")
        if hasattr(self.llm, 'request_timeout'):
            logger.info(f"LLM Timeout: {self.llm.request_timeout}s")
        if hasattr(self.llm, 'temperature'):
            logger.info(f"LLM Temperature: {self.llm.temperature}")
            
        if hasattr(self.embed_model, 'model_name'):
            logger.info(f"Embedding Model: {self.embed_model.model_name}")
        elif hasattr(self.embed_model, '_model_name'):
            logger.info(f"Embedding Model: {self.embed_model._model_name}")
        if hasattr(self.embed_model, 'base_url'):
            logger.info(f"Embedding Base URL: {self.embed_model.base_url}")
            
        logger.info(f"=== DATABASE CONFIGURATION ===")
        # Handle both enum and string values safely for database configs
        graph_db_name = getattr(config.graph_db, 'value', config.graph_db) if config.graph_db else 'none'
        vector_db_name = getattr(config.vector_db, 'value', config.vector_db) if config.vector_db else 'none'
        search_db_name = getattr(config.search_db, 'value', config.search_db) if config.search_db else 'none'
        
        logger.info(f"Graph DB: {graph_db_name}")
        logger.info(f"Vector DB: {vector_db_name}")
        logger.info(f"Search DB: {search_db_name}")
        logger.info(f"Knowledge Graph Enabled: {config.enable_knowledge_graph}")
        
        # Set global settings
        Settings.llm = self.llm
        Settings.embed_model = self.embed_model
        Settings.chunk_size = config.chunk_size
        
        # Initialize database connections
        self._setup_databases()
        
        # Initialize indexes
        self.vector_index = None
        self.graph_index = None
        self.hybrid_retriever = None
        
        # Track whether graph was intentionally skipped (for per-ingest skip_graph flag)
        self.graph_intentionally_skipped = False
        
        # Track observability status
        self._observability_enabled = getattr(config, 'enable_observability', False)
        
        # Initialize error counter at 0 so dashboard shows "0" instead of "No Data"
        if self._observability_enabled:
            try:
                from observability.metrics import get_rag_metrics
                metrics = get_rag_metrics()
                # Initialize error counter with 0 to ensure metric exists
                metrics.errors_total.add(0, {})
                logger.info("Initialized observability metrics (error counter at 0)")
            except Exception as e:
                logger.warning(f"Failed to initialize observability metrics: {e}")
        
        logger.info("=== SYSTEM READY ===")
        logger.info("HybridSearchSystem initialized successfully with Ollama!" if config.llm_provider == LLMProvider.OLLAMA else "HybridSearchSystem initialized successfully")
    
    
    def _setup_databases(self):
        """Initialize database connections based on configuration"""
        
        # Vector database
        self.vector_store = DatabaseFactory.create_vector_store(
            self.config.vector_db, 
            self.config.vector_db_config or {},
            self.config.llm_provider,
            self.config.llm_config,
            app_config=self.config
        )
        
        # Check if vector search is disabled
        if self.vector_store is None:
            logger.info("Vector search disabled - system will use only graph and/or fulltext search")
        
        # Graph database - pass vector store info and LLM config for Kuzu configuration
        self.graph_store = DatabaseFactory.create_graph_store(
            self.config.graph_db,
            self.config.graph_db_config or {},
            self.config.get_active_schema(),
            has_separate_vector_store=(self.vector_store is not None),
            llm_provider=self.config.llm_provider,
            llm_config=self.config.llm_config,
            app_config=self.config
        )
        
        # Check if graph search is disabled
        if self.graph_store is None:
            logger.info("Graph search disabled - system will use only vector and/or fulltext search")
        
        # Search database - handle BM25, external search engines, or none
        if self.config.search_db == SearchDBType.NONE:
            self.search_store = None
            logger.info("Full-text search disabled - no search store created")
        elif self.config.search_db == SearchDBType.BM25:
            self.search_store = None  # BM25 is handled by BM25Retriever
            logger.info("Using BM25 retriever for full-text search (no external search engine required)")
        else:
            self.search_store = DatabaseFactory.create_search_store(
                self.config.search_db,
                self.config.search_db_config or {},
                self.config.vector_db,  # Pass vector_db_type for OpenSearch hybrid detection
                self.config.llm_provider,
                self.config.llm_config,
                app_config=self.config
            )
            if self.search_store is not None:
                logger.info(f"Using external search engine: {self.config.search_db}")
            else:
                logger.info(f"Search store creation skipped (handled by factories.py logic)")
        
        # Validate that at least one search modality is enabled
        has_vector = str(self.config.vector_db) != "none"
        has_graph = str(self.config.graph_db) != "none" 
        has_search = str(self.config.search_db) != "none"
        
        if not (has_vector or has_graph or has_search):
            raise ValueError(
                "Invalid configuration: All search modalities are disabled! "
                "At least one of VECTOR_DB, GRAPH_DB, or SEARCH_DB must be enabled (not 'none'). "
                f"Current config: VECTOR_DB={self.config.vector_db}, "
                f"GRAPH_DB={self.config.graph_db}, SEARCH_DB={self.config.search_db}"
            )
        
        logger.info("Database connections established")
    
    @classmethod
    def from_settings(cls, settings: AppSettings):
        """Create HybridSearchSystem from Settings object"""
        return cls(settings)
    
    async def ingest_documents(self, file_paths: List[Union[str, Path]], processing_id: str = None, status_callback=None, skip_graph: bool = False):
        """Process and ingest documents into all search modalities
        
        Args:
            skip_graph: If True, skip knowledge graph extraction for this ingest (temporary override)
        """
        
        # Helper function to check cancellation
        def _check_cancellation():
            if processing_id:
                from backend import PROCESSING_STATUS
                return (processing_id in PROCESSING_STATUS and 
                        PROCESSING_STATUS[processing_id]["status"] == "cancelled")
            return False
        
        # Helper function to update progress with file info
        def _update_progress(message: str, progress: int, current_file: str = None, current_phase: str = None, files_completed: int = 0):
            if status_callback:
                status_callback(
                    processing_id=processing_id,
                    status="processing",
                    message=message,
                    progress=progress,
                    current_file=current_file,
                    current_phase=current_phase,
                    files_completed=files_completed,
                    total_files=len(file_paths)
                )
        
        # Check for partial state and clear it before starting new ingestion
        if (self.vector_index is None) != (self.graph_index is None):
            logger.warning("Detected partial system state - clearing before new ingestion")
            self._clear_partial_state()
        
        # Also clear if we have partial retriever setup
        if self.hybrid_retriever is None and (self.vector_index is not None or self.graph_index is not None):
            logger.warning("Detected incomplete retriever setup - clearing before new ingestion")
            self._clear_partial_state()
        
        # Step 1: Convert documents using Docling
        logger.info("Converting documents with Docling...")
        _update_progress("Converting documents with Docling...", 20, current_phase="docling")
        
        documents = await self.document_processor.process_documents(file_paths, processing_id=processing_id)
        
        if not documents:
            raise ValueError("No documents were successfully processed")
        
        # Check for cancellation after document processing
        if _check_cancellation():
            logger.info("Processing cancelled during document conversion")
            raise RuntimeError("Processing cancelled by user")
        
        # Step 2: Process documents into nodes once
        logger.info("Processing documents into nodes...")
        _update_progress("Splitting documents into chunks...", 30, current_phase="chunking")
        
        # Store documents for later use in search store indexing (accumulative)
        if not hasattr(self, '_last_ingested_documents') or self._last_ingested_documents is None:
            self._last_ingested_documents = []
        
        # Add new documents to existing collection
        previous_count = len(self._last_ingested_documents)
        self._last_ingested_documents.extend(documents)
        logger.info(f"Added {len(documents)} documents. Total stored: {len(self._last_ingested_documents)} (previous: {previous_count}, new: {len(documents)})")
        for i, doc in enumerate(documents):
            content_preview = doc.text[:100] + "..." if len(doc.text) > 100 else doc.text
            logger.info(f"New doc {i}: {content_preview}")
            logger.info(f"New doc {i} metadata: {doc.metadata}")
        
        # Conditional transformations based on LLM provider for performance
        transformations = [
            SentenceSplitter(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap
            ),
            self.embed_model
        ]
        
        # Skip expensive LLM-dependent extractors for ALL providers based on performance analysis
        # KeywordExtractor and SummaryExtractor add cost/latency without improving relationship extraction quality
        # Commented out for optimization - can be re-enabled for testing:
        # transformations.insert(-1, KeywordExtractor(keywords=5))
        # transformations.insert(-1, SummaryExtractor(summaries=["prev", "self", "next"]))
        logger.info("Skipped KeywordExtractor and SummaryExtractor for all LLM providers - optimized pipeline for speed and cost efficiency")
        
        # Process documents through transformations to get nodes
        import time
        start_time = time.time()
        logger.info(f"Starting LlamaIndex IngestionPipeline with transformations: {[type(t).__name__ for t in transformations]}")
        
        pipeline = IngestionPipeline(transformations=transformations)
        
        # Use run_in_executor to avoid asyncio conflict
        import asyncio
        import functools
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        run_pipeline = functools.partial(
            pipeline.run,
            documents=documents
        )
        
        logger.info("Executing IngestionPipeline.run() - this includes chunking and embedding generation (KeywordExtractor/SummaryExtractor removed for optimization)")
        # Use run_in_executor with proper event loop handling to avoid nested async issues
        nodes = await loop.run_in_executor(None, run_pipeline)
        
        pipeline_duration = time.time() - start_time
        logger.info(f"IngestionPipeline completed in {pipeline_duration:.2f}s - Generated {len(nodes)} nodes from {len(documents)} documents")
        
        # Log embedding model details for performance analysis
        embed_model_name = getattr(self.embed_model, 'model_name', str(type(self.embed_model).__name__))
        logger.info(f"Embeddings generated using: {embed_model_name}")
        
        # Check for cancellation after node processing
        if _check_cancellation():
            logger.info("Processing cancelled during node generation")
            raise RuntimeError("Processing cancelled by user")
        
        # Step 3: Create vector index from processed nodes (if vector search enabled)
        if self.vector_store is not None:
            vector_start_time = time.time()
            vector_store_type = type(self.vector_store).__name__
            logger.info(f"Creating vector index from {len(nodes)} nodes using {vector_store_type}...")
            _update_progress("Building vector index...", 50, current_phase="indexing")
            
            vector_storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
            logger.info("Starting VectorStoreIndex creation - this stores embeddings in the vector database")
            
            # Use run_in_executor for consistent async handling like other LlamaIndex operations
            import asyncio
            import functools
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            create_vector_index = functools.partial(
                VectorStoreIndex,
                nodes=nodes,
                storage_context=vector_storage_context,
                show_progress=True
            )
            self.vector_index = await loop.run_in_executor(None, create_vector_index)
            
            vector_duration = time.time() - vector_start_time
            logger.info(f"Vector index creation completed in {vector_duration:.2f}s using {vector_store_type}")
        else:
            logger.info("Vector search disabled - skipping vector index creation")
            _update_progress("Vector search disabled - skipping vector index...", 50, current_phase="indexing")
            self.vector_index = None
        
        # Check for cancellation after vector index creation
        if _check_cancellation():
            logger.info("Processing cancelled during vector index creation")
            raise RuntimeError("Processing cancelled by user")
        
        # Step 4: Create graph index using the same nodes (only if knowledge graph is enabled)
        # Check both global config AND per-ingest skip_graph flag
        should_skip_graph = skip_graph or not self.config.enable_knowledge_graph
        
        if should_skip_graph:
            if skip_graph and self.config.enable_knowledge_graph:
                logger.info("Knowledge graph extraction SKIPPED - per-ingest skip_graph flag is True (temporary override)")
                _update_progress("Skipping knowledge graph extraction (per-ingest flag)...", 70, current_phase="kg_extraction")
                # Track that graph was intentionally skipped for this ingestion
                self.graph_intentionally_skipped = True
                # Preserve existing graph_index if it exists (from previous ingestions)
                if self.graph_index:
                    logger.info("Preserving existing graph index from previous ingestion(s)")
                # If no existing graph, that's OK - partial graph state is allowed with skip_graph
            elif not self.config.enable_knowledge_graph:
                logger.info("Knowledge graph extraction disabled - skipping graph index creation")
                _update_progress("Skipping knowledge graph extraction...", 70, current_phase="kg_extraction")
                # Graph disabled in config - clear any existing graph since it shouldn't be used
                self.graph_index = None
                self.graph_intentionally_skipped = False
            kg_extractors = []
            logger.info("Graph index creation skipped")
        else:
            # Knowledge graph is enabled and not skipped - proceed with extraction
            # Clear the skip flag since we're creating a graph now
            self.graph_intentionally_skipped = False
            kg_setup_start_time = time.time()
            graph_store_type = type(self.graph_store).__name__
            llm_model_name = getattr(self.llm, 'model', str(type(self.llm).__name__))
            
            logger.info(f"Creating graph index from {len(nodes)} nodes using {graph_store_type} with LLM: {llm_model_name}")
            _update_progress("Extracting knowledge graph...", 70, current_phase="kg_extraction")
            
            # Use knowledge graph extraction for graph functionality
            kg_extractors = []
            
            # Check schema configuration based on database type and schema_name
            is_kuzu = str(self.config.graph_db) == "kuzu"
            active_schema = self.config.get_active_schema()
            has_schema = active_schema is not None
            
            # Use schema if explicitly configured
            if has_schema:
                kg_extractor = self.schema_manager.create_extractor(
                    self.llm, 
                    use_schema=True,
                    llm_provider=self.config.llm_provider,
                    extractor_type=self.config.kg_extractor_type
                )
                kg_extractors = [kg_extractor]
                logger.info(f"Using knowledge graph extraction with '{self.config.schema_name}' schema and LLM: {llm_model_name}")
            else:
                # Use simple extractor for Neo4j without schema
                kg_extractor = self.schema_manager.create_extractor(
                    self.llm, 
                    use_schema=False,
                    llm_provider=self.config.llm_provider,
                    extractor_type=self.config.kg_extractor_type
                )
                kg_extractors = [kg_extractor]
                logger.info(f"Using simple knowledge graph extraction (no schema) with LLM: {llm_model_name}")
            
            kg_setup_duration = time.time() - kg_setup_start_time
            logger.info(f"Knowledge graph extractor setup completed in {kg_setup_duration:.2f}s")
            
            # Create graph index
            graph_storage_context = StorageContext.from_defaults(
                property_graph_store=self.graph_store,
                docstore=self.vector_index.docstore  # Share the same docstore
            )
            
            # Use asyncio.get_event_loop().run_in_executor to avoid event loop conflict
            import asyncio
            import functools
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            # For Kuzu with separate vector store, we need to explicitly provide vector_store
            graph_index_kwargs = {
                "documents": documents,
                "llm": self.llm,
                "embed_model": self.embed_model,
                "kg_extractors": kg_extractors,
                "storage_context": graph_storage_context,
                "transformations": [],  # Skip transformations since already processed
                "show_progress": True,
                "include_embeddings": True,
                "include_metadata": True,
                "use_async": False  # Temporarily disable async to fix multi-file event loop conflicts
            }
            
            # CRITICAL: Neptune Analytics has non-atomic vector index limitations
            # Disable vector embeddings for knowledge graph nodes to avoid vector operation conflicts
            if hasattr(self.graph_store, '__class__') and 'NeptuneAnalytics' in str(self.graph_store.__class__):
                graph_index_kwargs["embed_kg_nodes"] = False
                logger.info("Neptune Analytics detected: Setting embed_kg_nodes=False to avoid vector index atomicity issues")
                logger.info("Knowledge graph structure will be created without vector embeddings (use separate VECTOR_DB for embeddings)")
            
            # This is the most time-consuming step - LLM calls for entity/relationship extraction
            graph_creation_start_time = time.time()
            logger.info(f"Starting PropertyGraphIndex.from_documents() - this will make LLM calls to extract entities and relationships from {len(documents)} documents")
            logger.info(f"LLM model being used for knowledge graph extraction: {llm_model_name}")
            logger.info(f"Graph database target: {graph_store_type}")                    
            
            # Create tracer span for graph extraction if observability is enabled
            if OBSERVABILITY_AVAILABLE:
                from opentelemetry import context, trace as otel_trace
                tracer = get_tracer(__name__)
                graph_span = tracer.start_span("rag.graph_extraction")
                graph_span.set_attribute("graph.num_documents", len(documents))
                graph_span.set_attribute("graph.llm_model", llm_model_name)
                graph_span.set_attribute("graph.database_type", graph_store_type)
                graph_span.set_attribute("graph.extractor_type", self.config.kg_extractor_type)
                
                # Attach span to current context for propagation to nested operations
                ctx = otel_trace.set_span_in_context(graph_span)
                token = context.attach(ctx)
            else:
                graph_span = None
                token = None
            
            try:
                # Use run_in_executor with proper nest_asyncio handling
                create_graph_index = functools.partial(PropertyGraphIndex.from_documents, **graph_index_kwargs)
                self.graph_index = await loop.run_in_executor(None, create_graph_index)
                
                graph_creation_duration = time.time() - graph_creation_start_time
                logger.info(f"PropertyGraphIndex creation completed in {graph_creation_duration:.2f}s")
                logger.info(f"Knowledge graph extraction finished - entities and relationships stored in {graph_store_type}")
                
                # Count entities and relations from the graph store
                num_entities = 0
                num_relations = 0
                try:
                    # Method 1: Try to get counts from graph index
                    if hasattr(self.graph_index, 'property_graph_store'):
                        pg_store = self.graph_index.property_graph_store
                        
                        # Try get_triplets method (works for most stores)
                        if hasattr(pg_store, 'get_triplets'):
                            try:
                                triplets = pg_store.get_triplets()
                                if triplets:
                                    # Count unique subjects (entities) and relations
                                    unique_entities = set()
                                    for triplet in triplets:
                                        if hasattr(triplet, 'subject_id'):
                                            unique_entities.add(triplet.subject_id)
                                        if hasattr(triplet, 'object_id'):
                                            unique_entities.add(triplet.object_id)
                                    num_entities = len(unique_entities)
                                    num_relations = len(triplets)
                                    logger.debug(f"Counted from triplets: {num_entities} entities, {num_relations} relations")
                            except Exception as triplet_error:
                                logger.debug(f"Could not get triplets: {triplet_error}")
                        
                        # Fallback: Try get_schema method
                        if num_entities == 0 and hasattr(pg_store, 'get_schema'):
                            try:
                                schema = pg_store.get_schema(refresh=True)
                                if schema:
                                    # Try different schema formats
                                    if isinstance(schema, str):
                                        # Parse string schema (Neo4j returns string)
                                        import re
                                        nodes_match = re.findall(r'Node properties:', schema)
                                        rels_match = re.findall(r'Relationship properties:|Relationships:', schema)
                                        # This is approximate - use triplets method if available
                                    elif isinstance(schema, dict):
                                        nodes = schema.get('nodes', [])
                                        rels = schema.get('relationships', [])
                                        num_entities = len(nodes) if nodes else 0
                                        num_relations = len(rels) if rels else 0
                                        logger.debug(f"Counted from schema: {num_entities} entity types, {num_relations} relation types")
                            except Exception as schema_error:
                                logger.debug(f"Could not get schema: {schema_error}")
                    
                    logger.info(f"Graph extraction complete: {num_entities} entities, {num_relations} relationships")
                except Exception as count_error:
                    logger.warning(f"Could not count graph entities/relations: {count_error}")
                    # Even if counting fails, we still have the timing data
                    logger.info(f"Graph extraction complete: entity/relation counts unavailable")
                
                # Add metrics to span if available
                if graph_span:
                    graph_span.set_attribute("graph.extraction_latency_ms", graph_creation_duration * 1000)
                    if num_entities > 0 or num_relations > 0:
                        graph_span.set_attribute("graph.num_entities", num_entities)
                        graph_span.set_attribute("graph.num_relations", num_relations)
                    graph_span.set_attribute("graph.status", "success")
                
                # Record custom metrics for Grafana dashboard
                if OBSERVABILITY_AVAILABLE and get_rag_metrics:
                    try:
                        metrics = get_rag_metrics()
                        # Record graph extraction with entity/relation counts
                        metrics.record_graph_extraction(
                            latency_ms=graph_creation_duration * 1000,
                            num_entities=num_entities,
                            num_relations=num_relations
                        )
                        logger.info(f"[PATH 1] Recorded graph extraction metrics: {graph_creation_duration * 1000:.2f}ms, {num_entities} entities, {num_relations} relations")
                    except Exception as e:
                        logger.warning(f"Failed to record graph metrics: {e}")
                    
            except Exception as e:
                graph_creation_duration = time.time() - graph_creation_start_time
                if graph_span:
                    graph_span.set_attribute("graph.status", "error")
                    graph_span.set_attribute("graph.error", str(e))
                    graph_span.record_exception(e)
                raise
            finally:
                if graph_span:
                    graph_span.end()
                if token is not None:
                    context.detach(token)
            
            # Check for cancellation after graph index creation
            if _check_cancellation():
                logger.info("Processing cancelled during graph index creation")
                raise RuntimeError("Processing cancelled by user")
        
        # Step 4: Setup hybrid retriever
        self._setup_hybrid_retriever()
        
        # Step 5: Persist indexes if configured
        self._persist_indexes()
        
        total_duration = time.time() - start_time
        vector_time = locals().get('vector_duration', 0)
        graph_time = locals().get('graph_creation_duration', 0)
        
        # Log warnings for missing timing data
        if self.vector_store and vector_time == 0:
            logger.warning("Vector creation duration not captured - timing may be inaccurate")
        if self.config.enable_knowledge_graph and graph_time == 0:
            logger.warning("Graph creation duration not captured - timing may be inaccurate")
        
        logger.info(f"Document ingestion completed successfully in {total_duration:.2f}s total!")
        logger.info(f"Performance summary - Pipeline: {pipeline_duration:.2f}s, Vector: {vector_time:.2f}s, Graph: {graph_time:.2f}s")
        
        # Record comprehensive metrics for Grafana dashboard
        if OBSERVABILITY_AVAILABLE and get_rag_metrics:
            try:
                metrics = get_rag_metrics()
                
                # Record document processing metrics (pipeline timing)
                metrics.record_document_processing(
                    latency_ms=pipeline_duration * 1000,
                    num_chunks=len(nodes)
                )
                logger.info(f"Recorded document processing metrics: {pipeline_duration * 1000:.2f}ms, {len(nodes)} chunks")
                
                # Record vector indexing metrics
                if self.vector_store and vector_time > 0:
                    metrics.record_vector_indexing(
                        latency_ms=vector_time * 1000,
                        num_vectors=len(nodes)
                    )
                    logger.info(f"Recorded vector indexing metrics: {vector_time * 1000:.2f}ms, {len(nodes)} vectors")
                
                logger.info(f"All metrics recorded successfully - Pipeline: {pipeline_duration:.2f}s, Vector: {vector_time:.2f}s, Graph: {graph_time:.2f}s")
                
                # Force flush metrics to ensure they're exported immediately
                try:
                    from opentelemetry import metrics as otel_metrics
                    meter_provider = otel_metrics.get_meter_provider()
                    if hasattr(meter_provider, 'force_flush'):
                        meter_provider.force_flush(timeout_millis=5000)
                        logger.debug("Forced metrics flush to OTEL collector")
                except Exception as flush_error:
                    logger.debug(f"Could not force flush metrics: {flush_error}")
                    
            except Exception as e:
                logger.warning(f"Failed to record ingestion metrics: {e}")
        
        # Notify completion via status callback - this will trigger the UI completion status
        if status_callback:
            # Generate proper completion message based on enabled features
            # Check if we have file_count stored (for sources that create chunks)
            from backend import PROCESSING_STATUS
            data_source = PROCESSING_STATUS.get(processing_id, {}).get("data_source", "")
            file_count = PROCESSING_STATUS.get(processing_id, {}).get("file_count")
            chunk_count = PROCESSING_STATUS.get(processing_id, {}).get("chunk_count")
            
            # Debug logging
            logger.info(f"Completion message logic - data_source: '{data_source}', file_count: {file_count}, chunk_count: {chunk_count}, len(documents): {len(documents)}")
            
            # Determine document count for completion message
            if data_source == "youtube":
                # YouTube: always show "1 video"
                doc_count = 1
                logger.info(f"Using YouTube special case: doc_count = 1")
            elif file_count and chunk_count and file_count != chunk_count:
                # Sources that create chunks: show file count instead of chunk count
                doc_count = file_count
                logger.info(f"Using file_count from stored metadata: doc_count = {file_count}")
            else:
                # Legacy or 1:1 file-to-doc ratio: use document count
                doc_count = len(documents)
                logger.info(f"Using legacy document count: doc_count = {len(documents)}")
            
            completion_message = self._generate_completion_message(doc_count, skip_graph=skip_graph)
            status_callback(
                processing_id=processing_id,
                status="completed",
                message=completion_message,
                progress=100
            )
    
    
    async def ingest_text(self, content: str, source_name: str = "text_input", processing_id: str = None):
        """Ingest raw text content"""
        logger.info(f"Ingesting text content from: {source_name}")
        
        # Helper function to check cancellation
        def _check_cancellation():
            if processing_id:
                from backend import PROCESSING_STATUS
                return (processing_id in PROCESSING_STATUS and 
                        PROCESSING_STATUS[processing_id]["status"] == "cancelled")
            return False
        
        # Create document from text
        document = self.document_processor.process_text_content(content, source_name)
        
        # Store document for later use in search store indexing (accumulate rather than overwrite)
        if not hasattr(self, '_last_ingested_documents') or self._last_ingested_documents is None:
            self._last_ingested_documents = []
        self._last_ingested_documents.append(document)
        logger.info(f"Added text document to collection. Total documents: {len(self._last_ingested_documents)}")
        
        # Check for cancellation after document processing
        if _check_cancellation():
            logger.info("Processing cancelled during text document creation")
            raise RuntimeError("Processing cancelled by user")
        
        # Process similar to file ingestion but with single document
        pipeline = IngestionPipeline(
            transformations=[
                SentenceSplitter(
                    chunk_size=self.config.chunk_size,
                    chunk_overlap=self.config.chunk_overlap
                ),
                # Commented out for optimization - can be re-enabled for testing:
                # KeywordExtractor(keywords=5),
                # SummaryExtractor(summaries=["prev", "self", "next"]),
                self.embed_model
            ]
        )
        
        # Use run_in_executor to avoid asyncio conflict
        import asyncio
        import functools
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        run_pipeline = functools.partial(
            pipeline.run,
            documents=[document]
        )
        
        # Use run_in_executor with proper event loop handling to avoid nested async issues
        nodes = await loop.run_in_executor(None, run_pipeline)
        
        # Check for cancellation after node processing
        if _check_cancellation():
            logger.info("Processing cancelled during text node generation")
            raise RuntimeError("Processing cancelled by user")
        
        # Update or create indexes
        if self.vector_index is None:
            storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
            
            # Use run_in_executor to avoid asyncio conflict
            import asyncio
            import functools
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            # Use run_in_executor with proper nest_asyncio handling
            create_vector_index = functools.partial(
                VectorStoreIndex.from_documents,
                documents=[document],
                storage_context=storage_context,
                embed_model=self.embed_model
            )
            self.vector_index = await loop.run_in_executor(None, create_vector_index)
        else:
            # Add to existing index
            self.vector_index.insert_nodes(nodes)
        
        # Check for cancellation after vector index creation/update
        if _check_cancellation():
            logger.info("Processing cancelled during text vector index creation")
            raise RuntimeError("Processing cancelled by user")
        
        # Update graph index - always use knowledge graph extraction for graph functionality
        kg_extractors = []
        if self.config.schema_config is not None:
            kg_extractor = self.schema_manager.create_extractor(
                self.llm, 
                use_schema=True,
                llm_provider=self.config.llm_provider,
                extractor_type=self.config.kg_extractor_type
            )
            kg_extractors = [kg_extractor]
            logger.info("Using knowledge graph extraction with schema for text ingestion")
        else:
            # Use simple extractor if no schema provided
            kg_extractor = self.schema_manager.create_extractor(
                self.llm, 
                use_schema=False,
                llm_provider=self.config.llm_provider,
                extractor_type=self.config.kg_extractor_type
            )
            kg_extractors = [kg_extractor]
            logger.info("Using simple knowledge graph extraction for text ingestion")
        
        if self.graph_index is None:
            graph_storage_context = StorageContext.from_defaults(
                property_graph_store=self.graph_store
            )
            
            # Use asyncio.get_event_loop().run_in_executor to avoid event loop conflict
            import asyncio
            import functools
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            # Use run_in_executor with proper nest_asyncio handling
            create_graph_index = functools.partial(
                PropertyGraphIndex.from_documents,
                documents=[document],
                llm=self.llm,
                embed_model=self.embed_model,
                kg_extractors=kg_extractors,
                storage_context=graph_storage_context
            )
            self.graph_index = await loop.run_in_executor(None, create_graph_index)
        else:
            # Add to existing graph index
            self.graph_index.insert_nodes(nodes)
        
        # Check for cancellation after graph index creation/update
        if _check_cancellation():
            logger.info("Processing cancelled during text graph index creation")
            raise RuntimeError("Processing cancelled by user")
        
        # Setup hybrid retriever
        self._setup_hybrid_retriever()
        
        logger.info("Text content ingestion completed successfully!")
    
    def _setup_hybrid_retriever(self):
        """Setup hybrid retriever combining all search modalities"""
        logger.info(f"Setting up hybrid retriever - SEARCH_DB={self.config.search_db} (type: {type(self.config.search_db)})")
        
        # Check if we have at least one search modality enabled
        has_vector = self.vector_index is not None
        has_graph = self.config.enable_knowledge_graph and self.graph_index is not None
        has_search = self.config.search_db != SearchDBType.NONE  # Any search DB type except 'none'
        
        if not (has_vector or has_graph or has_search):
            logger.warning("Cannot setup hybrid retriever: no search modalities available")
            return
        
        # Vector retriever (optional)
        vector_retriever = None
        opensearch_hybrid_retriever = None
        if has_vector:
            # Configure vector retriever based on database type
            if self.config.vector_db == VectorDBType.OPENSEARCH:
                # Check if we should use OpenSearch native hybrid search
                if has_search and self.config.search_db == SearchDBType.OPENSEARCH:
                    # Use OpenSearch native hybrid search with required parameters
                    from llama_index.core.vector_stores.types import VectorStoreQueryMode
                    opensearch_hybrid_retriever = self.vector_index.as_retriever(
                        similarity_top_k=10,
                        embed_model=self.embed_model,
                        vector_store_query_mode=VectorStoreQueryMode.HYBRID,
                        # Add required parameters for OpenSearch hybrid search
                        search_pipeline="hybrid-search-pipeline"  # Use hybrid search pipeline
                    )
                    logger.info("OpenSearch native hybrid retriever created (vector + fulltext) with required parameters")
                    # Skip individual vector retriever when using hybrid
                    vector_retriever = None
                else:
                    # OpenSearch vector-only mode
                    from llama_index.core.vector_stores.types import VectorStoreQueryMode
                    vector_retriever = self.vector_index.as_retriever(
                        similarity_top_k=10,
                        embed_model=self.embed_model,
                        vector_store_query_mode=VectorStoreQueryMode.DEFAULT  # Pure vector search
                    )
                    logger.info("OpenSearch vector retriever created with DEFAULT mode")
            else:
                # Other databases use standard retriever configuration
                vector_retriever = self.vector_index.as_retriever(
                    similarity_top_k=10,
                    embed_model=self.embed_model
                )
                logger.info(f"{self.config.vector_db} vector retriever created")
        else:
            logger.info("Vector search disabled - no vector retriever")
        
        # BM25 retriever for full-text search (only for builtin BM25, not OpenSearch)
        bm25_retriever = None
        logger.info(f"Checking BM25 condition: search_db={self.config.search_db}, SearchDBType.BM25={SearchDBType.BM25}")
        
        if self.config.search_db == SearchDBType.BM25:
            # Use native BM25 retriever for built-in BM25 (OpenSearch uses VectorStoreQueryMode.TEXT_SEARCH instead)
            bm25_config = {
                "similarity_top_k": self.config.bm25_similarity_top_k,
                "persist_dir": self.config.bm25_persist_dir
            }
            
            # Get docstore - either from vector index or create standalone for BM25-only
            docstore = None
            if self.vector_index and self.vector_index.docstore.docs:
                # Use existing vector index docstore
                docstore = self.vector_index.docstore
                logger.info(f"Creating BM25 retriever with {len(docstore.docs)} documents from vector index")
            elif hasattr(self, '_last_ingested_documents') and self._last_ingested_documents:
                # Create standalone docstore for BM25-only scenarios
                from llama_index.core.storage.docstore import SimpleDocumentStore
                docstore = SimpleDocumentStore()
                # Add all documents at once to avoid overwriting
                docstore.add_documents(self._last_ingested_documents)
                logger.info(f"Created standalone docstore with {len(self._last_ingested_documents)} documents for BM25")
                logger.info(f"Docstore now contains {len(docstore.docs)} documents")
                
                # Debug: Log document IDs and content preview
                for doc_id, doc in docstore.docs.items():
                    content_preview = doc.text[:100] + "..." if len(doc.text) > 100 else doc.text
                    logger.info(f"Doc {doc_id}: {content_preview}")
                    logger.info(f"Doc {doc_id} metadata: {doc.metadata}")
            elif hasattr(self, '_last_ingested_documents'):
                logger.warning(f"_last_ingested_documents exists but is empty: {self._last_ingested_documents}")
            else:
                logger.warning("_last_ingested_documents attribute not found - documents not stored during ingestion")
                
            if docstore:
                bm25_retriever = DatabaseFactory.create_bm25_retriever(
                    docstore=docstore,
                    config=bm25_config
                )
                logger.info(f"Built-in BM25 retriever created successfully with {len(docstore.docs)} documents")
            else:
                logger.error("No docstore available - BM25 retriever creation failed")
        else:
            logger.info(f"No BM25 retriever needed for search_db={self.config.search_db}")
        
        # Graph retriever - configure to return original text from shared docstore (if enabled)
        graph_retriever = None
        if self.config.enable_knowledge_graph and self.graph_index:
            graph_retriever = self.graph_index.as_retriever(
                include_text=True,
                similarity_top_k=5,
                # Return original document text from the shared docstore, not knowledge graph extraction results
                text_qa_template=None,  # Use default template
                include_metadata=True
            )
        
        # Create search retriever if configured (Elasticsearch or OpenSearch fulltext-only mode)
        search_retriever = None
        if self.search_store is not None and opensearch_hybrid_retriever is None:
            try:
                # Create search index using the same documents from ingestion
                from llama_index.core import VectorStoreIndex, StorageContext
                
                # Use the documents from the last ingestion (stored during ingestion)
                if hasattr(self, '_last_ingested_documents') and self._last_ingested_documents:
                    documents = self._last_ingested_documents
                    search_storage_context = StorageContext.from_defaults(vector_store=self.search_store)
                    search_index = VectorStoreIndex.from_documents(
                        documents,
                        storage_context=search_storage_context,
                        embed_model=self.embed_model
                    )
                    # Configure retriever based on search database type
                    if self.config.search_db == SearchDBType.OPENSEARCH:
                        # OpenSearch uses query modes for different search types
                        from llama_index.core.vector_stores.types import VectorStoreQueryMode
                        search_retriever = search_index.as_retriever(
                            similarity_top_k=10,
                            vector_store_query_mode=VectorStoreQueryMode.TEXT_SEARCH  # BM25 equivalent
                        )
                        logger.info(f"Created OpenSearch retriever with TEXT_SEARCH mode for BM25 fulltext search")
                    else:
                        # Elasticsearch uses strategy-based approach
                        search_retriever = search_index.as_retriever(similarity_top_k=10)
                        logger.info(f"Created {self.config.search_db} retriever with BM25 scoring for full-text search")
                # Fallback: try to get documents from vector index docstore  
                elif self.vector_index and self.vector_index.docstore.docs:
                    documents = list(self.vector_index.docstore.docs.values())
                    search_storage_context = StorageContext.from_defaults(vector_store=self.search_store)
                    search_index = VectorStoreIndex.from_documents(
                        documents,
                        storage_context=search_storage_context,
                        embed_model=self.embed_model
                    )
                    # Configure retriever based on search database type
                    if self.config.search_db == SearchDBType.OPENSEARCH:
                        # OpenSearch uses query modes for different search types
                        from llama_index.core.vector_stores.types import VectorStoreQueryMode
                        search_retriever = search_index.as_retriever(
                            similarity_top_k=10,
                            vector_store_query_mode=VectorStoreQueryMode.TEXT_SEARCH  # BM25 equivalent
                        )
                        logger.info(f"Created OpenSearch retriever with TEXT_SEARCH mode for BM25 fulltext search (from docstore)")
                    else:
                        # Elasticsearch uses strategy-based approach
                        search_retriever = search_index.as_retriever(similarity_top_k=10)
                        logger.info(f"Created {self.config.search_db} retriever with BM25 scoring (from docstore)")
                else:
                    logger.warning(f"No documents available for {self.config.search_db} indexing")
            except Exception as e:
                logger.warning(f"Failed to create {self.config.search_db} retriever: {str(e)} - continuing without it")
                search_retriever = None
        
        # Combine retrievers with fusion
        retrievers = []
        
        # Add OpenSearch hybrid retriever if available (combines vector + fulltext)
        if opensearch_hybrid_retriever is not None:
            retrievers.append(opensearch_hybrid_retriever)
            logger.info("Added OpenSearch hybrid retriever (vector + fulltext) to fusion")
        # Add vector retriever if available
        elif vector_retriever is not None:
            retrievers.append(vector_retriever)
            logger.info("Added vector retriever to fusion")
        else:
            logger.info("Vector retriever not available")
        
        # Add text search retriever if available  
        if bm25_retriever is not None:
            retrievers.append(bm25_retriever)
            logger.info("Added BM25 retriever to fusion")
        elif search_retriever is not None:
            retrievers.append(search_retriever)
            logger.info(f"Added {self.config.search_db} retriever to fusion")
        else:
            logger.info("No text search retriever available")
        
        # Add graph retriever if available
        if graph_retriever is not None:
            retrievers.append(graph_retriever)
            logger.info("Added graph retriever to fusion")
        else:
            logger.info("Graph retriever not available")
        
        # Build descriptive log message
        retriever_types = []
        if opensearch_hybrid_retriever is not None:
            retriever_types.append("OpenSearch-hybrid")
        elif vector_retriever is not None:
            retriever_types.append("vector")
        if bm25_retriever is not None:
            retriever_types.append("BM25")
        elif search_retriever is not None:
            retriever_types.append(str(self.config.search_db))
        if graph_retriever is not None:
            retriever_types.append("graph")
        
        if not retrievers:
            error_msg = (
                "No retrievers available for fusion! This usually means all search modalities are disabled. "
                f"Current config: VECTOR_DB={self.config.vector_db}, "
                f"GRAPH_DB={self.config.graph_db}, SEARCH_DB={self.config.search_db}. "
                "At least one must be enabled (not 'none')."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Fusion retriever created with {', '.join(retriever_types)} retrievers")
        
        # If only one retriever, use it directly for better relevance filtering
        if len(retrievers) == 1:
            self.hybrid_retriever = retrievers[0]
            logger.info(f"Using single {retriever_types[0]} retriever directly (no fusion needed)")
        else:
            # Use QueryFusionRetriever for multiple retrievers (async should work fine now)
            self.hybrid_retriever = QueryFusionRetriever(
                retrievers=retrievers,
                mode="reciprocal_rerank",
                similarity_top_k=15,
                num_queries=1,
                use_async=True  # Enable async - dual retriever conflicts are resolved
            )
            logger.info(f"Using QueryFusionRetriever for multiple retrievers (async enabled)")
        
        logger.info("Hybrid retriever setup completed")
    
    def _persist_indexes(self):
        """Persist indexes to disk if configured"""
        
        # Persist vector index if persist directory is configured
        if hasattr(self.config, 'vector_persist_dir') and self.config.vector_persist_dir:
            logger.info(f"Persisting vector index to: {self.config.vector_persist_dir}")
            self.vector_index.storage_context.persist(persist_dir=self.config.vector_persist_dir)
        
        # Persist graph index if persist directory is configured
        if hasattr(self.config, 'graph_persist_dir') and self.config.graph_persist_dir:
            logger.info(f"Persisting graph index to: {self.config.graph_persist_dir}")
            self.graph_index.storage_context.persist(persist_dir=self.config.graph_persist_dir)
        
        # BM25 persistence is handled automatically by the BM25Retriever
        # when it uses the persisted docstore from the vector index
        
        logger.info("Index persistence completed")
    
    def _clear_partial_state(self):
        """Clear partial system state when inconsistencies are detected"""
        logger.info("Clearing partial system state")
        self.vector_index = None
        self.graph_index = None
        self.hybrid_retriever = None
        logger.info("System state cleared - requires re-ingestion")
    
    async def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Execute hybrid search across all modalities"""
        from datetime import datetime
        
        # Check for complete system initialization
        if not self.hybrid_retriever:
            raise ValueError("System not initialized. Please ingest documents first.")
        
        logger.info(f"Searching for query: '{query}' with top_k={top_k}")
        logger.info(f"Available documents: {len(self._last_ingested_documents) if hasattr(self, '_last_ingested_documents') else 0}")
        
        # Get raw results from retriever using async method
        retrieval_start = datetime.now()
        logger.info(f"Starting hybrid retrieval at {retrieval_start.strftime('%H:%M:%S.%f')[:-3]}")
        
        query_bundle = QueryBundle(query_str=query)
        
        # Use async method directly - nest_asyncio.apply() already called in backend.py/main.py
        raw_results = await self.hybrid_retriever.aretrieve(query_bundle)
        
        retrieval_end = datetime.now()
        retrieval_duration = (retrieval_end - retrieval_start).total_seconds()
        logger.info(f"Hybrid retrieval completed in {retrieval_duration:.3f}s")
        
        # Filter out zero-relevance results with more aggressive threshold
        # BM25 should not return docs with zero relevance, but some systems return very low scores
        # Use a minimum threshold to filter out essentially irrelevant results
        min_score_threshold = 0.001  # Filter anything below 0.001 (effectively zero)
        filtered_results = [result for result in raw_results if result.score > min_score_threshold]
        logger.info(f"Raw results: {len(raw_results)}, Filtered results (score > {min_score_threshold}): {len(filtered_results)}")
        
        # Log scores for debugging
        for i, result in enumerate(raw_results):
            # Clean text preview to avoid emoji/encoding issues
            clean_preview = result.text[:50].encode('ascii', 'ignore').decode('ascii')
            logger.info(f"Result {i}: score={result.score:.3f}, text_preview={clean_preview}...")
            
        # Use filtered results for final processing
        results = filtered_results[:top_k]
        
        # Check for partial initialization state - only require indexes that should be enabled
        missing_required = False
        
        # Check vector index only if vector search is enabled
        if str(self.config.vector_db) != "none" and not self.vector_index:
            missing_required = True
            logger.warning(f"Vector DB {self.config.vector_db} enabled but vector_index is missing")
        
        # Check graph index only if graph search is enabled AND knowledge graph extraction is enabled
        # AND graph was not intentionally skipped (via per-ingest skip_graph flag)
        if (str(self.config.graph_db) != "none" and 
            self.config.enable_knowledge_graph and 
            not self.graph_index and
            not self.graph_intentionally_skipped):
            missing_required = True
            logger.warning(f"Graph DB {self.config.graph_db} enabled but graph_index is missing")
        
        if missing_required:
            logger.warning("System in partial state - missing required indexes, clearing and requiring re-ingestion")
            self._clear_partial_state()
            raise ValueError("System not initialized. Please ingest documents first.")
        
        # Results already retrieved and filtered above
        # No need for additional async call
        
        logger.info(f"Retrieved {len(results)} results from hybrid search")
        
        # Enhanced deduplication with multiple strategies
        seen_content = set()
        seen_sources = {}  # source -> content mapping for additional dedup
        deduplicated_results = []
        
        for result in results:
            source = result.metadata.get("source", "Unknown")
            full_text = result.text.strip()
            
            # Strategy 1: Extract core content by removing common prefixes
            core_content = self._extract_core_content(full_text)
            
            # Strategy 2: Create content hash from core content
            content_hash = core_content[:300].strip().lower()
            
            # Strategy 3: Check for exact source + core content combination
            content_key = f"{source}::{content_hash}"
            
            # Strategy 4: Check for very similar content from same source
            similar_found = False
            if source in seen_sources:
                for existing_content in seen_sources[source]:
                    # Check if content is very similar (overlap > 70%)
                    if len(content_hash) > 50 and len(existing_content) > 50:
                        overlap = len(set(content_hash.split()) & set(existing_content.split()))
                        total_words = len(set(content_hash.split()) | set(existing_content.split()))
                        if total_words > 0 and overlap / total_words > 0.7:
                            similar_found = True
                            break
            
            # Strategy 5: Check for entity-relationship patterns that might be duplicates
            if not similar_found and "->" in full_text:
                # This might be a graph result with entity-relationship format
                # Check if we already have the original text version
                for existing_result in deduplicated_results:
                    existing_text = existing_result.text.strip()
                    existing_core = self._extract_core_content(existing_text)
                    
                    # If existing result doesn't have entity-relationship format but has similar core content
                    if "->" not in existing_text and len(existing_core) > 50:
                        overlap = len(set(core_content.split()) & set(existing_core.split()))
                        total_words = len(set(core_content.split()) | set(existing_core.split()))
                        if total_words > 0 and overlap / total_words > 0.6:
                            similar_found = True
                            break
            
            if content_key not in seen_content and not similar_found:
                seen_content.add(content_key)
                if source not in seen_sources:
                    seen_sources[source] = []
                seen_sources[source].append(content_hash)
                deduplicated_results.append(result)
                clean_content = core_content[:100].encode('ascii', 'ignore').decode('ascii')
                logger.debug(f"Added result from {source}: {clean_content}...")
            else:
                clean_content = core_content[:100].encode('ascii', 'ignore').decode('ascii')
                logger.debug(f"Deduplicated result from {source}: {clean_content}...")
        
        # Format and rank results
        formatted_results = []
        for i, result in enumerate(deduplicated_results[:top_k]):
            formatted_results.append({
                "rank": i + 1,
                "content": result.text,
                "score": getattr(result, 'score', 0.0),
                "source": result.metadata.get("source", "Unknown"),
                "file_type": result.metadata.get("file_type", "Unknown"),
                "file_name": result.metadata.get("file_name", "Unknown")
            })
        
        logger.info(f"Deduplication summary: {len(results)} -> {len(deduplicated_results)} -> {len(formatted_results)} final results")
        
        # Record retrieval metrics for observability
        if self._observability_enabled:
            try:
                from observability.metrics import get_rag_metrics
                metrics = get_rag_metrics()
                retrieval_latency_ms = retrieval_duration * 1000
                top_score = formatted_results[0]["score"] if formatted_results else None
                metrics.record_retrieval(
                    latency_ms=retrieval_latency_ms,
                    num_documents=len(formatted_results),
                    top_score=top_score,
                    attributes={"query_length": len(query), "top_k": top_k}
                )
                logger.info(f"Recorded retrieval metrics: {retrieval_latency_ms:.2f}ms, {len(formatted_results)} docs")
            except Exception as e:
                logger.warning(f"Failed to record retrieval metrics: {e}")
        
        return formatted_results
    
    def _extract_core_content(self, text: str) -> str:
        """Extract core content by removing common prefixes and suffixes"""
        
        # Common prefixes to remove - expanded list for knowledge graph extraction results
        prefixes_to_remove = [
            "here are some facts extracted from the provided text:",
            "facts extracted from the provided text:",
            "extracted facts:",
            "key information:",
            "summary:",
            "important points:",
            "main points:",
            "key facts:",
            "extracted information:",
            "document summary:",
            "content summary:",
            "text summary:",
            "document facts:",
            "content facts:",
            "text facts:",
            "based on the provided text:",
            "from the provided text:",
            "the text contains:",
            "the document contains:",
            "the content includes:",
            "the information shows:",
            "the facts indicate:",
            "the data reveals:",
            "the analysis shows:",
            "the summary indicates:",
            "the key points are:",
            "the main findings are:",
            "the important details are:",
            "the relevant information is:",
            "the document states:",
            "the text states:",
            "the content states:",
            "the information states:",
            "the facts show:",
            "the data shows:",
            "the analysis reveals:",
            "the summary shows:",
            "the key points show:",
            "the main findings show:",
            "the important details show:",
            "the relevant information shows:",
            # Additional knowledge graph extraction prefixes
            "the following facts were extracted:",
            "extracted from the document:",
            "the document reveals:",
            "the text reveals:",
            "the content reveals:",
            "the information indicates:",
            "the facts demonstrate:",
            "the data indicates:",
            "the analysis indicates:",
            "the summary demonstrates:",
            "the key points indicate:",
            "the main findings indicate:",
            "the important details indicate:",
            "the relevant information indicates:",
            "the document demonstrates:",
            "the text demonstrates:",
            "the content demonstrates:",
            "the information demonstrates:",
            "the facts suggest:",
            "the data suggests:",
            "the analysis suggests:",
            "the summary suggests:",
            "the key points suggest:",
            "the main findings suggest:",
            "the important details suggest:",
            "the relevant information suggests:"
        ]
        
        # Convert to lowercase for comparison
        text_lower = text.lower().strip()
        
        # Remove prefixes
        for prefix in prefixes_to_remove:
            if text_lower.startswith(prefix.lower()):
                # Find the actual prefix in the original text (case-sensitive)
                prefix_start = text.lower().find(prefix.lower())
                if prefix_start != -1:
                    text = text[prefix_start + len(prefix):].strip()
                    break
        
        # Remove common suffixes
        suffixes_to_remove = [
            "end of document",
            "end of text",
            "document ends",
            "text ends",
            "this concludes the document",
            "this concludes the text",
            "this ends the document",
            "this ends the text"
        ]
        
        text_lower = text.lower().strip()
        for suffix in suffixes_to_remove:
            if text_lower.endswith(suffix.lower()):
                # Find the actual suffix in the original text (case-sensitive)
                suffix_start = text.lower().rfind(suffix.lower())
                if suffix_start != -1:
                    text = text[:suffix_start].strip()
                    break
        
        # Additional cleanup: remove entity-relationship patterns
        # Look for patterns like "Entity -> Relation -> Entity" and extract the original text
        import re
        
        # Pattern to find entity-relationship chains (more comprehensive)
        er_patterns = [
            r'^[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+:',
            r'^[A-Za-z\s]+->[A-Za-z\s]+:',
            r'^[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+:',
            r'^[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+->[A-Za-z\s]+:'
        ]
        
        for er_pattern in er_patterns:
            if re.match(er_pattern, text.strip()):
                # Try to find the original text after the entity-relationship chain
                # Look for common document start patterns
                original_patterns = [
                    r'LONDON.*?September.*?\d{4}.*?Alfresco',
                    r'[A-Z]{2,}.*?\d{1,2}.*?\d{4}.*?[A-Za-z]+',
                    r'[A-Z][a-z]+.*?\d{1,2},.*?\d{4}',
                    r'[A-Z][a-z]+.*?\d{1,2}.*?\d{4}',
                    r'[A-Z][a-z]+.*?\d{1,2}.*?\d{4}.*?[A-Za-z]+',
                    r'[A-Z]{2,}.*?\d{1,2}.*?\d{4}',
                    r'[A-Z][a-z]+.*?\d{1,2}.*?\d{4}.*?[A-Za-z]+.*?[A-Za-z]+'
                ]
                
                for pattern in original_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        # Extract from the match onwards
                        text = text[match.start():]
                        break
                break
        
        return text.strip()
    
    def get_query_engine(self, **kwargs):
        """Get query engine for Q&A"""
        
        # Check for complete system initialization
        if not self.hybrid_retriever:
            raise ValueError("System not initialized. Please ingest documents first.")
        
        # Check for partial initialization state - only require indexes that should be enabled
        missing_required = False
        
        # Check vector index only if vector search is enabled
        if str(self.config.vector_db) != "none" and not self.vector_index:
            missing_required = True
            logger.warning(f"Vector DB {self.config.vector_db} enabled but vector_index is missing")
        
        # Check graph index only if graph search is enabled AND knowledge graph extraction is enabled
        # AND graph was not intentionally skipped (via per-ingest skip_graph flag)
        if (str(self.config.graph_db) != "none" and 
            self.config.enable_knowledge_graph and 
            not self.graph_index and
            not self.graph_intentionally_skipped):
            missing_required = True
            logger.warning(f"Graph DB {self.config.graph_db} enabled but graph_index is missing")
        
        if missing_required:
            logger.warning("System in partial state - missing required indexes, clearing and requiring re-ingestion")
            self._clear_partial_state()
            raise ValueError("System not initialized. Please ingest documents first.")
        
        # Create query engine from the retriever
        from llama_index.core.query_engine import RetrieverQueryEngine
        
        try:
            return RetrieverQueryEngine.from_args(
                retriever=self.hybrid_retriever,
                llm=self.llm,
                **kwargs
            )
        except Exception as e:
            # Check if this is a Neo4j vector index error indicating partial state
            if "vector schema index" in str(e) or "There is no such vector schema index" in str(e):
                logger.warning(f"Detected missing vector indexes in Neo4j: {str(e)}")
                self._clear_partial_state()
                raise ValueError("System not initialized. Please ingest documents first.")
            else:
                # Re-raise other errors
                raise
    
    
    
    
    async def _process_documents_direct(self, documents: List, processing_id: str = None, status_callback=None, skip_graph: bool = False):
        """Process documents directly without file paths (for web, YouTube, Wikipedia sources)
        
        Args:
            skip_graph: If True, skip knowledge graph extraction for this ingest (temporary override)
        """
        logger.info(f"Processing {len(documents)} documents directly...")
        
        # Start timing for performance analysis
        import time
        start_time = time.time()
        
        # Store documents for later use in search store indexing
        if not hasattr(self, '_last_ingested_documents') or self._last_ingested_documents is None:
            self._last_ingested_documents = []
        self._last_ingested_documents.extend(documents)
        logger.info(f"Added {len(documents)} documents to collection. Total documents: {len(self._last_ingested_documents)}")
        
        # Helper function to check cancellation
        def _check_cancellation():
            if processing_id:
                from backend import PROCESSING_STATUS
                return (processing_id in PROCESSING_STATUS and 
                        PROCESSING_STATUS[processing_id]["status"] == "cancelled")
            return False
        
        # Check for cancellation before processing
        if _check_cancellation():
            logger.info("Processing cancelled during document preparation")
            raise RuntimeError("Processing cancelled by user")
        
        # Step 1: Process documents through transformations to get nodes
        pipeline_start_time = time.time()
        transformations = [
            SentenceSplitter(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap
            ),
            self.embed_model
        ]
        
        logger.info(f"Starting LlamaIndex IngestionPipeline with transformations: {[type(t).__name__ for t in transformations]}")
        
        pipeline = IngestionPipeline(transformations=transformations)
        
        # Use run_in_executor to avoid asyncio conflict
        import asyncio
        import functools
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        run_pipeline = functools.partial(pipeline.run, documents=documents)
        logger.info("Executing IngestionPipeline.run() - this includes chunking and embedding generation")
        nodes = await loop.run_in_executor(None, run_pipeline)
        
        pipeline_duration = time.time() - pipeline_start_time
        logger.info(f"IngestionPipeline completed in {pipeline_duration:.2f}s - Generated {len(nodes)} nodes from {len(documents)} documents")
        
        # Check for cancellation after node processing
        if _check_cancellation():
            logger.info("Processing cancelled during node generation")
            raise RuntimeError("Processing cancelled by user")
        
        # Step 2: Create or update vector index (if vector search enabled)
        vector_duration = 0
        if self.vector_store is not None:
            vector_start_time = time.time()
            vector_store_type = type(self.vector_store).__name__
            logger.info(f"Creating vector index from {len(nodes)} nodes using {vector_store_type}...")
            
            if self.vector_index is None:
                storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
                
                create_vector_index = functools.partial(
                    VectorStoreIndex.from_documents,
                    documents=documents,
                    storage_context=storage_context,
                    embed_model=self.embed_model
                )
                self.vector_index = await loop.run_in_executor(None, create_vector_index)
            else:
                # Add to existing index
                self.vector_index.insert_nodes(nodes)
            
            vector_duration = time.time() - vector_start_time
            logger.info(f"Vector index creation completed in {vector_duration:.2f}s using {vector_store_type}")
        else:
            logger.info("Vector search disabled - skipping vector index creation")
        
        # Check for cancellation after vector index creation/update
        if _check_cancellation():
            logger.info("Processing cancelled during vector index creation")
            raise RuntimeError("Processing cancelled by user")
        
        # Step 3: Create or update graph index (if knowledge graph extraction is enabled)
        # Check both global config AND per-ingest skip_graph flag
        should_skip_graph = skip_graph or not self.config.enable_knowledge_graph
        graph_creation_duration = 0
        
        if should_skip_graph:
            if skip_graph and self.config.enable_knowledge_graph:
                logger.info("Knowledge graph extraction SKIPPED - per-ingest skip_graph flag is True (temporary override)")
                # Track that graph was intentionally skipped for this ingestion
                self.graph_intentionally_skipped = True
                # Preserve existing graph_index if it exists (from previous ingestions)
                if self.graph_index:
                    logger.info("Preserving existing graph index from previous ingestion(s)")
            elif not self.config.enable_knowledge_graph:
                logger.info("Knowledge graph extraction disabled - skipping graph index creation")
                # Graph disabled in config - clear any existing graph since it shouldn't be used
                self.graph_index = None
                self.graph_intentionally_skipped = False
        else:
            # Knowledge graph is enabled and not skipped - proceed with extraction
            # Clear the skip flag since we're creating a graph now
            self.graph_intentionally_skipped = False
            kg_setup_start_time = time.time()
            graph_store_type = type(self.graph_store).__name__
            llm_model_name = getattr(self.llm, 'model', str(type(self.llm).__name__))
            
            kg_extractors = []
            if self.config.schema_config is not None:
                kg_extractor = self.schema_manager.create_extractor(
                    self.llm, 
                    use_schema=True,
                    llm_provider=self.config.llm_provider,
                    extractor_type=self.config.kg_extractor_type
                )
                kg_extractors = [kg_extractor]
                logger.info(f"Using knowledge graph extraction with schema and LLM: {llm_model_name}")
            else:
                kg_extractor = self.schema_manager.create_extractor(
                    self.llm, 
                    use_schema=False,
                    llm_provider=self.config.llm_provider,
                    extractor_type=self.config.kg_extractor_type
                )
                kg_extractors = [kg_extractor]
                logger.info(f"Using simple knowledge graph extraction (no schema) with LLM: {llm_model_name}")
            
            kg_setup_duration = time.time() - kg_setup_start_time
            logger.info(f"Knowledge graph extractor setup completed in {kg_setup_duration:.2f}s")
            
            if self.graph_index is None:
                graph_storage_context = StorageContext.from_defaults(
                    property_graph_store=self.graph_store
                )
                
                # This is the most time-consuming step - LLM calls for entity/relationship extraction
                graph_creation_start_time = time.time()
                logger.info(f"Starting PropertyGraphIndex.from_documents() - this will make LLM calls to extract entities and relationships from {len(documents)} documents")
                logger.info(f"LLM model being used for knowledge graph extraction: {llm_model_name}")
                
                # Create tracer span for graph extraction if observability is enabled
                if OBSERVABILITY_AVAILABLE:
                    tracer = get_tracer(__name__)
                    graph_span = tracer.start_span("rag.graph_extraction.create")
                    graph_span.set_attribute("graph.num_documents", len(documents))
                    graph_span.set_attribute("graph.llm_model", llm_model_name)
                    graph_span.set_attribute("graph.database_type", graph_store_type)
                    graph_span.set_attribute("graph.extractor_type", self.config.kg_extractor_type)
                else:
                    graph_span = None
                
                try:
                    # METHOD 1: Track counts during extraction by manually running extractors
                    # This follows LlamaIndex best practice for accurate entity/relation counting
                    
                    # First, convert documents to nodes (this is what PropertyGraphIndex does internally)
                    from llama_index.core.node_parser import SimpleNodeParser
                    node_parser = SimpleNodeParser.from_defaults()
                    
                    logger.info(f"Converting {len(documents)} documents to nodes for extraction...")
                    nodes = node_parser.get_nodes_from_documents(documents)
                    logger.info(f"Created {len(nodes)} nodes from documents")
                    
                    # Run extractors on nodes manually to capture metadata
                    logger.info(f"Running {len(kg_extractors)} extractor(s) on nodes to extract entities and relationships...")
                    
                    # CRITICAL: For Gemini/Vertex, run extractors directly (not in executor)
                    # Reason: Gemini SDK is async and needs to use the MAIN event loop
                    # Running in executor causes Gemini to create event loops in worker threads,
                    # then during search, Futures from those threads cause "attached to different loop" errors
                    logger.info(f"PATH 2: LLM Provider check: {self.config.llm_provider}")
                    logger.info(f"PATH 2: Is Gemini? {self.config.llm_provider in [LLMProvider.GEMINI, LLMProvider.VERTEX_AI]}")
                    
                    if self.config.llm_provider in [LLMProvider.GEMINI, LLMProvider.VERTEX_AI]:
                        logger.info("PATH 2: GEMINI BRANCH - Running extractors in main async context (NOT using executor)")
                        for i, extractor in enumerate(kg_extractors):
                            logger.info(f"PATH 2: Running extractor {i+1}/{len(kg_extractors)} directly (no executor)")
                            # Run directly - let Gemini use main event loop
                            nodes = extractor(nodes, show_progress=True)
                            logger.info(f"PATH 2: Extractor {i+1} completed")
                    else:
                        logger.info("PATH 2: NON-GEMINI BRANCH - Running extractors in executor")
                        # For other LLMs (OpenAI, Ollama, etc.), use executor as before
                        for i, extractor in enumerate(kg_extractors):
                            logger.info(f"PATH 2: Running extractor {i+1}/{len(kg_extractors)} in executor")
                            extract_func = functools.partial(extractor, nodes, show_progress=True)
                            nodes = await loop.run_in_executor(None, extract_func)
                            logger.info(f"PATH 2: Extractor {i+1} completed")
                    
                    # Count entities and relations from node metadata (before insertion)
                    num_entities, num_relations = count_extracted_entities_and_relations(nodes)
                    logger.info(f"Extraction complete: {num_entities} entities, {num_relations} relationships extracted from node metadata")
                    
                    # Prepare kwargs for PropertyGraphIndex using already-extracted nodes
                    # Method 1: Pass nodes (not documents) with empty extractors (already extracted!)
                    graph_kwargs = {
                        "nodes": nodes,  # Use pre-extracted nodes, not documents
                        "llm": self.llm,
                        "embed_model": self.embed_model,
                        "kg_extractors": [],  # Empty - extraction already done above!
                        "property_graph_store": self.graph_store,  # Pass store directly
                        "storage_context": graph_storage_context
                    }
                    
                    # CRITICAL: Neptune Analytics has non-atomic vector index limitations
                    # Disable vector embeddings for knowledge graph nodes to avoid vector operation conflicts
                    if hasattr(self.graph_store, '__class__') and 'NeptuneAnalytics' in str(self.graph_store.__class__):
                        graph_kwargs["embed_kg_nodes"] = False
                        logger.info("Neptune Analytics detected: Setting embed_kg_nodes=False to avoid vector index atomicity issues")
                        logger.info("Knowledge graph structure will be created without vector embeddings (use separate VECTOR_DB for embeddings)")
                    
                    # CRITICAL: For Gemini/Vertex, create PropertyGraphIndex directly (not in executor)
                    # Even though we pass empty kg_extractors, PropertyGraphIndex still does internal
                    # async operations that need the main event loop
                    if self.config.llm_provider in [LLMProvider.GEMINI, LLMProvider.VERTEX_AI]:
                        logger.info("PATH 2: Creating PropertyGraphIndex directly in main context (not executor)")
                        # Run synchronously in main context - PropertyGraphIndex.__init__ is not async
                        # but it internally uses asyncio.run() which needs to be in main loop
                        self.graph_index = PropertyGraphIndex(**graph_kwargs)
                        logger.info("PATH 2: PropertyGraphIndex creation completed")
                    else:
                        # For other LLMs, use executor as before
                        logger.info("PATH 2: Creating PropertyGraphIndex in executor")
                        create_graph_index = functools.partial(PropertyGraphIndex, **graph_kwargs)
                        self.graph_index = await loop.run_in_executor(None, create_graph_index)
                        logger.info("PATH 2: PropertyGraphIndex creation completed")
                    
                    graph_creation_duration = time.time() - graph_creation_start_time
                    logger.info(f"PropertyGraphIndex creation completed in {graph_creation_duration:.2f}s")
                    logger.info(f"Knowledge graph extraction finished - {num_entities} entities and {num_relations} relationships stored in {graph_store_type}")
                    
                    # Record metrics if available
                    if graph_span:
                        graph_span.set_attribute("graph.extraction_latency_ms", graph_creation_duration * 1000)
                        graph_span.set_attribute("graph.num_entities", num_entities)
                        graph_span.set_attribute("graph.num_relations", num_relations)
                        graph_span.set_attribute("graph.status", "success")
                    
                    # Record custom metrics for Grafana dashboard
                    if OBSERVABILITY_AVAILABLE and get_rag_metrics:
                        try:
                            metrics = get_rag_metrics()
                            # Record graph extraction with entity/relation counts
                            metrics.record_graph_extraction(
                                latency_ms=graph_creation_duration * 1000,
                                num_entities=num_entities,
                                num_relations=num_relations
                            )
                            logger.info(f"[PATH 2] Recorded graph extraction metrics: {graph_creation_duration * 1000:.2f}ms, {num_entities} entities, {num_relations} relations")
                        except Exception as e:
                            logger.warning(f"Failed to record graph metrics: {e}")
                        
                except Exception as e:
                    graph_creation_duration = time.time() - graph_creation_start_time
                    if graph_span:
                        graph_span.set_attribute("graph.status", "error")
                        graph_span.set_attribute("graph.error", str(e))
                        graph_span.record_exception(e)
                    raise
                finally:
                    if graph_span:
                        graph_span.end()
            else:
                # Add to existing graph index
                graph_update_start_time = time.time()
                logger.info(f"Adding {len(nodes)} nodes to existing graph index...")
                
                # Create tracer span for graph update if observability is enabled
                if OBSERVABILITY_AVAILABLE:
                    tracer = get_tracer(__name__)
                    graph_span = tracer.start_span("rag.graph_extraction.update")
                    graph_span.set_attribute("graph.num_nodes", len(nodes))
                    graph_span.set_attribute("graph.database_type", graph_store_type)
                else:
                    graph_span = None
                
                try:
                    # PATH 3: Run extractors manually on nodes to populate metadata with entities/relations
                    # This is necessary because IngestionPipeline doesn't include KG extractors
                    logger.info(f"Running {len(kg_extractors)} extractor(s) on {len(nodes)} nodes to extract entities and relationships...")
                    
                    # Get event loop for async compatibility
                    import asyncio
                    import functools
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    # CRITICAL: For Gemini/Vertex, run extractors directly (not in executor)
                    # Reason: Gemini SDK is async and needs to use the MAIN event loop
                    # Running in executor causes Gemini to create event loops in worker threads,
                    # then during search, Futures from those threads cause "attached to different loop" errors
                    logger.info(f"PATH 3: LLM Provider check: {self.config.llm_provider}")
                    logger.info(f"PATH 3: Is Gemini? {self.config.llm_provider in [LLMProvider.GEMINI, LLMProvider.VERTEX_AI]}")
                    
                    if self.config.llm_provider in [LLMProvider.GEMINI, LLMProvider.VERTEX_AI]:
                        logger.info("PATH 3: GEMINI BRANCH - Running extractors in main async context (NOT using executor)")
                        for i, extractor in enumerate(kg_extractors):
                            logger.info(f"PATH 3: Running extractor {i+1}/{len(kg_extractors)} directly (no executor)")
                            # Run directly - let Gemini use main event loop
                            nodes = extractor(nodes, show_progress=True)
                            logger.info(f"PATH 3: Extractor {i+1} completed")
                    else:
                        logger.info("PATH 3: NON-GEMINI BRANCH - Running extractors in executor")
                        # For other LLMs (OpenAI, Ollama, etc.), use executor as before
                        for i, extractor in enumerate(kg_extractors):
                            logger.info(f"PATH 3: Running extractor {i+1}/{len(kg_extractors)} in executor")
                            extract_func = functools.partial(extractor, nodes, show_progress=True)
                            nodes = await loop.run_in_executor(None, extract_func)
                            logger.info(f"PATH 3: Extractor {i+1} completed")
                    
                    # Count entities/relations from node metadata (after extraction, before insertion)
                    num_entities, num_relations = count_extracted_entities_and_relations(nodes)
                    logger.info(f"Extraction complete: {num_entities} entities, {num_relations} relationships extracted from node metadata")
                    logger.info(f"Inserting nodes with {num_entities} entities and {num_relations} relationships...")
                    
                    # Note: insert_nodes is synchronous but may trigger async operations internally
                    # For Gemini, this should work since we're in main async context and extractors already ran
                    logger.info(f"PATH 3: Calling graph_index.insert_nodes() with {len(nodes)} nodes")
                    self.graph_index.insert_nodes(nodes)
                    logger.info(f"PATH 3: graph_index.insert_nodes() completed")
                    graph_creation_duration = time.time() - graph_update_start_time
                    logger.info(f"Graph index update completed in {graph_creation_duration:.2f}s")
                    logger.info(f"Knowledge graph updated - {num_entities} new entities and {num_relations} new relationships added to {graph_store_type}")
                    
                    if graph_span:
                        graph_span.set_attribute("graph.update_latency_ms", graph_creation_duration * 1000)
                        graph_span.set_attribute("graph.num_entities", num_entities)
                        graph_span.set_attribute("graph.num_relations", num_relations)
                        graph_span.set_attribute("graph.status", "success")
                    
                    # Record custom metrics for Grafana dashboard
                    if OBSERVABILITY_AVAILABLE and get_rag_metrics:
                        try:
                            metrics = get_rag_metrics()
                            # Record graph extraction with entity/relation counts
                            metrics.record_graph_extraction(
                                latency_ms=graph_creation_duration * 1000,
                                num_entities=num_entities,
                                num_relations=num_relations
                            )
                            logger.info(f"[PATH 3 - UPDATE] Recorded graph extraction metrics: {graph_creation_duration * 1000:.2f}ms, {num_entities} entities, {num_relations} relations")
                        except Exception as e:
                            logger.warning(f"Failed to record graph metrics: {e}")
                        
                except Exception as e:
                    graph_creation_duration = time.time() - graph_update_start_time
                    if graph_span:
                        graph_span.set_attribute("graph.status", "error")
                        graph_span.set_attribute("graph.error", str(e))
                        graph_span.record_exception(e)
                    raise
                finally:
                    if graph_span:
                        graph_span.end()
        
        # Check for cancellation after graph index creation/update
        if _check_cancellation():
            logger.info("Processing cancelled during graph index creation")
            raise RuntimeError("Processing cancelled by user")
        
        # Setup hybrid retriever
        self._setup_hybrid_retriever()
        
        # Calculate total duration and log performance summary
        total_duration = time.time() - start_time
        
        # Use the graph_creation_duration variable that was initialized at function level
        graph_time = graph_creation_duration
        
        logger.info(f"Direct document processing completed successfully in {total_duration:.2f}s total!")
        logger.info(f"Performance summary - Pipeline: {pipeline_duration:.2f}s, Vector: {vector_duration:.2f}s, Graph: {graph_time:.2f}s")
        
        # Record metrics for document processing, vector indexing (graph already recorded in its own section)
        if OBSERVABILITY_AVAILABLE and get_rag_metrics:
            try:
                metrics = get_rag_metrics()
                
                # Record document processing metrics (pipeline time)
                if pipeline_duration > 0:
                    metrics.record_document_processing(
                        latency_ms=pipeline_duration * 1000,
                        num_chunks=len(nodes)
                    )
                    logger.info(f"Recorded document processing metrics: {pipeline_duration * 1000:.2f}ms, {len(nodes)} chunks")
                
                # Record vector indexing metrics
                if vector_duration > 0:
                    metrics.record_vector_indexing(
                        latency_ms=vector_duration * 1000,
                        num_vectors=len(nodes)
                    )
                    logger.info(f"Recorded vector indexing metrics: {vector_duration * 1000:.2f}ms, {len(nodes)} vectors")
                
                # Force flush metrics to ensure they're exported immediately
                try:
                    from opentelemetry import metrics as otel_metrics
                    meter_provider = otel_metrics.get_meter_provider()
                    if hasattr(meter_provider, 'force_flush'):
                        meter_provider.force_flush(timeout_millis=5000)
                        logger.debug("Forced metrics flush to OTEL collector")
                except Exception as flush_error:
                    logger.debug(f"Could not force flush metrics: {flush_error}")
                    
            except Exception as e:
                logger.warning(f"Failed to record processing metrics: {e}")
        
        # Notify completion via status callback - this will trigger the UI completion status
        if status_callback:
            # Generate proper completion message based on enabled features
            # Check if we have file_count stored (for sources that create chunks)
            from backend import PROCESSING_STATUS
            data_source = PROCESSING_STATUS.get(processing_id, {}).get("data_source", "")
            file_count = PROCESSING_STATUS.get(processing_id, {}).get("file_count")
            chunk_count = PROCESSING_STATUS.get(processing_id, {}).get("chunk_count")
            
            # Debug logging
            logger.info(f"Completion message logic (_process_documents_direct) - data_source: '{data_source}', file_count: {file_count}, chunk_count: {chunk_count}, len(documents): {len(documents)}")
            
            # Determine document count for completion message
            if data_source == "youtube":
                # YouTube: always show "1 video"
                doc_count = 1
                logger.info(f"Using YouTube special case: doc_count = 1")
            elif file_count and chunk_count and file_count != chunk_count:
                # Sources that create chunks: show file count instead of chunk count
                doc_count = file_count
                logger.info(f"Using file_count from stored metadata: doc_count = {file_count}")
            else:
                # Legacy or 1:1 file-to-doc ratio: use document count
                doc_count = len(documents)
                logger.info(f"Using legacy document count: doc_count = {len(documents)}")
            
            completion_message = self._generate_completion_message(doc_count, skip_graph=skip_graph)
            status_callback(
                processing_id=processing_id,
                status="completed",
                message=completion_message,
                progress=100
            )


    def _generate_completion_message(self, doc_count: int, skip_graph: bool = False) -> str:
        """Generate dynamic completion message based on enabled features
        
        Args:
            doc_count: Number of documents ingested
            skip_graph: If True, graph was skipped for this ingest
        """
        # Check what's actually enabled
        has_vector = str(self.config.vector_db) != "none"
        # Graph is only "has" if config enabled AND not skipped for this ingest
        has_graph = str(self.config.graph_db) != "none" and self.config.enable_knowledge_graph and not skip_graph
        has_search = str(self.config.search_db) != "none"
        
        # Build feature list in logical order: vector, search, knowledge graph
        features = []
        if has_vector:
            vector_type = str(self.config.vector_db).title()
            features.append(f"{vector_type} vector index")
        if has_search:
            if self.config.search_db == "bm25":
                features.append("BM25 search")
            else:
                search_type = str(self.config.search_db).title()
                features.append(f"{search_type} search")
        if has_graph:
            graph_type = str(self.config.graph_db).title()
            features.append(f"{graph_type} knowledge graph")
        
        # Create appropriate message with proper grammar
        if features:
            if len(features) == 1:
                feature_text = features[0]
            elif len(features) == 2:
                feature_text = f"{features[0]} and {features[1]}"
            else:
                feature_text = f"{', '.join(features[:-1])}, and {features[-1]}"
            return f"Successfully ingested {doc_count} document(s)! {feature_text} ready."
        else:
            # Fallback (shouldn't happen due to validation)
            return f"Successfully ingested {doc_count} document(s)!"

    def state(self) -> Dict[str, Any]:
        """Get current system state"""
        return {
            "has_vector_index": self.vector_index is not None,
            "has_graph_index": self.graph_index is not None,
            "has_hybrid_retriever": self.hybrid_retriever is not None,
            "config": {
                "data_source": self.config.data_source,
                "vector_db": self.config.vector_db,
                "graph_db": self.config.graph_db,
                "llm_provider": self.config.llm_provider
            }
        }