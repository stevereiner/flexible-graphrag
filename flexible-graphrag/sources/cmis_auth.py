"""CMIS identity: sign-in, request headers and per-vendor adapters.

CMIS itself has no ticket or token API -- each repository behind it has its own. Sign-in therefore
asks the server who it is (``cmis:vendorName`` in the AtomPub service document) and hands off to
that vendor's adapter, which gets a repository credential the way the vendor's own clients do.
Nobody's password is kept: the UI holds only the ticket / token.

Adapters (measured against ACS 26.2 and Nuxeo 2025, not taken from vendor docs):

| vendor   | sign-in                       | credential on CMIS calls                        |
|----------|-------------------------------|-------------------------------------------------|
| Alfresco | REST ``POST .../tickets``     | ``Authorization: Basic base64(ROLE_TICKET:<t>)`` |
| Nuxeo    | ``GET /authentication/token`` | ``X-Authentication-Token: <t>``                 |

``user:<ticket>`` and ``user:<token>`` as basic auth are both refused (401) by these servers,
whatever some vendor notes say.

A CMIS server of any other vendor has no adapter: its documents keep path-based doc ids (no
``cmis://``), so they are not permission-checked and stay visible to everyone, as before.
To add a vendor, see docs/DATA-SOURCES/README-cmis-sign-in.md.
"""

import base64
import logging
import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


def _basic(user: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()


def _origin_and_prefix(cmis_url: str, marker: str) -> str:
    """The part of ``cmis_url`` before ``marker`` (e.g. ``/alfresco/``), or its origin."""
    i = cmis_url.lower().find(marker)
    if i >= 0:
        return cmis_url[:i]
    p = urlsplit(cmis_url)
    return f"{p.scheme}://{p.netloc}"


class CmisAdapter:
    """One repository vendor behind CMIS. Subclass and register in ADAPTERS to support another."""

    name = ""            # matched (case-insensitively) inside cmis:vendorName
    auth_method = ""     # how its credential is named in source_auth.cmis / cmis_config

    def headers(self, credential: str) -> Dict[str, str]:
        """HTTP headers that authenticate a CMIS call with ``credential``."""
        raise NotImplementedError

    async def login(self, cmis_url: str, username: str, password: str) -> Dict[str, str]:
        """``{"credential", "user_id"}`` for username/password; PermissionError when refused."""
        raise NotImplementedError

    async def user(self, cmis_url: str, credential: str) -> str:
        """Whose ``credential`` is; PermissionError when it is no longer valid."""
        raise NotImplementedError

    def cmislib_session(self, client, credential: str) -> None:
        """Make a cmislib CmisClient (used by CmisSource for ingest) send ``credential``."""
        client.session.auth = None
        client.session.headers.update(self.headers(credential))


class AlfrescoCmisAdapter(CmisAdapter):
    name = "alfresco"
    auth_method = "ticket"

    def rest_base(self, cmis_url: str) -> str:
        # http://host:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom -> http://host:8080
        return _origin_and_prefix(cmis_url, "/alfresco/")

    def headers(self, credential: str) -> Dict[str, str]:
        return {"Authorization": _basic("ROLE_TICKET", credential)}

    async def login(self, cmis_url, username, password):
        from sources.alfresco_auth import alfresco_login
        r = await alfresco_login(self.rest_base(cmis_url), username, password)
        return {"credential": r["ticket"], "user_id": r["user_id"]}

    async def user(self, cmis_url, credential):
        from sources.alfresco_auth import alfresco_ticket_user
        return await alfresco_ticket_user(self.rest_base(cmis_url), credential)


class NuxeoCmisAdapter(CmisAdapter):
    name = "nuxeo"
    auth_method = "token"

    def nuxeo_url(self, cmis_url: str) -> str:
        # http://host:8081/nuxeo/atom/cmis -> http://host:8081/nuxeo
        return _origin_and_prefix(cmis_url, "/nuxeo/") + "/nuxeo"

    def headers(self, credential: str) -> Dict[str, str]:
        return {"X-Authentication-Token": credential}

    async def login(self, cmis_url, username, password):
        from sources.nuxeo_auth import nuxeo_login
        r = await nuxeo_login(self.nuxeo_url(cmis_url), username, password)
        return {"credential": r["token"], "user_id": r["user_id"]}

    async def user(self, cmis_url, credential):
        from sources.nuxeo_auth import nuxeo_token_user
        return await nuxeo_token_user(self.nuxeo_url(cmis_url), credential)


ADAPTERS = [AlfrescoCmisAdapter(), NuxeoCmisAdapter()]


def adapter_for_vendor(vendor: Optional[str]) -> Optional[CmisAdapter]:
    v = (vendor or "").lower()
    return next((a for a in ADAPTERS if a.name in v), None)


def adapter_for_method(auth_method: Optional[str]) -> Optional[CmisAdapter]:
    m = (auth_method or "").lower()
    return next((a for a in ADAPTERS if a.auth_method == m), None)


def cmis_headers(
    auth_method: Optional[str] = None,
    username: str = "",
    password: str = "",
    ticket: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Headers for a CMIS request credential (basic / ticket / token), or None when none given."""
    method = (auth_method or ("ticket" if ticket else "token" if token else "basic")).lower()
    adapter = adapter_for_method(method)
    if adapter is not None:
        credential = ticket if method == "ticket" else token
        return adapter.headers(credential) if credential else None
    if username:
        return {"Authorization": _basic(username, password or "")}
    return None


async def cmis_vendor(cmis_url: str, headers: Dict[str, str]) -> str:
    """``cmis:vendorName`` from the AtomPub service document; PermissionError on 401."""
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(cmis_url, headers=headers)
    if r.status_code in (401, 403):
        raise PermissionError("the CMIS server refused the username or password")
    r.raise_for_status()
    m = re.search(r"<cmis:vendorName>([^<]*)</cmis:vendorName>", r.text)
    return m.group(1).strip() if m else ""


async def cmis_login(cmis_url: str, username: str, password: str) -> Dict[str, str]:
    """Sign in to a CMIS server through its vendor's adapter:
    ``{"auth_method", "ticket"|"token", "user_id", "vendor"}``."""
    vendor = await cmis_vendor(cmis_url, {"Authorization": _basic(username, password)})
    adapter = adapter_for_vendor(vendor)
    if adapter is None:
        raise LookupError(
            f"CMIS sign-in supports Alfresco and Nuxeo servers; this one is "
            f"'{vendor or 'unknown'}'. Its documents are not permission-checked "
            f"(see docs/DATA-SOURCES/README-cmis-sign-in.md to add it).")
    r = await adapter.login(cmis_url, username, password)
    return {"auth_method": adapter.auth_method, adapter.auth_method: r["credential"],
            "user_id": r["user_id"], "vendor": adapter.name}


async def cmis_credential_user(cmis_url: str, auth_method: str, credential: str) -> str:
    adapter = adapter_for_method(auth_method)
    if adapter is None:
        raise PermissionError(f"unknown CMIS auth_method '{auth_method}'")
    return await adapter.user(cmis_url, credential)


def governed_vendor(vendor: Optional[str]) -> bool:
    """Whether documents from a CMIS server of this vendor get ``cmis://`` ids and permission checks."""
    return adapter_for_vendor(vendor) is not None


def split_credential(cfg: Dict) -> Tuple[Optional[CmisAdapter], Optional[str]]:
    """(adapter, credential) for a cmis_config that carries a sign-in ticket / token, else (None, None)."""
    adapter = adapter_for_method(cfg.get("auth_method"))
    if adapter is None:
        return None, None
    return adapter, cfg.get(adapter.auth_method)
