"""
Filesystem data source for Flexible GraphRAG.
"""

from pathlib import Path
from typing import List, Dict, Any
import logging
from llama_index.core import Document

from .base import BaseDataSource

logger = logging.getLogger(__name__)


def is_docling_supported(content_type: str, filename: str) -> bool:
    """Check if document type is supported by Docling"""
    content_type_lower = content_type.lower()
    filename_lower = filename.lower()
    
    # Supported MIME types (based on Docling supported formats)
    supported_types = [
        # PDF
        'application/pdf',
        # Microsoft Office modern formats (OpenXML)
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # DOCX
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # XLSX
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # PPTX
        # Text and markup formats
        'text/plain',  # TXT
        'text/markdown',  # MD
        'text/html',  # HTML
        'application/xhtml+xml',  # XHTML
        'text/csv',  # CSV
        'text/x-asciidoc',  # AsciiDoc
        # Image formats
        'image/png',  # PNG
        'image/jpeg',  # JPEG
        'image/tiff',  # TIFF
        'image/bmp',  # BMP
        'image/webp',  # WEBP
        # Schema-specific formats
        'application/xml',  # XML (USPTO, JATS)
        'application/json',  # JSON (Docling JSON)
    ]
    
    # Supported file extensions (based on Docling supported formats)
    supported_extensions = [
        # PDF
        '.pdf',
        # Microsoft Office modern formats (OpenXML)
        '.docx', '.xlsx', '.pptx',
        # Text and markup formats
        '.txt', '.md', '.markdown', '.html', '.htm', '.xhtml', '.csv',
        '.asciidoc', '.adoc',
        # Image formats
        '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.webp',
        # Schema-specific formats
        '.xml', '.json',
    ]
    
    # Check by exact MIME type match
    if content_type in supported_types:
        return True
        
    # Check by file extension
    if any(filename_lower.endswith(ext) for ext in supported_extensions):
        return True
        
    # Additional pattern matching for content types
    content_patterns = [
        'pdf', 'word', 'excel', 'powerpoint', 'officedocument',
        'text', 'markdown', 'html', 'csv', 'image', 'xml', 'json'
    ]
    
    return any(pattern in content_type_lower for pattern in content_patterns)


class FileSystemSource(BaseDataSource):
    """Data source for local filesystem files and directories"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.paths = config.get("paths", [])
        logger.info(f"FileSystemSource initialized with {len(self.paths)} paths")
    
    def validate_config(self) -> bool:
        """Validate the filesystem configuration."""
        if not self.paths:
            logger.error("No paths specified for filesystem source")
            return False
        
        for path_str in self.paths:
            path = Path(path_str)
            if not path.exists():
                logger.error(f"Path does not exist: {path.absolute()}")
                return False
        
        return True
    
    def list_files(self) -> List[Path]:
        """List all files from the specified paths (files or directories)"""
        files = []
        
        for path_str in self.paths:
            logger.info(f"Processing path: {path_str}")
            path = Path(path_str)
            logger.info(f"Resolved path: {path.absolute()}")
            
            if not path.exists():
                logger.warning(f"Path does not exist: {path.absolute()}")
                continue
            
            if path.is_file():
                # Single file
                logger.info(f"Found single file: {path.absolute()}")
                # Check if file type is supported by Docling
                if is_docling_supported('', path.name):
                    files.append(path)
                    logger.info(f"Added supported file: {path}")
                else:
                    logger.warning(f"Unsupported file type: {path.suffix} for file: {path}")
            elif path.is_dir():
                # Directory - recursively find all files
                logger.info(f"Scanning directory: {path.absolute()}")
                for file_path in path.rglob("*"):
                    if file_path.is_file():
                        # Filter for supported file types using Docling support
                        if is_docling_supported('', file_path.name):
                            files.append(file_path)
                            logger.info(f"Added file from directory: {file_path}")
            else:
                logger.warning(f"Path is neither file nor directory: {path.absolute()}")
        
        logger.info(f"FileSystemSource found {len(files)} files")
        return files
    
    def get_documents(self) -> List[Document]:
        """
        Get documents from filesystem paths.
        Note: This returns file path documents for processing by DocumentProcessor.
        """
        # For filesystem sources, we return the file paths for processing by DocumentProcessor
        # This maintains compatibility with existing workflow
        files = self.list_files()
        return [Document(text="", metadata={"file_path": str(f), "source": "filesystem"}) for f in files]
    
    async def get_documents_with_progress(self, progress_callback=None) -> List[Document]:
        """
        Get documents from filesystem paths with progress tracking.
        """
        import asyncio
        
        try:
            if progress_callback:
                progress_callback(
                    current=0,
                    total=1,
                    message="Scanning filesystem paths...",
                    current_file=""
                )
            
            # Get list of files
            files = self.list_files()
            
            if not files:
                return []
            
            # Process files using DocumentProcessor with configured parser type
            doc_processor = self._get_document_processor()
            file_paths = [str(f) for f in files]
            
            # Process documents with progress updates
            documents = []
            for i, file_path in enumerate(file_paths):
                try:
                    if progress_callback:
                        progress_callback(
                            current=i + 1,
                            total=len(files),
                            message=f"Processing file: {Path(file_path).name}",
                            current_file=Path(file_path).name
                        )
                    
                    # Process single file
                    processed_docs = await doc_processor.process_documents([file_path])
                    if processed_docs:
                        # Get file modification time
                        import os
                        from datetime import datetime, timezone
                        try:
                            mtime = os.path.getmtime(file_path)
                            modified_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                        except:
                            modified_at = None
                        
                        for doc in processed_docs:
                            # Update metadata to include filesystem source
                            doc.metadata.update({
                                "source": "filesystem",
                                "file_path": file_path,
                                "file_name": Path(file_path).name
                            })
                            # Add modification timestamp if available
                            if modified_at:
                                doc.metadata['modified at'] = modified_at
                        documents.extend(processed_docs)
                    
                except Exception as e:
                    logger.error(f"Error processing filesystem file {file_path}: {str(e)}")
                    continue
            
            logger.info(f"FileSystemSource processed {len(file_paths)} files ({len(documents)} chunks)")
            return (len(file_paths), documents)  # Return tuple: (file_count, documents)
            
        except Exception as e:
            logger.error(f"Error getting filesystem documents with progress: {str(e)}")
            raise
