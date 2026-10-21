"""Azure Storage sign-in (Azure Blob) for query-time permission checks.

A separate sign-in from Microsoft 365 (sources/microsoft_auth.py): the storage account usually
lives in another directory -- often the "Default Directory" of the personal Microsoft account
that owns the Azure subscription. Users sign in at Microsoft in a popup (the shared flow is in
sources/oauth_popup.py; ``form_post`` keeps the code out of logged URLs) for a delegated Azure
Storage token. Each Azure Blob result is then fetched as the user with *Get Blob Metadata*
(headers only, no content): 200 readable, 403 / 404 left out.

Configured only when AZURE_AUTH_CLIENT_ID is set (with _CLIENT_SECRET and _TENANT_ID): it is also
what turns Azure Blob permission filtering on. The Entra app (in the storage account's directory)
needs a **Web** redirect URI ``<backend>/api/auth/azure/callback`` and the delegated permission
Azure Storage ``user_impersonation`` with admin consent; each user needs a data role on the
storage account or container, e.g. **Storage Blob Data Reader** (Owner alone does not grant blob
data access with a sign-in).
"""

import os
import time
from typing import Any, Dict, Optional

from sources.oauth_popup import PopupProvider, urlencoded

AZURE_SERVER = "azure"  # one Azure Storage sign-in: every Azure Blob datasource belongs to it
SCOPES = "openid profile offline_access https://storage.azure.com/user_impersonation"
STORAGE_API_VERSION = "2023-11-03"  # x-ms-version: Bearer tokens need 2017-11-09 or later


def config() -> Optional[Dict[str, str]]:
    """``{client_id, client_secret, tenant_id}``, or None when Azure Storage sign-in is not configured."""
    client_id = (os.getenv("AZURE_AUTH_CLIENT_ID") or "").strip()
    if not client_id:
        return None
    return {
        "client_id": client_id,
        "client_secret": (os.getenv("AZURE_AUTH_CLIENT_SECRET") or "").strip(),
        "tenant_id": (os.getenv("AZURE_AUTH_TENANT_ID") or "organizations").strip(),
    }


def token_claims(access_token: str) -> Dict[str, Any]:
    """The claims inside an access token (read without verifying: Azure Storage does that)."""
    import base64
    import json
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def storage_headers(access_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "x-ms-version": STORAGE_API_VERSION}


class AzureProvider(PopupProvider):
    name = "azure"
    label = "Azure Storage"
    form_post = True

    def config(self) -> Optional[Dict[str, str]]:
        return config()

    def _authority(self, cfg: Dict[str, str]) -> str:
        return f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0"

    def authorize_url(self, cfg, redirect_uri, state, login_hint):
        return urlencoded(self._authority(cfg) + "/authorize", {
            "client_id": cfg["client_id"], "response_type": "code", "redirect_uri": redirect_uri,
            # form_post: the code comes back in a POST body, not in a URL that access logs record
            "response_mode": "form_post", "scope": SCOPES, "state": state,
            "login_hint": login_hint or None, "prompt": None if login_hint else "select_account",
        })

    async def exchange(self, cfg, code, redirect_uri) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(self._authority(cfg) + "/token", data={
                "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "scope": SCOPES,
            })
        if r.status_code != 200:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            raise RuntimeError(body.get("error_description") or f"token exchange failed ({r.status_code})")
        return r.json()

    async def user(self, access_token: str) -> str:
        """Who the token names. A Storage token cannot call Graph's /me, so its own claims are read;
        PermissionError once it has expired."""
        claims = token_claims(access_token)
        if not claims or float(claims.get("exp", 0)) < time.time():
            raise PermissionError("the Azure Storage sign-in has expired")
        name = (claims.get("upn") or claims.get("email") or claims.get("preferred_username")
                or claims.get("unique_name") or claims.get("name") or "")
        return name.split("#", 1)[-1]  # a guest's unique_name is "live.com#user@example.com"

    def server(self, cfg, access_token: str) -> str:
        return AZURE_SERVER


AZURE = AzureProvider()
