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
    if parser not in ['docling', 'llamaparse', 'liteparse']:
        logger.warning(f"Unknown DOCUMENT_PARSER value '{parser}', defaulting to 'docling'")
        return 'docling'
    return parser


_PARSER_DISPLAY_NAMES = {
    "docling": "Docling",
    "llamaparse": "LlamaParse",
    "liteparse": "LiteParse",
}


def format_parser_display_name(parser_type: str) -> str:
    """Mixed-case display label for framework config logging."""
    return _PARSER_DISPLAY_NAMES.get(str(parser_type).lower(), str(parser_type))

class DocumentProcessor:
    """Handles document conversion using Docling or LlamaParse before LlamaIndex processing"""
    
    def __init__(self, config=None, parser_type: str = "docling"):
        """
        Initialize DocumentProcessor with configurable parser.
        
        Args:
            config: Configuration object with timeout and API key settings
            parser_type: "docling", "llamaparse", or "liteparse" - which parser to use
        """
        self.config = config
        self.parser_type = parser_type.lower()

        # Store configuration for timeouts
        if self.parser_type == "docling":
            self._init_docling()
        elif self.parser_type == "llamaparse":
            self._init_llamaparse()
        elif self.parser_type == "liteparse":
            self._init_liteparse()
        else:
            raise ValueError(f"Unknown parser type: {parser_type}. Must be 'docling', 'llamaparse', or 'liteparse'")
        
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
                        "Docling OCR: requested_engine=auto - Docling chooses an installed "
                        "backend at conversion time; its log line "
                        "\"Auto OCR model selected ...\" is the effective engine."
                    )
            else:
                logger.info(
                    "Docling OCR config (app): enabled=false "
                    "(set DOCLING_OCR=true for scanned PDFs/images)"
                )

            # TableFormer (PDF table structure) imports cv2; opencv has no wheel for every
            # Python build (e.g. free-threaded 3.15), so skip table structure without it
            import importlib.util
            do_table_structure = importlib.util.find_spec("cv2") is not None
            if not do_table_structure:
                logger.warning("Docling PDF table structure disabled: opencv (cv2) not installed")

            # Configure Docling for optimal PDF processing
            pdf_pipeline_kwargs = dict(
                do_table_structure=do_table_structure,
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

            # docling-parse (the default PDF backend) is C++ and has no wheel for every Python
            # build (e.g. free-threaded 3.15); fall back to docling's pypdfium2 backend then
            pdf_format_kwargs = dict(pipeline_options=pdf_options)
            try:
                import docling_parse  # noqa: F401
            except ImportError:
                from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
                pdf_format_kwargs['backend'] = PyPdfiumDocumentBackend
                logger.info("Docling PDF backend: pypdfium2 (docling-parse not installed)")

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
                    InputFormat.PDF: PdfFormatOption(**pdf_format_kwargs)
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
    
    def _init_liteparse(self):
        """Initialize LiteParse — a local (Rust/PyO3) PDF/office/image parser, no API key.
        See https://github.com/run-llama/liteparse . All knobs are optional and come from settings:
        ocr (bool), ocr_language, ocr_server_url, tessdata_path, dpi (float), num_workers (int),
        max_pages (int), output_format ('markdown'/'text'/'json'), image_mode, extract_links (bool).
        Unset options fall back to LiteParse's own defaults. Default in-app output_format is 'markdown'."""
        try:
            from liteparse import LiteParse
        except ImportError:
            raise ImportError("Please install liteparse: uv pip install liteparse")

        kwargs = {"quiet": True, "output_format": "markdown"}  # quiet=suppress stdout timing; markdown output by default
        if self.config is not None:
            # (settings attr, LiteParse kwarg, caster) — only forwarded when the setting is provided
            _opts = [
                ('liteparse_ocr', 'ocr_enabled', bool),
                ('liteparse_ocr_language', 'ocr_language', str),
                ('liteparse_ocr_server_url', 'ocr_server_url', str),
                ('liteparse_tessdata_path', 'tessdata_path', str),
                ('liteparse_dpi', 'dpi', float),
                ('liteparse_num_workers', 'num_workers', int),
                ('liteparse_max_pages', 'max_pages', int),
                ('liteparse_output_format', 'output_format', str),
                ('liteparse_image_mode', 'image_mode', str),
                ('liteparse_extract_links', 'extract_links', bool),
            ]
            for _attr, _kw, _cast in _opts:
                _v = getattr(self.config, _attr, None)
                if _v is not None and _v != "":
                    kwargs[_kw] = _cast(_v)

        self.liteparse = LiteParse(**kwargs)
        # Remember the effective OCR verdict for the pre-parse complexity check (default on)
        self._liteparse_ocr_enabled = bool(kwargs.get("ocr_enabled", True))
        logger.info(
            "LiteParse initialized (local parser; ocr_enabled=%s, ocr_language=%s, dpi=%s, "
            "output_format=%s, ocr_server=%s)",
            kwargs.get("ocr_enabled", "default"), kwargs.get("ocr_language", "default"),
            kwargs.get("dpi", "default"), kwargs.get("output_format"),
            "custom" if kwargs.get("ocr_server_url") else "local-tesseract",
        )

    @staticmethod
    def _norm_reason(r) -> str:
        """Normalize a reason flag for matching: lowercase, hyphens (so 'embedded_images' == 'embedded-images')."""
        return str(r).strip().lower().replace('_', '-')

    @staticmethod
    def _has_markdown_table(md: str) -> bool:
        """True only when the markdown has a real table delimiter row (two+ dash columns joined by a pipe,
        e.g. '| --- | --- |' or '--- | ---'). Tighter than 'contains | and --- anywhere', which
        false-positives on prose/OCR text that merely has both characters. Used by PARSER_FORMAT_FOR_EXTRACTION
        'auto' (Docling / LlamaParse / LiteParse) to decide markdown-vs-plaintext for extraction."""
        import re
        return bool(re.search(r':?-{3,}:?\s*\|\s*:?-{3,}:?', md or ""))

    @staticmethod
    def _safe_log(s, limit: int = None) -> str:
        """Make text safe to log under any handler encoding. The Windows cp1252 console (e.g. Langflow's,
        which hosts our component code) raises UnicodeEncodeError when a log record contains characters it
        can't encode — e.g. \\u200b (zero-width space), em-dashes, CJK — as happens when we log raw document
        content. Non-ASCII is rendered as backslash escapes so the log record never crashes the handler."""
        s = str(s)
        if limit is not None:
            s = s[:limit]
        return s.encode('ascii', 'backslashreplace').decode('ascii')

    @staticmethod
    def _select_extraction_content(markdown: str, plaintext: str, format_config: str):
        """Pick which text (markdown vs plaintext) feeds KG extraction / embeddings / search, per
        PARSER_FORMAT_FOR_EXTRACTION. Shared by Docling / LlamaParse / LiteParse.
        Returns (content, format_used, has_tables).
        'auto' (default): markdown when a real table is present, else plaintext — BUT if a table is
        detected while the markdown is *shorter* than the plaintext, the markdown likely dropped
        content (lossy OCR / xlsx markdown), so prefer the more-complete plaintext."""
        markdown = markdown or ""
        plaintext = plaintext or ""
        has_tables = DocumentProcessor._has_markdown_table(markdown)
        fc = (format_config or "auto").lower()
        if fc == "markdown":
            return (markdown or plaintext), "markdown (config)", has_tables
        if fc == "plaintext":
            return (plaintext or markdown), "plaintext (config)", has_tables
        # auto
        if has_tables:
            if len(markdown) < len(plaintext):
                return (plaintext or markdown), "plaintext (table detected but markdown shorter - likely lossy)", has_tables
            return (markdown or plaintext), "markdown (tables detected)", has_tables
        return (plaintext or markdown), "plaintext (no tables)", has_tables

    def _analyze_liteparse_complexity(self, file_path: str, trigger_reasons=None):
        """Cheap pre-parse OCR analysis via LiteParse.is_complex() (no full parse / no OCR run).
        Logs a status line for how many pages need OCR and why; warns instead if pages need OCR
        but OCR is disabled. `trigger_reasons` selects which pages count as 'complex' for routing:
        None → the needs_ocr verdict; a set of normalized reason flags → pages whose reasons match
        any of them (OR). Returns {total, needs_ocr, reasons(Counter), matched, matched_fraction} or
        None if the check could not run. Best-effort — any failure is swallowed at debug so it never
        blocks parsing. See https://developers.llamaindex.ai/liteparse/guides/complexity/ ."""
        try:
            pages = self.liteparse.is_complex(file_path)
        except Exception as e:
            logger.debug(f"LiteParse complexity check skipped for {file_path}: {e}")
            return None

        total = len(pages)
        if total == 0:
            return None

        from collections import Counter
        ocr_pages = [p for p in pages if getattr(p, 'needs_ocr', False)]
        n = len(ocr_pages)
        # 'reasons' is an open-ended flag list (scanned / no-text / sparse-text / embedded-images /
        # garbled / vector-text / ...) and is non-empty exactly when needs_ocr is true; aggregate
        # counts across those pages.
        reason_counts = Counter()
        for p in ocr_pages:
            for r in (getattr(p, 'reasons', None) or []):
                reason_counts[self._norm_reason(r)] += 1
        summary = ", ".join(f"{r}: {c}" for r, c in reason_counts.most_common()) or "unspecified"

        if n == 0:
            logger.info(f"LiteParse complexity: 0/{total} pages need OCR (text-native) - {file_path}")
        elif self._liteparse_ocr_enabled:
            logger.info(f"LiteParse complexity: {n}/{total} pages will have OCR done ({summary}) - {file_path}")
        else:
            logger.warning(
                f"LiteParse complexity: {n}/{total} pages need OCR but LITEPARSE_OCR is OFF - these pages "
                f"may extract poorly ({summary}). Set LITEPARSE_OCR=true to OCR them. File: {file_path}"
            )
        # Per-page detail at DEBUG (avoids info-log spam on large/garbled docs)
        for p in ocr_pages:
            reasons = ", ".join(str(r) for r in (getattr(p, 'reasons', None) or [])) or "?"
            logger.debug(f"  LiteParse page {getattr(p, 'page_number', '?')}: {reasons}")

        # Pages that count as 'complex' for routing, per the configured trigger.
        if trigger_reasons:
            matched = sum(
                1 for p in ocr_pages
                if trigger_reasons & {self._norm_reason(r) for r in (getattr(p, 'reasons', None) or [])}
            )
        else:
            matched = n  # needs_ocr verdict
        return {"total": total, "needs_ocr": n, "reasons": reason_counts,
                "matched": matched, "matched_fraction": (matched / total)}

    async def _process_with_fallback_parser(self, name: str, file_paths: List[Union[str, Path]],
                                            check_cancellation, original_metadata: Dict[str, Dict]) -> List[Document]:
        """Route complex documents to a heavier parser (docling / llamaparse) for LiteParse
        complex-routing. Lazily initializes the chosen fallback parser the first time it's needed."""
        name = (name or "docling").lower()
        if name not in ("docling", "llamaparse"):
            logger.warning(f"Unknown LiteParse complex-routing fallback '{name}'; using docling")
            name = "docling"
        if not hasattr(self, "_fallback_inited"):
            self._fallback_inited = set()

        if name == "docling":
            if not getattr(self, "converter", None):
                logger.info("Initializing docling for LiteParse complex-routing fallback")
                self._init_docling()
            return await self._process_with_docling(file_paths, check_cancellation, {}, original_metadata)
        else:  # llamaparse
            if "llamaparse" not in self._fallback_inited:
                logger.info("Initializing llamaparse for LiteParse complex-routing fallback")
                self._init_llamaparse()  # validates API key / logs tier (client is resolved per-call)
                self._fallback_inited.add("llamaparse")
            return await self._process_with_llamaparse(file_paths, check_cancellation, {}, original_metadata)

    async def _process_with_liteparse(self, file_paths: List[Union[str, Path]], check_cancellation,
                                      original_filenames: Dict[str, str] = None,
                                      original_metadata: Dict[str, Dict] = None) -> List[Document]:
        """Parse documents with LiteParse (local). PDFs/office/images go through liteparse.parse()
        (synchronous → run in an executor); plain text/markdown is read directly since LiteParse
        targets rich documents. Before parsing each rich doc, a cheap is_complex() pass logs the
        OCR outlook; when LITEPARSE_COMPLEX_ROUTING is on, docs whose page-OCR fraction meets the
        threshold are routed to the configured heavier parser (docling / llamaparse) instead."""
        original_metadata = original_metadata or {}
        loop = asyncio.get_event_loop()

        # Provide a default no-op cancellation check if None (matches docling/llamaparse). The
        # cloud download-then-process path (process_documents_from_metadata) passes None; only the
        # filesystem path passes a real callable. The safe callable is also forwarded to
        # _liteparse_parse_files below, so its own check_cancellation() calls are covered too.
        if check_cancellation is None:
            check_cancellation = lambda: False

        cfg = self.config
        routing_on = bool(getattr(cfg, "liteparse_complex_routing", False)) if cfg else False
        fallback_name = ((getattr(cfg, "liteparse_complex_fallback", None) or "docling").lower()) if cfg else "docling"
        threshold = float(getattr(cfg, "liteparse_complex_threshold", 0.0) or 0.0) if cfg else 0.0
        # Trigger: 'needs_ocr' (verdict) OR a comma-separated list of reason flags matched with OR.
        trigger_raw = str((getattr(cfg, "liteparse_complex_trigger", None) or "needs_ocr") if cfg else "needs_ocr").strip().lower()
        if trigger_raw in ("", "needs_ocr", "needs-ocr", "ocr"):
            trigger_reasons = None
            trigger_desc = "needs_ocr"
        else:
            trigger_reasons = {self._norm_reason(r) for r in trigger_raw.split(",") if r.strip()}
            trigger_desc = "reasons " + "/".join(sorted(trigger_reasons))

        liteparse_files: List[Union[str, Path]] = []
        route_files: List[Union[str, Path]] = []

        for file_path in file_paths:
            if check_cancellation():
                logger.info("LiteParse processing cancelled")
                break
            path_obj = Path(file_path)
            if not path_obj.exists():
                logger.warning(f"File does not exist: {file_path}")
                continue
            # Plain text/markdown never needs OCR/complexity analysis — read directly.
            if path_obj.suffix.lower() in ['.txt', '.md']:
                liteparse_files.append(file_path)
                continue
            # Cheap pre-parse OCR analysis (status/warning) — runs regardless of routing.
            stats = await loop.run_in_executor(None, self._analyze_liteparse_complexity, str(file_path), trigger_reasons)
            if routing_on and stats and stats["matched"] > 0 and stats["matched_fraction"] >= threshold:
                logger.info(
                    f"LiteParse routing: '{file_path}' is complex "
                    f"({stats['matched']}/{stats['total']} pages match {trigger_desc}, fraction "
                    f"{stats['matched_fraction']:.2f} >= threshold {threshold:g}) -> routing to {fallback_name}"
                )
                route_files.append(file_path)
            else:
                liteparse_files.append(file_path)

        documents = await self._liteparse_parse_files(liteparse_files, check_cancellation, original_metadata)

        if route_files:
            fallback_docs: List[Document] = []
            try:
                fallback_docs = await self._process_with_fallback_parser(
                    fallback_name, route_files, check_cancellation, original_metadata)
            except Exception as e:
                logger.error(f"LiteParse complex-routing to {fallback_name} failed ({e})")
            documents.extend(fallback_docs)
            # Safety net: the fallback parser catches per-file errors internally and can return fewer
            # (or zero) docs WITHOUT raising. Re-parse any routed file it didn't produce a doc for with
            # LiteParse so complex-routing never silently drops a document.
            produced = set()
            for d in fallback_docs:
                for _k in ("source", "file_path"):
                    _v = d.metadata.get(_k)
                    if _v:
                        produced.add(str(_v))
            missing = [f for f in route_files if str(f) not in produced]
            if missing:
                logger.warning(
                    f"{fallback_name} returned no document for {len(missing)} routed file(s) "
                    f"(parser error/empty); parsing them with LiteParse instead: {[str(m) for m in missing]}"
                )
                documents.extend(await self._liteparse_parse_files(missing, check_cancellation, original_metadata))

        return documents

    async def _liteparse_parse_files(self, file_paths: List[Union[str, Path]], check_cancellation,
                                     original_metadata: Dict[str, Dict]) -> List[Document]:
        """Actually parse the given files with LiteParse (no complexity/routing) → Documents.
        PDFs/office/images go through liteparse.parse() in an executor; plain text/markdown is read
        directly. Honors PARSER_FORMAT_FOR_EXTRACTION (auto/markdown/plaintext) for which text goes to
        extraction, and SAVE_PARSING_OUTPUT (writes markdown + plaintext + metadata to ./parsing_output/),
        matching Docling/LlamaParse. Produces the same Document metadata shape as the other parsers,
        including file_path (needed for the stable filesystem doc_id)."""
        documents: List[Document] = []
        loop = asyncio.get_event_loop()
        format_config = getattr(self.config, 'parser_format_for_extraction', 'auto') if self.config else 'auto'
        save_output = bool(getattr(self.config, 'save_parsing_output', False)) if self.config else False

        for file_path in file_paths:
            if check_cancellation():
                logger.info("LiteParse processing cancelled")
                break
            path_obj = Path(file_path)
            if not path_obj.exists():
                logger.warning(f"File does not exist: {file_path}")
                continue

            orig_meta = original_metadata.get(str(file_path), {})
            suffix = path_obj.suffix.lower()
            try:
                if suffix in ['.txt', '.md']:
                    logger.info(f"Reading text file directly (LiteParse targets rich docs): {file_path}")
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        raw = f.read()
                    # The file *is* the content; treat .md as markdown, .txt as plaintext.
                    markdown_content = raw if suffix == '.md' else ""
                    plaintext_content = raw
                    conversion = "direct"
                else:
                    logger.info(f"Parsing with LiteParse: {file_path}")
                    result = await loop.run_in_executor(None, self.liteparse.parse, str(file_path))
                    # LiteParse exposes per-page markdown (populated when output_format=markdown, our
                    # default) AND per-page text — build both so PARSER_FORMAT_FOR_EXTRACTION can choose
                    # and SAVE_PARSING_OUTPUT can write both.
                    md_parts = [p.markdown for p in result.pages if getattr(p, 'markdown', '')]
                    txt_parts = [p.text for p in result.pages if getattr(p, 'text', '')]
                    markdown_content = "\n\n".join(md_parts)
                    plaintext_content = "\n\n".join(txt_parts) or (result.text or "")
                    conversion = "liteparse"

                # --- choose extraction format (shared policy: Docling/LlamaParse/LiteParse) ---
                content, format_used, has_tables = self._select_extraction_content(
                    markdown_content, plaintext_content, format_config)
                logger.info(
                    f"Table detection [liteparse]: {path_obj.name} -> has_table={has_tables} "
                    f"(md={len(markdown_content)}, txt={len(plaintext_content)} chars); extraction={format_used}"
                )

                if not content.strip():
                    logger.warning(f"LiteParse produced no content for {file_path}")
                    continue

                # --- optional save-to-disk (./parsing_output/) ---
                if save_output:
                    self._save_liteparse_output(path_obj, str(file_path), markdown_content, plaintext_content, conversion)

                doc = Document(
                    text=content,
                    metadata={
                        **orig_meta,  # Include original metadata first (cloud file id, etc.)
                        "source": str(file_path),
                        "file_path": orig_meta.get("file_path") or str(file_path),
                        "conversion_method": conversion,
                        "file_type": path_obj.suffix,
                        "file_name": orig_meta.get("file_name") or path_obj.name,
                    },
                )
                documents.append(doc)
                logger.info(
                    f"LiteParse extracted {len(content)} chars from {file_path} "
                    f"({conversion}, {format_used}; md={len(markdown_content)}, txt={len(plaintext_content)})"
                )
            except Exception as e:
                logger.error(f"Error processing {file_path} with LiteParse: {e}")

        return documents

    def _save_liteparse_output(self, path_obj: Path, file_path_str: str,
                               markdown_content: str, plaintext_content: str, conversion: str):
        """Write LiteParse markdown + plaintext + metadata to ./parsing_output/ (SAVE_PARSING_OUTPUT).
        Mirrors the Docling/LlamaParse save layout ({name-with-ext}_liteparse_output.md/.txt + _metadata.json;
        the extension is kept in the base name so foo.pdf and foo.txt don't overwrite each other). Only
        non-empty outputs are written — e.g. a plain .txt has no markdown, so no 0-byte .md is created."""
        try:
            import json as _json
            output_dir = Path("./parsing_output") / "liteparse"
            output_dir.mkdir(parents=True, exist_ok=True)
            base_name = path_obj.name.replace('.', '_')  # include extension so e.g. foo.pdf / foo.txt don't collide
            meta_file = output_dir / f"{base_name}_liteparse_metadata.json"
            saved = []
            if markdown_content:
                md_file = output_dir / f"{base_name}_liteparse_output.md"
                with open(md_file, 'w', encoding='utf-8') as fh:
                    fh.write(markdown_content)
                saved.append(md_file.name)
            if plaintext_content:
                txt_file = output_dir / f"{base_name}_liteparse_output.txt"
                with open(txt_file, 'w', encoding='utf-8') as fh:
                    fh.write(plaintext_content)
                saved.append(txt_file.name)
            with open(meta_file, 'w', encoding='utf-8') as fh:
                _json.dump({
                    "source": file_path_str,
                    "parser": "liteparse",
                    "conversion_method": conversion,
                    "markdown_chars": len(markdown_content),
                    "plaintext_chars": len(plaintext_content),
                }, fh, indent=2)
            logger.info(f"Saved LiteParse output to: {', '.join(saved) if saved else '(metadata only)'}")
        except Exception as e:
            logger.warning(f"Failed to save LiteParse parsing output for {path_obj.name}: {e}")

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
        elif self.parser_type == "liteparse":
            return await self._process_with_liteparse(file_paths, _check_cancellation, {}, original_metadata)
    
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
                    
                    # Smart format selection (shared policy: Docling/LlamaParse/LiteParse)
                    format_config = getattr(self.config, 'parser_format_for_extraction', 'auto') if self.config else 'auto'
                    content_to_use, format_used, has_tables = self._select_extraction_content(
                        markdown_content, plain_text, format_config)
                    logger.info(
                        f"Table detection [docling]: {path_obj.name} -> has_table={has_tables} "
                        f"(md={len(markdown_content)}, txt={len(plain_text)} chars); extraction={format_used}"
                    )
                    
                    # Save parsing output if configured (works for both Docling and LlamaParse)
                    if self.config and getattr(self.config, 'save_parsing_output', False):
                        try:
                            output_dir = Path("./parsing_output") / "docling"
                            output_dir.mkdir(parents=True, exist_ok=True)
                            
                            # Create output filename
                            base_name = path_obj.name.replace('.', '_')  # include extension so e.g. foo.pdf / foo.txt don't collide
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
                                "format_used_for_processing": "markdown" if format_used.startswith("markdown") else "plaintext",
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
                    logger.debug(f"First 200 chars: {self._safe_log(content_to_use, 200)}...")
                    
                    # Get original metadata if available (from cloud sources)
                    orig_meta = original_metadata.get(str(file_path), {})
                    
                    # Create LlamaIndex Document - merge original metadata with new fields
                    doc = Document(
                        text=content_to_use,
                        metadata={
                            **orig_meta,  # Include original metadata first (contains file id, etc.)
                            "source": str(file_path),  # Then override with processing metadata
                            # Set file_path (used for the stable filesystem doc_id) — but keep the
                            # cloud source's own file_path (bucket/key etc.) when provided. Without
                            # this, flow-mode filesystem docs got a filename-only doc_id that didn't
                            # match the filesystem detector's full-path doc_id → broken sync.
                            "file_path": orig_meta.get("file_path") or str(file_path),
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
                    logger.debug(f"First 200 chars: {self._safe_log(content, 200)}...")
                    
                    # Get original metadata if available (from cloud sources)
                    orig_meta = original_metadata.get(str(file_path), {})
                    
                    # Create LlamaIndex Document - merge original metadata with new fields
                    doc = Document(
                        text=content,
                        metadata={
                            **orig_meta,  # Include original metadata first (contains file id, etc.)
                            "source": str(file_path),  # Then override with processing metadata
                            # See docling branch above — set file_path for the stable filesystem
                            # doc_id, preserving a cloud source's own file_path when provided.
                            "file_path": orig_meta.get("file_path") or str(file_path),
                            "conversion_method": "direct",
                            "file_type": path_obj.suffix,
                            "file_name": orig_meta.get("file_name") or path_obj.name  # Prefer original name
                        }
                    )

                    # Save parsing output if configured — consistency with the docling-extensions branch
                    # (previously text files produced no parsing_output). .md is markdown, .txt is plaintext;
                    # empty outputs are skipped so a .txt doesn't create a 0-byte markdown file.
                    if self.config and getattr(self.config, 'save_parsing_output', False):
                        try:
                            import json as _json
                            output_dir = Path("./parsing_output") / "docling"
                            output_dir.mkdir(parents=True, exist_ok=True)
                            base_name = path_obj.name.replace('.', '_')
                            md_text = content if path_obj.suffix.lower() == '.md' else ""
                            saved = []
                            if md_text:
                                mf = output_dir / f"{base_name}_docling_markdown.md"
                                with open(mf, 'w', encoding='utf-8') as f:
                                    f.write(md_text)
                                saved.append(mf.name)
                            if content:
                                pf = output_dir / f"{base_name}_docling_plaintext.txt"
                                with open(pf, 'w', encoding='utf-8') as f:
                                    f.write(content)
                                saved.append(pf.name)
                            with open(output_dir / f"{base_name}_docling_metadata.json", 'w', encoding='utf-8') as f:
                                _json.dump({
                                    "source": str(file_path),
                                    "file_type": path_obj.suffix,
                                    "file_name": path_obj.name,
                                    "conversion_method": "direct",
                                    "markdown_length": len(md_text),
                                    "plaintext_length": len(content),
                                }, f, indent=2, ensure_ascii=False)
                            logger.info(f"Saved Docling output (direct text) to: {', '.join(saved) if saved else '(metadata only)'}")
                        except Exception as _e:
                            logger.warning(f"Failed to save Docling parsing output for {path_obj.name}: {_e}")

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

                # --- Step 4: choose content format (shared policy: Docling/LlamaParse/LiteParse) ---
                if fast_tier:
                    # fast tier returns text only — no markdown available
                    content_to_use, format_used, has_tables = plaintext_content, "plaintext (fast tier - no markdown)", False
                else:
                    content_to_use, format_used, has_tables = self._select_extraction_content(
                        markdown_content, plaintext_content, format_config)
                logger.info(
                    f"Table detection [llamaparse]: {path_obj.name} -> has_table={has_tables} "
                    f"(md={len(markdown_content)}, txt={len(plaintext_content)} chars); extraction={format_used}"
                )

                # --- Step 5: optional save-to-disk ---
                if self.config and getattr(self.config, 'save_parsing_output', False):
                    try:
                        import json as _json
                        output_dir = Path("./parsing_output") / "llamaparse"
                        output_dir.mkdir(parents=True, exist_ok=True)

                        base_name = path_obj.name.replace('.', '_')  # include extension so e.g. foo.pdf / foo.txt don't collide
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
                        # Stable filesystem doc_id needs file_path; keep cloud's own when provided.
                        "file_path": orig_meta.get("file_path") or file_path_str,
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
            elif self.parser_type == "liteparse":
                documents = await self._process_with_liteparse(file_paths_to_process, check_cancellation, original_filenames, original_metadata)
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