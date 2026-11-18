"""S3 browse: the "folders" and objects of one bucket, with the keys the ingest uses (sources/s3.py:
form keys, else S3_ACCESS_KEY / S3_SECRET_KEY, else boto3's own chain; region likewise).

S3 has no folders: a folder is a common prefix under ``Delimiter="/"``. The ingest takes the bucket
plus one ``prefix``, a folder ("docs/reports/") or one object's exact key, so ``id`` and ``path``
are both that prefix / key. Pages use ``ContinuationToken``.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

from browse import BrowseError, BrowseItem, BrowseResult

LABEL = "S3"
_MAX_KEYS = 1000  # S3's own maximum per page


def _clean(value: Any) -> str:
    v = str(value or "").strip()
    return "" if v in ("None", "null") else v


def _client_and_bucket(config: Dict[str, Any]):
    import boto3

    bucket = _clean(config.get("bucket_name") or config.get("bucket") or os.getenv("S3_BUCKET_NAME"))
    if not bucket:
        raise BrowseError("S3: fill in the bucket name first")
    key = _clean(config.get("access_key") or config.get("aws_access_key_id") or os.getenv("S3_ACCESS_KEY"))
    secret = _clean(config.get("secret_key") or config.get("aws_secret_access_key") or os.getenv("S3_SECRET_KEY"))
    kwargs = {"region_name": _clean(config.get("region_name") or os.getenv("S3_REGION_NAME")) or "us-east-1"}
    if key and secret:
        kwargs.update(aws_access_key_id=key, aws_secret_access_key=secret)
    return boto3.client("s3", **kwargs), bucket


def _error(e: Exception, bucket: str) -> BrowseError:
    from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

    if isinstance(e, NoCredentialsError):
        return BrowseError("S3: fill in the access key and secret key first", status_code=401)
    if isinstance(e, ClientError):
        err = e.response.get("Error", {})
        code, message = err.get("Code", ""), err.get("Message") or str(e)
        if code in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken", "InvalidToken"):
            return BrowseError(f"S3 sign-in failed: {message}", status_code=401)
        if code == "NoSuchBucket":
            return BrowseError(f"S3: no bucket named '{bucket}'", status_code=404)
        if code in ("AccessDenied", "AllAccessDisabled"):
            return BrowseError(f"S3: no permission to list bucket '{bucket}' ({message})", status_code=403)
        if code in ("PermanentRedirect", "AuthorizationHeaderMalformed", "IllegalLocationConstraintException"):
            return BrowseError(f"S3: bucket '{bucket}' is in another region: fix the AWS Region ({message})",
                               status_code=400)
        return BrowseError(f"S3: {code or 'error'}: {message}", status_code=502)
    if isinstance(e, EndpointConnectionError):
        return BrowseError(f"S3: could not reach AWS ({e})", status_code=502)
    return BrowseError(f"S3: {str(e).splitlines()[0] if str(e) else type(e).__name__}", status_code=502)


def _name(prefix_or_key: str) -> str:
    return prefix_or_key.rstrip("/").rsplit("/", 1)[-1]


async def browse(config: Dict[str, Any], parent: Optional[Dict[str, Any]], page_token: Optional[str],
                 page_size: int) -> BrowseResult:
    client, bucket = _client_and_bucket(config)
    prefix = (parent or {}).get("id") or ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"  # a folder is opened by its prefix

    def page():
        kwargs = {"Bucket": bucket, "Prefix": prefix, "Delimiter": "/", "MaxKeys": min(page_size, _MAX_KEYS)}
        if page_token:
            kwargs["ContinuationToken"] = page_token
        return client.list_objects_v2(**kwargs)

    try:
        result = await asyncio.to_thread(page)
    except Exception as e:
        raise _error(e, bucket)
    items = [BrowseItem(id=p["Prefix"], name=_name(p["Prefix"]), path=p["Prefix"], kind="folder")
             for p in result.get("CommonPrefixes", [])]
    for obj in result.get("Contents", []):
        key = obj["Key"]
        if key == prefix or key.endswith("/"):
            continue  # the "folder" placeholder objects consoles create
        modified = obj.get("LastModified")
        items.append(BrowseItem(id=key, name=_name(key), path=key, kind="file", size=obj.get("Size"),
                                modified=modified.isoformat() if hasattr(modified, "isoformat") else modified))
    items.sort(key=lambda i: (i.kind != "folder", i.name.lower()))
    return BrowseResult(items=items, next_page_token=result.get("NextContinuationToken") if result.get("IsTruncated") else None)
