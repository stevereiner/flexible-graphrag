"""
Amazon S3 data source for Flexible GraphRAG.
Uses S3Reader with passthrough extractor to download files, then DocumentProcessor for parsing.
"""

from typing import List, Dict, Any, Optional
import logging
import os
from llama_index.core import Document

from .base import BaseDataSource
from .passthrough_extractor import PassthroughExtractor

logger = logging.getLogger(__name__)


class S3Source(BaseDataSource):
    """Data source for Amazon S3 - uses S3Reader with passthrough + DocumentProcessor"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Log the raw config for debugging
        logger.debug(f"S3Source received config: {config}")
        
        # Get configuration from UI config or environment variables
        # Support both "bucket_name" (standard) and "bucket" (S3Reader compatible) for flexibility
        self.bucket_name = (
            config.get("bucket_name") or 
            config.get("bucket") or 
            os.getenv("S3_BUCKET_NAME", "")
        )
        
        # Handle prefix - filter out string "None" and actual None
        prefix_value = config.get("prefix", os.getenv("S3_PREFIX", ""))
        if prefix_value in [None, "None", "null"]:
            self.prefix = ""
        else:
            self.prefix = str(prefix_value) if prefix_value else ""
        
        # Handle region_name - filter out None values
        region_value = config.get("region_name") or os.getenv("S3_REGION_NAME")
        if region_value in [None, "None", "null"]:
            self.region_name = "us-east-1"  # Use default
        else:
            self.region_name = str(region_value)
        
        # Clean up prefix - ensure it doesn't contain the bucket name
        if self.prefix == self.bucket_name:
            logger.warning(f"Prefix '{self.prefix}' matches bucket name - clearing prefix")
            self.prefix = ""
        
        # Support both new and legacy credential field names
        self.aws_access_key_id = (
            config.get("access_key") or 
            config.get("aws_access_key_id") or 
            os.getenv("S3_ACCESS_KEY")
        )
        self.aws_secret_access_key = (
            config.get("secret_key") or 
            config.get("aws_secret_access_key") or 
            os.getenv("S3_SECRET_KEY")
        )
        
        logger.info(f"S3Source initialized for bucket: {self.bucket_name}, prefix: '{self.prefix}', region: {self.region_name}")
    
    def validate_config(self) -> bool:
        """Validate the S3 source configuration."""
        if not self.bucket_name:
            logger.error("No bucket_name specified for S3 source")
            return False
        return True
    
    def _create_s3_reader(self, progress_callback=None):
        """Create S3Reader with passthrough extractors"""
        try:
            from llama_index.readers.s3 import S3Reader
        except ImportError:
            logger.error("Failed to import S3Reader")
            raise ImportError("Please install llama-index-readers-s3: pip install llama-index-readers-s3")
        
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
        
        # Initialize S3Reader with credentials and passthrough extractors
        reader_kwargs = {
            "bucket": self.bucket_name,
            "file_extractor": file_extractor,
        }
        
        if self.prefix:
            reader_kwargs["key"] = self.prefix
        
        if self.aws_access_key_id and self.aws_secret_access_key:
            reader_kwargs["aws_access_id"] = self.aws_access_key_id
            reader_kwargs["aws_access_secret"] = self.aws_secret_access_key
        
        if self.region_name:
            reader_kwargs["region_name"] = self.region_name
        
        reader = S3Reader(**reader_kwargs)
        
        return reader, passthrough
    
    def get_documents(self) -> List[Document]:
        """
        Get documents from S3 using S3Reader for download, DocumentProcessor for parsing.
        """
        try:
            logger.info(f"Loading documents from S3 bucket: {self.bucket_name}")
            
            # Create S3Reader with passthrough extractors
            reader, _ = self._create_s3_reader()
            
            # Use S3Reader - PassthroughExtractor will capture file paths and fs
            placeholder_docs = reader.load_data()
            
            if not placeholder_docs:
                logger.warning("No files found in S3 bucket")
                return []
            
            logger.info(f"S3Reader returned {len(placeholder_docs)} placeholder documents")
            
            # Now process with DocumentProcessor (will handle download + parsing)
            doc_processor = self._get_document_processor()
            
            import asyncio
            documents = asyncio.run(doc_processor.process_documents_from_metadata(placeholder_docs))
            
            # Add S3 metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "s3",
                    "bucket_name": self.bucket_name,
                    "prefix": self.prefix,
                    "region": self.region_name,
                    "source_type": "s3_object"
                })
            
            logger.info(f"S3Source processed {len(documents)} documents from {len(placeholder_docs)} placeholders")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from S3 bucket '{self.bucket_name}': {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Amazon S3 with progress tracking.
        Uses S3Reader for download, DocumentProcessor for parsing.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        from document_processor import get_parser_type_from_env
        
        try:
            if progress_callback:
                progress_callback(
                    current=0,
                    total=1,
                    message="Connecting to S3 bucket...",
                    current_file=""
                )
            
            logger.info(f"Loading documents from S3 bucket: {self.bucket_name} with progress tracking")
            
            # Create S3Reader with progress-enabled passthrough extractor
            reader, passthrough = self._create_s3_reader(progress_callback=progress_callback)
            
            # Try to get file count for progress tracking
            # Temporarily disabled due to region/credential issues
            # try:
            #     import boto3
            #     s3_client = boto3.client(
            #         's3',
            #         aws_access_key_id=self.aws_access_key_id,
            #         aws_secret_access_key=self.aws_secret_access_key,
            #         region_name=self.region_name
            #     )
            #     
            #     # List objects to get file count
            #     paginator = s3_client.get_paginator('list_objects_v2')
            #     pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.prefix or '')
            #     
            #     file_count = 0
            #     for page in pages:
            #         if 'Contents' in page:
            #             file_count += len(page['Contents'])
            #     
            #     # Set total files for progress tracking
            #     passthrough.set_total_files(file_count)
            #     logger.info(f"Found {file_count} files in S3 bucket")
            #     
            # except Exception as e:
            #     logger.warning(f"Could not get S3 file count: {e}. Progress tracking will be limited.")
            
            logger.info("Skipping file count pre-check, will discover files during read")
            
            # Use S3Reader to download files (reports progress via passthrough extractor)
            placeholder_docs = reader.load_data()
            
            if not placeholder_docs:
                if progress_callback:
                    progress_callback(1, 1, "No documents found in S3 bucket")
                return []
            
            logger.info(f"S3Reader returned {len(placeholder_docs)} placeholder documents")
            
            # Report single entry for bucket (not individual files)
            bucket_display = f"s3://{self.bucket_name}"
            if self.prefix:
                bucket_display += f"/{self.prefix}"
            
            if progress_callback:
                progress_callback(
                    current=1,
                    total=1,
                    message=f"Processing {len(placeholder_docs)} files with {get_parser_type_from_env()}...",
                    current_file=bucket_display
                )
            
            # Process with DocumentProcessor (Docling or LlamaParse)
            # Pass the placeholder docs which contain file_path and _fs metadata
            doc_processor = self._get_document_processor()
            
            documents = await doc_processor.process_documents_from_metadata(placeholder_docs)
            
            # Add S3 metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "s3",
                    "bucket_name": self.bucket_name,
                    "prefix": self.prefix,
                    "region": self.region_name,
                    "source_type": "s3_object"
                })
            
            if progress_callback:
                progress_callback(
                    current=1,
                    total=1,
                    message=f"Completed processing {len(placeholder_docs)} files",
                    current_file=bucket_display
                )
            
            logger.info(f"S3Source processed {len(placeholder_docs)} files ({len(documents)} chunks)")
            return (len(placeholder_docs), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error loading documents from S3 bucket '{self.bucket_name}': {str(e)}")
            raise

