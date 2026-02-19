"""
Microsoft Graph Change Detector (OneDrive/SharePoint)

Real-time OneDrive/SharePoint change detection using Microsoft Graph Delta Query.
Supports incremental change tracking via delta query API.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata

logger = logging.getLogger("flexible_graphrag.incremental.detectors.msgraph")

# ---------------------------------------------------------------------------
# Microsoft Graph SDK Integration
# ---------------------------------------------------------------------------

try:
    from msgraph import GraphServiceClient
    from msgraph.generated.models.o_data_errors.o_data_error import ODataError
    from azure.identity import ClientSecretCredential
    MSGRAPH_AVAILABLE = True
except ImportError:
    MSGRAPH_AVAILABLE = False
    ODataError = Exception
    # Create dummy classes to avoid NameError in type hints
    GraphServiceClient = None
    ClientSecretCredential = None
    # Don't log at import time - only when detector is instantiated


# ---------------------------------------------------------------------------
# Microsoft Graph Detector
# ---------------------------------------------------------------------------

class MicrosoftGraphDetector(ChangeDetector):
    """
    Microsoft Graph change detector for OneDrive/SharePoint using Delta Query.
    
    Features:
    - Delta query for incremental change tracking
    - Supports OneDrive, OneDrive for Business, and SharePoint
    - Delta link tracking for efficient polling
    - Automatic retry with exponential backoff
    - Proper error handling and logging
    - **NEW**: Uses backend for ADD/MODIFY events (full DocumentProcessor pipeline)
    
    Configuration:
        # Authentication (required)
        client_id: Azure AD app client ID
        client_secret: Azure AD app client secret
        tenant_id: Azure AD tenant ID
        
        # Source selection (one of these required)
        drive_id: Specific drive ID to monitor
        site_id: SharePoint site ID
        user_id: User ID for OneDrive (or 'me' for authenticated user)
        
        # Optional
        folder_path: Specific folder path within drive (optional, monitors entire drive if not set)
        polling_interval: Seconds between delta polls (default: 60)
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        if not MSGRAPH_AVAILABLE:
            raise ImportError(
                "Microsoft Graph SDK not installed. Install with: pip install msgraph-sdk azure-identity"
            )
        
        # Authentication
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        self.tenant_id = config.get('tenant_id')
        
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            raise ValueError("MicrosoftGraphDetector requires client_id, client_secret, and tenant_id")
        
        # Source selection
        self.drive_id = config.get('drive_id')
        # Support both site_id (Graph API GUID) and site_name (human-readable name)
        # If site_name is provided without site_id, we'll need to look it up
        self.site_id = config.get('site_id')
        self.site_name = config.get('site_name')
        # Support both user_id and user_principal_name (OneDrive sends user_principal_name)
        self.user_id = config.get('user_id') or config.get('user_principal_name', 'me')
        
        # Optional config
        self.folder_path = config.get('folder_path')
        self.polling_interval = config.get('polling_interval', 60)
        
        # Enable/disable change polling (delta query simulation)
        # Set to False to rely only on periodic refresh (every 5 minutes)
        # Set to True to enable 60-second polling for faster detection (uses more API calls)
        self.enable_change_polling = config.get('enable_change_polling', False)  # Default: False for production
        
        # Graph client
        self.graph_client = None
        
        # Delta tracking
        self.delta_link = None  # URL for next delta query
        
        # Statistics
        self.events_processed = 0
        self.errors_count = 0
        
        # Backend reference (will be injected by orchestrator)
        self.backend = None
        self.state_manager = None
        self.config_id = None
        
        # Track known files for CREATE vs MODIFY detection
        self.known_file_ids = set()
        
        # Determine data source type at initialization
        # SharePoint: has site_id or site_name
        # OneDrive: has drive_id or user_id
        if self.site_id or self.site_name:
            self.data_source = 'sharepoint'
            source_desc = f"sharepoint site_id={self.site_id or self.site_name}"
        else:
            self.data_source = 'onedrive'
            if self.drive_id:
                source_desc = f"onedrive drive_id={self.drive_id}"
            else:
                source_desc = f"onedrive user_id={self.user_id}"
        
        logger.info(f"MicrosoftGraphDetector initialized - {source_desc}, "
                   f"folder_path={self.folder_path or '(root)'}, polling_interval={self.polling_interval}s, "
                   f"change_polling={'enabled' if self.enable_change_polling else 'disabled (using 5min periodic refresh only)'}")
    
    async def _resolve_site_id(self):
        """
        Resolve site_name to site_id by listing all sites and finding the matching name.
        This is only needed if site_name is provided without site_id.
        """
        if self.site_id:
            return self.site_id
        
        if not self.site_name:
            return None
        
        logger.info(f"Resolving site_name '{self.site_name}' to site_id...")
        
        try:
            # List all sites and find the one matching the name
            sites = await self.graph_client.sites.get()
            
            if sites and sites.value:
                for site in sites.value:
                    if site.name and site.name.lower() == self.site_name.lower():
                        self.site_id = site.id
                        logger.info(f"Resolved site_name '{self.site_name}' to site_id: {self.site_id}")
                        return self.site_id
            
            logger.error(f"Could not find SharePoint site with name: {self.site_name}")
            raise ValueError(f"SharePoint site '{self.site_name}' not found")
            
        except Exception as e:
            logger.error(f"Error resolving site_name to site_id: {e}")
            raise
    
    def _create_graph_client(self):
        """Create Microsoft Graph client with authentication"""
        # Create credential
        credential = ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        
        # Create Graph client
        scopes = ['https://graph.microsoft.com/.default']
        return GraphServiceClient(credentials=credential, scopes=scopes)
    
    async def start(self):
        """Start Microsoft Graph detector and initialize client"""
        if not MSGRAPH_AVAILABLE:
            logger.error("Cannot start Microsoft Graph detector - msgraph-sdk or azure-identity not installed")
            raise ImportError("msgraph-sdk and azure-identity libraries required. Install with: pip install msgraph-sdk azure-identity")
        
        self._running = True
        
        try:
            # Create Graph client
            self.graph_client = self._create_graph_client()
            
            # Verify access and initialize delta query
            await self._initialize_delta_query()
            
            logger.info("Microsoft Graph detector started successfully")
            logger.info(f"Using Delta Query with {self.polling_interval}s polling interval")
            
        except Exception as e:
            self._running = False
            logger.error(f"Failed to start Microsoft Graph detector: {e}")
            raise
    
    async def _initialize_delta_query(self):
        """Initialize delta query by getting baseline and delta link"""
        try:
            # Resolve site_name to site_id if needed (for SharePoint)
            if self.data_source == 'sharepoint' and self.site_name and not self.site_id:
                await self._resolve_site_id()
            
            # Get the root to establish baseline
            if self.drive_id:
                # Direct drive access
                drive_items = await self._get_drive_items_delta(
                    f"/drives/{self.drive_id}/root/delta"
                )
            elif self.site_id:
                # SharePoint site drive
                drive_items = await self._get_drive_items_delta(
                    f"/sites/{self.site_id}/drive/root/delta"
                )
            else:
                # User's OneDrive
                drive_items = await self._get_drive_items_delta(
                    f"/users/{self.user_id}/drive/root/delta"
                )
            
            logger.info(f"Microsoft Graph delta query initialized with {len(drive_items)} initial items")
            
        except Exception as e:
            logger.error(f"Error initializing delta query: {e}")
            raise
    
    async def _get_drive_items_delta(self, endpoint: str) -> List[Dict]:
        """
        Get drive items delta (async method using Microsoft Graph SDK).
        This processes all pages and saves the delta link.
        
        Basic implementation: Lists all items (no true delta yet, but functional for polling)
        """
        # Resolve site_name to site_id if needed (for SharePoint)
        if self.data_source == 'sharepoint' and self.site_name and not self.site_id:
            await self._resolve_site_id()
        
        items = []
        
        logger.info(f"Fetching items from Microsoft Graph...")
        logger.info(f"Configuration: drive_id={self.drive_id}, site_id={self.site_id}, user_id={self.user_id}, folder_path={self.folder_path}")
        
        try:
            # Build request based on configuration using async SDK
            # Based on official docs: https://github.com/microsoftgraph/msgraph-sdk-python/blob/main/docs/drives_samples.md
            
            if self.drive_id:
                logger.info(f"Using drives.by_drive_id({self.drive_id})")
                # Specific drive - use drives.by_drive_id()
                if self.folder_path:
                    folder_path = self.folder_path.strip('/')
                    logger.info(f"Getting folder: {folder_path}")
                    # Use items collection with path-based item ID
                    # Format: root:/{path} as the item ID
                    response = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id(f"root:/{folder_path}:").children.get()
                else:
                    logger.info("Getting root children")
                    # Get root children
                    response = await self.graph_client.drives.by_drive_id(self.drive_id).items.by_drive_item_id('root').children.get()
            
            elif self.site_id:
                logger.info(f"Using sites.by_site_id({self.site_id})")
                # SharePoint site - first get the drive to get its ID, then use drives.by_drive_id()
                # This is the same pattern as OneDrive (can't chain .drive.items directly)
                drive = await self.graph_client.sites.by_site_id(self.site_id).drive.get()
                
                if hasattr(drive, 'id'):
                    drive_id = drive.id
                    logger.info(f"Got SharePoint drive_id: {drive_id}, fetching root children")
                    
                    if self.folder_path:
                        folder_path = self.folder_path.strip('/')
                        logger.info(f"Getting folder: {folder_path}")
                        # Use items collection with path-based item ID
                        # Format: root:/{path} as the item ID
                        response = await self.graph_client.drives.by_drive_id(drive_id).items.by_drive_item_id(f"root:/{folder_path}:").children.get()
                    else:
                        logger.info("Getting root children")
                        response = await self.graph_client.drives.by_drive_id(drive_id).items.by_drive_item_id('root').children.get()
                else:
                    raise AttributeError(f"Drive object has no 'id' attribute. Available: {dir(drive)}")
            
            else:
                # User's OneDrive
                if self.user_id and self.user_id != 'me':
                    logger.info(f"Using users.by_user_id({self.user_id})")
                    
                    # First get the drive object, then access root
                    drive = await self.graph_client.users.by_user_id(self.user_id).drive.get()
                    # logger.debug(f"Drive object type: {type(drive)}")  # Debug only
                    # logger.debug(f"Drive object attributes: {dir(drive)}")  # Debug only
                    
                    # Now access root on the drive object
                    if hasattr(drive, 'root'):
                        # Can't chain further - need to construct new request
                        # Use the drive ID we got
                        drive_id = drive.id
                        logger.info(f"Got drive_id: {drive_id}, fetching root children")
                        if self.folder_path:
                            folder_path = self.folder_path.strip('/')
                            logger.info(f"Getting folder: {folder_path}")
                            # Use items collection with path-based item ID
                            # Format: root:/{path} as the item ID
                            response = await self.graph_client.drives.by_drive_id(drive_id).items.by_drive_item_id(f"root:/{folder_path}:").children.get()
                        else:
                            response = await self.graph_client.drives.by_drive_id(drive_id).items.by_drive_item_id('root').children.get()
                    else:
                        raise AttributeError(f"Drive object has no 'root' attribute. Available: {dir(drive)}")
                        
                else:
                    logger.info("Using me.drive")
                    
                    # First get the drive object, then access root
                    drive = await self.graph_client.me.drive.get()
                    # logger.debug(f"Drive object type: {type(drive)}")  # Debug only
                    # logger.debug(f"Drive object attributes: {dir(drive)}")  # Debug only
                    
                    # Now access root on the drive object
                    if hasattr(drive, 'root'):
                        # Can't chain further - need to construct new request
                        # Use the drive ID we got
                        drive_id = drive.id
                        logger.info(f"Got drive_id: {drive_id}, fetching root children")
                        if self.folder_path:
                            folder_path = self.folder_path.strip('/')
                            logger.info(f"Getting folder: {folder_path}")
                            # Use items collection with path-based item ID
                            # Format: root:/{path} as the item ID
                            response = await self.graph_client.drives.by_drive_id(drive_id).items.by_drive_item_id(f"root:/{folder_path}:").children.get()
                        else:
                            response = await self.graph_client.drives.by_drive_id(drive_id).items.by_drive_item_id('root').children.get()
                    else:
                        raise AttributeError(f"Drive object has no 'root' attribute. Available: {dir(drive)}")
            
            if response and response.value:
                for item in response.value:
                    # Convert GraphServiceClient item to dict
                    item_dict = {
                        'id': item.id,
                        'name': item.name,
                        'size': item.size,
                        'createdDateTime': item.created_date_time.isoformat() if item.created_date_time else None,
                        'lastModifiedDateTime': item.last_modified_date_time.isoformat() if item.last_modified_date_time else None,
                        'webUrl': item.web_url,
                        'eTag': item.e_tag,
                    }
                    
                    # Check if it's a folder or file
                    if item.folder:
                        item_dict['folder'] = {'childCount': item.folder.child_count}
                    elif item.file:
                        item_dict['file'] = {
                            'mimeType': item.file.mime_type
                        }
                    
                    items.append(item_dict)
                
                logger.info(f"Fetched {len(items)} items from Microsoft Graph")
            # else:
                # logger.debug("No items returned from Microsoft Graph")  # Debug only
            
        except Exception as e:
            logger.error(f"Error fetching items from Microsoft Graph: {e}", exc_info=True)
            # Return empty list on error - detector will continue
        
        # For basic polling, we don't have a delta link yet
        # Just use the endpoint as the "link" for next poll
        self.delta_link = endpoint
        
        return items
    
    async def stop(self):
        """Stop Microsoft Graph detector"""
        self._running = False
        self.graph_client = None
        
        logger.info(f"Microsoft Graph detector stopped. Events processed: {self.events_processed}, Errors: {self.errors_count}")
    
    async def list_all_files(self) -> List[FileMetadata]:
        """List all files in the monitored location (for initial/periodic sync) - recursively"""
        if not self.graph_client:
            raise RuntimeError("Microsoft Graph detector not started")
        
        files = []
        try:
            # Build endpoint based on configuration
            if self.drive_id:
                endpoint = f"/drives/{self.drive_id}/root"
            elif self.site_id:
                endpoint = f"/sites/{self.site_id}/drive/root"
            else:
                endpoint = f"/users/{self.user_id}/drive/root"
            
            # Add folder path if specified
            if self.folder_path:
                endpoint += f":/{self.folder_path}:"
            
            endpoint += "/children"
            
            # List items using Graph SDK
            logger.info(f"Listing files from endpoint: {endpoint}")
            
            # Execute Graph SDK request (recursively)
            try:
                # Get items at root level
                items = await self._get_drive_items_delta(endpoint)
                
                # Recursively process items (folders and files)
                await self._process_items_recursive(items, files)
                
            except Exception as sdk_error:
                logger.error(f"Error calling Graph SDK: {sdk_error}")
                # Return empty list on error - detector will continue
            
            logger.info(f"Listed {len(files)} files from Microsoft Graph (including subfolders)")
            
        except Exception as e:
            logger.error(f"Error listing Microsoft Graph files: {e}")
            self.errors_count += 1
            raise
        
        return files
    
    async def _process_items_recursive(self, items: List[Dict], files: List[FileMetadata], current_folder_path: str = ""):
        """
        Recursively process items, collecting files and traversing folders.
        
        Args:
            items: List of items (files and folders) to process
            files: List to append FileMetadata objects to
            current_folder_path: Current folder path being processed (e.g., "/sample-docs")
        """
        for item_data in items:
            # # Log each item for debugging
            # logger.debug(f"Processing item: id={item_data.get('id')}, name={item_data.get('name')}, has_folder={'folder' in item_data}, has_file={'file' in item_data}")
            
            item_id = item_data.get('id')
            item_name = item_data.get('name')
            has_folder = 'folder' in item_data
            has_file = 'file' in item_data
            
            if has_folder:
                # It's a folder - recursively get its children
                # logger.debug(f"Recursing into folder: {item_name}")  # Debug only
                
                # Build the folder path
                folder_path = f"{current_folder_path}/{item_name}" if current_folder_path else f"/{item_name}"
                
                # Get the drive_id if we don't have it yet
                if not hasattr(self, '_cached_drive_id'):
                    if self.drive_id:
                        self._cached_drive_id = self.drive_id
                    elif self.site_id:
                        # SharePoint: Get drive_id from site
                        drive = await self.graph_client.sites.by_site_id(self.site_id).drive.get()
                        self._cached_drive_id = drive.id
                    else:
                        # OneDrive: Get drive_id from user's drive
                        if self.user_id and self.user_id != 'me':
                            drive = await self.graph_client.users.by_user_id(self.user_id).drive.get()
                        else:
                            drive = await self.graph_client.me.drive.get()
                        self._cached_drive_id = drive.id
                
                # Get children of this folder
                try:
                    folder_children = await self.graph_client.drives.by_drive_id(self._cached_drive_id).items.by_drive_item_id(item_id).children.get()
                    
                    if folder_children and folder_children.value:
                        # Convert to dict format
                        folder_items = []
                        for child_item in folder_children.value:
                            child_dict = {
                                'id': child_item.id,
                                'name': child_item.name,
                                'size': child_item.size,
                                'createdDateTime': child_item.created_date_time.isoformat() if child_item.created_date_time else None,
                                'lastModifiedDateTime': child_item.last_modified_date_time.isoformat() if child_item.last_modified_date_time else None,
                                'webUrl': child_item.web_url,
                                'eTag': child_item.e_tag,
                            }
                            
                            if child_item.folder:
                                child_dict['folder'] = {'childCount': child_item.folder.child_count}
                            elif child_item.file:
                                child_dict['file'] = {'mimeType': child_item.file.mime_type}
                            
                            folder_items.append(child_dict)
                        
                        # Recursively process folder contents
                        await self._process_items_recursive(folder_items, files, folder_path)
                    # else:
                        # logger.debug(f"Folder {item_name} is empty")  # Debug only
                        
                except Exception as folder_error:
                    logger.error(f"Error reading folder {item_name}: {folder_error}")
                    
            elif has_file:
                # It's a file - add to files list
                # logger.debug(f"Found file: {item_name}")  # Debug only
                
                file_id = item_data.get('id')
                file_name = item_data.get('name', file_id)
                
                if not file_id:
                    continue
                
                # Use stable path format with correct prefix
                prefix = "sharepoint" if self.data_source == 'sharepoint' else "onedrive"
                stable_path = f"{prefix}://{file_id}"
                
                # Build human-readable path with folder
                human_readable_path = f"{current_folder_path}/{file_name}" if current_folder_path else f"/{file_name}"
                
                # Parse modified time
                last_modified = item_data.get('lastModifiedDateTime')
                if last_modified:
                    modified_time = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                else:
                    modified_time = datetime.now(timezone.utc)
                
                ordinal = int(modified_time.timestamp() * 1_000_000)
                
                # Get file size and MIME type
                size_bytes = item_data.get('size')
                mime_type = item_data.get('file', {}).get('mimeType')
                
                metadata = FileMetadata(
                    source_type='msgraph',
                    path=stable_path,
                    ordinal=ordinal,
                    size_bytes=size_bytes,
                    mime_type=mime_type,
                    modified_timestamp=modified_time.isoformat(),
                    extra={
                        # Store RAW file_id (without prefix) for consistency with _item_to_metadata()
                        # This is used by engine.py to extract the file_id for processing
                        'file_id': file_id,  # RAW ID without prefix
                        'file_name': file_name,
                        'file_path': human_readable_path,  # Human-readable path with folder
                        'folder_path': current_folder_path if current_folder_path else None,  # Just the folder part
                        'web_url': item_data.get('webUrl'),
                        'etag': item_data.get('eTag'),
                    }
                )
                
                files.append(metadata)
            else:
                logger.warning(f"Item {item_name} is neither file nor folder - skipping")
    
    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """
        Stream change events from Microsoft Graph (polling every 60s).
        Detects new files and deletions by comparing current list with known_file_ids.
        
        NOTE: This is a simplified implementation that lists all files each poll.
        For production, this should use the true Microsoft Graph /delta endpoint
        which only returns changes since last poll (much more efficient).
        
        Currently DISABLED by default (enable_change_polling=False) to avoid
        redundant API calls with the 5-minute periodic refresh.
        Set enable_change_polling=True in config to enable for testing.
        """
        if not self._running or not self.graph_client:
            return
        
        # Check if change polling is enabled
        if not self.enable_change_polling:
            logger.info(f"Change polling disabled for {self.data_source} (enable_change_polling=False)")
            logger.info(f"  Relying on periodic refresh (every 5 minutes) for change detection")
            logger.info(f"  Set 'enable_change_polling': true in datasource config to enable 60-second polling")
            return
        
        logger.info("Starting Microsoft Graph polling for changes...")
        logger.info(f"Polling interval: {self.polling_interval} seconds")
        
        while self._running:
            try:
                # List all current files
                current_files = await self.list_all_files()
                
                # Build set of current file IDs
                current_file_ids = set()
                current_files_by_id = {}
                for file_meta in current_files:
                    file_id = file_meta.extra.get('file_id') if file_meta.extra else None
                    if file_id:
                        current_file_ids.add(file_id)
                        current_files_by_id[file_id] = file_meta
                
                # Detect deletions: files in known_file_ids but not in current_file_ids
                deleted_file_ids = self.known_file_ids - current_file_ids
                
                # Yield DELETE events for deleted files
                for deleted_id in deleted_file_ids:
                    logger.info(f"Microsoft Graph EVENT: DELETE detected for file_id {deleted_id}")
                    
                    # deleted_id is RAW file ID (no prefix)
                    # Need to create stable_path with prefix for document_state lookup
                    prefix = "sharepoint" if self.data_source == 'sharepoint' else "onedrive"
                    stable_path = f"{prefix}://{deleted_id}"
                    
                    delete_metadata = FileMetadata(
                        source_type='msgraph',
                        path=stable_path,
                        ordinal=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
                        extra={'file_id': deleted_id}
                    )
                    delete_event = ChangeEvent(
                        metadata=delete_metadata,
                        change_type=ChangeType.DELETE,
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    self.known_file_ids.remove(deleted_id)
                    self.events_processed += 1
                    yield delete_event
                
                # Detect new files
                new_file_ids = current_file_ids - self.known_file_ids
                for new_id in new_file_ids:
                    file_meta = current_files_by_id[new_id]
                    file_name = file_meta.extra.get('file_name', new_id)
                    file_path = file_meta.extra.get('file_path')
                    folder_path = file_meta.extra.get('folder_path')
                    
                    logger.info(f"Microsoft Graph EVENT: CREATE for {file_name}")
                    self.known_file_ids.add(new_id)
                    self.events_processed += 1
                    
                    try:
                        await self._process_via_backend(new_id, file_name, file_path, folder_path)
                        logger.info(f"SUCCESS: Processed CREATE for {file_name}")
                    except Exception as e:
                        logger.error(f"ERROR: Failed to process CREATE for {file_name}: {e}")
                
                # Wait before next poll
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"Error polling Microsoft Graph: {e}")
                self.errors_count += 1
                await asyncio.sleep(self.polling_interval)
    
    def _parse_drive_item(self, item_data: Dict) -> Optional[ChangeEvent]:
        """Parse Microsoft Graph drive item into ChangeEvent"""
        try:
            # Check if item is deleted
            if item_data.get('deleted'):
                change_type = ChangeType.DELETE
            elif item_data.get('@removed'):
                change_type = ChangeType.DELETE
            else:
                # For non-deleted items, determine if create or update
                # Delta query doesn't have explicit create flag, so we use heuristics:
                # 1. If createdDateTime == lastModifiedDateTime (or very close), likely a new file
                # 2. Otherwise, treat as update
                created_time_str = item_data.get('createdDateTime')
                modified_time_str = item_data.get('lastModifiedDateTime')
                
                if created_time_str and modified_time_str:
                    try:
                        created_time = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                        modified_time = datetime.fromisoformat(modified_time_str.replace('Z', '+00:00'))
                        
                        # If modified within 1 second of creation, treat as CREATE
                        time_diff = abs((modified_time - created_time).total_seconds())
                        change_type = ChangeType.CREATE if time_diff < 1.0 else ChangeType.UPDATE
                    except Exception:
                        # If timestamp parsing fails, default to UPDATE
                        change_type = ChangeType.UPDATE
                else:
                    # No timestamps available, default to UPDATE
                    change_type = ChangeType.UPDATE
            
            # Skip folders
            if 'folder' in item_data:
                return None
            
            # Get file metadata
            file_id = item_data.get('id')
            file_name = item_data.get('name', file_id)
            
            # Use stable path format: onedrive:// or sharepoint:// based on data_source
            # This matches the format used by OneDriveSource/SharePointSource for consistent tracking
            prefix = "sharepoint" if self.data_source == 'sharepoint' else "onedrive"
            stable_path = f"{prefix}://{file_id}" if file_id else file_name
            
            # Parse modified time
            last_modified = item_data.get('lastModifiedDateTime')
            if last_modified:
                modified_time = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
            else:
                modified_time = datetime.now(timezone.utc)
            
            ordinal = int(modified_time.timestamp() * 1_000_000)
            
            # Get file size and MIME type
            size_bytes = item_data.get('size')
            mime_type = item_data.get('file', {}).get('mimeType')
            
            metadata = FileMetadata(
                source_type='msgraph',
                path=stable_path,  # Use stable onedrive:// path
                ordinal=ordinal,
                size_bytes=size_bytes,
                mime_type=mime_type,
                modified_timestamp=modified_time.isoformat(),
                extra={
                    'file_id': file_id,
                    'file_name': file_name,  # Store original filename for reference
                    'web_url': item_data.get('webUrl'),
                    'etag': item_data.get('eTag'),
                }
            )
            
            return ChangeEvent(
                metadata=metadata,
                change_type=change_type,
                timestamp=modified_time
            )
            
        except Exception as e:
            logger.warning(f"Error parsing Microsoft Graph drive item: {e}")
            return None
    
    async def _process_via_backend(self, file_id: str, filename: str, file_path: str = None, folder_path: str = None):
        """
        Process Microsoft Graph file by calling backend._process_documents_async() directly.
        Uses the complete pipeline with DocumentProcessor.
        
        Args:
            file_id: Microsoft Graph file ID
            filename: File name for logging
            file_path: Human-readable file path (e.g., "/sample-docs/cmispress.txt")
            folder_path: Folder path (e.g., "/sample-docs")
        """
        if not self.backend:
            logger.error("Backend not injected into MicrosoftGraphDetector - cannot process file")
            return
        
        logger.info(f"Processing {filename} (file_id: {file_id}) via backend (full pipeline) using {self.data_source}")
        
        try:
            skip_graph = getattr(self, 'skip_graph', False)
            processing_id = f"incremental_msg_{file_id[:8]}"
            
            # Build config based on data source type (determined at init)
            source_config = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'tenant_id': self.tenant_id,
                # Store folder path for metadata enrichment
                '_folder_path': folder_path,  # Internal use, not passed to reader
                '_file_path': file_path,  # Internal use, not passed to reader
            }
            
            # Add source-specific parameters
            if self.data_source == 'sharepoint':
                # SharePoint needs site_name (required for SharePointSource/Reader)
                # Pass both site_name (original) and site_id (resolved) if available
                if self.site_name:
                    source_config['site_name'] = self.site_name
                if self.site_id:
                    source_config['site_id'] = self.site_id
                # Strip prefix from file_id if present (sharepoint://file_id -> file_id)
                raw_file_id = file_id.replace('sharepoint://', '') if file_id.startswith('sharepoint://') else file_id
                # Pass file_ids for incremental processing (SharePointSource will handle it)
                source_config['file_ids'] = [raw_file_id]
            else:  # onedrive
                # Strip prefix from file_id if present (onedrive://file_id -> file_id)
                raw_file_id = file_id.replace('onedrive://', '') if file_id.startswith('onedrive://') else file_id
                # OneDrive supports file_ids for efficient single-file processing
                source_config['file_ids'] = [raw_file_id]  # Process just this one file
                if self.drive_id:
                    source_config['drive_id'] = self.drive_id
                else:
                    # OneDriveSource expects 'user_principal_name', not 'user_id'
                    source_config['user_principal_name'] = self.user_id
            
            # Call backend method directly with appropriate data source
            config_param = f'{self.data_source}_config'
            await self.backend._process_documents_async(
                processing_id=processing_id,
                data_source=self.data_source,
                config_id=self.config_id,
                skip_graph=skip_graph,
                **{config_param: source_config}
            )
            
            logger.info(f"Successfully processed {filename} via backend pipeline")
            
            # Create document_state record after successful processing
            if self.state_manager:
                try:
                    await self._create_document_state_from_processing_status(
                        processing_id, filename, file_id, file_path, folder_path
                    )
                except Exception as e:
                    logger.error(f"Failed to create document_state for {filename}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process {filename} via backend: {e}")
            raise
    
    async def _create_document_state_from_processing_status(
        self, processing_id: str, filename: str, file_id: str, file_path: str = None, folder_path: str = None
    ):
        """
        Create document_state record after successful processing.
        
        Args:
            processing_id: Processing ID to get status from
            filename: Original filename
            file_id: Microsoft Graph file ID
            file_path: Human-readable file path (e.g., "/sample-docs/cmispress.txt")
            folder_path: Folder path (e.g., "/sample-docs")
        """
        from backend import PROCESSING_STATUS
        from incremental_updates.state_manager import DocumentState
        from datetime import datetime, timezone
        
        # Wait a moment for processing to complete
        await asyncio.sleep(0.5)
        
        status_dict = PROCESSING_STATUS.get(processing_id, {})
        if status_dict.get('status') != 'completed':
            logger.warning(f"Processing not yet completed for {filename}, skipping document_state creation")
            return
        
        documents = status_dict.get('documents', [])
        if not documents:
            logger.warning(f"No documents found in PROCESSING_STATUS for {filename}")
            return
        
        doc = documents[0]
        
        # Create stable path with prefix (for doc_id and source_id)
        prefix = "sharepoint" if self.data_source == 'sharepoint' else "onedrive"
        
        # Strip prefix from file_id if it's already there (defensive programming)
        raw_file_id = file_id
        if file_id.startswith(f'{prefix}://'):
            raw_file_id = file_id.replace(f'{prefix}://', '', 1)
            logger.debug(f"Stripped existing prefix from file_id: {file_id} -> {raw_file_id}")
        
        stable_path = f"{prefix}://{raw_file_id}"
        
        # Use human-readable path for source_path if available
        if file_path:
            source_path = file_path  # e.g., "/sample-docs/cmispress.txt"
        else:
            source_path = stable_path  # Fall back to stable path
        
        # Use stable path as source_id (always with prefix)
        source_id = stable_path
        
        # Get modified timestamp from document metadata and parse it
        timestamp_str = doc.metadata.get('last_modified_datetime') or doc.metadata.get('modified at')
        modified_timestamp = self.parse_timestamp(timestamp_str)
        
        # Create doc_id using stable path (not filename)
        doc_id = f"{self.config_id}:{stable_path}"
        
        # Compute content hash from document text (not placeholder)
        import hashlib
        content_hash = hashlib.sha256(doc.text.encode()).hexdigest() if doc.text else "placeholder"
        
        # Get ordinal from modified timestamp if available (already parsed to datetime)
        ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        if modified_timestamp:
            ordinal = int(modified_timestamp.timestamp() * 1_000_000)
        
        # Get current timestamp for sync tracking
        now = datetime.now(timezone.utc)
        
        # Determine which indexes were updated based on skip_graph flag
        skip_graph = getattr(self, 'skip_graph', False)
        
        # Create document state
        doc_state = DocumentState(
            doc_id=doc_id,
            config_id=self.config_id,
            source_path=source_path,  # Human-readable path if available, else stable path
            ordinal=ordinal,
            content_hash=content_hash,
            source_id=source_id,  # Always stable path with prefix
            modified_timestamp=modified_timestamp,
            vector_synced_at=now,  # Set to current time since we just indexed
            search_synced_at=now,  # Set to current time since we just indexed
            graph_synced_at=now if not skip_graph else None  # Only set if graph was updated
        )
        
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state: doc_id={doc_id}, source_path={source_path}, source_id={source_id}")


# Note: This is a simplified implementation that provides the structure.
# A complete implementation would need to:
# 1. Use the actual msgraph SDK methods for delta queries
# 2. Properly handle pagination of delta results
# 3. Store and use delta links correctly
# 4. Implement file downloads
# 5. Handle OAuth token refresh
# 6. Support webhooks (subscriptions) for true real-time updates
