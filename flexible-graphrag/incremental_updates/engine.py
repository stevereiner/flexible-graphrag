"""
Incremental Update Engine

Updates vector, search, and graph indexes using LlamaIndex abstractions.
Integrates with existing hybrid_system.py for document processing.
"""

import asyncio
import functools
import logging
import os
import time
from typing import Optional, List, Dict
from pathlib import Path

from llama_index.core import Document
from llama_index.core import VectorStoreIndex, PropertyGraphIndex

from .detectors import ChangeEvent, ChangeType, FileMetadata
from .state_manager import StateManager, DocumentState
from process.document_processor import DocumentProcessor
from config import Settings as AppSettings

logger = logging.getLogger("flexible_graphrag.incremental.engine")


class IncrementalUpdateEngine:
    """
    Applies document changes to LlamaIndex indexes.
    Uses proper LlamaIndex abstractions instead of direct database calls.
    """
    
    def __init__(
        self,
        vector_index: Optional[VectorStoreIndex],
        graph_index: Optional[PropertyGraphIndex],
        search_index: Optional[VectorStoreIndex],  # For BM25/hybrid
        doc_processor: DocumentProcessor,
        state_manager: StateManager,
        app_config: AppSettings,
        hybrid_system = None,  # Optional: HybridSearchSystem for reusing ingestion logic
        config_manager = None  # Optional: ConfigManager for accessing datasource configs
    ):
        self.vector_index = vector_index
        self.graph_index = graph_index
        self.search_index = search_index
        self.doc_processor = doc_processor
        self.state_manager = state_manager
        self.config = app_config
        self.hybrid_system = hybrid_system  # Store for use in _insert_to_all_indexes
        self.config_manager = config_manager  # Store for accessing datasource configs
    
    def _delete_from_all_indexes(self, doc_id: str):
        """
        Delete document from all indexes (vector, search, graph).
        
        If hybrid_system is available, uses its indexes directly.
        This ensures we use the latest index references.
        
        Args:
            doc_id: The document ID to delete
        """
        # Get indexes - use hybrid_system's indexes if available
        vector_index = self.hybrid_system.vector_index if self.hybrid_system else self.vector_index
        search_index = self.hybrid_system.search_index if self.hybrid_system else self.search_index
        graph_index = self.hybrid_system.graph_index if self.hybrid_system else self.graph_index
        
        # Delete from Vector Index
        if vector_index is not None:
            try:
                vector_index.delete_ref_doc(ref_doc_id=doc_id, delete_from_docstore=True)
                logger.info(f"  Deleted from vector index")
            except Exception as e:
                if 'not found' in str(e).lower():
                    logger.debug(f"  Document not in vector index")
                else:
                    logger.warning(f"  Vector index delete error: {e}")
        
        # Delete from Search Index (only if separate from vector)
        if search_index is not None and search_index is not vector_index:
            try:
                search_index.delete_ref_doc(ref_doc_id=doc_id, delete_from_docstore=True)
                logger.info(f"  Deleted from search index")
            except Exception as e:
                error_str = str(e).lower()
                if 'not found' in error_str or 'version conflict' in error_str:
                    logger.debug(f"  Document not in search index or already deleted")
                else:
                    logger.warning(f"  Search index delete error: {e}")
        
        # Delete from Graph Index
        if graph_index is not None:
            self._delete_from_graph_helper(doc_id, graph_index)
            logger.info(f"  Deleted from graph index")

        # Delete from RDF stores (when rdf_graph_db != none)
        if self.hybrid_system is not None:
            try:
                rdf_adapter = getattr(self.hybrid_system, "rdf_adapter", None)
                if rdf_adapter is not None:
                    from rdf.kg_to_rdf_converter import DEFAULT_BASE_NS
                    graph_uri = DEFAULT_BASE_NS.rstrip("/")
                    rdf_adapter.delete(doc_id, graph_uri=graph_uri)
                    logger.info(f"  Deleted RDF triples for ref_doc_id={doc_id}")
                else:
                    self.hybrid_system._delete_from_rdf_stores(doc_id)
            except Exception as e:
                logger.warning(f"  RDF store delete error for doc '{doc_id}': {e}")
    
    async def _insert_to_all_indexes(self, llama_doc, doc_id: str, metadata: FileMetadata, datasource_config=None):
        """
        Insert document into all indexes (vector, search, graph).
        
        If hybrid_system is provided, reuses existing ingestion logic from backend.
        Otherwise, uses direct index insertion (current implementation).
        
        Args:
            llama_doc: The LlamaIndex Document to insert
            doc_id: The document ID
            metadata: File metadata
            datasource_config: Optional datasource configuration (contains skip_graph flag)
        """
        # Insert new version to all indexes
        # Option A: Use hybrid_system if available (RECOMMENDED - reuses all ingestion logic)
        if self.hybrid_system is not None:
            logger.info(f"  Using hybrid_system for ingestion (reuses existing logic)...")
            try:
                # hybrid_system.ingest_documents() expects file_paths, not Document objects
                # Since we already have the content, we need to use _ingest_source_documents() instead
                # which takes Document objects directly
                
                # Determine skip_graph: prioritize datasource config, fallback to default (False)
                if datasource_config and hasattr(datasource_config, 'skip_graph'):
                    skip_graph = datasource_config.skip_graph
                    logger.info(f"  Using datasource skip_graph={skip_graph}")
                else:
                    skip_graph = False  # Default: don't skip graph
                    logger.info(f"  Using default skip_graph={skip_graph}")
                
                # Call _ingest_source_documents() which is async
                await self.hybrid_system._ingest_source_documents(
                    documents=[llama_doc],
                    processing_id=None,
                    status_callback=None,
                    skip_graph=skip_graph
                )
                
                # Mark all targets as synced (only if databases are configured)
                if self.vector_index is not None and self.config.vector_db.lower() != 'none':
                    await self.state_manager.mark_target_synced(doc_id, 'vector')
                    logger.info(f"  Marked vector as synced")
                
                # When using hybrid_system, search is always enabled (part of hybrid_system)
                # Mark search as synced if search_db is configured (even if search_index is None)
                if self.config.search_db.lower() != 'none':
                    try:
                        await self.state_manager.mark_target_synced(doc_id, 'search')
                        logger.info(f"  Marked search as synced")
                    except Exception as e:
                        logger.error(f"  ERROR: Failed to mark search as synced: {e}")
                elif self.search_index is not None:
                    # Fallback: mark if search_index is explicitly provided
                    try:
                        await self.state_manager.mark_target_synced(doc_id, 'search')
                        logger.info(f"  Marked search as synced (fallback)")
                    except Exception as e:
                        logger.error(f"  ERROR: Failed to mark search as synced (fallback): {e}")
                
                # DON'T mark graph as synced if: skip_graph OR not enable_knowledge_graph OR graph_db is none
                should_skip_graph = (
                    skip_graph or 
                    not self.config.enable_knowledge_graph or 
                    self.config.pg_graph_db.lower() == 'none'
                )
                if self.graph_index is not None and not should_skip_graph:
                    await self.state_manager.mark_target_synced(doc_id, 'graph')
                
                logger.info(f"  All indexes updated via hybrid_system")
                return
                
            except Exception as e:
                logger.exception(f"  Error using hybrid_system: {e}")
                raise
        
        # Option B: Direct insert (FALLBACK - for testing or when hybrid_system not available)
        logger.info(f"  Using direct index insertion (fallback)...")
        
        # Insert new version to all indexes using direct insertion
        logger.info(f"  Inserting new version...")
        
        # Insert to Vector Index
        if self.vector_index is not None:
            try:
                logger.info(f"  Inserting to vector index...")
                await self._insert_to_vector_index(llama_doc, doc_id)
            except Exception as e:
                logger.exception(f"  ERROR: Error inserting to vector index: {e}")
                raise
        
        # Insert to Search Index
        if self.search_index is not None and self.search_index is not self.vector_index:
            try:
                logger.info(f"  Inserting to search index...")
                await self._insert_to_search_index(llama_doc, doc_id)
            except Exception as e:
                error_str = str(e).lower()
                if 'version conflict' in error_str:
                    logger.debug(f"  Version conflict (expected): {e}")
                    # Only mark as synced if search DB is actually configured
                    if self.config.search_db.lower() != 'none':
                        await self.state_manager.mark_target_synced(doc_id, 'search')
                else:
                    logger.exception(f"  ERROR: Error inserting to search index: {e}")
                    raise
        
        # Insert to Graph Index
        # Determine skip_graph: prioritize datasource config, fallback to default (False)
        if datasource_config and hasattr(datasource_config, 'skip_graph'):
            skip_graph = datasource_config.skip_graph
        else:
            skip_graph = False  # Default: don't skip graph
        
        # DON'T do graph if: skip_graph OR not enable_knowledge_graph OR graph_db is none
        should_skip_graph = (
            skip_graph or 
            not self.config.enable_knowledge_graph or 
            self.config.pg_graph_db.lower() == 'none'
        )
        
        if self.graph_index is not None and not should_skip_graph:
            try:
                logger.info(f"  Inserting to graph index...")
                num_entities = await self._process_and_insert_to_graph(llama_doc, doc_id, metadata)
                await self.state_manager.mark_target_synced(doc_id, 'graph')
                logger.info(f"  Graph index updated with {num_entities} entities")
            except Exception as e:
                logger.exception(f"  ERROR: Error inserting to graph index: {e}")
                raise
        elif should_skip_graph:
            logger.info(f"  SKIP: Graph extraction (skip_graph={skip_graph}, enable_knowledge_graph={self.config.enable_knowledge_graph}, graph_db={self.config.pg_graph_db})")
    
    async def _delete_from_all_indexes(self, doc_id: str) -> None:
        """
        Delete document from all indexes by doc_id.
        
        Now that backend and incremental system use same stable doc_id format (config_id:filename),
        this simple doc_id-based delete will work correctly!
        """
        
        hs = self.hybrid_system

        # ── Vector store delete ───────────────────────────────────────────────
        # Both LC and LI adapters expose delete(ref_doc_id).
        # LC adapter: custom delete using native client (Qdrant FilterSelector, ES delete_by_query, etc.)
        # LI adapter: delegates to self._store.delete(ref_doc_id) — works for Qdrant, pgvector, etc.
        _vector_adapter = getattr(hs, "vector_store", None) if hs else None
        _vector_is_lc = (
            _vector_adapter is not None
            and callable(getattr(_vector_adapter, "is_langchain", None))
            and _vector_adapter.is_langchain()
        )
        if _vector_adapter is not None and _vector_is_lc:
            try:
                _vector_adapter.delete(doc_id)
                logger.info(f"  Deleted from LC vector store (ref_doc_id={doc_id})")
            except Exception as e:
                logger.warning(f"  LC vector delete failed: {e}")
        elif _vector_adapter is not None and hasattr(_vector_adapter, "delete"):
            # LI adapter: use adapter.delete() which calls self._store.delete()
            try:
                _vector_adapter.delete(doc_id)
                logger.info(f"  Deleted from LI vector store (ref_doc_id={doc_id})")
            except Exception as e:
                logger.warning(f"  LI vector delete failed: {e}")
        elif self.vector_index:
            # Fallback: use VectorStoreIndex.delete_ref_doc
            try:
                if hs and hs.vector_store:
                    vector_store_type = type(hs.vector_store).__name__
                    if vector_store_type == "WeaviateVectorStore":
                        if hasattr(hs.vector_store, '_aclient') and hs.vector_store._aclient is not None:
                            if not hs.vector_store._aclient.is_connected():
                                await hs.vector_store._aclient.connect()
                            await hs.vector_store.adelete(doc_id)
                            logger.info(f"  Deleted from Weaviate adelete() (ref_doc_id={doc_id})")
                        else:
                            self.vector_index.delete_ref_doc(doc_id, delete_from_docstore=True)
                    else:
                        self.vector_index.delete_ref_doc(doc_id, delete_from_docstore=True)
                else:
                    self.vector_index.delete_ref_doc(doc_id, delete_from_docstore=True)
                logger.info(f"  Deleted from LI vector index (delete_ref_doc)")
            except Exception as e:
                logger.warning(f"  LI vector index delete failed: {e}")

        # ── Search store delete ───────────────────────────────────────────────
        # LC mode: custom delete using ES/OpenSearch delete_by_query.
        # LI mode: use search_index.delete_ref_doc (LI async-safe path).
        _search_adapter = getattr(hs, "search_store", None) if hs else None
        _search_is_lc = (
            _search_adapter is not None
            and callable(getattr(_search_adapter, "is_langchain", None))
            and _search_adapter.is_langchain()
        )
        if _search_adapter is not None and _search_is_lc:
            try:
                _search_adapter.delete(doc_id)
                logger.info(f"  Deleted from LC search store (ref_doc_id={doc_id})")
            except Exception as e:
                logger.warning(f"  LC search delete failed: {e}")
        elif _search_adapter is not None:
            # LI mode: prefer the async delete path on the underlying store to avoid
            # "There is no current event loop" errors from asyncio.run() inside sync delete().
            _li_store = getattr(_search_adapter, "_store", None)
            try:
                if _li_store is not None and hasattr(_li_store, "adelete"):
                    await _li_store.adelete(doc_id)
                    logger.info(f"  Deleted from LI search store async (ref_doc_id={doc_id})")
                elif _li_store is not None and hasattr(_li_store, "delete"):
                    _li_store.delete(doc_id)
                    logger.info(f"  Deleted from LI search store (ref_doc_id={doc_id})")
                elif hasattr(_search_adapter, "delete"):
                    _search_adapter.delete(doc_id)
                    logger.info(f"  Deleted from LI search adapter (ref_doc_id={doc_id})")
            except Exception as e:
                logger.warning(f"  LI search delete failed: {e}")
        elif self.search_index:
            # Final fallback: use delete_ref_doc on the search index
            try:
                self.search_index.delete_ref_doc(doc_id, delete_from_docstore=True)
                logger.info(f"  Deleted from LI search index (ref_doc_id={doc_id})")
            except Exception as e:
                logger.warning(f"  LI search delete failed: {e}")

        # ── Property graph delete ─────────────────────────────────────────────
        # LC mode: LangChainPGAdapter.delete() uses Cypher/AQL/etc. with ref_doc_id.
        # LI mode: _delete_from_graph_helper uses graph_index.delete_ref_doc() + store.delete().
        _pg_adapter = getattr(hs, "pg_adapter", None) if hs else None
        _pg_is_lc = (
            _pg_adapter is not None
            and callable(getattr(_pg_adapter, "is_langchain", None))
            and _pg_adapter.is_langchain()
        )
        if _pg_adapter is not None and _pg_is_lc:
            try:
                _pg_adapter.delete(doc_id)
                logger.info(f"  Deleted from LC property graph (ref_doc_id={doc_id})")
            except Exception as e:
                logger.warning(f"  LC graph delete failed: {e}")
        else:
            # LI mode: cascading delete via graph_index.delete_ref_doc + store.delete(properties)
            _li_graph_index = self.graph_index or (getattr(hs, "graph_index", None) if hs else None)
            if _li_graph_index is not None:
                try:
                    self._delete_from_graph_helper(doc_id, _li_graph_index, "graph")
                    logger.info(f"  Deleted from LI graph index (ref_doc_id={doc_id})")
                except Exception as e:
                    logger.warning(f"  LI graph delete failed: {e}")

        # Delete from RDF stores (when rdf_graph_db != none)
        if self.hybrid_system is not None:
            try:
                rdf_adapter = getattr(self.hybrid_system, "rdf_adapter", None)
                if rdf_adapter is not None:
                    from rdf.kg_to_rdf_converter import DEFAULT_BASE_NS
                    graph_uri = DEFAULT_BASE_NS.rstrip("/")
                    rdf_adapter.delete(doc_id, graph_uri=graph_uri)
                    logger.info(f"  Deleted RDF triples for ref_doc_id={doc_id}")
                else:
                    self.hybrid_system._delete_from_rdf_stores(doc_id)
            except Exception as e:
                logger.warning(f"  RDF store delete error for doc '{doc_id}': {e}")

    def _delete_from_graph_helper(self, doc_id: str, graph_index, context: str = "") -> None:
        """
        Helper method to delete all graph nodes associated with a document.
        
        Performs cascading delete in 3 steps:
        1. Delete TextNode chunks (via delete_ref_doc)
        2. Delete EntityNodes by doc_id property
        3. Delete Document node by id
        
        Args:
            doc_id: The document ID to delete
            context: Logging context (e.g., "old" for updates, "" for deletes)
        """
        if not graph_index:
            return
            
        prefix = f"{context} " if context else ""
        
        try:
            # Step 1: Delete chunk nodes by ref_doc_id
            # Note: May log "ref_doc_id not found" warning from LlamaIndex - this is expected
            try:
                logger.debug(f"  Deleting {prefix}chunk nodes")
                graph_index.delete_ref_doc(ref_doc_id=doc_id, delete_from_docstore=True)
            except Exception as e:
                # Expected: document might not exist in graph docstore
                logger.debug(f"  {prefix}chunk nodes not found or already deleted")
            
            # Step 2: Delete entities by doc_id property
            graph_store = graph_index.property_graph_store
            if hasattr(graph_store, 'delete') and callable(graph_store.delete):
                try:
                    logger.debug(f"  Deleting {prefix}entities")
                    graph_store.delete(properties={'doc_id': doc_id})
                except Exception as e:
                    logger.debug(f"  Could not delete {prefix}entities: {e}")
            
            # Step 3: Delete document node (stored in docstore as graph node)
            if hasattr(graph_store, 'delete') and callable(graph_store.delete):
                try:
                    logger.debug(f"  Deleting {prefix}document node")
                    graph_store.delete(ids=[doc_id])
                except Exception as e:
                    logger.debug(f"  Could not delete {prefix}document node: {e}")
                    
        except Exception as e:
            logger.debug(f"  Could not delete {prefix}graph data: {e}")
    
    async def _process_and_insert_to_graph(self, llama_doc, doc_id: str, metadata: FileMetadata) -> int:
        """
        Helper method to extract entities from document and insert into graph.
        
        Steps:
        1. Convert Document to TextNodes
        2. Run KG extractor to extract entities/relations
        3. Propagate doc_id/ref_doc_id to entity properties
        4. Insert nodes into graph index
        
        Args:
            llama_doc: The LlamaIndex Document to process
            doc_id: The document ID
            metadata: File metadata
            
        Returns:
            Number of entities extracted
        """
        from llama_index.core.node_parser import SimpleNodeParser
        from process.kg_extractor import count_extracted_entities_and_relations
        
        # Convert document to nodes
        node_parser = SimpleNodeParser.from_defaults()
        logger.info(f"  Converting document to nodes for extraction...")
        nodes = node_parser.get_nodes_from_documents([llama_doc])
        logger.info(f"  Created {len(nodes)} nodes from document")
        
        # Log node IDs for debugging (first 3)
        for i, node in enumerate(nodes[:3]):
            logger.info(f"  Node {i}: id={node.node_id}, ref_doc_id={node.ref_doc_id}, doc_id in metadata={node.metadata.get('doc_id')}")
        
        # Get or create extractors
        # Use the hybrid_system's singleton schema_manager to avoid re-loading
        # the ontology manager on every incremental update call.
        if self.hybrid_system and hasattr(self.hybrid_system, 'schema_manager'):
            schema_manager = self.hybrid_system.schema_manager
        else:
            from schema_manager import SchemaManager
            schema_manager = SchemaManager(self.config.get_active_schema(), self.config)
        
        kg_extractor = schema_manager.create_extractor(
            self.graph_index._llm,
            use_schema=self.config.get_active_schema() is not None,
            llm_provider=self.config.llm_provider,
            extractor_type=self.config.kg_extractor_type
        )
        
        # Run extractor
        logger.info(f"  Running extractor on {len(nodes)} nodes...")
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        extract_func = functools.partial(kg_extractor, nodes, show_progress=True)
        nodes = await loop.run_in_executor(None, extract_func)
        
        # Count entities/relations (also propagates doc_id metadata to entities)
        num_entities, num_relations = count_extracted_entities_and_relations(nodes)
        logger.info(f"  Extraction complete: {num_entities} entities, {num_relations} relations")
        
        # Insert enriched nodes (preserves doc_id/ref_doc_id metadata)
        logger.info(f"  Inserting {len(nodes)} enriched nodes into graph...")
        self.graph_index.insert_nodes(nodes)
        
        return num_entities
    
    async def _insert_to_vector_index(self, llama_doc, doc_id: str):
        """Helper to insert document into vector index."""
        self.vector_index.refresh_ref_docs([llama_doc])
        # Only mark as synced if vector DB is actually configured
        if self.config.vector_db.lower() != 'none':
            await self.state_manager.mark_target_synced(doc_id, 'vector')
        logger.info(f"  Vector index updated")
    
    async def _insert_to_search_index(self, llama_doc, doc_id: str):
        """Helper to insert document into search index."""
        # Insert new version - handle Elasticsearch race conditions
        try:
            self.search_index.refresh_ref_docs([llama_doc])
        except Exception as e:
            error_str = str(e).lower()
            # Handle expected Elasticsearch race conditions
            if 'resource_already_exists_exception' in error_str:
                logger.debug(f"  Index exists, retrying insert...")
                await asyncio.sleep(0.1)  # Brief pause to let index stabilize
                self.search_index.refresh_ref_docs([llama_doc])
            elif 'version_conflict_engine_exception' in error_str or 'version conflict' in error_str:
                # Version conflict during delete+insert is expected - document already updated
                logger.debug(f"  INFO: Version conflict during update (expected - document already updated)")
            else:
                raise
        
        # Only mark as synced if search DB is actually configured
        if self.config.search_db.lower() != 'none':
            await self.state_manager.mark_target_synced(doc_id, 'search')
        logger.info(f"  Search index updated")
    
    async def process_change_event(self, event: ChangeEvent, detector, config_id: str):
        """
        Process a single change event.
        
        For CREATE/MODIFY events:
        1. Load and prepare document
        2. Delete from all indexes (if document already exists)
        3. Insert to all indexes
        4. State is preserved with updated sync timestamps
        
        For DELETE events:
        1. Delete from all indexes
        2. Remove state from PostgreSQL (hard delete)
        """
        metadata = event.metadata
        # Use normalized path for filesystem so path case (e.g. C:\ vs c:\) does not break lookups
        path_for_doc_id = metadata.path
        if getattr(metadata, 'source_type', None) == 'filesystem':
            from incremental_updates.path_utils import normalize_filesystem_path
            path_for_doc_id = normalize_filesystem_path(metadata.path)
        doc_id = StateManager.make_doc_id(config_id, path_for_doc_id)
        
        # Load datasource config to get skip_graph setting
        datasource_config = None
        if self.config_manager:
            try:
                datasource_config = await self.config_manager.get_config(config_id)
                if datasource_config:
                    logger.info(f"Loaded datasource config: skip_graph={datasource_config.skip_graph}")
            except Exception as e:
                logger.debug(f"Could not load datasource config: {e}")
        
        # Handle DELETE events
        if event.change_type == ChangeType.DELETE:
            logger.info(f"DELETE: Delete event for {metadata.path}")
            
            # Check if this is a MODIFY delete (with callback)
            if event.is_modify_delete:
                logger.info(f"DELETE: This is part of a MODIFY operation")
            
            # Try to find by source_id first (for cloud sources like Google Drive, Alfresco, etc.)
            existing_state = None
            # Check for source_id in different formats depending on data source
            source_id = (
                metadata.extra.get('file_id') or      # Google Drive, Box, OneDrive, SharePoint
                metadata.extra.get('node_id') or       # Alfresco
                metadata.extra.get('object_key') or    # S3
                metadata.extra.get('blob_name')        # Azure Blob, GCS
            ) if metadata.extra else None
            
            if source_id:
                logger.info(f"DELETE: Looking up by source_id: {source_id}")
                existing_state = await self.state_manager.get_state_by_source_id(config_id, source_id)
                if existing_state:
                    logger.info(f"DELETE: Found document by source_id: {existing_state.source_path}")
                    # Use the correct doc_id from the state record
                    doc_id = existing_state.doc_id
            
            # Fall back to path lookup (for filesystem sources or if source_id lookup failed)
            if not existing_state:
                logger.info(f"DELETE: Looking up by path: {metadata.path}")
                existing_state = await self.state_manager.get_state(doc_id)
                # S3: document_state uses doc_id = config_id:s3_uri and source_id = s3_uri; event path is bucket/key
                if not existing_state and getattr(metadata, 'source_type', None) == 's3' and not (metadata.path or '').startswith('s3://'):
                    s3_uri = f"s3://{metadata.path}"
                    logger.info(f"DELETE: S3 fallback looking up by source_id: {s3_uri}")
                    existing_state = await self.state_manager.get_state_by_source_id(config_id, s3_uri)
                    if existing_state:
                        doc_id = existing_state.doc_id
                        logger.info(f"DELETE: Found by S3 source_id: {existing_state.source_path}")
                # Case-insensitive path fallback for filesystem (e.g. c:\ vs C:\ on Windows)
                if not existing_state and getattr(metadata, 'source_type', None) == 'filesystem':
                    existing_state = await self.state_manager.get_state_by_path_fallback(config_id, metadata.path)
                    if existing_state:
                        doc_id = existing_state.doc_id
                        logger.info(f"DELETE: Found by path fallback: {existing_state.source_path}")
            
            if not existing_state:
                logger.info(f"SKIP DELETE: {metadata.path} not found in document_state (not tracked)")
                # Still invoke callback if this is a MODIFY (to process ADD even if DELETE not found)
                if event.is_modify_delete and event.modify_callback:
                    logger.info(f"MODIFY: Invoking callback for ADD (despite DELETE not found)")
                    await event.modify_callback()
                return
            
            logger.info(f"DELETE: Document found in database, proceeding with deletion...")
            
            # Determine which ID to use for index deletion (must match ref_doc_id in vector/search):
            # - S3: pipeline indexes with config_id:s3_uri; use config_id:existing_state.source_id
            # - Other cloud: use doc_id (stable) or source_id (old format)
            # - Filesystem: use doc_id
            delete_id = doc_id
            if existing_state.source_id and str(existing_state.source_id).startswith("s3://"):
                # Vector/search were indexed with ref_doc_id = config_id:s3_uri
                delete_id = f"{config_id}:{existing_state.source_id}"
                logger.info(f"DELETE: Using S3 ref_doc_id for index deletion: {delete_id}")
            elif ':' in doc_id and source_id:
                delete_id = doc_id
                logger.info(f"DELETE: Using stable doc_id for index deletion: {delete_id}")
            elif source_id:
                delete_id = source_id
                logger.info(f"DELETE: Using source_id for index deletion: {delete_id}")
            else:
                delete_id = doc_id
                logger.info(f"DELETE: Using doc_id for index deletion: {delete_id}")
            
            # Delete from all indexes using the correct ID
            await self._delete_from_all_indexes(delete_id)
            
            # HARD DELETE: Remove state from PostgreSQL completely
            await self.state_manager.mark_deleted(doc_id)
            logger.info(f"SUCCESS: Deleted {metadata.path}")
            
            # If this is a MODIFY delete, invoke callback to process ADD
            if event.is_modify_delete and event.modify_callback:
                logger.info(f"MODIFY: DELETE completed, invoking callback for ADD")
                await event.modify_callback()
            
            return
        
        # Handle CREATE/MODIFY events
        # Check if we can skip download by comparing modification timestamps
        
        # For cloud sources with source_id, look up by source_id instead of doc_id
        # This handles the case where metadata.path is just a filename (Box, etc.)
        existing_state = None
        if hasattr(metadata, 'extra') and metadata.extra and metadata.extra.get('file_id'):
            # Cloud source with file_id - look up by source_id
            source_id = metadata.extra.get('file_id') or metadata.extra.get('id') or metadata.extra.get('node_id')
            if source_id:
                existing_state = await self.state_manager.get_state_by_source_id(config_id, source_id)
                if existing_state:
                    logger.debug(f"Found existing state by source_id: {source_id}")
        
        # Fallback to doc_id lookup
        if not existing_state:
            existing_state = await self.state_manager.get_state(doc_id)
            if existing_state:
                logger.debug(f"Found existing state by doc_id: {doc_id}")
        
        # Quick timestamp-based change detection (optimization for Alfresco and other sources)
        if (existing_state and 
            metadata.modified_timestamp and 
            existing_state.modified_timestamp == metadata.modified_timestamp):
            # Timestamp hasn't changed - file content is guaranteed unchanged
            logger.info(f"SKIP: {metadata.path}: timestamp unchanged (no download needed)")
            
            # Update ordinal to latest seen version (even though content is same)
            await self.state_manager._update_ordinal_only(
                doc_id, 
                metadata.ordinal, 
                metadata.modified_timestamp
            )
            return
        
        # Check if detector uses backend pattern (has backend attribute)
        # For backend-integrated detectors:
        # - If file is NEW (not in document_state):
        #   * For detectors with event streams (Box, Drive, S3, Alfresco): SKIP - let event stream handle it
        #   * For detectors without events (GCS, Azure): Process via backend
        # - If file EXISTS: Check timestamps, skip if unchanged
        if hasattr(detector, 'backend') and detector.backend is not None:
            # Check if this is a NEW file (not in document_state)
            if not existing_state:
                # NEW file detected
                detector_name = detector.__class__.__name__ if hasattr(detector, '__class__') else 'unknown'
                
                # For detectors with event streams (polling or webhooks), skip NEW files in periodic refresh
                # Let the event stream handle new file detection and processing
                # BUT: Check if the event stream is actually enabled before skipping!
                if detector_name in ['BoxDetector', 'GoogleDriveDetector', 'S3Detector', 'AlfrescoDetector']:
                    logger.info(f"NEW FILE: {metadata.path}: Skipping in periodic refresh (will be processed by event stream)")
                    return
                
                # For MicrosoftGraphDetector, only skip if change polling is enabled
                if detector_name == 'MicrosoftGraphDetector':
                    if hasattr(detector, 'enable_change_polling') and detector.enable_change_polling:
                        logger.info(f"NEW FILE: {metadata.path}: Skipping in periodic refresh (will be processed by change polling)")
                        return
                    else:
                        logger.info(f"NEW FILE: {metadata.path}: Processing via backend (change polling disabled)...")
                        # Fall through to process via backend
                
                # For other detectors without event streams (GCS, Azure, Filesystem), process via backend
                if detector_name not in ['BoxDetector', 'GoogleDriveDetector', 'S3Detector', 'AlfrescoDetector', 'MicrosoftGraphDetector']:
                    logger.info(f"NEW FILE: {metadata.path}: Processing via backend...")
                
                try:
                    if detector_name == 'FilesystemDetector':
                        # Filesystem needs full_path, relative_path
                        # Filesystem needs full_path, relative_path
                        relative_path = os.path.basename(metadata.path)
                        await detector._process_via_backend(metadata.path, relative_path)
                    elif detector_name == 'MicrosoftGraphDetector':
                        # OneDrive/SharePoint needs file_id, filename, file_path, folder_path
                        # Extract from metadata.extra
                        file_id = metadata.extra.get('file_id')
                        file_name = metadata.extra.get('file_name', os.path.basename(metadata.path))
                        file_path = metadata.extra.get('file_path', f"/{file_name}")
                        folder_path = metadata.extra.get('folder_path', '/')
                        await detector._process_via_backend(file_id, file_name, file_path, folder_path)
                    else:
                        # GCS, Azure - single parameter (path/key/object_name)
                        await detector._process_via_backend(metadata.path)
                except Exception as e:
                    logger.error(f"Failed to process new file {metadata.path}: {e}")
                    raise
                
                return
            else:
                # File already exists in document_state
                detector_name = detector.__class__.__name__ if hasattr(detector, '__class__') else 'unknown'

                # For FilesystemDetector: if mtime has changed, re-process (MODIFY = DELETE + ADD).
                # The timestamp-unchanged check above returned early when mtime matched,
                # so reaching here means the mtime DID change (or was not recorded).
                if detector_name == 'FilesystemDetector':
                    # Guard: only re-process if the ordinal (mtime×1e6) actually changed.
                    # If ordinal is unchanged, the file content is the same — skip.
                    if existing_state and existing_state.ordinal and metadata.ordinal and existing_state.ordinal >= metadata.ordinal:
                        logger.debug(f"SKIP: {metadata.path}: ordinal unchanged ({existing_state.ordinal})")
                        return

                    logger.info(f"MODIFY: {metadata.path}: mtime changed (ordinal {getattr(existing_state, 'ordinal', '?')} -> {metadata.ordinal}) — emitting DELETE+ADD event")
                    full_path = metadata.path

                    async def _modify_add_callback():
                        logger.info(f"MODIFY: DELETE completed, now re-ingesting {full_path}")
                        try:
                            relative_path = os.path.basename(full_path)
                            await detector._process_via_backend(full_path, relative_path)
                            logger.info(f"MODIFY: re-ingest succeeded for {full_path}")
                        except Exception as exc:
                            logger.error(f"MODIFY: re-ingest failed for {full_path}: {exc}")

                    delete_event = ChangeEvent(
                        metadata=FileMetadata(
                            source_type='filesystem',
                            path=full_path,
                            ordinal=metadata.ordinal,
                            extra={},
                        ),
                        change_type=ChangeType.DELETE,
                        timestamp=event.timestamp,
                        is_modify_delete=True,
                        modify_callback=_modify_add_callback,
                    )
                    await self.process_change_event(delete_event, detector, config_id)
                    return

                # For detectors with real-time events (Box, Drive, S3, Alfresco), skip —
                # the event stream already handles MODIFY events.
                # For GCS/Azure periodic mode without real-time events, updating would require
                # downloading content to compare; skip for now (rely on timestamp check above).
                logger.info(f"SKIP: {metadata.path}: Backend-integrated detector (existing file)")
                return
        
        # Load file content (only for legacy detectors without backend integration)
        if not hasattr(detector, 'load_file_content'):
            logger.warning(f"SKIP: {metadata.path}: Detector has no load_file_content method")
            return
            
        content = await detector.load_file_content(metadata.path)
        if not content:
            logger.warning(f"Could not load content for {metadata.path}")
            return
        
        # Decode content
        try:
            text = content.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Error decoding {metadata.path}: {e}")
            return
        
        # Compute content hash
        content_hash = StateManager.compute_content_hash(text)
        
        # Check if processing needed (content hash verification)
        should_process, reason = await self.state_manager.should_process(
            doc_id, metadata.ordinal, content_hash
        )
        
        if not should_process:
            logger.info(f"SKIP: {metadata.path}: {reason}")
            return
        
        logger.info(f"PROCESSING: {metadata.path} ({reason})...")
        start_time = time.time()
        
        # Create LlamaIndex Document
        llama_doc = Document(
            text=text,
            doc_id=doc_id,
            metadata={
                'source_path': metadata.path,
                'source_type': metadata.source_type,
                'size_bytes': metadata.size_bytes,
                'ordinal': metadata.ordinal,
                'doc_id': doc_id  # Add doc_id to metadata for propagation to entities
            }
        )
        
        # Explicitly set doc.id_ to ensure it's not overwritten by hybrid_system
        llama_doc.id_ = doc_id
        logger.info(f"  Set document id_: {llama_doc.id_}")
        
        # Check if document already exists in indexes BEFORE saving state
        # Check both database state AND vector index (in case state hasn't been created yet)
        existing_state = await self.state_manager.get_state(doc_id)
        
        # Also check if document exists in vector index directly
        # Note: Some vector stores (like Qdrant) don't support ref_doc_info
        doc_exists_in_index = False
        if self.vector_index:
            try:
                if hasattr(self.vector_index, 'ref_doc_info'):
                    doc_exists_in_index = doc_id in self.vector_index.ref_doc_info
            except NotImplementedError:
                # Vector store doesn't support ref_doc_info (e.g., Qdrant)
                # Fall back to database state only
                pass
        
        is_update = (existing_state and (
            existing_state.vector_synced_at or 
            existing_state.search_synced_at or 
            existing_state.graph_synced_at
        )) or doc_exists_in_index  # Also update if doc exists in index!
        
        logger.info(f"  existing_state: {existing_state is not None}")
        if existing_state:
            logger.info(f"  vector_synced_at: {existing_state.vector_synced_at}")
            logger.info(f"  search_synced_at: {existing_state.search_synced_at}")
            logger.info(f"  graph_synced_at: {existing_state.graph_synced_at}")
        logger.info(f"  doc_exists_in_index: {doc_exists_in_index}")
        logger.info(f"  is_update: {is_update}")
        
        # Save state (updates ordinal, content_hash, and modified_timestamp)
        # Create state object with existing sync timestamps to preserve them
        # Extract source_id from metadata extra (e.g., Google Drive file_id)
        source_id = metadata.extra.get('file_id') if metadata.extra else None
        
        state = DocumentState(
            doc_id=doc_id,
            config_id=config_id,
            source_path=metadata.path,
            source_id=source_id,  # Store source-specific file ID
            ordinal=metadata.ordinal,
            content_hash=content_hash,
            modified_timestamp=metadata.modified_timestamp,
            # Preserve existing sync timestamps if this is an update
            vector_synced_at=existing_state.vector_synced_at if existing_state else None,
            search_synced_at=existing_state.search_synced_at if existing_state else None,
            graph_synced_at=existing_state.graph_synced_at if existing_state else None
        )
        await self.state_manager.save_state(state)
        
        # If updating, delete old version from all indexes first
        # NOTE: We delete from INDEXES only, NOT from state DB
        if is_update:
            logger.info(f"  Deleting old version from indexes...")
            await self._delete_from_all_indexes(doc_id)
        
        # Insert new version to all indexes
        logger.info(f"  Inserting new version...")
        await self._insert_to_all_indexes(llama_doc, doc_id, metadata, datasource_config)
        
        # State is automatically updated with new sync timestamps by _insert_to_all_indexes
        
        duration = time.time() - start_time
        
        logger.info(f"SUCCESS: Processed {metadata.path} in {duration:.2f}s")
    
    async def process_batch(self, events: List[ChangeEvent], detector, config_id: str):
        """Process a batch of change events"""
        
        logger.info(f"Processing batch of {len(events)} change events")
        
        for event in events:
            try:
                await self.process_change_event(event, detector, config_id)
            except Exception as e:
                logger.exception(f"Error processing event for {event.metadata.path}: {e}")
                # Continue with other events
    
    async def periodic_refresh(self, detector, config_id: str, max_ordinal: int) -> int:
        """
        Perform periodic refresh - check all files and process changes.
        Also detects deletions by comparing current files with document_state.
        Returns the maximum ordinal seen.
        """
        
        logger.info(f"Starting periodic refresh (last ordinal: {max_ordinal})...")
        
        # List all files currently in source
        files = await detector.list_all_files()
        logger.info(f"Found {len(files)} files in source")
        
        # Build set of current file identifiers (use source_id if available, otherwise path)
        # For cloud sources (Box, Drive, S3), metadata.extra contains file_id/key
        current_identifiers = set()
        file_meta_by_id = {}  # Map identifier -> FileMetadata for quick lookup
        
        for file_meta in files:
            # Try to get source-specific ID from metadata.extra
            identifier = None
            if hasattr(file_meta, 'extra') and file_meta.extra:
                # Try common source ID fields
                # For S3: use s3_uri (s3://bucket/key) to match document_state.source_id
                # For GCS: use object_name (gs://bucket/object)
                # For msgraph (OneDrive/SharePoint): use path (stable_path with onedrive:// prefix)
                # For others: use file_id, id, node_id
                if file_meta.source_type == 'msgraph':
                    # Use the stable path (onedrive:// or sharepoint://) to match document_state.source_id
                    identifier = file_meta.path
                else:
                    identifier = (file_meta.extra.get('s3_uri') or
                                 file_meta.extra.get('object_name') or
                                 file_meta.extra.get('file_id') or 
                                 file_meta.extra.get('id') or
                                 file_meta.extra.get('node_id'))
            
            # Fall back to path if no source ID
            if not identifier:
                identifier = file_meta.path
            
            current_identifiers.add(identifier)
            file_meta_by_id[identifier] = file_meta
        
        logger.info(f"Current file identifiers ({len(current_identifiers)}): {current_identifiers}")
        
        # Get existing files from document_state to detect deletions
        existing_states = await self.state_manager.get_all_states_for_config(config_id)
        
        # Build set of existing identifiers (prefer source_id, fall back to source_path)
        existing_identifiers = set()
        state_by_id = {}  # Map identifier -> DocumentState for quick lookup
        
        for state in existing_states:
            identifier = state.source_id if state.source_id else state.source_path
            existing_identifiers.add(identifier)
            state_by_id[identifier] = state
        
        logger.info(f"Existing document_state identifiers ({len(existing_identifiers)}): {existing_identifiers}")
        
        # Detect deletions - files in document_state but not in current source.
        # On Windows, paths may be stored with different case (C:\ vs c:\) across
        # the initial REST ingest and the filesystem detector.  Normalize both sets
        # so that "C:\foo\bar.txt" and "c:\foo\bar.txt" are treated as equal.
        import sys as _sys
        if _sys.platform == "win32":
            try:
                from incremental_updates.path_utils import normalize_filesystem_path as _norm
                _current_norm  = {_norm(i) for i in current_identifiers}
                _existing_norm = {_norm(i) for i in existing_identifiers}
                # Rebuild state_by_id with normalized keys so the deletion loop finds states
                _state_by_id_norm = {_norm(k): v for k, v in state_by_id.items()}
                deleted_norm = _existing_norm - _current_norm
                # Map normalized deleted keys back to original identifiers for logging
                deleted_identifiers = {k for k in existing_identifiers if _norm(k) in deleted_norm}
                # Update state_by_id lookup to use normalized key for deleted entries
                for _k in list(deleted_identifiers):
                    if _norm(_k) in _state_by_id_norm and _k not in state_by_id:
                        state_by_id[_k] = _state_by_id_norm[_norm(_k)]
            except Exception:
                deleted_identifiers = existing_identifiers - current_identifiers
        else:
            deleted_identifiers = existing_identifiers - current_identifiers
        if deleted_identifiers:
            logger.info(f"Detected {len(deleted_identifiers)} deleted file(s): {deleted_identifiers}")
            logger.info(f"   These files are in document_state but NOT in current source listing")
        else:
            logger.info(f"No deletions detected (all document_state files found in source)")
        
        new_max_ordinal = max_ordinal
        processed_count = 0
        
        # Process existing/new files
        for file_meta in files:
            if file_meta.ordinal > new_max_ordinal:
                new_max_ordinal = file_meta.ordinal
            
            # Check if file needs processing
            doc_id = StateManager.make_doc_id(config_id, file_meta.path)
            
            # Create a synthetic change event
            event = ChangeEvent(
                metadata=file_meta,
                change_type=ChangeType.UPDATE,
                timestamp=None
            )
            
            try:
                await self.process_change_event(event, detector, config_id)
                processed_count += 1
            except Exception as e:
                logger.exception(f"Error processing {file_meta.path}: {e}")
        
        # Process deletions
        for deleted_id in deleted_identifiers:
            try:
                # Get the document state for this deleted identifier
                state = state_by_id.get(deleted_id)
                if not state:
                    logger.warning(f"Cannot find state for deleted identifier: {deleted_id}")
                    continue
                
                logger.info(f"Processing deletion: {state.source_path}")
                # Create DELETE event using the stored source_path and source_id
                # Include source_id in extra so engine can look it up by stable ID
                delete_event = ChangeEvent(
                    metadata=FileMetadata(
                        source_type='deleted',  # Will be ignored for DELETE anyway
                        path=state.source_path,
                        ordinal=int(time.time() * 1_000_000),  # Current timestamp
                        size_bytes=0,
                        mime_type=None,
                        extra={'file_id': state.source_id} if state.source_id else None
                    ),
                    change_type=ChangeType.DELETE,
                    timestamp=None
                )
                await self.process_change_event(delete_event, detector, config_id)
                processed_count += 1
            except Exception as e:
                logger.exception(f"Error processing deletion of {deleted_id}: {e}")
        
        logger.info(f"Periodic refresh complete: processed {processed_count} files ({len(files)} updates, {len(deleted_identifiers)} deletions), max ordinal: {new_max_ordinal}")
        
        return new_max_ordinal


