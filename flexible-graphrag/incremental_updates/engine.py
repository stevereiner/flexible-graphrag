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
from document_processor import DocumentProcessor
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
                # Since we already have the content, we need to use _process_documents_direct() instead
                # which takes Document objects directly
                
                # Determine skip_graph: prioritize datasource config, fallback to default (False)
                if datasource_config and hasattr(datasource_config, 'skip_graph'):
                    skip_graph = datasource_config.skip_graph
                    logger.info(f"  Using datasource skip_graph={skip_graph}")
                else:
                    skip_graph = False  # Default: don't skip graph
                    logger.info(f"  Using default skip_graph={skip_graph}")
                
                # Call _process_documents_direct() which is async
                await self.hybrid_system._process_documents_direct(
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
                    self.config.graph_db.lower() == 'none'
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
            self.config.graph_db.lower() == 'none'
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
            logger.info(f"  SKIP: Graph extraction (skip_graph={skip_graph}, enable_knowledge_graph={self.config.enable_knowledge_graph}, graph_db={self.config.graph_db})")
    
    async def _delete_from_all_indexes(self, doc_id: str) -> None:
        """
        Delete document from all indexes by doc_id.
        
        Now that backend and incremental system use same stable doc_id format (config_id:filename),
        this simple doc_id-based delete will work correctly!
        """
        
        # Delete from vector index
        if self.vector_index:
            try:
                logger.info(f"  Attempting to delete from vector index (doc_id: {doc_id})...")
                
                # Check if this is Weaviate with async client
                if self.hybrid_system and self.hybrid_system.vector_store:
                    vector_store_type = type(self.hybrid_system.vector_store).__name__
                    
                    if vector_store_type == "WeaviateVectorStore":
                        # For Weaviate with async client, use async delete method
                        if hasattr(self.hybrid_system.vector_store, '_aclient') and self.hybrid_system.vector_store._aclient is not None:
                            # Ensure connected
                            if not self.hybrid_system.vector_store._aclient.is_connected():
                                await self.hybrid_system.vector_store._aclient.connect()
                                logger.info("  Connected Weaviate async client for delete operation")
                            
                            # Use async delete method directly on vector store
                            await self.hybrid_system.vector_store.adelete(doc_id)
                            logger.info(f"  Deleted from Weaviate using adelete() (ref_doc_id: {doc_id})")
                        else:
                            # Sync client - use standard method
                            result = self.vector_index.delete_ref_doc(doc_id, delete_from_docstore=True)
                            logger.info(f"  Deleted from vector index (result: {result})")
                    else:
                        # Other vector stores - use standard sync delete
                        result = self.vector_index.delete_ref_doc(doc_id, delete_from_docstore=True)
                        logger.info(f"  Deleted from vector index (result: {result})")
                else:
                    # No hybrid_system reference, use standard delete
                    result = self.vector_index.delete_ref_doc(doc_id, delete_from_docstore=True)
                    logger.info(f"  Deleted from vector index (result: {result})")
            except Exception as e:
                logger.warning(f"  Vector delete failed: {e}")
                
        # Also try direct Qdrant deletion as fallback (for Qdrant specifically)
        if self.vector_index and hasattr(self.vector_index, '_client'):
            try:
                from qdrant_client import models
                qdrant_client = self.vector_index._client
                collection_name = self.vector_index._collection_name
                
                # Delete by filter (ref_doc_id payload field)
                logger.info(f"  Attempting direct Qdrant delete by ref_doc_id filter...")
                delete_result = qdrant_client.delete(
                    collection_name=collection_name,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="ref_doc_id",
                                    match=models.MatchValue(value=doc_id),
                                )
                            ]
                        )
                    )
                )
                logger.info(f"  Direct Qdrant delete result: {delete_result}")
            except Exception as e:
                logger.debug(f"  Direct Qdrant delete not applicable or failed: {e}")
        
        # Delete from search index (Elasticsearch/OpenSearch)
        logger.info(f"  Attempting to delete from search index...")
        logger.info(f"  hybrid_system exists: {self.hybrid_system is not None}")
        if self.hybrid_system:
            logger.info(f"  search_store exists: {self.hybrid_system.search_store is not None}")
        
        if self.hybrid_system and self.hybrid_system.search_store:
            try:
                from elasticsearch import AsyncElasticsearch
                from opensearchpy import AsyncOpenSearch
                
                search_store = self.hybrid_system.search_store
                logger.info(f"  search_store type: {type(search_store)}")
                
                # Get the underlying client - check both _client and client attributes
                client = None
                if hasattr(search_store, '_client'):
                    client = search_store._client
                    logger.info(f"  Found _client attribute")
                elif hasattr(search_store, 'client'):
                    client = search_store.client
                    logger.info(f"  Found client attribute")
                
                if client:
                    logger.info(f"  client type: {type(client)}")
                    logger.info(f"  is AsyncElasticsearch: {isinstance(client, AsyncElasticsearch)}")
                    
                    if isinstance(client, (AsyncElasticsearch, AsyncOpenSearch)):
                        index_name = "hybrid_search_fulltext"
                        logger.info(f"  Executing delete_by_query for doc_id: {doc_id}")
                        
                        # First, try to find documents to see what fields exist
                        try:
                            search_result = await client.search(
                                index=index_name,
                                body={
                                    "query": {"match_all": {}},
                                    "size": 1
                                }
                            )
                            if search_result.get('hits', {}).get('hits'):
                                sample_doc = search_result['hits']['hits'][0]['_source']
                                logger.info(f"  Sample document fields in Elasticsearch: {list(sample_doc.keys())}")
                                if 'metadata' in sample_doc:
                                    logger.info(f"  Sample metadata fields: {list(sample_doc['metadata'].keys())}")
                        except Exception as e:
                            logger.debug(f"  Could not get sample document: {e}")
                        
                        # Delete by metadata.ref_doc_id (primary) and metadata.doc_id (fallback)
                        # Note: ref_doc_id is stored inside the metadata object in Elasticsearch
                        # Use 'match' instead of 'term' because these fields don't have .keyword mapping
                        result = await client.delete_by_query(
                            index=index_name,
                            body={
                                "query": {
                                    "bool": {
                                        "should": [
                                            {"match": {"metadata.ref_doc_id": doc_id}},
                                            {"match": {"metadata.doc_id": doc_id}}
                                        ],
                                        "minimum_should_match": 1
                                    }
                                }
                            },
                            refresh=True
                        )
                        deleted = result.get('deleted', 0)
                        logger.info(f"  Deleted {deleted} docs from search index")
                        if deleted == 0:
                            logger.warning(f"  No documents found in search index with doc_id: {doc_id}")
                    else:
                        logger.warning(f"  Client is not AsyncElasticsearch or AsyncOpenSearch!")
                else:
                    logger.warning(f"  search_store has no _client or client attribute!")
            except Exception as e:
                logger.warning(f"  Search delete failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            logger.warning(f"  No search_store available for deletion")
        
        # Delete from graph index
        if self.graph_index:
            try:
                self._delete_from_graph_helper(doc_id, self.graph_index, "graph")
                logger.info(f"  Deleted from graph index")
            except Exception as e:
                logger.warning(f"  Graph delete failed: {e}")
    
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
                self.graph_index.delete_ref_doc(ref_doc_id=doc_id, delete_from_docstore=True)
            except Exception as e:
                # Expected: document might not exist in graph docstore
                logger.debug(f"  {prefix}chunk nodes not found or already deleted")
            
            # Step 2: Delete entities by doc_id property
            graph_store = self.graph_index.property_graph_store
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
        from hybrid_system import SchemaManager, count_extracted_entities_and_relations
        
        # Convert document to nodes
        node_parser = SimpleNodeParser.from_defaults()
        logger.info(f"  Converting document to nodes for extraction...")
        nodes = node_parser.get_nodes_from_documents([llama_doc])
        logger.info(f"  Created {len(nodes)} nodes from document")
        
        # Log node IDs for debugging (first 3)
        for i, node in enumerate(nodes[:3]):
            logger.info(f"  Node {i}: id={node.node_id}, ref_doc_id={node.ref_doc_id}, doc_id in metadata={node.metadata.get('doc_id')}")
        
        # Get or create extractors
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
        doc_id = StateManager.make_doc_id(config_id, metadata.path)
        
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
            
            if not existing_state:
                logger.info(f"SKIP DELETE: {metadata.path} not found in document_state (not tracked)")
                # Still invoke callback if this is a MODIFY (to process ADD even if DELETE not found)
                if event.is_modify_delete and event.modify_callback:
                    logger.info(f"MODIFY: Invoking callback for ADD (despite DELETE not found)")
                    await event.modify_callback()
                return
            
            logger.info(f"DELETE: Document found in database, proceeding with deletion...")
            
            # Determine which ID to use for deletion:
            # - If doc_id has stable format (config_id:filename), use it (new data)
            # - Otherwise, use source_id if available (old data with file ID)
            # - Fallback to doc_id (filesystem sources)
            if ':' in doc_id and source_id:
                # New stable format - use doc_id
                delete_id = doc_id
                logger.info(f"DELETE: Using stable doc_id for index deletion: {delete_id}")
            elif source_id:
                # Old format - use source_id (Google Drive file ID)
                delete_id = source_id
                logger.info(f"DELETE: Using source_id for index deletion: {delete_id}")
            else:
                # Filesystem or fallback
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
                if detector_name in ['BoxDetector', 'GoogleDriveDetector', 'S3Detector', 'AlfrescoDetector', 'MicrosoftGraphDetector']:
                    logger.info(f"NEW FILE: {metadata.path}: Skipping in periodic refresh (will be processed by event stream)")
                    return
                
                # For detectors without event streams (GCS, Azure, Filesystem), process via backend
                logger.info(f"NEW FILE: {metadata.path}: Processing via backend...")
                
                try:
                    if detector_name == 'FilesystemDetector':
                        # Filesystem needs full_path, relative_path
                        import os
                        relative_path = os.path.basename(metadata.path)
                        await detector._process_via_backend(metadata.path, relative_path)
                    else:
                        # GCS, Azure - single parameter (path/key/object_name)
                        await detector._process_via_backend(metadata.path)
                except Exception as e:
                    logger.error(f"Failed to process new file {metadata.path}: {e}")
                    raise
                
                return
            else:
                # File already exists in document_state
                # For detectors with real-time events, skip (already processed)
                # For detectors without real-time events (GCS, Azure), we should check for updates
                # but this requires downloading content, so skip for now (rely on timestamp check above)
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
                identifier = (file_meta.extra.get('file_id') or 
                             file_meta.extra.get('id') or
                             file_meta.extra.get('node_id') or
                             file_meta.extra.get('s3_key') or
                             file_meta.extra.get('object_name'))
            
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
        
        # Detect deletions - files in document_state but not in current source
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
                # Create DELETE event using the stored source_path
                delete_event = ChangeEvent(
                    metadata=FileMetadata(
                        source_type='deleted',  # Will be ignored for DELETE anyway
                        path=state.source_path,
                        ordinal=int(time.time() * 1_000_000),  # Current timestamp
                        size_bytes=0,
                        mime_type=None,
                        extra=None
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


