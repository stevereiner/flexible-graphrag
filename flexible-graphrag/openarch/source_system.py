"""Which source system a document comes from, and where it goes in the OpenArch tree.

A document is stored once per source system object: ``/fg-sources/<source type>/<system id>/<source path>``,
identified by ``cin_sourceId`` (the source system) and ``cin_id`` (the object in it). Two data
sources covering the same folder share the same OpenArch documents.

The backend names the source system of an ingest job (``set_current_source_system``) from the
job's data source type and connection config; the store reads it while writing that job's
documents (a context variable, so concurrent jobs don't mix).
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import re
import socket
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_current_source_system: contextvars.ContextVar[Optional[Tuple[str, str]]] = contextvars.ContextVar(
    "openarch_source_system", default=None)

# doc_id = "<config_id>:<identity>", config_id being a uuid (main._resolve_config_id)
_CONFIG_ID_PREFIX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}:")

_UNSAFE_NAME = re.compile(r"[\\/\x00-\x1f]")


def _conf(kwargs: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = kwargs.get(key) or {}
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return value if isinstance(value, dict) else {}


def _host_port(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = (parsed.hostname or "").lower()
    return f"{host}-{parsed.port}" if parsed.port else host


def named_source_id(url: str) -> Optional[str]:
    """The name OPENARCH_SOURCE_IDS gives the repository server at ``url``, matched by host and
    port. OPENARCH_SOURCE_IDS is a JSON object of name -> URL, or name -> list of URLs for a
    server reached under several addresses, e.g.
    ``{"nuxeo-repo-1": "http://localhost:8081/nuxeo", "nuxeo-repo-2": ["http://nx2:8080/nuxeo"]}``."""
    raw = os.getenv("OPENARCH_SOURCE_IDS")
    if not raw or not url:
        return None
    try:
        names = json.loads(raw)
    except ValueError:
        logger.warning("OPENARCH_SOURCE_IDS is not valid JSON: ignored")
        return None
    wanted = _server(url)
    for name, urls in names.items():
        for candidate in ([urls] if isinstance(urls, str) else urls or []):
            if _server(candidate) == wanted:
                return str(name)
    return None


def _server(url: str) -> Tuple[str, int]:
    """Host and port of a URL, the scheme's default port filled in."""
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return (parsed.hostname or "").lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


_alfresco_repository_ids: Dict[str, Optional[str]] = {}


def alfresco_repository_id(config: Dict[str, Any]) -> Optional[str]:
    """The Alfresco repository's id (Discovery API), the same however the server is reached;
    cached per server URL. None when it can't be read."""
    import httpx

    url = (config.get("url") or os.getenv("ALFRESCO_URL", "")).rstrip("/")
    if not url:
        return None
    if url not in _alfresco_repository_ids:
        base = url[: -len("/alfresco")] if url.endswith("/alfresco") else url
        auth, params, headers = None, None, None
        method = (config.get("auth_method") or "basic").lower()
        token = (config.get("oauth2") or {}).get("access_token") if isinstance(config.get("oauth2"), dict) else None
        if method == "ticket" and config.get("ticket"):
            params = {"alf_ticket": config["ticket"]}
        elif method == "oauth2" and token:
            headers = {"Authorization": f"Bearer {token}"}
        else:
            auth = (config.get("username") or os.getenv("ALFRESCO_USERNAME", "admin"),
                    config.get("password") or os.getenv("ALFRESCO_PASSWORD", "admin"))
        try:
            r = httpx.get(f"{base}/alfresco/api/discovery", auth=auth, params=params, headers=headers, timeout=10)
            r.raise_for_status()
            _alfresco_repository_ids[url] = r.json()["entry"]["repository"]["id"]
        except Exception as e:
            logger.warning("Alfresco repository id unavailable from %s (%s): using its host and port", url, e)
            _alfresco_repository_ids[url] = None
    return _alfresco_repository_ids[url]


def source_system_for(data_source: Optional[str], kwargs: Dict[str, Any]) -> Tuple[str, str]:
    """``(source type, source system)`` of an ingest job: the repository, bucket, site...
    Repository servers: the ``source_id`` of the job's source config when given, else the
    server's name in OPENARCH_SOURCE_IDS, else Alfresco's repository id (as content-lake-app),
    else the server's host and port (Nuxeo has no repository id). Several Nuxeo or Alfresco
    servers stay apart either way.
    For example ``("alfresco", "68caf25c-...")``, ``("nuxeo", "localhost-8081")`` or
    ``("s3", "my-bucket")``."""
    ds = (data_source or "filesystem").lower()
    if ds == "upload":
        ds = "filesystem"
    if ds in ("alfresco", "nuxeo", "cmis"):
        config = _conf(kwargs, f"{ds}_config")
        if config.get("source_id"):
            return ds, str(config["source_id"])
        url = config.get("url") or os.getenv(f"{ds.upper()}_URL", "")
        named = named_source_id(url)
        if named:
            return ds, named
        if ds == "alfresco":
            repository_id = alfresco_repository_id(config)
            if repository_id:
                return ds, repository_id
        return ds, _host_port(url) if url else "default"
    if ds in ("s3", "gcs"):
        return ds, _conf(kwargs, f"{ds}_config").get("bucket_name") or "default"
    if ds == "azure_blob":
        c = _conf(kwargs, "azure_blob_config")
        account = c.get("account_name") or (_host_port(c["account_url"]) if c.get("account_url") else "")
        return ds, "-".join(p for p in (account, c.get("container_name")) if p) or "default"
    if ds == "sharepoint":
        c = _conf(kwargs, "sharepoint_config")
        # site_name first: an auto sync's re-ingest passes the resolved site_id as well, and naming
        # the system by it put a second copy of each document under another folder
        return ds, c.get("site_name") or c.get("site_id") or "default"
    if ds == "onedrive":
        return ds, _conf(kwargs, "onedrive_config").get("user_principal_name") or "default"
    if ds == "web":
        url = _conf(kwargs, "web_config").get("url", "")
        return ds, _host_port(url) if url else "default"
    if ds == "wikipedia":
        return ds, _conf(kwargs, "wikipedia_config").get("language") or "en"
    if ds == "filesystem":
        return ds, socket.gethostname().lower()
    return ds, "default"  # youtube, box, google_drive: one account-wide namespace


