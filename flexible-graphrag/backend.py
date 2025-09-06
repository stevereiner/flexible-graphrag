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
from sources import FileSystemSource

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
                    status_callback=completion_callback
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
                )
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
    
    async def ingest_documents(self, data_source: str = None, paths: List[str] = None, **kwargs) -> Dict[str, Any]:
        """Start async document ingestion and return processing ID"""
        processing_id = self._create_processing_id()
        
        # Start processing immediately in background
        self._update_processing_status(
            processing_id, 
            "started", 
            "Complex document processing has started, please wait...", 
            0
        )
        
        # Start background task
        asyncio.create_task(self._process_documents_async(processing_id, data_source, paths, **kwargs))
        
        estimated_time = self._estimate_processing_time(data_source, paths)
        
        return {
            "processing_id": processing_id,
            "status": "started", 
            "message": "Document processing has started, please wait...",
            "estimated_time": estimated_time
        }
    
    async def _process_documents_async(self, processing_id: str, data_source: str = None, paths: List[str] = None, **kwargs):
        """Background task for document processing"""
        try:
            data_source = data_source or self.settings.data_source
            
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
                
                # Initialize per-file progress tracking
                file_progress = self._initialize_file_progress(processing_id, cleaned_paths)
                logger.info(f"Initialized per-file progress for {len(file_progress)} files")
                
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    f"Processing {len(cleaned_paths)} file(s)...", 
                    30,
                    total_files=len(cleaned_paths),
                    files_completed=0,
                    file_progress=file_progress
                )
                
                logger.info(f"Updated status with file_progress: {len(file_progress)} files")
                
                # Check for cancellation before heavy processing
                if self._is_processing_cancelled(processing_id):
                    return
                
                # Process files with per-file progress tracking (batch processing)
                await self._process_files_batch_with_progress(processing_id, cleaned_paths)
                
                # Completion status is now sent by the callback from hybrid_system.py
                # This ensures proper timing after all processing logs are written
                logger.info(f"Batch processing method completed for {len(cleaned_paths)} files")
                
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
                    "Scanning CMIS repository for documents...", 
                    40
                )
                
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Downloading and processing CMIS documents...", 
                    60
                )
                
                cmis_config = kwargs.get('cmis_config')
                if cmis_config:
                    await self.system.ingest_cmis(cmis_config, processing_id=processing_id, status_callback=self._update_processing_status)
                else:
                    await self.system.ingest_cmis(processing_id=processing_id, status_callback=self._update_processing_status)
                    
                self._update_processing_status(
                    processing_id, 
                    "completed", 
                    "Successfully ingested documents from CMIS repository!", 
                    100
                )
                
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
                    "Scanning Alfresco repository for documents...", 
                    40
                )
                
                self._update_processing_status(
                    processing_id, 
                    "processing", 
                    "Downloading and processing Alfresco documents...", 
                    60
                )
                
                alfresco_config = kwargs.get('alfresco_config')
                if alfresco_config:
                    await self.system.ingest_alfresco(alfresco_config, processing_id=processing_id, status_callback=self._update_processing_status)
                else:
                    await self.system.ingest_alfresco(processing_id=processing_id, status_callback=self._update_processing_status)
                    
                self._update_processing_status(
                    processing_id, 
                    "completed", 
                    "Successfully ingested documents from Alfresco repository!", 
                    100
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
                logger.error(f"Runtime error in processing {processing_id}: {str(e)}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"Document processing failed: {str(e)}", 
                    0
                )
        except Exception as e:
            # Handle LLM self-cancellation and timeout errors gracefully
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['timeout', 'timed out', 'request timeout', 'connection timeout']):
                logger.warning(f"LLM timeout in processing {processing_id}: {str(e)}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"Processing timeout - LLM took too long to respond. Try increasing timeout or using smaller documents: {str(e)}", 
                    0
                )
            elif any(keyword in error_str for keyword in ['cancelled', 'aborted', 'interrupted']):
                logger.warning(f"LLM self-cancelled in processing {processing_id}: {str(e)}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"LLM processing was interrupted. This can happen with complex documents: {str(e)}", 
                    0
                )
            else:
                logger.error(f"Error ingesting documents {processing_id}: {str(e)}")
                self._update_processing_status(
                    processing_id, 
                    "failed", 
                    f"Document processing failed: {str(e)}", 
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
            
            # Use async methods as recommended by LlamaIndex error message
            logger.info("Using async query method (aquery) for all LLM providers")
            response = await query_engine.aquery(query)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            answer = str(response)
            logger.info(f"Q&A query completed in {duration:.3f}s - Answer length: {len(answer)} characters")
            
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
            
            # Use async methods as recommended by LlamaIndex error message
            logger.info("Using async query method (aquery) for all LLM providers")
            response = await query_engine.aquery(query)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            answer = str(response)
            logger.info(f"Document query completed in {duration:.3f}s - Answer length: {len(answer)} characters")
            
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