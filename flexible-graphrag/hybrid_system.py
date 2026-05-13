"""
HybridSearchSystem — Facade

This module is the single public entry point for the search system.
All heavy implementation lives in the component modules:

  process/       — document processing, chunking, KG extraction
  stores/        — database setup, index initialisation, persistence, RDF
  ingest/        — ingest_from_files, ingest_from_text, ingest_from_source
  retriever_setup — fusion retriever assembly
  query_engine   — search() and get_query_engine()
  schema_manager — KG extractor schema management

The facade stores shared state (stores, indexes, retriever) as instance
attributes and passes itself to the component functions.
"""

from llama_index.core import Settings
from llama_index.core.schema import BaseNode
from typing import List, Dict, Any, Union
from pathlib import Path
import logging

from config import Settings as AppSettings, LLMProvider
from schema_manager import SchemaManager
from factories import LLMFactory
from process.document_processor import DocumentProcessor
from stores.index_manager import setup_databases, initialize_indexes, persist_indexes
from process.kg_extractor import count_extracted_entities_and_relations
from ingest.ingest_from_files import (
    ingest_documents as _ingest_documents,
    generate_completion_message,
)
from ingest.ingest_from_text import ingest_text as _ingest_text
from ingest.ingest_from_source import ingest_source_documents as _ingest_source_documents
from retriever_setup import setup_hybrid_retriever
from query_engine import search as _search, get_query_engine as _get_query_engine

logger = logging.getLogger(__name__)


