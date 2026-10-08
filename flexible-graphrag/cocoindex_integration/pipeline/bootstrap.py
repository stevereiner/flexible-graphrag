"""Import-time environment bootstrap for the CocoIndex pipeline.

This module centralises all the process-level setup that MUST run before
``cocoindex`` (and other libraries that call ``nest_asyncio.apply()``) are
imported:

* neutralise ``nest_asyncio.apply`` on Python 3.14 (before any cocoindex import)
* load flexible-graphrag's ``.env`` (``override=False`` so shell vars win)
* route flexible-graphrag Python logging to a dedicated log file
* suppress cosmetic third-party warnings
* apply the runtime Python 3.14 asyncio / sniffio / asyncpg patches

All of the above run **as import-time side effects** so that simply importing
this module (before ``import cocoindex``) reproduces the exact ordering the
pipeline relies on.  ``pipeline/app.py`` imports this module first, then imports
cocoindex.

IMPORTANT: this module must NOT import ``cocoindex`` — its whole purpose is to
run before cocoindex is loaded.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import warnings

# ── Python 3.14 compatibility — must run before any import that calls
# nest_asyncio.apply() (cocoindex, LlamaIndex, elasticsearch-client all do this).
# On 3.14, nest_asyncio patches loop.run_until_complete() so coroutines run
# without a Task wrapper.  asyncio.Runner.close() then calls
# loop.shutdown_default_executor() which internally uses asyncio.timeout()
# — that raises RuntimeError("Timeout should be used inside a task") on shutdown.
# Fix: neutralise nest_asyncio.apply so the patch is never applied.
if sys.version_info >= (3, 14):
    try:
        import nest_asyncio as _nest_asyncio_early
        _nest_asyncio_early.apply = lambda *a, **kw: None
    except ImportError:
        pass

# Load flexible-graphrag's .env before any os.getenv() calls.
# python-dotenv is already a flexible-graphrag dependency.
# override=False so explicit env vars (e.g. from the shell) always win.
try:
    from dotenv import find_dotenv as _find_dotenv, load_dotenv as _load_dotenv
    # working directory first (wheel installs live in site-packages), then next to the code
    _load_dotenv(_find_dotenv(usecwd=True) or _find_dotenv(), override=False)
except ImportError:
    pass

logger = logging.getLogger(__name__)


# ── Python logging — make flexible-graphrag output visible alongside CocoIndex ──
# CocoIndex controls its own Rust tracing via COCOINDEX_LOG_LEVEL; Python's
# logging module is *separate* and starts with no handlers, so logger.info()
# calls in flexible-graphrag code are silently dropped unless we configure one.
#
# Set LOG_LEVEL in .env (or shell) to control Python log verbosity:
#   LOG_LEVEL=DEBUG   — full diagnostic output
#   LOG_LEVEL=INFO    — normal operational messages  (default)
#   LOG_LEVEL=WARNING — only warnings and errors
#
# COCOINDEX_LOG_LEVEL controls CocoIndex's own Rust-level tracing independently.
def _configure_python_logging() -> None:
    """Route flexible-graphrag Python logging to a dedicated log file.

    The file path is controlled by ``FLEXIBLE_GRAPHRAG_LOG`` (default:
    ``flexible-graphrag-cocoindex.log`` next to the working directory).
    Set ``LOG_LEVEL`` to control verbosity (default ``INFO``).

    This keeps flexible-graphrag log output completely separate from
    CocoIndex's own Rust-level tracing that goes to the terminal.
    """
    _level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    _level = getattr(logging, _level_name, logging.INFO)

    _log_path = os.getenv("FLEXIBLE_GRAPHRAG_LOG", "flexible-graphrag-cocoindex.log")

    root = logging.getLogger()
    # Avoid adding duplicate handlers if the module is reloaded.
    _already_has_file = any(
        isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == os.path.abspath(_log_path)
        for h in root.handlers
    )
    if not _already_has_file:
        _fh = logging.FileHandler(_log_path, encoding="utf-8")
        _fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s  %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root.addHandler(_fh)
    root.setLevel(_level)

    # Silence known noisy third-party loggers regardless of LOG_LEVEL.
    for _noisy in (
        "transformers", "diffusers", "LiteLLM", "litellm",
        "httpx", "httpcore", "urllib3", "asyncio",
        "openai._base_client", "anthropic._base_client",
        "google.auth", "boto3", "botocore", "s3transfer",
        # kafka-python's consumer loop logs every fetch, heartbeat and offset
        # commit at DEBUG.  The Nuxeo audit consumer polls continuously, so at
        # LOG_LEVEL=DEBUG this alone was ~1200 of 2000 lines in a single run.
        "kafka", "kafka.client", "kafka.conn", "kafka.consumer",
        "kafka.coordinator", "kafka.protocol", "kafka.cluster",
    ):
        logging.getLogger(_noisy).setLevel(logging.ERROR)


_configure_python_logging()

# ── Suppress cosmetic third-party warnings that pollute cocoindex update output ──
# transformers: "Using a slow image processor …" / "use_fast will be default in v4.52"
warnings.filterwarnings("ignore", message=".*use_fast.*", category=UserWarning)
# transformers/PyTorch: "`torch_dtype` is deprecated! Use `dtype` instead"
warnings.filterwarnings("ignore", message=".*torch_dtype.*", category=FutureWarning)
# transformers general deprecation noise
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")


def _apply_python314_patches() -> None:
    """Mirror the subset of main.py's Python 3.14 patches relevant to CocoIndex.

    Patches asyncio.wait_for, sniffio, and re-neutralises nest_asyncio.apply
    at runtime (in case a lazy import applied it after our early neutralisation).
    """
    if sys.version_info < (3, 14):
        return

    # Re-neutralise nest_asyncio at runtime (cocoindex may import it lazily)
    try:
        import nest_asyncio as _na
        _na.apply = lambda *a, **kw: None
    except ImportError:
        pass

    # Patch asyncio.wait_for — asyncio.timeout() inside it requires a Task on 3.14
    try:
        _orig_wait_for = asyncio.wait_for

        async def _safe_wait_for(fut, timeout, **kwargs):
            if timeout is None or asyncio.current_task() is not None:
                return await _orig_wait_for(fut, timeout, **kwargs)
            task = asyncio.ensure_future(fut)
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if _ :
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

    # Patch sniffio so it detects asyncio even when current_task() is None
    try:
        import sniffio._impl as _sniffio_impl

        def _safe_current_async_library():
            value = _sniffio_impl.thread_local.name
            if value is not None:
                return value
            value = _sniffio_impl.current_async_library_cvar.get()
            if value is not None:
                return value
            if "asyncio" in sys.modules:
                try:
                    if asyncio.current_task() is not None:
                        return "asyncio"
                    asyncio.get_running_loop()
                    return "asyncio"
                except RuntimeError:
                    pass
            raise _sniffio_impl.AsyncLibraryNotFoundError(
                "unknown async library, or not in async context"
            )

        _sniffio_impl.current_async_library = _safe_current_async_library
        import sniffio as _sniffio
        _sniffio.current_async_library = _safe_current_async_library
    except Exception:
        pass

    # Patch asyncpg.compat.timeout (used during connection pool creation)
    try:
        from contextlib import asynccontextmanager
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


_apply_python314_patches()
