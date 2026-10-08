"""Ingest status of a repository selection: which datasources already hold it -- active
auto-syncs ("synced"), and sources ingested without sync ("ingested", recorded with
auto_sync = FALSE).

Answers, before an ingest starts, "is any of this already being synced?" -- so a UI can show it
per row instead of ingesting the same documents a second time under a different config_id
(different config_id means different ref_doc_ids, so a repeat is a duplicate, not an update).

Two independent sources of truth, used together:

* **What each datasource is configured to cover** -- its root path(s) and ``recursive`` flag.
  A path-based datasource has one root, its ``path``; a multi-select has one root per entry in
  ``nodeDetails``. This is the only answer available for a folder.
* **What each datasource actually indexed** -- ``document_state`` rows, matched by the
  repository's own node id (``source_id``). Exact for a file however many folders up its
  datasource is rooted, and it still matches after the file is renamed or moved.

Only repository sources whose datasources are rooted at a folder path (Alfresco, Nuxeo) are
handled. The functions here are pure; the endpoint in main.py does the database reads.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

PATH_SOURCES = ("alfresco", "nuxeo")
# Sources whose rows are files on the backend's disk: an uploaded file (by its name, saved under
# the upload directory) or a filesystem path. Ingest status and per-row runs cover them too.
FS_SOURCES = ("filesystem", "upload")
ROW_SOURCES = PATH_SOURCES + FS_SOURCES


def fs_key(path: str) -> str:
    """A filesystem path as document_state keeps it (its source_id): normalized, lowercase on
    Windows (incremental_updates.path_utils)."""
    from .path_utils import normalize_filesystem_path
    return normalize_filesystem_path(path)


def fs_item(path: str, is_folder: bool = False) -> "Item":
    """A filesystem row as an Item: path in repository form (forward slashes, for folder
    depth) and the document_state source_id as its id (exact file matching)."""
    key = fs_key(path)
    return Item(normalize_repo_path(key), is_folder, None if is_folder else key)

# Strongest first: one item may relate to several datasources, and its status is the
# strongest of those relations.
STATUS_ORDER = ("synced", "partial", "overlaps", "none")
# Not ranked: set after the fact for a file whose only copy an auto-sync keeps, after it was
# removed from every store (incremental_updates/removal.py).
REMOVED = "removed"


def normalize_repo_path(path: Optional[str]) -> str:
    """Canonical form for comparing repository paths: leading slash, no trailing slash,
    no doubled slashes, and Alfresco's ``/Company Home`` prefix dropped (the UIs strip it,
    older configs may still carry it)."""
    # (backslashes too: a filesystem path compares the same way -- repository names cannot
    # contain one)
    p = re.sub(r"/+", "/", "/" + (path or "").strip().replace("\\", "/"))
    p = re.sub(r"^/Company Home(?=/|$)", "", p) or "/"
    return p.rstrip("/") or "/"


def _depth_below(path: str, root: str) -> Optional[int]:
    """How many levels ``path`` sits below ``root`` (0 = same), or None if it is not under it."""
    if path == root:
        return 0
    prefix = root if root == "/" else root + "/"
    if not path.startswith(prefix):
        return None
    return len(path[len(prefix):].split("/"))


def normalize_url(url: Optional[str]) -> str:
    return (url or "").strip().rstrip("/").lower()


@dataclass
class Root:
    path: str
    is_folder: bool
    node_id: Optional[str] = None


@dataclass
class Datasource:
    config_id: str
    source_type: str
    source_name: str
    url: str
    recursive: bool
    skip_graph: bool
    roots: List[Root]
    auto_sync: bool = True  # False: recorded by an ingest without auto change sync

    @classmethod
    def from_config(cls, cfg: Any) -> "Datasource":
        cp: Dict[str, Any] = dict(getattr(cfg, "connection_params", None) or {})
        details = cp.get("nodeDetails") or []
        if cp.get("paths") and not details:
            # A filesystem / upload datasource: its paths are the roots
            import os
            roots = [Root(path=normalize_repo_path(fs_key(p)), is_folder=os.path.isdir(p),
                          node_id=None if os.path.isdir(p) else fs_key(p))
                     for p in cp.get("paths") or [] if p]
        elif details:
            roots = [
                Root(
                    path=normalize_repo_path(nd.get("path")),
                    is_folder=bool(nd.get("isFolder")),
                    node_id=nd.get("id"),
                )
                for nd in details
                if isinstance(nd, dict) and nd.get("path")
            ]
        else:
            roots = [Root(path=normalize_repo_path(cp.get("path")), is_folder=True)]
        return cls(
            config_id=cfg.config_id,
            source_type=cfg.source_type,
            source_name=getattr(cfg, "source_name", "") or "",
            url=normalize_url(cp.get("url")),
            recursive=bool(cp.get("recursive", False)),
            skip_graph=bool(getattr(cfg, "skip_graph", False)),
            roots=roots,
            auto_sync=bool(getattr(cfg, "auto_sync", True)),
        )


@dataclass
class Item:
    path: str
    is_folder: bool
    id: Optional[str] = None


@dataclass
class Match:
    config_id: str
    source_name: str
    root: str
    recursive: bool
    skip_graph: bool
    relation: str  # same | inside | contains | indexed
    status: str    # synced | partial | overlaps
    auto_sync: bool = True  # False: ingested once, not kept in sync

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def relate(item: Item, ds: Datasource, request_recursive: bool) -> List[Match]:
    """How one selected item relates to one datasource's roots.

    ``same``     the item IS a root. A folder synced non-recursively, selected now with
                 recursive on, is only ``partial``: its subfolders are not covered.
    ``inside``   the item is below a root. Covered at any depth when the datasource is
                 recursive; otherwise only a file directly in a root folder is covered, since
                 a non-recursive sync never descends into subfolders.
    ``contains`` the item is a folder above a root. Ingesting it would ingest that root's
                 documents again -- when recursive, or when the root is a file sitting
                 directly in it.
    """
    matches: List[Match] = []

    def add(root: Root, relation: str, status: str) -> None:
        matches.append(Match(ds.config_id, ds.source_name, root.path, ds.recursive,
                             ds.skip_graph, relation, status, ds.auto_sync))

    for root in ds.roots:
        if (item.id and root.node_id and item.id == root.node_id) or item.path == root.path:
            partial = item.is_folder and root.is_folder and request_recursive and not ds.recursive
            add(root, "same", "partial" if partial else "synced")
            continue

        if root.is_folder:
            depth = _depth_below(item.path, root.path)
            if depth is not None:
                if ds.recursive or (depth == 1 and not item.is_folder):
                    add(root, "inside", "synced")
                continue

        if item.is_folder:
            depth = _depth_below(root.path, item.path)
            if depth is not None and (request_recursive or (depth == 1 and not root.is_folder)):
                add(root, "contains", "overlaps")
    return matches


def check_ingest_status(
    items: Iterable[Item],
    datasources: Iterable[Datasource],
    indexed: Dict[str, List[Dict[str, Any]]],
    request_recursive: bool = False,
    present: Optional[List[set]] = None,
) -> List[Dict[str, Any]]:
    """Per-item ingest status. ``indexed`` maps a node id to its ``document_state`` rows (each with
    ``config_id`` and the ``*_synced_at`` timestamps), already limited to ``datasources``.

    ``present``, per item, names the datasources that still have one of its documents in a
    store. An ingest-only datasource missing from it no longer covers the item: what it
    ingested there was removed, and its path rules alone would still claim it."""
    datasources = list(datasources)
    by_id = {ds.config_id: ds for ds in datasources}
    results = []
    for n, item in enumerate(items):
        item = Item(normalize_repo_path(item.path), item.is_folder, item.id)
        matches: List[Match] = []
        for ds in datasources:
            if present is not None and not ds.auto_sync and ds.config_id not in present[n]:
                continue
            matches.extend(relate(item, ds, request_recursive))

        # document_state is ground truth for a file: it catches a file the path rules miss
        # (moved or renamed since it was synced).
        targets = None
        auto_sync = None  # per document: an auto-sync datasource, and its own auto_sync on
        if item.id and not item.is_folder:
            rows = [r for r in indexed.get(item.id) or [] if r.get("config_id") in by_id]
            for row in rows:
                ds = by_id[row["config_id"]]
                if not any(m.config_id == ds.config_id and m.status == "synced" for m in matches):
                    matches.append(Match(ds.config_id, ds.source_name, "", ds.recursive,
                                         ds.skip_graph, "indexed", "synced", ds.auto_sync))
            if rows:
                targets = {
                    t: any(r.get(f"{t}_synced_at") for r in rows)
                    for t in ("vector", "search", "graph")
                }
                auto_sync = any(by_id[r["config_id"]].auto_sync and r.get("auto_sync", True) for r in rows)
        if auto_sync is None:
            # Nothing per document (a folder, or a file no sync has recorded yet): the
            # datasources that cover it
            auto_sync = any(m.auto_sync for m in matches)

        status = min((m.status for m in matches), key=STATUS_ORDER.index, default="none")
        if targets is not None and not any(targets.values()):
            status = REMOVED
        results.append({
            "id": item.id,
            "path": item.path,
            "is_folder": item.is_folder,
            "status": status,
            "datasources": [m.as_dict() for m in matches],
            "indexed": targets,
            "auto_sync": auto_sync,
        })
    return results
