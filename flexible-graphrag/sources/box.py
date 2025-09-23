"""
Box data source for Flexible GraphRAG using LlamaIndex BoxReader.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class BoxSource(BaseDataSource):
    """Data source for Box using LlamaIndex BoxReader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.box_folder_id = config.get("box_folder_id", "0")  # "0" is root folder
        self.box_file_ids = config.get("box_file_ids", [])  # Optional: specific file IDs
        
        # Box API credentials
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.access_token = config.get("access_token", "")
        
        # Import LlamaIndex Box reader
        try:
            from llama_index.readers.box import BoxReader
            
            # Initialize BoxReader
            if self.access_token:
                # Use access token directly
                self.reader = BoxReader(access_token=self.access_token)
            else:
                # Use OAuth flow (requires client_id and client_secret)
                self.reader = BoxReader(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
            
            logger.info(f"BoxSource initialized for folder ID: {self.box_folder_id}")
        except ImportError as e:
            logger.error(f"Failed to import BoxReader: {e}")
            raise ImportError("Please install llama-index-readers-box: pip install llama-index-readers-box")
    
    def validate_config(self) -> bool:
        """Validate the Box source configuration."""
        if not self.access_token and (not self.client_id or not self.client_secret):
            logger.error("Either access_token or both client_id and client_secret must be specified for Box source")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Box.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from Box folder ID: {self.box_folder_id}")
            
            # Use BoxReader to load documents
            if self.box_file_ids:
                # Load specific files by ID
                documents = self.reader.load_data(file_ids=self.box_file_ids)
                logger.info(f"Loading {len(self.box_file_ids)} specific files by ID")
            else:
                # Load all files from folder
                documents = self.reader.load_data(folder_id=self.box_folder_id)
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "box",
                    "folder_id": self.box_folder_id,
                    "source_type": "box_file"
                })
            
            logger.info(f"BoxSource loaded {len(documents)} documents from Box")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Box folder '{self.box_folder_id}': {str(e)}")
            raise
    
    def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Box with progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading documents from Box folder '{self.box_folder_id}' with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, f"Connecting to Box folder: {self.box_folder_id}")
            
            # Use BoxReader to load documents
            if self.box_file_ids:
                # Loading specific files by ID
                documents = self.reader.load_data(file_ids=self.box_file_ids)
                
                if progress_callback:
                    for i, doc in enumerate(documents, 1):
                        filename = doc.metadata.get('file_name', f'file_{i}')
                        progress_callback(i, len(documents), f"Processing Box file", filename)
            else:
                # Loading from folder
                documents = self.reader.load_data(folder_id=self.box_folder_id)
                
                if progress_callback:
                    progress_callback(1, 1, f"Processing Box folder: {self.box_folder_id}")
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "box",
                    "folder_id": self.box_folder_id,
                    "client_id": self.client_id,
                    "source_type": "box_file"
                })
            
            logger.info(f"BoxSource loaded {len(documents)} documents from Box")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Box folder '{self.box_folder_id}': {str(e)}")
            raise
