"""
Google Cloud Storage (GCS) Change Detector

Real-time GCS change detection using Cloud Pub/Sub notifications.
Supports both event-based (Pub/Sub) and periodic (polling) modes.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata
from incremental_updates.state_manager import StateManager

logger = logging.getLogger("flexible_graphrag.incremental.detectors.gcs")

# ---------------------------------------------------------------------------
# Google Cloud SDK Integration
# ---------------------------------------------------------------------------

try:
    from google.cloud import storage
    from google.cloud import pubsub_v1
    from google.api_core.exceptions import GoogleAPIError, NotFound
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    GoogleAPIError = Exception
    NotFound = Exception
    logger.warning("google-cloud-storage and/or google-cloud-pubsub not installed - GCS change detection unavailable")


# ---------------------------------------------------------------------------
# GCS Detector
# ---------------------------------------------------------------------------

class GCSDetector(ChangeDetector):
    """
    GCS change detector using Cloud Pub/Sub notifications.
    
    Features:
    - Event-based detection via GCS -> Pub/Sub notifications
    - Fallback to periodic refresh when Pub/Sub not configured
    - Automatic retry with exponential backoff
    - Proper error handling and logging
    - **NEW**: Uses backend for ADD/MODIFY events (full DocumentProcessor pipeline)
    
    Configuration:
        bucket: GCS bucket name (required)
        bucket_name: GCS bucket name (alternative to 'bucket')
        prefix: GCS prefix/folder filter (optional)
        project_id: GCP project ID (optional, uses default if not set)
        pubsub_subscription: Pub/Sub subscription name for notifications (optional)
        service_account_key: Service account key dict (optional)
        service_account_key_path: Path to service account key JSON (optional)
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # Required config - accept both 'bucket' and 'bucket_name'
        self.bucket = config.get('bucket') or config.get('bucket_name')
        if not self.bucket:
            raise ValueError("GCSDetector requires 'bucket' or 'bucket_name' in config")
        
        self.prefix = config.get('prefix', '')
        self.project_id = config.get('project_id')
        self.pubsub_subscription = config.get('pubsub_subscription')
        
        # Service account credentials
        # Handle both 'service_account_key' (dict) and 'credentials' (JSON string)
        self.service_account_key = config.get('service_account_key')
        if not self.service_account_key and config.get('credentials'):
            # Parse credentials from JSON string
            import json
            self.service_account_key = json.loads(config['credentials'])
            logger.info("Parsed GCS credentials from JSON string")
            
            # Extract project_id from credentials if not explicitly provided
            if not self.project_id and 'project_id' in self.service_account_key:
                self.project_id = self.service_account_key['project_id']
                logger.info(f"Extracted project_id from credentials: {self.project_id}")
        
        self.service_account_key_path = config.get('service_account_key_path')
        
        # Clients
        self.storage_client = None
        self.subscriber_client = None
        
        # Event-based vs periodic mode
        self.use_event_mode = bool(self.pubsub_subscription)
        
        # Pub/Sub state
        self.subscription_path = None
        self.streaming_pull_future = None
        
        # Statistics
        self.events_processed = 0
        self.errors_count = 0
        
        # Backend reference (will be injected by orchestrator)
        self.backend = None
        self.state_manager = None
        self.config_id = None
        
        # Track known objects for CREATE vs MODIFY detection
        self.known_object_names = set()
        
        logger.info(f"GCSDetector initialized - bucket={self.bucket}, prefix={self.prefix}, "
                   f"event_mode={self.use_event_mode}, project_id={self.project_id}")
    
    def _create_storage_client(self):
        """Create GCS Storage client with credentials"""
        if self.service_account_key:
            # Use service account key dict
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_info(
                self.service_account_key
            )
            return storage.Client(credentials=credentials, project=self.project_id)
        elif self.service_account_key_path:
            # Use service account key file
            return storage.Client.from_service_account_json(
                self.service_account_key_path,
                project=self.project_id
            )
        else:
            # Use default credentials
            return storage.Client(project=self.project_id)
    
    async def start(self):
        """Start GCS detector and initialize clients"""
        if not GCS_AVAILABLE:
            logger.error("Cannot start GCS detector - google-cloud libraries not installed")
            raise ImportError("google-cloud-storage and google-cloud-pubsub libraries required")
        
        self._running = True
        
        try:
            # Create Storage client
            self.storage_client = self._create_storage_client()
            
            # Verify bucket access
            await self._verify_bucket_access()
            
            # Populate known objects before starting event monitoring
            await self._populate_known_objects()
            
            # Create Pub/Sub subscriber if subscription provided
            if self.pubsub_subscription:
                logger.info(f"[PUBSUB SETUP] Pub/Sub subscription configured: {self.pubsub_subscription}")
                logger.info(f"[PUBSUB SETUP] Project ID: {self.project_id}")
                logger.info(f"[PUBSUB SETUP] Creating Pub/Sub subscriber client...")
                
                if self.service_account_key:
                    logger.info(f"[PUBSUB SETUP] Using service account key from config")
                    from google.oauth2 import service_account
                    credentials = service_account.Credentials.from_service_account_info(
                        self.service_account_key
                    )
                    self.subscriber_client = pubsub_v1.SubscriberClient(credentials=credentials)
                    logger.info(f"[PUBSUB SETUP] Subscriber client created with service account credentials")
                elif self.service_account_key_path:
                    logger.info(f"[PUBSUB SETUP] Using service account key file: {self.service_account_key_path}")
                    self.subscriber_client = pubsub_v1.SubscriberClient.from_service_account_json(
                        self.service_account_key_path
                    )
                    logger.info(f"[PUBSUB SETUP] Subscriber client created from file")
                else:
                    logger.info(f"[PUBSUB SETUP] Using default credentials")
                    self.subscriber_client = pubsub_v1.SubscriberClient()
                    logger.info(f"[PUBSUB SETUP] Subscriber client created with default credentials")
                
                # Build subscription path
                if not self.project_id:
                    logger.error(f"[PUBSUB SETUP] ERROR: project_id is required but missing!")
                    raise ValueError("project_id required for Pub/Sub subscriptions")
                
                logger.info(f"[PUBSUB SETUP] Building subscription path...")
                self.subscription_path = self.subscriber_client.subscription_path(
                    self.project_id,
                    self.pubsub_subscription
                )
                logger.info(f"[PUBSUB SETUP] SUCCESS: Subscription path: {self.subscription_path}")
                
                # Try to verify subscription exists (optional - requires pubsub.subscriptions.get permission)
                # This is just for diagnostics - streaming pull will work even if this fails
                try:
                    logger.info(f"[PUBSUB SETUP] Attempting to verify subscription (requires pubsub.subscriptions.get permission)...")
                    subscription = self.subscriber_client.get_subscription(
                        request={"subscription": self.subscription_path}
                    )
                    logger.info(f"[PUBSUB SETUP] SUCCESS: Subscription verified!")
                    logger.info(f"[PUBSUB SETUP]   Topic: {subscription.topic}")
                    logger.info(f"[PUBSUB SETUP]   Ack deadline: {subscription.ack_deadline_seconds}s")
                    logger.info(f"[PUBSUB SETUP]   Message retention: {subscription.message_retention_duration.seconds}s")
                except Exception as e:
                    error_msg = str(e)
                    if "403" in error_msg or "PermissionDenied" in str(type(e)):
                        logger.warning(f"[PUBSUB SETUP] WARNING: Could not verify subscription (403 Permission Denied)")
                        logger.warning(f"[PUBSUB SETUP]   Service account '{self.service_account_key.get('client_email', 'UNKNOWN')}' needs Pub/Sub permissions")
                        logger.warning(f"[PUBSUB SETUP]   See GCS-SETUP.md for IAM configuration instructions")
                    elif "404" in error_msg or "NotFound" in str(type(e)):
                        logger.error(f"[PUBSUB SETUP] ERROR: Subscription '{self.pubsub_subscription}' does not exist!")
                        logger.error(f"[PUBSUB SETUP]   See GCS-SETUP.md for subscription creation instructions")
                    else:
                        logger.warning(f"[PUBSUB SETUP] WARNING: Could not verify subscription: {error_msg}")
                        logger.warning(f"[PUBSUB SETUP]   This may indicate missing permissions or configuration issues")
                
                logger.info(f"GCS detector started in EVENT MODE - Pub/Sub subscription: {self.pubsub_subscription}")
            else:
                logger.info("GCS detector started in PERIODIC MODE - no Pub/Sub subscription configured")
            
            logger.info(f"GCS detector started successfully for bucket: {self.bucket}")
            
        except Exception as e:
            self._running = False
            logger.error(f"Failed to start GCS detector: {e}")
            raise
    
    async def _populate_known_objects(self):
        """Populate known_object_names set with all currently existing objects"""
        try:
            logger.info("POPULATE: Starting to populate known_object_names...")
            
            all_files = await self.list_all_files()
            for file_meta in all_files:
                self.known_object_names.add(file_meta.path)
            
            logger.info(f"POPULATE: Populated known_object_names with {len(self.known_object_names)} existing objects")
            
        except Exception as e:
            logger.error(f"Error populating known_object_names: {e}")
    
    async def _verify_bucket_access(self):
        """Verify we can access the GCS bucket"""
        try:
            bucket = self.storage_client.bucket(self.bucket)
            
            # Try to list blobs with limit 1 to verify access
            blobs = list(bucket.list_blobs(prefix=self.prefix or None, max_results=1))
            
            logger.info(f"GCS bucket access verified: {self.bucket}")
            
        except NotFound:
            logger.error(f"GCS bucket not found: {self.bucket}")
            raise
        except GoogleAPIError as e:
            logger.error(f"Error accessing GCS bucket {self.bucket}: {e}")
            raise
    
    async def stop(self):
        """Stop GCS detector"""
        self._running = False
        
        # Cancel Pub/Sub subscription if active
        if self.streaming_pull_future:
            self.streaming_pull_future.cancel()
            self.streaming_pull_future = None
        
        # Close clients
        if self.subscriber_client:
            self.subscriber_client.close()
            self.subscriber_client = None
        
        self.storage_client = None
        
        logger.info(f"GCS detector stopped. Events processed: {self.events_processed}, Errors: {self.errors_count}")
    
    async def list_all_files(self) -> List[FileMetadata]:
        """List all objects in the bucket (for initial/periodic sync)"""
        if not self.storage_client:
            raise RuntimeError("GCS detector not started")
        
        files = []
        try:
            bucket = self.storage_client.bucket(self.bucket)
            
            # List blobs with prefix filter
            blobs = bucket.list_blobs(prefix=self.prefix or None)
            
            for blob in blobs:
                # Skip directories (blobs ending with /)
                if blob.name.endswith('/'):
                    continue
                
                # Convert updated time to microsecond timestamp
                updated = blob.updated or datetime.now(timezone.utc)
                ordinal = int(updated.timestamp() * 1_000_000)
                
                # Use full path (bucket/object_key) to match what GCSReader returns in file_path
                # This ensures consistency with document_state source_path
                full_path = f"{self.bucket}/{blob.name}"
                
                metadata = FileMetadata(
                    source_type='gcs',
                    path=full_path,  # Full path: bucket/object_key
                    ordinal=ordinal,
                    size_bytes=blob.size,
                    modified_timestamp=updated.isoformat() if updated else None,
                    extra={
                        'bucket': self.bucket,
                        'object_key': blob.name,
                        'content_type': blob.content_type,
                        'etag': blob.etag
                    }
                )
                files.append(metadata)
            
            logger.info(f"Listed {len(files)} objects from GCS bucket {self.bucket}")
            
        except Exception as e:
            logger.error(f"Error listing files from GCS: {e}")
            raise
        
        return files
    
    async def load_file_content(self, object_path: str) -> bytes:
        """
        Download a single file from GCS.
        
        Args:
            object_path: Full path (bucket/object_key) or just object_key
            
        Returns:
            File content as bytes
        """
        if not self.storage_client:
            raise RuntimeError("GCS detector not started")
        
        # Extract object key from full path if needed
        if object_path.startswith(f"{self.bucket}/"):
            object_key = object_path[len(self.bucket) + 1:]
        else:
            object_key = object_path
        
        try:
            bucket = self.storage_client.bucket(self.bucket)
            blob = bucket.blob(object_key)
            
            logger.info(f"Downloading {object_key} from GCS bucket {self.bucket}...")
            content = blob.download_as_bytes()
            logger.info(f"Downloaded {len(content)} bytes from {object_key}")
            
            return content
            
        except Exception as e:
            logger.error(f"Error downloading {object_key} from GCS: {e}")
            raise
    
    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """
        Stream change events from GCS via Pub/Sub.
        Yields change events as they are detected.
        """
        if not self._running:
            return
        
        if not self.subscriber_client or not self.subscription_path:
            # Pub/Sub not available - caller should use periodic refresh
            logger.debug("Pub/Sub not available - no events to stream")
            return
        
        logger.info(f"Starting GCS Pub/Sub monitoring: {self.subscription_path}")
        
        # Create async queue to bridge Pub/Sub callback to async generator
        event_queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        
        def pubsub_callback(message):
            """Callback for Pub/Sub messages"""
            try:
                logger.info(f"[PUBSUB] Received message! Attributes: {message.attributes}")
                logger.info(f"[PUBSUB] Message ID: {message.message_id}")
                logger.info(f"[PUBSUB] Publish time: {message.publish_time}")
                
                # Parse Pub/Sub message
                event = self._parse_pubsub_message(message)
                if event:
                    logger.info(f"[PUBSUB] Parsed event: {event.change_type.value} for {event.metadata.path}")
                    # Put event in queue (non-blocking, thread-safe)
                    logger.info(f"[PUBSUB] Adding event to queue...")
                    loop.call_soon_threadsafe(event_queue.put_nowait, event)
                    logger.info(f"[PUBSUB] Event added to queue, queue size: {event_queue.qsize()}")
                    self.events_processed += 1
                else:
                    logger.warning(f"[PUBSUB] Message parsed but returned None (filtered out)")
                
                # Acknowledge message
                message.ack()
                logger.info(f"[PUBSUB] Message acknowledged")
                
            except Exception as e:
                logger.error(f"[PUBSUB] Error processing GCS Pub/Sub message: {e}", exc_info=True)
                self.errors_count += 1
                message.nack()
        
        # Start streaming pull in background
        logger.info(f"[PUBSUB] Starting streaming pull...")
        logger.info(f"[PUBSUB] Subscription path: {self.subscription_path}")
        logger.info(f"[PUBSUB] Project ID: {self.project_id}")
        
        try:
            self.streaming_pull_future = self.subscriber_client.subscribe(
                self.subscription_path,
                callback=pubsub_callback
            )
            logger.info(f"[PUBSUB] Streaming pull started successfully! Waiting for messages...")
        except Exception as e:
            logger.error(f"[PUBSUB] Failed to start streaming pull: {e}", exc_info=True)
            return
        
        # Stream events from queue
        logger.info(f"[PUBSUB] Starting event queue processing loop...")
        loop_iterations = 0
        while self._running:
            try:
                loop_iterations += 1
                if loop_iterations % 60 == 0:  # Log every 60 seconds
                    logger.debug(f"[PUBSUB] Event loop still running (iteration {loop_iterations}), queue size: {event_queue.qsize()}")
                
                # Wait for events with timeout
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                
                if not event:
                    logger.debug(f"[PUBSUB] Got None event from queue, skipping...")
                    continue
                
                logger.info(f"[PUBSUB] Processing event from queue: {event.change_type.value} for {event.metadata.path}")
                
                # Handle different event types
                if event.change_type == ChangeType.DELETE:
                    # Yield DELETE events for engine to handle
                    logger.info(f"GCS EVENT: DELETE for {event.metadata.path}")
                    yield event
                
                elif event.change_type == ChangeType.CREATE:
                    # Check if truly new (using known_object_names)
                    object_name = event.metadata.path
                    is_new = object_name not in self.known_object_names
                    
                    if is_new:
                        # Truly new - CREATE
                        logger.info(f"GCS EVENT: CREATE for {object_name}")
                        self.known_object_names.add(object_name)
                        try:
                            await self._process_via_backend(object_name)
                            logger.info(f"SUCCESS: Processed CREATE for {object_name}")
                        except Exception as e:
                            logger.error(f"ERROR: Failed to process CREATE for {object_name}: {e}")
                    else:
                        # Already known - treat as UPDATE (DELETE + ADD)
                        logger.info(f"GCS EVENT: UPDATE (reported as CREATE) for {object_name}")
                        
                        async def add_callback():
                            logger.info(f"UPDATE: DELETE completed, now processing ADD for {object_name}")
                            try:
                                await self._process_via_backend(object_name)
                                logger.info(f"SUCCESS: UPDATE completed for {object_name}")
                            except Exception as e:
                                logger.error(f"ERROR: Failed to process ADD for {object_name}: {e}")
                        
                        delete_metadata = FileMetadata(
                            source_type='gcs',
                            path=object_name,
                            ordinal=event.metadata.ordinal,
                            extra={'bucket': self.bucket}
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
                    object_name = event.metadata.path
                    logger.info(f"GCS EVENT: UPDATE for {object_name}")
                    
                    # Check if truly known (might be false positive)
                    is_new = object_name not in self.known_object_names
                    
                    if is_new:
                        # Actually new - treat as CREATE
                        logger.info(f"GCS EVENT: CREATE (reported as UPDATE) for {object_name}")
                        self.known_object_names.add(object_name)
                        try:
                            await self._process_via_backend(object_name)
                            logger.info(f"SUCCESS: Processed CREATE for {object_name}")
                        except Exception as e:
                            logger.error(f"ERROR: Failed to process CREATE for {object_name}: {e}")
                    else:
                        # True UPDATE - DELETE + ADD
                        logger.info(f"GCS EVENT: UPDATE - emitting DELETE with callback")
                        
                        async def add_callback():
                            logger.info(f"UPDATE: DELETE completed, now processing ADD for {object_name}")
                            try:
                                await self._process_via_backend(object_name)
                                logger.info(f"SUCCESS: UPDATE completed for {object_name}")
                            except Exception as e:
                                logger.error(f"ERROR: Failed to process ADD for {object_name}: {e}")
                        
                        delete_metadata = FileMetadata(
                            source_type='gcs',
                            path=object_name,
                            ordinal=event.metadata.ordinal,
                            extra={'bucket': self.bucket}
                        )
                        delete_event = ChangeEvent(
                            metadata=delete_metadata,
                            change_type=ChangeType.DELETE,
                            timestamp=event.timestamp,
                            is_modify_delete=True,
                            modify_callback=add_callback
                        )
                        yield delete_event
                
            except asyncio.TimeoutError:
                # No events, continue
                continue
            
            except Exception as e:
                logger.error(f"Error streaming GCS events: {e}")
                self.errors_count += 1
                await asyncio.sleep(1)
    
    def _parse_pubsub_message(self, message) -> Optional[ChangeEvent]:
        """Parse GCS Pub/Sub notification into ChangeEvent"""
        try:
            # Parse message data
            data = json.loads(message.data.decode('utf-8'))
            
            logger.info(f"[PUBSUB PARSE] Raw data keys: {list(data.keys())}")
            
            # IMPORTANT: GCS sends eventType in message ATTRIBUTES, not in data!
            event_type = message.attributes.get('eventType', '')
            logger.info(f"[PUBSUB PARSE] Event type from attributes: {event_type}")
            logger.info(f"[PUBSUB PARSE] Object name: {data.get('name', 'MISSING')}")
            
            # Get object name (path)
            object_name = data.get('name', '')
            
            # IMPORTANT: GCS Pub/Sub sends object name WITHOUT bucket prefix
            # But document_state stores it WITH bucket prefix (bucket/object)
            # We need to add bucket prefix for consistency with document_state
            full_path = f"{self.bucket}/{object_name}"
            
            logger.info(f"[PUBSUB PARSE] Object name from message: {object_name}")
            logger.info(f"[PUBSUB PARSE] Full path for processing: {full_path}")
            
            # Apply prefix filter (use original object_name for filter)
            if self.prefix and not object_name.startswith(self.prefix):
                logger.info(f"[PUBSUB PARSE] Filtered out by prefix: {object_name} (prefix={self.prefix})")
                return None
            
            # Skip directories
            if object_name.endswith('/'):
                logger.info(f"[PUBSUB PARSE] Skipping directory: {object_name}")
                return None
            
            # Get event type from attributes (not data!)
            
            # Map GCS event types to ChangeType
            if event_type == 'OBJECT_FINALIZE':
                # OBJECT_FINALIZE can be create or update
                # Use generation to determine (generation 1 = new object)
                generation = data.get('generation', 1)
                change_type = ChangeType.CREATE if generation == 1 else ChangeType.UPDATE
            elif event_type == 'OBJECT_DELETE':
                change_type = ChangeType.DELETE
            elif event_type == 'OBJECT_ARCHIVE':
                change_type = ChangeType.DELETE  # Treat archive as delete
            else:
                logger.debug(f"Ignoring GCS event type: {event_type}")
                return None
            
            # Get timestamp
            time_created = data.get('timeCreated') or data.get('updated')
            if time_created:
                event_time = datetime.fromisoformat(time_created.replace('Z', '+00:00'))
            else:
                event_time = datetime.now(timezone.utc)
            
            ordinal = int(event_time.timestamp() * 1_000_000)
            
            # Use full path (bucket/object) for consistency with document_state
            metadata = FileMetadata(
                source_type='gcs',
                path=full_path,  # Use bucket/object format
                ordinal=ordinal,
                size_bytes=data.get('size'),
                mime_type=data.get('contentType'),
                modified_timestamp=event_time.isoformat(),
                extra={
                    'generation': str(data.get('generation', '')),
                    'metageneration': str(data.get('metageneration', '')),
                    'bucket': data.get('bucket', self.bucket),
                    'event_type': event_type,
                    'object_name': object_name,  # Store original object name too
                }
            )
            
            return ChangeEvent(
                metadata=metadata,
                change_type=change_type,
                timestamp=event_time
            )
            
        except Exception as e:
            logger.warning(f"Error parsing GCS Pub/Sub message: {e}")
            return None
    
    async def _process_via_backend(self, object_name: str):
        """
        Process GCS object by downloading it directly and passing to backend.
        Unlike directory-based processing, this downloads only the specific file.
        
        Args:
            object_name: GCS object name - can be either:
                         - Just the object key (e.g., 'sample-docs/test/file.txt')
                         - Full path (e.g., 'bucket/sample-docs/test/file.txt')
        """
        if not self.backend:
            logger.error("Backend not injected into GCSDetector - cannot process object")
            return
        
        # Extract object key from full path if needed
        # Full path format: bucket/object_key
        if object_name.startswith(f"{self.bucket}/"):
            object_key = object_name[len(self.bucket) + 1:]  # Remove "bucket/" prefix
            logger.info(f"Processing {object_name} via backend (extracted key: {object_key})")
        else:
            object_key = object_name
            logger.info(f"Processing {object_name} via backend (direct download)")
        
        try:
            import tempfile
            import os
            
            skip_graph = getattr(self, 'skip_graph', False)
            processing_id = f"incremental_gcs_{object_key.replace('/', '_').replace('.', '_')[:16]}"
            
            # Download file to temporary location
            bucket = self.storage_client.bucket(self.bucket)
            blob = bucket.blob(object_key)
            
            # Get original filename
            filename = os.path.basename(object_key)
            
            # Create temp file with original extension
            suffix = os.path.splitext(filename)[1]
            with tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, delete=False) as tmp_file:
                temp_path = tmp_file.name
                logger.info(f"Downloading {object_key} to {temp_path}...")
                blob.download_to_file(tmp_file)
            
            logger.info(f"Downloaded {object_key} ({blob.size} bytes)")
            
            try:
                # Get blob metadata for document_state creation
                updated = blob.updated or datetime.now(timezone.utc)
                ordinal = int(updated.timestamp() * 1_000_000)
                content_hash = StateManager.compute_content_hash(updated.isoformat())
                
                # Create a placeholder Document with GCS metadata
                # This ensures the doc_id is set correctly (bucket/object_key instead of temp path)
                from llama_index.core import Document
                
                full_path = f"{self.bucket}/{object_key}"
                
                placeholder_doc = Document(
                    text="",  # Will be filled by DocumentProcessor
                    metadata={
                        "file_path": temp_path,  # ACTUAL temp file location for DocumentProcessor
                        "file_name": filename,
                        "source": "gcs",
                        "bucket_name": self.bucket,
                        "object_key": object_key,  # Store the GCS object key
                        "gcs_path": full_path,  # Store the full GCS path for reference
                        "last_modified_date": updated.isoformat(),
                        "size": blob.size,
                        "content_type": blob.content_type,
                    }
                )
                
                # Process the document via DocumentProcessor
                # This will parse the temp file but preserve GCS metadata
                doc_processor = self.backend.system.document_processor
                processed_docs = await doc_processor.process_documents_from_metadata([placeholder_doc])
                
                # Restore GCS metadata (in case DocumentProcessor overwrote it)
                for doc in processed_docs:
                    doc.metadata.update({
                        "file_path": object_key,  # Use object key for doc_id generation
                        "file_name": filename,    # Restore correct filename (not temp name)
                        "source": "gcs",
                        "bucket_name": self.bucket,
                    })
                
                # Index the processed documents via backend
                await self.backend.system._process_documents_direct(
                    processed_docs,
                    processing_id=processing_id,
                    skip_graph=skip_graph,
                    config_id=self.config_id
                )
                
                logger.info(f"Successfully processed {object_key} via backend pipeline")
                
                # Create document_state record directly from GCS metadata
                # Don't try to extract from filesystem processing (temp files have wrong metadata)
                if self.state_manager:
                    try:
                        from incremental_updates.state_manager import DocumentState
                        
                        now = datetime.now(timezone.utc)
                        skip_graph_flag = getattr(self, 'skip_graph', False)
                        
                        # doc_id format: config_id:source_path
                        doc_id = f"{self.config_id}:{full_path}"
                        
                        doc_state = DocumentState(
                            doc_id=doc_id,
                            config_id=self.config_id,
                            source_path=full_path,
                            ordinal=ordinal,
                            content_hash=content_hash,
                            source_id=full_path,  # Use full path as source_id
                            modified_timestamp=updated.isoformat(),
                            vector_synced_at=now,
                            search_synced_at=now,
                            graph_synced_at=now if not skip_graph_flag else None
                        )
                        
                        await self.state_manager.save_state(doc_state)
                        logger.info(f"Created document_state for {full_path}: {doc_id}")
                        
                    except Exception as e:
                        logger.error(f"Failed to create document_state for {full_path}: {e}")
            
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                    logger.debug(f"Cleaned up temp file: {temp_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_path}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process {object_name} via backend: {e}")
            raise
    
    async def _create_document_state_from_processing_status(
        self, processing_id: str, object_name: str
    ):
        """Create document_state record after successful processing"""
        from backend import PROCESSING_STATUS
        from incremental_updates.state_manager import DocumentState
        from datetime import datetime, timezone
        
        # Wait a moment for processing to complete
        await asyncio.sleep(0.5)
        
        status_dict = PROCESSING_STATUS.get(processing_id, {})
        if status_dict.get('status') != 'completed':
            logger.warning(f"Processing not yet completed for {object_name}, skipping document_state creation")
            return
        
        documents = status_dict.get('documents', [])
        if not documents:
            logger.warning(f"No documents found in PROCESSING_STATUS for {object_name}")
            return
        
        doc = documents[0]
        
        # Use GCS URI as source_id
        source_id = f"gs://{self.bucket}/{object_name}"
        modified_timestamp = doc.metadata.get('modified at')
        
        # Extract filename from object name
        filename = object_name.split('/')[-1]
        
        # Create doc_id
        doc_id = f"{self.config_id}:{filename}"
        
        # Compute content hash (placeholder)
        content_hash = "placeholder"
        
        # Create document state
        doc_state = DocumentState(
            doc_id=doc_id,
            config_id=self.config_id,
            source_path=object_name,
            ordinal=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
            content_hash=content_hash,
            source_id=source_id,
            modified_timestamp=modified_timestamp
        )
        
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for {object_name}: {doc_id}")
