"""Popup sign-in for repositories whose users sign in at the vendor (OAuth 2.0 authorization code):
Microsoft 365 (SharePoint + OneDrive), Box, Google (Google Drive + Cloud Storage) and Azure
Storage (Azure Blob), so far.

The backend owns the redirect URI and swaps the code for a *delegated* token with the app's client
secret, so the UIs need no vendor library:

1. In the click, the UI opens a popup on ``GET /api/auth/<provider>/popup?state=<random>`` (a real
   URL, so nothing has to be written into the popup afterwards -- browsers may refuse that). The
   backend records the sign-in, sets a short-lived HttpOnly cookie binding it to this browser, and
   redirects the popup to the vendor's login.
2. The vendor returns the popup to ``/api/auth/<provider>/callback`` (Microsoft as a form POST, so
   the code never appears in a logged URL; Box in the query string, which the access log filter
   in main.py redacts); the backend exchanges the code and the popup closes.
3. The UI polls ``GET /api/auth/<provider>/result?state=...`` (with that cookie) ->
   ``{access_token, user_id, url, expires_at}`` once. ``url`` is the "server" the identity belongs
   to (Microsoft: the tenant id). The cookie means knowing a state is not enough to collect
   someone else's token.

A provider is configured -- and its sources' documents permission-checked -- only when its
client id is set (e.g. MICROSOFT_AUTH_CLIENT_ID, BOX_AUTH_CLIENT_ID).
"""

import re
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

_PENDING_TTL = 600.0  # seconds a started sign-in / its result is kept
pending: Dict[str, Dict[str, Any]] = {}  # state -> {provider, redirect_uri, created, binder, result | error}


class PopupProvider:
    """One vendor's sign-in. Subclasses fill in the endpoints and how to name the user / server."""
    name = ""             # URL segment and source_auth key: "microsoft", "box"
    label = ""            # "Microsoft 365", "Box"
    form_post = False     # the vendor can return the code in a POST body (keeps it out of logs)

    def config(self) -> Optional[Dict[str, str]]:
        raise NotImplementedError

    def authorize_url(self, cfg: Dict[str, str], redirect_uri: str, state: str,
                      login_hint: Optional[str]) -> str:
        raise NotImplementedError

    async def exchange(self, cfg: Dict[str, str], code: str, redirect_uri: str) -> Dict[str, Any]:
        """The token response; RuntimeError with the vendor's reason when refused."""
        raise NotImplementedError

    async def user(self, access_token: str) -> str:
        """Whose the token is; PermissionError when it is expired / invalid."""
        raise NotImplementedError

    def server(self, cfg: Dict[str, str], access_token: str) -> str:
        """The server the identity belongs to (matched to documents' datasources)."""
        raise NotImplementedError


def _expire() -> None:
    now = time.monotonic()
    for state in [s for s, p in pending.items() if now - p["created"] > _PENDING_TTL]:
        pending.pop(state, None)


def start(provider: PopupProvider, redirect_uri: str, state: str, binder: str,
          login_hint: Optional[str] = None) -> str:
    """Record a new sign-in and return the vendor's authorize URL. ``state`` comes from the UI
    (random, at least 32 URL-safe characters); ``binder`` is the cookie value the result is
    released to; ``login_hint`` (the account used last time) skips the account picker where the
    vendor supports it."""
    cfg = provider.config()
    if cfg is None:
        raise LookupError(f"{provider.label} sign-in is not configured ({provider.name.upper()}_AUTH_CLIENT_ID)")
    _expire()
    if len(state) < 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", state) or state in pending:
        raise ValueError("state must be a new random string of at least 32 URL-safe characters")
    pending[state] = {"provider": provider.name, "redirect_uri": redirect_uri,
                      "created": time.monotonic(), "binder": binder}
    return provider.authorize_url(cfg, redirect_uri, state, login_hint)


async def finish(provider: PopupProvider, state: str, code: Optional[str], error: Optional[str] = None) -> bool:
    """The callback: exchange ``code`` and keep the result for ``result(state)``. False for an
    unknown / expired state (or one started for another provider)."""
    _expire()
    p = pending.get(state)
    if p is None or p["provider"] != provider.name:
        return False
    if error or not code:
        p["error"] = error or "no authorization code"
        return True
    cfg = provider.config()
    try:
        token = await provider.exchange(cfg, code, p["redirect_uri"])
        user = await provider.user(token["access_token"])
    except Exception as e:
        p["error"] = str(e) or "the sign-in could not be completed"
        return True
    p["result"] = {
        "access_token": token["access_token"],
        "user_id": user,
        "url": provider.server(cfg, token["access_token"]),
        "expires_at": int(time.time()) + int(token.get("expires_in", 3600)),
    }
    return True


