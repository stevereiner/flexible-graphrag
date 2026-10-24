"""
Filesystem Change Detector

Real-time filesystem monitoring using the watchdog library.
Detects file creates, modifications, and deletions.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
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
        
        def _put(self, change_event: ChangeEvent) -> None:
            """Queue an event from watchdog's thread: an asyncio queue is not thread-safe, so it is
            handed to the detector's event loop (put_nowait from this thread can leave the waiting
            reader unwoken, stalling the stream until the next periodic refresh)."""
            loop = getattr(self.detector, "_loop", None)
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self.event_queue.put_nowait, change_event)
            else:
                self.event_queue.put_nowait(change_event)

        def _create_event(self, src_path: str, change_type: ChangeType) -> ChangeEvent:
            """Create a ChangeEvent from filesystem event"""
            path = Path(src_path)
            
            # For deletions, use current timestamp since file doesn't exist
            if change_type == ChangeType.DELETE:
                ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
                size_bytes = None
            else:
                # For creates/updates, use file's modification time
                try:
                    ordinal = int(path.stat().st_mtime * 1_000_000)
                    size_bytes = path.stat().st_size
                except Exception:
                    # Fallback if file doesn't exist anymore
                    ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
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
                timestamp=datetime.now(timezone.utc)
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
                        self.detector.recent_events[event.src_path] = (ChangeType.CREATE, datetime.now(timezone.utc))
                    
                    self._put(self._create_event(event.src_path, ChangeType.CREATE))
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
                    time_since = (datetime.now(timezone.utc) - timestamp).total_seconds()
                    if event_type == ChangeType.CREATE and time_since < 1.0:
                        logger.info(f"WATCHDOG: Skipping UPDATE event (CREATE just processed {time_since:.2f}s ago): {event.src_path}")
                        return
                
                logger.info(f"WATCHDOG: UPDATE event queued for: {event.src_path}")
                
                try:
                    self._put(self._create_event(event.src_path, ChangeType.UPDATE))
                    logger.info(f"WATCHDOG: Event queued successfully")
                except Exception as e:
                    logger.error(f"WATCHDOG: Failed to queue event: {e}")
        
        def on_moved(self, event):
            """A file renamed or moved within the watched directory (a moved directory's files come
            as their own moved events): its old path is removed, its new one ingested. A selected
            file renamed away is no longer the selected file."""
            if event.is_directory:
                return
            src, dest = Path(event.src_path), Path(event.dest_path)
            if self.watch_file:
                follows_src, follows_dest = src == self.watch_file, dest == self.watch_file
            else:
                root = self.watch_root.resolve()
                follows_src = True
                follows_dest = dest.resolve().is_relative_to(root)
            logger.info(f"WATCHDOG: MOVE {event.src_path} -> {event.dest_path}")
            try:
                if follows_src:
                    self._put(self._create_event(event.src_path, ChangeType.DELETE))
                if follows_dest:
                    if self.detector:
                        self.detector.recent_events[event.dest_path] = (ChangeType.CREATE, datetime.now(timezone.utc))
                    self._put(self._create_event(event.dest_path, ChangeType.CREATE))
            except Exception as e:
                logger.error(f"WATCHDOG: Failed to queue move events: {e}")

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
                    self._put(self._create_event(event.src_path, ChangeType.DELETE))
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
    - **Incremental mode** (``backend`` injected by orchestrator): ADD/MODIFY call
      ``_process_via_backend`` directly; DELETE events go to the engine.
    - **Event-only mode** (``backend is None``, e.g. CocoIndex ``FlexibleMapView``):
      yield CREATE/UPDATE/DELETE events for the CocoIndex pipeline to process.
    
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
        # Files currently being ingested — dedups a concurrent periodic-refresh + watchdog overlap
        # (both call _process_via_backend during the window before document_state is written).
        self._in_flight = set()
        
        # Track recent events to deduplicate CREATE+UPDATE bursts
        self.recent_events: dict = {}  # path -> (event_type, timestamp)

    @property
    def _event_only(self) -> bool:
        """When True, yield change events for CocoIndex instead of backend processing."""
        return self.backend is None

    async def _emit_create_or_update(
        self,
        event: ChangeEvent,
        full_path: str,
        is_new: bool,
    ) -> AsyncGenerator[ChangeEvent, None]:
        """Dispatch CREATE/UPDATE — backend pipeline or event-only (CocoIndex)."""
        path_label = event.metadata.path

        if self._event_only:
            _meta = FileMetadata(
                source_type="filesystem",
                path=full_path,
                ordinal=event.metadata.ordinal,
                size_bytes=event.metadata.size_bytes,
                extra=event.metadata.extra or {},
            )
            if is_new:
                # New file — simple CREATE so CocoIndex ingests it fresh.
                self.known_file_paths.add(full_path)
                logger.info(
                    "EVENT: create for %s (event-only — CocoIndex pipeline)",
                    path_label,
                )
                yield ChangeEvent(metadata=_meta, change_type=ChangeType.CREATE, timestamp=event.timestamp)
            else:
                # Modified file — emit DELETE then CREATE, mirroring the backend
                # modify path (delete + add).  Most LI/LC stores do not support
                # true in-place updates for chunked documents; CocoIndex's memo
                # comparison is also unreliable without a real modified_time
                # (the filesystem detector does not set modified_timestamp).
                logger.info(
                    "EVENT: modify for %s (event-only — CocoIndex pipeline): DELETE then CREATE",
                    path_label,
                )
                yield ChangeEvent(metadata=_meta, change_type=ChangeType.DELETE, timestamp=event.timestamp)
                yield ChangeEvent(metadata=_meta, change_type=ChangeType.CREATE, timestamp=event.timestamp)
            return

        if is_new:
            logger.info(f"EVENT: CREATE detected for {path_label}")
            self.known_file_paths.add(full_path)
            try:
                await self._process_via_backend(full_path, path_label)
                logger.info(f"SUCCESS: Processed {path_label} via backend pipeline")
            except Exception as e:
                logger.error(f"ERROR: Failed to process {path_label} via backend: {e}")
            return

        # Known file MODIFY — incremental path: DELETE + callback ADD
        logger.info(f"EVENT: MODIFY detected for {path_label}")
        logger.info("MODIFY: Emitting DELETE event with callback")

        async def add_callback():
            logger.info(f"MODIFY: DELETE completed, now processing ADD for {path_label}")
            try:
                await self._process_via_backend(full_path, path_label)
                logger.info(f"SUCCESS: MODIFY completed for {path_label}")
            except Exception as e:
                logger.error(f"ERROR: Failed to process ADD for {path_label}: {e}")

        delete_metadata = FileMetadata(
            source_type="filesystem",
            path=full_path,
            ordinal=event.metadata.ordinal,
            extra={},
        )
        yield ChangeEvent(
            metadata=delete_metadata,
            change_type=ChangeType.DELETE,
            timestamp=event.timestamp,
            is_modify_delete=True,
            modify_callback=add_callback,
        )
    
    async def start(self):
        """Start filesystem monitoring"""
        if not WATCHDOG_AVAILABLE:
            logger.error("Cannot start filesystem detector - watchdog not installed")
            raise ImportError("watchdog library required for filesystem detector")
        
        self._running = True
        self._loop = asyncio.get_running_loop()  # watchdog's thread queues events onto it
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
                logger.debug(f"Watching file: {path.name} (monitoring directory: {watch_dir})")
            else:
                handler = FilesystemEventHandler(path, self.event_queue, detector=self)
                self.observer.schedule(handler, str(path), recursive=True)
                logger.debug(f"Watching directory: {path} (recursive)")
        
        self.observer.start()
        logger.debug(f"Filesystem detector started for {len(self.paths)} path(s)")
    
    async def stop(self):
        """Stop filesystem monitoring"""
        self._running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        logger.debug("Filesystem detector stopped")
    
    async def _populate_known_files(self):
        """Populate known_file_paths set with all currently existing files (normalized paths)."""
        try:
            logger.debug("POPULATE: Starting to populate known_file_paths...")
            all_files = await self.list_all_files()
            for file_meta in all_files:
                # list_all_files already returns normalized paths
                self.known_file_paths.add(normalize_filesystem_path(file_meta.path))
            logger.debug(f"POPULATE: Populated known_file_paths with {len(self.known_file_paths)} existing files")
            
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
                    if self._ignore_changes_until and datetime.now(timezone.utc) < self._ignore_changes_until:
                        logger.debug(f"Ignoring event during quiet period: {event.metadata.path}")
                        continue
                    
                    logger.info(f"Filesystem event: {event.change_type.value} - {event.metadata.path}")
                    
                    # Resolve full path for the event (metadata.path is already normalized from _create_event)
                    full_path = None
                    for watch_path in self.paths:
                        if watch_path.is_file() or (event.change_type == ChangeType.DELETE and not watch_path.exists()):
                            # a selected file: this event's file only (not another of that name)
                            if normalize_filesystem_path(str(watch_path.absolute())) == event.metadata.path:
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
                        logger.info(
                            f"CREATE/MODIFY check for {event.metadata.path}: is_new={is_new}"
                        )
                        async for emitted in self._emit_create_or_update(
                            event, full_path, is_new
                        ):
                            yield emitted
                    
                    # Handle UPDATE events
                    elif event.change_type == ChangeType.UPDATE:
                        is_new = full_path not in self.known_file_paths
                        if not is_new and await self._unchanged(full_path, event.metadata.ordinal):
                            logger.info(f"UPDATE event for {event.metadata.path}: modification time "
                                        f"unchanged -- skipping")
                            continue
                        logger.info(
                            f"UPDATE event for {event.metadata.path}: is_new={is_new}"
                        )
                        async for emitted in self._emit_create_or_update(
                            event, full_path, is_new
                        ):
                            yield emitted
                    
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
    
    async def _unchanged(self, full_path: str, ordinal: Optional[int]) -> bool:
        """Whether a file's modification time (its ordinal) is the one already ingested: an UPDATE
        event that changed nothing (e.g. attributes only)."""
        if not (self.state_manager and self.config_id and ordinal):
            return False
        try:
            from incremental_updates.state_manager import StateManager
            state = await self.state_manager.get_state(StateManager.make_doc_id(self.config_id, full_path))
        except Exception as e:
            logger.debug(f"Could not check the state of {full_path}: {e}")
            return False
        return bool(state and state.ordinal and state.ordinal >= ordinal)

    def set_quiet_period(self, seconds: int = 5):
        """
        Set a quiet period to ignore file changes.
        
        Useful to ignore events triggered by our own file operations.
        """
        self._ignore_changes_until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
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

        # In-flight guard: the periodic refresh AND the watchdog both call this for a newly-added
        # file and can overlap during the ingest window before document_state is written. Skip the
        # second concurrent trigger (asyncio → check-then-add is atomic). Genuine modifies still run:
        # the modify path deletes document_state before re-adding, and a file is only in _in_flight
        # while a process is actively running for it.
        if full_path in self._in_flight:
            logger.info(f"Filesystem: {full_path} already being ingested (periodic/watchdog overlap) — skipping duplicate")
            return

        # The data source's graphs, as its folder's / its own scope rules or this document's own
        # flags have them (incremental_updates/doc_graphs.py); None: the rules say not to follow it
        from incremental_updates.doc_graphs import graphs_for
        from incremental_updates.path_utils import normalize_filesystem_path
        graphs = await graphs_for(self, full_path, normalize_filesystem_path(full_path))
        if graphs is None:
            return
        self._in_flight.add(full_path)

        logger.info(f"Processing {relative_path} via backend (full pipeline)")

        try:
            from .. import sync_jobs
            processing_id = sync_jobs.processing_id("fs", full_path)
            
            # Call backend method directly (skips REST API layer)
            await self.backend._process_documents_async(
                processing_id=processing_id,
                data_source='filesystem',
                config_id=self.config_id,
                graphs=graphs,
                filesystem_config={
                    'paths': [full_path]  # Process just this one file
                }
            )
            
            logger.info(f"Successfully processed {relative_path} via backend pipeline")
            
            # Create document_state record after successful processing
            if self.state_manager:
                try:
                    await self._create_document_state_from_processing_status(
                        processing_id, relative_path, full_path, graphs=graphs
                    )
                except Exception as e:
                    logger.error(f"Failed to create document_state for {relative_path}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process {relative_path} via backend: {e}")
            raise
        finally:
            self._in_flight.discard(full_path)

    async def _create_document_state_from_processing_status(
        self, processing_id: str, filename: str, full_path: str, graphs=None
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
        # FileSystemSource now writes 'modified_at' (underscore); accept the legacy
        # 'modified at' (space) too for documents ingested before that change (issue #18).
        modified_timestamp = self.parse_timestamp(
            doc.metadata.get('modified_at') or doc.metadata.get('modified at')
        )
        
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
        from incremental_updates.doc_graphs import datasource_graphs, synced_times
        graph_at, rdf_at = synced_times(self, graphs if graphs is not None else datasource_graphs(self), now)
        
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
            graph_synced_at=graph_at,
            rdf_synced_at=rdf_at,
        )
        
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for {filename}: {doc_id}")