class HybridSearchSystem:
    """Configurable hybrid search system with full-text, vector, and graph search."""

    def __init__(self, config: AppSettings):
        self.config = config

        # Log mixed LLM + embedding config
        embedding_kind = getattr(config, 'embedding_kind', None)
        if embedding_kind in ['google', 'vertex'] and config.llm_provider not in [LLMProvider.GEMINI, LLMProvider.VERTEX_AI]:
            logger.info(f"Using {config.llm_provider} LLM with {embedding_kind} embeddings")

        # DocumentProcessor (Docling / LlamaParse)
        if hasattr(config, 'document_parser'):
            parser_type = config.document_parser.value if hasattr(config.document_parser, 'value') else str(config.document_parser)
        else:
            parser_type = "docling"
        self.document_processor = DocumentProcessor(config, parser_type=parser_type)

        # Schema logging
        active_schema = config.get_active_schema()
        if active_schema:
            entities = active_schema.get('entities', [])
            relations = active_schema.get('relations', [])
            try:
                entity_count = len(entities) if hasattr(entities, '__len__') and not hasattr(entities, '__args__') else len(getattr(entities, '__args__', []))
                relation_count = len(relations) if hasattr(relations, '__len__') and not hasattr(relations, '__args__') else len(getattr(relations, '__args__', []))
                logger.info(f"Schema: '{config.schema_name}' with {entity_count} entity types and {relation_count} relation types")
            except (TypeError, AttributeError):
                logger.info(f"Schema: '{config.schema_name}'")
        else:
            logger.info(f"Schema: '{config.schema_name}' (no custom schema — extractor defaults or ontology apply)")

        self.schema_manager = SchemaManager(active_schema, config)

        # LLM + embedding model
        logger.info(f"=== LLM CONFIGURATION ===")
        provider_name = getattr(config.llm_provider, 'value', config.llm_provider)
        logger.info(f"LLM Provider: {provider_name}")
        self.llm = LLMFactory.create_llm(config.llm_provider, config.llm_config)
        self.embed_model = LLMFactory.create_embedding_model(config.llm_provider, config.llm_config, settings=config)

        if hasattr(self.llm, 'model'): logger.info(f"LLM Model: {self.llm.model}")
        if hasattr(self.llm, 'base_url'): logger.info(f"LLM Base URL: {self.llm.base_url}")
        if hasattr(self.llm, 'request_timeout'): logger.info(f"LLM Timeout: {self.llm.request_timeout}s")
        if hasattr(self.llm, 'temperature'): logger.info(f"LLM Temperature: {self.llm.temperature}")
        if hasattr(self.embed_model, 'model_name'): logger.info(f"Embedding Model: {self.embed_model.model_name}")
        elif hasattr(self.embed_model, '_model_name'): logger.info(f"Embedding Model: {self.embed_model._model_name}")
        if hasattr(self.embed_model, 'base_url'): logger.info(f"Embedding Base URL: {self.embed_model.base_url}")

        logger.info(f"=== DATABASE CONFIGURATION ===")
        graph_db_name  = getattr(config.pg_graph_db,  'value', config.pg_graph_db)  if config.pg_graph_db  else 'none'
        rdf_db_name    = getattr(config.rdf_graph_db, 'value', config.rdf_graph_db) if hasattr(config, 'rdf_graph_db') and config.rdf_graph_db else 'none'
        vector_db_name = getattr(config.vector_db,    'value', config.vector_db)    if config.vector_db    else 'none'
        search_db_name = getattr(config.search_db,    'value', config.search_db)    if config.search_db    else 'none'
        logger.info(f"Property Graph DB: {graph_db_name}")
        logger.info(f"RDF Graph DB: {rdf_db_name}")
        logger.info(f"Vector DB: {vector_db_name}")
        logger.info(f"Search DB: {search_db_name}")
        logger.info(f"KG Extraction / Store: {config.enable_knowledge_graph}")

        _pg_str  = str(graph_db_name).lower()
        _rdf_str = str(rdf_db_name).lower()
        _vec_str = str(vector_db_name).lower()
        _src_str = str(search_db_name).lower()

        def _fw(db_str, backend_attr, lc_label, li_label="LlamaIndex"):
            if db_str in ("none", ""):
                return "none"
            return lc_label if (getattr(config, backend_attr, "llamaindex") or "llamaindex").lower() == "langchain" else li_label

        # Property Graph Store framework is always LlamaIndex or LangChain regardless of db choice
        _pg_fw  = "LangChain" if (getattr(config, "graph_backend", "llamaindex") or "llamaindex").lower() == "langchain" else "LlamaIndex"
        _vec_fw = _fw(_vec_str, "vector_backend", "LangChain")
        _src_fw = _fw(_src_str, "search_backend", "LangChain")
        _kg_ext = (getattr(config, "kg_extractor_backend", "llamaindex") or "llamaindex").strip().lower()
        _kg_fw  = "LangChain" if _kg_ext == "langchain" else "LlamaIndex"
        _fusion_setting = (getattr(config, "retrieval_fusion", "llamaindex") or "llamaindex").strip().lower()
        _fusion_fw = "LangChain (EnsembleRetriever, RRF)" if _fusion_setting == "langchain" else "LlamaIndex (QueryFusionRetriever)"

        _chunker_backend = (getattr(config, "chunker_backend", "llamaindex") or "llamaindex").strip().lower()
        _chunker_fw = "LangChain" if _chunker_backend == "langchain" else "LlamaIndex"

        logger.info(f"=== FRAMEWORK CONFIGURATION ===")
        logger.info(f"Property Graph Store: {_pg_fw}")
        logger.info(f"RDF Graph Store: LangChain / RDFLib")
        logger.info(f"Vector Store: {_vec_fw}")
        logger.info(f"Search Store: {_src_fw}")
        logger.info(f"Doc Chunking / Splitting Pipeline: {_chunker_fw}")
        logger.info(f"KG Extraction: {_kg_fw}")
        logger.info(f"Retrieval Fusion: {_fusion_fw}")

        # Global LlamaIndex settings
        Settings.llm = self.llm
        Settings.embed_model = self.embed_model
        Settings.chunk_size = config.chunk_size

        # Database connections and indexes
        self.vector_store, self.graph_store, self.search_store = setup_databases(config)
        self.vector_index, self.graph_index, self.search_index = initialize_indexes(
            config, self.vector_store, self.graph_store, self.search_store, self.llm, self.embed_model
        )

        # Unified adapter layer (wraps the raw stores created above)
        self._init_adapters(config)

        # Runtime state
        self.hybrid_retriever = None
        self.graph_intentionally_skipped = False
        self._last_ingested_documents: list = []
        self._observability_enabled = getattr(config, 'enable_observability', False)

        if self._observability_enabled:
            try:
                from observability.metrics import get_rag_metrics
                metrics = get_rag_metrics()
                metrics.errors_total.add(0, {})
                logger.info("Initialized observability metrics (error counter at 0)")
            except Exception as e:
                logger.warning(f"Failed to initialize observability metrics: {e}")

        logger.info("=== SYSTEM READY ===")
        if config.llm_provider == LLMProvider.OLLAMA:
            logger.info("HybridSearchSystem initialized successfully with Ollama!")
        else:
            logger.info("HybridSearchSystem initialized successfully")

    @classmethod
    def from_settings(cls, settings: AppSettings):
        """Create HybridSearchSystem from Settings object."""
        return cls(settings)

    def _init_adapters(self, config: AppSettings) -> None:
        """Initialise the unified adapter layer (wraps raw stores in adapter objects)."""
        from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter
        from llamaindex.search.search_store_factory import LlamaIndexSearchAdapter
        from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter
        from adapters.graph.pg_store_adapter import build_pg_store_adapter, LC_ONLY_PG_STORES, LI_ONLY_PG_STORES
        from adapters.graph.rdf_store_adapter import build_rdf_store_adapter

        self.vector_adapter = LlamaIndexVectorAdapter(self.vector_store)
        self.search_adapter = LlamaIndexSearchAdapter(self.search_store)
        self.rdf_adapter = build_rdf_store_adapter(config)

        # Build property graph adapter: LangChain for langchain backend / LC-only stores,
        # LlamaIndex for everything else (including disabled graph_store=None).
        graph_backend_str = (getattr(config, "graph_backend", "llamaindex") or "llamaindex").lower()
        db_type_str = str(getattr(config, "pg_graph_db", "none") or "none").lower()
        is_lc_backend = (
            (graph_backend_str == "langchain" or db_type_str in LC_ONLY_PG_STORES)
            and db_type_str not in LI_ONLY_PG_STORES
        )

        if db_type_str != "none" and is_lc_backend:

            self.pg_adapter = build_pg_store_adapter(
                db_type_str=db_type_str,
                config=config.graph_db_config or {},
                schema_config=config.get_active_schema(),
                has_separate_vector_store=(self.vector_store is not None),
                llm_provider=config.llm_provider,
                llm_config=config.llm_config,
                app_config=config,
                graph_backend="langchain",
            )
            logger.info(
                "LangChain property graph adapter ready (store=%s, backend=langchain)",
                db_type_str,
            )
        else:
            self.pg_adapter = LlamaIndexPGAdapter(self.graph_store)

        if self.rdf_adapter:
            logger.info(f"RDF adapter initialized: {self.rdf_adapter.store_type}")
        else:
            logger.debug("No RDF adapter (rdf_graph_db=none)")



    # -----------------------------------------------------------------------
    # Ingestion
    # -----------------------------------------------------------------------

    async def ingest_documents(self, file_paths: List[Union[str, Path]], processing_id: str = None, status_callback=None, skip_graph: bool = False):
        """Process and ingest documents from file paths into all search modalities."""
        return await _ingest_documents(self, file_paths, processing_id=processing_id, status_callback=status_callback, skip_graph=skip_graph)

    async def ingest_text(self, content: str, source_name: str = "text_input", processing_id: str = None, skip_graph: bool = False):
        """Ingest raw text content."""
        return await _ingest_text(self, content, source_name=source_name, processing_id=processing_id, skip_graph=skip_graph)

    async def _ingest_source_documents(self, documents: List, processing_id: str = None, status_callback=None, skip_graph: bool = False, config_id: str = None):
        """Process documents directly (web/YouTube/Wikipedia/incremental updates)."""
        return await _ingest_source_documents(self, documents, processing_id=processing_id, status_callback=status_callback, skip_graph=skip_graph, config_id=config_id)

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------

    async def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Execute hybrid search across all configured modalities."""
        return await _search(self, query, top_k=top_k)

    def get_query_engine(self, **kwargs):
        """Build and return a RetrieverQueryEngine for Q&A."""
        return _get_query_engine(self, **kwargs)

    # -----------------------------------------------------------------------
    # Retriever / state management
    # -----------------------------------------------------------------------

    def _setup_hybrid_retriever(self):
        """Assemble hybrid_retriever from all configured search modalities."""
        setup_hybrid_retriever(self)

    def _persist_indexes(self):
        """Persist indexes to disk if configured."""
        persist_indexes(self.config, self.vector_index, self.graph_index)

    def _clear_partial_state(self):
        """Clear partial system state when inconsistencies are detected."""
        logger.info("Clearing partial system state")
        self.vector_index = None
        self.graph_index = None
        self.hybrid_retriever = None
        logger.info("System state cleared - requires re-ingestion")

    # -----------------------------------------------------------------------
    # RDF helpers (delegated to stores.index_manager)
    # -----------------------------------------------------------------------

    def _export_nodes_to_rdf_stores(self, nodes: List) -> None:
        """Push extracted KG nodes/relations to all enabled RDF stores."""
        from stores.rdf_manager import export_nodes_to_rdf_stores
        export_nodes_to_rdf_stores(nodes, self.config, schema_manager=self.schema_manager)

    def _delete_from_rdf_stores(self, ref_doc_id: str) -> None:
        """Delete all triples for ref_doc_id from every configured RDF store."""
        from stores.rdf_manager import delete_from_rdf_stores
        delete_from_rdf_stores(ref_doc_id, self.config)

    # -----------------------------------------------------------------------
    # KG extraction helper (kept for incremental engine compatibility)
    # -----------------------------------------------------------------------

    async def _run_kg_extractors_on_nodes(self, nodes: List, kg_extractors: List):
        """Run KG extractors on nodes. Returns (nodes, num_entities, num_relations)."""
        from process.kg_extractor import run_kg_extractors_on_nodes
        extracted_nodes, num_entities, num_relations, _ = await run_kg_extractors_on_nodes(
            nodes, kg_extractors, self.config
        )
        return extracted_nodes, num_entities, num_relations

    def _generate_completion_message(self, doc_count: int, skip_graph: bool = False) -> str:
        """Generate dynamic completion message based on enabled features."""
        return generate_completion_message(self.config, doc_count, skip_graph=skip_graph)

    # -----------------------------------------------------------------------
    # State property
    # -----------------------------------------------------------------------

    def state(self) -> Dict[str, Any]:
        """Get current system state."""
        return {
            "has_vector_index": self.vector_index is not None,
            "has_graph_index": self.graph_index is not None,
            "has_hybrid_retriever": self.hybrid_retriever is not None,
            "config": {
                "data_source": self.config.data_source,
                "vector_db": self.config.vector_db,
                "pg_graph_db": self.config.pg_graph_db,
                "llm_provider": self.config.llm_provider,
            },
        }
