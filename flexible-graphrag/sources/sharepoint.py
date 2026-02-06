"""
Microsoft SharePoint data source for Flexible GraphRAG using LlamaIndex SharePointReader.
Uses PassthroughExtractor pattern to capture file metadata without parsing.
"""

from typing import List, Dict, Any, Optional
import logging
from llama_index.core import Document

from .base import BaseDataSource
from .passthrough_extractor import PassthroughExtractor

logger = logging.getLogger(__name__)


class SharePointSource(BaseDataSource):
    """Data source for Microsoft SharePoint using LlamaIndex SharePointReader with PassthroughExtractor"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.tenant_id = config.get("tenant_id", "")
        self.site_name = config.get("site_name", "")  # LlamaCloud field name
        self.site_id = config.get("site_id", "")  # Optional: for Sites.Selected permission
        self.folder_path = config.get("folder_path", "/")  # LlamaCloud field name
        self.folder_id = config.get("folder_id", "")  # LlamaCloud field name (replaces document_library)
        self.file_ids = config.get("file_ids")  # Optional: specific file IDs (None for folder scan, list for incremental)
        
        # Import LlamaIndex SharePoint reader
        try:
            from llama_index.readers.microsoft_sharepoint import SharePointReader
            
            logger.info(f"SharePointSource initialized for site: {self.site_name}")
        except ImportError as e:
            logger.error(f"Failed to import SharePointReader: {e}")
            raise ImportError("Please install llama-index-readers-microsoft-sharepoint: pip install llama-index-readers-microsoft-sharepoint")
    
    async def _download_file_by_id(self, file_id: str) -> tuple[Optional[bytes], Optional[dict]]:
        """
        Download a single file from SharePoint by its file ID using Microsoft Graph API.
        SharePointReader doesn't support file_ids, so we need direct Graph API access.
        
        Args:
            file_id: The SharePoint file ID (drive item ID)
            
        Returns:
            Tuple of (file content as bytes, file metadata dict) or (None, None) if download fails
        """
        try:
            from msgraph import GraphServiceClient
            from azure.identity import ClientSecretCredential
            
            # Strip prefix if present (file_id might come with sharepoint:// or onedrive:// prefix)
            raw_file_id = file_id
            if '://' in file_id:
                raw_file_id = file_id.split('://')[-1]
            
            # Create Graph client
            credential = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            graph_client = GraphServiceClient(credentials=credential)
            
            # Download file content
            # For SharePoint: sites/{site-id}/drive/items/{item-id}/content
            if not self.site_id:
                logger.error("site_id is required to download files by ID from SharePoint")
                return None, None
                
            # Get the drive first
            drive = await graph_client.sites.by_site_id(self.site_id).drive.get()
            if not drive or not drive.id:
                logger.error(f"Could not get drive for SharePoint site {self.site_id}")
                return None, None
            
            # Get file metadata first (to get modified date)
            file_item = await graph_client.drives.by_drive_id(drive.id).items.by_drive_item_id(raw_file_id).get()
            
            # Download file content
            content_stream = await graph_client.drives.by_drive_id(drive.id).items.by_drive_item_id(raw_file_id).content.get()
            
            if content_stream:
                # Read the stream into bytes
                content_bytes = content_stream.read() if hasattr(content_stream, 'read') else content_stream
                logger.info(f"Downloaded file {raw_file_id} from SharePoint ({len(content_bytes)} bytes)")
                
                # Extract metadata
                metadata = {}
                if file_item:
                    if hasattr(file_item, 'last_modified_date_time'):
                        metadata['last_modified_datetime'] = file_item.last_modified_date_time.isoformat() if file_item.last_modified_date_time else None
                    if hasattr(file_item, 'size'):
                        metadata['size'] = file_item.size
                    if hasattr(file_item, 'name'):
                        metadata['name'] = file_item.name
                
                return content_bytes, metadata
            else:
                logger.warning(f"No content returned for file {file_id}")
                return None, None
                
        except Exception as e:
            logger.error(f"Error downloading SharePoint file {file_id}: {e}")
            return None, None
    
    
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
        
        # Require either site_name OR site_id (at least one)
        if not self.site_name and not self.site_id:
            logger.error("No site_name or site_id specified for SharePoint source")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Microsoft SharePoint using PassthroughExtractor.
        Returns placeholder documents with file metadata for DocumentProcessor.
        
        If file_ids is provided, downloads files directly via Microsoft Graph API
        since SharePointReader doesn't support file_ids parameter.
        
        Returns:
            List[Document]: List of placeholder Document objects with _fs metadata
        """
        try:
            # If file_ids is specified, we need async context - redirect to async method
            if self.file_ids:
                import asyncio
                logger.info(f"file_ids specified - using async method for SharePoint download")
                
                # Run async method in sync context
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                return loop.run_until_complete(self.get_documents_with_progress())
            
            # Normal folder scanning path (no file_ids)
            from llama_index.readers.microsoft_sharepoint import SharePointReader
            
            logger.info(f"Loading documents from SharePoint site: {self.site_name}")
            logger.info(f"Folder path: {self.folder_path}")
            
            # Create PassthroughExtractor (no progress callback for get_documents)
            extractor = PassthroughExtractor(progress_callback=None)
            
            # Initialize SharePointReader with PassthroughExtractor
            # Pass all available SharePoint parameters to constructor
            reader = SharePointReader(
                client_id=self.client_id,
                client_secret=self.client_secret,
                tenant_id=self.tenant_id,
                sharepoint_site_name=self.site_name,
                sharepoint_site_id=self.site_id if self.site_id else None,
                sharepoint_folder_path=self.folder_path if self.folder_path else None,
                sharepoint_folder_id=self.folder_id if self.folder_id else None,
                file_extractor={".pdf": extractor, ".docx": extractor, ".pptx": extractor,
                               ".xlsx": extractor, ".txt": extractor, ".md": extractor,
                               ".html": extractor, ".csv": extractor}
            )
            
            # Use SharePointReader to load placeholder documents
            # All parameters already set in constructor, just call load_data()
            documents = reader.load_data()
            
            # Check if documents is None (SharePointReader may return None on error)
            if documents is None:
                logger.error("SharePointReader.load_data() returned None - authentication or loading failed")
                raise ValueError("SharePointReader.load_data() returned None - authentication or loading failed")
            
            logger.info(f"Loaded {len(documents)} SharePoint files from site: {self.site_name}")
            
            # Add source metadata and use stable file_id as path
            for doc in documents:
                # Extract SharePoint file_id from metadata (provided by SharePointReader)
                sharepoint_file_id = doc.metadata.get('file_id')
                
                if sharepoint_file_id:
                    # Use SharePoint file_id as the stable path for document tracking
                    # This ensures consistent identification across ingestions
                    stable_path = f"sharepoint://{sharepoint_file_id}"
                    
                    # Store ORIGINAL file_path from SharePointReader (has folder structure)
                    original_path = doc.metadata.get('file_path', '')
                    
                    # Store stable_path separately (not as primary file_path)
                    doc.metadata['stable_file_path'] = stable_path
                    
                    # Determine the human-readable path to use
                    # Priority: 1) from config (_file_path), 2) from Graph API, 3) from SharePointReader (original_path), 4) just filename
                    if '_file_path' in self.config:
                        # From incremental detector - most accurate
                        human_path = self.config['_file_path']
                    elif '_graph_api_path' in doc.metadata:
                        # From Graph API fetch - has full folder structure
                        human_path = doc.metadata['_graph_api_path']
                    elif original_path and not original_path.startswith('/tmp/') and not original_path.startswith('C:\\'):
                        # From SharePointReader - has folder structure if available and not a temp path
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
                    
                    logger.info(f"SharePoint file: stable={stable_path}, human={human_path}, folder={doc.metadata.get('folder_path', 'N/A')}")
                else:
                    logger.warning(f"Document missing file_id in metadata: {doc.metadata}")
                
                # Update metadata - but don't overwrite folder_path if already set
                updates = {
                    "source": "sharepoint",
                    "tenant_id": self.tenant_id,
                    "site_name": self.site_name,
                    "site_id": self.site_id,
                    "source_type": "sharepoint_file"
                }
                # Only add folder_path/folder_id if not already set (preserve the extracted ones)
                if 'folder_path' not in doc.metadata or not doc.metadata['folder_path']:
                    updates["folder_path"] = self.folder_path
                if 'folder_id' not in doc.metadata or not doc.metadata.get('folder_id'):
                    updates["folder_id"] = self.folder_id
                
                doc.metadata.update(updates)
            
            logger.info(f"SharePointSource created {len(documents)} placeholder documents for processing")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from SharePoint site '{self.site_name}': {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from SharePoint with progress tracking.
        SharePoint downloads files directly and extracts actual content.
        
        If file_ids is provided, downloads files directly via Microsoft Graph API
        since SharePointReader doesn't support file_ids parameter.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of Document objects with actual file content
        """
        try:
            # If file_ids is specified, download files directly via Graph API
            if self.file_ids:
                logger.info(f"Downloading {len(self.file_ids)} specific file(s) from SharePoint via Graph API")
                
                # SharePoint downloads files to temp directory, so we need immediate processing
                from document_processor import DocumentProcessor, get_parser_type_from_env
                parser_type = get_parser_type_from_env()
                doc_processor = DocumentProcessor(parser_type=parser_type)
                
                # Create PassthroughExtractor with progress callback AND doc_processor
                from .passthrough_extractor import PassthroughExtractor
                extractor = PassthroughExtractor(
                    progress_callback=progress_callback,
                    doc_processor=doc_processor
                )
                
                documents = []
                for i, file_id in enumerate(self.file_ids):
                    if progress_callback:
                        progress_callback(i, len(self.file_ids), f"Downloading file {i+1}/{len(self.file_ids)}")
                    
                    # Download file content and metadata
                    content, file_metadata = await self._download_file_by_id(file_id)
                    if content:
                        # Save to temp file
                        import tempfile
                        import os
                        from llama_index.core import Document
                        
                        # Get file metadata from config if available
                        file_path = self.config.get('_file_path', f'/{file_id}')
                        folder_path = self.config.get('_folder_path', '/')
                        
                        # Extract filename from path or use metadata name
                        if file_path and file_path != f'/{file_id}':
                            file_name = os.path.basename(file_path)
                        elif file_metadata and 'name' in file_metadata:
                            file_name = file_metadata['name']
                        else:
                            file_name = file_id
                        
                        # Save content to temp file with proper extension
                        suffix = os.path.splitext(file_name)[1] if file_name else '.bin'
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                            tmp.write(content)
                            tmp_path = tmp.name
                        
                        try:
                            # Process file through extractor (which will use doc_processor)
                            # This mimics what SharePointReader does
                            doc = Document(text="placeholder")
                            doc.metadata['file_path'] = tmp_path
                            doc.metadata['file_name'] = file_name
                            doc.metadata['file_id'] = file_id
                            doc.metadata['source'] = 'sharepoint'
                            
                            # Add modified timestamp if available
                            if file_metadata and 'last_modified_datetime' in file_metadata:
                                doc.metadata['last_modified_datetime'] = file_metadata['last_modified_datetime']
                            
                            # Process through extractor (synchronously - it's a BaseReader, not a transformer)
                            # PassthroughExtractor.load_data() processes the file
                            from pathlib import Path
                            processed_docs = extractor.load_data(Path(tmp_path), extra_info=doc.metadata)
                            
                            # Add metadata
                            for doc in processed_docs:
                                stable_path = f"sharepoint://{file_id}"
                                doc.metadata['stable_file_path'] = stable_path
                                doc.metadata['file_path'] = file_path
                                doc.metadata['human_file_path'] = file_path
                                doc.metadata['folder_path'] = folder_path
                                doc.metadata['source'] = 'sharepoint'
                                doc.metadata['tenant_id'] = self.tenant_id
                                doc.metadata['site_name'] = self.site_name
                                doc.metadata['site_id'] = self.site_id
                                doc.metadata['source_type'] = 'sharepoint_file'
                                
                                # Preserve last_modified_datetime if it was set
                                if file_metadata and 'last_modified_datetime' in file_metadata:
                                    doc.metadata['last_modified_datetime'] = file_metadata['last_modified_datetime']
                            
                            documents.extend(processed_docs)
                        finally:
                            # Clean up temp file
                            try:
                                os.unlink(tmp_path)
                            except:
                                pass
                    else:
                        logger.warning(f"Failed to download file {file_id} from SharePoint")
                
                logger.info(f"Downloaded and processed {len(documents)} file(s) from SharePoint")
                return documents
            
            # Normal folder scanning path
            from llama_index.readers.microsoft_sharepoint import SharePointReader
            from .passthrough_extractor import PassthroughExtractor
            
            logger.info(f"Loading documents from SharePoint site '{self.site_name}' with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, f"Connecting to SharePoint site: {self.site_name}")
            
            # SharePoint downloads files to temp directory, so we need immediate processing
            # Create DocumentProcessor for immediate file processing
            from document_processor import DocumentProcessor, get_parser_type_from_env
            parser_type = get_parser_type_from_env()
            doc_processor = DocumentProcessor(parser_type=parser_type)
            
            # Create PassthroughExtractor with progress callback AND doc_processor for immediate processing
            extractor = PassthroughExtractor(progress_callback=progress_callback, doc_processor=doc_processor)
            
            # Initialize SharePointReader with PassthroughExtractor
            # Pass all available SharePoint parameters to constructor
            reader = SharePointReader(
                client_id=self.client_id,
                client_secret=self.client_secret,
                tenant_id=self.tenant_id,
                sharepoint_site_name=self.site_name,
                sharepoint_site_id=self.site_id if self.site_id else None,
                sharepoint_folder_path=self.folder_path if self.folder_path else None,
                sharepoint_folder_id=self.folder_id if self.folder_id else None,
                file_extractor={".pdf": extractor, ".docx": extractor, ".pptx": extractor,
                               ".xlsx": extractor, ".txt": extractor, ".md": extractor,
                               ".html": extractor, ".csv": extractor}
            )
            
            # Use SharePointReader to load documents with actual content (processed immediately by PassthroughExtractor)
            # All parameters already set in constructor, just call load_data()
            documents = reader.load_data()
            
            # Check if documents is None (SharePointReader may return None on error)
            if documents is None:
                logger.error("SharePointReader.load_data() returned None - authentication or loading failed")
                raise ValueError("SharePointReader.load_data() returned None - authentication or loading failed")
            
            logger.info(f"Loaded {len(documents)} SharePoint files from site: {self.site_name}")
            
            # Initialize Graph API client if needed to fetch file metadata (timestamps)
            graph_client = None
            drive = None
            if documents:
                try:
                    from azure.identity.aio import ClientSecretCredential
                    from msgraph import GraphServiceClient
                    
                    credentials = ClientSecretCredential(
                        tenant_id=self.tenant_id,
                        client_id=self.client_id,
                        client_secret=self.client_secret
                    )
                    graph_client = GraphServiceClient(credentials=credentials)
                    
                    # Get the drive once for all files
                    if self.site_id:
                        site = await graph_client.sites.by_site_id(self.site_id).get()
                    elif self.site_name:
                        site = await graph_client.sites.by_site_id(f"root:/sites/{self.site_name}").get()
                    else:
                        raise ValueError("Either site_id or site_name must be specified")
                    
                    drive = await graph_client.sites.by_site_id(site.id).drive.get()
                    logger.info(f"Initialized Graph API client to fetch file modification timestamps")
                except Exception as e:
                    logger.warning(f"Could not initialize Graph API client for metadata: {e}")
            
            # Add source metadata and use stable file_id as path
            for doc in documents:
                # Extract SharePoint file_id from metadata (provided by SharePointReader)
                sharepoint_file_id = doc.metadata.get('file_id')
                
                if sharepoint_file_id:
                    # Fetch file metadata (including last_modified_datetime and path) from Graph API
                    if graph_client and drive:
                        try:
                            file_item = await graph_client.drives.by_drive_id(drive.id).items.by_drive_item_id(sharepoint_file_id).get()
                            if file_item:
                                # Extract last_modified_datetime
                                if hasattr(file_item, 'last_modified_date_time') and file_item.last_modified_date_time:
                                    doc.metadata['last_modified_datetime'] = file_item.last_modified_date_time.isoformat()
                                    logger.info(f"Fetched last_modified_datetime for {sharepoint_file_id}: {doc.metadata['last_modified_datetime']}")
                                
                                # Extract proper file path from parentReference
                                if hasattr(file_item, 'parent_reference') and file_item.parent_reference:
                                    # parentReference has a 'path' field like "/drives/xxx/root:/test"
                                    parent_path = getattr(file_item.parent_reference, 'path', None)
                                    file_name = getattr(file_item, 'name', doc.metadata.get('file_name', ''))
                                    
                                    if parent_path and file_name:
                                        # Extract folder path after "root:" prefix
                                        if '/root:' in parent_path:
                                            folder_path = parent_path.split('/root:')[1]
                                        elif '/root' in parent_path:
                                            folder_path = parent_path.split('/root')[1]
                                        else:
                                            folder_path = '/'
                                        
                                        # Construct full human-readable path
                                        if folder_path == '/' or folder_path == '':
                                            human_path = f"/{file_name}"
                                        else:
                                            human_path = f"{folder_path}/{file_name}"
                                        
                                        doc.metadata['_graph_api_path'] = human_path
                                        logger.info(f"Fetched human-readable path for {sharepoint_file_id}: {human_path}")
                        except Exception as e:
                            logger.warning(f"Could not fetch metadata for file {sharepoint_file_id}: {e}")
                    
                    # Use SharePoint file_id as the stable path for document tracking
                    # This ensures consistent identification across ingestions
                    stable_path = f"sharepoint://{sharepoint_file_id}"
                    
                    # Store ORIGINAL file_path from SharePointReader (has folder structure)
                    original_path = doc.metadata.get('file_path', '')
                    
                    # Store stable_path separately (not as primary file_path)
                    doc.metadata['stable_file_path'] = stable_path
                    
                    # Determine the human-readable path to use
                    # Priority: 1) from config (_file_path), 2) from Graph API, 3) from SharePointReader (original_path), 4) just filename
                    if '_file_path' in self.config:
                        # From incremental detector - most accurate
                        human_path = self.config['_file_path']
                    elif '_graph_api_path' in doc.metadata:
                        # From Graph API fetch - has full folder structure
                        human_path = doc.metadata['_graph_api_path']
                    elif original_path and not original_path.startswith('/tmp/') and not original_path.startswith('C:\\'):
                        # From SharePointReader - has folder structure if available and not a temp path
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
                    
                    logger.info(f"SharePoint file: stable={stable_path}, human={human_path}, folder={doc.metadata.get('folder_path', 'N/A')}")
                else:
                    logger.warning(f"Document missing file_id in metadata: {doc.metadata}")
                
                # Update metadata - but don't overwrite folder_path if already set
                updates = {
                    "source": "sharepoint",
                    "tenant_id": self.tenant_id,
                    "site_name": self.site_name,
                    "site_id": self.site_id,
                    "source_type": "sharepoint_file"
                }
                # Only add folder_path/folder_id if not already set (preserve the extracted ones)
                if 'folder_path' not in doc.metadata or not doc.metadata['folder_path']:
                    updates["folder_path"] = self.folder_path
                if 'folder_id' not in doc.metadata or not doc.metadata.get('folder_id'):
                    updates["folder_id"] = self.folder_id
                
                doc.metadata.update(updates)
            
            logger.info(f"SharePointSource created {len(documents)} placeholder documents for processing")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from SharePoint site '{self.site_name}': {str(e)}")
            raise
