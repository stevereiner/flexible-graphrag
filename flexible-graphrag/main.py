import os
import logging
import sys
from datetime import datetime

# Neutralise nest_asyncio.apply on Python 3.14+ before any imports that might trigger it.
# LlamaIndex (async_utils, elasticsearch store) calls nest_asyncio.apply() unconditionally;
# on 3.14 this breaks asyncio.Runner.close() → shutdown_default_executor().
if sys.version_info >= (3, 14):
    try:
        import nest_asyncio as _nest_asyncio_early
        _nest_asyncio_early.apply = lambda *a, **kw: None
    except ImportError:
        pass

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import asyncio
from pathlib import Path
import uvicorn
import shutil
from dotenv import load_dotenv
import importlib.metadata
import nest_asyncio
from config import Settings, DataSourceType
from backend import get_backend

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load .env before any Settings() so observability and ontology paths match the shell cwd.
load_dotenv()

# Initialize observability if enabled
try:
    from observability import setup_observability
    # Use Settings class for type-safe configuration with validation
    temp_settings = Settings()
    
    if temp_settings.enable_observability:
        # Note: observability_backend is already a string due to use_enum_values=True in Settings
        logger.info(f"Initializing observability (backend: {temp_settings.observability_backend})...")
        setup_observability(
            service_name=temp_settings.otel_service_name,
            otlp_endpoint=temp_settings.otel_exporter_otlp_endpoint,
            enable_instrumentation=temp_settings.enable_llama_index_instrumentation,
            service_version=temp_settings.otel_service_version,
            service_namespace=temp_settings.otel_service_namespace,
            backend=temp_settings.observability_backend  # Already a string, not .value needed
        )
        logger.info("Observability initialized successfully")
    else:
        logger.info("Observability disabled (ENABLE_OBSERVABILITY=false)")
except ImportError:
    logger.info("Observability dependencies not installed (optional feature)")
except Exception as e:
    logger.error(f"Failed to initialize observability: {e}")
    import traceback
    traceback.print_exc()

# Fix for async event loop issues with containers and LlamaIndex
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    # Docker/Linux environments - use default policy but ensure proper loop handling
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# Apply nest_asyncio to allow nested event loops (required for LlamaIndex in FastAPI)
# nest_asyncio is incompatible with Python 3.14+ — it patches the event loop in a way
# that breaks asyncio.current_task(), causing failures in aiohttp, asyncpg, etc.
if sys.version_info < (3, 14):
    nest_asyncio.apply()

# Ensure we have a proper event loop for Docker containers
# Note: Only create a new event loop if there isn't one already running.
# Do NOT call set_event_loop() unconditionally — on Python 3.14 this creates
# a mismatch with uvicorn's event loop causing asyncio.current_task() to return None.
try:
    asyncio.get_running_loop()
except RuntimeError:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


# ---------------------------------------------------------------------------
# Python 3.14 compatibility patches
# asyncio.current_task() returns None in certain contexts (lifespan startup,
# some task scheduling paths). Libraries that use asyncio.timeout() or aiohttp's
# TimerContext raise RuntimeError("Timeout ... should be used inside a task").
# Patch both to be no-ops when there is no current task.
# ---------------------------------------------------------------------------
def _apply_aiohttp_task_patches() -> None:
    """Patch aiohttp TimerContext / ceil_timeout for Python >= 3.12.

    aiohttp's TimerContext.__enter__ calls ``asyncio.current_task()`` and
    raises RuntimeError if it returns None.  On Python 3.12+ this can happen
    when an aiohttp-backed async client (e.g. Elasticsearch AsyncElasticsearch)
    was initialised in a sync context (e.g. during HybridSearchSystem.__init__)
    and its internal aiohttp session stores a stale loop reference.  The patches
    make the timeout a safe no-op when there is no current asyncio task.
    """
    from contextlib import asynccontextmanager

    try:
        import aiohttp.helpers as _aiohttp_helpers

        def _safe_timer_enter(self):
            # asyncio.current_task(loop=self._loop) in the stock __enter__ returns
            # None when self._loop is a stale loop (e.g. created in run_in_executor
            # or at startup before uvicorn's event loop).  In Python 3.13+,
            # current_task(loop=other_loop) always returns None even inside a task.
            # We call current_task() without the broken loop= arg and fully replace
            # the __enter__ logic so the original method is never invoked.
            task = asyncio.current_task()
            if task is None:
                return self  # no-op timeout when not inside a task
            if self._cancelled:
                raise asyncio.TimeoutError from None
            if sys.version_info >= (3, 11):
                self._cancelling = task.cancelling()
            self._tasks.append(task)
            return self

        _aiohttp_helpers.TimerContext.__enter__ = _safe_timer_enter

        _orig_ceil_timeout = _aiohttp_helpers.ceil_timeout

        @asynccontextmanager
        async def _safe_ceil_timeout(delay, ceil_threshold=5):
            if delay is None or delay <= 0 or asyncio.current_task() is None:
                yield
            else:
                async with _orig_ceil_timeout(delay, ceil_threshold):
                    yield

        _aiohttp_helpers.ceil_timeout = _safe_ceil_timeout

        try:
            import aiohttp.connector as _aiohttp_connector
            _aiohttp_connector.ceil_timeout = _safe_ceil_timeout
        except Exception:
            pass
    except Exception:
        pass


def _apply_python314_patches() -> None:
    if sys.version_info < (3, 14):
        return

    from contextlib import asynccontextmanager

    # Patch asyncpg.compat.timeout (used during connection pool creation)
    try:
        import asyncpg.compat as _asyncpg_compat
        _orig_asyncpg_timeout = _asyncpg_compat.timeout

        @asynccontextmanager
        async def _safe_asyncpg_timeout(delay):
            if delay is None or asyncio.current_task() is None:
                yield
            else:
                async with _orig_asyncpg_timeout(delay):
                    yield

        _asyncpg_compat.timeout = _safe_asyncpg_timeout
    except Exception:
        pass

    # Patch anyio.CancelScope.__enter__ / __exit__ — called by httpcore's AsyncShieldCancellation
    # during HTTP connection cleanup. anyio uses current_task() to track which task owns the scope;
    # when current_task() is None (executor threads), it tries to look up None in a
    # WeakValueDictionary and raises TypeError: cannot create weak reference to 'NoneType'.
    # Fix: make CancelScope.__enter__/__exit__ no-ops when there is no current task.
    try:
        from anyio._backends._asyncio import CancelScope as _AnyioCancelScope
        _orig_cancel_scope_enter = _AnyioCancelScope.__enter__
        _orig_cancel_scope_exit = _AnyioCancelScope.__exit__

        def _safe_cancel_scope_enter(self):
            if asyncio.current_task() is None:
                self._active = True
                self._no_task_noop = True
                return self
            self._no_task_noop = False
            return _orig_cancel_scope_enter(self)

        def _safe_cancel_scope_exit(self, exc_type, exc_val, exc_tb):
            if getattr(self, '_no_task_noop', False):
                self._active = False
                self._no_task_noop = False
                return False
            return _orig_cancel_scope_exit(self, exc_type, exc_val, exc_tb)

        _AnyioCancelScope.__enter__ = _safe_cancel_scope_enter
        _AnyioCancelScope.__exit__ = _safe_cancel_scope_exit
    except Exception:
        pass

    # Patch httpcore.AsyncShieldCancellation — used during HTTP connection cleanup.
    # It calls anyio.CancelScope(shield=True).__enter__() which calls current_task().
    # When current_task() is None (executor threads, lifespan), anyio tries to look up
    # None in a WeakValueDictionary and raises TypeError.
    # Fix: make AsyncShieldCancellation a no-op context manager when there is no current task.
    try:
        import httpcore._synchronization as _httpcore_sync

        class _SafeAsyncShieldCancellation:
            def __init__(self) -> None:
                self._active = asyncio.current_task() is not None
                if self._active:
                    self._orig = _httpcore_sync._orig_AsyncShieldCancellation()

            def __enter__(self):
                if self._active:
                    self._orig.__enter__()
                return self

            def __exit__(self, *args):
                if self._active:
                    return self._orig.__exit__(*args)
                return False

        # Save original so the wrapper above can instantiate it
        _httpcore_sync._orig_AsyncShieldCancellation = _httpcore_sync.AsyncShieldCancellation
        _httpcore_sync.AsyncShieldCancellation = _SafeAsyncShieldCancellation
    except Exception:
        pass

    # Patch sniffio.current_async_library — on Python 3.14, asyncio.current_task()
    # returns None in threads spawned from async context (e.g. openai's to_thread calls).
    # sniffio uses current_task() to detect asyncio, so it raises AsyncLibraryNotFoundError.
    # Fix: also return "asyncio" when there is a running event loop, even without a current task.
    try:
        import sniffio._impl as _sniffio_impl

        def _safe_current_async_library():
            # Fast path: context var or thread-local already set
            value = _sniffio_impl.thread_local.name
            if value is not None:
                return value
            value = _sniffio_impl.current_async_library_cvar.get()
            if value is not None:
                return value
            # asyncio sniff: current_task() OR a running event loop is enough
            if "asyncio" in sys.modules:
                try:
                    if asyncio.current_task() is not None:
                        return "asyncio"
                    # Python 3.14: current_task() may be None in threads — fall back to loop check
                    asyncio.get_running_loop()
                    return "asyncio"
                except RuntimeError:
                    pass
            raise _sniffio_impl.AsyncLibraryNotFoundError(
                "unknown async library, or not in async context"
            )

        _sniffio_impl.current_async_library = _safe_current_async_library
        # Also patch the top-level sniffio module attribute
        import sniffio as _sniffio
        _sniffio.current_async_library = _safe_current_async_library
    except Exception:
        pass

    # aiohttp TimerContext / ceil_timeout patching is handled by
    # _apply_aiohttp_task_patches() which runs for Python >= 3.12.
    # No need to duplicate it here.

    # Neutralise nest_asyncio.apply() on Python 3.14 — LlamaIndex's async_utils and
    # the elasticsearch vector store both call nest_asyncio.apply() unconditionally at
    # runtime.  On 3.14 this patches loop.run_until_complete() in a way that breaks
    # asyncio.Runner.close() → shutdown_default_executor(), which uses asyncio.timeout()
    # and requires a Task.  The patched version runs the coroutine without a Task,
    # causing RuntimeError("Timeout should be used inside a task").
    # Fix: replace nest_asyncio.apply with a no-op so every caller (including third-party
    # libraries) is silently ignored on 3.14+.
    try:
        import nest_asyncio as _nest_asyncio
        _nest_asyncio.apply = lambda *a, **kw: None
    except ImportError:
        pass

    # Patch asyncio.wait_for — on Python 3.14 it uses asyncio.timeout() internally,
    # which raises RuntimeError("Timeout should be used inside a task") when called
    # outside a Task (e.g. from async generators that run in executor threads or
    # during lifespan startup).  Wrap it so that when there is no current task and
    # the timeout expires we raise asyncio.TimeoutError as callers expect.
    try:
        _orig_wait_for = asyncio.wait_for

        async def _safe_wait_for(fut, timeout, **kwargs):
            if timeout is None or asyncio.current_task() is not None:
                return await _orig_wait_for(fut, timeout, **kwargs)
            # No current Task — use asyncio.wait() to implement a timeout without
            # asyncio.timeout(), which requires a Task on Python 3.14.
            task = asyncio.ensure_future(fut)
            done, pending = await asyncio.wait({task}, timeout=timeout)
            if pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                raise asyncio.TimeoutError()
            return task.result()

        asyncio.wait_for = _safe_wait_for
    except Exception:
        pass


