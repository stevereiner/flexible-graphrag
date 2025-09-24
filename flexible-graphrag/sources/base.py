"""
Base data source interface for Flexible GraphRAG.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging
from llama_index.core import Document

logger = logging.getLogger(__name__)


class BaseDataSource(ABC):
    """Abstract base class for all data sources."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the data source with configuration."""
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from the data source.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        pass
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from the data source with progress tracking.
        
        Args:
            progress_callback: Optional callback function for progress updates
                              Should accept (current, total, message, current_file)
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        # Default implementation just calls get_documents
        # Subclasses can override this for detailed progress tracking
        return self.get_documents()
    
    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate the configuration for this data source.
        
        Returns:
            bool: True if configuration is valid, False otherwise
        """
        pass
    
    def get_source_info(self) -> Dict[str, Any]:
        """
        Get information about this data source.
        
        Returns:
            Dict[str, Any]: Source information including type, config, etc.
        """
        return {
            "type": self.__class__.__name__,
            "config": self.config
        }
