"""Answer only from documents the asking user may read (query-time permission filtering).

Permissions are checked when the question is asked, never stored at ingest: ACLs change after
a document is indexed, and only the repository knows them now. A request carries the user's
identities -- one per repository server they signed in to (``source_auth`` on search / query,
or ``X-Alfresco-Ticket`` from KG Spaces in ACA) -- and each candidate document is checked against
its own repository with the identity for that server: an item the user can fetch is one they may
read (403 / 404 otherwise). The readable ones become the question's scope, so every store's
in-store filter and scope_filter.ScopedRetriever keep the answer inside them.

Governed documents are recognised by the repository id in their stable doc id:

| source   | doc id contains   | check                                        |
|----------|-------------------|----------------------------------------------|
| alfresco | ``alfresco://<node>`` | REST ``GET nodes/{node}``                |
| nuxeo    | ``nuxeo://<uid>``     | REST ``GET /api/v1/id/{uid}``            |
| cmis     | ``cmis://<id>``       | AtomPub ``objectbyid`` (Alfresco / Nuxeo CMIS servers only, sources/cmis_auth.py) |
| sharepoint | ``sharepoint://<item>`` | Graph ``GET /sites/{site}/drive/items/{item}`` (Microsoft 365 sign-in) |
| onedrive | ``onedrive://<item>`` | Graph ``GET /users/{upn}/drive/items/{item}`` (Microsoft 365 sign-in) |

SharePoint and OneDrive are checked only when Microsoft sign-in is configured
(MICROSOFT_AUTH_CLIENT_ID, sources/microsoft_auth.py); one delegated Microsoft 365 token per tenant
covers both.

Documents from other sources are not governed by repository permissions and stay visible.
A governed document whose server the asker has no identity for is left out when that source's
query auth is required (``SOURCE_QUERY_AUTH`` / ``<SOURCE>_QUERY_AUTH``), or when the asker gave
an identity for that source at all (it belongs to another server); otherwise it stays visible.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)

SCHEMES = {"alfresco": "alfresco://", "nuxeo": "nuxeo://", "cmis": "cmis://",
           "sharepoint": "sharepoint://", "onedrive": "onedrive://"}
LABELS = {"alfresco": "Alfresco", "nuxeo": "Nuxeo", "cmis": "CMIS", "sharepoint": "SharePoint",
          "onedrive": "OneDrive", "microsoft": "Microsoft 365", "box": "Box",
          "google_drive": "Google Drive", "gcs": "Google Cloud Storage", "google": "Google",
          "azure_blob": "Azure Blob", "azure": "Azure Storage", "s3": "Amazon S3"}
# The sign-in a source's documents are checked with, when it is not the source itself: one
# Microsoft 365 sign-in (per tenant) covers SharePoint and OneDrive.
AUTH_SOURCE = {"sharepoint": "microsoft", "onedrive": "microsoft", "google_drive": "google", "gcs": "google",
               "azure_blob": "azure"}
GRAPH = "https://graph.microsoft.com/v1.0"


def auth_source(source: str) -> str:
    return AUTH_SOURCE.get(source, source)

_MAX_PARALLEL = 16  # permission checks in flight at once, per question
_CACHE_TTL = 60.0  # seconds a (credential, item) answer is reused: a few questions in a row
_cache: Dict[Tuple, Tuple[float, bool]] = {}
_cmis_templates: Dict[str, str] = {}  # CMIS server -> its objectbyid URI template


class CredentialRefused(PermissionError):
    """A repository refused the asker's credential on its own server: sign in again."""

    def __init__(self, source: str, url: str):
        self.source, self.url = source, url
        super().__init__(f"the {LABELS.get(source, source)} credentials for {url} were refused "
                         f"(expired or invalid) -- sign in again")


@dataclass
class Identity:
    """Who the asker is on one repository server."""
    source: str                 # alfresco | nuxeo | cmis
    url: str                    # the server the credential belongs to
    headers: Dict[str, str] = field(default_factory=dict)

    @property
    def server(self) -> str:
        return server_key(self.source, self.url)

    @property
    def cache_id(self) -> Tuple:
        return (self.source, tuple(sorted(self.headers.items())))


