import os
import ntpath
import logging
import re
import sys
import warnings
from datetime import datetime

# google-auth / api-core warn at import that grpcio < 1.83 lacks post-quantum cryptography. grpcio
# can't move up yet: weaviate-client (4.23.1) requires grpcio < 1.80. Drop this once it can.
# weaviate's own import calls warnings.simplefilter("default"), which goes in front of every
# earlier filter -- so import it first (it is imported only once), then put this filter ahead of it.
try:
    import weaviate  # noqa: F401
except Exception:
    pass
warnings.filterwarnings("ignore", message=r".*does not support Post-Quantum Cryptography.*", category=FutureWarning)

# Neutralise nest_asyncio.apply on Python 3.14+ before any imports that might trigger it.
# LlamaIndex (async_utils, elasticsearch store) calls nest_asyncio.apply() unconditionally;
# on 3.14 this breaks asyncio.Runner.close() → shutdown_default_executor().
if sys.version_info >= (3, 14):
    try:
        import nest_asyncio as _nest_asyncio_early
        _nest_asyncio_early.apply = lambda *a, **kw: None
    except ImportError:
        pass

# Use the OS certificate store for TLS verification when available. Antivirus /
# corporate TLS-inspection proxies (e.g. Norton Web Shield) re-sign every HTTPS
# connection with a root that Windows trusts but certifi does not, which makes
# every outbound call fail with CERTIFICATE_VERIFY_FAILED. Opt out with
# USE_SYSTEM_CERT_STORE=false.
if os.getenv("USE_SYSTEM_CERT_STORE", "true").lower() != "false":
    try:
        import truststore as _truststore
        _truststore.inject_into_ssl()
    except ImportError:
        pass

from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic as _monotonic
from dotenv import find_dotenv, load_dotenv

# Load .env FIRST before any other imports (especially backend.py) so environment vars are available.
# From the working directory first: in a wheel install this file is in site-packages, where a bare
# load_dotenv() (which searches from the caller's folder) finds nothing -- every os.getenv()
# setting (e.g. the *_DB_CONFIG JSON) then silently fell back to its default. Next to this file
# second (a source checkout run from elsewhere).
load_dotenv(find_dotenv(usecwd=True) or find_dotenv())

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator
from typing import Any, Dict, List, Optional, Union
import asyncio
import uvicorn
import shutil
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


class _QuietStatusPolls(logging.Filter):
    """Keep the UIs' job polling (GET /api/processing-status..., every few seconds per open UI)
    out of the uvicorn access log; failed polls are still logged."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 5:
            method, path, code = args[1], str(args[2]), args[4]
            if method == "GET" and path.startswith("/api/processing-status") and code in (200, 304):
                return False
        return True


logging.getLogger("uvicorn.access").addFilter(_QuietStatusPolls())


class _DropStaleUvicornColorMessage(logging.Filter):
    """litellm's SecretRedactionFilter (attached to "uvicorn.error" when litellm is imported)
    pre-formats the message and sets record.args = None, but leaves uvicorn's `color_message`
    template behind. In a terminal uvicorn formats that template against the now-empty args and
    prints "Uvicorn running on %s://%s:%d". Dropping the template makes uvicorn fall back to the
    already-formatted, redacted message. Must run after litellm's filter (added at module end)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args is None and "color_message" in record.__dict__:
            del record.__dict__["color_message"]
        return True

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
    #
    # anyio 4.14+ uses __slots__ on CancelScope, so we cannot set arbitrary instance attributes.
    # Fix: track no-op scopes by id() in a module-level set instead of instance attributes.
    try:
        from anyio._backends._asyncio import CancelScope as _AnyioCancelScope
        _orig_cancel_scope_enter = _AnyioCancelScope.__enter__
        _orig_cancel_scope_exit = _AnyioCancelScope.__exit__

        # Scopes entered while there is no current task — stored by id() to avoid
        # needing to set attributes on __slots__-restricted objects.
        _noop_cancel_scope_ids: set = set()

        def _safe_cancel_scope_enter(self):
            if asyncio.current_task() is None:
                self._active = True
                _noop_cancel_scope_ids.add(id(self))
                return self
            return _orig_cancel_scope_enter(self)

        def _safe_cancel_scope_exit(self, exc_type, exc_val, exc_tb):
            scope_id = id(self)
            if scope_id in _noop_cancel_scope_ids:
                self._active = False
                _noop_cancel_scope_ids.discard(scope_id)
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
    #
    # IMPORTANT: httpcore._async.{connection_pool,http11,http2} all do
    #   from .._synchronization import AsyncShieldCancellation
    # at module-load time, caching the class in their own namespace.  We must
    # patch those cached references too, not just the _synchronization module.
    try:
        import httpcore._synchronization as _httpcore_sync
        import httpcore._async.connection_pool as _hc_pool
        import httpcore._async.http11 as _hc_http11

        # If cocoindex_integration._compat already patched AsyncShieldCancellation
        # (CLI mode: _compat runs before main.py), skip to avoid double-patch
        # mutual-recursion: each wrapper's __init__ would call the other's class
        # causing a RecursionError 540 frames deep.
        if not hasattr(_httpcore_sync, "_orig_AsyncShieldCancellation"):
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
            # Also update the references already cached by the async sub-modules
            _hc_pool.AsyncShieldCancellation = _SafeAsyncShieldCancellation
            _hc_http11.AsyncShieldCancellation = _SafeAsyncShieldCancellation
            try:
                import httpcore._async.http2 as _hc_http2
                _hc_http2.AsyncShieldCancellation = _SafeAsyncShieldCancellation
            except Exception:
                pass
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

# When the CocoIndex pipeline is active, apply the full CocoIndex async
# compatibility patch suite (includes neo4j AsyncCooperativeRLock,
# falkordb.asyncio / surrealdb.AsyncSurreal task-context guards, etc.) that
# are needed for Python-backed native connectors running under CocoIndex's
# Rust dispatcher where ``asyncio.current_task()`` returns ``None``.
#
# _compat.apply_async_patches() is idempotent (guarded by _PATCHED flag +
# per-patch guards) so it is safe to call even though _apply_python314_patches()
# already applied the anyio/httpcore/sniffio/nest_asyncio/wait_for subset.
if os.getenv("PIPELINE_BACKEND", "default").lower() == "cocoindex":
    try:
        from cocoindex_integration._compat import (  # type: ignore[import-untyped]
            apply_async_patches as _apply_coco_compat_patches,
        )
        _apply_coco_compat_patches()
    except Exception:
        pass


def _patch_ssl_context() -> None:
    """Patch ssl.create_default_context so all Python versions work on Windows.

    Two issues affect HTTPS connections (OpenAI, Anthropic, etc.) on Windows:

    1. ssl.VERIFY_X509_STRICT is enabled by default from Python 3.12+ when the
       Windows certificate store is loaded.  It rejects CA certs that lack the
       Basic Constraints extension — a common trait of SSL-inspection roots
       installed by antivirus or corporate proxy software.

    2. httpx always passes cafile=certifi.where() to create_default_context,
       loading only certifi's ~118 root CAs.  Any locally-installed CA (e.g.
       a corporate root added to the Windows store) is therefore invisible and
       the TLS handshake fails with "unable to get local issuer certificate".

    Fix: wrap create_default_context to clear VERIFY_X509_STRICT and also
    call load_default_certs() so the Windows cert store supplements certifi.
    """
    # Implementation lives in ssl_compat so the Langflow components and the
    # examples/ scripts share it instead of each carrying a copy.
    try:
        from ssl_compat import patch_ssl_context as _patch  # noqa: PLC0415

        if _patch():
            logger.info(
                "SSL patch applied: cleared VERIFY_X509_STRICT, added OS cert store"
            )
    except Exception:
        pass


_patch_ssl_context()
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
#
# encoding is load-bearing on Windows.  Without it FileHandler uses the locale
# encoding (cp1252 here), which cannot represent characters this codebase logs
# routinely — "→" in the backend-resolution messages, "—" in several warnings —
# so writing one raises
#
#     UnicodeEncodeError: 'charmap' codec can't encode character '→'
#
# and the record is mangled or lost exactly when something has gone wrong and you
# most need to read it (the ontology "could not load … — <urlopen error>"
# warning was landing that way).  Matches setup_cli_logging() in
# cocoindex_integration/_compat.py, which already opens its log file as UTF-8.
file_handler = logging.FileHandler(log_filename, encoding="utf-8")
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
# kafka-python logs every fetch/heartbeat/offset-commit at DEBUG; the Nuxeo
# audit consumer polls continuously, which swamps the log at LOG_LEVEL=DEBUG.
for _kafka_logger in (
    "kafka", "kafka.client", "kafka.conn", "kafka.consumer",
    "kafka.coordinator", "kafka.protocol", "kafka.cluster",
):
    logging.getLogger(_kafka_logger).setLevel(logging.WARNING)
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

# Global references for incremental system and CocoIndex bridge
incremental_manager = None
cocoindex_bridge = None   # CocoIndexBridge instance (set when PIPELINE_BACKEND=cocoindex)


def _state_pool():
    """The incremental registry's pool, for naming the documents results came from (doc_refs)."""
    if incremental_manager and incremental_manager.is_initialized():
        return getattr(incremental_manager.state_manager, "pool", None)
    return None


import doc_refs as _doc_refs  # noqa: E402
_doc_refs.set_pool_provider(_state_pool)


def _log_cocoindex_pipeline_config() -> None:
    """Emit the structured CocoIndex LLM / DB / framework config block to the log."""
    try:
        from cocoindex_integration.pipeline.env_config import load_config_from_env as _lcfe  # noqa: PLC0415
        from cocoindex_integration.pipeline.flexible_app import (  # noqa: PLC0415
            _resolve_pipeline_config as _rpc,
            log_pipeline_config as _lpc,
        )
        _raw = _lcfe()
        _lpc(_raw, _rpc(_raw))
    except Exception as _log_exc:
        logger.debug("CocoIndex config log failed: %s", _log_exc)


async def _ensure_cocoindex_bridge(fg_config=None) -> bool:
    """Start the CocoIndex bridge on first use when PIPELINE_BACKEND=cocoindex.

    When DATA_SOURCE is empty at startup the bridge is deferred until the user
    submits a source through the UI (or another ingest call).
    """
    global cocoindex_bridge
    if os.getenv("PIPELINE_BACKEND", "default").lower() != "cocoindex":
        return False
    if cocoindex_bridge is not None:
        return True
    try:
        from cocoindex_integration.bridge import CocoIndexBridge
        cocoindex_bridge = CocoIndexBridge(fg_config=fg_config)
        await cocoindex_bridge.start()
        logger.info(
            "SUCCESS: CocoIndex pipeline bridge started (lazy) — "
            "source=%s  watch_dir=%s  db=%s",
            cocoindex_bridge._data_source or "(UI sources only)",
            cocoindex_bridge._source_dir,
            cocoindex_bridge._db_path,
        )
        _log_cocoindex_pipeline_config()
        return True
    except Exception as _ce:
        logger.error("ERROR: Failed to start CocoIndex bridge (lazy): %s", _ce)
        import traceback as _tb
        _tb.print_exc()
        cocoindex_bridge = None
        return False

# ---------------------------------------------------------------------------
# Startup helpers — called from lifespan()
# ---------------------------------------------------------------------------

async def _startup_cocoindex_bridge(backend) -> None:
    """Start CocoIndex bridge at app startup when PIPELINE_BACKEND=cocoindex.

    Sets the module-level ``cocoindex_bridge`` global on success.
    Defers start when DATA_SOURCE is empty (bridge starts lazily on first UI ingest).
    """
    global cocoindex_bridge
    _pipeline_backend = os.getenv("PIPELINE_BACKEND", "default").lower()
    if "DATA_SOURCE" in os.environ:
        _startup_data_source = os.getenv("DATA_SOURCE", "").strip()
        if _startup_data_source.lower() == "none":
            _startup_data_source = ""
    else:
        _startup_data_source = "filesystem"

    if _pipeline_backend != "cocoindex":
        logger.info(
            "INFO: Using per-stage pipeline config (PIPELINE_BACKEND=%s; "
            "set PIPELINE_BACKEND=cocoindex to enable CocoIndex memoized pipeline)",
            _pipeline_backend,
        )
        return

    if not _startup_data_source:
        logger.info(
            "CocoIndex pipeline configured (PIPELINE_BACKEND=cocoindex) but "
            "DATA_SOURCE is empty — bridge deferred until first UI ingest. "
            "Set DATA_SOURCE=filesystem to auto-start a primary source at boot."
        )
        return

    try:
        from cocoindex_integration.bridge import CocoIndexBridge
        cocoindex_bridge = CocoIndexBridge(fg_config=getattr(backend.system, "config", None))
        await cocoindex_bridge.start()
        logger.info(
            "SUCCESS: CocoIndex pipeline bridge started — "
            "source=%s  watch_dir=%s  db=%s",
            cocoindex_bridge._data_source,
            cocoindex_bridge._source_dir,
            cocoindex_bridge._db_path,
        )
        _log_cocoindex_pipeline_config()
    except Exception as _ce:
        logger.error("ERROR: Failed to start CocoIndex bridge: %s", _ce)
        import traceback as _tb
        _tb.print_exc()
        cocoindex_bridge = None


async def _startup_langflow(backend) -> None:
    """Bind Langflow flows at startup when ENABLE_LANGFLOW_FLOWS=true (best-effort).

    Mutually exclusive with ``PIPELINE_BACKEND=cocoindex``: CocoIndex is not wired
    into Langflow flows.  When CocoIndex is active, force-disable flow mode so
    ingest/search/QA do not split across incompatible orchestrators.
    """
    pipeline_backend = os.getenv("PIPELINE_BACKEND", "default").lower()
    if pipeline_backend == "cocoindex":
        if backend.settings.enable_langflow_flows:
            logger.warning(
                "ENABLE_LANGFLOW_FLOWS=true is ignored when "
                "PIPELINE_BACKEND=cocoindex (mutually exclusive — CocoIndex is "
                "not supported inside Langflow flows). Flow mode disabled for "
                "this process. Set ENABLE_LANGFLOW_FLOWS=false to silence this "
                "warning."
            )
            backend.settings.enable_langflow_flows = False
        else:
            logger.info(
                "Langflow flow mode disabled "
                "(PIPELINE_BACKEND=cocoindex — CocoIndex owns ingest)"
            )
        return

    if backend.settings.enable_langflow_flows:
        logger.info(
            "Langflow flow mode ENABLED — ingest/query run via Langflow flows at %s",
            backend.settings.langflow_url,
        )
        try:
            fsvc = await backend._get_flow_service()
            logger.info(
                "Langflow flows bound — ingest_flow_id=%s, query_flow_id=%s",
                fsvc.ingestion_flow_id, fsvc.query_flow_id,
            )
        except Exception as e:
            logger.warning(
                "Could not bind Langflow flows at startup (will retry on first request): %s", e
            )
    else:
        logger.info("Langflow flow mode disabled (ENABLE_LANGFLOW_FLOWS not true) — using direct pipeline")


