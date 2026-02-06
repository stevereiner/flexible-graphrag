"""
Alfresco Change Detector

Detects changes in Alfresco repositories through:
1. Real-time events (Event Gateway for Enterprise, ActiveMQ for Community)
2. Periodic polling (fallback mode)
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Optional, AsyncGenerator, List
from asyncio import Queue

from .base import ChangeDetector, ChangeEvent, ChangeType, FileMetadata

logger = logging.getLogger("flexible_graphrag.incremental.detectors.alfresco")

# Try to import event client
try:
    from python_alfresco_api.events import AlfrescoEventClient, EventNotification
    EVENTS_AVAILABLE = True
except ImportError:
    EVENTS_AVAILABLE = False
    logger.warning("python-alfresco-api events not available - will use polling mode only")

# Try to import stomp for direct connection
try:
    import stomp
    STOMP_AVAILABLE = True
except ImportError:
    STOMP_AVAILABLE = False
    logger.warning("stomp.py not available - direct event monitoring disabled")


class DirectAlfrescoEventListener(stomp.ConnectionListener if STOMP_AVAILABLE else object):
    """
    Direct STOMP listener for Alfresco CloudEvents format
    Parses events from alfresco.repo.event2 topic and queues them for processing
    """
    
    def __init__(self, detector: 'AlfrescoDetector'):
        self.detector = detector
        self.event_count = 0
    
    def on_error(self, frame):
        logger.error(f"STOMP ERROR: {frame.body if hasattr(frame, 'body') else frame}")
    
    def on_connected(self, frame):
        logger.info("STOMP CONNECTED to ActiveMQ")
        logger.info(f"   Session: {frame.headers.get('session', 'N/A') if hasattr(frame, 'headers') else 'N/A'}")
        # Set connected flag
        if self.detector:
            self.detector._stomp_connected = True
    
    def on_disconnected(self):
        logger.warning("STOMP DISCONNECTED from ActiveMQ")
        # Set flag to trigger reconnection
        if self.detector:
            self.detector._stomp_connected = False
    
    def on_message(self, frame):
        """Handle incoming Alfresco CloudEvents"""
        try:
            self.event_count += 1
            
            # Parse CloudEvents format
            event = json.loads(frame.body)
            event_type = event.get("type", "")  # e.g., "org.alfresco.event.node.Created"
            event_id = event.get("id", "")
            event_time = event.get("time", "")
            
            # Extract node info from CloudEvents data structure
            data = event.get("data", {})
            resource = data.get("resource", {})
            resource_before = data.get("resourceBefore", {})
            
            # Extract key fields
            node_id = resource.get("id")
            name = resource.get("name")
            node_type = resource.get("nodeType", "")
            is_file = resource.get("isFile", False)
            is_folder = resource.get("isFolder", False)
            modified_at = resource.get("modifiedAt")
            primary_hierarchy = resource.get("primaryHierarchy", [])
            
            # Content info (files only)
            content = resource.get("content", {})
            mime_type = content.get("mimeType")
            size_bytes = content.get("sizeInBytes", 0)
            
            logger.info(f"EVENT #{self.event_count} RECEIVED: {event_type}")
            logger.info(f"   Event ID: {event_id}")
            logger.info(f"   Node ID: {node_id}")
            logger.info(f"   Name: {name}")
            logger.info(f"   Type: {node_type}")
            logger.info(f"   Is File: {is_file}, Is Folder: {is_folder}")
            logger.info(f"   Modified: {modified_at}")
            if primary_hierarchy:
                logger.info(f"   Parent: {primary_hierarchy[0] if primary_hierarchy else 'N/A'}")
            
            # Only process file events (skip folders)
            if not is_file:
                logger.info(f"   SKIPPED: Not a file (folder or other type)")
                return
            
            # Event-type-specific filtering logic
            if "Created" in event_type:
                # CREATE: Check if parent folder is monitored folder
                # (New file added to folder, or new version 1.0->1.1 with new node ID)
                if self.detector._monitored_folder_id and primary_hierarchy:
                    immediate_parent = primary_hierarchy[0] if primary_hierarchy else None
                    
                    # Check if file's parent is the monitored folder OR any ancestor is
                    if self.detector._monitored_folder_id not in primary_hierarchy:
                        logger.info(f"   SKIPPED (CREATE): Parent folder not monitored")
                        logger.info(f"      Parent: {immediate_parent}")
                        logger.info(f"      Monitored folder: {self.detector._monitored_folder_id}")
                        return
                    logger.debug(f"   CREATE in monitored folder: {self.detector.path}")
            
            elif "Updated" in event_type:
                # UPDATE: Check if node is already in document_state (tracked file)
                # Check version change - if versionLabel changed, it's actually a CREATE
                properties = resource.get("properties", {})
                properties_before = resource_before.get("properties", {})
                
                version_before = properties_before.get("cm:versionLabel")
                version_after = properties.get("cm:versionLabel")
                
                if version_before and version_after and version_before != version_after:
                    logger.info(f"   VERSION CHANGE: {version_before} -> {version_after}")
                    logger.info(f"   NOTE: Version changes create new node IDs (will be CREATE event)")
                    # This shouldn't happen - Alfresco sends CREATE for new version
                    # But if it does, we'll process it as an update to the logical file
                
                # Log what changed
                name_before = resource_before.get("name")
                name_after = resource.get("name")
                modified_at_before = resource_before.get("modifiedAt")
                aspects_before = resource_before.get("aspectNames", [])
                aspects_after = resource.get("aspectNames", [])
                
                # Detect changes
                name_changed = name_before and name_after and name_before != name_after
                content_changed = modified_at != modified_at_before
                aspects_changed = set(aspects_before) != set(aspects_after)
                thumbnail_changed = properties.get("cm:lastThumbnailModification") != properties_before.get("cm:lastThumbnailModification")
                
                # Log what changed
                changes = []
                if name_changed:
                    changes.append(f"name: '{name_before}'->'{name_after}'")
                if content_changed:
                    changes.append(f"content: {modified_at_before}->{modified_at}")
                if aspects_changed:
                    changes.append(f"aspects: {len(aspects_before)}->{len(aspects_after)}")
                if thumbnail_changed:
                    changes.append("thumbnail")
                
                if changes:
                    logger.info(f"   UPDATE CHANGES: {', '.join(changes)}")
                else:
                    logger.info(f"   UPDATE: No obvious changes detected")
                
                # Check if only thumbnail changed
                if thumbnail_changed and not content_changed and not name_changed and not aspects_changed:
                    logger.info(f"   SKIPPED (UPDATE): Thumbnail/rendition update only")
                    return
                
                # Check if this is a tracked document
                is_tracked = node_id in self.detector._known_documents
                
                if not is_tracked:
                    # Not in our tracked documents - check if in monitored folder
                    if self.detector._monitored_folder_id and primary_hierarchy:
                        if self.detector._monitored_folder_id not in primary_hierarchy:
                            logger.info(f"   SKIPPED (UPDATE): Not tracked and not in monitored folder")
                            return
                        logger.info(f"   UPDATE for file in monitored folder (not yet tracked)")
                else:
                    logger.debug(f"   UPDATE for tracked document: {node_id}")
            
            elif "Deleted" in event_type:
                # DELETE: Check if this file was in our monitored folder
                # Use primary_hierarchy from "resource" (the deleted node's last known location)
                if self.detector._monitored_folder_id and primary_hierarchy:
                    # Check if any ancestor is the monitored folder
                    if self.detector._monitored_folder_id not in primary_hierarchy:
                        logger.info(f"   SKIPPED (DELETE): File not in monitored folder")
                        logger.info(f"      Primary hierarchy: {primary_hierarchy[:2] if len(primary_hierarchy) > 2 else primary_hierarchy}")
                        logger.info(f"      Monitored folder: {self.detector._monitored_folder_id}")
                        return
                    logger.debug(f"   DELETE in monitored folder: {self.detector.path}")
                else:
                    # No folder filtering, or no hierarchy info available
                    logger.debug(f"   DELETE event - queuing for validation by engine")
                
                is_tracked = True  # Let engine validate
            
            # Queue event for async processing
            logger.info(f"ACCEPTED: Queuing event for processing...")
            
            # Determine event type for processing
            if "Created" in event_type:
                change_type = "CREATE"
            elif "Updated" in event_type:
                change_type = "UPDATE"
            elif "Deleted" in event_type:
                change_type = "DELETE"
            else:
                logger.warning(f"   Unknown event type: {event_type}")
                return
            
            # Queue the event
            event_data = {
                'node_id': node_id,
                'name': name,
                'change_type': change_type,
                'modified_at': modified_at,
                'mime_type': mime_type,
                'size_bytes': size_bytes,
                'primary_hierarchy': primary_hierarchy,
                'event_type': event_type,
                'event_time': event_time
            }
            
            # Put in async queue (thread-safe)
            self.detector._event_queue_sync.put(event_data)
            logger.info(f"   QUEUED: Event #{self.event_count} queued for processing")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event JSON: {e}")
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)


class AlfrescoDetector(ChangeDetector):
    """
    Detector for Alfresco repositories with dual mode support:
    
    1. **Event Mode (Real-time)**: Uses Alfresco Event Gateway (Enterprise) or ActiveMQ (Community)
       - Near-instant detection (< 1 second)
       - Requires python-alfresco-api with events support
       - Automatically falls back to polling if events unavailable
    
    2. **Polling Mode (Fallback)**: Periodic checks for changes
       - Configurable interval (default: 5 minutes)
       - Works with any Alfresco version
    
    The detector automatically chooses the best available mode.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize Alfresco detector.
        
        Args:
            config: Configuration dictionary with:
                - url: Alfresco server URL
                - username: Alfresco username
                - password: Alfresco password
                - path: Path within Alfresco to monitor (optional, default: '/')
                - nodeIds: List of specific node IDs (UUIDs) to monitor (optional)
                - nodeDetails: List of node details from ACA/ADF (optional)
                - recursive: Whether to recursively monitor subfolders (default: False)
                - polling_interval: Seconds between checks (default: 300)
                - event_mode: Force event mode on/off (default: auto-detect)
        """
        super().__init__(config)
        
        # Alfresco connection parameters
        self.url = config.get('url')
        self.username = config.get('username')
        self.password = config.get('password')
        self.path = config.get('path', '/')
        self.node_ids = config.get('nodeIds', None)
        self.node_details = config.get('nodeDetails', None)
        self.recursive = config.get('recursive', False)
        
        # Mode configuration
        self.polling_interval = config.get('polling_interval', 300)  # 5 minutes default
        self.force_event_mode = config.get('event_mode', None)  # None = auto-detect
        
        # State tracking
        self._last_check_time: Optional[datetime] = None
        self._known_documents: Dict[str, dict] = {}  # node_id -> {name, path, modified, etag}
        self._running = False
        self._event_mode = False
        self._event_client: Optional[AlfrescoEventClient] = None
        self._event_queue: Queue = Queue()  # Async queue for library events
        
        # Direct STOMP connection (bypasses library) - SHARED via broadcaster
        self._broadcaster = None  # Shared event broadcaster
        self._event_queue_sync = None  # Thread-safe queue for STOMP events
        self._use_direct_stomp = False
        self._stomp_connected = False
        
        # Monitored folder node ID (for event filtering)
        self._monitored_folder_id: Optional[str] = None
        
        # State manager (for checking if documents exist in database)
        self.state_manager: Optional[StateManager] = None  # Will be set by orchestrator
        self.config_id: Optional[str] = None  # Will be set by orchestrator
        
        # Backend reference (will be injected by orchestrator)
        self.backend = None
        
        # Event deduplication (to avoid processing duplicate UPDATE events)
        self._recent_events: Dict[str, float] = {}  # node_id -> timestamp
        self._dedup_window_seconds = 60  # Ignore duplicate events within 60 seconds (after processing completes)
        
        # Validate required config
        if not self.url:
            raise ValueError("AlfrescoDetector requires 'url' in config")
        if not self.username:
            raise ValueError("AlfrescoDetector requires 'username' in config")
        if not self.password:
            raise ValueError("AlfrescoDetector requires 'password' in config")
        
        # Extract host from URL for event client
        self.host = self._extract_host(self.url)
        
        logger.info(f"AlfrescoDetector initialized - host={self.host}, path={self.path}, "
                   f"recursive={self.recursive}, polling_interval={self.polling_interval}s")
    
    def _extract_host(self, url: str) -> str:
        """Extract hostname from URL (remove protocol and path)"""
        import re
        # Remove protocol
        url = re.sub(r'^https?://', '', url)
        # Remove port and path
        host = url.split(':')[0].split('/')[0]
        return host
    
    async def start(self) -> None:
        """Start the detector"""
        if self._running:
            logger.warning("AlfrescoDetector already running")
            return
        
        logger.info(f"Starting AlfrescoDetector for {self.url}{self.path}")
        self._running = True
        
        # Verify Alfresco connection
        await self._verify_connection()
        
        # Try to initialize event mode
        if self.force_event_mode is not False:  # Allow if None (auto) or True (forced)
            # Try direct STOMP first (real event handling)
            event_initialized = await self._try_initialize_direct_stomp()
            
            # If direct STOMP failed, try library (mock implementation)
            if not event_initialized:
                logger.info("Direct STOMP not available, trying python-alfresco-api library...")
                event_initialized = await self._try_initialize_events()
            
            if event_initialized:
                self._event_mode = True
                logger.info("Event mode enabled - real-time change detection active")
            elif self.force_event_mode is True:
                raise RuntimeError("Event mode was forced but initialization failed")
            else:
                logger.info("Event mode not available - falling back to polling mode")
                self._event_mode = False
        else:
            logger.info("Event mode disabled by configuration - using polling mode")
            self._event_mode = False
        
        # Initialize baseline for tracking known documents
        # This is needed for event mode too (to filter DELETE events)
        try:
            await self._initialize_baseline()
            logger.info(f"Baseline initialized: tracking {len(self._known_documents)} documents")
        except Exception as e:
            logger.error(f"Failed to initialize baseline: {e}")
            raise
    
    async def _try_initialize_events(self) -> bool:
        """
        Try to initialize event-based monitoring.
        
        Returns:
            True if events are available and initialized, False otherwise
        """
        if not EVENTS_AVAILABLE:
            logger.info("python-alfresco-api events module not available")
            return False
        
        try:
            logger.info("Initializing Alfresco event client...")
            
            # Create event flag for detection completion
            detection_complete = asyncio.Event()
            detection_result = {'available': False}
            
            # Create event client WITHOUT auto_detect (we'll handle it ourselves)
            self._event_client = AlfrescoEventClient(
                alfresco_host=self.host,
                username=self.username,
                password=self.password,
                community_port=61613,  # STOMP port (ActiveMQ bridges from OpenWire 61616)
                auto_detect=False,  # Disable auto-detect, we'll do it manually
                debug=False  # Set to True for troubleshooting
            )
            
            # Start manual detection with callback
            logger.info("Starting event system detection...")
            
            async def detection_callback():
                """Run detection and signal completion"""
                try:
                    await self._event_client._detect_event_systems()
                    
                    # Check results
                    if self._event_client.event_gateway_available or self._event_client.activemq_available:
                        detection_result['available'] = True
                        logger.info("Event system detection completed successfully")
                    else:
                        logger.info("Event system detection completed - no systems available")
                finally:
                    detection_complete.set()
            
            # Start detection in background
            asyncio.create_task(detection_callback())
            
            # Wait for detection to complete (with timeout)
            logger.info("Waiting for event system detection to complete...")
            try:
                await asyncio.wait_for(detection_complete.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Event system detection timed out after 10 seconds")
                return False
            
            # Check what was detected
            system_info = self._event_client.get_system_info()
            logger.info(f"Event Gateway available: {system_info.get('event_gateway_available', False)}")
            logger.info(f"ActiveMQ available: {system_info.get('activemq_available', False)}")
            logger.info(f"Active system: {system_info.get('active_system', 'none')}")
            
            # Check if either system is available
            if not detection_result['available']:
                logger.info("No event system detected")
                return False
            
            # Register event handlers
            await self._register_event_handlers()
            
            # Setup content monitoring
            logger.info("Setting up content monitoring...")
            subscription_result = await self._event_client.setup_content_monitoring()
            
            if not subscription_result.get("success", True):
                logger.warning(f"Content monitoring setup failed: {subscription_result.get('error', 'Unknown')}")
                return False
                return False
            
            # Start listening
            logger.info("Starting event listener...")
            await self._event_client.start_listening()
            
            logger.info("Event-based monitoring successfully initialized")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to initialize event mode: {e}")
            if self._event_client:
                try:
                    await self._event_client.stop_listening()
                except:
                    pass
                self._event_client = None
            return False
    
    async def _try_initialize_direct_stomp(self) -> bool:
        """
        Initialize direct STOMP connection to ActiveMQ (bypasses python-alfresco-api library).
        This provides real event handling since the library only has mock implementations.
        
        Returns:
            True if STOMP connection established, False otherwise
        """
        if not STOMP_AVAILABLE:
            logger.info("stomp.py not available - cannot use direct STOMP connection")
            return False
        
        try:
            import queue
            from .alfresco_broadcaster import AlfrescoEventBroadcaster
            
            logger.info("=" * 60)
            logger.info("INITIALIZING SHARED STOMP CONNECTION (BROADCASTER)")
            logger.info("=" * 60)
            logger.info(f"Host: {self.host}")
            logger.info(f"Port: 61613 (STOMP)")
            logger.info(f"Topic: /topic/alfresco.repo.event2")
            logger.info(f"Monitored path: {self.path}")
            
            # Create thread-safe queue for receiving broadcast events
            self._event_queue_sync = queue.Queue(maxsize=1000)
            
            # Get or create shared broadcaster for this Alfresco instance
            self._broadcaster = await AlfrescoEventBroadcaster.get_instance(
                host=self.host,
                port=61613,
                username=self.username,
                password=self.password
            )
            
            # Register this detector with the broadcaster
            self._broadcaster.register_detector(self)
            
            logger.info("=" * 60)
            logger.info("SHARED STOMP EVENT MODE ACTIVE")
            logger.info("  Real-time CloudEvents from Alfresco")
            logger.info("  Latency: <1 second")
            logger.info(f"  Broadcasting to {self._broadcaster.detector_count} detector(s)")
            logger.info("=" * 60)
            
            self._use_direct_stomp = True
            self._stomp_connected = self._broadcaster.is_connected
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize shared STOMP connection: {e}", exc_info=True)
            self._event_queue_sync = None
            self._use_direct_stomp = False
            self._broadcaster = None
            return False
    
    async def _register_event_handlers(self) -> None:
        """Register handlers for Alfresco events with optional node filtering"""
        if not self._event_client:
            logger.error("ERROR: Cannot register event handlers - event client is None")
            return
        
        logger.info("=" * 60)
        logger.info("REGISTERING EVENT HANDLERS")
        logger.info("=" * 60)
        
        # Build list of node IDs to monitor (if specified)
        monitored_node_ids = set()
        
        if self.node_ids:
            # User specified specific node IDs (UUIDs from REST API)
            monitored_node_ids.update(self.node_ids)
            logger.info(f"Monitoring {len(self.node_ids)} specific nodeIds: {self.node_ids}")
        
        if self.node_details:
            # User specified node details (from ACA/ADF)
            for node in self.node_details:
                if 'id' in node:
                    monitored_node_ids.add(node['id'])
            logger.info(f"Monitoring {len(self.node_details)} nodes from nodeDetails")
        
        if monitored_node_ids:
            logger.info(f"Event filtering ENABLED for {len(monitored_node_ids)} specific node(s)")
            logger.info(f"  Monitored node IDs: {list(monitored_node_ids)}")
        else:
            logger.info("Event filtering DISABLED - monitoring ALL repository changes")
            logger.info("  This means ANY file change in Alfresco will trigger an event")
        
        logger.info("")
        logger.info("Monitored folder: " + self.path)
        
        async def handle_node_created(notification: EventNotification):
            """Handle node created events"""
            logger.info(f"EVENT RECEIVED: node.created - Processing...")
            logger.info(f"   Event type: {notification.event_type if hasattr(notification, 'event_type') else 'N/A'}")
            logger.info(f"   Node ID: {notification.node_id if hasattr(notification, 'node_id') else 'N/A'}")
            logger.info(f"   User: {notification.user_id if hasattr(notification, 'user_id') else 'N/A'}")
            logger.info(f"   Timestamp: {notification.timestamp if hasattr(notification, 'timestamp') else 'N/A'}")
            logger.info(f"   Notification object: {notification}")
            
            if not notification.node_id:
                logger.warning(f"   WARNING: No node_id in notification, skipping")
                return
                
            # Filter by node IDs if specified
            if monitored_node_ids:
                logger.info(f"   Checking against {len(monitored_node_ids)} monitored nodes...")
                if notification.node_id not in monitored_node_ids:
                    # Check if parent node is monitored (for new docs in monitored folder)
                    logger.info(f"   Node not in monitored list, checking descendants...")
                    if not self._is_descendant_of_monitored_nodes(notification):
                        logger.info(f"   SKIPPED: Not a monitored node: {notification.node_id}")
                        return
                    else:
                        logger.info(f"   ACCEPTED: Descendant of monitored node")
                else:
                    logger.info(f"   ACCEPTED: Node in monitored list")
            else:
                logger.info(f"   ACCEPTED: No filtering (monitoring all)")
            
            logger.info(f"QUEUING: Node created event - {notification.node_id}")
            await self._queue_event_from_notification(notification, ChangeType.CREATE)
        
        async def handle_node_updated(notification: EventNotification):
            """Handle node updated events"""
            logger.info(f"EVENT RECEIVED: node.updated - Processing...")
            logger.info(f"   Event type: {notification.event_type if hasattr(notification, 'event_type') else 'N/A'}")
            logger.info(f"   Node ID: {notification.node_id if hasattr(notification, 'node_id') else 'N/A'}")
            logger.info(f"   User: {notification.user_id if hasattr(notification, 'user_id') else 'N/A'}")
            logger.info(f"   Timestamp: {notification.timestamp if hasattr(notification, 'timestamp') else 'N/A'}")
            logger.info(f"   Notification object: {notification}")
            
            if not notification.node_id:
                logger.warning(f"   WARNING: No node_id in notification, skipping")
                return
                
            # Filter by node IDs if specified
            if monitored_node_ids:
                logger.info(f"   Checking against {len(monitored_node_ids)} monitored nodes...")
                if notification.node_id not in monitored_node_ids:
                    logger.info(f"   Node not in monitored list, checking descendants...")
                    if not self._is_descendant_of_monitored_nodes(notification):
                        logger.info(f"   SKIPPED: Not a monitored node: {notification.node_id}")
                        return
                    else:
                        logger.info(f"   ACCEPTED: Descendant of monitored node")
                else:
                    logger.info(f"   ACCEPTED: Node in monitored list")
            else:
                logger.info(f"   ACCEPTED: No filtering (monitoring all)")
            
            logger.info(f"QUEUING: Node updated event - {notification.node_id}")
            await self._queue_event_from_notification(notification, ChangeType.UPDATE)
        
        async def handle_node_deleted(notification: EventNotification):
            """Handle node deleted events"""
            logger.info(f"EVENT RECEIVED: node.deleted - Processing...")
            logger.info(f"   Event type: {notification.event_type if hasattr(notification, 'event_type') else 'N/A'}")
            logger.info(f"   Node ID: {notification.node_id if hasattr(notification, 'node_id') else 'N/A'}")
            logger.info(f"   User: {notification.user_id if hasattr(notification, 'user_id') else 'N/A'}")
            logger.info(f"   Timestamp: {notification.timestamp if hasattr(notification, 'timestamp') else 'N/A'}")
            logger.info(f"   Notification object: {notification}")
            
            if not notification.node_id:
                logger.warning(f"   WARNING: No node_id in notification, skipping")
                return
                
            # Filter by node IDs if specified
            if monitored_node_ids:
                logger.info(f"   Checking against {len(monitored_node_ids)} monitored nodes...")
                if notification.node_id not in monitored_node_ids:
                    logger.info(f"   Node not in monitored list, checking descendants...")
                    if not self._is_descendant_of_monitored_nodes(notification):
                        logger.info(f"   SKIPPED: Not a monitored node: {notification.node_id}")
                        return
                    else:
                        logger.info(f"   ACCEPTED: Descendant of monitored node")
                else:
                    logger.info(f"   ACCEPTED: Node in monitored list")
            else:
                logger.info(f"   ACCEPTED: No filtering (monitoring all)")
            
            logger.info(f"QUEUING: Node deleted event - {notification.node_id}")
            await self._queue_event_from_notification(notification, ChangeType.DELETE)
        
        # Register handlers
        logger.info("")
        logger.info("Registering handler functions with event client...")
        self._event_client.register_event_handler("node.created", handle_node_created)
        logger.info("  Registered: node.created")
        
        self._event_client.register_event_handler("node.updated", handle_node_updated)
        logger.info("  Registered: node.updated")
        
        self._event_client.register_event_handler("node.deleted", handle_node_deleted)
        logger.info("  Registered: node.deleted")
        
        logger.info("")
        logger.info("SUCCESS: ALL EVENT HANDLERS REGISTERED")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Waiting for events from Alfresco...")
        logger.info("   To test: Create, update, or delete a file in Alfresco")
    
    def _is_descendant_of_monitored_nodes(self, notification: EventNotification) -> bool:
        """
        Check if a node event should be processed based on parent path.
        
        For now, accepts all events if no specific nodes are configured.
        Future: Could fetch node path from Alfresco API to check if it's under monitored folder.
        
        Args:
            notification: Event notification
            
        Returns:
            True if event should be processed, False to skip
        """
        # If monitoring specific nodes, for now we're conservative and only
        # process events for exact node ID matches.
        # In the future, we could query the Alfresco API to get the node's path
        # and check if it's a descendant of monitored folders.
        
        # If path-based monitoring (not specific nodes), accept all document events
        if not self.node_ids and not self.node_details:
            # Check if it's a document type (not folder, not other system nodes)
            # This basic check helps reduce noise from non-document events
            return True
        
        return False
    
    async def _queue_event_from_notification(self, notification: EventNotification, change_type: ChangeType) -> None:
        """
        Convert Alfresco event notification to ChangeEvent and queue it.
        
        Args:
            notification: Event notification from Alfresco
            change_type: Type of change (CREATE, UPDATE, DELETE)
        """
        try:
            logger.info(f"CONVERTING notification to ChangeEvent...")
            
            # Extract node information
            node_id = notification.node_id
            logger.info(f"   Node ID: {node_id}")
            
            # For now, use node_id as path (we can fetch full metadata if needed)
            # TODO: Consider fetching node metadata for more accurate path
            path = f"alfresco://node/{node_id}"
            logger.info(f"   Path: {path}")
            
            ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
            logger.info(f"   Ordinal: {ordinal}")
            
            metadata = FileMetadata(
                source_type='alfresco',
                path=path,
                ordinal=ordinal,
                size_bytes=0,  # Size not available in event
                extra={
                    'node_id': node_id,
                    'event_type': notification.event_type,
                    'user_id': notification.user_id if hasattr(notification, 'user_id') else None
                }
            )
            
            event = ChangeEvent(
                metadata=metadata,
                change_type=change_type,
                timestamp=datetime.utcnow()
            )
            
            # Queue the event
            logger.info(f"   Putting event in queue...")
            await self._event_queue.put(event)
            logger.info(f"EVENT QUEUED: {change_type.value} for {node_id}")
            logger.info(f"   Queue size: {self._event_queue.qsize()}")
            
        except Exception as e:
            logger.exception(f"ERROR queuing event from notification: {e}")
            logger.error(f"   Notification: {notification}")
            logger.error(f"   Change type: {change_type}")
    
    async def stop(self) -> None:
        """Stop the detector"""
        logger.info("Stopping AlfrescoDetector")
        self._running = False
        
        # Unregister from shared broadcaster
        if self._broadcaster:
            try:
                logger.info("Unregistering from shared event broadcaster...")
                self._broadcaster.unregister_detector(self)
                self._broadcaster = None
                logger.info("Unregistered from broadcaster")
            except Exception as e:
                logger.warning(f"Error unregistering from broadcaster: {e}")
        
        # Stop event client if active
        if self._event_client:
            try:
                logger.info("Stopping event client...")
                await self._event_client.stop_listening()
                self._event_client = None
                logger.info("Event client stopped")
            except Exception as e:
                logger.warning(f"Error stopping event client: {e}")
    
    async def get_changes(self) -> AsyncGenerator[Optional[ChangeEvent], None]:
        """
        Async generator that yields change events as they are detected.
        
        **Event Mode**: Yields events from the queue as they arrive from Alfresco events
        **Polling Mode**: Periodically checks for changes and yields detected events
        
        Yields:
            ChangeEvent for each detected change, or None during wait periods
        """
        if not self._running:
            logger.warning("AlfrescoDetector not started - call start() first")
            return
        
        if self._event_mode:
            logger.info("Starting Alfresco change monitoring (EVENT MODE - real-time)")
            async for event in self._get_changes_event_mode():
                yield event
        else:
            logger.info(f"Starting Alfresco change monitoring (POLLING MODE - every {self.polling_interval}s)")
            async for event in self._get_changes_polling_mode():
                yield event
    
    async def _get_changes_event_mode(self) -> AsyncGenerator[Optional[ChangeEvent], None]:
        """
        Get changes in event mode - yields events from queue as they arrive.
        Handles both direct STOMP events and library events.
        """
        logger.info("EVENT MODE: Starting event processing loop")
        logger.info(f"   Running: {self._running}")
        logger.info(f"   Using direct STOMP: {self._use_direct_stomp}")
        if self._use_direct_stomp:
            logger.info(f"   Direct STOMP queue initial size: {self._event_queue_sync.qsize() if self._event_queue_sync else 0}")
        else:
            logger.info(f"   Library queue initial size: {self._event_queue.qsize()}")
        
        iteration = 0
        while self._running:
            try:
                iteration += 1
                
                # Check broadcaster connection status
                if self._use_direct_stomp and self._broadcaster:
                    self._stomp_connected = self._broadcaster.is_connected
                    if not self._stomp_connected:
                        logger.warning("Broadcaster connection lost")
                
                if iteration % 600 == 0:  # Log heartbeat every 600 iterations (~10 minutes)
                    if self._use_direct_stomp and self._event_queue_sync and self._broadcaster:
                        conn_status = "connected" if self._stomp_connected else "disconnected"
                        detector_count = self._broadcaster.detector_count
                        logger.info(f"EVENT MODE: Heartbeat - iteration {iteration}, STOMP queue size: {self._event_queue_sync.qsize()}, "
                                  f"status: {conn_status}, detectors: {detector_count}")
                    elif self._use_direct_stomp and self._event_queue_sync:
                        conn_status = "connected" if self._stomp_connected else "disconnected"
                        logger.info(f"EVENT MODE: Heartbeat - iteration {iteration}, STOMP queue size: {self._event_queue_sync.qsize()}, status: {conn_status}")
                    else:
                        logger.info(f"EVENT MODE: Heartbeat - iteration {iteration}, library queue size: {self._event_queue.qsize()}")
                
                # Check for direct STOMP events first
                if self._use_direct_stomp and self._event_queue_sync:
                    try:
                        # Check sync queue (non-blocking)
                        event_data = self._event_queue_sync.get_nowait()

                        # Convert to ChangeEvent
                        logger.info(f"STOMP EVENT PROCESSING: {event_data['change_type']} for {event_data['name']}")
                        
                        # FILTER: Check if this event is for our monitored folder
                        primary_hierarchy = event_data.get('primary_hierarchy', [])
                        if self._monitored_folder_id and primary_hierarchy:
                            if self._monitored_folder_id not in primary_hierarchy:
                                logger.info(f"   SKIPPED: Event not in monitored folder")
                                logger.info(f"      Event hierarchy: {primary_hierarchy[:2] if len(primary_hierarchy) > 2 else primary_hierarchy}")
                                logger.info(f"      Monitored folder: {self._monitored_folder_id}")
                                continue  # Skip this event

                        # Construct path
                        file_path = f"{self.path}{event_data['name']}" if self.path.endswith('/') else f"{self.path}/{event_data['name']}"
                        
                        # Create FileMetadata
                        metadata = FileMetadata(
                            source_type='alfresco',
                            path=file_path,
                            ordinal=int(datetime.utcnow().timestamp() * 1_000_000),
                            size_bytes=event_data.get('size_bytes', 0),
                            mime_type=event_data.get('mime_type'),
                            modified_timestamp=event_data.get('modified_at'),
                            extra={
                                'node_id': event_data['node_id'],
                                'name': event_data['name'],
                                'event_type': event_data['event_type'],
                                'primary_hierarchy': event_data.get('primary_hierarchy', [])
                            }
                        )
                        
                        # Handle different event types
                        if event_data['change_type'] == 'DELETE':
                            logger.info(f"STOMP EVENT: DELETE for {file_path}")
                            # For DELETE, yield event for engine to handle removal from stores
                            change_event = ChangeEvent(change_type=ChangeType.DELETE, metadata=metadata, timestamp=None)
                            logger.info(f"STOMP EVENT CONVERTED: {change_event.change_type.value} for {change_event.metadata.path}")
                            yield change_event
                        
                        elif event_data['change_type'] == 'CREATE':
                            # For CREATE, process via backend (full pipeline) directly
                            logger.info(f"STOMP EVENT: CREATE for {file_path} - processing via backend")
                            
                            # Record this event to block subsequent UPDATE events
                            import time
                            node_id = event_data['node_id']
                            self._recent_events[node_id] = time.time()
                            
                            try:
                                await self._process_via_backend(
                                    node_id=event_data['node_id'],
                                    filename=event_data['name'],
                                    file_path=file_path
                                )
                                logger.info(f"SUCCESS: Processed CREATE for {file_path} via backend (full pipeline)")
                            except Exception as e:
                                logger.error(f"ERROR: Failed to process CREATE for {file_path}: {e}")
                        
                        elif event_data['change_type'] == 'UPDATE':
                            # For UPDATE, check deduplication first
                            node_id = event_data['node_id']
                            filename = event_data['name']
                            
                            # Check if this is a duplicate event (within dedup window)
                            import time
                            current_time = time.time()
                            last_event_time = self._recent_events.get(node_id, 0)
                            time_since_last = current_time - last_event_time if last_event_time > 0 else 999999
                            
                            if time_since_last < self._dedup_window_seconds:
                                logger.info(f"STOMP EVENT: Ignoring duplicate UPDATE for {file_path} "
                                          f"(last event {time_since_last:.1f}s ago)")
                                continue
                            
                            logger.info(f"STOMP EVENT: UPDATE for {file_path}")
                            
                            # Check if document actually exists in database
                            doc_exists = False
                            if self.state_manager and self.config_id:
                                try:
                                    # Try to find by node_id (source_id)
                                    existing_state = await self.state_manager.get_state_by_source_id(self.config_id, node_id)
                                    if existing_state:
                                        doc_exists = True
                                        logger.info(f"STOMP EVENT: Document exists in database (source_id: {node_id})")
                                    else:
                                        # Also try by doc_id path
                                        from incremental_updates.state_manager import StateManager
                                        doc_id = StateManager.make_doc_id(self.config_id, file_path)
                                        existing_state = await self.state_manager.get_state(doc_id)
                                        if existing_state:
                                            doc_exists = True
                                            logger.info(f"STOMP EVENT: Document exists in database (doc_id: {doc_id})")
                                except Exception as e:
                                    logger.debug(f"Could not check document existence: {e}")
                            
                            if not doc_exists:
                                # Document doesn't exist - treat as CREATE
                                logger.info(f"STOMP EVENT: UPDATE for NEW document - treating as CREATE for {file_path}")
                                
                                # Record this event BEFORE processing
                                self._recent_events[node_id] = current_time
                                
                                try:
                                    await self._process_via_backend(
                                        node_id=node_id,
                                        filename=filename,
                                        file_path=file_path
                                    )
                                    logger.info(f"SUCCESS: Processed CREATE for {file_path} via backend (full pipeline)")
                                except Exception as e:
                                    logger.error(f"ERROR: Failed to process CREATE for {file_path}: {e}")
                            else:
                                # Document exists - emit DELETE with callback for ADD
                                logger.info(f"STOMP EVENT: UPDATE for EXISTING document - emitting DELETE with callback for {file_path}")
                                
                                # Record this event BEFORE processing
                                self._recent_events[node_id] = current_time
                                
                                # Create callback for ADD operation (to be called after DELETE completes)
                                async def add_callback():
                                    logger.info(f"UPDATE: DELETE completed, now processing ADD for {file_path}")
                                    try:
                                        await self._process_via_backend(
                                            node_id=node_id,
                                            filename=filename,
                                            file_path=file_path
                                        )
                                        logger.info(f"SUCCESS: UPDATE completed for {file_path}")
                                    except Exception as e:
                                        logger.error(f"ERROR: Failed to process ADD for {file_path}: {e}")
                                
                                # Create DELETE event with callback
                                delete_event = ChangeEvent(
                                    metadata=metadata,
                                    change_type=ChangeType.DELETE,
                                    timestamp=None,
                                    is_modify_delete=True,
                                    modify_callback=add_callback
                                )
                                logger.info(f"STOMP EVENT CONVERTED: DELETE (for UPDATE) with callback for {file_path}")
                                yield delete_event
                            
                            # Clean up old entries (older than 2x dedup window)
                            cutoff_time = current_time - (self._dedup_window_seconds * 2)
                            self._recent_events = {
                                k: v for k, v in self._recent_events.items() 
                                if v > cutoff_time
                            }
                        
                        continue
                        
                    except Exception as queue_exc:
                        if "Empty" not in str(type(queue_exc)):
                            logger.error(f"Error processing STOMP event: {queue_exc}")
                
                # Wait for library events from async queue (with timeout)
                try:
                    logger.debug(f"   Waiting for library event (timeout 5s)...")
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=5.0)
                    if event:
                        logger.info(f"LIBRARY EVENT DEQUEUED: {event.change_type.value} for {event.metadata.path}")
                        logger.info(f"   Queue remaining: {self._event_queue.qsize()}")
                        yield event
                    else:
                        logger.debug(f"   Got None event from queue")
                        yield None
                except asyncio.TimeoutError:
                    # No events in queue, yield None to allow other processing
                    logger.debug(f"   Timeout - no events in queue")
                    yield None
                    
            except asyncio.CancelledError:
                logger.info("Event mode monitoring cancelled")
                self._running = False
                break
            
            except Exception as e:
                logger.exception(f"ERROR in event mode change detection: {e}")
                await asyncio.sleep(5)
                yield None
        
        logger.info("EVENT MODE: Exiting event processing loop")
    
    async def _get_changes_polling_mode(self) -> AsyncGenerator[Optional[ChangeEvent], None]:
        """
        Get changes in polling mode - periodically checks for changes.
        """
        while self._running:
            try:
                # Wait for polling interval
                logger.debug(f"Waiting {self.polling_interval}s until next check...")
                await asyncio.sleep(self.polling_interval)
                
                if not self._running:
                    break
                
                # Check for changes
                logger.debug("Checking for Alfresco changes...")
                current_state = await self._get_current_state()
                
                # Compare with known state and yield events
                async for event in self._detect_changes(current_state):
                    if event:
                        yield event
                
                # Update last check time
                self._last_check_time = datetime.utcnow()
                
                # Yield None to allow other processing
                yield None
                
            except asyncio.CancelledError:
                logger.info("AlfrescoDetector monitoring cancelled")
                self._running = False
                break
            
            except Exception as e:
                logger.exception(f"Error in Alfresco change detection: {e}")
                # Continue monitoring despite errors
                await asyncio.sleep(10)
                yield None
    
    async def _verify_connection(self) -> None:
        """Verify connection to Alfresco server"""
        logger.info(f"Verifying Alfresco connection to {self.url}")
        
        try:
            # Import here to avoid dependency issues if not installed
            from python_alfresco_api import ClientFactory
            
            # Remove /alfresco suffix if present
            api_base_url = self.url.rstrip('/')
            if api_base_url.endswith('/alfresco'):
                api_base_url = api_base_url[:-9]
            
            # Create client and test connection
            loop = asyncio.get_event_loop()
            factory = await loop.run_in_executor(
                None,
                lambda: ClientFactory(
                    base_url=api_base_url,
                    username=self.username,
                    password=self.password
                )
            )
            
            core_client = await loop.run_in_executor(None, factory.create_core_client)
            
            # Test connection by getting a node (use -root- which is always available)
            await loop.run_in_executor(None, lambda: core_client.nodes.get("-root-"))
            
            logger.info(f"Successfully connected to Alfresco at {self.url}")
            
        except ImportError:
            logger.warning("python-alfresco-api not installed, will use CMIS fallback")
            # Try CMIS as fallback
            try:
                from cmislib import CmisClient
                import os
                
                cmis_url = os.getenv("CMIS_URL", f"{self.url.rstrip('/')}/api/-default-/public/cmis/versions/1.1/atom")
                loop = asyncio.get_event_loop()
                cmis_client = await loop.run_in_executor(
                    None,
                    lambda: CmisClient(cmis_url, self.username, self.password)
                )
                repo = cmis_client.defaultRepository
                
                logger.info(f"Successfully connected to Alfresco via CMIS at {cmis_url}")
            except Exception as e:
                raise ConnectionError(f"Failed to connect to Alfresco: {e}")
        
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Alfresco at {self.url}: {e}")
        
        # Resolve monitored folder path to node ID for event filtering
        await self._resolve_monitored_folder_id()
    
    async def _resolve_monitored_folder_id(self) -> None:
        """Resolve the monitored folder path to a node ID for event filtering"""
        if not self.path or self.path == '/':
            logger.info("Monitoring root - no folder filtering needed")
            return
        
        logger.info(f"Resolving monitored folder path to node ID: {self.path}")
        
        try:
            from python_alfresco_api import ClientFactory
            
            api_base_url = self.url.rstrip('/')
            if api_base_url.endswith('/alfresco'):
                api_base_url = api_base_url[:-9]
            
            logger.info(f"   Creating ClientFactory with base_url: {api_base_url}")
            
            loop = asyncio.get_event_loop()
            factory = await loop.run_in_executor(
                None,
                lambda: ClientFactory(
                    base_url=api_base_url,
                    username=self.username,
                    password=self.password
                )
            )
            
            logger.info(f"   Creating core client...")
            core_client = await loop.run_in_executor(None, factory.create_core_client)
            
            # Get node by path
            path_clean = self.path.lstrip('/')
            logger.info(f"   Getting node by path: '{path_clean}' from -root-")
            node = await loop.run_in_executor(
                None,
                lambda: core_client.nodes.get("-root-", relative_path=path_clean)
            )
            
            logger.info(f"   Node retrieval result: {type(node)}")
            
            # NodeResponse has 'entry' attribute which contains the actual Node with 'id'
            if node and hasattr(node, 'entry') and hasattr(node.entry, 'id'):
                self._monitored_folder_id = node.entry.id
                logger.info(f"SUCCESS: EVENT FILTERING ENABLED")
                logger.info(f"   Monitoring folder: {self.path}")
                logger.info(f"   Folder Node ID: {self._monitored_folder_id}")
                logger.info(f"   Events outside this folder will be SKIPPED")
            elif node and hasattr(node, 'id'):
                # Fallback for direct Node objects
                self._monitored_folder_id = node.id
                logger.info(f"SUCCESS: EVENT FILTERING ENABLED")
                logger.info(f"   Monitoring folder: {self.path}")
                logger.info(f"   Folder Node ID: {self._monitored_folder_id}")
                logger.info(f"   Events outside this folder will be SKIPPED")
            else:
                logger.warning(f"Could not resolve folder node ID for {self.path}")
                logger.warning(f"   Node type: {type(node)}")
                logger.warning(f"   Has 'entry': {hasattr(node, 'entry') if node else 'N/A'}")
                logger.warning(f"   Will accept all events (no folder filtering)")
                
        except Exception as e:
            logger.error(f"Failed to resolve monitored folder ID: {e}", exc_info=True)
            logger.warning(f"Event filtering disabled - will accept all events")
    
    async def _initialize_baseline(self) -> None:
        """Get initial state of all documents in the monitored path"""
        logger.info("Initializing baseline state...")
        
        current_state = await self._get_current_state()
        self._known_documents = current_state
        
        logger.info(f"Baseline: {len(self._known_documents)} documents tracked")
    
    async def _get_current_state(self) -> Dict[str, dict]:
        """
        Get current state of all documents in Alfresco path.
        
        Returns:
            Dict mapping node_id -> {name, path, modified, size, etag}
        """
        from sources.alfresco import AlfrescoSource
        
        # Create Alfresco source to list files
        source_config = {
            'url': self.url,
            'username': self.username,
            'password': self.password,
            'path': self.path,
            'nodeIds': self.node_ids,
            'nodeDetails': self.node_details,
            'recursive': self.recursive
        }
        
        loop = asyncio.get_event_loop()
        source = await loop.run_in_executor(None, lambda: AlfrescoSource(source_config))
        
        # List all files
        files = await loop.run_in_executor(None, source.list_files)
        
        # Build state dict
        current_state = {}
        for file_info in files:
            node_id = file_info['id']
            
            # Extract metadata for comparison
            metadata = {
                'name': file_info['name'],
                'path': file_info['path'],
                'content_type': file_info.get('content_type', ''),
            }
            
            # Try to get modification time and size from alfresco_object or cmis_object
            if file_info.get('alfresco_object'):
                # From Alfresco REST API response
                obj = file_info['alfresco_object']
                if hasattr(obj, 'entry'):
                    entry = obj.entry
                    if hasattr(entry, 'modified_at'):
                        metadata['modified'] = entry.modified_at
                    if hasattr(entry, 'content') and hasattr(entry.content, 'size_in_bytes'):
                        metadata['size'] = entry.content.size_in_bytes
                elif isinstance(obj, dict) and 'entry' in obj:
                    entry = obj['entry']
                    metadata['modified'] = entry.get('modifiedAt', '')
                    if 'content' in entry:
                        metadata['size'] = entry['content'].get('sizeInBytes', 0)
            
            elif file_info.get('cmis_object'):
                # From CMIS
                cmis_obj = file_info['cmis_object']
                metadata['modified'] = cmis_obj.properties.get('cmis:lastModificationDate', '')
                metadata['size'] = cmis_obj.properties.get('cmis:contentStreamLength', 0)
            
            current_state[node_id] = metadata
        
        return current_state
    
    async def _detect_changes(self, current_state: Dict[str, dict]) -> AsyncGenerator[ChangeEvent, None]:
        """
        Compare current state with known state and yield change events.
        
        Args:
            current_state: Dict of node_id -> metadata
        """
        # Detect new or modified documents
        for node_id, current_meta in current_state.items():
            if node_id not in self._known_documents:
                # New document
                logger.info(f"New document detected: {current_meta['path']}")
                
                ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
                
                # Get modified timestamp if available
                modified_timestamp = str(current_meta.get('modified', '')) if current_meta.get('modified') else None
                
                metadata = FileMetadata(
                    source_type='alfresco',
                    path=current_meta['path'],
                    ordinal=ordinal,
                    size_bytes=current_meta.get('size', 0),
                    modified_timestamp=modified_timestamp,
                    extra={
                        'node_id': node_id,
                        'content_type': current_meta.get('content_type', ''),
                        'modified': str(current_meta.get('modified', ''))
                    }
                )
                
                event = ChangeEvent(
                    metadata=metadata,
                    change_type=ChangeType.CREATE,
                    timestamp=datetime.utcnow()
                )
                
                yield event
            
            else:
                # Check if modified
                known_meta = self._known_documents[node_id]
                
                # Compare modification time or size
                if (current_meta.get('modified') != known_meta.get('modified') or
                    current_meta.get('size') != known_meta.get('size')):
                    
                    logger.info(f"Modified document detected: {current_meta['path']}")
                    
                    ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
                    
                    # Get modified timestamp if available
                    modified_timestamp = str(current_meta.get('modified', '')) if current_meta.get('modified') else None
                    
                    metadata = FileMetadata(
                        source_type='alfresco',
                        path=current_meta['path'],
                        ordinal=ordinal,
                        size_bytes=current_meta.get('size', 0),
                        modified_timestamp=modified_timestamp,
                        extra={
                            'node_id': node_id,
                            'content_type': current_meta.get('content_type', ''),
                            'modified': str(current_meta.get('modified', ''))
                        }
                    )
                    
                    event = ChangeEvent(
                        metadata=metadata,
                        change_type=ChangeType.UPDATE,
                        timestamp=datetime.utcnow()
                    )
                    
                    yield event
        
        # Detect deleted documents
        for node_id, known_meta in self._known_documents.items():
            if node_id not in current_state:
                logger.info(f"Deleted document detected: {known_meta['path']}")
                
                ordinal = int(datetime.utcnow().timestamp() * 1_000_000)
                metadata = FileMetadata(
                    source_type='alfresco',
                    path=known_meta['path'],
                    ordinal=ordinal,
                    size_bytes=0,
                    extra={
                        'node_id': node_id
                    }
                )
                
                event = ChangeEvent(
                    metadata=metadata,
                    change_type=ChangeType.DELETE,
                    timestamp=datetime.utcnow()
                )
                
                yield event
        
        # Update known state
        self._known_documents = current_state
    
    async def list_all_files(self) -> List[FileMetadata]:
        """
        List all files with metadata (for initial/periodic sync).
        
        Returns:
            List of FileMetadata for all documents in the monitored Alfresco path/nodes
        """
        logger.info("Listing all files in Alfresco repository...")
        
        try:
            # Get current state which includes all files
            current_state = await self._get_current_state()
            
            # Convert to list of FileMetadata
            file_list = []
            for node_id, metadata in current_state.items():
                # Get modified timestamp if available
                modified_timestamp = str(metadata.get('modified', '')) if metadata.get('modified') else None
                
                file_metadata = FileMetadata(
                    source_type='alfresco',
                    path=metadata['path'],
                    ordinal=int(datetime.utcnow().timestamp() * 1_000_000),
                    size_bytes=metadata.get('size', 0),
                    mime_type=metadata.get('content_type'),
                    modified_timestamp=modified_timestamp,
                    extra={
                        'node_id': node_id,
                        'name': metadata['name'],
                        'modified': str(metadata.get('modified', ''))
                    }
                )
                file_list.append(file_metadata)
            
            logger.info(f"Listed {len(file_list)} files from Alfresco")
            return file_list
            
        except Exception as e:
            logger.error(f"Error listing Alfresco files: {e}")
            raise
    
    async def _process_via_backend(self, node_id: str, filename: str, file_path: str):
        """
        Process Alfresco file by calling backend._process_documents_async() directly.
        Uses the complete pipeline with DocumentProcessor.
        
        Args:
            node_id: Alfresco node ID
            filename: File name for logging
            file_path: Full path for the file (e.g., /Shared/GraphRAG/space-station.txt)
        """
        if not self.backend:
            logger.error("Backend not injected into AlfrescoDetector - cannot process file")
            return
        
        logger.info(f"Processing {filename} (node: {node_id}) via backend (full pipeline)")
        
        try:
            skip_graph = getattr(self, 'skip_graph', False)
            processing_id = f"incremental_alf_{node_id[:8]}"
            
            # Build nodeDetails like KG Spaces does (this already works in AlfrescoSource)
            node_details = [{
                'id': node_id,
                'name': filename,
                'path': file_path,
                'isFile': True,
                'isFolder': False
            }]
            
            # Build Alfresco config using nodeDetails (not nodeIds)
            alfresco_config = {
                'url': self.url,
                'username': self.username,
                'password': self.password,
                'path': self.path,
                'nodeDetails': node_details,  # Use existing nodeDetails mode
                'recursive': False
            }
            
            # Call backend method directly
            await self.backend._process_documents_async(
                processing_id=processing_id,
                data_source='alfresco',
                config_id=self.config_id,
                skip_graph=skip_graph,
                alfresco_config=alfresco_config
            )
            
            logger.info(f"Successfully processed {filename} via backend pipeline")
            
            # Create document_state record after successful processing
            # This is needed because incremental processing bypasses /api/ingest endpoint
            # which would normally trigger the background task
            if self.state_manager:
                try:
                    await self._create_document_state_from_processing_status(
                        processing_id, filename, node_id, file_path
                    )
                except Exception as e:
                    logger.error(f"Failed to create document_state for {filename}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process {filename} via backend: {e}")
            raise
    
    async def _create_document_state_from_processing_status(
        self, processing_id: str, filename: str, node_id: str, file_path: str
    ):
        """Create document_state record after successful processing"""
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
        
        # Extract real metadata from the processed document
        source_id = doc.metadata.get('alfresco_id') or node_id
        modified_timestamp = doc.metadata.get('modified_at')
        
        # Create doc_id in stable format using alfresco://node_id (consistent with hybrid_system)
        # This is stable across renames/moves
        stable_path = doc.metadata.get('stable_file_path') or f"alfresco://{source_id}"
        doc_id = f"{self.config_id}:{stable_path}"
        logger.info(f"Creating document_state with stable doc_id: {doc_id}")
        
        # Compute actual content hash from document text
        content_hash = None
        if hasattr(doc, 'text') and doc.text:
            from incremental_updates.state_manager import StateManager
            content_hash = StateManager.compute_content_hash(doc.text)
        
        # Use document's ordinal (modification timestamp) if available
        ordinal = doc.metadata.get('ordinal')
        if not ordinal and modified_timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(modified_timestamp.replace('Z', '+00:00'))
                ordinal = int(dt.timestamp() * 1_000_000)
            except:
                ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        elif not ordinal:
            ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        
        # Record synced timestamps (document is already in vector/search stores)
        now = datetime.now(timezone.utc)
        
        # Create document state with real data
        doc_state = DocumentState(
            doc_id=doc_id,
            config_id=self.config_id,
            source_path=file_path,  # Use full path, not just filename
            ordinal=ordinal,
            content_hash=content_hash,
            source_id=source_id,
            modified_timestamp=modified_timestamp,
            vector_synced_at=now,
            search_synced_at=now,
            graph_synced_at=now if not getattr(self, 'skip_graph', False) else None
        )
        
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for {filename}: {doc_id}")