_apply_python314_patches()
if sys.version_info >= (3, 12):
    _apply_aiohttp_task_patches()


# ---------------------------------------------------------------------------
# Weaviate / llama-index-vector-stores-weaviate compatibility patch
#
# weaviate-client >= 4.9 renamed _ContextManagerWrapper to _ContextManagerSync.
# llama-index-vector-stores-weaviate <= 1.6.0 still imports the old name, so
# ``import llama_index.vector_stores.weaviate`` fails at module load time.
# Inject the alias into the weaviate batch_wrapper module before the first
# import so the llama-index weaviate module finds it.
# ---------------------------------------------------------------------------
try:
    import weaviate.collections.batch.batch_wrapper as _wv_bw
    if not hasattr(_wv_bw, "_ContextManagerWrapper"):
        if hasattr(_wv_bw, "_ContextManagerSync"):
            _wv_bw._ContextManagerWrapper = _wv_bw._ContextManagerSync
        elif hasattr(_wv_bw, "_ContextManagerAsync"):
            _wv_bw._ContextManagerWrapper = _wv_bw._ContextManagerAsync
except Exception:
    pass

# On Python 3.14, asyncio.Runner propagates CancelledError out of run() after
# Ctrl-C even though the shutdown completed cleanly, producing an ugly traceback.
# Install an excepthook that suppresses it so the console stays clean on exit.
if sys.version_info >= (3, 14):
    _orig_excepthook = sys.excepthook

    def _clean_exit_excepthook(exc_type, exc_val, exc_tb):
        # asyncio.Runner on 3.14 raises CancelledError then converts it to
        # KeyboardInterrupt on clean Ctrl-C — suppress both at top level.
        if issubclass(exc_type, (asyncio.CancelledError, KeyboardInterrupt)):
            return
        _orig_excepthook(exc_type, exc_val, exc_tb)

    sys.excepthook = _clean_exit_excepthook

# Configure logging with both file and console output
log_filename = f'flexible-graphrag-api-{datetime.now().strftime("%Y%m%d-%H%M%S")}.log'

_log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)

# Force logging to work properly with uvicorn
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(_log_level)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(_log_level)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configure root logger (prevent duplicate handlers)
root_logger = logging.getLogger()
root_logger.setLevel(_log_level)

# Clear any existing handlers to prevent duplicates
root_logger.handlers.clear()

# Add our handlers
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Suppress verbose Azure SDK HTTP transport logging (request headers/responses every poll)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.storage.blob").setLevel(logging.WARNING)
logging.getLogger("azure.storage.blob.changefeed").setLevel(logging.WARNING)

# Suppress Neo4j driver connection-pool and I/O noise at DEBUG level
logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("neo4j.io").setLevel(logging.WARNING)
logging.getLogger("neo4j.pool").setLevel(logging.WARNING)

# Suppress aiohttp connector cleanup noise — "close.failed Event loop is closed" appears
# when the TCPConnector is GC'd after the event loop ends. The OpenAI client retries
# successfully; this is cosmetic cleanup-time chatter, not a real failure.
logging.getLogger("aiohttp.connector").setLevel(logging.ERROR)
logging.getLogger("aiohttp.client").setLevel(logging.WARNING)

# Suppress httpcore structured-logging noise at DEBUG level (close.failed, connect_tcp, etc.)
# These are transport-layer lifecycle events; failures here are retried by the OpenAI SDK.
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)

# Suppress "Encountered Exception" + RuntimeError('Event loop is closed') traceback that
# openai._base_client logs at DEBUG when the first cold connection hits a stale TLS socket.
# The SDK retries automatically (3 retries); this is pure noise at DEBUG log level.
logging.getLogger("openai._base_client").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.info(f"Starting application with log file: {log_filename}")

# Force flush
file_handler.flush()
console_handler.flush()

