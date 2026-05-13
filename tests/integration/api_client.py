"""
REST API client helper for Flexible GraphRAG integration tests.

Uses the FastAPI HTTP endpoints only (not MCP).

Wraps every endpoint the tests use, with retry-on-startup support and
structured result objects so assertions stay readable.
"""
from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes returned to tests
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IngestResult:
    processing_id: str
    status: str
    message: str
    raw: dict = field(default_factory=dict)

@dataclass
class SearchResult:
    results: list[dict]
    query: str
    total: int = 0

@dataclass
class StatusResult:
    processing_id: str
    status: str          # "processing" | "completed" | "failed"
    progress: float = 0.0
    message: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def is_done(self) -> bool:
        return self.status in ("completed", "failed", "error")


@dataclass
class QueryResult:
    """Response from POST /api/query (LLM Q&A over retrieved context)."""

    status: str
    answer: str
    raw: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Client
# ──────────────────────────────────────────────────────────────────────────────

class APIClient:
    """Thin wrapper around the Flexible GraphRAG REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> None:
        self.base_url = (base_url or os.getenv("API_TEST_BASE_URL", "http://localhost:8000")).rstrip("/")
        self.timeout = timeout
        self._session = self._make_session()

    # ── session ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
        )
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    # ── health ────────────────────────────────────────────────────────────────

    def wait_until_healthy(self, max_wait: int = 60, interval: float = 2.0) -> bool:
        """Poll /api/health until the backend responds or max_wait expires."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                r = self._session.get(f"{self.base_url}/api/health", timeout=5)
                if r.status_code == 200:
                    logger.info("Backend healthy: %s", r.json())
                    return True
            except requests.ConnectionError:
                pass
            time.sleep(interval)
        return False

    def health(self) -> dict:
        return self._session.get(f"{self.base_url}/api/health", timeout=self.timeout).json()

    def info(self) -> dict:
        return self._session.get(f"{self.base_url}/api/info", timeout=self.timeout).json()

    # ── ingest ────────────────────────────────────────────────────────────────

    def ingest_file(self, file_path: str | Path) -> IngestResult:
        """Upload via /api/upload, then start async ingestion with /api/ingest (returns processing_id).

        ``/api/upload`` only saves bytes under the server's ``uploads/`` folder; processing is started
        by ``POST /api/ingest`` with the saved path. Multipart field name must be ``files`` (FastAPI
        ``List[UploadFile]``), not ``file``.
        """
        file_path = Path(file_path)
        with file_path.open("rb") as fh:
            r = self._session.post(
                f"{self.base_url}/api/upload",
                files=[("files", (file_path.name, fh, "text/plain"))],
                timeout=self.timeout,
            )
        r.raise_for_status()
        upload_data = r.json()
        uploaded = upload_data.get("files") or []
        if not uploaded:
            skipped = upload_data.get("skipped") or []
            raise RuntimeError(
                f"/api/upload saved no files (skipped={skipped!r}). Response: {upload_data!r}"
            )
        server_path = uploaded[0].get("path")
        if not server_path:
            raise RuntimeError(f"/api/upload response missing files[0].path: {upload_data!r}")

        r2 = self._session.post(
            f"{self.base_url}/api/ingest",
            json={"paths": [server_path], "data_source": "filesystem"},
            timeout=self.timeout,
        )
        r2.raise_for_status()
        data = r2.json()
        return IngestResult(
            processing_id=data.get("processing_id", ""),
            status=data.get("status", ""),
            message=data.get("message", ""),
            raw={"upload": upload_data, "ingest": data},
        )

    def ingest_folder(
        self,
        folder_path: str | Path,
        *,
        batch: bool = False,
    ) -> list[IngestResult]:
        """Ingest all files in *folder_path* via POST /api/ingest with filesystem paths.

        Since the test runner and backend share the same filesystem, absolute paths are
        passed directly — no upload step needed.  The backend's ``FileSystemSource``
        handles both individual file paths and directory paths (recurses into dirs).

        Parameters
        ----------
        folder_path:
            Directory whose files should be ingested.
        batch:
            If ``True``, send the **folder path itself** in a single POST /api/ingest
            request.  The backend's ``FileSystemSource`` walks the directory and
            processes all supported files under one ``processing_id``.
            If ``False`` (default), enumerate files here and send one request per file
            so each gets its own ``processing_id`` that can be polled independently.

        Returns a list of :class:`IngestResult` — one item in batch mode, one per
        file in one-at-a-time mode.

        This approach also generalises for multi-datasource testing: swap
        ``data_source`` and add a config blob (``s3_config``, ``azure_blob_config``,
        etc.) to cover cloud sources without changing the calling convention.
        """
        folder_path = Path(folder_path).resolve()
        if not folder_path.is_dir():
            raise ValueError(f"ingest_folder: {folder_path!r} is not a directory")

        if batch:
            # Pass the folder path directly — FileSystemSource.list_files() recurses
            # into directories, so the backend discovers all supported files itself.
            abs_dir = str(folder_path)
            logger.info("POST /api/ingest filesystem batch dir=%s", abs_dir)
            r = self._session.post(
                f"{self.base_url}/api/ingest",
                json={"data_source": "filesystem", "paths": [abs_dir]},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            return [IngestResult(
                processing_id=data.get("processing_id", ""),
                status=data.get("status", ""),
                message=data.get("message", ""),
                raw=data,
            )]

        # One-at-a-time: enumerate files client-side, one request + processing_id each.
        files = sorted(p for p in folder_path.iterdir() if p.is_file())
        if not files:
            raise RuntimeError(f"ingest_folder: no files found in {folder_path!r}")

        results: list[IngestResult] = []
        for fp in files:
            abs_path = str(fp)
            logger.info("POST /api/ingest filesystem path=%s", abs_path)
            r = self._session.post(
                f"{self.base_url}/api/ingest",
                json={"data_source": "filesystem", "paths": [abs_path]},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            results.append(IngestResult(
                processing_id=data.get("processing_id", ""),
                status=data.get("status", ""),
                message=data.get("message", ""),
                raw=data,
            ))
        return results

    def ingest_filesystem_paths_with_sync(
        self,
        paths: list[str],
        *,
        enable_sync: bool = True,
    ) -> IngestResult:
        """POST /api/ingest with filesystem paths and incremental sync registration.

        Resolves each path with :func:`Path.resolve` so the server receives absolute paths
        (required for ``enable_sync`` / filesystem monitoring in ``main.py``).
        """
        abs_paths = [str(Path(p).resolve()) for p in paths]
        payload: dict[str, Any] = {
            "data_source": "filesystem",
            "paths": abs_paths,
            "enable_sync": enable_sync,
        }
        logger.info("POST /api/ingest filesystem enable_sync=%s paths=%s", enable_sync, abs_paths)
        r = self._session.post(
            f"{self.base_url}/api/ingest",
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return IngestResult(
            processing_id=data.get("processing_id", ""),
            status=data.get("status", ""),
            message=data.get("message", ""),
            raw=data,
        )

    def ingest_text(
        self,
        text: str,
        filename: str = "test_doc.txt",
        skip_graph: bool = False,
    ) -> IngestResult:
        """Ingest a text string via /api/ingest-text.

        The endpoint's ``TextIngestRequest`` model expects ``content`` (not
        ``text``) and ``source_name`` (not ``filename``).
        """
        body: dict = {"content": text, "source_name": filename}
        if skip_graph:
            body["skip_graph"] = True
        r = self._session.post(
            f"{self.base_url}/api/ingest-text",
            json=body,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return IngestResult(
            processing_id=data.get("processing_id", ""),
            status=data.get("status", ""),
            message=data.get("message", ""),
            raw=data,
        )

    def ingest_url(self, url: str) -> IngestResult:
        """Ingest a URL via /api/ingest."""
        r = self._session.post(
            f"{self.base_url}/api/ingest",
            json={"url": url},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return IngestResult(
            processing_id=data.get("processing_id", ""),
            status=data.get("status", ""),
            message=data.get("message", ""),
            raw=data,
        )

    # ── status polling ────────────────────────────────────────────────────────

    def get_status(self, processing_id: str) -> StatusResult:
        r = self._session.get(
            f"{self.base_url}/api/processing-status/{processing_id}",
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return StatusResult(
            processing_id=processing_id,
            status=data.get("status", "unknown"),
            progress=float(data.get("progress", 0)),
            message=data.get("message", ""),
            raw=data,
        )

    def wait_for_completion(
        self,
        processing_id: str,
        max_wait: int = 300,
        poll_interval: float = 3.0,
    ) -> StatusResult:
        """Block until ingestion completes (or times out)."""
        deadline = time.time() + max_wait
        last: StatusResult | None = None
        while time.time() < deadline:
            last = self.get_status(processing_id)
            logger.debug(
                "Status [%s]: %s %.0f%%", processing_id, last.status, last.progress * 100
            )
            if last.is_done:
                return last
            time.sleep(poll_interval)
        raise TimeoutError(
            f"Processing {processing_id} did not finish within {max_wait}s. "
            f"Last status: {last}"
        )

    # ── search / query ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 5,
        extra: dict | None = None,
    ) -> SearchResult:
        payload = {"query": query, "top_k": top_k, **(extra or {})}
        r = self._session.post(
            f"{self.base_url}/api/search",
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        return SearchResult(query=query, results=results, total=len(results))

    def query(
        self,
        question: str,
        *,
        top_k: int = 10,
        query_type: str | None = None,
        extra: dict | None = None,
        timeout: int | None = None,
    ) -> QueryResult:
        """LLM Q&A via /api/query (same contract as main.QueryRequest)."""
        payload: dict[str, Any] = {"query": question, "top_k": top_k}
        if query_type is not None:
            payload["query_type"] = query_type
        if extra:
            payload.update(extra)
        _slow_providers = {"ollama", "openai_like", "vllm", "litellm"}
        _default_ai_timeout = (
            600 if os.getenv("LLM_PROVIDER", "openai").lower() in _slow_providers
            else max(self.timeout, 180)
        )
        ai_timeout = timeout if timeout is not None else int(
            os.getenv("API_TEST_AI_TIMEOUT", str(_default_ai_timeout))
        )
        r = self._session.post(
            f"{self.base_url}/api/query",
            json=payload,
            timeout=ai_timeout,
        )
        r.raise_for_status()
        data = r.json()
        return QueryResult(
            status=str(data.get("status", "") or ""),
            answer=str(data.get("answer", "") or ""),
            raw=data,
        )

    # ── graph query ───────────────────────────────────────────────────────────

    def graph_query(
        self,
        query: str,
        *,
        language: str | None = None,
        params: dict | None = None,
    ) -> dict:
        """POST /api/graph/query — run a native graph query against the configured store.

        Routes through the LC adapter's ``lc_graph.query()`` for all 15 PG stores,
        falling back to LI ``structured_query()`` and finally SPARQL for RDF-only
        deployments.

        Parameters
        ----------
        query:
            Native query string: Cypher, AQL, SurrealQL, Gremlin, GSQL, GQL, SPARQL, etc.
        language:
            Optional hint (``"cypher"``, ``"aql"``, ``"sparql"``, ...).  The backend
            infers it from the configured DB type if omitted.
        params:
            Optional parameter dict passed to the store's query method.

        Returns the raw response dict with keys ``results``, ``row_count``,
        ``backend``, ``language``, and optionally ``error``.
        """
        payload: dict[str, Any] = {"query": query}
        if language:
            payload["language"] = language
        if params:
            payload["params"] = params
        r = self._session.post(
            f"{self.base_url}/api/graph/query",
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    # ── graph stats ───────────────────────────────────────────────────────────

    def get_graph_stats(self) -> dict:
        """GET /api/graph — returns graph database info / configuration status.

        The endpoint currently returns a status dict (database type, store type,
        message). It does not yet return node / relationship counts directly — use
        it to confirm the store is configured and to read the dashboard URL.
        For actual counts: query the graph DB directly (Neo4j Browser, ArangoDB
        web UI, etc.) or extend /api/graph in main.py to run a native count query.
        """
        r = self._session.get(f"{self.base_url}/api/graph", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ── incremental sync ──────────────────────────────────────────────────────

    def list_datasources(self) -> list[dict]:
        r = self._session.get(
            f"{self.base_url}/api/sync/datasources",
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json().get("datasources", [])

    def start_monitoring(self) -> dict:
        r = self._session.post(
            f"{self.base_url}/api/sync/start-monitoring",
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def sync_now(self) -> dict:
        r = self._session.post(
            f"{self.base_url}/api/sync/sync-now",
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def sync_status(self) -> dict:
        r = self._session.get(
            f"{self.base_url}/api/sync/status",
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def wait_for_watching(self, min_updaters: int = 1, max_wait: int = 60, poll: float = 2.0) -> bool:
        """Poll /api/sync/status until active_updaters >= min_updaters (watchdog is live)."""
        import time
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                status = self.sync_status()
                if status.get("active_updaters", 0) >= min_updaters:
                    return True
            except Exception:
                pass
            time.sleep(poll)
        return False
