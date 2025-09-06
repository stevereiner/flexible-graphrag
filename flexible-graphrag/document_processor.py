import asyncio
from pathlib import Path
from typing import List, Union
import logging

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from llama_index.core import Document

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Handles document conversion using Docling before LlamaIndex processing"""
    
    def __init__(self, config=None):
        # Configure Docling for optimal PDF processing
        pdf_options = PdfPipelineOptions(
            do_table_structure=True,
            do_picture_classification=True,
            do_formula_enrichment=True,
            table_structure_options=TableStructureOptions(
                do_cell_matching=True
            )
        )
        
        # Configure all supported Docling formats
        self.converter = DocumentConverter(
            allowed_formats=[
                InputFormat.PDF,
                InputFormat.DOCX, 
                InputFormat.PPTX,
                InputFormat.HTML,
                InputFormat.IMAGE,
                InputFormat.XLSX,
                InputFormat.MD,
                InputFormat.ASCIIDOC,
                InputFormat.CSV
            ],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)
            }
        )
        
        # Store configuration for timeouts
        self.config = config
        
        logger.info("DocumentProcessor initialized with Docling converter")
    
    async def _run_with_cancellation_checks(self, loop, func, check_cancellation, timeout=None):
        """Run a function in executor with periodic cancellation checks"""
        import asyncio
        import concurrent.futures
        
        # Use configured timeout and check interval, or defaults
        if timeout is None:
            timeout = self.config.docling_timeout if self.config else 300
        check_interval = self.config.docling_cancel_check_interval if self.config else 0.5
        
        # Submit the task to executor
        future = loop.run_in_executor(None, func)
        
        elapsed = 0
        
        while not future.done():
            try:
                # Wait for a short period or task completion
                await asyncio.wait_for(asyncio.shield(future), timeout=check_interval)
                break  # Task completed
            except asyncio.TimeoutError:
                # Check for cancellation
                if check_cancellation():
                    logger.info("Cancelling Docling conversion due to user request")
                    future.cancel()
                    raise RuntimeError("Processing cancelled by user")
                
                # Check for overall timeout
                elapsed += check_interval
                if elapsed >= timeout:
                    logger.warning(f"Docling conversion timeout after {timeout} seconds")
                    future.cancel()
                    raise concurrent.futures.TimeoutError()
        
        return await future
    
    async def process_documents(self, file_paths: List[Union[str, Path]], processing_id: str = None) -> List[Document]:
        """Convert documents to markdown using Docling with parallel processing, then create LlamaIndex Documents"""
        documents = []
        
        # Helper function to check cancellation
        def _check_cancellation():
            if processing_id:
                try:
                    from backend import PROCESSING_STATUS
                    return (processing_id in PROCESSING_STATUS and 
                            PROCESSING_STATUS[processing_id]["status"] == "cancelled")
                except ImportError:
                    return False
            return False
        
        # Process files in parallel for better performance with multiple files
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        async def process_single_file(file_path):
            """Process a single file and return Document or None"""
            # Check for cancellation before processing each file
            if _check_cancellation():
                logger.info("Document processing cancelled by user")
                raise RuntimeError("Processing cancelled by user")
            try:
                path_obj = Path(file_path)
                
                # Check if file exists
                if not path_obj.exists():
                    logger.warning(f"File does not exist: {file_path}")
                    return None
                
                # Check if it's a supported file type by Docling
                docling_extensions = [
                    '.pdf', '.docx', '.xlsx', '.pptx',
                    '.html', '.htm', '.md', '.markdown', '.asciidoc', '.adoc',
                    '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.webp',
                    '.csv', '.xml', '.json'
                ]
                if path_obj.suffix.lower() in docling_extensions:
                    # Check for cancellation before heavy processing
                    if _check_cancellation():
                        logger.info("Document processing cancelled before Docling conversion")
                        raise RuntimeError("Processing cancelled by user")
                    
                    logger.info(f"Converting document with Docling: {file_path}")
                    
                    # Convert using Docling with cancellation support and proper async handling
                    import asyncio
                    import functools
                    import concurrent.futures
                    
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    convert_func = functools.partial(self.converter.convert, str(file_path))
                    
                    # Run with periodic cancellation checks using configured timeout
                    try:
                        result = await self._run_with_cancellation_checks(
                            loop, convert_func, _check_cancellation
                        )
                    except concurrent.futures.TimeoutError:
                        raise RuntimeError("Processing cancelled by user")
                    
                    # Final check for cancellation after Docling conversion
                    if _check_cancellation():
                        logger.info("Document processing cancelled after Docling conversion")
                        raise RuntimeError("Processing cancelled by user")
                    
                    # Extract both markdown and plain text
                    markdown_content = result.document.export_to_markdown()
                    plain_text = result.document.export_to_text()
                    
                    # Smart format selection: use markdown if tables detected, otherwise plain text
                    has_tables = "|" in markdown_content and "---" in markdown_content  # Simple table detection
                    
                    if has_tables:
                        content_to_use = markdown_content
                        format_used = "markdown (tables detected)"
                    else:
                        content_to_use = plain_text
                        format_used = "plain text (better for entities)"
                    
                    logger.info(f"Using {format_used} for {file_path}")
                    
                    # Log content length for debugging
                    logger.info(f"Docling extracted {len(content_to_use)} characters from {file_path}")
                    logger.debug(f"First 200 chars: {content_to_use[:200]}...")
                    
                    # Create LlamaIndex Document
                    doc = Document(
                        text=content_to_use,
                        metadata={
                            "source": str(file_path),
                            "conversion_method": "docling",
                            "file_type": path_obj.suffix,
                            "file_name": path_obj.name
                        }
                    )
                    return doc
                    
                elif path_obj.suffix.lower() in ['.txt', '.md']:
                    # Handle plain text files directly
                    logger.info(f"Reading text file directly: {file_path}")
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Log content length for debugging
                    logger.info(f"Direct read extracted {len(content)} characters from {file_path}")
                    logger.debug(f"First 200 chars: {content[:200]}...")
                    
                    doc = Document(
                        text=content,
                        metadata={
                            "source": str(file_path),
                            "conversion_method": "direct",
                            "file_type": path_obj.suffix,
                            "file_name": path_obj.name
                        }
                    )
                    return doc
                
                else:
                    logger.warning(f"Unsupported file type: {file_path}")
                    return None
                
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                return None
        
        # Process files in parallel using asyncio.gather
        logger.info(f"Processing {len(file_paths)} files in parallel...")
        tasks = [process_single_file(file_path) for file_path in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        documents = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing file {file_paths[i]}: {result}")
            elif result is not None:
                documents.append(result)
        
        logger.info(f"Successfully processed {len(documents)} documents in parallel")
        return documents
    
    def process_text_content(self, content: str, source_name: str = "text_input") -> Document:
        """Create a LlamaIndex Document from text content"""
        return Document(
            text=content,
            metadata={
                "source": source_name,
                "conversion_method": "direct_text",
                "file_type": ".txt",
                "file_name": source_name
            }
        )