async def _startup_incremental_manager(backend) -> None:
    """Initialize incremental update system when ENABLE_INCREMENTAL_UPDATES=true.

    Sets the module-level ``incremental_manager`` global on success.

    Mutually exclusive with ``PIPELINE_BACKEND=cocoindex``.  The FG incremental
    engine ingests via ``hybrid_system`` (default LI/LC pipeline), not CocoIndex.
    If both were started, UI/REST could use CocoIndex while detectors re-ingest
    through the default pipeline — a bad state.  When CocoIndex is active, skip
    this orchestrator even if ``ENABLE_INCREMENTAL_UPDATES=true``.
    """
    global incremental_manager
    enable_incremental = os.getenv('ENABLE_INCREMENTAL_UPDATES', 'false').lower() == 'true'
    postgres_url = os.getenv('POSTGRES_INCREMENTAL_URL')
    pipeline_backend = os.getenv("PIPELINE_BACKEND", "default").lower()

    if pipeline_backend == "cocoindex":
        if enable_incremental:
            logger.warning(
                "ENABLE_INCREMENTAL_UPDATES=true is ignored when "
                "PIPELINE_BACKEND=cocoindex (mutually exclusive). The FG "
                "incremental engine uses the default hybrid_system pipeline, "
                "not CocoIndex — both enabled is a bad state. document_state "
                "orchestrator will not start. Set ENABLE_INCREMENTAL_UPDATES=false "
                "to silence this warning."
            )
        else:
            logger.info(
                "INFO: FG incremental orchestrator not started "
                "(PIPELINE_BACKEND=cocoindex — CocoIndex owns change processing)"
            )
        return

    if not enable_incremental:
        logger.info("INFO: Incremental updates disabled (set ENABLE_INCREMENTAL_UPDATES=true to enable)")
        return

    if not postgres_url:
        logger.warning("WARNING: ENABLE_INCREMENTAL_UPDATES=true but POSTGRES_INCREMENTAL_URL not set")
        logger.warning("   Incremental updates disabled - set POSTGRES_INCREMENTAL_URL in .env")
        return

    def _is_connection_error(msg: str) -> bool:
        return ("refused" in msg.lower() or "WinError" in msg or "could not connect" in msg.lower()
                or "connect call failed" in msg.lower())

    # A connection error at startup can be a passing one (Docker Desktop's port forwarding has
    # failed once with WinError 64 while the container was up): without a retry the whole run
    # went on with no incremental system -- ingests not recorded, "ask about" refused.
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            from incremental_system import IncrementalSystemManager
            incremental_manager = IncrementalSystemManager.get_instance()
            await incremental_manager.initialize(
                postgres_url=postgres_url,
                vector_index=backend.system.vector_index,
                graph_index=backend.system.graph_index,
                search_index=None,
                doc_processor=backend.system.document_processor,
                app_config=backend.system.config,
                hybrid_system=backend.system,
                backend=backend,
            )
            await incremental_manager.start_monitoring()
            logger.info("SUCCESS: Incremental updates enabled and monitoring started")
            return
        except Exception as e:
            last_error, error_msg = e, str(e)
            if attempt < attempts and _is_connection_error(error_msg):
                logger.warning(f"Incremental updates: PostgreSQL connection failed ({error_msg}); "
                               f"retrying in 5s (attempt {attempt} of {attempts})")
                await asyncio.sleep(5)
                continue
            break
    # Every attempt failed
    logger.error(f"ERROR: Failed to initialize incremental updates: {error_msg}")
    _db_missing = "does not exist" in error_msg
    _server_down = _is_connection_error(error_msg)
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
        logger.error("Incremental updates initialization error", exc_info=last_error)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup/shutdown lifecycle.
    Initialize incremental system (or CocoIndex bridge) at startup.
    """
    global incremental_manager, cocoindex_bridge
    
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

    backend = get_backend()
    logger.info("Backend initialized")

    await _startup_cocoindex_bridge(backend)
    await _startup_langflow(backend)
    await _startup_incremental_manager(backend)

    yield

    # === SHUTDOWN ===
    logger.info("Shutting down application...")
    if incremental_manager:
        try:
            await incremental_manager.stop_monitoring()
            logger.info("SUCCESS: Incremental system stopped")
        except Exception as e:
            logger.error(f"Error stopping incremental system: {e}")

    if cocoindex_bridge:
        try:
            await cocoindex_bridge.stop()
            logger.info("SUCCESS: CocoIndex bridge stopped")
        except Exception as e:
            logger.error(f"Error stopping CocoIndex bridge: {e}")

    logger.info("SUCCESS: Shutdown complete")

# Initialize FastAPI app with lifespan
class _RedactAuthCodes(logging.Filter):
    """Keep one-time sign-in codes out of the access log: a popup sign-in's callback
    (/api/auth/<provider>/callback?code=...) -- Box sends its code in the query string."""
    _CODE = re.compile(r"((?:^|[?&])(?:code|session_state)=)[^&\s]+")

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and "/api/auth/" in str(args[2]):
            record.args = args[:2] + (self._CODE.sub(r"\1[redacted]", str(args[2])),) + args[3:]
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactAuthCodes())

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
    username: Optional[str] = None
    password: Optional[str] = None
    folder_path: str
    # From the UI's CMIS sign-in (sources/cmis_auth.py): an Alfresco server's ticket
    # (auth_method=ticket) or a Nuxeo server's token (auth_method=token) instead of a password.
    auth_method: Optional[str] = None  # basic | ticket | token
    ticket: Optional[str] = None
    token: Optional[str] = None

class NodeDetail(BaseModel):
    id: str
    name: str
    path: str
    isFile: bool
    isFolder: bool

class AlfrescoOAuth2Config(BaseModel):
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_endpoint: Optional[str] = None
    grant_type: Optional[str] = None  # client_credentials (default) | refresh_token | authorization_code
    scope: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None

class AlfrescoConfig(BaseModel):
    url: str
    auth_method: Optional[str] = "basic"  # basic | ticket | oauth2
    username: Optional[str] = None
    password: Optional[str] = None
    # A login ticket the caller already holds (for auth_method="ticket"). Supplied instead of
    # username/password -- e.g. an ADF front end passing on the ticket it got at login.
    ticket: Optional[str] = None
    oauth2: Optional[AlfrescoOAuth2Config] = None  # for auth_method="oauth2"
    path: str
    nodeIds: Optional[List[str]] = None  # Array of node IDs (UUIDs from REST API) for multi-select
    nodeDetails: Optional[List[NodeDetail]] = None  # Array of node details with metadata
    recursive: Optional[bool] = False  # Whether to recursively process subfolders (default: False)
    stomp_port: Optional[int] = None  # ActiveMQ STOMP port for real-time events (default: 61613, or set via ALFRESCO_STOMP_PORT env var)

    @model_validator(mode="after")
    def _ticket_alone_means_ticket_auth(self):
        # A caller that only has a ticket (an ADF/ACA front end, an MCP client) need not also know
        # to set auth_method: without a username, the default "basic" would ignore the ticket.
        if self.ticket and not self.username and (self.auth_method or "basic").lower() == "basic":
            self.auth_method = "ticket"
        return self

class NuxeoOAuth2Config(BaseModel):
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_at: Optional[float] = None
    expires_in: Optional[float] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    redirect_uri: Optional[str] = None
    openid_configuration_url: Optional[str] = None

class NuxeoConfig(BaseModel):
    url: str
    auth_method: Optional[str] = "basic"  # basic | oauth2 | token
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None  # for auth_method="token" (X-Authentication-Token)
    oauth2: Optional[NuxeoOAuth2Config] = None  # for auth_method="oauth2"
    path: Optional[str] = "/"
    nodeIds: Optional[List[str]] = None  # Array of Nuxeo document uids for multi-select
    nodeDetails: Optional[List[NodeDetail]] = None  # Array of node details with metadata
    recursive: Optional[bool] = False  # Whether to recursively process subfolders (default: False)

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
    credentials: Optional[str] = None           # Service-account JSON string (inline)
    service_account_key_path: Optional[str] = None  # Path to service-account JSON file
    prefix: Optional[str] = None
    pubsub_subscription: Optional[str] = None   # Pub/Sub subscription for event-based sync

class AzureBlobConfig(BaseModel):
    container_name: str
    account_url: Optional[str] = None
    blob: Optional[str] = None  # renamed from blob_name to match LlamaCloud
    prefix: Optional[str] = None
    account_name: Optional[str] = None
    account_key: Optional[str] = None
    connection_string: Optional[str] = None  # alternative to account_url + account_key

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

class ItemAction(BaseModel):
    """One processing-tab row and what it should end up as (repository sources)."""
    path: str
    id: Optional[str] = None
    is_folder: bool = False
    # ingest: search + vector + graphs | ingest_no_graph: search + vector only |
    # remove_graph: drop the graphs, keep search + vector | remove_all: drop everything |
    # keep: no store change (only auto_sync below)
    action: str = "keep"
    # The Auto Sync column: False stops this row's auto sync (its documents are skipped by the
    # sync, and a datasource root is taken off the root list); True resumes it for documents
    # whose sync was stopped, or -- on a row being ingested that no sync covers -- makes this
    # run's datasource an auto sync watching it (its other rows are recorded with auto sync
    # off; see _plan_row_sync). None = no change.
    auto_sync: Optional[bool] = None


ITEM_ACTIONS = ("ingest", "ingest_no_graph", "remove_graph", "remove_all", "keep")


class IngestRequest(BaseModel):
    paths: Optional[List[str]] = None  # overrides config
    data_source: Optional[str] = None  # filesystem, cmis, alfresco, nuxeo, web, wikipedia, youtube, s3, gcs, azure_blob, onedrive, sharepoint, box, google_drive
    skip_graph: Optional[bool] = False  # Per-ingest flag to skip knowledge graph step (doesn't persist)
    enable_sync: Optional[bool] = False  # Enable incremental sync monitoring for this datasource
    # Per-row actions (Alfresco/Nuxeo): one job runs the removals, then one ingest pass per
    # graph setting, all under the datasource of the rows being ingested.
    item_actions: Optional[List[ItemAction]] = None
    # Who started it (e.g. the ACA user), so a jobs list can show a user their own runs
    owner: Optional[str] = None
    cmis_config: Optional[CmisConfig] = None
    alfresco_config: Optional[AlfrescoConfig] = None
    nuxeo_config: Optional[NuxeoConfig] = None
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

class AskScope(BaseModel):
    """Ask about one repository document or folder only (KG Spaces "Ask AI about this ...")."""
    data_source: str = "alfresco"  # alfresco | nuxeo
    url: Optional[str] = None      # repository url; omitted = every datasource of that type
    node_id: Optional[str] = None  # the document's / folder's node id
    path: Optional[str] = None     # its repository path (a folder covers everything below it)
    is_folder: bool = False
    name: Optional[str] = None     # for messages


class AlfrescoQueryAuth(BaseModel):
    """Who is asking, for Alfresco's permission check: the same credentials ingest takes
    (basic / ticket / oauth2). No path -- a question is not tied to one folder."""
    url: Optional[str] = None  # the Alfresco server to check on; omitted = the document's own datasource (or ALFRESCO_URL)
    auth_method: Optional[str] = None  # basic | ticket | oauth2; omitted = ticket if only a ticket is given, else basic
    username: Optional[str] = None
    password: Optional[str] = None
    ticket: Optional[str] = None
    oauth2: Optional[AlfrescoOAuth2Config] = None


class NuxeoQueryAuth(BaseModel):
    """Who is asking, for Nuxeo's permission check: the credentials ingest takes (basic / token /
    oauth2 with an access_token) -- normally the token from POST /api/auth/nuxeo/login."""
    url: Optional[str] = None  # the Nuxeo server (http://host:8081/nuxeo); omitted = NUXEO_URL
    auth_method: Optional[str] = None  # basic | token | oauth2; omitted = token if only a token is given, else basic
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    oauth2: Optional[NuxeoOAuth2Config] = None


class CmisQueryAuth(BaseModel):
    """Who is asking, for a CMIS server's permission check. From POST /api/auth/cmis/login: an
    Alfresco server's ticket (auth_method=ticket) or a Nuxeo server's token (auth_method=token);
    basic username/password also works."""
    url: Optional[str] = None  # the CMIS service URL (AtomPub); omitted = CMIS_URL
    auth_method: Optional[str] = None  # basic | ticket | token
    username: Optional[str] = None
    password: Optional[str] = None
    ticket: Optional[str] = None
    token: Optional[str] = None


class MicrosoftQueryAuth(BaseModel):
    """Who is asking, for SharePoint / OneDrive permission checks: a delegated Microsoft Graph
    access token from the Microsoft 365 sign-in (GET /api/auth/microsoft/popup)."""
    url: Optional[str] = None  # the tenant id; omitted = the token's own tenant (else MICROSOFT_AUTH_TENANT_ID)
    access_token: str


class S3QueryAuth(BaseModel):
    """Who is asking, for Amazon S3 permission checks: the token from POST /api/auth/s3/login
    (the user's temporary STS session credentials, packed)."""
    url: Optional[str] = None  # always "aws" (one S3 sign-in)
    token: str


class AzureQueryAuth(BaseModel):
    """Who is asking, for Azure Blob permission checks: an Azure Storage access token from the
    Azure Storage sign-in (GET /api/auth/azure/popup)."""
    url: Optional[str] = None  # always "azure" (one Azure Storage sign-in)
    access_token: str


class GoogleQueryAuth(BaseModel):
    """Who is asking, for Google Drive / Cloud Storage permission checks: a Google access token
    from the Google sign-in (GET /api/auth/google/popup)."""
    url: Optional[str] = None  # always google.com (one Google)
    access_token: str


class BoxQueryAuth(BaseModel):
    """Who is asking, for Box permission checks: a Box access token from the Box sign-in
    (GET /api/auth/box/popup)."""
    url: Optional[str] = None  # always box.com (one Box)
    access_token: str


class SourceAuth(BaseModel):
    """The asker's identities per data source, for each source's query-time permission check
    (permission_filter.py). Each entry is one credential or a list of them -- one per server, e.g.
    two Alfresco repositories -- matched to documents by url. ``microsoft`` (one per tenant)
    covers SharePoint and OneDrive."""
    alfresco: Optional[Union[AlfrescoQueryAuth, List[AlfrescoQueryAuth]]] = None
    nuxeo: Optional[Union[NuxeoQueryAuth, List[NuxeoQueryAuth]]] = None
    cmis: Optional[Union[CmisQueryAuth, List[CmisQueryAuth]]] = None
    microsoft: Optional[Union[MicrosoftQueryAuth, List[MicrosoftQueryAuth]]] = None
    box: Optional[Union[BoxQueryAuth, List[BoxQueryAuth]]] = None
    google: Optional[Union[GoogleQueryAuth, List[GoogleQueryAuth]]] = None
    azure: Optional[Union[AzureQueryAuth, List[AzureQueryAuth]]] = None
    s3: Optional[Union[S3QueryAuth, List[S3QueryAuth]]] = None


class SourceSelector(BaseModel):
    """One source to search: a data source type (as GET /api/sources/available lists it), and
    optionally one server of it."""
    source: str            # alfresco | nuxeo | cmis | filesystem | s3 | sharepoint | ...
    url: Optional[str] = None  # one server of that type; omitted = all of them


class QueryRequest(BaseModel):
    query: str
    top_k: int = 10
    query_type: Optional[str] = "hybrid"  # hybrid, qa
    scope: Optional[AskScope] = None  # answer only from this document / folder
    # Answer only from these sources (the UIs' source picker); omitted / empty = all sources
    sources: Optional[List[SourceSelector]] = None
    # Who is asking, per data source (planning/SOURCE-AUTH-LOGIN.md). A repository's documents
    # (Alfresco, Nuxeo, CMIS) are only answered from when an identity for their server is given
    # (here or as X-Alfresco-Ticket) unless <SOURCE>_QUERY_AUTH / SOURCE_QUERY_AUTH=optional.
    source_auth: Optional["SourceAuth"] = None

class TextIngestRequest(BaseModel):
    content: str
    source_name: Optional[str] = "sample-test"
    skip_graph: Optional[bool] = False


class SampleTestRequest(BaseModel):
    """Body for POST /api/test-sample (sample text comes from settings.sample_text)."""

    skip_graph: bool = False


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
async def _create_document_states_after_ingestion(processing_id: str, config_id: str, paths: List[str], data_source: str = "filesystem", skip_graph: bool = None):
    """
    Background task to create document_state records after ingestion completes.
    Delegates to PostIngestionStateManager for cleaner code organization.

    skip_graph: pass explicitly so state creation doesn't need the datasource_config row yet
    (lets it run before the sync detector is started — prevents re-ingest duplicates).
    """
    from post_ingestion_state import PostIngestionStateManager

    state_manager = PostIngestionStateManager(incremental_manager.state_manager.postgres_url)
    await state_manager.create_document_states_after_ingestion(
        processing_id, config_id, paths, data_source, skip_graph
    )




# ---------------------------------------------------------------------------
# Ingest endpoint helpers
# ---------------------------------------------------------------------------

def _build_ingest_kwargs(request) -> dict:
    """Extract datasource config dicts from an IngestRequest into backend kwargs."""
    kwargs: dict = {}
    if request.skip_graph:
        kwargs['skip_graph'] = request.skip_graph

    for attr, key in [
        ('cmis_config', 'cmis_config'),
        ('alfresco_config', 'alfresco_config'),
        ('web_config', 'web_config'),
        ('wikipedia_config', 'wikipedia_config'),
        ('youtube_config', 'youtube_config'),
        ('s3_config', 's3_config'),
        ('gcs_config', 'gcs_config'),
        ('azure_blob_config', 'azure_blob_config'),
        ('onedrive_config', 'onedrive_config'),
        ('sharepoint_config', 'sharepoint_config'),
        ('google_drive_config', 'google_drive_config'),
    ]:
        val = getattr(request, attr, None)
        if val:
            kwargs[key] = val.model_dump()

    # Nuxeo uses exclude_none so unset auth fields don't override source defaults.
    if request.nuxeo_config:
        kwargs['nuxeo_config'] = request.nuxeo_config.model_dump(exclude_none=True)

    if request.box_config:
        box_dict = request.box_config.model_dump()
        # Map UI parameter names to BoxSource expected names
        if 'folder_id' in box_dict and box_dict['folder_id']:
            box_dict['box_folder_id'] = box_dict.pop('folder_id')
        if 'developer_token' in box_dict and box_dict['developer_token']:
            box_dict['access_token'] = box_dict.pop('developer_token')
        kwargs['box_config'] = box_dict

    return kwargs


def _selected_node_ids(repo_config) -> List[str]:
    """Sorted node ids of a multi-select, or [] for a plain folder path.

    A multi-select arrives with ``path`` set to the selection's common parent, so url + path
    alone would give "files A and B" and later "file C" in the same folder one config_id --
    and the ON CONFLICT upsert would then replace the first selection's nodeDetails, silently
    dropping A and B from sync. A whole-folder sync of that parent would collide the same way.
    """
    ids = set(getattr(repo_config, "nodeIds", None) or [])
    for nd in getattr(repo_config, "nodeDetails", None) or []:
        nd_id = nd.get("id") if isinstance(nd, dict) else getattr(nd, "id", None)
        if nd_id:
            ids.add(nd_id)
    return ["nodes:" + ",".join(sorted(ids))] if ids else []


def _resolve_config_id(data_source: str, request, paths: Optional[List[str]]) -> str:
    """Return a stable uuid5 config_id derived from the datasource identity.

    The ID is deterministic across restarts — it is embedded in every doc's
    ref_doc_id and used for incremental-sync and CocoIndex per-app keying.
    """
    import uuid as _uuid_mod
    _DS_NAMESPACE = _uuid_mod.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
    parts = [data_source]
    if data_source == "alfresco" and request.alfresco_config:
        ac = request.alfresco_config
        # Deliberately NOT keyed on username. A synced folder is one datasource_config
        # regardless of who set it up: sync runs as a service identity, and who may read a
        # result is a query-time decision. Keying on the user would give the same repo+path a
        # different config_id per caller, so the same documents would be ingested repeatedly
        # under different ref_doc_ids.
        parts += [ac.url or "", ac.path or ""]
        parts += _selected_node_ids(ac)
    elif data_source == "nuxeo" and request.nuxeo_config:
        nc = request.nuxeo_config
        parts += [nc.url or "", nc.username or "", nc.path or ""]
        parts += _selected_node_ids(nc)
    elif data_source == "filesystem":
        parts += sorted(paths or [])
    elif data_source == "s3" and request.s3_config:
        sc = request.s3_config
        parts += [sc.bucket_name or "", sc.prefix or ""]
    elif data_source == "azure_blob" and request.azure_blob_config:
        ab = request.azure_blob_config
        parts += [
            ab.connection_string or ab.account_url or "",
            ab.account_name or "",
            ab.container_name or "",
            ab.prefix or "",
        ]
    elif data_source == "gcs" and request.gcs_config:
        gc = request.gcs_config
        parts += [gc.bucket_name or "", gc.prefix or ""]
    elif data_source == "onedrive" and request.onedrive_config:
        od = request.onedrive_config
        parts += [od.user_principal_name or ""]
    elif data_source == "sharepoint" and request.sharepoint_config:
        sp = request.sharepoint_config
        parts += [sp.site_name or "", sp.site_id or "", sp.folder_path or ""]
    elif data_source == "box" and request.box_config:
        bx = request.box_config
        parts += [bx.folder_id or ""]
    elif data_source == "google_drive" and request.google_drive_config:
        gd = request.google_drive_config
        parts += [gd.folder_id or ""]
    elif data_source == "cmis" and request.cmis_config:
        cm = request.cmis_config
        parts += [cm.url or "", cm.username or "", cm.folder_path or ""]
    elif data_source == "web" and request.web_config:
        parts += [str(getattr(request.web_config, "url", "") or "")]
    elif data_source == "wikipedia" and request.wikipedia_config:
        parts += [str(
            getattr(request.wikipedia_config, "query", "")
            or getattr(request.wikipedia_config, "page", "")
            or ""
        )]
    elif data_source == "youtube" and request.youtube_config:
        parts += [str(getattr(request.youtube_config, "url", "") or "")]
    return str(_uuid_mod.uuid5(_DS_NAMESPACE, "|".join(parts)))


def _coco_connection_params_for_request(data_source: str, request) -> Dict[str, Any]:
    """Build connection_params for CocoIndex bridge.ingest_source() from a UI request.

    Covers all 13 remote/URL sources.  ``filesystem`` is intentionally absent —
    it needs no connection_params and is routed to bridge.ingest_files().

    A source MISSING from this map fails in a way that points nowhere near here:
    the params come back empty, ``build_app_for_config`` then sets no
    ``_source_config_override``, ``flexible_app_main`` falls back to the
    ``{PREFIX}_*`` environment variables, and if those are unset the detector is
    built with no url -- which surfaces from inside CocoIndex's task as the
    opaque "Child component build cancelled".  Keep this list in step with
    ``_SOURCE_ENV_PREFIX`` in cocoindex_integration/pipeline/flexible_app.py.
    """
    cp: Dict[str, Any] = {}
    if data_source == "s3" and request.s3_config:
        cp = request.s3_config.model_dump(exclude_none=True)
    elif data_source == "alfresco" and request.alfresco_config:
        cp = request.alfresco_config.model_dump(exclude_none=True)
        if "stomp_port" not in cp:
            _sp = os.getenv("ALFRESCO_STOMP_PORT")
            if _sp:
                cp["stomp_port"] = int(_sp)
    elif data_source == "nuxeo" and request.nuxeo_config:
        # exclude_none so unset auth fields don't override source defaults,
        # matching how _build_ingest_kwargs passes nuxeo_config.
        cp = request.nuxeo_config.model_dump(exclude_none=True)
    elif data_source == "cmis" and request.cmis_config:
        cp = request.cmis_config.model_dump(exclude_none=True)
    elif data_source == "gcs" and request.gcs_config:
        cp = request.gcs_config.model_dump(exclude_none=True)
    elif data_source == "azure_blob" and request.azure_blob_config:
        cp = request.azure_blob_config.model_dump(exclude_none=True)
    elif data_source == "box" and request.box_config:
        cp = request.box_config.model_dump(exclude_none=True)
    elif data_source == "onedrive" and request.onedrive_config:
        cp = request.onedrive_config.model_dump(exclude_none=True)
    elif data_source == "sharepoint" and request.sharepoint_config:
        cp = request.sharepoint_config.model_dump(exclude_none=True)
    elif data_source == "google_drive" and request.google_drive_config:
        cp = request.google_drive_config.model_dump(exclude_none=True)
    elif data_source == "web" and request.web_config:
        cp = request.web_config.model_dump(exclude_none=True)
    elif data_source == "wikipedia" and request.wikipedia_config:
        cp = request.wikipedia_config.model_dump(exclude_none=True)
    elif data_source == "youtube" and request.youtube_config:
        cp = request.youtube_config.model_dump(exclude_none=True)
    return cp


def _build_sync_connection_params(
    data_source: str, request, paths: Optional[List[str]]
) -> tuple:
    """Return (connection_params, source_path) for incremental-sync registration.

    Returns ({}, None) when the datasource does not have enough config to register.
    """
    import json as _json
    connection_params: Dict[str, Any] = {}
    source_path: Optional[str] = None

    if data_source == "filesystem":
        if paths and os.path.isabs(paths[0]):
            connection_params = {'paths': paths}
            source_path = paths[0] if len(paths) == 1 else os.path.commonpath(paths)
        else:
            uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
            connection_params = {'paths': [uploads_dir]}
            source_path = uploads_dir

    elif data_source == "s3" and request.s3_config:
        connection_params = request.s3_config.model_dump(exclude_none=True)
        if not connection_params.get('region_name'):
            connection_params['region_name'] = os.getenv('S3_REGION_NAME', 'us-east-1')
            logger.info(f"Set S3 region_name to: {connection_params['region_name']}")
        if not connection_params.get('sqs_queue_url'):
            _sqs = os.getenv('S3_SQS_QUEUE_URL')
            if not _sqs:
                _s3cfg = os.getenv('S3_CONFIG')
                if _s3cfg:
                    try:
                        _sqs = _json.loads(_s3cfg).get('sqs_queue_url')
                    except Exception:
                        pass
            if _sqs:
                connection_params['sqs_queue_url'] = _sqs
                logger.info("S3 datasource: sqs_queue_url merged from env var into connection_params")
        source_path = f"s3://{connection_params.get('bucket_name', 'unknown')}"

    elif data_source == "alfresco" and request.alfresco_config:
        connection_params = request.alfresco_config.model_dump(exclude_none=True)
        # A pass-through login ticket must never become the stored sync credential. This row is
        # durable and re-read on every future sync, but an Alfresco ticket expires and cannot be
        # renewed from itself -- persisting one writes a config that looks fine and is already
        # dead. Sync needs a durable credential (a service account), and per-user access is a
        # query-time concern, not an ingest-time one.
        if connection_params.pop('ticket', None):
            if connection_params.get('username') and connection_params.get('password'):
                logger.warning(
                    "Alfresco sync: dropped the pass-through ticket from the stored connection "
                    "params; sync will use the supplied username/password instead."
                )
            else:
                # A caller holding only a ticket (an ACA/ADF extension, say) has no durable
                # credential to offer. Substitute the deployment's configured service account
                # so the caller still chooses *what* to sync while FG decides *as whom*.
                svc_user = os.getenv("ALFRESCO_SYNC_USERNAME") or os.getenv("ALFRESCO_USERNAME")
                svc_pass = os.getenv("ALFRESCO_SYNC_PASSWORD") or os.getenv("ALFRESCO_PASSWORD")
                if not (svc_user and svc_pass):
                    raise ValueError(
                        "Alfresco sync cannot be enabled with only a login ticket: a ticket "
                        "expires and cannot be renewed. Configure a service account via "
                        "ALFRESCO_SYNC_USERNAME/ALFRESCO_SYNC_PASSWORD (or "
                        "ALFRESCO_USERNAME/ALFRESCO_PASSWORD), supply a username and password "
                        "in the request, or ingest without enable_sync."
                    )
                connection_params['username'] = svc_user
                connection_params['password'] = svc_pass
                # auth_method stays "ticket": with a username/password it becomes acquire mode,
                # so the stored credential still is not resent on every request.
                logger.info(
                    "Alfresco sync: caller supplied only a ticket; storing the configured "
                    "service account (%s) as the sync credential instead.", svc_user
                )
        source_path = connection_params.get('path', '/unknown')
        if 'stomp_port' not in connection_params:
            stomp_port = os.getenv("ALFRESCO_STOMP_PORT")
            if stomp_port:
                connection_params["stomp_port"] = int(stomp_port)
                logger.info(f"Added ALFRESCO_STOMP_PORT={stomp_port} to datasource config")

    elif data_source == "nuxeo" and request.nuxeo_config:
        connection_params = request.nuxeo_config.model_dump(exclude_none=True)
        source_path = connection_params.get('path', '/unknown')

    elif data_source == "google_drive" and request.google_drive_config:
        connection_params = request.google_drive_config.model_dump(exclude_none=True)
        source_path = f"google_drive://{connection_params.get('folder_id', 'root')}"

    elif data_source == "gcs" and request.gcs_config:
        connection_params = request.gcs_config.model_dump(exclude_none=True)
        source_path = f"gs://{connection_params.get('bucket_name', 'unknown')}"

    elif data_source == "azure_blob" and request.azure_blob_config:
        connection_params = request.azure_blob_config.model_dump(exclude_none=True)
        source_path = f"azure://{connection_params.get('container_name', 'unknown')}"

    elif data_source == "box" and request.box_config:
        connection_params = request.box_config.model_dump(exclude_none=True)
        source_path = f"box://{connection_params.get('folder_id', '0')}"

    elif data_source == "onedrive" and request.onedrive_config:
        connection_params = request.onedrive_config.model_dump(exclude_none=True)
        source_path = f"onedrive://{connection_params.get('user_principal_name', 'unknown')}"

    elif data_source == "sharepoint" and request.sharepoint_config:
        connection_params = request.sharepoint_config.model_dump(exclude_none=True)
        source_path = f"sharepoint://{connection_params.get('site_name', 'unknown')}"

    return connection_params, source_path


def _ingest_registry_available() -> bool:
    """True when ingests can be recorded in datasource_config / document_state: the
    incremental system is up (ENABLE_INCREMENTAL_UPDATES + POSTGRES_INCREMENTAL_URL, and not
    PIPELINE_BACKEND=cocoindex, which keeps its own change tracking)."""
    return bool(incremental_manager and incremental_manager.is_initialized())


def _without_secrets(value: Any) -> Any:
    """Copy of a config with credential-like keys dropped (same markers the log redaction
    uses). An ingest-only record is never synced, so it needs no credentials -- only enough
    to identify what was ingested."""
    from flow_service import _SECRET_KEY_MARKERS
    if isinstance(value, dict):
        return {
            k: _without_secrets(v) for k, v in value.items()
            if str(k).lower().endswith("_path")
            or not any(m in str(k).lower() for m in _SECRET_KEY_MARKERS)
        }
    if isinstance(value, list):
        return [_without_secrets(v) for v in value]
    return value


def _record_ingest_only(data_source: str, request, paths: Optional[List[str]],
                        config_id: str, processing_id: str) -> None:
    """Record an ingest made without auto change sync: its datasource row now, its
    document_state rows once the ingest completes (in the background -- unlike the sync path
    there is no detector waiting on them, so the request need not)."""
    if data_source == "filesystem":
        params: Dict[str, Any] = {"paths": list(paths or [])}
    else:
        params = _without_secrets(_coco_connection_params_for_request(data_source, request))

    async def _run() -> None:
        try:
            await incremental_manager.register_ingest_only(
                source_type=data_source,
                source_name=f"{data_source}_ingest",
                connection_params=params,
                config_id=config_id,
                skip_graph=bool(request.skip_graph),
            )
            await _create_document_states_after_ingestion(
                processing_id=processing_id,
                config_id=config_id,
                paths=paths or [],
                data_source=data_source,
                skip_graph=bool(request.skip_graph),
            )
            await _take_over_other_ingest_copies(config_id)
        except Exception as e:
            logger.warning(f"Could not record ingest {processing_id} ({data_source}, {config_id}): {e}")

    asyncio.create_task(_run())


async def _take_over_other_ingest_copies(config_id: str, sync_takeover: bool = False) -> None:
    """Delete copies of this ingest's documents that an earlier ingest made through a
    DIFFERENT selection (so under another config_id and doc_id): files A+B, then A alone; or
    a file uploaded again in another batch. Runs after the new copy is in place. With
    ``sync_takeover`` (a sync just registered): other syncs' copies too, and those syncs give
    up the roots this one covers (_hand_over_roots)."""
    doc_ids = await incremental_manager.take_over_other_ingest_copies(config_id, sync_takeover)
    if doc_ids:
        from ingest.replace_existing import delete_doc_ids
        await delete_doc_ids(backend_instance.system, doc_ids)
    if sync_takeover:
        losers = {d.split(":", 1)[0] for d in doc_ids if ":" in d} - {config_id}
        if losers:
            await _hand_over_roots(config_id, losers)


async def _hand_over_roots(winner: str, losers: set) -> None:
    """Syncs that lost documents to a newly registered sync (``winner``) stop watching what it
    covers: each root of theirs that falls inside the winner's roots comes off their list; one
    left with no roots is retired (removal.retire_datasource) and its updater stopped, the
    others restart on the roots they keep."""
    from incremental_updates.ingest_status import Datasource, Item, relate
    from incremental_updates.removal import retire_datasource, trim_roots
    cm = incremental_manager.config_manager
    orch = getattr(incremental_manager, "orchestrator", None)
    win_cfg = await cm.get_config(winner)
    if win_cfg is None:
        return
    win = Datasource.from_config(win_cfg)
    for config_id in losers:
        try:
            cfg = await cm.get_config(config_id)
            if cfg is None or not getattr(cfg, "auto_sync", False):
                continue
            ds = Datasource.from_config(cfg)
            covered = [Item(r.path, r.is_folder, r.node_id) for r in ds.roots
                       if any(m.status == "synced" for m in relate(Item(r.path, r.is_folder, r.node_id), win, ds.recursive))]
            new_cp, left, did = trim_roots(cfg.connection_params, covered)
            if not did:
                continue
            if left:
                await cm.update_config(config_id, connection_params=new_cp)
                cfg = await cm.get_config(config_id)
                if orch is not None and cfg is not None:
                    await orch._handle_config_change({"operation": "update", "config": cfg})
                logger.info(f"Auto sync {config_id}: handed {len(covered)} root(s) over to {winner}")
            else:
                async with incremental_manager.state_manager.pool.acquire() as conn:
                    outcome = await retire_datasource(conn, config_id)
                if orch is not None:
                    await orch._handle_config_change({"operation": "delete", "config_id": config_id})
                logger.info(f"Auto sync {config_id}: all roots handed over to {winner} ({outcome})")
        except Exception as e:
            logger.warning(f"Auto sync {config_id}: could not hand roots over to {winner}: {e}")


async def _enable_incremental_sync(
    data_source: str,
    result: dict,
    config_id: str,
    request,
    paths: Optional[List[str]],
    inc_mgr,
    row_sync: Optional[dict] = None,
) -> None:
    """Register datasource for incremental sync after a successful ingest.

    ``row_sync`` (_plan_row_sync): only its "synced" rows become the sync's roots, and the
    documents of its "unsynced" rows are recorded with their auto sync off.

    Creates document_state rows SYNCHRONOUSLY before starting the detector so the
    detector's first scan finds all files already tracked (prevents duplicate ingest).
    ORDER MATTERS: document_state rows must exist before add_datasource_for_sync().
    """
    import time
    connection_params, _source_path = _build_sync_connection_params(data_source, request, paths)
    if not connection_params or not config_id:
        logger.warning(f"Could not enable sync for {data_source}: missing configuration")
        result['sync_enabled'] = False
        return

    unsynced = [_row_item(r) for r in (row_sync or {}).get("unsynced", [])]
    async with inc_mgr.state_manager.pool.acquire() as conn:
        was_ingest_only = (await conn.fetchval(
            "SELECT auto_sync FROM datasource_config WHERE config_id = $1", config_id)) is False
    if unsynced:
        from incremental_updates.removal import trim_roots
        trimmed, left, _ = trim_roots(connection_params, unsynced)
        if left:
            connection_params = trimmed

    processing_id = result['processing_id']
    logger.info(
        f"Creating document_state records synchronously for {data_source} "
        "before starting sync monitoring..."
    )
    await _create_document_states_after_ingestion(
        processing_id=processing_id,
        config_id=config_id,
        paths=paths or [],
        data_source=data_source,
        skip_graph=request.skip_graph,
    )
    logger.info(f"Document_state records created synchronously for {data_source}")
    if was_ingest_only:
        # Converting an ingest-only datasource: its rows were recorded with auto sync off
        from incremental_updates.removal import fetch_rows, select_rows, set_auto_sync
        async with inc_mgr.state_manager.pool.acquire() as conn:
            if row_sync and row_sync.get("synced"):
                rows = await fetch_rows(conn, [config_id])
                ids = [r.doc_id for m in select_rows([_row_item(r) for r in row_sync["synced"]], rows,
                                                     recursive=True) for r in m]
            else:
                ids = [r["doc_id"] for r in await conn.fetch(
                    "SELECT doc_id FROM document_state WHERE config_id = $1", config_id)]
            await set_auto_sync(conn, ids, True)
    if unsynced:
        await _turn_off_row_sync(config_id, unsynced, [_row_item(r) for r in row_sync["synced"]])

    # NOW start monitoring — detector's first scan finds files already in document_state.
    await inc_mgr.add_datasource_for_sync(
        source_type=data_source,
        source_name=f"{data_source}_{int(time.time())}",
        connection_params=connection_params,
        config_id=config_id,
        skip_graph=request.skip_graph,
    )
    logger.info(
        f"SUCCESS: Enabled incremental sync for {data_source}: {config_id}, "
        f"skip_graph={request.skip_graph}"
    )
    # Only now: the row has just become auto_sync = TRUE. Before registration a source being
    # switched from ingest-only to sync would still look ingest-only, and would wrongly hand
    # its documents to an overlapping sync.
    try:
        await _take_over_other_ingest_copies(config_id, sync_takeover=True)
    except Exception as e:
        logger.warning(f"Could not settle duplicate copies for {config_id}: {e}")
    result['sync_enabled'] = True
    result['config_id'] = config_id


async def _turn_off_row_sync(config_id: str, unsynced, synced) -> None:
    """Auto sync off for the documents of the rows not synced in a new auto sync -- before its
    detector starts. A document a synced row also stands for (a synced file in an unsynced
    folder) stays on."""
    from incremental_updates.removal import fetch_rows, select_rows, set_auto_sync
    async with incremental_manager.state_manager.pool.acquire() as conn:
        rows = await fetch_rows(conn, [config_id])
        keep = {r.doc_id for m in select_rows(synced, rows, recursive=True) for r in m}
        ids = [r.doc_id for m in select_rows(unsynced, rows, recursive=True) for r in m
               if r.doc_id not in keep]
        n = await set_auto_sync(conn, ids, False)
    logger.info(f"{config_id}: auto sync off for {n} document(s) of rows not synced")


def _register_row_sync(data_source: str, result: dict, config_id: str, request, paths,
                       row_sync: Optional[dict]) -> None:
    """_enable_incremental_sync for a per-row run, in the background."""
    async def _run() -> None:
        try:
            await _enable_incremental_sync(data_source, dict(result), config_id, request, paths,
                                           incremental_manager, row_sync)
        except Exception as e:
            logger.error(f"Could not enable auto sync for {config_id}: {e}", exc_info=True)

    asyncio.create_task(_run())


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Max time to wait for a CocoIndex live stream to finish at least one file before
# declaring the ingest failed.  Never inferred from file counts — cloud sources
# legitimately report 0 files (or chunk counts instead of file counts).
_LIVE_INGEST_TIMEOUT: float = _env_float("COCOINDEX_LIVE_INGEST_TIMEOUT", 600.0)

# For a *directory* registration the live stream keeps emitting file_done events
# for siblings after the first one.  Once the stream has been quiet this long, the
# directory is treated as fully processed.
_DIR_QUIET_SECONDS: float = _env_float("COCOINDEX_DIR_QUIET_SECONDS", 15.0)


async def _start_cocoindex_ingest(
    data_source: str,
    paths: Optional[List[str]],
    config_id: str,
    bridge_primary_ds: str,
    conn_params: Dict[str, Any],
    skip_graph: bool = False,
    enable_sync: bool = False,
) -> dict:
    """Register a background CocoIndex ingest task and return immediately.

    The background task (``_run_cocoindex_bg``) updates PROCESSING_STATUS as it
    progresses so the SSE stream can show per-file / per-stage advancement.
    Returns the initial ``result`` dict with ``processing_id`` and ``status="started"``.
    """
    from datetime import datetime as _dt

    _skip_graph = skip_graph
    _coco_pid = backend_instance._create_processing_id()
    _coco_paths = list(paths or [])
    _n_files = max(len(_coco_paths), 1)

    # Build the initial per-file pending list the UI's Process tab needs.
    _now_iso = _dt.now().isoformat()
    _file_progress_init = [
        {
            "index": _fi,
            "filename": Path(_fp).name,
            "filepath": str(_fp),
            # A directory (watch-folder registration) has no per-file event of
            # its own — the live stream emits file_done for its *children*.  The
            # completion barrier keys on filename, so without this flag the
            # directory entry could never be satisfied and the ingest hung for
            # the full live-wait timeout.
            "is_dir": os.path.isdir(str(_fp)),
            "status": "processing",
            "progress": 0,
            "phase": "cocoindex",
            "message": "CocoIndex pipeline running...",
            "started_at": _now_iso,
            "completed_at": None,
            "error": None,
        }
        for _fi, _fp in enumerate(_coco_paths)
    ] or [{
        "index": 0,
        "filename": data_source or "source",
        "filepath": data_source or "source",
        "status": "processing",
        "progress": 0,
        "phase": "cocoindex",
        "message": "CocoIndex pipeline running...",
        "started_at": _now_iso,
        "completed_at": None,
        "error": None,
    }]

    # Register as "started" immediately so the SSE stream has something to return.
    backend_instance._update_processing_status(
        _coco_pid, "started",
        f"CocoIndex: processing {_n_files} file(s)...",
        progress=5,
        files_completed=0, total_files=_n_files,
        file_progress=_file_progress_init,
    )

    # ── Filesystem routing inputs (see the route block in _run_cocoindex_bg) ──
    # Directories become their own CocoIndex app with their own watch root;
    # loose files keep going through the WATCH_DIR staging path.
    _dir_paths = [str(_p) for _p in _coco_paths if os.path.isdir(str(_p))]

    def _same_path(a: str, b: str) -> bool:
        """True when two paths name the same folder (case/sep-insensitive on Windows)."""
        if not a or not b:
            return False
        try:
            return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
                os.path.realpath(b)
            )
        except OSError:
            return False

    # If the requested folder IS the bridge's own WATCH_DIR, the primary .env app
    # already watches it — building a second app on the same root would process
    # every file twice.  Fall back to the staging path in that case.
    _bridge_watch_dir = getattr(cocoindex_bridge, "_source_dir", "") if cocoindex_bridge else ""
    _dirs_are_watch_dir = bool(_dir_paths) and all(
        _same_path(_d, _bridge_watch_dir) for _d in _dir_paths
    )
    if _dirs_are_watch_dir:
        logger.info(
            "CocoIndex ingest: %s is the primary WATCH_DIR — using the existing "
            "primary app instead of registering a duplicate source",
            _dir_paths[0],
        )

    async def _run_cocoindex_bg(
        bridge=cocoindex_bridge,
        pid=_coco_pid,
        fpaths=_coco_paths,
        ds=data_source,
        sg=_skip_graph,
        n=_n_files,
        fp_init=_file_progress_init,
        connection_params=conn_params,
        cfg_id=config_id,
        primary_ds=bridge_primary_ds,
        _enable_sync=enable_sync,
        dir_paths=_dir_paths,
        _dir_is_watch_dir=_dirs_are_watch_dir,
    ):
        """Background task: run CocoIndex bridge and update PROCESSING_STATUS.

        Postgres monitoring rows are written by the bridge's own monitor, not
        here.  This task used to open a second CocoIngestMonitor (its own asyncpg
        pool, per request) and log every progress event a second time, so each
        stage produced two cocoindex_ingest_log rows under two different run_ids.
        Passing ``run_id=pid`` down instead gives one row per event, keyed by the
        processing_id so DB rows join back to this UI job.
        """
        try:
            backend_instance._update_processing_status(
                pid, "processing",
                f"CocoIndex: indexing {n} file(s) — please wait...",
                progress=10,
                files_completed=0, total_files=n,
                file_progress=[{**f, "progress": 10} for f in fp_init],
            )

            # ── Per-file / per-stage progress bridge ──────────────────────────
            # CocoIndex emits dict events via the progress hook.  We translate
            # them into _update_processing_status so the Process tab shows real
            # per-file stage advancement instead of a single 10→100 jump.
            _stage_pct = {
                "downloading": 15, "downloaded": 25,
                "parsing": 35, "parsed": 50,
                "chunked": 60, "embedded": 68,
                "kg_extracting": 72, "kg_extracted": 78,
                "vector_indexing": 82, "graph_indexing": 86,
                "search_indexing": 90, "rdf_indexing": 93,
                "indexing_complete": 97,
                "synced": 97,  # legacy alias
            }
            _stage_msg = {
                "downloading": "Downloading...", "downloaded": "Downloaded",
                "parsing": "Parsing document...", "parsed": "Parsed",
                "chunked": "Chunked", "embedded": "Embedded",
                "kg_extracting": "Extracting knowledge graph...",
                "kg_extracted": "KG extraction complete",
                "vector_indexing": "Writing vector index...",
                "graph_indexing": "Writing property graph...",
                "search_indexing": "Writing search index...",
                "rdf_indexing": "Writing RDF graph...",
                "indexing_complete": "Indexes updated",
                "synced": "Writing to indexes...",
            }
            _fp_state: dict = {f["filename"]: dict(f) for f in fp_init}
            _fp_order: list = [f["filename"] for f in fp_init]
            _completed_names: set = set()
            _live_done = asyncio.Event()
            _ingest_job_finished = False
            # Wall-clock of the most recent CocoIndex progress event.  Used to
            # detect that a directory registration has stopped producing files.
            _last_event_at: float = _monotonic()
            _has_dir_entry = any(f.get("is_dir") for f in fp_init)

            def _finalize_ingest_status(
                *, msg: str | None = None, force_failed: bool = False
            ) -> None:
                nonlocal _ingest_job_finished
                if _ingest_job_finished:
                    return
                _ingest_job_finished = True
                _done_iso = _dt.now().isoformat()
                _done_n = len([
                    f for f in fp_init
                    if f["filename"] in _completed_names
                    or os.path.basename(f["filename"]) in _completed_names
                ])
                _any_failed = any(
                    _fp_state.get(f["filename"], {}).get("status") == "failed"
                    for f in fp_init
                )
                # NOTE: never decide success from file counts — cloud sources
                # legitimately report 0 files (or chunk counts instead).  Only an
                # explicit failure or a pipeline timeout marks the job failed.
                _final = "failed" if (_any_failed or force_failed) else "completed"
                _fp_done = []
                for f in fp_init:
                    _fe = dict(_fp_state.get(f["filename"], {
                        **f, "status": _final, "progress": 100,
                        "phase": "completed", "message": "Processing completed",
                        "completed_at": _done_iso,
                    }))
                    if _fe.get("status") in ("completed", "skipped"):
                        _fe["phase"] = "completed"
                        _fe["progress"] = 100
                    _fp_done.append(_fe)
                _status_msg = msg or (
                    f"CocoIndex: {_done_n}/{n} file(s) processed"
                    if _final == "completed"
                    else f"CocoIndex pipeline error: one or more files failed"
                )
                backend_instance._update_processing_status(
                    pid, _final, _status_msg,
                    progress=100 if _final == "completed" else 0,
                    files_completed=_done_n, total_files=n,
                    file_progress=_fp_done,
                )

            def _ingest_files_done() -> bool:
                for f in fp_init:
                    if f.get("is_dir"):
                        # Directory registration: satisfied once any child file
                        # has finished.  How long to keep collecting siblings is
                        # decided by the quiet-period wait in _wait_live_done().
                        if not _completed_names:
                            return False
                        continue
                    if not (
                        f["filename"] in _completed_names
                        or os.path.basename(f["filename"]) in _completed_names
                    ):
                        return False
                return True

            def _coco_progress(evt: dict) -> None:
                nonlocal _last_event_at
                _last_event_at = _monotonic()
                try:
                    # NOTE: no Postgres logging here — the bridge's monitor hook
                    # wraps this callback and writes the cocoindex_ingest_log row
                    # (once, under run_id=pid).  This callback is UI state only.
                    _fname = evt.get("file_name") or evt.get("file_path") or "source"
                    _ev = evt.get("event")
                    _entry = _fp_state.get(_fname)
                    if _entry is None:
                        _base = os.path.basename(_fname)
                        for _k, _v in _fp_state.items():
                            if _k == _base or os.path.basename(_k) == _base:
                                _entry = _v
                                break
                    if _entry is None:
                        # Cloud source file not in the initial list — add it.
                        _entry = {
                            "index": len(_fp_order),
                            "filename": _fname,
                            "filepath": evt.get("file_path", _fname),
                            "status": "processing", "progress": 10,
                            "phase": "cocoindex", "message": "Processing...",
                            "started_at": _dt.now().isoformat(),
                            "completed_at": None, "error": None,
                        }
                        _fp_state[_fname] = _entry
                        _fp_order.append(_fname)
                    if _ev == "file_done":
                        _st = evt.get("status", "completed")
                        _completed_names.add(_fname)
                        _completed_names.add(os.path.basename(_fname))
                        _entry.update({
                            "status": "completed" if _st in ("completed", "skipped") else "failed",
                            "progress": 100,
                            "phase": "indexing",
                            "message": (
                                # Transform finished; flexible TargetStateProvider sinks
                                # (vector/search/graph writes) may still be in flight.
                                "Writing indexes..." if _st == "completed"
                                else "Skipped (unchanged)" if _st == "skipped"
                                else _st.capitalize()
                            ),
                            "completed_at": _dt.now().isoformat(),
                        })
                        if _ingest_files_done():
                            # Signal transform complete only — do NOT finalize status
                            # here. Flexible sinks run after file_done; finalizing early
                            # lets hybrid search race ahead of vector writes (0 results).
                            _live_done.set()
                            return  # all transforms done — keep status at processing
                    else:  # file_stage
                        _stg = evt.get("stage", "")
                        _entry.update({
                            "status": "processing",
                            "progress": _stage_pct.get(_stg, _entry.get("progress", 10)),
                            "phase": _stg or _entry.get("phase", "cocoindex"),
                            "message": _stage_msg.get(_stg, _stg or "Processing..."),
                        })
                    _done = len([
                        f for f in fp_init
                        if f["filename"] in _completed_names
                        or os.path.basename(f["filename"]) in _completed_names
                    ])
                    _tot = max(len(_fp_order), n)
                    _overall = 10 + int(85 * _done / _tot) if _tot else 10
                    backend_instance._update_processing_status(
                        pid, "processing",
                        f"CocoIndex: {_done}/{_tot} file(s) — {_entry.get('message', '')}",
                        progress=min(_overall, 99),
                        files_completed=_done, total_files=_tot,
                        file_progress=[_fp_state[k] for k in _fp_order],
                    )
                except Exception as _pe:
                    logger.debug("coco progress cb error (ignored): %s", _pe)

            # Route to the appropriate bridge method.
            # ``ds == ""`` is short-circuited before this task is created, so only
            # "filesystem" and remote sources reach here.
            if ds == "filesystem" and dir_paths and not _dir_is_watch_dir:
                # A filesystem *directory* is a data source in its own right —
                # exactly like an S3 bucket or an Alfresco site — so it gets its
                # own coco.App with its own watch root, keyed by config_id.
                #
                # It must NOT go through ingest_files(): that copies each path
                # into WATCH_DIR, and shutil.copy2() on a directory raises, so
                # the whole registration failed with nothing staged.  Routing
                # here also means enable_sync starts a live stream on *this*
                # directory rather than on the primary .env WATCH_DIR — which is
                # what makes "watch any folder you point at" work under the
                # CocoIndex pipeline, matching the default pipeline's behaviour.
                #
                # ``paths`` carries every requested path (files and folders):
                # the flexible filesystem source and its detector both accept a
                # mixed list and walk directories recursively.
                _fs_params = {"paths": list(fpaths), "path": dir_paths[0]}
                coco_result = await bridge.ingest_source(
                    "filesystem", _fs_params,
                    config_id=cfg_id,
                    source_name=f"filesystem ({dir_paths[0]})",
                    skip_graph=sg,
                    enable_sync=_enable_sync,
                    progress_cb=_coco_progress,
                    run_id=pid,
                )
            elif ds == "filesystem":
                # Loose files (UI upload staging, or a folder that IS the primary
                # WATCH_DIR) — stage into WATCH_DIR and let the primary app pick
                # them up.
                coco_result = await bridge.ingest_files(
                    fpaths, skip_graph=sg, progress_cb=_coco_progress,
                    run_id=pid,
                )
            elif ds == primary_ds and not connection_params:
                # Same source type as primary .env source AND no explicit per-source
                # config from the UI — primary app already covers this; just update.
                coco_result = await bridge.update(
                    progress_cb=_coco_progress, run_id=pid,
                )
            else:
                # Different source, or same type but different UI config (e.g. a
                # different S3 bucket).  Build/run a dedicated app keyed by config_id.
                coco_result = await bridge.ingest_source(
                    ds, connection_params,
                    config_id=cfg_id,
                    source_name=f"{ds} ({cfg_id[:8]})" if cfg_id else ds,
                    skip_graph=sg,
                    enable_sync=_enable_sync,
                    progress_cb=_coco_progress,
                    run_id=pid,
                )

            # A failed bridge call must not be reported as a successful ingest.
            # Without this the job fell through to the completion message and the
            # UI said "Successfully ingested N document(s)!" for a run where the
            # CocoIndex app errored and wrote nothing.
            if coco_result.get("status") == "error":
                _err = str(coco_result.get("error") or "unknown error")
                logger.error(
                    "CocoIndex ingest %s: bridge reported failure: %s", pid, _err,
                )
                _finalize_ingest_status(
                    msg=f"CocoIndex pipeline error: {_err}", force_failed=True,
                )
                return

            # Live mode: ingest_files only stages files; processing runs in the
            # background live stream — wait for file_done progress events.
            if coco_result.get("live_deferred"):
                async def _wait_live_done() -> bool:
                    """Wait for the live stream.  True = nothing ever processed."""
                    _deadline = _monotonic() + _LIVE_INGEST_TIMEOUT
                    try:
                        await asyncio.wait_for(
                            _live_done.wait(),
                            timeout=max(1.0, _deadline - _monotonic()),
                        )
                    except asyncio.TimeoutError:
                        return True
                    if not _has_dir_entry:
                        return False
                    # Directory registration: siblings keep arriving after the
                    # first file_done.  Settle once the stream goes quiet rather
                    # than releasing on the first child.
                    while _monotonic() < _deadline:
                        _idle = _monotonic() - _last_event_at
                        if _idle >= _DIR_QUIET_SECONDS:
                            break
                        await asyncio.sleep(min(1.0, _DIR_QUIET_SECONDS - _idle))
                    return False

                if await _wait_live_done():
                    logger.error(
                        "CocoIndex live ingest %s: no file completed within %.0fs — "
                        "marking failed. Is the live stream running for this source?",
                        pid, _LIVE_INGEST_TIMEOUT,
                    )
                    _finalize_ingest_status(
                        msg=(
                            f"CocoIndex pipeline timed out after "
                            f"{_LIVE_INGEST_TIMEOUT:.0f}s — no file finished processing."
                        ),
                        force_failed=True,
                    )
                    return

            # Flexible TargetStateProvider sinks (vector/search/graph) run after
            # process_file emits file_done.  Wait until those writes finish so
            # search/QA immediately after ingest does not race an empty index.
            try:
                from cocoindex_integration.connectors.flexible.base import (
                    wait_targets_flushed as _wait_targets_flushed,
                )
                await _wait_targets_flushed(timeout=180.0)
            except Exception as _sink_exc:
                logger.debug(
                    "CocoIndex ingest %s: wait_targets_flushed skipped: %s",
                    pid, _sink_exc,
                )

            _done_iso = _dt.now().isoformat()
            _added = len([
                f for f in fp_init
                if f["filename"] in _completed_names
                or os.path.basename(f["filename"]) in _completed_names
            ])
            if not coco_result.get("live_deferred"):
                # The bridge returns flat, already document-level counters
                # (adds / deletes / unchanged / errors) — there is no "stats"
                # object in the result dict.  ``adds`` counts newly processed
                # documents; ``unchanged`` are memo hits, which still count as
                # successfully ingested from the caller's point of view.
                _reported = int(coco_result.get("adds") or 0)
                _added = max(_added, _reported)
                if not _added:
                    _added = n

            from ingest._helpers import generate_completion_message as _gen_completion_msg
            _cfg = getattr(backend_instance.system, "config", None)
            if _cfg is not None:
                _msg = _gen_completion_msg(_cfg, max(_added, n), skip_graph=sg)
                try:
                    # Import from the submodule that actually defines it, NOT
                    # ``from cocoindex_integration.pipeline import app`` — the
                    # package __init__ rebinds the name ``app`` to the coco.App
                    # instance, so that form yields an App (no such method) and
                    # the AttributeError was silently swallowed below.
                    from cocoindex_integration.pipeline.state import (
                        native_pg_write_skipped as _native_pg_write_skipped,
                    )
                    if _native_pg_write_skipped():
                        _pg = str(getattr(_cfg, "pg_graph_db", "none"))
                        _msg = (
                            f"Successfully ingested {max(_added, n)} document(s)! "
                            f"Vector index updated. "
                            f"Property graph write to {_pg} was skipped — "
                            f"database unreachable (see log)."
                        )
                except Exception:
                    pass
            else:
                _msg = f"Successfully processed {max(_added, n)} file(s)."

            if not _ingest_job_finished:
                _fp_done = []
                for f in fp_init:
                    _fe = dict(_fp_state.get(f["filename"], {
                        **f, "status": "completed", "progress": 100,
                        "phase": "completed", "message": "Processing completed",
                        "completed_at": _done_iso,
                    }))
                    if _fe.get("status") == "completed":
                        _fe["phase"] = "completed"
                        _fe["progress"] = 100
                    _fp_done.append(_fe)
                backend_instance._update_processing_status(
                    pid, "completed", _msg,
                    progress=100,
                    files_completed=_added, total_files=n,
                    file_progress=_fp_done,
                )
            logger.info("CocoIndex background task %s: completed", pid)
        except asyncio.CancelledError:
            logger.warning("CocoIndex background task %s: cancelled (shutdown)", pid)
            raise
        except Exception as _bg_exc:
            logger.error("CocoIndex background task %s: failed: %s", pid, _bg_exc)
            backend_instance._update_processing_status(
                pid, "failed",
                f"CocoIndex pipeline error: {_bg_exc}",
                progress=0,
                file_progress=[
                    {**f, "status": "failed", "error": str(_bg_exc)}
                    for f in fp_init
                ],
            )
        finally:
            try:
                # Clearing the hook here is REQUIRED: on the live-deferred path
                # bridge.update() deliberately leaves it installed and documents
                # this finally block as the owner of the cleanup.  Import from
                # pipeline.run directly — ``from ...pipeline import app`` returns
                # the coco.App instance (the package __init__ rebinds that name),
                # so the old form raised AttributeError into the bare except and
                # the hook leaked into every subsequent cycle.
                from cocoindex_integration.pipeline.run import (
                    set_progress_hook as _set_progress_hook,
                )
                _set_progress_hook(None)
            except Exception as _hook_exc:
                logger.debug(
                    "CocoIndex ingest %s: could not clear progress hook: %s",
                    pid, _hook_exc,
                )

    asyncio.create_task(_run_cocoindex_bg(), name=f"cocoindex-ingest-{_coco_pid}")

    if enable_sync:
        logger.info(
            "CocoIndex bridge: enable_sync=true acknowledged — "
            "CocoIndex tracks document state via LMDB automatically."
        )

    return {
        "processing_id": _coco_pid,
        "status": "started",
        "message": f"CocoIndex: processing {_n_files} file(s) in background",
        "pipeline_backend": "cocoindex",
    }


