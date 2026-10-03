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
