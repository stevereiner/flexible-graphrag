"""
Microsoft OneDrive data source for Flexible GraphRAG using LlamaIndex OneDriveReader.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class OneDriveSource(BaseDataSource):
    """Data source for Microsoft OneDrive using LlamaIndex OneDriveReader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.user_principal_name = config.get("user_principal_name", "")  # Required field from LlamaCloud
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.tenant_id = config.get("tenant_id", "")
        self.folder_path = config.get("folder_path", "/")
        self.folder_id = config.get("folder_id", "")  # Optional: specific folder ID
        self.file_ids = config.get("file_ids", [])  # Optional: specific file IDs
        
        # Import LlamaIndex OneDrive reader
        try:
            from llama_index.readers.microsoft_onedrive import OneDriveReader
            
            # Initialize OneDriveReader with LlamaCloud parameters
            self.reader = OneDriveReader(
                client_id=self.client_id,
                client_secret=self.client_secret,
                tenant_id=self.tenant_id,
                user_principal_name=self.user_principal_name  # Required by LlamaCloud
            )
            
            logger.info(f"OneDriveSource initialized for tenant: {self.tenant_id}")
        except ImportError as e:
            logger.error(f"Failed to import OneDriveReader: {e}")
            raise ImportError("Please install llama-index-readers-microsoft-onedrive: pip install llama-index-readers-microsoft-onedrive")
    
    def validate_config(self) -> bool:
        """Validate the OneDrive source configuration."""
        if not self.user_principal_name:
            logger.error("No user_principal_name specified for OneDrive source")
            return False
        
        if not self.client_id:
            logger.error("No client_id specified for OneDrive source")
            return False
        
        if not self.client_secret:
            logger.error("No client_secret specified for OneDrive source")
            return False
        
        if not self.tenant_id:
            logger.error("No tenant_id specified for OneDrive source")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Microsoft OneDrive.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from OneDrive folder: {self.folder_path}")
            
            # Use OneDriveReader to load documents
            if self.file_ids:
                # Load specific files by ID
                documents = self.reader.load_data(file_ids=self.file_ids)
                logger.info(f"Loading {len(self.file_ids)} specific files by ID")
            else:
                # Load all files from folder path
                documents = self.reader.load_data(folder_path=self.folder_path)
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "onedrive",
                    "user_principal_name": self.user_principal_name,
                    "tenant_id": self.tenant_id,
                    "folder_path": self.folder_path,
                    "source_type": "onedrive_file"
                })
            
            logger.info(f"OneDriveSource loaded {len(documents)} documents from OneDrive")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from OneDrive: {str(e)}")
            raise
    
    def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from OneDrive with progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from OneDrive with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, "Connecting to OneDrive...")
            
            # Use OneDriveReader to load documents
            if self.file_ids:
                # Loading specific files
                documents = self.reader.load_data(file_ids=self.file_ids)
                
                if progress_callback:
                    for i, doc in enumerate(documents, 1):
                        filename = doc.metadata.get('file_name', f'file_{i}')
                        progress_callback(i, len(documents), f"Processing OneDrive file", filename)
            else:
                # Loading from folder path
                documents = self.reader.load_data(folder_path=self.folder_path)
                
                if progress_callback:
                    progress_callback(1, 1, f"Processing OneDrive folder: {self.folder_path}")
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "onedrive",
                    "user_principal_name": self.user_principal_name,
                    "client_id": self.client_id,
                    "tenant_id": self.tenant_id,
                    "folder_path": self.folder_path,
                    "source_type": "onedrive_file"
                })
            
            logger.info(f"OneDriveSource loaded {len(documents)} documents from OneDrive")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from OneDrive: {str(e)}")
            raise
