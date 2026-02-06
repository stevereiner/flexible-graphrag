"""
Passthrough extractor for LlamaIndex readers.
Captures file paths and fs objects without parsing, allowing DocumentProcessor to handle download and parsing.
"""

from typing import List, Dict, Any, Optional, Callable
import logging
import os
from pathlib import Path
from llama_index.core import Document
from llama_index.core.readers.base import BaseReader
from llama_index.core.readers.file.base import is_default_fs

logger = logging.getLogger(__name__)


class PassthroughExtractor(BaseReader):
    """
    Custom extractor that captures file paths and fs objects without parsing.
    Passes file information to DocumentProcessor which handles download and parsing.
    
    For remote filesystems (S3, GCS, Azure), passes the fs object to DocumentProcessor.
    For local filesystems, just passes through the file path.
    """
    
    def __init__(self, progress_callback: Optional[Callable] = None, doc_processor=None):
        """
        Initialize passthrough extractor.
        
        Args:
            progress_callback: Optional callback for progress updates during file discovery
                              Signature: callback(current, total, message, current_file)
            doc_processor: Optional DocumentProcessor for immediate file processing (for Box)
                          If provided, files are processed immediately instead of returning placeholders
        """
        self.progress_callback = progress_callback
        self.doc_processor = doc_processor  # For Box immediate processing
        self.files_processed = 0
        self.total_files = 0
    
    def set_total_files(self, total: int):
        """Set the total number of files for progress tracking"""
        self.total_files = total
        self.files_processed = 0
    
    def load_data(self, file_path: Path, extra_info: Dict = None, **kwargs) -> List[Document]:
        """
        Download file if from remote filesystem, or pass through local path.
        Reports progress if callback is provided.
        
        This matches the standard LlamaIndex file extractor signature:
        - file_path: Path to the file (can be local path or remote fs path like "bucket/file.pdf")
        - extra_info: Metadata dict from SimpleDirectoryReader  
        - fs: Optional AbstractFileSystem (passed in kwargs for remote filesystems like S3)
        
        Args:
            file_path: Path to the file
            extra_info: Additional metadata from the reader
            **kwargs: Additional arguments including:
                - fs: AbstractFileSystem for remote filesystems (S3, GCS, Azure, etc.)
                - errors: Error handling mode
        
        Returns:
            List with single Document containing local file path metadata
        """
        # Extract fs from kwargs if provided (for remote filesystems)
        fs = kwargs.get('fs', None)
        
        # Log what kwargs we're receiving for debugging
        if kwargs:
            logger.info(f"PassthroughExtractor received kwargs: {list(kwargs.keys())}")
        if extra_info:
            logger.info(f"PassthroughExtractor received extra_info: {extra_info}")
        
        # Check if fs is default or remote
        if fs:
            is_default = is_default_fs(fs)
            logger.info(f"PassthroughExtractor: fs={type(fs).__name__}, is_default_fs={is_default}, file_path={file_path}")
        else:
            logger.info(f"PassthroughExtractor: fs=None, file_path={file_path}")
        
        self.files_processed += 1
        
        # Get file name for progress reporting
        # Try to extract original filename from extra_info (for Google Drive, Box, etc.)
        original_file_name = None
        if extra_info:
            # Google Drive provides 'file path' in extra_info (e.g., 'sample-docs/cmispress.txt')
            # Extract just the filename from the path
            file_path_from_metadata = extra_info.get('file path') or extra_info.get('file_name') or extra_info.get('filename')
            if file_path_from_metadata:
                # Extract just the filename from path like 'sample-docs/cmispress.txt' -> 'cmispress.txt'
                original_file_name = file_path_from_metadata.split('/')[-1]
        
        file_name = str(file_path)
        if hasattr(file_path, 'name'):
            file_name = file_path.name
        elif '/' in str(file_path):
            file_name = str(file_path).split('/')[-1]
        
        # Use original filename if available (for better LlamaCloud display)
        if original_file_name:
            logger.info(f"Found original filename in metadata: {original_file_name} (temp name: {file_name})")
            file_name = original_file_name
        
        # Report download progress if callback provided
        if self.progress_callback and self.total_files > 0:
            self.progress_callback(
                current=self.files_processed,
                total=self.total_files,
                message=f"Downloaded {self.files_processed}/{self.total_files} files",
                current_file=file_name
            )
        
        # Get file size if possible
        file_size = 0
        try:
            if fs:
                info = fs.info(str(file_path))
                file_size = info.get('size', 0)
            elif hasattr(file_path, 'stat'):
                file_size = file_path.stat().st_size
            elif os.path.exists(str(file_path)):
                file_size = os.path.getsize(str(file_path))
        except Exception as e:
            logger.debug(f"Could not get file size for {file_path}: {e}")
        
        logger.info(f"Passthrough extractor returning path: {file_path}, has_fs: {fs is not None}")
        
        # If doc_processor is provided (Box/GoogleDrive case), process file immediately while it exists
        if self.doc_processor and not fs:  # Only for local files (Box/GoogleDrive download locally)
            logger.info(f"Processing file immediately with DocumentProcessor: {file_path}")
            
            # Rename temp file to original filename for better LlamaCloud display
            # Then rename it back after processing so reader's cleanup works
            actual_file_path = file_path
            renamed_path = None
            
            if original_file_name and str(file_path) != original_file_name:
                # The temp file has ugly name like "1gJHJKS7VvWaBCKhTbMkgQudsZgeV9OoZ.txt"
                # Rename it to original name like "space-station.txt"
                try:
                    import shutil
                    temp_dir = Path(file_path).parent
                    new_path = temp_dir / original_file_name
                    
                    # If file already exists, append number to avoid collision
                    if new_path.exists():
                        base_name = Path(original_file_name).stem
                        extension = Path(original_file_name).suffix
                        counter = 1
                        while new_path.exists():
                            new_path = temp_dir / f"{base_name}_{counter}{extension}"
                            counter += 1
                    
                    # Rename to good filename for LlamaParse
                    shutil.move(str(file_path), str(new_path))
                    actual_file_path = new_path
                    renamed_path = new_path  # Save for renaming back
                    logger.info(f"Renamed temp file from {Path(file_path).name} to {new_path.name} for processing")
                except Exception as e:
                    logger.warning(f"Could not rename temp file {file_path} to {original_file_name}: {e}")
                    # Continue with original path if rename fails
            
            try:
                # Prepare metadata to pass to DocumentProcessor (preserve cloud source metadata like file id)
                # Filter out internal fields that shouldn't be passed
                metadata_to_pass = {k: v for k, v in (extra_info or {}).items() if not k.startswith('_')}
                
                # For Box, construct stable file_path from path_collection + name instead of temp path
                if extra_info and extra_info.get('path_collection') and extra_info.get('name'):
                    # Box: Use stable path
                    path_collection = extra_info.get('path_collection', '')
                    name = extra_info.get('name', file_name)
                    if not path_collection.endswith('/'):
                        path_collection += '/'
                    stable_file_path = f"{path_collection}{name}"
                    metadata_to_pass['file_path'] = stable_file_path
                    logger.info(f"Using Box stable file_path: {stable_file_path} (temp was: {actual_file_path})")
                else:
                    # Other sources: Use actual file path
                    metadata_to_pass['file_path'] = str(actual_file_path)
                
                metadata_to_pass['file_name'] = file_name
                metadata_to_pass['file_size'] = file_size
                metadata_dict = {str(actual_file_path): metadata_to_pass}
                
                # Process the file right now while it still exists in temp directory
                # process_documents is async and takes a list of paths + optional metadata
                import asyncio
                processed_docs = asyncio.run(
                    self.doc_processor.process_documents([str(actual_file_path)], original_metadata=metadata_dict)
                )
                
                # Rename back to original ugly name so reader's cleanup works
                if renamed_path:
                    try:
                        shutil.move(str(renamed_path), str(file_path))
                        logger.info(f"Renamed file back to {Path(file_path).name} for cleanup")
                    except Exception as e:
                        logger.warning(f"Could not rename file back to original: {e}")
                
                if processed_docs and len(processed_docs) > 0:
                    logger.info(f"Successfully processed file immediately: {file_name}")
                    return [processed_docs[0]]  # Return the first processed document
                else:
                    logger.warning(f"No document returned from processing {file_name}")
            except Exception as e:
                logger.error(f"Error processing file {file_name} immediately: {e}")
                # Try to rename back even if processing failed
                if renamed_path:
                    try:
                        shutil.move(str(renamed_path), str(file_path))
                        logger.info(f"Renamed file back to {Path(file_path).name} after error")
                    except:
                        pass  # Ignore errors during cleanup
                # Fall through to return placeholder if processing fails
        
        # Return placeholder document with file path and fs object
        # DocumentProcessor will handle downloading if fs is provided
        
        # For Box, use stable path instead of temp path
        if extra_info and extra_info.get('path_collection') and extra_info.get('name'):
            # Box: Construct stable file_path
            path_collection = extra_info.get('path_collection', '')
            name = extra_info.get('name', file_name)
            if not path_collection.endswith('/'):
                path_collection += '/'
            stable_file_path = f"{path_collection}{name}"
            logger.info(f"Placeholder: Using Box stable file_path: {stable_file_path}")
            file_path_to_store = stable_file_path
        else:
            # Other sources: Use actual file path
            file_path_to_store = str(file_path)
        
        metadata = {
            "file_path": file_path_to_store,  # Stable path for Box, temp/actual path for others
            "file_name": file_name,
            "file_size": file_size,
            **(extra_info or {})  # Merge in metadata from SimpleDirectoryReader
        }
        
        # Pass fs object in metadata if it's a remote filesystem
        if fs and not is_default_fs(fs):
            metadata["_fs"] = fs  # Store fs object for DocumentProcessor
            logger.info(f"Passing remote filesystem {type(fs).__name__} to DocumentProcessor")
        
        return [Document(
            text="",  # Empty text - will be filled by DocumentProcessor
            metadata=metadata
        )]

