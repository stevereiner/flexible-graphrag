"""Shared env/path helpers for integration tests (avoid quoting bugs in .env / shell)."""
from __future__ import annotations

import os


def normalized_integration_watch_dir() -> str:
    """Return INTEGRATION_WATCH_DIR with outer quotes stripped and path normalized."""
    raw = os.getenv("INTEGRATION_WATCH_DIR")
    if not raw:
        return ""
    s = raw.strip()
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        s = s[1:-1]
    s = s.strip()
    return os.path.normpath(s) if s else ""