def governed_ref(doc_id: str) -> Optional[Tuple[str, str]]:
    """``(source, repository id)`` for a governed doc id (``{config_id}:nuxeo://{uid}``), or None."""
    for source, mark in SCHEMES.items():
        i = (doc_id or "").find(mark)
        if i >= 0:
            item = doc_id[i + len(mark):]
            return (source, item) if item else None
    return None


def config_id_of(doc_id: str) -> str:
    """The datasource config_id in front of a governed doc id ('' when it has none)."""
    for mark in SCHEMES.values():
        i = (doc_id or "").find(mark)
        if i > 0:
            return doc_id[:i].rstrip(":")
    return ""


def alfresco_node_id(doc_id: str) -> Optional[str]:
    """The Alfresco node id inside a stable doc id (``{config_id}:alfresco://{node}``), or None."""
    ref = governed_ref(doc_id)
    return ref[1] if ref and ref[0] == "alfresco" else None


def _rest_base(url: str) -> str:
    """The repository's base URL for the public REST API (an ``/alfresco`` suffix dropped)."""
    url = (url or "").strip().rstrip("/")
    return url[: -len("/alfresco")] if url.lower().endswith("/alfresco") else url


def server_key(source: str, url: Optional[str]) -> str:
    """One spelling per server, so a credential's url matches its documents' datasource url."""
    url = (url or "").strip().rstrip("/")
    if source == "alfresco":
        url = _rest_base(url)
    return url.lower()


async def _cmis_objectbyid(client, server: str, ident: Identity) -> str:
    template = _cmis_templates.get(server.lower())
    if template:
        return template
    r = await client.get(server, headers=ident.headers)
    if r.status_code == 401:
        raise CredentialRefused("cmis", server)
    r.raise_for_status()
    m = re.search(r"<cmisra:template>([^<]*)</cmisra:template>\s*<cmisra:type>objectbyid<", r.text)
    if not m:
        raise RuntimeError(f"no objectbyid URI template in {server}'s CMIS service document")
    template = m.group(1).replace("&amp;", "&")
    _cmis_templates[server.lower()] = template
    return template


_CMIS_ARGS = {"filter": "cmis:objectId", "includeAllowableActions": "false", "includeACL": "false",
              "includePolicyIds": "false", "includeRelationships": "none", "renditionFilter": "cmis:none"}


_sp_sites: Dict[Tuple, str] = {}  # (identity, site name) -> Graph site id


async def _sharepoint_site_id(client, ctx: Dict[str, str], ident: Identity) -> str:
    """The Graph site id of a SharePoint datasource's site: configured, or resolved by name as the user."""
    if ctx.get("site_id"):
        return ctx["site_id"]
    name = ctx.get("site_name") or ""
    if not name:
        raise RuntimeError("the SharePoint datasource names no site")
    key = (ident.cache_id, name.lower())
    if key not in _sp_sites:
        r = await client.get(f"{GRAPH}/sites/root:/sites/{quote(name, safe='')}", params={"$select": "id"},
                             headers=ident.headers)
        if r.status_code == 401:
            raise CredentialRefused("microsoft", ident.url)
        r.raise_for_status()
        _sp_sites[key] = r.json()["id"]
    return _sp_sites[key]


