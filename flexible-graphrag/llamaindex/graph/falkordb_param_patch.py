"""Patch FalkorDB's param stringifier so LlamaIndex graph ingest works.

FalkorDB's ``stringify_param_value`` (falkordb.helpers) falls through to ``str()``
for bools and numpy types. That emits Python ``True``/``False`` and ndarray reprs,
which are invalid inside the ``CYPHER ...`` header.

**Critical:** ``falkordb/graph.py`` does ``from .helpers import stringify_param_value``,
so it holds a **module-level binding** to the original function. Replacing only
``falkordb.helpers.stringify_param_value`` does **not** change what ``Graph._build_params_header``
calls. This module patches **both** ``falkordb.helpers`` and ``falkordb.graph``.

Map keys in nested dicts must be valid Cypher identifiers; metadata keys such as
``modified at`` (space) produce invalid map literals and parse errors near ``data=``.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_PATCH_LOCK = False

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _cypher_map_key(key: Any) -> str:
    """Emit a valid unquoted map key for FalkorDB's inline CYPHER param maps."""
    k = str(key)
    if _IDENT.match(k):
        return k
    s = re.sub(r"[^0-9A-Za-z_]+", "_", k.strip()).strip("_")
    if not s:
        return "key"
    if s[0].isdigit():
        s = "k_" + s
    return s


def _flexible_stringify_param_value(value: Any) -> str:
    from falkordb.helpers import quote_string

    if isinstance(value, str):
        return quote_string(value)
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return quote_string(value.isoformat())
    if isinstance(value, UUID):
        return quote_string(str(value))
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "null"
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        inner = ",".join(_flexible_stringify_param_value(x) for x in value)
        return f"[{inner}]"
    if isinstance(value, dict):
        parts = [
            f"{_cypher_map_key(k)}:{_flexible_stringify_param_value(v)}" for k, v in value.items()
        ]
        return "{" + ",".join(parts) + "}"
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return _flexible_stringify_param_value(value.tolist())
        if isinstance(value, np.generic):
            return _flexible_stringify_param_value(value.item())
    except ImportError:
        pass
    if hasattr(value, "tolist") and callable(getattr(value, "tolist")):
        if not isinstance(value, (str, bytes, dict, list, tuple, set)):
            try:
                return _flexible_stringify_param_value(value.tolist())
            except Exception:
                pass
    return str(value)


def ensure_falkordb_stringify_patch() -> None:
    """Idempotently patch stringify on ``falkordb.helpers`` and ``falkordb.graph``."""
    global _PATCH_LOCK
    if _PATCH_LOCK:
        return
    try:
        import falkordb.graph as fdg
        import falkordb.helpers as fdh
    except ImportError:
        logger.warning("falkordb is not installed; skipping FalkorDB stringify patch")
        _PATCH_LOCK = True
        return
    if getattr(fdh, "_flexible_graphrag_stringify_patched", False):
        _PATCH_LOCK = True
        return
    fdh._flexible_graphrag_original_stringify = fdh.stringify_param_value
    fdh.stringify_param_value = _flexible_stringify_param_value
    fdg._flexible_graphrag_original_stringify = getattr(fdg, "stringify_param_value", fdh._flexible_graphrag_original_stringify)
    fdg.stringify_param_value = _flexible_stringify_param_value
    fdh._flexible_graphrag_stringify_patched = True
    _PATCH_LOCK = True
    logger.debug("FalkorDB stringify_param_value patched (helpers + graph module, bool, numpy, map keys)")
