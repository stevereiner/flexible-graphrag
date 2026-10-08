"""
Nuxeo data source for Flexible GraphRAG.

Uses the official Nuxeo Python client (``nuxeo`` on PyPI). Supports basic
(username/password), token, and OAuth2 (Bearer) authentication. Mirrors the
Alfresco source: enumerate documents under a path or by node id(s), download
each file's main blob, and hand it to the shared document processor.
"""

from typing import List, Dict, Any, Optional
import logging
import time

from llama_index.core import Document

from .base import BaseDataSource
from .filesystem import is_docling_supported

logger = logging.getLogger(__name__)


def _ensure_nuxeo_jwt_compat() -> None:
    """Let ``nuxeo.auth`` import when PyJWT (not the GehirnInc ``jwt`` package) owns the ``jwt`` module.

    ``nuxeo/auth/oauth2.py`` does ``from jwt import JWT, jwk_from_dict`` and
    ``from jwt.exceptions import JWTDecodeError`` at import time (the GehirnInc ``jwt`` API), and
    ``nuxeo/auth/__init__`` imports that module unconditionally. In a venv where **PyJWT** is installed
    instead (e.g. the Langflow venv — Langflow requires PyJWT, which owns the same ``jwt`` module and
    can't coexist with GehirnInc ``jwt``), those names are missing, so ``import nuxeo.auth`` fails and
    the Nuxeo source is disabled entirely (even for basic/token auth).

    Graft stubs onto the ``jwt`` module so ``nuxeo.auth`` loads. In flexible-graphrag's usage **all three
    auth methods (basic / token / oauth2) work in flow mode** — the OAuth2 path uses a pre-obtained Bearer
    token (minted separately by ``scripts/nuxeo``), so the runtime source only attaches the header and never
    decodes a JWT. The stubs raise a clear error *only if* nuxeo actually decodes a JWT client-side (its
    auth-code exchange / id_token path), which the ingest path never hits. This is a **no-op** when the real
    GehirnInc ``jwt`` is present (the backend venv), and it only **adds** symbols — PyJWT's own
    ``encode``/``decode``/``InvalidTokenError`` are never touched, so Langflow is unaffected.
    """
    try:
        import jwt as _jwt
    except ImportError:
        return  # no jwt module at all — the try/except below handles the missing client
    if hasattr(_jwt, "JWT") and hasattr(_jwt, "jwk_from_dict"):
        return  # real GehirnInc jwt present — nothing to do

    _msg = ("This nuxeo path needs the real `jwt` (GehirnInc) package to decode a JWT client-side "
            "(auth-code exchange / id_token) — unavailable here because PyJWT owns the `jwt` module (e.g. "
            "the Langflow venv). Mint the OAuth2 token via scripts/nuxeo, or run the source in the direct "
            "backend path. (Basic/token and pre-obtained-Bearer OAuth2 ingest do NOT hit this.)")

    # PyJWT can do everything nuxeo asks of the GehirnInc package — it is only
    # the spelling that differs.  ``nuxeo/auth/oauth2.py`` uses exactly three
    # symbols, in exactly one method (``validate_access_token``):
    #
    #     jwk_from_dict(key_dict)                     -> PyJWK.from_dict()
    #     JWT().decode(token, key, do_time_check=...) -> jwt.decode()
    #     except JWTDecodeError                       -> jwt.exceptions.PyJWTError
    #
    # So rather than stubbing them out to raise, implement them on top of PyJWT.
    # That makes client-side token validation genuinely work in a PyJWT
    # environment, which is every environment we ship: the GehirnInc package is
    # deliberately NOT a dependency (it claims the same ``jwt`` module name and
    # would break python-arango / langchain-arangodb, authlib and Langflow).

    def _jwk_from_dict(key_dict, *_a, **_k):
        """GehirnInc ``jwk_from_dict`` -> PyJWK."""
        return _jwt.PyJWK.from_dict(key_dict)

    class _JWTCompat:
        """GehirnInc ``JWT`` API implemented with PyJWT."""

        @staticmethod
        def _split(key):
            """Accept a PyJWK or a raw key; return ``(key_material, algorithms)``."""
            material = getattr(key, "key", key)
            alg = getattr(key, "algorithm_name", None)
            return material, ([alg] if alg else None)

        # Signatures mirror GehirnInc's jwt.JWT exactly (jwt/jwt.py), so a caller
        # written against that package behaves identically here.
        def decode(
            self,
            message,
            key=None,
            do_verify=True,
            algorithms=None,
            do_time_check=True,
        ):
            material, key_algs = self._split(key)
            algs = list(algorithms) if algorithms else key_algs
            return _jwt.decode(
                message,
                material,
                algorithms=algs or ["RS256"],
                options={
                    "verify_signature": bool(do_verify),
                    "verify_exp": bool(do_time_check),
                },
            )

        def encode(self, payload, key=None, alg="HS256", optional_headers=None):
            material, _ = self._split(key)
            return _jwt.encode(
                payload, material, algorithm=alg, headers=optional_headers or None
            )

    if not hasattr(_jwt, "JWT"):
        _jwt.JWT = _JWTCompat
    if not hasattr(_jwt, "jwk_from_dict"):
        _jwt.jwk_from_dict = _jwk_from_dict

    # nuxeo also does `from jwt.exceptions import JWTDecodeError`.  Alias it to
    # PyJWT's base error rather than inventing a new class: nuxeo catches
    # JWTDecodeError around the decode call, and PyJWT's failures
    # (InvalidSignatureError, ExpiredSignatureError, DecodeError, ...) all derive
    # from PyJWTError.  A fresh Exception subclass would catch none of them, so
    # a bad token would escape as an unhandled error instead of the OAuth2Error
    # nuxeo intends.
    try:
        import jwt.exceptions as _jwt_exc  # PyJWT ships this module
    except ImportError:
        import sys
        import types
        _jwt_exc = types.ModuleType("jwt.exceptions")
        sys.modules["jwt.exceptions"] = _jwt_exc
        _jwt.exceptions = _jwt_exc
    if not hasattr(_jwt_exc, "JWTDecodeError"):
        _jwt_exc.JWTDecodeError = getattr(_jwt_exc, "PyJWTError", Exception)

    logger.debug(
        "Applied Nuxeo jwt-compat shim (PyJWT backend): all three auth methods, "
        "including client-side access-token validation, are functional."
    )