async def _check_url(client, source: str, server: str, item: str, ident: Identity,
                     ctx: Optional[Dict[str, str]] = None) -> str:
    ctx = ctx or {}
    if source == "sharepoint":
        site = await _sharepoint_site_id(client, ctx, ident)
        return f"{GRAPH}/sites/{site}/drive/items/{quote(item, safe='')}?$select=id"
    if source == "azure_blob":
        # `item`: "<container>/<blob name>" (the doc id after its config_id); the account from the
        # datasource. Get Blob Metadata: headers only, the blob's content is never downloaded.
        account = (ctx.get("account_url") or "").rstrip("/")
        if not account:
            raise RuntimeError("the Azure Blob datasource names no storage account")
        container, _, blob = item.partition("/")
        return f"{account}/{quote(container, safe='')}/{quote(blob, safe='/')}?comp=metadata"
    if source == "google_drive":
        # `item`: the Drive file id (document_state.source_id)
        return (f"https://www.googleapis.com/drive/v3/files/{quote(item, safe='')}"
                f"?fields=id&supportsAllDrives=true")
    if source == "gcs":
        # `item`: "<bucket>/<object name>" (the GCS doc id after its config_id)
        bucket, _, name = item.partition("/")
        return (f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/"
                f"{quote(name, safe='')}?fields=name")
    if source == "box":
        # Box documents keep path doc ids; `item` is their Box file id (document_state.source_id)
        return f"https://api.box.com/2.0/files/{quote(item, safe='')}?fields=id"
    if source == "onedrive":
        upn = ctx.get("user_principal_name")
        if not upn:
            raise RuntimeError("the OneDrive datasource names no user_principal_name")
        return f"{GRAPH}/users/{quote(upn, safe='@')}/drive/items/{quote(item, safe='')}?$select=id"
    if source == "alfresco":
        return (f"{_rest_base(server)}/alfresco/api/-default-/public/alfresco/versions/1/nodes/"
                f"{quote(item, safe='')}?fields=id")
    if source == "nuxeo":
        return f"{server.rstrip('/')}/api/v1/id/{quote(item, safe='')}"
    template = await _cmis_objectbyid(client, server, ident)
    args = {**_CMIS_ARGS, "id": quote(item, safe="")}
    return re.sub(r"\{(\w+)\}", lambda m: args.get(m.group(1), ""), template)


S3_TOKEN_HEADER = "X-S3-Token"  # an S3 Identity's packed session credentials (never sent as is)


async def _s3_can_read(client, item: str, ident: Identity, ctx: Dict[str, str]) -> bool:
    """An S3 object ("<bucket>/<key>") as the user: a signed 1-byte ranged GET (sources/s3_auth.py).
    Every request needs its own SigV4 signature, so the Identity carries the credentials instead
    of fixed headers."""
    from sources.s3_auth import REFUSED_CODES, _error_code, object_request, unpack
    try:
        creds = unpack(ident.headers.get(S3_TOKEN_HEADER, ""))
    except PermissionError:
        raise CredentialRefused("s3", ident.url)
    url, headers = object_request(item, creds, ctx.get("region", ""))
    r = await client.get(url, headers=headers)
    if r.status_code in (200, 206, 416):  # 416: an empty object, which the user may still read
        return True
    code = _error_code(r.text)
    if code in REFUSED_CODES:
        raise CredentialRefused("s3", ident.url)
    if r.status_code in (301, 307, 400) and code not in ("", "AccessDenied"):
        logger.warning(f"S3 check for {item} failed ({r.status_code} {code}): is the datasource's region right?")
    return False


async def _can_read(client, source: str, server: str, item: str, ident: Identity,
                    ctx: Optional[Dict[str, str]] = None) -> bool:
    key = (ident.cache_id, server_key(source, server), item)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        if source == "s3":
            ok = await _s3_can_read(client, item, ident, ctx or {})
            _cache[key] = (time.monotonic(), ok)
            return ok
        r = await client.get(await _check_url(client, source, server, item, ident, ctx), headers=ident.headers)
        if r.status_code == 401 or (source == "nuxeo" and r.status_code in (302, 303)):
            raise CredentialRefused(auth_source(source), ident.url or server)
        ok = r.status_code == 200
    except PermissionError:
        raise
    except Exception as e:
        logger.warning(f"Permission check for {source} item {item} failed, treating as not readable: {type(e).__name__}: {e!r}")
        ok = False
    _cache[key] = (time.monotonic(), ok)
    return ok


def forget(identity_or_authorization) -> None:
    """Drop the cached answers for one credential -- on sign-out, so a ticket that was just
    invalidated is not honoured for the rest of the cache window. (A ticket that expires on its
    own can still be honoured for up to _CACHE_TTL seconds.) Takes an Identity or a bare
    Authorization header value."""
    if isinstance(identity_or_authorization, Identity):
        drop = lambda k: k[0] == identity_or_authorization.cache_id
    else:
        drop = lambda k: any(v == identity_or_authorization for _, v in k[0][1])
    for key in [k for k in _cache if drop(k)]:
        _cache.pop(key, None)


