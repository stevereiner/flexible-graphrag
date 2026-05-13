"""
Integration tests for data source ingestion via REST API.

Tests each data source type by posting to POST /api/ingest with the appropriate
*_config blob and verifying the ingestion completes and content is searchable.

Sources covered
---------------
Web sources (no credentials needed):
  - web           : ingest a public URL
  - wikipedia     : ingest a Wikipedia article by query
  - youtube       : ingest a YouTube video transcript

Local sources (require running services):
  - alfresco      : ALFRESCO_* env vars, folder /Shared/GraphRAG
                    also tested with enable_sync=True (incremental)
  - cmis          : CMIS_* env vars, same folder

Cloud sources (require credentials in env / .env):
  - s3            : S3_* env vars (stevereiner-bucket-1, us-east-2)
  - box           : BOX_CONFIG env var

Skipped if credentials not present:
  - azure_blob    : AZURE_BLOB_CONFIG env var
  - onedrive      : ONEDRIVE_CONFIG env var
  - sharepoint    : SHAREPOINT_CONFIG env var
  - google_drive  : GOOGLE_DRIVE_CONFIG env var
  - gcs           : GCS_CONFIG env var

Each test:
  1. Posts to /api/ingest with the source config
  2. Waits for completion (or skip/fail on missing creds)
  3. Runs a search to confirm content was indexed

Run:
    pytest tests/integration/test_datasources.py -m datasource -s

Via matrix runner:
    python run_matrix.py --test-path tests/integration/test_datasources.py --vector qdrant --pg neo4j
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import pytest

from tests.integration.api_client import APIClient, IngestResult, StatusResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_WAIT = 300   # seconds for slow cloud sources
FAST_WAIT = 120  # seconds for web/wikipedia/youtube


def _env(key: str) -> str | None:
    """Return env var value or None if missing/empty."""
    v = os.getenv(key, "").strip()
    return v if v else None


def _env_json(key: str) -> dict | None:
    """Parse a JSON env var, return None if missing or invalid."""
    raw = _env(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Could not parse %s as JSON", key)
        return None


def _wait_and_assert(client: APIClient, result: IngestResult, source: str, max_wait: int = MAX_WAIT) -> StatusResult:
    """Wait for ingestion to complete; assert success."""
    logger.info("[%s] ingest started: id=%s", source, result.processing_id)
    status = client.wait_for_completion(result.processing_id, max_wait=max_wait)
    logger.info("[%s] ingest finished: status=%s  msg=%s", source, status.status, status.message[:120])
    assert status.status == "completed", f"[{source}] Ingest failed: {status.message}"
    return status


def _search_and_log(client: APIClient, query: str, source: str, expected_terms: list[str] | None = None) -> None:
    """Run a search and optionally assert at least one expected term is present."""
    sr = client.search(query, top_k=5)
    logger.info("[%s] search '%s' -> %d results", source, query, sr.total)
    for r in sr.results[:3]:
        snippet = str(r.get("content") or r.get("text") or "")[:100]
        logger.info("  score=%.3f  src=%s  text=%s", r.get("score", 0), r.get("source", "?"), snippet)
    if expected_terms:
        combined = " ".join(
            str(r.get("content") or r.get("text") or "") for r in sr.results
        ).lower()
        matched = [t for t in expected_terms if t.lower() in combined]
        logger.info("[%s] terms matched: %s / %s", source, matched, expected_terms)
        assert matched, (
            f"[{source}] Search returned {sr.total} results but none contained "
            f"expected terms {expected_terms}"
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> APIClient:
    c = APIClient()
    assert c.wait_until_healthy(max_wait=30), "Backend not healthy"
    return c


# ---------------------------------------------------------------------------
# Web sources (no credentials needed)
# ---------------------------------------------------------------------------

@pytest.mark.datasource
@pytest.mark.integration
def test_web_ingest(client: APIClient) -> None:
    """Ingest a public web page and verify content is searchable."""
    url = "https://en.wikipedia.org/wiki/Content_management_system"
    payload: dict[str, Any] = {
        "data_source": "web",
        "web_config": {"url": url},
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "web", max_wait=FAST_WAIT)
    _search_and_log(client, "content management system", "web",
                    expected_terms=["content", "management"])


@pytest.mark.datasource
@pytest.mark.integration
def test_wikipedia_ingest(client: APIClient) -> None:
    """Ingest a Wikipedia article by search query."""
    payload: dict[str, Any] = {
        "data_source": "wikipedia",
        "wikipedia_config": {
            "query": "Content Management Interoperability Services",
            "language": "en",
            "max_docs": 1,
        },
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "wikipedia", max_wait=FAST_WAIT)
    _search_and_log(client, "CMIS content management", "wikipedia",
                    expected_terms=["cmis", "content"])


@pytest.mark.datasource
@pytest.mark.integration
def test_youtube_ingest(client: APIClient) -> None:
    """Ingest a YouTube video transcript."""
    # Short public video with a confirmed English auto-transcript available
    # (TED talk: "The next web" by Tim Berners-Lee, ~16 min, stable transcript)
    url = "https://www.youtube.com/watch?v=OM6XIICm_qo"
    payload: dict[str, Any] = {
        "data_source": "youtube",
        "youtube_config": {
            "url": url,
            "chunk_size_seconds": 60,
        },
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "youtube", max_wait=FAST_WAIT)
    # Don't assert specific terms — transcript content varies; just assert completion
    _search_and_log(client, "knowledge graph retrieval", "youtube")


# ---------------------------------------------------------------------------
# Alfresco (requires local Docker stack)
# ---------------------------------------------------------------------------

def _alfresco_config() -> dict | None:
    url  = _env("ALFRESCO_URL")
    user = _env("ALFRESCO_USERNAME")
    pwd  = _env("ALFRESCO_PASSWORD")
    if not (url and user and pwd):
        return None
    return {
        "url": url,
        "username": user,
        "password": pwd,
        "path": "/Shared/GraphRAG",
        "recursive": True,
    }


@pytest.mark.datasource
@pytest.mark.integration
def test_alfresco_ingest(client: APIClient) -> None:
    """Ingest from Alfresco /Shared/GraphRAG (no incremental)."""
    cfg = _alfresco_config()
    if not cfg:
        pytest.skip("ALFRESCO_URL / ALFRESCO_USERNAME / ALFRESCO_PASSWORD not set")

    payload: dict[str, Any] = {
        "data_source": "alfresco",
        "alfresco_config": cfg,
        "enable_sync": False,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "alfresco", max_wait=MAX_WAIT)
    _search_and_log(client, "content management", "alfresco")


@pytest.mark.datasource
@pytest.mark.integration
def test_alfresco_ingest_with_sync(client: APIClient) -> None:
    """Ingest from Alfresco with incremental sync enabled."""
    cfg = _alfresco_config()
    if not cfg:
        pytest.skip("ALFRESCO_URL / ALFRESCO_USERNAME / ALFRESCO_PASSWORD not set")

    # Add STOMP port if set in env
    stomp_port = _env("ALFRESCO_STOMP_PORT")
    if stomp_port:
        cfg["stomp_port"] = int(stomp_port)

    payload: dict[str, Any] = {
        "data_source": "alfresco",
        "alfresco_config": cfg,
        "enable_sync": True,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "alfresco+sync", max_wait=MAX_WAIT)

    # Confirm datasource is registered for sync
    sources = client.list_datasources()
    alfresco_sources = [s for s in sources if s.get("source_type") == "alfresco"]
    logger.info("[alfresco+sync] registered datasources: %d alfresco sources", len(alfresco_sources))
    assert alfresco_sources, "Alfresco datasource not registered for sync after enable_sync=True"

    _search_and_log(client, "content management", "alfresco+sync")


# ---------------------------------------------------------------------------
# CMIS (requires local Docker stack — same Alfresco instance)
# ---------------------------------------------------------------------------

def _cmis_config() -> dict | None:
    url  = _env("CMIS_URL")
    user = _env("CMIS_USERNAME")
    pwd  = _env("CMIS_PASSWORD")
    if not (url and user and pwd):
        return None
    return {
        "url": url,
        "username": user,
        "password": pwd,
        "folder_path": "/Shared/GraphRAG",
    }


@pytest.mark.datasource
@pytest.mark.integration
def test_cmis_ingest(client: APIClient) -> None:
    """Ingest from CMIS /Shared/GraphRAG folder."""
    cfg = _cmis_config()
    if not cfg:
        pytest.skip("CMIS_URL / CMIS_USERNAME / CMIS_PASSWORD not set")

    payload: dict[str, Any] = {
        "data_source": "cmis",
        "cmis_config": cfg,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "cmis", max_wait=MAX_WAIT)
    _search_and_log(client, "content management", "cmis")


# ---------------------------------------------------------------------------
# S3 (credentials in env)
# ---------------------------------------------------------------------------

def _s3_config() -> dict | None:
    bucket = _env("S3_BUCKET_NAME")
    access = _env("S3_ACCESS_KEY")
    secret = _env("S3_SECRET_KEY")
    if not (bucket and access and secret):
        # Fall back to S3_CONFIG JSON blob
        cfg = _env_json("S3_CONFIG")
        if cfg:
            # Normalise key names to match S3Config model
            return {
                "bucket_name": cfg.get("bucket") or cfg.get("bucket_name", ""),
                "access_key":  cfg.get("access_key", ""),
                "secret_key":  cfg.get("secret_key", ""),
                "region_name": cfg.get("region_name"),
                "prefix":      cfg.get("prefix") or cfg.get("key") or "",
            }
        return None
    return {
        "bucket_name": bucket,
        "access_key":  access,
        "secret_key":  secret,
        "region_name": _env("S3_REGION_NAME") or "us-east-1",
        "prefix":      _env("S3_PREFIX") or "",
    }


@pytest.mark.datasource
@pytest.mark.integration
def test_s3_ingest(client: APIClient) -> None:
    """Ingest from S3 bucket."""
    cfg = _s3_config()
    if not cfg:
        pytest.skip("S3_BUCKET_NAME / S3_ACCESS_KEY / S3_SECRET_KEY (or S3_CONFIG) not set")

    payload: dict[str, Any] = {
        "data_source": "s3",
        "s3_config": cfg,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "s3", max_wait=MAX_WAIT)
    _search_and_log(client, "content", "s3")


# ---------------------------------------------------------------------------
# Box (credentials in env)
# ---------------------------------------------------------------------------

def _box_config() -> dict | None:
    cfg = _env_json("BOX_CONFIG")
    if cfg:
        return cfg
    # Try individual vars
    dev_token = _env("BOX_DEVELOPER_TOKEN")
    if dev_token:
        return {"developer_token": dev_token, "folder_id": _env("BOX_FOLDER_ID") or "0"}
    client_id = _env("BOX_CLIENT_ID")
    client_secret = _env("BOX_CLIENT_SECRET")
    enterprise_id = _env("BOX_ENTERPRISE_ID")
    if client_id and client_secret and enterprise_id:
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "enterprise_id": enterprise_id,
            "folder_id": _env("BOX_FOLDER_ID") or "0",
        }
    return None


@pytest.mark.datasource
@pytest.mark.integration
def test_box_ingest(client: APIClient) -> None:
    """Ingest from Box folder."""
    cfg = _box_config()
    if not cfg:
        pytest.skip("BOX_CONFIG (or BOX_DEVELOPER_TOKEN / BOX_CLIENT_ID) not set")

    payload: dict[str, Any] = {
        "data_source": "box",
        "box_config": cfg,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "box", max_wait=MAX_WAIT)
    _search_and_log(client, "content", "box")


# ---------------------------------------------------------------------------
# Cloud sources — skipped unless credentials are present
# ---------------------------------------------------------------------------

@pytest.mark.datasource
@pytest.mark.integration
def test_azure_blob_ingest(client: APIClient) -> None:
    """Ingest from Azure Blob Storage (requires AZURE_BLOB_CONFIG)."""
    cfg = _env_json("AZURE_BLOB_CONFIG")
    if not cfg:
        pytest.skip("AZURE_BLOB_CONFIG not set")

    payload: dict[str, Any] = {
        "data_source": "azure_blob",
        "azure_blob_config": cfg,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "azure_blob", max_wait=MAX_WAIT)
    _search_and_log(client, "content", "azure_blob")


@pytest.mark.datasource
@pytest.mark.integration
def test_onedrive_ingest(client: APIClient) -> None:
    """Ingest from OneDrive (requires ONEDRIVE_CONFIG)."""
    cfg = _env_json("ONEDRIVE_CONFIG")
    if not cfg:
        pytest.skip("ONEDRIVE_CONFIG not set")

    payload: dict[str, Any] = {
        "data_source": "onedrive",
        "onedrive_config": cfg,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "onedrive", max_wait=MAX_WAIT)
    _search_and_log(client, "content", "onedrive")


@pytest.mark.datasource
@pytest.mark.integration
def test_sharepoint_ingest(client: APIClient) -> None:
    """Ingest from SharePoint (requires SHAREPOINT_CONFIG)."""
    cfg = _env_json("SHAREPOINT_CONFIG")
    if not cfg:
        pytest.skip("SHAREPOINT_CONFIG not set")

    payload: dict[str, Any] = {
        "data_source": "sharepoint",
        "sharepoint_config": cfg,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "sharepoint", max_wait=MAX_WAIT)
    _search_and_log(client, "content", "sharepoint")


@pytest.mark.datasource
@pytest.mark.integration
def test_google_drive_ingest(client: APIClient) -> None:
    """Ingest from Google Drive (requires GOOGLE_DRIVE_CONFIG)."""
    cfg = _env_json("GOOGLE_DRIVE_CONFIG")
    if not cfg:
        pytest.skip("GOOGLE_DRIVE_CONFIG not set")

    payload: dict[str, Any] = {
        "data_source": "google_drive",
        "google_drive_config": cfg,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "google_drive", max_wait=MAX_WAIT)
    _search_and_log(client, "content", "google_drive")


@pytest.mark.datasource
@pytest.mark.integration
def test_gcs_ingest(client: APIClient) -> None:
    """Ingest from Google Cloud Storage (requires GCS_CONFIG)."""
    cfg = _env_json("GCS_CONFIG")
    if not cfg:
        pytest.skip("GCS_CONFIG not set")

    payload: dict[str, Any] = {
        "data_source": "gcs",
        "gcs_config": cfg,
    }
    r = client._session.post(f"{client.base_url}/api/ingest", json=payload, timeout=client.timeout)
    r.raise_for_status()
    result = IngestResult(
        processing_id=r.json().get("processing_id", ""),
        status=r.json().get("status", ""),
        message=r.json().get("message", ""),
        raw=r.json(),
    )
    _wait_and_assert(client, result, "gcs", max_wait=MAX_WAIT)
    _search_and_log(client, "content", "gcs")
