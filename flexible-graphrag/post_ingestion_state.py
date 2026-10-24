"""
Post-Ingestion Document State Manager

Creates document_state records after initial ingestion completes.
This prevents duplicate processing by the incremental update system.

Handles path extraction for different data sources:
- Filesystem: Uses local file paths
- Alfresco/CMIS: Constructs full repository paths
- S3: Uses bucket/key format
- Azure Blob: Uses container/blob format
- GCS: Uses bucket/object format
- Google Drive: Uses file paths from metadata
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger(__name__)


class PostIngestionStateManager:
    """Manages document_state creation after ingestion completes."""
    
    def __init__(self, postgres_url: Optional[str] = None):
        """
        Initialize the post-ingestion state manager.
        
        Args:
            postgres_url: PostgreSQL connection URL for state manager (unused with
                INCREMENTAL_STATE_STORE=openarch, see incremental_updates/stores.py)
        """
        self.postgres_url = postgres_url
    
    async def create_document_states_after_ingestion(
        self,
        processing_id: str,
        config_id: str,
        paths: List[str],
        data_source: str = "filesystem",
        skip_graph: Optional[bool] = None,
        graphs=None,
    ):
        """
        Background task to create document_state records after ingestion completes.
        ``graphs`` (graph_flags.GraphFlags): which graphs the run built (else ``skip_graph``, the
        older single flag, else the datasource's).
        This prevents duplicate processing by incremental system.
        
        Args:
            processing_id: ID of the processing task
            config_id: Configuration ID for the datasource
            paths: Input paths (may be empty for non-filesystem sources)
            data_source: Type of data source (filesystem, s3, alfresco, etc.)
        """
        try:
            from backend import PROCESSING_STATUS
            from incremental_updates.stores import new_state_manager
            
            logger.info(f"Monitoring ingestion {processing_id} for completion to create document_state records...")
            # GET/DELETE /api/processing-status: this job's documents are still needed until the
            # rows below are written; "Clear finished" leaves it until then.
            PROCESSING_STATUS.setdefault(processing_id, {})["records_state"] = True
            
            # Poll processing status until completed (max 10 minutes)
            max_attempts = 600  # 10 minutes at 1 second intervals
            attempt = 0
            
            while attempt < max_attempts:
                await asyncio.sleep(1)
                attempt += 1
                
                status_dict = PROCESSING_STATUS.get(processing_id, {})
                status = status_dict.get('status')
                
                if status == 'completed':
                    logger.info(f"Ingestion {processing_id} completed! Creating document_state records...")
                    
                    # Create a NEW state manager with its own connection pool for this background task
                    # Don't use incremental_manager.state_manager because its pool may be closed
                    state_mgr = new_state_manager(self.postgres_url)
                    await state_mgr.initialize()
                    
                    try:
                        # Create document states
                        created_count = await self._create_states(
                            state_mgr,
                            processing_id,
                            config_id,
                            paths,
                            data_source,
                            status_dict,
                            skip_graph,
                            graphs,
                        )
                        
                        logger.info(f"SUCCESS: Created {created_count} document_state records for config {config_id}")
                    
                    finally:
                        # Close the state manager's connection pool
                        await state_mgr.close()
                    
                    return
                    
                elif status == 'failed' or status == 'cancelled':
                    logger.info(f"Ingestion {processing_id} ended with status {status}, not creating document_state records")
                    return
            
            logger.warning(f"Timeout waiting for ingestion {processing_id} to complete (waited {max_attempts} seconds)")
            
        except Exception as e:
            logger.error(f"Error in background document_state creation: {e}")
            import traceback
            traceback.print_exc()
        finally:
            from backend import PROCESSING_STATUS as _ps
            if processing_id in _ps:
                _ps[processing_id]["state_recorded"] = True
    
    async def _create_states(
        self,
        state_mgr,
        processing_id: str,
        config_id: str,
        paths: List[str],
        data_source: str,
        status_dict: dict,
        skip_graph: Optional[bool] = None,
        graphs=None,
    ) -> int:
        """
        Create document_state records for all processed files.
        
        Returns:
            Number of document_state records created
        """
        from incremental_updates.state_manager import DocumentState, StateManager
        from incremental_updates.stores import new_config_manager

        # The run's graphs: prefer explicitly-passed ones so this can run BEFORE the
        # datasource_config row is registered (see main.py enable_sync ordering — state must exist
        # before the detector starts, or it re-ingests the just-ingested files). Fall back to the
        # datasource's.
        from graph_flags import GraphFlags
        if graphs is None and skip_graph is not None:
            graphs = GraphFlags.of(bool(skip_graph))
        if graphs is None:
            config_mgr = new_config_manager(self.postgres_url)
            await config_mgr.initialize()
            datasource_config = await config_mgr.get_config(config_id)
            await config_mgr.close()
            graphs = datasource_config.graphs if datasource_config else GraphFlags.defaults()
        
        # Only record a target as synced when a store is behind it (any can be "none" in .env),
        # so ingest status and removal see what is really in the stores.
        from config import Settings
        from incremental_updates.removal import configured_stores
        settings = Settings()
        stores = configured_stores(settings)

        # Extract processed files and their metadata
        processed_files, documents_dict = self._extract_processed_files(status_dict, paths)

        # The source system the job wrote its documents under (backend._process_documents_async):
        # with INCREMENTAL_STATE_STORE=openarch the state goes on those same documents, before
        # the datasource may be registered
        source_token = None
        if status_dict.get("source_system"):
            from openarch.source_system import use_source_system
            source_token = use_source_system(status_dict["source_system"])

        logger.info(f"Creating document_state for {len(processed_files)} files: {processed_files}")
        
        created_count = 0
        ingest_only: dict = {}  # config_id -> datasource is ingest-only
        config_mgr = None
        for filename in processed_files:
            try:
                logger.info(f"Creating state for: {filename}")
                
                # Extract source path (human-readable) and stable path (for doc_id)
                source_path, stable_path = self._extract_source_path(
                    filename,
                    data_source,
                    paths,
                    documents_dict
                )
                
                # Get modification timestamp and source_id from document metadata
                modified_timestamp, source_id = self._extract_metadata(
                    filename,
                    data_source,
                    documents_dict
                )
                
                # Generate stable doc_id using stable_path
                # For Alfresco/OneDrive/SharePoint: stable_path = alfresco://node_id or onedrive://file_id
                # For other sources: stable_path = source_path (same as display path)
                # source_path is the human-readable path (for display in UI)
                # A per-row run can ingest documents under different datasources (a row already
                # held by one is refreshed under it): each document's stable doc id names its own
                doc_config_id = config_id
                _doc = documents_dict.get(filename)
                _did = str(getattr(_doc, 'id_', '') or '') if _doc is not None else ''
                _colon = _did.find(':')
                if _colon > 1 and '-' in _did[:_colon]:
                    doc_config_id = _did[:_colon]
                doc_id = StateManager.make_doc_id(doc_config_id, stable_path)
                # A document of an ingest-only datasource is followed by no sync: auto_sync off
                # (a sync turns its rows on itself when it is registered, main.py)
                if doc_config_id not in ingest_only:
                    if config_mgr is None:
                        config_mgr = new_config_manager(self.postgres_url)
                        await config_mgr.initialize()
                    ingest_only[doc_config_id] = (await config_mgr.get_auto_sync(doc_config_id)) is False
                
                # Compute content hash based on data source
                content_hash = self._compute_content_hash(
                    filename,
                    data_source,
                    paths,
                    modified_timestamp
                )
                
                # Compute ordinal from modification timestamp
                ordinal = self._compute_ordinal(modified_timestamp)
                
                # Get current UTC time for sync timestamps
                now = datetime.now(timezone.utc)
                
                # Which graphs this document got -- per document when the run had a graph choice
                # per row (backend.run_item_actions marks each doc), else the run's
                doc = documents_dict.get(filename)
                meta = (getattr(doc, 'metadata', None) or {}) if doc is not None else {}
                if '_enabled_graph' in meta or '_enabled_rdf' in meta:
                    doc_graphs = GraphFlags(bool(meta.get('_enabled_graph')), bool(meta.get('_enabled_rdf')))
                elif meta.get('_skip_graph') is not None:
                    doc_graphs = GraphFlags.of(bool(meta['_skip_graph']), default=graphs)
                else:
                    doc_graphs = graphs
                built = doc_graphs.built(settings)
                graph_synced = now if built.graph else None
                rdf_synced = now if built.rdf else None
                logger.info(f"Document state sync timestamps: vector={now}, search={now}, "
                            f"graph={'synced' if graph_synced else 'null'}, rdf={'synced' if rdf_synced else 'null'}")
                
                # Create document state with all targets marked as synced
                state = DocumentState(
                    doc_id=doc_id,
                    config_id=doc_config_id,
                    source_path=source_path,
                    source_id=source_id,
                    ordinal=ordinal,
                    content_hash=content_hash,
                    modified_timestamp=modified_timestamp,
                    vector_synced_at=now if stores["vector"] else None,
                    search_synced_at=now if stores["search"] else None,
                    graph_synced_at=graph_synced,
                    rdf_synced_at=rdf_synced,
                    # per document when the run chose per row, else the run's own graphs
                    enabled_graph=doc_graphs.graph,
                    enabled_rdf=doc_graphs.rdf,
                    skip_graph=doc_graphs.none,
                    auto_sync=False if ingest_only.get(doc_config_id) else None,
                )
                
                await state_mgr.save_state(state)
                created_count += 1
                logger.info(f"Created document_state: {doc_id} (content_hash: {content_hash[:16] if content_hash else 'none'}...)")
                
            except Exception as e:
                logger.error(f"Error creating document_state for {filename}: {e}")

        if config_mgr is not None:
            await config_mgr.close()
        if source_token is not None:
            source_token.var.reset(source_token)
        return created_count
    
    def _extract_processed_files(self, status_dict: dict, paths: List[str]) -> tuple:
        """
        Extract processed files and their metadata from status dict.
        
        Returns:
            Tuple of (processed_files list, documents_dict mapping)
        """
        processed_files = []
        documents_dict = {}  # Map filename -> document for metadata extraction
        
        # Try to get documents from PROCESSING_STATUS
        if 'documents' in status_dict and status_dict['documents']:
            logger.info(f"Extracting filenames and metadata from {len(status_dict['documents'])} documents for document_state creation")
            for doc in status_dict['documents']:
                # Documents have stable doc_id format: config_id:filename where config_id is a UUID.
                # A bare ':' check is insufficient on Windows because drive paths (C:\...) also contain ':'.
                # Detect the stable format by checking that the part before the first ':' looks like a UUID
                # (36 chars with hyphens) rather than a single drive letter.
                doc_id_str = getattr(doc, 'id_', '') or ''
                colon_pos = doc_id_str.find(':')
                is_stable_doc_id = colon_pos > 1 and '-' in doc_id_str[:colon_pos]
                if is_stable_doc_id:
                    filename = doc_id_str.split(':', 1)[1]
                    processed_files.append(filename)
                    documents_dict[filename] = doc
                # Fallback: try metadata
                elif hasattr(doc, 'metadata') and 'file_name' in doc.metadata:
                    filename = doc.metadata['file_name']
                    processed_files.append(filename)
                    documents_dict[filename] = doc
                    logger.info(f"Extracted filename from metadata: {filename}")
        else:
            logger.warning(f"No documents found in PROCESSING_STATUS, falling back to alternative methods")
        
        # Fallback: extract from individual_files if available
        if not processed_files and 'individual_files' in status_dict and status_dict['individual_files']:
            for file_info in status_dict['individual_files']:
                if 'name' in file_info:
                    processed_files.append(file_info['name'])
        
        # Last resort: try to extract from paths, but skip directories
        if not processed_files:
            for file_path in paths:
                path_obj = Path(file_path)
                if path_obj.is_file():
                    processed_files.append(path_obj.name)
        
        return processed_files, documents_dict
    
    def _extract_source_path(
        self,
        filename: str,
        data_source: str,
        paths: List[str],
        documents_dict: dict
    ) -> tuple[str, str]:
        """
        Extract the correct source_path based on data source type.
        
        Returns:
            tuple: (human_readable_path, stable_path)
            - human_readable_path: For display in UI, logs, etc.
            - stable_path: For doc_id generation (stable across renames/moves)
            
        For most sources, both are the same.
        For Alfresco/OneDrive/SharePoint: stable_path uses object ID format.
        """
        source_path = filename
        stable_path = filename  # Default: same as source_path
        
        if data_source == "box":
            # For Box, construct path from path_collection + filename
            if filename in documents_dict:
                doc = documents_dict[filename]
                if hasattr(doc, 'metadata'):
                    path_collection = doc.metadata.get('path_collection', '')
                    file_name = doc.metadata.get('name', doc.metadata.get('file_name', ''))
                    if path_collection and file_name:
                        # Construct Box path: "All Files/sample-docs/cmispress.txt"
                        if not path_collection.endswith('/'):
                            path_collection += '/'
                        source_path = f"{path_collection}{file_name}"
                        logger.info(f"Box: Constructed source_path from metadata: {source_path}")
                    else:
                        # Fallback to just filename
                        source_path = file_name if file_name else filename
                        logger.warning(f"Box: Missing path_collection, using filename only: {source_path}")
            else:
                logger.warning(f"Box: Document not found in documents_dict, using filename: {filename}")
        
        elif data_source in ["alfresco", "cmis"]:
            # For Alfresco/CMIS:
            # - source_path (human-readable) = /Shared/GraphRAG/cmispress.txt (for display)
            # - stable_path (for doc_id) = alfresco://node_id (stable across renames/moves)
            if filename in documents_dict:
                doc = documents_dict[filename]
                if hasattr(doc, 'metadata'):
                    # Get human-readable file_path for source_path (display)
                    file_path = doc.metadata.get('file_path', filename)
                    source_path = file_path
                    
                    # Get stable_file_path for doc_id (identity)
                    stable_file_path = doc.metadata.get('stable_file_path')
                    if stable_file_path:
                        stable_path = stable_file_path
                        logger.info(f"Alfresco: source_path={source_path}, stable_path={stable_path}")
                    elif data_source == "cmis" and doc.metadata.get('cmis_id'):
                        # the repository's object id, as ingest_from_source names it
                        stable_path = f"cmis://{doc.metadata['cmis_id']}"
                        logger.info(f"CMIS: source_path={source_path}, stable_path={stable_path}")
                    else:
                        # Fallback: construct from alfresco_id
                        alfresco_id = doc.metadata.get('alfresco_id')
                        if alfresco_id:
                            stable_path = f"alfresco://{alfresco_id}"
                            logger.info(f"Alfresco: source_path={source_path}, constructed stable_path={stable_path}")
                        else:
                            # Last resort: use file_path for both (old behavior)
                            stable_path = file_path
                            logger.warning(f"Alfresco: No stable_file_path or alfresco_id, using file_path for both: {stable_path}")
                else:
                    logger.warning(f"Alfresco: Document has no metadata, using filename: {filename}")
            else:
                logger.warning(f"Alfresco: Document not found in documents_dict, using filename: {filename}")
        
        elif data_source == "nuxeo":
            # For Nuxeo:
            # - source_path (human-readable) = /default-domain/workspaces/.../file (display)
            # - stable_path (for doc_id) = nuxeo://uid (stable across renames/moves)
            if filename in documents_dict:
                doc = documents_dict[filename]
                if hasattr(doc, 'metadata'):
                    file_path = doc.metadata.get('file_path', filename)
                    source_path = file_path
                    stable_file_path = doc.metadata.get('stable_file_path')
                    if stable_file_path:
                        stable_path = stable_file_path
                    else:
                        nuxeo_id = doc.metadata.get('nuxeo_id')
                        stable_path = f"nuxeo://{nuxeo_id}" if nuxeo_id else file_path
                    logger.info(f"Nuxeo: source_path={source_path}, stable_path={stable_path}")

        elif data_source == "s3":
            # For S3, filename is already the key (from S3 events or metadata)
            source_path = filename
            logger.info(f"S3: Using key as source_path: {source_path}")
        
        elif data_source == "azure_blob":
            # For Azure Blob, extract container and blob name from metadata
            if filename in documents_dict:
                doc = documents_dict[filename]
                if hasattr(doc, 'metadata'):
                    container_name = doc.metadata.get('container', doc.metadata.get('container_name', ''))
                    blob_name = doc.metadata.get('name', '')  # 'name' is the blob name
                    if container_name and blob_name:
                        source_path = f"{container_name}/{blob_name}"
                        logger.info(f"Azure Blob: Constructed source_path from metadata: {source_path}")
                    else:
                        logger.warning(f"Azure Blob: Missing container or blob name in metadata, using filename: {filename}")
            else:
                logger.warning(f"Azure Blob: Document not found in documents_dict, using filename: {filename}")
        
        elif data_source == "gcs":
            # For GCS initial ingest, filename already contains the full path (bucket/object_key)
            # This is because GCSReader returns file_path with bucket prefix included
            # Just use filename as-is
            source_path = filename
            logger.info(f"GCS: Using filename as source_path: {source_path}")
        
        elif data_source == "google_drive":
            # For Google Drive:
            # - source_path (human-readable) = filename or path (for display)
            # - stable_path (for doc_id) = file_id (stable across renames/moves)
            if filename in documents_dict:
                doc = documents_dict[filename]
                if hasattr(doc, 'metadata'):
                    # Get human-readable path for source_path (display)
                    # GoogleDriveReader provides 'file path' (with space) in metadata
                    source_path = doc.metadata.get('file path') or doc.metadata.get('file_name') or filename
                    
                    # Get stable file_id for doc_id (identity)
                    stable_path = doc.metadata.get('file id') or source_path
                    
                    logger.info(f"Google Drive: source_path={source_path}, stable_path={stable_path}")
        
        elif data_source in ["onedrive", "sharepoint"]:
            # For OneDrive/SharePoint:
            # - source_path (human-readable) = /test/cmispress.txt (for display)
            # - stable_path (for doc_id) = onedrive://file_id (stable across renames/moves)
            if filename in documents_dict:
                doc = documents_dict[filename]
                if hasattr(doc, 'metadata'):
                    # Prefer the source's human_file_path (e.g. "/test/cmispress.txt"), matching the
                    # alfresco/cmis/box/azure branches which all store a human-readable PATH.
                    # This used to store the bare file_name ("OneDrive doesn't provide reliable folder
                    # paths") — no longer true: OneDriveSource/SharePointSource both set human_file_path,
                    # and the incremental delta stream reports the same shape, so both ingest paths now
                    # agree. NOTE: do NOT fall back to metadata['file_path'] — during processing that can
                    # hold the local TEMP path (e.g. C:\...\Temp\tmp32raz2xv.txt).
                    source_path = (
                        doc.metadata.get('human_file_path')
                        or doc.metadata.get('file_name')
                        or filename
                    )
                    
                    # Get stable file_id path for doc_id (identity)
                    stable_file_path = doc.metadata.get('stable_file_path')
                    if stable_file_path:
                        stable_path = stable_file_path
                    else:
                        # Fallback: construct from file_id
                        file_id = doc.metadata.get('file_id')
                        if file_id:
                            prefix = "sharepoint" if data_source == "sharepoint" else "onedrive"
                            stable_path = f"{prefix}://{file_id}"
                        else:
                            stable_path = source_path
                    
                    logger.info(f"{data_source.title()}: source_path={source_path}, stable_path={stable_path}")
        
        # For filesystem and others, source_path and stable_path are the same.
        # Normalize the stable_path on Windows so that the stored doc_id matches the
        # lowercase paths produced by the filesystem detector (normalize_filesystem_path).
        # Without this, an initial REST ingest stores "C:\..." but the detector compares
        # "c:\..." → false "deleted" detection → phantom delete+re-ingest cycle every sync.
        #
        # ONLY filesystem/local: normalize_filesystem_path runs os.path.normpath (flips '/'→'\'
        # on Windows) + lowercases. Cloud sources (gcs/s3/azure/box, CMIS repo paths, and Drive's
        # case-sensitive file IDs) use forward slashes and must NOT be mangled — doing so made the
        # initial-ingest doc_id "config_id:bucket\a\b.txt" while the sync path kept
        # "config_id:bucket/a/b.txt", so the sync never matched and wrote a DUPLICATE document_state
        # (Windows-only; indexes were unaffected since ingest-side ids stay forward-slashed).
        if data_source in ("filesystem", "local"):
            try:
                from incremental_updates.path_utils import normalize_filesystem_path
                stable_path = normalize_filesystem_path(stable_path)
                source_path = normalize_filesystem_path(source_path)
            except Exception:
                pass
        return source_path, stable_path
    
    def _extract_metadata(
        self,
        filename: str,
        data_source: str,
        documents_dict: dict
    ) -> tuple:
        """
        Extract modification timestamp and source_id from document metadata.
        
        Returns:
            Tuple of (modified_timestamp, source_id)
        """
        modified_timestamp = None
        source_id = None
        
        if filename not in documents_dict:
            return modified_timestamp, source_id
        
        doc = documents_dict[filename]
        if not hasattr(doc, 'metadata'):
            return modified_timestamp, source_id
        
        # Log all metadata keys for debugging
        logger.info(f"DEBUG: Document metadata keys for {filename}: {list(doc.metadata.keys())}")
        
        # Extract modification timestamp
        timestamp_fields = [
            'modified_at',
            'modified at',  # Google Drive
            'last_modified_datetime',  # OneDrive/SharePoint
            'last_modified_date',  # GCS and Azure
            'modified',
            'last_modified'
        ]
        
        for field in timestamp_fields:
            if field in doc.metadata:
                raw_timestamp = doc.metadata[field]
                logger.info(f"Extracted modification timestamp: {raw_timestamp}")
                
                # Convert string timestamp to datetime object if needed
                if raw_timestamp:
                    if isinstance(raw_timestamp, str):
                        try:
                            from dateutil import parser as dateutil_parser
                            modified_timestamp = dateutil_parser.parse(raw_timestamp)
                            logger.info(f"Parsed timestamp string to datetime: {modified_timestamp}")
                        except Exception as e:
                            logger.warning(f"Could not parse timestamp '{raw_timestamp}': {e}. Keeping as string.")
                            modified_timestamp = raw_timestamp
                    else:
                        # Already a datetime object
                        modified_timestamp = raw_timestamp
                break
        
        # Extract source_id for cloud sources
        source_id_fields = [
            ('box_file_id', 'box_file_id'),  # Box
            ('file id', 'file id'),  # Google Drive
            ('file_id', 'file_id'),  # OneDrive/SharePoint
            ('alfresco_id', 'alfresco_id'),
            ('nuxeo_id', 'nuxeo_id'),
            ('node_id', 'node_id'),
            ('s3_uri', 's3_uri'),  # S3 - prefer full URI
            ('s3_key', 's3_key'),
        ]
        
        for field, name in source_id_fields:
            if field in doc.metadata:
                raw_value = doc.metadata[field]
                
                # For OneDrive/SharePoint, add prefix if not already present
                if field == 'file_id' and data_source in ['onedrive', 'sharepoint']:
                    if not raw_value.startswith(('onedrive://', 'sharepoint://')):
                        prefix = "sharepoint" if data_source == "sharepoint" else "onedrive"
                        source_id = f"{prefix}://{raw_value}"
                        logger.info(f"Extracted source_id ({name}): {source_id}")
                    else:
                        source_id = raw_value
                        logger.info(f"Extracted source_id ({name}): {source_id}")
                else:
                    source_id = raw_value
                    logger.info(f"Extracted source_id ({name}): {source_id}")
                
                return modified_timestamp, source_id
        
        # For Azure Blob, construct source_id from container + blob name
        if data_source == 'azure_blob':
            container_name = doc.metadata.get('container', doc.metadata.get('container_name', ''))
            blob_name = doc.metadata.get('name', '')
            if container_name and blob_name:
                source_id = f"{container_name}/{blob_name}"
                logger.info(f"Extracted source_id (Azure Blob): {source_id}")
                return modified_timestamp, source_id
        
        # For GCS, use the filename as source_id (it already contains bucket/object_key)
        if data_source == 'gcs':
            # The filename extracted from doc_id is already bucket/object_key format
            # Just use it as source_id
            source_id = filename
            logger.info(f"Extracted source_id (GCS): {source_id}")
            return modified_timestamp, source_id
        
        # For filesystem, use file_path as source_id — normalized to lowercase on Windows
        # so that it matches what the filesystem detector produces via normalize_filesystem_path().
        if 'file_path' in doc.metadata and data_source == 'filesystem':
            raw_path = doc.metadata['file_path']
            try:
                from incremental_updates.path_utils import normalize_filesystem_path
                source_id = normalize_filesystem_path(raw_path)
            except Exception:
                source_id = raw_path
            logger.info(f"Extracted source_id (file_path): {source_id}")
        else:
            logger.info(f"DEBUG: source_id not found in metadata")
        
        return modified_timestamp, source_id
    
    def _compute_content_hash(
        self,
        filename: str,
        data_source: str,
        paths: List[str],
        modified_timestamp: Union[datetime, str, None]
    ) -> str:
        """
        Compute content hash based on data source.
        
        For filesystem: Hash of actual file content
        For cloud sources: Hash of modification timestamp (more efficient)
        """
        from incremental_updates.state_manager import StateManager
        
        if data_source == "filesystem" and paths:
            # For filesystem, read local file to compute hash
            file_to_read = None
            filename_path = Path(filename)
            if filename_path.is_file() and (
                filename_path.is_absolute() or any(Path(p) == filename_path for p in paths)
            ):
                # filename is usually the path itself (the filesystem source_id): absolute, or
                # exactly one of the (possibly relative) input paths -- not a bare name
                file_to_read = filename_path
            else:
                for input_path in paths:
                    input_path_obj = Path(input_path)
                    if input_path_obj.is_dir():
                        # Check if file is in this directory
                        potential_file = input_path_obj / filename
                        if potential_file.exists():
                            file_to_read = potential_file
                            break
                    elif input_path_obj.is_file() and input_path_obj.name == filename:
                        file_to_read = input_path_obj
                        break
            
            if file_to_read and file_to_read.exists():
                # Read file content to compute hash
                with open(file_to_read, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                content_hash = StateManager.compute_content_hash(content)
                logger.info(f"Filesystem: Computed content_hash: {content_hash[:16]}...")
                return content_hash
            else:
                logger.warning(f"File not found when creating state: {filename}, using empty hash")
                return StateManager.compute_content_hash("")
        
        else:
            # For non-filesystem sources (Alfresco, S3, Azure, GCS, etc.)
            # Use modification timestamp for change detection (more efficient)
            if modified_timestamp:
                content_hash = StateManager.compute_content_hash(str(modified_timestamp))
                logger.info(f"Using timestamp-based hash for change detection: {modified_timestamp}")
                return content_hash
            else:
                # No timestamp available - use empty hash as placeholder
                logger.info(f"No modification timestamp available, using placeholder hash")
                return StateManager.compute_content_hash("")
    
    def _compute_ordinal(self, modified_timestamp: Union[datetime, str, None]) -> int:
        """
        Compute ordinal (microseconds since epoch) from modification timestamp.
        Falls back to current time if timestamp is unavailable.
        """
        ordinal = int(time.time() * 1_000_000)
        
        if modified_timestamp:
            try:
                # modified_timestamp is already a datetime object (from metadata)
                # or a string that needs parsing
                if isinstance(modified_timestamp, str):
                    from dateutil import parser as dateutil_parser
                    dt = dateutil_parser.parse(modified_timestamp)
                else:
                    dt = modified_timestamp
                
                ordinal = int(dt.timestamp() * 1_000_000)
                logger.info(f"Using file modification timestamp for ordinal: {modified_timestamp} -> {ordinal}")
            except Exception as e:
                logger.warning(f"Could not parse modification timestamp '{modified_timestamp}': {e}. Using current time.")
                ordinal = int(time.time() * 1_000_000)
        
        return ordinal
