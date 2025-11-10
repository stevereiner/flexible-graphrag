"""
Alfresco data source for Flexible GraphRAG.
"""

from typing import List, Dict, Any
import logging
import tempfile
from llama_index.core import Document

from .base import BaseDataSource
from .filesystem import is_docling_supported

logger = logging.getLogger(__name__)

try:
    from python_alfresco_api import ClientFactory
    # Try to import the direct API functions - these may or may not exist
    try:
        from python_alfresco_api.api.nodes import sync as get_node_sync
        from python_alfresco_api.api.nodes import list_node_children_sync
    except ImportError:
        get_node_sync = None
        list_node_children_sync = None
        logging.info("Using hybrid approach: python-alfresco-api + CMIS for path-based operations")
except ImportError:
    ClientFactory = None
    get_node_sync = None
    list_node_children_sync = None
    logging.warning("python-alfresco-api not installed, Alfresco will use CMIS only")


class AlfrescoSource(BaseDataSource):
    """Data source for Alfresco repositories"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("url", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.path = config.get("path", "/")
        
        # Initialize Alfresco client
        if ClientFactory:
            try:
                factory = ClientFactory(
                    base_url=self.url,
                    username=self.username,
                    password=self.password
                )
                self.client = factory.create_core_client()
                self.nodes_client = self.client.nodes if hasattr(self.client, 'nodes') else None
                logger.info("Successfully connected to Alfresco using python-alfresco-api")
                self.use_api = True
            except Exception as e:
                logger.warning(f"Failed to connect using python-alfresco-api: {str(e)}")
                self.use_api = False
        else:
            self.use_api = False
        
        # Always initialize CMIS for path operations (even if API is available)
        try:
            from cmislib import CmisClient
            import os
            cmis_url = os.getenv("CMIS_URL", f"{self.url.rstrip('/')}/api/-default-/public/cmis/versions/1.1/atom")
            logger.info(f"AlfrescoSource using CMIS URL: {cmis_url}")
            self.cmis_client = CmisClient(cmis_url, self.username, self.password)
            self.cmis_repo = self.cmis_client.defaultRepository
            logger.info("Successfully connected to Alfresco using CMIS for path operations")
        except Exception as e:
            logger.error(f"Failed to connect to Alfresco via CMIS: {str(e)}")
            raise
    
    def validate_config(self) -> bool:
        """Validate the Alfresco source configuration."""
        if not self.url:
            logger.error("No URL specified for Alfresco source")
            return False
        
        if not self.username:
            logger.error("No username specified for Alfresco source")
            return False
        
        if not self.password:
            logger.error("No password specified for Alfresco source")
            return False
        
        return True
    
    def list_files(self) -> List[dict]:
        """List all documents from the Alfresco path or get specific file"""
        try:
            # Use CMIS getObjectByPath for reliable path-based access
            # Check if path points to a specific document
            try:
                obj = self.cmis_repo.getObjectByPath(self.path)
                if obj and obj.properties['cmis:baseTypeId'] == 'cmis:document':
                    # It's a specific document
                    content_type = obj.properties.get('cmis:contentStreamMimeType', '')
                    filename = obj.getName()
                    
                    if is_docling_supported(content_type, filename):
                        logger.info(f"AlfrescoSource found specific document: {filename}")
                        return [{
                            'id': obj.getObjectId(),
                            'name': filename,
                            'path': self.path,
                            'content_type': content_type,
                            'cmis_object': obj,
                            'alfresco_object': None  # Could enhance later with python-alfresco-api
                        }]
                    else:
                        logger.warning(f"Unsupported document type: {filename} ({content_type})")
                        return []
            except:
                # Not a document, proceed as folder
                pass
            
            # Treat as folder - use CMIS for folder operations
            try:
                folder = self.cmis_repo.getObjectByPath(self.path)
                if not folder:
                    raise ValueError(f"Folder not found: {self.path}")
                
                documents = []
                children = folder.getChildren()
                
                for child in children:
                    if child.properties['cmis:baseTypeId'] == 'cmis:document':
                        content_type = child.properties.get('cmis:contentStreamMimeType', '')
                        filename = child.getName()
                        
                        if is_docling_supported(content_type, filename):
                            documents.append({
                                'id': child.getObjectId(),
                                'name': filename,
                                'path': f"{self.path.rstrip('/')}/{filename}",
                                'content_type': content_type,
                                'cmis_object': child,
                                'alfresco_object': None  # Could enhance later with python-alfresco-api
                            })
                    elif child.properties['cmis:baseTypeId'] == 'cmis:folder':
                        # Recursively process subfolders
                        subfolder_path = f"{self.path.rstrip('/')}/{child.getName()}"
                        try:
                            subfolder_source = AlfrescoSource({
                                "url": self.url,
                                "username": self.username,
                                "password": self.password,
                                "path": subfolder_path
                            })
                            documents.extend(subfolder_source.list_files())
                        except Exception as e:
                            logger.warning(f"Error processing subfolder {subfolder_path}: {str(e)}")
                
                logger.info(f"AlfrescoSource found {len(documents)} documents")
                return documents
                
            except Exception as e:
                logger.error(f"Error accessing folder {self.path}: {str(e)}")
                raise
            
        except Exception as e:
            logger.error(f"Error listing Alfresco files: {str(e)}")
            raise
    
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Get documents from Alfresco repository with progress tracking.
        """
        import tempfile
        import os
        
        try:
            if progress_callback:
                progress_callback(
                    current=0,
                    total=1,
                    message="Connecting to Alfresco repository...",
                    current_file=""
                )
            
            # Get file list
            files = self.list_files()
            documents = []
            
            if not files:
                return documents
            
            # Create temporary directory for downloads
            temp_dir = tempfile.mkdtemp(prefix="alfresco_download_")
            
            try:
                # Initialize document processor with configured parser type
                doc_processor = self._get_document_processor()
                
                # Process each file with progress updates
                for i, file_info in enumerate(files):
                    try:
                        if progress_callback:
                            progress_callback(
                                current=i + 1,
                                total=len(files),
                                message=f"Processing document: {file_info['name']}",
                                current_file=file_info['name']
                            )
                        
                        # Download document to temporary file
                        temp_file_path = self._download_document(file_info, temp_dir)
                        
                        # Process the downloaded file (async call)
                        import asyncio
                        processed_docs = await asyncio.get_event_loop().run_in_executor(
                            None, 
                            lambda: asyncio.run(doc_processor.process_documents([temp_file_path]))
                        )
                        if not processed_docs:
                            raise ValueError(f"Failed to process document: {file_info['name']}")
                        processed_doc = processed_docs[0]
                        
                        # Update metadata to include Alfresco information
                        processed_doc.metadata.update({
                            "source": "alfresco",
                            "alfresco_id": file_info['id'],
                            "file_name": file_info['name'],
                            "file_path": file_info['path'],
                            "content_type": file_info['content_type']
                        })
                        
                        documents.append(processed_doc)
                        
                        # Clean up temporary file
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                            
                    except Exception as e:
                        logger.error(f"Error processing Alfresco document {file_info['name']}: {str(e)}")
                        continue
                        
            finally:
                # Clean up temporary directory
                try:
                    if os.path.exists(temp_dir):
                        os.rmdir(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
            
            logger.info(f"AlfrescoSource processed {len(files)} files ({len(documents)} chunks)")
            return (len(files), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error getting Alfresco documents with progress: {str(e)}")
            raise
    
    def get_documents(self) -> List[Document]:
        """
        Get documents from Alfresco repository by downloading and processing them.
        """
        import tempfile
        import os
        
        files = self.list_files()
        documents = []
        
        # Create temporary directory for downloads
        temp_dir = tempfile.mkdtemp(prefix="alfresco_download_")
        
        try:
            # Initialize document processor with configured parser type
            doc_processor = self._get_document_processor()
            
            for file_info in files:
                try:
                    # Download document to temporary file
                    temp_file_path = self._download_document(file_info, temp_dir)
                    
                    # Process the downloaded file
                    processed_doc = doc_processor.process_file(temp_file_path)
                    
                    # Update metadata to include Alfresco information
                    processed_doc.metadata.update({
                        "source": "alfresco",
                        "alfresco_id": file_info['id'],
                        "file_name": file_info['name'],
                        "file_path": file_info['path'],
                        "content_type": file_info['content_type']
                    })
                    
                    documents.append(processed_doc)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        
                except Exception as e:
                    logger.error(f"Error processing Alfresco document {file_info['name']}: {str(e)}")
                    continue
                    
        finally:
            # Clean up temporary directory
            try:
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
        
        return documents
    
    def _download_document(self, document: dict, temp_dir: str) -> str:
        """Download an Alfresco document to a temporary file and return the file path"""
        import tempfile
        import os
        
        try:
            filename = document['name']
            node_id = document['id']
            
            # Determine file extension from filename or content type
            file_ext = ''
            if '.' in filename:
                file_ext = '.' + filename.split('.')[-1]
            elif 'pdf' in document['content_type'].lower():
                file_ext = '.pdf'
            elif 'docx' in document['content_type'].lower():
                file_ext = '.docx'
            elif 'pptx' in document['content_type'].lower():
                file_ext = '.pptx'
            elif 'text' in document['content_type'].lower():
                file_ext = '.txt'
            elif 'markdown' in document['content_type'].lower():
                file_ext = '.md'
            
            # Create temporary file with original filename for LlamaParse display
            # Use original filename so it appears correctly in LlamaCloud
            temp_file_path = os.path.join(temp_dir, filename)
            temp_file = open(temp_file_path, 'wb')
            
            # Try python-alfresco-api first if available
            content_downloaded = False
            if self.use_api and self.nodes_client:
                try:
                    content_response = self.nodes_client.get_content(node_id=node_id)
                    if content_response and hasattr(content_response, 'content'):
                        temp_file.write(content_response.content)
                        content_downloaded = True
                        logger.info(f"Downloaded via python-alfresco-api: {filename}")
                except Exception as e:
                    logger.debug(f"python-alfresco-api download failed: {str(e)}, trying CMIS")
            
            # Fall back to CMIS if python-alfresco-api didn't work
            if not content_downloaded and 'cmis_object' in document:
                cmis_object = document['cmis_object']
                content_stream = cmis_object.getContentStream()
                if content_stream:
                    temp_file.write(content_stream.read())
                    content_stream.close()
                    content_downloaded = True
                    logger.info(f"Downloaded via CMIS: {filename}")
            
            if content_downloaded:
                temp_file.flush()
                temp_file.close()
                logger.info(f"Downloaded Alfresco document {filename} to {temp_file_path}")
                return temp_file_path
            else:
                temp_file.close()
                os.unlink(temp_file_path)
                raise ValueError(f"No content available for document: {filename}")
                
        except Exception as e:
            logger.error(f"Error downloading Alfresco document {document.get('name', 'unknown')}: {str(e)}")
            raise