def _label_job(result: dict, data_source: str, request, paths) -> None:
    """Record what a job is and who started it, for GET /api/processing-status."""
    from backend import PROCESSING_STATUS
    entry = PROCESSING_STATUS.get((result or {}).get("processing_id") or "")
    if entry is None:
        return
    label = entry.get("label")
    if not label:
        repo = getattr(request, f"{data_source}_config", None)
        nodes = getattr(repo, "nodeDetails", None) or []
        label = (", ".join(nd.path for nd in nodes) if nodes
                 else getattr(repo, "path", None) or ", ".join(paths or []) or data_source)
    entry.update({"data_source": data_source, "label": str(label)[:200],
                  "owner": getattr(request, "owner", None)})


def _prepare_item_actions(data_source: str, request) -> dict:
    """Validate per-row actions and narrow the request's selection to the rows being ingested,
    so its config_id -- the datasource -- is that of those rows alone (a row being removed in
    the same run must not turn the selection into a different datasource). Returns the rows
    split by action."""
    from incremental_updates.ingest_status import FS_SOURCES, ROW_SOURCES, fs_key
    if data_source not in ROW_SOURCES:
        raise HTTPException(status_code=400,
                            detail=f"per-row actions are available for {', '.join(ROW_SOURCES)}, not {data_source}")
    if data_source in FS_SOURCES:
        # Filesystem / upload rows: each row's path is its file (an upload by name); its
        # document_state key (source_id) is the normalized path -- used as the row's id
        for a in request.item_actions:
            a.path = _fs_row_path(a.path)
            a.id = None if a.is_folder else fs_key(a.path)
    bad = sorted({a.action for a in request.item_actions} - set(ITEM_ACTIONS))
    if bad:
        raise HTTPException(status_code=400,
                            detail=f"unknown action(s) {', '.join(bad)}; use {', '.join(ITEM_ACTIONS)}")
    split = {a: [i for i in request.item_actions if i.action == a] for a in ITEM_ACTIONS}
    ingest_rows = split["ingest"] + split["ingest_no_graph"]
    if (split["remove_graph"] or split["remove_all"]) and not _ingest_registry_available():
        raise HTTPException(status_code=400,
                            detail="removing needs ENABLE_INCREMENTAL_UPDATES=true "
                                   "(document_state says what a row stands for)")

    if data_source in FS_SOURCES:
        keep = {fs_key(i.path) for i in ingest_rows}
        request.paths = [p for p in (request.paths or []) if fs_key(p) in keep] or None
    cfg_attr = f"{data_source}_config"
    cfg = getattr(request, cfg_attr, None)
    if cfg is not None and (cfg.nodeDetails or cfg.nodeIds):
        keep = {i.id for i in ingest_rows if i.id}
        setattr(request, cfg_attr, cfg.copy(update={
            "nodeDetails": [nd for nd in (cfg.nodeDetails or []) if nd.id in keep] or None,
            "nodeIds": [n for n in (cfg.nodeIds or []) if n in keep] or None,
        }))
    # The datasource's own skip_graph: on only when nothing in this run builds graphs.
    request.skip_graph = not split["ingest"]
    split["sync_changes"] = [i for i in request.item_actions if i.auto_sync is not None]
    # "ingest_rows": every row that is ingested (with graphs or not); "ingest" alone is only the
    # rows ingested with graphs -- they must not share a key, or a run whose rows are all
    # "search + vector only" looks like a removal-only run and registers no datasource.
    return {**split, "ingest_rows": ingest_rows}


