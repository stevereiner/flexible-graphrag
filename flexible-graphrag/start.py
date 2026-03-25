#!/usr/bin/env python3
"""
Startup script for flexible-graphrag using uvicorn
Usage: flexible-graphrag            (after uv pip install flexible-graphrag)
       uv run start.py              (with source)
"""

import sys
import uvicorn


def main():
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="info",
            loop="asyncio"
        )
    except (KeyboardInterrupt, SystemExit):
        pass
    except BaseException as e:
        # On Python 3.14, asyncio.Runner converts CancelledError -> KeyboardInterrupt
        # inside run(), which then re-raises as a plain exception crossing the boundary.
        # Swallow any clean-exit exception types so no traceback is printed.
        name = type(e).__name__
        if name not in ("KeyboardInterrupt", "SystemExit", "CancelledError"):
            raise


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
