"""Amazon S3 sign-in for query-time permission checks.

AWS has no browser sign-in for plain IAM users that a third-party app can use, so users sign in
with their own IAM access key (as the AWS CLI does). The key is used once, here, to get
temporary session credentials from STS ``GetSessionToken`` (12 hours by default); only those go
back to the UI, packed into one opaque token, and the long-term secret is never stored. Each S3
result is then fetched as the user with a signed 1-byte ranged GET: readable when S3 serves it,
left out on AccessDenied / NoSuchKey.

Opt-in: S3_AUTH_ENABLED=true turns S3 sign-in, and with it S3 permission filtering, on.
Requests are signed with botocore (a dependency through boto3) and sent with httpx.
"""

import base64
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, Optional, Tuple
from urllib.parse import quote

S3_SERVER = "aws"  # one S3 sign-in: every S3 datasource belongs to it
STS_URL = "https://sts.amazonaws.com/"  # the global endpoint (signed for us-east-1)
_STS_NS = {"sts": "https://sts.amazonaws.com/doc/2011-06-15/"}
# S3 / STS error codes meaning the credential itself is bad (sign in again), not "no access"
REFUSED_CODES = {"InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken", "InvalidToken",
                 "TokenRefreshRequired", "InvalidClientTokenId", "AccessDeniedException"}


def enabled() -> bool:
    return (os.getenv("S3_AUTH_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")


def session_seconds() -> int:
    """How long a sign-in lasts: S3_AUTH_SESSION_SECONDS, 900 .. 129600 (STS's limits), default 12 h."""
    try:
        n = int(os.getenv("S3_AUTH_SESSION_SECONDS") or 43200)
    except ValueError:
        n = 43200
    return max(900, min(n, 129600))


def pack(creds: Dict[str, str]) -> str:
    """Session credentials -> the one opaque token the UIs keep (and send back as source_auth.s3.token)."""
    return base64.urlsafe_b64encode(json.dumps(creds, separators=(",", ":")).encode()).decode().rstrip("=")


def unpack(token: str) -> Dict[str, str]:
    """The token from pack() -> {access_key_id, secret_access_key, session_token, expires_at, user};
    PermissionError when it is malformed or expired."""
    try:
        raw = (token or "").strip()
        creds = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if not creds.get("access_key_id") or not creds.get("secret_access_key"):
            raise ValueError
    except Exception:
        raise PermissionError("not an Amazon S3 sign-in token")
    if float(creds.get("expires_at") or 0) and float(creds["expires_at"]) < time.time():
        raise PermissionError("the Amazon S3 sign-in has expired")
    return creds


def _signed(method: str, url: str, creds: Dict[str, str], service: str, region: str,
            headers: Optional[Dict[str, str]] = None, body: Optional[str] = None) -> Dict[str, str]:
    """The headers that sign one request with SigV4 as ``creds``."""
    from botocore.auth import S3SigV4Auth, SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials
    req = AWSRequest(method=method, url=url, headers=dict(headers or {}), data=body)
    auth = S3SigV4Auth if service == "s3" else SigV4Auth
    auth(Credentials(creds["access_key_id"], creds["secret_access_key"], creds.get("session_token")),
         service, region).add_auth(req)
    return dict(req.headers.items())


def _error_code(text: str) -> str:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ""
    for el in root.iter():
        if el.tag.split("}")[-1] == "Code" and el.text:
            return el.text.strip()
    return ""


async def _sts(client, action: str, creds: Dict[str, str], params: Optional[Dict[str, str]] = None) -> ET.Element:
    from urllib.parse import urlencode
    body = urlencode({"Action": action, "Version": "2011-06-15", **(params or {})})
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}
    r = await client.post(STS_URL, content=body,
                          headers=_signed("POST", STS_URL, creds, "sts", "us-east-1", headers, body))
    if r.status_code != 200:
        code = _error_code(r.text)
        if r.status_code in (401, 403) or code in REFUSED_CODES:
            raise PermissionError(f"AWS refused the access key ({code or r.status_code})")
        raise RuntimeError(f"AWS STS {action} failed ({code or r.status_code})")
    return ET.fromstring(r.text)


def _text(root: ET.Element, path: str) -> str:
    el = root.find(path, _STS_NS)
    return (el.text or "").strip() if el is not None else ""


def _user_of(arn: str) -> str:
    """arn:aws:iam::123456789012:user/alice -> alice (a role session: its session name)."""
    return arn.rsplit("/", 1)[-1] if "/" in arn else arn


async def s3_login(access_key_id: str, secret_access_key: str) -> Dict[str, object]:
    """IAM access key -> ``{token, user_id, expires_at}``: temporary credentials from STS
    GetSessionToken, packed. PermissionError when AWS refuses the key."""
    import httpx
    long_term = {"access_key_id": access_key_id.strip(), "secret_access_key": secret_access_key.strip()}
    if not long_term["access_key_id"] or not long_term["secret_access_key"]:
        raise PermissionError("enter an access key ID and secret access key")
    if not re.fullmatch(r"AKIA[A-Z0-9]{16}", long_term["access_key_id"]):
        # a long-term IAM user key; a 40-character value here is usually the secret in the wrong field
        raise PermissionError("that is not an IAM user's access key ID (20 characters starting with AKIA)"
                              + (" -- it looks like a secret access key" if len(long_term["access_key_id"]) == 40 else ""))
    async with httpx.AsyncClient(timeout=20.0) as client:
        root = await _sts(client, "GetSessionToken", long_term, {"DurationSeconds": str(session_seconds())})
        c = "sts:GetSessionTokenResult/sts:Credentials/"
        creds = {"access_key_id": _text(root, c + "sts:AccessKeyId"),
                 "secret_access_key": _text(root, c + "sts:SecretAccessKey"),
                 "session_token": _text(root, c + "sts:SessionToken")}
        exp = _text(root, c + "sts:Expiration")
        who = await _sts(client, "GetCallerIdentity", creds)
    from datetime import datetime
    expires_at = int(datetime.fromisoformat(exp.replace("Z", "+00:00")).timestamp()) if exp else 0
    user = _user_of(_text(who, "sts:GetCallerIdentityResult/sts:Arn"))
    creds.update(expires_at=expires_at, user=user)
    return {"token": pack(creds), "user_id": user, "expires_at": expires_at}


async def s3_token_user(token: str) -> str:
    """Whose sign-in token this is, after asking AWS that it is still valid (GetCallerIdentity);
    PermissionError otherwise."""
    import httpx
    creds = unpack(token)
    async with httpx.AsyncClient(timeout=20.0) as client:
        who = await _sts(client, "GetCallerIdentity", creds)
    return _user_of(_text(who, "sts:GetCallerIdentityResult/sts:Arn"))


def object_request(item: str, creds: Dict[str, str], region: str) -> Tuple[str, Dict[str, str]]:
    """``item`` "<bucket>/<key>" -> (url, signed headers) of a 1-byte ranged GET of that object as
    the user (HEAD would hide why a 403 happened: its error has no body)."""
    bucket, _, key = item.partition("/")
    region = region or "us-east-1"
    host = "s3.amazonaws.com" if region == "us-east-1" else f"s3.{region}.amazonaws.com"
    # virtual-hosted style, except for bucket names with dots (their TLS name would not match)
    url = (f"https://{host}/{bucket}/{quote(key, safe='/~')}" if "." in bucket
           else f"https://{bucket}.{host}/{quote(key, safe='/~')}")
    return url, _signed("GET", url, creds, "s3", region, {"Range": "bytes=0-0"})
