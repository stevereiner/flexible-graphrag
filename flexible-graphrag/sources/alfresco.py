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
    from python_alfresco_api.utils import content_utils
except ImportError:
    ClientFactory = None
    content_utils = None
    logging.warning("python-alfresco-api not installed, Alfresco will use CMIS only")


class AlfrescoSource(BaseDataSource):
    """Data source for Alfresco repositories"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("url", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.path = config.get("path", "/")
        self.node_details = config.get("nodeDetails", None)  # Multi-select from ACA/ADF
        self.node_refs = config.get("nodeRefs", None)  # Node IDs for multi-select
        self.recursive = config.get("recursive", False)  # Whether to recursively process subfolders (default: False)
        
        logger.info("=== INITIALIZING ALFRESCO SOURCE ===")
        logger.info(f"URL: {self.url}")
        logger.info(f"Username: {self.username}")
        logger.info(f"Path: {self.path}")
        logger.info(f"Recursive: {self.recursive}")
        logger.info(f"Has nodeDetails: {self.node_details is not None}")
        if self.node_details:
            logger.info(f"Number of nodeDetails: {len(self.node_details)}")
            for idx, nd in enumerate(self.node_details, 1):
                logger.info(f"  NodeDetail {idx}: {nd.get('name')} (id: {nd.get('id')}, isFile: {nd.get('isFile')}, isFolder: {nd.get('isFolder')})")
        logger.info(f"Has nodeRefs: {self.node_refs is not None}")
        if self.node_refs:
            logger.info(f"Number of nodeRefs: {len(self.node_refs)}")
        
        # Initialize Alfresco client
        logger.info("--- Initializing Alfresco REST API ---")
        logger.info(f"ClientFactory available: {ClientFactory is not None}")
        
        if ClientFactory:
            try:
                # Fix: Remove /alfresco from base_url if present, as the library adds it
                api_base_url = self.url.rstrip('/')
                if api_base_url.endswith('/alfresco'):
                    api_base_url = api_base_url[:-9]  # Remove '/alfresco'
                    logger.info(f"Adjusted base_url for API: {api_base_url} (removed /alfresco suffix)")
                
                logger.info(f"Creating ClientFactory with base_url: {api_base_url}")
                factory = ClientFactory(
                    base_url=api_base_url,
                    username=self.username,
                    password=self.password
                )
                logger.info("ClientFactory created successfully")
                
                logger.info("Creating core client...")
                self.core_client = factory.create_core_client()
                logger.info(f"Core client created: {type(self.core_client)}")
                logger.info(f"Core client has 'nodes' property: {hasattr(self.core_client, 'nodes')}")
                
                logger.info("[OK] Successfully connected to Alfresco using python-alfresco-api")
                self.use_api = True
            except Exception as e:
                logger.warning(f"[FAIL] Failed to connect using python-alfresco-api: {str(e)}", exc_info=True)
                self.core_client = None
                self.use_api = False
        else:
            logger.info("ClientFactory not available - skipping Alfresco REST API initialization")
            self.core_client = None
            self.use_api = False
        
        logger.info(f"Final use_api value: {self.use_api}")
        logger.info(f"Final core_client available: {self.core_client is not None}")
        
        # Lazy initialization - CMIS will be initialized only when needed
        self.cmis_client = None
        self.cmis_repo = None
        
        logger.info("=== ALFRESCO SOURCE INITIALIZATION COMPLETE ===")
        logger.info(f"Summary: use_api={self.use_api}, has_core_client={self.core_client is not None}")
    
    def _ensure_cmis_initialized(self):
        """Lazy initialization of CMIS client - only when needed"""
        if self.cmis_repo is not None:
            return  # Already initialized
        
        logger.info("--- Initializing CMIS (lazy init) ---")
        try:
            from cmislib import CmisClient
            import os
            cmis_url = os.getenv("CMIS_URL", f"{self.url.rstrip('/')}/api/-default-/public/cmis/versions/1.1/atom")
            logger.info(f"CMIS URL: {cmis_url}")
            logger.info(f"Creating CMIS client...")
            self.cmis_client = CmisClient(cmis_url, self.username, self.password)
            logger.info("CMIS client created, getting default repository...")
            self.cmis_repo = self.cmis_client.defaultRepository
            logger.info(f"Default repository: {self.cmis_repo}")
            logger.info("[OK] Successfully connected to Alfresco using CMIS for path operations")
        except Exception as e:
            logger.error(f"[FAIL] Failed to connect to Alfresco via CMIS: {str(e)}", exc_info=True)
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
            # NEW: Process specific files/folders using nodeDetails
            if self.node_details:
                logger.info(f"=== NODEDETAILS MODE ACTIVE ===")
                logger.info(f"Processing {len(self.node_details)} nodes from nodeDetails")
                logger.info(f"Recursive mode: {self.recursive}")
                logger.info(f"Use Alfresco API: {self.use_api}")
                logger.info(f"Has core_client: {self.core_client is not None}")
                
                documents = []
                
                for idx, node in enumerate(self.node_details, 1):
                    logger.info(f"--- Node {idx}/{len(self.node_details)} ---")
                    logger.info(f"Node ID: {node['id']}")
                    logger.info(f"Node name: {node['name']}")
                    logger.info(f"Node path: {node['path']}")
                    logger.info(f"Is file: {node['isFile']}, Is folder: {node['isFolder']}")
                    
                    if node['isFile']:
                        # Process this specific file using node ID (Alfresco API)
                        logger.info(f"Routing to _process_file_by_id() for file: {node['name']}")
                        file_doc = self._process_file_by_id(node['id'], node['path'], node['name'])
                        if file_doc:
                            logger.info(f"Successfully processed file: {node['name']}")
                            documents.append(file_doc)
                        else:
                            logger.warning(f"Failed to process or unsupported file: {node['name']}")
                    elif node['isFolder']:
                        # Process all files in this folder using node ID (Alfresco API)
                        logger.info(f"Routing to _process_folder_by_id() for folder: {node['name']}")
                        folder_docs = self._process_folder_by_id(node['id'], node['path'], node['name'])
                        logger.info(f"Folder {node['name']} returned {len(folder_docs)} documents")
                        documents.extend(folder_docs)
                    else:
                        logger.warning(f"Node {node['name']} is neither file nor folder - skipping")
                
                logger.info(f"=== NODEDETAILS MODE COMPLETE ===")
                logger.info(f"AlfrescoSource found {len(documents)} documents from nodeDetails")
                return documents
            
            # OLD: Use the single path (backward compatibility)
            logger.info(f"=== BACKWARD COMPATIBLE PATH MODE ===")
            logger.info(f"Using single path mode: {self.path}")
            logger.info(f"Recursive mode: {self.recursive}")
            return self._process_folder_by_path(self.path)
            
        except Exception as e:
            logger.error(f"Error listing Alfresco files: {str(e)}", exc_info=True)
            raise
    
    def _process_folder_by_id(self, node_id: str, path: str, name: str) -> List[dict]:
        """Process all files in a folder by node ID using Alfresco REST API"""
        try:
            logger.info(f">>> _process_folder_by_id() START")
            logger.info(f"    Folder: {name}")
            logger.info(f"    Node ID: {node_id}")
            logger.info(f"    Path: {path}")
            logger.info(f"    Recursive: {self.recursive}")
            
            # Try Alfresco REST API first (more efficient with node ID)
            if self.use_api and self.core_client:
                try:
                    logger.info(f"Attempting Alfresco REST API list_children for folder: {name}")
                    logger.info(f"Calling: self.core_client.nodes.list_children(node_id='{node_id}')")
                    
                    # Get folder children using Alfresco REST API
                    children_response = self.core_client.nodes.list_children(node_id=node_id)
                    
                    logger.info(f"API Response type: {type(children_response)}")
                    logger.info(f"Has 'list' attr: {hasattr(children_response, 'list')}")
                    
                    if hasattr(children_response, 'list'):
                        logger.info(f"children_response.list type: {type(children_response.list)}")
                        logger.info(f"children_response.list keys: {children_response.list.keys() if isinstance(children_response.list, dict) else 'not a dict'}")
                    
                    # The response structure is: NodeListResponse.list (dict) -> 'entries' (list)
                    if children_response and hasattr(children_response, 'list') and isinstance(children_response.list, dict):
                        entries = children_response.list.get('entries', [])
                        logger.info(f"Found {len(entries)} entries in response")
                        
                        if entries:
                            logger.info(f"Successfully retrieved children for folder: {name}")
                            logger.info(f"Number of entries: {len(entries)}")
                            
                            documents = []
                            
                            for idx, child_data in enumerate(entries, 1):
                                # Each entry is a dict with 'entry' key containing the node data
                                if not isinstance(child_data, dict) or 'entry' not in child_data:
                                    logger.warning(f"  Skipping invalid child data at index {idx}")
                                    continue
                                    
                                entry = child_data['entry']
                                child_id = entry.get('id')
                                child_name = entry.get('name')
                                child_path = f"{path.rstrip('/')}/{child_name}"
                                is_file = entry.get('isFile', False)
                                is_folder = entry.get('isFolder', False)
                                
                                logger.info(f"  Child {idx}: {child_name} (id: {child_id})")
                                logger.info(f"    is_file: {is_file}, is_folder: {is_folder}")
                                
                                if is_file:
                                    # Process file
                                    content_type = entry.get('content', {}).get('mimeType', '') if isinstance(entry.get('content'), dict) else ''
                                    logger.info(f"    Content type: {content_type}")
                                    
                                    if is_docling_supported(content_type, child_name):
                                        logger.info(f"    [+] Supported - adding to documents list")
                                        documents.append({
                                            'id': child_id,
                                            'name': child_name,
                                            'path': child_path,
                                            'content_type': content_type,
                                            'cmis_object': None,
                                            'alfresco_object': child_data
                                        })
                                    else:
                                        logger.info(f"    [-] Unsupported file type - skipping")
                                        
                                elif is_folder and self.recursive:
                                    # Only recursively process subfolders if recursive=True
                                    logger.info(f"    [>>] Recursing into subfolder (recursive=True)")
                                    subfolder_docs = self._process_folder_by_id(child_id, child_path, child_name)
                                    logger.info(f"    [<<] Returned {len(subfolder_docs)} docs from subfolder")
                                    documents.extend(subfolder_docs)
                                elif is_folder:
                                    # Skip subfolder if recursive=False
                                    logger.info(f"    [SKIP] Skipping subfolder (recursive=False)")
                            
                            logger.info(f"<<< _process_folder_by_id() COMPLETE via Alfresco API")
                            logger.info(f"    Total documents found: {len(documents)}")
                            return documents
                        else:
                            logger.info(f"No entries found in folder: {name}")
                            return []
                        
                except Exception as e:
                    logger.warning(f"Alfresco API folder listing failed for {node_id}: {str(e)}", exc_info=True)
                    logger.info(f"Attempting CMIS fallback...")
            else:
                logger.info(f"Alfresco API not available (use_api={self.use_api}, core_client={self.core_client is not None})")
                logger.info(f"Skipping to CMIS fallback...")
            
            # Fallback to CMIS using path
            logger.info(f"Using CMIS fallback for folder: {name}")
            result = self._process_folder_by_path(path)
            logger.info(f"<<< _process_folder_by_id() COMPLETE via CMIS fallback")
            logger.info(f"    Total documents found: {len(result)}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing folder {name} (id: {node_id}): {str(e)}", exc_info=True)
            raise
    
    def _process_file_by_id(self, node_id: str, path: str, name: str) -> dict:
        """Process a specific file by node ID using Alfresco REST API"""
        try:
            logger.info(f">>> _process_file_by_id() START")
            logger.info(f"    File: {name}")
            logger.info(f"    Node ID: {node_id}")
            logger.info(f"    Path: {path}")
            
            # Try Alfresco REST API first (more efficient with node ID)
            if self.use_api and self.core_client:
                try:
                    logger.info(f"Attempting Alfresco REST API get for file: {name}")
                    logger.info(f"Calling: self.core_client.nodes.get(node_id='{node_id}')")
                    
                    # Get node info using Alfresco REST API with node ID
                    node_info = self.core_client.nodes.get(node_id=node_id)
                    
                    logger.info(f"API Response type: {type(node_info)}")
                    logger.info(f"Has 'entry' attr: {hasattr(node_info, 'entry')}")
                    
                    if node_info and hasattr(node_info, 'entry'):
                        entry = node_info.entry
                        logger.info(f"Retrieved node entry for: {name}")
                        logger.info(f"    entry.is_file: {entry.is_file}")
                        logger.info(f"    entry.is_folder: {entry.is_folder}")
                        
                        # Check if it's a file (document)
                        if entry.is_file:
                            content_type = entry.content.mime_type if hasattr(entry, 'content') else ''
                            logger.info(f"    Content type: {content_type}")
                            
                            if is_docling_supported(content_type, name):
                                logger.info(f"    [+] Supported document type - returning file metadata")
                                logger.info(f"<<< _process_file_by_id() SUCCESS via Alfresco API")
                                return {
                                    'id': node_id,
                                    'name': name,
                                    'path': path,
                                    'content_type': content_type,
                                    'cmis_object': None,
                                    'alfresco_object': node_info
                                }
                            else:
                                logger.warning(f"    [-] Unsupported document type: {name} ({content_type})")
                                logger.info(f"<<< _process_file_by_id() FAILED - unsupported type")
                                return None
                        else:
                            logger.warning(f"Node {node_id} is not a file (is_file={entry.is_file})")
                            logger.info(f"<<< _process_file_by_id() FAILED - not a file")
                            return None
                    else:
                        logger.warning(f"API returned node_info without entry attribute")
                            
                except Exception as e:
                    logger.warning(f"Alfresco API failed for node {node_id}: {str(e)}", exc_info=True)
                    logger.info(f"Attempting CMIS fallback...")
            else:
                logger.info(f"Alfresco API not available (use_api={self.use_api}, core_client={self.core_client is not None})")
                logger.info(f"Skipping to CMIS fallback...")
            
            # Fallback to CMIS using path
            logger.info(f"Using CMIS fallback for file: {name}")
            logger.info(f"Calling: self.cmis_repo.getObjectByPath('{path}')")
            
            # Ensure CMIS is initialized before using it
            self._ensure_cmis_initialized()
            
            obj = self.cmis_repo.getObjectByPath(path)
            logger.info(f"CMIS object retrieved: {obj is not None}")
            
            if obj and obj.properties['cmis:baseTypeId'] == 'cmis:document':
                content_type = obj.properties.get('cmis:contentStreamMimeType', '')
                logger.info(f"    Content type: {content_type}")
                
                if is_docling_supported(content_type, name):
                    logger.info(f"    [+] Supported document type - returning file metadata")
                    logger.info(f"<<< _process_file_by_id() SUCCESS via CMIS")
                    return {
                        'id': node_id,
                        'name': name,
                        'path': path,
                        'content_type': content_type,
                        'cmis_object': obj,
                        'alfresco_object': None
                    }
                else:
                    logger.warning(f"    [-] Unsupported document type: {name} ({content_type})")
                    logger.info(f"<<< _process_file_by_id() FAILED - unsupported type")
                    return None
            else:
                base_type = obj.properties.get('cmis:baseTypeId', 'unknown') if obj else 'no object'
                logger.warning(f"Node at path {path} is not a document (baseTypeId: {base_type})")
                logger.info(f"<<< _process_file_by_id() FAILED - not a document")
                return None
                
        except Exception as e:
            logger.error(f"Error processing file {name} (id: {node_id}): {str(e)}", exc_info=True)
            logger.info(f"<<< _process_file_by_id() FAILED - exception")
            return None
    
    def _process_folder_by_path(self, folder_path: str) -> List[dict]:
        """Process all files in a folder by path"""
        try:
            logger.info(f">>> _process_folder_by_path() START")
            logger.info(f"    Path: {folder_path}")
            logger.info(f"    Recursive: {self.recursive}")
            logger.info(f"    Use API: {self.use_api}")
            
            # Try Alfresco REST API with relative_path first (python-alfresco-api 1.1.5+)
            if self.use_api and self.core_client:
                try:
                    logger.info(f"Attempting Alfresco REST API with relative_path feature")
                    
                    # Remove leading slash and /Company Home prefix if present
                    # Note: -root- IS Company Home, so paths should be relative to it
                    relative_path = folder_path.lstrip('/')
                    
                    # Strip "Company Home/" prefix if present (case-insensitive)
                    if relative_path.lower().startswith('company home/'):
                        relative_path = relative_path[13:]  # Remove "Company Home/"
                        logger.info(f"    Stripped 'Company Home/' prefix from path")
                    
                    logger.info(f"    Using relative_path: '{relative_path}' from -root-")
                    
                    # Get node using relative_path from root (-root- IS Company Home)
                    logger.info(f"Calling: self.core_client.nodes.get('-root-', relative_path='{relative_path}')")
                    node_info = self.core_client.nodes.get("-root-", relative_path=relative_path)
                    
                    if node_info and hasattr(node_info, 'entry'):
                        entry = node_info.entry
                        node_id = entry.id
                        logger.info(f"[OK] Successfully retrieved node via relative_path")
                        logger.info(f"    Node ID: {node_id}")
                        logger.info(f"    Node name: {entry.name}")
                        logger.info(f"    Is file: {entry.is_file}, Is folder: {entry.is_folder}")
                        
                        # Check if it's a file (document)
                        if entry.is_file:
                            logger.info(f"Path points to a file - processing as single document")
                            content_type = entry.content.mime_type if hasattr(entry, 'content') else ''
                            filename = entry.name
                            
                            if is_docling_supported(content_type, filename):
                                logger.info(f"<<< _process_folder_by_path() SUCCESS via Alfresco API (file)")
                                return [{
                                    'id': node_id,
                                    'name': filename,
                                    'path': folder_path,
                                    'content_type': content_type,
                                    'cmis_object': None,
                                    'alfresco_object': node_info
                                }]
                            else:
                                logger.warning(f"Unsupported document type: {filename} ({content_type})")
                                return []
                        
                        # It's a folder - use the more efficient _process_folder_by_id
                        elif entry.is_folder:
                            logger.info(f"Path points to a folder - delegating to _process_folder_by_id()")
                            result = self._process_folder_by_id(node_id, folder_path, entry.name)
                            logger.info(f"<<< _process_folder_by_path() SUCCESS via Alfresco API (folder)")
                            logger.info(f"    Total documents: {len(result)}")
                            return result
                        
                except Exception as e:
                    logger.warning(f"Alfresco API relative_path failed for {folder_path}: {str(e)}", exc_info=True)
                    logger.info(f"Falling back to CMIS...")
            else:
                logger.info(f"Alfresco API not available (use_api={self.use_api}, core_client={self.core_client is not None})")
                logger.info(f"Skipping to CMIS fallback...")
            
            # Fallback to CMIS getObjectByPath for backward compatibility
            logger.info(f"Using CMIS fallback for path: {folder_path}")
            
            # Ensure CMIS is initialized before using it
            self._ensure_cmis_initialized()
            
            # Use CMIS getObjectByPath for reliable path-based access
            # Check if path points to a specific document
            try:
                obj = self.cmis_repo.getObjectByPath(folder_path)
                if obj and obj.properties['cmis:baseTypeId'] == 'cmis:document':
                    # It's a specific document
                    content_type = obj.properties.get('cmis:contentStreamMimeType', '')
                    filename = obj.getName()
                    
                    if is_docling_supported(content_type, filename):
                        logger.info(f"AlfrescoSource found specific document: {filename}")
                        return [{
                            'id': obj.getObjectId(),
                            'name': filename,
                            'path': folder_path,
                            'content_type': content_type,
                            'cmis_object': obj,
                            'alfresco_object': None
                        }]
                    else:
                        logger.warning(f"Unsupported document type: {filename} ({content_type})")
                        return []
            except:
                # Not a document, proceed as folder
                pass
            
            # Treat as folder - use CMIS for folder operations
            try:
                folder = self.cmis_repo.getObjectByPath(folder_path)
                if not folder:
                    raise ValueError(f"Folder not found: {folder_path}")
                
                logger.info(f"Processing folder via CMIS: {folder_path} (recursive: {self.recursive})")
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
                                'path': f"{folder_path.rstrip('/')}/{filename}",
                                'content_type': content_type,
                                'cmis_object': child,
                                'alfresco_object': None
                            })
                    elif child.properties['cmis:baseTypeId'] == 'cmis:folder' and self.recursive:
                        # Only recursively process subfolders if recursive=True
                        subfolder_path = f"{folder_path.rstrip('/')}/{child.getName()}"
                        try:
                            subfolder_source = AlfrescoSource({
                                "url": self.url,
                                "username": self.username,
                                "password": self.password,
                                "path": subfolder_path,
                                "recursive": self.recursive  # Pass recursive flag to subfolder
                            })
                            documents.extend(subfolder_source.list_files())
                        except Exception as e:
                            logger.warning(f"Error processing subfolder {subfolder_path}: {str(e)}")
                    elif child.properties['cmis:baseTypeId'] == 'cmis:folder':
                        # Skip subfolder if recursive=False
                        logger.debug(f"Skipping subfolder (recursive=False): {child.getName()}")
                
                logger.info(f"<<< _process_folder_by_path() SUCCESS via CMIS")
                logger.info(f"    Total documents: {len(documents)}")
                return documents
                
            except Exception as e:
                logger.error(f"<<< _process_folder_by_path() FAILED - CMIS error")
                logger.error(f"Error accessing folder {folder_path}: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"<<< _process_folder_by_path() FAILED - exception")
            logger.error(f"Error processing folder {folder_path}: {str(e)}")
            raise
    
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Get documents from Alfresco repository with progress tracking.
        """
        import tempfile
        import os
        
        try:
            logger.info("=== GET_DOCUMENTS_WITH_PROGRESS START ===")
            
            if progress_callback:
                progress_callback(
                    current=0,
                    total=1,
                    message="Connecting to Alfresco repository...",
                    current_file=""
                )
            
            # Get file list
            logger.info("Calling list_files()...")
            files = self.list_files()
            logger.info(f"list_files() returned {len(files)} files")
            
            documents = []
            
            if not files:
                logger.info("No files to process - returning empty list")
                return documents
            
            # Create temporary directory for downloads
            temp_dir = tempfile.mkdtemp(prefix="alfresco_download_")
            logger.info(f"Created temporary directory: {temp_dir}")
            
            try:
                # Initialize document processor with configured parser type
                logger.info("Getting document processor...")
                doc_processor = self._get_document_processor()
                logger.info(f"Document processor: {type(doc_processor)}")
                
                # Process each file with progress updates
                for i, file_info in enumerate(files):
                    try:
                        logger.info(f"=== Processing file {i+1}/{len(files)} ===")
                        logger.info(f"File: {file_info['name']}")
                        logger.info(f"ID: {file_info['id']}")
                        logger.info(f"Path: {file_info['path']}")
                        logger.info(f"Content type: {file_info['content_type']}")
                        
                        if progress_callback:
                            progress_callback(
                                current=i + 1,
                                total=len(files),
                                message=f"Processing document: {file_info['name']}",
                                current_file=file_info['name']
                            )
                        
                        # Download document to temporary file
                        logger.info(f"Downloading document: {file_info['name']}")
                        temp_file_path = self._download_document(file_info, temp_dir)
                        logger.info(f"Downloaded to: {temp_file_path}")
                        
                        # Process the downloaded file (async call)
                        logger.info(f"Processing document with doc_processor...")
                        import asyncio
                        processed_docs = await asyncio.get_event_loop().run_in_executor(
                            None, 
                            lambda: asyncio.run(doc_processor.process_documents([temp_file_path]))
                        )
                        logger.info(f"Doc processor returned {len(processed_docs) if processed_docs else 0} documents")
                        
                        if not processed_docs:
                            raise ValueError(f"Failed to process document: {file_info['name']}")
                        processed_doc = processed_docs[0]
                        
                        # Update metadata to include Alfresco information
                        logger.info(f"Updating document metadata...")
                        processed_doc.metadata.update({
                            "source": "alfresco",
                            "alfresco_id": file_info['id'],
                            "file_name": file_info['name'],
                            "file_path": file_info['path'],
                            "content_type": file_info['content_type']
                        })
                        logger.info(f"Metadata updated: {processed_doc.metadata}")
                        
                        documents.append(processed_doc)
                        logger.info(f"[OK] Successfully processed document {i+1}/{len(files)}")
                        
                        # Clean up temporary file
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                            logger.info(f"Cleaned up temp file: {temp_file_path}")
                            
                    except Exception as e:
                        logger.error(f"[ERROR] Error processing Alfresco document {file_info['name']}: {str(e)}", exc_info=True)
                        continue
                        
            finally:
                # Clean up temporary directory
                try:
                    if os.path.exists(temp_dir):
                        os.rmdir(temp_dir)
                        logger.info(f"Cleaned up temp directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
            
            logger.info(f"=== GET_DOCUMENTS_WITH_PROGRESS COMPLETE ===")
            logger.info(f"Processed {len(files)} files into {len(documents)} document chunks")
            logger.info(f"Returning tuple: ({len(files)}, {len(documents)} documents)")
            return (len(files), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error getting Alfresco documents with progress: {str(e)}", exc_info=True)
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
            
            logger.info(f">>> _download_document() START")
            logger.info(f"    File: {filename}")
            logger.info(f"    Node ID: {node_id}")
            logger.info(f"    Temp dir: {temp_dir}")
            logger.info(f"    Has alfresco_object: {'alfresco_object' in document and document['alfresco_object'] is not None}")
            logger.info(f"    Has cmis_object: {'cmis_object' in document and document['cmis_object'] is not None}")
            
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
            
            logger.info(f"    File extension: {file_ext}")
            
            # Create temporary file with original filename for LlamaParse display
            # Use original filename so it appears correctly in LlamaCloud
            temp_file_path = os.path.join(temp_dir, filename)
            logger.info(f"    Target path: {temp_file_path}")
            temp_file = open(temp_file_path, 'wb')
            
            content_downloaded = False
            download_method = None
            
            # Try python-alfresco-api content_utils first (most efficient)
            if self.use_api and self.core_client and content_utils:
                try:
                    logger.info(f"Attempting download via python-alfresco-api content_utils")
                    logger.info(f"Calling: content_utils.download_file(core_client, '{node_id}')")
                    
                    # Download file content as bytes (no output path = returns bytes)
                    content_bytes = content_utils.download_file(self.core_client, node_id)
                    
                    logger.info(f"    Content bytes type: {type(content_bytes)}")
                    logger.info(f"    Content size: {len(content_bytes) if content_bytes else 0} bytes")
                    
                    if content_bytes:
                        bytes_written = temp_file.write(content_bytes)
                        content_downloaded = True
                        download_method = "python-alfresco-api (content_utils)"
                        logger.info(f"    [OK] Downloaded {bytes_written} bytes via python-alfresco-api content_utils")
                except Exception as e:
                    logger.warning(f"python-alfresco-api content_utils download failed: {str(e)}", exc_info=True)
                    logger.info(f"Attempting CMIS fallback...")
            else:
                logger.info(f"Skipping python-alfresco-api (use_api={self.use_api}, core_client={self.core_client is not None}, content_utils={content_utils is not None})")
            
            # Fall back to CMIS if Alfresco APIs didn't work
            if not content_downloaded and 'cmis_object' in document:
                try:
                    logger.info(f"Attempting download via CMIS")
                    
                    # Ensure CMIS is initialized before using it
                    self._ensure_cmis_initialized()
                    
                    cmis_object = document['cmis_object']
                    logger.info(f"    CMIS object: {cmis_object}")
                    logger.info(f"Calling: cmis_object.getContentStream()")
                    content_stream = cmis_object.getContentStream()
                    logger.info(f"    Content stream: {content_stream}")
                    
                    if content_stream:
                        content_data = content_stream.read()
                        bytes_written = temp_file.write(content_data)
                        content_stream.close()
                        content_downloaded = True
                        download_method = "CMIS"
                        logger.info(f"    [OK] Downloaded {bytes_written} bytes via CMIS")
                except Exception as e:
                    logger.warning(f"CMIS download failed: {str(e)}", exc_info=True)
            else:
                if not content_downloaded:
                    logger.info(f"Skipping CMIS download (no cmis_object)")
            
            if content_downloaded:
                temp_file.flush()
                temp_file.close()
                file_size = os.path.getsize(temp_file_path)
                logger.info(f"<<< _download_document() SUCCESS")
                logger.info(f"    Method: {download_method}")
                logger.info(f"    File size: {file_size} bytes")
                logger.info(f"    Path: {temp_file_path}")
                return temp_file_path
            else:
                temp_file.close()
                os.unlink(temp_file_path)
                logger.error(f"<<< _download_document() FAILED - no method succeeded")
                raise ValueError(f"No content available for document: {filename} (tried Alfresco API, python-alfresco-api, and CMIS)")
                
        except Exception as e:
            logger.error(f"Error downloading Alfresco document {document.get('name', 'unknown')}: {str(e)}", exc_info=True)
            raise
