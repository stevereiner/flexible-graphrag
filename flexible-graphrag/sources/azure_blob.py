"""
Azure Blob Storage data source for Flexible GraphRAG.
Uses AzStorageBlobReader with passthrough extractor to download files, then DocumentProcessor for parsing.
"""

from typing import List, Dict, Any, Optional
import logging
import os
from llama_index.core import Document

from .base import BaseDataSource
from .passthrough_extractor import PassthroughExtractor

logger = logging.getLogger(__name__)


class AzureBlobSource(BaseDataSource):
    """Data source for Azure Blob Storage - uses AzStorageBlobReader with passthrough + DocumentProcessor"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Get configuration
        self.container_name = config.get("container_name", "")
        self.account_url = config.get("account_url", "")
        self.blob_name = config.get("blob", "") or config.get("blob_name", "")  # Specific blob or prefix
        self.prefix = config.get("prefix", "")  # Optional: folder prefix
        self.account_name = config.get("account_name", "")
        self.account_key = config.get("account_key", "")
        self.connection_string = config.get("connection_string", "")
        
        logger.info(f"AzureBlobSource initialized for container: {self.container_name}")
    
    def validate_config(self) -> bool:
        """Validate the Azure Blob Storage source configuration."""
        if not self.container_name:
            logger.error("No container_name specified for Azure Blob Storage source")
            return False
        
        # Need either connection_string OR (account_url/account_name + account_key)
        has_connection_string = bool(self.connection_string)
        has_account_key_auth = bool(self.account_url and self.account_name and self.account_key)
        
        if not has_connection_string and not has_account_key_auth:
            logger.error("Azure Blob Storage requires either connection_string or (account_url + account_name + account_key)")
            return False
        
        return True
    
    def _create_azure_blob_reader(self, progress_callback=None):
        """Create AzStorageBlobReader with passthrough extractors"""
        try:
            from llama_index.readers.azstorage_blob import AzStorageBlobReader
        except ImportError:
            logger.error("Failed to import AzStorageBlobReader")
            raise ImportError("Please install llama-index-readers-azstorage-blob: pip install llama-index-readers-azstorage-blob")
        
        # Create passthrough extractor with progress tracking
        passthrough = PassthroughExtractor(progress_callback=progress_callback)
        
        # Map all supported file types to passthrough extractor
        file_extractor = {
            ".pdf": passthrough,
            ".docx": passthrough,
            ".pptx": passthrough,
            ".xlsx": passthrough,
            ".doc": passthrough,
            ".ppt": passthrough,
            ".xls": passthrough,
            ".txt": passthrough,
            ".md": passthrough,
            ".html": passthrough,
            ".csv": passthrough,
            ".png": passthrough,
            ".jpg": passthrough,
            ".jpeg": passthrough,
        }
        
        # Initialize AzStorageBlobReader with credentials and passthrough extractors
        reader_kwargs = {
            "container_name": self.container_name,
            "file_extractor": file_extractor,
        }
        
        # Add authentication
        if self.connection_string:
            reader_kwargs["connection_string"] = self.connection_string
        elif self.account_url and self.account_key:
            reader_kwargs["account_url"] = self.account_url
            reader_kwargs["credential"] = self.account_key
        
        # Add blob name or prefix if specified
        if self.blob_name:
            reader_kwargs["blob"] = self.blob_name
        elif self.prefix:
            reader_kwargs["prefix"] = self.prefix
        
        reader = AzStorageBlobReader(**reader_kwargs)
        
        return reader, passthrough
    
    def get_documents(self) -> List[Document]:
        """Load files via AzStorageBlobReader (with passthrough), then process with DocumentProcessor"""
        try:
            logger.info(f"Loading documents from Azure Blob Storage container: {self.container_name}")
            
            # Create reader
            reader, _ = self._create_azure_blob_reader()
            
            # Use AzStorageBlobReader to discover and capture files (returns placeholder Documents)
            placeholder_docs = reader.load_data()
            
            if not placeholder_docs:
                logger.warning("No files found in Azure Blob Storage container")
                return []
            
            logger.info(f"Found {len(placeholder_docs)} files in Azure Blob Storage")
            
            # Process with DocumentProcessor (downloads from Azure and parses)
            doc_processor = self._get_document_processor()
            
            import asyncio
            documents = asyncio.run(doc_processor.process_documents_from_metadata(placeholder_docs))
            
            # Add Azure Blob Storage metadata
            for doc in documents:
                doc.metadata.update({
                    "source": "azure_blob",
                    "container_name": self.container_name,
                    "account_name": self.account_name,
                    "source_type": "azure_blob_object"
                })
            
            logger.info(f"AzureBlobSource processed {len(documents)} documents from {len(placeholder_docs)} placeholders")
            return documents
            
        except Exception as e:
            logger.error(f"Error loading documents from Azure Blob Storage container '{self.container_name}': {str(e)}")
            raise
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Retrieve documents from Azure Blob Storage with detailed progress tracking.
        PassthroughExtractor processes files immediately as AzStorageBlobReader downloads them.
        
        Args:
            progress_callback: Callback function for progress updates
        
        Returns:
            Tuple[int, List[Document]]: (file_count, list of processed Document objects)
        """
        try:
            from llama_index.readers.azstorage_blob import AzStorageBlobReader
            from document_processor import DocumentProcessor, get_parser_type_from_env
            
            logger.info(f"Loading documents from Azure Blob Storage container '{self.container_name}' with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, f"Connecting to Azure Blob Storage container: {self.container_name}")
            
            # Create PassthroughExtractor WITHOUT doc_processor (return placeholders)
            # We'll process all files together after correcting paths
            extractor = PassthroughExtractor(
                progress_callback=progress_callback
            )
            
            # Define file extractor mapping once
            file_extractor = {
                ".pdf": extractor, ".docx": extractor, ".pptx": extractor,
                ".xlsx": extractor, ".doc": extractor, ".ppt": extractor,
                ".xls": extractor, ".txt": extractor, ".md": extractor,
                ".html": extractor, ".csv": extractor, ".png": extractor,
                ".jpg": extractor, ".jpeg": extractor
            }
            
            # Initialize AzStorageBlobReader with credentials and PassthroughExtractor
            reader_kwargs = {
                "container_name": self.container_name,
                "file_extractor": file_extractor,
            }
            
            # Add authentication
            if self.connection_string:
                logger.info("Using Azure Blob Storage connection string authentication")
                reader_kwargs["connection_string"] = self.connection_string
            elif self.account_url and self.account_key:
                logger.info(f"Using Azure Blob Storage account key authentication for account: {self.account_name}")
                reader_kwargs["account_url"] = self.account_url
                reader_kwargs["credential"] = self.account_key
            
            # Add blob name or prefix if specified
            if self.blob_name:
                reader_kwargs["blob"] = self.blob_name
            elif self.prefix:
                reader_kwargs["prefix"] = self.prefix
            
            reader = AzStorageBlobReader(**reader_kwargs)
            
            # Use AzStorageBlobReader to load and process documents
            # PassthroughExtractor will process each file immediately and return processed docs
            placeholder_docs = reader.load_data()
            logger.info(f"Loaded {len(placeholder_docs)} Azure Blob files from container: {self.container_name}")
            
            # CRITICAL: AzStorageBlobReader returns file_path with blob_name
            # But DocumentProcessor will change it to temp path, so we need to map back
            # Extract actual Azure paths and file names BEFORE processing
            azure_path_mapping = {}  # Map file_name -> correct_azure_path
            for placeholder_doc in placeholder_docs:
                # AzStorageBlobReader stores blob name in metadata['file_path']
                # Example: 'cmispress.txt' or 'folder/cmispress.txt' (relative to container)
                blob_name = placeholder_doc.metadata.get('file_path', '')
                file_name = placeholder_doc.metadata.get('file_name', '')
                
                if blob_name and file_name:
                    # Construct full Azure path (container/blob_name format)
                    azure_full_path = f"{self.container_name}/{blob_name}"
                    # Map by filename so we can find it after DocumentProcessor changes file_path
                    azure_path_mapping[file_name] = azure_full_path
                    logger.debug(f"Azure path mapping: {file_name} -> {azure_full_path}")
            
            logger.info(f"Extracted {len(azure_path_mapping)} Azure path mappings")
            
            # Now process the documents with DocumentProcessor
            parser_type = get_parser_type_from_env()
            doc_processor = DocumentProcessor(parser_type=parser_type)
            
            documents = await doc_processor.process_documents_from_metadata(placeholder_docs)
            
            # Add Azure Blob Storage metadata to processed documents and CORRECT file_path
            for doc in documents:
                # Look up the correct Azure path using file_name
                file_name = doc.metadata.get('file_name', '')
                correct_azure_path = azure_path_mapping.get(file_name, None)
                
                # Update metadata with correct Azure path and metadata
                update_dict = {
                    "source": "azure_blob",
                    "container_name": self.container_name,
                    "account_name": self.account_name,
                    "source_type": "azure_blob_object"
                }
                
                # CRITICAL: Override file_path with correct Azure path (container/blob_name format)
                if correct_azure_path:
                    update_dict["file_path"] = correct_azure_path
                    logger.debug(f"Corrected file_path for '{file_name}' to '{correct_azure_path}'")
                else:
                    logger.warning(f"Could not find Azure path mapping for file_name: {file_name}")
                
                doc.metadata.update(update_dict)
            
            logger.info(f"AzureBlobSource processed {len(documents)} documents from Azure Blob Storage")
            return (len(documents), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error loading documents from Azure Blob Storage container '{self.container_name}': {str(e)}")
            raise