async def _sync_datasources(data_source: str, url):
    """The auto sync datasources of this source (and repository, when ``url`` is given):
    (configs by config_id, Datasource list)."""
    from incremental_updates.ingest_status import Datasource, normalize_url
    await ensure_config_manager_ready()
    url = normalize_url(url)
    configs = [c for c in await incremental_manager.config_manager.get_ingest_status_configs()
               if getattr(c, "auto_sync", True) and c.source_type == data_source]
    syncs = [ds for ds in map(Datasource.from_config, configs) if not url or ds.url == url]
    return {c.config_id: c for c in configs}, syncs


def _fs_row_path(path: str) -> str:
    """The backend path of a filesystem / upload row: an uploaded file is named by its file name
    (saved under ./uploads, see /api/upload); anything else is a path already."""
    if path and not os.path.isabs(path) and not any(sep in path for sep in ("/", "\\")):
        safe = safe_upload_filename(path) or path
        return str((Path("./uploads") / safe).resolve())
    return path


def _row_item(row):
    from incremental_updates.ingest_status import Item, normalize_repo_path
    return Item(normalize_repo_path(row.path), row.is_folder, row.id)


async def _place_rows(data_source: str, request, rows) -> Optional[dict]:
    """Where each row being ingested belongs, so a selection stays one datasource and a document
    one copy: a file row a datasource already holds is refreshed under that datasource (an
    auto sync preferred over an ingest record); rows held by nobody are "new" and join the
    auto sync holding the others ("target"), or -- when no sync holds any -- start this run's
    own datasource as before. None when the registry is off."""
    from incremental_updates.ingest_status import Datasource, normalize_url
    from incremental_updates.removal import fetch_rows, select_rows
    if not rows or not _ingest_registry_available():
        return None
    await ensure_config_manager_ready()
    repo = getattr(request, f"{data_source}_config", None)
    url = normalize_url(getattr(repo, "url", None))
    configs = [c for c in await incremental_manager.config_manager.get_ingest_status_configs()
               if c.source_type == data_source]
    dss = {ds.config_id: ds for ds in map(Datasource.from_config, configs) if not url or ds.url == url}
    held: Dict[int, str] = {}
    if dss:
        async with incremental_manager.state_manager.pool.acquire() as conn:
            state_rows = await fetch_rows(conn, list(dss))
        for r in rows:
            if r.is_folder:  # a folder may span datasources: it is ingested as one, as before
                continue
            cfgs = {m.config_id for m in select_rows([_row_item(r)], state_rows, recursive=False)[0]}
            if cfgs:
                held[id(r)] = sorted([c for c in cfgs if dss[c].auto_sync] or cfgs)[0]
    syncs = sorted({c for c in held.values() if dss[c].auto_sync})
    return {"held": held, "new": [r for r in rows if id(r) not in held],
            "target": syncs[0] if syncs else None, "datasources": dss}


def _record_row_run(data_source: str, result: dict, paths, placement: dict) -> None:
    """Record a per-row run that started no datasource of its own (_place_rows): every
    document's row under the datasource that holds it, the new rows in the target sync --
    those sent with Auto Sync on become its roots, the others are kept with auto sync off --
    and a sync that now has a graph on some document builds graphs on its updates."""
    from incremental_updates.removal import add_roots

    async def _run() -> None:
        try:
            pid = result["processing_id"]
            target = placement["target"]
            fallback = target or next(iter(placement["held"].values()))
            await _create_document_states_after_ingestion(
                processing_id=pid, config_id=fallback, paths=paths or [], data_source=data_source)
            cm = incremental_manager.config_manager
            changed = set()
            if target and placement["new"]:
                synced = [r for r in placement["new"] if r.auto_sync is True]
                unsynced = [r for r in placement["new"] if r.auto_sync is not True]
                if unsynced:
                    await _turn_off_row_sync(target, [_row_item(r) for r in unsynced],
                                             [_row_item(r) for r in synced])
                if synced:
                    cfg = await cm.get_config(target)
                    cp, added = add_roots(cfg.connection_params, [_row_item(r) for r in synced])
                    if added:
                        await cm.update_config(target, connection_params=cp)
                        changed.add(target)
            # Graphs built for a document of a skip-graph sync: its updates must build them too
            # (documents ingested without graphs carry their own skip_graph)
            for config_id in placement.get("graphed") or ():
                ds = placement["datasources"].get(config_id)
                if ds is not None and ds.skip_graph:
                    await cm.update_config(config_id, skip_graph=False)
                    changed.add(config_id)
            orch = getattr(incremental_manager, "orchestrator", None)
            for config_id in changed:
                cfg = await cm.get_config(config_id)
                if orch is not None and cfg is not None and getattr(cfg, "auto_sync", False):
                    await orch._handle_config_change({"operation": "update", "config": cfg})
            for config_id in set(placement["held"].values()) | ({target} if target else set()):
                await _take_over_other_ingest_copies(config_id)
        except Exception as e:
            logger.error(f"Could not record per-row run {result.get('processing_id')}: {e}", exc_info=True)

    asyncio.create_task(_run())


async def _plan_row_sync(data_source: str, request, actions: dict) -> Optional[dict]:
    """Auto Sync on the rows being ingested. A row with ``auto_sync: true`` that no auto sync
    covers yet (none watches it or holds its documents) starts one: this run's datasource
    becomes an auto sync (``request.enable_sync``) watching those rows, and the other rows it
    ingests are recorded in it with their auto sync off. With ``enable_sync`` already set, every
    ingested row is synced except those sent with ``auto_sync: false``. None: no sync to start.
    Rows an existing sync covers are resumed / stopped there (_apply_row_sync) instead."""
    from incremental_updates.ingest_status import relate
    from incremental_updates.removal import fetch_rows, select_rows
    placement = actions.get("placement")
    rows = placement["new"] if placement else actions["ingest_rows"]
    if placement and placement["target"]:
        return None  # new rows join an existing sync (_record_row_run), no sync to start
    if not rows:
        return None
    if request.enable_sync:
        synced = [r for r in rows if r.auto_sync is not False]
    else:
        want = [r for r in rows if r.auto_sync is True]
        if not want or not _ingest_registry_available():
            return None
        repo = getattr(request, f"{data_source}_config", None)
        recursive = bool(getattr(repo, "recursive", False))
        _, syncs = await _sync_datasources(data_source, getattr(repo, "url", None))
        items = [_row_item(r) for r in want]
        held = [[]] * len(items)
        if syncs:
            async with incremental_manager.state_manager.pool.acquire() as conn:
                held = select_rows(items, await fetch_rows(conn, [ds.config_id for ds in syncs]),
                                   recursive=True)
        # Covered: a sync watches it (it is, or is inside, a root) -- or, for a file, a sync
        # holds it. A sync holding some files of a folder does not watch the folder.
        synced = [r for r, it, h in zip(want, items, held)
                  if not (h and not it.is_folder) and not any(m.status == "synced" for ds in syncs
                                                              for m in relate(it, ds, recursive))]
        if not synced:
            return None
        request.enable_sync = True
    unsynced = [r for r in rows if all(r is not s for s in synced)]
    return {"synced": synced, "unsynced": unsynced}


