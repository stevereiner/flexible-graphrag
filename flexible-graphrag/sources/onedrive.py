"""
Microsoft OneDrive data source for Flexible GraphRAG using LlamaIndex OneDriveReader.
Uses PassthroughExtractor pattern to capture file metadata without parsing.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource
from .passthrough_extractor import PassthroughExtractor

logger = logging.getLogger(__name__)


class OneDriveSource(BaseDataSource):
    """Data source for Microsoft OneDrive using LlamaIndex OneDriveReader with PassthroughExtractor"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.user_principal_name = config.get("user_principal_name", "")  # Required field from LlamaCloud
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.tenant_id = config.get("tenant_id", "")
        self.folder_path = config.get("folder_path", "/")
        self.folder_id = config.get("folder_id", "")  # Optional: specific folder ID
        self.file_ids = config.get("file_ids", [])  # Optional: specific file IDs
        
        # Log all configuration for debugging
        logger.info(f"OneDriveSource __init__ received config keys: {list(config.keys())}")
        logger.info(f"OneDriveSource __init__ - user_principal_name: '{self.user_principal_name}'")
        logger.info(f"OneDriveSource __init__ - client_id: '{self.client_id[:10]}...' (truncated)")
        logger.info(f"OneDriveSource __init__ - tenant_id: '{self.tenant_id}'")
        logger.info(f"OneDriveSource __init__ - folder_path: '{self.folder_path}'")
        logger.info(f"OneDriveSource __init__ - NOTE: LlamaIndex parameter name is 'userprincipalname' (not user_principal_name)")
        
        # Import LlamaIndex OneDrive reader
        try:
            from llama_index.readers.microsoft_onedrive import OneDriveReader
            
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
        Retrieve documents from Microsoft OneDrive using PassthroughExtractor.
        Returns placeholder documents with file metadata for DocumentProcessor.
        
        Returns:
            List[Document]: List of placeholder Document objects with _fs metadata
        """
        try:
            from llama_index.readers.microsoft_onedrive import OneDriveReader
            
            # Initialize OneDriveReader with PassthroughExtractor
            # NOTE: LlamaIndex parameter name is 'userprincipalname' (not user_principal_name)
            logger.info(f"get_documents() called - Loading documents from OneDrive folder: {self.folder_path}")
            logger.info(f"get_documents() - user_principal_name: '{self.user_principal_name}'")
            logger.info(f"get_documents() - client_id: '{self.client_id[:10]}...'")
            logger.info(f"get_documents() - tenant_id: '{self.tenant_id}'")
            
            # Create PassthroughExtractor (no progress callback for get_documents)
            extractor = PassthroughExtractor(progress_callback=None)
            
            logger.info(f"get_documents() - Creating OneDriveReader with userprincipalname='{self.user_principal_name}'")
            reader = OneDriveReader(
                client_id=self.client_id,
                client_secret=self.client_secret,
                tenant_id=self.tenant_id,
                userprincipalname=self.user_principal_name,  # Note: LlamaIndex uses 'userprincipalname' not 'user_principal_name'
                file_extractor={".pdf": extractor, ".docx": extractor, ".pptx": extractor,
                               ".xlsx": extractor, ".txt": extractor, ".md": extractor,
                               ".html": extractor, ".csv": extractor}
            )
            logger.info(f"get_documents() - OneDriveReader created successfully")
            
            # Use OneDriveReader to load placeholder documents
            if self.file_ids:
                # Load specific files by ID
                logger.info(f"get_documents() - Loading {len(self.file_ids)} specific files by ID")
                documents = reader.load_data(file_ids=self.file_ids)
                logger.info(f"Loaded {len(self.file_ids)} specific OneDrive files by ID")
            else:
                # Load all files from folder path
                logger.info(f"get_documents() - Loading files from folder path: {self.folder_path}")
                documents = reader.load_data(folder_path=self.folder_path)
                logger.info(f"Loaded {len(documents)} OneDrive files from folder: {self.folder_path}")
            
            # Add source metadata and use stable file_id as path
            for doc in documents:
                # Extract OneDrive file_id from metadata (provided by OneDriveReader)
                onedrive_file_id = doc.metadata.get('file_id')
                
                if onedrive_file_id:
                    # Use OneDrive file_id as the stable path for document tracking
                    # This ensures consistent identification across ingestions
                    stable_path = f"onedrive://{onedrive_file_id}"
                    
                    # Store ORIGINAL file_path from OneDriveReader (has folder structure)
                    original_path = doc.metadata.get('file_path', '')
                    
                    # Store stable_path separately (not as primary file_path)
                    doc.metadata['stable_file_path'] = stable_path
                    
                    # Determine the human-readable path to use
                    # Priority: 1) from config (_file_path), 2) from OneDriveReader (original_path), 3) just filename
                    if '_file_path' in self.config:
                        # From incremental detector - most accurate
                        human_path = self.config['_file_path']
                    elif original_path and not original_path.startswith('/tmp/'):
                        # From OneDriveReader - has folder structure if available
                        human_path = original_path
                    else:
                        # Fallback - just use filename from metadata
                        human_path = doc.metadata.get('file_name', doc.metadata.get('name', ''))
                    
                    # Set file_path to human-readable version (this is what vector DB will use)
                    doc.metadata['file_path'] = human_path
                    doc.metadata['human_file_path'] = human_path
                    
                    # Set folder_path
                    if '_folder_path' in self.config:
                        doc.metadata['folder_path'] = self.config['_folder_path']
                    elif human_path:
                        # Extract folder from path
                        import os
                        folder = os.path.dirname(human_path)
                        if folder and folder != '/':
                            doc.metadata['folder_path'] = folder
                        else:
                            doc.metadata['folder_path'] = '/'
                    
                    logger.info(f"OneDrive file: stable={stable_path}, human={human_path}, folder={doc.metadata.get('folder_path', 'N/A')}")
                else:
                    logger.warning(f"Document missing file_id in metadata: {doc.metadata}")
                
                # Update metadata - but don't overwrite folder_path if already set
                updates = {
                    "source": "onedrive",
                    "user_principal_name": self.user_principal_name,
                    "tenant_id": self.tenant_id,
                    "source_type": "onedrive_file"
                }
                # Only add folder_path if not already set (preserve the extracted one)
                if 'folder_path' not in doc.metadata or not doc.metadata['folder_path']:
                    updates["folder_path"] = self.folder_path
                
                doc.metadata.update(updates)
            
            logger.info(f"OneDriveSource created {len(documents)} placeholder documents for processing")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from OneDrive in get_documents(): {str(e)}", exc_info=True)
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from OneDrive with progress tracking.
        OneDrive downloads files directly and extracts actual content.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of Document objects with actual file content
        """
        try:
            from llama_index.readers.microsoft_onedrive import OneDriveReader
            
            logger.info(f"get_documents_with_progress() called - Loading documents from OneDrive with progress tracking")
            logger.info(f"get_documents_with_progress() - user_principal_name: '{self.user_principal_name}'")
            logger.info(f"get_documents_with_progress() - client_id: '{self.client_id[:10]}...'")
            logger.info(f"get_documents_with_progress() - tenant_id: '{self.tenant_id}'")
            logger.info(f"get_documents_with_progress() - folder_path: '{self.folder_path}'")
            
            if progress_callback:
                logger.info(f"get_documents_with_progress() - progress_callback provided, calling with initial message")
                progress_callback(0, 1, "Connecting to OneDrive...")
            
            # OneDrive downloads files to temp directory, so we need immediate processing
            # Create DocumentProcessor for immediate file processing
            from document_processor import DocumentProcessor, get_parser_type_from_env
            parser_type = get_parser_type_from_env()
            doc_processor = DocumentProcessor(parser_type=parser_type)
            
            # Create PassthroughExtractor with progress callback AND doc_processor for immediate processing
            extractor = PassthroughExtractor(progress_callback=progress_callback, doc_processor=doc_processor)
            
            # Initialize OneDriveReader with PassthroughExtractor
            # NOTE: LlamaIndex parameter name is 'userprincipalname' (not user_principal_name)
            logger.info(f"get_documents_with_progress() - Creating OneDriveReader with userprincipalname='{self.user_principal_name}'")
            reader = OneDriveReader(
                client_id=self.client_id,
                client_secret=self.client_secret,
                tenant_id=self.tenant_id,
                userprincipalname=self.user_principal_name,
                file_extractor={".pdf": extractor, ".docx": extractor, ".pptx": extractor,
                               ".xlsx": extractor, ".txt": extractor, ".md": extractor,
                               ".html": extractor, ".csv": extractor}
            )
            # logger.debug("OneDriveReader created successfully")  # Debug only
            
            # Use OneDriveReader to load documents with actual content (processed immediately by PassthroughExtractor)
            if self.file_ids:
                # Loading specific files by ID
                logger.info(f"Loading {len(self.file_ids)} specific files by ID")
                documents = reader.load_data(file_ids=self.file_ids)
                logger.info(f"Loaded {len(self.file_ids) if self.file_ids else 0} specific OneDrive files by ID")
            else:
                # Loading from folder path
                logger.info(f"Loading OneDrive files from folder: {self.folder_path}")
                documents = reader.load_data(folder_path=self.folder_path)
                # logger.debug(f"load_data() returned: {documents} (type: {type(documents)})")  # Debug only
                if documents is None:
                    logger.error("load_data() returned None - this indicates OneDriveReader failed to authenticate or load documents")
                    raise ValueError("OneDriveReader.load_data() returned None - authentication or loading failed")
                logger.info(f"Loaded {len(documents)} OneDrive files from folder")
            
            # Add source metadata and use stable file_id as path
            if documents:
                for doc in documents:
                    # Extract OneDrive file_id from metadata (provided by OneDriveReader)
                    onedrive_file_id = doc.metadata.get('file_id')
                    
                    if onedrive_file_id:
                        # Use OneDrive file_id as the stable path for document tracking
                        # This ensures consistent identification across ingestions
                        stable_path = f"onedrive://{onedrive_file_id}"
                        
                        # Store ORIGINAL file_path from OneDriveReader (has folder structure)
                        original_path = doc.metadata.get('file_path', '')
                        
                        # Store stable_path separately (not as primary file_path)
                        doc.metadata['stable_file_path'] = stable_path
                        
                        # Determine the human-readable path to use
                        # Priority: 1) from config (_file_path), 2) from OneDriveReader (original_path), 3) just filename
                        if '_file_path' in self.config:
                            # From incremental detector - most accurate
                            human_path = self.config['_file_path']
                        elif original_path and not original_path.startswith('/tmp/'):
                            # From OneDriveReader - has folder structure if available
                            human_path = original_path
                        else:
                            # Fallback - just use filename from metadata
                            human_path = doc.metadata.get('file_name', doc.metadata.get('name', ''))
                        
                        # Set file_path to human-readable version (this is what vector DB will use)
                        doc.metadata['file_path'] = human_path
                        doc.metadata['human_file_path'] = human_path
                        
                        # Set folder_path
                        if '_folder_path' in self.config:
                            doc.metadata['folder_path'] = self.config['_folder_path']
                        elif human_path:
                            # Extract folder from path
                            import os
                            folder = os.path.dirname(human_path)
                            if folder and folder != '/':
                                doc.metadata['folder_path'] = folder
                            else:
                                doc.metadata['folder_path'] = '/'
                        
                        # logger.debug(f"Stable: {stable_path}, Human: {human_path}")  # Debug only
                    else:
                        logger.warning(f"Document missing file_id in metadata: {doc.metadata}")
                    
                    # Update metadata - but don't overwrite folder_path if already set
                    updates = {
                        "source": "onedrive",
                        "user_principal_name": self.user_principal_name,
                        "client_id": self.client_id,
                        "tenant_id": self.tenant_id,
                        "source_type": "onedrive_file"
                    }
                    # Only add folder_path if not already set (preserve the extracted one)
                    if 'folder_path' not in doc.metadata or not doc.metadata['folder_path']:
                        updates["folder_path"] = self.folder_path
                    
                    doc.metadata.update(updates)
                
                logger.info(f"OneDriveSource created {len(documents)} placeholder documents for processing")
                return documents
            else:
                logger.warning("No documents returned from OneDrive")
                return []
            
        except Exception as e:
            logger.error(f"Error loading documents from OneDrive in get_documents_with_progress(): {str(e)}", exc_info=True)
            raise
