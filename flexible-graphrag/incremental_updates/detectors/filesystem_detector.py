"""
Filesystem Change Detector

Real-time filesystem monitoring using the watchdog library.
Detects file creates, modifications, and deletions.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata
from incremental_updates.path_utils import normalize_filesystem_path

logger = logging.getLogger("flexible_graphrag.incremental.detectors.filesystem")

# ---------------------------------------------------------------------------
# Watchdog Integration
# ---------------------------------------------------------------------------

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = None
    logger.warning("watchdog not installed - filesystem change detection unavailable")


if WATCHDOG_AVAILABLE:
    class FilesystemEventHandler(FileSystemEventHandler):
        """Watchdog handler for filesystem events"""
        
        def __init__(self, watch_root: Path, event_queue: "asyncio.Queue[ChangeEvent]", watch_file: Optional[Path] = None, detector=None):
            super().__init__()
            self.watch_root = watch_root
            self.event_queue = event_queue
            self.watch_file = watch_file  # If set, only process events for this specific file
            self.detector = detector  # Reference to FilesystemDetector for deduplication
        
        def _create_event(self, src_path: str, change_type: ChangeType) -> ChangeEvent:
            """Create a ChangeEvent from filesystem event"""
            path = Path(src_path)
            
            # For deletions, use current timestamp since file doesn't exist
            if change_type == ChangeType.DELETE:
                ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
                size_bytes = None
            else:
                # For creates/updates, use file's modification time
                try:
                    ordinal = int(path.stat().st_mtime * 1_000_000)
                    size_bytes = path.stat().st_size
                except Exception:
                    # Fallback if file doesn't exist anymore
                    ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
                    size_bytes = None
            
            metadata = FileMetadata(
                source_type='filesystem',
                path=normalize_filesystem_path(str(path.absolute())),  # Normalize for doc_id/lookups
                ordinal=ordinal,
                size_bytes=size_bytes
            )
            
            return ChangeEvent(
                metadata=metadata,
                change_type=change_type,
                timestamp=datetime.utcnow()
            )
        
        def on_created(self, event):
            """Handle file creation events"""
            if not event.is_directory:
                logger.debug(f"WATCHDOG: on_created triggered for: {event.src_path}")
                
                # If watching specific file, only process events for that file
                if self.watch_file and Path(event.src_path) != self.watch_file:
                    logger.debug(f"WATCHDOG: Ignoring created event (not target file): {event.src_path} != {self.watch_file}")
                    return
                
                logger.info(f"WATCHDOG: CREATE event queued for: {event.src_path}")
                
                try:
                    # Track this event for deduplication
                    if self.detector:
                        self.detector.recent_events[event.src_path] = (ChangeType.CREATE, datetime.utcnow())
                    
                    self.event_queue.put_nowait(self._create_event(event.src_path, ChangeType.CREATE))
                    logger.info(f"WATCHDOG: Event queued successfully")
                except Exception as e:
                    logger.error(f"WATCHDOG: Failed to queue event: {e}")
        
        def on_modified(self, event):
            """Handle file modification events"""
            if not event.is_directory:
                logger.debug(f"WATCHDOG: on_modified triggered for: {event.src_path}")
                
                # If watching specific file, only process events for that file
                if self.watch_file and Path(event.src_path) != self.watch_file:
                    logger.debug(f"WATCHDOG: Ignoring modified event (not target file): {event.src_path} != {self.watch_file}")
                    return
                
                # Check if we just processed a CREATE for this file (within 1 second)
                # If so, skip this UPDATE to avoid duplicate processing
                if event.src_path in self.detector.recent_events:
                    event_type, timestamp = self.detector.recent_events[event.src_path]
                    time_since = (datetime.utcnow() - timestamp).total_seconds()
                    if event_type == ChangeType.CREATE and time_since < 1.0:
                        logger.info(f"WATCHDOG: Skipping UPDATE event (CREATE just processed {time_since:.2f}s ago): {event.src_path}")
                        return
                
                logger.info(f"WATCHDOG: UPDATE event queued for: {event.src_path}")
                
                try:
                    self.event_queue.put_nowait(self._create_event(event.src_path, ChangeType.UPDATE))
                    logger.info(f"WATCHDOG: Event queued successfully")
                except Exception as e:
                    logger.error(f"WATCHDOG: Failed to queue event: {e}")
        
        def on_deleted(self, event):
            """Handle file deletion events"""
            if not event.is_directory:
                logger.debug(f"WATCHDOG: on_deleted triggered for: {event.src_path}")
                
                # If watching specific file, only process events for that file
                if self.watch_file and Path(event.src_path) != self.watch_file:
                    logger.debug(f"WATCHDOG: Ignoring deleted event (not target file): {event.src_path} != {self.watch_file}")
                    return
                
                logger.info(f"WATCHDOG: DELETE event queued for: {event.src_path}")
                
                try:
                    self.event_queue.put_nowait(self._create_event(event.src_path, ChangeType.DELETE))
                    logger.info(f"WATCHDOG: Event queued successfully")
                except Exception as e:
                    logger.error(f"WATCHDOG: Failed to queue event: {e}")


# ---------------------------------------------------------------------------
# Filesystem Detector
# ---------------------------------------------------------------------------

class FilesystemDetector(ChangeDetector):
    """
    Filesystem change detector using watchdog.
    
    Features:
    - Real-time OS-level event detection
    - Support for both files and directories
    - Recursive directory monitoring
    - Quiet period to ignore own changes
    - Retry logic for file locks (Windows)
    - **NEW**: Uses backend for ADD/MODIFY events (full DocumentProcessor pipeline)
    
    Configuration:
        paths: List of file or directory paths to monitor
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.paths = [Path(p).resolve() for p in config.get('paths', [])]
        self.event_queue: asyncio.Queue[ChangeEvent] = asyncio.Queue()
        self.observer: Optional[Observer] = None
        self._ignore_changes_until: Optional[datetime] = None
        
        # Backend reference (will be injected by orchestrator)
        self.backend = None
        self.state_manager = None
        self.config_id = None
        
        # Track known files for CREATE vs MODIFY detection
        self.known_file_paths = set()
        
        # Track recent events to deduplicate CREATE+UPDATE bursts
        self.recent_events: dict = {}  # path -> (event_type, timestamp)
    
    async def start(self):
        """Start filesystem monitoring"""
        if not WATCHDOG_AVAILABLE:
            logger.error("Cannot start filesystem detector - watchdog not installed")
            raise ImportError("watchdog library required for filesystem detector")
        
        self._running = True
        self.observer = Observer()
        
        # Populate known_file_paths before starting monitoring
        await self._populate_known_files()
        
        for path in self.paths:
            # Watchdog can only watch directories, not individual files
            # If path is a file, watch its parent directory
            if path.is_file():
                watch_dir = path.parent
                handler = FilesystemEventHandler(watch_dir, self.event_queue, watch_file=path, detector=self)
                self.observer.schedule(handler, str(watch_dir), recursive=False)
                logger.info(f"Watching file: {path.name} (monitoring directory: {watch_dir})")
            else:
                handler = FilesystemEventHandler(path, self.event_queue, detector=self)
                self.observer.schedule(handler, str(path), recursive=True)
                logger.info(f"Watching directory: {path} (recursive)")
        
        self.observer.start()
        logger.info(f"Filesystem detector started for {len(self.paths)} path(s)")
    
    async def stop(self):
        """Stop filesystem monitoring"""
        self._running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        logger.info("Filesystem detector stopped")
    
    async def _populate_known_files(self):
        """Populate known_file_paths set with all currently existing files (normalized paths)."""
        try:
            logger.info("POPULATE: Starting to populate known_file_paths...")
            all_files = await self.list_all_files()
            for file_meta in all_files:
                # list_all_files already returns normalized paths
                self.known_file_paths.add(normalize_filesystem_path(file_meta.path))
            logger.info(f"POPULATE: Populated known_file_paths with {len(self.known_file_paths)} existing files")
            
        except Exception as e:
            logger.error(f"Error populating known_file_paths: {e}")
    
    async def list_all_files(self) -> List[FileMetadata]:
        """List all files in watched directories or specific files"""
        files = []

        for watch_path in self.paths:
            if watch_path.is_file():
                # Single file - use full absolute path (normalized for consistent doc_id)
                stat = watch_path.stat()
                files.append(FileMetadata(
                    source_type='filesystem',
                    path=normalize_filesystem_path(str(watch_path.absolute())),
                    ordinal=int(stat.st_mtime * 1_000_000),
                    size_bytes=stat.st_size
                ))
            elif watch_path.is_dir():
                # Directory - scan all files recursively with full paths (normalized)
                for path in watch_path.rglob('*'):
                    if path.is_file():
                        stat = path.stat()
                        files.append(FileMetadata(
                            source_type='filesystem',
                            path=normalize_filesystem_path(str(path.absolute())),
                            ordinal=int(stat.st_mtime * 1_000_000),
                            size_bytes=stat.st_size
                        ))

        return files
    
    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """
        Stream filesystem events from watchdog.
        
        NEW BEHAVIOR:
        - For CREATE: Check known_file_paths, then process via backend
        - For UPDATE (MODIFY): Emit DELETE with callback, callback processes ADD after DELETE completes
        - For DELETE: Yield event for engine to handle
        
        This ensures ADD/MODIFY use DocumentProcessor for ALL file types (PDF, DOCX, etc.)
        """
        logger.info(f"Filesystem detector: starting event stream")
        
        try:
            while self._running:
                try:
                    # Wait for event from queue with timeout to check _running flag
                    event = await asyncio.wait_for(self.event_queue.get(), timeout=5.0)
                    
                    if event is None:
                        yield None
                        continue
                    
                    # Check if we should ignore this event (quiet period after processing)
                    if self._ignore_changes_until and datetime.utcnow() < self._ignore_changes_until:
                        logger.debug(f"Ignoring event during quiet period: {event.metadata.path}")
                        continue
                    
                    logger.info(f"Filesystem event: {event.change_type.value} - {event.metadata.path}")
                    
                    # Resolve full path for the event (metadata.path is already normalized from _create_event)
                    full_path = None
                    for watch_path in self.paths:
                        if watch_path.is_file():
                            if watch_path.name == Path(event.metadata.path).name or normalize_filesystem_path(str(watch_path.absolute())) == event.metadata.path:
                                full_path = str(watch_path)
                                break
                        else:
                            candidate_path = watch_path / event.metadata.path
                            if candidate_path.exists() or event.change_type == ChangeType.DELETE:
                                full_path = str(candidate_path)
                                break
                    if full_path:
                        full_path = normalize_filesystem_path(full_path)
                    
                    if not full_path:
                        logger.warning(f"Could not resolve full path for: {event.metadata.path}")
                        continue
                    
                    # Handle DELETE events
                    if event.change_type == ChangeType.DELETE:
                        if full_path in self.known_file_paths:
                            self.known_file_paths.discard(full_path)
                        yield event
                    
                    # Handle CREATE events - check known_file_paths
                    elif event.change_type == ChangeType.CREATE:
                        is_new = full_path not in self.known_file_paths
                        
                        logger.info(f"CREATE/MODIFY check for {event.metadata.path}: is_new={is_new}")
                        
                        if is_new:
                            # Truly new file - CREATE
                            logger.info(f"EVENT: CREATE detected for {event.metadata.path}")
                            self.known_file_paths.add(full_path)
                            try:
                                await self._process_via_backend(full_path, event.metadata.path)
                                logger.info(f"SUCCESS: Processed {event.metadata.path} via backend pipeline")
                            except Exception as e:
                                logger.error(f"ERROR: Failed to process {event.metadata.path} via backend: {e}")
                        else:
                            # Already known - treat as MODIFY (DELETE + ADD)
                            logger.info(f"EVENT: MODIFY detected for {event.metadata.path}")
                            logger.info(f"MODIFY: Emitting DELETE event with callback")
                            
                            async def add_callback():
                                logger.info(f"MODIFY: DELETE completed, now processing ADD for {event.metadata.path}")
                                try:
                                    await self._process_via_backend(full_path, event.metadata.path)
                                    logger.info(f"SUCCESS: MODIFY completed for {event.metadata.path}")
                                except Exception as e:
                                    logger.error(f"ERROR: Failed to process ADD for {event.metadata.path}: {e}")
                            
                            delete_metadata = FileMetadata(
                                source_type='filesystem',
                                path=full_path,  # Normalized so engine doc_id matches document_state
                                ordinal=event.metadata.ordinal,
                                extra={}
                            )
                            delete_event = ChangeEvent(
                                metadata=delete_metadata,
                                change_type=ChangeType.DELETE,
                                timestamp=event.timestamp,
                                is_modify_delete=True,
                                modify_callback=add_callback
                            )
                            yield delete_event
                    
                    # Handle UPDATE events
                    elif event.change_type == ChangeType.UPDATE:
                        is_new = full_path not in self.known_file_paths
                        
                        logger.info(f"UPDATE event for {event.metadata.path}: is_new={is_new}")
                        
                        if is_new:
                            # Treat as CREATE
                            logger.info(f"EVENT: CREATE detected for {event.metadata.path} (reported as UPDATE)")
                            self.known_file_paths.add(full_path)
                            try:
                                await self._process_via_backend(full_path, event.metadata.path)
                                logger.info(f"SUCCESS: Processed {event.metadata.path} via backend pipeline")
                            except Exception as e:
                                logger.error(f"ERROR: Failed to process {event.metadata.path} via backend: {e}")
                        else:
                            # True MODIFY (DELETE + ADD)
                            logger.info(f"EVENT: MODIFY detected for {event.metadata.path}")
                            logger.info(f"MODIFY: Emitting DELETE event with callback")
                            
                            async def add_callback():
                                logger.info(f"MODIFY: DELETE completed, now processing ADD for {event.metadata.path}")
                                try:
                                    await self._process_via_backend(full_path, event.metadata.path)
                                    logger.info(f"SUCCESS: MODIFY completed for {event.metadata.path}")
                                except Exception as e:
                                    logger.error(f"ERROR: Failed to process ADD for {event.metadata.path}: {e}")
                            
                            delete_metadata = FileMetadata(
                                source_type='filesystem',
                                path=full_path,  # Normalized so engine doc_id matches document_state
                                ordinal=event.metadata.ordinal,
                                extra={}
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
                    # No event for 5 seconds, yield None to check if still running
                    yield None
                    
        except GeneratorExit:
            logger.info("Filesystem detector: event stream closed")
        except Exception as e:
            logger.error(f"Error in filesystem event stream: {e}")
            raise
        finally:
            logger.info("Filesystem detector: exiting event stream")
    
    def set_quiet_period(self, seconds: int = 5):
        """
        Set a quiet period to ignore file changes.
        
        Useful to ignore events triggered by our own file operations.
        """
        self._ignore_changes_until = datetime.utcnow() + timedelta(seconds=seconds)
        logger.debug(f"Quiet period set for {seconds}s (until {self._ignore_changes_until})")
    
    async def _process_via_backend(self, full_path: str, relative_path: str):
        """
        Process file by calling backend._process_documents_async() directly.
        Uses the complete pipeline with DocumentProcessor.
        
        Args:
            full_path: Full filesystem path to the file
            relative_path: Relative path for logging
        """
        if not self.backend:
            logger.error("Backend not injected into FilesystemDetector - cannot process file")
            return
        
        logger.info(f"Processing {relative_path} via backend (full pipeline)")
        
        try:
            skip_graph = getattr(self, 'skip_graph', False)
            processing_id = f"incremental_fs_{Path(full_path).stem[:8]}"
            
            # Call backend method directly (skips REST API layer)
            await self.backend._process_documents_async(
                processing_id=processing_id,
                data_source='filesystem',
                config_id=self.config_id,
                skip_graph=skip_graph,
                filesystem_config={
                    'paths': [full_path]  # Process just this one file
                }
            )
            
            logger.info(f"Successfully processed {relative_path} via backend pipeline")
            
            # Create document_state record after successful processing
            if self.state_manager:
                try:
                    await self._create_document_state_from_processing_status(
                        processing_id, relative_path, full_path
                    )
                except Exception as e:
                    logger.error(f"Failed to create document_state for {relative_path}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process {relative_path} via backend: {e}")
            raise
    
    async def _create_document_state_from_processing_status(
        self, processing_id: str, filename: str, full_path: str
    ):
        """Create document_state record after successful processing"""
        from backend import PROCESSING_STATUS
        from incremental_updates.state_manager import DocumentState
        from datetime import datetime, timezone
        
        # Wait a moment for processing to complete
        await asyncio.sleep(0.5)
        
        status_dict = PROCESSING_STATUS.get(processing_id, {})
        if status_dict.get('status') != 'completed':
            logger.warning(f"Processing not yet completed for {filename}, skipping document_state creation")
            return
        
        documents = status_dict.get('documents', [])
        if not documents:
            logger.warning(f"No documents found in PROCESSING_STATUS for {filename}")
            return
        
        doc = documents[0]
        
        # Use filesystem path as source_id
        source_id = full_path
        modified_timestamp = self.parse_timestamp(doc.metadata.get('modified at'))
        
        # Create doc_id using full_path for consistency
        doc_id = f"{self.config_id}:{full_path}"
        
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
                # modified_timestamp is already a datetime object now
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
            source_path=full_path,  # Use full path, not just filename
            ordinal=ordinal,
            content_hash=content_hash,
            source_id=source_id,
            modified_timestamp=modified_timestamp,
            vector_synced_at=now,
            search_synced_at=now,
            graph_synced_at=now if not getattr(self, 'skip_graph', False) else None
        )
        
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for {filename}: {doc_id}")
