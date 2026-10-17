"""Answer only from documents the asking user may read (query-time permission filtering).

Permissions are checked when the question is asked, never stored at ingest: ACLs change after
a document is indexed, and only the repository knows them now. A request carries the user's
Alfresco identity -- a ticket (``X-Alfresco-Ticket``, sent by KG Spaces in ACA) or the same
``alfresco_config`` credentials ingest takes (basic / ticket / oauth2), as an ``Authorization``
header (sources/alfresco_auth.alfresco_authorization); the candidate documents are then checked
against Alfresco with it -- a node the user can fetch is one they may read
(403 / 404 otherwise) -- and the readable ones become the question's scope, so every store's
in-store filter and scope_filter.ScopedRetriever keep the answer inside them.

Only Alfresco documents are checked: their stable doc id ends in ``alfresco://<node id>``.
Documents from other sources are not governed by Alfresco permissions and stay visible.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_ALFRESCO_MARK = "alfresco://"
_CACHE_TTL = 60.0  # seconds a (credential, node) answer is reused: a few questions in a row
_cache: Dict[Tuple[str, str, str], Tuple[float, bool]] = {}


def alfresco_node_id(doc_id: str) -> Optional[str]:
    """The Alfresco node id inside a stable doc id (``{config_id}:alfresco://{node}``), or None."""
    i = (doc_id or "").find(_ALFRESCO_MARK)
    if i < 0:
        return None
    return doc_id[i + len(_ALFRESCO_MARK):] or None


def without_alfresco(doc_ids: Iterable[str]) -> List[str]:
    """``doc_ids`` minus every Alfresco document: what a caller with no Alfresco identity may see
    when ALFRESCO_QUERY_AUTH=required."""
    return [d for d in dict.fromkeys(doc_ids) if alfresco_node_id(d) is None]


def _rest_base(url: str) -> str:
    """The repository's base URL for the public REST API (an ``/alfresco`` suffix dropped)."""
    url = (url or "").strip().rstrip("/")
    return url[: -len("/alfresco")] if url.lower().endswith("/alfresco") else url


async def _can_read(client, base: str, node_id: str, authorization: str, home: str = "") -> bool:
    key = (authorization, base, node_id)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        r = await client.get(
            f"{base}/alfresco/api/-default-/public/alfresco/versions/1/nodes/{node_id}",
            params={"fields": "id"}, headers={"Authorization": authorization},
        )
        ok = r.status_code == 200
        if r.status_code == 401:
            if not home or base == home:
                raise PermissionError("the Alfresco credentials were refused (expired or invalid)")
            # A different Alfresco server than the one this credential belongs to (e.g. ACA's
            # ticket and a document from a second repository): not readable with this identity --
            # leave the document out rather than failing the whole question.
            logger.info(f"Node {node_id} on {base}: this Alfresco identity is not valid there; left out")
    except PermissionError:
        raise
    except Exception as e:
        logger.warning(f"Permission check for node {node_id} failed, treating as not readable: {e}")
        ok = False
    _cache[key] = (time.monotonic(), ok)
    return ok


def forget(authorization: str) -> None:
    """Drop the cached answers for one credential -- on sign-out, so a ticket that was just
    invalidated is not honoured for the rest of the cache window. (A ticket that expires on its
    own can still be honoured for up to _CACHE_TTL seconds.)"""
    for key in [k for k in _cache if k[0] == authorization]:
        _cache.pop(key, None)


async def readable_doc_ids(doc_ids: Iterable[str], authorization: str,
                           repo_url_for_doc, default_url: Optional[str] = None) -> List[str]:
    """``doc_ids`` minus the Alfresco documents the caller may not read. ``authorization`` is the
    ``Authorization`` header value that identifies the caller to Alfresco.

    ``repo_url_for_doc(doc_id)`` names the Alfresco server a document came from (its
    datasource's url); ``default_url`` is used when it names none.
    """
    import httpx
    doc_ids = list(dict.fromkeys(doc_ids))
    keep: Set[str] = {d for d in doc_ids if alfresco_node_id(d) is None}
    checks = []
    for d in doc_ids:
        node = alfresco_node_id(d)
        if node is None:
            continue
        base = _rest_base(repo_url_for_doc(d) or default_url or "")
        if not base:
            logger.warning(f"No Alfresco URL for {d}; leaving it out")
            continue
        checks.append((d, base, node))
    # The server the credential belongs to: only a refusal there means "sign in again"
    home = _rest_base(default_url or "")
    if checks:
        async with httpx.AsyncClient(timeout=10.0) as client:
            results = await asyncio.gather(*(_can_read(client, b, n, authorization, home) for _, b, n in checks))
        keep |= {d for (d, _, _), ok in zip(checks, results) if ok}
    out = [d for d in doc_ids if d in keep]
    logger.info(f"Permissions: {len(out)} of {len(doc_ids)} candidate document(s) readable")
    return out
