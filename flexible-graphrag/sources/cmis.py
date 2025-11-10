"""
CMIS data source for Flexible GraphRAG.
"""

from typing import List, Dict, Any
import logging
from llama_index.core import Document
from cmislib import CmisClient

from .base import BaseDataSource
from .filesystem import is_docling_supported

logger = logging.getLogger(__name__)


class CmisSource(BaseDataSource):
    """Data source for CMIS repositories"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("url", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.folder_path = config.get("folder_path", "/")
        
        try:
            self.client = CmisClient(self.url, self.username, self.password)
            self.repo = self.client.getDefaultRepository()
            logger.info("Successfully connected to CMIS repository")
        except Exception as e:
            logger.error(f"Failed to connect to CMIS repository: {str(e)}")
            raise
    
    def validate_config(self) -> bool:
        """Validate the CMIS source configuration."""
        if not self.url:
            logger.error("No URL specified for CMIS source")
            return False
        
        if not self.username:
            logger.error("No username specified for CMIS source")
            return False
        
        if not self.password:
            logger.error("No password specified for CMIS source")
            return False
        
        return True
    
    def is_document_supported(self, content_type: str, filename: str) -> bool:
        """Check if document type is supported by Docling"""
        return is_docling_supported(content_type, filename)
    
    def get_document_by_path(self, document_path: str) -> dict:
        """Get a specific document by its full path"""
        try:
            doc_object = self.repo.getObjectByPath(document_path)
            if not doc_object:
                raise ValueError(f"Document not found: {document_path}")
            
            if doc_object.properties['cmis:baseTypeId'] != 'cmis:document':
                raise ValueError(f"Path does not point to a document: {document_path}")
            
            content_type = doc_object.properties.get('cmis:contentStreamMimeType', '')
            filename = doc_object.getName()
            
            if not self.is_document_supported(content_type, filename):
                raise ValueError(f"Unsupported document type: {filename} ({content_type})")
            
            return {
                'id': doc_object.getObjectId(),
                'name': filename,
                'path': document_path,
                'content_type': content_type,
                'cmis_object': doc_object
            }
            
        except Exception as e:
            logger.error(f"Error getting CMIS document by path {document_path}: {str(e)}")
            raise
    
    def list_files(self) -> List[dict]:
        """List all documents from the CMIS folder or get specific file"""
        try:
            # Check if folder_path points to a specific document
            try:
                folder_or_doc = self.repo.getObjectByPath(self.folder_path)
                if folder_or_doc and folder_or_doc.properties['cmis:baseTypeId'] == 'cmis:document':
                    # It's a specific document
                    content_type = folder_or_doc.properties.get('cmis:contentStreamMimeType', '')
                    filename = folder_or_doc.getName()
                    
                    if self.is_document_supported(content_type, filename):
                        logger.info(f"CmisSource found specific document: {filename}")
                        return [{
                            'id': folder_or_doc.getObjectId(),
                            'name': filename,
                            'path': self.folder_path,
                            'content_type': content_type,
                            'cmis_object': folder_or_doc
                        }]
                    else:
                        logger.warning(f"Unsupported document type: {filename} ({content_type})")
                        return []
            except Exception:
                # Not a document, continue as folder
                pass
            
            # It's a folder - list all documents
            folder = self.repo.getObjectByPath(self.folder_path)
            if not folder:
                raise ValueError(f"Folder not found: {self.folder_path}")
            
            documents = []
            
            def process_folder(folder_obj, current_path=""):
                """Recursively process folder and its children"""
                try:
                    children = folder_obj.getChildren()
                    for child in children:
                        child_name = child.getName()
                        child_path = f"{current_path}/{child_name}" if current_path else child_name
                        
                        if child.properties['cmis:baseTypeId'] == 'cmis:document':
                            # It's a document
                            content_type = child.properties.get('cmis:contentStreamMimeType', '')
                            
                            if self.is_document_supported(content_type, child_name):
                                documents.append({
                                    'id': child.getObjectId(),
                                    'name': child_name,
                                    'path': f"{self.folder_path.rstrip('/')}/{child_path}",
                                    'content_type': content_type,
                                    'cmis_object': child
                                })
                                logger.info(f"Found supported document: {child_name}")
                            else:
                                logger.info(f"Skipping unsupported document: {child_name} ({content_type})")
                        
                        elif child.properties['cmis:baseTypeId'] == 'cmis:folder':
                            # It's a folder - recurse
                            logger.info(f"Processing subfolder: {child_name}")
                            process_folder(child, child_path)
                
                except Exception as e:
                    logger.warning(f"Error processing folder {current_path}: {str(e)}")
            
            process_folder(folder)
            
            logger.info(f"CmisSource found {len(documents)} supported documents")
            return documents
            
        except Exception as e:
            logger.error(f"Error listing CMIS documents: {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Get documents from CMIS repository with progress tracking.
        """
        import tempfile
        import os
        
        try:
            if progress_callback:
                progress_callback(
                    current=0,
                    total=1,
                    message="Connecting to CMIS repository...",
                    current_file=""
                )
            
            # Get file list
            files = self.list_files()
            documents = []
            
            if not files:
                return documents
            
            # Create temporary directory for downloads
            temp_dir = tempfile.mkdtemp(prefix="cmis_download_")
            
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
                        
                        # Update metadata to include CMIS information
                        processed_doc.metadata.update({
                            "source": "cmis",
                            "cmis_id": file_info['id'],
                            "file_name": file_info['name'],
                            "file_path": file_info['path'],
                            "content_type": file_info['content_type']
                        })
                        
                        documents.append(processed_doc)
                        
                        # Clean up temporary file
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                            
                    except Exception as e:
                        logger.error(f"Error processing CMIS document {file_info['name']}: {str(e)}")
                        continue
                        
            finally:
                # Clean up temporary directory
                try:
                    if os.path.exists(temp_dir):
                        os.rmdir(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
            
            logger.info(f"CmisSource processed {len(files)} files ({len(documents)} chunks)")
            return (len(files), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error getting CMIS documents with progress: {str(e)}")
            raise
    
    def get_documents(self) -> List[Document]:
        """
        Get documents from CMIS repository by downloading and processing them.
        """
        import tempfile
        import os
        
        files = self.list_files()
        documents = []
        
        # Create temporary directory for downloads
        temp_dir = tempfile.mkdtemp(prefix="cmis_download_")
        
        try:
            # Initialize document processor with configured parser type
            doc_processor = self._get_document_processor()
            
            for file_info in files:
                try:
                    # Download document to temporary file
                    temp_file_path = self._download_document(file_info, temp_dir)
                    
                    # Process the downloaded file
                    processed_doc = doc_processor.process_file(temp_file_path)
                    
                    # Update metadata to include CMIS information
                    processed_doc.metadata.update({
                        "source": "cmis",
                        "cmis_id": file_info['id'],
                        "file_name": file_info['name'],
                        "file_path": file_info['path'],
                        "content_type": file_info['content_type']
                    })
                    
                    documents.append(processed_doc)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        
                except Exception as e:
                    logger.error(f"Error processing CMIS document {file_info['name']}: {str(e)}")
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
        """Download a CMIS document to a temporary file and return the file path"""
        import tempfile
        import os
        
        try:
            cmis_object = document['cmis_object']
            filename = document['name']
            
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
            
            # Download content
            content_stream = cmis_object.getContentStream()
            if content_stream:
                content = content_stream.read()
                temp_file.write(content)
                temp_file.flush()
                temp_file.close()
                
                logger.info(f"Downloaded CMIS document {filename} to {temp_file_path}")
                return temp_file_path
            else:
                temp_file.close()
                os.unlink(temp_file_path)
                raise ValueError(f"No content stream available for document: {filename}")
                
        except Exception as e:
            logger.error(f"Error downloading CMIS document {document.get('name', 'unknown')}: {str(e)}")
            raise
