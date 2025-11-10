import asyncio
from pathlib import Path
from typing import List, Union, Optional, Dict
import logging
import os
import tempfile

from llama_index.core import Document

logger = logging.getLogger(__name__)

def get_parser_type_from_env() -> str:
    """Get parser type from environment variable, defaulting to docling"""
    parser = os.getenv('DOCUMENT_PARSER', 'docling').lower()
    if parser not in ['docling', 'llamaparse']:
        logger.warning(f"Unknown DOCUMENT_PARSER value '{parser}', defaulting to 'docling'")
        return 'docling'
    return parser

class DocumentProcessor:
    """Handles document conversion using Docling or LlamaParse before LlamaIndex processing"""
    
    def __init__(self, config=None, parser_type: str = "docling"):
        """
        Initialize DocumentProcessor with configurable parser.
        
        Args:
            config: Configuration object with timeout and API key settings
            parser_type: "docling" or "llamaparse" - which parser to use
        """
        self.config = config
        self.parser_type = parser_type.lower()
        
        # Store configuration for timeouts
        if self.parser_type == "docling":
            self._init_docling()
        elif self.parser_type == "llamaparse":
            self._init_llamaparse()
        else:
            raise ValueError(f"Unknown parser type: {parser_type}. Must be 'docling' or 'llamaparse'")
        
        logger.info(f"DocumentProcessor initialized with {self.parser_type} parser")
    
    def _init_docling(self):
        """Initialize Docling parser"""
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
            
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
            logger.info("Docling converter initialized")
        except ImportError as e:
            logger.error(f"Failed to import Docling: {e}")
            raise ImportError("Please install docling: pip install docling")
    
    def _init_llamaparse(self):
        """Initialize LlamaParse parser"""
        try:
            from llama_parse import LlamaParse
            
            # Get API key from config or environment
            api_key = None
            if self.config:
                api_key = getattr(self.config, 'llamaparse_api_key', None)
            
            if not api_key:
                api_key = os.getenv('LLAMAPARSE_API_KEY')
            
            if not api_key:
                raise ValueError("LLAMAPARSE_API_KEY not found in config or environment variables")
            
            # Initialize LlamaParse with configurable mode and model
            # Parsing mode options (credits per page):
            # 1. parse_mode="parse_page_without_llm" - 1 credit/page (cheapest, text-only)
            # 2. parse_mode="parse_page_with_llm" - 3 credits/page (no model param needed) - DEFAULT
            # 3. parse_mode="parse_page_with_agent" + model="openai-gpt-4-1-mini" - 10 credits/page
            #    (range: 10-90 credits/page depending on model chosen)
            
            # Get parse mode from environment or config, default to "parse_page_with_llm"
            parse_mode = os.getenv('LLAMAPARSE_MODE', 'parse_page_with_llm')
            
            # Set result_type based on parse_mode
            # parse_page_without_llm only produces text, not markdown
            result_type = "text" if parse_mode == "parse_page_without_llm" else "markdown"
            
            # Build parser kwargs
            parser_kwargs = {
                "api_key": api_key,
                "result_type": result_type,
                "verbose": True,
                "language": "en",
                "parse_mode": parse_mode,
                "show_progress": True
            }
            
            # If using agent mode, add model parameter
            if parse_mode == "parse_page_with_agent":
                model_name = os.getenv('LLAMAPARSE_AGENT_MODEL', 'openai-gpt-4-1-mini')
                parser_kwargs["model"] = model_name
                logger.info(f"LlamaParse parser initialized with parse_mode={parse_mode}, model={model_name}, result_type={result_type}")
            else:
                logger.info(f"LlamaParse parser initialized with parse_mode={parse_mode}, result_type={result_type}")
            
            self.parser = LlamaParse(**parser_kwargs)
        except ImportError as e:
            logger.error(f"Failed to import LlamaParse: {e}")
            raise ImportError("Please install llama-parse: pip install llama-parse")
        except Exception as e:
            logger.error(f"Failed to initialize LlamaParse: {e}")
            raise
    
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
        """Convert documents to markdown using selected parser, then create LlamaIndex Documents"""
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
        
        if self.parser_type == "docling":
            return await self._process_with_docling(file_paths, _check_cancellation, {})
        elif self.parser_type == "llamaparse":
            return await self._process_with_llamaparse(file_paths, _check_cancellation, {})
    
    async def _process_with_docling(self, file_paths: List[Union[str, Path]], check_cancellation, original_filenames: Dict[str, str] = None) -> List[Document]:
        """Process documents using Docling
        
        Args:
            file_paths: List of file paths to process
            check_cancellation: Function to check if processing should be cancelled
            original_filenames: Optional dict mapping temp paths to original filenames
        """
        documents = []
        
        if original_filenames is None:
            original_filenames = {}
        
        # Provide a default no-op cancellation check if None
        if check_cancellation is None:
            check_cancellation = lambda: False
        
        # Process files in parallel for better performance with multiple files
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        async def process_single_file(file_path):
            """Process a single file and return Document or None"""
            # Check for cancellation before processing each file
            if check_cancellation():
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
                    if check_cancellation():
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
                            loop, convert_func, check_cancellation
                        )
                    except concurrent.futures.TimeoutError:
                        raise RuntimeError("Processing cancelled by user")
                    
                    # Final check for cancellation after Docling conversion
                    if check_cancellation():
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
        logger.info(f"Processing {len(file_paths)} files with Docling in parallel...")
        tasks = [process_single_file(file_path) for file_path in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        documents = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing file {file_paths[i]}: {result}")
            elif result is not None:
                documents.append(result)
        
        logger.info(f"Successfully processed {len(documents)} documents with Docling in parallel")
        return documents
    
    async def _process_with_llamaparse(self, file_paths: List[Union[str, Path]], check_cancellation, original_filenames: Dict[str, str] = None) -> List[Document]:
        """Process documents using LlamaParse
        
        Args:
            file_paths: List of file paths to process (temp files already have meaningful names)
            check_cancellation: Optional function to check if processing should be cancelled
            original_filenames: Optional dict (kept for backward compatibility, but not needed anymore)
        """
        documents = []
        
        # Check for cancellation before starting
        if check_cancellation and check_cancellation():
            logger.info("Document processing cancelled by user")
            raise RuntimeError("Processing cancelled by user")
        
        # Verify parser is initialized
        if not hasattr(self, 'parser') or self.parser is None:
            error_msg = "LlamaParse parser not initialized. Check LLAMAPARSE_API_KEY in environment or config."
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info(f"Processing {len(file_paths)} files with LlamaParse...")
        
        # Convert paths to strings
        str_paths = [str(p) for p in file_paths]
        
        try:
            # Use LlamaParse async loading - temp files already have meaningful names
            # so LlamaCloud will display them correctly
            parsed_docs = await self.parser.aload_data(str_paths)
            
            # Check for cancellation after parsing
            if check_cancellation and check_cancellation():
                logger.info("Document processing cancelled after LlamaParse conversion")
                raise RuntimeError("Processing cancelled by user")
            
            # Convert LlamaParse documents to LlamaIndex Documents
            for i, parsed_doc in enumerate(parsed_docs):
                file_path = Path(file_paths[i]) if i < len(file_paths) else Path("unknown")
                
                # Log content length for debugging
                content = parsed_doc.text
                logger.info(f"LlamaParse extracted {len(content)} characters from {file_path.name}")
                logger.debug(f"First 200 chars: {content[:200]}...")
                
                # Create LlamaIndex Document with LlamaParse metadata
                doc = Document(
                    text=content,
                    metadata={
                        **parsed_doc.metadata,  # Include metadata from LlamaParse first
                        "source": str(file_path),  # Then override with corrected values
                        "conversion_method": "llamaparse",
                        "file_type": file_path.suffix,
                        "file_name": file_path.name,
                    }
                )
                documents.append(doc)
            
            logger.info(f"Successfully processed {len(file_paths)} files ({len(documents)} chunks) with LlamaParse")
            return documents
            
        except Exception as e:
            logger.error(f"Error processing files with LlamaParse: {e}")
            raise
    
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
    
    async def process_documents_from_metadata(self, placeholder_docs: List[Document], check_cancellation=None) -> List[Document]:
        """
        Process documents that contain file_path and optionally _fs in metadata.
        If _fs is present, downloads the file from remote filesystem first.
        
        Args:
            placeholder_docs: List of placeholder documents with metadata containing:
                             - file_path: path to file (local or remote)
                             - _fs: optional filesystem object for remote files
            check_cancellation: Optional function to check if processing should be cancelled
        
        Returns:
            List[Document]: Processed documents with full content
        """
        temp_files = []  # Track temp files for cleanup
        original_filenames = {}  # Map temp paths to original filenames
        
        try:
            # Process each placeholder document
            file_paths_to_process = []
            
            for doc in placeholder_docs:
                file_path = doc.metadata.get("file_path")
                fs = doc.metadata.get("_fs")
                
                if not file_path:
                    logger.warning("Placeholder document missing file_path in metadata")
                    continue
                
                # If remote filesystem, download to temp
                if fs:
                    try:
                        from llama_index.core.readers.file.base import is_default_fs
                        
                        if not is_default_fs(fs):
                            logger.info(f"Downloading remote file {file_path} to temp location")
                            
                            # Get original filename
                            file_name = doc.metadata.get("file_name", Path(file_path).name)
                            
                            # Create temp file with original filename preserved
                            # Files from same source should have unique names already
                            temp_dir = tempfile.gettempdir()
                            temp_path = os.path.join(temp_dir, file_name)
                            
                            # Download file
                            with fs.open(str(file_path), 'rb') as remote_file:
                                with open(temp_path, 'wb') as local_file:
                                    local_file.write(remote_file.read())
                            
                            file_paths_to_process.append(temp_path)
                            temp_files.append(temp_path)
                            logger.info(f"Downloaded {file_path} to {temp_path} (preserving original name: {file_name})")
                        else:
                            # Local filesystem - use path as-is
                            file_paths_to_process.append(file_path)
                    except Exception as e:
                        logger.error(f"Failed to download {file_path}: {e}")
                        # Skip this file but continue with others
                        continue
                else:
                    # No fs object - assume local path
                    file_paths_to_process.append(file_path)
            
            if not file_paths_to_process:
                logger.warning("No files to process after download phase")
                return []
            
            logger.info(f"Processing {len(file_paths_to_process)} files with {self.parser_type}")
            
            # Process files based on parser type
            if self.parser_type == "docling":
                documents = await self._process_with_docling(file_paths_to_process, check_cancellation, original_filenames)
            elif self.parser_type == "llamaparse":
                documents = await self._process_with_llamaparse(file_paths_to_process, check_cancellation, original_filenames)
            else:
                raise ValueError(f"Unknown parser type: {self.parser_type}")
            
            return documents
            
        finally:
            # Clean up temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                        logger.debug(f"Cleaned up temp file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file {temp_file}: {e}")