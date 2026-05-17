import asyncio
from datetime import datetime, timezone
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
        """Initialize Docling parser with GPU/device configuration"""
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
            from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
            
            # Get device configuration from environment or config
            # Options: "auto" (default - uses GPU if available), "cpu", "cuda", "mps" (Mac)
            device_str = os.getenv('DOCLING_DEVICE', 'auto')
            if self.config:
                device_str = getattr(self.config, 'docling_device', 'auto')
            
            # Map string to Docling's AcceleratorDevice enum
            device_mapping = {
                'auto': AcceleratorDevice.AUTO,
                'cpu': AcceleratorDevice.CPU,
                'cuda': AcceleratorDevice.CUDA,
                'mps': AcceleratorDevice.MPS,
            }
            
            accelerator_device = device_mapping.get(device_str.lower(), AcceleratorDevice.AUTO)
            logger.info(f"Docling device configuration: {device_str} -> {accelerator_device}")
            
            # Create accelerator options with device selection
            accelerator_options = AcceleratorOptions(
                num_threads=8,  # Reasonable default for parallel processing
                device=accelerator_device
            )
            
            # OCR configuration (env fallbacks align with config.py defaults)
            do_ocr = bool(os.getenv('DOCLING_OCR', '').lower() in ('1', 'true', 'yes'))
            ocr_engine_str = os.getenv('DOCLING_OCR_ENGINE', 'auto')
            if self.config:
                do_ocr = getattr(self.config, 'docling_ocr', False)
                ocr_engine_str = getattr(self.config, 'docling_ocr_engine', 'auto')

            ocr_options = None
            if do_ocr:
                from docling.datamodel.pipeline_options import (
                    OcrAutoOptions, EasyOcrOptions, TesseractOcrOptions,
                    TesseractCliOcrOptions, RapidOcrOptions,
                )
                engine = ocr_engine_str.lower()
                if engine == 'auto':
                    ocr_options = OcrAutoOptions()
                elif engine == 'easyocr':
                    ocr_options = EasyOcrOptions()
                elif engine == 'tesserocr':
                    ocr_options = TesseractOcrOptions()
                elif engine == 'tesseract_cli':
                    ocr_options = TesseractCliOcrOptions()
                elif engine == 'rapidocr':
                    ocr_options = RapidOcrOptions()
                elif engine == 'ocrmac':
                    try:
                        from docling.datamodel.pipeline_options import OcrMacOptions
                        ocr_options = OcrMacOptions()
                    except ImportError:
                        logger.warning("OcrMacOptions not available (macOS only), falling back to auto")
                        ocr_options = OcrAutoOptions()
                else:
                    logger.warning(f"Unknown DOCLING_OCR_ENGINE '{ocr_engine_str}', falling back to auto")
                    ocr_options = OcrAutoOptions()

                resolved = type(ocr_options).__name__
                logger.info(
                    "Docling OCR config (app): enabled=true requested_engine=%r "
                    "pipeline_ocr_options=%s",
                    ocr_engine_str,
                    resolved,
                )
                if str(ocr_engine_str).lower().strip() == "auto":
                    logger.info(
                        "Docling OCR: requested_engine=auto — Docling chooses an installed "
                        "backend at conversion time; its log line "
                        "\"Auto OCR model selected ...\" is the effective engine."
                    )
            else:
                logger.info(
                    "Docling OCR config (app): enabled=false "
                    "(set DOCLING_OCR=true for scanned PDFs/images)"
                )

            # Configure Docling for optimal PDF processing
            pdf_pipeline_kwargs = dict(
                do_table_structure=True,
                do_picture_classification=True,
                do_formula_enrichment=True,
                do_ocr=do_ocr,
                table_structure_options=TableStructureOptions(
                    do_cell_matching=True
                ),
                accelerator_options=accelerator_options,
            )
            if do_ocr and ocr_options is not None:
                pdf_pipeline_kwargs['ocr_options'] = ocr_options

            pdf_options = PdfPipelineOptions(**pdf_pipeline_kwargs)
            
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
            
            # Log device info
            try:
                import torch
                if torch.cuda.is_available():
                    device_name = torch.cuda.get_device_name(0)
                    logger.info(f"Docling converter initialized - CUDA available: {device_name}")
                elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    logger.info("Docling converter initialized - MPS (Apple Metal) available")
                else:
                    logger.info("Docling converter initialized - Running on CPU")
            except ImportError:
                logger.info("Docling converter initialized - PyTorch not available, using CPU")
                
        except ImportError as e:
            logger.error(f"Failed to import Docling: {e}")
            raise ImportError("Please install docling: pip install docling")
    
    # ------------------------------------------------------------------
    # LlamaParse v2 (llama-cloud >= 2.1) helpers
    # ------------------------------------------------------------------

    # Map v1 parse_mode values -> v2 tier names.
    # "fast" tier returns text only (no markdown); everything else supports markdown.
    _TIER_MAP: dict = {
        # v1 name                   v2 tier
        "parse_page_with_llm":      "cost_effective",
        "parse_page_with_agent":    "agentic",
        "parse_page_without_llm":   "fast",          # fast = no markdown
        # direct v2 tier names pass through unchanged
        "cost_effective":           "cost_effective",
        "agentic":                  "agentic",
        "agentic_plus":             "agentic_plus",
        "fast":                     "fast",
    }

    def _resolve_llamaparse_api_key(self) -> str:
        """Return the LlamaCloud API key from config or environment."""
        api_key = None
        if self.config:
            # Both LLAMAPARSE_API_KEY and LLAMA_CLOUD_API_KEY are accepted
            api_key = (
                getattr(self.config, 'llamaparse_api_key', None)
                or getattr(self.config, 'llama_cloud_api_key', None)
            )
        if not api_key:
            api_key = os.getenv('LLAMA_CLOUD_API_KEY') or os.getenv('LLAMAPARSE_API_KEY')
        if not api_key:
            raise ValueError(
                "LlamaCloud API key not found. "
                "Set LLAMA_CLOUD_API_KEY (or LLAMAPARSE_API_KEY) in environment or config."
            )
        return api_key

    def _resolve_llamaparse_tier(self) -> str:
        """Map the LLAMAPARSE_MODE env var to a v2 tier string."""
        raw = os.getenv('LLAMAPARSE_MODE', 'parse_page_with_llm')
        tier = self._TIER_MAP.get(raw, 'cost_effective')
        if tier != raw:
            logger.info(f"LlamaParse: LLAMAPARSE_MODE={raw!r} mapped to v2 tier={tier!r}")
        return tier

    def _make_llamaparse_client(self):
        """Create a fresh AsyncLlamaCloud client (v2 SDK).

        The client itself is stateless — no event-loop locks — so recreation
        is only needed if the API key changes between calls.
        """
        from llama_cloud import AsyncLlamaCloud  # llama-cloud >= 2.1

        api_key = self._resolve_llamaparse_api_key()
        return AsyncLlamaCloud(api_key=api_key)

    def _init_llamaparse(self):
        """Validate the API key and log v2 tier at startup."""
        try:
            from llama_cloud import AsyncLlamaCloud  # noqa: F401 — import check only
        except ImportError as exc:
            raise ImportError(
                "Please install llama-cloud>=2.1: pip install 'llama-cloud>=2.1'"
            ) from exc

        try:
            tier = self._resolve_llamaparse_tier()
            # Validate API key is present (raises ValueError if missing)
            self._resolve_llamaparse_api_key()
            if tier == "fast":
                logger.warning(
                    "LlamaParse tier=fast returns text only (no markdown). "
                    "Switch LLAMAPARSE_MODE to 'agentic' or 'cost_effective' for markdown output."
                )
            logger.info(f"LlamaParse v2 client ready (tier={tier})")
        except Exception as exc:
            logger.error(f"Failed to initialize LlamaParse v2: {exc}")
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
    
    async def process_documents(self, file_paths: List[Union[str, Path]], processing_id: str = None, original_metadata: Dict[str, Dict] = None) -> List[Document]:
        """Convert documents to markdown using selected parser, then create LlamaIndex Documents
        
        Args:
            file_paths: List of file paths to process
            processing_id: Optional processing ID for cancellation checks
            original_metadata: Optional dict mapping file paths to original metadata (e.g., from cloud sources)
        """
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
        
        if original_metadata is None:
            original_metadata = {}
        
        if self.parser_type == "docling":
            return await self._process_with_docling(file_paths, _check_cancellation, {}, original_metadata)
        elif self.parser_type == "llamaparse":
            return await self._process_with_llamaparse(file_paths, _check_cancellation, {}, original_metadata)
    
    async def _process_with_docling(self, file_paths: List[Union[str, Path]], check_cancellation, original_filenames: Dict[str, str] = None, original_metadata: Dict[str, Dict] = None) -> List[Document]:
        """Process documents using Docling
        
        Args:
            file_paths: List of file paths to process
            check_cancellation: Function to check if processing should be cancelled
            original_filenames: Optional dict mapping temp paths to original filenames
            original_metadata: Optional dict mapping file paths to original metadata from placeholder docs
        """
        documents = []
        
        if original_filenames is None:
            original_filenames = {}
        
        if original_metadata is None:
            original_metadata = {}
        
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
                    
                    # Determine which format to use for extraction
                    format_config = getattr(self.config, 'parser_format_for_extraction', 'auto') if self.config else 'auto'
                    
                    if format_config == 'markdown':
                        content_to_use = markdown_content
                        format_used = "markdown (forced by config)"
                    elif format_config == 'plaintext':
                        content_to_use = plain_text
                        format_used = "plaintext (forced by config)"
                    else:  # auto
                        if has_tables:
                            content_to_use = markdown_content
                            format_used = "markdown (tables detected)"
                        else:
                            content_to_use = plain_text
                            format_used = "plaintext (no tables)"
                    
                    # Save parsing output if configured (works for both Docling and LlamaParse)
                    if self.config and getattr(self.config, 'save_parsing_output', False):
                        try:
                            output_dir = Path("./parsing_output")
                            output_dir.mkdir(exist_ok=True)
                            
                            # Create output filename
                            base_name = path_obj.stem
                            markdown_file = output_dir / f"{base_name}_docling_markdown.md"
                            plaintext_file = output_dir / f"{base_name}_docling_plaintext.txt"
                            metadata_file = output_dir / f"{base_name}_docling_metadata.json"
                            
                            # Save both formats
                            with open(markdown_file, 'w', encoding='utf-8') as f:
                                f.write(markdown_content)
                            logger.info(f"Saved Docling markdown output to: {markdown_file}")
                            
                            with open(plaintext_file, 'w', encoding='utf-8') as f:
                                f.write(plain_text)
                            logger.info(f"Saved Docling plain text output to: {plaintext_file}")
                            
                            # Save metadata as JSON
                            import json
                            docling_metadata = {
                                "source": str(file_path),
                                "file_type": path_obj.suffix,
                                "file_name": path_obj.name,
                                "conversion_method": "docling",
                                "markdown_length": len(markdown_content),
                                "plaintext_length": len(plain_text),
                                "has_tables": has_tables,
                                "format_used_for_processing": "markdown" if has_tables else "plaintext",
                            }
                            with open(metadata_file, 'w', encoding='utf-8') as f:
                                json.dump(docling_metadata, f, indent=2, ensure_ascii=False)
                            logger.info(f"Saved Docling metadata to: {metadata_file}")
                            
                            # Check for parser errors in content
                            error_indicators = ['Parser Error', 'ParserError', 'Failed to parse', 'ERROR:', 'Exception:']
                            for indicator in error_indicators:
                                if indicator in markdown_content or indicator in plain_text:
                                    logger.warning(f"Possible parser error detected in {markdown_file} - content contains '{indicator}'")
                            
                            # Check for LaTeX/KaTeX rendering issues that might appear in preview
                            latex_issues = ['\\[', '\\]', '$$', '\\begin{', '\\end{']
                            has_latex = any(indicator in markdown_content for indicator in latex_issues)
                            if has_latex:
                                logger.info(f"Note: {markdown_file} contains LaTeX/math expressions - may show rendering errors in preview")
                            
                        except Exception as e:
                            logger.warning(f"Failed to save Docling parsing output: {e}")
                    
                    logger.info(f"Using {format_used} for {file_path}")
                    
                    # Log content length for debugging
                    logger.info(f"Docling extracted {len(content_to_use)} characters from {file_path}")
                    logger.debug(f"First 200 chars: {content_to_use[:200]}...")
                    
                    # Get original metadata if available (from cloud sources)
                    orig_meta = original_metadata.get(str(file_path), {})
                    
                    # Create LlamaIndex Document - merge original metadata with new fields
                    doc = Document(
                        text=content_to_use,
                        metadata={
                            **orig_meta,  # Include original metadata first (contains file id, etc.)
                            "source": str(file_path),  # Then override with processing metadata
                            "conversion_method": "docling",
                            "file_type": path_obj.suffix,
                            "file_name": orig_meta.get("file_name") or path_obj.name  # Prefer original name
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
                    
                    # Get original metadata if available (from cloud sources)
                    orig_meta = original_metadata.get(str(file_path), {})
                    
                    # Create LlamaIndex Document - merge original metadata with new fields
                    doc = Document(
                        text=content,
                        metadata={
                            **orig_meta,  # Include original metadata first (contains file id, etc.)
                            "source": str(file_path),  # Then override with processing metadata
                            "conversion_method": "direct",
                            "file_type": path_obj.suffix,
                            "file_name": orig_meta.get("file_name") or path_obj.name  # Prefer original name
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
    
    async def _process_with_llamaparse(
        self,
        file_paths: List[Union[str, Path]],
        check_cancellation,
        original_filenames: Dict[str, str] = None,
        original_metadata: Dict[str, Dict] = None,
    ) -> List[Document]:
        """Process documents using LlamaParse v2 (llama-cloud >= 2.1).

        Creates ONE Document per file (all pages combined) for proper document-level tracking.
        Uses the two-step v2 flow: upload file -> parse with structured options.

        Args:
            file_paths: List of file paths to process.
            check_cancellation: Callable that returns True when the job should abort.
            original_filenames: Kept for backward-compat; not used by v2.
            original_metadata: Dict mapping file-path -> original metadata from placeholder docs.
        """
        documents = []

        if original_metadata is None:
            original_metadata = {}

        if check_cancellation and check_cancellation():
            logger.info("Document processing cancelled by user")
            raise RuntimeError("Processing cancelled by user")

        tier = self._resolve_llamaparse_tier()
        # v2 "fast" tier returns text only — no markdown available
        fast_tier = tier == "fast"

        # Determine which expand fields to request
        expand = ["text"] if fast_tier else ["text", "markdown"]

        # Build v2 options from config / env
        language = os.getenv('LLAMAPARSE_LANGUAGE', 'en')
        format_config = getattr(self.config, 'parser_format_for_extraction', 'auto') if self.config else 'auto'

        processing_options: dict = {
            "ocr_parameters": {"languages": [language]},
        }

        # LLAMAPARSE_AGENT_MODEL -> agentic_options.custom_prompt (v2 no longer takes model directly)
        # Custom prompt supported on cost_effective / agentic / agentic_plus
        agentic_options: Optional[dict] = None
        if tier in ("agentic", "agentic_plus", "cost_effective"):
            custom_prompt = os.getenv('LLAMAPARSE_CUSTOM_PROMPT', '')
            if custom_prompt:
                agentic_options = {"custom_prompt": custom_prompt}

        output_options: dict = {}
        if not fast_tier:
            output_options = {
                "markdown": {
                    "tables": {
                        "output_tables_as_markdown": True,
                    },
                },
            }

        logger.info(
            f"Processing {len(file_paths)} files with LlamaParse v2 "
            f"(tier={tier}, expand={expand})"
        )

        # One fresh client per batch (stateless — no event-loop binding in v2)
        client = self._make_llamaparse_client()

        try:
            for file_path in file_paths:
                if check_cancellation and check_cancellation():
                    logger.info("Document processing cancelled by user")
                    raise RuntimeError("Processing cancelled by user")

                file_path_str = str(file_path)
                path_obj = Path(file_path)
                logger.info(f"Processing {file_path} with LlamaParse v2...")

                try:
                    file_size = path_obj.stat().st_size
                    logger.info(f"File size: {file_size} bytes")
                except Exception as exc:
                    logger.warning(f"Could not determine file size: {exc}")

                # --- Step 1: upload ---
                try:
                    with open(file_path_str, "rb") as fh:
                        file_obj = await client.files.create(file=fh, purpose="parse")
                except Exception as exc:
                    logger.error(f"LlamaParse v2 file upload failed for {path_obj.name}: {exc}")
                    logger.warning(f"Skipping {path_obj.name}")
                    continue

                # --- Step 2: parse ---
                parse_kwargs: dict = {
                    "file_id": file_obj.id,
                    "tier": tier,
                    "version": "latest",
                    "expand": expand,
                }
                if processing_options:
                    parse_kwargs["processing_options"] = processing_options
                if output_options:
                    parse_kwargs["output_options"] = output_options
                if agentic_options:
                    parse_kwargs["agentic_options"] = agentic_options

                try:
                    result = await client.parsing.parse(**parse_kwargs)
                except Exception as exc:
                    logger.error(f"LlamaParse v2 parse failed for {path_obj.name}: {exc}")
                    logger.warning(f"Skipping {path_obj.name}")
                    continue

                if check_cancellation and check_cancellation():
                    logger.info("Document processing cancelled after LlamaParse v2 conversion")
                    raise RuntimeError("Processing cancelled by user")

                # --- Step 3: extract content from result ---
                # result.markdown.pages[i].markdown  (if expand includes "markdown")
                # result.text.pages[i].text           (if expand includes "text")
                markdown_parts: List[str] = []
                plaintext_parts: List[str] = []

                md_pages = []
                txt_pages = []
                try:
                    if not fast_tier and result.markdown and result.markdown.pages:
                        md_pages = result.markdown.pages
                except AttributeError:
                    pass
                try:
                    if result.text and result.text.pages:
                        txt_pages = result.text.pages
                except AttributeError:
                    pass

                for page in md_pages:
                    md = getattr(page, "markdown", None)
                    if md:
                        markdown_parts.append(md)
                for page in txt_pages:
                    txt = getattr(page, "text", None)
                    if txt:
                        plaintext_parts.append(txt)

                markdown_content = "\n\n".join(markdown_parts)
                plaintext_content = "\n\n".join(plaintext_parts)
                total_pages = max(len(md_pages), len(txt_pages))

                logger.info(
                    f"LlamaParse v2 extracted {len(markdown_content)} chars (markdown), "
                    f"{len(plaintext_content)} chars (plaintext) from {path_obj.name} "
                    f"({total_pages} pages)"
                )

                if not markdown_content.strip() and not plaintext_content.strip():
                    logger.warning(f"LlamaParse v2 extracted empty content for {path_obj.name} - skipping")
                    continue

                # --- Step 4: choose content format ---
                if fast_tier:
                    content_to_use = plaintext_content
                    format_used = "plaintext (fast tier - no markdown)"
                elif format_config == 'plaintext':
                    content_to_use = plaintext_content
                    format_used = "plaintext (config)"
                elif format_config == 'markdown':
                    content_to_use = markdown_content
                    format_used = "markdown (config)"
                else:
                    # auto: prefer markdown when tables are present
                    has_tables = "|" in markdown_content and "---" in markdown_content
                    if has_tables:
                        content_to_use = markdown_content
                        format_used = "markdown (tables detected)"
                    else:
                        content_to_use = plaintext_content
                        format_used = "plaintext (no tables)"

                logger.info(
                    f"Using {format_used} format for document processing (config: {format_config})"
                )

                # --- Step 5: optional save-to-disk ---
                if self.config and getattr(self.config, 'save_parsing_output', False):
                    try:
                        import json as _json
                        output_dir = Path("./parsing_output")
                        output_dir.mkdir(exist_ok=True)

                        base_name = path_obj.stem
                        markdown_file = output_dir / f"{base_name}_llamaparse_output.md"
                        plaintext_file = output_dir / f"{base_name}_llamaparse_output.txt"
                        metadata_file = output_dir / f"{base_name}_llamaparse_metadata.json"

                        with open(markdown_file, 'w', encoding='utf-8') as fh:
                            fh.write(markdown_content)
                        logger.info(f"Saved LlamaParse markdown output to: {markdown_file}")

                        with open(plaintext_file, 'w', encoding='utf-8') as fh:
                            fh.write(plaintext_content)
                        logger.info(f"Saved LlamaParse plaintext output to: {plaintext_file}")

                        save_meta = {
                            "source": file_path_str,
                            "file_name": path_obj.name,
                            "file_type": path_obj.suffix,
                            "total_pages": total_pages,
                            "markdown_length": len(markdown_content),
                            "plaintext_length": len(plaintext_content),
                            "tier": tier,
                            "format_used_for_processing": format_used,
                        }
                        with open(metadata_file, 'w', encoding='utf-8') as fh:
                            _json.dump(save_meta, fh, indent=2, ensure_ascii=False)
                        logger.info(f"Saved LlamaParse metadata to: {metadata_file}")

                        error_indicators = ['Parser Error', 'ParserError', 'Failed to parse', 'ERROR:', 'Exception:']
                        for indicator in error_indicators:
                            if indicator in markdown_content:
                                logger.warning(
                                    f"Possible parser error in {markdown_file} - "
                                    f"content contains '{indicator}'"
                                )

                        latex_issues = ['\\[', '\\]', '$$', '\\begin{', '\\end{']
                        if any(indicator in markdown_content for indicator in latex_issues):
                            logger.info(
                                f"Note: {markdown_file} contains LaTeX/math - "
                                "may show rendering errors in preview"
                            )
                    except Exception as exc:
                        logger.warning(f"Failed to save LlamaParse parsing output: {exc}")

                # --- Step 6: build LlamaIndex Document ---
                orig_meta = original_metadata.get(file_path_str, {})
                job_id = getattr(result, "id", None) or getattr(result, "job_id", None)
                try:
                    job_id = result.job.id
                except AttributeError:
                    pass

                doc = Document(
                    text=content_to_use,
                    metadata={
                        **orig_meta,
                        "source": file_path_str,
                        "conversion_method": "llamaparse",
                        "file_type": path_obj.suffix,
                        "file_name": orig_meta.get("file_name") or path_obj.name,
                        "total_pages": total_pages,
                        "format_used": format_used,
                        "job_id": job_id,
                        "llamaparse_tier": tier,
                    },
                )
                documents.append(doc)
                logger.info(
                    f"Created 1 Document for {path_obj.name} "
                    f"({total_pages} pages, {len(content_to_use)} chars)"
                )

            logger.info(
                f"LlamaParse v2: processed {len(file_paths)} files, "
                f"produced {len(documents)} documents"
            )
            if len(documents) < len(file_paths):
                failed = len(file_paths) - len(documents)
                logger.warning(
                    f"Processing incomplete: {failed}/{len(file_paths)} files produced no documents"
                )
            return documents

        except Exception as exc:
            logger.error(f"Error processing files with LlamaParse v2: {exc}")
            raise
    
    def process_text_content(self, content: str, source_name: str = "text_input") -> Document:
        """Create a LlamaIndex Document from text content"""
        return Document(
            text=content,
            metadata={
                "source": source_name,
                "conversion_method": "direct_text",
                "file_type": ".txt",
                "file_name": source_name,
                "file_path": "",
                "modified_at": datetime.now(timezone.utc).isoformat(),
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
        original_metadata = {}  # Map file paths to original metadata from placeholder docs
        
        try:
            # Process each placeholder document
            file_paths_to_process = []
            
            for doc in placeholder_docs:
                file_path = doc.metadata.get("file_path")
                fs = doc.metadata.get("_fs")
                
                if not file_path:
                    logger.warning("Placeholder document missing file_path in metadata")
                    continue
                
                # Store original metadata (excluding internal fields)
                # Filter out internal fields like _fs
                original_meta = {k: v for k, v in doc.metadata.items() if not k.startswith('_')}
                
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
                            # Map temp path to original metadata
                            original_metadata[temp_path] = original_meta
                            logger.info(f"Downloaded {file_path} to {temp_path} (preserving original name: {file_name})")
                        else:
                            # Local filesystem - use path as-is
                            file_paths_to_process.append(file_path)
                            original_metadata[file_path] = original_meta
                    except Exception as e:
                        logger.error(f"Failed to download {file_path}: {e}")
                        # Skip this file but continue with others
                        continue
                else:
                    # No fs object - assume local path
                    file_paths_to_process.append(file_path)
                    original_metadata[file_path] = original_meta
            
            if not file_paths_to_process:
                logger.warning("No files to process after download phase")
                return []
            
            logger.info(f"Processing {len(file_paths_to_process)} files with {self.parser_type}")
            
            # Process files based on parser type
            if self.parser_type == "docling":
                documents = await self._process_with_docling(file_paths_to_process, check_cancellation, original_filenames, original_metadata)
            elif self.parser_type == "llamaparse":
                documents = await self._process_with_llamaparse(file_paths_to_process, check_cancellation, original_filenames, original_metadata)
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