def result(provider: PopupProvider, state: str, binder: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """None while the user is still signing in; then the result or ``{"error": ...}``, given out
    once -- and only to the browser holding the sign-in's cookie (``binder``)."""
    _expire()
    p = pending.get(state)
    if (p is None or p["provider"] != provider.name
            or (p.get("binder") and not secrets.compare_digest(p["binder"], binder or ""))):
        return {"error": "unknown or expired sign-in"}
    if "result" in p or "error" in p:
        pending.pop(state, None)
        return p.get("result") or {"error": p["error"]}
    return None


# ---- browser handoff: the same sign-in for a caller with no browser of its own (MCP) -------------
#
# Like a TV's "enter this code" sign-in. The caller (e.g. the MCP server) gets a link and a short
# code; the user opens the link in any browser, sees the code on a confirmation page, checks it
# matches the one their client shows, and continues to the vendor's login. The caller collects the
# token with a secret poll key it never shows (POSTed, so it is in no URL), which plays the part
# of the popup's cookie. The code check is what stops a sign-in link sent by someone else from
# handing that someone the user's token.

handoffs: Dict[str, Dict[str, Any]] = {}  # handoff id -> {provider, user_code, poll_key, state, created}
_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"  # no vowels (no accidental words), no look-alikes


def _expire_handoffs() -> None:
    now = time.monotonic()
    for hid in [h for h, v in handoffs.items() if now - v["created"] > _PENDING_TTL]:
        handoffs.pop(hid, None)


def start_handoff(provider: PopupProvider) -> Dict[str, Any]:
    """A new handoff: ``{handoff_id, user_code, poll_key, expires_in}``. The link to open is
    ``/api/auth/<provider>/handoff/<handoff_id>``."""
    if provider.config() is None:
        raise LookupError(f"{provider.label} sign-in is not configured ({provider.name.upper()}_AUTH_CLIENT_ID)")
    _expire_handoffs()
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    h = {"provider": provider.name, "user_code": f"{code[:4]}-{code[4:]}",
         "poll_key": secrets.token_urlsafe(32), "state": None, "created": time.monotonic()}
    hid = secrets.token_urlsafe(24)
    handoffs[hid] = h
    return {"handoff_id": hid, "user_code": h["user_code"], "poll_key": h["poll_key"],
            "expires_in": int(_PENDING_TTL)}


def handoff(provider: PopupProvider, handoff_id: str) -> Optional[Dict[str, Any]]:
    """A live handoff for this provider, or None."""
    _expire_handoffs()
    h = handoffs.get(handoff_id or "")
    return h if h and h["provider"] == provider.name else None


def continue_handoff(provider: PopupProvider, handoff_id: str, redirect_uri: str) -> str:
    """The user confirmed the code: start the vendor sign-in, bound to the poll key (once)."""
    h = handoff(provider, handoff_id)
    if h is None:
        raise ValueError("this sign-in link has expired: start the sign-in again from your client")
    if h["state"]:
        raise ValueError("this sign-in link was already used: start the sign-in again from your client")
    h["state"] = secrets.token_urlsafe(32)
    url = start(provider, redirect_uri, h["state"], h["poll_key"])
    pending[h["state"]]["handoff"] = True
    return url


def handoff_result(provider: PopupProvider, handoff_id: str, poll_key: str) -> Optional[Dict[str, Any]]:
    """None while the user has not finished; then the result or ``{"error": ...}``, once, and only
    for the holder of the poll key."""
    h = handoff(provider, handoff_id)
    if h is None or not secrets.compare_digest(h["poll_key"], poll_key or ""):
        return {"error": "unknown or expired sign-in"}
    if not h["state"]:
        return None
    r = result(provider, h["state"], poll_key)
    if r is not None:
        handoffs.pop(handoff_id, None)
    return r


def providers() -> Dict[str, PopupProvider]:
    """Every popup sign-in provider, by name (configured or not)."""
    from sources.azure_auth import AZURE
    from sources.box_auth import BOX
    from sources.google_auth import GOOGLE
    from sources.microsoft_auth import MICROSOFT
    return {p.name: p for p in (MICROSOFT, BOX, GOOGLE, AZURE)}


def urlencoded(base: str, params: Dict[str, Any]) -> str:
    return base + "?" + urlencode({k: v for k, v in params.items() if v is not None})
