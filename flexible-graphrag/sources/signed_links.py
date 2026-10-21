"""Open links that work for the asker: short-lived signed URLs for S3 and Azure Blob results.

A private S3 object or Azure blob has no address a browser tab can open on its own: S3's console
page shows only the object's properties, and Azure has no viewer at all. When a question carries
the asker's own sign-in for that source, each such result's ``open_url`` becomes a URL signed
with *that* sign-in, so the storage service still applies the asker's own permissions when the
link is opened:

- **S3:** a presigned GET (SigV4 query signing, computed locally) with the asker's temporary
  session credentials.
- **Azure Blob:** a user-delegation SAS: one call per question to get a delegation key with the
  asker's Azure Storage token (cached while it lasts), then local signing.

Links last ``SIGNED_LINK_SECONDS`` (1 hour), and never longer than the sign-in itself. Text,
PDF and image files are served to open in the tab (text always as plain text, so a stored HTML
file is not run); others download.
"""

import logging
import mimetypes
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

SIGNED_LINK_SECONDS = 3600
_delegation_keys: Dict[Tuple[str, str], Tuple[float, Any]] = {}  # (account, token) -> (until, key)


def _view_headers(name: str) -> Tuple[Optional[str], Optional[str]]:
    """(content type, content disposition) to serve a file to open in the tab, or (None, None)
    to leave how it is served to the store (usually a download)."""
    kind = mimetypes.guess_type(name)[0] or ""
    if kind.startswith("text/") or kind in ("application/json", "application/xml"):
        return "text/plain; charset=utf-8", "inline"
    if kind == "application/pdf" or (kind.startswith("image/") and kind != "image/svg+xml"):
        return kind, "inline"
    return None, None


def s3_presigned_url(bucket: str, key: str, region: str, token: str) -> Optional[str]:
    """A presigned GET of s3://bucket/key with the S3 sign-in token's session (no AWS call)."""
    import boto3
    from botocore.config import Config
    from sources.s3_auth import unpack
    try:
        creds = unpack(token)
    except PermissionError:
        return None
    left = float(creds.get("expires_at") or 0) - time.time() if creds.get("expires_at") else SIGNED_LINK_SECONDS
    if left < 60:
        return None
    client = boto3.client("s3", region_name=region or "us-east-1", aws_access_key_id=creds["access_key_id"],
                          aws_secret_access_key=creds["secret_access_key"],
                          aws_session_token=creds.get("session_token") or None,
                          config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    params = {"Bucket": bucket, "Key": key}
    ctype, disposition = _view_headers(key)
    if ctype:
        params.update(ResponseContentType=ctype, ResponseContentDisposition=disposition)
    return client.generate_presigned_url("get_object", Params=params,
                                         ExpiresIn=int(min(SIGNED_LINK_SECONDS, left)))


async def _delegation_key(client, account_url: str, token: str):
    """The asker's user-delegation key for a storage account (Get User Delegation Key, as them)."""
    from xml.etree import ElementTree as ET
    from azure.storage.blob import UserDelegationKey
    from sources.azure_auth import storage_headers, token_claims
    now = time.time()
    hit = _delegation_keys.get((account_url, token))
    if hit and hit[0] - now > 300:
        return hit[1]
    until = min(now + SIGNED_LINK_SECONDS, float(token_claims(token).get("exp") or now + SIGNED_LINK_SECONDS))
    if until - now < 60:
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    start = datetime.fromtimestamp(now - 300, timezone.utc).strftime(fmt)  # allow for clock skew
    expiry = datetime.fromtimestamp(until, timezone.utc).strftime(fmt)
    body = (f'<?xml version="1.0" encoding="utf-8"?><KeyInfo><Start>{start}</Start>'
            f'<Expiry>{expiry}</Expiry></KeyInfo>')
    r = await client.post(f"{account_url}/?restype=service&comp=userdelegationkey", content=body,
                          headers={**storage_headers(token), "Content-Type": "application/xml"})
    if r.status_code != 200:
        logger.info(f"No Azure user delegation key for {account_url} ({r.status_code}): blob links stay unsigned")
        return None
    root = ET.fromstring(r.text)
    key = UserDelegationKey()
    for field, tag in (("signed_oid", "SignedOid"), ("signed_tid", "SignedTid"), ("signed_start", "SignedStart"),
                       ("signed_expiry", "SignedExpiry"), ("signed_service", "SignedService"),
                       ("signed_version", "SignedVersion"), ("value", "Value")):
        el = root.find(tag)
        setattr(key, field, el.text if el is not None else None)
    _delegation_keys[(account_url, token)] = (until, key)
    return key


def azure_sas_url(account_url: str, container: str, blob: str, key) -> str:
    from urllib.parse import quote
    from azure.storage.blob import BlobSasPermissions, generate_blob_sas
    account = account_url.split("//", 1)[-1].split(".", 1)[0]
    ctype, disposition = _view_headers(blob)
    expiry = datetime.fromisoformat(key.signed_expiry.replace("Z", "+00:00"))
    sas = generate_blob_sas(account, container, blob, user_delegation_key=key,
                            permission=BlobSasPermissions(read=True),
                            expiry=min(expiry, datetime.now(timezone.utc) + timedelta(seconds=SIGNED_LINK_SECONDS)),
                            content_type=ctype, content_disposition=disposition)
    return f"{account_url}/{quote(container, safe='')}/{quote(blob, safe='/')}?{sas}"


async def sign_open_links(refs: Iterable[Dict[str, Any]], s3_tokens: List[str], azure_tokens: List[str],
                          context_of: Callable[[str], Dict[str, str]]) -> None:
    """Point each S3 / Azure Blob document ref's ``open_url`` (refs as doc_refs.describe gives
    them, changed in place) at a URL signed with the asker's sign-in. ``context_of(doc_id)`` gives
    its datasource's {"region"} (S3) or {"account_url"} (Azure). Refs the asker has no sign-in
    for keep their link."""
    refs = [r for r in refs if r.get("doc_id") and r.get("source_type") in ("s3", "azure_blob")]
    if not refs:
        return
    azure_client = None
    try:
        for ref in refs:
            doc_id, ctx = ref["doc_id"], context_of(ref["doc_id"]) or {}
            try:
                if ref["source_type"] == "s3" and s3_tokens:
                    i = doc_id.find("s3://")
                    bucket, _, key = doc_id[i + 5:].partition("/") if i >= 0 else ("", "", "")
                    url = s3_presigned_url(bucket, key, ctx.get("region", ""), s3_tokens[0]) if key else None
                elif ref["source_type"] == "azure_blob" and azure_tokens and ctx.get("account_url"):
                    container, _, blob = (doc_id.split(":", 1)[1] if ":" in doc_id else "").partition("/")
                    if not blob:
                        continue
                    if azure_client is None:
                        import httpx
                        azure_client = httpx.AsyncClient(timeout=10.0)
                    key = await _delegation_key(azure_client, ctx["account_url"], azure_tokens[0])
                    url = azure_sas_url(ctx["account_url"], container, blob, key) if key else None
                else:
                    continue
            except Exception as e:
                logger.warning(f"Could not sign the open link for {doc_id}: {type(e).__name__}: {e}")
                continue
            if url:
                ref["open_url"] = url
    finally:
        if azure_client is not None:
            await azure_client.aclose()
