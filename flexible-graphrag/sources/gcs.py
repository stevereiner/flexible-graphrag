"""
Google Cloud Storage data source for Flexible GraphRAG using LlamaIndex GCSReader.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class GCSSource(BaseDataSource):
    """Data source for Google Cloud Storage using LlamaIndex GCSReader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.bucket = config.get("bucket", "")
        self.key = config.get("key", "")  # Optional: specific key/prefix
        self.project_id = config.get("project_id")
        self.service_account_key_path = config.get("service_account_key_path")
        
        # Import LlamaIndex GCS reader
        try:
            from llama_index.readers.gcs import GCSReader
            
            # Initialize GCSReader
            if self.service_account_key_path:
                self.reader = GCSReader(
                    bucket=self.bucket,
                    key=self.key,
                    service_account_key_path=self.service_account_key_path
                )
            else:
                # Use default credentials (from environment, service account, etc.)
                self.reader = GCSReader(
                    bucket=self.bucket,
                    key=self.key
                )
            
            logger.info(f"GCSSource initialized for bucket: {self.bucket}")
        except ImportError as e:
            logger.error(f"Failed to import GCSReader: {e}")
            raise ImportError("Please install llama-index-readers-gcs: pip install llama-index-readers-gcs")
    
    def validate_config(self) -> bool:
        """Validate the GCS source configuration."""
        if not self.bucket:
            logger.error("No bucket specified for GCS source")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Google Cloud Storage.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from GCS bucket: {self.bucket}")
            if self.key:
                logger.info(f"Using key/prefix: {self.key}")
            
            # Use GCSReader to load documents
            documents = self.reader.load_data()
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "gcs",
                    "bucket": self.bucket,
                    "key": self.key,
                    "project_id": self.project_id,
                    "source_type": "gcs_object"
                })
            
            logger.info(f"GCSSource loaded {len(documents)} documents from bucket: {self.bucket}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from GCS bucket '{self.bucket}': {str(e)}")
            raise
    
    def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Google Cloud Storage with detailed progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from GCS bucket: {self.bucket} with progress tracking")
            if self.key:
                logger.info(f"Using key/prefix: {self.key}")
            
            # First, try to get file list for progress tracking
            if progress_callback:
                progress_callback(0, 1, "Scanning GCS bucket for files...")
            
            try:
                # Try to get file listing using google-cloud-storage directly for progress
                from google.cloud import storage
                from google.cloud.exceptions import GoogleCloudError
                
                # Create GCS client with same credentials as reader
                if self.service_account_key_path:
                    client = storage.Client.from_service_account_json(
                        self.service_account_key_path,
                        project=self.project_id
                    )
                else:
                    client = storage.Client(project=self.project_id)
                
                bucket = client.bucket(self.bucket)
                
                # List blobs to get file count
                prefix = self.key if self.key else None
                blobs = bucket.list_blobs(prefix=prefix)
                
                file_list = []
                for blob in blobs:
                    # Filter for supported file types
                    if any(blob.name.lower().endswith(ext) for ext in ['.pdf', '.txt', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.md', '.html', '.csv']):
                        file_list.append({
                            'name': blob.name,
                            'size': blob.size,
                            'updated': blob.updated
                        })
                
                total_files = len(file_list)
                logger.info(f"Found {total_files} supported files in GCS bucket")
                
                if progress_callback:
                    progress_callback(0, total_files, f"Found {total_files} files, starting download...")
                
                # Use GCSReader to load documents (it handles the actual downloading)
                documents = self.reader.load_data()
                
                # Simulate progress during processing
                if progress_callback and total_files > 0:
                    for i, doc in enumerate(documents, 1):
                        # Try to extract filename from document metadata
                        filename = doc.metadata.get('file_name', doc.metadata.get('source', f'document_{i}'))
                        progress_callback(i, len(documents), f"Processing document", filename)
                
            except (ImportError, GoogleCloudError) as e:
                logger.warning(f"Could not get detailed GCS file listing: {e}. Using fallback progress.")
                # Fallback to simple progress
                if progress_callback:
                    progress_callback(0, 1, "Loading GCS documents...")
                
                documents = self.reader.load_data()
                
                if progress_callback:
                    progress_callback(1, 1, f"Loaded {len(documents)} documents")
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "gcs",
                    "bucket": self.bucket,
                    "key": self.key,
                    "project_id": self.project_id,
                    "source_type": "gcs_object"
                })
            
            logger.info(f"GCSSource loaded {len(documents)} documents from bucket: {self.bucket}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from GCS bucket '{self.bucket}': {str(e)}")
            raise
