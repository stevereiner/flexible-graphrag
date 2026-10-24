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
from .extractor_extensions import PASSTHROUGH_EXTENSIONS

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
    
    def _target_kwargs(self) -> Dict[str, Any]:
        """What AzStorageBlobReader reads: one blob, or the blobs under the prefix (its own
        "prefix" filters nothing: name_starts_with does). A single blob in a folder ("dir/a.txt") is
        saved under its own name, which fails (the folder is not created), so it is listed by name
        instead -- saved flattened -- and _only_selected_blob keeps just it."""
        if self.blob_name:
            return {"name_starts_with": self.blob_name} if "/" in self.blob_name else {"blob": self.blob_name}
        return {"name_starts_with": self.prefix} if self.prefix else {}

    def _only_selected_blob(self, docs: List[Document]) -> List[Document]:
        """The selected blob's documents, when it was listed by name (_target_kwargs)."""
        if not (self.blob_name and "/" in self.blob_name):
            return docs
        return [d for d in docs if (d.metadata or {}).get("name") in (self.blob_name, None)]

    def _create_azure_blob_reader(self, progress_callback=None):
        """Create AzStorageBlobReader with passthrough extractors"""
        try:
            from llama_index.readers.azstorage_blob import AzStorageBlobReader
        except ImportError:
            logger.error("Failed to import AzStorageBlobReader")
            raise ImportError("Please install llama-index-readers-azstorage-blob: pip install llama-index-readers-azstorage-blob")
        
        # Create passthrough extractor with progress tracking
        passthrough = PassthroughExtractor(progress_callback=progress_callback)
        
        # Map all supported file types to passthrough extractor (not hardcoded here)
        file_extractor = {ext: passthrough for ext in PASSTHROUGH_EXTENSIONS}
        
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
        reader_kwargs.update(self._target_kwargs())
        
        reader = AzStorageBlobReader(**reader_kwargs)
        
        return reader, passthrough

    def get_placeholder_docs(self, extractor=None) -> List[Document]:
        """
        Return reader-level placeholder documents captured by *extractor*.

        Azure Blob caveat
        -----------------
        ``AzStorageBlobReader`` downloads each blob to a **temporary directory**
        and deletes that directory after calling the extractor.  This means:

        * ``PassthroughExtractor`` (default, no bytes capture): returns a
          placeholder with the local temp path — which no longer exists by the
          time ``process_documents_from_metadata`` is called.  Use
          ``get_documents()`` / ``get_documents_with_progress()`` instead.

        * ``BytesCaptureExtractor`` (CocoIndex path): reads the bytes from the
          temp file *immediately* inside the extractor call, before the temp dir
          is deleted.  This is the correct extractor for CocoIndex ingestion.

        Parameters
        ----------
        extractor:
            Required for Azure Blob when you want raw bytes.  Pass
            ``BytesCaptureExtractor()``.  If None, uses PassthroughExtractor
            (path-only placeholder — only useful if a later step re-downloads).
        """
        from llama_index.readers.azstorage_blob import AzStorageBlobReader

        actual_extractor = extractor or PassthroughExtractor()
        file_extractor = {ext: actual_extractor for ext in PASSTHROUGH_EXTENSIONS}

        reader_kwargs: Dict[str, Any] = {
            "container_name": self.container_name,
            "file_extractor": file_extractor,
        }
        if self.connection_string:
            reader_kwargs["connection_string"] = self.connection_string
        elif self.account_url and self.account_key:
            reader_kwargs["account_url"] = self.account_url
            reader_kwargs["credential"] = self.account_key
        reader_kwargs.update(self._target_kwargs())

        reader = AzStorageBlobReader(**reader_kwargs)
        return self._only_selected_blob(reader.load_data())

    def read_file_bytes(self, blob_name: str) -> bytes:
        """
        Read the raw bytes of a single Azure blob, reusing the source's cached
        credentials/config and the LlamaIndex ``AzStorageBlobReader`` restricted
        to one blob.

        NO new SDK code — uses the same reader machinery as the full listing with
        a ``BytesCaptureExtractor``.  Azure blobs are downloaded to a temp dir that
        the reader deletes after ``load_data``; ``BytesCaptureExtractor`` reads the
        bytes WITHIN that scope (inside the extractor call) so nothing is lost.

        Parameters
        ----------
        blob_name:
            The blob name within the container (may include a folder path).

        Returns
        -------
        Raw file bytes (``b""`` if the blob could not be read).
        """
        from llama_index.readers.azstorage_blob import AzStorageBlobReader
        from .bytes_capture_extractor import BytesCaptureExtractor

        extractor = BytesCaptureExtractor()
        file_extractor = {ext: extractor for ext in PASSTHROUGH_EXTENSIONS}

        reader_kwargs: Dict[str, Any] = {
            "container_name": self.container_name,
            # single blob — restricts reader to one key (one in a folder is listed by name: _target_kwargs)
            **({"name_starts_with": blob_name} if "/" in blob_name else {"blob": blob_name}),
            "file_extractor": file_extractor,
        }
        if self.connection_string:
            reader_kwargs["connection_string"] = self.connection_string
        elif self.account_url and self.account_key:
            reader_kwargs["account_url"] = self.account_url
            reader_kwargs["credential"] = self.account_key

        reader = AzStorageBlobReader(**reader_kwargs)
        docs = [d for d in reader.load_data() if (d.metadata or {}).get("name") in (blob_name, None)]
        for d in docs:
            rb = d.metadata.get("raw_bytes")
            if rb is not None:
                return rb
        logger.warning("AzureBlobSource.read_file_bytes: no bytes captured for blob %s", blob_name)
        return b""

    def get_documents(self) -> List[Document]:
        """Load files via AzStorageBlobReader (with passthrough), then process with DocumentProcessor"""
        try:
            logger.info(f"Loading documents from Azure Blob Storage container: {self.container_name}")
            
            # Create reader
            reader, _ = self._create_azure_blob_reader()
            
            # Use AzStorageBlobReader to discover and capture files (returns placeholder Documents)
            placeholder_docs = self._only_selected_blob(reader.load_data())
            
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
            from process.document_processor import DocumentProcessor, get_parser_type_from_env
            
            logger.info(f"Loading documents from Azure Blob Storage container '{self.container_name}' with progress tracking")
            
            if progress_callback:
                progress_callback(0, 1, f"Connecting to Azure Blob Storage container: {self.container_name}")
            
            # Create PassthroughExtractor WITH doc_processor so files are processed immediately
            # while the AzStorageBlobReader temp files still exist on disk.
            # AzStorageBlobReader downloads blobs to temp dir, calls the extractor, then deletes
            # the temp dir - so we MUST process each file while it is still present.
            parser_type = get_parser_type_from_env()
            doc_processor = DocumentProcessor(parser_type=parser_type)
            extractor = PassthroughExtractor(
                progress_callback=progress_callback,
                doc_processor=doc_processor
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
            reader_kwargs.update(self._target_kwargs())
            
            reader = AzStorageBlobReader(**reader_kwargs)
            
            # Use AzStorageBlobReader to load and process documents
            # PassthroughExtractor will process each file immediately and return processed docs
            placeholder_docs = self._only_selected_blob(reader.load_data())
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
            
            # placeholder_docs are now already fully processed (PassthroughExtractor with doc_processor
            # processes each file immediately while the temp file still exists)
            documents = placeholder_docs
            
            # Replace metadata with a clean, useful subset and CORRECT file_path.
            # AzStorageBlobReader dumps the ENTIRE blob-properties dict (~40 fields, several nested
            # dicts: content_settings / copy / lease / immutability_policy / metadata) onto each doc.
            # Left as-is that (a) bloats chunk metadata so LlamaIndex splits the text into far too
            # many tiny chunks (e.g. a 2-chunk file became 12), (b) pollutes graph node/entity
            # properties, and (c) trips Neo4j on the dict values. Keep only what downstream reads.
            for doc in documents:
                _md = doc.metadata or {}
                file_name = _md.get('file_name', '')
                # The blob's full name in the container ('name', from the blob properties) names it. By now
                # file_path can be the local temporary download path, which must not leak into the
                # document's path ("container/C:\Users\...\Temp\tmpXXXX\cmispress.txt").
                blob_path = _md.get('file_path', '')
                local_path = bool(blob_path) and (os.path.isabs(blob_path) or ":\\" in blob_path)
                if _md.get('name'):
                    correct_azure_path = f"{self.container_name}/{_md['name']}"
                elif blob_path and not local_path and not blob_path.startswith(self.container_name + '/'):
                    correct_azure_path = f"{self.container_name}/{blob_path}"
                else:
                    correct_azure_path = azure_path_mapping.get(file_name, None)

                _cs = _md.get('content_settings')
                content_type = _cs.get('content_type') if isinstance(_cs, dict) else _md.get('content_type')

                # 'name' (raw blob name) + container_name are read by doc_id / document_state creation
                clean = {
                    "source": "azure_blob",
                    "source_type": "azure_blob_object",
                    "container_name": self.container_name,
                    "account_name": self.account_name,
                    "name": _md.get('name') or file_name,
                    "file_name": file_name,
                    "file_path": correct_azure_path or blob_path,
                    "file_type": _md.get('file_type'),
                    "file_size": _md.get('file_size') or _md.get('size'),
                    "last_modified": _md.get('last_modified'),
                    "content_type": content_type,
                    "conversion_method": _md.get('conversion_method'),
                }
                if _md.get('doc_id'):
                    clean['doc_id'] = _md['doc_id']
                doc.metadata = {k: v for k, v in clean.items() if v is not None}

                if correct_azure_path:
                    logger.debug(f"Corrected file_path for '{file_name}' to '{correct_azure_path}'")
                else:
                    logger.warning(f"Could not find Azure path mapping for file_name: {file_name}")
            
            logger.info(f"AzureBlobSource processed {len(documents)} documents from Azure Blob Storage")
            return (len(documents), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error loading documents from Azure Blob Storage container '{self.container_name}': {str(e)}")
            raise
