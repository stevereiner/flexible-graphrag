"""
Google Drive data source for Flexible GraphRAG using LlamaIndex GoogleDriveReader.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class GoogleDriveSource(BaseDataSource):
    """Data source for Google Drive using LlamaIndex GoogleDriveReader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
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
        
        # Import LlamaIndex Google Drive reader
        try:
            from llama_index.readers.google import GoogleDriveReader
            
            # Initialize GoogleDriveReader with proper authentication
            if self.service_account_key:
                # Use service account key (preferred method from LlamaIndex docs)
                self.reader = GoogleDriveReader(service_account_key=self.service_account_key)
                logger.info("GoogleDriveReader initialized with service account key")
            elif self.credentials_path:
                # Use credentials file path
                self.reader = GoogleDriveReader(
                    credentials_path=self.credentials_path,
                    token_path=self.token_path
                )
                logger.info("GoogleDriveReader initialized with credentials file")
            else:
                # This will fail with the error we saw - no authentication provided
                logger.error("No authentication method provided for Google Drive")
                raise ValueError("Must specify service account credentials, credentials_path, or other authentication method")
            
            logger.info("GoogleDriveSource initialized successfully")
        except ImportError as e:
            logger.error(f"Failed to import GoogleDriveReader: {e}")
            raise ImportError("Please install llama-index-readers-google-drive: pip install llama-index-readers-google-drive")
    
    def validate_config(self) -> bool:
        """Validate the Google Drive source configuration."""
        # Check authentication
        if not self.service_account_key and not self.credentials_path:
            logger.error("Google Drive authentication required: provide service account credentials or credentials file path")
            return False
        
        # At least one of folder_id, file_ids, or query should be specified
        # If none specified, will load from root folder (which is valid)
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Google Drive.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            documents = []
            
            if self.file_ids:
                # Load specific files by ID
                logger.info(f"Loading {len(self.file_ids)} specific files by ID from Google Drive")
                documents = self.reader.load_data(file_ids=self.file_ids)
            elif self.folder_id:
                # Load all files from folder
                logger.info(f"Loading documents from Google Drive folder ID: {self.folder_id}")
                documents = self.reader.load_data(folder_id=self.folder_id)
            elif self.query:
                # Search for files using query
                logger.info(f"Searching Google Drive with query: {self.query}")
                documents = self.reader.load_data(query=self.query)
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "google_drive",
                    "folder_id": self.folder_id,
                    "query": self.query,
                    "source_type": "google_drive_file"
                })
            
            logger.info(f"GoogleDriveSource loaded {len(documents)} documents from Google Drive")
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
        try:
            logger.info(f"Loading documents from Google Drive with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, "Connecting to Google Drive...")
            
            # Use GoogleDriveReader to load documents
            if self.file_ids:
                # Loading specific files by ID
                documents = self.reader.load_data(file_ids=self.file_ids)
                
                if progress_callback:
                    for i, doc in enumerate(documents, 1):
                        filename = doc.metadata.get('file_name', f'file_{i}')
                        progress_callback(i, len(documents), f"Processing Google Drive file", filename)
            elif self.folder_id:
                # Loading from specific folder
                documents = self.reader.load_data(folder_id=self.folder_id)
                
                if progress_callback:
                    progress_callback(1, 1, f"Processing Google Drive folder: {self.folder_id}")
            elif self.query:
                # Loading based on search query
                documents = self.reader.load_data(query=self.query)
                
                if progress_callback:
                    progress_callback(1, 1, f"Processing Google Drive search: {self.query}")
            else:
                # Loading from root folder
                documents = self.reader.load_data()
                
                if progress_callback:
                    progress_callback(1, 1, "Processing Google Drive root folder")
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "google_drive",
                    "folder_id": self.folder_id,
                    "query": self.query,
                    "source_type": "google_drive_file"
                })
            
            logger.info(f"GoogleDriveSource loaded {len(documents)} documents from Google Drive")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Google Drive: {str(e)}")
            raise