async def _apply_row_sync(data_source: str, url, off_rows, on_rows) -> list:
    """The Auto Sync column (incremental_updates/removal.py): stop or resume rows' auto sync.
    Stopping takes a datasource root off its root list, and resuming puts it back; a
    datasource left with no roots stops syncing -- ingest-only while documents of it are in a
    store, else deleted. Returns lines for the job message."""
    from incremental_updates.ingest_status import relate
    from incremental_updates.removal import (
        add_roots, fetch_rows, retire_datasource, select_rows, set_auto_sync, trim_roots,
    )
    if not incremental_manager or not incremental_manager.is_initialized():
        return []
    cm = incremental_manager.config_manager
    by_id, syncs = await _sync_datasources(data_source, url)
    lines: list = []
    if not syncs:
        return lines
    off = [_row_item(r) for r in off_rows]
    on = [_row_item(r) for r in on_rows]
    async with incremental_manager.state_manager.pool.acquire() as conn:
        rows = await fetch_rows(conn, [ds.config_id for ds in syncs])
        if off:
            ids = [r.doc_id for m in select_rows(off, rows, recursive=True) for r in m]
            n = await set_auto_sync(conn, ids, False)
            if n:
                lines.append(f"stopped auto sync for {n} document(s)")
        if on:
            ids = [r.doc_id for m in select_rows(on, rows, recursive=True) for r in m if not r.auto_sync]
            n = await set_auto_sync(conn, ids, True)
            if n:
                lines.append(f"resumed auto sync for {n} document(s)")
        changed = []
        for ds in syncs:
            cfg = by_id[ds.config_id]
            new_cp, left, did = trim_roots(cfg.connection_params, off) if off else (None, 1, False)
            if on:
                # A resumed row this sync holds documents of but no longer watches (it was taken
                # off the roots when stopped) goes back on them, so new files there sync again
                mine = [r for r in rows if r.config_id == ds.config_id]
                back = [it for it, m in zip(on, select_rows(on, mine, recursive=True))
                        if m and not any(x.status == "synced" for x in relate(it, ds, ds.recursive))]
                new_cp, added = add_roots(new_cp if did else cfg.connection_params, back)
                if added:
                    did, left = True, len(new_cp.get("nodeDetails") or []) or 1
            if not did:
                continue
            if left:
                await cm.update_config(ds.config_id, connection_params=new_cp)
                changed.append((ds.config_id, "trimmed"))
                lines.append(f"auto sync {ds.source_name or ds.config_id} now watches {left} item(s)")
            else:
                outcome = await retire_datasource(conn, ds.config_id)
                changed.append((ds.config_id, outcome))
                lines.append(f"auto sync {ds.source_name or ds.config_id} stopped"
                             + (" (its documents stay in the stores, now tracked as ingested)"
                                if outcome == "ingest-only" else " and removed"))
    # Restart (new roots) or stop the running syncs this changed
    orch = getattr(incremental_manager, "orchestrator", None)
    for config_id, outcome in changed:
        try:
            if orch is None:
                break
            if outcome == "trimmed":
                cfg = await cm.get_config(config_id)
                if cfg is not None:
                    await orch._handle_config_change({"operation": "update", "config": cfg})
            else:
                await orch._handle_config_change({"operation": "delete", "config_id": config_id})
        except Exception as e:
            logger.warning(f"Auto sync {config_id}: could not restart/stop its updater: {e}")
    return lines


async def _start_item_actions(data_source: str, request, paths, kwargs: dict, actions: dict,
                              row_sync: Optional[dict] = None) -> dict:
    """Start the per-row run: removals, then an ingest pass with graphs and one without."""
    from incremental_updates.ingest_status import Item
    from incremental_updates.removal import configured_stores

    repo = getattr(request, f"{data_source}_config", None)
    url = getattr(repo, "url", None)
    recursive = bool(getattr(repo, "recursive", False))

    async def remove_step() -> list:
        """One line per removal kind, e.g. "removed 5 document(s) from property graph and RDF
        stores"."""
        from incremental_updates.removal import store_names
        stores = configured_stores(settings)
        lines = []
        for action, targets in (("remove_all", ["vector", "search", "graph"]), ("remove_graph", ["graph"])):
            rows = actions[action]
            targets = [t for t in targets if stores[t]]
            if rows and targets:
                res = await _remove_items(data_source, url, recursive,
                                          [Item(r.path, r.is_folder, r.id) for r in rows], targets)
                if res["documents"]:
                    lines.append(f"removed {res['documents']} document(s) from "
                                 f"{store_names(res['targets_hit'] or targets, settings)}")
        return lines

    sync_off = [r for r in request.item_actions if r.auto_sync is False]
    # (rows starting this run's own sync are not resumed elsewhere: no sync covers them)
    starting = (row_sync or {}).get("synced", [])
    sync_on = [r for r in request.item_actions
               if r.auto_sync is True and all(r is not s for s in starting)]

    async def change_step() -> list:
        """Auto sync changes first (so a datasource retired here is ingest-only before the
        removals, which then drop it once it is empty), then the removals."""
        lines = await _apply_row_sync(data_source, url, sync_off, sync_on) if (sync_off or sync_on) else []
        removed = await remove_step()
        if removed and any(" stopped" in line for line in lines):
            # The same run removes the documents: just "auto sync X stopped", then the removal
            # (not "its documents stay in the stores", nor a per-document count first)
            lines = [line.split(" (its documents stay", 1)[0].replace(" and removed", "")
                     for line in lines if not line.startswith("stopped auto sync for ")]
        return lines + removed

    has_removals = bool(actions["remove_all"] or actions["remove_graph"] or sync_off or sync_on)

    cfg_key = f"{data_source}_config"
    base_cfg = kwargs.get(cfg_key) or {}
    # One pass per (datasource, graph setting): a row a datasource already holds is refreshed
    # under it, the new rows go to the target sync or this run's own datasource (_place_rows)
    placement = actions.get("placement") or {}
    held = placement.get("held") or {}
    default_cfg = placement.get("target") or kwargs.get("config_id")
    passes = []
    for action, skip in (("ingest", False), ("ingest_no_graph", True)):
        groups: Dict[Optional[str], list] = {}
        for r in actions[action]:
            groups.setdefault(held.get(id(r), default_cfg), []).append(r)
        for pass_cfg, rows in groups.items():
            sub = {}
            if base_cfg.get("nodeDetails") or base_cfg.get("nodeIds"):
                ids = {r.id for r in rows if r.id}
                sub[cfg_key] = {
                    **base_cfg,
                    "nodeDetails": [nd for nd in (base_cfg.get("nodeDetails") or []) if nd.get("id") in ids] or None,
                    "nodeIds": [n for n in (base_cfg.get("nodeIds") or []) if n in ids] or None,
                }
            entry = {"skip_graph": skip, "kwargs": sub, "config_id": pass_cfg}
            if data_source == "filesystem":
                from incremental_updates.ingest_status import fs_key
                ids = {fs_key(r.path) for r in rows}
                entry["paths"] = [p for p in (paths or []) if fs_key(p) in ids] or [r.path for r in rows]
            passes.append(entry)

    run_kwargs = {k: v for k, v in kwargs.items() if k not in ("skip_graph", "config_id")}
    label = ", ".join(r.path for r in request.item_actions)[:200]
    return await backend_instance.run_item_actions(
        data_source, passes, change_step if has_removals else None,
        paths=paths, config_id=kwargs.get("config_id"), label=label, **run_kwargs)


# Sources an auto sync can watch (incremental_updates/detectors); the others are ingested once
_SYNC_SOURCES = ("filesystem", "alfresco", "nuxeo", "s3", "gcs", "azure_blob", "onedrive",
                 "sharepoint", "box", "google_drive")


async def _datasource_row(data_source: str, request, paths):
    """A single-row source's datasource -- the whole S3 bucket / prefix, SharePoint folder, web
    page, ... -- by the same stable config_id its ingest gets: (config_id, config or None, its
    document_state rows)."""
    from incremental_updates.removal import fetch_rows
    config_id = _resolve_config_id(data_source, request, paths)
    if not _ingest_registry_available():
        return config_id, None, []
    await ensure_config_manager_ready()
    cfg = await incremental_manager.config_manager.get_config(config_id)
    async with incremental_manager.state_manager.pool.acquire() as conn:
        rows = await fetch_rows(conn, [config_id])
    return config_id, cfg, rows


async def _datasource_row_status(request) -> dict:
    """/api/sync/ingest-status for a single-row source: one row, the whole datasource, in the
    same shape as a repository row's (status, the datasource, which stores hold its documents,
    whether it is an auto sync)."""
    from incremental_updates.ingest_status import Datasource
    from incremental_updates.removal import configured_stores
    try:
        ireq = IngestRequest(data_source=request.data_source, **(request.source or {}))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid source for {request.data_source}: {e}")
    config_id, cfg, rows = await _datasource_row(request.data_source, ireq, ireq.paths)
    live = [r for r in rows if any(r.synced.values())]
    status = "synced" if cfg is not None and live else "removed" if cfg is not None and rows else "none"
    auto_sync = bool(cfg is not None and getattr(cfg, "auto_sync", False))
    label = request.items[0].path if request.items else config_id
    datasources = []
    if status != "none":
        ds = Datasource.from_config(cfg)
        datasources = [{"config_id": config_id, "source_name": ds.source_name, "root": label,
                        "recursive": False, "skip_graph": ds.skip_graph, "relation": "same",
                        "status": "synced" if live else status, "auto_sync": auto_sync}]
    item = {
        "id": None, "path": label, "is_folder": False, "status": status,
        "datasources": datasources,
        "indexed": {t: any(r.synced[t] for r in rows) for t in ("vector", "search", "graph")} if rows else None,
        "auto_sync": auto_sync,
        "documents": len(live),
    }
    return {"enabled": True, "stores": configured_stores(settings), "items": [item for _ in request.items] or [item]}


async def _datasource_row_actions(data_source: str, request, paths) -> Optional[dict]:
    """The processing tab's Search+Vector / Graphs / Auto Sync columns for a single-row source:
    its one row is the whole datasource. Store removals and stopping its auto sync are done here
    (as a job when nothing is ingested: that job is returned); an ingest -- with graphs, without,
    or to start the auto sync -- turns the request into the ordinary ingest of that datasource
    (``skip_graph`` / ``enable_sync`` set, ``item_actions`` cleared) and None is returned."""
    from incremental_updates.removal import (
        configured_stores, record_removal, retire_datasource, set_auto_sync, store_names,
    )
    from ingest.replace_existing import delete_doc_ids
    if len(request.item_actions) != 1:
        raise HTTPException(status_code=400,
                            detail=f"{data_source} has one row (the whole datasource): send one item action")
    row = request.item_actions[0]
    if row.action not in ITEM_ACTIONS:
        raise HTTPException(status_code=400,
                            detail=f"unknown action {row.action}; use {', '.join(ITEM_ACTIONS)}")
    if row.action in ("remove_graph", "remove_all") and not _ingest_registry_available():
        raise HTTPException(status_code=400,
                            detail="removing needs ENABLE_INCREMENTAL_UPDATES=true "
                                   "(document_state says what the datasource holds)")
    config_id, cfg, rows = await _datasource_row(data_source, request, paths)
    syncing = bool(cfg is not None and getattr(cfg, "auto_sync", False))
    want_sync = bool((row.auto_sync if row.auto_sync is not None else syncing) and data_source in _SYNC_SOURCES)
    has_graph = any(r.synced["graph"] for r in rows)

    async def changes() -> list:
        lines = []
        if syncing and not want_sync:
            async with incremental_manager.state_manager.pool.acquire() as conn:
                await set_auto_sync(conn, [r.doc_id for r in rows], False)
                outcome = await retire_datasource(conn, config_id)
            orch = getattr(incremental_manager, "orchestrator", None)
            if orch is not None:
                try:
                    await orch._handle_config_change({"operation": "delete", "config_id": config_id})
                except Exception as e:
                    logger.warning(f"Auto sync {config_id}: could not stop its updater: {e}")
            lines.append("auto sync stopped" + (" (its documents stay in the stores, now tracked as ingested)"
                                                if outcome == "ingest-only" else ""))
        targets = {"remove_all": ["vector", "search", "graph"], "remove_graph": ["graph"]}.get(row.action)
        if targets:
            stores = configured_stores(settings)
            targets = [t for t in targets if stores[t]]
            in_stores = [r for r in rows if any(r.synced[t] for t in targets)]
            if in_stores and targets:
                await delete_doc_ids(backend_instance.system, [r.doc_id for r in in_stores], targets)
                hit = [t for t in targets if any(r.synced[t] for r in in_stores)]
                async with incremental_manager.state_manager.pool.acquire() as conn:
                    await record_removal(conn, in_stores, targets, [config_id] if syncing and want_sync else [])
                lines.append(f"removed {len(in_stores)} document(s) from {store_names(hit or targets, settings)}")
        return lines

    if row.action in ("ingest", "ingest_no_graph") or (want_sync and not syncing):
        lines = await changes()  # (only a sync stop can precede an ingest)
        if lines:
            logger.info(f"{data_source} {config_id}: " + "; ".join(lines))
        request.item_actions = None
        request.skip_graph = (row.action == "ingest_no_graph") if row.action != "keep" else not has_graph
        request.enable_sync = want_sync
        return None
    result = await backend_instance.run_item_actions(data_source, [], changes, paths=paths,
                                                     config_id=config_id, label=row.path[:200])
    result["sync_enabled"] = want_sync
    return result


@app.post("/api/ingest")
async def ingest(request: IngestRequest):
    try:
        from flow_service import redact_config_for_log
        logger.info("Starting async document ingestion: %s", redact_config_for_log(request.model_dump()))
        logger.info(f"Data source: {request.data_source}, Paths: {request.paths}")

        data_source = request.data_source or str(settings.data_source)
        paths = request.paths

        if data_source == "alfresco" and not request.alfresco_config:
            # Never fall back to the backend's own ALFRESCO_* settings for someone else's ingest:
            # that fallback ignores `paths` (ALFRESCO_PATH, default "/" = the whole repository)
            # and authenticates as the service account (admin/admin when unset).
            raise HTTPException(
                status_code=400,
                detail="alfresco_config is required for an Alfresco ingest: url, path and the "
                       "caller's credentials (username/password, ticket, or oauth2)",
            )

        # A single-row source (S3, SharePoint, web, ...): its one row is the whole datasource
        from incremental_updates.ingest_status import ROW_SOURCES as _ROW_SOURCES
        if request.item_actions and data_source not in _ROW_SOURCES:
            early = await _datasource_row_actions(data_source, request, paths)
            if early is not None:  # removals / stopping its sync only: that job
                _label_job(early, data_source, request, paths)
                return early

        actions = None
        row_sync = None
        id_request = request  # the selection this run's own datasource id comes from
        id_paths = paths
        if request.item_actions:
            actions = _prepare_item_actions(data_source, request)
            paths = request.paths if data_source == "filesystem" else paths  # narrowed above
            id_paths = paths
            placement = await _place_rows(data_source, request, actions["ingest_rows"])
            if placement:
                actions["placement"] = placement
                if data_source == "filesystem" and placement["new"]:
                    from incremental_updates.ingest_status import fs_key
                    new_keys = {fs_key(r.path) for r in placement["new"]}
                    id_paths = [p for p in (paths or []) if fs_key(p) in new_keys]
                cfg_attr = f"{data_source}_config"
                cfg = getattr(request, cfg_attr, None)
                if cfg is not None and (cfg.nodeDetails or cfg.nodeIds) and placement["new"]:
                    # this run's own datasource is that of its new rows only
                    new_ids = {r.id for r in placement["new"] if r.id}
                    id_request = request.copy(update={cfg_attr: cfg.copy(update={
                        "nodeDetails": [nd for nd in (cfg.nodeDetails or []) if nd.id in new_ids] or None,
                        "nodeIds": [n for n in (cfg.nodeIds or []) if n in new_ids] or None,
                    })})
            if placement and not placement["target"]:
                # A row held by an ingest-only datasource that asks for Auto Sync: that datasource
                # becomes the sync (same id), its rows in this run are recorded in it as before
                convert = sorted({placement["held"][id(r)] for r in actions["ingest_rows"]
                                  if r.auto_sync is True and id(r) in placement["held"]})
                if convert:
                    moved = [r for r in actions["ingest_rows"] if placement["held"].get(id(r)) == convert[0]]
                    for r in moved:
                        del placement["held"][id(r)]
                    placement["new"] = moved + placement["new"]
                    placement["convert"] = convert[0]
            # Auto Sync on rows being ingested: may make this run's datasource an auto sync
            # (sets request.enable_sync), so before the cocoindex check and registration below
            row_sync = await _plan_row_sync(data_source, request, actions)

        # Build backend kwargs and stable config_id from datasource identity.
        kwargs = _build_ingest_kwargs(request)
        config_id = _resolve_config_id(data_source, id_request, id_paths)
        if actions is not None and (actions.get("placement") or {}).get("convert"):
            config_id = actions["placement"]["convert"]  # an ingest-only datasource becoming a sync
        # With the incremental registry available, every ingest -- not only an auto-sync one --
        # gets stable doc_ids and is recorded, so ingesting the same source again replaces what
        # the earlier run stored instead of adding a second copy.
        _record_ingest = _ingest_registry_available()
        if request.enable_sync or _record_ingest:
            kwargs['config_id'] = config_id
            logger.info(f"Stable config_id ({data_source}, sync={bool(request.enable_sync)}): {config_id}")

        # ── CocoIndex pipeline routing ─────────────────────────────────────────
        _bridge_primary_ds = (
            getattr(cocoindex_bridge, "_data_source", "filesystem")
            if cocoindex_bridge else ""
        )
        _used_cocoindex = False

        # Lazy-start bridge when DATA_SOURCE was empty at boot but user picked a
        # source through the UI (PIPELINE_BACKEND=cocoindex guard inside helper).
        if os.getenv("PIPELINE_BACKEND", "default").lower() == "cocoindex":
            await _ensure_cocoindex_bridge(
                fg_config=getattr(backend_instance.system, "config", None),
            )

        if cocoindex_bridge and data_source == "":
            # Empty data_source: nothing to start — already-running apps keep
            # everything up to date on their own live/poll loops.
            logger.info(
                "CocoIndex bridge active and data_source is empty — no new ingest "
                "started; existing apps continue their live/poll updates."
            )
            _used_cocoindex = True
            result = {
                "processing_id": None,
                "status": "noop",
                "message": "No data_source specified; existing CocoIndex sources keep updating.",
                "pipeline_backend": "cocoindex",
            }
        elif cocoindex_bridge and actions is not None:
            raise HTTPException(
                status_code=400,
                detail="per-row actions need the default or Langflow pipeline "
                       "(PIPELINE_BACKEND=cocoindex keeps its own state)",
            )
        elif cocoindex_bridge:
            _conn_params = _coco_connection_params_for_request(data_source, request)
            result = await _start_cocoindex_ingest(
                data_source=data_source,
                paths=paths,
                config_id=config_id,
                bridge_primary_ds=_bridge_primary_ds,
                conn_params=_conn_params,
                skip_graph=getattr(request, "skip_graph", False) or False,
                enable_sync=bool(getattr(request, "enable_sync", False)),
            )
            _used_cocoindex = True

        if actions is not None:
            result = await _start_item_actions(data_source, request, paths, kwargs, actions, row_sync)
        elif not _used_cocoindex:
            result = await backend_instance.ingest_documents(data_source=data_source, paths=paths, **kwargs)

        # A run that only removed: no datasource to register or record.
        if actions is not None and not actions["ingest_rows"]:
            result['sync_enabled'] = False
            _label_job(result, data_source, request, paths)
            return result

        # A run whose rows all belong to existing datasources (refreshed in place, new rows
        # joining a sync): no datasource of its own to register, only rows to record
        _placement = (actions or {}).get("placement")
        if _placement:
            # the datasources this run builds graphs in (rows ingested with graphs)
            _placement["graphed"] = {_placement["held"].get(id(r)) or _placement["target"]
                                     for r in actions["ingest"]} - {None}
        if _placement and (_placement["target"] or not _placement["new"]) and result.get("processing_id"):
            _record_row_run(data_source, result, paths, _placement)
            result['sync_enabled'] = bool(_placement["target"])
            _label_job(result, data_source, request, paths)
            return result

        # ── Incremental sync registration ──────────────────────────────────────
        if request.enable_sync and actions is not None and _ingest_registry_available():
            # Per-row run: register in the background (it waits for the job to finish), so the
            # request returns at once and the UI follows the job like any other
            _register_row_sync(data_source, result, config_id, request, paths, row_sync)
            result['sync_enabled'] = True
            result['config_id'] = config_id
        elif request.enable_sync and incremental_manager and incremental_manager.is_initialized():
            try:
                await _enable_incremental_sync(
                    data_source=data_source,
                    result=result,
                    config_id=config_id,
                    request=request,
                    paths=paths,
                    inc_mgr=incremental_manager,
                )
            except asyncio.CancelledError:
                logger.warning("ingest: sync registration cancelled (server shutting down)")
                raise HTTPException(status_code=503, detail="Server is shutting down")
            except Exception as e:
                logger.error(f"Error enabling incremental sync: {e}")
                import traceback
                traceback.print_exc()
                result['sync_enabled'] = False
        else:
            result['sync_enabled'] = False
            if _record_ingest and not _used_cocoindex and result.get('processing_id'):
                _record_ingest_only(data_source, request, id_paths, config_id, result['processing_id'])

        _label_job(result, data_source, request, paths)
        logger.info(f"Document ingestion started with ID: {result['processing_id']}")
        return result

    except HTTPException:
        raise
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

