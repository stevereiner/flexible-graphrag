"""OpenArch REST access for the store, on python-openarch-api.

The few calls the writer and the vector store make, as plain dicts (wire names), over
``python_openarch_api.OpenArchClient``: documents by id and path, HXQL queries, vector search,
uploads. The repository is chosen per request with OpenArch's ``HXCS-REPOSITORY`` header.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from python_openarch_api import OpenArchClient as _ApiClient
from python_openarch_api import OpenArchConflictError, OpenArchError, OpenArchNotFoundError

logger = logging.getLogger(__name__)

ROOT_ID = "00000000-0000-0000-0000-000000000000"

__all__ = ["OpenArchClient", "OpenArchError", "OpenArchConflictError", "OpenArchNotFoundError",
           "ROOT_ID", "hxql_literal", "under"]


def _doc(document) -> Dict[str, Any]:
    return document.to_json() if document is not None else None


class OpenArchClient:
    """OpenArch REST API client for the store (dict in, dict out)."""

    def __init__(self, url: str, username: str = "admin", password: str = "password",
                 repository: str = "default", timeout: float = 60.0):
        self.url = url.rstrip("/")
        self.repository = repository
        self.api = _ApiClient(self.url, repository=repository, username=username or None,
                              password=password or None, timeout=timeout)
        self._folders: set = set()  # repository paths known to exist
        self._folder_lock = threading.Lock()

    def close(self) -> None:
        self.api.close()

    # ----- documents -----

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        try:
            return _doc(self.api.get_document(doc_id))
        except OpenArchNotFoundError:
            return None

    def get_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            return _doc(self.api.get_document_by_path(path))
        except OpenArchNotFoundError:
            return None

    def create(self, parent_path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Create a document under ``parent_path``; ``enforceSysName`` makes a duplicate name a
        409 (``OpenArchConflictError``) instead of a silent rename."""
        if parent_path.strip("/"):
            return _doc(self.api.create_document_by_path(parent_path, body, enforce_sys_name=True))
        return _doc(self.api.create_document(ROOT_ID, body, enforce_sys_name=True))

    def create_child(self, parent_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return _doc(self.api.create_document(parent_id, body, enforce_sys_name=True))

    def update(self, doc_id: str, body: Dict[str, Any], condition: Optional[str] = None) -> Dict[str, Any]:
        """Update the properties in ``body``; with an HXQL ``condition`` (e.g. on ``sys_ugen``),
        only if the document still matches it (else OpenArchError 412)."""
        return _doc(self.api.update_document(doc_id, body, condition=condition))

    def move(self, doc_id: str, target_parent_id: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Move a document under another folder (by id), renamed to ``name`` where the server takes
        a name on move (a stock OpenArch ignores it: see writer.place_source_document); returns it
        at its new place."""
        body = {"targetParentId": target_parent_id}
        if name:
            body["name"] = name
        return _doc(self.api.move(doc_id, body))

    def copy(self, doc_id: str, target_parent_id: str, name: str) -> Dict[str, Any]:
        """Copy a document (with its children) under a folder (by id), named ``name``; returns the copy."""
        return _doc(self.api.copy(doc_id, {"targetParentId": target_parent_id, "name": name}))

    def delete(self, doc_id: str) -> bool:
        try:
            self.api.delete_document(doc_id)
            return True
        except OpenArchNotFoundError:
            return False

    def ensure_folders(self, path: str) -> None:
        """Create the missing ``SysFolder``s of ``path`` (an existing name is fine: 409).
        Serialized: a folder another thread is still creating answers 409 before it can be
        used as a parent."""
        with self._folder_lock:
            parent = ""
            for name in [s for s in path.strip("/").split("/") if s]:
                current = f"{parent}/{name}"
                if current not in self._folders:
                    try:
                        self.create(parent, {"sys_primaryType": "SysFolder", "sys_name": name, "sys_title": name})
                    except OpenArchConflictError:
                        if self.get_by_path(current) is None:
                            raise
                    self._folders.add(current)
                parent = current

    # ----- queries -----

    def query(self, hxql: str, limit: int = 100, offset: int = 0, sync: bool = True) -> Dict[str, Any]:
        """HXQL query; ``sync=True`` runs it on the repository itself (consistent with the last
        writes), otherwise on OpenSearch (needed for keys inside a map property)."""
        result = self.api.query(hxql, limit=limit, offset=offset, sync=sync)
        return {"documents": [_doc(d) for d in result.documents or []]}

    def query_all(self, hxql: str, page_size: int = 200, sync: bool = True) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        offset = 0
        while True:
            page = self.query(hxql, limit=page_size, offset=offset, sync=sync)["documents"]
            docs.extend(page)
            if len(page) < page_size:
                return docs
            offset += page_size

    def query_embeddings(self, vector: List[float], limit: int = 10, embedding_type: str = "*",
                         hxql: Optional[str] = None, chunk_fts: Optional[str] = None) -> List[Dict[str, Any]]:
        """kNN search over chunks; ``hxql`` filters by the chunks' documents, ``chunk_fts`` makes it
        a hybrid query (kNN + chunk text match, fused by OpenSearch's RRF pipeline)."""
        body: Dict[str, Any] = {"vector": vector, "limit": limit, "embeddingType": embedding_type,
                                "repositoryId": self.repository}
        if hxql:
            body["query"] = hxql
        if chunk_fts:
            body["chunkFTS"] = chunk_fts
        result = self.api.vector_search(body)
        return [e.model_dump(mode="json", by_alias=True, exclude_none=True) for e in result.embeddings or []]

    def wait_for_indexing(self, timeout_seconds: int = 10) -> None:
        self.api.wait_for_indexing(refresh=True, timeout=timeout_seconds)

    # ----- uploads -----

    def upload(self, data: bytes, file_name: str, mime_type: str) -> str:
        """Upload a blob; returns the upload id to attach as ``{"uploadId": id}``."""
        return self.api.upload(data, file_name=file_name, mime_type=mime_type).id


def under(path: str) -> str:
    """HXQL condition: the document is below ``path`` (one Flexible GraphRAG's own tree, so that several
    instances, or a test run, can share a repository without seeing each other's documents)."""
    return "sys_path STARTSWITH " + hxql_literal("/" + str(path).strip("/") + "/")


def hxql_literal(value: str) -> str:
    """Quote a string for HXQL (backslash escapes; SQL-style doubled quotes are rejected)."""
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"
