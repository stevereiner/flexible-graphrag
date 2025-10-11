"""
Amazon S3 data source for Flexible GraphRAG.
Uses S3 filesystem interface to download files and DocumentProcessor for Docling processing.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource
from .filesystem import is_docling_supported

logger = logging.getLogger(__name__)


class S3Source(BaseDataSource):
    """Data source for Amazon S3 buckets - uses s3fs for file access and DocumentProcessor for Docling"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        import os
        
        # Get configuration from UI config or environment variables
        self.bucket_name = config.get("bucket_name", os.getenv("S3_BUCKET_NAME", ""))
        self.prefix = config.get("prefix", os.getenv("S3_PREFIX", ""))  # Optional: folder prefix
        
        # Clean up prefix - ensure it doesn't contain the bucket name
        if self.prefix == self.bucket_name:
            logger.warning(f"Prefix '{self.prefix}' matches bucket name - clearing prefix to scan entire bucket")
            self.prefix = ""
        
        # Support both new and legacy credential field names (no session token needed)
        # Priority: UI config > environment variables > None (use IAM role/default credentials)
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
        self.region_name = config.get("region_name", os.getenv("S3_REGION_NAME", "us-east-2"))
        
        # Import s3fs for filesystem-like S3 access
        try:
            import s3fs
            
            # Initialize s3fs filesystem
            if self.aws_access_key_id and self.aws_secret_access_key:
                self.s3 = s3fs.S3FileSystem(
                    key=self.aws_access_key_id,
                    secret=self.aws_secret_access_key,
                    client_kwargs={'region_name': self.region_name}
                )
            else:
                # Use default AWS credentials (from environment, IAM role, etc.)
                self.s3 = s3fs.S3FileSystem(
                    anon=False,
                    client_kwargs={'region_name': self.region_name}
                )
            
            logger.info(f"S3Source initialized with s3fs for bucket: {self.bucket_name}, prefix: '{self.prefix}'")
        except ImportError as e:
            logger.error(f"Failed to import s3fs: {e}")
            raise ImportError("Please install s3fs: pip install s3fs boto3")
    
    def validate_config(self) -> bool:
        """Validate the S3 source configuration."""
        if not self.bucket_name:
            logger.error("No bucket_name specified for S3 source")
            return False
        
        return True
    
    def list_files(self) -> List[dict]:
        """List all supported files from the S3 bucket with the given prefix"""
        files = []
        
        try:
            # Construct S3 path
            if self.prefix:
                s3_path = f"{self.bucket_name}/{self.prefix}"
            else:
                s3_path = self.bucket_name
            
            # List all files recursively
            all_files = self.s3.ls(s3_path, detail=True)
            
            for file_info in all_files:
                # Skip directories
                if file_info['type'] != 'file':
                    continue
                
                s3_key = file_info['name']  # Full S3 path like 'bucket/path/file.pdf'
                filename = s3_key.split('/')[-1]
                
                # Check if file type is supported by Docling
                if is_docling_supported('', filename):
                    files.append({
                        'key': s3_key,
                        'filename': filename,
                        'size': file_info['size']
                    })
                    logger.info(f"Found supported S3 file: {s3_key}")
                else:
                    logger.info(f"Skipping unsupported S3 file: {s3_key}")
            
            logger.info(f"S3Source found {len(files)} supported files in bucket: {self.bucket_name}")
            return files
            
        except Exception as e:
            logger.error(f"Error listing S3 files: {e}")
            raise
    
    def get_documents(self) -> List[Document]:
        """
        Get documents from S3 by downloading and processing them with DocumentProcessor.
        """
        import tempfile
        import os
        from document_processor import DocumentProcessor
        
        files = self.list_files()
        documents = []
        
        # Create temporary directory for downloads
        temp_dir = tempfile.mkdtemp(prefix="s3_download_")
        
        try:
            # Initialize document processor
            doc_processor = DocumentProcessor()
            
            for file_info in files:
                try:
                    # Download file to temporary location
                    temp_file_path = os.path.join(temp_dir, file_info['filename'])
                    
                    logger.info(f"Downloading S3 file: {file_info['key']}")
                    self.s3.get(file_info['key'], temp_file_path)
                    
                    # Process the downloaded file with DocumentProcessor
                    import asyncio
                    processed_docs = asyncio.run(doc_processor.process_documents([temp_file_path]))
                    
                    if processed_docs:
                        processed_doc = processed_docs[0]
                        
                        # Update metadata to include S3 information
                        processed_doc.metadata.update({
                            "source": "s3",
                            "bucket_name": self.bucket_name,
                            "s3_key": file_info['key'],
                            "file_name": file_info['filename'],
                            "file_path": file_info['key'],
                            "region": self.region_name
                        })
                        
                        documents.append(processed_doc)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        
                except Exception as e:
                    logger.error(f"Error processing S3 file {file_info['filename']}: {str(e)}")
                    continue
                    
        finally:
            # Clean up temporary directory
            try:
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
        
        return documents
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Amazon S3 with progress tracking.
        Downloads files using s3fs and processes them with DocumentProcessor.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        import tempfile
        import os
        from document_processor import DocumentProcessor
        
        try:
            if progress_callback:
                progress_callback(
                    current=0,
                    total=1,
                    message="Connecting to S3 bucket...",
                    current_file=""
                )
            
            # Get file list
            files = self.list_files()
            documents = []
            
            if not files:
                if progress_callback:
                    progress_callback(1, 1, "No documents found in S3 bucket")
                return documents
            
            logger.info(f"Found {len(files)} files in S3 bucket: {self.bucket_name}")
            
            # Report single entry for bucket (not individual files)
            bucket_display = f"s3://{self.bucket_name}"
            if self.prefix:
                bucket_display += f"/{self.prefix}"
            
            # Create temporary directory for downloads
            temp_dir = tempfile.mkdtemp(prefix="s3_download_")
            
            try:
                # Initialize document processor
                doc_processor = DocumentProcessor()
                
                # Process each file with progress updates (aggregate progress for bucket)
                for i, file_info in enumerate(files):
                    try:
                        if progress_callback:
                            # Report aggregate progress for the bucket, not individual files
                            progress_callback(
                                current=1,  # Always 1 (single bucket entry)
                                total=1,    # Always 1 (single bucket entry)
                                message=f"Processing {i+1}/{len(files)} files from bucket: {file_info['filename']}",
                                current_file=bucket_display  # Show bucket path as "filename"
                            )
                        
                        # Download file to temporary location
                        temp_file_path = os.path.join(temp_dir, file_info['filename'])
                        
                        logger.info(f"Downloading S3 file: {file_info['key']}")
                        self.s3.get(file_info['key'], temp_file_path)
                        
                        # Process the downloaded file with DocumentProcessor
                        processed_docs = await doc_processor.process_documents([temp_file_path])
                        
                        if processed_docs:
                            processed_doc = processed_docs[0]
                            
                            # Update metadata to include S3 information (simple primitives only)
                            processed_doc.metadata.update({
                                "source": "s3",
                                "bucket_name": self.bucket_name,
                                "s3_key": file_info['key'],
                                "file_name": file_info['filename'],
                                "file_path": file_info['key'],
                                "region": self.region_name
                            })
                            
                            documents.append(processed_doc)
                        
                        # Clean up temporary file
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                            
                    except Exception as e:
                        logger.error(f"Error processing S3 file {file_info['filename']}: {str(e)}")
                        continue
                        
            finally:
                # Clean up temporary directory
                try:
                    if os.path.exists(temp_dir):
                        os.rmdir(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
            
            logger.info(f"S3Source processed {len(documents)} documents from {len(files)} files")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from S3 bucket '{self.bucket_name}': {str(e)}")
            raise