def safe_upload_filename(filename: str) -> Optional[str]:
    """Reduce a client-supplied upload filename to a bare, safe basename.

    Clients control the multipart ``filename`` field entirely, so it may contain
    directory separators ("../../etc/cron.d/x"), an absolute path ("/etc/x"), or a
    Windows drive prefix ("C:x") - all of which ``upload_dir / filename`` would
    happily follow outside the upload directory. ``ntpath.basename`` is used on every
    platform because it strips "/", "\\" and drive prefixes alike, so a Windows-style
    path is neutralized even when the server runs on Linux.

    Returns the safe basename, or None if nothing usable is left.
    """
    if not filename:
        return None

    # Null bytes would truncate the path at the OS layer
    if "\x00" in filename:
        return None

    name = ntpath.basename(filename).strip()

    # "." and ".." survive basename() but are not filenames
    if not name or name in (".", ".."):
        return None

    return name


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
        
        # Anything written must land directly inside this directory
        upload_root = upload_dir.resolve()

        for file in files:
            # Validate file type (basic validation)
            if not file.filename:
                continue

            # Strip any directory components a client may have put in the filename
            safe_name = safe_upload_filename(file.filename)
            if safe_name is None:
                skipped_files.append({
                    "filename": file.filename,
                    "reason": "Invalid or unsafe filename"
                })
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
            file_extension = Path(safe_name).suffix.lower()
            
            if file_extension not in supported_extensions:
                skipped_files.append({
                    "filename": file.filename,
                    "reason": f"Unsupported file type: {file_extension}"
                })
                continue
            
            # Save file to upload directory (overwrite if exists)
            file_path = (upload_root / safe_name).resolve()

            # Defense in depth: never write outside the upload directory, whatever
            # basename() left behind (e.g. a symlinked name already in uploads/)
            if file_path.parent != upload_root:
                skipped_files.append({
                    "filename": file.filename,
                    "reason": "Rejected: resolves outside the upload directory"
                })
                logger.warning(f"[WARN] Rejected upload path outside uploads dir: {file.filename!a}")
                continue

            # Write file content (content already read for size validation)
            # This will overwrite existing files with the same name
            with open(file_path, "wb") as buffer:
                buffer.write(content)
            
            uploaded_files.append({
                "filename": file.filename,
                "saved_as": file_path.name,  # sanitized name actually written to disk
                "path": str(file_path),
                "size": len(content)
            })
            
            logger.info(f"Uploaded file: {file.filename!a} -> {file_path}")
        
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

async def _scope_doc_ids(scope: "AskScope") -> List[str]:
    """The stable doc ids of the documents a scope stands for, and only those in a store now:
    a document by its node id, a folder by everything below its path (any depth). Through
    document_state, so it needs the incremental system (ENABLE_INCREMENTAL_UPDATES=true)."""
    from incremental_updates.ingest_status import Datasource, Item, normalize_url
    from incremental_updates.removal import fetch_rows, select_rows

    if not incremental_manager or not incremental_manager.is_initialized():
        if os.getenv("PIPELINE_BACKEND", "default").lower() == "cocoindex":
            # the incremental registry cannot run with CocoIndex, which keeps its own state
            raise HTTPException(status_code=400, detail=(
                "asking about one document or folder is not available with PIPELINE_BACKEND=cocoindex "
                "(it needs the incremental registry, which CocoIndex replaces with its own state)"))
        if os.getenv("ENABLE_INCREMENTAL_UPDATES", "").lower() == "true" and os.getenv("POSTGRES_INCREMENTAL_URL"):
            raise HTTPException(status_code=503, detail=(
                "asking about one document or folder needs the incremental system, which did not start "
                "(it could not connect to PostgreSQL at backend startup -- see the backend log). "
                "Check PostgreSQL is up, then restart the backend"))
        raise HTTPException(status_code=400,
                            detail="asking about one document or folder needs ENABLE_INCREMENTAL_UPDATES=true "
                                   "and POSTGRES_INCREMENTAL_URL")
    if not (scope.node_id or scope.path):
        raise HTTPException(status_code=400, detail="scope needs a node_id or a path")
    await ensure_config_manager_ready()
    url = normalize_url(scope.url)
    config_ids = [
        ds.config_id for ds in map(Datasource.from_config,
                                   await incremental_manager.config_manager.get_ingest_status_configs())
        if ds.source_type == scope.data_source and (not url or ds.url == url)
    ]
    if not config_ids:
        return []
    async with incremental_manager.state_manager.pool.acquire() as conn:
        rows = await fetch_rows(conn, config_ids)
    item = Item(scope.path or "", scope.is_folder, None if scope.is_folder else scope.node_id)
    matched = select_rows([item], rows, recursive=True)[0]
    return sorted({r.doc_id for r in matched if r.synced["vector"] or r.synced["search"] or r.synced["graph"]})


async def _candidate_doc_ids(query: str, within: Optional[List[str]] = None) -> List[str]:
    """The documents a retrieval finds for ``query``: what a permission check has to look at.
    ``within`` (a scope / the picked sources) prefilters the retrieval inside the stores, so only
    the search results from those documents are checked, not every document they stand for."""
    from retriever_setup import setup_hybrid_retriever
    from scope_filter import build_scoped_retriever, node_doc_id
    from llama_index.core.schema import QueryBundle
    system = backend_instance.system
    if within is not None:
        if not within:
            return []
        retriever = build_scoped_retriever(system, within)
    else:
        if not system.hybrid_retriever:
            setup_hybrid_retriever(system)
        retriever = system.hybrid_retriever
    if not retriever:
        return []
    nodes = await retriever.aretrieve(QueryBundle(query_str=query))
    return list(dict.fromkeys(d for d in (node_doc_id(n) for n in nodes) if d))


_REPO_SOURCES = ("alfresco", "nuxeo", "cmis")
_MICROSOFT_SOURCES = ("sharepoint", "onedrive")
_BOX_SOURCES = ("box",)
_GOOGLE_SOURCES = ("google_drive", "gcs")
_AZURE_SOURCES = ("azure_blob",)
_S3_SOURCES = ("s3",)
# Sources whose doc ids carry no repository id: the check finds it in the registry (Box, Drive:
# document_state.source_id) or in the doc id itself (GCS: "<config_id>:<bucket>/<object>")
_ID_SOURCES = _BOX_SOURCES + _GOOGLE_SOURCES + _AZURE_SOURCES + _S3_SOURCES
_SOURCE_URL_ENV = {"alfresco": "ALFRESCO_URL", "nuxeo": "NUXEO_URL", "cmis": "CMIS_URL",
                   "microsoft": "MICROSOFT_AUTH_TENANT_ID"}
_auth_providers_cache: Dict[str, Any] = {"at": 0.0, "value": None}


def _governed_sources() -> tuple:
    """The data sources whose documents are permission-checked: Alfresco, Nuxeo, CMIS, and
    SharePoint + OneDrive / Box once Microsoft / Box sign-in is configured
    (MICROSOFT_AUTH_CLIENT_ID / BOX_AUTH_CLIENT_ID) -- without it nobody could sign in, so their
    documents stay visible as before."""
    from sources.azure_auth import config as azure_config
    from sources.box_auth import config as box_config
    from sources.google_auth import config as google_config
    from sources.microsoft_auth import config as microsoft_config
    from sources.s3_auth import enabled as s3_enabled
    return (_REPO_SOURCES + (_MICROSOFT_SOURCES if microsoft_config() else ())
            + (_BOX_SOURCES if box_config() else ()) + (_GOOGLE_SOURCES if google_config() else ())
            + (_AZURE_SOURCES if azure_config() else ()) + (_S3_SOURCES if s3_enabled() else ()))


def _source_default_url(source: str) -> str:
    """The server a source's credential / document is assumed to belong to when it names none
    (for SharePoint / OneDrive: the Microsoft tenant)."""
    from permission_filter import auth_source
    if auth_source(source) == "box":
        from sources.box_auth import BOX_SERVER
        return BOX_SERVER
    if auth_source(source) == "google":
        from sources.google_auth import GOOGLE_SERVER
        return GOOGLE_SERVER
    if auth_source(source) == "azure":
        from sources.azure_auth import AZURE_SERVER
        return AZURE_SERVER
    if auth_source(source) == "s3":
        from sources.s3_auth import S3_SERVER
        return S3_SERVER
    return (os.getenv(_SOURCE_URL_ENV.get(auth_source(source), "")) or "").strip()


async def _registry_datasources() -> list:
    """(Datasource, connection_params) for every datasource with documents in the stores; [] without the registry."""
    if not incremental_manager or not incremental_manager.is_initialized():
        return []
    from incremental_updates.ingest_status import Datasource
    await ensure_config_manager_ready()
    return [(Datasource.from_config(cfg), dict(getattr(cfg, "connection_params", None) or {}))
            for cfg in await incremental_manager.config_manager.get_ingest_status_configs()]


def _datasource_server(ds, params: Dict[str, Any]) -> str:
    """The server a datasource's documents are checked on: its url, or for SharePoint / OneDrive
    its Microsoft tenant (else the source's configured default)."""
    if ds.source_type in _MICROSOFT_SOURCES:
        return (params.get("tenant_id") or "").strip() or _source_default_url(ds.source_type)
    if ds.source_type in _ID_SOURCES:
        return _source_default_url(ds.source_type)
    return ds.url or _source_default_url(ds.source_type)


def _azure_account_url(params: Dict[str, Any]) -> str:
    """An Azure Blob datasource's storage account URL: account_url, else from account_name or the
    connection string's AccountName (the public blob endpoint)."""
    url = (params.get("account_url") or "").strip().rstrip("/")
    if url:
        return url
    name = (params.get("account_name") or "").strip()
    if not name:
        import re as _re
        m = _re.search(r"AccountName=([^;]+)", params.get("connection_string") or "")
        name = m.group(1) if m else ""
    return f"https://{name}.blob.core.windows.net" if name else ""


def _query_auth_required(source: str) -> bool:
    """``<SOURCE>_QUERY_AUTH`` (e.g. NUXEO_QUERY_AUTH), else ``SOURCE_QUERY_AUTH``, else required.
    required: a question with no identity for that source is answered without its documents.
    optional: such a question sees them (the pre-0.8.5 behaviour, for a backend only trusted
    callers can reach)."""
    value = os.getenv(f"{source.upper()}_QUERY_AUTH") or os.getenv("SOURCE_QUERY_AUTH") or "required"
    return value.strip().lower() != "optional"


async def _auth_providers(max_age: float = 30.0) -> List[Dict[str, Any]]:
    """The sign-ins the stored content needs (planning/SOURCE-AUTH-LOGIN.md): one entry per
    repository server (Alfresco, Nuxeo, CMIS) whose documents in the stores are permission-checked.
    With the incremental registry this is exact (document_state rows with a repository doc id);
    without it nothing records what is stored, so each configured ALFRESCO_URL / NUXEO_URL /
    CMIS_URL is listed with ``documents: None`` (unknown). Cached for ``max_age`` seconds."""
    import time as _time
    from permission_filter import LABELS, SCHEMES, auth_source, server_key
    now = _time.monotonic()
    if _auth_providers_cache["value"] is not None and now - _auth_providers_cache["at"] < max_age:
        return _auth_providers_cache["value"]

    def entry(source: str, url: str, documents: Optional[int]) -> Dict[str, Any]:
        methods = ["popup"] if source in ("microsoft", "box", "google", "azure") else ["basic"]
        if source == "alfresco" and os.getenv("ALFRESCO_OAUTH2_CLIENT_ID"):
            methods.append("oauth2")
        return {"source": source, "label": LABELS[source], "url": url, "methods": methods,
                "documents": documents, "required": _query_auth_required(source)}

    providers: List[Dict[str, Any]] = []
    governed = _governed_sources()
    if incremental_manager and incremental_manager.is_initialized():
        await ensure_config_manager_ready()
        counts = await incremental_manager.config_manager.count_governed_documents_by_config(list(SCHEMES.values()))
        if any(s in governed for s in _ID_SOURCES):
            # Box / Drive / GCS doc ids carry no repository scheme: all of such a datasource's count
            all_counts = await incremental_manager.config_manager.count_documents_by_config()
            id_cfgs = {ds.config_id for ds, _ in await _registry_datasources() if ds.source_type in _ID_SOURCES}
            counts = {**counts, **{c: n for c, n in all_counts.items() if c in id_cfgs}}
        # (sign-in source, server key) -> [url as given, documents, {data source: documents}]
        per_server: Dict[tuple, List[Any]] = {}
        for ds, params in await _registry_datasources():
            if ds.source_type in governed and counts.get(ds.config_id):
                auth = auth_source(ds.source_type)  # SharePoint / OneDrive -> one Microsoft 365 sign-in
                url = _datasource_server(ds, params)
                slot = per_server.setdefault((auth, server_key(auth, url)), [url, 0, {}])
                slot[1] += counts[ds.config_id]
                slot[2][ds.source_type] = slot[2].get(ds.source_type, 0) + counts[ds.config_id]
        providers = []
        for (s, _), (url, n, by_source) in per_server.items():
            p = entry(s, url, n)
            if s in ("microsoft", "google"):
                # one sign-in covers these: the UIs name them ("SharePoint 2 docs · OneDrive 1 doc")
                p["services"] = [{"source": src, "label": LABELS.get(src, src), "documents": docs}
                                 for src, docs in sorted(by_source.items())]
            providers.append(p)
    else:
        # without the registry SharePoint / OneDrive documents carry no repository ids: not governed
        providers = [entry(s, _source_default_url(s), None)
                     for s in _REPO_SOURCES if _source_default_url(s)]
    _auth_providers_cache.update(at=now, value=providers)
    return providers


def _as_list(value) -> list:
    return [] if value is None else value if isinstance(value, list) else [value]


async def _identities(request: "QueryRequest", ticket: Optional[str] = None,
                      ticket_url: Optional[str] = None) -> list:
    """The asker's identities (permission_filter.Identity), one per repository server: the
    X-Alfresco-Ticket header (KG Spaces; X-Alfresco-Url names its server), then every entry of the
    request's source_auth.alfresco / .nuxeo / .cmis. A credential that names no url belongs to
    that source's configured server (ALFRESCO_URL / NUXEO_URL / CMIS_URL)."""
    from permission_filter import Identity, _rest_base
    from sources.alfresco_auth import alfresco_authorization
    from sources.nuxeo_auth import nuxeo_headers
    from sources.cmis_auth import cmis_headers
    out = []
    if ticket and ticket.strip():
        out.append(Identity("alfresco", (ticket_url or "").strip() or _source_default_url("alfresco"),
                            {"Authorization": alfresco_authorization("", "ticket", ticket=ticket.strip())}))
    sa = request.source_auth
    if not sa:
        return out
    try:
        for ac in _as_list(sa.alfresco):
            url = (ac.url or _source_default_url("alfresco")).strip()
            header = await asyncio.to_thread(
                alfresco_authorization, _rest_base(url), ac.auth_method, ac.username or "",
                ac.password or "", ac.ticket, ac.oauth2.model_dump(exclude_none=True) if ac.oauth2 else None)
            if header:
                out.append(Identity("alfresco", url, {"Authorization": header}))
        for nc in _as_list(sa.nuxeo):
            headers = nuxeo_headers(nc.auth_method, nc.username or "", nc.password or "", nc.token,
                                    nc.oauth2.model_dump(exclude_none=True) if nc.oauth2 else None)
            if headers:
                out.append(Identity("nuxeo", (nc.url or _source_default_url("nuxeo")).strip(), headers))
        for cc in _as_list(sa.cmis):
            headers = cmis_headers(cc.auth_method, cc.username or "", cc.password or "", cc.ticket, cc.token)
            if headers:
                out.append(Identity("cmis", (cc.url or _source_default_url("cmis")).strip(), headers))
        for mc in _as_list(sa.microsoft):
            from sources.microsoft_auth import tenant_of
            tenant = (mc.url or tenant_of(mc.access_token) or _source_default_url("microsoft")).strip()
            out.append(Identity("microsoft", tenant, {"Authorization": f"Bearer {mc.access_token}"}))
        for sc in _as_list(sa.s3):
            from permission_filter import S3_TOKEN_HEADER
            out.append(Identity("s3", (sc.url or _source_default_url("s3")).strip(), {S3_TOKEN_HEADER: sc.token}))
        for zc in _as_list(sa.azure):
            from sources.azure_auth import storage_headers
            out.append(Identity("azure", (zc.url or _source_default_url("azure_blob")).strip(),
                                storage_headers(zc.access_token)))
        for gc in _as_list(sa.google):
            out.append(Identity("google", (gc.url or _source_default_url("google_drive")).strip(),
                                {"Authorization": f"Bearer {gc.access_token}"}))
        for bc in _as_list(sa.box):
            out.append(Identity("box", (bc.url or _source_default_url("box")).strip(),
                                {"Authorization": f"Bearer {bc.access_token}"}))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return out


def _trusted_client(key: Optional[str]) -> bool:
    """The request comes from a client the backend trusts to decide its own filtering (the MCP
    server): X-Trusted-Client-Key matches TRUSTED_CLIENT_KEY. Such a question is filtered only for
    the sources it brings credentials for; with none it sees everything. Unset key: nobody is."""
    import secrets as _secrets
    expected = (os.getenv("TRUSTED_CLIENT_KEY") or "").strip()
    return bool(expected and key and _secrets.compare_digest(expected, key.strip()))


async def _readable(doc_ids: List[str], identities: list, trusted: bool = False):
    """``doc_ids`` the asker may read (permission_filter.py) -> permission_filter.Readable. Each
    governed document is checked on the server its datasource ingested it from (the registry's
    url, else that source's configured URL), with the asker's identity for that server."""
    from permission_filter import CredentialRefused, auth_source, config_id_of, readable_doc_ids
    urls: Dict[str, str] = {}
    contexts: Dict[str, Dict[str, str]] = {}  # what a SharePoint / OneDrive check needs
    datasources = await _registry_datasources()
    governed = _governed_sources()
    # Box / Drive documents keep their path doc ids: their file id is document_state.source_id;
    # a GCS doc id is "<config_id>:<bucket>/<object>"
    id_refs: Dict[str, tuple] = {}
    id_types = {ds.config_id: ds.source_type for ds, _ in datasources
                if ds.source_type in _ID_SOURCES and ds.source_type in governed}
    if id_types:
        from incremental_updates.removal import fetch_rows
        async with incremental_manager.state_manager.pool.acquire() as conn:
            for r in await fetch_rows(conn, list(id_types)):
                kind = id_types[r.config_id]
                if kind == "s3":  # "<config_id>:s3://<bucket>/<key>"
                    i = r.doc_id.find("s3://")
                    if i >= 0 and "/" in r.doc_id[i + 5:]:
                        id_refs[r.doc_id] = (kind, r.doc_id[i + 5:])
                elif kind in ("gcs", "azure_blob"):  # "<bucket|container>/<object|blob>"
                    item = r.doc_id.split(":", 1)[1] if ":" in r.doc_id else ""
                    if "/" in item:
                        id_refs[r.doc_id] = (kind, item)
                elif r.source_id:
                    id_refs[r.doc_id] = (kind, r.source_id)

    def cfg_of(d: str) -> str:
        return config_id_of(d) or (d.split(":", 1)[0] if ":" in d else "")

    for ds, params in datasources:
        server = _datasource_server(ds, params)
        if server:
            urls[ds.config_id] = server
        if ds.source_type in _MICROSOFT_SOURCES:
            contexts[ds.config_id] = {k: params[k] for k in ("site_name", "site_id", "user_principal_name")
                                      if params.get(k)}
        if ds.source_type in _AZURE_SOURCES:
            contexts[ds.config_id] = {"account_url": _azure_account_url(params)}
        if ds.source_type in _S3_SOURCES:
            contexts[ds.config_id] = {"region": (params.get("region_name") or "").strip()}
    try:
        return await readable_doc_ids(doc_ids, identities, lambda d: urls.get(cfg_of(d)),
                                      {auth_source(s): _source_default_url(s) for s in governed},
                                      (lambda s: False) if trusted else _query_auth_required, governed,
                                      lambda d: contexts.get(cfg_of(d)), lambda d: id_refs.get(d))
    except PermissionError as e:
        # X-Auth-Source / X-Auth-Url name the sign-in to renew, when known
        headers = ({"X-Auth-Source": e.source, "X-Auth-Url": e.url}
                   if isinstance(e, CredentialRefused) else None)
        raise HTTPException(status_code=401, detail=str(e), headers=headers)


_SOURCE_TYPE_LABELS = {
    "alfresco": "Alfresco", "nuxeo": "Nuxeo", "cmis": "CMIS", "filesystem": "Files", "upload": "Uploads",
    "s3": "Amazon S3", "gcs": "Google Cloud Storage", "azure_blob": "Azure Blob", "onedrive": "OneDrive",
    "sharepoint": "SharePoint", "box": "Box", "google_drive": "Google Drive", "web": "Web",
    "wikipedia": "Wikipedia", "youtube": "YouTube",
}


async def _source_groups() -> Optional[List[Dict[str, Any]]]:
    """The sources that have documents in the stores, one per data source type and server, with
    their datasources' config_ids; None without the incremental registry (nothing records it)."""
    if not incremental_manager or not incremental_manager.is_initialized():
        return None
    from permission_filter import auth_source, server_key
    await ensure_config_manager_ready()
    counts = await incremental_manager.config_manager.count_documents_by_config()
    governed = _governed_sources()
    groups: Dict[tuple, Dict[str, Any]] = {}
    for ds, params in await _registry_datasources():
        if not counts.get(ds.config_id):
            continue
        gated = ds.source_type in governed
        url = ds.url or (_source_default_url(ds.source_type) if ds.source_type in _REPO_SOURCES else "")
        g = groups.setdefault((ds.source_type, server_key(ds.source_type, url)), {
            "source": ds.source_type, "label": _SOURCE_TYPE_LABELS.get(ds.source_type, ds.source_type),
            "url": url or None, "documents": 0, "login_gated": gated,
            # the sign-in that unlocks it: SharePoint / OneDrive -> "microsoft" on its tenant
            "auth_source": auth_source(ds.source_type) if gated else None,
            "auth_url": _datasource_server(ds, params) if gated else None,
            "config_ids": [],
        })
        g["documents"] += counts[ds.config_id]
        g["config_ids"].append(ds.config_id)
    return sorted(groups.values(), key=lambda g: (g["label"].lower(), g["url"] or ""))


