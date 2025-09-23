"""
Microsoft SharePoint data source for Flexible GraphRAG using LlamaIndex SharePointReader.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class SharePointSource(BaseDataSource):
    """Data source for Microsoft SharePoint using LlamaIndex SharePointReader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.tenant_id = config.get("tenant_id", "")
        self.site_name = config.get("site_name", "")  # LlamaCloud field name
        self.site_id = config.get("site_id", "")  # Optional: for Sites.Selected permission
        self.folder_path = config.get("folder_path", "/")  # LlamaCloud field name
        self.folder_id = config.get("folder_id", "")  # LlamaCloud field name (replaces document_library)
        self.file_ids = config.get("file_ids", [])  # Optional: specific file IDs
        
        # Import LlamaIndex SharePoint reader
        try:
            from llama_index.readers.microsoft_sharepoint import SharePointReader
            
            # Initialize SharePointReader
            self.reader = SharePointReader(
                client_id=self.client_id,
                client_secret=self.client_secret,
                tenant_id=self.tenant_id
            )
            
            logger.info(f"SharePointSource initialized for site: {self.site_name}")
        except ImportError as e:
            logger.error(f"Failed to import SharePointReader: {e}")
            raise ImportError("Please install llama-index-readers-microsoft-sharepoint: pip install llama-index-readers-microsoft-sharepoint")
    
    def validate_config(self) -> bool:
        """Validate the SharePoint source configuration."""
        if not self.client_id:
            logger.error("No client_id specified for SharePoint source")
            return False
        
        if not self.client_secret:
            logger.error("No client_secret specified for SharePoint source")
            return False
        
        if not self.tenant_id:
            logger.error("No tenant_id specified for SharePoint source")
            return False
        
        if not self.site_name:
            logger.error("No site_name specified for SharePoint source")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Microsoft SharePoint.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from SharePoint site: {self.site_name}")
            logger.info(f"Folder path: {self.folder_path}")
            
            # Use SharePointReader to load documents following LlamaCloud patterns
            if self.file_ids:
                # Load specific files by ID
                documents = self.reader.load_data(
                    sharepoint_site_name=self.site_name,  # Use site_name
                    file_ids=self.file_ids
                )
                logger.info(f"Loading {len(self.file_ids)} specific files by ID")
            else:
                # Load all files from folder path
                documents = self.reader.load_data(
                    sharepoint_site_name=self.site_name,  # Use site_name
                    sharepoint_folder_path=self.folder_path  # Use folder_path
                )
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "sharepoint",
                    "tenant_id": self.tenant_id,
                    "site_name": self.site_name,
                    "site_id": self.site_id,
                    "folder_path": self.folder_path,
                    "folder_id": self.folder_id,
                    "source_type": "sharepoint_file"
                })
            
            logger.info(f"SharePointSource loaded {len(documents)} documents from SharePoint")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from SharePoint site '{self.site_name}': {str(e)}")
            raise
    
    def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from SharePoint with progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from SharePoint site '{self.site_name}' with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, f"Connecting to SharePoint site: {self.site_name}")
            
            # Use SharePointReader to load documents
            if self.file_ids:
                # Loading specific files by ID
                documents = self.reader.load_data(file_ids=self.file_ids)
                
                if progress_callback:
                    for i, doc in enumerate(documents, 1):
                        filename = doc.metadata.get('file_name', f'file_{i}')
                        progress_callback(i, len(documents), f"Processing SharePoint file", filename)
            else:
                # Loading from folder path
                documents = self.reader.load_data(
                    sharepoint_site_name=self.site_name,  # Use site_name
                    sharepoint_folder_path=self.folder_path  # Use folder_path
                )
                
                if progress_callback:
                    progress_callback(1, 1, f"Processing SharePoint folder: {self.folder_path}")
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "sharepoint",
                    "tenant_id": self.tenant_id,
                    "site_name": self.site_name,
                    "site_id": self.site_id,
                    "folder_path": self.folder_path,
                    "folder_id": self.folder_id,
                    "source_type": "sharepoint_file"
                })
            
            logger.info(f"SharePointSource loaded {len(documents)} documents from SharePoint")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from SharePoint site '{self.site_name}': {str(e)}")
            raise
