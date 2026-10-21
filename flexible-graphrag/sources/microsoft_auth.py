"""Microsoft 365 sign-in (SharePoint + OneDrive) for query-time permission checks.

Users sign in at Microsoft in a popup (authorization code flow, so MFA and conditional access
work); the shared popup flow is in sources/oauth_popup.py. Microsoft returns the code as a form
POST (``response_mode=form_post``), so it never appears in a logged URL, and a ``login_hint`` (the
account used last time) lets it pick that account without the picker.

Configured only when MICROSOFT_AUTH_CLIENT_ID is set (with _CLIENT_SECRET and _TENANT_ID): it is
also what turns SharePoint / OneDrive permission filtering on. The Entra app needs a **Web**
redirect URI ``<backend>/api/auth/microsoft/callback`` and delegated Graph permissions
Files.Read.All + Sites.Read.All (+ User.Read, offline_access) with admin consent. It can be the same
app the SharePoint / OneDrive data sources ingest with (their client credentials).
"""

import os
from typing import Any, Dict, Optional

from sources.oauth_popup import PopupProvider, urlencoded

SCOPES = "openid profile offline_access User.Read Files.Read.All Sites.Read.All"


def config() -> Optional[Dict[str, str]]:
    """``{client_id, client_secret, tenant_id}``, or None when Microsoft sign-in is not configured."""
    client_id = (os.getenv("MICROSOFT_AUTH_CLIENT_ID") or "").strip()
    if not client_id:
        return None
    return {
        "client_id": client_id,
        "client_secret": (os.getenv("MICROSOFT_AUTH_CLIENT_SECRET") or "").strip(),
        "tenant_id": (os.getenv("MICROSOFT_AUTH_TENANT_ID") or "organizations").strip(),
    }


def _authority(cfg: Dict[str, str]) -> str:
    return f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0"


def tenant_of(access_token: str) -> str:
    """The tenant id (``tid``) inside a Graph access token (read without verifying: Graph does that)."""
    import base64
    import json
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("tid", "")
    except Exception:
        return ""


async def token_user(access_token: str) -> str:
    """The user a Graph token belongs to; PermissionError when it is expired / invalid."""
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get("https://graph.microsoft.com/v1.0/me",
                             params={"$select": "userPrincipalName,displayName"},
                             headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code == 401:
        raise PermissionError("the Microsoft 365 sign-in has expired")
    r.raise_for_status()
    me = r.json()
    return me.get("userPrincipalName") or me.get("displayName") or ""


class MicrosoftProvider(PopupProvider):
    name = "microsoft"
    label = "Microsoft 365"
    form_post = True

    def config(self) -> Optional[Dict[str, str]]:
        return config()

    def authorize_url(self, cfg, redirect_uri, state, login_hint):
        return urlencoded(_authority(cfg) + "/authorize", {
            "client_id": cfg["client_id"], "response_type": "code", "redirect_uri": redirect_uri,
            # form_post: the code comes back in a POST body, not in a URL that access logs record
            "response_mode": "form_post", "scope": SCOPES, "state": state,
            "login_hint": login_hint or None, "prompt": None if login_hint else "select_account",
        })

    async def exchange(self, cfg, code, redirect_uri) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(_authority(cfg) + "/token", data={
                "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "scope": SCOPES,
            })
        if r.status_code != 200:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            raise RuntimeError(body.get("error_description") or f"token exchange failed ({r.status_code})")
        return r.json()

    async def user(self, access_token: str) -> str:
        return await token_user(access_token)

    def server(self, cfg, access_token: str) -> str:
        return tenant_of(access_token) or cfg["tenant_id"]


MICROSOFT = MicrosoftProvider()
