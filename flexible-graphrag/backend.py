"""
Shared backend core for Flexible GraphRAG
This module contains the business logic that can be called by both FastAPI and FastMCP servers
"""

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
        self.ingestion_manager = IngestionManager()
        logger.info("FlexibleGraphRAGBackend initialized")
    
    @property
    def system(self) -> HybridSearchSystem:
        """Lazy-load the hybrid search system"""
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
        
        PROCESSING_STATUS[processing_id] = status_update
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
                                         display_name: str, connect_message: str, process_message: str, **kwargs):
        """Generic method to process modular data sources with proper progress tracking"""
        # Get configuration
        config = kwargs.get(config_key)
        if not config:
            raise ValueError(f"{data_source.title()} configuration is required for {data_source} data source")
        
        # Get skip_graph flag from kwargs
        skip_graph = kwargs.get('skip_graph', False)
        
        # Log the config for debugging
        logger.info(f"Processing {data_source} with config: {config}")
        
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
        
        # Store data source type for completion message
        PROCESSING_STATUS[processing_id]["data_source"] = data_source
        
        await self.system._process_documents_direct(documents, processing_id=processing_id, status_callback=status_callback, skip_graph=skip_graph)
    
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
            
            # Update the main status with the new file progress
            completed_count = sum(1 for f in file_progress if f["status"] == "completed")
            logger.info(f"File progress update: {file_info['filename']} -> {status} ({progress}%) - {completed_count}/{len(file_progress)} completed")
            
            self._update_processing_status(
                processing_id,
                current_status.get("status", "processing"),
                current_status.get("message", "Processing files..."),
                current_status.get("progress", 0),
                current_file=file_info["filename"],
                current_phase=phase,
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
    
    async def ingest_documents(self, data_source: str = None, paths: List[str] = None, skip_graph: bool = False, **kwargs) -> Dict[str, Any]:
        """Start async document ingestion and return processing ID
        
        Args:
            skip_graph: If True, skip knowledge graph extraction for this ingest (temporary, doesn't persist)
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
        asyncio.create_task(self._process_documents_async(processing_id, data_source, paths, skip_graph, **kwargs))
        
        estimated_time = self._estimate_processing_time(data_source, paths)
        
        return {
            "processing_id": processing_id,
            "status": "started", 
            "message": "Document processing has started, please wait...",
            "estimated_time": estimated_time
        }
    
    async def _process_documents_async(self, processing_id: str, data_source: str = None, paths: List[str] = None, skip_graph: bool = False, **kwargs):
        """Background task for document processing"""
        try:
            data_source = data_source or self.settings.data_source
            
            # Log skip_graph flag if set
            if skip_graph:
                logger.info(f"skip_graph=True for processing_id={processing_id} - Knowledge graph extraction will be skipped for this ingest")
            
            # Check for cancellation before starting
            if self._is_processing_cancelled(processing_id):
                return
                
            self._update_processing_status(
                processing_id, 
                "processing", 
                f"Initializing {data_source} document ingestion...", 
                10
            )
            
            if data_source == "filesystem":
                file_paths = paths or self.settings.source_paths
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
                    20,
                    total_files=len(cleaned_paths),
                    files_completed=0,
                    file_progress=file_progress
                )
                if self._is_processing_cancelled(processing_id):
                    return
                self._update_processing_status(
                    processing_id,
                    "processing",
                    "Scanning filesystem paths...",
                    40,
                    total_files=len(cleaned_paths),
                    files_completed=0,
                    file_progress=file_progress
                )
                if self._is_processing_cancelled(processing_id):
                    return
                self._update_processing_status(
                    processing_id,
                    "processing",
                    "Processing filesystem documents...",
                    60,
                    total_files=len(cleaned_paths),
                    files_completed=0,
                    file_progress=file_progress
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
                        for i in range(len(file_progress)):
                            self._update_file_progress(
                                processing_id, 
                                i, 
                                status="completed", 
                                progress=100,
                                phase="completed",
                                message="Processing completed"
                            )
                    # Handle loading progress - update individual file progress
                    elif files_completed > 0 and files_completed <= len(file_progress):
                        file_index = files_completed - 1  # Convert to 0-based index
                        self._update_file_progress(
                            processing_id, 
                            file_index, 
                            status="processing", 
                            progress=min(progress, 90),  # Don't complete during loading
                            phase="loading",
                            message=f"Loading {current_file}" if current_file else "Loading..."
                        )
                    
                    # Add the individual_files data to the callback
                    cb_kwargs["file_progress"] = file_progress
                    self._update_processing_status(**cb_kwargs)
                
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
                        progress=90,  # Loaded but not processed
                        phase="loaded",
                        message="Documents loaded, starting pipeline processing..."
                    )
                
                await self.system._process_documents_direct(documents, processing_id=processing_id, status_callback=filesystem_status_callback, skip_graph=skip_graph)
                
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
                await self.system._process_documents_direct(documents, processing_id=processing_id, status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs), skip_graph=skip_graph)
                
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
                        "username": os.getenv("ALFRESCO_USERNAME", "admin"),
                        "password": os.getenv("ALFRESCO_PASSWORD", "admin"),
                        "path": os.getenv("ALFRESCO_PATH", "/")
                    }
                
                documents = await self.ingestion_manager.ingest_from_source(
                    source_type="alfresco",
                    config=config,
                    processing_id=processing_id,
                    status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs)
                )
                await self.system._process_documents_direct(documents, processing_id=processing_id, status_callback=lambda **cb_kwargs: self._update_processing_status(**cb_kwargs), skip_graph=skip_graph)
                
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
                await self.system._process_documents_direct(documents, processing_id=processing_id, status_callback=web_status_callback, skip_graph=skip_graph)
                
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
                await self.system._process_documents_direct(documents, processing_id=processing_id, status_callback=youtube_status_callback, skip_graph=skip_graph)
                
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
                await self.system._process_documents_direct(documents, processing_id=processing_id, status_callback=wikipedia_status_callback, skip_graph=skip_graph)
                
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
                await self.system._process_documents_direct(documents, processing_id=processing_id, status_callback=s3_status_callback, skip_graph=skip_graph)
                
            elif data_source == "gcs":
                gcs_config = kwargs.get('gcs_config', {})
                bucket_name = gcs_config.get('bucket_name', 'GCS Bucket')
                await self._process_modular_data_source(
                    processing_id=processing_id,
                    data_source="gcs",
                    config_key="gcs_config",
                    display_name=bucket_name,
                    connect_message="Connecting to Google Cloud Storage...",
                    process_message="Processing GCS documents...",
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
            results = await self.system.search(query, top_k=top_k)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"Search query completed in {duration:.3f}s - Returning {len(results)} final results (post-deduplication)")
            
            return {"success": True, "results": results, "query_time": f"{duration:.3f}s"}
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.error(f"Search query failed after {duration:.3f}s: {str(e)}")
            return {"success": False, "error": str(e), "query_time": f"{duration:.3f}s"}
    
    async def qa_query(self, query: str) -> Dict[str, Any]:
        """Answer a question using the Q&A system"""
        start_time = datetime.now()
        logger.info(f"Q&A query started at {start_time.strftime('%H:%M:%S.%f')[:-3]} - Query: '{query}'")
        
        try:
            query_engine = self.system.get_query_engine()
            
            # Use async method directly (nest_asyncio.apply() called at module level)
            response = await query_engine.aquery(query)
            
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
            logger.error(f"Q&A query failed after {duration:.3f}s: {str(e)}")
            return {"success": False, "error": str(e), "query_time": f"{duration:.3f}s"}
    
    async def query_documents(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """Query documents with AI-generated answers"""
        start_time = datetime.now()
        logger.info(f"Document query started at {start_time.strftime('%H:%M:%S.%f')[:-3]} - Query: '{query}'")
        
        try:
            query_engine = self.system.get_query_engine()
            
            # Use async method directly (nest_asyncio.apply() called at module level)
            response = await query_engine.aquery(query)
            
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
    
    async def ingest_text(self, content: str, source_name: str = "text_input") -> Dict[str, Any]:
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
        asyncio.create_task(self._process_text_async(processing_id, content, source_name))
        
        estimated_time = self._estimate_processing_time(content=content)
        
        return {
            "processing_id": processing_id,
            "status": "started", 
            "message": "Text processing has started, please wait...",
            "estimated_time": estimated_time
        }
    
    async def _process_text_async(self, processing_id: str, content: str, source_name: str):
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
            await self.system.ingest_text(content=content, source_name=source_name, processing_id=processing_id)
            
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
                logger.error(f"Runtime error in text processing {processing_id}: {str(e)}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"Processing failed: {str(e)}", 
                    0
                )
        except Exception as e:
            logger.error(f"Error ingesting text {processing_id}: {str(e)}")
            self._update_processing_status(
                processing_id, 
                "failed", 
                f"Processing failed: {str(e)}", 
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
                        "graph_db": self.settings.graph_db,
                        "search_db": self.settings.search_db,
                        "llm_provider": self.settings.llm_provider
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
                "graph_db": self.settings.graph_db,
                "llm_provider": self.settings.llm_provider
            }
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Health check"""
        return {"success": True, "status": "ok"}
    
    def _generate_completion_message(self, doc_count: int) -> str:
        """Generate dynamic completion message based on enabled features"""
        # Check what's actually enabled
        has_vector = str(self.settings.vector_db) != "none"
        has_graph = str(self.settings.graph_db) != "none" and self.settings.enable_knowledge_graph
        has_search = str(self.settings.search_db) != "none"
        
        # Build feature list
        features = []
        if has_vector:
            features.append("vector index")
        if has_graph:
            features.append("knowledge graph")
        if has_search:
            if self.settings.search_db == "bm25":
                features.append("BM25 search")
            else:
                features.append(f"{self.settings.search_db} search")
        
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