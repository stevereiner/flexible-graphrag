"""Flow Service for Flexible GraphRAG.

Runs the Langflow ingest/query FLOWS via the Langflow REST API, so the app/backend can use
the same visual flows as the pipeline (OpenRAG-style). Used by backend.py when
settings.enable_langflow_flows is true.

- Loads the flow JSON files (paths from config), reusing an existing flow by name when present
  (so backend restarts don't create duplicates).
- Discovers node IDs by component type from the flow JSON, so tweaks target the right nodes
  regardless of exact IDs.
- Ingestion: tweaks the FlexibleDataSource node with source_type + source_config (the app's
  per-source JSON) + config_path; the flow loads the source and runs the whole pipeline.
- Query: sends the question as input_value (ChatInput); returns the flow output.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Substrings that mark a config value as a secret (matched case-insensitively against the key).
# "_path" keys (e.g. service_account_key_path) are file references, not secrets — kept for debug.
_SECRET_KEY_MARKERS = (
    "credential", "service_account_key", "account_key", "connection_string",
    "secret", "password", "api_key", "apikey", "client_secret", "token", "private_key",
    "ticket",  # an Alfresco login ticket authenticates on its own, like a bearer token
)


def redact_config_for_log(cfg: Any, max_len: int = 60) -> Any:
    """Return a copy of a config dict safe to write to logs.

    Secret-looking keys are masked; long string values are truncated. Nested dicts (e.g.
    run_cfg -> source_config) are handled recursively. Used for DEBUG-level config logging so
    ingest config can be inspected without dumping credentials or huge key blobs to disk.
    """
    if isinstance(cfg, dict):
        out: Dict[str, Any] = {}
        for k, v in cfg.items():
            kl = str(k).lower()
            if not kl.endswith("_path") and any(m in kl for m in _SECRET_KEY_MARKERS):
                # Mask the value, but not its absence. Redacting None and "" as well made a
                # log unable to answer "was a credential actually sent?" -- an unset ticket
                # printed exactly like a real one. Neither None nor "" discloses anything.
                out[k] = v if v is None or v == "" else "***redacted***"
            else:
                out[k] = redact_config_for_log(v, max_len)
        return out
    if isinstance(cfg, str) and len(cfg) > max_len:
        return f"{cfg[:max_len]}…(+{len(cfg) - max_len} chars)"
    return cfg


class FlowService:
    """Service for executing Langflow flows."""

    def __init__(self, langflow_url: str = None, langflow_api_key: str = None):
        self.langflow_url = (langflow_url or os.getenv("LANGFLOW_URL", "http://localhost:7860")).rstrip("/")
        self.langflow_api_key = langflow_api_key or os.getenv("LANGFLOW_API_KEY")
        # Ingestion runs synchronously over this one HTTP call and can take many minutes
        # (KG extraction is LLM-bound — ~minutes per hundred chunks). No READ timeout so a
        # long ingest isn't cut off; keep a short connect timeout to fail fast if langflow is down.
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=30.0))

        self.ingestion_flow_id: Optional[str] = None
        self.query_flow_id: Optional[str] = None       # combined (Playground); app uses the dedicated flows below
        self.search_flow_id: Optional[str] = None      # dedicated search-only flow (no AI Query branch)
        self.aiquery_flow_id: Optional[str] = None      # dedicated AI-query-only flow (no Hybrid Search branch)
        # component-type -> node-id maps, per flow
        self._ingest_nodes: Dict[str, str] = {}
        self._query_nodes: Dict[str, str] = {}
        self._search_nodes: Dict[str, str] = {}
        self._aiquery_nodes: Dict[str, str] = {}

    async def close(self):
        await self.client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        url = f"{self.langflow_url}{endpoint}"
        headers = kwargs.pop("headers", {})
        if self.langflow_api_key:
            # Langflow API endpoints (incl. /run) authenticate via the API key header
            # (x-api-key). Do NOT also send "Authorization: Bearer <api_key>" — langflow
            # tries to decode the Authorization header as a JWT and 401s when it's an API key.
            headers["x-api-key"] = self.langflow_api_key
        else:
            # local AUTO_LOGIN fallback (works for read endpoints like /flows)
            try:
                tok = (await self.client.get(f"{self.langflow_url}/api/v1/auto_login")).json().get("access_token")
                if tok:
                    headers["Authorization"] = f"Bearer {tok}"
            except Exception:
                pass
        response = await self.client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response

    # ----------------------------------------------------------------- flow loading

    @staticmethod
    def _node_id_map(flow_data: dict) -> Dict[str, str]:
        """Map component `data.type` -> node id from a flow JSON."""
        out: Dict[str, str] = {}
        for n in (flow_data.get("data", {}) or {}).get("nodes", []) or []:
            t = (n.get("data", {}) or {}).get("type")
            if t and t not in out:
                out[t] = n.get("id")
        return out

    async def _ensure_flow(self, flow_path: str) -> tuple:
        """Return (flow_id, node_id_map). Reuse an existing flow by name, else upload the file."""
        path = Path(flow_path)
        if not path.exists():
            raise FileNotFoundError(f"Flow file not found: {flow_path}")
        flow_data = json.loads(path.read_text(encoding="utf-8"))
        name = flow_data.get("name")
        node_map = self._node_id_map(flow_data)

        # Delete any existing flows with this name, then upload the current file — so the
        # running flow always matches flows/*.json (correct node IDs + latest fields).
        try:
            existing = (await self._request("GET", "/api/v1/flows/")).json()
            for f in existing if isinstance(existing, list) else existing.get("flows", []):
                if f.get("name") == name and f.get("id"):
                    try:
                        await self._request("DELETE", f"/api/v1/flows/{f['id']}")
                        logger.info("FlowService: removed stale flow '%s' (%s)", name, f["id"])
                    except Exception as de:
                        logger.debug("FlowService: could not delete flow %s: %s", f.get("id"), de)
        except Exception as exc:
            logger.debug("FlowService: could not list flows: %s", exc)

        result = (await self._request("POST", "/api/v1/flows/", json=flow_data)).json()
        logger.info("FlowService: uploaded flow '%s' -> %s", name, result.get("id"))
        return result.get("id"), node_map

    async def initialize_flows(self, ingestion_flow_path: str, query_flow_path: str,
                               search_flow_path: Optional[str] = None,
                               aiquery_flow_path: Optional[str] = None):
        self.ingestion_flow_id, self._ingest_nodes = await self._ensure_flow(ingestion_flow_path)
        self.query_flow_id, self._query_nodes = await self._ensure_flow(query_flow_path)
        # Dedicated single-branch flows for the app: a search runs ONLY Hybrid Search and an AI
        # query runs ONLY AI Query (langflow runs every branch present in a flow, so the combined
        # query flow would also fire the other branch — e.g. an AI Query LLM call on each search).
        # Optional / best-effort: fall back to the combined query flow if a file is missing.
        for path, attr, nodes_attr in (
            (search_flow_path, "search_flow_id", "_search_nodes"),
            (aiquery_flow_path, "aiquery_flow_id", "_aiquery_nodes"),
        ):
            if path and Path(path).exists():
                try:
                    fid, nmap = await self._ensure_flow(path)
                    setattr(self, attr, fid)
                    setattr(self, nodes_attr, nmap)
                except Exception as exc:
                    logger.warning("FlowService: could not load dedicated flow %s: %s", path, exc)
            elif path:
                logger.info("FlowService: dedicated flow not found (%s) — falling back to the combined query flow", path)

    # ----------------------------------------------------------------- run

    async def run_ingestion_flow(
        self,
        source_type: str,
        source_config: Optional[Dict[str, Any]] = None,
        config_path: Optional[str] = None,
        skip_graph: bool = False,
        config_id: Optional[str] = None,
        tweaks: Optional[Dict[str, Any]] = None,
        replace_doc_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not self.ingestion_flow_id:
            raise ValueError("Ingestion flow not loaded. Call initialize_flows() first.")

        # Pass the per-run config as the flow's input_value (ChatInput -> Data Source trigger
        # edge) — the natural langflow data path. We do NOT use tweaks (langflow drops tweaks
        # on non-param inputs and caches flows in ways that make them unreliable here).
        run_cfg = {"source_type": source_type, "source_config": source_config or {}}
        if config_path:
            run_cfg["config_path"] = config_path
        if skip_graph:
            run_cfg["skip_graph"] = True
        if config_id:
            # Stable doc_id prefix for incremental sync — the Data Source threads it through
            # the run-cache; the Document Processor assigns {config_id}:{identity} doc_ids.
            run_cfg["config_id"] = config_id
        if replace_doc_ids:
            # doc_ids an earlier ingest of this source stored. The langflow process has no
            # incremental registry of its own, so the backend looks them up and the Document
            # Processor deletes those it is about to insert again.
            run_cfg["replace_doc_ids"] = list(replace_doc_ids)

        # output_type="debug" returns ALL component outputs (not just ChatOutput) so we can
        # also read the Document Processor's doc_states (needed to create document_state rows
        # for incremental sync). The chat summary is still in there for extract_message().
        out_type = "debug" if config_id else "text"
        payload = {"input_value": json.dumps(run_cfg), "input_type": "chat",
                   "output_type": out_type, "tweaks": dict(tweaks or {})}
        logger.info("FlowService: run ingest flow %s output=%s", self.ingestion_flow_id, out_type)
        logger.debug("FlowService: run_cfg=%s", redact_config_for_log(run_cfg))
        response = await self._request("POST", f"/api/v1/run/{self.ingestion_flow_id}", json=payload)
        return response.json()

    def extract_doc_states(self, run_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Pull the Document Processor's compact doc-states ({id_, metadata}) out of a debug
        run result, for incremental-sync document_state creation. [] if absent."""
        data = self.extract_data(run_result, ("doc_states",)) or {}
        return data.get("doc_states") or []

    async def run_query_flow(
        self,
        query: str,
        config_path: Optional[str] = None,
        top_k: int = 10,
        tweaks: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.query_flow_id:
            raise ValueError("Query flow not loaded. Call initialize_flows() first.")

        # The question flows as input_value (ChatInput -> Hybrid Search + AI Query query edges).
        # No tweaks — top_k / config_path use the flow's defaults (backend .env). If per-run
        # overrides are needed later, thread them the same way the ingest flow does.
        payload = {"input_value": query, "input_type": "chat",
                   "output_type": "chat", "tweaks": dict(tweaks or {})}
        logger.info("FlowService: run query flow %s input_value=%r", self.query_flow_id, query[:200])
        response = await self._request("POST", f"/api/v1/run/{self.query_flow_id}", json=payload)
        return response.json()

    async def _run_query_component(self, query: str, component_type: str,
                                   flow_id: Optional[str] = None,
                                   node_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run a flow returning ONE component's structured Data output.

        The question flows as input_value (ChatInput -> the component's query edge); we ask
        langflow for just that component's output (output_component), so the app gets the
        same structured result the non-flow backend produces — not the combined chat summary.
        Defaults to the combined query flow; pass flow_id/node_map to target a dedicated flow.
        """
        flow_id = flow_id or self.query_flow_id
        node_map = node_map if node_map is not None else self._query_nodes
        if not flow_id:
            raise ValueError("Query flow not loaded. Call initialize_flows() first.")
        nid = node_map.get(component_type)
        if not nid:
            raise ValueError(f"Component {component_type} not found in flow")
        payload = {"input_value": query, "input_type": "chat", "output_type": "any",
                   "output_component": nid, "tweaks": {}}
        response = await self._request("POST", f"/api/v1/run/{flow_id}", json=payload)
        return response.json()

    async def run_search_flow(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Hybrid search via the flow — returns the raw system.search() result list.

        system.search() returns source/file_name/file_type at the top level; the UI reads
        result.metadata?.source, so we also mirror those under `metadata` (keeping the
        top-level fields) so flow-mode search renders identically to direct mode.

        Uses the dedicated search-only flow when available (so no AI Query branch runs).
        """
        fid, nmap = ((self.search_flow_id, self._search_nodes) if self.search_flow_id
                     else (self.query_flow_id, self._query_nodes))
        result = await self._run_query_component(query, "FlexibleHybridSearch", fid, nmap)
        data = self.extract_data(result, ("results", "count")) or {}
        results = data.get("results") or []
        for r in results:
            if isinstance(r, dict) and not r.get("metadata"):
                r["metadata"] = {"source": r.get("source"), "file_name": r.get("file_name"),
                                 "file_type": r.get("file_type"), "score": r.get("score")}
        return results

    async def run_aiquery_flow(self, query: str) -> Dict[str, Any]:
        """AI Q&A via the flow — returns {answer, sources}.

        Uses the dedicated AI-query-only flow when available (so no Hybrid Search branch runs).
        """
        fid, nmap = ((self.aiquery_flow_id, self._aiquery_nodes) if self.aiquery_flow_id
                     else (self.query_flow_id, self._query_nodes))
        result = await self._run_query_component(query, "FlexibleAIQuery", fid, nmap)
        # Match the component's Data payload ({answer:str, sources:[...], query}), NOT langflow's
        # output wrapper (which also has an "answer" key but maps it to a {repr, raw, type} dict).
        data = self.extract_data(result, ("answer", "sources")) or {}
        answer = data.get("answer", "")
        if isinstance(answer, dict):  # defensive: unwrap if we still landed on a wrapper
            answer = answer.get("raw") or answer.get("text") or ""
        return {"answer": answer if isinstance(answer, str) else str(answer),
                "sources": data.get("sources") or []}

    @staticmethod
    def extract_data(run_result: Dict[str, Any], marker_keys) -> Optional[Dict[str, Any]]:
        """Recursively find the first dict in a run result containing all marker_keys.

        Component Data outputs are nested under outputs[].outputs[].results.<name>.data in a
        version-dependent way; searching by marker keys is robust to those shape differences.
        """
        want = set(marker_keys)

        def walk(o):
            if isinstance(o, dict):
                if want.issubset(o.keys()):
                    return o
                for v in o.values():
                    r = walk(v)
                    if r is not None:
                        return r
            elif isinstance(o, list):
                for v in o:
                    r = walk(v)
                    if r is not None:
                        return r
            return None

        return walk(run_result)

    @staticmethod
    def extract_message(run_result: Dict[str, Any]) -> str:
        """Pull the chat/text message out of a Langflow run response (best-effort).

        In debug output mode (used for incremental sync) the run result also contains the
        echoed ChatInput payload — our run_cfg JSON, which embeds source_config CREDENTIALS.
        We must NOT surface that to the caller/UI, so skip any message that looks like the
        input echo, and never fall back to dumping the raw run_result.
        """
        def _is_input_echo(s: str) -> bool:
            t = (s or "").lstrip()
            # run_cfg is a JSON object that always carries the "source_config" key
            return t.startswith("{") and '"source_config"' in t

        try:
            outputs = run_result.get("outputs", [])
            for o in outputs:
                for inner in o.get("outputs", []):
                    res = inner.get("results", {})
                    msg = res.get("message") or res.get("text")
                    if isinstance(msg, dict):
                        text = msg.get("text") or msg.get("message") or str(msg)
                        if text and not _is_input_echo(text):
                            return text
                        continue
                    if isinstance(msg, str):
                        if msg and not _is_input_echo(msg):
                            return msg
                        continue
                    # some shapes: inner["messages"][0]["message"]
                    for m in inner.get("messages", []) or []:
                        mm = m.get("message")
                        if mm and not _is_input_echo(mm):
                            return mm
        except Exception:
            pass
        # Safe fallback — do NOT dump run_result; it embeds the echoed source_config credentials.
        return "Ingestion flow completed."

    async def list_flows(self) -> List[Dict[str, Any]]:
        return (await self._request("GET", "/api/v1/flows/")).json()
