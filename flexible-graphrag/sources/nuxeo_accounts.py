"""Which Nuxeo credentials an ingest or an auto sync uses.

A request brings its own credentials (a user's token from KG Spaces for Nuxeo Web UI, or a user name and password
from a source form), and they may be for any Nuxeo server. The backend's own account (NUXEO_URL, NUXEO_AUTH_METHOD,
NUXEO_USERNAME / NUXEO_PASSWORD, NUXEO_TOKEN, NUXEO_OAUTH2_*) belongs to one server, NUXEO_URL, and is used for that
server only:

- as the fallback when a request or a sync has no credentials;
- for an auto sync, instead of the credentials it was registered with, when NUXEO_SYNC_CREDENTIALS=account;
- by a running sync whose credentials stop working (a revoked token, say): incremental_updates/detectors/
  nuxeo_detector.py switches to it.

NUXEO_SYNC_CREDENTIALS: ``token`` (default) keeps a sync's own credentials, so syncs of any Nuxeo server work and
each reads as the user who started it; ``account`` runs syncs of the backend's server as the backend's account.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

# the fields that carry a credential (url, path and the selection are not)
CREDENTIAL_FIELDS = ("auth_method", "username", "password", "token", "oauth2")


def server_key(url: Optional[str]) -> str:
    """A Nuxeo server's address in one comparable form: host:port/context, lower case, no scheme, no trailing
    slash (``http://Nuxeo:8080/nuxeo/`` and ``http://nuxeo:8080/nuxeo`` are the same server)."""
    if not url:
        return ""
    parts = urlsplit(url.strip() if "//" in url else f"//{url.strip()}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return f"{(parts.hostname or '').lower()}:{port}{parts.path.rstrip('/').lower()}"


def has_credentials(config: Dict[str, Any]) -> bool:
    return bool(config.get("token") or config.get("password") or config.get("oauth2"))


def backend_account(url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The backend's own Nuxeo credentials (the NUXEO_* settings), or None when it has none, or when ``url`` is
    given and is not the backend's server (NUXEO_URL)."""
    backend_url = os.getenv("NUXEO_URL", "").strip()
    if not backend_url or (url is not None and server_key(url) != server_key(backend_url)):
        return None
    account: Dict[str, Any] = {"auth_method": (os.getenv("NUXEO_AUTH_METHOD") or "basic").lower()}
    for key, env in (("username", "NUXEO_USERNAME"), ("password", "NUXEO_PASSWORD"), ("token", "NUXEO_TOKEN")):
        value = os.getenv(env)
        if value:
            account[key] = value
    oauth2 = {k: v for k, v in {
        "client_id": os.getenv("NUXEO_OAUTH2_CLIENT_ID"),
        "client_secret": os.getenv("NUXEO_OAUTH2_CLIENT_SECRET"),
        "access_token": os.getenv("NUXEO_OAUTH2_ACCESS_TOKEN"),
        "refresh_token": os.getenv("NUXEO_OAUTH2_REFRESH_TOKEN"),
        "token_endpoint": os.getenv("NUXEO_OAUTH2_TOKEN_ENDPOINT"),
        "openid_configuration_url": os.getenv("NUXEO_OAUTH2_OPENID_CONFIG_URL"),
    }.items() if v}
    if oauth2:
        account["oauth2"] = oauth2
    return account if has_credentials(account) else None


def with_account(config: Dict[str, Any], account: Dict[str, Any]) -> Dict[str, Any]:
    """``config`` with its credentials replaced by ``account``'s (everything else kept)."""
    return {**{k: v for k, v in config.items() if k not in CREDENTIAL_FIELDS}, **account}


def fill_missing(config: Dict[str, Any]) -> Dict[str, Any]:
    """The fallback: a config without credentials gets the backend's account, if it is for the backend's
    server."""
    if has_credentials(config):
        return config
    account = backend_account(config.get("url"))
    if account is None:
        return config
    logger.info("Nuxeo: no credentials in the request; using the backend's account for %s", config.get("url"))
    return with_account(config, account)


def sync_mode() -> str:
    """NUXEO_SYNC_CREDENTIALS: ``token`` (default) or ``account``."""
    mode = (os.getenv("NUXEO_SYNC_CREDENTIALS") or "token").strip().lower()
    if mode not in ("token", "account"):
        logger.warning("NUXEO_SYNC_CREDENTIALS=%r: use token or account; using token", mode)
        return "token"
    return mode


def for_sync(config: Dict[str, Any]) -> Dict[str, Any]:
    """The credentials an auto sync is stored with: its own (NUXEO_SYNC_CREDENTIALS=token), or the backend's account
    for the backend's server (=account); the backend's account either way when it has none."""
    if sync_mode() == "account":
        account = backend_account(config.get("url"))
        if account is not None:
            logger.info("Nuxeo sync: NUXEO_SYNC_CREDENTIALS=account, storing the backend's account for %s",
                        config.get("url"))
            return with_account(config, account)
    return fill_missing(config)
