"""
S3 Change Detector

Real-time S3 change detection using S3 Event Notifications + SQS.
Supports both event-based (real-time) and periodic (polling) modes.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata

logger = logging.getLogger("flexible_graphrag.incremental.detectors.s3")

# ---------------------------------------------------------------------------
# boto3 Integration
# ---------------------------------------------------------------------------

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    ClientError = Exception
    BotoCoreError = Exception
    logger.warning("boto3 not installed - S3 change detection unavailable")


# ---------------------------------------------------------------------------
# S3 Detector
# ---------------------------------------------------------------------------

class S3Detector(ChangeDetector):
    """
    S3 change detector using SQS event notifications.
    
    Features:
    - Event-based detection via S3 -> SQS notifications
    - Fallback to periodic refresh when SQS not configured
    - Automatic retry with exponential backoff
    - Proper error handling and logging
    - Support for SNS -> SQS wrapper pattern
    - **NEW**: Uses backend for ADD/MODIFY events (full DocumentProcessor pipeline)
    
    Configuration:
        bucket: S3 bucket name (required)
        prefix: S3 prefix/folder filter (optional)
        sqs_queue_url: SQS queue URL for event notifications (optional)
        aws_region: AWS region (default: us-east-1)
        aws_access_key_id: AWS access key (optional, uses default credentials if not set)
        aws_secret_access_key: AWS secret key (optional)
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # Required config - accept both 'bucket' and 'bucket_name'
        self.bucket = config.get('bucket') or config.get('bucket_name')
        if not self.bucket:
            raise ValueError("S3Detector requires 'bucket' or 'bucket_name' in config")
        
        self.prefix = config.get('prefix') or config.get('prefix', '') or ''  # Must be string, not None
        self.sqs_queue_url = config.get('sqs_queue_url')
        self.aws_region = config.get('aws_region') or config.get('region_name') or 'us-east-1'  # Must have default
        
        # Optional AWS credentials - check multiple key names for compatibility
        self.aws_access_key_id = (
            config.get('aws_access_key_id') or 
            config.get('access_key')
        )
        self.aws_secret_access_key = (
            config.get('aws_secret_access_key') or 
            config.get('secret_key')
        )
        
        # Clients
        self.s3_client = None
        self.sqs_client = None
        
        # Event-based vs periodic mode
        self.use_event_mode = bool(self.sqs_queue_url)
        
        # Retry configuration
        self.max_retries = 3
        self.base_retry_delay = 1.0  # seconds
        
        # Statistics
        self.events_processed = 0
        self.errors_count = 0
        
        # Backend reference (will be injected by orchestrator)
        self.backend = None
        self.state_manager = None
        self.config_id = None
        
        # Track known objects for CREATE vs MODIFY detection
        self.known_object_keys = set()
        
        logger.info(f"S3Detector initialized - bucket={self.bucket}, prefix={self.prefix}, "
                   f"event_mode={self.use_event_mode}, region={self.aws_region}")
    
    def _create_boto_session_kwargs(self) -> Dict:
        """Create boto3 session kwargs with optional credentials"""
        kwargs = {'region_name': self.aws_region}
        
        if self.aws_access_key_id and self.aws_secret_access_key:
            kwargs['aws_access_key_id'] = self.aws_access_key_id
            kwargs['aws_secret_access_key'] = self.aws_secret_access_key
        
        return kwargs
    
    async def start(self):
        """Start S3 detector and initialize AWS clients"""
        if not BOTO3_AVAILABLE:
            logger.error("Cannot start S3 detector - boto3 not installed")
            raise ImportError("boto3 library required for S3 detector")
        
        self._running = True
        
        try:
            # Create S3 client
            boto_kwargs = self._create_boto_session_kwargs()
            self.s3_client = boto3.client('s3', **boto_kwargs)
            
            # Verify bucket access
            await self._verify_bucket_access()
            
            # Populate known objects before starting event monitoring
            await self._populate_known_objects()
            
            # Create SQS client if queue URL provided
            if self.sqs_queue_url:
                self.sqs_client = boto3.client('sqs', **boto_kwargs)
                await self._verify_sqs_access()
                logger.info(f"S3 detector started in EVENT MODE - SQS queue: {self.sqs_queue_url}")
            else:
                logger.info(f"S3 detector started in PERIODIC MODE - no SQS queue configured")
            
            logger.info(f"S3 detector started successfully for bucket: {self.bucket}")
            
        except Exception as e:
            self._running = False
            logger.error(f"Failed to start S3 detector: {e}")
            raise
    
    async def _populate_known_objects(self):
        """Populate known_object_keys set with all currently existing objects"""
        try:
            logger.info("POPULATE: Starting to populate known_object_keys...")
            
            all_files = await self.list_all_files()
            for file_meta in all_files:
                self.known_object_keys.add(file_meta.path)
            
            logger.info(f"POPULATE: Populated known_object_keys with {len(self.known_object_keys)} existing objects")
            
        except Exception as e:
            logger.error(f"Error populating known_object_keys: {e}")
    
    async def _verify_bucket_access(self):
        """Verify we can access the S3 bucket"""
        try:
            # Try to list objects with limit 1 to verify access
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=self.prefix,
                MaxKeys=1
            )
            logger.info(f"S3 bucket access verified: {self.bucket}")
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchBucket':
                raise ValueError(f"S3 bucket does not exist: {self.bucket}")
            elif error_code == 'AccessDenied':
                raise PermissionError(f"Access denied to S3 bucket: {self.bucket}")
            else:
                raise RuntimeError(f"Error accessing S3 bucket: {e}")
    
    async def _verify_sqs_access(self):
        """Verify we can access the SQS queue"""
        try:
            # Try to get queue attributes to verify access
            self.sqs_client.get_queue_attributes(
                QueueUrl=self.sqs_queue_url,
                AttributeNames=['ApproximateNumberOfMessages']
            )
            logger.info(f"SQS queue access verified: {self.sqs_queue_url}")
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code in ('QueueDoesNotExist', 'AWS.SimpleQueueService.NonExistentQueue'):
                raise ValueError(f"SQS queue does not exist: {self.sqs_queue_url}")
            elif error_code == 'AccessDenied':
                raise PermissionError(f"Access denied to SQS queue: {self.sqs_queue_url}")
            else:
                raise RuntimeError(f"Error accessing SQS queue: {e}")
    
    async def stop(self):
        """Stop S3 detector"""
        self._running = False
        logger.info(f"S3 detector stopped - events_processed={self.events_processed}, "
                   f"errors={self.errors_count}")
    
    async def list_all_files(self) -> List[FileMetadata]:
        """
        List all objects in bucket (periodic refresh / initial scan).
        
        Uses pagination to handle large buckets efficiently.
        """
        if not self.s3_client:
            logger.warning("S3 client not initialized")
            return []
        
        files = []
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                paginator = self.s3_client.get_paginator('list_objects_v2')
                page_count = 0
                
                for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
                    page_count += 1
                    
                    for obj in page.get('Contents', []):
                        # Skip folders (keys ending with /)
                        if obj['Key'].endswith('/'):
                            continue
                        
                        # Convert LastModified to microsecond timestamp
                        ordinal = int(obj['LastModified'].timestamp() * 1_000_000)
                        
                        # Use bucket/key format for path (for display/logging)
                        path_with_bucket = f"{self.bucket}/{obj['Key']}"
                        
                        # Include s3_uri in extra for consistent identifier matching with document_state
                        s3_uri = f"s3://{self.bucket}/{obj['Key']}"
                        
                        files.append(FileMetadata(
                            source_type='s3',
                            path=path_with_bucket,
                            ordinal=ordinal,
                            size_bytes=obj['Size'],
                            extra={
                                'etag': obj['ETag'].strip('"'),
                                's3_uri': s3_uri  # Add s3_uri for identifier matching
                            }
                        ))
                    
                    # Yield control periodically for large buckets
                    if page_count % 10 == 0:
                        await asyncio.sleep(0)
                
                logger.info(f"Listed {len(files)} files from S3 bucket: {self.bucket}/{self.prefix}")
                return files
                
            except ClientError as e:
                retry_count += 1
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                
                if retry_count < self.max_retries:
                    delay = self.base_retry_delay * (2 ** (retry_count - 1))
                    logger.warning(f"S3 list error (attempt {retry_count}/{self.max_retries}): "
                                 f"{error_code} - retrying in {delay}s")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Failed to list S3 objects after {self.max_retries} attempts: {e}")
                    self.errors_count += 1
                    return files
            
            except Exception as e:
                logger.exception(f"Unexpected error listing S3 objects: {e}")
                self.errors_count += 1
                return files
        
        return files
    
    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """
        Stream S3 events from SQS queue.
        
        NEW BEHAVIOR:
        - For CREATE: Check known_object_keys, then process via backend
        - For UPDATE/MODIFY: Emit DELETE with callback, callback processes ADD after DELETE completes
        - For DELETE: Yield event for engine to handle
        
        This ensures ADD/MODIFY use DocumentProcessor for ALL file types (PDF, DOCX, etc.)
        
        Continuously polls SQS for S3 event notifications:
        - ObjectCreated:* -> CREATE
        - ObjectRemoved:* -> DELETE
        - Other -> UPDATE
        
        Supports both direct S3->SQS and S3->SNS->SQS patterns.
        """
        if not self.sqs_client or not self.sqs_queue_url:
            logger.warning("SQS not configured - change stream unavailable. "
                         "Use periodic refresh via list_all_files() instead.")
            return
        
        logger.info(f"Starting S3 event stream from SQS: {self.sqs_queue_url}")
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        # Use thread pool executor for blocking boto3 calls
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        
        try:
            while self._running:
                try:
                    # Run blocking SQS call in executor with timeout
                    loop = asyncio.get_event_loop()
                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            executor,
                            lambda: self.sqs_client.receive_message(
                                QueueUrl=self.sqs_queue_url,
                                MaxNumberOfMessages=10,
                                WaitTimeSeconds=20,  # Max long-poll for efficiency
                                AttributeNames=['ApproximateReceiveCount']
                            )
                        ),
                        timeout=25.0  # Slightly longer than WaitTimeSeconds
                    )
                    
                    messages = response.get('Messages', [])
                    
                    if not messages:
                        # No messages, yield None to allow other processing
                        yield None
                        continue
                    
                    logger.debug(f"Received {len(messages)} SQS messages")
                    
                    for message in messages:
                        receipt_handle = message['ReceiptHandle']
                        
                        try:
                            # Parse message body
                            body = json.loads(message['Body'])
                            
                            # Handle SNS wrapper if present (S3 -> SNS -> SQS pattern)
                            if 'Message' in body and 'Type' in body:
                                # SNS notification wrapper
                                s3_event = json.loads(body['Message'])
                            else:
                                # Direct S3 -> SQS
                                s3_event = body
                            
                            # Process S3 event records
                            for record in s3_event.get('Records', []):
                                event_name = record.get('eventName', '')
                                s3_info = record.get('s3', {})
                                bucket_name = s3_info.get('bucket', {}).get('name')
                                key = s3_info.get('object', {}).get('key')
                                size = s3_info.get('object', {}).get('size')
                                
                                # Filter by bucket and validate key
                                if bucket_name != self.bucket:
                                    logger.debug(f"Skipping event for different bucket: {bucket_name}")
                                    continue
                                
                                if not key:
                                    logger.warning(f"S3 event missing object key: {event_name}")
                                    continue
                                
                                # Filter by prefix if configured
                                if self.prefix and not key.startswith(self.prefix):
                                    logger.debug(f"Skipping event outside prefix: {key}")
                                    continue
                                
                                # Use bucket/key format to match document_state paths
                                path_with_bucket = f"{self.bucket}/{key}"
                                
                                # Determine change type from event name
                                if 'ObjectCreated' in event_name:
                                    # Check if truly new (use path_with_bucket for comparison)
                                    is_new = path_with_bucket not in self.known_object_keys
                                    
                                    logger.info(f"ObjectCreated event for {key}: is_new={is_new}")
                                    
                                    if is_new:
                                        # Truly new object - CREATE
                                        logger.info(f"EVENT: CREATE detected for {key}")
                                        self.known_object_keys.add(path_with_bucket)
                                        try:
                                            await self._process_via_backend(key)
                                            logger.info(f"SUCCESS: Processed {key} via backend pipeline")
                                        except Exception as e:
                                            logger.error(f"ERROR: Failed to process {key} via backend: {e}")
                                    else:
                                        # Already known - treat as MODIFY (DELETE + ADD)
                                        logger.info(f"EVENT: MODIFY detected for {key}")
                                        logger.info(f"MODIFY: Emitting DELETE event with callback for {key}")
                                        
                                        async def add_callback():
                                            logger.info(f"MODIFY: DELETE completed, now processing ADD for {key}")
                                            try:
                                                await self._process_via_backend(key)
                                                logger.info(f"SUCCESS: MODIFY completed for {key}")
                                            except Exception as e:
                                                logger.error(f"ERROR: Failed to process ADD for {key}: {e}")
                                        
                                        ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
                                        delete_metadata = FileMetadata(
                                            source_type='s3',
                                            path=path_with_bucket,  # Use bucket/key format
                                            ordinal=ordinal,
                                            extra={'event_name': event_name}
                                        )
                                        delete_event = ChangeEvent(
                                            metadata=delete_metadata,
                                            change_type=ChangeType.DELETE,
                                            timestamp=datetime.utcnow(),
                                            is_modify_delete=True,
                                            modify_callback=add_callback
                                        )
                                        yield delete_event
                                
                                elif 'ObjectRemoved' in event_name:
                                    # DELETE
                                    if path_with_bucket in self.known_object_keys:
                                        self.known_object_keys.discard(path_with_bucket)
                                    
                                    ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
                                    metadata = FileMetadata(
                                        source_type='s3',
                                        path=path_with_bucket,  # Use bucket/key format
                                        ordinal=ordinal,
                                        size_bytes=size,
                                        extra={
                                            'event_name': event_name,
                                            'etag': s3_info.get('object', {}).get('eTag', '').strip('"')
                                        }
                                    )
                                    
                                    event = ChangeEvent(
                                        metadata=metadata,
                                        change_type=ChangeType.DELETE,
                                        timestamp=datetime.utcnow()
                                    )
                                    
                                    logger.info(f"S3 event: DELETE - {key} ({event_name})")
                                    self.events_processed += 1
                                    yield event
                                
                                else:
                                    # ObjectRestore, ObjectTagging, etc. - treat as UPDATE
                                    is_new = path_with_bucket not in self.known_object_keys
                                    
                                    logger.info(f"Other S3 event for {key}: {event_name}, is_new={is_new}")
                                    
                                    if is_new:
                                        logger.info(f"EVENT: CREATE detected for {key}")
                                        self.known_object_keys.add(path_with_bucket)
                                        try:
                                            await self._process_via_backend(key)
                                            logger.info(f"SUCCESS: Processed {key} via backend pipeline")
                                        except Exception as e:
                                            logger.error(f"ERROR: Failed to process {key} via backend: {e}")
                                    else:
                                        logger.info(f"EVENT: MODIFY detected for {key}")
                                        
                                        async def add_callback():
                                            logger.info(f"MODIFY: DELETE completed, now processing ADD for {key}")
                                            try:
                                                await self._process_via_backend(key)
                                                logger.info(f"SUCCESS: MODIFY completed for {key}")
                                            except Exception as e:
                                                logger.error(f"ERROR: Failed to process ADD for {key}: {e}")
                                        
                                        ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
                                        delete_metadata = FileMetadata(
                                            source_type='s3',
                                            path=path_with_bucket,  # Use bucket/key format
                                            ordinal=ordinal,
                                            extra={'event_name': event_name}
                                        )
                                        delete_event = ChangeEvent(
                                            metadata=delete_metadata,
                                            change_type=ChangeType.DELETE,
                                            timestamp=datetime.utcnow(),
                                            is_modify_delete=True,
                                            modify_callback=add_callback
                                        )
                                        yield delete_event
                        
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse SQS message JSON: {e}")
                            logger.debug(f"Message body: {message.get('Body', '')[:500]}")
                            self.errors_count += 1
                        
                        except KeyError as e:
                            logger.error(f"Missing expected field in S3 event: {e}")
                            logger.debug(f"Message body: {message.get('Body', '')[:500]}")
                            self.errors_count += 1
                        
                        except Exception as e:
                            logger.exception(f"Error processing S3 event: {e}")
                            self.errors_count += 1
                        
                        finally:
                            # Always delete message from queue (even on error)
                            try:
                                # Run delete in executor too (non-blocking)
                                await loop.run_in_executor(
                                    executor,
                                    lambda: self.sqs_client.delete_message(
                                        QueueUrl=self.sqs_queue_url,
                                        ReceiptHandle=receipt_handle
                                    )
                                )
                            except Exception as e:
                                logger.error(f"Failed to delete SQS message: {e}")
                    
                    # Reset error counter on successful batch
                    consecutive_errors = 0
                
                except asyncio.TimeoutError:
                    # SQS receive timed out, continue loop
                    logger.debug("SQS receive timed out, continuing...")
                    consecutive_errors = 0
                    yield None
                
                except ClientError as e:
                    consecutive_errors += 1
                    error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                    logger.error(f"AWS error receiving SQS messages ({consecutive_errors}/{max_consecutive_errors}): "
                               f"{error_code} - {e}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.critical(f"Too many consecutive SQS errors, stopping detector")
                        self._running = False
                        break
                    
                    # Exponential backoff
                    delay = min(30, self.base_retry_delay * (2 ** consecutive_errors))
                    await asyncio.sleep(delay)
                
                except (KeyboardInterrupt, asyncio.CancelledError):
                    logger.info("S3 detector interrupted, stopping gracefully...")
                    self._running = False
                    break
                
                except Exception as e:
                    consecutive_errors += 1
                    logger.exception(f"Unexpected error in S3 change stream ({consecutive_errors}/{max_consecutive_errors}): {e}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.critical(f"Too many consecutive errors, stopping detector")
                        self._running = False
                        break
                    
                    await asyncio.sleep(5)
        
        finally:
            # Cleanup executor
            executor.shutdown(wait=False)
            logger.debug("SQS executor shut down")
    
    async def _process_via_backend(self, key: str):
        """
        Process S3 object by calling backend._process_documents_async() directly.
        Uses the complete pipeline with DocumentProcessor.
        
        Args:
            key: S3 object key
        """
        if not self.backend:
            logger.error("Backend not injected into S3Detector - cannot process object")
            return
        
        logger.info(f"Processing {key} via backend (full pipeline)")
        
        try:
            skip_graph = getattr(self, 'skip_graph', False)
            processing_id = f"incremental_s3_{key.replace('/', '_')[:16]}"
            
            # Build S3 config
            s3_config = {
                'bucket_name': self.bucket,
                'region_name': self.aws_region,
                'prefix': key,  # Process just this one object
            }
            
            # Add credentials if available
            if self.aws_access_key_id and self.aws_secret_access_key:
                s3_config['access_key'] = self.aws_access_key_id
                s3_config['secret_key'] = self.aws_secret_access_key
            
            # Call backend method directly
            await self.backend._process_documents_async(
                processing_id=processing_id,
                data_source='s3',
                config_id=self.config_id,
                skip_graph=skip_graph,
                s3_config=s3_config
            )
            
            logger.info(f"Successfully processed {key} via backend pipeline")
            
            # Create document_state record after successful processing
            if self.state_manager:
                try:
                    await self._create_document_state_from_processing_status(processing_id, key)
                except Exception as e:
                    logger.error(f"Failed to create document_state for {key}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process {key} via backend: {e}")
            raise
    
    async def _create_document_state_from_processing_status(
        self, processing_id: str, key: str
    ):
        """Create document_state record after successful processing via event"""
        from backend import PROCESSING_STATUS
        from incremental_updates.state_manager import DocumentState, StateManager
        from datetime import datetime, timezone
        
        # Wait a moment for processing to complete
        await asyncio.sleep(0.5)
        
        status_dict = PROCESSING_STATUS.get(processing_id, {})
        if status_dict.get('status') != 'completed':
            logger.warning(f"Processing not yet completed for {key}, skipping document_state creation")
            return
        
        documents = status_dict.get('documents', [])
        if not documents:
            logger.warning(f"No documents found in PROCESSING_STATUS for {key}")
            return
        
        doc = documents[0]
        
        # Use S3 URI as source_id
        source_id = f"s3://{self.bucket}/{key}"
        
        # Extract metadata from document
        modified_timestamp = None
        ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        
        if hasattr(doc, 'metadata'):
            # Try to get modification timestamp (use modified_at which S3Source sets)
            modified_timestamp = doc.metadata.get('modified_at') or doc.metadata.get('last_modified')
            
            # If we have timestamp, use it for ordinal and content_hash
            if modified_timestamp:
                try:
                    from dateutil import parser as dateutil_parser
                    dt = dateutil_parser.parse(modified_timestamp)
                    ordinal = int(dt.timestamp() * 1_000_000)
                    logger.info(f"Event-added file: Using modification timestamp for ordinal: {modified_timestamp} -> {ordinal}")
                except Exception as e:
                    logger.warning(f"Could not parse modification timestamp '{modified_timestamp}': {e}")
        
        # Use bucket/key format for source_path (consistent with initial ingest)
        source_path = f"{self.bucket}/{key}"
        
        # Create doc_id using bucket/key format (consistent with initial ingest)
        doc_id = f"{self.config_id}:{source_path}"
        
        # Compute content hash from timestamp or use placeholder
        if modified_timestamp:
            content_hash = StateManager.compute_content_hash(str(modified_timestamp))
            logger.info(f"Event-added file: Using timestamp-based hash: {modified_timestamp}")
        else:
            content_hash = StateManager.compute_content_hash("")
            logger.warning(f"Event-added file: No timestamp, using placeholder hash")
        
        # Get current time for sync timestamps (file was just ingested)
        now = datetime.now(timezone.utc)
        
        # Determine if graph was synced based on skip_graph setting
        # If skip_graph=False, graph extraction was performed, so mark as synced
        # If skip_graph=True, graph extraction was skipped, so leave as None
        graph_synced = now if not getattr(self, 'skip_graph', False) else None
        
        # Create document state with sync timestamps marked
        # (backend just ingested to vector, search, and optionally graph indexes)
        doc_state = DocumentState(
            doc_id=doc_id,
            config_id=self.config_id,
            source_path=source_path,
            ordinal=ordinal,
            content_hash=content_hash,
            source_id=source_id,
            modified_timestamp=modified_timestamp,
            vector_synced_at=now,        # Mark as synced (just ingested)
            search_synced_at=now,        # Mark as synced (just ingested)
            graph_synced_at=graph_synced  # Mark as synced if graph extraction was performed
        )
        
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for event-added file: {doc_id} (ordinal={ordinal}, source_id={source_id}, graph_synced={graph_synced is not None})")