def set_current_source_system(data_source: Optional[str], kwargs: Dict[str, Any]) -> contextvars.Token:
    return _current_source_system.set(source_system_for(data_source, kwargs))


def use_source_system(source: Tuple[str, str]) -> contextvars.Token:
    """Set the current ``(source type, source system)`` as already named (a recorded job's)."""
    return _current_source_system.set((str(source[0]), str(source[1])))


def current_source_system() -> Optional[Tuple[str, str]]:
    return _current_source_system.get()


def source_folder(source_type: str, system: str) -> str:
    """Folders of a source system under the root: ``<source type>/<system id>``, e.g.
    ``alfresco/68caf25c-...`` or ``nuxeo/localhost-8081``."""
    return f"{safe_name(source_type)}/{safe_name(system)}"


def cin_source_id(source_type: str, system: str) -> str:
    """``cin_sourceId`` of a source system, in content-lake's ``<type>:<id>`` form."""
    return f"{source_type}:{system}"


def safe_name(name: str) -> str:
    """A usable ``sys_name``: no slashes or control characters, not empty."""
    name = _UNSAFE_NAME.sub("_", str(name)).strip()
    return name if name not in ("", ".", "..") else "_"


def document_identity(doc_id: str, metadata: Dict[str, Any]) -> str:
    """The object's identity in its source system: the part of Flexible GraphRAG's stable
    ``config_id:identity`` doc id after the data source's config id (``alfresco://<node id>``,
    ``s3://bucket/key``, a normalized file path...), or a metadata-derived fallback."""
    if doc_id and _CONFIG_ID_PREFIX.match(doc_id):
        return doc_id[37:]
    if doc_id and metadata.get("conversion_method") == "direct_text":
        # ingested text has no object in a source: each ingest its own document, like the other
        # stores keep it (its name, e.g. MCP's "mcp-input", is shared by many)
        return f"text://{doc_id}"
    for key in ("stable_file_path", "s3_uri", "file_path", "url", "source_url", "file_name"):
        if metadata.get(key):
            value = str(metadata[key])
            if key == "file_path" and str(metadata.get("source") or "filesystem") == "filesystem":
                # Same form as the data sources' stable ids (lowercase on Windows)
                from incremental_updates.path_utils import normalize_filesystem_path
                value = normalize_filesystem_path(value)
            return value
    return doc_id


def is_data_source_doc_id(doc_id: str) -> bool:
    """Whether a doc id is a data source's stable ``<config_id>:<identity>`` id (else an ad-hoc
    ingest's random id)."""
    return bool(doc_id and _CONFIG_ID_PREFIX.match(doc_id))


def document_path(source_type: str, identity: str, metadata: Dict[str, Any]) -> list:
    """Path segments of the document below its source system folder: its human path in the
    source (repository path, file path, bucket key, URL path), else its name."""
    raw = None
    if source_type == "youtube" and metadata.get("video_id"):
        # a video's transcript comes in segments: <video id>/<segment start>
        start = metadata.get("start_timestamp")
        return [safe_name(metadata["video_id"])] + ([safe_name(str(start).replace(":", "-"))] if start else [])
    if source_type in ("alfresco", "nuxeo", "cmis", "onedrive", "sharepoint"):
        raw = metadata.get("human_file_path") or metadata.get("file_path")
    elif source_type == "s3":
        raw = metadata.get("s3_key") or metadata.get("file_path")
    elif source_type in ("gcs", "azure_blob", "box"):
        raw = metadata.get("file_path") or metadata.get("name")
        # "<bucket or container>/<key>": the system folder already names the bucket / container
        holder = (metadata.get("bucket_name") or metadata.get("bucket") or metadata.get("container_name")
                  or metadata.get("container"))
        if raw and holder and str(raw).replace("\\", "/").startswith(f"{holder}/"):
            raw = str(raw).replace("\\", "/")[len(holder) + 1:]
    elif source_type in ("web", "youtube"):
        url = metadata.get("url") or metadata.get("source_url") or identity
        parsed = urlparse(url if "://" in str(url) else "")
        raw = parsed.path or None
    elif source_type == "filesystem":
        raw = metadata.get("file_path") or identity
        drive, rest = os.path.splitdrive(str(raw))
        raw = (drive.rstrip(":").lower() + "/" if drive else "") + rest.replace("\\", "/")
    segments = [safe_name(s) for s in str(raw or "").replace("\\", "/").split("/") if s.strip()]
    file_name = metadata.get("file_name")
    flattened = safe_name("-".join(segments)) if segments else None  # e.g. Azure's "kg-matrix-a.txt" for kg-matrix/a.txt
    # Some sources give the parent folder's path. Not Nuxeo or CMIS: their path is the document's own, and its
    # name can differ from its file's (a renamed Nuxeo document keeps its file's original name), so appending
    # that would put the document in a folder named after itself
    if (segments and file_name and source_type not in ("web", "youtube", "nuxeo", "cmis")
            and segments[-1] != safe_name(file_name) and safe_name(file_name) != flattened):
        segments.append(safe_name(file_name))
    if not segments:
        name = metadata.get("file_name") or metadata.get("title")
        if not name:
            name = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
        segments = [safe_name(name)]
    return segments