@dataclass
class Readable:
    doc_ids: List[str]                                    # what the asker may read
    unsigned: Set[str] = field(default_factory=set)       # sources left out for want of a sign-in


async def readable_doc_ids(
    doc_ids: Iterable[str],
    identities: List[Identity],
    server_for_doc: Callable[[str], Optional[str]],
    default_urls: Optional[Dict[str, str]] = None,
    required: Callable[[str], bool] = lambda source: True,
    governed: Optional[Iterable[str]] = None,
    context_for_doc: Callable[[str], Optional[Dict[str, str]]] = lambda doc_id: None,
    ref_for_doc: Callable[[str], Optional[Tuple[str, str]]] = lambda doc_id: None,
) -> Readable:
    """``doc_ids`` minus the governed documents the asker may not read.

    ``server_for_doc(doc_id)`` names the server a document came from (its datasource's url);
    ``default_urls[source]`` is used when it names none. ``required(source)`` says whether a
    document of that source is left out when the asker has no identity for it at all.
    ``governed`` limits the checked sources (default: every scheme; SharePoint / OneDrive only
    when Microsoft sign-in is configured). Identities, ``default_urls`` and ``required`` are keyed
    by the sign-in source (auth_source: "microsoft" for SharePoint / OneDrive, whose "server" is
    the tenant). ``context_for_doc`` gives a document's datasource details a check needs
    (SharePoint site, OneDrive user). ``ref_for_doc`` names the (source, repository id) of a document
    whose doc id carries none -- a Box document's path id -> ("box", its Box file id). Raises
    CredentialRefused when a server refuses the identity given for it.
    """
    import httpx
    default_urls = default_urls or {}
    doc_ids = list(dict.fromkeys(doc_ids))
    by_source: Dict[str, List[Identity]] = {}
    for ident in identities:
        by_source.setdefault(ident.source, []).append(ident)

    keep: Set[str] = set()
    unsigned: Set[str] = set()
    checks = []
    governed_set = set(governed) if governed is not None else set(SCHEMES)
    for d in doc_ids:
        ref = governed_ref(d) or ref_for_doc(d)
        if ref is None or ref[0] not in governed_set:
            keep.add(d)
            continue
        source, item = ref
        auth = auth_source(source)
        idents = by_source.get(auth)
        if not idents:
            if required(auth):
                unsigned.add(auth)
            else:
                keep.add(d)
            continue
        server = server_for_doc(d) or default_urls.get(auth) or ""
        match = next((i for i in idents if i.server == server_key(auth, server)), None)
        if not server or match is None:
            # A server this asker gave no identity for (e.g. ACA's ticket and a second Alfresco)
            logger.info(f"{d}: no {LABELS[auth]} identity for {server or 'an unknown server'}; left out")
            unsigned.add(auth)
            continue
        checks.append((d, source, server, item, match, context_for_doc(d)))
    if checks:
        # a whole source can be in scope (the UIs' source picker): don't open hundreds of requests at once
        limit = asyncio.Semaphore(_MAX_PARALLEL)
        refused: List[CredentialRefused] = []

        async def check(s, srv, i, ident, ctx):
            async with limit:
                if refused:  # a refused credential ends the question: skip the checks still queued
                    return False
                try:
                    return await _can_read(client, s, srv, i, ident, ctx)
                except CredentialRefused as e:
                    refused.append(e)
                    return False

        # every check finishes before the client closes, so those still in flight when one is
        # refused end normally instead of failing (and logging) on a closed connection
        async with httpx.AsyncClient(timeout=10.0) as client:
            results = await asyncio.gather(*(check(s, srv, i, ident, ctx) for _, s, srv, i, ident, ctx in checks))
        if refused:
            raise refused[0]
        keep |= {c[0] for c, ok in zip(checks, results) if ok}
    out = [d for d in doc_ids if d in keep]
    logger.info(f"Permissions: {len(out)} of {len(doc_ids)} candidate document(s) readable"
                + (f"; no sign-in for {', '.join(sorted(unsigned))}" if unsigned else ""))
    return Readable(out, unsigned)
