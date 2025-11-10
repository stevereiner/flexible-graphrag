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
    
    def _get_document_processor(self):
        """
        Get a DocumentProcessor instance configured with the correct parser type.
        This centralizes parser type configuration for all data sources.
        
        Returns:
            DocumentProcessor: Initialized document processor
        """
        from document_processor import DocumentProcessor, get_parser_type_from_env
        from config import Settings
        
        parser_type = get_parser_type_from_env()
        
        # Pass Settings instance to DocumentProcessor for LlamaParse API key access
        config = Settings()
        return DocumentProcessor(config=config, parser_type=parser_type)
    
    @abstractmethod
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from the data source.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        pass
    
    async def get_documents_with_progress(self, progress_callback=None):
        """
        Retrieve documents from the data source with progress tracking.
        
        Args:
            progress_callback: Optional callback function for progress updates
                              Should accept (current, total, message, current_file)
        
        Returns:
            tuple: (file_count, documents) where:
                   - file_count: Number of original files/sources processed
                   - documents: List[Document] - LlamaIndex Document objects (may be chunks)
                   
        Note: file_count represents original files, while len(documents) may be higher
              due to chunking during processing (especially with LlamaParse).
        """
        # Default implementation just calls get_documents and returns (1, documents)
        # Subclasses should override to track actual file counts
        documents = self.get_documents()
        return (len(documents), documents)  # Assume 1 doc = 1 file for simple sources
    
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
