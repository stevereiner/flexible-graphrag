"""
Wikipedia data source for Flexible GraphRAG using LlamaIndex WikipediaReader.
Enhanced with Neo4j LLM Graph Builder URL parsing approach.
"""

from typing import List, Dict, Any, Optional, Iterator
import logging
import re
from urllib.parse import unquote
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


class WikipediaSource(BaseDataSource):
    """Data source for Wikipedia articles using LlamaIndex WikipediaReader"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.raw_query = config.get("query", "")
        self.language = config.get("language", "en")
        self.max_docs = config.get("max_docs", 1)
        
        # Parse the query to extract proper Wikipedia title and language
        self.query, self.language = self._parse_wikipedia_input(self.raw_query, self.language)
        
        # Import LlamaIndex Wikipedia reader
        try:
            from llama_index.readers.wikipedia import WikipediaReader
            self.reader = WikipediaReader()
            logger.info(f"WikipediaSource initialized with LlamaIndex WikipediaReader for query: '{self.query}' (language: {self.language})")
        except ImportError as e:
            logger.error(f"Failed to import WikipediaReader: {e}")
            raise ImportError("Please install llama-index-readers-wikipedia: pip install llama-index-readers-wikipedia")
        
        # Wikipedia library will be lazy-loaded when needed for search functionality
        self._wikipedia = None
        self._wikipedia_import_attempted = False
    
    @property
    def wikipedia(self):
        """Lazy-load the wikipedia library when first accessed."""
        if not self._wikipedia_import_attempted:
            self._wikipedia_import_attempted = True
            try:
                import wikipedia
                self._wikipedia = wikipedia
                logger.info("Wikipedia search library lazy-loaded for enhanced title resolution")
            except ImportError as e:
                logger.warning(f"Wikipedia library not available for search functionality: {e}")
                logger.warning("Install with: pip install wikipedia")
                self._wikipedia = None
        return self._wikipedia
    
    def _parse_wikipedia_input(self, input_query: str, default_language: str = "en") -> tuple[str, str]:
        """
        Parse Wikipedia input to extract article title and language.
        Handles both URLs and direct queries, inspired by Neo4j LLM Graph Builder approach.
        
        Args:
            input_query: Wikipedia URL or article title
            default_language: Default language if not detected from URL
            
        Returns:
            tuple: (article_title, language)
        """
        if not input_query.strip():
            return "", default_language
        
        # Check if input is a Wikipedia URL (inspired by Neo4j approach)
        wikipedia_url_regex = r'https?:\/\/(www\.)?([a-zA-Z]{2,3})\.wikipedia\.org\/wiki\/(.*)'
        match = re.search(wikipedia_url_regex, input_query.strip())
        
        if match:
            # Extract language and article title from URL
            detected_language = match.group(2)
            article_title = match.group(3)
            
            # URL decode the title
            article_title = unquote(article_title)
            
            
            logger.info(f"Parsed Wikipedia URL: language='{detected_language}', title='{article_title}'")
            return article_title, detected_language
        else:
            # Input is likely a direct query/title
            logger.info(f"Using direct Wikipedia query: '{input_query.strip()}'")
            return input_query.strip(), default_language
    
    def validate_config(self) -> bool:
        """Validate the Wikipedia source configuration."""
        if not self.query:
            logger.error("No query specified for Wikipedia source")
            return False
        
        if self.max_docs <= 0:
            logger.error(f"Invalid max_docs value: {self.max_docs}")
            return False
        
        return True
    
    def get_documents(self) -> List[Document]:
        """
        Retrieve documents from Wikipedia with improved error handling and fallback strategies.
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Searching Wikipedia for: '{self.query}' (language: {self.language})")
            
            # Strategy 1: Try exact query as-is
            documents = self._try_load_wikipedia_page(self.query)
            if documents:
                return self._add_metadata_and_limit(documents, "exact_match")
            
            
            # Strategy 5: Try Wikipedia search as final fallback
            logger.info(f"Trying Wikipedia search as final fallback for: '{self.query}'")
            search_result = self._search_wikipedia_page(self.query)
            if search_result:
                logger.info(f"Wikipedia search found: '{search_result}' for query: '{self.query}'")
                documents = self._try_load_wikipedia_page(search_result)
                if documents:
                    return self._add_metadata_and_limit(documents, "search_based")
            
            # All strategies failed
            logger.error(f"All Wikipedia title strategies failed for '{self.query}'. Tried:")
            logger.error(f"  1. Exact match: '{self.query}'")
            logger.error(f"  2. Wikipedia search for: '{self.query}'")
            
            raise Exception(f"Wikipedia page not found for: '{self.query}' (tried multiple title formats)")
            
        except Exception as e:
            logger.error(f"Error loading Wikipedia article for query '{self.query}': {str(e)}")
            raise
    
    def _try_load_wikipedia_page(self, page_title: str) -> Optional[List[Document]]:
        """
        Try to load a Wikipedia page with the given title.
        
        Args:
            page_title: The page title to try
            
        Returns:
            List of documents if successful, None if failed
        """
        try:
            logger.info(f"Attempting to load Wikipedia page: '{page_title}' (language: {self.language})")
            logger.info(f"Page title length: {len(page_title)}, repr: {repr(page_title)}")
            
            # Ensure wikipedia library language is set consistently
            if self.wikipedia:
                self.wikipedia.set_lang(self.language)
            
            # Primary: Use LlamaIndex WikipediaReader (was working well before)
            logger.info(f"Using LlamaIndex WikipediaReader for: '{page_title}'")
            try:
                documents = self.reader.load_data(
                    pages=[page_title],
                    lang_prefix=self.language
                )
                if documents:
                    # Log document lengths and apply content limit like Neo4j LLM Graph Builder
                    for i, doc in enumerate(documents):
                        original_length = len(doc.text)
                        logger.info(f"LlamaIndex document {i+1}: {original_length} characters")
                        if original_length > 100000:
                            doc.text = doc.text[:100000]
                            if not doc.metadata:
                                doc.metadata = {}
                            doc.metadata["content_truncated"] = True
                            doc.metadata["original_length"] = original_length
                            logger.info(f"Truncated LlamaIndex document {i+1} from {original_length} to 100000 characters")
                    logger.info(f"Successfully loaded Wikipedia page: '{page_title}' - {len(documents)} documents")
                    return documents
            except Exception as reader_error:
                logger.info(f"LlamaIndex WikipediaReader failed: {reader_error}")
                logger.info(f"Error type: {type(reader_error).__name__}")
                # Continue to fallback methods
            
            # Fallback: Try direct wikipedia library approach (for cases like Nasdaq-100)
            if self.wikipedia:
                logger.info(f"Falling back to direct wikipedia library approach for: '{page_title}'")
                try:
                    self.wikipedia.set_lang(self.language)
                    
                    # Method 1: Try with auto_suggest=False first (UI provides exact URL/title)
                    try:
                        logger.info(f"Method 1: Trying with auto_suggest=False: '{page_title}'")
                        page = self.wikipedia.page(page_title, auto_suggest=False)
                        # Limit content length like Neo4j LLM Graph Builder (100,000 chars)
                        content = page.content[:100000] if len(page.content) > 100000 else page.content
                        if len(page.content) > 100000:
                            logger.info(f"Truncated Wikipedia content from {len(page.content)} to 100000 characters")
                        doc = Document(
                            text=content,
                            metadata={
                                "title": page.title,
                                "url": page.url,
                                "source": "wikipedia",
                                "language": self.language,
                                "page_id": getattr(page, 'pageid', None),
                                "summary": page.summary if hasattr(page, 'summary') else None,
                                "content_truncated": len(page.content) > 100000,
                                "original_length": len(page.content)
                            }
                        )
                        logger.info(f"Successfully loaded via direct wikipedia (no auto-suggest): '{page.title}' - 1 document")
                        return [doc]
                    except Exception as e1:
                        logger.info(f"Method 1 failed: {e1}")
                    
                    # Method 2: Try exact page title (fallback)
                    try:
                        logger.info(f"Method 2: Trying exact page title: '{page_title}'")
                        page = self.wikipedia.page(page_title)
                        # Limit content length like Neo4j LLM Graph Builder (100,000 chars)
                        content = page.content[:100000] if len(page.content) > 100000 else page.content
                        doc = Document(
                            text=content,
                            metadata={
                                "title": page.title,
                                "url": page.url,
                                "source": "wikipedia",
                                "language": self.language,
                                "page_id": getattr(page, 'pageid', None),
                                "summary": page.summary if hasattr(page, 'summary') else None,
                                "content_truncated": len(page.content) > 100000,
                                "original_length": len(page.content)
                            }
                        )
                        logger.info(f"Successfully loaded via direct wikipedia: '{page.title}' - 1 document")
                        return [doc]
                    except Exception as e2:
                        logger.info(f"Method 2 failed: {e2}")
                    
                    # Method 3: Try with redirect=False
                    try:
                        logger.info(f"Method 3: Trying with redirect=False: '{page_title}'")
                        page = self.wikipedia.page(page_title, redirect=False)
                        # Limit content length like Neo4j LLM Graph Builder (100,000 chars)
                        content = page.content[:100000] if len(page.content) > 100000 else page.content
                        doc = Document(
                            text=content,
                            metadata={
                                "title": page.title,
                                "url": page.url,
                                "source": "wikipedia",
                                "language": self.language,
                                "page_id": getattr(page, 'pageid', None),
                                "summary": page.summary if hasattr(page, 'summary') else None,
                                "content_truncated": len(page.content) > 100000,
                                "original_length": len(page.content)
                            }
                        )
                        logger.info(f"Successfully loaded via direct wikipedia (no redirect): '{page.title}' - 1 document")
                        return [doc]
                    except Exception as e3:
                        logger.info(f"Method 3 failed: {e3}")
                        
                    raise Exception(f"All direct wikipedia methods failed for '{page_title}'")
                    
                except Exception as direct_error:
                    logger.info(f"Direct wikipedia approach failed: {direct_error}")
            
            logger.info(f"No documents returned for: '{page_title}' (page may not exist)")
            return None
                    
        except Exception as e:
            logger.info(f"Failed to load '{page_title}': {str(e)}")
            return None
    
    def lazy_load(self) -> Iterator[Document]:
        """
        Lazy load Wikipedia documents 
        Returns an iterator over documents for memory efficiency.
        
        Yields:
            Document: Individual Wikipedia document
        """
        try:
            documents = self.get_documents()
            if documents:
                for doc in documents:
                    yield doc
        except Exception as e:
            logger.error(f"Error in lazy_load for query '{self.query}': {str(e)}")
            return
    
    def _search_wikipedia_page(self, search_query: str) -> Optional[str]:
        """
        Search for a Wikipedia page title using the Wikipedia API (LangChain-style approach).
        
        Args:
            search_query: The search query
            
        Returns:
            The actual page title if found, None if not found
        """
        if not self.wikipedia:
            logger.info(f"❌ Wikipedia search not available (library not installed)")
            return None
            
        try:
            # Set language
            self.wikipedia.set_lang(self.language)
            
            # Search for pages (this is what LangChain does)
            logger.info(f"Searching Wikipedia for: '{search_query}' (language: {self.language})")
            search_results = self.wikipedia.search(search_query, results=3)
            
            if search_results:
                # Get the top result (LangChain approach)
                top_result = search_results[0]
                logger.info(f"Wikipedia search results: {search_results}")
                logger.info(f"Using top result: '{top_result}'")
                return top_result
            else:
                logger.info(f"No Wikipedia search results for: '{search_query}'")
                return None
                
        except Exception as e:
            logger.info(f"Wikipedia search failed for '{search_query}': {str(e)}")
            return None
    
    
    def _add_metadata_and_limit(self, documents: List[Document], strategy: str) -> List[Document]:
        """
        Add metadata to documents and apply max_docs limit.
        
        Args:
            documents: List of documents to process
            strategy: The strategy used to find the documents
            
        Returns:
            Processed and limited list of documents
        """
        # Add source metadata
        for doc in documents:
            doc.metadata.update({
                "source": "wikipedia",
                "query": self.raw_query,  # Original input query
                "resolved_title": self.query,  # Resolved title
                "language": self.language,
                "source_type": "wikipedia_article",
                "resolution_strategy": strategy
            })
        
        # Apply limit if specified
        limited_docs = documents[:self.max_docs] if self.max_docs else documents
        logger.info(f"Returning {len(limited_docs)} Wikipedia documents (strategy: {strategy})")
        return limited_docs
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Wikipedia with progress tracking.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            List[Document]: List of LlamaIndex Document objects
        """
        try:
            logger.info(f"Loading Wikipedia articles for query: {self.query} with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, f"Searching Wikipedia for '{self.query}'...")
            
            # Use the synchronous method
            documents = self.get_documents()
            
            # Add progress tracking for each document
            for i, doc in enumerate(documents, 1):
                if progress_callback:
                    # Extract article title from metadata if available
                    title = doc.metadata.get('title', f'Article {i}')
                    progress_callback(i, len(documents), f"Processing Wikipedia article", title)
            
            logger.info(f"WikipediaSource loaded {len(documents)} documents for query: {self.query}")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading Wikipedia article for query '{self.query}': {str(e)}")
            raise
