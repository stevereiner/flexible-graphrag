"""
Web page data source for Flexible GraphRAG using LlamaIndex SimpleWebPageReader.
"""

from typing import List, Dict, Any
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class WebSource(BaseDataSource):
    """Data source for web pages using LlamaIndex SimpleWebPageReader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("url", "")
        
        # Import LlamaIndex web reader
        try:
            from llama_index.readers.web import SimpleWebPageReader
            self.reader = SimpleWebPageReader()
            logger.info(f"WebSource initialized for URL: {self.url}")
        except ImportError as e:
            logger.error(f"Failed to import SimpleWebPageReader: {e}")
            raise ImportError("Please install llama-index-readers-web: pip install llama-index-readers-web")
    
    def validate_config(self) -> bool:
        """Validate the web source configuration."""
        if not self.url:
            logger.error("No URL specified for web source")
            return False
        
        if not self.url.startswith(('http://', 'https://')):
            logger.error(f"Invalid URL format: {self.url}")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from the web page.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading web page: {self.url}")
            
            # Use SimpleWebPageReader to load the web page
            documents = self.reader.load_data([self.url])
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "web",
                    "url": self.url,
                    "source_type": "web_page"
                })
            
            logger.info(f"WebSource loaded {len(documents)} documents from: {self.url}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading web page '{self.url}': {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from the web page with progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading web page: {self.url} with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, "Connecting to web page...", self.url)
            
            # Use SimpleWebPageReader to load the web page
            documents = self.reader.load_data([self.url])
            
            if progress_callback:
                progress_callback(1, 1, "Processing web page content", self.url)
            
            # Add source metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "web",
                    "url": self.url,
                    "source_type": "web_page"
                })
            
            logger.info(f"WebSource loaded {len(documents)} documents from: {self.url}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading web page '{self.url}': {str(e)}")
            raise
