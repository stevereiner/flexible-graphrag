"""
Path utilities for incremental updates.

Normalizes filesystem paths so that doc_id and comparisons are case-insensitive
on Windows, avoiding false DELETE/CREATE when only the path case differs.
"""

import os
import sys


def normalize_filesystem_path(path: str) -> str:
    """
    Normalize a filesystem path for use in doc_id, source_path, and set comparisons.
    On Windows, uses lowercase so "C:\\test\\file.txt" and "c:\\test\\file.txt" match.
    On Unix, returns the path unchanged (filesystems are case-sensitive).
    """
    if not path:
        return path
    normalized = os.path.normpath(path)
    if sys.platform == "win32":
        normalized = normalized.lower()
    return normalized
