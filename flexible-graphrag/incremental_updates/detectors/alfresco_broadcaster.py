"""
Shared Alfresco Event Broadcaster

Manages a single STOMP connection per Alfresco server and broadcasts events
to all registered detectors. This allows multiple datasource configs to receive
real-time events from the same Alfresco instance.

Architecture:
- ONE STOMP connection per Alfresco server (host:port)
- Multiple detectors can register with the broadcaster
- Events are broadcast to ALL registered detectors
- Each detector applies its own filtering logic

Usage:
    # In orchestrator or detector factory
    broadcaster = AlfrescoEventBroadcaster.get_instance(host, port, username, password)
    await broadcaster.register_detector(detector)
    
    # Detector receives events via its _event_queue_sync
"""

import asyncio
import logging
import json
import queue
from typing import Dict, Set, Optional
from datetime import datetime

logger = logging.getLogger("flexible_graphrag.incremental.detectors.alfresco_broadcaster")

try:
    import stomp
    STOMP_AVAILABLE = True
except ImportError:
    STOMP_AVAILABLE = False
    logger.warning("stomp.py not available - event broadcasting disabled")


class SharedAlfrescoEventListener(stomp.ConnectionListener if STOMP_AVAILABLE else object):
    """
    Shared STOMP listener that broadcasts events to all registered detectors
    """
    
    def __init__(self, broadcaster: 'AlfrescoEventBroadcaster'):
        self.broadcaster = broadcaster
        self.event_count = 0
    
    def on_error(self, frame):
        logger.error(f"STOMP ERROR: {frame.body if hasattr(frame, 'body') else frame}")
    
    def on_connected(self, frame):
        logger.info("STOMP CONNECTED to ActiveMQ (Shared Broadcaster)")
        logger.info(f"   Session: {frame.headers.get('session', 'N/A') if hasattr(frame, 'headers') else 'N/A'}")
        self.broadcaster._connected = True
    
    def on_disconnected(self):
        logger.warning("STOMP DISCONNECTED from ActiveMQ (Shared Broadcaster)")
        self.broadcaster._connected = False
    
    def on_message(self, frame):
        """Receive event and broadcast to all registered detectors"""
        try:
            self.event_count += 1
            
            # Parse CloudEvents format
            event = json.loads(frame.body)
            event_type = event.get("type", "")
            event_id = event.get("id", "")
            event_time = event.get("time", "")
            
            # Extract node info
            data = event.get("data", {})
            resource = data.get("resource", {})
            resource_before = data.get("resourceBefore", {})
            
            node_id = resource.get("id")
            name = resource.get("name")
            node_type = resource.get("nodeType", "")
            is_file = resource.get("isFile", False)
            is_folder = resource.get("isFolder", False)
            modified_at = resource.get("modifiedAt")
            primary_hierarchy = resource.get("primaryHierarchy", [])
            
            content = resource.get("content", {})
            mime_type = content.get("mimeType")
            size_bytes = content.get("sizeInBytes", 0)
            
            logger.info(f"BROADCAST EVENT #{self.event_count} RECEIVED: {event_type}")
            logger.info(f"   Event ID: {event_id}")
            logger.info(f"   Node ID: {node_id}")
            logger.info(f"   Name: {name}")
            logger.info(f"   Type: {node_type}")
            logger.info(f"   Is File: {is_file}, Is Folder: {is_folder}")
            
            # Only broadcast file events
            if not is_file:
                logger.info(f"   SKIPPED: Not a file (folder or other type)")
                return
            
            # Determine change type
            if "Created" in event_type:
                change_type = "CREATE"
            elif "Updated" in event_type:
                change_type = "UPDATE"
            elif "Deleted" in event_type:
                change_type = "DELETE"
            else:
                logger.warning(f"   Unknown event type: {event_type}")
                return
            
            # Create event data
            event_data = {
                'node_id': node_id,
                'name': name,
                'change_type': change_type,
                'modified_at': modified_at,
                'mime_type': mime_type,
                'size_bytes': size_bytes,
                'primary_hierarchy': primary_hierarchy,
                'event_type': event_type,
                'event_time': event_time,
                'resource': resource,
                'resource_before': resource_before
            }
            
            # Broadcast to all registered detectors
            broadcasted_count = self.broadcaster.broadcast_event(event_data)
            logger.info(f"   BROADCAST: Event sent to {broadcasted_count} detector(s)")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event JSON: {e}")
        except Exception as e:
            logger.error(f"Error broadcasting event: {e}", exc_info=True)


