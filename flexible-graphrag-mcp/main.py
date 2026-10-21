#!/usr/bin/env python3
"""
MCP Server for Flexible GraphRAG
Uses the flexible-graphrag backend through HTTP API calls
"""

import asyncio
import os
import sys
import httpx
from typing import List, Dict, Any, Optional, Union
from fastmcp import FastMCP

# Windows encoding is handled by environment variables in Claude Desktop config:
# PYTHONIOENCODING=utf-8 and PYTHONLEGACYWINDOWSSTDIO=1

# Add parent directory to path to import from flexible-graphrag
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'flexible-graphrag'))

# Default backend URL
BACKEND_URL = os.getenv("FLEXIBLE_GRAPHRAG_URL", "http://localhost:8000")

def _build_transport_auth():
    """Optionally secure the MCP transport itself with OAuth2/JWT bearer validation.

    Enabled by env MCP_TRANSPORT_AUTH=true (applies to HTTP/SSE transports only; stdio ignores
    it). Validates RS256 bearer tokens from an OIDC IdP (e.g. Keycloak) via its JWKS; a client
    (including MCP Inspector) must send `Authorization: Bearer <token>`. This gates who may call
    the flexible-graphrag MCP server — separate from the data-source credentials passed through in
    alfresco_config/nuxeo_config. Defaults target the local Keycloak realm.
    """
    if os.getenv("MCP_TRANSPORT_AUTH", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    # FastMCP 3.x: JWT transport auth uses JWTVerifier (v2 BearerAuthProvider was removed).
    from fastmcp.server.auth.providers.jwt import JWTVerifier as _Verifier
    jwks_uri = os.getenv(
        "MCP_AUTH_JWKS_URI",
        "http://host.docker.internal:8091/realms/alfresco/protocol/openid-connect/certs",
    )
    # The MCP SDK enforces HTTPS for the issuer URL (localhost/127.0.0.1 excepted); a local http
    # Keycloak issuer is rejected. Leave issuer unset by default (the JWKS signature check still
    # gates access); set MCP_AUTH_ISSUER with an HTTPS IdP for strict issuer validation.
    issuer = os.getenv("MCP_AUTH_ISSUER") or None
    audience = os.getenv("MCP_AUTH_AUDIENCE") or None
    print(f"MCP transport auth ENABLED (jwks_uri={jwks_uri}, issuer={issuer}, audience={audience})", file=sys.stderr)
    return _Verifier(jwks_uri=jwks_uri, issuer=issuer, audience=audience)


# Initialize MCP server (optionally with transport-level OAuth2/JWT bearer auth)
mcp = FastMCP("flexible-graphrag-mcp", auth=_build_transport_auth())

# httpx defaults to a 5s timeout on every phase. Several backend operations exceed that —
# notably the first query/search after a fresh backend start, which lazily reconnects to the
# vector/graph/search indexes (~13s observed). Use a generous explicit timeout so cold-start
# calls don't fail as bare timeouts (issue #20). Override via FLEXIBLE_GRAPHRAG_TIMEOUT.
_API_TIMEOUT = float(os.getenv("FLEXIBLE_GRAPHRAG_TIMEOUT", "120.0"))


def _fmt_error(e: Exception) -> str:
    """Format an exception including its type name.

    Some exceptions (e.g. httpx.ReadTimeout/ConnectTimeout) stringify to '', which
    surfaces to the MCP client as a mysterious empty-string failure. Always include the
    type so a bare timeout is identifiable (issue #20).
    """
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


# Permission filtering, from the MCP side -- three levels:
#   1. search_documents / query_documents with no credentials: no filtering. Needs the backend to
#      trust this server: FLEXIBLE_GRAPHRAG_TRUSTED_KEY here = TRUSTED_CLIENT_KEY on the backend
#      (otherwise the backend's own SOURCE_QUERY_AUTH applies and may leave sources out).
#   2. with credentials (source_auth / alfresco_ticket, e.g. from sign_in): those sources are
#      filtered to what that user may read; the others stay unfiltered.
#   3. MCP_BROWSER_SIGN_IN=true: also the start_sign_in / finish_sign_in tools, for Microsoft 365,
#      Box, Google and Azure Storage sign-in in the user's browser (off by default).
TRUSTED_KEY = (os.getenv("FLEXIBLE_GRAPHRAG_TRUSTED_KEY") or "").strip()
BROWSER_SIGN_IN = os.getenv("MCP_BROWSER_SIGN_IN", "false").strip().lower() in ("1", "true", "yes", "on")


def _ticket_headers(alfresco_ticket: Optional[str]) -> Optional[Dict[str, str]]:
    """The question's headers: the asking user's Alfresco ticket (read by the backend's permission
    filter), and this server's trusted-client key (level 1: no credentials, no filtering)."""
    headers: Dict[str, str] = {}
    if alfresco_ticket and alfresco_ticket.strip():
        headers["X-Alfresco-Ticket"] = alfresco_ticket.strip()
    if TRUSTED_KEY:
        headers["X-Trusted-Client-Key"] = TRUSTED_KEY
    return headers or None


def _parse_obj(value: Optional[Union[str, dict]], name: str) -> Optional[dict]:
    """An object argument (dict, or a JSON string from LLM clients); raises ValueError if invalid."""
    if not value:
        return None
    if isinstance(value, dict):
        return value
    import json
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return parsed


async def make_api_call(method: str, endpoint: str, data: Optional[Dict] = None,
                        headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Make HTTP API call to the flexible-graphrag backend"""
    async with httpx.AsyncClient(timeout=httpx.Timeout(_API_TIMEOUT)) as client:
        url = f"{BACKEND_URL}{endpoint}"

        if method.upper() == "GET":
            response = await client.get(url, headers=headers)
        elif method.upper() == "POST":
            response = await client.post(url, json=data or {}, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if response.is_error:
            # Pass on the backend's reason (FastAPI "detail"), not just the status line --
            # e.g. a refused ticket (401) or a scope that needs the incremental registry (400)
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = response.text[:300]
            raise httpx.HTTPStatusError(f"{response.status_code} from {endpoint}: {detail}",
                                        request=response.request, response=response)
        return response.json()

@mcp.tool()
async def get_system_status() -> Dict[str, Any]:
    """Get the current status of the flexible-graphrag system"""
    try:
        result = await make_api_call("GET", "/api/status")
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}

@mcp.tool()
async def ingest_documents(
    data_source: str = "filesystem", 
    paths: Optional[Union[str, List[str]]] = None,  # List[str], not bare list: typed array items (MCP schema portability)
    enable_sync: Optional[bool] = False,
    skip_graph: Optional[bool] = False,
    cmis_config: Optional[Union[str, dict]] = None,
    alfresco_config: Optional[Union[str, dict]] = None,
    nuxeo_config: Optional[Union[str, dict]] = None,
    web_config: Optional[Union[str, dict]] = None,
    wikipedia_config: Optional[Union[str, dict]] = None,
    youtube_config: Optional[Union[str, dict]] = None,
    s3_config: Optional[Union[str, dict]] = None,
    gcs_config: Optional[Union[str, dict]] = None,
    azure_blob_config: Optional[Union[str, dict]] = None,
    onedrive_config: Optional[Union[str, dict]] = None,
    sharepoint_config: Optional[Union[str, dict]] = None,
    box_config: Optional[Union[str, dict]] = None,
    google_drive_config: Optional[Union[str, dict]] = None,
    alfresco_ticket: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingest documents from filesystem, web, or cloud sources.

    Args:
        data_source: Source type (filesystem, cmis, alfresco, nuxeo, web, wikipedia, youtube, s3, gcs, azure_blob, etc.)
        paths: File path(s) as JSON array for filesystem source
        enable_sync: Enable automatic change detection and incremental updates
        skip_graph: Skip knowledge graph extraction (faster, vector+search only)
        *_config: JSON configuration string for the selected data source. Required for
            data_source="alfresco": alfresco_config with url, path and credentials
            (username/password, or alfresco_ticket below); the server's own Alfresco settings
            are never used for an ingest.
        alfresco_ticket: For data_source="alfresco": an Alfresco login ticket (TICKET_...) the
            caller already holds, used as the whole credential -- no username/password needed.
            alfresco_config still gives url and path, e.g. {"url": "http://localhost:8080/alfresco",
            "path": "/Shared/GraphRAG"}. A ticket expires, so it cannot be combined with enable_sync
            (auto-sync needs a stored username/password).
    """
    try:
        import json
        
        request_data = {"data_source": data_source}
        
        # Add skip_graph flag if set
        if skip_graph:
            request_data["skip_graph"] = skip_graph
        
        # Add enable_sync flag if set
        if enable_sync:
            request_data["enable_sync"] = enable_sync
        
        # Add paths if provided
        if isinstance(paths, list):
            # Structured MCP clients (e.g. MCP Inspector) send an actual array
            request_data["paths"] = paths
        elif paths:
            # Handle multiple formats:
            # 1. JSON array string: "[\"path1\", \"path2\"]"
            # 2. Comma-separated string: "path1,path2"
            # 3. Single path string: "path"
            try:
                # Try to parse as JSON array first
                parsed_paths = json.loads(paths)
                if isinstance(parsed_paths, list):
                    request_data["paths"] = parsed_paths
                    import sys
                    sys.stderr.write(f"DEBUG: Parsed JSON array: {request_data['paths']}\n")
                    sys.stderr.flush()
                else:
                    request_data["paths"] = [str(parsed_paths)]
                    import sys
                    sys.stderr.write(f"DEBUG: Wrapped single JSON value: {request_data['paths']}\n")
                    sys.stderr.flush()
            except json.JSONDecodeError:
                # If JSON parsing fails, check for comma-separated paths
                if ',' in paths:
                    # Split by comma and strip whitespace
                    request_data["paths"] = [p.strip() for p in paths.split(',') if p.strip()]
                    import sys
                    sys.stderr.write(f"DEBUG: Split comma-separated: {request_data['paths']}\n")
                    sys.stderr.flush()
                else:
                    # Single path
                    request_data["paths"] = [paths]
                    import sys
                    sys.stderr.write(f"DEBUG: Single path: {request_data['paths']}\n")
                    sys.stderr.flush()
        
        # Add data source configurations if provided (parse JSON strings)
        config_mappings = {
            "cmis_config": cmis_config,
            "alfresco_config": alfresco_config,
            "nuxeo_config": nuxeo_config,
            "web_config": web_config,
            "wikipedia_config": wikipedia_config,
            "youtube_config": youtube_config,
            "s3_config": s3_config,
            "gcs_config": gcs_config,
            "azure_blob_config": azure_blob_config,
            "onedrive_config": onedrive_config,
            "sharepoint_config": sharepoint_config,
            "box_config": box_config,
            "google_drive_config": google_drive_config
        }
        
        for config_key, config_value in config_mappings.items():
            if config_value:
                # Accept either a dict (structured MCP clients like MCP Inspector send an object)
                # or a JSON string (LLM clients typically send a stringified object).
                if isinstance(config_value, dict):
                    request_data[config_key] = config_value
                else:
                    try:
                        request_data[config_key] = json.loads(config_value)
                    except json.JSONDecodeError as e:
                        return {
                            "processing_id": "error",
                            "status": "failed",
                            "message": f"Invalid JSON in {config_key}: {str(e)}",
                            "progress": 0
                        }

        if alfresco_ticket and alfresco_ticket.strip():
            # The caller's ticket replaces username/password for this one ingest
            alf = request_data.setdefault("alfresco_config", {})
            alf["ticket"] = alfresco_ticket.strip()
            if not alf.get("username"):
                alf["auth_method"] = "ticket"

        result = await make_api_call("POST", "/api/ingest", request_data)
        return result  # Return the async processing response directly
    except Exception as e:
        return {
            "processing_id": "error", 
            "status": "failed", 
            "message": f"Failed to start document processing: {_fmt_error(e)}",
            "progress": 0
        }

async def _ask(endpoint: str, query: str, top_k: int, alfresco_ticket, source_auth, scope,
               sources=None) -> Dict[str, Any]:
    """search_documents / query_documents: the question plus who is asking and where."""
    try:
        request_data = {"query": query, "top_k": top_k}
        if scope:
            request_data["scope"] = _parse_obj(scope, "scope")
        if sources:
            parsed = sources
            if isinstance(sources, str) and sources.strip().startswith(("[", "{")):
                import json
                parsed = json.loads(sources)  # a JSON list (or one object) from an LLM client
            if isinstance(parsed, str):
                parsed = [x.strip() for x in parsed.split(",") if x.strip()]
            if isinstance(parsed, dict):
                parsed = [parsed]
            request_data["sources"] = [x if isinstance(x, dict) else {"source": x} for x in parsed]
        if source_auth:
            request_data["source_auth"] = _parse_obj(source_auth, "source_auth")
        result = await make_api_call("POST", endpoint, request_data, headers=_ticket_headers(alfresco_ticket))
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}


@mcp.tool()
async def get_auth_requirements() -> Dict[str, Any]:
    """
    Which sign-ins the stored content needs before search_documents / query_documents.

    Returns {"required": bool, "providers": [{"source": "alfresco" | "nuxeo" | "cmis", "url": ...,
    "methods": [...], "documents": n, "required": bool}]}, one provider per server. An empty
    providers list means no sign-in is needed. Documents of a provider whose required is true are
    only used if the call passes that user's identity for that server (alfresco_ticket or
    source_auth); ask the user for it rather than guessing.
    """
    try:
        return {"success": True, "data": await make_api_call("GET", "/api/auth/requirements")}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}


