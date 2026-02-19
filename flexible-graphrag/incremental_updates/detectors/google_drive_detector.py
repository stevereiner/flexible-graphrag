"""
Google Drive Change Detector

Real-time Google Drive change detection using Push Notifications (Watch API).
Supports both event-based (webhooks) and periodic (Changes API polling) modes.
"""

import asyncio
import json
import logging
import ssl
from datetime import datetime, timezone
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata

logger = logging.getLogger("flexible_graphrag.incremental.detectors.google_drive")

# ---------------------------------------------------------------------------
# Google API Integration
# ---------------------------------------------------------------------------

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    HttpError = Exception
    logger.warning("google-api-python-client not installed - Google Drive change detection unavailable")


# ---------------------------------------------------------------------------
# Google Drive Detector
# ---------------------------------------------------------------------------

class GoogleDriveDetector(ChangeDetector):
    """
    Google Drive change detector using Changes API (polling mode).
    
    Features:
    - Changes API polling for incremental updates
    - Page token tracking for efficient change detection
    - Automatic retry with exponential backoff
    - Proper error handling and logging
    - Supports both service account and OAuth credentials
    - **NEW**: Uses backend for ADD/MODIFY events (full DocumentProcessor pipeline)
    
    Note: Push notifications (webhooks) require a public HTTPS endpoint and
    domain verification, which is complex to set up. This implementation uses
    the Changes API with polling, which is simpler and more reliable for most cases.
    
    Configuration:
        folder_id: Google Drive folder ID to monitor (optional, monitors all files if not set)
        credentials: Service account credentials dict (optional)
        credentials_path: Path to service account credentials JSON (optional)
        token_path: Path to OAuth token JSON (optional)
        polling_interval: Seconds between change checks (default: 60)
        recursive: Monitor subfolders recursively (default: True)
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # Configuration
        self.folder_id = config.get('folder_id', '')  # Empty = root
        self.recursive = config.get('recursive', True)
        self.polling_interval = config.get('polling_interval', 60)
        
        # Store config_id for backend calls
        self.config_id = config.get('config_id')
        
        # Handle credentials from UI form (JSON string) - match working data source pattern
        credentials_str = config.get('credentials', '')
        self.service_account_key = None
        
        if credentials_str:
            try:
                # Parse JSON credentials from UI form (same as google_drive.py data source)
                self.service_account_key = json.loads(credentials_str)
                logger.info("Parsed service account credentials from JSON string")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in credentials: {e}")
                # Don't raise - allow fallback to file-based credentials
                logger.warning("Falling back to file-based credentials")
        
        # Fallback to file-based credentials
        self.credentials_path = config.get('credentials_path')
        self.token_path = config.get('token_path')
        
        # Drive API client
        self.drive_service = None
        
        # Change tracking
        self.page_token = None  # Start token for change detection
        self.folder_cache = {}  # Cache of folder IDs we're monitoring
        self.known_file_ids = set()  # Track file IDs we've seen before (for CREATE vs MODIFY detection)
        
        # Backend reference (will be injected by orchestrator)
        self.backend = None
        self.state_manager = None  # Will be injected
        
        # Statistics
        self.events_processed = 0
        self.errors_count = 0
        
        logger.info(f"GoogleDriveDetector initialized - folder_id={self.folder_id or '(root)'}, "
                   f"recursive={self.recursive}, polling_interval={self.polling_interval}s")
    
    def _create_drive_service(self):
        """Create Google Drive API service with credentials"""
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        
        creds = None
        
        if self.service_account_key:
            # Use service account key dict (already parsed in __init__)
            creds = service_account.Credentials.from_service_account_info(
                self.service_account_key,
                scopes=SCOPES
            )
        elif self.credentials_path:
            # Use service account key file
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )
        elif self.token_path:
            # Use OAuth token file
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        else:
            raise ValueError("Google Drive credentials required: provide credentials, credentials_path, or token_path")
        
        return build('drive', 'v3', credentials=creds)
    
    async def start(self):
        """Start Google Drive detector and initialize API client"""
        if not GOOGLE_DRIVE_AVAILABLE:
            logger.error("Cannot start Google Drive detector - google-api-python-client not installed")
            raise ImportError("google-api-python-client library required")
        
        self._running = True
        
        try:
            # Create Drive API service
            self.drive_service = self._create_drive_service()
            
            # Verify access and get start token
            await self._initialize_change_tracking()
            
            logger.info(f"Google Drive detector started successfully for folder: {self.folder_id or '(root)'}")
            logger.info(f"Using Changes API with {self.polling_interval}s polling interval")
            
        except Exception as e:
            self._running = False
            logger.error(f"Failed to start Google Drive detector: {e}")
            raise
    
    async def _initialize_change_tracking(self):
        """Initialize change tracking by getting start page token and known files"""
        try:
            # Build folder cache first if monitoring specific folder
            if self.folder_id:
                await self._build_folder_cache()
            
            # Populate known_file_ids with all existing files FIRST
            # This ensures we know what files exist before we start tracking changes
            await self._populate_known_files()
            
            # THEN get the start page token for future changes
            # This way we don't miss any changes that happen during the file listing
            response = await asyncio.to_thread(
                self.drive_service.changes().getStartPageToken().execute
            )
            self.page_token = response.get('startPageToken')
            
            logger.info(f"Google Drive change tracking initialized with page token: {self.page_token}")
            
        except HttpError as e:
            logger.error(f"Error initializing Google Drive change tracking: {e}")
            raise
    
    async def _populate_known_files(self):
        """Populate known_file_ids set with all currently existing files"""
        try:
            logger.info("POPULATE: Starting to populate known_file_ids...")
            
            # List all files to populate known_file_ids
            all_files = await self.list_all_files()
            for file_meta in all_files:
                file_id = file_meta.extra.get('file_id')
                if file_id:
                    self.known_file_ids.add(file_id)
            
            logger.info(f"POPULATE: Populated known_file_ids with {len(self.known_file_ids)} existing files")
            
            # Always log the file IDs (for debugging, helpful for small sets)
            if len(self.known_file_ids) <= 20:
                logger.info(f"POPULATE: known_file_ids = {self.known_file_ids}")
            else:
                logger.info(f"POPULATE: known_file_ids has {len(self.known_file_ids)} entries (too many to log)")
                
        except Exception as e:
            logger.error(f"Error populating known_file_ids: {e}")
            # Don't raise - allow detector to continue with empty set
            
        except Exception as e:
            logger.warning(f"Error populating known files: {e}")
    
    async def _build_folder_cache(self):
        """Build cache of folder IDs we're monitoring (for recursive filtering)"""
        if not self.folder_id:
            return
        
        try:
            self.folder_cache = {self.folder_id: True}
            
            if self.recursive:
                # Find all subfolders recursively
                query = f"'{self.folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
                
                page_token = None
                while True:
                    response = await asyncio.to_thread(
                        self.drive_service.files().list(
                            q=query,
                            spaces='drive',
                            fields='nextPageToken, files(id, name)',
                            pageToken=page_token,
                            supportsAllDrives=True,
                            includeItemsFromAllDrives=True
                        ).execute
                    )
                    
                    for folder in response.get('files', []):
                        self.folder_cache[folder['id']] = True
                    
                    page_token = response.get('nextPageToken')
                    if not page_token:
                        break
                
                logger.info(f"Built folder cache with {len(self.folder_cache)} folders")
            
        except HttpError as e:
            logger.warning(f"Error building folder cache: {e}")
    
    async def stop(self):
        """Stop Google Drive detector"""
        self._running = False
        self.drive_service = None
        
        logger.info(f"Google Drive detector stopped. Events processed: {self.events_processed}, Errors: {self.errors_count}")
    
    async def list_all_files(self) -> List[FileMetadata]:
        """List all files in the monitored folder (for initial/periodic sync)"""
        if not self.drive_service:
            raise RuntimeError("Google Drive detector not started")
        
        files = []
        try:
            # Build query
            query_parts = []
            
            if self.folder_id:
                query_parts.append(f"'{self.folder_id}' in parents")
            
            # Exclude folders and trashed files
            query_parts.append("mimeType != 'application/vnd.google-apps.folder'")
            query_parts.append("trashed = false")
            
            query = ' and '.join(query_parts)
            
            # List files
            page_token = None
            while True:
                response = await asyncio.to_thread(
                    self.drive_service.files().list(
                        q=query,
                        spaces='drive',
                        fields='nextPageToken, files(id, name, mimeType, modifiedTime, size, parents)',
                        pageToken=page_token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True
                    ).execute
                )
                
                for file in response.get('files', []):
                    # Skip if not in monitored folders (when recursive)
                    if self.folder_id and not self._is_file_in_monitored_folder(file):
                        continue
                    
                    metadata = self._file_to_metadata(file)
                    if metadata:
                        files.append(metadata)
                
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            
            logger.info(f"Listed {len(files)} files from Google Drive")
            
        except HttpError as e:
            logger.error(f"Error listing Google Drive files: {e}")
            self.errors_count += 1
            raise
        
        return files
    
    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """
        Stream change events from Google Drive Changes API (polling).
        
        NEW BEHAVIOR:
        - For CREATE: Process via backend directly (full DocumentProcessor pipeline)
        - For UPDATE (MODIFY): Emit DELETE with callback, callback processes ADD after DELETE completes
        - For DELETE: Yield event for engine to handle
        
        This ensures ADD/MODIFY use DocumentProcessor for ALL file types (PDF, DOCX, etc.)
        """
        if not self._running or not self.drive_service:
            return
        
        logger.info("Starting Google Drive Changes API monitoring...")
        
        while self._running:
            try:
                # Poll for changes
                page_token = self.page_token
                
                while page_token:
                    response = await asyncio.to_thread(
                        self.drive_service.changes().list(
                            pageToken=page_token,
                            spaces='drive',
                            fields='nextPageToken, newStartPageToken, changes(removed, fileId, file(id, name, mimeType, modifiedTime, size, parents, trashed, createdTime))',
                            includeItemsFromAllDrives=True,
                            supportsAllDrives=True
                        ).execute
                    )
                    
                    # Process changes
                    for change in response.get('changes', []):
                        event = self._parse_change(change)
                        if event:
                            self.events_processed += 1
                            
                            # Safety check: populate known_file_ids on first event if not yet done
                            if self.events_processed == 1 and len(self.known_file_ids) == 0:
                                logger.warning("SAFETY CHECK: known_file_ids is empty on first event - populating now...")
                                await self._populate_known_files()
                                logger.info(f"SAFETY CHECK: Populated known_file_ids with {len(self.known_file_ids)} files")
                                if len(self.known_file_ids) <= 10:
                                    logger.info(f"SAFETY CHECK: known_file_ids = {self.known_file_ids}")
                            
                            # Handle DELETE events - emit for engine to process and remove from known_file_ids
                            if event.change_type == ChangeType.DELETE:
                                file_id = event.metadata.extra.get('file_id')
                                if file_id and file_id in self.known_file_ids:
                                    self.known_file_ids.discard(file_id)  # Remove from known files
                                yield event
                            
                            # Handle CREATE events - check known_file_ids to confirm it's truly new
                            elif event.change_type == ChangeType.CREATE:
                                file_id = event.metadata.extra.get('file_id')
                                file_name = event.metadata.path
                                
                                if file_id:
                                    # Check if file is already known (simple and fast)
                                    is_new = file_id not in self.known_file_ids
                                    
                                    logger.info(f"CREATE/MODIFY check for {file_name}: file_id={file_id}, is_new={is_new}, known_file_ids_count={len(self.known_file_ids)}")
                                    if len(self.known_file_ids) <= 5:
                                        logger.info(f"  known_file_ids: {self.known_file_ids}")
                                    
                                    if is_new:
                                        # Truly new file - CREATE
                                        logger.info(f"EVENT: CREATE detected for {file_name} (new file_id)")
                                        self.known_file_ids.add(file_id)  # Add to known files
                                        try:
                                            await self._process_via_backend(file_id, file_name)
                                            logger.info(f"SUCCESS: Processed {file_name} via backend pipeline")
                                        except Exception as e:
                                            logger.error(f"ERROR: Failed to process {file_name} via backend: {e}")
                                    else:
                                        # Already known - treat as MODIFY (DELETE + ADD)
                                        logger.info(f"EVENT: MODIFY detected for {file_name} (known file_id)")
                                        logger.info(f"MODIFY: Emitting DELETE event with callback for {file_name}")
                                        
                                        async def add_callback():
                                            logger.info(f"MODIFY: DELETE completed, now processing ADD for {file_name}")
                                            try:
                                                await self._process_via_backend(file_id, file_name)
                                                logger.info(f"SUCCESS: MODIFY completed for {file_name}")
                                            except Exception as e:
                                                logger.error(f"ERROR: Failed to process ADD for {file_name}: {e}")
                                        
                                        delete_metadata = FileMetadata(
                                            source_type='google_drive',
                                            path=file_id,
                                            ordinal=event.metadata.ordinal,
                                            extra={'file_id': file_id}
                                        )
                                        delete_event = ChangeEvent(
                                            metadata=delete_metadata,
                                            change_type=ChangeType.DELETE,
                                            timestamp=event.timestamp,
                                            is_modify_delete=True,
                                            modify_callback=add_callback
                                        )
                                        yield delete_event
                                else:
                                    logger.warning(f"SKIP: No file_id for {file_name}")
                            
                            # Handle UPDATE (MODIFY) events - DELETE first, then ADD via callback
                            elif event.change_type == ChangeType.UPDATE:
                                file_id = event.metadata.extra.get('file_id')
                                file_name = event.metadata.path
                                
                                if file_id:
                                    # Check if file is already known (might be false positive UPDATE)
                                    is_new = file_id not in self.known_file_ids
                                    
                                    logger.info(f"UPDATE event for {file_name}: file_id={file_id}, is_new={is_new}, known_file_ids_count={len(self.known_file_ids)}")
                                    if len(self.known_file_ids) <= 5:
                                        logger.info(f"  known_file_ids: {self.known_file_ids}")
                                    
                                    if is_new:
                                        # Truly new file - treat as CREATE (not MODIFY)
                                        logger.info(f"EVENT: CREATE detected for {file_name} (new file_id, reported as UPDATE)")
                                        self.known_file_ids.add(file_id)  # Add to known files
                                        try:
                                            await self._process_via_backend(file_id, file_name)
                                            logger.info(f"SUCCESS: Processed {file_name} via backend pipeline")
                                        except Exception as e:
                                            logger.error(f"ERROR: Failed to process {file_name} via backend: {e}")
                                    else:
                                        # Already known - true MODIFY (DELETE + ADD)
                                        logger.info(f"EVENT: MODIFY detected for {file_name}")
                                        logger.info(f"MODIFY: Emitting DELETE event with callback for {file_name}")
                                        
                                        # Create callback for ADD operation (to be called after DELETE completes)
                                        async def add_callback():
                                            logger.info(f"MODIFY: DELETE completed, now processing ADD for {file_name}")
                                            try:
                                                await self._process_via_backend(file_id, file_name)
                                                logger.info(f"SUCCESS: MODIFY completed for {file_name}")
                                            except Exception as e:
                                                logger.error(f"ERROR: Failed to process ADD for {file_name}: {e}")
                                        
                                        # Create DELETE event with callback
                                        delete_metadata = FileMetadata(
                                            source_type='google_drive',
                                            path=file_id,  # Use file ID as path
                                            ordinal=event.metadata.ordinal,
                                            extra={'file_id': file_id}
                                        )
                                        delete_event = ChangeEvent(
                                            metadata=delete_metadata,
                                            change_type=ChangeType.DELETE,
                                            timestamp=event.timestamp,
                                            is_modify_delete=True,  # Mark as part of MODIFY
                                            modify_callback=add_callback  # Callback for ADD
                                        )
                                        yield delete_event
                                else:
                                    logger.warning(f"SKIP: No file_id for {file_name}")
                    
                    # Update page token
                    if 'newStartPageToken' in response:
                        self.page_token = response['newStartPageToken']
                        page_token = None
                    else:
                        page_token = response.get('nextPageToken')
                
                # Wait before next poll
                await asyncio.sleep(self.polling_interval)
                
            except HttpError as e:
                logger.error(f"Error polling Google Drive changes: {e}")
                self.errors_count += 1
                await asyncio.sleep(self.polling_interval)
            
            except Exception as e:
                logger.error(f"Unexpected error in Google Drive changes: {e}")
                self.errors_count += 1
                await asyncio.sleep(self.polling_interval)
    
    def _is_file_in_monitored_folder(self, file: Dict) -> bool:
        """Check if file is in a monitored folder"""
        if not self.folder_id:
            return True  # Monitoring all files
        
        parents = file.get('parents', [])
        for parent_id in parents:
            if parent_id in self.folder_cache:
                return True
        
        return False
    
    def _parse_change(self, change: Dict) -> Optional[ChangeEvent]:
        """Parse Google Drive change into ChangeEvent"""
        try:
            # Check if file was removed or trashed
            if change.get('removed') or change.get('file', {}).get('trashed'):
                change_type = ChangeType.DELETE
                file_id = change.get('fileId')
                
                # For deletions, we have limited metadata
                metadata = FileMetadata(
                    source_type='google_drive',
                    path=file_id,  # Use file ID as path for deletions
                    ordinal=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
                    extra={'file_id': file_id}
                )
                
                return ChangeEvent(
                    metadata=metadata,
                    change_type=change_type,
                    timestamp=datetime.now(timezone.utc)
                )
            
            # Regular file change
            file = change.get('file')
            if not file:
                return None
            
            # Skip folders
            if file.get('mimeType') == 'application/vnd.google-apps.folder':
                return None
            
            # Skip if not in monitored folders
            if self.folder_id and not self._is_file_in_monitored_folder(file):
                return None
            
            # Determine if CREATE or UPDATE by comparing timestamps
            created_time_str = file.get('createdTime')
            modified_time_str = file.get('modifiedTime')
            
            change_type = ChangeType.UPDATE  # Default
            
            if created_time_str and modified_time_str:
                try:
                    created = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                    modified = datetime.fromisoformat(modified_time_str.replace('Z', '+00:00'))
                    
                    # If created and modified are within 5 seconds, consider it a CREATE
                    time_diff = abs((modified - created).total_seconds())
                    if time_diff < 5:
                        change_type = ChangeType.CREATE
                        logger.debug(f"CREATE detected: {file.get('name')} (time_diff={time_diff}s)")
                    else:
                        logger.debug(f"UPDATE detected: {file.get('name')} (time_diff={time_diff}s)")
                except Exception as e:
                    logger.debug(f"Error parsing timestamps: {e}")
            
            # Convert to metadata
            metadata = self._file_to_metadata(file)
            if not metadata:
                return None
            
            # Parse modified time
            if modified_time_str:
                modified_time = datetime.fromisoformat(modified_time_str.replace('Z', '+00:00'))
            else:
                modified_time = datetime.now(timezone.utc)
            
            return ChangeEvent(
                metadata=metadata,
                change_type=change_type,
                timestamp=modified_time
            )
            
        except Exception as e:
            logger.warning(f"Error parsing Google Drive change: {e}")
            return None
    
    def _file_to_metadata(self, file: Dict) -> Optional[FileMetadata]:
        """Convert Google Drive file to FileMetadata"""
        try:
            # Parse modified time
            modified_time_str = file.get('modifiedTime')
            if modified_time_str:
                modified_time = datetime.fromisoformat(modified_time_str.replace('Z', '+00:00'))
            else:
                modified_time = datetime.now(timezone.utc)
            
            ordinal = int(modified_time.timestamp() * 1_000_000)
            
            # For Google Drive, use file_id as path (stable across renames/moves)
            # This matches what we use in hybrid_system.py for doc_id generation
            file_id = file.get('id')
            file_name = file.get('name', file_id)
            
            # Build full path from parent folders (for display purposes)
            # Note: This is best-effort - GoogleDriveReader provides better paths during actual download
            file_path = file_name  # Default to just filename
            parents = file.get('parents', [])
            
            # If monitoring a specific folder and file is in that folder, construct relative path
            if self.folder_id and parents and self.folder_id in parents:
                # File is directly in monitored folder
                file_path = file_name
            
            return FileMetadata(
                source_type='google_drive',
                path=file_id,  # Use file_id as path for stability
                ordinal=ordinal,
                size_bytes=int(file.get('size', 0)) if file.get('size') else None,
                mime_type=file.get('mimeType'),
                modified_timestamp=modified_time.isoformat(),
                extra={
                    'file_id': file_id,
                    'file_name': file_name,  # Store name for logging/display
                    'file_path': file_path,  # Store best-effort path
                    'parents': parents,
                }
            )
            
        except Exception as e:
            logger.warning(f"Error converting Google Drive file to metadata: {e}")
            return None
    
    async def _process_via_backend(self, file_id: str, filename: str):
        """
        Process file by calling backend._process_documents_async() directly.
        This is the SAME code path the UI uses, but without REST API overhead.
        
        Goes through the complete pipeline:
        - GoogleDriveReader → PassthroughExtractor → DocumentProcessor (Docling/LlamaParse)
        - HybridSystem → vector/search/graph indexes
        - main.py → document_state creation
        
        Args:
            file_id: Google Drive file ID
            filename: File name for logging
        """
        if not self.backend:
            logger.error("Backend not injected into GoogleDriveDetector - cannot process file")
            return
        
        logger.info(f"Processing {filename} via backend (full pipeline)")
        
        try:
            # Use injected skip_graph (set by orchestrator)
            skip_graph = getattr(self, 'skip_graph', False)
            
            # Create processing ID
            processing_id = f"incremental_{file_id[:8]}"
            
            # Convert credentials dict back to JSON string (datasource expects string)
            credentials_json = json.dumps(self.service_account_key) if self.service_account_key else None
            
            # Call backend method directly (skips REST API layer)
            # This goes through the EXACT same pipeline as UI
            await self.backend._process_documents_async(
                processing_id=processing_id,
                data_source='google_drive',
                config_id=self.config_id,
                skip_graph=skip_graph,
                google_drive_config={
                    'credentials': credentials_json,  # Pass as JSON string
                    'file_ids': [file_id],  # Process just this one file
                    'folder_id': None,
                    'query': ''
                }
            )
            
            logger.info(f"Successfully processed {filename} via backend pipeline")
            
            # Create document_state record after successful processing
            # This is needed because incremental processing bypasses the /api/ingest endpoint
            # which would normally trigger the background task
            if self.state_manager:
                try:
                    await self._create_document_state_from_processing_status(processing_id, filename, file_id)
                except Exception as e:
                    logger.error(f"Failed to create document_state for {filename}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process {filename} via backend: {e}")
            raise
    
    async def _create_document_state_from_processing_status(self, processing_id: str, filename: str, file_id: str):
        """Create document_state record after successful processing"""
        from backend import PROCESSING_STATUS
        from incremental_updates.state_manager import DocumentState, StateManager
        from datetime import datetime, timezone
        
        # Wait a moment for processing to complete and status to update
        await asyncio.sleep(0.5)
        
        status_dict = PROCESSING_STATUS.get(processing_id, {})
        if status_dict.get('status') != 'completed':
            logger.warning(f"Processing not yet completed for {filename}, skipping document_state creation")
            return
        
        documents = status_dict.get('documents', [])
        if not documents:
            logger.warning(f"No documents found in PROCESSING_STATUS for {filename}")
            return
        
        # Find the document for this file
        doc = documents[0]  # Should only be one file per incremental processing
        
        # Extract metadata
        source_id = doc.metadata.get('file id') or file_id
        timestamp_str = doc.metadata.get('modified at')  # Google Drive uses 'modified at' with space
        modified_timestamp = self.parse_timestamp(timestamp_str)
        
        # Get human-readable path for source_path (for database/queries)
        human_file_path = doc.metadata.get('file path') or doc.metadata.get('file_name') or filename
        
        # Create doc_id in stable format (using file_id as stable path)
        doc_id = f"{self.config_id}:{file_id}"
        
        # Compute content hash from modification timestamp if available
        if modified_timestamp:
            content_hash = StateManager.compute_content_hash(str(modified_timestamp))
            logger.info(f"Event-added file: Using timestamp-based hash: {modified_timestamp}")
        else:
            content_hash = StateManager.compute_content_hash("")
            logger.warning(f"Event-added file: No timestamp, using placeholder hash")
        
        # Compute ordinal from file's modification timestamp (not current time)
        ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        if modified_timestamp:
            ordinal = int(modified_timestamp.timestamp() * 1_000_000)
            logger.info(f"Event-added file: Using modification timestamp for ordinal: {modified_timestamp} -> {ordinal}")
        
        # Get current time for sync timestamps (file was just ingested)
        now = datetime.now(timezone.utc)
        
        # Determine if graph was synced based on skip_graph setting
        skip_graph = getattr(self, 'skip_graph', False)
        graph_synced = now if not skip_graph else None
        
        # Create document state with sync timestamps marked
        # (backend just ingested to vector, search, and optionally graph indexes)
        # Use human-readable path for source_path (for UI display)
        # Use file_id for stable identification (in doc_id and source_id)
        doc_state = DocumentState(
            doc_id=doc_id,
            config_id=self.config_id,
            source_path=human_file_path,  # Use human-readable path for display
            ordinal=ordinal,
            content_hash=content_hash,
            source_id=source_id,
            modified_timestamp=modified_timestamp,
            vector_synced_at=now,        # Mark as synced (just ingested)
            search_synced_at=now,        # Mark as synced (just ingested)
            graph_synced_at=graph_synced  # Mark as synced if graph extraction was performed
        )
        
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for {filename}: doc_id={doc_id}, source_path={human_file_path}, source_id={source_id}")

    
    async def _find_file_id(self, path: str) -> Optional[str]:
        """Find file ID by name or path"""
        # If path looks like a file ID (alphanumeric), use it directly
        if len(path) > 20 and path.replace('-', '').replace('_', '').isalnum():
            return path
        
        try:
            # Search for file by name
            query_parts = [f"name = '{path}'", "trashed = false"]
            
            if self.folder_id:
                query_parts.append(f"'{self.folder_id}' in parents")
            
            query = ' and '.join(query_parts)
            
            response = await asyncio.to_thread(
                self.drive_service.files().list(
                    q=query,
                    spaces='drive',
                    fields='files(id)',
                    pageSize=1,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute
            )
            
            files = response.get('files', [])
            if files:
                return files[0]['id']
            
            return None
            
        except HttpError as e:
            logger.warning(f"Error finding Google Drive file ID: {e}")
            return None