async def _selected_doc_ids(selectors: List["SourceSelector"]) -> List[str]:
    """The stable doc ids in the stores from the selected sources (type, optionally one server)."""
    from incremental_updates.removal import fetch_rows
    from permission_filter import server_key
    groups = await _source_groups()
    if groups is None:
        raise HTTPException(status_code=400, detail=(
            "picking sources needs the incremental registry (ENABLE_INCREMENTAL_UPDATES=true and "
            "POSTGRES_INCREMENTAL_URL): nothing else records which source a document came from"))
    config_ids = [cid for g in groups for sel in selectors
                  if g["source"] == sel.source
                  and (not sel.url or server_key(g["source"], g["url"]) == server_key(sel.source, sel.url))
                  for cid in g["config_ids"]]
    if not config_ids:
        return []
    async with incremental_manager.state_manager.pool.acquire() as conn:
        rows = await fetch_rows(conn, list(dict.fromkeys(config_ids)))
    return sorted({r.doc_id for r in rows if r.synced["vector"] or r.synced["search"] or r.synced["graph"]})


@app.get("/api/sources/available")
async def sources_available():
    """The sources a question can be limited to (the UIs' source picker): one entry per data source
    type and server with documents in the stores -- ``{source, label, url, documents, login_gated,
    auth_source, auth_url}``. ``login_gated`` sources (Alfresco, Nuxeo, CMIS; SharePoint and
    OneDrive with Microsoft sign-in configured) only answer for a user signed in to
    ``auth_source`` at ``auth_url`` unless its query auth is optional. ``available: false``
    without the incremental registry."""
    groups = await _source_groups()
    if groups is None:
        return {"available": False, "sources": []}
    return {"available": True,
            "sources": [{k: v for k, v in g.items() if k != "config_ids"} for g in groups]}


def _join_labels(sources) -> str:
    from permission_filter import LABELS
    names = [LABELS.get(s, s) for s in sorted(sources)]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


async def _question_scope(request: "QueryRequest", ticket: Optional[str], ticket_url: Optional[str] = None,
                          trusted: bool = False):
    """The doc ids a question may be answered from, or None for everything: the request's scope,
    narrowed to the governed documents the asker may read with the identities they gave
    (X-Alfresco-Ticket, source_auth.*). With no identity, a source whose query auth is required
    contributes no documents. Nothing is checked when no identity is given and the stores need
    no sign-in. Returns (doc_ids or None, message when nothing is left)."""
    scope_ids = None
    if request.scope:
        scope_ids = await _scope_doc_ids(request.scope)
        if not scope_ids:
            return [], _nothing_in_scope(request.scope)
    if request.sources:
        selected = await _selected_doc_ids(request.sources)
        if scope_ids is not None:
            keep = set(selected)
            selected = [d for d in scope_ids if d in keep]
        if not selected:
            return [], "Nothing from the selected source(s) is in the stores."
        scope_ids = selected
    identities = await _identities(request, ticket, ticket_url)
    # the asker's Alfresco sign-in also finds result documents' folders for their ACA links
    from doc_refs import set_asker_alfresco
    from permission_filter import _rest_base
    set_asker_alfresco({_rest_base(i.url): i.headers.get("Authorization", "")
                        for i in identities if i.source == "alfresco"})
    # a trusted client (MCP server) with no credentials: no filtering (it decides for itself)
    if identities or (not trusted and any(p["required"] for p in await _auth_providers())):
        # the search results (prefiltered to the scope / picked sources), not the whole scope
        candidates = await _candidate_doc_ids(request.query, scope_ids)
        readable = await _readable(candidates, identities, trusted)
        scope_ids = readable.doc_ids
        if not scope_ids:
            if readable.unsigned:
                names = _join_labels(readable.unsigned)
                return [], (f"The documents that answer this are in {names}. "
                            f"Sign in to {names} to see the ones you may read.")
            return [], ("You don't have access to any document that answers this."
                        if candidates else "Nothing in the stores matches this question.")
    return scope_ids, None


async def _sign_links(request: "QueryRequest", *ref_lists) -> None:
    """S3 / Azure Blob results' open links, signed with the asker's own sign-in (sources/signed_links.py),
    so they open the file itself; without that sign-in they keep the console link / none."""
    sa = request.source_auth
    s3_tokens = [c.token for c in _as_list(sa.s3)] if sa else []
    azure_tokens = [c.access_token for c in _as_list(sa.azure)] if sa else []
    refs = [r for refs in ref_lists for r in (refs or []) if isinstance(r, dict)]
    if not (s3_tokens or azure_tokens) or not any(r.get("source_type") in ("s3", "azure_blob") for r in refs):
        return
    from sources.signed_links import sign_open_links
    contexts: Dict[str, Dict[str, str]] = {}
    for ds, params in await _registry_datasources():
        if ds.source_type in _S3_SOURCES:
            contexts[ds.config_id] = {"region": (params.get("region_name") or "").strip()}
        elif ds.source_type in _AZURE_SOURCES:
            contexts[ds.config_id] = {"account_url": _azure_account_url(params)}
    try:
        await sign_open_links(refs, s3_tokens, azure_tokens, lambda d: contexts.get(d.split(":", 1)[0], {}))
    except Exception as e:  # a link is a convenience: never fail the answer over it
        logger.warning(f"Signing open links failed: {type(e).__name__}: {e}")


def _result_documents(results) -> list:
    return [d for r in (results or []) if isinstance(r, dict) for d in (r.get("documents") or [])]


def _nothing_in_scope(scope: "AskScope") -> str:
    what = scope.name or scope.path or "the selected item"
    return (f"Nothing from {what} is in the stores yet. Add it to KG Spaces and process it, "
            f"then ask again.")


class SourceLoginRequest(BaseModel):
    url: Optional[str] = None  # the server; omitted = ALFRESCO_URL / NUXEO_URL / CMIS_URL
    username: str
    password: str


AlfrescoLoginRequest = SourceLoginRequest


def _source_url(source: str, url: Optional[str]) -> str:
    url = (url or _source_default_url(source)).strip()
    if not url:
        raise HTTPException(status_code=400,
                            detail=f"no {source} URL: pass url or set {_SOURCE_URL_ENV[source]}")
    return url


def _alfresco_url(url: Optional[str]) -> str:
    return _source_url("alfresco", url)


@app.get("/api/auth/requirements")
async def auth_requirements():
    """Which sign-ins the stored content needs before search / AI chat (planning/SOURCE-AUTH-LOGIN.md).
    An empty ``providers`` list means no sign-in is needed. Each provider's ``required`` is its
    source's query auth (``<SOURCE>_QUERY_AUTH`` / ``SOURCE_QUERY_AUTH``): when false, a question
    without that sign-in still sees its documents. The top-level ``required`` is true when any
    provider's is (Alfresco's setting when there are none)."""
    providers = await _auth_providers(max_age=0)
    return {"required": any(p["required"] for p in providers) if providers else _query_auth_required("alfresco"),
            "providers": providers}


@app.post("/api/auth/alfresco/login")
async def alfresco_login_endpoint(body: SourceLoginRequest):
    """Sign in to Alfresco the way ACA does (POST tickets): returns ``{ticket, user_id, url}``.
    Stateless -- the ticket is not stored here. Send it back as X-Alfresco-Ticket or
    source_auth.alfresco.ticket on search / query / ingest."""
    from sources.alfresco_auth import alfresco_login
    url = _alfresco_url(body.url)
    try:
        result = await alfresco_login(url, body.username, body.password)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"could not reach Alfresco at {url}: {e}")
    return {**result, "url": url}


def _not_valid(detail: str) -> Dict[str, Any]:
    """A /me check's answer for a sign-in that is no longer valid (expired, signed out, revoked).
    200, not 401: checking a stored sign-in is not a refused request, and a 401 would log as one."""
    return {"valid": False, "detail": detail}


@app.get("/api/auth/alfresco/me")
async def alfresco_me_endpoint(url: Optional[str] = None,
                               x_alfresco_ticket: Optional[str] = Header(default=None)):
    """Whether the X-Alfresco-Ticket is still valid, and whose it is: ``{valid: true, user_id, url}``, or ``{valid: false, detail}``."""
    from sources.alfresco_auth import alfresco_ticket_user
    if not x_alfresco_ticket:
        return _not_valid("no X-Alfresco-Ticket header")
    url = _alfresco_url(url)
    try:
        return {"valid": True, "user_id": await alfresco_ticket_user(url, x_alfresco_ticket.strip()), "url": url}
    except PermissionError as e:
        return _not_valid(str(e))


@app.post("/api/auth/alfresco/logout")
async def alfresco_logout_endpoint(url: Optional[str] = None,
                                   x_alfresco_ticket: Optional[str] = Header(default=None)):
    """Sign out: invalidate the X-Alfresco-Ticket on Alfresco (as ACA's logout does)."""
    from sources.alfresco_auth import alfresco_authorization, alfresco_logout
    from permission_filter import forget
    if x_alfresco_ticket:
        ticket = x_alfresco_ticket.strip()
        forget(alfresco_authorization("", "ticket", ticket=ticket))  # no cached "readable" answers
        await alfresco_logout(_alfresco_url(url), ticket)
    return {"success": True}


@app.post("/api/auth/nuxeo/login")
async def nuxeo_login_endpoint(body: SourceLoginRequest):
    """Sign in to Nuxeo: returns ``{token, user_id, url}``, a Nuxeo auth token (as for
    auth_method=token ingest). Stateless -- send it back as source_auth.nuxeo.token on search /
    query, or nuxeo_config.token on ingest. The token lasts until revoked in Nuxeo."""
    from sources.nuxeo_auth import nuxeo_login
    url = _source_url("nuxeo", body.url)
    try:
        result = await nuxeo_login(url, body.username, body.password)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"could not reach Nuxeo at {url}: {e}")
    return {**result, "url": url}


@app.get("/api/auth/nuxeo/me")
async def nuxeo_me_endpoint(url: Optional[str] = None,
                            x_nuxeo_token: Optional[str] = Header(default=None)):
    """Whether the X-Nuxeo-Token is still valid, and whose it is: ``{valid: true, user_id, url}``, or ``{valid: false, detail}``."""
    from sources.nuxeo_auth import nuxeo_token_user
    if not x_nuxeo_token:
        return _not_valid("no X-Nuxeo-Token header")
    url = _source_url("nuxeo", url)
    try:
        return {"valid": True, "user_id": await nuxeo_token_user(url, x_nuxeo_token.strip()), "url": url}
    except PermissionError as e:
        return _not_valid(str(e))


class S3LoginRequest(BaseModel):
    """An IAM user's access key, used once for STS GetSessionToken (never stored). The UIs' sign-in
    dialog sends it as username / password."""
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


@app.post("/api/auth/s3/login")
async def s3_login_endpoint(body: S3LoginRequest):
    """Sign in to Amazon S3 (sources/s3_auth.py): an IAM access key -> ``{token, user_id,
    expires_at, url}``, the user's temporary session credentials packed into one token. Send it
    back as source_auth.s3.token on search / query."""
    from sources.s3_auth import S3_SERVER, enabled, s3_login
    if not enabled():
        raise HTTPException(status_code=400, detail="Amazon S3 sign-in is not enabled (S3_AUTH_ENABLED)")
    try:
        result = await s3_login(body.access_key_id or body.username or "", body.secret_access_key or body.password or "")
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"could not reach AWS STS: {e}")
    return {**result, "url": S3_SERVER}


@app.get("/api/auth/s3/me")
async def s3_me_endpoint(x_auth_token: Optional[str] = Header(default=None)):
    """Whether an S3 sign-in token (X-Auth-Token) is still valid, and whose it is: ``{valid: true, user_id, url}``, or ``{valid: false, detail}``."""
    from sources.s3_auth import S3_SERVER, s3_token_user
    if not x_auth_token:
        return _not_valid("no X-Auth-Token header")
    try:
        return {"valid": True, "user_id": await s3_token_user(x_auth_token.strip()), "url": S3_SERVER}
    except PermissionError as e:
        return _not_valid(str(e))


@app.post("/api/auth/cmis/login")
async def cmis_login_endpoint(body: SourceLoginRequest):
    """Sign in to a CMIS server through its vendor (sources/cmis_auth.py): an Alfresco server
    gives ``{auth_method: "ticket", ticket}``, a Nuxeo server ``{auth_method: "token", token}``,
    plus ``user_id``, ``vendor`` and ``url``. Other vendors: 400 (no adapter yet). Send it back as
    source_auth.cmis on search / query, or in cmis_config on ingest."""
    from sources.cmis_auth import cmis_login
    url = _source_url("cmis", body.url)
    try:
        result = await cmis_login(url, body.username, body.password)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"could not reach the CMIS server at {url}: {e}")
    return {**result, "url": url}


@app.get("/api/auth/cmis/me")
async def cmis_me_endpoint(auth_method: str, url: Optional[str] = None,
                           x_cmis_credential: Optional[str] = Header(default=None)):
    """Whether a CMIS sign-in's ticket / token (X-Cmis-Credential; auth_method ticket | token) is
    still valid, and whose it is: ``{valid: true, user_id, url}``, or ``{valid: false, detail}``."""
    from sources.cmis_auth import cmis_credential_user
    if not x_cmis_credential:
        return _not_valid("no X-Cmis-Credential header")
    url = _source_url("cmis", url)
    try:
        return {"valid": True, "user_id": await cmis_credential_user(url, auth_method, x_cmis_credential.strip()), "url": url}
    except PermissionError as e:
        return _not_valid(str(e))



def _popup_provider(provider: str):
    from sources.oauth_popup import providers
    p = providers().get(provider)
    if p is None:
        raise HTTPException(status_code=404, detail=f"no popup sign-in for {provider}")
    return p


def _popup_redirect_uri(request: Request, provider: str) -> str:
    """The redirect URI the vendor sends the popup back to: <PROVIDER>_AUTH_REDIRECT_URI, else this
    backend's own /api/auth/<provider>/callback as the browser reaches it (127.0.0.1 written as
    localhost, which is what the vendor apps register)."""
    explicit = (os.getenv(f"{provider.upper()}_AUTH_REDIRECT_URI") or "").strip()
    if explicit:
        return explicit
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{scheme}://{host.replace('127.0.0.1', 'localhost')}/api/auth/{provider}/callback"


def _popup_cookie(provider: str) -> str:
    return f"fg_{provider}_signin"


@app.get("/api/auth/{provider}/popup")
async def popup_signin_endpoint(provider: str, request: Request, state: str, login_hint: Optional[str] = None):
    """Open this in the sign-in popup (``provider``: microsoft = SharePoint + OneDrive, box) with a
    new random ``state``: it records the sign-in, binds it to this browser with a short-lived
    HttpOnly cookie, and redirects to the vendor's login. ``login_hint`` (the account used last
    time) skips the account picker where the vendor supports it. Then poll
    GET /api/auth/<provider>/result?state=... (sources/oauth_popup.py)."""
    import secrets as _secrets
    from fastapi.responses import RedirectResponse
    from sources.oauth_popup import start
    p = _popup_provider(provider)
    binder = _secrets.token_urlsafe(24)
    try:
        url = start(p, _popup_redirect_uri(request, provider), state, binder,
                    (login_hint or "").strip()[:256] or None)
    except (LookupError, ValueError) as e:
        return HTMLResponse(status_code=400, content=f"<!doctype html><meta charset=utf-8><body "
                            f"style='font-family:sans-serif;padding:2em'>Cannot sign in: {e}</body>")
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(_popup_cookie(provider), binder, max_age=600, httponly=True, samesite="lax",
                    path=f"/api/auth/{provider}")
    return resp


@app.api_route("/api/auth/{provider}/callback", methods=["GET", "POST"], response_class=HTMLResponse)
async def popup_callback_endpoint(provider: str, request: Request):
    """Where the vendor returns the sign-in popup (Microsoft: a form POST, keeping the code out of
    logged URLs; Box: query arguments, redacted in the access log): exchange the code, then close
    the popup."""
    from sources.oauth_popup import finish, pending
    import html as _html
    p = _popup_provider(provider)
    args = dict(await request.form()) if request.method == "POST" else dict(request.query_params)
    state, code = str(args.get("state") or ""), args.get("code")
    error, error_description = args.get("error"), args.get("error_description")
    handoff = bool(pending.get(state, {}).get("handoff"))  # a browser handoff (MCP), not a popup
    known = await finish(p, state, code, error_description or error)
    back = ("Return to your MCP client and finish the sign-in there; you can close this tab." if handoff
            else "Return to Flexible GraphRAG; this window closes itself (or close it).")
    msg = (f"<b>Signed in to {p.label}.</b> {back}" if known and not (error or error_description)
           else f"Sign-in did not complete: {_html.escape(error_description or error or 'unknown or expired sign-in')}")
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>{p.label} sign-in</title>"
                        f"<body style='font-family:sans-serif;padding:2em'>{msg}"
                        f"<script>setTimeout(function(){{window.close()}},800)</script></body>")


@app.get("/api/auth/{provider}/result")
async def popup_result_endpoint(provider: str, request: Request, state: str):
    """A started sign-in's outcome: 202 while the user is still signing in, then (once)
    ``{access_token, user_id, url, expires_at}`` -- ``url`` being the server the identity belongs
    to (Microsoft: the tenant) -- or 401 with the reason. Only for the browser that opened the
    popup (its sign-in cookie)."""
    from sources.oauth_popup import result
    r = result(_popup_provider(provider), state, request.cookies.get(_popup_cookie(provider)))
    if r is None:
        return JSONResponse(status_code=202, content={"pending": True})
    if "error" in r:
        raise HTTPException(status_code=401, detail=r["error"])
    return r


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(status_code=status, content=(
        f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<title>{title}</title><body style='font-family:sans-serif;max-width:32em;margin:3em auto;"
        f"padding:0 1em;line-height:1.5'>{body}</body>"))


class HandoffResultRequest(BaseModel):
    handoff_id: str
    poll_key: str


@app.post("/api/auth/{provider}/handoff")
async def handoff_start_endpoint(provider: str, request: Request):
    """Browser handoff for a caller with no browser (the MCP server): returns ``{sign_in_url,
    user_code, handoff_id, poll_key, expires_in}``. Show the user ``sign_in_url`` and
    ``user_code``; keep ``poll_key`` to yourself and POST it to /api/auth/<provider>/handoff/result.
    The page at sign_in_url shows the code and, once the user confirms it matches, continues to
    the vendor's login (sources/oauth_popup.py)."""
    from sources.oauth_popup import start_handoff
    p = _popup_provider(provider)
    try:
        h = start_handoff(p)
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    base = f"{scheme}://{host.replace('127.0.0.1', 'localhost')}"
    if not _handoff_confirm_code():
        h.pop("user_code", None)  # nothing to compare: the link goes straight to the vendor
    return {**h, "sign_in_url": f"{base}/api/auth/{provider}/handoff/{h['handoff_id']}", "label": p.label}


def _handoff_confirm_code() -> bool:
    """AUTH_HANDOFF_CONFIRM_CODE=true: a handoff link first shows its code for the user to compare
    with their client's before going on to the vendor. It stops a sign-in link sent by someone
    else from handing them the user's token -- worth it on a shared backend. Default off: the link
    goes straight to the vendor's login."""
    return (os.getenv("AUTH_HANDOFF_CONFIRM_CODE") or "").strip().lower() in ("1", "true", "yes", "on")


@app.get("/api/auth/{provider}/handoff/{handoff_id}", response_class=HTMLResponse)
async def handoff_page_endpoint(provider: str, handoff_id: str, request: Request):
    """The link the user opens: straight to the vendor's login, or (AUTH_HANDOFF_CONFIRM_CODE)
    first a page with the code to compare and a button on."""
    import html as _html
    from sources.oauth_popup import handoff
    p = _popup_provider(provider)
    h = handoff(p, handoff_id)
    if h is None or h["state"]:
        return _page(f"{p.label} sign-in", "This sign-in link has expired or was already used. "
                     "Start the sign-in again from your client.", 410)
    if not _handoff_confirm_code():
        # straight on to the vendor's login (single-user / local setups)
        return await handoff_continue_endpoint(provider, handoff_id, request)
    label = _html.escape(p.label)
    return _page(f"{label} sign-in", (
        f"<h2>Sign in to {label} for Flexible GraphRAG</h2>"
        f"<p>Your client (e.g. an AI assistant using the Flexible GraphRAG MCP server) asked for this "
        f"sign-in. Continue only if it shows this same code:</p>"
        f"<p style='font-size:2em;letter-spacing:.15em;font-weight:bold;font-family:monospace'>"
        f"{_html.escape(h['user_code'])}</p>"
        f"<p>Search and AI answers through that client will then include the {label} documents "
        f"you may read.</p>"
        f"<p><a href='{_html.escape(handoff_id)}/continue' style='display:inline-block;padding:.6em 1.2em;"
        f"background:#1565c0;color:#fff;border-radius:4px;text-decoration:none'>The codes match: "
        f"continue to {label}</a></p>"
        f"<p style='opacity:.7;font-size:.9em'>If you did not start this, close this page: "
        f"someone may be trying to get access to your {label} documents.</p>"))


@app.get("/api/auth/{provider}/handoff/{handoff_id}/continue")
async def handoff_continue_endpoint(provider: str, handoff_id: str, request: Request):
    """The user confirmed the code: on to the vendor's login (a link works once)."""
    import html as _html
    from fastapi.responses import RedirectResponse
    from sources.oauth_popup import continue_handoff
    p = _popup_provider(provider)
    try:
        url = continue_handoff(p, handoff_id, _popup_redirect_uri(request, provider))
    except (LookupError, ValueError) as e:
        return _page(f"{p.label} sign-in", _html.escape(str(e)), 410)
    return RedirectResponse(url, status_code=302)


