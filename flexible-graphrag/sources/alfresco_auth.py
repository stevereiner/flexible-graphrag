"""Shared Alfresco authentication helper.

One place that turns an Alfresco source config into a python-alfresco-api auth util,
so the ingest source, the incremental-update detector and any other caller cannot
drift apart on what `auth_method` means.

Three methods are supported:

- ``basic``   username/password; returns None so ClientFactory builds its own auth.
- ``ticket``  either *acquire* (username/password, a ticket is fetched on demand) or
              *pass-through* (a ``ticket`` the caller already holds, e.g. one an ADF
              front end obtained at login). Pass-through needs no password.
- ``oauth2``  client_credentials/refresh, or a pre-obtained access_token -> Bearer.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def build_alfresco_auth_util(
    api_base_url: str,
    auth_method: str,
    username: str = "",
    password: str = "",
    ticket: Optional[str] = None,
    oauth2: Optional[Dict[str, Any]] = None,
    verify_ssl: Any = True,
    timeout: Optional[int] = None,
):
    """Build an auth util for the configured method, or None to mean plain basic auth.

    A ticket supplied by the caller is never downgraded to basic auth on failure:
    there is no password to fall back to, and falling back to whatever username
    happens to be in the config would authenticate as the wrong identity.
    """
    method = (auth_method or "basic").lower()

    if method == "ticket":
        from python_alfresco_api.auth_util import TicketAuthUtil

        if ticket:
            logger.info("Using Alfresco ticket authentication (caller-supplied ticket)")
            return TicketAuthUtil(
                base_url=api_base_url, ticket=ticket,
                verify_ssl=verify_ssl, timeout=timeout,
            )

        try:
            logger.info("Using Alfresco ticket authentication (acquired from username/password)")
            return TicketAuthUtil(
                username, password, base_url=api_base_url,
                verify_ssl=verify_ssl, timeout=timeout,
            )
        except Exception as e:
            logger.warning(f"Ticket auth setup failed, falling back to basic: {e}")
            return None

    if method == "oauth2":
        try:
            from python_alfresco_api.auth_util import OAuth2AuthUtil

            o = oauth2 or {}
            logger.info("Using Alfresco OAuth2 (Bearer) authentication")
            return OAuth2AuthUtil(
                base_url=api_base_url,
                client_id=o.get("client_id", ""),
                client_secret=o.get("client_secret"),
                token_endpoint=o.get("token_endpoint"),
                grant_type=o.get("grant_type") or "client_credentials",
                scope=o.get("scope"),
                access_token=o.get("access_token"),
                refresh_token=o.get("refresh_token"),
                load_env=False,
            )
        except Exception as e:
            logger.warning(f"OAuth2 auth setup failed, falling back to basic: {e}")
            return None

    return None  # basic


def alfresco_authorization(
    api_base_url: str,
    auth_method: Optional[str] = None,
    username: str = "",
    password: str = "",
    ticket: Optional[str] = None,
    oauth2: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """The ``Authorization`` header value that makes Alfresco REST calls as the given identity,
    or None when no credential was supplied.

    Used for query-time permission checks (permission_filter.py), which ask Alfresco whether
    *this* caller may read a node. Same three methods as ingest:

    - ``ticket``  a caller-held ticket -> ``Basic base64(<ticket>)`` (the bare ticket, no colon);
                  with username/password instead it is checked as basic auth below.
    - ``basic``   ``Basic base64(user:password)`` (Alfresco accepts it on every REST call).
    - ``oauth2``  ``Bearer <token>``: a supplied access_token, else one fetched through
                  python-alfresco-api's OAuth2AuthUtil (client_credentials / refresh_token).
    Blocking for oauth2 token fetches -- call it in a worker thread.
    """
    import base64

    method = (auth_method or ("ticket" if ticket and not username else "basic")).lower()
    if method == "oauth2":
        o = oauth2 or {}
        if o.get("access_token"):
            return f"Bearer {o['access_token']}"
        util = build_alfresco_auth_util(api_base_url, "oauth2", oauth2=o)
        header = (util.get_auth_headers() if util is not None else {}).get("Authorization")
        if not header:
            raise PermissionError("could not obtain an Alfresco OAuth2 access token")
        return header
    if ticket and method == "ticket":
        return "Basic " + base64.b64encode(ticket.encode()).decode()
    if username:
        return "Basic " + base64.b64encode(f"{username}:{password or ''}".encode()).decode()
    return None


# ---------------------------------------------------------------------------
# Sign-in for the UIs (planning/SOURCE-AUTH-LOGIN.md): the same ticket API ACA/ADF uses.
# Stateless -- the ticket goes back to the caller and is never stored here.
# ---------------------------------------------------------------------------

_TICKETS = "/alfresco/api/-default-/public/authentication/versions/1/tickets"


def _rest_base(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    return url[: -len("/alfresco")] if url.lower().endswith("/alfresco") else url


async def alfresco_login(url: str, username: str, password: str) -> Dict[str, str]:
    """Create a login ticket for username/password: ``{"ticket", "user_id"}``.
    Raises PermissionError when Alfresco refuses the credentials."""
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(_rest_base(url) + _TICKETS, json={"userId": username, "password": password})
    if r.status_code in (400, 401, 403):
        raise PermissionError("Alfresco refused the username or password")
    r.raise_for_status()
    entry = r.json()["entry"]
    return {"ticket": entry["id"], "user_id": entry.get("userId") or username}


async def alfresco_ticket_user(url: str, ticket: str) -> str:
    """The user a ticket belongs to (``GET people/-me-``; ``tickets/-me-`` does not name the
    user); PermissionError if the ticket is no longer valid."""
    import base64
    import httpx
    auth = "Basic " + base64.b64encode(ticket.encode()).decode()
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(_rest_base(url) + "/alfresco/api/-default-/public/alfresco/versions/1/people/-me-",
                             params={"fields": "id"}, headers={"Authorization": auth})
    if r.status_code in (401, 404):
        raise PermissionError("the Alfresco ticket is no longer valid (expired or signed out)")
    r.raise_for_status()
    return r.json()["entry"].get("id", "")


async def alfresco_logout(url: str, ticket: str) -> None:
    """Invalidate a ticket (``DELETE tickets/-me-``). An already invalid ticket is not an error."""
    import base64
    import httpx
    auth = "Basic " + base64.b64encode(ticket.encode()).decode()
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.delete(_rest_base(url) + _TICKETS + "/-me-", headers={"Authorization": auth})
    if r.status_code not in (200, 204, 401, 404):
        r.raise_for_status()
