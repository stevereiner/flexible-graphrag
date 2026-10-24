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

        # NOTE: do NOT touch self.delta_link here. This method is a plain lister (called by
        # list_all_files(), i.e. every periodic refresh) and used to stash the RELATIVE endpoint
        # path here as a leftover of the old basic-polling design. self.delta_link now holds Graph's
        # absolute @odata.deltaLink URL for _run_delta_cycle(); overwriting it with a relative path
        # made every delta cycle fail with "Valid url scheme and host required" and fall back to a
        # full re-enumeration (once per periodic refresh).

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
                
                # Recursively process items (folders and files). Paths start at the sync's
                # folder ("/test/cmispress.txt"), as the delta stream and the API ingest record them
                await self._process_items_recursive(items, files, self._base_path())
                
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
    
    def _base_path(self) -> str:
        """The sync's folder as a drive path ("/test"), or "" for the whole drive."""
        return "/" + self.folder_path.strip("/") if self.folder_path and self.folder_path.strip("/") else ""

    def _in_folder(self, file_path: Optional[str]) -> bool:
        """Whether a drive path is under the sync's folder (at any depth: the listing is recursive)."""
        from ..recovery import comparable_path
        base = self._base_path()
        if not base:
            return True
        return bool(file_path) and comparable_path(file_path).startswith(comparable_path(base) + "/")

    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """Stream change events from Microsoft Graph using the ``/delta`` endpoint.

        This is a true incremental delta stream: each cycle asks Graph only for
        items that changed since the last ``deltaLink`` (persisted per
        ``config_id``).  The very first cycle enumerates the drive and returns a
        ``deltaLink``; subsequent cycles return just adds / updates / removals.

        Each returned drive item is routed through :meth:`_parse_drive_item`
        which classifies it as CREATE / UPDATE / DELETE.  The ``deltaLink`` is
        persisted after every cycle so a restart resumes exactly where it left
        off.

        If the delta call fails (SDK/version issue, transient error), the cycle
        falls back to the legacy full-list comparison so change detection keeps
        working.

        Disabled by default (``enable_change_polling=False``) so it does not
        duplicate the 5-minute periodic refresh; set
        ``enable_change_polling: true`` in the datasource config to enable.
        """
        if not self._running or not self.graph_client:
            return

        if not self.enable_change_polling:
            # no events will come: the periodic refresh takes every change (recovery.py)
            self._events_live_since = datetime.max.replace(tzinfo=timezone.utc)
            logger.info(f"Change polling disabled for {self.data_source} (enable_change_polling=False)")
            logger.info(f"  Relying on periodic refresh (every 5 minutes) for change detection")
            logger.info(f"  Set 'enable_change_polling': true in datasource config to enable delta polling")
            return

        logger.info("Starting Microsoft Graph DELTA polling for changes...")
        logger.info(f"Polling interval: {self.polling_interval} seconds")

        # Resume from a persisted deltaLink if one exists for this config.
        if self.delta_link is None:
            self.delta_link = await self._load_delta_link()
            if self.delta_link:
                logger.info("Resumed Microsoft Graph delta stream from persisted deltaLink")

        while self._running:
            try:
                async for event in self._run_delta_cycle():
                    yield event
                await asyncio.sleep(self.polling_interval)
            except Exception as e:
                logger.error(f"Error in Microsoft Graph delta cycle: {e}", exc_info=True)
                self.errors_count += 1
                # Fall back to a full-list comparison for this cycle so we don't
                # miss changes while the delta stream recovers.
                try:
                    async for event in self._run_fulllist_cycle():
                        yield event
                except Exception as fe:
                    logger.error(f"Fallback full-list cycle also failed: {fe}")
                await asyncio.sleep(self.polling_interval)

    async def _run_delta_cycle(self) -> AsyncGenerator[ChangeEvent, None]:
        """Run one delta query cycle: fetch changes, yield events, persist deltaLink."""
        drive_id = await self._resolve_drive_id()
        if not drive_id:
            raise RuntimeError("Could not resolve drive_id for delta query")

        # Build the delta request builder — start from persisted deltaLink when
        # available, otherwise a fresh /root/delta enumeration.
        # NOTE: in msgraph-sdk (1.58.0) `delta` is NOT on `.items` (ItemsRequestBuilder) nor on
        # `.root` — it hangs off an individual item builder, so the root enumeration is
        # `.items.by_drive_item_id("root").delta` -> GET /drives/{drive-id}/items/root/delta.
        # Using `.items.delta` raises AttributeError: 'ItemsRequestBuilder' object has no attribute 'delta'.
        delta_builder = self.graph_client.drives.by_drive_id(drive_id).items.by_drive_item_id("root").delta

        page = None
        if self.delta_link:
            try:
                page = await delta_builder.with_url(self.delta_link).get()
            except Exception as e:
                logger.warning(f"deltaLink stale/invalid ({e}) — restarting delta enumeration")
                self.delta_link = None
        if page is None:
            page = await delta_builder.get()

        # Iterate all pages (nextLink) until we reach the final deltaLink.
        while page is not None:
            for item in (getattr(page, "value", None) or []):
                item_dict = self._drive_item_to_dict(item)
                event = self._parse_drive_item(item_dict)
                if event is None:
                    continue  # folder or unparseable

                # The delta covers the whole drive: only what is under the sync's folder is its
                # own; a document it follows that moved out of it is no longer its to keep
                if event.change_type != ChangeType.DELETE and not self._in_folder(event.metadata.extra.get('file_path')):
                    gone = await self._moved_out_event(event)
                    if gone is not None:
                        yield gone
                    continue

                self.events_processed += 1
                if event.change_type == ChangeType.DELETE:
                    yield event
                else:
                    # CREATE / UPDATE — the CocoIndex map view (or engine) pulls
                    # the file; we surface the event either way.
                    yield event

            next_link = getattr(page, "odata_next_link", None)
            delta_link = getattr(page, "odata_delta_link", None)
            if next_link:
                page = await delta_builder.with_url(next_link).get()
            else:
                if delta_link:
                    self.delta_link = delta_link
                    await self._save_delta_link(delta_link)
                page = None

    async def _moved_out_event(self, event: ChangeEvent) -> Optional[ChangeEvent]:
        """A DELETE for a followed document now outside the sync's folder, else None."""
        if not (self.state_manager and self.config_id):
            return None
        from ..recovery import moved_out
        from ..state_manager import StateManager
        try:
            state = await self.state_manager.get_state(StateManager.make_doc_id(self.config_id, event.metadata.path))
        except Exception as e:
            logger.debug(f"Could not check {event.metadata.path}: {e}")
            return None
        if not moved_out(state, event.metadata.extra.get('file_path')):
            return None
        logger.info(f"Microsoft Graph EVENT: {state.source_path} moved out of this sync's folder -- removing it")
        return ChangeEvent(
            metadata=FileMetadata(source_type='msgraph', path=event.metadata.path,
                                  ordinal=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
                                  extra={'file_id': event.metadata.extra.get('file_id')}),
            change_type=ChangeType.DELETE, timestamp=datetime.now(timezone.utc))

    async def _run_fulllist_cycle(self) -> AsyncGenerator[ChangeEvent, None]:
        """Legacy fallback: list all files and diff against known IDs."""
        current_files = await self.list_all_files()
        current_file_ids = set()
        current_files_by_id = {}
        for file_meta in current_files:
            file_id = file_meta.extra.get('file_id') if file_meta.extra else None
            if file_id:
                current_file_ids.add(file_id)
                current_files_by_id[file_id] = file_meta

        deleted_file_ids = self.known_file_ids - current_file_ids
        for deleted_id in deleted_file_ids:
            logger.info(f"Microsoft Graph EVENT (fallback): DELETE for file_id {deleted_id}")
            prefix = "sharepoint" if self.data_source == 'sharepoint' else "onedrive"
            stable_path = f"{prefix}://{deleted_id}"
            delete_metadata = FileMetadata(
                source_type='msgraph',
                path=stable_path,
                ordinal=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
                extra={'file_id': deleted_id},
            )
            self.known_file_ids.discard(deleted_id)
            self.events_processed += 1
            yield ChangeEvent(
                metadata=delete_metadata,
                change_type=ChangeType.DELETE,
                timestamp=datetime.now(timezone.utc),
            )

        new_file_ids = current_file_ids - self.known_file_ids
        for new_id in new_file_ids:
            file_meta = current_files_by_id[new_id]
            self.known_file_ids.add(new_id)
            self.events_processed += 1
            yield ChangeEvent(
                metadata=file_meta,
                change_type=ChangeType.CREATE,
                timestamp=datetime.now(timezone.utc),
            )

    async def _resolve_drive_id(self) -> Optional[str]:
        """Resolve and cache the drive id for the configured drive/site/user."""
        if getattr(self, "_cached_drive_id", None):
            return self._cached_drive_id

        if self.drive_id:
            self._cached_drive_id = self.drive_id
        elif self.site_id or self.site_name:
            if self.site_name and not self.site_id:
                await self._resolve_site_id()
            drive = await self.graph_client.sites.by_site_id(self.site_id).drive.get()
            self._cached_drive_id = getattr(drive, "id", None)
        else:
            if self.user_id and self.user_id != 'me':
                drive = await self.graph_client.users.by_user_id(self.user_id).drive.get()
            else:
                drive = await self.graph_client.me.drive.get()
            self._cached_drive_id = getattr(drive, "id", None)
        return self._cached_drive_id

    @staticmethod
    def _paths_from_parent_ref(item_data: Dict, file_name: str) -> tuple:
        """Derive (folder_path, file_path) from a drive item's parentReference.

        Graph formats ``parentReference.path`` as ``/drive/root:/test`` or
        ``/drives/{drive-id}/root:/test`` (URL-encoded), and just ``/drive/root:`` at the drive root.
        Returns the same shape the OneDrive/SharePoint sources produce on the initial ingest:
        ``("/test", "/test/cmispress.txt")`` — or ``("/", "/cmispress.txt")`` at the root — so a
        delta-added file records the same path as the same file ingested initially.
        """
        from urllib.parse import unquote
        raw = ((item_data.get('parentReference') or {}).get('path') or '')
        folder_path = '/'
        if 'root:' in raw:
            folder_path = unquote(raw.split('root:', 1)[1]) or '/'
        if not folder_path.startswith('/'):
            folder_path = '/' + folder_path
        file_path = f"{folder_path.rstrip('/')}/{file_name}" if file_name else folder_path
        return folder_path, file_path

    @staticmethod
    def _drive_item_to_dict(item) -> Dict:
        """Convert an msgraph SDK ``DriveItem`` to the dict :meth:`_parse_drive_item` expects."""
        additional = getattr(item, "additional_data", None) or {}
        d: Dict = {
            'id': getattr(item, "id", None),
            'name': getattr(item, "name", None),
            'size': getattr(item, "size", None),
            'webUrl': getattr(item, "web_url", None),
            'eTag': getattr(item, "e_tag", None),
        }
        _created = getattr(item, "created_date_time", None)
        _modified = getattr(item, "last_modified_date_time", None)
        d['createdDateTime'] = _created.isoformat() if _created else None
        d['lastModifiedDateTime'] = _modified.isoformat() if _modified else None
        # Deletion markers: the delta stream sets a `deleted` facet and the raw
        # payload carries an `@removed` annotation in additional_data.
        if getattr(item, "deleted", None) is not None:
            d['deleted'] = True
        if '@removed' in additional:
            d['@removed'] = additional['@removed']
        if getattr(item, "folder", None) is not None:
            d['folder'] = {'childCount': getattr(item.folder, "child_count", None)}
        elif getattr(item, "file", None) is not None:
            d['file'] = {'mimeType': getattr(item.file, "mime_type", None)}
        # parentReference carries the containing folder — Graph formats `path` as
        # "/drive/root:/test" (or "/drives/{drive-id}/root:/test"). Without it, _parse_drive_item
        # can't report a folder and the engine falls back to file_path="/{name}", folder_path="/",
        # so a delta-added file loses its folder vs the same file from the initial ingest.
        _parent = getattr(item, "parent_reference", None)
        if _parent is not None:
            d['parentReference'] = {
                'path': getattr(_parent, "path", None),
                'id': getattr(_parent, "id", None),
                'driveId': getattr(_parent, "drive_id", None),
            }
        return d

    async def _load_delta_link(self) -> Optional[str]:
        """Load the persisted deltaLink for this config_id (if any), from the state store."""
        if not self.config_id or self.state_manager is None:
            return None
        try:
            return await self.state_manager.load_sync_cursor(self.config_id)
        except Exception as e:
            logger.debug(f"Could not load msgraph deltaLink: {e}")
            return None

    async def _save_delta_link(self, delta_link: str) -> None:
        """Persist the deltaLink for this config_id so restarts resume in place."""
        if not self.config_id or self.state_manager is None:
            return
        try:
            await self.state_manager.save_sync_cursor(self.config_id, delta_link)
        except Exception as e:
            logger.debug(f"Could not save msgraph deltaLink: {e}")
    
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

            # Derive the human-readable folder/file path from parentReference so delta events carry
            # the SAME shape the sources produce on the initial ingest (folder_path="/test",
            # file_path="/test/cmispress.txt"). Without these in `extra`, engine.py falls back to
            # file_path=f"/{file_name}" and folder_path="/", losing the folder.
            folder_path, file_path = self._paths_from_parent_ref(item_data, file_name)

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
                    'file_path': file_path,      # e.g. /test/cmispress.txt
                    'folder_path': folder_path,  # e.g. /test  (or "/" at the drive root)
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
            from incremental_updates.doc_graphs import datasource_graphs, synced_times
            graphs = datasource_graphs(self)  # which graphs it builds
            from .. import sync_jobs
            processing_id = sync_jobs.processing_id("msg", file_id)
            
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
                graphs=graphs,
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
        
        # each graph's sync time, only where a store is behind it
        from incremental_updates.doc_graphs import datasource_graphs, synced_times
        graph_at, rdf_at = synced_times(self, datasource_graphs(self), now)
        
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
            graph_synced_at=graph_at,  # each graph only if it was built
            rdf_synced_at=rdf_at
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
