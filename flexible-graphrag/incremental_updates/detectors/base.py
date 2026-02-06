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
    modified_timestamp: Optional[str] = None  # Source modification timestamp (for quick change detection)
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
