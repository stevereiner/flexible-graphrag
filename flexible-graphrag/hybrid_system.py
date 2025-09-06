from llama_index.core import VectorStoreIndex, PropertyGraphIndex, StorageContext, Settings, QueryBundle
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.extractors import KeywordExtractor, SummaryExtractor
from llama_index.core.indices.property_graph import SchemaLLMPathExtractor, SimpleLLMPathExtractor, DynamicLLMPathExtractor
from typing import List, Dict, Any, Union
from pathlib import Path
import logging
import asyncio

from config import Settings as AppSettings, SAMPLE_SCHEMA, SearchDBType, VectorDBType, LLMProvider
from document_processor import DocumentProcessor
from factories import LLMFactory, DatabaseFactory
from sources import FileSystemSource, CmisSource, AlfrescoSource

logger = logging.getLogger(__name__)

class SchemaManager:
    """Manages schema definitions for entity and relationship extraction"""
    
    def __init__(self, schema_config: Dict[str, Any] = None):
        self.schema_config = schema_config or {}
    
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
        
        # Handle dynamic extractor type
        if extractor_type == "dynamic":
            logger.info("Using DynamicLLMPathExtractor for flexible relationship discovery")
            # DynamicLLMPathExtractor can work with or without initial schema guidance
            if self.schema_config:
                logger.info("Providing initial ontology guidance to DynamicLLMPathExtractor")
                # With initial ontology - provide starting guidance but allow expansion
                return DynamicLLMPathExtractor(
                    llm=llm,
                    max_triplets_per_chunk=20,
                    num_workers=workers,
                    allowed_entity_types=self.schema_config.get("entities", []),
                    allowed_relation_types=self.schema_config.get("relations", [])
                )
            else:
                logger.info("Using DynamicLLMPathExtractor without initial ontology - full LLM freedom")
                # Without initial ontology - complete freedom to infer schema
                return DynamicLLMPathExtractor(
                    llm=llm,
                    max_triplets_per_chunk=20,
                    num_workers=workers
                )
        
        # Use schema if explicitly requested
        if not use_schema:
            return SimpleLLMPathExtractor(
                llm=llm,
                max_paths_per_chunk=10,
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
            return SimpleLLMPathExtractor(
                llm=llm,
                max_paths_per_chunk=10,
                num_workers=workers
            )
        
        # Create schema-guided extractor
        return SchemaLLMPathExtractor(
            llm=llm,
            possible_entities=schema_to_use.get("entities", []),
            possible_relations=schema_to_use.get("relations", []),
            kg_validation_schema=schema_to_use.get("validation_schema"),
            strict=schema_to_use.get("strict", True),
            num_workers=workers
        )

class HybridSearchSystem:
    """Configurable hybrid search system with full-text, vector, and graph search"""
    
    def __init__(self, config: AppSettings):
        self.config = config
        self.document_processor = DocumentProcessor(config)
        
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
        
        self.schema_manager = SchemaManager(active_schema)
        
        # Initialize LLM and embedding models with enhanced logging
        logger.info(f"=== LLM CONFIGURATION ===")
        # Handle both enum and string values safely
        provider_name = getattr(config.llm_provider, 'value', config.llm_provider)
        logger.info(f"LLM Provider: {provider_name}")
        
        self.llm = LLMFactory.create_llm(config.llm_provider, config.llm_config)
        self.embed_model = LLMFactory.create_embedding_model(config.llm_provider, config.llm_config)
        
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
        
        logger.info("=== SYSTEM READY ===")
        logger.info("HybridSearchSystem initialized successfully with Ollama!" if config.llm_provider == LLMProvider.OLLAMA else "HybridSearchSystem initialized successfully")
    
    def _setup_databases(self):
        """Initialize database connections based on configuration"""
        
        # Vector database
        self.vector_store = DatabaseFactory.create_vector_store(
            self.config.vector_db, 
            self.config.vector_db_config or {},
            self.config.llm_provider,
            self.config.llm_config
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
                self.config.llm_config
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
    
    async def ingest_documents(self, file_paths: List[Union[str, Path]], processing_id: str = None, status_callback=None):
        """Process and ingest documents into all search modalities"""
        
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
        if self.config.enable_knowledge_graph:
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
        else:
            logger.info("Knowledge graph extraction disabled - skipping graph index creation")
            _update_progress("Skipping knowledge graph extraction...", 70, current_phase="kg_extraction")
            kg_extractors = []
        
        # Only create graph index if knowledge graph is enabled
        if self.config.enable_knowledge_graph:
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
            
            # If using Kuzu with separate vector store, provide explicit vector store
            if str(self.config.graph_db) == "kuzu" and hasattr(self, 'vector_store') and self.vector_store:
                graph_index_kwargs["vector_store"] = self.vector_store
                logger.info("Using explicit vector store for Kuzu PropertyGraphIndex")
            

            # This is the most time-consuming step - LLM calls for entity/relationship extraction
            graph_creation_start_time = time.time()
            logger.info(f"Starting PropertyGraphIndex.from_documents() - this will make LLM calls to extract entities and relationships from {len(documents)} documents")
            logger.info(f"LLM model being used for knowledge graph extraction: {llm_model_name}")
            logger.info(f"Graph database target: {graph_store_type}")
            
            # Initialize schema right before PropertyGraphIndex creation for optimal timing
            if str(self.config.graph_db) == "kuzu":
                try:
                    logger.info("Initializing Kuzu schema right before PropertyGraphIndex creation")
                    self.graph_store.init_schema()
                    logger.info("Kuzu schema initialized successfully")
                    
                    # Inspect schema after initialization
                    schema = self.graph_store.get_schema()
                    # logger.info(f"Schema after initialization: {schema}")  # Commented out - verbose schema dump
                    
                except Exception as e:
                    logger.warning(f"Schema initialization failed: {e} - LlamaIndex will create tables as needed during extraction")
            
            # Use run_in_executor with proper nest_asyncio handling
            create_graph_index = functools.partial(PropertyGraphIndex.from_documents, **graph_index_kwargs)
            self.graph_index = await loop.run_in_executor(None, create_graph_index)
            
            graph_creation_duration = time.time() - graph_creation_start_time
            logger.info(f"PropertyGraphIndex creation completed in {graph_creation_duration:.2f}s")
            logger.info(f"Knowledge graph extraction finished - entities and relationships stored in {graph_store_type}")
            
            # Check for cancellation after graph index creation
            if _check_cancellation():
                logger.info("Processing cancelled during graph index creation")
                raise RuntimeError("Processing cancelled by user")
        else:
            # Skip graph index creation
            self.graph_index = None
            logger.info("Graph index creation skipped - knowledge graph disabled")
        
        # Step 4: Setup hybrid retriever
        self._setup_hybrid_retriever()
        
        # Step 5: Persist indexes if configured
        self._persist_indexes()
        
        total_duration = time.time() - start_time
        vector_time = vector_duration if self.vector_store and 'vector_duration' in locals() else 0
        graph_time = graph_creation_duration if self.config.enable_knowledge_graph and 'graph_creation_duration' in locals() else 0
        
        logger.info(f"Document ingestion completed successfully in {total_duration:.2f}s total!")
        logger.info(f"Performance summary - Pipeline: {pipeline_duration:.2f}s, Vector: {vector_time:.2f}s, Graph: {graph_time:.2f}s")
        
        # Notify completion via status callback - this will trigger the UI completion status
        if status_callback:
            status_callback(
                processing_id=processing_id,
                status="completed",
                message="Document ingestion completed successfully!",
                progress=100
            )
    
    async def ingest_cmis(self, cmis_config: dict = None, processing_id: str = None, status_callback=None):
        """Ingest documents from CMIS source"""
        logger.info("Starting CMIS document ingestion...")
        
        # Use provided config or fall back to global config
        if cmis_config:
            config = cmis_config
        else:
            import os
            config = {
                "url": os.getenv("CMIS_URL", "http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom"),
                "username": os.getenv("CMIS_USERNAME", "admin"),
                "password": os.getenv("CMIS_PASSWORD", "admin"),
                "folder_path": os.getenv("CMIS_FOLDER_PATH", "/")
            }
        
        # Initialize CMIS source
        cmis_source = CmisSource(
            url=config["url"],
            username=config["username"],
            password=config["password"],
            folder_path=config["folder_path"]
        )
        
        # Update status: Connected, now scanning
        if status_callback:
            status_callback(
                processing_id=processing_id,
                status="processing",
                message="Connected to CMIS! Scanning for documents...",
                progress=45
            )
        
        # Get documents from CMIS
        cmis_docs = cmis_source.list_files()
        
        if not cmis_docs:
            logger.warning("No supported documents found in CMIS repository")
            if status_callback:
                status_callback(
                    processing_id=processing_id,
                    status="completed",
                    message="No supported documents found in CMIS repository",
                    progress=100
                )
            return
        
        # Update status with document count
        if status_callback:
            status_callback(
                processing_id=processing_id,
                status="processing",
                message=f"Found {len(cmis_docs)} document(s) in CMIS repository",
                progress=50,
                total_files=len(cmis_docs),
                files_completed=0
            )
        
        # Create temporary directory for downloaded files
        import tempfile
        import os
        
        temp_dir = tempfile.mkdtemp(prefix="cmis_ingestion_")
        temp_files = []
        
        try:
            # Download all documents to temporary files
            for i, doc in enumerate(cmis_docs):
                try:
                    # Update progress during download
                    if status_callback:
                        download_progress = 50 + int((i / len(cmis_docs)) * 20)  # 50-70% for downloads
                        status_callback(
                            processing_id=processing_id,
                            status="processing",
                            message=f"Downloading document {i+1}/{len(cmis_docs)}: {doc['name']}",
                            progress=download_progress,
                            current_file=doc['name'],
                            current_phase="downloading",
                            files_completed=i,
                            total_files=len(cmis_docs)
                        )
                    
                    temp_file_path = cmis_source.download_document(doc, temp_dir)
                    temp_files.append(temp_file_path)
                    logger.info(f"Downloaded CMIS document: {doc['name']} -> {temp_file_path}")
                except Exception as e:
                    logger.error(f"Failed to download CMIS document {doc['name']}: {str(e)}")
                    continue
            
            if temp_files:
                # Update status: Starting document processing
                if status_callback:
                    status_callback(
                        processing_id=processing_id,
                        status="processing",
                        message=f"Processing {len(temp_files)} downloaded document(s)...",
                        progress=70,
                        total_files=len(temp_files),
                        files_completed=0
                    )
                
                # Process the downloaded files
                await self.ingest_documents(temp_files, processing_id=processing_id, status_callback=status_callback)
                logger.info(f"Successfully ingested {len(temp_files)} documents from CMIS")
            else:
                logger.warning("No documents were successfully downloaded from CMIS")
                if status_callback:
                    status_callback(
                        processing_id=processing_id,
                        status="completed",
                        message="No documents were successfully downloaded from CMIS",
                        progress=100
                    )
                
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                        logger.debug(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file {temp_file}: {str(e)}")
            
            # Remove temporary directory
            try:
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                    logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
    
    async def ingest_alfresco(self, alfresco_config: dict = None, processing_id: str = None, status_callback=None):
        """Ingest documents from Alfresco source"""
        logger.info("Starting Alfresco document ingestion...")
        
        # Use provided config or fall back to global config
        if alfresco_config:
            config = alfresco_config
        else:
            import os
            config = {
                "url": os.getenv("ALFRESCO_URL", "http://localhost:8080/alfresco"),
                "username": os.getenv("ALFRESCO_USERNAME", "admin"),
                "password": os.getenv("ALFRESCO_PASSWORD", "admin"),
                "path": os.getenv("ALFRESCO_PATH", "/")
            }
        
        # Initialize Alfresco source
        alfresco_source = AlfrescoSource(
            base_url=config["url"],
            username=config["username"],
            password=config["password"],
            path=config["path"]
        )
        
        # Update status: Connected, now scanning
        if status_callback:
            status_callback(
                processing_id=processing_id,
                status="processing",
                message="Connected to Alfresco! Scanning for documents...",
                progress=45
            )
        
        # Get documents from Alfresco
        alfresco_docs = alfresco_source.list_files()
        
        if not alfresco_docs:
            logger.warning("No supported documents found in Alfresco repository")
            if status_callback:
                status_callback(
                    processing_id=processing_id,
                    status="completed",
                    message="No supported documents found in Alfresco repository",
                    progress=100
                )
            return
        
        # Update status with document count
        if status_callback:
            status_callback(
                processing_id=processing_id,
                status="processing",
                message=f"Found {len(alfresco_docs)} document(s) in Alfresco repository",
                progress=50,
                total_files=len(alfresco_docs),
                files_completed=0
            )
        
        # Create temporary directory for downloaded files
        import tempfile
        import os
        
        temp_dir = tempfile.mkdtemp(prefix="alfresco_ingestion_")
        temp_files = []
        
        try:
            # Download all documents to temporary files
            for i, doc in enumerate(alfresco_docs):
                try:
                    # Update progress during download
                    if status_callback:
                        download_progress = 50 + int((i / len(alfresco_docs)) * 20)  # 50-70% for downloads
                        status_callback(
                            processing_id=processing_id,
                            status="processing",
                            message=f"Downloading document {i+1}/{len(alfresco_docs)}: {doc['name']}",
                            progress=download_progress,
                            current_file=doc['name'],
                            current_phase="downloading",
                            files_completed=i,
                            total_files=len(alfresco_docs)
                        )
                    
                    temp_file_path = alfresco_source.download_document(doc, temp_dir)
                    temp_files.append(temp_file_path)
                    logger.info(f"Downloaded Alfresco document: {doc['name']} -> {temp_file_path}")
                except Exception as e:
                    logger.error(f"Failed to download Alfresco document {doc['name']}: {str(e)}")
                    continue
            
            if temp_files:
                # Update status: Starting document processing
                if status_callback:
                    status_callback(
                        processing_id=processing_id,
                        status="processing",
                        message=f"Processing {len(temp_files)} downloaded document(s)...",
                        progress=70,
                        total_files=len(temp_files),
                        files_completed=0
                    )
                
                # Process the downloaded files
                await self.ingest_documents(temp_files, processing_id=processing_id, status_callback=status_callback)
                logger.info(f"Successfully ingested {len(temp_files)} documents from Alfresco")
            else:
                logger.warning("No documents were successfully downloaded from Alfresco")
                if status_callback:
                    status_callback(
                        processing_id=processing_id,
                        status="completed",
                        message="No documents were successfully downloaded from Alfresco",
                        progress=100
                    )
                
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                        logger.debug(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file {temp_file}: {str(e)}")
            
            # Remove temporary directory
            try:
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                    logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
    
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
        if (str(self.config.graph_db) != "none" and 
            self.config.enable_knowledge_graph and 
            not self.graph_index):
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
        if (str(self.config.graph_db) != "none" and 
            self.config.enable_knowledge_graph and 
            not self.graph_index):
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