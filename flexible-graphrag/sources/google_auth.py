"""Google sign-in (Google Drive + Google Cloud Storage) for query-time permission checks.

Users sign in at Google in a popup (OAuth 2.0 authorization code; the shared popup flow is in
sources/oauth_popup.py). Google returns the code as a form POST (``response_mode=form_post``), so
it never appears in a logged URL, and a ``login_hint`` (the account used last time) lets it pick
that account without the picker. One token covers both sources: each Drive result is fetched as
the user with ``files.get``, each GCS result with ``objects.get`` (200 readable, 403 / 404 left out).

Configured only when GOOGLE_AUTH_CLIENT_ID is set (with GOOGLE_AUTH_CLIENT_SECRET): it is also
what turns Google Drive / GCS permission filtering on. It needs an OAuth client of type **Web
application** with the redirect URI ``<backend>/api/auth/google/callback``, and the consent
screen's scopes drive.readonly + devstorage.read_only (+ openid / email / profile). In Testing
mode only the consent screen's test users can sign in.
"""

import os
from typing import Any, Dict, Optional

from sources.oauth_popup import PopupProvider, urlencoded

GOOGLE_SERVER = "google.com"  # one Google: every Drive / GCS datasource and sign-in belongs to it
SCOPES = ("openid email profile https://www.googleapis.com/auth/drive.readonly "
          "https://www.googleapis.com/auth/devstorage.read_only")


def config() -> Optional[Dict[str, str]]:
    """``{client_id, client_secret}``, or None when Google sign-in is not configured."""
    client_id = (os.getenv("GOOGLE_AUTH_CLIENT_ID") or "").strip()
    if not client_id:
        return None
    return {"client_id": client_id, "client_secret": (os.getenv("GOOGLE_AUTH_CLIENT_SECRET") or "").strip()}


class GoogleProvider(PopupProvider):
    name = "google"
    label = "Google"
    form_post = True

    def config(self) -> Optional[Dict[str, str]]:
        return config()

    def authorize_url(self, cfg, redirect_uri, state, login_hint):
        return urlencoded("https://accounts.google.com/o/oauth2/v2/auth", {
            "client_id": cfg["client_id"], "response_type": "code", "redirect_uri": redirect_uri,
            # form_post: the code comes back in a POST body, not in a URL that access logs record
            "response_mode": "form_post", "scope": SCOPES, "state": state, "access_type": "online",
            "include_granted_scopes": "true",
            "login_hint": login_hint or None, "prompt": None if login_hint else "select_account",
        })

    async def exchange(self, cfg, code, redirect_uri) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            })
        if r.status_code != 200:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            raise RuntimeError(body.get("error_description") or body.get("error") or f"token exchange failed ({r.status_code})")
        return r.json()

    async def user(self, access_token: str) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get("https://openidconnect.googleapis.com/v1/userinfo",
                                 headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code == 401:
            raise PermissionError("the Google sign-in has expired")
        r.raise_for_status()
        me = r.json()
        return me.get("email") or me.get("name") or ""

    def server(self, cfg, access_token: str) -> str:
        return GOOGLE_SERVER


GOOGLE = GoogleProvider()
