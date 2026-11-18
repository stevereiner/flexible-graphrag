"""Optional API token, and filesystem ingest folders set at runtime.

API_TOKEN: when set, every ``/api`` request must carry it, as ``X-API-Token: <token>`` or
``Authorization: Bearer <token>``. Meant first for the desktop app, which starts its own backend on
127.0.0.1 with a secret made for that launch. Binding to localhost alone doesn't stop the web pages
open in the user's browser from calling ``localhost:8000`` (CORS allows any origin unless
CORS_ORIGINS is set), and with the user's folders allowed that would let any page read their files
through ingest + search. Any other deployment can set it too, as a shared secret in front of the API.

Not checked (with a token set):
- CORS preflights (``OPTIONS``): the browser sends them without custom headers;
- ``/api/health``: liveness checks (Docker, the desktop app's wait for startup);
- the sign-in pages the browser opens itself (popup, vendor callback, handoff link), which can't
  carry a header. They are bound to a sign-in ``state`` / handoff id and the popup's cookie, and the
  token they produce is only handed out by ``/result`` endpoints, which do need the API token.

Runtime ingest folders: with API_TOKEN set, the token holder (the desktop app, when the user adds a
folder) can set extra folders that filesystem ingests may read, without a restart
(``PUT /api/ingest-allowed-paths``). Without API_TOKEN that is refused: any caller could otherwise
allow ``/`` and read every file the backend can (GHSA-2558-gvg9-whcx).
"""
from __future__ import annotations

import hmac
import re
import threading
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Tuple

TOKEN_HEADER = "x-api-token"

# Pages the browser navigates to (no custom headers possible); see the module docstring.
_EXEMPT_PATHS = (
    re.compile(r"^/api/health/?$"),
    re.compile(r"^/api/auth/[^/]+/popup/?$"),
    re.compile(r"^/api/auth/[^/]+/callback/?$"),
    re.compile(r"^/api/auth/[^/]+/handoff/(?!result/?$)[^/]+(/continue)?/?$"),
)


def token_required(path: str, method: str, token: Optional[str]) -> bool:
    """Whether a request to ``path`` must carry the API token."""
    if not token or method.upper() == "OPTIONS":
        return False
    if path != "/api" and not path.startswith("/api/"):
        return False  # only the API: "/" and FastAPI's /docs schema pages call nothing themselves
    return not any(p.match(path) for p in _EXEMPT_PATHS)


def supplied_token(headers: Mapping[str, str]) -> Optional[str]:
    """The token a request carries: ``X-API-Token``, else an ``Authorization: Bearer`` value."""
    value = headers.get(TOKEN_HEADER)
    if value:
        return value.strip()
    auth = headers.get("authorization") or ""
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return None


def token_matches(supplied: Optional[str], token: str) -> bool:
    return bool(supplied) and hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8"))


def parse_list(value) -> Optional[List[str]]:
    """A list setting from the environment: a JSON list, or comma-separated values."""
    if value is None or isinstance(value, list):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("["):
        import json
        return [str(v).strip() for v in json.loads(text) if str(v).strip()]
    return [v.strip() for v in text.split(",") if v.strip()]


class RuntimeIngestPaths:
    """Folders (or files) filesystem ingests may read besides the configured ones, set while the
    backend runs. Kept in memory: the app that sets them sends them again after a restart."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._paths: Tuple[str, ...] = ()

    def get(self) -> List[str]:
        return list(self._paths)

    def set(self, paths: Iterable[str]) -> Tuple[List[str], List[str]]:
        """Replace the list with the entries of ``paths`` that exist (resolved, deduplicated).
        Returns ``(kept, rejected)``."""
        kept: List[str] = []
        rejected: List[str] = []
        for raw in paths:
            s = str(raw).strip().strip('"').strip("'")
            try:
                if not s or "\x00" in s or not Path(s).is_absolute():
                    raise ValueError
                resolved = Path(s).resolve()
                if not resolved.exists():
                    raise ValueError
            except (OSError, ValueError):
                rejected.append(str(raw))
                continue
            if str(resolved) not in kept:
                kept.append(str(resolved))
        with self._lock:
            self._paths = tuple(kept)
        return kept, rejected


runtime_ingest_paths = RuntimeIngestPaths()