class AlfrescoEventBroadcaster:
    """
    Singleton broadcaster for each Alfresco instance (host:port)
    Manages STOMP connection and broadcasts events to registered detectors
    """
    
    _instances: Dict[str, 'AlfrescoEventBroadcaster'] = {}
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_instance(cls, host: str, port: int, username: str, password: str) -> 'AlfrescoEventBroadcaster':
        """Get or create broadcaster instance for this Alfresco server"""
        key = f"{host}:{port}"
        
        if key not in cls._instances:
            async with cls._lock:
                if key not in cls._instances:  # Double-check after acquiring lock
                    instance = cls(host, port, username, password)
                    await instance.connect()
                    cls._instances[key] = instance
                    logger.info(f"Created new broadcaster for {key}")
        
        return cls._instances[key]
    
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        
        self._stomp_conn = None
        self._stomp_listener = None
        self._connected = False
        self._registered_detectors: Set['AlfrescoDetector'] = set()
        
        logger.info(f"Initializing AlfrescoEventBroadcaster for {host}:{port}")
    
    async def connect(self):
        """Establish STOMP connection"""
        if not STOMP_AVAILABLE:
            logger.error("Cannot connect - stomp.py not available")
            return False
        
        try:
            logger.info(f"Connecting to ActiveMQ at {self.host}:{self.port}...")
            
            # Create STOMP connection
            self._stomp_conn = stomp.Connection(
                host_and_ports=[(self.host, self.port)],
                heartbeats=(3600000, 3600000)
            )
            
            # Create and set listener
            self._stomp_listener = SharedAlfrescoEventListener(self)
            self._stomp_conn.set_listener('shared-alfresco-listener', self._stomp_listener)
            
            # Connect
            self._stomp_conn.connect(
                username=self.username,
                password=self.password,
                wait=True,
                headers={'client-id': 'flexible-graphrag-broadcaster'}
            )
            logger.info(f"SUCCESS: Connected to ActiveMQ on {self.host}:{self.port}")
            
            # Subscribe to events topic
            topic = "/topic/alfresco.repo.event2"
            self._stomp_conn.subscribe(
                destination=topic,
                id="flexible-graphrag-broadcast-sub",
                ack="auto"
            )
            logger.info(f"SUCCESS: Subscribed to {topic}")
            
            self._connected = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect broadcaster: {e}", exc_info=True)
            if self._stomp_conn:
                try:
                    self._stomp_conn.disconnect()
                except:
                    pass
                self._stomp_conn = None
            self._stomp_listener = None
            return False
    
    def register_detector(self, detector: 'AlfrescoDetector'):
        """Register a detector to receive broadcast events"""
        self._registered_detectors.add(detector)
        logger.info(f"Registered detector {detector.config_id} with broadcaster")
        logger.info(f"   Monitored path: {detector.path}")
        logger.info(f"   Total detectors: {len(self._registered_detectors)}")
    
    def unregister_detector(self, detector: 'AlfrescoDetector'):
        """Unregister a detector from receiving broadcast events"""
        self._registered_detectors.discard(detector)
        logger.info(f"Unregistered detector {detector.config_id} from broadcaster")
        logger.info(f"   Remaining detectors: {len(self._registered_detectors)}")
    
    def broadcast_event(self, event_data: Dict) -> int:
        """Broadcast event to all registered detectors"""
        count = 0
        for detector in self._registered_detectors:
            try:
                # Put event in detector's queue (non-blocking)
                if detector._event_queue_sync:
                    detector._event_queue_sync.put_nowait(event_data)
                    count += 1
            except queue.Full:
                logger.warning(f"Queue full for detector {detector.config_id}, event dropped")
            except Exception as e:
                logger.error(f"Error broadcasting to detector {detector.config_id}: {e}")
        
        return count
    
    async def disconnect(self):
        """Disconnect STOMP connection"""
        if self._stomp_conn:
            try:
                logger.info("Disconnecting broadcaster STOMP connection...")
                self._stomp_conn.disconnect()
                self._stomp_conn = None
                self._stomp_listener = None
                self._connected = False
                logger.info("Broadcaster disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting broadcaster: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if broadcaster is connected"""
        return self._connected
    
    @property
    def detector_count(self) -> int:
        """Get number of registered detectors"""
        return len(self._registered_detectors)
