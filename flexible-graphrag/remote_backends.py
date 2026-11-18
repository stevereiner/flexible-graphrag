"""Remote Flexible GraphRAG backends fused into this backend's search and Q&A (federation).

A local backend (the desktop's, a laptop's) keeps its own documents and indexes, and at query time
also asks a team / business backend and fuses the answers: only the question (and the asker's own
source sign-ins) leave this machine, never its documents.

    REMOTE_FG_URL=https://graphrag.example.com    # the remote backend
    REMOTE_FG_API_TOKEN=...                       # its API_TOKEN, if it has one
    REMOTE_FG_NAME=team                           # shown on its results (default: its host)
    REMOTE_FG_TIMEOUT=60                          # seconds; a slower / down remote is skipped

Several: REMOTE_FG_BACKENDS, a JSON list of {name, url, api_token?, timeout?} (``configured()``);
REMOTE_FG_URL, when also set, is one more. Each remote is asked in parallel and weighs the same as
this backend's own results in the fusion.

Each remote is one retriever (RemoteFGRetriever): it calls the remote's ``POST /api/search``
(hybrid), so the remote runs its own full retrieval (vector, search, graph) and permission checks,
and its ranked results come back as nodes. They are fused with this backend's own results by
LlamaIndex's QueryFusionRetriever (relative_score: each side min-max scaled, equal weights), then
deduped by text like any other retriever's (query_engine._dedup_and_sum_scores).

Loops: a call to a remote carries ``X-FG-Federated: 1``; a backend answering such a call uses only
its own indexes, so A -> B -> A cannot recurse. A question limited to a scope here is not sent to
remotes either (a scope names this backend's documents).

Picked sources: GET /api/sources/available lists the remotes' sources too, tagged ``backend``. A
pick with a ``backend`` goes to that remote as its own pick; with picks, only the remotes that have
some are asked, and this backend answers only when some of its own are picked. The sign-ins the
remotes need are listed by GET /api/auth/requirements the same way.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from llama_index.core import QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode

logger = logging.getLogger(__name__)

FEDERATED_HEADER = "X-FG-Federated"

# metadata a remote result carries; kept out of the LLM prompt and embeddings
REMOTE_KEY = "_remote_backend"
REMOTE_SOURCE_KEY = "_remote_source"
REMOTE_DOCS_KEY = "_remote_documents"
_HIDDEN_KEYS = [REMOTE_KEY, REMOTE_SOURCE_KEY, REMOTE_DOCS_KEY]


@dataclass(frozen=True)
class RemoteBackend:
    name: str
    url: str
    token: Optional[str] = None
    timeout: float = 60.0


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _timeout(value: Any, default: float = 60.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def configured() -> List[RemoteBackend]:
    """The remote backends from the environment: REMOTE_FG_BACKENDS (a JSON list, for several:
    ``[{"name": "b", "url": "http://localhost:8001"}, {"name": "c", "url": "...", "api_token": "...",
    "timeout": 30}]``), then the single one of REMOTE_FG_URL / _API_TOKEN / _NAME. REMOTE_FG_TIMEOUT
    is every remote's default timeout. Names must differ: picks and results are told apart by them
    (a repeated name gets the URL's host / port added)."""
    default_timeout = _timeout(_env("REMOTE_FG_TIMEOUT"))
    entries: List[Dict[str, Any]] = []
    raw = _env("REMOTE_FG_BACKENDS")
    if raw:
        try:
            parsed = json.loads(raw)
            entries += [e for e in (parsed if isinstance(parsed, list) else [parsed]) if isinstance(e, dict)]
        except json.JSONDecodeError as e:
            logger.error("REMOTE_FG_BACKENDS is not valid JSON (%s): no remote backends from it", e)
    if _env("REMOTE_FG_URL"):
        entries.append({"url": _env("REMOTE_FG_URL"), "name": _env("REMOTE_FG_NAME"),
                        "api_token": _env("REMOTE_FG_API_TOKEN")})
    out: List[RemoteBackend] = []
    for e in entries:
        url = str(e.get("url") or "").strip().rstrip("/")
        if not url or any(r.url == url for r in out):
            continue
        parsed_url = urlparse(url)
        name = str(e.get("name") or "").strip() or parsed_url.hostname or "remote"
        if any(r.name == name for r in out):
            name = f"{name} ({parsed_url.netloc or url})"
        out.append(RemoteBackend(name=name, url=url, token=str(e.get("api_token") or "").strip() or None,
                                 timeout=_timeout(e.get("timeout"), default_timeout)))
    return out


@dataclass
class _Request:
    """What the question being answered allows (set by the /api/search and /api/query endpoints)."""
    federated: bool = False        # it came from another backend: answer from our own indexes only
    local_selection: bool = False  # a scope: this backend's documents only
    # picked sources, per remote ({name: [{source, url}]}): only those remotes are asked, each with
    # its picks; None = nothing picked (every remote, all its sources)
    remote_sources: Optional[Dict[str, List[Dict[str, Any]]]] = None
    # the asker's identities to pass on, so the remote applies their permissions
    source_auth: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = field(default_factory=dict)
    # what went wrong with a remote, for the answer
    notes: List[str] = field(default_factory=list)


_request: ContextVar[Optional[_Request]] = ContextVar("fg_remote_request", default=None)


def begin_request(federated: bool = False, local_selection: bool = False,
                  source_auth: Optional[Dict[str, Any]] = None,
                  alfresco_ticket: Optional[str] = None, alfresco_url: Optional[str] = None,
                  remote_sources: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
    headers = {}
    if alfresco_ticket:
        headers["X-Alfresco-Ticket"] = alfresco_ticket
        if alfresco_url:
            headers["X-Alfresco-Url"] = alfresco_url
    _request.set(_Request(federated=federated, local_selection=local_selection,
                          remote_sources=remote_sources, source_auth=source_auth or None, headers=headers))


def active() -> List[RemoteBackend]:
    """The remotes this question goes to: none when it came from another backend, or is limited
    to a scope here; with picked sources, only the remotes that have some picked."""
    req = _request.get()
    if req is not None and (req.federated or req.local_selection):
        return []
    remotes = configured()
    if req is not None and req.remote_sources is not None:
        remotes = [r for r in remotes if req.remote_sources.get(r.name)]
    return remotes


def notes() -> List[str]:
    req = _request.get()
    return list(req.notes) if req else []


def _note(text: str) -> None:
    req = _request.get()
    if req is not None and text not in req.notes:
        req.notes.append(text)


class RemoteFGRetriever(BaseRetriever):
    """One remote backend's hybrid search as a retriever. A remote that fails or times out gives
    no results (and a note); it never fails the question."""

    def __init__(self, remote: RemoteBackend, top_k: int = 10, transport=None) -> None:
        self._remote = remote
        self._top_k = top_k
        self._transport = transport  # tests: an httpx mock transport
        super().__init__()

    def _request_args(self, query: str):
        req = _request.get()
        headers = {FEDERATED_HEADER: "1", **(req.headers if req else {})}
        if self._remote.token:
            headers["X-API-Token"] = self._remote.token
        body: Dict[str, Any] = {"query": query, "top_k": self._top_k, "query_type": "hybrid"}
        if req is not None and req.source_auth:
            body["source_auth"] = req.source_auth
        if req is not None and req.remote_sources and req.remote_sources.get(self._remote.name):
            body["sources"] = req.remote_sources[self._remote.name]  # its own sources, as picked here
        return f"{self._remote.url}/api/search", body, headers

    def _nodes(self, response: httpx.Response) -> List[NodeWithScore]:
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        if not data.get("success", True):
            raise RuntimeError(str(data.get("error") or data.get("detail") or "failed"))
        name = self._remote.name
        out: List[NodeWithScore] = []
        for r in data.get("results") or []:
            text = (r.get("content") or "").strip()
            if not text:
                continue
            source = r.get("source") or r.get("file_name") or ""
            docs = [{**d, "backend": name} for d in (r.get("documents") or []) if isinstance(d, dict)]
            node = TextNode(
                id_=hashlib.sha256(f"{name}\n{text}".encode("utf-8", "surrogatepass")).hexdigest(),
                text=text,
                # "source" is what the LLM sees next to the text
                metadata={"source": f"{name}: {source}" if source else name,
                          REMOTE_KEY: name, REMOTE_SOURCE_KEY: source, REMOTE_DOCS_KEY: docs},
                excluded_llm_metadata_keys=list(_HIDDEN_KEYS),
                excluded_embed_metadata_keys=list(_HIDDEN_KEYS),
            )
            out.append(NodeWithScore(node=node, score=float(r.get("score") or 0.0)))
        return out

    def _failed(self, e: Exception) -> List[NodeWithScore]:
        what = "timed out" if isinstance(e, httpx.TimeoutException) else f"failed ({type(e).__name__}: {e})"
        logger.warning("Remote backend %s (%s) %s: answering without it", self._remote.name, self._remote.url, what)
        _note(f"{self._remote.name} didn't answer ({'timed out' if isinstance(e, httpx.TimeoutException) else 'error'}); "
              f"results are from the other backends only.")
        return []

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        url, body, headers = self._request_args(query_bundle.query_str)
        try:
            with httpx.Client(timeout=self._remote.timeout, transport=self._transport) as client:
                nodes = self._nodes(client.post(url, json=body, headers=headers))
        except Exception as e:
            return self._failed(e)
        logger.info("Remote backend %s: %d result(s)", self._remote.name, len(nodes))
        return nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        url, body, headers = self._request_args(query_bundle.query_str)
        try:
            async with httpx.AsyncClient(timeout=self._remote.timeout, transport=self._transport) as client:
                nodes = self._nodes(await client.post(url, json=body, headers=headers))
        except Exception as e:
            return self._failed(e)
        logger.info("Remote backend %s: %d result(s)", self._remote.name, len(nodes))
        return nodes


# tests: the httpx transport remote retrievers use (None = the network)
_transport = None


async def _remote_lists(path: str, key: str, what: str) -> List[Dict[str, Any]]:
    """GET ``path`` on every configured remote (all at once); the dicts in each answer's ``key``,
    tagged with the remote's name, in the remotes' order. A remote that doesn't answer adds none
    (a warning, never a failure)."""
    async def one(r: RemoteBackend) -> List[Dict[str, Any]]:
        headers = {FEDERATED_HEADER: "1"}
        if r.token:
            headers["X-API-Token"] = r.token
        try:
            async with httpx.AsyncClient(timeout=min(r.timeout, 5.0), transport=_transport) as client:
                resp = await client.get(f"{r.url}{path}", headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            return [{**p, "backend": r.name} for p in (resp.json().get(key) or []) if isinstance(p, dict)]
        except Exception as e:
            logger.warning("Remote backend %s: %s not known (%s: %s)", r.name, what, type(e).__name__, e)
            return []
    lists = await asyncio.gather(*(one(r) for r in configured()))
    return [p for items in lists for p in items]


async def remote_auth_providers() -> List[Dict[str, Any]]:
    """The sign-ins the remotes' stored content needs (each one's /api/auth/requirements), tagged
    with the remote's name. This backend's UIs then offer them too: without, a remote's Alfresco
    documents stay hidden (it gets no sign-in), and nothing here would ask for one. The asker's
    sign-ins already go to the remotes with each question."""
    return await _remote_lists("/api/auth/requirements", "providers", "sign-ins it needs")


async def remote_sources_available() -> List[Dict[str, Any]]:
    """The remotes' sources (each one's /api/sources/available), tagged with the remote's name, for
    this backend's source picker; a pick sent back with that ``backend`` goes to that remote."""
    return await _remote_lists("/api/sources/available", "sources", "its sources")


def with_remotes(local: Optional[BaseRetriever], top_k: int = 10) -> Optional[BaseRetriever]:
    """``local`` fused with the remotes this question goes to; ``local`` itself when there are
    none. ``local`` may be None (nothing indexed here, or nothing here the asker may read)."""
    remotes = active()
    if not remotes:
        return local
    parts: List[BaseRetriever] = ([local] if local is not None else [])
    parts += [RemoteFGRetriever(r, top_k=top_k, transport=_transport) for r in remotes]
    if len(parts) == 1:
        return parts[0]
    from llama_index.core.llms import MockLLM
    from llama_index.core.retrievers import QueryFusionRetriever
    logger.info("Fusing this backend's results with remote backend(s): %s", ", ".join(r.name for r in remotes))
    return QueryFusionRetriever(
        retrievers=parts,
        llm=MockLLM(),  # num_queries=1: it writes no extra queries, so it needs no real LLM
        mode="relative_score",
        similarity_top_k=15,
        num_queries=1,
        use_async=True,
    )


def remote_result(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """For a node from a remote: {backend, source, documents}; None for this backend's own."""
    name = (meta or {}).get(REMOTE_KEY)
    if not name:
        return None
    return {"backend": name, "source": meta.get(REMOTE_SOURCE_KEY) or "",
            "documents": list(meta.get(REMOTE_DOCS_KEY) or [])}
