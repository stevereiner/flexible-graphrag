"""Box sign-in for query-time permission checks.

Users sign in at Box in a popup (OAuth 2.0 authorization code; the shared popup flow is in
sources/oauth_popup.py). The delegated token then fetches each Box search result as that user
(``GET /2.0/files/{id}``): 200 readable, 403 / 404 left out.

Configured only when BOX_AUTH_CLIENT_ID is set (with BOX_AUTH_CLIENT_SECRET): it is also what
turns Box permission filtering on. It needs its own Box Platform App of type **User**
(OAuth 2.0) -- the data source's Server / Client Credentials Grant app cannot sign users in --
with the redirect URI ``<backend>/api/auth/box/callback`` and the scope "Read all files and
folders stored in Box". Box has no ``form_post``: its code arrives in the callback's query
string, which main.py's access-log filter redacts.
"""

import os
from typing import Any, Dict, Optional

from sources.oauth_popup import PopupProvider, urlencoded

BOX_SERVER = "box.com"  # one Box: every Box datasource and sign-in belongs to it


def config() -> Optional[Dict[str, str]]:
    """``{client_id, client_secret}``, or None when Box sign-in is not configured."""
    client_id = (os.getenv("BOX_AUTH_CLIENT_ID") or "").strip()
    if not client_id:
        return None
    return {"client_id": client_id, "client_secret": (os.getenv("BOX_AUTH_CLIENT_SECRET") or "").strip()}


class BoxProvider(PopupProvider):
    name = "box"
    label = "Box"

    def config(self) -> Optional[Dict[str, str]]:
        return config()

    def authorize_url(self, cfg, redirect_uri, state, login_hint):
        # Box has no login hint / account picker parameters; its own session decides the account
        return urlencoded("https://account.box.com/api/oauth2/authorize", {
            "client_id": cfg["client_id"], "response_type": "code", "redirect_uri": redirect_uri, "state": state,
        })

    async def exchange(self, cfg, code, redirect_uri) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post("https://api.box.com/oauth2/token", data={
                "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            })
        if r.status_code != 200:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            raise RuntimeError(body.get("error_description") or f"token exchange failed ({r.status_code})")
        return r.json()

    async def user(self, access_token: str) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get("https://api.box.com/2.0/users/me", params={"fields": "login,name"},
                                 headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code == 401:
            raise PermissionError("the Box sign-in has expired")
        r.raise_for_status()
        me = r.json()
        return me.get("login") or me.get("name") or ""

    def server(self, cfg, access_token: str) -> str:
        return BOX_SERVER


BOX = BoxProvider()
