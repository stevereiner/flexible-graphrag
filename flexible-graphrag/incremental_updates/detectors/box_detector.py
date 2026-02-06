"""
Box Change Detector

Real-time Box change detection using Events API (User Events stream).
Supports both event-based (Events stream) and periodic (polling) modes.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata

logger = logging.getLogger("flexible_graphrag.incremental.detectors.box")

# ---------------------------------------------------------------------------
# Box SDK Integration
# ---------------------------------------------------------------------------

try:
    from box_sdk_gen import BoxClient, BoxDeveloperTokenAuth, BoxCCGAuth, CCGConfig, BoxAPIError
    BOX_AVAILABLE = True
except ImportError:
    BOX_AVAILABLE = False
    BoxAPIError = Exception
    # Create dummy classes to avoid NameError
    BoxClient = None
    BoxDeveloperTokenAuth = None
    BoxCCGAuth = None
    CCGConfig = None
    # Don't log at import time - only when detector is instantiated


# ---------------------------------------------------------------------------
# Box Detector
# ---------------------------------------------------------------------------

class BoxDetector(ChangeDetector):
    """
    Box change detector using Events API (User Events stream).
    
    Features:
    - Event-based detection via Box Events API
    - Fallback to periodic refresh
    - Automatic retry with exponential backoff
    - Proper error handling and logging
    - Supports Developer Token and CCG authentication
    - **NEW**: Uses backend for ADD/MODIFY events (full DocumentProcessor pipeline)
    
    Configuration:
        folder_id: Box folder ID to monitor (optional, "0" = root)
        box_folder_id: Alternative name for folder_id
        
        # Developer Token (simple, but expires)
        access_token: Box developer token
        
        # CCG Auth (Client Credentials Grant - recommended for production)
        client_id: Box app client ID
        client_secret: Box app client secret
        enterprise_id: Box enterprise ID (for enterprise auth)
        user_id: Box user ID (for user auth)
        
        polling_interval: Seconds between event polls (default: 30)
        recursive: Monitor subfolders recursively (default: True)
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        if not BOX_AVAILABLE:
            raise ImportError(
                "Box SDK not installed. Install with: pip install box-sdk-gen llama-index-readers-box"
            )
        
        # Folder configuration
        self.folder_id = config.get('folder_id') or config.get('box_folder_id', '0')
        self.recursive = config.get('recursive', True)
        self.polling_interval = config.get('polling_interval', 30)
        
        # Authentication config
        self.access_token = config.get('access_token')
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        self.enterprise_id = config.get('enterprise_id')
        self.user_id = config.get('user_id')
        
        # Box client
        self.box_client = None
        
        # Event tracking
        self.stream_position = 'now'  # Start from current time
        self.folder_cache = {}  # Cache of folder IDs we're monitoring
        
        # Statistics
        self.events_processed = 0
        self.errors_count = 0
        
        # Backend reference (will be injected by orchestrator)
        self.backend = None
        self.state_manager = None
        self.config_id = None
        
        # Track known files for CREATE vs MODIFY detection
        self.known_file_ids = set()
        
        logger.info(f"BoxDetector initialized - folder_id={self.folder_id}, "
                   f"recursive={self.recursive}, polling_interval={self.polling_interval}s")
    
    def _create_box_client(self):
        """Create Box client with authentication"""
        if not BOX_AVAILABLE:
            raise ImportError("box-sdk-gen library required for Box detector")
        
        # Developer Token (simple but expires)
        if self.access_token:
            logger.info("Using Box Developer Token authentication")
            auth = BoxDeveloperTokenAuth(token=self.access_token)
            return BoxClient(auth=auth)
        
        # CCG Auth (Client Credentials Grant)
        if self.client_id and self.client_secret:
            if self.enterprise_id:
                logger.info(f"Using Box CCG authentication with enterprise_id: {self.enterprise_id}")
                ccg_config = CCGConfig(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    enterprise_id=self.enterprise_id
                )
            elif self.user_id:
                logger.info(f"Using Box CCG authentication with user_id: {self.user_id}")
                ccg_config = CCGConfig(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    user_id=self.user_id
                )
            else:
                raise ValueError("CCG Auth requires either enterprise_id or user_id")
            
            auth = BoxCCGAuth(config=ccg_config)
            return BoxClient(auth=auth)
        
        raise ValueError("Box authentication required: provide access_token or (client_id + client_secret + enterprise_id/user_id)")
    
    async def start(self):
        """Start Box detector and initialize client"""
        if not BOX_AVAILABLE:
            logger.error("Cannot start Box detector - box-sdk-gen not installed")
            raise ImportError("box-sdk-gen library required. Install with: pip install box-sdk-gen")
        
        self._running = True
        
        try:
            # Create Box client
            self.box_client = self._create_box_client()
            
            # Verify access
            await self._verify_access()
            
            # Build folder cache if monitoring specific folder
            if self.folder_id and self.folder_id != '0':
                await self._build_folder_cache()
            
            # Initialize event stream position
            await self._initialize_event_stream()
            
            logger.info(f"Box detector started successfully for folder: {self.folder_id}")
            logger.info(f"Using Events API with {self.polling_interval}s polling interval")
            
        except Exception as e:
            self._running = False
            logger.error(f"Failed to start Box detector: {e}")
            raise
    
    async def _verify_access(self):
        """Verify we can access Box"""
        try:
            # Get current user info to verify authentication
            user = await asyncio.to_thread(self.box_client.users.get_user_me)
            logger.info(f"Box access verified - user: {user.name} ({user.id})")
            
        except BoxAPIError as e:
            logger.error(f"Error verifying Box access: {e}")
            raise
    
    async def _build_folder_cache(self):
        """Build cache of folder IDs we're monitoring (for recursive filtering)"""
        try:
            self.folder_cache = {self.folder_id: True}
            
            if self.recursive:
                # Get folder items
                folder_items = await asyncio.to_thread(
                    self.box_client.folders.get_folder_items,
                    folder_id=self.folder_id
                )
                
                # Recursively find all subfolders
                await self._add_subfolders_to_cache(self.folder_id)
                
                logger.info(f"Built folder cache with {len(self.folder_cache)} folders")
            
        except BoxAPIError as e:
            logger.warning(f"Error building folder cache: {e}")
    
    async def _add_subfolders_to_cache(self, folder_id: str):
        """Recursively add subfolders to cache"""
        try:
            folder_items = await asyncio.to_thread(
                self.box_client.folders.get_folder_items,
                folder_id=folder_id
            )
            
            for item in folder_items.entries:
                if item.type.value == 'folder':
                    self.folder_cache[item.id] = True
                    if self.recursive:
                        await self._add_subfolders_to_cache(item.id)
            
        except BoxAPIError as e:
            logger.warning(f"Error adding subfolders to cache: {e}")
    
    async def _initialize_event_stream(self):
        """Initialize event stream position"""
        try:
            # Get current stream position
            events = await asyncio.to_thread(
                self.box_client.events.get_events,
                stream_position='now',
                limit=0
            )
            
            self.stream_position = events.next_stream_position
            logger.info(f"Box event stream initialized at position: {self.stream_position}")
            
        except BoxAPIError as e:
            logger.warning(f"Error initializing event stream: {e}")
            self.stream_position = 'now'
    
    async def stop(self):
        """Stop Box detector"""
        self._running = False
        self.box_client = None
        
        logger.info(f"Box detector stopped. Events processed: {self.events_processed}, Errors: {self.errors_count}")
    
    async def list_all_files(self) -> List[FileMetadata]:
        """List all files in the monitored folder (for initial/periodic sync)"""
        if not self.box_client:
            raise RuntimeError("Box detector not started")
        
        files = []
        try:
            # Get items from folder
            await self._list_folder_items(self.folder_id, files)
            
            logger.info(f"Listed {len(files)} files from Box")
            
        except BoxAPIError as e:
            logger.error(f"Error listing Box files: {e}")
            self.errors_count += 1
            raise
        
        return files
    
    async def _list_folder_items(self, folder_id: str, files: List[FileMetadata]):
        """Recursively list folder items"""
        try:
            folder_items = await asyncio.to_thread(
                self.box_client.folders.get_folder_items,
                folder_id=folder_id
            )
            
            for item in folder_items.entries:
                if item.type.value == 'file':
                    metadata = await self._item_to_metadata(item)
                    if metadata:
                        files.append(metadata)
                elif item.type.value == 'folder' and self.recursive:
                    await self._list_folder_items(item.id, files)
            
        except BoxAPIError as e:
            logger.warning(f"Error listing folder items: {e}")
    
    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """
        Stream change events from Box Events API (polling).
        Yields change events as they are detected.
        """
        if not self._running or not self.box_client:
            return
        
        logger.info("Starting Box Events API monitoring...")
        
        while self._running:
            try:
                # Poll for events
                events = await asyncio.to_thread(
                    self.box_client.events.get_events,
                    stream_position=self.stream_position,
                    limit=100
                )
                
                # Process events
                for event_data in events.entries:
                    event = await self._parse_event(event_data)
                    if event:
                        self.events_processed += 1
                        
                        # Handle different event types
                        if event.change_type == ChangeType.DELETE:
                            # Yield DELETE events for engine to handle
                            logger.info(f"Box EVENT: DELETE for {event.metadata.path}")
                            yield event
                        
                        elif event.change_type == ChangeType.CREATE:
                            # Check if truly new (using known_file_ids)
                            file_id = event.metadata.extra.get('file_id')
                            file_name = event.metadata.path
                            
                            if not file_id:
                                logger.warning(f"SKIP: No file_id for {file_name}")
                                continue
                            
                            is_new = file_id not in self.known_file_ids
                            
                            if is_new:
                                # Truly new - CREATE
                                logger.info(f"Box EVENT: CREATE for {file_name}")
                                self.known_file_ids.add(file_id)
                                try:
                                    await self._process_via_backend(file_id, file_name)
                                    logger.info(f"SUCCESS: Processed CREATE for {file_name}")
                                except Exception as e:
                                    logger.error(f"ERROR: Failed to process CREATE for {file_name}: {e}")
                            else:
                                # Already known - treat as UPDATE (DELETE + ADD)
                                logger.info(f"Box EVENT: UPDATE (reported as CREATE) for {file_name}")
                                
                                async def add_callback():
                                    logger.info(f"UPDATE: DELETE completed, now processing ADD for {file_name}")
                                    try:
                                        await self._process_via_backend(file_id, file_name)
                                        logger.info(f"SUCCESS: UPDATE completed for {file_name}")
                                    except Exception as e:
                                        logger.error(f"ERROR: Failed to process ADD for {file_name}: {e}")
                                
                                delete_metadata = FileMetadata(
                                    source_type='box',
                                    path=file_id,  # Use file_id as path for delete
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
                        
                        elif event.change_type == ChangeType.UPDATE:
                            # UPDATE event - DELETE first, then ADD via callback
                            file_id = event.metadata.extra.get('file_id')
                            file_name = event.metadata.path
                            
                            if not file_id:
                                logger.warning(f"SKIP: No file_id for {file_name}")
                                continue
                            
                            logger.info(f"Box EVENT: UPDATE for {file_name}")
                            
                            # Check if truly known (might be false positive)
                            is_new = file_id not in self.known_file_ids
                            
                            if is_new:
                                # Actually new - treat as CREATE
                                logger.info(f"Box EVENT: CREATE (reported as UPDATE) for {file_name}")
                                self.known_file_ids.add(file_id)
                                try:
                                    await self._process_via_backend(file_id, file_name)
                                    logger.info(f"SUCCESS: Processed CREATE for {file_name}")
                                except Exception as e:
                                    logger.error(f"ERROR: Failed to process CREATE for {file_name}: {e}")
                            else:
                                # True UPDATE - DELETE + ADD
                                logger.info(f"Box EVENT: UPDATE - emitting DELETE with callback")
                                
                                async def add_callback():
                                    logger.info(f"UPDATE: DELETE completed, now processing ADD for {file_name}")
                                    try:
                                        await self._process_via_backend(file_id, file_name)
                                        logger.info(f"SUCCESS: UPDATE completed for {file_name}")
                                    except Exception as e:
                                        logger.error(f"ERROR: Failed to process ADD for {file_name}: {e}")
                                
                                delete_metadata = FileMetadata(
                                    source_type='box',
                                    path=file_id,  # Use file_id as path for delete
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
                
                # Update stream position
                self.stream_position = events.next_stream_position
                
                # Wait before next poll
                await asyncio.sleep(self.polling_interval)
                
            except BoxAPIError as e:
                logger.error(f"Error polling Box events: {e}")
                self.errors_count += 1
                await asyncio.sleep(self.polling_interval)
            
            except Exception as e:
                logger.error(f"Unexpected error in Box events: {e}")
                self.errors_count += 1
                await asyncio.sleep(self.polling_interval)
    
    async def _parse_event(self, event_data) -> Optional[ChangeEvent]:
        """Parse Box event into ChangeEvent"""
        try:
            event_type = event_data.event_type.value if hasattr(event_data.event_type, 'value') else str(event_data.event_type)
            source = event_data.source
            
            # Only process file events
            if source.type.value != 'file':
                return None
            
            # Map Box event types to ChangeType
            if event_type in ['ITEM_UPLOAD', 'ITEM_CREATE', 'ITEM_COPY']:
                change_type = ChangeType.CREATE
            elif event_type in ['ITEM_MODIFY', 'ITEM_RENAME', 'ITEM_MOVE']:
                change_type = ChangeType.UPDATE
            elif event_type in ['ITEM_TRASH', 'ITEM_DELETE']:
                change_type = ChangeType.DELETE
            else:
                # Ignore other event types (ITEM_DOWNLOAD, ITEM_PREVIEW, etc.)
                return None
            
            # Check if file is in monitored folders
            parent = source.parent
            if self.folder_id and self.folder_id != '0':
                parent_id = parent.id if parent else None
                if parent_id not in self.folder_cache:
                    return None
            
            # Parse event timestamp
            created_at = event_data.created_at
            if created_at:
                if isinstance(created_at, str):
                    event_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    event_time = created_at
            else:
                event_time = datetime.now(timezone.utc)
            
            # Get file metadata
            file_id = source.id
            file_name = source.name or file_id
            
            ordinal = int(event_time.timestamp() * 1_000_000)
            
            metadata = FileMetadata(
                source_type='box',
                path=file_name,
                ordinal=ordinal,
                size_bytes=source.size if hasattr(source, 'size') else None,
                mime_type=None,  # Box doesn't always provide MIME type in events
                modified_timestamp=event_time.isoformat(),
                extra={
                    'file_id': file_id,
                    'parent_id': parent.id if parent else None,
                    'etag': source.etag if hasattr(source, 'etag') else None,
                    'event_type': event_type,
                }
            )
            
            return ChangeEvent(
                metadata=metadata,
                change_type=change_type,
                timestamp=event_time
            )
            
        except Exception as e:
            logger.warning(f"Error parsing Box event: {e}")
            return None
    
    async def _item_to_metadata(self, item) -> Optional[FileMetadata]:
        """Convert Box file item to FileMetadata"""
        try:
            # Get full file details
            file = await asyncio.to_thread(
                self.box_client.files.get_file_by_id,
                file_id=item.id
            )
            
            # Parse modified time
            modified_at = file.modified_at
            if isinstance(modified_at, str):
                modified_time = datetime.fromisoformat(modified_at.replace('Z', '+00:00'))
            else:
                modified_time = modified_at if modified_at else datetime.now(timezone.utc)
            
            ordinal = int(modified_time.timestamp() * 1_000_000)
            
            return FileMetadata(
                source_type='box',
                path=file.name,
                ordinal=ordinal,
                size_bytes=file.size,
                mime_type=None,  # Box doesn't consistently provide MIME type
                modified_timestamp=modified_time.isoformat(),
                extra={
                    'file_id': file.id,
                    'etag': file.etag if hasattr(file, 'etag') else None,
                }
            )
            
        except Exception as e:
            logger.warning(f"Error converting Box item to metadata: {e}")
            return None
    
    async def _process_via_backend(self, file_id: str, filename: str):
        """
        Process Box file by calling backend._process_documents_async() directly.
        Uses the complete pipeline with DocumentProcessor.
        
        Args:
            file_id: Box file ID
            filename: File name for logging
        """
        if not self.backend:
            logger.error("Backend not injected into BoxDetector - cannot process file")
            return
        
        logger.info(f"Processing {filename} (file_id: {file_id}) via backend (full pipeline)")
        
        try:
            skip_graph = getattr(self, 'skip_graph', False)
            processing_id = f"incremental_box_{file_id[:8]}"
            
            # Build Box config
            box_config = {
                'folder_id': self.folder_id,
                'box_file_ids': [file_id],  # Process just this one file (BoxSource expects box_file_ids)
                'recursive': False,
            }
            
            # Add authentication
            if self.access_token:
                box_config['access_token'] = self.access_token
            elif self.client_id and self.client_secret:
                box_config['client_id'] = self.client_id
                box_config['client_secret'] = self.client_secret
                if self.enterprise_id:
                    box_config['enterprise_id'] = self.enterprise_id
                elif self.user_id:
                    box_config['user_id'] = self.user_id
            
            # Call backend method directly
            await self.backend._process_documents_async(
                processing_id=processing_id,
                data_source='box',
                config_id=self.config_id,
                skip_graph=skip_graph,
                box_config=box_config
            )
            
            logger.info(f"Successfully processed {filename} via backend pipeline")
            
            # Create document_state record after successful processing using proper PostIngestionStateManager
            if self.state_manager:
                try:
                    from post_ingestion_state import PostIngestionStateManager
                    post_state_manager = PostIngestionStateManager(self.state_manager.postgres_url)
                    await post_state_manager.create_document_states_after_ingestion(
                        processing_id=processing_id,
                        config_id=self.config_id,
                        paths=[],  # Box doesn't use paths
                        data_source='box'
                    )
                    logger.info(f"Created document_state for {filename} via PostIngestionStateManager")
                except Exception as e:
                    logger.error(f"Failed to create document_state for {filename}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process {filename} via backend: {e}")
            raise
    
    async def _find_file_id(self, path: str) -> Optional[str]:
        """Find file ID by name or path"""
        # If path looks like a file ID (numeric), use it directly
        if path.isdigit():
            return path
        
        try:
            # Search for file by name in monitored folder
            folder_items = await asyncio.to_thread(
                self.box_client.folders.get_folder_items,
                folder_id=self.folder_id
            )
            
            for item in folder_items.entries:
                if item.type.value == 'file' and item.name == path:
                    return item.id
            
            # If recursive, search subfolders
            if self.recursive:
                for folder_id in self.folder_cache.keys():
                    if folder_id != self.folder_id:
                        folder_items = await asyncio.to_thread(
                            self.box_client.folders.get_folder_items,
                            folder_id=folder_id
                        )
                        
                        for item in folder_items.entries:
                            if item.type.value == 'file' and item.name == path:
                                return item.id
            
            return None
            
        except BoxAPIError as e:
            logger.warning(f"Error finding Box file ID: {e}")
            return None