_ensure_nuxeo_jwt_compat()

try:
    from nuxeo.client import Nuxeo
    from nuxeo.auth import BasicAuth, TokenAuth, OAuth2
except ImportError:
    Nuxeo = None
    BasicAuth = None
    TokenAuth = None
    OAuth2 = None
    logging.warning("nuxeo client not installed - install with `uv pip install \"nuxeo[oauth2]\"`")


# NXQL clauses shared by folder/path enumeration: live, non-version, non-proxy docs
_NXQL_FILTER = "ecm:isVersion = 0 AND ecm:isProxy = 0 AND ecm:isTrashed = 0"

# Page size used when paginating NXQL results
_PAGE_SIZE = 100

# Fallback extension by mime-type for Note documents (whose title may lack one)
_NOTE_MIME_EXT = {
    "text/plain": ".txt",
    "text/html": ".html",
    "text/xml": ".xml",
    "application/xml": ".xml",
    "text/x-web-markdown": ".md",
    "text/markdown": ".md",
}


class NuxeoSource(BaseDataSource):
    """Data source for Nuxeo repositories."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get("url", "")
        self.auth_method = (config.get("auth_method") or "basic").lower()

        # Basic auth
        self.username = config.get("username", "")
        self.password = config.get("password", "")

        # Token auth (X-Authentication-Token). If no token is supplied, it is fetched
        # from username/password on connect (like Alfresco ticket mode) — see _fetch_token_sync.
        self.token = config.get("token", "")
        self.verify_ssl = config.get("verify_ssl", True)
        self.timeout = config.get("timeout", 30)
        # Params for the token-acquisition endpoint (only used for the auto-fetch path)
        self.token_app_name = config.get("token_app_name", "flexible-graphrag")
        self.token_device_id = config.get("token_device_id", "flexible-graphrag")
        self.token_device_desc = config.get("token_device_description", "Flexible GraphRAG")
        self.token_permission = config.get("token_permission", "rw")

        # OAuth2 (Bearer). A token is normally obtained out-of-band (authorization
        # code + PKCE) and passed in here; the client auto-refreshes when possible.
        self.oauth2 = config.get("oauth2") or {}

        # Selection
        self.path = config.get("path", "/")
        self.node_details = config.get("nodeDetails", None)  # [{id,name,path,isFile,isFolder}]
        self.node_ids = config.get("nodeIds", None)  # list of Nuxeo document uids
        self.recursive = config.get("recursive", False)

        logger.info("=== INITIALIZING NUXEO SOURCE ===")
        logger.info(f"URL: {self.url}")
        logger.info(f"Auth method: {self.auth_method}")
        logger.info(f"Username: {self.username}")
        logger.info(f"Path: {self.path}")
        logger.info(f"Recursive: {self.recursive}")
        logger.info(f"Has nodeDetails: {self.node_details is not None}")
        logger.info(f"Has nodeIds: {self.node_ids is not None}")

        self.nuxeo = None
        self.nx_client = None

        if Nuxeo is None:
            logger.error("nuxeo client library not available - NuxeoSource cannot connect")
            return

        try:
            # host must end with a trailing slash; the client appends api/v1
            host = self.url.rstrip("/") + "/"
            logger.info(f"Creating Nuxeo client with host: {host}")
            self.nuxeo = Nuxeo(host=host)
            self.nx_client = self.nuxeo.client
            self.nx_client.auth = self._build_auth(host)
            # Request full document properties (populates file:content, dc:*, etc.)
            self.nx_client.set(schemas="*")
            logger.info("[OK] Nuxeo client initialized")
        except Exception as e:
            logger.error(f"[FAIL] Failed to initialize Nuxeo client: {str(e)}", exc_info=True)
            self.nuxeo = None
            self.nx_client = None
            # Keep the cause.  Construction stays non-fatal so validate_config()
            # can still report, but every later use must be able to say WHY —
            # otherwise the first dereference of self.nuxeo raises
            # "'NoneType' object has no attribute 'documents'", which hides a
            # perfectly clear message like "token auth needs either a token or
            # username+password".
            self._init_error = e

        logger.info("=== NUXEO SOURCE INITIALIZATION COMPLETE ===")

    def _build_auth(self, host: str):
        """Build the requests-compatible auth object for the configured method."""
        if self.auth_method == "oauth2":
            logger.info("Configuring OAuth2 (Bearer) auth")
            token = self._build_oauth_token()
            return OAuth2(
                host,
                client_id=self.oauth2.get("client_id"),
                client_secret=self.oauth2.get("client_secret"),
                token=token,
                authorization_endpoint=self.oauth2.get("authorization_endpoint"),
                token_endpoint=self.oauth2.get("token_endpoint"),
                redirect_uri=self.oauth2.get("redirect_uri"),
                openid_configuration_url=self.oauth2.get("openid_configuration_url"),
            )
        if self.auth_method == "token":
            # Use a supplied token directly (API/programmatic use); otherwise self-fetch
            # one from username/password, mirroring Alfresco ticket mode so the UI only
            # needs user/pw and the password isn't resent on every request.
            token = self.token or self._fetch_token_sync()
            logger.info("Configuring token auth (X-Authentication-Token)")
            return TokenAuth(token)
        # default: basic
        logger.info("Configuring basic auth")
        return BasicAuth(self.username, self.password)

    def _fetch_token_sync(self) -> str:
        """Acquire a reusable Nuxeo auth token from username/password.

        Calls ``GET <url>/authentication/token`` with Basic auth; the returned token is
        then used as X-Authentication-Token on every request (so the password isn't
        resent). This is the Nuxeo analog of Alfresco's ticket auth.
        """
        import httpx

        if not (self.username and self.password):
            raise RuntimeError(
                "Nuxeo token auth needs either a token or username+password to fetch one"
            )
        endpoint = self.url.rstrip("/") + "/authentication/token"
        params = {
            "applicationName": self.token_app_name,
            "deviceId": self.token_device_id,
            "deviceDescription": self.token_device_desc,
            "permission": self.token_permission,
        }
        logger.info(f"Fetching Nuxeo auth token from {endpoint} (user={self.username})")
        with httpx.Client(verify=self.verify_ssl, timeout=self.timeout) as client:
            resp = client.get(endpoint, params=params, auth=(self.username, self.password))
            resp.raise_for_status()
            token = (resp.text or "").strip()
        if not token:
            raise RuntimeError("Nuxeo token endpoint returned an empty token")
        logger.info("[OK] Acquired Nuxeo auth token from username/password")
        return token

    def _build_oauth_token(self) -> Optional[Dict[str, Any]]:
        """Assemble the OAuth2 token dict the client reuses, if an access token was supplied."""
        access_token = self.oauth2.get("access_token")
        if not access_token:
            # No pre-obtained token; the caller must drive the interactive flow first.
            return None
        token: Dict[str, Any] = {
            "access_token": access_token,
            "token_type": self.oauth2.get("token_type", "bearer"),
        }
        refresh_token = self.oauth2.get("refresh_token")
        if refresh_token:
            token["refresh_token"] = refresh_token
        # expires_at gates auto-refresh; derive it so token_is_expired() never KeyErrors
        expires_at = self.oauth2.get("expires_at")
        expires_in = self.oauth2.get("expires_in")
        if expires_at:
            token["expires_at"] = float(expires_at)
        elif expires_in:
            token["expires_at"] = time.time() + float(expires_in)
        else:
            token["expires_at"] = time.time() + 3600  # assume 1h if unspecified
        return token

    def validate_config(self) -> bool:
        """Validate the Nuxeo source configuration."""
        # Check the client library FIRST.  Without it self.nuxeo stays None and
        # every later call dies with "'NoneType' object has no attribute
        # 'documents'" — four cascading tracebacks that say nothing about the
        # actual problem, and that is the message the UI ends up showing.
        if Nuxeo is None:
            logger.error(
                "nuxeo client library not installed - run: uv pip install -e . "
                "(or: uv pip install \"nuxeo[oauth2]\")"
            )
            return False

        if not self.url:
            logger.error("No URL specified for Nuxeo source")
            return False

        if self.auth_method == "oauth2":
            if not self.oauth2.get("client_id"):
                logger.error("OAuth2 auth requires oauth2.client_id")
                return False
            if not (self.oauth2.get("access_token") or self.oauth2.get("client_secret")):
                logger.error("OAuth2 auth requires an access_token or client_secret")
                return False
        elif self.auth_method == "token":
            # Either a pre-obtained token (API use) OR username+password to fetch one (UI).
            if not self.token and not (self.username and self.password):
                logger.error("Token auth requires either a token or username+password")
                return False
        else:  # basic
            if not self.username:
                logger.error("No username specified for Nuxeo source")
                return False
            if not self.password:
                logger.error("No password specified for Nuxeo source")
                return False

        return True

    # ------------------------------------------------------------------ listing

    def _require_client(self) -> None:
        """Raise the ORIGINAL initialisation failure if the client never built.

        Every read path goes through ``list_files()``, so guarding here converts
        a downstream ``'NoneType' object has no attribute 'documents'`` into the
        actual reason — e.g. a missing token, bad credentials or an unreachable
        server.
        """
        if self.nuxeo is None or self.nx_client is None:
            cause = getattr(self, "_init_error", None)
            raise RuntimeError(
                f"Nuxeo client is not initialised ({self.auth_method} auth): "
                f"{cause if cause else 'check url, credentials and connectivity'}"
            )

    def list_files(self) -> List[dict]:
        """List all documents from the Nuxeo path or specific node id(s)."""
        self._require_client()
        try:
            if self.node_details:
                logger.info(f"=== NODEDETAILS MODE: {len(self.node_details)} nodes ===")
                documents = []
                for idx, node in enumerate(self.node_details, 1):
                    logger.info(f"--- Node {idx}/{len(self.node_details)}: {node.get('name')} "
                                f"(id={node.get('id')}, isFile={node.get('isFile')}, isFolder={node.get('isFolder')}) ---")
                    if node.get("isFile"):
                        file_doc = self._process_file_by_id(node["id"])
                        if file_doc:
                            documents.append(file_doc)
                    elif node.get("isFolder"):
                        documents.extend(self._process_folder_by_id(node["id"]))
                    else:
                        logger.warning(f"Node {node.get('name')} is neither file nor folder - skipping")
                logger.info(f"NuxeoSource found {len(documents)} documents from nodeDetails")
                return documents

            if self.node_ids:
                logger.info(f"=== NODEIDS MODE: {len(self.node_ids)} ids ===")
                documents = []
                for node_id in self.node_ids:
                    file_doc = self._process_file_by_id(node_id)
                    if file_doc:
                        documents.append(file_doc)
                    else:
                        # Not a file (or unsupported) - treat as a folder
                        documents.extend(self._process_folder_by_id(node_id))
                return documents

            logger.info(f"=== PATH MODE: {self.path} (recursive={self.recursive}) ===")
            return self._process_folder_by_path(self.path)

        except Exception as e:
            logger.error(f"Error listing Nuxeo files: {str(e)}", exc_info=True)
            raise

    def _run_query(self, nxql: str) -> List[dict]:
        """Run an NXQL query, paginating until all entries are collected."""
        entries: List[dict] = []
        page = 0
        while True:
            result = self.nx_client.query(
                nxql,
                params={"properties": "*", "pageSize": _PAGE_SIZE, "currentPageIndex": page},
            )
            entries.extend(result.get("entries", []))
            if not result.get("isNextPageAvailable"):
                break
            page += 1
        return entries

    @staticmethod
    def _file_info_from_entry(entry: dict) -> Optional[dict]:
        """Turn a Nuxeo document JSON entry into our file_info dict, or None if unsupported.

        Handles both File documents (binary blob in file:content) and Note documents
        (inline text in note:note). Folders / blob-less non-note docs return None.
        """
        props = entry.get("properties", {}) or {}
        modified_at = props.get("dc:modified") or entry.get("lastModified")
        last_segment = (entry.get("path") or "").split("/")[-1]

        blob = props.get("file:content")
        note_text = props.get("note:note")

        if blob:
            content_type = blob.get("mime-type", "") or ""
            filename = blob.get("name") or entry.get("title") or last_segment
            kind = "blob"
        elif note_text is not None:
            content_type = props.get("note:mime_type") or "text/plain"
            filename = entry.get("title") or last_segment
            # Notes may have a title without an extension - derive one from the mime-type
            if "." not in filename:
                filename += _NOTE_MIME_EXT.get(content_type, ".txt")
            kind = "note"
        else:
            return None  # folder or unsupported blob-less document

        if not is_docling_supported(content_type, filename):
            logger.info(f"    [-] Unsupported: {filename} ({content_type})")
            return None

        file_info = {
            "id": entry.get("uid"),
            "name": filename,
            "path": entry.get("path"),
            "content_type": content_type,
            "modified_at": modified_at,
            "kind": kind,
        }
        if kind == "note":
            file_info["note_text"] = note_text
        return file_info

    def _process_folder_by_id(self, node_id: str) -> List[dict]:
        """List supported files under a folder document, respecting the recursive flag."""
        scope = f"ecm:ancestorId = '{node_id}'" if self.recursive else f"ecm:parentId = '{node_id}'"
        nxql = f"SELECT * FROM Document WHERE {scope} AND {_NXQL_FILTER}"
        logger.info(f">>> _process_folder_by_id({node_id}) recursive={self.recursive}")
        documents = []
        for entry in self._run_query(nxql):
            file_info = self._file_info_from_entry(entry)
            if file_info:
                documents.append(file_info)
        logger.info(f"<<< _process_folder_by_id found {len(documents)} files")
        return documents

    def _process_file_by_id(self, node_id: str) -> Optional[dict]:
        """Fetch a single document by uid and return file_info if it is a supported file."""
        try:
            doc = self.nuxeo.documents.get(uid=node_id)
        except Exception as e:
            logger.warning(f"Failed to get Nuxeo document {node_id}: {str(e)}")
            return None
        entry = {
            "uid": doc.uid,
            "path": doc.path,
            "title": getattr(doc, "title", None),
            "lastModified": getattr(doc, "lastModified", None),
            "properties": doc.properties or {},
        }
        return self._file_info_from_entry(entry)

    def _process_folder_by_path(self, path: str) -> List[dict]:
        """Enumerate files under a path (a single file path is returned as one item)."""
        try:
            doc = self.nuxeo.documents.get(path=path)
        except Exception as e:
            logger.error(f"Failed to get Nuxeo document at path '{path}': {str(e)}", exc_info=True)
            raise

        entry = {
            "uid": doc.uid,
            "path": doc.path,
            "title": getattr(doc, "title", None),
            "lastModified": getattr(doc, "lastModified", None),
            "properties": doc.properties or {},
        }
        # If the path points to a single supported document (File blob OR Note text),
        # return it directly. _file_info_from_entry returns None for folders (and for
        # unsupported/blob-less docs), in which case we enumerate children instead.
        file_info = self._file_info_from_entry(entry)
        if file_info:
            return [file_info]

        # Otherwise treat it as a folder and enumerate its children
        return self._process_folder_by_id(doc.uid)

    # --------------------------------------------------------------- downloading

    def read_file_bytes(self, node_id: str) -> bytes:
        """Read raw bytes of a single Nuxeo document by uid.

        Used by the lazy CocoIndex source path (``FlexibleMapView``), which lists
        metadata first and only downloads documents whose fingerprint changed —
        so this fetches exactly one document and never touches the filesystem.
        Accepts a raw uid or a ``nuxeo://<uid>`` URI (the form the detector and
        ``FileRecord.key`` use).

        Note documents keep their content inline in ``note:note`` rather than in
        a blob, so they are encoded here instead of fetched, mirroring
        :meth:`_download_document`.
        """
        if node_id.startswith("nuxeo://"):
            node_id = node_id[len("nuxeo://"):]

        file_info = self._process_file_by_id(node_id)
        if file_info and file_info.get("kind") == "note":
            return (file_info.get("note_text") or "").encode("utf-8")

        try:
            content_bytes = self.nuxeo.documents.fetch_blob(uid=node_id)
            if content_bytes:
                return content_bytes
        except Exception as exc:
            logger.warning(
                f"NuxeoSource.read_file_bytes blob fetch failed for {node_id}: {str(exc)}"
            )
        logger.warning(f"NuxeoSource.read_file_bytes: no bytes captured for {node_id}")
        return b""

    def _download_document(self, document: dict, temp_dir: str) -> str:
        """Download a Nuxeo document's main blob to a temp file and return the path."""
        import os

        filename = document["name"]
        node_id = document["id"]
        local_name = filename
        if "." not in filename and document.get("content_type"):
            # the parser picks by extension: give the temp file one from the content type
            import mimetypes
            local_name += mimetypes.guess_extension(document["content_type"].split(";")[0].strip()) or ""
        temp_file_path = os.path.join(temp_dir, local_name)

        logger.info(f">>> _download_document() {filename} (id={node_id}, kind={document.get('kind')})")

        if document.get("kind") == "note":
            # Note documents hold their content inline as text (note:note)
            text = document.get("note_text") or ""
            with open(temp_file_path, "w", encoding="utf-8") as temp_file:
                temp_file.write(text)
            logger.info(f"<<< _download_document() wrote {len(text)} chars (note) to {temp_file_path}")
            return temp_file_path

        # File documents: download the main blob's bytes
        content_bytes = self.nuxeo.documents.fetch_blob(uid=node_id)
        if not content_bytes:
            raise ValueError(f"No content available for Nuxeo document: {filename}")

        with open(temp_file_path, "wb") as temp_file:
            bytes_written = temp_file.write(content_bytes)
        logger.info(f"<<< _download_document() wrote {bytes_written} bytes to {temp_file_path}")
        return temp_file_path

    # ----------------------------------------------------------------- documents

    def _apply_metadata(self, processed_doc: Document, file_info: dict) -> None:
        processed_doc.metadata.update({
            "source": "nuxeo",
            "nuxeo_id": file_info["id"],
            "stable_file_path": f"nuxeo://{file_info['id']}",  # uid is stable across renames/moves
            "file_name": file_info["name"],
            "file_path": file_info["path"],
            "content_type": file_info["content_type"],
        })
        if file_info.get("modified_at"):
            processed_doc.metadata["modified_at"] = str(file_info["modified_at"])

    async def get_documents_with_progress(self, progress_callback=None):
        """Get documents from Nuxeo with progress tracking."""
        import tempfile
        import os
        import asyncio

        try:
            logger.info("=== GET_DOCUMENTS_WITH_PROGRESS START ===")
            if progress_callback:
                progress_callback(current=0, total=1, message="Connecting to Nuxeo repository...", current_file="")

            files = self.list_files()
            logger.info(f"list_files() returned {len(files)} files")
            documents = []
            if not files:
                return (0, documents)

            temp_dir = tempfile.mkdtemp(prefix="nuxeo_download_")
            try:
                doc_processor = self._get_document_processor()
                for i, file_info in enumerate(files):
                    try:
                        if progress_callback:
                            progress_callback(
                                current=i + 1,
                                total=len(files),
                                message=f"Processing document: {file_info['name']}",
                                current_file=file_info["name"],
                            )
                        temp_file_path = self._download_document(file_info, temp_dir)
                        processed_docs = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: asyncio.run(doc_processor.process_documents([temp_file_path])),
                        )
                        if not processed_docs:
                            raise ValueError(f"Failed to process document: {file_info['name']}")
                        processed_doc = processed_docs[0]
                        self._apply_metadata(processed_doc, file_info)
                        documents.append(processed_doc)

                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                    except Exception as e:
                        logger.error(f"[ERROR] Error processing Nuxeo document {file_info['name']}: {str(e)}", exc_info=True)
                        continue
            finally:
                try:
                    if os.path.exists(temp_dir):
                        os.rmdir(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory {temp_dir}: {str(e)}")

            logger.info(f"=== GET_DOCUMENTS_WITH_PROGRESS COMPLETE: {len(files)} files, {len(documents)} chunks ===")
            return (len(files), documents)

        except Exception as e:
            logger.error(f"Error getting Nuxeo documents with progress: {str(e)}", exc_info=True)
            raise

    def get_documents(self) -> List[Document]:
        """Get documents from Nuxeo by downloading and processing them."""
        import asyncio
        import tempfile
        import os

        files = self.list_files()
        documents = []
        failures: List[str] = []
        temp_dir = tempfile.mkdtemp(prefix="nuxeo_download_")

        try:
            doc_processor = self._get_document_processor()
            for file_info in files:
                try:
                    temp_file_path = self._download_document(file_info, temp_dir)
                    # DocumentProcessor exposes process_documents(list) -> list and it
                    # is async; there is no process_file().  See the async sibling
                    # get_documents_with_progress() above, which does the same thing.
                    processed_docs = asyncio.run(
                        doc_processor.process_documents([temp_file_path])
                    )
                    if not processed_docs:
                        raise ValueError(f"Parser returned nothing for {file_info['name']}")
                    processed_doc = processed_docs[0]
                    self._apply_metadata(processed_doc, file_info)
                    documents.append(processed_doc)

                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                except Exception as e:
                    logger.error(f"Error processing Nuxeo document {file_info['name']}: {str(e)}")
                    failures.append(f"{file_info['name']}: {e}")
                    continue
        finally:
            try:
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {str(e)}")

        # A per-document failure must not abort the batch, but if EVERY file failed
        # the caller has to hear about it: returning [] silently made ingest report
        # "completed" having stored nothing, which is how a missing processor method
        # went unnoticed.
        if files and not documents:
            raise RuntimeError(
                f"Nuxeo: all {len(files)} document(s) failed to process. "
                + "; ".join(failures[:3])
                + ("..." if len(failures) > 3 else "")
            )

        return documents
