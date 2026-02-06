"""
Google Drive data source for Flexible GraphRAG.
Uses GoogleDriveReader with passthrough extractor to download files, then DocumentProcessor for parsing.
"""

from typing import List, Dict, Any, Optional
import logging
import os
from llama_index.core import Document

from .base import BaseDataSource
from .passthrough_extractor import PassthroughExtractor

logger = logging.getLogger(__name__)


class GoogleDriveSource(BaseDataSource):
    """Data source for Google Drive - uses GoogleDriveReader with passthrough + DocumentProcessor"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Get configuration
        self.folder_id = config.get("folder_id", "")  # Optional: specific folder ID
        self.file_ids = config.get("file_ids", [])  # Optional: specific file IDs
        self.query = config.get("query", "")  # Optional: search query
        
        # Handle credentials from UI form (JSON string)
        credentials_str = config.get("credentials", "")
        self.service_account_key = None
        
        if credentials_str:
            try:
                # Parse JSON credentials from UI form
                import json
                self.service_account_key = json.loads(credentials_str)
                logger.info("Parsed service account credentials from JSON string")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in credentials: {e}")
                raise ValueError("Invalid JSON format in service account credentials")
        
        # Fallback to file-based credentials
        self.credentials_path = config.get("credentials_path", "")
        self.token_path = config.get("token_path", "")
        
        logger.info("GoogleDriveSource initialized successfully")
    
    def validate_config(self) -> bool:
        """Validate the Google Drive source configuration."""
        # Check authentication
        if not self.service_account_key and not self.credentials_path:
            logger.error("Google Drive authentication required: provide service account credentials or credentials file path")
            return False
        
        # At least one of folder_id, file_ids, or query should be specified
        # If none specified, will load from root folder (which is valid)
        
        return True
    
    def _create_google_drive_reader(self, progress_callback=None):
        """Create GoogleDriveReader with passthrough extractors"""
        try:
            from llama_index.readers.google import GoogleDriveReader
        except ImportError:
            logger.error("Failed to import GoogleDriveReader")
            raise ImportError("Please install llama-index-readers-google: pip install llama-index-readers-google")
        
        # Create passthrough extractor with progress tracking
        passthrough = PassthroughExtractor(progress_callback=progress_callback)
        
        # Map all supported file types to passthrough extractor
        file_extractor = {
            ".pdf": passthrough,
            ".docx": passthrough,
            ".pptx": passthrough,
            ".xlsx": passthrough,
            ".doc": passthrough,
            ".ppt": passthrough,
            ".xls": passthrough,
            ".txt": passthrough,
            ".md": passthrough,
            ".html": passthrough,
            ".csv": passthrough,
            ".png": passthrough,
            ".jpg": passthrough,
            ".jpeg": passthrough,
        }
        
        # Initialize GoogleDriveReader with credentials and passthrough extractors
        reader_kwargs = {
            "file_extractor": file_extractor,
        }
        
        if self.service_account_key:
            # Pass service account key as dict
            reader_kwargs["service_account_key"] = self.service_account_key
        elif self.credentials_path:
            reader_kwargs["credentials_path"] = self.credentials_path
        
        if self.token_path:
            reader_kwargs["token_path"] = self.token_path
        
        reader = GoogleDriveReader(**reader_kwargs)
        
        return reader, passthrough
    
    def get_documents(self) -> List[Document]:
        """Load files via GoogleDriveReader (with passthrough), then process with DocumentProcessor"""
        from document_processor import DocumentProcessor, get_parser_type_from_env
        
        try:
            logger.info("Loading documents from Google Drive")
            
            # Create reader
            reader, _ = self._create_google_drive_reader()
            
            # Build load_data arguments based on configuration
            load_kwargs = {}
            if self.folder_id:
                load_kwargs["folder_id"] = self.folder_id
            if self.file_ids:
                load_kwargs["file_ids"] = self.file_ids
            if self.query:
                load_kwargs["query"] = self.query
            
            # Use GoogleDriveReader to discover and capture files (returns placeholder Documents)
            placeholder_docs = reader.load_data(**load_kwargs)
            
            if not placeholder_docs:
                logger.warning("No files found in Google Drive")
                return []
            
            logger.info(f"Found {len(placeholder_docs)} files in Google Drive")
            
            # Process with DocumentProcessor (downloads from Google Drive and parses)
            parser_type = get_parser_type_from_env()
            doc_processor = DocumentProcessor(parser_type=parser_type)
            
            import asyncio
            documents = asyncio.run(doc_processor.process_documents_from_metadata(placeholder_docs))
            
            # Add Google Drive metadata
            for doc in documents:
                # Preserve existing metadata (including 'file id') and add new fields
                doc.metadata["source"] = "google_drive"
                doc.metadata["folder_id"] = self.folder_id
                doc.metadata["query"] = self.query
                doc.metadata["source_type"] = "google_drive_file"
            
            logger.info(f"GoogleDriveSource processed {len(documents)} documents from {len(placeholder_docs)} placeholders")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Google Drive: {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Google Drive with progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        from document_processor import DocumentProcessor, get_parser_type_from_env
        
        try:
            if progress_callback:
                progress_callback(
                    current=0,
                    total=1,
                    message="Connecting to Google Drive...",
                    current_file=""
                )
            
            logger.info("Loading documents from Google Drive with progress tracking")
            
            # Get DocumentProcessor for immediate processing
            parser_type = get_parser_type_from_env()
            doc_processor = DocumentProcessor(parser_type=parser_type)
            
            # Create passthrough extractor with BOTH progress callback AND doc_processor
            # This allows PassthroughExtractor to process files immediately as they're downloaded
            passthrough = PassthroughExtractor(
                progress_callback=progress_callback,
                doc_processor=doc_processor  # Process files immediately!
            )
            
            # Map all supported file types to passthrough extractor
            file_extractor = {
                ".pdf": passthrough,
                ".docx": passthrough,
                ".pptx": passthrough,
                ".xlsx": passthrough,
                ".doc": passthrough,
                ".ppt": passthrough,
                ".xls": passthrough,
                ".txt": passthrough,
                ".md": passthrough,
                ".html": passthrough,
                ".csv": passthrough,
                ".png": passthrough,
                ".jpg": passthrough,
                ".jpeg": passthrough,
            }
            
            # Initialize GoogleDriveReader with credentials and passthrough extractors
            try:
                from llama_index.readers.google import GoogleDriveReader
            except ImportError:
                logger.error("Failed to import GoogleDriveReader")
                raise ImportError("Please install llama-index-readers-google: pip install llama-index-readers-google")
            
            reader_kwargs = {
                "file_extractor": file_extractor,
            }
            
            if self.service_account_key:
                # Pass service account key as dict
                reader_kwargs["service_account_key"] = self.service_account_key
            elif self.credentials_path:
                reader_kwargs["credentials_path"] = self.credentials_path
            
            if self.token_path:
                reader_kwargs["token_path"] = self.token_path
            
            reader = GoogleDriveReader(**reader_kwargs)
            
            # Build load_data arguments based on configuration
            load_kwargs = {}
            if self.folder_id:
                load_kwargs["folder_id"] = self.folder_id
            if self.file_ids:
                load_kwargs["file_ids"] = self.file_ids
            if self.query:
                load_kwargs["query"] = self.query
            
            # Use GoogleDriveReader to load and process documents
            # PassthroughExtractor will process each file immediately and return processed docs
            documents = reader.load_data(**load_kwargs)
            
            if not documents:
                if progress_callback:
                    progress_callback(1, 1, "No documents found in Google Drive", "")
                return []
            
            logger.info(f"Found {len(documents)} files in Google Drive")
            
            # Add Google Drive metadata to processed documents (preserve existing metadata like 'file id')
            for doc in documents:
                # Preserve all existing metadata and add new fields
                # Don't use update() as it might overwrite; instead add fields individually
                doc.metadata["source"] = "google_drive"
                doc.metadata["folder_id"] = self.folder_id
                doc.metadata["query"] = self.query
                doc.metadata["source_type"] = "google_drive_file"
            
            if progress_callback:
                gdrive_display = "Google Drive"
                if self.folder_id:
                    gdrive_display += f" (folder)"
                elif self.query:
                    gdrive_display += f" (search)"
                progress_callback(
                    current=len(documents),
                    total=len(documents),
                    message=f"Completed processing {len(documents)} files",
                    current_file=gdrive_display
                )
            
            logger.info(f"GoogleDriveSource processed {len(documents)} files")
            return (len(documents), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error loading documents from Google Drive: {str(e)}")
            raise