@mcp.tool()
async def list_sources() -> Dict[str, Any]:
    """
    The sources that have documents in the stores, for search_documents / query_documents'
    sources argument: [{"source", "label", "url", "documents", "login_gated"}], one per data source
    type and server. login_gated sources (Alfresco, Nuxeo, CMIS) answer only for a caller that
    passes its identity there (source_auth). available is false without the incremental registry.
    """
    try:
        return {"success": True, "data": await make_api_call("GET", "/api/sources/available")}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}


@mcp.tool()
async def sign_in(source: str, username: str, password: str, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Sign in to a repository for search_documents / query_documents (and ingest).

    Args:
        source: "alfresco", "nuxeo", "cmis" or "s3"
        username: The user's name on that repository (s3: their IAM access key ID)
        password: Their password (s3: their secret access key) -- used once here, never stored
        url: The server (a CMIS service URL for cmis); default: the backend's configured one

    Returns the credential to pass back, ready to put in source_auth[source]:
    alfresco {"ticket", "user_id", "url"}; nuxeo {"token", "user_id", "url"};
    cmis {"auth_method": "ticket"|"token", "ticket"|"token", "user_id", "vendor", "url"}
    (CMIS sign-in supports Alfresco and Nuxeo servers); s3 {"token", "user_id", "expires_at", "url"}
    (temporary STS session credentials, packed; needs S3_AUTH_ENABLED on the backend).
    """
    if source not in ("alfresco", "nuxeo", "cmis", "s3"):
        return {"success": False, "error": "source must be alfresco, nuxeo, cmis or s3 (microsoft, box, "
                                            "google and azure sign in in a browser: start_sign_in, when the "
                                            "server runs with MCP_BROWSER_SIGN_IN=true)"}
    try:
        body = {"username": username, "password": password}
        if url:
            body["url"] = url
        data = await make_api_call("POST", f"/api/auth/{source}/login", body)
        data.pop("password", None)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}


_BROWSER_SIGN_INS = ("microsoft", "box", "google", "azure")
_handoff_keys: Dict[str, tuple] = {}  # handoff_id -> (source, poll key): kept here, never shown to the model


async def start_sign_in(source: str) -> Dict[str, Any]:
    """
    Start a sign-in that happens in the user's browser: "microsoft" (SharePoint + OneDrive),
    "box", "google" (Google Drive + Cloud Storage) or "azure" (Azure Blob). For username /
    password sources (alfresco, nuxeo, cmis) and s3, use sign_in instead.

    Returns {sign_in_url, handoff_id, expires_in} (plus user_code when the backend asks users to
    confirm a code). Show the user the link (and the code, if any) and ask them to open it in
    their browser and sign in. When they say they have, call finish_sign_in(handoff_id). The link works once and
    expires after expires_in seconds.
    """
    if source not in _BROWSER_SIGN_INS:
        return {"success": False, "error": f"source must be one of {', '.join(_BROWSER_SIGN_INS)} "
                                            "(use sign_in for alfresco, nuxeo, cmis and s3)"}
    try:
        data = await make_api_call("POST", f"/api/auth/{source}/handoff")
        _handoff_keys[data["handoff_id"]] = (source, data.pop("poll_key"))
        label = data.get("label", source)
        steps = (f"Open {data['sign_in_url']} in your browser, check it shows the code {data['user_code']}, "
                 f"then continue and sign in to {label}." if data.get("user_code")
                 else f"Open {data['sign_in_url']} in your browser and sign in to {label}.")
        return {"success": True, "data": {**data, "instructions": steps}}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}


async def finish_sign_in(handoff_id: str, wait_seconds: int = 0) -> Dict[str, Any]:
    """
    Collect a browser sign-in started with start_sign_in. Call it after the user says they have
    signed in: by default it checks once and returns at once (no waiting); wait_seconds (max 300)
    waits that long for the user to finish. Returns the credential, ready to put in
    source_auth[source]: {"source", "credential": {"access_token", "url"}, "user_id",
    "expires_at"} -- pass it as source_auth={source: credential} to search_documents /
    query_documents. While the user is still signing in, returns {"pending": true}: ask them to
    finish, then call finish_sign_in again.
    """
    import time as _time
    entry = _handoff_keys.get(handoff_id)
    if entry is None:
        return {"success": False, "error": "unknown sign-in: start it with start_sign_in"}
    source, poll_key = entry
    deadline = _time.monotonic() + max(0, min(int(wait_seconds or 0), 300))
    try:
        while True:
            data = await make_api_call("POST", f"/api/auth/{source}/handoff/result",
                                       {"handoff_id": handoff_id, "poll_key": poll_key})
            if not data.get("pending"):
                _handoff_keys.pop(handoff_id, None)
                return {"success": True, "data": {
                    "source": source, "user_id": data.get("user_id"), "expires_at": data.get("expires_at"),
                    "credential": {"access_token": data["access_token"], "url": data.get("url")}}}
            if _time.monotonic() >= deadline:
                return {"success": True, "data": {"pending": True, "handoff_id": handoff_id,
                                                  "message": "The user has not finished signing in yet."}}
            await asyncio.sleep(2)
    except Exception as e:
        _handoff_keys.pop(handoff_id, None)
        return {"success": False, "error": _fmt_error(e)}


if BROWSER_SIGN_IN:  # level 3 only: otherwise these tools are not offered
    start_sign_in = mcp.tool()(start_sign_in)
    finish_sign_in = mcp.tool()(finish_sign_in)


@mcp.tool()
async def search_documents(query: str, top_k: int = 10, alfresco_ticket: Optional[str] = None,
                           source_auth: Optional[Union[str, dict]] = None,
                           scope: Optional[Union[str, dict]] = None,
                           sources: Optional[Union[str, List[Union[str, Dict[str, str]]]]] = None) -> Dict[str, Any]:
    """
    Search documents using hybrid search

    Repository documents (Alfresco, Nuxeo, and CMIS on Alfresco/Nuxeo servers) are only searched
    when the caller says who they are on that server (alfresco_ticket or source_auth); results
    then include only the documents that user may read, checked against each repository at query
    time. Documents from other sources are always searched.

    Args:
        query: Search query string
        top_k: Number of results to return
        alfresco_ticket: The asking user's Alfresco login ticket (TICKET_...)
        source_auth: The asking user's identities per data source -- one object or a list (one
            per server) for each of "alfresco", "nuxeo" and "cmis", e.g.
            {"alfresco": {"ticket": "TICKET_..."}, "nuxeo": {"token": "..."}},
            {"alfresco": [{"url": "http://a:8080", "ticket": "..."}, {"url": "http://b:8080", "ticket": "..."}]},
            {"cmis": {"url": "<CMIS service URL>", "auth_method": "ticket", "ticket": "TICKET_..."}},
            {"microsoft": {"access_token": "<delegated Graph token>"}} (SharePoint + OneDrive),
            {"box" | "google" | "azure": {"access_token": "..."}} (popup sign-ins in the UIs),
            {"s3": {"token": "<from sign_in source=s3>"}} (Amazon S3),
            {"alfresco": {"auth_method": "basic", "username": "...", "password": "..."}} or
            {"alfresco": {"auth_method": "oauth2", "oauth2": {"access_token": "..."}}}.
            "url" names the server (default: the backend's configured one for that source).
            sign_in turns a username/password into the ticket/token; get_auth_requirements
            lists the servers the stored content needs.
        scope: Limit to one repository document or folder, as a JSON object:
            {"data_source": "alfresco", "path": "/Shared/GraphRAG", "is_folder": true}
            or {"data_source": "alfresco", "node_id": "<node id>"}. A folder covers everything
            below it. Optional "url" picks one repository; "name" is used in messages.
        sources: Answer only from these sources (list_sources names them): "nuxeo,sharepoint",
            ["alfresco", "filesystem"], or [{"source": "alfresco", "url": "http://a:8080"}] for one
            server. Omitted = all sources.
    """
    return await _ask("/api/search", query, top_k, alfresco_ticket, source_auth, scope, sources)


@mcp.tool()
async def query_documents(query: str, top_k: int = 10, alfresco_ticket: Optional[str] = None,
                          source_auth: Optional[Union[str, dict]] = None,
                          scope: Optional[Union[str, dict]] = None,
                          sources: Optional[Union[str, List[Union[str, Dict[str, str]]]]] = None) -> Dict[str, Any]:
    """
    Query documents with AI-generated answers

    Repository documents (Alfresco, Nuxeo, and CMIS on Alfresco/Nuxeo servers) are only used
    when the caller says who they are on that server (alfresco_ticket or source_auth); the answer
    then draws only on the documents that user may read, checked against each repository at query
    time. Documents from other sources are always used.

    Args:
        query: Question to ask
        top_k: Number of source documents to consider
        alfresco_ticket: The asking user's Alfresco login ticket (TICKET_...)
        source_auth: The asking user's identities per data source -- one object or a list (one
            per server) for each of "alfresco", "nuxeo" and "cmis", e.g.
            {"alfresco": {"ticket": "TICKET_..."}, "nuxeo": {"token": "..."}},
            {"alfresco": [{"url": "http://a:8080", "ticket": "..."}, {"url": "http://b:8080", "ticket": "..."}]},
            {"cmis": {"url": "<CMIS service URL>", "auth_method": "ticket", "ticket": "TICKET_..."}},
            {"microsoft": {"access_token": "<delegated Graph token>"}} (SharePoint + OneDrive),
            {"box" | "google" | "azure": {"access_token": "..."}} (popup sign-ins in the UIs),
            {"s3": {"token": "<from sign_in source=s3>"}} (Amazon S3),
            {"alfresco": {"auth_method": "basic", "username": "...", "password": "..."}} or
            {"alfresco": {"auth_method": "oauth2", "oauth2": {"access_token": "..."}}}.
            "url" names the server (default: the backend's configured one for that source).
            sign_in turns a username/password into the ticket/token; get_auth_requirements
            lists the servers the stored content needs.
        scope: Limit to one repository document or folder, as a JSON object:
            {"data_source": "alfresco", "path": "/Shared/GraphRAG", "is_folder": true}
            or {"data_source": "alfresco", "node_id": "<node id>"}. A folder covers everything
            below it. Optional "url" picks one repository; "name" is used in messages.
        sources: Answer only from these sources (list_sources names them): "nuxeo,sharepoint",
            ["alfresco", "filesystem"], or [{"source": "alfresco", "url": "http://a:8080"}] for one
            server. Omitted = all sources.
    """
    return await _ask("/api/query", query, top_k, alfresco_ticket, source_auth, scope, sources)

@mcp.tool()
async def test_with_sample(skip_graph: bool = False) -> Dict[str, Any]:
    """Test the system with sample text for quick verification"""
    try:
        request_data = {}
        if skip_graph:
            request_data["skip_graph"] = skip_graph
        result = await make_api_call("POST", "/api/test-sample", request_data or None)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}

@mcp.tool()
async def ingest_text(content: str, source_name: str = "mcp-input", skip_graph: bool = False) -> Dict[str, Any]:
    """
    Ingest raw text content into the knowledge graph
    
    Args:
        content: Text content to ingest
        source_name: Name/identifier for this text source
        skip_graph: Skip knowledge graph extraction (faster, vector+search only)
    """
    try:
        request_data = {"content": content, "source_name": source_name}
        if skip_graph:
            request_data["skip_graph"] = skip_graph
        result = await make_api_call("POST", "/api/ingest-text", request_data)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}

@mcp.tool()
async def check_processing_status(processing_id: str) -> Dict[str, Any]:
    """
    Check the status of an async processing operation
    
    Args:
        processing_id: The processing ID returned from ingest_text
    """
    try:
        result = await make_api_call("GET", f"/api/processing-status/{processing_id}")
        return {"success": True, "processing": result}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}

@mcp.tool()
async def get_python_info() -> Dict[str, Any]:
    """Get information about the Python environment of the backend"""
    try:
        result = await make_api_call("GET", "/api/python-info")
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}

@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if the backend is healthy and responsive"""
    try:
        result = await make_api_call("GET", "/api/health")
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": _fmt_error(e)}

def main():
    """Run the MCP server"""
    import sys
    
    # Check for HTTP mode via command line arguments
    http_mode = "--http" in sys.argv or "--serve" in sys.argv
    
    # Check for --transport http pattern
    if "--transport" in sys.argv:
        try:
            transport_idx = sys.argv.index("--transport") + 1
            if transport_idx < len(sys.argv) and sys.argv[transport_idx].lower() == "http":
                http_mode = True
        except (IndexError, ValueError):
            pass
    port = 3001  # Default MCP Inspector port
    host = "localhost"  # Default host
    
    # Parse port argument
    if "--port" in sys.argv:
        try:
            port_idx = sys.argv.index("--port") + 1
            port = int(sys.argv[port_idx])
        except (IndexError, ValueError):
            port = 3001
    
    # Parse host argument
    if "--host" in sys.argv:
        try:
            host_idx = sys.argv.index("--host") + 1
            host = sys.argv[host_idx]
        except IndexError:
            host = "localhost"
    
    # Log to stderr instead of stdout to avoid interfering with MCP protocol
    sys.stderr.write("🚀 Starting Flexible GraphRAG MCP Server\n")
    sys.stderr.write(f"📡 Backend URL: {BACKEND_URL}\n")
    
    if http_mode:
        sys.stderr.write(f"🌐 Running in HTTP mode on {host}:{port}\n")
        sys.stderr.write("🔍 Suitable for MCP Inspector debugging\n")
    else:
        sys.stderr.write("📱 Running in stdio mode for Claude Desktop\n")
    
    sys.stderr.write("🛠️  Available tools:\n")
    sys.stderr.write("   • get_system_status\n")
    sys.stderr.write("   • ingest_documents (supports paths, skip_graph, enable_sync, nodeDetails, all 14 data sources)\n")
    sys.stderr.write("   • get_auth_requirements\n")
    sys.stderr.write("   • sign_in\n")
    sys.stderr.write("   • list_sources\n")
    sys.stderr.write("   • search_documents\n")
    sys.stderr.write("   • query_documents\n")
    sys.stderr.write("   • test_with_sample\n")
    sys.stderr.write("   • ingest_text\n")
    sys.stderr.write("   • check_processing_status\n")
    sys.stderr.write("   • get_python_info\n")
    sys.stderr.write("   • health_check\n")
    sys.stderr.flush()
    
    try:
        if http_mode:
            asyncio.run(mcp.run_http_async(host=host, port=port))
        else:
            # Do NOT apply nest_asyncio in either mode — it patches asyncio.run() in a way
            # that breaks anyio's task-state weakref lookup on Python 3.14 (host_task
            # becomes None, triggering "cannot create weak reference to 'NoneType'").
            # All tools are async def using await, so nest_asyncio is not needed.
            asyncio.run(mcp.run_async())
    except KeyboardInterrupt:
        # Ctrl-C: the server has already run its async shutdown ("Application shutdown
        # complete"); on Python 3.14 asyncio.run() then re-raises KeyboardInterrupt, which
        # would print a bare CancelledError/KeyboardInterrupt traceback. Exit quietly instead.
        sys.stderr.write("\nMCP server stopped.\n")

if __name__ == "__main__":
    main()