"""
Google Cloud Storage data source for Flexible GraphRAG.
Uses GCSReader with passthrough extractor to download files, then DocumentProcessor for parsing.
"""

from typing import List, Dict, Any, Optional
import logging
import os
from llama_index.core import Document

from .base import BaseDataSource
from .passthrough_extractor import PassthroughExtractor

logger = logging.getLogger(__name__)


class GCSSource(BaseDataSource):
    """Data source for Google Cloud Storage - uses GCSReader with passthrough + DocumentProcessor"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Get configuration
        self.bucket = config.get("bucket_name", "") or config.get("bucket", "")
        self.prefix = config.get("prefix", "") or config.get("key", "")
        self.project_id = config.get("project_id")
        self.service_account_key_path = config.get("service_account_key_path")
        
        # Handle service account key JSON from UI form
        credentials_str = config.get("credentials", "")
        self.service_account_key = None
        
        if credentials_str:
            try:
                # Parse JSON credentials from UI form
                import json
                self.service_account_key = json.loads(credentials_str)
                logger.info("Parsed GCS service account credentials from JSON string")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in GCS credentials: {e}")
                raise ValueError("Invalid JSON format in GCS service account credentials")
        
        logger.info(f"GCSSource initialized for bucket: {self.bucket}, prefix: '{self.prefix}'")
    
    def validate_config(self) -> bool:
        """Validate the GCS source configuration."""
        if not self.bucket:
            logger.error("No bucket specified for GCS source")
            return False
        return True
    
    def _create_gcs_reader(self, progress_callback=None):
        """Create GCSReader with passthrough extractors"""
        try:
            from llama_index.readers.gcs import GCSReader
        except ImportError:
            logger.error("Failed to import GCSReader")
            raise ImportError("Please install llama-index-readers-gcs: pip install llama-index-readers-gcs")
        
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
        
        # Initialize GCSReader with credentials and passthrough extractors
        reader_kwargs = {
            "bucket": self.bucket,
            "file_extractor": file_extractor,
            "recursive": False,  # Don't recursively descend into subdirectories
        }
        
        # Use 'prefix' parameter (not 'key') to filter objects in the bucket
        if self.prefix:
            reader_kwargs["prefix"] = self.prefix
        
        if self.service_account_key:
            # GCSReader expects service_account_key as dict (already parsed from JSON in __init__)
            reader_kwargs["service_account_key"] = self.service_account_key
        elif self.service_account_key_path:
            reader_kwargs["service_account_key_path"] = self.service_account_key_path
        
        logger.info(f"Initializing GCSReader with bucket={self.bucket}, prefix={self.prefix or '(root)'}, recursive=False, has_credentials={bool(self.service_account_key)}")
        reader = GCSReader(**reader_kwargs)
        
        return reader, passthrough
    
    def get_documents(self) -> List[Document]:
        """Load files via GCSReader (with passthrough), then process with DocumentProcessor"""
        try:
            logger.info(f"Loading documents from GCS bucket: {self.bucket}")
            
            # Create reader
            reader, _ = self._create_gcs_reader()
            
            # Use GCSReader to discover and capture files (returns placeholder Documents)
            placeholder_docs = reader.load_data()
            
            if not placeholder_docs:
                logger.warning("No files found in GCS bucket")
                return []
            
            logger.info(f"Found {len(placeholder_docs)} files in GCS bucket")
            
            # Process with DocumentProcessor (downloads from GCS and parses)
            doc_processor = self._get_document_processor()
            
            import asyncio
            documents = asyncio.run(doc_processor.process_documents_from_metadata(placeholder_docs))
            
            # Add GCS metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "gcs",
                    "bucket": self.bucket,
                    "prefix": self.prefix,
                    "project_id": self.project_id,
                    "source_type": "gcs_object"
                })
            
            logger.info(f"GCSSource processed {len(documents)} documents from {len(placeholder_docs)} placeholders")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from GCS bucket '{self.bucket}': {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Google Cloud Storage with detailed progress tracking.
        
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
                    message="Connecting to GCS bucket...",
                    current_file=""
                )
            
            logger.info(f"Loading documents from GCS bucket: {self.bucket} with progress tracking")
            
            # Create reader with progress callback
            try:
                reader, passthrough = self._create_gcs_reader(progress_callback=progress_callback)
                logger.info("GCSReader created successfully")
            except Exception as e:
                logger.error(f"Failed to create GCSReader: {str(e)}", exc_info=True)
                raise
            
            # Use GCSReader to discover files and report download progress
            try:
                logger.info(f"Calling GCSReader.load_data() for bucket: {self.bucket}")
                placeholder_docs = reader.load_data()
                logger.info(f"GCSReader.load_data() returned {len(placeholder_docs) if placeholder_docs else 0} documents")
            except Exception as e:
                logger.error(f"Error loading data from GCS: {str(e)}", exc_info=True)
                raise
            
            if not placeholder_docs:
                if progress_callback:
                    progress_callback(1, 1, "No documents found in GCS bucket", "")
                return []
            
            logger.info(f"Found {len(placeholder_docs)} files in GCS bucket")
            
            # Report processing phase
            if progress_callback:
                bucket_display = f"gs://{self.bucket}"
                if self.prefix:
                    bucket_display += f"/{self.prefix}"
                progress_callback(
                    current=len(placeholder_docs),
                    total=len(placeholder_docs),
                    message=f"Processing {len(placeholder_docs)} files with {get_parser_type_from_env()}...",
                    current_file=bucket_display
                )
            
            # Process with DocumentProcessor (downloads from GCS and parses)
            parser_type = get_parser_type_from_env()
            doc_processor = DocumentProcessor(parser_type=parser_type)
            
            documents = await doc_processor.process_documents_from_metadata(placeholder_docs)
            
            # Add GCS metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "gcs",
                    "bucket": self.bucket,
                    "prefix": self.prefix,
                    "project_id": self.project_id,
                    "source_type": "gcs_object"
                })
            
            if progress_callback:
                progress_callback(
                    current=len(placeholder_docs),
                    total=len(placeholder_docs),
                    message=f"Completed processing {len(placeholder_docs)} files",
                    current_file=bucket_display
                )
            
            logger.info(f"GCSSource processed {len(placeholder_docs)} files ({len(documents)} chunks)")
            return (len(placeholder_docs), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error loading documents from GCS bucket '{self.bucket}': {str(e)}")
            raise
