"""Shared parts of the auto-sync matrix: the backend under test, the OpenArch tree it keeps its
state in, the .env reader and the report.

The checks read the tree (``<root>/<source type>/<system>/<source path>``, the OpenArch state
store's source documents): a document is *followed* by a sync when its ``fg_docstate_states``
has an entry for that sync's config id. With ``ENABLE_OPENARCH=true`` the tree documents also hold
the extracted text; without it (state only, vectors and search elsewhere) an edit shows as a new
``contentHash`` in the sync's entry.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

# As the backend does (main.py): verify TLS against the OS cert store, so the source clients
# (boto3, Azure, Google, Box, Graph) work behind TLS-inspecting proxies such as Norton Web Shield
if os.getenv("USE_SYSTEM_CERT_STORE", "true").lower() != "false":
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass

REPO = Path(__file__).resolve().parents[3]
FG = REPO / "flexible-graphrag"
if str(FG) not in sys.path:
    sys.path.insert(0, str(FG))

from openarch.client import OpenArchClient, under  # noqa: E402


# ── .env ─────────────────────────────────────────────────────────────────────────────────────

_ENV: Optional[Dict[str, str]] = None


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    """A setting from the environment, else flexible-graphrag/.env. Never printed by the harness."""
    global _ENV
    if name in os.environ:
        return os.environ[name]
    if _ENV is None:
        _ENV = {}
        path = FG / ".env"
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)$", line)
                if m and m.group(1) not in _ENV:
                    value = m.group(2).strip()
                    if not value.startswith("{"):
                        value = value.split(" #", 1)[0].strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    _ENV[m.group(1)] = value
    return _ENV.get(name, default)


def env_json(name: str) -> Dict[str, Any]:
    """A JSON setting such as S3_CONFIG ({} when missing or not JSON; text may follow the JSON)."""
    raw = env(name) or ""
    if not raw.startswith("{"):
        return {}
    try:
        value, _ = json.JSONDecoder().raw_decode(raw)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


# ── report ───────────────────────────────────────────────────────────────────────────────────

@dataclass
class Report:
    results: List[Dict[str, Any]] = field(default_factory=list)
    source: str = ""
    scenario: str = ""

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append({"source": self.source, "scenario": self.scenario, "check": name,
                             "ok": bool(ok), "detail": detail})
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)
        return bool(ok)

    def note(self, text: str) -> None:
        print(f"        {text}", flush=True)

    def error(self, text: str) -> None:
        self.check(f"{self.scenario}: ran without an error", False, text[:300])

    def summary(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for r in self.results:
            s = out.setdefault(r["source"], {"passed": 0, "failed": 0})
            s["passed" if r["ok"] else "failed"] += 1
        return out

    def failed(self) -> List[Dict[str, Any]]:
        return [r for r in self.results if not r["ok"]]

    def save(self, path: Path, meta: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"meta": meta, "summary": self.summary(), "results": self.results},
                                   indent=1), encoding="utf-8")


def wait(pred: Callable[[], bool], timeout: float, every: float = 5) -> Optional[int]:
    """Seconds until ``pred()`` held, or None after ``timeout``."""
    t0 = time.time()
    while True:
        try:
            if pred():
                return int(time.time() - t0)
        except Exception:
            pass
        if time.time() - t0 >= timeout:
            return None
        time.sleep(every)


# ── the backend under test ───────────────────────────────────────────────────────────────────

class Backend:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.api = f"{self.url}/api"
        self.process: Optional[subprocess.Popen] = None

    def healthy(self) -> bool:
        try:
            return httpx.get(f"{self.api}/health", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    @classmethod
    def start(cls, port: int, overrides: Dict[str, str], log_path: Path, timeout: int = 240) -> "Backend":
        """Start flexible-graphrag's backend on ``port`` with ``overrides`` over .env (one process,
        no reload). Started from Python, so Git Bash never rewrites the /fg-... path values."""
        be = cls(f"http://127.0.0.1:{port}")
        if be.healthy():
            raise RuntimeError(f"something already answers on port {port}; stop it or pick --port")
        python = REPO / "venv-3.14" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        child_env = dict(os.environ, **overrides)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "w", encoding="utf-8", errors="replace")
        be.process = subprocess.Popen(
            [str(python), "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(FG), env=child_env, stdout=log, stderr=subprocess.STDOUT)
        if wait(lambda: be.process.poll() is not None or be.healthy(), timeout, every=3) is None \
                or be.process.poll() is not None:
            be.stop()
            raise RuntimeError(f"backend on port {port} did not come up; see {log_path}")
        return be

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def ingest(self, body: Dict[str, Any], timeout: int = 900) -> Dict[str, Any]:
        """Run an ingest to its end: the response (config_id, ...) plus ``status`` / ``message``."""
        r = httpx.post(f"{self.api}/ingest", json=body, timeout=600)
        if r.status_code >= 400:
            return {"status": "http_error", "message": f"{r.status_code} {r.text[:300]}"}
        job = r.json()
        pid = job.get("processing_id")
        t0 = time.time()
        while pid and time.time() - t0 < timeout:
            s = httpx.get(f"{self.api}/processing-status/{pid}", timeout=30).json()
            if s.get("status") in ("completed", "failed", "error", "cancelled"):
                return dict(job, status=s.get("status"), message=s.get("message") or "")
            time.sleep(3)
        return dict(job, status=job.get("status") or ("timeout" if pid else "unknown"),
                    message=job.get("message") or "")

    def ingest_status(self, body: Dict[str, Any]) -> Dict[str, Any]:
        r = httpx.post(f"{self.api}/sync/ingest-status", json=body, timeout=120)
        r.raise_for_status()
        return r.json()

    def remove(self, body: Dict[str, Any]) -> Dict[str, Any]:
        r = httpx.post(f"{self.api}/sync/remove", json=body, timeout=600)
        r.raise_for_status()
        return r.json()

    def set_interval(self, config_id: str, seconds: int) -> None:
        httpx.patch(f"{self.api}/sync/datasources/{config_id}/interval",
                    params={"interval_seconds": seconds}, timeout=60).raise_for_status()

    def search(self, query: str, top_k: int = 10, source_auth: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        body: Dict[str, Any] = {"query": query, "top_k": top_k, "query_type": "hybrid"}
        if source_auth:
            body["source_auth"] = source_auth
        r = httpx.post(f"{self.api}/search", json=body, timeout=300)
        r.raise_for_status()
        return r.json().get("results") or []


# ── the OpenArch tree ────────────────────────────────────────────────────────────────────────

@dataclass
class TreeDoc:
    path: str
    states: List[Dict[str, Any]]
    text: str

    def state(self, config_id: Optional[str]) -> Optional[Dict[str, Any]]:
        for s in self.states:
            if config_id is None or s.get("configId") == config_id:
                return s
        return None


class Tree:
    def __init__(self, url: str, root: str):
        self.client = OpenArchClient(url, env("OPENARCH_USERNAME", "admin"), env("OPENARCH_PASSWORD", "password"))
        self.root = "/" + root.strip("/")

    def docs(self, source_type: str, key: str, case_insensitive: bool = False) -> Dict[str, TreeDoc]:
        """The source documents of ``source_type`` whose path contains ``/<key>/``, by their path
        below it (lower case when ``case_insensitive``)."""
        marker = f"/{key.strip('/')}/"
        if case_insensitive:
            marker = marker.lower()
        out: Dict[str, TreeDoc] = {}
        for d in self.client.query_all("SELECT * FROM SysFile WHERE " + under(f"{self.root}/{source_type}")):
            path = d.get("sys_path") or ""
            hay = (path + "/").lower() if case_insensitive else path + "/"
            if marker in hay:
                rel = path[hay.index(marker) + len(marker):]
                out[rel.lower() if case_insensitive else rel] = TreeDoc(
                    path, list(d.get("fg_docstate_states") or []),
                    (d.get("cin_ingestProperties") or {}).get("fg_extractedText") or "")
        return out

    def delete_folder(self, path: str) -> bool:
        """Delete a folder with its subtree (the test run's own tree roots); False when missing."""
        d = self.client.get_by_path("/" + path.strip("/"))
        return bool(d and self.client.delete(d["sys_id"]))
