"""Nuxeo identity for sign-in and query-time permission checks.

The Nuxeo counterpart of the sign-in half of sources/alfresco_auth.py
(planning/SOURCE-AUTH-LOGIN.md):

- ``nuxeo_login``      username/password -> a Nuxeo auth token (``GET /authentication/token``),
                       the same endpoint NuxeoSource uses for ``auth_method: token``.
- ``nuxeo_token_user`` whose a token is (``GET /api/v1/me``); PermissionError once revoked.
- ``nuxeo_headers``    a request credential (basic / token / oauth2) -> HTTP headers.

Unlike an Alfresco ticket, a Nuxeo token does not expire: it lasts until it is revoked (Nuxeo Web
UI > user settings > Authentication Tokens). Nuxeo returns the SAME token for the same user,
application and device, so signing in again does not pile up tokens. The UIs' sign-out only
forgets the token locally, because an ingest from the sign-in may have stored that token as an
Auto Sync credential.
"""

import base64
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TOKEN_APPLICATION = "flexible-graphrag"
UI_DEVICE_ID = "flexible-graphrag-ui"


def nuxeo_base(url: str) -> str:
    """The Nuxeo server URL as configured (``http://host:8081/nuxeo``), no trailing slash."""
    return (url or "").strip().rstrip("/")


def nuxeo_headers(
    auth_method: Optional[str] = None,
    username: str = "",
    password: str = "",
    token: Optional[str] = None,
    oauth2: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, str]]:
    """The headers that make Nuxeo REST (and CMIS) calls as the given identity, or None when no
    credential was supplied. Method omitted = token if only a token is given, else basic."""
    method = (auth_method or ("token" if token and not username else "basic")).lower()
    if method == "oauth2":
        access = (oauth2 or {}).get("access_token")
        return {"Authorization": f"Bearer {access}"} if access else None
    if method == "token" and token:
        return {"X-Authentication-Token": token}
    if username:
        return {"Authorization": "Basic " + base64.b64encode(f"{username}:{password or ''}".encode()).decode()}
    return None


async def nuxeo_login(url: str, username: str, password: str,
                      device_id: str = UI_DEVICE_ID) -> Dict[str, str]:
    """Get a token for username/password: ``{"token", "user_id"}``. Raises PermissionError when
    Nuxeo refuses the credentials (it answers a bad password with a redirect to its login page)."""
    import httpx
    base = nuxeo_base(url)
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        r = await client.get(
            base + "/authentication/token",
            params={"applicationName": TOKEN_APPLICATION, "deviceId": device_id,
                    "deviceDescription": "Flexible GraphRAG sign-in", "permission": "rw"},
            auth=(username, password),
        )
        if r.status_code in (301, 302, 303, 401, 403):
            raise PermissionError("Nuxeo refused the username or password")
        r.raise_for_status()
        token = (r.text or "").strip()
        if not token:
            raise RuntimeError("Nuxeo's token endpoint returned no token")
    return {"token": token, "user_id": await nuxeo_token_user(base, token)}


async def nuxeo_token_user(url: str, token: str) -> str:
    """The user a token belongs to; PermissionError if it is not (or no longer) valid."""
    import httpx
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        r = await client.get(nuxeo_base(url) + "/api/v1/me", headers={"X-Authentication-Token": token})
    if r.status_code in (301, 302, 303, 401, 403):
        raise PermissionError("the Nuxeo token is no longer valid (revoked)")
    r.raise_for_status()
    return r.json().get("id", "")
