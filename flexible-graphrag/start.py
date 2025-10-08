#!/usr/bin/env python3
"""
Startup script for flexible-graphrag using uvicorn
Usage: uv run start.py
"""

import uvicorn
import platform

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
        loop="asyncio"
    )