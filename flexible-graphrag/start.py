#!/usr/bin/env python3
"""
Startup script for flexible-graphrag using uvicorn
Usage:
  flexible-graphrag        # console entry point (any install: PyPI or source)
  python -m start          # equivalent — works when the package env is active
  uv run start.py          # source checkout only (run from this directory)

FLEXIBLE_GRAPHRAG_HOST / FLEXIBLE_GRAPHRAG_PORT (environment, not .env: read before the app loads
it) set the address; default 0.0.0.0:8000. The desktop app starts its backend on 127.0.0.1.
"""

import logging
import os
import sys
import uvicorn


def _exit_now(code: int = 0) -> None:
    """End the process once the server has stopped and the app's shutdown has run.

    Seen on Windows (2026-11-15): after Ctrl+C the app logged "Shutdown complete" and the process
    then sat in the interpreter's own exit (no Python frames, main thread in native code), so the
    console never got its prompt back. Everything that matters is done by then; flush the logs and
    leave without the interpreter's teardown.
    """
    try:
        logging.shutdown()
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)


def main():
    code = 0
    try:
        _serve()
    except SystemExit as e:
        # uvicorn exits non-zero when it can't start (port in use, app import error): keep that
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except KeyboardInterrupt:
        pass
    except BaseException as e:
        if type(e).__name__ != "CancelledError":
            raise
    _exit_now(code)


def _serve():
    # On Python 3.14, asyncio.Runner turns CancelledError into KeyboardInterrupt inside run();
    # main() treats both (and SystemExit) as a clean stop, so no traceback is printed.
    uvicorn.run(
        "main:app",
        host=os.getenv("FLEXIBLE_GRAPHRAG_HOST") or "0.0.0.0",
        port=int(os.getenv("FLEXIBLE_GRAPHRAG_PORT") or 8000),
        reload=False,
        log_level="info",
        loop="asyncio"
    )


if __name__ == "__main__":
    # Suppress Python's default traceback for clean Ctrl-C exits.
    # asyncio.Runner on 3.14 raises KeyboardInterrupt from runner.run() which
    # Python would otherwise print as an unhandled exception traceback.
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
    except BaseException as e:
        name = type(e).__name__
        if name in ("KeyboardInterrupt", "SystemExit", "CancelledError"):
            pass
        else:
            raise
