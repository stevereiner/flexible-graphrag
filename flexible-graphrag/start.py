#!/usr/bin/env python3
"""
Startup script for flexible-graphrag using uvicorn
Usage: flexible-graphrag            (after uv pip install flexible-graphrag)
       uv run start.py              (with source or after package install)
"""

import uvicorn
import platform


def main():
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
        loop="asyncio"
    )


if __name__ == "__main__":
    main()
