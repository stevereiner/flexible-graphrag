"""
Azure Blob Storage Change Detector

Real-time Azure Blob Storage change detection using Azure Blob Change Feed.
Supports both event-based (change feed) and periodic (polling) modes.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata
from incremental_updates.state_manager import StateManager

logger = logging.getLogger("flexible_graphrag.incremental.detectors.azure_blob")

# ---------------------------------------------------------------------------
# Azure SDK Integration
# ---------------------------------------------------------------------------

try:
    from azure.storage.blob import BlobServiceClient
    from azure.storage.blob.changefeed import ChangeFeedClient
    from azure.core.exceptions import AzureError, ResourceNotFoundError
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    AzureError = Exception
    ResourceNotFoundError = Exception
    ResourceNotFoundError = Exception
    logger.warning("azure-storage-blob and/or azure-storage-blob-changefeed not installed - Azure Blob change detection unavailable")


# ---------------------------------------------------------------------------
# Azure Blob Detector
# ---------------------------------------------------------------------------

class AzureBlobDetector(ChangeDetector):
    """
    Azure Blob Storage change detector using Change Feed.
    
    Features:
    - Event-based detection via Azure Blob Change Feed
    - Fallback to periodic refresh when change feed not enabled
    - Automatic retry with exponential backoff
    - Proper error handling and logging
    - Continuation token support for resuming
    - **NEW**: Uses backend for ADD/MODIFY events (full DocumentProcessor pipeline)
    
    Configuration:
        container_name: Azure Blob container name (required)
        connection_string: Azure Storage connection string (optional)
        account_url: Azure Storage account URL (optional)
        account_name: Azure Storage account name (optional)
        account_key: Azure Storage account key (optional)
        prefix: Blob prefix/folder filter (optional)
        enable_change_feed: Enable change feed monitoring (default: True)
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # Required config
        self.container_name = config.get('container_name') or config.get('container')
        if not self.container_name:
            raise ValueError("AzureBlobDetector requires 'container_name' or 'container' in config")
        
        # Connection options
        self.connection_string = config.get('connection_string')
        self.account_url = config.get('account_url')
        self.account_name = config.get('account_name')
        self.account_key = config.get('account_key')
        
        # Validate credentials
        has_connection_string = bool(self.connection_string)
        has_account_key_auth = bool(self.account_url and self.account_key)
        
        if not has_connection_string and not has_account_key_auth:
            raise ValueError("AzureBlobDetector requires either 'connection_string' or ('account_url' + 'account_key')")
        
        self.prefix = config.get('prefix', '')
        # One selected blob, else everything under the prefix is followed
        self.blob = config.get('blob') or None
        self.enable_change_feed = config.get('enable_change_feed', True)
        
        # Clients
        self.blob_service_client = None
        self.change_feed_client = None
        
        # Change feed state
        self.continuation_token = None
        self.last_cursor_time = None
        # Record startup time so we ignore old change feed events replayed from history
        self.start_time = datetime.now(timezone.utc)
        
        # Statistics
        self.events_processed = 0
        self.errors_count = 0
        
        # Backend reference (will be injected by orchestrator)
        self.backend = None
        self.state_manager = None
        self.config_id = None
        
        # Track known blobs for CREATE vs MODIFY detection
        self.known_blob_names = set()
        # Blobs currently being ingested — dedups a concurrent periodic-refresh + event-stream overlap
        # (both call _process_via_backend during the window before document_state is written).
        self._in_flight = set()
        # Track when each blob was last processed (for debounce)
        # Azure Change Feed often emits 2-3 events per operation (BlobCreated + BlobPropertiesUpdated)
        self._last_processed: dict = {}  # full_path -> datetime
        self._debounce_seconds = 30  # ignore duplicate events within this window
        
        logger.info(f"AzureBlobDetector initialized - container={self.container_name}, "
                   f"prefix={self.prefix}, change_feed={self.enable_change_feed}")
    
    async def start(self):
        """Start Azure Blob detector and initialize clients"""
        if not AZURE_AVAILABLE:
            logger.error("Cannot start Azure Blob detector - azure-storage-blob libraries not installed")
            raise ImportError("azure-storage-blob and azure-storage-blob-changefeed libraries required")
        
        self._running = True
        
        try:
            # Create BlobServiceClient
            if self.connection_string:
                self.blob_service_client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
            elif self.account_url and self.account_key:
                from azure.storage.blob import BlobServiceClient
                self.blob_service_client = BlobServiceClient(
                    account_url=self.account_url,
                    credential=self.account_key
                )
            
            # Verify container access
            await self._verify_container_access()
            
            # Populate known blobs before starting change feed
            await self._populate_known_blobs()
            
            # Try to enable change feed if requested
            if self.enable_change_feed:
                try:
                    # ChangeFeedClient requires account_url string + credential, not a BlobServiceClient
                    if self.connection_string:
                        # Parse connection string to extract account URL and key
                        self.change_feed_client = ChangeFeedClient.from_connection_string(
                            self.connection_string
                        )
                    elif self.account_url and self.account_key:
                        self.change_feed_client = ChangeFeedClient(
                            account_url=self.account_url,
                            credential=self.account_key
                        )
                    else:
                        raise ValueError("Cannot create ChangeFeedClient: need connection_string or account_url+account_key")
                    logger.info("Azure Blob detector started in CHANGE FEED MODE")
                except Exception as e:
                    logger.warning(f"Change feed not available: {e}. Falling back to periodic mode.")
                    self.change_feed_client = None
            
            if not self.change_feed_client:
                logger.debug("Azure Blob detector started in PERIODIC MODE")
            
            logger.debug(f"Azure Blob detector started successfully for container: {self.container_name}")
            
        except Exception as e:
            self._running = False
            logger.error(f"Failed to start Azure Blob detector: {e}")
            raise
    
    async def _populate_known_blobs(self):
        """Populate known_blob_names set with all currently existing blobs"""
        try:
            logger.info("POPULATE: Starting to populate known_blob_names...")
            
            all_files = await self.list_all_files()
            for file_meta in all_files:
                self.known_blob_names.add(file_meta.path)
            
            logger.info(f"POPULATE: Populated known_blob_names with {len(self.known_blob_names)} existing blobs")
            
        except Exception as e:
            logger.error(f"Error populating known_blob_names: {e}")
    
    async def _verify_container_access(self):
        """Verify we can access the Azure Blob container"""
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            
            # Try to list blobs with limit 1 to verify access
            blobs = container_client.list_blobs(name_starts_with=self.prefix or None, results_per_page=1)
            _ = list(blobs)[:1]  # Force evaluation
            
            logger.info(f"Azure Blob container access verified: {self.container_name}")
            
        except ResourceNotFoundError:
            logger.error(f"Azure Blob container not found: {self.container_name}")
            raise
        except AzureError as e:
            logger.error(f"Error accessing Azure Blob container {self.container_name}: {e}")
            raise
    
    async def stop(self):
        """Stop Azure Blob detector"""
        self._running = False
        
        # Close clients
        if self.blob_service_client:
            await asyncio.to_thread(self.blob_service_client.close)
            self.blob_service_client = None
        
        self.change_feed_client = None
        
        logger.debug(f"Azure Blob detector stopped. Events processed: {self.events_processed}, Errors: {self.errors_count}")
    
    async def list_all_files(self) -> List[FileMetadata]:
        """List all blobs in the container (for initial/periodic sync)"""
        if not self.blob_service_client:
            raise RuntimeError("Azure Blob detector not started")
        
        files = []
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            
            # List blobs with prefix filter (the selected blob only, when there is one)
            blobs = container_client.list_blobs(name_starts_with=self.blob or self.prefix or None)

            for blob in blobs:
                if self.blob and blob.name != self.blob:
                    continue
                # Skip directories (blobs ending with /)
                if blob.name.endswith('/'):
                    continue
                
                # Convert last_modified to microsecond timestamp
                last_modified = blob.last_modified or datetime.now(timezone.utc)
                ordinal = int(last_modified.timestamp() * 1_000_000)
                
                metadata = FileMetadata(
                    source_type='azure_blob',
                    path=f"{self.container_name}/{blob.name}",  # Use full path: container/blob_name
                    ordinal=ordinal,
                    size_bytes=blob.size,
                    mime_type=blob.content_settings.content_type if blob.content_settings else None,
                    modified_timestamp=last_modified.isoformat(),
                    extra={
                        'etag': blob.etag,
                        'container': self.container_name,
                        'blob_name': blob.name,  # Store raw blob name too
                    }
                )
                files.append(metadata)
            
            logger.info(f"Listed {len(files)} blobs from Azure Blob container {self.container_name}")
            
        except AzureError as e:
            logger.error(f"Error listing Azure Blobs: {e}")
            self.errors_count += 1
            raise
        
        return files

    async def _already_ingested_unchanged(self, full_path: str, ordinal) -> bool:
        """True if this blob is already in document_state with an unchanged ordinal — i.e. the
        periodic refresh (or a prior event) already ingested it. The event stream and the periodic
        refresh track state separately (known_blob_names vs document_state), so without this a
        just-refreshed blob gets re-ingested by the CREATE event → duplicate chunks."""
        if not self.state_manager or not self.config_id:
            return False
        try:
            st = await self.state_manager.get_state(f"{self.config_id}:{full_path}")
        except Exception as e:
            logger.debug(f"document_state check failed for {full_path}: {e}")
            return False
        # Present in document_state → the periodic refresh (or a prior event) already ingested it,
        # so this is_new CREATE event is a duplicate. We deliberately do NOT compare ordinals: the
        # event ordinal is the change-feed eventTime while document_state stores the blob's
        # last_modified, so they don't line up (that's why the earlier ordinal check never skipped).
        # A genuine later modify is caught by the periodic refresh; and because the caller adds this
        # path to known_blob_names on skip, subsequent modifies route through the UPDATE branch.
        return st is not None

    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """
        Stream change events from Azure Blob Change Feed.
        Yields change events as they are detected.
        """
        if not self._running:
            return
        
        if not self.change_feed_client:
            # Change feed not available - caller should use periodic refresh
            logger.debug("Change feed not available - no events to stream")
            return
        
        logger.info("Starting Azure Blob change feed monitoring...")
        
        while self._running:
            try:
                # Get change feed events
                # If we have a continuation token, resume from where we left off.
                # Otherwise start from detector startup time so we don't replay all history.
                # Note: pass continuation_token to by_page(), not to list_changes(), to avoid
                # the "got multiple values for keyword argument" error.
                if self.continuation_token:
                    change_feed = self.change_feed_client.list_changes(
                        results_per_page=100
                    )
                    pages = change_feed.by_page(continuation_token=self.continuation_token)
                else:
                    change_feed = self.change_feed_client.list_changes(
                        start_time=self.start_time,
                        results_per_page=100
                    )
                    pages = change_feed.by_page()
                
                for change_page in pages:
                    # Save continuation token from the page iterator after each page.
                    # The token lives on the 'pages' iterator, not on individual change_page items.
                    if hasattr(pages, 'continuation_token') and pages.continuation_token:
                        self.continuation_token = pages.continuation_token
                        logger.debug(f"Saved continuation_token after page")

                    for change in change_page:
                        # Filter by container and prefix
                        if not self._should_process_change(change):
                            continue
                        
                        # Parse change event
                        event = self._parse_change_event(change)
                        if event:
                            # Skip events that occurred before this detector started.
                            # The change feed replays all history when there is no saved
                            # continuation_token, so without this guard we would re-process
                            # every historical CREATE/DELETE on every fresh start.
                            if event.timestamp and event.timestamp < self.start_time:
                                logger.debug(
                                    f"Skipping historical change feed event for "
                                    f"{event.metadata.path} (ts={event.timestamp})"
                                )
                                continue
                            
                            self.events_processed += 1
                            
                            # Handle different event types
                            if event.change_type == ChangeType.DELETE:
                                # Yield DELETE events for engine to handle
                                logger.info(f"Azure Blob EVENT: DELETE for {event.metadata.path}")
                                yield event
                            
                            elif event.change_type == ChangeType.CREATE:
                                # Check if truly new (using known_blob_names)
                                # event.metadata.path is now container/blob_name
                                full_path = event.metadata.path
                                blob_name = full_path.split('/', 1)[-1] if '/' in full_path else full_path
                                is_new = full_path not in self.known_blob_names

                                # Skip if the periodic refresh (or a prior event) already ingested this
                                # blob unchanged — the two paths track state separately, so without this
                                # the CREATE event re-ingests it → duplicate chunks (periodic + event).
                                if is_new and await self._already_ingested_unchanged(full_path, event.metadata.ordinal):
                                    logger.info(f"Azure Blob EVENT: CREATE for {blob_name} already in document_state (unchanged) — skipping duplicate (periodic+event)")
                                    self.known_blob_names.add(full_path)
                                    self._last_processed[full_path] = datetime.now(timezone.utc)
                                    continue

                                if is_new:
                                    # Truly new - CREATE
                                    logger.info(f"Azure Blob EVENT: CREATE for {blob_name}")
                                    self.known_blob_names.add(full_path)
                                    self._last_processed[full_path] = datetime.now(timezone.utc)
                                    if self.backend:
                                        try:
                                            await self._process_via_backend(blob_name)
                                            logger.info(f"SUCCESS: Processed CREATE for {blob_name}")
                                        except Exception as e:
                                            logger.error(f"ERROR: Failed to process CREATE for {blob_name}: {e}")
                                    else:
                                        # CocoIndex mode: yield CREATE so FlexibleMapView.watch() ingests it
                                        logger.info(f"Azure Blob EVENT: new blob {blob_name} (CocoIndex mode): yielding CREATE")
                                        yield event
                                else:
                                    # Already known - but Azure often emits duplicate CREATE events
                                    # (e.g. BlobCreated + BlobPropertiesUpdated) within seconds.
                                    # Debounce: skip if we processed this blob very recently.
                                    last_proc = self._last_processed.get(full_path)
                                    now = datetime.now(timezone.utc)
                                    if last_proc and (now - last_proc).total_seconds() < self._debounce_seconds:
                                        logger.info(f"Azure Blob EVENT: Debouncing duplicate CREATE for {blob_name} ({(now - last_proc).total_seconds():.1f}s since last process)")
                                        continue
                                    # Treat as UPDATE (DELETE + ADD)
                                    logger.info(f"Azure Blob EVENT: UPDATE (reported as CREATE) for {blob_name}")
                                    self._last_processed[full_path] = datetime.now(timezone.utc)
                                    _mod_meta = FileMetadata(
                                        source_type='azure_blob',
                                        path=full_path,
                                        ordinal=event.metadata.ordinal,
                                        extra={'container': self.container_name, 'blob_name': full_path}
                                    )
                                    if self.backend:
                                        async def add_callback(bn=blob_name, fp=full_path):
                                            logger.info(f"UPDATE: DELETE completed, now processing ADD for {bn}")
                                            try:
                                                await self._process_via_backend(bn)
                                                self._last_processed[fp] = datetime.now(timezone.utc)
                                                logger.info(f"SUCCESS: UPDATE completed for {bn}")
                                            except Exception as e:
                                                logger.error(f"ERROR: Failed to process ADD for {bn}: {e}")
                                        yield ChangeEvent(
                                            metadata=_mod_meta,
                                            change_type=ChangeType.DELETE,
                                            timestamp=event.timestamp,
                                            is_modify_delete=True,
                                            modify_callback=add_callback
                                        )
                                    else:
                                        # CocoIndex mode: DELETE then CREATE
                                        logger.info(f"Azure Blob EVENT: modify for {blob_name} (CocoIndex mode): DELETE then CREATE")
                                        yield ChangeEvent(metadata=_mod_meta, change_type=ChangeType.DELETE, timestamp=event.timestamp)
                                        yield ChangeEvent(metadata=_mod_meta, change_type=ChangeType.CREATE, timestamp=event.timestamp)
                            
                            elif event.change_type == ChangeType.UPDATE:
                                # UPDATE event - DELETE first, then ADD via callback
                                full_path = event.metadata.path
                                blob_name = full_path.split('/', 1)[-1] if '/' in full_path else full_path
                                
                                # Debounce: Azure emits metadata/properties events alongside content events
                                last_proc = self._last_processed.get(full_path)
                                now = datetime.now(timezone.utc)
                                if last_proc and (now - last_proc).total_seconds() < self._debounce_seconds:
                                    logger.info(f"Azure Blob EVENT: Debouncing UPDATE for {blob_name} ({(now - last_proc).total_seconds():.1f}s since last process)")
                                    continue
                                
                                logger.info(f"Azure Blob EVENT: UPDATE for {blob_name}")
                                
                                # Check if truly known (might be false positive)
                                is_new = full_path not in self.known_blob_names

                                # Same periodic+event dedup as the CREATE branch above.
                                if is_new and await self._already_ingested_unchanged(full_path, event.metadata.ordinal):
                                    logger.info(f"Azure Blob EVENT: UPDATE(as CREATE) for {blob_name} already in document_state (unchanged) — skipping duplicate (periodic+event)")
                                    self.known_blob_names.add(full_path)
                                    self._last_processed[full_path] = datetime.now(timezone.utc)
                                    continue

                                if is_new:
                                    # Actually new - treat as CREATE
                                    logger.info(f"Azure Blob EVENT: CREATE (reported as UPDATE) for {blob_name}")
                                    self.known_blob_names.add(full_path)
                                    self._last_processed[full_path] = datetime.now(timezone.utc)
                                    if self.backend:
                                        try:
                                            await self._process_via_backend(blob_name)
                                            logger.info(f"SUCCESS: Processed CREATE for {blob_name}")
                                        except Exception as e:
                                            logger.error(f"ERROR: Failed to process CREATE for {blob_name}: {e}")
                                    else:
                                        # CocoIndex mode: yield CREATE so FlexibleMapView.watch() ingests it
                                        logger.info(f"Azure Blob EVENT: new blob {blob_name} from UPDATE (CocoIndex mode): yielding CREATE")
                                        yield event
                                else:
                                    # True UPDATE - DELETE + ADD
                                    logger.info(f"Azure Blob EVENT: UPDATE - emitting DELETE with callback")
                                    self._last_processed[full_path] = datetime.now(timezone.utc)
                                    _upd_meta = FileMetadata(
                                        source_type='azure_blob',
                                        path=full_path,
                                        ordinal=event.metadata.ordinal,
                                        extra={'container': self.container_name, 'blob_name': full_path}
                                    )
                                    if self.backend:
                                        async def add_callback(bn=blob_name, fp=full_path):
                                            logger.info(f"UPDATE: DELETE completed, now processing ADD for {bn}")
                                            try:
                                                await self._process_via_backend(bn)
                                                self._last_processed[fp] = datetime.now(timezone.utc)
                                                logger.info(f"SUCCESS: UPDATE completed for {bn}")
                                            except Exception as e:
                                                logger.error(f"ERROR: Failed to process ADD for {bn}: {e}")
                                        yield ChangeEvent(
                                            metadata=_upd_meta,
                                            change_type=ChangeType.DELETE,
                                            timestamp=event.timestamp,
                                            is_modify_delete=True,
                                            modify_callback=add_callback
                                        )
                                    else:
                                        # CocoIndex mode: DELETE then CREATE
                                        logger.info(f"Azure Blob EVENT: modify for {blob_name} (CocoIndex mode): DELETE then CREATE")
                                        yield ChangeEvent(metadata=_upd_meta, change_type=ChangeType.DELETE, timestamp=event.timestamp)
                                        yield ChangeEvent(metadata=_upd_meta, change_type=ChangeType.CREATE, timestamp=event.timestamp)
                    
                # Also save after exhausting all pages (final position)
                if hasattr(pages, 'continuation_token') and pages.continuation_token:
                    self.continuation_token = pages.continuation_token
                
                # Wait before next poll (change feed is eventually consistent)
                await asyncio.sleep(5)
                
            except (ResourceNotFoundError, AzureError) as e:
                error_str = str(e)
                # ContainerNotFound means the $blobchangefeed container doesn't exist,
                # i.e. Change Feed is not enabled on this storage account.
                # The error surfaces lazily from the iterator, so catch both
                # ResourceNotFoundError (specific) and AzureError (general) here.
                # Disable the client and fall back to periodic-only mode permanently.
                if 'ContainerNotFound' in error_str or 'container does not exist' in error_str.lower():
                    logger.warning(
                        "Azure Blob Change Feed is not enabled on this storage account "
                        "($blobchangefeed container not found). "
                        "Falling back to periodic refresh mode. "
                        "To enable: Azure Portal -> Storage Account -> "
                        "Data management -> Data protection -> enable Blob change feed."
                    )
                    self.change_feed_client = None
                    return  # Exit get_changes() - engine will use periodic refresh only
                logger.error(f"Error reading Azure Blob change feed: {e}")
                self.errors_count += 1
                await asyncio.sleep(10)  # Back off on error
            
            except Exception as e:
                logger.error(f"Unexpected error in Azure Blob change feed: {e}")
                self.errors_count += 1
                await asyncio.sleep(10)
    
    def _should_process_change(self, change) -> bool:
        """Check if change should be processed based on container and prefix filters"""
        try:
            # Get blob path from change event
            subject = change.get('subject', '')
            
            # Subject format: /blobServices/default/containers/{container}/blobs/{blob_path}
            if f'/containers/{self.container_name}/blobs/' not in subject:
                return False
            
            # Extract blob path
            blob_path = subject.split('/blobs/')[-1]
            
            # Apply prefix filter (the selected blob only, when there is one)
            if self.blob:
                return blob_path == self.blob
            if self.prefix and not blob_path.startswith(self.prefix):
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Error checking change filter: {e}")
            return False
    
    def _parse_change_event(self, change) -> Optional[ChangeEvent]:
        """Parse Azure Blob change feed event into ChangeEvent"""
        try:
            # Get event type
            event_type = change.get('eventType', '')
            
            # Map Azure event types to ChangeType
            if 'BlobCreated' in event_type:
                change_type = ChangeType.CREATE
            elif 'BlobDeleted' in event_type:
                change_type = ChangeType.DELETE
            elif 'BlobPropertiesUpdated' in event_type or 'BlobMetadataUpdated' in event_type:
                change_type = ChangeType.UPDATE
            else:
                logger.debug(f"Ignoring Azure Blob event type: {event_type}")
                return None
            
            # Extract blob path from subject
            subject = change.get('subject', '')
            blob_path = subject.split('/blobs/')[-1]
            
            # Get event timestamp
            event_time = change.get('eventTime')
            if isinstance(event_time, str):
                event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
            elif not event_time:
                event_time = datetime.now(timezone.utc)
            
            ordinal = int(event_time.timestamp() * 1_000_000)
            
            # Get blob properties if available
            data = change.get('data', {})
            
            # Use container/blob_path as the canonical path so it matches document_state source_id
            full_path = f"{self.container_name}/{blob_path}"
            
            metadata = FileMetadata(
                source_type='azure_blob',
                path=full_path,
                ordinal=ordinal,
                size_bytes=data.get('contentLength'),
                mime_type=data.get('contentType'),
                modified_timestamp=event_time.isoformat(),
                extra={
                    'etag': data.get('etag'),
                    'container': self.container_name,
                    'blob_name': full_path,   # for source_id lookup in engine DELETE handler
                    'event_type': event_type,
                }
            )
            
            return ChangeEvent(
                metadata=metadata,
                change_type=change_type,
                timestamp=event_time
            )
            
        except Exception as e:
            logger.warning(f"Error parsing Azure Blob change event: {e}")
            return None
    
    async def _process_via_backend(self, blob_path: str):
        """
        Process Azure Blob by downloading it directly and passing to backend.
        Unlike directory-based processing, this downloads only the specific file.
        
        Args:
            blob_path: Azure Blob path - can be either:
                       - Full path (container/blob_name) 
                       - Just blob name
        """
        if not self.backend:
            logger.error("Backend not injected into AzureBlobDetector - cannot process blob")
            return
        
        logger.info(f"Processing {blob_path} via backend (direct download)")

        full_path = None
        _added_inflight = False
        try:
            from incremental_updates.doc_graphs import datasource_graphs, synced_times
            graphs = datasource_graphs(self)  # which graphs it builds

            # Extract blob name from full path if needed
            # Full path format: container/blob_name
            if blob_path.startswith(f"{self.container_name}/"):
                blob_name = blob_path[len(self.container_name) + 1:]  # Remove "container/" prefix
                full_path = blob_path
                logger.info(f"Processing {blob_path} (extracted blob name: {blob_name})")
            else:
                blob_name = blob_path
                full_path = f"{self.container_name}/{blob_path}"
                logger.info(f"Processing {blob_path} (constructed full path: {full_path})")

            # In-flight guard: the periodic refresh AND the change-feed event stream both call this
            # method, and either can trigger for the same blob during the ~15-30s ingest window
            # before document_state is written — so a document_state check alone can't dedup a
            # concurrent overlap (that's the observed periodic+event double). Skip the second
            # concurrent trigger. asyncio is single-threaded, so this check-then-add is atomic.
            if full_path in self._in_flight:
                logger.info(f"Azure Blob: {full_path} already being ingested (periodic/event overlap) — skipping duplicate")
                return
            self._in_flight.add(full_path)
            _added_inflight = True

            from .. import sync_jobs
            processing_id = sync_jobs.processing_id("az", blob_name)

            # Route ingestion through the backend's data-source pipeline — the SAME path used by
            # the initial ingest — instead of calling system.document_processor /
            # system._ingest_source_documents directly. _process_documents_async() checks
            # settings.enable_langflow_flows and runs the Langflow ingest flow when enabled, so
            # incremental updates now honor regular-vs-Langflow routing (mirrors S3Detector).
            # Scope to just this one blob via the reader's exact "blob" key.
            azure_blob_config = dict(self.config or {})
            azure_blob_config["container_name"] = self.container_name
            azure_blob_config["blob"] = blob_name  # single-blob scope (exact)

            await self.backend._process_documents_async(
                processing_id=processing_id,
                data_source="azure_blob",
                config_id=self.config_id,
                graphs=graphs,
                azure_blob_config=azure_blob_config,
            )

            # Don't record state if the ingest did not complete successfully.
            from backend import PROCESSING_STATUS
            if PROCESSING_STATUS.get(processing_id, {}).get("status") == "failed":
                logger.error(f"Backend ingest failed for {blob_name}; not recording document_state")
                return

            logger.info(f"Successfully processed {blob_name} via backend pipeline (flow-aware routing)")

            # Create document_state directly from Azure Blob metadata. doc_id/source_path use
            # full_path (container/blob_name) to match list_all_files() and process_change_event() —
            # the keys change detection uses — and the doc_id from the initial post-ingestion state.
            if self.state_manager:
                try:
                    from incremental_updates.state_manager import DocumentState

                    container_client = self.blob_service_client.get_container_client(self.container_name)
                    blob_client = container_client.get_blob_client(blob_name)
                    blob_properties = blob_client.get_blob_properties()  # metadata only, no download
                    updated = blob_properties.last_modified
                    ordinal = int(updated.timestamp() * 1_000_000)
                    content_hash = StateManager.compute_content_hash(updated.isoformat())

                    now = datetime.now(timezone.utc)
                    from incremental_updates.doc_graphs import datasource_graphs, synced_times
                    graph_at, rdf_at = synced_times(self, datasource_graphs(self), now)
                    doc_id = f"{self.config_id}:{full_path}"

                    doc_state = DocumentState(
                        doc_id=doc_id,
                        config_id=self.config_id,
                        source_path=full_path,
                        ordinal=ordinal,
                        content_hash=content_hash,
                        source_id=full_path,  # Use full path as source_id
                        modified_timestamp=updated,  # datetime required by PostgreSQL TIMESTAMPTZ
                        vector_synced_at=now,
                        search_synced_at=now,
                        graph_synced_at=graph_at,
                        rdf_synced_at=rdf_at
                    )

                    await self.state_manager.save_state(doc_state)
                    logger.info(f"Created document_state for {full_path}: {doc_id}")

                except Exception as e:
                    logger.error(f"Failed to create document_state for {full_path}: {e}")

        except Exception as e:
            logger.error(f"Failed to process {blob_path} via backend: {e}")
            raise
        finally:
            if _added_inflight and full_path is not None:
                self._in_flight.discard(full_path)

    async def _create_document_state_from_processing_status(
        self, processing_id: str, blob_path: str
    ):
        """Create document_state record after successful processing"""
        from backend import PROCESSING_STATUS
        from incremental_updates.state_manager import DocumentState
        from datetime import datetime, timezone
        
        # Wait a moment for processing to complete
        await asyncio.sleep(0.5)
        
        status_dict = PROCESSING_STATUS.get(processing_id, {})
        if status_dict.get('status') != 'completed':
            logger.warning(f"Processing not yet completed for {blob_path}, skipping document_state creation")
            return
        
        documents = status_dict.get('documents', [])
        if not documents:
            logger.warning(f"No documents found in PROCESSING_STATUS for {blob_path}")
            return
        
        doc = documents[0]
        
        # Use Azure Blob URI as source_id
        source_id = f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{blob_path}"
        modified_timestamp = self.parse_timestamp(doc.metadata.get('modified at'))
        
        # Extract filename from blob path
        filename = blob_path.split('/')[-1]
        
        # Create doc_id
        doc_id = f"{self.config_id}:{filename}"
        
        # Compute actual content hash from document text (not placeholder)
        content_hash = None
        if hasattr(doc, 'text') and doc.text:
            from incremental_updates.state_manager import StateManager
            content_hash = StateManager.compute_content_hash(doc.text)
        
        # Use document's ordinal (modification timestamp) if available
        ordinal = doc.metadata.get('ordinal')
        if not ordinal and modified_timestamp:
            try:
                from datetime import datetime
                if isinstance(modified_timestamp, datetime):
                    ordinal = int(modified_timestamp.timestamp() * 1_000_000)
                else:
                    ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
            except:
                ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        elif not ordinal:
            ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        
        # Record synced timestamps (document is already in vector/search stores after initial ingest)
        now = datetime.now(timezone.utc)
        
        # Create document state
        doc_state = DocumentState(
            doc_id=doc_id,
            config_id=self.config_id,
            source_path=blob_path,
            ordinal=ordinal,
            content_hash=content_hash,
            source_id=source_id,
            modified_timestamp=modified_timestamp,
            vector_synced_at=now,
            search_synced_at=now,
            graph_synced_at=synced_times(self, datasource_graphs(self), now)[0],
            rdf_synced_at=synced_times(self, datasource_graphs(self), now)[1],
        )
        
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for {blob_path}: {doc_id}")
