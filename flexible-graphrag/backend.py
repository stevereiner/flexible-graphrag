"""
Shared backend core for Flexible GraphRAG
This module contains the business logic that can be called by both FastAPI and FastMCP servers
"""

import os
import logging
import uuid
import asyncio
import sys

# Fix for async event loop issues with containers and LlamaIndex
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    # Docker/Linux environments - use default policy but ensure proper loop handling
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

try:
    import nest_asyncio
    # nest_asyncio patches loop.run_until_complete() in a way that breaks
    # asyncio.Runner.close() → shutdown_default_executor() on Python 3.14+
    # (asyncio.timeout() inside shutdown_default_executor requires a Task, but
    # the patched run_until_complete runs it outside one).  Only apply on < 3.14.
    if sys.version_info < (3, 14):
        nest_asyncio.apply()

    # Ensure we have a proper event loop for Docker containers
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
except ImportError:
    pass
from datetime import datetime
from typing import List, Dict, Any, Union, Optional
from pathlib import Path

from config import Settings
from hybrid_system import HybridSearchSystem
from ingest import IngestionManager
from sources.filesystem import FileSystemSource

logger = logging.getLogger(__name__)

# Global processing status storage
PROCESSING_STATUS = {}

# File processing phases for dynamic time estimation
PROCESSING_PHASES = {
    "docling": {"weight": 0.2, "name": "Converting document"},
    "chunking": {"weight": 0.1, "name": "Splitting into chunks"}, 
    "kg_extraction": {"weight": 0.6, "name": "Extracting knowledge graph"},
    "indexing": {"weight": 0.1, "name": "Building indexes"}
}

