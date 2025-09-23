"""
Azure Blob Storage data source for Flexible GraphRAG using LlamaIndex AzStorageBlobReader.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class AzureBlobSource(BaseDataSource):
    """Data source for Azure Blob Storage using LlamaIndex AzStorageBlobReader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.container_name = config.get("container_name", "")
        self.account_url = config.get("account_url", "")
        self.blob = config.get("blob", "")  # Optional: specific blob name/prefix (renamed to match LlamaCloud)
        self.prefix = config.get("prefix", "")  # Optional: folder prefix
        self.account_name = config.get("account_name", "")
        self.account_key = config.get("account_key", "")
        
        # Import LlamaIndex Azure Blob reader
        try:
            from llama_index.readers.azstorage_blob import AzStorageBlobReader
            
            # Initialize AzStorageBlobReader using Method 1 (Account Key Authentication)
            # Following LlamaCloud pattern: container_name, account_url, blob, prefix, account_name, account_key
            self.reader = AzStorageBlobReader(
                container_name=self.container_name,
                account_url=self.account_url,
                blob_name=self.blob or None,  # Use blob parameter, fallback to None if empty
                prefix=self.prefix or None,   # Use prefix parameter
                account_name=self.account_name,
                account_key=self.account_key
            )
            
            logger.info(f"AzureBlobSource initialized for container: {self.container_name}")
        except ImportError as e:
            logger.error(f"Failed to import AzStorageBlobReader: {e}")
            raise ImportError("Please install llama-index-readers-azstorage-blob: pip install llama-index-readers-azstorage-blob")
    
    def validate_config(self) -> bool:
        """Validate the Azure Blob Storage source configuration for Method 1 (Account Key Authentication)."""
        if not self.container_name:
            logger.error("No container_name specified for Azure Blob Storage source")
            return False
        
        if not self.account_url:
            logger.error("No account_url specified for Azure Blob Storage source")
            return False
        
        if not self.account_name:
            logger.error("No account_name specified for Azure Blob Storage source")
            return False
            
        if not self.account_key:
            logger.error("No account_key specified for Azure Blob Storage source")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Azure Blob Storage.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from Azure Blob Storage container: {self.container_name}")
            if self.blob_name:
                logger.info(f"Using blob name/prefix: {self.blob_name}")
            
            # Use AzStorageBlobReader to load documents
            documents = self.reader.load_data()
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "azure_blob",
                    "container_name": self.container_name,
                    "blob_name": self.blob_name,
                    "account_name": self.account_name,
                    "source_type": "azure_blob_object"
                })
            
            logger.info(f"AzureBlobSource loaded {len(documents)} documents from container: {self.container_name}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Azure Blob Storage container '{self.container_name}': {str(e)}")
            raise
    
    def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Azure Blob Storage with detailed progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from Azure Blob Storage container: {self.container_name} with progress tracking")
            if self.blob_name:
                logger.info(f"Using blob name/prefix: {self.blob_name}")
            
            # First, try to get blob list for progress tracking
            if progress_callback:
                progress_callback(0, 1, "Scanning Azure Blob Storage for files...")
            
            try:
                # Try to get blob listing using azure-storage-blob directly for progress
                from azure.storage.blob import BlobServiceClient
                from azure.core.exceptions import AzureError
                
                # Create blob service client with same credentials as reader
                if self.connection_string:
                    blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
                elif self.account_name and self.account_key:
                    blob_service_client = BlobServiceClient(
                        account_url=f"https://{self.account_name}.blob.core.windows.net",
                        credential=self.account_key
                    )
                else:
                    # Use default credentials (managed identity, etc.)
                    blob_service_client = BlobServiceClient(
                        account_url=f"https://{self.account_name}.blob.core.windows.net"
                    )
                
                container_client = blob_service_client.get_container_client(self.container_name)
                
                # List blobs to get file count
                name_starts_with = self.blob_name if self.blob_name else None
                blob_list = container_client.list_blobs(name_starts_with=name_starts_with)
                
                file_list = []
                for blob in blob_list:
                    # Filter for supported file types
                    if any(blob.name.lower().endswith(ext) for ext in ['.pdf', '.txt', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.md', '.html', '.csv']):
                        file_list.append({
                            'name': blob.name,
                            'size': blob.size,
                            'last_modified': blob.last_modified
                        })
                
                total_files = len(file_list)
                logger.info(f"Found {total_files} supported files in Azure Blob Storage container")
                
                if progress_callback:
                    progress_callback(0, total_files, f"Found {total_files} files, starting download...")
                
                # Use AzStorageBlobReader to load documents (it handles the actual downloading)
                documents = self.reader.load_data()
                
                # Simulate progress during processing
                if progress_callback and total_files > 0:
                    for i, doc in enumerate(documents, 1):
                        # Try to extract filename from document metadata
                        filename = doc.metadata.get('file_name', doc.metadata.get('source', f'document_{i}'))
                        progress_callback(i, len(documents), f"Processing document", filename)
                
            except (ImportError, AzureError) as e:
                logger.warning(f"Could not get detailed Azure Blob Storage file listing: {e}. Using fallback progress.")
                # Fallback to simple progress
                if progress_callback:
                    progress_callback(0, 1, "Loading Azure Blob Storage documents...")
                
                documents = self.reader.load_data()
                
                if progress_callback:
                    progress_callback(1, 1, f"Loaded {len(documents)} documents")
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "azure_blob",
                    "container_name": self.container_name,
                    "blob_name": self.blob_name,
                    "account_name": self.account_name,
                    "source_type": "azure_blob_object"
                })
            
            logger.info(f"AzureBlobSource loaded {len(documents)} documents from container: {self.container_name}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Azure Blob Storage container '{self.container_name}': {str(e)}")
            raise
