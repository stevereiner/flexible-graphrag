"""
Box data source for Flexible GraphRAG using LlamaIndex BoxReader.
Uses PassthroughExtractor pattern to capture file metadata without parsing.
"""

from typing import List, Dict, Any, Optional
import logging
import os
from llama_index.core import Document

from .base import BaseDataSource
from .passthrough_extractor import PassthroughExtractor

# Suppress llama-index-readers-file warning by importing it if available
try:
    import llama_index.readers.file  # noqa: F401
except ImportError:
    pass  # Package not needed since we provide custom extractors

logger = logging.getLogger(__name__)


class BoxSource(BaseDataSource):
    """Data source for Box using LlamaIndex BoxReader with PassthroughExtractor"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # First, check if BOX_CONFIG environment variable exists and merge it
        import json
        box_env_config = os.getenv("BOX_CONFIG", "")
        if box_env_config:
            try:
                env_config = json.loads(box_env_config)
                logger.info("Loading Box configuration from BOX_CONFIG environment variable")
                # Merge env config with provided config (provided config takes precedence)
                for key, value in env_config.items():
                    if key not in config or not config.get(key):
                        config[key] = value
                        logger.info(f"Using {key} from BOX_CONFIG environment variable")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse BOX_CONFIG environment variable: {e}")
        
        self.box_folder_id = config.get("box_folder_id", "0")  # "0" is root folder
        self.box_file_ids = config.get("box_file_ids", [])  # Optional: specific file IDs
        
        # Box API credentials
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.access_token = config.get("access_token", "")
        
        # Enterprise ID and User ID - check config first, then individual env vars
        self.enterprise_id = config.get("enterprise_id", "") or os.getenv("BOX_ENTERPRISE_ID", "")
        self.user_id = config.get("user_id", "") or os.getenv("BOX_USER_ID", "")
        
        # Import LlamaIndex Box reader
        try:
            from llama_index.readers.box import BoxReader
            
            logger.info(f"BoxSource initialized for folder ID: {self.box_folder_id}")
            if self.user_id:
                logger.info(f"Box user_id configured: {self.user_id}")
            if self.enterprise_id:
                logger.info(f"Box enterprise_id configured: {self.enterprise_id}")
        except ImportError as e:
            logger.error(f"Failed to import BoxReader: {e}")
            raise ImportError("Please install llama-index-readers-box: pip install llama-index-readers-box")
    
    def validate_config(self) -> bool:
        """Validate the Box source configuration."""
        # Developer token (access_token) is simplest
        if self.access_token:
            return True
        
        # CCG requires client_id, client_secret, and at least one of enterprise_id or user_id
        if self.client_id and self.client_secret:
            if self.enterprise_id or self.user_id:
                return True
            else:
                logger.error("Box CCG authentication requires enterprise_id and/or user_id")
                return False
        
        logger.error("Box authentication requires either access_token OR (client_id + client_secret + enterprise_id/user_id)")
        return False
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Box using PassthroughExtractor.
        Returns placeholder documents with file metadata for DocumentProcessor.
        
        Returns:
            List[Document]: List of placeholder Document objects with _fs metadata
        """
        try:
            from llama_index.readers.box import BoxReader
            from box_sdk_gen import BoxClient, BoxDeveloperTokenAuth, BoxCCGAuth, CCGConfig
            
            logger.info(f"Loading documents from Box folder ID: {self.box_folder_id}")
            
            # Create PassthroughExtractor (no progress callback for get_documents)
            extractor = PassthroughExtractor(progress_callback=None)
            
            # Define file extractor mapping once
            file_extractor = {
                ".pdf": extractor, ".docx": extractor, ".pptx": extractor,
                ".xlsx": extractor, ".txt": extractor, ".md": extractor,
                ".html": extractor, ".csv": extractor
            }
            
            # Create BoxClient with appropriate authentication
            if self.access_token:
                # Use developer token (simplest for testing)
                logger.info("Using Box Developer Token authentication")
                auth = BoxDeveloperTokenAuth(token=self.access_token)
                box_client = BoxClient(auth=auth)
            else:
                # Use CCG (Client Credentials Grant) for production
                logger.info(f"Using Box CCG authentication (enterprise_id: {self.enterprise_id}, user_id: {self.user_id})")
                ccg_config = CCGConfig(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    enterprise_id=self.enterprise_id if self.enterprise_id else None,
                    user_id=self.user_id if self.user_id else None
                )
                auth = BoxCCGAuth(config=ccg_config)
                box_client = BoxClient(auth=auth)
            
            # Initialize BoxReader with authenticated client
            reader = BoxReader(
                box_client=box_client,
                file_extractor=file_extractor
            )
            
            # Use BoxReader to load placeholder documents
            if self.box_file_ids:
                # Load specific files by ID
                documents = reader.load_data(file_ids=self.box_file_ids)
                logger.info(f"Loaded {len(self.box_file_ids)} specific Box files by ID")
            else:
                # Load all files from folder
                documents = reader.load_data(folder_id=self.box_folder_id)
                logger.info(f"Loaded {len(documents)} Box files from folder: {self.box_folder_id}")
            
            # Add source metadata to placeholder documents
            for doc in documents:
                doc.metadata.update({
                    "source": "box",
                    "folder_id": self.box_folder_id,
                    "source_type": "box_file"
                })
            
            logger.info(f"BoxSource created {len(documents)} placeholder documents for processing")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Box folder '{self.box_folder_id}': {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Box with progress tracking using PassthroughExtractor.
        PassthroughExtractor processes files immediately as BoxReader downloads them.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of processed Document objects
        """
        try:
            from llama_index.readers.box import BoxReader
            from box_sdk_gen import BoxClient, BoxDeveloperTokenAuth, BoxCCGAuth, CCGConfig
            
            logger.info(f"Loading documents from Box folder '{self.box_folder_id}' with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, f"Connecting to Box folder: {self.box_folder_id}")
            
            # Get DocumentProcessor for immediate processing
            doc_processor = self._get_document_processor()
            
            # Create PassthroughExtractor with BOTH progress callback AND doc_processor
            # This allows PassthroughExtractor to process files immediately as they're downloaded
            extractor = PassthroughExtractor(
                progress_callback=progress_callback,
                doc_processor=doc_processor  # Process files immediately!
            )
            
            # Define file extractor mapping once
            file_extractor = {
                ".pdf": extractor, ".docx": extractor, ".pptx": extractor,
                ".xlsx": extractor, ".txt": extractor, ".md": extractor,
                ".html": extractor, ".csv": extractor
            }
            
            # Create BoxClient with appropriate authentication
            if self.access_token:
                # Use developer token (simplest for testing)
                logger.info("Using Box Developer Token authentication")
                auth = BoxDeveloperTokenAuth(token=self.access_token)
                box_client = BoxClient(auth=auth)
            else:
                # Use CCG (Client Credentials Grant) for production
                logger.info(f"Using Box CCG authentication (enterprise_id: {self.enterprise_id}, user_id: {self.user_id})")
                ccg_config = CCGConfig(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    enterprise_id=self.enterprise_id if self.enterprise_id else None,
                    user_id=self.user_id if self.user_id else None
                )
                auth = BoxCCGAuth(config=ccg_config)
                box_client = BoxClient(auth=auth)
            
            # Initialize BoxReader with authenticated client
            reader = BoxReader(
                box_client=box_client,
                file_extractor=file_extractor
            )
            
            # Use BoxReader to load and process documents
            # PassthroughExtractor will process each file immediately and return processed docs
            if self.box_file_ids:
                # Loading specific files by ID
                documents = reader.load_data(file_ids=self.box_file_ids)
                logger.info(f"Loaded and processed {len(self.box_file_ids)} specific Box files by ID")
            else:
                # Loading from folder
                documents = reader.load_data(folder_id=self.box_folder_id)
                logger.info(f"Loaded and processed {len(documents)} Box files from folder: {self.box_folder_id}")
            
            # Add Box metadata to processed documents
            for doc in documents:
                doc.metadata.update({
                    "source": "box",
                    "folder_id": self.box_folder_id,
                    "source_type": "box_file"
                })
            
            logger.info(f"BoxSource processed {len(documents)} documents from Box")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Box folder '{self.box_folder_id}': {str(e)}")
            raise