class FlexibleGraphRAGBackend:
    """Shared backend core for both REST API and MCP server"""
    
    def __init__(self, settings: Settings = None):
        self.settings = settings or Settings()
        self._system = None
        self._flow_service = None  # lazy: Langflow flow runner (app/flow mode)
        self.ingestion_manager = IngestionManager()
        logger.info("FlexibleGraphRAGBackend initialized")

    async def _get_flow_service(self):
        """Lazy-init the Langflow FlowService and load the ingest/query flows.

        Used when settings.enable_langflow_flows is true — the backend runs the Langflow
        flows (via the Langflow API) instead of calling the system directly.
        """
        if self._flow_service is None:
            from flow_service import FlowService
            fs = FlowService(self.settings.langflow_url, self.settings.langflow_api_key)
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ingest = self.settings.ingest_flow_path or os.path.join(repo_root, "flows", "fg_ingestion_flow.json")
            query = self.settings.query_flow_path or os.path.join(repo_root, "flows", "fg_query_flow.json")
            search = self.settings.search_flow_path or os.path.join(repo_root, "flows", "fg_search_flow.json")
            aiquery = self.settings.aiquery_flow_path or os.path.join(repo_root, "flows", "fg_aiquery_flow.json")
            logger.info("FlowService: ingest flow file  = %s", ingest)
            logger.info("FlowService: query flow file   = %s", query)
            logger.info("FlowService: search flow file  = %s", search)
            logger.info("FlowService: aiquery flow file = %s", aiquery)
            await fs.initialize_flows(ingest, query, search, aiquery)
            self._flow_service = fs
            logger.info("FlowService initialized (Langflow flow mode) — ingest=%s query=%s",
                        fs.ingestion_flow_id, fs.query_flow_id)
        return self._flow_service

    @staticmethod
    def _source_config_for_flow(data_source, paths, kwargs) -> dict:
        """Build the per-source config dict the flow's Data Source node expects."""
        if data_source == "filesystem":
            fs = kwargs.get("filesystem_config", {}) or {}
            p = paths or fs.get("paths") or []
            # Absolute paths: the langflow process resolves them in ITS cwd, not the backend's.
            return {"paths": [os.path.abspath(str(x).strip('"').strip("'")) for x in (p or [])]}
        return kwargs.get(f"{data_source}_config") or {}

    @staticmethod
    def _store_flow_docs_for_sync(processing_id, data_source, doc_states):
        """Reconstruct lightweight Document stand-ins (id_ + metadata) from the flow's
        doc_states and stash them in PROCESSING_STATUS so create_document_states_after_ingestion
        (which reads PROCESSING_STATUS['documents']) can build document_state rows in flow mode."""
        from llama_index.core import Document
        docs = []
        for ds in doc_states or []:
            # Carry the real text so the sync engine's content_hash = SHA-256(doc.text) is
            # correct (empty text -> null content_hash -> NOT NULL violation + broken change detect).
            d = Document(text=ds.get("text") or "", metadata=dict(ds.get("metadata") or {}))
            if ds.get("id_"):
                d.id_ = ds["id_"]
            docs.append(d)
        entry = PROCESSING_STATUS.setdefault(processing_id, {})
        entry["documents"] = docs
        entry["data_source"] = data_source
        logger.info("Flow sync: stored %d doc_states in PROCESSING_STATUS for document_state creation", len(docs))

    async def _ingest_via_flow(self, processing_id, data_source, paths, skip_graph, **kwargs):
        """Run the Langflow ingestion flow with the app's per-source config as tweaks."""
        self._update_processing_status(
            processing_id, "processing", f"Running Langflow ingestion flow for {data_source}...", 30
        )
        source_config = self._source_config_for_flow(data_source, paths, kwargs)
        config_id = kwargs.get("config_id")
        logger.info("Flow ingest: source=%s paths=%s config_id=%s", data_source, paths, config_id)
        # Config can hold credentials — DEBUG only, secrets masked / long values truncated.
        from flow_service import redact_config_for_log
        logger.debug("Flow ingest: source_config=%s", redact_config_for_log(source_config))
        try:
            fsvc = await self._get_flow_service()
            # doc_ids this datasource already stored (from document_state). The flow runs in the
            # langflow process, which has no access to these tables, so the backend looks them
            # up and passes them along; the flow's Document Processor deletes each of them from
            # the stores before inserting it again, so a repeat ingest replaces rather than
            # duplicates. None (no config_id, or incremental system off) = insert only.
            # The default pipeline does this lookup itself, in ingest_source_documents.
            replace_doc_ids = None
            if config_id:
                from incremental_system import IncrementalSystemManager
                _inc = IncrementalSystemManager._instance
                if _inc is not None and _inc.is_initialized():
                    replace_doc_ids = await _inc.get_doc_ids(config_id)
            result = await fsvc.run_ingestion_flow(
                source_type=data_source, source_config=source_config,
                skip_graph=skip_graph, config_id=config_id,
                replace_doc_ids=replace_doc_ids,
            )
            msg = fsvc.extract_message(result)
            # Incremental sync: the docs were parsed in the langflow process, so the backend's
            # document_state creator (reads PROCESSING_STATUS['documents']) has nothing unless
            # we feed it the flow's doc_states. Populate BEFORE marking completed so the
            # post-ingestion poller finds them.
            if config_id:
                self._store_flow_docs_for_sync(processing_id, data_source,
                                               fsvc.extract_doc_states(result))
            self._update_processing_status(
                processing_id, "completed", f"Langflow ingestion complete. {msg}", 100
            )
        except Exception as e:
            logger.error(f"Langflow ingestion flow failed: {e}", exc_info=True)
            self._update_processing_status(processing_id, "failed", f"Langflow ingestion failed: {e}", 0)
    
    @property
    def system(self):
        """Lazy-load the hybrid search system (full LangChain + LlamaIndex adapter layer)."""
        if self._system is None:
            self._system = HybridSearchSystem.from_settings(self.settings)
            logger.info("HybridSearchSystem initialized")
        return self._system
    
    # Processing status management
    
    def _create_processing_id(self) -> str:
        """Create a unique processing ID"""
        return str(uuid.uuid4())[:8]
    
    def _estimate_processing_time(self, data_source: str = None, paths: List[str] = None, content: str = None) -> str:
        """Estimate processing time based on input size and type"""
        try:
            if content:
                # Text content - quick processing
                char_count = len(content)
                if char_count < 1000:
                    return "30-60 seconds"
                elif char_count < 5000:
                    return "1-2 minutes"
                else:
                    return "2-3 minutes"
            
            elif paths:
                import os
                total_size = 0
                file_count = 0
                has_complex_files = False
                
                for path in paths:
                    if os.path.isfile(path):
                        file_count += 1
                        size = os.path.getsize(path)
                        total_size += size
                        
                        # Check for complex file types
                        ext = os.path.splitext(path)[1].lower()
                        if ext in ['.pdf', '.docx', '.pptx', '.xlsx']:
                            has_complex_files = True
                    elif os.path.isdir(path):
                        # Estimate directory contents
                        for root, dirs, files in os.walk(path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                try:
                                    file_count += 1
                                    size = os.path.getsize(file_path)
                                    total_size += size
                                    ext = os.path.splitext(file)[1].lower()
                                    if ext in ['.pdf', '.docx', '.pptx', '.xlsx']:
                                        has_complex_files = True
                                except:
                                    continue
                
                # Size-based estimation
                size_mb = total_size / (1024 * 1024)
                
                if file_count == 0:
                    return "30 seconds"
                elif file_count == 1 and size_mb < 1:
                    return "30-60 seconds"  # Single small file
                elif file_count == 1 and size_mb < 5:
                    return "1-2 minutes"    # Single medium file
                elif file_count == 1:
                    return "2-4 minutes"    # Single large file
                elif file_count <= 5 and not has_complex_files:
                    return "1-3 minutes"    # Few simple files
                elif file_count <= 10:
                    return "2-5 minutes"    # Several files
                else:
                    return "3-8 minutes"    # Many files
            
            return "2-4 minutes"  # Default fallback
            
        except Exception as e:
            logger.warning(f"Error estimating processing time: {e}")
            return "2-4 minutes"  # Safe fallback
    
    def _update_processing_status(self, processing_id: str, status: str, message: str, progress: int = 0, 
                                  current_file: str = None, current_phase: str = None, 
                                  files_completed: int = 0, total_files: int = 0,
                                  estimated_time_remaining: str = None, file_progress: List[Dict] = None):
        """Update processing status with dynamic timing information"""
        current_time = datetime.now()
        existing_status = PROCESSING_STATUS.get(processing_id, {})
        started_at = existing_status.get("started_at", current_time.isoformat())
        
        # Calculate dynamic time estimates if we have timing info
        if isinstance(started_at, str):
            start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
        else:
            start_time = started_at
            
        elapsed_seconds = (current_time - start_time).total_seconds()
        
        # Build enhanced status
        status_update = {
            "processing_id": processing_id,
            "status": status,
            "message": message,
            "progress": progress,
            "updated_at": current_time.isoformat(),
            "started_at": started_at if isinstance(started_at, str) else started_at.isoformat()
        }
        
        # Add file-level progress information
        if current_file:
            status_update["current_file"] = current_file
        if current_phase:
            status_update["current_phase"] = current_phase
        if total_files > 0:
            status_update["files_completed"] = files_completed
            status_update["total_files"] = total_files
            # Handle both in-progress (0-based) and completion (actual count) scenarios
            if status == "completed" or files_completed >= total_files:
                status_update["file_progress"] = f"File {files_completed} of {total_files}"
            else:
                status_update["file_progress"] = f"File {files_completed + 1} of {total_files}"
            
        # Add dynamic time estimation
        if estimated_time_remaining:
            status_update["estimated_time_remaining"] = estimated_time_remaining
        elif total_files > 0 and files_completed > 0 and elapsed_seconds > 0:
            # Calculate based on files completed so far
            avg_time_per_file = elapsed_seconds / files_completed
            remaining_files = total_files - files_completed
            estimated_remaining = avg_time_per_file * remaining_files
            
            if estimated_remaining < 60:
                status_update["estimated_time_remaining"] = f"{int(estimated_remaining)} seconds"
            elif estimated_remaining < 3600:
                status_update["estimated_time_remaining"] = f"{int(estimated_remaining / 60)} minutes"
            else:
                status_update["estimated_time_remaining"] = f"{estimated_remaining / 3600:.1f} hours"
        
        # Add individual file progress tracking
        if file_progress:
            status_update["individual_files"] = file_progress
        
        # Update existing status dict instead of replacing it (preserves documents field)
        existing = PROCESSING_STATUS.get(processing_id, {})
        existing.update(status_update)
        PROCESSING_STATUS[processing_id] = existing
        if total_files > 0:
            # Handle both in-progress (0-based) and completion (actual count) scenarios
            if status == "completed" or files_completed >= total_files:
                logger.info(f"Processing {processing_id}: {status} - {message} ({files_completed}/{total_files} files)")
            else:
                logger.info(f"Processing {processing_id}: {status} - {message} ({files_completed + 1}/{total_files} files)")
        else:
            logger.info(f"Processing {processing_id}: {status} - {message}")
    
    def get_processing_status(self, processing_id: str) -> Dict[str, Any]:
        """Get processing status by ID"""
        if processing_id not in PROCESSING_STATUS:
            return {"success": False, "error": f"Processing ID {processing_id} not found"}
        
        return {"success": True, "processing": PROCESSING_STATUS[processing_id]}
    
    def cancel_processing(self, processing_id: str) -> Dict[str, Any]:
        """Cancel a processing operation"""
        if processing_id not in PROCESSING_STATUS:
            return {"success": False, "error": f"Processing ID {processing_id} not found"}
            
        status = PROCESSING_STATUS[processing_id]
        if status["status"] in ["started", "processing"]:
            self._update_processing_status(
                processing_id, 
                "cancelled", 
                "Processing cancelled by user", 
                status.get("progress", 0)
            )
            return {"success": True, "message": "Processing cancelled successfully"}
        else:
            return {"success": False, "error": f"Cannot cancel processing in status: {status['status']}"}
    
    def _is_processing_cancelled(self, processing_id: str) -> bool:
        """Check if processing has been cancelled"""
        return (processing_id in PROCESSING_STATUS and 
                PROCESSING_STATUS[processing_id]["status"] == "cancelled")
    
    def _initialize_file_progress(self, processing_id: str, file_paths: List[str]) -> List[Dict]:
        """Initialize per-file progress tracking"""
        file_progress = []
        for i, file_path in enumerate(file_paths):
            filename = Path(file_path).name
            file_progress.append({
                "index": i,
                "filename": filename,
                "filepath": file_path,
                "status": "pending",  # pending, processing, completed, failed
                "progress": 0,
                "phase": "waiting",  # waiting, docling, chunking, kg_extraction, indexing
                "message": "Waiting to process...",
                "started_at": None,
                "completed_at": None,
                "error": None
            })
        return file_progress
    
    def _initialize_data_source_progress(self, processing_id: str, data_source: str, source_description: str = None) -> List[Dict]:
        """Initialize progress tracking for new modular data sources"""
        # Create a single "file" entry representing the data source
        source_name = source_description or f"{data_source.title()} Source"
        file_progress = [{
            "index": 0,
            "filename": source_name,
            "filepath": source_name,
            "status": "pending",
            "progress": 0,
            "phase": "connecting",
            "message": f"Connecting to {data_source}...",
            "started_at": None,
            "completed_at": None,
            "error": None
        }]
        return file_progress
    
    def _update_data_source_progress(self, processing_id: str, status: str = None, 
                                   progress: int = None, phase: str = None, message: str = None):
        """Update progress for modular data sources (single source entry)"""
        current_status = PROCESSING_STATUS.get(processing_id, {})
        file_progress = current_status.get("individual_files", [])
        
        if file_progress:
            # Update the single data source entry
            if status:
                file_progress[0]["status"] = status
            if progress is not None:
                file_progress[0]["progress"] = progress
            if phase:
                file_progress[0]["phase"] = phase
            if message:
                file_progress[0]["message"] = message
            
            # Update completion time
            if status == "completed":
                from datetime import datetime
                file_progress[0]["completed_at"] = datetime.now().isoformat()
            elif status == "processing" and not file_progress[0]["started_at"]:
                from datetime import datetime
                file_progress[0]["started_at"] = datetime.now().isoformat()
            
            # CRITICAL FIX: Update the main processing status to reflect the individual file progress
            # This ensures the UI's top area progress bar gets updated
            files_completed = 1 if status == "completed" else 0
            self._update_processing_status(
                processing_id=processing_id,
                status=status or current_status.get("status", "processing"),
                message=message or current_status.get("message", "Processing..."),
                progress=progress if progress is not None else current_status.get("progress", 0),
                total_files=1,
                files_completed=files_completed,
                file_progress=file_progress
            )
    
    async def _process_modular_data_source(self, processing_id: str, data_source: str, config_key: str, 
                                         display_name: str, connect_message: str, process_message: str, 
                                         config_id: str = None, skip_graph: bool = False, **kwargs):
        """Generic method to process modular data sources with proper progress tracking"""
        # Get configuration
        config = kwargs.get(config_key)
        if not config:
            raise ValueError(f"{data_source.title()} configuration is required for {data_source} data source")
        
        # DEBUG: Log skip_graph extraction
        logger.info(f"=== _process_modular_data_source DEBUG ===")
        logger.info(f"  data_source: {data_source}")
        logger.info(f"  skip_graph parameter (explicit): {skip_graph} (type: {type(skip_graph)})")
        logger.info(f"  kwargs keys: {list(kwargs.keys())}")
        logger.info(f"  'skip_graph' in kwargs: {'skip_graph' in kwargs}")
        logger.info(f"  config_id: {config_id}")
        logger.info(f"=== END _process_modular_data_source DEBUG ===")
        
        # Log the config for debugging — config may hold credentials, so redact
        from flow_service import redact_config_for_log
        logger.info("Processing %s with config: %s", data_source, redact_config_for_log(config))
        
        # Initialize progress tracking
        file_progress = self._initialize_data_source_progress(processing_id, data_source, display_name)
        
        # Initial connection status
        self._update_processing_status(
            processing_id, 
            "processing", 
            connect_message, 
            20,
            total_files=1,
            files_completed=0,
            file_progress=file_progress
        )
        self._update_data_source_progress(processing_id, "processing", 20, "connecting", connect_message)
        
        # Check for cancellation
        if self._is_processing_cancelled(processing_id):
            return
            
        # Processing status
        self._update_processing_status(
            processing_id, 
            "processing", 
            process_message, 
            60,
            total_files=1,
            files_completed=0,
            file_progress=file_progress
        )
        self._update_data_source_progress(processing_id, "processing", 60, "loading", process_message)
        
        # Create status callback
        def status_callback(**cb_kwargs):
            status = cb_kwargs.get("status", "processing")
            progress = cb_kwargs.get("progress", 0)
            message = cb_kwargs.get("message", "")
            
            # Update data source progress (this internally calls _update_processing_status)
            self._update_data_source_progress(processing_id, status, progress, "processing", message)
        
        # Process documents
        documents = await self.ingestion_manager.ingest_from_source(
            source_type=data_source,
            config=config,
            processing_id=processing_id,
            status_callback=status_callback
        )
        
        # Store documents in PROCESSING_STATUS for document_state creation
        PROCESSING_STATUS[processing_id]["documents"] = documents
        logger.info(f"Stored {len(documents)} documents in PROCESSING_STATUS for incremental sync (data_source={data_source})")
        
        # Store data source type for completion message
        PROCESSING_STATUS[processing_id]["data_source"] = data_source
        
        await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=status_callback, skip_graph=skip_graph, config_id=config_id)
    
    def _update_file_progress(self, processing_id: str, file_index: int, status: str = None, 
                             progress: int = None, phase: str = None, message: str = None, error: str = None):
        """Update progress for a specific file"""
        current_status = PROCESSING_STATUS.get(processing_id, {})
        file_progress = current_status.get("individual_files", [])
        
        if file_index < len(file_progress):
            file_info = file_progress[file_index]
            current_time = datetime.now().isoformat()
            
            if status:
                file_info["status"] = status
                if status == "processing" and not file_info["started_at"]:
                    file_info["started_at"] = current_time
                elif status in ["completed", "failed"]:
                    file_info["completed_at"] = current_time
            
            if progress is not None:
                file_info["progress"] = progress
            if phase:
                file_info["phase"] = phase
            if message:
                file_info["message"] = message
            if error:
                file_info["error"] = error
            
            # Keep overall progress in sync with per-file bars (average).
            completed_count = sum(1 for f in file_progress if f["status"] == "completed")
            overall_progress = round(
                sum(f.get("progress", 0) for f in file_progress) / len(file_progress)
            )
            overall_message = message or current_status.get("message", "Processing files...")
            overall_phase = phase or current_status.get("current_phase")
            logger.info(
                f"File progress update: {file_info['filename']} -> {file_info.get('status')} "
                f"({file_info.get('progress')}%) - {completed_count}/{len(file_progress)} completed, "
                f"overall={overall_progress}%"
            )
            
            self._update_processing_status(
                processing_id,
                current_status.get("status", "processing"),
                overall_message,
                overall_progress,
                current_file=file_info["filename"],
                current_phase=overall_phase,
                files_completed=completed_count,
                total_files=len(file_progress),
                file_progress=file_progress
            )
    
    async def _process_files_batch_with_progress(self, processing_id: str, file_paths: List[str]):
        """Process files in batch with per-file progress simulation"""
        try:
            logger.info(f"Starting batch processing with per-file progress for {len(file_paths)} files")
            
            # Get current status to preserve file_progress
            current_status = PROCESSING_STATUS.get(processing_id, {})
            existing_file_progress = current_status.get("individual_files", [])
            
            # If no existing file progress, initialize it
            if not existing_file_progress:
                logger.warning(f"No existing file progress found for {processing_id}, initializing now")
                existing_file_progress = self._initialize_file_progress(processing_id, file_paths)
            
            logger.info(f"Found {len(existing_file_progress)} files in progress tracking")
            
            # Mark all files as processing
            for file_index in range(len(file_paths)):
                self._update_file_progress(
                    processing_id, file_index,
                    status="processing",
                    progress=0,
                    phase="docling",
                    message="Starting batch processing..."
                )
            
            # Simulate progress updates during batch processing
            async def progress_updater():
                """Background task to simulate per-file progress during batch processing"""
                phases = [
                    ("docling", "Converting documents...", 20),
                    ("chunking", "Splitting into chunks...", 40),
                    ("kg_extraction", "Extracting knowledge graph...", 70),
                    ("indexing", "Building indexes...", 90)
                ]
                
                for phase_name, message, progress in phases:
                    await asyncio.sleep(0.5)  # Wait between phases
                    for file_index in range(len(file_paths)):
                        if not self._is_processing_cancelled(processing_id):
                            self._update_file_progress(
                                processing_id, file_index,
                                progress=progress,
                                phase=phase_name,
                                message=message
                            )
                    
                    # Check for cancellation
                    if self._is_processing_cancelled(processing_id):
                        return
            
            # Start progress updater in background
            progress_task = asyncio.create_task(progress_updater())
            
            try:
                # Create a completion callback that will be called when processing truly finishes
                def completion_callback(callback_processing_id=None, status=None, message=None, progress=None, **kwargs):
                    if status == "completed" or (progress and progress >= 100):
                        # This is called from hybrid_system.py AFTER the completion logs
                        logger.info(f"Real processing completed - now sending completion status to UI")
                        
                        # Use the processing_id from the outer scope
                        current_status = PROCESSING_STATUS.get(processing_id, {})
                        existing_file_progress = current_status.get("individual_files", [])
                        
                        # Optional: Clean up uploaded files after successful processing
                        # Check if files are from uploads directory
                        from pathlib import Path
                        upload_files = [f for f in file_paths if Path(f).parent.name == "uploads"]
                        if upload_files:
                            logger.info(f"Processing completed successfully - uploaded files can be cleaned up if needed")
                            # Note: Cleanup is available via /api/cleanup-uploads endpoint
                        
                        completion_message = self._generate_completion_message(len(file_paths))
                        self._update_processing_status(
                            processing_id,  # Use the processing_id from outer scope
                            "completed", 
                            completion_message, 
                            100,
                            total_files=len(file_paths),
                            files_completed=len(file_paths),
                            file_progress=existing_file_progress
                        )
                
                # Actual batch processing - use completion callback for proper timing
                await self.system.ingest_documents(
                    file_paths,
                    processing_id=processing_id,
                    status_callback=completion_callback,
                    skip_graph=skip_graph
                )
                
                # Cancel progress updater since real processing is done
                progress_task.cancel()
                
                # Mark all files as completed with a small delay to show 90% → 100% transition
                for file_index in range(len(file_paths)):
                    self._update_file_progress(
                        processing_id, file_index,
                        status="completed",
                        progress=100,
                        phase="completed",
                        message="Processing completed successfully"
                    )
                
                # No delay here - let the main method handle timing
                
            except Exception as e:
                # Cancel progress updater on error
                progress_task.cancel()
                
                # Mark all files as failed
                for file_index in range(len(file_paths)):
                    self._update_file_progress(
                        processing_id, file_index,
                        status="failed",
                        progress=0,
                        phase="error",
                        message=f"Processing failed: {str(e)}",
                        error=str(e)
                    )
                raise e
            
            # Don't send completed status here - let the main method handle it
            # This avoids duplicate "completed" messages and ensures proper timing
            logger.info(f"Batch processing completed for {len(file_paths)} files")
            
        except Exception as e:
            import traceback
            error_details = f"{type(e).__name__}: {str(e)}"
            if not str(e):  # If error message is empty, get more details
                error_details = f"{type(e).__name__} (no message) - Traceback: {traceback.format_exc()}"
            logger.error(f"Error in batch file processing: {error_details}")
            self._update_processing_status(
                processing_id,
                "failed",
                f"File processing failed: {error_details}",
                0
            )

    async def _process_files_with_progress(self, processing_id: str, file_paths: List[str]):
        """Process files sequentially with detailed per-file progress tracking"""
        try:
            for file_index, file_path in enumerate(file_paths):
                # Check for cancellation before each file
                if self._is_processing_cancelled(processing_id):
                    return
                
                filename = Path(file_path).name
                logger.info(f"Starting processing of file {file_index + 1}/{len(file_paths)}: {filename}")
                
                # Update file status to processing
                self._update_file_progress(
                    processing_id, file_index, 
                    status="processing", 
                    progress=0, 
                    phase="docling", 
                    message="Converting document..."
                )
                
                try:
                    # Process individual file with progress updates
                    await self._process_single_file_with_progress(processing_id, file_index, file_path)
                    
                    # Mark file as completed
                    self._update_file_progress(
                        processing_id, file_index,
                        status="completed",
                        progress=100,
                        phase="completed",
                        message="Processing completed successfully"
                    )
                    
                except Exception as e:
                    logger.error(f"Error processing file {filename}: {str(e)}")
                    self._update_file_progress(
                        processing_id, file_index,
                        status="failed",
                        progress=0,
                        phase="error",
                        message=f"Processing failed: {str(e)}",
                        error=str(e)
                    )
                    # Continue with next file instead of stopping entire process
                    continue
            
            # Update overall progress to completed
            completed_files = sum(1 for i in range(len(file_paths)) 
                                if PROCESSING_STATUS.get(processing_id, {}).get("individual_files", [{}])[i].get("status") == "completed")
            
            completion_message = self._generate_completion_message(completed_files)
            if completed_files < len(file_paths):
                failed_count = len(file_paths) - completed_files
                completion_message += f" ({failed_count} files failed)"
            
            self._update_processing_status(
                processing_id,
                "completed",
                completion_message,
                100
            )
            
        except Exception as e:
            logger.error(f"Error in file processing: {str(e)}")
            self._update_processing_status(
                processing_id,
                "failed",
                f"File processing failed: {str(e)}",
                0
            )
    
    async def _process_single_file_with_progress(self, processing_id: str, file_index: int, file_path: str):
        """Process a single file with detailed progress updates"""
        try:
            filename = Path(file_path).name
            logger.info(f"Processing file {file_index + 1}: {filename}")
            
            # Phase 1: Document conversion (Docling)
            self._update_file_progress(
                processing_id, file_index,
                progress=10,
                phase="docling",
                message="Converting document format..."
            )
            logger.info(f"File {filename}: Starting document conversion")
            await asyncio.sleep(0.5)  # Small delay to make progress visible
            
            # Phase 2: Text chunking
            self._update_file_progress(
                processing_id, file_index,
                progress=30,
                phase="chunking",
                message="Splitting into chunks..."
            )
            logger.info(f"File {filename}: Starting text chunking")
            await asyncio.sleep(0.5)  # Small delay to make progress visible
            
            # Phase 3: Knowledge graph extraction
            self._update_file_progress(
                processing_id, file_index,
                progress=50,
                phase="kg_extraction",
                message="Extracting knowledge graph..."
            )
            logger.info(f"File {filename}: Starting knowledge graph extraction")
            
            # Actual processing - call the system with single file
            # Note: This processes the single file through the full pipeline
            await self.system.ingest_documents(
                [file_path],
                processing_id=processing_id,
                status_callback=lambda pid, status, msg, prog, **kwargs: self._update_file_progress(
                    processing_id, file_index, progress=min(50 + int(prog * 0.4), 90)
                ),
                skip_graph=skip_graph
            )
            
            # Phase 4: Indexing
            self._update_file_progress(
                processing_id, file_index,
                progress=90,
                phase="indexing",
                message="Building indexes..."
            )
            logger.info(f"File {filename}: Completed processing")
            await asyncio.sleep(0.5)  # Small delay to make progress visible
            
        except Exception as e:
            logger.error(f"Error in single file processing: {str(e)}")
            raise e
    
    async def _cleanup_partial_processing(self, processing_id: str):
        """Clean up partial processing artifacts when cancelled"""
        try:
            logger.info(f"Cleaning up partial processing for {processing_id}")
            
            # Check if we have a fully functional system (completed previous ingestion)
            has_complete_system = (
                hasattr(self.system, 'vector_index') and self.system.vector_index is not None and
                hasattr(self.system, 'graph_index') and self.system.graph_index is not None and
                hasattr(self.system, 'hybrid_retriever') and self.system.hybrid_retriever is not None
            )
            
            if has_complete_system:
                # System was fully functional from previous ingestion - preserve it
                logger.info(f"Preserving existing functional system state after cancellation of {processing_id}")
                # Only clean up processing-specific state, not the core indexes
                if processing_id in PROCESSING_STATUS:
                    PROCESSING_STATUS[processing_id]["status"] = "cancelled"
                    PROCESSING_STATUS[processing_id]["message"] = "Processing cancelled - existing data preserved"
            else:
                # System was in partial state, safe to clear everything
                logger.info(f"Clearing partial system state after cancellation of {processing_id}")
                if hasattr(self.system, 'vector_index'):
                    self.system.vector_index = None
                if hasattr(self.system, 'graph_index'):
                    self.system.graph_index = None
                if hasattr(self.system, 'hybrid_retriever'):
                    self.system.hybrid_retriever = None
                
                # Also call the system's clear method if it exists
                if hasattr(self.system, '_clear_partial_state'):
                    self.system._clear_partial_state()
            
            logger.info(f"Cleanup completed for {processing_id}")
        except Exception as e:
            logger.error(f"Error during cleanup for {processing_id}: {str(e)}")
    
    # Core business logic methods
    
    async def ingest_documents(self, data_source: str = None, paths: List[str] = None, skip_graph: bool = False, config_id: str = None, **kwargs) -> Dict[str, Any]:
        """Start async document ingestion and return processing ID
        
        Args:
            skip_graph: If True, skip knowledge graph extraction for this ingest (temporary, doesn't persist)
            config_id: Optional stable config_id for incremental sync (generates stable doc_id format)
        """
        processing_id = self._create_processing_id()
        
        # Start processing immediately in background
        self._update_processing_status(
            processing_id, 
            "started", 
            "Complex document processing has started, please wait...", 
            0
        )
        
        # Start background task
        asyncio.create_task(self._process_documents_async(processing_id, data_source, paths, skip_graph, config_id, **kwargs))
        
        estimated_time = self._estimate_processing_time(data_source, paths)
        
        return {
            "processing_id": processing_id,
            "status": "started", 
            "message": "Document processing has started, please wait...",
            "estimated_time": estimated_time
        }
    
    async def _process_documents_async(self, processing_id: str, data_source: str = None, paths: List[str] = None, skip_graph: bool = False, config_id: str = None, **kwargs):
        """Background task for document processing"""
        try:
            data_source = data_source or self.settings.data_source
            
            # Log skip_graph flag if set
            if skip_graph:
                logger.info(f"skip_graph=True for processing_id={processing_id} - Knowledge graph extraction will be skipped for this ingest")
            
            # Log config_id if set (for stable doc_id)
            if config_id:
                logger.info(f"config_id={config_id} for processing_id={processing_id} - Using stable doc_id format for incremental sync")
            
            # Check for cancellation before starting
            if self._is_processing_cancelled(processing_id):
                return
                
            self._update_processing_status(
                processing_id,
                "processing",
                f"Initializing {data_source} document ingestion...",
                10
            )

            # FLOW MODE: run the Langflow ingestion flow (same spot as the use-component
            # pipeline branch) instead of the direct per-source pipeline below.
            if self.settings.enable_langflow_flows:
                # config_id is a named param here, so it isn't in **kwargs — pass it explicitly
                # (the flow needs it for stable doc_ids + document_state creation).
                await self._ingest_via_flow(processing_id, data_source, paths, skip_graph,
                                            config_id=config_id, **kwargs)
                return

            if data_source == "filesystem":
                # Extract filesystem_config from kwargs if provided (used by detectors)
                filesystem_config = kwargs.get('filesystem_config', {})
                # `paths is not None` on purpose, NOT truthiness: an explicitly empty list
                # means "the caller had nothing to ingest" (e.g. a UI upload where every file
                # was skipped), which must fail below rather than silently fall through to the
                # server's SOURCE_PATHS. Only an omitted `paths` (None) uses the config default.
                if paths is not None:
                    file_paths = paths
                else:
                    file_paths = filesystem_config.get('paths') or self.settings.source_paths
                if not file_paths:
                    self._update_processing_status(
                        processing_id, 
                        "failed", 
                        "No file paths provided for filesystem source", 
                        0
                    )
                    return
                
                # Clean paths - remove extra quotes that might come from frontend
                cleaned_paths = []
                for path in file_paths:
                    if isinstance(path, str):
                        # Remove surrounding quotes if present
                        cleaned_path = path.strip('"').strip("'")
                        cleaned_paths.append(cleaned_path)
                        logger.info(f"Cleaned path: {path} -> {cleaned_path}")
                    else:
                        cleaned_paths.append(path)
                
                # Initialize per-file progress tracking for UI
                file_progress = self._initialize_file_progress(processing_id, cleaned_paths)
                logger.info(f"Initialized per-file progress for {len(file_progress)} files")
                
                self._update_processing_status(
                    processing_id,
                    "processing",
                    "Initializing filesystem document ingestion...",
                    10,
                    total_files=len(cleaned_paths),
                    files_completed=0,
                    file_progress=file_progress
                )
                if self._is_processing_cancelled(processing_id):
                    return
                # Mark all files as starting load
                for i in range(len(file_progress)):
                    self._update_file_progress(
                        processing_id,
                        i,
                        status="processing",
                        progress=10,
                        phase="loading",
                        message="Scanning filesystem paths...",
                    )
                
                config = {"paths": cleaned_paths}
                
                # Use the same pattern as CMIS and Alfresco - go through IngestionManager
                # But create a custom status callback that provides individual_files data for UI
                def filesystem_status_callback(**cb_kwargs):
                    status = cb_kwargs.get("status", "processing")
                    progress = cb_kwargs.get("progress", 0)
                    current_file = cb_kwargs.get("current_file", "")
                    files_completed = cb_kwargs.get("files_completed", 0)
                    total_files = cb_kwargs.get("total_files", 0)
                    
                    # Handle completion status - mark all individual files as completed
                    if status == "completed" and progress == 100:
                        completion_msg = cb_kwargs.get("message") or "Processing completed"
                        for i in range(len(file_progress)):
                            self._update_file_progress(
                                processing_id, 
                                i, 
                                status="completed", 
                                progress=100,
                                phase="completed",
                                message=completion_msg
                            )
                        # _update_file_progress inherits the existing "processing" status when it
                        # calls _update_processing_status internally, so we must explicitly mark
                        # the overall job as completed here.
                        self._update_processing_status(
                            processing_id,
                            "completed",
                            completion_msg,
                            100,
                            total_files=len(file_progress),
                            files_completed=len(file_progress),
                            file_progress=file_progress,
                        )
                        return
                    # Handle loading progress - update individual file progress
                    elif files_completed > 0 and files_completed <= len(file_progress):
                        file_index = files_completed - 1  # Convert to 0-based index
                        self._update_file_progress(
                            processing_id, 
                            file_index, 
                            status="processing", 
                            progress=min(progress, 40),  # loading phase caps at 40%
                            phase="loading",
                            message=f"Loading {current_file}" if current_file else "Loading..."
                        )
                        return
                    
                    # Pipeline stage updates (chunk / vector / KG / RDF) — fan out to all active files
                    current_phase = cb_kwargs.get("current_phase", "processing")
                    pipeline_message = cb_kwargs.get("message", "Processing...")
                    if progress > 0:
                        for i, fp in enumerate(file_progress):
                            if fp.get("status") not in ("completed", "failed"):
                                self._update_file_progress(
                                    processing_id,
                                    i,
                                    status="processing",
                                    progress=progress,
                                    phase=current_phase,
                                    message=pipeline_message,
                                )
                
                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="filesystem",
                    config=config,
                    processing_id=processing_id,
                    status_callback=filesystem_status_callback
                )
                
                # Mark all files as loaded (not completed) after IngestionManager finishes
                for i in range(len(file_progress)):
                    self._update_file_progress(
                        processing_id, 
                        i, 
                        status="processing", 
                        progress=40,
                        phase="loaded",
                        message="Documents loaded, starting pipeline processing..."
                    )
                
                # Store documents in PROCESSING_STATUS for document_state creation
                PROCESSING_STATUS[processing_id]["documents"] = documents
                if config_id:
                    logger.info(f"Stored {len(documents)} documents in PROCESSING_STATUS for incremental sync (data_source=filesystem, config_id={config_id})")
                else:
                    logger.info(f"Stored {len(documents)} documents in PROCESSING_STATUS for one-time ingestion (data_source=filesystem)")
                
                await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=filesystem_status_callback, skip_graph=skip_graph, config_id=config_id)
                
            elif data_source == "cmis":
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Connecting to CMIS repository...", 
                    20
                )
                
                # Check for cancellation before connecting
                if self._is_processing_cancelled(processing_id):
                    return
                    
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Processing CMIS documents...", 
                    60
                )
                
                # Use new modular approach with IngestionManager
                cmis_config = kwargs.get('cmis_config')
                if cmis_config:
                    # Use provided config
                    config = cmis_config
                else:
                    # Use environment variables
                    import os
                    config = {
                        "url": os.getenv("CMIS_URL", "http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom"),
                        "username": os.getenv("CMIS_USERNAME", "admin"),
                        "password": os.getenv("CMIS_PASSWORD", "admin"),
                        "folder_path": os.getenv("CMIS_FOLDER_PATH", "/")
                    }
                
                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="cmis",
                    config=config,
                    processing_id=processing_id,
                    status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs)
                )
                
                # Store documents in PROCESSING_STATUS for document_state creation
                PROCESSING_STATUS[processing_id]["documents"] = documents
                
                await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs), skip_graph=skip_graph, config_id=config_id)
                
            elif data_source == "alfresco":
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Connecting to Alfresco repository...", 
                    20
                )
                
                # Check for cancellation before connecting
                if self._is_processing_cancelled(processing_id):
                    return
                    
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Processing Alfresco documents...", 
                    60
                )
                
                # Use new modular approach with IngestionManager
                alfresco_config = kwargs.get('alfresco_config')
                if alfresco_config:
                    # Use provided config
                    config = alfresco_config
                else:
                    # Use environment variables
                    import os
                    config = {
                        "url": os.getenv("ALFRESCO_URL", "http://localhost:8080/alfresco"),
                        "auth_method": os.getenv("ALFRESCO_AUTH_METHOD", "basic"),
                        "username": os.getenv("ALFRESCO_USERNAME", "admin"),
                        "password": os.getenv("ALFRESCO_PASSWORD", "admin"),
                        # Pre-obtained login ticket; with auth_method=ticket it replaces
                        # username/password rather than being fetched from them.
                        "ticket": os.getenv("ALFRESCO_TICKET", ""),
                        "path": os.getenv("ALFRESCO_PATH", "/")
                    }
                    # Optional OAuth2 config from env (auth_method=oauth2)
                    oauth2 = {
                        k: v for k, v in {
                            "client_id": os.getenv("ALFRESCO_OAUTH2_CLIENT_ID"),
                            "client_secret": os.getenv("ALFRESCO_OAUTH2_CLIENT_SECRET"),
                            "token_endpoint": os.getenv("ALFRESCO_OAUTH2_TOKEN_ENDPOINT"),
                            "grant_type": os.getenv("ALFRESCO_OAUTH2_GRANT_TYPE"),
                            "scope": os.getenv("ALFRESCO_OAUTH2_SCOPE"),
                            "access_token": os.getenv("ALFRESCO_OAUTH2_ACCESS_TOKEN"),
                            "refresh_token": os.getenv("ALFRESCO_OAUTH2_REFRESH_TOKEN"),
                        }.items() if v
                    }
                    if oauth2:
                        config["oauth2"] = oauth2
                    # Add STOMP port if configured
                    stomp_port = os.getenv("ALFRESCO_STOMP_PORT")
                    if stomp_port:
                        config["stomp_port"] = int(stomp_port)
                
                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="alfresco",
                    config=config,
                    processing_id=processing_id,
                    status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs)
                )
                
                # Store documents in PROCESSING_STATUS for document_state creation
                PROCESSING_STATUS[processing_id]["documents"] = documents
                
                await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs), skip_graph=skip_graph, config_id=config_id)

            elif data_source == "nuxeo":
                self._update_processing_status(
                    processing_id,
                    "processing",
                    "Connecting to Nuxeo repository...",
                    20
                )

                # Check for cancellation before connecting
                if self._is_processing_cancelled(processing_id):
                    return

                self._update_processing_status(
                    processing_id,
                    "processing",
                    "Processing Nuxeo documents...",
                    60
                )

                # Use new modular approach with IngestionManager
                nuxeo_config = kwargs.get('nuxeo_config')
                if nuxeo_config:
                    # Use provided config
                    config = nuxeo_config
                else:
                    # Use environment variables
                    import os
                    config = {
                        "url": os.getenv("NUXEO_URL", "http://localhost:8081/nuxeo"),
                        "auth_method": os.getenv("NUXEO_AUTH_METHOD", "basic"),
                        "username": os.getenv("NUXEO_USERNAME", "Administrator"),
                        "password": os.getenv("NUXEO_PASSWORD", "Administrator"),
                        "path": os.getenv("NUXEO_PATH", "/"),
                    }
                    # Optional token auth
                    token = os.getenv("NUXEO_TOKEN")
                    if token:
                        config["token"] = token
                    # Optional OAuth2 config from env
                    oauth2 = {
                        k: v for k, v in {
                            "client_id": os.getenv("NUXEO_OAUTH2_CLIENT_ID"),
                            "client_secret": os.getenv("NUXEO_OAUTH2_CLIENT_SECRET"),
                            "access_token": os.getenv("NUXEO_OAUTH2_ACCESS_TOKEN"),
                            "refresh_token": os.getenv("NUXEO_OAUTH2_REFRESH_TOKEN"),
                            "token_endpoint": os.getenv("NUXEO_OAUTH2_TOKEN_ENDPOINT"),
                            "openid_configuration_url": os.getenv("NUXEO_OAUTH2_OPENID_CONFIG_URL"),
                        }.items() if v
                    }
                    if oauth2:
                        config["oauth2"] = oauth2

                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="nuxeo",
                    config=config,
                    processing_id=processing_id,
                    status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs)
                )

                # Store documents in PROCESSING_STATUS for document_state creation
                PROCESSING_STATUS[processing_id]["documents"] = documents

                await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs), skip_graph=skip_graph, config_id=config_id)

            elif data_source == "web":
                # Initialize progress tracking for web source
                web_config = kwargs.get('web_config')
                if not web_config:
                    raise ValueError("Web configuration is required for web data source")
                
                # Get URL for display
                url = web_config.get('url', 'Web Page')
                file_progress = self._initialize_data_source_progress(processing_id, "web", url)
                
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Connecting to web page...", 
                    20,
                    total_files=1,
                    files_completed=0,
                    file_progress=file_progress
                )
                
                # Update data source progress
                self._update_data_source_progress(processing_id, "processing", 20, "connecting", "Connecting to web page...")
                
                # Check for cancellation before connecting
                if self._is_processing_cancelled(processing_id):
                    return
                    
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Processing web page content...", 
                    60,
                    total_files=1,
                    files_completed=0,
                    file_progress=file_progress
                )
                
                # Update data source progress
                self._update_data_source_progress(processing_id, "processing", 60, "loading", "Processing web page content...")
                
                # Create status callback that updates both overall and individual progress
                def web_status_callback(**cb_kwargs):
                    status = cb_kwargs.get("status", "processing")
                    progress = cb_kwargs.get("progress", 0)
                    message = cb_kwargs.get("message", "")
                    
                    # Update data source progress
                    self._update_data_source_progress(processing_id, status, progress, "processing", message)
                
                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="web",
                    config=web_config,
                    processing_id=processing_id,
                    status_callback=web_status_callback
                )
                
                # Store documents in PROCESSING_STATUS for document_state creation
                PROCESSING_STATUS[processing_id]["documents"] = documents
                
                await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=web_status_callback, skip_graph=skip_graph, config_id=config_id)
                
            elif data_source == "youtube":
                # Initialize progress tracking for YouTube source
                youtube_config = kwargs.get('youtube_config')
                if not youtube_config:
                    raise ValueError("YouTube configuration is required for YouTube data source")
                
                # Get video URL for display
                video_url = youtube_config.get('url', 'YouTube Video')
                file_progress = self._initialize_data_source_progress(processing_id, "youtube", video_url)
                
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Connecting to YouTube...", 
                    20,
                    total_files=1,
                    files_completed=0,
                    file_progress=file_progress
                )
                
                # Update data source progress
                self._update_data_source_progress(processing_id, "processing", 20, "connecting", "Connecting to YouTube...")
                
                # Check for cancellation before connecting
                if self._is_processing_cancelled(processing_id):
                    return
                    
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Processing YouTube transcript...", 
                    60,
                    total_files=1,
                    files_completed=0,
                    file_progress=file_progress
                )
                
                # Update data source progress
                self._update_data_source_progress(processing_id, "processing", 60, "loading", "Processing YouTube transcript...")
                
                # Create status callback that updates both overall and individual progress
                def youtube_status_callback(**cb_kwargs):
                    status = cb_kwargs.get("status", "processing")
                    progress = cb_kwargs.get("progress", 0)
                    message = cb_kwargs.get("message", "")
                    
                    # Update data source progress
                    self._update_data_source_progress(processing_id, status, progress, "processing", message)
                    
                    # Update overall status
                    current_status = PROCESSING_STATUS.get(processing_id, {})
                    current_file_progress = current_status.get("individual_files", file_progress)
                    
                    self._update_processing_status(
                        processing_id=processing_id,
                        status=status,
                        message=message,
                        progress=progress,
                        total_files=1,
                        files_completed=1 if status == "completed" else 0,
                        file_progress=current_file_progress
                    )
                
                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="youtube",
                    config=youtube_config,
                    processing_id=processing_id,
                    status_callback=youtube_status_callback
                )
                
                # Store documents in PROCESSING_STATUS for document_state creation
                PROCESSING_STATUS[processing_id]["documents"] = documents
                
                await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=youtube_status_callback, skip_graph=skip_graph, config_id=config_id)
                
            elif data_source == "wikipedia":
                # Initialize progress tracking for Wikipedia source
                wikipedia_config = kwargs.get('wikipedia_config')
                if not wikipedia_config:
                    raise ValueError("Wikipedia configuration is required for Wikipedia data source")
                
                # Get query for display
                query = wikipedia_config.get('query', 'Wikipedia Article')
                file_progress = self._initialize_data_source_progress(processing_id, "wikipedia", query)
                
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Connecting to Wikipedia...", 
                    20,
                    total_files=1,
                    files_completed=0,
                    file_progress=file_progress
                )
                
                # Update data source progress
                self._update_data_source_progress(processing_id, "processing", 20, "connecting", "Connecting to Wikipedia...")
                
                # Check for cancellation before connecting
                if self._is_processing_cancelled(processing_id):
                    return
                    
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Processing Wikipedia content...", 
                    60,
                    total_files=1,
                    files_completed=0,
                    file_progress=file_progress
                )
                
                # Update data source progress
                self._update_data_source_progress(processing_id, "processing", 60, "loading", "Processing Wikipedia content...")
                
                # Create status callback that updates both overall and individual progress
                def wikipedia_status_callback(**cb_kwargs):
                    status = cb_kwargs.get("status", "processing")
                    progress = cb_kwargs.get("progress", 0)
                    message = cb_kwargs.get("message", "")
                    
                    # Update data source progress
                    self._update_data_source_progress(processing_id, status, progress, "processing", message)
                    
                    # Update overall status
                    current_status = PROCESSING_STATUS.get(processing_id, {})
                    current_file_progress = current_status.get("individual_files", file_progress)
                    
                    self._update_processing_status(
                        processing_id=processing_id,
                        status=status,
                        message=message,
                        progress=progress,
                        total_files=1,
                        files_completed=1 if status == "completed" else 0,
                        file_progress=current_file_progress
                    )
                
                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="wikipedia",
                    config=wikipedia_config,
                    processing_id=processing_id,
                    status_callback=wikipedia_status_callback
                )
                
                # Store documents in PROCESSING_STATUS for document_state creation
                PROCESSING_STATUS[processing_id]["documents"] = documents
                
                await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=wikipedia_status_callback, skip_graph=skip_graph, config_id=config_id)
                
            elif data_source == "s3":
                # Initialize progress tracking for S3 source
                s3_config = kwargs.get('s3_config')
                if not s3_config:
                    raise ValueError("S3 configuration is required for S3 data source")
                
                # Get bucket and prefix for display
                bucket_name = s3_config.get('bucket_name', 'S3 Bucket')
                prefix = s3_config.get('prefix', '')
                
                # Create display name with bucket and prefix
                if prefix:
                    display_name = f's3://{bucket_name}/{prefix}'
                else:
                    display_name = f's3://{bucket_name}'
                
                file_progress = self._initialize_data_source_progress(processing_id, "s3", display_name)
                
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Connecting to Amazon S3...", 
                    20,
                    total_files=1,
                    files_completed=0,
                    file_progress=file_progress
                )
                
                # Update data source progress
                self._update_data_source_progress(processing_id, "processing", 20, "connecting", "Connecting to Amazon S3...")
                
                # Check for cancellation before connecting
                if self._is_processing_cancelled(processing_id):
                    return
                    
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Processing S3 documents...", 
                    60,
                    total_files=1,
                    files_completed=0,
                    file_progress=file_progress
                )
                
                # Update data source progress
                self._update_data_source_progress(processing_id, "processing", 60, "loading", "Processing S3 documents...")
                
                # Create status callback that updates both overall and individual progress
                def s3_status_callback(**cb_kwargs):
                    status = cb_kwargs.get("status", "processing")
                    progress = cb_kwargs.get("progress", 0)
                    message = cb_kwargs.get("message", "")
                    
                    # Update data source progress (this internally calls _update_processing_status)
                    self._update_data_source_progress(processing_id, status, progress, "processing", message)
                
                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="s3",
                    config=s3_config,
                    processing_id=processing_id,
                    status_callback=s3_status_callback
                )
                
                # Store documents in PROCESSING_STATUS for document_state creation
                PROCESSING_STATUS[processing_id]["documents"] = documents
                
                await self.system._ingest_source_documents(documents, processing_id=processing_id, status_callback=s3_status_callback, skip_graph=skip_graph, config_id=config_id)
                
            elif data_source == "gcs":
                gcs_config = kwargs.get('gcs_config', {})
                # Resolve service_account_key_path → credentials string if needed
                if not gcs_config.get('credentials') and gcs_config.get('service_account_key_path'):
                    _sa_path = gcs_config['service_account_key_path']
                    try:
                        import json as _json_mod, os as _os
                        if not _os.path.isabs(_sa_path):
                            _sa_path = _os.path.join(_os.path.dirname(__file__), _sa_path)
                        with open(_sa_path, encoding="utf-8") as _fh:
                            gcs_config = dict(gcs_config)
                            gcs_config['credentials'] = _fh.read()
                            kwargs = dict(kwargs, gcs_config=gcs_config)
                        logger.info("GCS: loaded credentials from service_account_key_path=%s", _sa_path)
                    except Exception as _e:
                        logger.warning("GCS: could not read service_account_key_path %s: %s", _sa_path, _e)
                bucket_name = gcs_config.get('bucket_name', 'GCS Bucket')
                await self._process_modular_data_source(
                    processing_id=processing_id,
                    data_source="gcs",
                    config_key="gcs_config",
                    display_name=bucket_name,
                    connect_message="Connecting to Google Cloud Storage...",
                    process_message="Processing GCS documents...",
                    config_id=config_id,
                    skip_graph=skip_graph,  # Pass explicitly as named parameter
                    **kwargs
                )
                
            elif data_source == "azure_blob":
                azure_blob_config = kwargs.get('azure_blob_config', {})
                container_name = azure_blob_config.get('container_name', 'Container')
                account_url = azure_blob_config.get('account_url', '')
                # Extract account name from URL for display
                if account_url:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(account_url)
                        account_name = parsed.hostname.split('.')[0] if parsed.hostname else 'Azure'
                        display_name = f'Azure: {account_name}/{container_name}'
                    except:
                        display_name = f'Azure: {container_name}'
                else:
                    display_name = f'Azure: {container_name}'
                await self._process_modular_data_source(
                    processing_id=processing_id,
                    data_source="azure_blob",
                    config_key="azure_blob_config",
                    display_name=display_name,
                    connect_message="Connecting to Azure Blob Storage...",
                    process_message="Processing Azure Blob Storage documents...",
                    config_id=config_id,
                    skip_graph=skip_graph,  # Pass explicitly as named parameter
                    **kwargs
                )
                
            elif data_source == "onedrive":
                onedrive_config = kwargs.get('onedrive_config', {})
                user_principal_name = onedrive_config.get('user_principal_name', '')
                folder_path = onedrive_config.get('folder_path', '')
                folder_id = onedrive_config.get('folder_id', '')
                
                # Create display name using user principal name and folder info
                if user_principal_name:
                    if folder_path:
                        display_name = f'OneDrive: {user_principal_name}{folder_path}'
                    elif folder_id:
                        display_name = f'OneDrive: {user_principal_name} (Folder ID: {folder_id})'
                    else:
                        display_name = f'OneDrive: {user_principal_name}'
                else:
                    display_name = 'OneDrive'
                    
                await self._process_modular_data_source(
                    processing_id=processing_id,
                    data_source="onedrive",
                    config_key="onedrive_config",
                    display_name=display_name,
                    connect_message="Connecting to Microsoft OneDrive...",
                    process_message="Processing OneDrive documents...",
                    config_id=config_id,
                    skip_graph=skip_graph,  # Pass explicitly as named parameter
                    **kwargs
                )
                
            elif data_source == "sharepoint":
                sharepoint_config = kwargs.get('sharepoint_config', {})
                site_name = sharepoint_config.get('site_name', '')
                site_id = sharepoint_config.get('site_id', '')
                folder_path = sharepoint_config.get('folder_path', '')
                folder_id = sharepoint_config.get('folder_id', '')
                
                # Create display name using site name and folder info
                if site_name:
                    if folder_path:
                        display_name = f'SharePoint: {site_name}{folder_path}'
                    elif folder_id:
                        display_name = f'SharePoint: {site_name} (Folder ID: {folder_id})'
                    else:
                        display_name = f'SharePoint: {site_name}'
                elif site_id:
                    display_name = f'SharePoint: Site ID {site_id}'
                else:
                    display_name = 'SharePoint'
                    
                await self._process_modular_data_source(
                    processing_id=processing_id,
                    data_source="sharepoint",
                    config_key="sharepoint_config",
                    display_name=display_name,
                    connect_message="Connecting to Microsoft SharePoint...",
                    process_message="Processing SharePoint documents...",
                    config_id=config_id,
                    skip_graph=skip_graph,  # Pass explicitly as named parameter
                    **kwargs
                )
                
            elif data_source == "box":
                box_config = kwargs.get('box_config', {})
                folder_id = box_config.get('folder_id', 'Box Folder')
                await self._process_modular_data_source(
                    processing_id=processing_id,
                    data_source="box",
                    config_key="box_config",
                    display_name=folder_id,
                    connect_message="Connecting to Box...",
                    process_message="Processing Box documents...",
                    config_id=config_id,
                    skip_graph=skip_graph,  # Pass explicitly as named parameter
                    **kwargs
                )
                
            elif data_source == "google_drive":
                google_drive_config = kwargs.get('google_drive_config', {})
                # Use folder_id if provided, otherwise generic name
                folder_id = google_drive_config.get('folder_id')
                if folder_id:
                    display_name = f'Google Drive: {folder_id}'
                else:
                    display_name = 'Google Drive'
                await self._process_modular_data_source(
                    processing_id=processing_id,
                    data_source="google_drive",
                    config_key="google_drive_config",
                    display_name=display_name,
                    connect_message="Connecting to Google Drive...",
                    process_message="Processing Google Drive documents...",
                    config_id=config_id,
                    skip_graph=skip_graph,  # Pass explicitly as named parameter
                    **kwargs
                )
                
            else:
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"Unsupported data source: {data_source}", 
                    0
                )
                
        except RuntimeError as e:
            if "cancelled by user" in str(e):
                logger.info(f"Processing {processing_id} was cancelled by user")
                # Clean up any partial indexes that might have been created
                await self._cleanup_partial_processing(processing_id)
            else:
                import traceback
                error_msg = str(e) if str(e) else repr(e)
                logger.error(f"Runtime error in processing {processing_id}: {error_msg}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"Document processing failed: {error_msg}", 
                    0
                )
        except Exception as e:
            import traceback
            # Handle LLM self-cancellation and timeout errors gracefully
            error_str = str(e).lower() if str(e) else ""
            error_msg = str(e) if str(e) else repr(e)
            
            if any(keyword in error_str for keyword in ['timeout', 'timed out', 'request timeout', 'connection timeout']):
                logger.warning(f"LLM timeout in processing {processing_id}: {error_msg}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"Processing timeout - LLM took too long to respond. Try increasing timeout or using smaller documents: {error_msg}", 
                    0
                )
            elif any(keyword in error_str for keyword in ['cancelled', 'aborted', 'interrupted']):
                logger.warning(f"LLM self-cancelled in processing {processing_id}: {error_msg}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"LLM processing was interrupted. This can happen with complex documents: {error_msg}", 
                    0
                )
            else:
                logger.error(f"Error ingesting documents {processing_id}: {error_msg}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"Document processing failed: {error_msg}", 
                    0
                )
    
    async def search_documents(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """Search documents using hybrid search"""
        start_time = datetime.now()
        logger.info(f"Search query started at {start_time.strftime('%H:%M:%S.%f')[:-3]} - Query: '{query}' (top_k={top_k})")

        try:
            # FLOW MODE: run the Langflow query flow instead of the system.
            if self.settings.enable_langflow_flows:
                fsvc = await self._get_flow_service()
                results = await fsvc.run_search_flow(query, top_k=top_k)
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"Flow search returned {len(results)} results in {duration:.3f}s")
                return {"success": True, "results": results, "query_time": f"{duration:.3f}s"}

            results = await self.system.search(query, top_k=top_k)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"Search query completed in {duration:.3f}s - Returning {len(results)} final results (post-deduplication)")
            
            return {"success": True, "results": results, "query_time": f"{duration:.3f}s"}
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            error_msg = str(e)
            # Return empty results (not a red error) when the system is simply not yet
            # populated — same behaviour as when a vector/search DB returns no hits.
            _not_ready_phrases = (
                "no search indexes available",
                "please ingest documents first",
                "system not initialized",
                "rdf graph retriever could not be initialised",
                "databases may be empty",
            )
            if any(p in error_msg.lower() for p in _not_ready_phrases):
                logger.warning(f"Search attempted before ingestion: {error_msg}")
                return {"success": True, "results": [], "query_time": f"{duration:.3f}s",
                        "message": "No documents have been indexed yet. Please ingest documents first."}
            logger.error(f"Search query failed after {duration:.3f}s: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg, "query_time": f"{duration:.3f}s"}
    
    async def qa_query(self, query: str) -> Dict[str, Any]:
        """Answer a question using the Q&A system"""
        start_time = datetime.now()
        logger.info(f"Q&A query started at {start_time.strftime('%H:%M:%S.%f')[:-3]} - Query: '{query}'")

        try:
            # FLOW MODE: run the Langflow query flow instead of the system.
            if self.settings.enable_langflow_flows:
                fsvc = await self._get_flow_service()
                qa = await fsvc.run_aiquery_flow(query)
                duration = (datetime.now() - start_time).total_seconds()
                return {"success": True, "answer": qa["answer"], "sources": qa["sources"],
                        "query_time": f"{duration:.3f}s"}

            # Ensure Weaviate async client is connected before Q&A query
            if self.system.vector_store and type(self.system.vector_store).__name__ == "WeaviateVectorStore":
                if hasattr(self.system.vector_store, '_aclient') and self.system.vector_store._aclient is not None:
                    if not self.system.vector_store._aclient.is_connected():
                        await self.system.vector_store._aclient.connect()
                        logger.info("Connected Weaviate async client for Q&A query")
            
            query_engine = self.system.get_query_engine()
            
            # Use async method directly (nest_asyncio.apply() called at module level)
            _qa_attempts = 0
            while True:
                try:
                    _qa_attempts += 1
                    response = await query_engine.aquery(query)
                    break
                except Exception as e:
                    error_msg = str(e)
                    # Handle index/collection not found errors and not-yet-ingested state gracefully
                    _not_ready = (
                        'index_not_found_exception' in error_msg or
                        'no such index' in error_msg or
                        "doesn't exist" in error_msg or
                        'Not found' in error_msg or
                        'could not find class' in error_msg or  # Weaviate collection not found
                        'NotFoundError' in str(type(e)) or
                        'no search indexes available' in error_msg.lower() or
                        'please ingest documents first' in error_msg.lower() or
                        'system not initialized' in error_msg.lower() or
                        'rdf graph retriever could not be initialised' in error_msg.lower() or
                        'databases may be empty' in error_msg.lower()
                    )
                    if _not_ready:
                        logger.warning(f"Q&A attempted before ingestion or index not found: {error_msg}")
                        end_time = datetime.now()
                        duration = (end_time - start_time).total_seconds()
                        return {
                            "success": True,  # Don't show as error in UI
                            "answer": "No documents have been indexed yet. Please ingest documents first.",
                            "query_time": f"{duration:.3f}s",
                            "sources": []
                        }
                    _is_transient = any(p in error_msg for p in (
                        "Error code: 400", "Error code: 429", "Error code: 500", "Error code: 503",
                        "Connection", "timeout", "invalid_request_error",
                    ))
                    if _is_transient and _qa_attempts < 3:
                        _wait = 5 * _qa_attempts
                        logger.warning(
                            f"Q&A attempt {_qa_attempts} failed "
                            f"(transient): {error_msg[:120]} — retrying in {_wait}s"
                        )
                        await asyncio.sleep(_wait)
                    else:
                        raise
                    # Re-raise other exceptions
                    raise
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            answer = str(response)
            logger.info(f"Q&A query completed in {duration:.3f}s - Answer length: {len(answer)} characters")
            
            # Record LLM generation metrics for observability
            if hasattr(self.system, '_observability_enabled') and self.system._observability_enabled:
                try:
                    from observability.metrics import get_rag_metrics
                    metrics = get_rag_metrics()
                    generation_latency_ms = duration * 1000
                    
                    # Extract token counts from response metadata if available
                    prompt_tokens = 0
                    completion_tokens = 0
                    if hasattr(response, 'metadata') and response.metadata:
                        prompt_tokens = response.metadata.get('prompt_tokens', 0)
                        completion_tokens = response.metadata.get('completion_tokens', 0)
                    elif hasattr(response, 'source_nodes'):
                        # Try to get from source nodes metadata
                        for node in response.source_nodes:
                            if hasattr(node, 'metadata') and node.metadata:
                                prompt_tokens += node.metadata.get('prompt_tokens', 0)
                                completion_tokens += node.metadata.get('completion_tokens', 0)
                    
                    metrics.record_llm_call(
                        latency_ms=generation_latency_ms,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        attributes={"operation": "qa_query", "query_length": len(query)}
                    )
                    logger.info(f"Recorded LLM generation metrics: {generation_latency_ms:.2f}ms, {prompt_tokens} prompt tokens, {completion_tokens} completion tokens")
                except Exception as e:
                    logger.warning(f"Failed to record LLM metrics: {e}")
            
            return {"success": True, "answer": answer, "query_time": f"{duration:.3f}s"}
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            error_msg = str(e)
            _not_ready_phrases = (
                "no search indexes available",
                "please ingest documents first",
                "system not initialized",
                "rdf graph retriever could not be initialised",
                "databases may be empty",
            )
            if any(p in error_msg.lower() for p in _not_ready_phrases):
                logger.warning(f"Q&A attempted before ingestion: {error_msg}")
                return {
                    "success": True,
                    "answer": "No documents have been indexed yet. Please ingest documents first.",
                    "query_time": f"{duration:.3f}s",
                    "sources": []
                }
            logger.error(f"Q&A query failed after {duration:.3f}s: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg, "query_time": f"{duration:.3f}s"}
    
    async def query_documents(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """Query documents with AI-generated answers"""
        start_time = datetime.now()
        logger.info(f"Document query started at {start_time.strftime('%H:%M:%S.%f')[:-3]} - Query: '{query}'")

        try:
            # FLOW MODE: run the Langflow query flow instead of the system.
            if self.settings.enable_langflow_flows:
                fsvc = await self._get_flow_service()
                qa = await fsvc.run_aiquery_flow(query)
                duration = (datetime.now() - start_time).total_seconds()
                return {"success": True, "answer": qa["answer"], "sources": qa["sources"],
                        "query_time": f"{duration:.3f}s"}

            query_engine = self.system.get_query_engine()

            # Use async method directly (nest_asyncio.apply() called at module level)
            _qd_attempts = 0
            while True:
                try:
                    _qd_attempts += 1
                    response = await query_engine.aquery(query)
                    break
                except Exception as e:
                    error_msg = str(e)
                    _err_lower = error_msg.lower()
                    # LLM config errors (bad deployment, missing key, model not found) — surface clearly
                    _is_llm_config_err = (
                        'deploymentnotfound' in _err_lower or
                        'deployment not found' in _err_lower or
                        'resource not found' in _err_lower or
                        'model not found' in _err_lower or
                        'publisher model' in _err_lower or
                        "requires 'api_key'" in _err_lower
                    )
                    if _is_llm_config_err:
                        logger.warning(f"LLM configuration error during document query: {error_msg[:300]}")
                        end_time = datetime.now()
                        duration = (end_time - start_time).total_seconds()
                        return {
                            "success": False,
                            "answer": f"LLM configuration error: {error_msg[:300]}",
                            "query_time": f"{duration:.3f}s",
                            "sources": []
                        }
                    # Handle index/collection not found errors gracefully (case-insensitive)
                    if ('index_not_found_exception' in _err_lower or
                        'no such index' in _err_lower or
                        "doesn't exist" in _err_lower or
                        'not found' in _err_lower or
                        'NotFoundError' in str(type(e))):
                        logger.warning(f"Collection/Index not found during document query: {error_msg}")
                        end_time = datetime.now()
                        duration = (end_time - start_time).total_seconds()
                        return {
                            "success": True,  # Don't show as error in UI
                            "answer": "No documents have been indexed yet.",
                            "query_time": f"{duration:.3f}s",
                            "sources": []
                        }
                    # Rate limit / request too large — return clean answer so test shows readable failure
                    if ('Error code: 413' in error_msg or
                        'rate_limit_exceeded' in error_msg or
                        'Request too large' in error_msg or
                        'tokens_per_minute' in error_msg):
                        logger.warning(f"LLM rate limit / request too large: {error_msg[:600]}")
                        end_time = datetime.now()
                        duration = (end_time - start_time).total_seconds()
                        return {
                            "success": True,
                            "answer": f"LLM rate limit exceeded: {error_msg[:600]}",
                            "query_time": f"{duration:.3f}s",
                            "sources": []
                        }
                    _is_transient = any(p in error_msg for p in (
                        "Error code: 400", "Error code: 429", "Error code: 500", "Error code: 503",
                        "Connection", "timeout", "invalid_request_error",
                    ))
                    if _is_transient and _qd_attempts < 3:
                        _wait = 5 * _qd_attempts
                        logger.warning(
                            f"Document query attempt {_qd_attempts} failed "
                            f"(transient): {error_msg[:120]} — retrying in {_wait}s"
                        )
                        await asyncio.sleep(_wait)
                    else:
                        raise

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            answer = str(response)
            logger.info(f"Document query completed in {duration:.3f}s - Answer length: {len(answer)} characters")
            
            # Record LLM generation metrics for observability
            if hasattr(self.system, '_observability_enabled') and self.system._observability_enabled:
                try:
                    from observability.metrics import get_rag_metrics
                    metrics = get_rag_metrics()
                    generation_latency_ms = duration * 1000
                    
                    # Extract token counts from response metadata if available
                    prompt_tokens = 0
                    completion_tokens = 0
                    if hasattr(response, 'metadata') and response.metadata:
                        prompt_tokens = response.metadata.get('prompt_tokens', 0)
                        completion_tokens = response.metadata.get('completion_tokens', 0)
                    elif hasattr(response, 'source_nodes'):
                        # Try to get from source nodes metadata
                        for node in response.source_nodes:
                            if hasattr(node, 'metadata') and node.metadata:
                                prompt_tokens += node.metadata.get('prompt_tokens', 0)
                                completion_tokens += node.metadata.get('completion_tokens', 0)
                    
                    metrics.record_llm_call(
                        latency_ms=generation_latency_ms,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        attributes={"operation": "query_documents", "query_length": len(query)}
                    )
                    logger.info(f"Recorded LLM generation metrics: {generation_latency_ms:.2f}ms, {prompt_tokens} prompt tokens, {completion_tokens} completion tokens")
                except Exception as e:
                    logger.warning(f"Failed to record LLM metrics: {e}")
            
            return {"success": True, "answer": answer, "query_time": f"{duration:.3f}s"}
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.error(f"Document query failed after {duration:.3f}s: {str(e)}")
            return {"success": False, "error": str(e), "query_time": f"{duration:.3f}s"}
    
    async def ingest_text(self, content: str, source_name: str = "text_input", skip_graph: bool = False) -> Dict[str, Any]:
        """Start async text ingestion and return processing ID"""
        processing_id = self._create_processing_id()
        
        # Start processing immediately in background
        self._update_processing_status(
            processing_id, 
            "started", 
            "Complex document processing has started, please wait...", 
            0
        )
        
        # Start background task
        asyncio.create_task(self._process_text_async(processing_id, content, source_name, skip_graph=skip_graph))
        
        estimated_time = self._estimate_processing_time(content=content)
        
        return {
            "processing_id": processing_id,
            "status": "started", 
            "message": "Text processing has started, please wait...",
            "estimated_time": estimated_time
        }
    
    async def _process_text_async(self, processing_id: str, content: str, source_name: str, skip_graph: bool = False):
        """Background task for text processing"""
        try:
            self._update_processing_status(
                processing_id, 
                "processing", 
                "Creating document and initializing pipeline...", 
                10
            )
            
            self._update_processing_status(
                processing_id, 
                "processing", 
                "Processing text and generating embeddings...", 
                30
            )
            
            self._update_processing_status(
                processing_id, 
                "processing", 
                "Building vector index...", 
                50
            )
            
            self._update_processing_status(
                processing_id, 
                "processing", 
                "Extracting knowledge graph...", 
                70
            )
            
            self._update_processing_status(
                processing_id, 
                "processing", 
                "Creating graph index and relationships...", 
                85
            )
            
            # Actual processing with cancellation support
            await self.system.ingest_text(content=content, source_name=source_name, processing_id=processing_id, skip_graph=skip_graph)
            
            self._update_processing_status(
                processing_id, 
                "completed", 
                "Text content ingested successfully! Knowledge graph and vector index ready.", 
                100
            )
            
        except RuntimeError as e:
            if "cancelled by user" in str(e):
                logger.info(f"Text processing {processing_id} was cancelled by user")
                # Clean up any partial indexes that might have been created
                await self._cleanup_partial_processing(processing_id)
            else:
                logger.error(f"Runtime error in text processing {processing_id}: {str(e)}", exc_info=True)
                self._update_processing_status(
                    processing_id,
                    "failed",
                    f"Processing failed: {str(e)}",
                    0
                )
        except Exception as e:
            logger.error(f"Error ingesting text {processing_id}: {str(e)}", exc_info=True)
            self._update_processing_status(
                processing_id,
                "failed",
                f"Processing failed: {repr(e)}",
                0
            )
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status without triggering database initialization"""
        try:
            # Return status without initializing databases to avoid APOC calls
            return {
                "success": True,
                "status": {
                    "has_vector_index": self._system is not None and self._system.vector_index is not None,
                    "has_graph_index": self._system is not None and self._system.graph_index is not None,
                    "has_hybrid_retriever": self._system is not None and self._system.hybrid_retriever is not None,
                    "config": {
                        "data_source": self.settings.data_source,
                        "vector_db": self.settings.vector_db,
                        "pg_graph_db": self.settings.pg_graph_db,
                        "rdf_graph_db": self.settings.rdf_graph_db,
                        "search_db": self.settings.search_db,
                        "llm_provider": self.settings.llm_provider,
                        "enable_knowledge_graph": self.settings.enable_knowledge_graph,
                        "graph_backend": self.settings.graph_backend,
                        "vector_backend": self.settings.vector_backend,
                        "search_backend": self.settings.search_backend,
                        "chunker_backend": self.settings.chunker_backend,
                        "kg_extractor_backend": self.settings.kg_extractor_backend,
                        "retrieval_fusion": self.settings.retrieval_fusion,
                    },
                    "system_initialized": self._system is not None
                }
            }
        except Exception as e:
            logger.error(f"Error getting status: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        return {
            "success": True,
            "config": {
                "data_source": self.settings.data_source,
                "vector_db": self.settings.vector_db,
                "pg_graph_db": self.settings.pg_graph_db,
                "rdf_graph_db": self.settings.rdf_graph_db,
                "search_db": self.settings.search_db,
                "llm_provider": self.settings.llm_provider,
                "enable_knowledge_graph": self.settings.enable_knowledge_graph,
                "graph_backend": self.settings.graph_backend,
                "vector_backend": self.settings.vector_backend,
                "search_backend": self.settings.search_backend,
                "chunker_backend": self.settings.chunker_backend,
                "kg_extractor_backend": self.settings.kg_extractor_backend,
                "retrieval_fusion": self.settings.retrieval_fusion,
            }
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Health check"""
        return {"success": True, "status": "ok"}
    
    def _generate_completion_message(self, doc_count: int) -> str:
        """Generate dynamic completion message based on enabled features"""
        # Check what's actually enabled
        has_vector = str(self.settings.vector_db) != "none"
        has_graph = str(self.settings.pg_graph_db) != "none" and self.settings.enable_knowledge_graph
        has_search = str(self.settings.search_db) != "none"
        
        # Map database names to proper capitalization
        db_name_map = {
            "opensearch": "OpenSearch",
            "elasticsearch": "Elasticsearch",
            "qdrant": "Qdrant",
            "chroma": "Chroma",
            "neo4j": "Neo4j",
            "ladybug": "Ladybug",
            "falkordb": "FalkorDB",
            "nebula": "NebulaGraph",
            "bm25": "BM25"
        }
        
        # Build feature list
        features = []
        if has_vector:
            features.append("vector index")
        if has_graph:
            features.append("knowledge graph")
        if has_search:
            search_db = str(self.settings.search_db).lower()
            search_name = db_name_map.get(search_db, search_db.title())
            features.append(f"{search_name} search")
        
        # Create appropriate message
        if features:
            feature_text = " and ".join(features)
            return f"Successfully ingested {doc_count} document(s)! {feature_text.title()} ready."
        else:
            # Fallback (shouldn't happen due to validation)
            return f"Successfully ingested {doc_count} document(s)!"

# Global backend instance
_backend_instance = None

def get_backend() -> FlexibleGraphRAGBackend:
    """Get the global backend instance"""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = FlexibleGraphRAGBackend()
    return _backend_instance