@app.post("/api/auth/{provider}/handoff/result")
async def handoff_result_endpoint(provider: str, body: HandoffResultRequest):
    """A handoff's outcome for the holder of its poll key: 202 while the user has not finished,
    then (once) ``{access_token, user_id, url, expires_at}``, or 401 with the reason."""
    from sources.oauth_popup import handoff_result
    r = handoff_result(_popup_provider(provider), body.handoff_id, body.poll_key)
    if r is None:
        return JSONResponse(status_code=202, content={"pending": True})
    if "error" in r:
        raise HTTPException(status_code=401, detail=r["error"])
    return r


@app.get("/api/auth/{provider}/me")
async def popup_me_endpoint(provider: str, x_auth_token: Optional[str] = Header(default=None),
                            x_microsoft_token: Optional[str] = Header(default=None)):
    """Whether a popup sign-in's token (X-Auth-Token) is still valid, and whose it is:
    ``{valid: true, user_id, url}``, or ``{valid: false, detail}``."""
    p = _popup_provider(provider)
    token = (x_auth_token or x_microsoft_token or "").strip()
    if not token:
        return _not_valid("no X-Auth-Token header")
    try:
        return {"valid": True, "user_id": await p.user(token), "url": p.server(p.config() or {}, token)}
    except PermissionError as e:
        return _not_valid(str(e))


@app.post("/api/search")
async def search(request: QueryRequest, x_alfresco_ticket: Optional[str] = Header(default=None),
                 x_alfresco_url: Optional[str] = Header(default=None),
                 x_trusted_client_key: Optional[str] = Header(default=None)):
    try:
        logger.info(f"Processing {request.query_type} query: {request.query}"
                    + (f" (scope: {request.scope.path or request.scope.node_id})" if request.scope else ""))
        # A scope, and/or the asking user's Alfresco permissions (X-Alfresco-Ticket [+ X-Alfresco-Url])
        scope_ids, nothing = await _question_scope(request, x_alfresco_ticket, x_alfresco_url,
                                                  _trusted_client(x_trusted_client_key))
        if nothing:
            if request.query_type == "qa":
                return {"success": True, "answer": nothing}
            return {"success": True, "results": [], "message": nothing}
        
        if request.query_type == "qa":
            # Q&A query - return answer
            result = await backend_instance.qa_query(request.query, scope_doc_ids=scope_ids)
            if result["success"]:
                logger.info("Q&A query completed successfully")
                await _sign_links(request, result.get("sources"))
                return {"success": True, "answer": result["answer"], "sources": result.get("sources", [])}
            else:
                raise HTTPException(500, result["error"])
        else:
            # Hybrid search - return results
            result = await backend_instance.search_documents(request.query, request.top_k, scope_doc_ids=scope_ids)
            if result["success"]:
                logger.info("Hybrid search completed successfully")
                await _sign_links(request, _result_documents(result["results"]))
                return {"success": True, "results": result["results"]}
            else:
                raise HTTPException(500, result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query")
async def query_graph(request: QueryRequest, x_alfresco_ticket: Optional[str] = Header(default=None),
                      x_alfresco_url: Optional[str] = Header(default=None),
                      x_trusted_client_key: Optional[str] = Header(default=None)):
    try:
        logger.info(f"Processing query: {request.query}")
        scope_ids, nothing = await _question_scope(request, x_alfresco_ticket, x_alfresco_url,
                                                  _trusted_client(x_trusted_client_key))
        if nothing:
            return {"status": "success", "answer": nothing}
        result = await backend_instance.query_documents(request.query, request.top_k, scope_doc_ids=scope_ids)
        
        if result["success"]:
            logger.info("Query processing completed successfully")
            await _sign_links(request, result.get("sources"))
            return {"status": "success", "answer": result["answer"], "sources": result.get("sources", [])}
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
        raise HTTPException(status_code=500, detail= str(e))

async def _start_cocoindex_text_ingest(
    content: str,
    source_name: str,
    skip_graph: bool = False,
) -> dict:
    """Route raw text through CocoIndex (same branch pattern as ``/api/ingest``).

    Stages content into ``uploads/`` as a ``.txt`` file, then reuses
    ``_start_cocoindex_ingest`` → ``bridge.ingest_files`` so native CocoIndex
    vector/graph targets are used (not the flexible LlamaIndex write path).
    """
    await _ensure_cocoindex_bridge(
        getattr(backend_instance.system, "config", None)
    )
    if not cocoindex_bridge:
        raise HTTPException(
            status_code=500,
            detail="CocoIndex bridge unavailable for text ingest",
        )

    _safe_name = Path(source_name or "text_input.txt").name
    if not _safe_name.lower().endswith((".txt", ".md", ".markdown", ".html", ".htm")):
        _safe_name = f"{_safe_name}.txt"
    if not _safe_name or _safe_name in (".", ".."):
        _safe_name = "text_input.txt"

    _uploads = Path(getattr(cocoindex_bridge, "_uploads_dir", "./uploads"))
    _uploads.mkdir(parents=True, exist_ok=True)
    _staged = _uploads / _safe_name
    _staged.write_text(content, encoding="utf-8")
    logger.info(
        "CocoIndex text ingest: staged %d chars -> %s",
        len(content), _staged,
    )

    return await _start_cocoindex_ingest(
        data_source="filesystem",
        paths=[str(_staged)],
        config_id="",
        bridge_primary_ds=getattr(cocoindex_bridge, "_data_source", "filesystem") or "filesystem",
        conn_params={},
        skip_graph=skip_graph,
        enable_sync=False,
    )


@app.post("/api/test-sample")
async def test_sample_default(request: SampleTestRequest):
    """Test endpoint with configurable sample text using async processing."""
    try:
        content = settings.sample_text
        source_name = "sample-test"
        skip_graph = request.skip_graph

        logger.info("Starting async sample text processing")
        if os.getenv("PIPELINE_BACKEND", "default").lower() == "cocoindex":
            result = await _start_cocoindex_text_ingest(
                content=content, source_name=source_name, skip_graph=skip_graph,
            )
        else:
            result = await backend_instance.ingest_text(
                content=content, source_name=source_name, skip_graph=skip_graph,
            )

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
        if os.getenv("PIPELINE_BACKEND", "default").lower() == "cocoindex":
            result = await _start_cocoindex_text_ingest(
                content=request.content,
                source_name=request.source_name or "text_input",
                skip_graph=request.skip_graph,
            )
        else:
            result = await backend_instance.ingest_text(
                content=request.content,
                source_name=request.source_name,
                skip_graph=request.skip_graph,
            )

        logger.info(f"Text ingestion started with ID: {result['processing_id']}")
        return result
    except Exception as e:
        logger.error(f"Error starting text ingestion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/processing-status")
async def list_processing_status(owner: Optional[str] = None, limit: int = 50):
    """Processing jobs, oldest first and newest last: running ones and recent results (memory only -- a backend
    restart forgets them). ``owner`` limits the list to one user's jobs; auto-sync runs have no
    owner and are always listed (``kind: "sync"``). Passes of a per-row run are folded into it."""
    from backend import PROCESSING_STATUS
    from job_retention import prune
    prune(PROCESSING_STATUS)
    jobs = []
    for pid, st in list(PROCESSING_STATUS.items()):
        if st.get("pass_of"):  # a pass of a per-row run (backend.run_item_actions)
            continue
        kind = "sync" if pid.startswith("incremental_") else "ingest"
        if owner and kind == "ingest" and st.get("owner") != owner:
            continue
        jobs.append({
            "processing_id": pid,
            "kind": kind,
            "status": st.get("status"),
            "message": st.get("message"),
            "progress": st.get("progress", 0),
            "data_source": st.get("data_source"),
            "label": st.get("label"),
            "sync_action": st.get("sync_action"),  # auto sync: add | update | delete
            "owner": st.get("owner"),
            "started_at": st.get("started_at"),
            "updated_at": st.get("updated_at"),
        })
    # Oldest first, newest last (the order they ran); past ``limit`` the oldest are dropped.
    jobs.sort(key=lambda j: str(j.get("started_at") or j.get("updated_at") or ""))
    return {"jobs": jobs[-max(1, min(limit, 500)):]}


@app.delete("/api/processing-status")
async def clear_processing_status():
    """Forget finished jobs (completed, failed, cancelled); running ones stay. So does a finished
    job whose document_state rows are still being written (its documents are read for them) --
    unless it finished over ten minutes ago, when that writer has given up."""
    from backend import PROCESSING_STATUS
    from job_retention import clear_finished
    return clear_finished(PROCESSING_STATUS)


@app.get("/api/processing-status/{processing_id}")
async def get_processing_status(processing_id: str):
    """Get processing status by ID (without the job's ingested documents -- see job_retention)."""
    from backend import PROCESSING_STATUS
    from job_retention import prune, public_view
    try:
        prune(PROCESSING_STATUS)
        logger.debug(f"Checking processing status for ID: {processing_id}")
        result = backend_instance.get_processing_status(processing_id)

        if result["success"]:
            logger.debug(f"Status retrieved for {processing_id}: {result['processing']['status']}")
            return public_view(result["processing"])
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
    
    from job_retention import public_view

    def event_stream():
        while True:
            result = backend_instance.get_processing_status(processing_id)
            if result["success"]:
                status_data = result["processing"]
                # Without the job's ingested documents, like /api/processing-status/{id}
                yield f"data: {json.dumps(public_view(status_data), default=str)}\n\n"
                
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


def _load_declared_requirement_lines() -> List[str]:
    """The backend's declared dependencies ([project].dependencies): from pyproject.toml next to this
    file (a source checkout or editable install), else from the installed package's metadata (a
    wheel install, e.g. from PyPI, ships no pyproject.toml). Optional extras are left out."""
    pyproject_path = os.path.join(os.path.dirname(__file__), "pyproject.toml")
    if os.path.isfile(pyproject_path):
        import tomllib

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        deps = data.get("project", {}).get("dependencies") or []
        return [d.strip() for d in deps if isinstance(d, str) and d.strip()]
    try:
        from importlib.metadata import requires

        reqs = requires("flexible-graphrag") or []
    except Exception:
        return []
    # Requires-Dist lines; an optional extra's carries the marker `extra == "<name>"`
    return [r.strip() for r in reqs if "extra ==" not in r.replace("extra==", "extra ==")]


def _requirement_install_name(req_line: str) -> str:
    """Normalized distribution name for lookup in importlib.metadata (handles PEP 508 specs)."""
    try:
        from packaging.requirements import Requirement

        return Requirement(req_line).name.lower()
    except Exception:
        base = req_line.strip().lower()
        if "[" in base:
            base = base.split("[", 1)[0].strip()
        for sep in ("===", "==", ">=", "<=", "!=", "~=", "<", ">", "@"):
            if sep in base:
                base = base.split(sep, 1)[0].strip()
                break
        return base


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
    
    requirements = _load_declared_requirement_lines()
    
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
        install_name = _requirement_install_name(req)
        installed_version = installed_packages.get(install_name)
        req_status.append({
            "name": install_name,
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

class IngestStatusItem(BaseModel):
    path: str
    id: Optional[str] = None  # repository node id; enables the exact document_state match
    is_folder: bool = False


class IngestStatusRequest(BaseModel):
    data_source: str          # alfresco | nuxeo | filesystem | upload -- or any other source (see `source`)
    url: Optional[str] = None  # repository url; omitted = every datasource of that type
    recursive: bool = False   # what the pending ingest would use
    items: List[IngestStatusItem]
    # Every other source (S3, GCS, Azure Blob, Box, Google Drive, OneDrive, SharePoint, CMIS, web,
    # Wikipedia, YouTube) is ONE row: the whole datasource. `source` is the ingest request's own
    # source fields (e.g. {"s3_config": {...}}, CMIS also "paths"), which name that datasource.
    source: Optional[Dict[str, Any]] = None


@app.post("/api/sync/ingest-status")
async def sync_ingest_status(request: IngestStatusRequest):
    """Ingest status of each selected item: which datasources already hold it -- active
    auto-syncs, and sources ingested without sync (``auto_sync: false`` on the match).

    One call for a whole multi-select; results come back in request order. Lets a UI flag
    rows that are already in the stores instead of ingesting them again.
    Answers ``enabled: false`` rather than an error when incremental sync is off, so callers
    need no separate check.
    """
    from incremental_updates.ingest_status import (
        FS_SOURCES, ROW_SOURCES, Datasource, Item, check_ingest_status, fs_item, normalize_url,
    )
    from incremental_updates.removal import (
        configs_present, configured_stores, fetch_rows, stores_holding,
    )

    if request.data_source not in ROW_SOURCES:
        if request.source is None:
            raise HTTPException(
                status_code=400,
                detail=f"ingest status for {request.data_source} needs `source`: the ingest request's "
                       f"source fields (one row, the whole datasource)",
            )
        if not incremental_manager or not incremental_manager.is_initialized():
            return {"enabled": False, "items": []}
        return await _datasource_row_status(request)
    fs = request.data_source in FS_SOURCES
    source_type = "filesystem" if fs else request.data_source  # uploads are filesystem ingests
    if not incremental_manager or not incremental_manager.is_initialized():
        return {"enabled": False, "items": []}

    try:
        await ensure_config_manager_ready()
        url = normalize_url(request.url)
        datasources = [
            ds for ds in map(
                Datasource.from_config,
                await incremental_manager.config_manager.get_ingest_status_configs(),
            )
            if ds.source_type == source_type and (fs or not url or ds.url == url)
        ]

        rows = []
        if datasources:
            async with incremental_manager.state_manager.pool.acquire() as conn:
                rows = await fetch_rows(conn, [ds.config_id for ds in datasources])
        indexed: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            if row.source_id:
                indexed.setdefault(row.source_id, []).append(
                    {"config_id": row.config_id, "auto_sync": row.auto_sync,
                     **{f"{t}_synced_at": v for t, v in row.synced.items()}})

        items = ([fs_item(_fs_row_path(i.path), i.is_folder) for i in request.items] if fs
                 else [Item(i.path, i.is_folder, i.id) for i in request.items])
        results = check_ingest_status(items, datasources, indexed, request.recursive,
                                      present=configs_present(items, rows))
        # A folder row: which stores hold the documents below it (files get theirs above), and
        # whether any of them is still auto-synced (document_state.auto_sync)
        from incremental_updates.removal import item_matches
        auto_ids = {ds.config_id for ds in datasources if ds.auto_sync}
        for item, result in zip(items, results):
            if item.is_folder and result["indexed"] is None and result["status"] != "none":
                result["indexed"] = stores_holding(item, rows, request.recursive)
            if item.is_folder:
                under = [r for r in rows if r.config_id in auto_ids
                         and item_matches(item, r, request.recursive)]
                if under:
                    result["auto_sync"] = any(r.auto_sync for r in under)
        return {
            "enabled": True,
            "stores": configured_stores(settings),
            "items": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking ingest status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RemoveRequest(IngestStatusRequest):
    # vector | search | graph (graph = property graph and RDF together)
    targets: List[str] = ["vector", "search", "graph"]


async def _remove_items(data_source: str, url, recursive: bool, items, targets: List[str]) -> dict:
    """Remove ``items`` (ingest_status.Item) from ``targets``; see /api/sync/remove."""
    from incremental_updates.ingest_status import Datasource, normalize_url
    from incremental_updates.removal import fetch_rows, record_removal, select_rows
    from ingest.replace_existing import delete_doc_ids

    await ensure_config_manager_ready()
    url = normalize_url(url)
    datasources = [
        ds for ds in map(
            Datasource.from_config,
            await incremental_manager.config_manager.get_ingest_status_configs(),
        )
        if ds.source_type == data_source and (not url or ds.url == url)
    ]
    auto_sync = {ds.config_id for ds in datasources if ds.auto_sync}

    async with incremental_manager.state_manager.pool.acquire() as conn:
        rows = await fetch_rows(conn, [ds.config_id for ds in datasources]) if datasources else []
    per_item = select_rows(items, rows, recursive)

    # Only delete where the document is: skips stores it never reached (skip_graph).
    selected = {r.doc_id: r for matched in per_item for r in matched}
    in_stores = [r for r in selected.values() if any(r.synced[t] for t in targets)]
    # Which of the targets those documents were actually in: what the message should name
    hit = [t for t in targets if any(r.synced[t] for r in in_stores)]
    if in_stores:
        await delete_doc_ids(backend_instance.system, [r.doc_id for r in in_stores], targets)
    async with incremental_manager.state_manager.pool.acquire() as conn:
        counts = await record_removal(conn, selected.values(), targets, auto_sync)

    return {
        "status": "success",
        "targets": targets,
        "documents": len(in_stores),
        "targets_hit": hit,
        **counts,
        "items": [
            {
                "id": item.id,
                "path": item.path,
                "documents": len(matched),
                "kept_out_of_auto_sync": sum(r.config_id in auto_sync for r in matched),
            }
            for item, matched in zip(items, per_item)
        ],
    }


@app.post("/api/sync/remove")
async def sync_remove(request: RemoveRequest):
    """Take the selected files and folders back out of some or all of the stores.

    Same body as /api/sync/ingest-status plus ``targets``. A folder stands for the documents
    below it (all depths when ``recursive``). A document an auto-sync keeps, removed from every
    store, stays out of that sync until it is ingested again; see
    incremental_updates/removal.py.
    """
    from incremental_updates.ingest_status import PATH_SOURCES, Item
    from incremental_updates.engine import DELETE_TARGETS

    if request.data_source not in PATH_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"remove is available for {', '.join(PATH_SOURCES)}, not {request.data_source}",
        )
    targets = list(dict.fromkeys(request.targets))
    unknown = set(targets) - set(DELETE_TARGETS)
    if not targets or unknown:
        raise HTTPException(
            status_code=400,
            detail=f"targets must be some of {', '.join(DELETE_TARGETS)}"
                   + (f"; unknown: {', '.join(sorted(unknown))}" if unknown else ""),
        )
    if not incremental_manager or not incremental_manager.is_initialized():
        raise HTTPException(
            status_code=400,
            detail="remove needs ENABLE_INCREMENTAL_UPDATES=true: document_state is what says "
                   "which documents a selection stands for",
        )

    try:
        await ensure_config_manager_ready()
        items = [Item(i.path, i.is_folder, i.id) for i in request.items]
        return await _remove_items(request.data_source, request.url, request.recursive, items, targets)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing documents: {e}")
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
            # auto_sync = false rows were ingested without sync: inactive by design, not paused
            rows = await conn.fetch("""
                SELECT config_id FROM datasource_config
                WHERE is_active = false AND auto_sync = true
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

# ─────────────────────────────────────────────────────────────────────────────
# CocoIndex pipeline bridge endpoints
# Active only when PIPELINE_BACKEND=cocoindex is set in .env.
# These endpoints let you trigger on-demand updates, check status, and force
# a full reprocess — mirroring what ``cocoindex update`` does from the CLI.
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/cocoindex/status")
async def cocoindex_status():
    """Return CocoIndex bridge status and last update results.

    Returns 200 with ``{"active": false}`` when PIPELINE_BACKEND != cocoindex.
    """
    if not cocoindex_bridge:
        return {
            "active": False,
            "message": (
                "CocoIndex pipeline bridge is not running. "
                "Set PIPELINE_BACKEND=cocoindex in .env to enable it."
            ),
        }
    return {"active": True, **cocoindex_bridge.status()}


@app.post("/api/cocoindex/sync-now")
async def cocoindex_sync_now(request: dict = None):
    """Trigger a CocoIndex update cycle — mirrors ``POST /api/sync/sync-now``.

    Processes all pending / changed files through the CocoIndex pipeline.
    CocoIndex's LMDB memoization means unchanged documents are skipped
    automatically; only new or modified files are re-processed.

    Equivalent to running:
      ``cocoindex update cocoindex_integration/pipeline/app.py``

    The pipeline ``app.py`` is configured by ``.env`` — same sources, targets,
    and functions as when running the CLI directly.

    Optional JSON body:
      ``{"full_reprocess": true}``  — invalidate LMDB memo state and reprocess
      every document from scratch (slow; use after changing chunking / extraction
      config).  Equivalent to deleting ``cocoindex.db`` and re-running.

    Returns update stats and elapsed time.
    """
    if not cocoindex_bridge:
        raise HTTPException(
            status_code=400,
            detail=(
                "CocoIndex bridge is not running. "
                "Set PIPELINE_BACKEND=cocoindex in .env to enable it."
            ),
        )
    full_reprocess = bool((request or {}).get("full_reprocess", False))
    try:
        result = await cocoindex_bridge.sync_now(full_reprocess=full_reprocess)
        return result
    except asyncio.CancelledError:
        logger.warning("cocoindex/sync-now: request cancelled (server shutting down)")
        raise HTTPException(status_code=503, detail="Server is shutting down")
    except Exception as exc:
        logger.error("cocoindex/sync-now error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/cocoindex/config")
async def cocoindex_config():
    """Show the CocoIndex pipeline configuration loaded from .env.

    Returns the same ``load_config_from_env()`` dict that
    ``cocoindex_integration/pipeline/app.py`` uses — useful for verifying
    the bridge sees the right source / target / function settings before
    triggering a sync.

    The same config is used whether you trigger ingest via:
      - REST:  ``POST /api/cocoindex/sync-now`` (server bridge)
      - CLI:   ``cocoindex update cocoindex_integration/pipeline/app.py``
    """
    try:
        from cocoindex_integration.pipeline.app import load_config_from_env
        cfg = load_config_from_env()
        return {
            "active": cocoindex_bridge is not None,
            "pipeline_app": "cocoindex_integration/pipeline/app.py",
            "cli_equivalent": "cocoindex update cocoindex_integration/pipeline/app.py",
            "pipeline_config": cfg,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Backend API only - no frontend serving
@app.get("/")
async def root():
    return {
        "message": "Flexible GraphRAG API", 
        "api": "/api",
        "info": "/api/info",
        "note": "Backend API only - use separate dev servers for UIs"
    }

# After all imports, so it runs after the redaction filter litellm adds to this logger
logging.getLogger("uvicorn.error").addFilter(_DropStaleUvicornColorMessage())

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
