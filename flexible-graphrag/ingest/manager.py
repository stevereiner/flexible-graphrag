"""
Ingestion manager for coordinating data source processing.
"""

from typing import List, Dict, Any, Optional, Callable
import logging
from llama_index.core import Document

from .factory import DataSourceFactory
from sources.base import BaseDataSource

logger = logging.getLogger(__name__)


class IngestionManager:
    """Manager for coordinating data ingestion from various sources."""
    
    def __init__(self):
        self.factory = DataSourceFactory()
    
    async def ingest_from_source(
        self, 
        source_type: str, 
        config: Dict[str, Any],
        processing_id: Optional[str] = None,
        status_callback: Optional[Callable] = None
    ) -> List[Document]:
        """
        Ingest documents from a specific data source with detailed progress tracking.
        
        Args:
            source_type: Type of data source (e.g., "web", "s3", "gcs")
            config: Configuration dictionary for the data source
            processing_id: Optional processing ID for status tracking
            status_callback: Optional callback function for status updates
            
        Returns:
            List[Document]: List of ingested documents
            
        Raises:
            Exception: If ingestion fails
        """
        try:
            # Update status: Starting ingestion
            if status_callback:
                status_callback(
                    processing_id=processing_id,
                    status="processing",
                    message=f"Initializing {source_type} data source...",
                    progress=10
                )
            
            # Create data source
            source = self.factory.create_source(source_type, config)
            
            # Update status: Connected
            if status_callback:
                status_callback(
                    processing_id=processing_id,
                    status="processing",
                    message=f"Connected to {source_type}! Scanning for documents...",
                    progress=20
                )
            
            # Create a progress wrapper for the source
            progress_wrapper = self._create_progress_wrapper(
                source_type, processing_id, status_callback
            )
            
            # Get documents from source with progress tracking
            import asyncio
            loop = asyncio.get_event_loop()
            
            # Pass progress callback to source if it supports it
            if hasattr(source, 'get_documents_with_progress'):
                documents = await source.get_documents_with_progress(progress_wrapper)
            else:
                # Fallback for sources without progress support
                documents = await loop.run_in_executor(None, source.get_documents)
                
                # Simulate progress for sources without built-in progress
                if status_callback:
                    status_callback(
                        processing_id=processing_id,
                        status="processing",
                        message=f"Processing {len(documents)} documents from {source_type}...",
                        progress=70
                    )
            
            # Final status update
            if status_callback:
                # YouTube returns pre-chunked transcript segments, so report as 1 video instead of chunk count
                if source_type == "youtube":
                    doc_count_message = f"Successfully loaded 1 video transcript from {source_type} ({len(documents)} time-based chunks)"
                else:
                    doc_count_message = f"Successfully loaded {len(documents)} documents from {source_type}"
                
                status_callback(
                    processing_id=processing_id,
                    status="processing",
                    message=doc_count_message,
                    progress=90
                )
            
            logger.info(f"Successfully ingested {len(documents)} documents from {source_type}")
            return documents
            
        except Exception as e:
            error_msg = f"Failed to ingest from {source_type}: {str(e)}"
            logger.error(error_msg)
            
            if status_callback:
                status_callback(
                    processing_id=processing_id,
                    status="failed",
                    message=error_msg,
                    progress=0
                )
            
            raise
    
    def _create_progress_wrapper(self, source_type: str, processing_id: Optional[str], status_callback: Optional[Callable]):
        """Create a progress callback wrapper for data sources with individual file tracking."""
        # Track individual files for UI progress bars
        file_progress = []
        initialized = False
        
        def progress_callback(current: int, total: int, message: str = "", current_file: str = ""):
            nonlocal file_progress, initialized
            
            if status_callback:
                # Initialize individual_files array on first call with total > 0
                if not initialized and total > 0:
                    initialized = True
                    file_progress = [
                        {
                            "filename": f"File {i+1}",  # Placeholder, will be updated with actual filename
                            "status": "pending",
                            "progress": 0,
                            "phase": "pending",
                            "message": ""
                        }
                        for i in range(total)
                    ]
                    logger.info(f"Initialized progress tracking for {total} files from {source_type}")
                
                # Calculate progress: 20% (connection) + 70% (loading) = 90% max
                base_progress = 20
                loading_progress = int((current / total) * 70) if total > 0 else 0
                total_progress = min(base_progress + loading_progress, 90)
                
                # Update individual file progress
                if current > 0 and current <= len(file_progress):
                    file_index = current - 1
                    file_progress[file_index] = {
                        "filename": current_file or f"File {current}",
                        "status": "processing",
                        "progress": min(total_progress, 90),  # Don't complete until final phase
                        "phase": "loading",
                        "message": message or f"Processing {current_file}"
                    }
                
                # Create detailed message - prefer the source's message if provided
                if message:
                    detailed_message = f"{message}"
                elif current_file:
                    detailed_message = f"Processing file {current}/{total}: {current_file}"
                else:
                    detailed_message = f"Loading documents from {source_type} ({current}/{total})"
                
                status_callback(
                    processing_id=processing_id,
                    status="processing",
                    message=detailed_message,
                    progress=total_progress,
                    current_file=current_file,
                    current_phase="loading",
                    files_completed=current,
                    total_files=total,
                    file_progress=file_progress  # Include individual file progress
                )
        
        return progress_callback
    
    def get_supported_sources(self) -> List[str]:
        """Get list of supported data source types."""
        return self.factory.get_supported_types()
    
    def is_source_supported(self, source_type: str) -> bool:
        """Check if a data source type is supported."""
        return self.factory.is_supported(source_type)
    
    def validate_source_config(self, source_type: str, config: Dict[str, Any]) -> bool:
        """
        Validate configuration for a specific data source type.
        
        Args:
            source_type: Type of data source
            config: Configuration dictionary
            
        Returns:
            bool: True if configuration is valid, False otherwise
        """
        try:
            source = self.factory.create_source(source_type, config)
            return source.validate_config()
        except Exception as e:
            logger.error(f"Configuration validation failed for {source_type}: {str(e)}")
            return False