# Global references for incremental system
incremental_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup/shutdown lifecycle.
    Initialize incremental system at startup.
    """
    global incremental_manager
    
    # === STARTUP ===
    logger.info("Application startup...")

    # Suppress asyncio "Event loop is closed" stderr noise from httpcore/anyio TLS
    # socket cleanup. These occur when a TLS transport tries to schedule a callback
    # on an already-closed selector loop during connection teardown. The OpenAI SDK
    # retries automatically; these are harmless. Without this handler Python's default
    # asyncio exception handler prints the full traceback to stderr even at WARNING log
    # level, because it bypasses the logging system entirely.
    def _suppress_closed_loop_noise(loop, context):
        msg = context.get("message", "")
        exc = context.get("exception")
        if isinstance(exc, RuntimeError) and "Event loop is closed" in str(exc):
            return
        if "Event loop is closed" in msg:
            return
        loop.default_exception_handler(context)

    import asyncio as _asyncio
    _asyncio.get_event_loop().set_exception_handler(_suppress_closed_loop_noise)
    
    # Initialize backend (hybrid_system lazy-loaded)
    backend = get_backend()
    logger.info("Backend initialized")
    
    # Check if incremental updates enabled
    enable_incremental = os.getenv('ENABLE_INCREMENTAL_UPDATES', 'false').lower() == 'true'
    postgres_url = os.getenv('POSTGRES_INCREMENTAL_URL')
    
    if enable_incremental:
        if not postgres_url:
            logger.warning("WARNING: ENABLE_INCREMENTAL_UPDATES=true but POSTGRES_INCREMENTAL_URL not set")
            logger.warning("   Incremental updates disabled - set POSTGRES_INCREMENTAL_URL in .env")
        else:
            try:
                # Import incremental system
                from incremental_system import IncrementalSystemManager
                
                # Create singleton instance
                incremental_manager = IncrementalSystemManager.get_instance()
                
                # Initialize (reuses backend's indexes!)
                # Indexes are connected to existing data at startup via _initialize_indexes()
                # Engine can access them immediately for both search and incremental updates
                await incremental_manager.initialize(
                    postgres_url=postgres_url,
                    vector_index=backend.system.vector_index,  # Connected to existing vector data
                    graph_index=backend.system.graph_index,    # Connected to existing graph data
                    search_index=None,  # HybridSearchSystem doesn't expose search_index directly
                    doc_processor=backend.system.document_processor,  # Correct attribute name
                    app_config=backend.system.config,
                    hybrid_system=backend.system,  # Engine uses this for insert operations
                    backend=backend  # NEW: Pass backend for detector ADD/MODIFY processing
                )
                
                # Start background monitoring
                await incremental_manager.start_monitoring()
                
                logger.info("SUCCESS: Incremental updates enabled and monitoring started")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"ERROR: Failed to initialize incremental updates: {error_msg}")
                _db_missing = "does not exist" in error_msg
                _server_down = (
                    "refused" in error_msg.lower()
                    or "WinError" in error_msg
                    or "could not connect" in error_msg.lower()
                    or "connect call failed" in error_msg.lower()
                )
                if _db_missing:
                    logger.info("  The incremental updates database does not exist yet.")
                    logger.info("  Recreate the PostgreSQL container and volume so the init scripts run fresh:")
                    logger.info("    docker compose -p flexible-graphrag down postgres-pgvector pgadmin")
                    logger.info("    docker volume rm flexible-graphrag_postgres_data flexible-graphrag_pgadmin_data")
                    logger.info("    docker compose -p flexible-graphrag up -d postgres-pgvector pgadmin")
                elif _server_down:
                    logger.info("  PostgreSQL is not running. Start the containers:")
                    logger.info("    docker compose -p flexible-graphrag up -d postgres-pgvector pgadmin")
                else:
                    import traceback
                    traceback.print_exc()
    else:
        logger.info("INFO: Incremental updates disabled (set ENABLE_INCREMENTAL_UPDATES=true to enable)")
    
    yield
    
    # === SHUTDOWN ===
    logger.info("Shutting down application...")
    if incremental_manager:
        try:
            await incremental_manager.stop_monitoring()
            logger.info("SUCCESS: Incremental system stopped")
        except Exception as e:
            logger.error(f"Error stopping incremental system: {e}")
    
    logger.info("SUCCESS: Shutdown complete")

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Flexible GraphRAG API",
    description="API for processing documents with configurable hybrid search (vector, graph, full-text)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include RDF/Ontology router if enabled
try:
    from rdf.api_rdf_enhancements import router as rdf_router
    app.include_router(rdf_router)
    logger.info("RDF store API endpoints registered (/api/rdf/query/sparql, /api/rdf/export, /api/rdf/ontology)")
except Exception as e:
    logger.warning(f"RDF/Ontology module not available: {e}")


# Models
class CmisConfig(BaseModel):
    url: str
    username: str
    password: str
    folder_path: str

class NodeDetail(BaseModel):
    id: str
    name: str
    path: str
    isFile: bool
    isFolder: bool

class AlfrescoConfig(BaseModel):
    url: str
    username: str
    password: str
    path: str
    nodeIds: Optional[List[str]] = None  # Array of node IDs (UUIDs from REST API) for multi-select
    nodeDetails: Optional[List[NodeDetail]] = None  # Array of node details with metadata
    recursive: Optional[bool] = False  # Whether to recursively process subfolders (default: False)
    stomp_port: Optional[int] = None  # ActiveMQ STOMP port for real-time events (default: 61613, or set via ALFRESCO_STOMP_PORT env var)

class WebConfig(BaseModel):
    url: str

class WikipediaConfig(BaseModel):
    query: str
    language: Optional[str] = "en"
    max_docs: Optional[int] = 1

class YouTubeConfig(BaseModel):
    url: str
    chunk_size_seconds: Optional[int] = 60

class S3Config(BaseModel):
    bucket_name: str  # Modern approach - required bucket name
    prefix: Optional[str] = None
    access_key: str
    secret_key: str
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    region_name: Optional[str] = None  # Will use S3_REGION_NAME env var or S3Source default
    sqs_queue_url: Optional[str] = None  # Optional: SQS queue URL for event-based sync

class GCSConfig(BaseModel):
    bucket_name: str
    credentials: str
    prefix: Optional[str] = None
    pubsub_subscription: Optional[str] = None  # Optional: Pub/Sub subscription for event-based sync

class AzureBlobConfig(BaseModel):
    container_name: str
    account_url: str
    blob: Optional[str] = None  # renamed from blob_name to match LlamaCloud
    prefix: Optional[str] = None
    account_name: str
    account_key: str

class OneDriveConfig(BaseModel):
    user_principal_name: str  # Required field from LlamaCloud
    client_id: str
    client_secret: str
    tenant_id: str
    folder_path: Optional[str] = None
    folder_id: Optional[str] = None
    file_ids: Optional[List[str]] = []

class SharePointConfig(BaseModel):
    client_id: str
    client_secret: str
    tenant_id: str
    site_name: str  # Changed from site_url to site_name (LlamaCloud compatible)
    site_id: Optional[str] = None  # Optional: for Sites.Selected permission
    folder_path: Optional[str] = None
    folder_id: Optional[str] = None  # Changed from document_library to folder_id

class BoxConfig(BaseModel):
    folder_id: Optional[str] = None  # UI sends this - will be mapped to box_folder_id
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    developer_token: Optional[str] = None  # UI sends this - will be mapped to access_token
    enterprise_id: Optional[str] = None  # For enterprise accounts with CCG
    user_id: Optional[str] = None  # For user-specific access with CCG
    box_folder_id: Optional[str] = "0"
    box_file_ids: Optional[List[str]] = []
    access_token: Optional[str] = None

class GoogleDriveConfig(BaseModel):
    folder_id: Optional[str] = None
    file_ids: Optional[List[str]] = []
    query: Optional[str] = ""
    credentials: Optional[str] = None
    credentials_path: Optional[str] = None
    token_path: Optional[str] = None

class IngestRequest(BaseModel):
    paths: Optional[List[str]] = None  # overrides config
    data_source: Optional[str] = None  # filesystem, cmis, alfresco, web, wikipedia, youtube, s3, gcs, azure_blob, onedrive, sharepoint, box, google_drive
    skip_graph: Optional[bool] = False  # Per-ingest flag to skip knowledge graph step (doesn't persist)
    enable_sync: Optional[bool] = False  # Enable incremental sync monitoring for this datasource
    cmis_config: Optional[CmisConfig] = None
    alfresco_config: Optional[AlfrescoConfig] = None
    web_config: Optional[WebConfig] = None
    wikipedia_config: Optional[WikipediaConfig] = None
    youtube_config: Optional[YouTubeConfig] = None
    s3_config: Optional[S3Config] = None
    gcs_config: Optional[GCSConfig] = None
    azure_blob_config: Optional[AzureBlobConfig] = None
    onedrive_config: Optional[OneDriveConfig] = None
    sharepoint_config: Optional[SharePointConfig] = None
    box_config: Optional[BoxConfig] = None
    google_drive_config: Optional[GoogleDriveConfig] = None

class QueryRequest(BaseModel):
    query: str
    top_k: int = 10
    query_type: Optional[str] = "hybrid"  # hybrid, qa

class TextIngestRequest(BaseModel):
    content: str
    source_name: Optional[str] = "sample-test"
    skip_graph: Optional[bool] = False

class Document(BaseModel):
    id: str
    name: str
    content: str

# Initialize system
settings = Settings()
backend_instance = get_backend()

# Initialize RDF/Ontology system if enabled
try:
    if settings.use_ontology or settings.rdf_enabled_stores:
        from rdf.api_rdf_enhancements import initialize_rdf_system
        
        # Get property graph index from backend if available
        property_graph_index = getattr(backend_instance, 'index', None)
        
        initialize_rdf_system(settings, property_graph_index)
        logger.info("RDF/Ontology system initialized")
except Exception as e:
    logger.warning(f"Failed to initialize RDF/Ontology system: {e}")

# API Endpoints
@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
async def _create_document_states_after_ingestion(processing_id: str, config_id: str, paths: List[str], data_source: str = "filesystem"):
    """
    Background task to create document_state records after ingestion completes.
    Delegates to PostIngestionStateManager for cleaner code organization.
    """
    from post_ingestion_state import PostIngestionStateManager
    
    state_manager = PostIngestionStateManager(incremental_manager.state_manager.postgres_url)
    await state_manager.create_document_states_after_ingestion(
        processing_id, config_id, paths, data_source
    )


@app.post("/api/ingest")
async def ingest(request: IngestRequest):
    try:
        logger.info(f"Starting async document ingestion: {request}")
        logger.info(f"Data source: {request.data_source}, Paths: {request.paths}")
        
        data_source = request.data_source or str(settings.data_source)
        paths = request.paths
        
        # Prepare additional kwargs for data source configs
        kwargs = {}
        
        # Pass skip_graph flag if set
        if request.skip_graph:
            kwargs['skip_graph'] = request.skip_graph
            logger.info(f"Per-ingest skip_graph flag set to: {request.skip_graph}")
        
        if request.cmis_config:
            kwargs['cmis_config'] = request.cmis_config.dict()
        if request.alfresco_config:
            kwargs['alfresco_config'] = request.alfresco_config.dict()
        if request.web_config:
            kwargs['web_config'] = request.web_config.dict()
        if request.wikipedia_config:
            kwargs['wikipedia_config'] = request.wikipedia_config.dict()
        if request.youtube_config:
            kwargs['youtube_config'] = request.youtube_config.dict()
        if request.s3_config:
            kwargs['s3_config'] = request.s3_config.dict()
        if request.gcs_config:
            kwargs['gcs_config'] = request.gcs_config.dict()
        if request.azure_blob_config:
            kwargs['azure_blob_config'] = request.azure_blob_config.dict()
        if request.onedrive_config:
            kwargs['onedrive_config'] = request.onedrive_config.dict()
        if request.sharepoint_config:
            kwargs['sharepoint_config'] = request.sharepoint_config.dict()
        if request.box_config:
            box_dict = request.box_config.dict()
            # Map UI parameter names to BoxSource expected names
            if 'folder_id' in box_dict and box_dict['folder_id']:
                box_dict['box_folder_id'] = box_dict['folder_id']
                del box_dict['folder_id']  # Remove the UI parameter name
            if 'developer_token' in box_dict and box_dict['developer_token']:
                box_dict['access_token'] = box_dict['developer_token']
                del box_dict['developer_token']  # Remove the UI parameter name
            kwargs['box_config'] = box_dict
        if request.google_drive_config:
            kwargs['google_drive_config'] = request.google_drive_config.dict()
        
        # Generate config_id BEFORE ingestion if sync enabled.
        # IMPORTANT: config_id must be STABLE across restarts — it is embedded in
        # every doc's ref_doc_id and used by delete_doc() to find RDF triples.
        # Use uuid5 (name-based) derived from the datasource identity so the same
        # datasource always produces the same config_id regardless of restarts.
        config_id = None
        if request.enable_sync:
            import uuid as _uuid_mod
            _DS_NAMESPACE = _uuid_mod.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace
            # Build a stable identity string from datasource type + connection identity
            _identity_parts = [data_source]
            if data_source == "alfresco" and request.alfresco_config:
                ac = request.alfresco_config
                _identity_parts += [ac.url or "", ac.username or "", ac.path or ""]
            elif data_source == "filesystem":
                _identity_parts += sorted(paths or [])
            elif data_source == "s3" and request.s3_config:
                sc = request.s3_config
                _identity_parts += [sc.bucket_name or "", sc.prefix or ""]
            elif data_source == "azure_blob" and request.azure_blob_config:
                ab = request.azure_blob_config
                _identity_parts += [ab.connection_string or "", ab.container_name or ""]
            elif data_source == "gcs" and request.gcs_config:
                gc = request.gcs_config
                _identity_parts += [gc.bucket_name or "", gc.prefix or ""]
            elif data_source == "onedrive" and request.onedrive_config:
                od = request.onedrive_config
                _identity_parts += [od.user_principal_name or ""]
            elif data_source == "sharepoint" and request.sharepoint_config:
                sp = request.sharepoint_config
                _identity_parts += [sp.site_name or "", sp.site_url or ""]
            elif data_source == "box" and request.box_config:
                bx = request.box_config
                _identity_parts += [bx.folder_id or ""]
            elif data_source == "google_drive" and request.google_drive_config:
                gd = request.google_drive_config
                _identity_parts += [gd.folder_id or ""]
            elif data_source == "cmis" and request.cmis_config:
                cm = request.cmis_config
                _identity_parts += [cm.url or "", cm.repository_id or "", cm.path or ""]
            _identity_str = "|".join(_identity_parts)
            config_id = str(_uuid_mod.uuid5(_DS_NAMESPACE, _identity_str))
            kwargs['config_id'] = config_id
            logger.info(f"Stable config_id for sync ({data_source}): {config_id}")
        
        result = await backend_instance.ingest_documents(data_source=data_source, paths=paths, **kwargs)
        
        # If enable_sync is True and incremental system is initialized, add datasource for monitoring
        if request.enable_sync and incremental_manager and incremental_manager.is_initialized():
            try:
                import time
                
                # Determine source path based on data source type
                source_path = None
                connection_params = {}
                
                if data_source == "filesystem":
                    # Check if paths are full paths (MCP/local) or just filenames (file upload UI)
                    if paths and os.path.isabs(paths[0]):
                        # MCP or local filesystem path - monitor the actual paths
                        connection_params = {'paths': paths}
                        source_path = paths[0] if len(paths) == 1 else os.path.commonpath(paths)
                    else:
                        # File uploads - monitor the uploads directory
                        uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
                        connection_params = {'paths': [uploads_dir]}
                        source_path = uploads_dir
                    
                elif data_source == "s3" and request.s3_config:
                    connection_params = request.s3_config.dict(exclude_none=True)
                    # Ensure region_name is set - use env var or default to us-east-1
                    if not connection_params.get('region_name'):
                        connection_params['region_name'] = os.getenv('S3_REGION_NAME', 'us-east-1')
                        logger.info(f"Set S3 region_name to: {connection_params['region_name']}")
                    source_path = f"s3://{connection_params.get('bucket_name', 'unknown')}"
                    
                elif data_source == "alfresco" and request.alfresco_config:
                    connection_params = request.alfresco_config.dict(exclude_none=True)
                    source_path = connection_params.get('path', '/unknown')
                    # Add STOMP port if configured in environment and not already in params
                    if 'stomp_port' not in connection_params:
                        stomp_port = os.getenv("ALFRESCO_STOMP_PORT")
                        if stomp_port:
                            connection_params["stomp_port"] = int(stomp_port)
                            logger.info(f"Added ALFRESCO_STOMP_PORT={stomp_port} to datasource config")
                    
                elif data_source == "google_drive" and request.google_drive_config:
                    connection_params = request.google_drive_config.dict(exclude_none=True)
                    source_path = f"google_drive://{connection_params.get('folder_id', 'root')}"
                    
                elif data_source == "gcs" and request.gcs_config:
                    connection_params = request.gcs_config.dict(exclude_none=True)
                    source_path = f"gs://{connection_params.get('bucket_name', 'unknown')}"
                    
                elif data_source == "azure_blob" and request.azure_blob_config:
                    connection_params = request.azure_blob_config.dict(exclude_none=True)
                    source_path = f"azure://{connection_params.get('container_name', 'unknown')}"
                    
                elif data_source == "box" and request.box_config:
                    connection_params = request.box_config.dict(exclude_none=True)
                    source_path = f"box://{connection_params.get('folder_id', '0')}"
                    
                elif data_source == "onedrive" and request.onedrive_config:
                    connection_params = request.onedrive_config.dict(exclude_none=True)
                    source_path = f"onedrive://{connection_params.get('user_principal_name', 'unknown')}"
                    
                elif data_source == "sharepoint" and request.sharepoint_config:
                    connection_params = request.sharepoint_config.dict(exclude_none=True)
                    source_path = f"sharepoint://{connection_params.get('site_name', 'unknown')}"
                    
                # Add datasource for incremental sync
                if connection_params and config_id:
                    # Use the config_id we already generated (for stable doc_id)
                    await incremental_manager.add_datasource_for_sync(
                        source_type=data_source,
                        source_name=f"{data_source}_{int(time.time())}",
                        connection_params=connection_params,
                        config_id=config_id,  # Pass our pre-generated config_id
                        skip_graph=request.skip_graph  # Pass skip_graph flag
                    )
                    
                    logger.info(f"SUCCESS: Enabled incremental sync for {data_source}: {config_id}, skip_graph={request.skip_graph}")
                    result['sync_enabled'] = True
                    result['config_id'] = config_id
                    
                    # CRITICAL: Create document_state records SYNCHRONOUSLY (not background task)
                    # This ensures records exist BEFORE periodic refresh runs, preventing race condition duplicates
                    # We must await this to block periodic refresh from processing these files
                    processing_id = result['processing_id']
                    logger.info(f"Creating document_state records synchronously for {data_source} to prevent duplicates...")
                    await _create_document_states_after_ingestion(
                        processing_id=processing_id,
                        config_id=config_id,  # Same config_id used throughout
                        paths=paths or [],
                        data_source=data_source  # Pass data source type for proper handling
                    )
                    logger.info(f"Document_state records created synchronously for {data_source}")
                else:
                    logger.warning(f"Could not enable sync for {data_source}: missing configuration")
                    result['sync_enabled'] = False
                    
            except Exception as e:
                logger.error(f"Error enabling incremental sync: {e}")
                import traceback
                traceback.print_exc()
                result['sync_enabled'] = False
        else:
            result['sync_enabled'] = False
        
        logger.info(f"Document ingestion started with ID: {result['processing_id']}")
        return result
            
    except Exception as e:
        logger.error(f"Error starting document ingestion: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def cleanup_uploads(keep_recent_files: int = 0):
    """Clean up uploaded files, optionally keeping most recent files"""
    try:
        upload_dir = Path("./uploads")
        if not upload_dir.exists():
            return
        
        # Get all files sorted by modification time (newest first)
        files = sorted(upload_dir.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Remove files beyond the keep_recent_files limit
        for file_path in files[keep_recent_files:]:
            if file_path.is_file():
                file_path.unlink()
                logger.info(f"Cleaned up uploaded file: {file_path.name}")
                
        logger.info(f"Upload cleanup completed - kept {min(len(files), keep_recent_files)} recent files")
    except Exception as e:
        logger.warning(f"Error during upload cleanup: {str(e)}")

@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload files and store them in upload directory for processing"""
    try:
        # Create upload directory if it doesn't exist
        upload_dir = Path("./uploads")
        upload_dir.mkdir(exist_ok=True)
        
        uploaded_files = []
        skipped_files = []
        
        # File size limit (100MB per file)
        MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB in bytes
        
        for file in files:
            # Validate file type (basic validation)
            if not file.filename:
                continue
            
            # Read file content to check size
            content = await file.read()
            
            # Check file size
            if len(content) > MAX_FILE_SIZE:
                skipped_files.append({
                    "filename": file.filename,
                    "reason": f"File too large ({len(content) / 1024 / 1024:.1f}MB > 100MB)"
                })
                continue
                
            # Check if file type is supported
            supported_extensions = {'.pdf', '.docx', '.xlsx', '.pptx', '.txt', '.md', '.html', '.csv', '.png', '.jpg', '.jpeg'}
            file_extension = Path(file.filename).suffix.lower()
            
            if file_extension not in supported_extensions:
                skipped_files.append({
                    "filename": file.filename,
                    "reason": f"Unsupported file type: {file_extension}"
                })
                continue
            
            # Save file to upload directory (overwrite if exists)
            file_path = upload_dir / file.filename
            
            # Write file content (content already read for size validation)
            # This will overwrite existing files with the same name
            with open(file_path, "wb") as buffer:
                buffer.write(content)
            
            uploaded_files.append({
                "filename": file.filename,
                "saved_as": file_path.name,  # Now always matches original filename
                "path": str(file_path),
                "size": len(content)
            })
            
            logger.info(f"Uploaded file: {file.filename} -> {file_path}")
        
        response_message = f"Successfully uploaded {len(uploaded_files)} files"
        if skipped_files:
            response_message += f", skipped {len(skipped_files)} files"
        
        return {
            "success": True,
            "message": response_message,
            "files": uploaded_files,
            "skipped": skipped_files
        }
        
    except Exception as e:
        logger.error(f"Error uploading files: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def search(request: QueryRequest):
    try:
        logger.info(f"Processing {request.query_type} query: {request.query}")
        
        if request.query_type == "qa":
            # Q&A query - return answer
            result = await backend_instance.qa_query(request.query)
            if result["success"]:
                logger.info("Q&A query completed successfully")
                return {"success": True, "answer": result["answer"]}
            else:
                raise HTTPException(500, result["error"])
        else:
            # Hybrid search - return results
            result = await backend_instance.search_documents(request.query, request.top_k)
            if result["success"]:
                logger.info("Hybrid search completed successfully")
                return {"success": True, "results": result["results"]}
            else:
                raise HTTPException(500, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query")
async def query_graph(request: QueryRequest):
    try:
        logger.info(f"Processing query: {request.query}")
        result = await backend_instance.query_documents(request.query, request.top_k)
        
        if result["success"]:
            logger.info("Query processing completed successfully")
            return {"status": "success", "answer": result["answer"]}
        else:
            raise HTTPException(500, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying system: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
async def get_status():
    try:
        logger.info("Fetching system status")
        result = backend_instance.get_system_status()
        
        if result["success"]:
            logger.info("Status fetched successfully")
            return {"status": "success", "system_status": result["status"]}
        else:
            raise HTTPException(500, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test-sample")
async def test_sample_default(request: TextIngestRequest = None):
    """Test endpoint with configurable sample text using async processing."""
    try:
        content = settings.sample_text
        source_name = "sample-test"
        skip_graph = request.skip_graph if request else False
        
        logger.info("Starting async sample text processing")
        result = await backend_instance.ingest_text(content=content, source_name=source_name, skip_graph=skip_graph)
        
        # Return the async processing response (same format as ingest-text)
        logger.info(f"Sample text processing started with ID: {result['processing_id']}")
        return result
    except Exception as e:
        logger.error(f"Error starting sample text processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest-text")
async def ingest_custom_text(request: TextIngestRequest):
    """Start async text ingestion and return processing ID."""
    try:
        logger.info(f"Starting async text ingestion: source='{request.source_name}'")
        result = await backend_instance.ingest_text(content=request.content, source_name=request.source_name, skip_graph=request.skip_graph)
        
        logger.info(f"Text ingestion started with ID: {result['processing_id']}")
        return result
    except Exception as e:
        logger.error(f"Error starting text ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/processing-status/{processing_id}")
async def get_processing_status(processing_id: str):
    """Get processing status by ID."""
    try:
        logger.info(f"Checking processing status for ID: {processing_id}")
        result = backend_instance.get_processing_status(processing_id)
        
        if result["success"]:
            logger.info(f"Status retrieved for {processing_id}: {result['processing']['status']}")
            return result["processing"]
        else:
            raise HTTPException(404, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting processing status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cancel-processing/{processing_id}")
async def cancel_processing(processing_id: str):
    """Cancel processing by ID."""
    try:
        logger.info(f"Cancelling processing for ID: {processing_id}")
        result = backend_instance.cancel_processing(processing_id)
        
        if result["success"]:
            logger.info(f"Processing {processing_id} cancelled successfully")
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(400, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cleanup-uploads")
async def cleanup_uploads_endpoint(keep_recent: int = 0):
    """Clean up uploaded files, optionally keeping most recent files"""
    try:
        cleanup_uploads(keep_recent_files=keep_recent)
        return {
            "success": True,
            "message": f"Upload cleanup completed - kept {keep_recent} recent files"
        }
    except Exception as e:
        logger.error(f"Error during upload cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/processing-events/{processing_id}")
async def processing_events(processing_id: str):
    """Server-Sent Events for real-time processing updates (UI clients only)."""
    from fastapi.responses import StreamingResponse
    import json
    import time
    
    def event_stream():
        while True:
            result = backend_instance.get_processing_status(processing_id)
            if result["success"]:
                status_data = result["processing"]
                yield f"data: {json.dumps(status_data)}\n\n"
                
                # Stop streaming if completed or failed
                if status_data["status"] in ["completed", "failed"]:
                    break
            else:
                yield f"data: {json.dumps({'error': result['error']})}\n\n"
                break
                
            time.sleep(2)  # Poll every 2 seconds
    
    return StreamingResponse(
        event_stream(), 
        media_type="text/plain",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/api/info")
async def get_api_info():
    """Get API information and available endpoints"""
    return {
        "name": "Flexible GraphRAG API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "ingest": "/api/ingest",
            "search": "/api/search", 
            "query": "/api/query",
            "status": "/api/status",
            "test_sample": "/api/test-sample",
            "python_info": "/api/python-info",
            "graph": "/api/graph"
        },
        "frontends": {
            "angular": "/angular",
            "react": "/react", 
            "vue": "/vue"
        },
        "mcp_server": "Available as separate fastmcp-server.py"
    }

@app.get("/api/graph")
async def get_graph_data(limit: int = 50):
    """Return graph database status and node/relationship counts where supported.

    Node + relationship counts are currently implemented for Neo4j (via Cypher)
    and for LC-backed graph stores that expose a ``query()`` method.  Other stores
    return a status/dashboard URL without counts.
    """
    try:
        if not hasattr(backend_instance, '_system') or backend_instance._system is None:
            return {"error": "System not initialized - please ingest documents first"}

        system = backend_instance.system
        if not hasattr(system, 'graph_store') or system.graph_store is None:
            # LC-only path: pg_adapter may hold the graph store
            if hasattr(system, 'pg_adapter') and system.pg_adapter is not None:
                graph_store = None
                lc_graph = getattr(system.pg_adapter, 'lc_graph', None)
            else:
                return {"error": "Graph database not configured"}
        else:
            graph_store = system.graph_store
            lc_graph = None

        graph_store_type = type(graph_store).__name__ if graph_store else "LC"
        pg_adapter = getattr(system, 'pg_adapter', None)

        # ── Neo4j LI store: run count Cypher directly via the driver ─────────
        if graph_store_type == "Neo4jPropertyGraphStore":
            counts: dict = {}
            try:
                driver = getattr(graph_store, '_driver', None)
                if driver is None:
                    # some versions expose it differently
                    driver = getattr(graph_store, 'driver', None)
                if driver:
                    with driver.session() as s:
                        node_res = s.run("MATCH (n) WHERE NOT n:__Entity__ OR n.text IS NOT NULL RETURN count(n) AS n").single()
                        entity_res = s.run("MATCH (n:__Entity__) RETURN count(n) AS n").single()
                        rel_res = s.run("MATCH ()-[r]->() RETURN count(r) AS n").single()
                        counts = {
                            "nodes": int(node_res["n"]) if node_res else None,
                            "entities": int(entity_res["n"]) if entity_res else None,
                            "relationships": int(rel_res["n"]) if rel_res else None,
                        }
            except Exception as count_err:
                counts = {"count_error": str(count_err)}
            return {
                "database": "neo4j",
                "store_type": graph_store_type,
                "status": "configured",
                "dashboard_url": "http://localhost:7474",
                **counts,
            }

        # ── LC pg_adapter: use lc_graph.query() if available ─────────────────
        if pg_adapter is not None:
            try:
                lc_g = lc_graph or (pg_adapter.get_lc_graph() if hasattr(pg_adapter, 'get_lc_graph') else None)
                if lc_g is not None and hasattr(lc_g, 'query'):
                    db_type = str(settings.pg_graph_db).lower()
                    counts = {}
                    if db_type == "neo4j":
                        r_n = lc_g.query("MATCH (n) RETURN count(n) AS n")
                        r_r = lc_g.query("MATCH ()-[r]->() RETURN count(r) AS n")
                        counts = {
                            "nodes": r_n[0]["n"] if r_n else None,
                            "relationships": r_r[0]["n"] if r_r else None,
                        }
                    return {
                        "database": db_type,
                        "store_type": graph_store_type,
                        "status": "configured",
                        **counts,
                    }
            except Exception as lc_err:
                logger.debug("get_graph_data: LC query failed: %s", lc_err)

        if "Ladybug" in graph_store_type:
            return {
                "database": "ladybug",
                "store_type": graph_store_type,
                "status": "configured",
                "dashboard_url": "http://localhost:7003",
                "message": "Use Ladybug Explorer for graph visualization.",
            }

        return {
            "database": str(settings.pg_graph_db),
            "store_type": graph_store_type,
            "status": "configured",
            "message": f"Count queries not yet implemented for {graph_store_type}; use that database's dashboard.",
        }

    except Exception as e:
        return {"error": f"Error fetching graph data: {str(e)}"}


class GraphQueryRequest(BaseModel):
    query: str
    language: Optional[str] = None  # cypher | sparql | aql | surql | gremlin | gsql | opencypher
    params: Optional[Dict[str, Any]] = None


@app.post("/api/graph/query")
async def graph_query(request: GraphQueryRequest):
    """Execute a native graph query against the configured store.

    Routes through the LC adapter's ``lc_graph.query()`` so the correct query
    language is used for every store:
      - Neo4j / Memgraph / FalkorDB / ArcadeDB / Nebula / Apache AGE → Cypher
      - ArangoDB → AQL
      - SurrealDB → SurrealQL
      - HugeGraph → openCypher (via Cypher endpoint)
      - TigerGraph → GSQL
      - Cosmos Gremlin → Gremlin
      - Neptune / Neptune Analytics → openCypher
      - Google Spanner → Spanner Graph Query Language (GQL)
      - Ladybug → Cypher

    When no LC adapter is available but an LI PropertyGraphStore is configured,
    falls back to ``structured_query()`` on that store.

    For RDF-only deployments, falls back to the SPARQL path via UnifiedQueryEngine
    (same backend as ``/api/rdf/query/sparql``).

    Returns:
        ``{"results": [...], "backend": "<db>", "language": "<lang>", "row_count": N}``
    """
    try:
        system = backend_instance.system if hasattr(backend_instance, 'system') else None
        if system is None:
            return {"error": "System not initialized"}

        pg_db = str(settings.pg_graph_db).lower()
        rdf_db = str(settings.rdf_graph_db).lower() if hasattr(settings, 'rdf_graph_db') else "none"
        lang = (request.language or "").lower()
        params = request.params or {}

        # ── SPARQL short-circuit: when caller explicitly requests SPARQL and an
        # RDF store is configured, route straight to the SPARQL engine.
        # Without this, the PG-store paths below would try to run SPARQL against
        # Neo4j / Cypher stores and raise a CypherSyntaxError.
        if lang == "sparql" and rdf_db not in ("none", ""):
            from rdf.api_rdf_enhancements import unified_query_engine
            from rdf.unified_query_engine import QueryType
            if unified_query_engine is not None:
                result = unified_query_engine.query(
                    query_text=request.query,
                    query_type=QueryType.SPARQL,
                )
                return {
                    "results": result.formatted_results,
                    "row_count": len(result.formatted_results),
                    "backend": rdf_db,
                    "language": "sparql",
                }

        # ── LC adapter path: covers all 15 PG stores ──────────────────────────
        pg_adapter = getattr(system, 'pg_adapter', None)
        if pg_adapter is not None:
            lc_graph = None
            if hasattr(pg_adapter, 'get_lc_graph'):
                try:
                    lc_graph = pg_adapter.get_lc_graph()
                except Exception:
                    pass
            if lc_graph is None:
                lc_graph = getattr(pg_adapter, 'lc_graph', None)

            if lc_graph is not None and hasattr(lc_graph, 'query'):
                import inspect as _inspect, functools as _functools
                _q_method = lc_graph.query
                if _inspect.iscoroutinefunction(_q_method):
                    # Async query method (e.g. SurrealDB) — await directly
                    try:
                        raw = await _q_method(request.query, **({"params": params} if params else {}))
                    except TypeError:
                        raw = await _q_method(request.query)
                    except ValueError as _ve:
                        # SurrealDB raises ValueError for non-list results (e.g. INFO FOR DB)
                        raw = [{"result": str(_ve)}]
                else:
                    # Sync query method — run in a thread to avoid blocking the event loop.
                    # Many sync graph clients (gremlinpython, pyTigerGraph, etc.) use
                    # blocking I/O or call asyncio.run() internally, which raises
                    # "Cannot run the event loop while another loop is running" when called
                    # directly from an async FastAPI handler.
                    _qfn = _functools.partial(_q_method, request.query, **({"params": params} if params else {}))
                    try:
                        raw = await asyncio.to_thread(_qfn)
                    except TypeError:
                        raw = await asyncio.to_thread(_q_method, request.query)
                    except ValueError as _ve:
                        # SurrealDB (sync) raises ValueError for non-list results
                        raw = [{"result": str(_ve)}]
                # Normalise: some stores return list, some return dict, some None
                if raw is None:
                    raw = []
                elif isinstance(raw, dict):
                    raw = [raw]
                elif not isinstance(raw, list):
                    raw = [{"result": str(raw)}]
                return {
                    "results": raw,
                    "row_count": len(raw),
                    "backend": pg_db,
                    "language": lang or _infer_language(pg_db),
                }

        # ── LI PropertyGraphStore fallback (Neo4j LI, ArcadeDB LI, Spanner LI, etc.) ─────
        graph_store = getattr(system, 'graph_store', None)
        if graph_store is not None and hasattr(graph_store, 'structured_query'):
            import functools as _functools
            _sq_fn = _functools.partial(
                graph_store.structured_query, request.query, param_map=params
            )
            raw = await asyncio.to_thread(_sq_fn)
            if raw is None:
                raw = []
            return {
                "results": raw if isinstance(raw, list) else [raw],
                "row_count": len(raw) if isinstance(raw, list) else 1,
                "backend": pg_db,
                "language": lang or _infer_language(pg_db),
                "note": "LI structured_query path",
            }

        # ── RDF SPARQL fallback ────────────────────────────────────────────────
        if rdf_db not in ("none", ""):
            # Forward to /api/rdf/query/sparql logic (reuse unified_query_engine)
            from rdf.api_rdf_enhancements import unified_query_engine
            from rdf.unified_query_engine import QueryType
            if unified_query_engine is not None:
                result = unified_query_engine.query(
                    query_text=request.query,
                    query_type=QueryType.SPARQL,
                )
                return {
                    "results": result.formatted_results,
                    "row_count": len(result.formatted_results),
                    "backend": rdf_db,
                    "language": "sparql",
                }

        return {"error": "No graph store configured (PG_GRAPH_DB=none and RDF_GRAPH_DB=none)"}

    except Exception as e:
        logger.exception("graph_query error")
        return {"error": str(e)}


def _infer_language(db_type: str) -> str:
    """Map DB type to its native query language name."""
    _MAP = {
        "neo4j": "cypher", "memgraph": "cypher", "falkordb": "cypher",
        "arcadedb": "opencypher", "nebula": "cypher", "apache_age": "cypher",
        "ladybug": "cypher", "hugegraph": "cypher",
        "arangodb": "aql",
        "surrealdb": "surql",
        "cosmos_gremlin": "gremlin",
        "tigergraph": "gsql",
        "neptune": "opencypher", "neptune_analytics": "opencypher",
        "spanner": "gql",
        "fuseki": "sparql", "graphdb": "sparql", "oxigraph": "sparql", "neptune_rdf": "sparql",
    }
    return _MAP.get(db_type, "unknown")


@app.get("/api/python-info")
async def python_info():
    """Return information about the Python interpreter being used."""
    # More reliable way to check if running in a virtual environment
    in_virtualenv = False
    venv_path = os.environ.get("VIRTUAL_ENV", "")
    
    # If VIRTUAL_ENV is set, use that
    if venv_path:
        in_virtualenv = True
    # Otherwise check if the Python executable is in a venv directory structure
    elif "venv" in sys.executable or "virtualenv" in sys.executable:
        in_virtualenv = True
        # Try to extract the venv path from the executable path
        venv_path = sys.executable
        if "\\Scripts\\" in venv_path:
            venv_path = venv_path.split("\\Scripts\\")[0]
        elif "/bin/" in venv_path:
            venv_path = venv_path.split("/bin/")[0]
    
    # Read requirements.txt
    requirements = []
    req_file_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if os.path.exists(req_file_path):
        with open(req_file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    requirements.append(line)
    
    # Get installed packages
    installed_packages: Dict[str, str] = {}
    try:
        for dist in importlib.metadata.distributions():
            try:
                name = dist.metadata["Name"].lower()
                installed_packages[name] = dist.version
            except (KeyError, AttributeError):
                # Skip packages with missing metadata
                pass
    except Exception as e:
        logger.warning(f"Error getting installed packages: {str(e)}")
        # Empty dict as fallback
        installed_packages = {}
    
    # Check requirements against installed packages
    req_status = []
    for req in requirements:
        original_req = req
        # Handle requirements with version specifiers
        if "==" in req:
            pkg_name, version_spec = req.split("==", 1)
            pkg_name = pkg_name.strip().lower()
        elif ">=" in req:
            pkg_name, version_spec = req.split(">=", 1)
            pkg_name = pkg_name.strip().lower()
        elif "[" in req:
            # Handle packages with extras like 'package[extra]'
            pkg_name = req.split("[", 1)[0].strip().lower()
        else:
            pkg_name = req.strip().lower()
        
        # For packages with extras, we need to check the base package name
        base_pkg_name = pkg_name.split("[")[0] if "[" in pkg_name else pkg_name
        
        installed_version = installed_packages.get(base_pkg_name)
        req_status.append({
            "name": pkg_name,
            "required": original_req,
            "installed": installed_version if installed_version else "Not installed"
        })
    
    return {
        "python_path": sys.executable,
        "python_version": sys.version,
        "virtual_env": venv_path if in_virtualenv else "Not in a virtual environment",
        "in_virtualenv": in_virtualenv,
        "requirements": req_status
    }

# === Incremental Sync API Endpoints ===

async def ensure_config_manager_ready():
    """Ensure config_manager pool is open, reinitialize if needed"""
    if not incremental_manager or not incremental_manager.is_initialized():
        raise HTTPException(status_code=400, detail="Incremental system not initialized")
    
    if incremental_manager.config_manager.pool is None or incremental_manager.config_manager.pool._closed:
        logger.warning("Config manager pool is closed, reinitializing...")
        await incremental_manager.config_manager.initialize()

@app.get("/api/sync/datasources")
async def list_datasources():
    """List all configured datasources for incremental sync"""
    try:
        await ensure_config_manager_ready()
        
        configs = await incremental_manager.config_manager.get_all_active_configs()
        
        datasources = []
        for config in configs:
            datasources.append({
                "config_id": config.config_id,
                "source_type": config.source_type,
                "source_name": config.source_name,
                "is_active": config.is_active,
                "sync_status": config.sync_status,
                "last_sync_at": config.last_sync_completed_at.isoformat() if config.last_sync_completed_at else None,
                "refresh_interval_seconds": config.refresh_interval_seconds,
                "skip_graph": config.skip_graph
            })
        
        return {"status": "success", "datasources": datasources}
    
    except Exception as e:
        logger.error(f"Error listing datasources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/sync-now/{config_id}")
async def sync_now_single(config_id: str):
    """
    Trigger an immediate sync for a specific datasource.
    Useful for testing without waiting for periodic refresh.
    """
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        if not incremental_manager.orchestrator:
            raise HTTPException(status_code=400, detail="Orchestrator not running")
        
        logger.info(f"API: Triggering sync-now for config_id: {config_id}")
        
        result = await incremental_manager.orchestrator.trigger_sync(config_id)
        
        return {
            "status": "success",
            "message": f"Sync completed for {result['source_name']}",
            "config_id": config_id
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except asyncio.CancelledError:
        # Raised when the server is shutting down mid-request (e.g. SIGTERM during KG extraction).
        # Returning 503 keeps uvicorn alive for any remaining in-flight requests instead of
        # letting the CancelledError propagate to the ASGI lifespan and crash the process.
        logger.warning("sync-now/%s: request cancelled (server shutting down)", config_id)
        raise HTTPException(status_code=503, detail="Server is shutting down")
    except Exception as e:
        logger.error(f"Error triggering sync-now: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/sync/datasources/{config_id}/interval")
async def update_refresh_interval(config_id: str, interval_seconds: int = None, hours: int = None, minutes: int = None, seconds: int = None):
    """
    Update the periodic refresh interval for a datasource.
    
    Args:
        config_id: UUID of the datasource
        interval_seconds: Direct seconds value (takes precedence)
        hours: Number of hours (combined with minutes/seconds)
        minutes: Number of minutes (combined with hours/seconds)
        seconds: Number of seconds (combined with hours/minutes)
        
    Examples:
        ?interval_seconds=3600  (1 hour)
        ?hours=1  (1 hour)
        ?hours=2&minutes=30  (2.5 hours)
        ?minutes=90  (1.5 hours)
        ?hours=24  (24 hours)
    """
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        # Calculate total seconds
        if interval_seconds is not None:
            total_seconds = interval_seconds
        else:
            total_seconds = 0
            if hours:
                total_seconds += hours * 3600
            if minutes:
                total_seconds += minutes * 60
            if seconds:
                total_seconds += seconds
            
            if total_seconds == 0:
                raise HTTPException(status_code=400, detail="Must provide interval_seconds or at least one time unit (hours/minutes/seconds)")
        
        if total_seconds < 60 and total_seconds != 0:
            raise HTTPException(status_code=400, detail="Interval must be at least 60 seconds or 0 to disable")
        
        # Update the config in database
        async with incremental_manager.config_manager.pool.acquire() as conn:
            await conn.execute("""
                UPDATE datasource_config 
                SET refresh_interval_seconds = $1, updated_at = NOW()
                WHERE config_id = $2
            """, total_seconds, config_id)
        
        # Restart the updater to apply new interval
        if incremental_manager.orchestrator and config_id in incremental_manager.orchestrator.active_updaters:
            await incremental_manager.orchestrator._stop_updater(config_id)
            config = await incremental_manager.config_manager.get_config(config_id)
            if config:
                await incremental_manager.orchestrator._start_updater(config)
        
        logger.info(f"API: Updated refresh interval for {config_id} to {total_seconds}s")
        
        return {
            "status": "success",
            "message": f"Refresh interval updated to {total_seconds} seconds",
            "config_id": config_id,
            "interval_seconds": total_seconds
        }
    
    except Exception as e:
        logger.error(f"Error updating refresh interval: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sync/status")
async def get_sync_status():
    """Get overall incremental sync system status"""
    try:
        if not incremental_manager:
            return {
                "status": "disabled",
                "message": "Incremental system not configured"
            }
        
        return {
            "status": "active" if incremental_manager.is_monitoring() else "initialized",
            "initialized": incremental_manager.is_initialized(),
            "monitoring": incremental_manager.is_monitoring(),
            "active_updaters": len(incremental_manager.orchestrator.active_updaters) if incremental_manager.orchestrator else 0
        }
    
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/start-monitoring")
async def start_monitoring():
    """
    Manually start the orchestrator monitoring (debug/recovery endpoint).
    Use if monitoring stopped for some reason.
    """
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        if incremental_manager.is_monitoring():
            return {
                "status": "already_running",
                "message": "Monitoring is already active"
            }
        
        logger.info("API: Manually starting orchestrator monitoring...")
        await incremental_manager.start_monitoring()
        
        return {
            "status": "success",
            "message": "Monitoring started",
            "active_updaters": len(incremental_manager.orchestrator.active_updaters) if incremental_manager.orchestrator else 0
        }
    
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/disable-all")
async def disable_all_syncing():
    """
    Disable automatic syncing for ALL datasources by setting is_active=false.
    Useful for testing or maintenance without deleting configurations.
    """
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        logger.info("API: Disabling all datasources...")
        
        # Get all active configs
        configs = await incremental_manager.config_manager.get_all_active_configs()
        
        if not configs:
            return {
                "status": "success",
                "message": "No active datasources to disable",
                "disabled_count": 0
            }
        
        # Disable each config
        disabled_count = 0
        async with incremental_manager.config_manager.pool.acquire() as conn:
            for config in configs:
                await conn.execute("""
                    UPDATE datasource_config 
                    SET is_active = false, updated_at = NOW()
                    WHERE config_id = $1
                """, config.config_id)
                disabled_count += 1
        
        logger.info(f"API: Disabled {disabled_count} datasource(s)")
        
        return {
            "status": "success",
            "message": f"Disabled {disabled_count} datasource(s)",
            "disabled_count": disabled_count,
            "note": "Datasources will stop syncing. Use /api/sync/enable-all to re-enable."
        }
    
    except Exception as e:
        logger.error(f"Error disabling all syncing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/enable-all")
async def enable_all_syncing():
    """
    Enable automatic syncing for ALL datasources by setting is_active=true.
    """
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        logger.info("API: Enabling all datasources...")
        
        # Get all inactive configs
        async with incremental_manager.config_manager.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT config_id FROM datasource_config 
                WHERE is_active = false
            """)
        
        if not rows:
            return {
                "status": "success",
                "message": "No disabled datasources to enable",
                "enabled_count": 0
            }
        
        # Enable each config
        enabled_count = 0
        async with incremental_manager.config_manager.pool.acquire() as conn:
            for row in rows:
                await conn.execute("""
                    UPDATE datasource_config 
                    SET is_active = true, updated_at = NOW()
                    WHERE config_id = $1
                """, row['config_id'])
                enabled_count += 1
        
        logger.info(f"API: Enabled {enabled_count} datasource(s)")
        
        return {
            "status": "success",
            "message": f"Enabled {enabled_count} datasource(s)",
            "enabled_count": enabled_count,
            "note": "Datasources will resume syncing automatically"
        }
    
    except Exception as e:
        logger.error(f"Error enabling all syncing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/sync-now")
async def sync_now_all():
    """
    Trigger immediate sync for ALL active datasources.
    Syncs run sequentially to avoid overwhelming the system.
    Useful for testing or immediate sync after bulk changes.
    """
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        # Auto-start monitoring if not running
        if not incremental_manager.is_monitoring():
            logger.info("API: Monitoring not active, starting automatically...")
            await incremental_manager.start_monitoring()
            # Give it a moment to initialize
            await asyncio.sleep(1)
        
        if not incremental_manager.orchestrator:
            raise HTTPException(status_code=400, detail="Orchestrator not running")
        
        logger.info("API: Triggering sync-now for all datasources (sequential)...")
        
        # Get all active updaters
        active_updaters = incremental_manager.orchestrator.active_updaters
        
        if not active_updaters:
            return {
                "status": "success",
                "message": "No active datasources to sync",
                "synced_count": 0,
                "results": [],
                "note": "Check that datasources exist and are active in database"
            }
        
        # Trigger sync for each SEQUENTIALLY to avoid overwhelming system
        results = []
        synced_count = 0
        failed_count = 0
        
        for config_id, updater in active_updaters.items():
            try:
                logger.info(f"API: Syncing datasource {config_id}...")
                result = await updater.trigger_manual_sync()
                results.append({
                    "config_id": config_id,
                    "source_name": result['source_name'],
                    "status": "success"
                })
                synced_count += 1
                logger.info(f"API: Completed sync for {config_id}")
            except asyncio.CancelledError:
                # Re-raise so the outer handler can return a graceful 503 instead of
                # crashing uvicorn's ASGI lifespan.
                raise
            except Exception as e:
                logger.error(f"Failed to sync {config_id}: {e}")
                results.append({
                    "config_id": config_id,
                    "status": "failed",
                    "error": str(e)
                })
                failed_count += 1
        
        logger.info(f"API: Completed sync-now - {synced_count} succeeded, {failed_count} failed")
        
        return {
            "status": "success" if failed_count == 0 else "partial",
            "message": f"Synced {synced_count} datasource(s), {failed_count} failed",
            "synced_count": synced_count,
            "failed_count": failed_count,
            "results": results,
            "note": "Datasources synced sequentially to avoid system overload"
        }
    
    except asyncio.CancelledError:
        # Server is shutting down mid-sync (SIGTERM during slow cloud graph write).
        # Return 503 instead of letting the CancelledError propagate to uvicorn's
        # ASGI lifespan, which would crash the process and make subsequent test
        # requests get "connection refused".
        logger.warning("sync-now (all): request cancelled (server shutting down)")
        raise HTTPException(status_code=503, detail="Server is shutting down")
    except Exception as e:
        logger.error(f"Error triggering sync-now: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/sync/interval")
async def update_all_refresh_intervals(interval_seconds: int = None, hours: int = None, minutes: int = None, seconds: int = None):
    """
    Update the periodic refresh interval for ALL datasources.
    
    Args:
        interval_seconds: Direct seconds value (takes precedence)
        hours: Number of hours (combined with minutes/seconds)
        minutes: Number of minutes (combined with hours/seconds)
        seconds: Number of seconds (combined with hours/minutes)
        
    Examples:
        ?hours=1  (1 hour for all)
        ?hours=24  (24 hours for all)
        ?minutes=30  (30 minutes for all)
    """
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        # Calculate total seconds
        if interval_seconds is not None:
            total_seconds = interval_seconds
        else:
            total_seconds = 0
            if hours:
                total_seconds += hours * 3600
            if minutes:
                total_seconds += minutes * 60
            if seconds:
                total_seconds += seconds
            
            if total_seconds == 0:
                raise HTTPException(status_code=400, detail="Must provide interval_seconds or at least one time unit")
        
        if total_seconds < 60 and total_seconds != 0:
            raise HTTPException(status_code=400, detail="Interval must be at least 60 seconds")
        
        # Get all configs
        configs = await incremental_manager.config_manager.get_all_active_configs()
        
        if not configs:
            return {
                "status": "success",
                "message": "No datasources to update",
                "updated_count": 0
            }
        
        # Update all configs
        updated_count = 0
        async with incremental_manager.config_manager.pool.acquire() as conn:
            for config in configs:
                await conn.execute("""
                    UPDATE datasource_config 
                    SET refresh_interval_seconds = $1, updated_at = NOW()
                    WHERE config_id = $2
                """, total_seconds, config.config_id)
                
                # Restart updater
                if incremental_manager.orchestrator and config.config_id in incremental_manager.orchestrator.active_updaters:
                    await incremental_manager.orchestrator._stop_updater(config.config_id)
                    new_config = await incremental_manager.config_manager.get_config(config.config_id)
                    if new_config:
                        await incremental_manager.orchestrator._start_updater(new_config)
                
                updated_count += 1
        
        logger.info(f"API: Updated refresh interval for {updated_count} datasource(s) to {total_seconds}s")
        
        return {
            "status": "success",
            "message": f"Updated refresh interval to {total_seconds} seconds for {updated_count} datasource(s)",
            "updated_count": updated_count,
            "interval_seconds": total_seconds
        }
    
    except Exception as e:
        logger.error(f"Error updating all refresh intervals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/sync/datasources/{config_id}/disable")
async def disable_datasource(config_id: str):
    """Disable automatic syncing for a specific datasource."""
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        async with incremental_manager.config_manager.pool.acquire() as conn:
            await conn.execute("""
                UPDATE datasource_config 
                SET is_active = false, updated_at = NOW()
                WHERE config_id = $1
            """, config_id)
        
        logger.info(f"API: Disabled datasource {config_id}")
        
        return {
            "status": "success",
            "message": f"Disabled datasource {config_id}",
            "config_id": config_id
        }
    
    except Exception as e:
        logger.error(f"Error disabling datasource: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/sync/datasources/{config_id}/enable")
async def enable_datasource(config_id: str):
    """Enable automatic syncing for a specific datasource."""
    try:
        if not incremental_manager or not incremental_manager.is_initialized():
            raise HTTPException(status_code=400, detail="Incremental system not initialized")
        
        async with incremental_manager.config_manager.pool.acquire() as conn:
            await conn.execute("""
                UPDATE datasource_config 
                SET is_active = true, updated_at = NOW()
                WHERE config_id = $1
            """, config_id)
        
        logger.info(f"API: Enabled datasource {config_id}")
        
        return {
            "status": "success",
            "message": f"Enabled datasource {config_id}",
            "config_id": config_id
        }
    
    except Exception as e:
        logger.error(f"Error enabling datasource: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Backend API only - no frontend serving
@app.get("/")
async def root():
    return {
        "message": "Flexible GraphRAG API", 
        "api": "/api",
        "info": "/api/info",
        "note": "Backend API only - use separate dev servers for UIs"
    }

if __name__ == "__main__":
    # Disable uvicorn's default logging to prevent duplicate messages
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_config=None,  # Disable uvicorn's default logging config
        access_log=False  # Disable access logging to reduce noise
    )
