"""
Base classes for change detection.

Defines the abstract interface that all detectors must implement.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, AsyncGenerator, List, Any, Callable


class ChangeType(Enum):
    """Type of change detected"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class FileMetadata:
    """Metadata about a file from a data source"""
    source_type: str
    path: str  # Logical path within the source
    ordinal: int  # Microsecond timestamp
    size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    modified_timestamp: Optional[datetime] = None  # Source modification timestamp (for quick change detection)
    extra: Optional[Dict] = None  # Source-specific metadata


@dataclass
class ChangeEvent:
    """Unified change event"""
    metadata: FileMetadata
    change_type: ChangeType
    timestamp: datetime
    is_modify_delete: bool = False  # True if this DELETE is part of a MODIFY operation
    modify_callback: Optional[Callable] = None  # Async callback to invoke after DELETE completes


class ChangeDetector(ABC):
    """Abstract base for change detectors"""
    
    def __init__(self, config: Dict):
        self.config = config
        self._running = False
    
    @staticmethod
    def parse_timestamp(timestamp_value):
        """
        Convert timestamp string to datetime object.
        
        Handles ISO format timestamps from various sources (Alfresco, S3, Google Drive, etc.)
        and converts them to datetime objects for database storage.
        
        Args:
            timestamp_value: String timestamp (ISO format), datetime object, or None
            
        Returns:
            datetime object or None
            
        Examples:
            >>> parse_timestamp('2026-02-11T04:09:20.340000+00:00')
            datetime.datetime(2026, 2, 11, 4, 9, 20, 340000, tzinfo=...)
            
            >>> parse_timestamp(datetime.now())
            datetime.datetime(...)
            
            >>> parse_timestamp(None)
            None
        """
        if not timestamp_value:
            return None
            
        if isinstance(timestamp_value, str):
            try:
                # Handle ISO format with 'Z' or timezone offset
                parsed = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                return parsed
            except Exception as e:
                # Log warning but don't fail - timestamp is optional
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Could not parse timestamp '{timestamp_value}': {e}")
                return None
        else:
            # Already a datetime object (or date)
            return timestamp_value
    
    @abstractmethod
    async def start(self):
        """Start detecting changes"""
        pass
    
    @abstractmethod
    async def stop(self):
        """Stop detecting changes"""
        pass
    
    @abstractmethod
    async def list_all_files(self) -> List[FileMetadata]:
        """List all files with metadata (for initial/periodic sync)"""
        pass
    
    @abstractmethod
    async def get_changes(self) -> AsyncGenerator[ChangeEvent, None]:
        """Stream change events (for event-driven updates)"""
        pass
