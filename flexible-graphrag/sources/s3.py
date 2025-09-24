"""
Amazon S3 data source for Flexible GraphRAG using LlamaIndex S3Reader.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class S3Source(BaseDataSource):
    """Data source for Amazon S3 buckets using LlamaIndex S3Reader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.bucket_name = config.get("bucket_name", "")  # Modern field name
        self.prefix = config.get("prefix", "")  # Optional: folder prefix
        # Support both new and legacy credential field names
        self.aws_access_key_id = config.get("access_key") or config.get("aws_access_key_id")
        self.aws_secret_access_key = config.get("secret_key") or config.get("aws_secret_access_key")
        self.aws_session_token = config.get("aws_session_token")
        self.region_name = config.get("region_name", "us-east-1")
        
        # Import LlamaIndex S3 reader
        try:
            from llama_index.readers.s3 import S3Reader
            
            # Initialize S3Reader with credentials if provided
            if self.aws_access_key_id and self.aws_secret_access_key:
                self.reader = S3Reader(
                    bucket=self.bucket_name,  # Use modern bucket_name
                    key=self.prefix,  # Use prefix as key
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key,
                    aws_session_token=self.aws_session_token,
                    region_name=self.region_name
                )
            else:
                # Use default AWS credentials (from environment, IAM role, etc.)
                self.reader = S3Reader(
                    bucket=self.bucket_name,  # Use modern bucket_name
                    key=self.prefix,  # Use prefix as key
                    region_name=self.region_name
                )
            
            logger.info(f"S3Source initialized for bucket: {self.bucket_name}")
        except ImportError as e:
            logger.error(f"Failed to import S3Reader: {e}")
            raise ImportError("Please install llama-index-readers-s3: pip install llama-index-readers-s3")
    
    def validate_config(self) -> bool:
        """Validate the S3 source configuration."""
        if not self.bucket_name:
            logger.error("No bucket_name specified for S3 source")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Amazon S3.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from S3 bucket: {self.bucket_name}")
            if self.prefix:
                logger.info(f"Using prefix: {self.prefix}")
            
            # Use S3Reader to load documents
            documents = self.reader.load_data()
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "s3",
                    "bucket_name": self.bucket_name,
                    "prefix": self.prefix,
                    "region": self.region_name,
                    "source_type": "s3_object"
                })
            
            logger.info(f"S3Source loaded {len(documents)} documents from bucket: {self.bucket_name}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from S3 bucket '{self.bucket_name}': {str(e)}")
            raise
    
    def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Amazon S3 with detailed progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from S3 bucket: {self.bucket} with progress tracking")
            if self.key:
                logger.info(f"Using key/prefix: {self.key}")
            
            # First, try to get file list for progress tracking
            if progress_callback:
                progress_callback(0, 1, "Scanning S3 bucket for files...")
            
            try:
                # Try to get file listing using boto3 directly for progress
                import boto3
                from botocore.exceptions import ClientError
                
                # Create S3 client with same credentials as reader
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key,
                    aws_session_token=self.aws_session_token,
                    region_name=self.region_name
                )
                
                # List objects to get file count
                paginator = s3_client.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(
                    Bucket=self.bucket_name,
                    Prefix=self.prefix if self.prefix else ''
                )
                
                file_list = []
                for page in page_iterator:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            # Filter for supported file types
                            key = obj['Key']
                            if any(key.lower().endswith(ext) for ext in ['.pdf', '.txt', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.md', '.html', '.csv']):
                                file_list.append({
                                    'key': key,
                                    'size': obj['Size'],
                                    'modified': obj['LastModified']
                                })
                
                total_files = len(file_list)
                logger.info(f"Found {total_files} supported files in S3 bucket")
                
                if progress_callback:
                    progress_callback(0, total_files, f"Found {total_files} files, starting download...")
                
                # Use S3Reader to load documents (it handles the actual downloading)
                documents = self.reader.load_data()
                
                # Simulate progress during processing
                if progress_callback and total_files > 0:
                    for i, doc in enumerate(documents, 1):
                        # Try to extract filename from document metadata
                        filename = doc.metadata.get('file_name', doc.metadata.get('source', f'document_{i}'))
                        progress_callback(i, len(documents), f"Processing document", filename)
                
            except (ImportError, ClientError) as e:
                logger.warning(f"Could not get detailed S3 file listing: {e}. Using fallback progress.")
                # Fallback to simple progress
                if progress_callback:
                    progress_callback(0, 1, "Loading S3 documents...")
                
                documents = self.reader.load_data()
                
                if progress_callback:
                    progress_callback(1, 1, f"Loaded {len(documents)} documents")
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "s3",
                    "bucket_name": self.bucket_name,
                    "prefix": self.prefix,
                    "region": self.region_name,
                    "source_type": "s3_object"
                })
            
            logger.info(f"S3Source loaded {len(documents)} documents from bucket: {self.bucket_name}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from S3 bucket '{self.bucket_name}': {str(e)}")
            raise
