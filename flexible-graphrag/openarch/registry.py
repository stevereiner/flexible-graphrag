"""Data source configs and document state in the OpenArch tree (INCREMENTAL_STATE_STORE=openarch).

The incremental registry -- PostgreSQL's ``datasource_config`` and ``document_state`` tables
(incremental_updates/schema.sql) -- kept in OpenArch instead, behind the same ConfigManager /
StateManager methods:

- a data source is a ``SysFolder`` with the ``FgDataSource`` mixin (schema ``fgdatasource``,
  fields ``fg_datasource_*``) at ``<OPENARCH_DATASOURCES_PATH>/<project>/<config id>``, titled with its
  name. (Scope rules are not here: they go on the objects themselves, openarch/scope.py.)
- document state goes on the source document itself, the one the OpenArch store writes once per
  source system object at ``<OPENARCH_ROOT_PATH>/<source type>/<system id>/<source path>``
  (openarch/writer.py): the ``FgDocState`` mixin (schema ``fgdocstate``, fields ``fg_docstate_*``) holds
  one entry per data source that has the document (``fg_docstate_states``, the rows of
  ``document_state``), plus the data sources' config ids, doc ids and source ids as lists, for
  queries. A document only some data source's state refers to (its content went, or OpenArch is
  not the vector / search store) has no text and no chunks; it is deleted with the last entry.

The schemas are added to the repository model on first use. Read-modify-write updates of a
document are conditional on its ``sys_ugen`` and retried on a conflict.

The OpenArch REST client is synchronous: the async methods run it in a worker thread.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from incremental_updates.config_manager import ConfigManager, DataSourceConfig
from incremental_updates.state_manager import DocumentState, StateManager
from openarch import source_system as ss
from openarch.client import OpenArchClient, OpenArchError, hxql_literal, under
from openarch.scope import (
    EFFECTIVE, FLAGS_MIXIN, FLAGS_SCHEMA, ROOT_SOURCES, RULE_MIXIN, RULE_SCHEMA, ScopeStore, effective_flags,
    graphs_skipped, roots_params, sync_decision,
)
from openarch.writer import (
    DOC_IDS_KEY, create_source_document, delete_with_chunks, doc_ids_of, place_source_document,
)

logger = logging.getLogger("flexible_graphrag.incremental_system")

DATASOURCE_MIXIN = "FgDataSource"
STATE_MIXIN = "FgDocState"

_IN_BATCH = 100   # values per HXQL IN (...)
_RETRIES = 8      # conditional update attempts
# A concurrent change: 412 (our sys_ugen condition no longer holds) or 409 (the repository's own
# concurrent-update check; seen, rarely, on sequential updates with openarch-graph-storage's Neo4j)
_CONFLICTS = (409, 412)

# ── Repository model ─────────────────────────────────────────────────────────────────────────

_S, _D, _L, _B = {"type": "string"}, {"type": "date"}, {"type": "long"}, {"type": "boolean"}

# One data source's state of a document (a document_state row). modifiedAt is kept as the
# source gave it (a string): the sync compares it for equality, and a date property can lose
# precision (milliseconds on MongoDB).
STATE_FIELDS = {
    "docId": _S, "configId": _S, "sourcePath": _S, "sourceId": _S, "ordinal": _L, "contentHash": _S,
    "modifiedAt": _S, "vectorSyncedAt": _D, "searchSyncedAt": _D, "graphSyncedAt": _D,
    "autoSync": _B, "skipGraph": _B, "createdAt": _D, "updatedAt": _D,
    # the RDF graph's sync time, and per graph whether this document leaves it out (graph_flags.py)
    "rdfSyncedAt": _D, "enabledGraph": _B, "enabledRdf": _B,
}

MODEL_TYPES = {
    "fgdocstate#state": {"fields": STATE_FIELDS},
    "fgdocstate#stateList": {"list": {"type": "fgdocstate#state"}},
    "fgdocstate#stringList": {"list": {"type": "string"}},
}

# Field names carry their schema: fg_datasource_*, fg_docstate_* (and fg_rule_*, fg_flags_* in
# openarch/scope.py). OpenArch derives a schema's "prefix" from its first field name up to the first
# "_", so all four show as "fg" in the model; fields are resolved by their full names.
MODEL_SCHEMAS = {
    "fgdocstate": {"prefix": "fg_docstate", "fields": {
        "fg_docstate_states": {"type": "fgdocstate#stateList"},
        "fg_docstate_configIds": {"type": "fgdocstate#stringList"},
        "fg_docstate_docIds": {"type": "fgdocstate#stringList"},
        "fg_docstate_sourceIds": {"type": "fgdocstate#stringList"},
    }},
    "fgdatasource": {"prefix": "fg_datasource", "fields": {
        "fg_datasource_configId": _S, "fg_datasource_projectId": _S, "fg_datasource_sourceType": _S, "fg_datasource_sourceName": _S,
        "fg_datasource_connectionParams": _S, "fg_datasource_refreshIntervalSeconds": _L, "fg_datasource_watchdogFilesystemSeconds": _L,
        "fg_datasource_enableChangeStream": _B, "fg_datasource_skipGraph": _B, "fg_datasource_isActive": _B, "fg_datasource_autoSync": _B,
        # which graphs it builds (graph_flags.py); unset = from skipGraph, else the defaults
        "fg_datasource_enabledGraph": _B, "fg_datasource_enabledRdf": _B,
        "fg_datasource_syncStatus": _S, "fg_datasource_lastSyncOrdinal": _L, "fg_datasource_lastSyncCompletedAt": _D, "fg_datasource_lastError": _S,
        "fg_datasource_syncCursor": _S,
        "fg_datasource_followsRules": _B,  # its roots are what the scope rules follow (apply_rule_roots)
    }},
}

MODEL_SCHEMAS["fgrule"] = RULE_SCHEMA     # per-object scope rules (openarch/scope.py)
MODEL_SCHEMAS["fgflags"] = FLAGS_SCHEMA   # the flags in effect on a document

MODEL_MIXINS = {
    STATE_MIXIN: {"schemas": ["fgdocstate"]},
    DATASOURCE_MIXIN: {"schemas": ["fgdatasource"]},
    RULE_MIXIN: {"schemas": ["fgrule"]},
    FLAGS_MIXIN: {"schemas": ["fgflags"]},
}

_models_ready: Set[Tuple[str, str]] = set()
_model_lock = threading.Lock()


def model_patch(model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """JSON Patch adding what the repository model lacks of ours: types, schemas, their
    fields, mixins. Existing definitions are left as they are."""
    ops: List[Dict[str, Any]] = []
    for section, wanted in (("types", MODEL_TYPES), ("schemas", MODEL_SCHEMAS), ("mixinTypes", MODEL_MIXINS)):
        have = model.get(section) or {}
        for name, definition in wanted.items():
            if name not in have:
                ops.append({"op": "add", "path": f"/{section}/{name}", "value": definition})
                continue
            fields = (have[name] or {}).get("fields")
            for field, spec in (definition.get("fields") or {}).items():
                if fields is not None and field not in fields:
                    ops.append({"op": "add", "path": f"/{section}/{name}/fields/{field}", "value": spec})
    return ops


def ensure_model(client: OpenArchClient) -> None:
    """Add our schemas and mixins to the repository model (once per process and repository)."""
    key = (client.url, client.repository)
    with _model_lock:
        if key in _models_ready:
            return
        model = client.api.get_model().model_dump(by_alias=True, exclude_none=True)
        ops = model_patch(model)
        if ops:
            client.api.patch_model(ops)
            logger.info("OpenArch: added %d definition(s) of the data source / document state schemas "
                        "to the repository model", len(ops))
        _models_ready.add(key)


# ── Values ───────────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> Optional[str]:
    """A timestamp as an ISO string (UTC when it has a zone), or None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return (value.astimezone(timezone.utc) if value.tzinfo else value).isoformat()
    return str(value)


def _dt(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _chunks(values: List[str], size: int = _IN_BATCH):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _in(values: Iterable[str]) -> str:
    return "(" + ", ".join(hxql_literal(v) for v in values) + ")"


def _has_content(doc: Dict[str, Any]) -> bool:
    """Whether the OpenArch store has the document's content (text, chunks) here."""
    return bool(str((doc.get("cin_ingestProperties") or {}).get(DOC_IDS_KEY) or "").strip())


TARGET_FIELDS = {"vector": "vectorSyncedAt", "search": "searchSyncedAt", "graph": "graphSyncedAt",
                 "rdf": "rdfSyncedAt"}


def _in_store(entry: Dict[str, Any]) -> bool:
    return any(entry.get(f) for f in TARGET_FIELDS.values())


def _entry_graphs(entry: Optional[Dict[str, Any]]):
    """A state entry's own graphs; one written before the per-graph fields: skipGraph = neither."""
    from graph_flags import GraphFlags
    if not entry:
        return GraphFlags()
    off = bool(entry.get("skipGraph"))
    g, r = entry.get("enabledGraph"), entry.get("enabledRdf")
    return GraphFlags(not off if g is None else g is not False, not off if r is None else r is not False)


def _state_of(entry: Dict[str, Any]) -> DocumentState:
    return DocumentState(
        doc_id=entry["docId"],
        config_id=entry.get("configId") or "",
        source_path=entry.get("sourcePath") or "",
        source_id=entry.get("sourceId"),
        ordinal=int(entry.get("ordinal") or 0),
        content_hash=entry.get("contentHash"),
        modified_timestamp=_dt(entry.get("modifiedAt")),
        vector_synced_at=_dt(entry.get("vectorSyncedAt")),
        search_synced_at=_dt(entry.get("searchSyncedAt")),
        graph_synced_at=_dt(entry.get("graphSyncedAt")),
        rdf_synced_at=_dt(entry.get("rdfSyncedAt")),
        skip_graph=bool(entry.get("skipGraph")),
        enabled_graph=_entry_graphs(entry).graph,
        enabled_rdf=_entry_graphs(entry).rdf,
        auto_sync=entry.get("autoSync") is not False,
        created_at=_dt(entry.get("createdAt")),
        updated_at=_dt(entry.get("updatedAt")),
    )


def _row_of(entry: Dict[str, Any]):
    from incremental_updates.removal import StateRow
    return StateRow(
        doc_id=entry["docId"],
        config_id=entry.get("configId") or "",
        source_id=entry.get("sourceId"),
        source_path=entry.get("sourcePath") or "",
        synced={t: bool(entry.get(f)) for t, f in TARGET_FIELDS.items()},
        auto_sync=entry.get("autoSync") is not False,
    )


def _identity(doc_id: str, config_id: str) -> str:
    """The source object part of a ``<config_id>:<identity>`` doc id."""
    prefix = f"{config_id}:"
    return doc_id[len(prefix):] if config_id and doc_id.startswith(prefix) else ss.document_identity(doc_id, {})


# ── Data source documents ────────────────────────────────────────────────────────────────────

_CONFIG_FIELDS = {  # DataSourceConfig attribute -> property
    "config_id": "fg_datasource_configId", "project_id": "fg_datasource_projectId", "source_type": "fg_datasource_sourceType",
    "source_name": "fg_datasource_sourceName", "refresh_interval_seconds": "fg_datasource_refreshIntervalSeconds",
    "watchdog_filesystem_seconds": "fg_datasource_watchdogFilesystemSeconds",
    "enable_change_stream": "fg_datasource_enableChangeStream", "skip_graph": "fg_datasource_skipGraph",
    "enabled_graph": "fg_datasource_enabledGraph", "enabled_rdf": "fg_datasource_enabledRdf",
    "is_active": "fg_datasource_isActive", "auto_sync": "fg_datasource_autoSync", "sync_status": "fg_datasource_syncStatus",
    "last_sync_ordinal": "fg_datasource_lastSyncOrdinal", "last_error": "fg_datasource_lastError",
}


def _config_props(**values: Any) -> Dict[str, Any]:
    """Data source properties from DataSourceConfig fields; ``graphs`` (a GraphFlags), skip_graph or
    enabled_graph / enabled_rdf are kept consistent (config_manager.graph_updates)."""
    from incremental_updates.config_manager import graph_updates
    values = graph_updates(values)
    props: Dict[str, Any] = {}
    for key, value in values.items():
        if key == "connection_params":
            props["fg_datasource_connectionParams"] = json.dumps(value or {})
        elif key == "last_sync_completed_at":
            props["fg_datasource_lastSyncCompletedAt"] = _iso(value)
        elif key in _CONFIG_FIELDS:
            props[_CONFIG_FIELDS[key]] = value
    if "source_name" in values:
        props["sys_title"] = values["source_name"]
    return props


def _config_of(doc: Dict[str, Any]) -> DataSourceConfig:
    try:
        params = json.loads(doc.get("fg_datasource_connectionParams") or "{}")
    except ValueError:
        params = {}
    return DataSourceConfig(
        config_id=doc.get("fg_datasource_configId"),
        project_id=doc.get("fg_datasource_projectId") or "default",
        source_type=doc.get("fg_datasource_sourceType") or "",
        source_name=doc.get("fg_datasource_sourceName") or doc.get("sys_title") or "",
        connection_params=params,
        refresh_interval_seconds=int(doc.get("fg_datasource_refreshIntervalSeconds") or 3600),
        watchdog_filesystem_seconds=int(doc.get("fg_datasource_watchdogFilesystemSeconds") or 60),
        enable_change_stream=bool(doc.get("fg_datasource_enableChangeStream")),
        skip_graph=bool(doc.get("fg_datasource_skipGraph")),
        enabled_graph=doc.get("fg_datasource_enabledGraph"),
        enabled_rdf=doc.get("fg_datasource_enabledRdf"),
        is_active=doc.get("fg_datasource_isActive") is not False,
        auto_sync=doc.get("fg_datasource_autoSync") is not False,
        sync_status=doc.get("fg_datasource_syncStatus") or "idle",
        last_sync_ordinal=doc.get("fg_datasource_lastSyncOrdinal"),
        last_sync_completed_at=_dt(doc.get("fg_datasource_lastSyncCompletedAt")),
        last_error=doc.get("fg_datasource_lastError"),
        created_at=_dt(doc.get("sys_created")),
        updated_at=_dt(doc.get("sys_modified")),
    )


class OpenArchRegistry:
    """The OpenArch side of both managers: data source documents and document state."""

    def __init__(self, settings: Dict[str, Any]):
        self.client = OpenArchClient(
            url=settings.get("url", "http://localhost:8080"),
            username=settings.get("username", "admin"),
            password=settings.get("password", "password"),
            repository=settings.get("repository", "default"),
            timeout=float(settings.get("timeout", 60)),
        )
        self.root_path = "/" + str(settings.get("root_path") or "/fg-sources").strip("/")
        self.datasources_path = "/" + str(settings.get("datasources_path") or "/fg-datasources").strip("/")
        # every query stays in this instance's own trees
        self.in_sources = under(self.root_path)
        self.in_datasources = under(self.datasources_path)
        self._sources: Dict[str, Tuple[str, str]] = {}  # config id -> (source type, source system)
        self.scope = ScopeStore(self)

    def initialize(self) -> None:
        ensure_model(self.client)

    def update_with_mixin(self, doc: Dict[str, Any], mixin: str, props: Dict[str, Any]) -> Dict[str, Any]:
        """Set ``props`` on a document, adding ``mixin`` to it when missing; conditional on its
        ``sys_ugen``, read again and redone on a concurrent change. Returns the document."""
        for attempt in range(_RETRIES):
            body = dict(props)
            mixins = list(doc.get("sys_mixinTypes") or [])
            if mixin not in mixins:
                body["sys_mixinTypes"] = mixins + [mixin]
            try:
                return self.client.update(doc["sys_id"], body,
                                          condition=f"sys_ugen = {int(doc.get('sys_ugen') or 0)}")
            except OpenArchError as e:
                if e.status_code not in _CONFLICTS or attempt == _RETRIES - 1:
                    raise
            doc = self.client.get(doc["sys_id"]) or doc
        return doc

    def close(self) -> None:
        self.client.close()

    # ----- data sources -----

    def config_docs(self) -> List[Dict[str, Any]]:
        docs = self.client.query_all(
            f"SELECT * FROM SysFolder WHERE fg_datasource_configId IS NOT NULL AND {self.in_datasources}")
        docs.sort(key=lambda d: str(d.get("sys_created") or ""))
        return docs

    def config_doc(self, config_id: str) -> Optional[Dict[str, Any]]:
        docs = self.client.query(
            f"SELECT * FROM SysFolder WHERE fg_datasource_configId = {hxql_literal(config_id)} AND {self.in_datasources}",
            limit=5)["documents"]
        return docs[0] if docs else None

    def create_config_doc(self, config: DataSourceConfig) -> Dict[str, Any]:
        project = ss.safe_name(config.project_id or "default")
        parent = f"{self.datasources_path}/{project}"
        self.client.ensure_folders(parent)
        body = {"sys_primaryType": "SysFolder", "sys_mixinTypes": [DATASOURCE_MIXIN],
                "sys_name": ss.safe_name(config.config_id),
                **_config_props(
                    config_id=config.config_id, project_id=config.project_id or "default",
                    source_type=config.source_type, source_name=config.source_name,
                    connection_params=config.connection_params,
                    refresh_interval_seconds=config.refresh_interval_seconds,
                    watchdog_filesystem_seconds=config.watchdog_filesystem_seconds,
                    enable_change_stream=config.enable_change_stream, graphs=config.graphs,
                    is_active=config.is_active, auto_sync=config.auto_sync,
                    sync_status=config.sync_status or "idle")}
        return self.client.create(parent, body)

    def update_config_doc(self, config_id: str, **values: Any) -> bool:
        doc = self.config_doc(config_id)
        if doc is None:
            return False
        self.client.update(doc["sys_id"], _config_props(**values))
        return True

    def delete_config_doc(self, config_id: str) -> None:
        doc = self.config_doc(config_id)
        if doc is not None:
            self.client.delete(doc["sys_id"])

    def source_system(self, config_id: str) -> Tuple[str, str]:
        """``(source type, source system)`` of a data source's documents, as the OpenArch store
        names them (openarch/source_system.py): the current ingest job's when set (what the
        store wrote them under; the data source may not be registered yet), else from the data
        source's type and connection."""
        current = ss.current_source_system()
        if current:
            return current
        if config_id not in self._sources:
            doc = self.config_doc(config_id)
            config = _config_of(doc) if doc else None
            source_type = (config.source_type if config else "") or "filesystem"
            kwargs = {f"{source_type}_config": config.connection_params if config else {}}
            self._sources[config_id] = ss.source_system_for(source_type, kwargs)
        return self._sources[config_id]

    # ----- document state: lookups -----

    def docs_where(self, where: str) -> List[Dict[str, Any]]:
        return self.client.query_all(f"SELECT * FROM SysFile WHERE {where} AND {self.in_sources}")

    def docs_by_list(self, field: str, values: Iterable[str]) -> List[Dict[str, Any]]:
        """The documents whose list property ``field`` has any of ``values`` (each once)."""
        found: Dict[str, Dict[str, Any]] = {}
        for batch in _chunks(list(dict.fromkeys(values))):
            for doc in self.docs_where(f"{field} IN {_in(batch)}"):
                found[doc["sys_id"]] = doc
        return list(found.values())

    def doc_of(self, doc_id: str) -> Optional[Dict[str, Any]]:
        docs = self.client.query(
            f"SELECT * FROM SysFile WHERE fg_docstate_docIds = {hxql_literal(doc_id)} AND {self.in_sources}",
            limit=5)["documents"]
        return docs[0] if docs else None

    def source_doc(self, config_id: str, identity: str) -> Optional[Dict[str, Any]]:
        """The source document of an object, as the OpenArch store wrote it (by source system and
        identity)."""
        source_type, system = self.source_system(config_id)
        docs = self.client.query(
            f"SELECT * FROM SysFile WHERE cin_id = {hxql_literal(identity)} "
            f"AND cin_sourceId = {hxql_literal(ss.cin_source_id(source_type, system))} AND {self.in_sources}",
            limit=5)["documents"]
        return docs[0] if docs else None

    @staticmethod
    def entries(doc: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [dict(e) for e in (doc or {}).get("fg_docstate_states") or [] if e.get("docId")]

    # ----- document state: writes -----

    def _state_props(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "fg_docstate_states": entries,
            "fg_docstate_configIds": sorted({e["configId"] for e in entries if e.get("configId")}),
            "fg_docstate_docIds": [e["docId"] for e in entries],
            "fg_docstate_sourceIds": sorted({e["sourceId"] for e in entries if e.get("sourceId")}),
        }

    def write_entries(self, doc: Dict[str, Any], entries: List[Dict[str, Any]]) -> None:
        """Store a document's entries, conditional on its ``sys_ugen`` (OpenArchError 412 on a
        concurrent change). A document left with no entries, no content and no scope rule is
        deleted."""
        if not entries and not _has_content(doc) and not doc.get("fg_rule_path"):
            delete_with_chunks(self.client, doc["sys_id"])
            return
        body = self._state_props(entries)
        mixins = list(doc.get("sys_mixinTypes") or [])
        if STATE_MIXIN not in mixins:
            body["sys_mixinTypes"] = mixins + [STATE_MIXIN]
        self.client.update(doc["sys_id"], body, condition=f"sys_ugen = {int(doc.get('sys_ugen') or 0)}")

    def modify(self, doc: Dict[str, Any], change: Callable[[List[Dict[str, Any]]], Optional[List[Dict[str, Any]]]]) -> bool:
        """Apply ``change`` to a document's entries (it returns the new entries, or None for no
        change) and store them; on a concurrent change, read the document again and redo it.
        Returns whether anything changed."""
        for attempt in range(_RETRIES):
            new = change(self.entries(doc))
            if new is None:
                return False
            try:
                self.write_entries(doc, new)
                return True
            except OpenArchError as e:
                if e.status_code not in _CONFLICTS or attempt == _RETRIES - 1:
                    raise
            doc = self.client.get(doc["sys_id"])
            if doc is None:
                return False
        return False

    def modify_entry(self, doc_id: str, change: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]) -> bool:
        """Change one data source's entry of a document (``change`` returns the new entry, or
        None for no change)."""
        doc = self.doc_of(doc_id)
        if doc is None:
            return False

        def apply(entries):
            for i, entry in enumerate(entries):
                if entry["docId"] == doc_id:
                    new = change(dict(entry))
                    if new is None:
                        return None
                    entries[i] = dict(new, updatedAt=_now())
                    return entries
            return None
        return self.modify(doc, apply)

    def modify_entries(self, docs: Iterable[Dict[str, Any]],
                       change: Callable[[Dict[str, Any]], Any]) -> List[Dict[str, Any]]:
        """Apply ``change`` to every entry of ``docs``: it returns the entry (changed or not), or
        None to drop it. Returns the dropped entries."""
        dropped: List[Dict[str, Any]] = []

        for doc in docs:
            gone: List[Dict[str, Any]] = []

            def apply(entries):
                gone.clear()
                out, changed = [], False
                for entry in entries:
                    new = change(dict(entry))
                    if new is None:
                        gone.append(entry)
                        changed = True
                    elif new != entry:
                        out.append(dict(new, updatedAt=_now()))
                        changed = True
                    else:
                        out.append(entry)
                return out if changed else None
            self.modify(doc, apply)
            dropped.extend(gone)
        return dropped

    def place_state_doc(self, doc: Dict[str, Any], config_id: str, identity: str, source_path: str) -> Dict[str, Any]:
        """Move / rename a state-alone source document after its source object moved or was
        renamed; returns it at its new place (a new document when renamed). Documents the
        OpenArch store writes are placed by it (writer.write)."""
        if doc_ids_of(doc.get("cin_ingestProperties") or {}):
            return doc
        source_type, system = self.source_system(config_id)
        path = str(source_path or "")
        if "://" in path:
            path = path.split("://", 1)[1]
            if source_type in ("s3", "gcs") and path.split("/", 1)[0] == system:
                path = path.split("/", 1)[1] if "/" in path else ""
        name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        metadata = {"file_path": path, "human_file_path": path, "file_name": name, "s3_key": path}
        segments = ss.document_path(source_type, identity, metadata)
        return place_source_document(self.client, self.root_path, source_type, system, segments, doc)

    def create_state_doc(self, config_id: str, identity: str, source_path: str) -> Dict[str, Any]:
        """A source document for state alone (the OpenArch store has not written it), where the
        store would put it."""
        source_type, system = self.source_system(config_id)
        path = str(source_path or "")
        if "://" in path:
            path = path.split("://", 1)[1]
            if source_type in ("s3", "gcs") and path.split("/", 1)[0] == system:
                path = path.split("/", 1)[1] if "/" in path else ""
        name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        metadata = {"file_path": path, "human_file_path": path, "file_name": name, "s3_key": path}
        segments = ss.document_path(source_type, identity, metadata)
        body = {"sys_primaryType": "SysFile", "sys_mixinTypes": ["CinRemote", STATE_MIXIN],
                "sys_title": name or segments[-1], "cin_id": identity,
                "cin_sourceId": ss.cin_source_id(source_type, system), "cin_paths": [str(source_path or identity)]}
        return create_source_document(self.client, self.root_path, source_type, system, segments, body)


# Serializes this process's writes of one source object's state (conditional updates guard
# against other processes)
_object_locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
_object_locks_guard = threading.Lock()


def _object_lock(key: str) -> threading.Lock:
    with _object_locks_guard:
        return _object_locks[key]


# ── ConfigManager ────────────────────────────────────────────────────────────────────────────

class OpenArchConfigManager(ConfigManager):
    """ConfigManager on OpenArch data source documents."""

    postgres_url = None

    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.pool = None
        self.registry: Optional[OpenArchRegistry] = None

    async def initialize(self):
        self.registry = OpenArchRegistry(self.settings)
        await asyncio.to_thread(self.registry.initialize)

    async def close(self):
        if self.registry is not None:
            self.registry.close()

    async def ensure_ready(self) -> None:
        if self.registry is None:
            await self.initialize()

    async def _run(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def create_config(self, config: DataSourceConfig) -> str:
        """Create or refresh a data source (see ConfigManager.create_config): the caller's current
        settings win, sync progress is left as it is."""
        from uuid import uuid4
        if not config.config_id:
            config.config_id = str(uuid4())
        reg = self.registry

        def run():
            if reg.update_config_doc(
                    config.config_id, source_name=config.source_name, connection_params=config.connection_params,
                    refresh_interval_seconds=config.refresh_interval_seconds,
                    watchdog_filesystem_seconds=config.watchdog_filesystem_seconds,
                    enable_change_stream=config.enable_change_stream, graphs=config.graphs,
                    is_active=config.is_active, auto_sync=config.auto_sync):
                return
            reg.create_config_doc(config)
        await self._run(run)
        return config.config_id

    async def register_ingest_only(self, config: DataSourceConfig) -> None:
        reg = self.registry

        def run():
            doc = reg.config_doc(config.config_id)
            if doc is None:
                config.is_active, config.auto_sync = False, False
                reg.create_config_doc(config)
            elif doc.get("fg_datasource_autoSync") is False:
                reg.client.update(doc["sys_id"], _config_props(
                    source_name=config.source_name, connection_params=config.connection_params,
                    graphs=config.graphs))
            else:
                # An ingest that built a graph makes the auto sync of the same source build it
                # again (its graph may have been removed, which turned it off -- see removal.py)
                graphs, current = config.graphs, _config_of(doc).graphs
                if (graphs.graph and not current.graph) or (graphs.rdf and not current.rdf):
                    reg.client.update(doc["sys_id"], _config_props(graphs=current | graphs))
        await self._run(run)

    async def get_config(self, config_id: str) -> Optional[DataSourceConfig]:
        doc = await self._run(self.registry.config_doc, config_id)
        return _config_of(doc) if doc else None

    async def _configs(self, keep: Callable[[DataSourceConfig], bool]) -> List[DataSourceConfig]:
        docs = await self._run(self.registry.config_docs)
        return [c for c in map(_config_of, docs) if keep(c)]

    async def get_ingest_status_configs(self) -> List[DataSourceConfig]:
        return await self._configs(lambda c: c.is_active or not c.auto_sync)

    async def get_all_active_configs(self) -> List[DataSourceConfig]:
        return await self._configs(lambda c: c.is_active)

    async def get_paused_configs(self) -> List[DataSourceConfig]:
        return await self._configs(lambda c: not c.is_active and c.auto_sync)

    async def get_auto_sync(self, config_id: str) -> Optional[bool]:
        doc = await self._run(self.registry.config_doc, config_id)
        return None if doc is None else doc.get("fg_datasource_autoSync") is not False

    async def update_sync_status(self, config_id: str, status: str,
                                 ordinal: Optional[int] = None, error: Optional[str] = None):
        if status == "idle" and ordinal is not None:
            values = dict(sync_status=status, last_sync_ordinal=ordinal,
                          last_sync_completed_at=datetime.now(timezone.utc), last_error=None)
        elif status == "error":
            values = dict(sync_status=status, last_error=error)
        else:
            values = dict(sync_status=status)
        await self._run(self.registry.update_config_doc, config_id, **values)

    async def update_config(self, config_id: str, **kwargs):
        allowed = {"source_name", "connection_params", "refresh_interval_seconds",
                   "enable_change_stream", "is_active", "skip_graph", "auto_sync",
                   "enabled_graph", "enabled_rdf", "graphs"}
        values = {k: v for k, v in kwargs.items() if k in allowed}
        if values:
            await self._run(self.registry.update_config_doc, config_id, **values)

    async def delete_config(self, config_id: str):
        await self._run(self.registry.delete_config_doc, config_id)

    async def count_documents_by_config(self) -> Dict[str, int]:
        """How many documents each data source has (its data source state entries)."""
        reg = self.registry

        def run():
            counts: Dict[str, int] = defaultdict(int)
            for doc in reg.docs_where("fg_docstate_docIds IS NOT NULL"):
                for entry in reg.entries(doc):
                    if entry.get("configId"):
                        counts[entry["configId"]] += 1
            return dict(counts)
        return await self._run(run)

    async def count_governed_documents_by_config(self, schemes) -> Dict[str, int]:
        """How many documents each data source has whose doc id carries a repository id (``alfresco://``,
        ``nuxeo://``, ``cmis://``): the ones query-time permission checks govern (see ConfigManager)."""
        reg = self.registry
        schemes = list(schemes)

        def run():
            counts: Dict[str, int] = defaultdict(int)
            for doc in reg.docs_where("fg_docstate_docIds IS NOT NULL"):
                for entry in reg.entries(doc):
                    doc_id = entry.get("docId") or ""
                    if entry.get("configId") and any(s in doc_id for s in schemes):
                        counts[entry["configId"]] += 1
            return dict(counts)
        return await self._run(run)

    def follows_rules(self, source_type: str) -> bool:
        return source_type in ROOT_SOURCES

    async def apply_rule_roots(self, source_type: str) -> List[Tuple[DataSourceConfig, str]]:
        """Point each auto sync of ``source_type`` at the objects its rules follow
        (openarch/scope.py connection_roots), stored as its roots. Returns ``(config, outcome)``
        for those that change: "updated" (new roots stored) or "empty" (nothing left to follow).
        A sync no rule names yet (registered before rules named their followers) is named on the
        rules of its roots when they all have one, else keeps its roots as stored."""
        from incremental_updates.ingest_status import Datasource, Item
        if not self.follows_rules(source_type):
            return []
        reg = self.registry

        def run():
            out = []
            for doc in reg.config_docs():
                cfg = _config_of(doc)
                if cfg.source_type != source_type or not cfg.auto_sync:
                    continue
                cin = ss.cin_source_id(*ss.source_system_for(
                    source_type, {f"{source_type}_config": cfg.connection_params}))
                roots = reg.scope.connection_roots(cin, cfg.config_id)
                if roots is None and not doc.get("fg_datasource_followsRules"):
                    stored = [Item(r.path, r.is_folder, r.node_id) for r in Datasource.from_config(cfg).roots]
                    if not reg.scope.claim_roots(cin, cfg.config_id, stored):
                        continue
                    roots = reg.scope.connection_roots(cin, cfg.config_id)
                if not doc.get("fg_datasource_followsRules"):
                    # from now on its roots are the rules' (a rule handed to another sync goes)
                    reg.client.update(doc["sys_id"], {"fg_datasource_followsRules": True})
                if not roots:
                    out.append((cfg, "empty"))
                    continue
                params = roots_params(source_type, cfg.connection_params, roots)
                if params != cfg.connection_params:
                    reg.update_config_doc(cfg.config_id, connection_params=params)
                    cfg.connection_params = params
                    out.append((cfg, "updated"))
            return out
        return await self._run(run)


# ── StateManager ─────────────────────────────────────────────────────────────────────────────

class OpenArchStateManager(StateManager):
    """StateManager on the source documents' ``FgDocState`` entries."""

    postgres_url = None

    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.pool = None
        self.registry: Optional[OpenArchRegistry] = None

    async def initialize(self):
        self.registry = OpenArchRegistry(self.settings)
        await asyncio.to_thread(self.registry.initialize)

    async def close(self):
        if self.registry is not None:
            self.registry.close()

    async def _run(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    # ----- one document -----

    def _entry(self, doc_id: str) -> Optional[Dict[str, Any]]:
        doc = self.registry.doc_of(doc_id)
        return next((e for e in self.registry.entries(doc) if e["docId"] == doc_id), None)

    async def get_state(self, doc_id: str) -> Optional[DocumentState]:
        entry = await self._run(self._entry, doc_id)
        return _state_of(entry) if entry else None

    async def get_state_by_source_id(self, config_id: str, source_id: str) -> Optional[DocumentState]:
        def run():
            docs = self.registry.client.query(
                f"SELECT * FROM SysFile WHERE fg_docstate_configIds = {hxql_literal(config_id)} "
                f"AND fg_docstate_sourceIds = {hxql_literal(source_id)} AND {self.registry.in_sources}",
                limit=5)["documents"]
            for doc in docs:
                for entry in self.registry.entries(doc):
                    if entry.get("configId") == config_id and entry.get("sourceId") == source_id:
                        return entry
            return None
        entry = await self._run(run)
        return _state_of(entry) if entry else None

    def _config_entries(self, config_ids: Iterable[str]) -> List[Dict[str, Any]]:
        wanted = set(config_ids)
        return [e for doc in self.registry.docs_by_list("fg_docstate_configIds", wanted)
                for e in self.registry.entries(doc) if e.get("configId") in wanted]

    async def get_all_states_for_config(self, config_id: str) -> List[DocumentState]:
        return [_state_of(e) for e in await self._run(self._config_entries, [config_id])]

    async def save_state(self, state: DocumentState):
        """Save or update a data source's state of a document (StateManager.save_state's
        semantics), creating the source document when the OpenArch store has not."""
        def update(entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            now = _now()
            new = {
                "docId": state.doc_id, "configId": state.config_id, "sourcePath": state.source_path,
                "sourceId": state.source_id or (entry or {}).get("sourceId"),
                "ordinal": int(state.ordinal or 0), "contentHash": state.content_hash,
                "modifiedAt": _iso(state.modified_timestamp),
                "vectorSyncedAt": _iso(state.vector_synced_at), "searchSyncedAt": _iso(state.search_synced_at),
                "graphSyncedAt": _iso(state.graph_synced_at), "rdfSyncedAt": _iso(state.rdf_synced_at),
                "createdAt": (entry or {}).get("createdAt") or now, "updatedAt": now,
            }
            # per graph: what the state says, else the entry's (back on when this save wrote it);
            # the older skip_graph alone means both off
            eg, er = state.enabled_graph, state.enabled_rdf
            if state.skip_graph and eg is None and er is None:
                eg = er = False
            if entry is None:
                new["autoSync"] = True if state.auto_sync is None else bool(state.auto_sync)
                g = True if eg is None else bool(eg)
                r = True if er is None else bool(er)
            else:
                new["autoSync"] = (entry.get("autoSync") is not False) if state.auto_sync is None else bool(state.auto_sync)
                was = _entry_graphs(entry)
                g = bool(eg) if eg is not None else (was.graph or state.graph_synced_at is not None)
                r = bool(er) if er is not None else (was.rdf or state.rdf_synced_at is not None)
            new["enabledGraph"], new["enabledRdf"], new["skipGraph"] = g, r, not (g or r)
            return {k: v for k, v in new.items() if v is not None}

        moved = []

        def apply(entries):
            for i, entry in enumerate(entries):
                if entry["docId"] == state.doc_id:
                    if entry.get("sourcePath") and state.source_path and entry["sourcePath"] != state.source_path:
                        moved.append(True)
                    entries[i] = update(entry)
                    return entries
            return entries + [update(None)]

        def run():
            identity = _identity(state.doc_id, state.config_id)
            with _object_lock(identity):
                reg = self.registry
                doc = reg.doc_of(state.doc_id) or reg.source_doc(state.config_id, identity)
                if doc is None:
                    try:
                        doc = reg.create_state_doc(state.config_id, identity, state.source_path)
                    except OpenArchError as e:
                        if e.status_code != 409:
                            raise
                        doc = reg.source_doc(state.config_id, identity)
                        if doc is None:
                            raise
                reg.modify(doc, apply)
                if moved:  # its source object was moved or renamed: so is its document
                    fresh = reg.client.get(doc["sys_id"])
                    if fresh:
                        doc = reg.place_state_doc(fresh, state.config_id, identity, state.source_path)
                # its effective flags, when its source system has scope rules
                rules = reg.scope.rules(doc.get("cin_sourceId") or "")
                if rules:
                    doc = reg.client.get(doc["sys_id"])
                    props = reg.scope.effective_props(rules, doc) if doc else {}
                    if doc and any(doc.get(k) != v for k, v in props.items()):
                        reg.update_with_mixin(doc, FLAGS_MIXIN, props)
        await self._run(run)

    async def mark_target_synced(self, doc_id: str, target: str):
        field = TARGET_FIELDS.get(target)
        if field:
            await self._run(self.registry.modify_entry, doc_id, lambda e: dict(e, **{field: _now()}))

    # ----- scope rules (openarch/scope.py) decide where they set a flag; else the entry -----

    def _doc_and_entry(self, doc_id: str):
        doc = self.registry.doc_of(doc_id)
        return doc, next((e for e in self.registry.entries(doc) if e["docId"] == doc_id), None)

    async def sync_off(self, doc_id: str) -> bool:
        """Whether the sync skips this document: its effective ``autoSync`` (scope rules), else
        its own entry's auto sync."""
        doc, entry = await self._run(self._doc_and_entry, doc_id)
        if doc is not None and doc.get(EFFECTIVE["autoSync"]) is not None:
            return doc[EFFECTIVE["autoSync"]] is False
        return bool(entry) and entry.get("autoSync") is False

    @staticmethod
    def _graphs_of(doc: Optional[Dict[str, Any]], entry: Optional[Dict[str, Any]]):
        """A document's own graphs: its effective flags (scope rules) where a rule says, else its
        entry's."""
        from graph_flags import GraphFlags
        own = _entry_graphs(entry)
        eff = {f: (doc or {}).get(EFFECTIVE[f]) for f in ("pgGraph", "rdfGraph")}
        return GraphFlags(own.graph if eff["pgGraph"] is None else bool(eff["pgGraph"]),
                          own.rdf if eff["rdfGraph"] is None else bool(eff["rdfGraph"]))

    async def doc_graphs(self, doc_id: Optional[str] = None, config_id: Optional[str] = None,
                         source_id: Optional[str] = None):
        """This document's own graphs (graph_flags.GraphFlags): its effective graph flags (scope
        rules), else its own entry's; by doc_id or by (config_id, source_id)."""
        from graph_flags import GraphFlags
        if doc_id:
            doc, entry = await self._run(self._doc_and_entry, doc_id)
            return self._graphs_of(doc, entry)

        def run():
            docs = self.registry.client.query(
                f"SELECT * FROM SysFile WHERE fg_docstate_configIds = {hxql_literal(config_id)} "
                f"AND fg_docstate_sourceIds = {hxql_literal(source_id)} AND {self.registry.in_sources}",
                limit=20)["documents"]
            out = GraphFlags()
            for d in docs:
                for e in self.registry.entries(d):
                    if e.get("configId") == config_id and e.get("sourceId") == source_id:
                        out = out & self._graphs_of(d, e)
            return out
        return await self._run(run)

    async def doc_skip_graph(self, doc_id: Optional[str] = None, config_id: Optional[str] = None,
                             source_id: Optional[str] = None) -> bool:
        """Whether this document leaves both graphs out (the older single flag; doc_graphs)."""
        return (await self.doc_graphs(doc_id, config_id, source_id)).none

    async def document_scope(self, config_id: str, path: Optional[str], source_id: Optional[str] = None,
                             ancestor_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """StateManager.document_scope from the scope rules of the data source's source system:
        the document's nearest rules decide (by node id, its ancestors' ids, or its path)."""
        from incremental_updates.removal import StateRow

        def run():
            reg = self.registry
            rules = reg.scope.rules(ss.cin_source_id(*reg.source_system(config_id)))
            if not rules:
                return {"follow": True, "graph": None, "rdf": None, "skip_graph": None, "reason": None}
            row = StateRow(doc_id="", config_id=config_id, source_id=source_id, source_path=path or "", synced={})
            return sync_decision(effective_flags(rules, row, ancestor_ids))
        return await self._run(run)

    async def clear_targets(self, doc_id: str):
        def clear(entry):
            for f in TARGET_FIELDS.values():
                entry.pop(f, None)
            return entry
        await self._run(self.registry.modify_entry, doc_id, clear)

    async def mark_deleted(self, doc_id: str):
        def run():
            doc = self.registry.doc_of(doc_id)
            if doc is not None:
                self.registry.modify(doc, lambda entries: [e for e in entries if e["docId"] != doc_id])
        await self._run(run)

    async def _update_ordinal_only(self, doc_id: str, new_ordinal: int, modified_timestamp: Optional[datetime] = None):
        def change(entry):
            entry["ordinal"] = int(new_ordinal)
            if modified_timestamp is not None:
                entry["modifiedAt"] = _iso(modified_timestamp)
            return entry
        await self._run(self.registry.modify_entry, doc_id, change)

    async def _update_hash_only(self, doc_id: str, content_hash: str, new_ordinal: int):
        await self._run(self.registry.modify_entry, doc_id,
                        lambda e: dict(e, contentHash=content_hash, ordinal=int(new_ordinal)))

    async def _update_source_path(self, doc_id: str, new_source_path: str):
        await self._run(self.registry.modify_entry, doc_id, lambda e: dict(e, sourcePath=new_source_path))

    async def get_sync_stats(self, config_id: str) -> Dict:
        entries = await self._run(self._config_entries, [config_id])
        return {"total_docs": len(entries),
                **{f"{t}_synced": sum(1 for e in entries if e.get(f)) for t, f in TARGET_FIELDS.items()}}

    # ----- registry queries -----

    async def doc_ids_for_config(self, config_id: str) -> List[str]:
        return [e["docId"] for e in await self._run(self._config_entries, [config_id])]

    async def known_doc_ids(self, doc_ids: List[str]) -> Set[str]:
        wanted = set(doc_ids)

        def run():
            return {d for doc in self.registry.docs_by_list("fg_docstate_docIds", wanted)
                    for d in doc.get("fg_docstate_docIds") or [] if d in wanted}
        return await self._run(run)

    async def fetch_rows(self, config_ids: List[str]) -> list:
        return [_row_of(e) for e in await self._run(self._config_entries, config_ids)]

    async def set_auto_sync(self, doc_ids: Iterable[str], value: bool) -> int:
        ids = list(dict.fromkeys(doc_ids))
        if not ids:
            return 0
        wanted = set(ids)

        def run():
            docs = self.registry.docs_by_list("fg_docstate_docIds", wanted)
            self.registry.modify_entries(
                docs, lambda e: dict(e, autoSync=bool(value)) if e["docId"] in wanted else e)
        await self._run(run)
        return len(ids)

    def _drop_empty_ingest_only(self, config_ids: Iterable[str]) -> List[str]:
        """Delete ingest-only data sources left with no documents; returns their ids."""
        reg, dropped = self.registry, []
        for config_id in set(config_ids):
            doc = reg.config_doc(config_id)
            if doc is None or doc.get("fg_datasource_autoSync") is not False:
                continue
            if not reg.client.query(f"SELECT * FROM SysFile WHERE fg_docstate_configIds = {hxql_literal(config_id)} "
                                    f"AND {reg.in_sources}", limit=1)["documents"]:
                reg.client.delete(doc["sys_id"])
                dropped.append(config_id)
        return dropped

    async def record_removal(self, rows: Iterable[Any], targets: Iterable[str],
                             auto_sync_configs: Iterable[str]) -> Dict[str, int]:
        """StateManager.record_removal on the documents' entries."""
        rows, targets = list(rows), [t for t in targets if t in TARGET_FIELDS]
        doc_ids = set(r.doc_id for r in rows)
        if not doc_ids or not targets:
            return {"forgotten": 0, "datasources_dropped": 0, "datasources_now_skip_graph": 0}
        syncs = set(auto_sync_configs)
        reg = self.registry

        def change(entry):
            if entry["docId"] not in doc_ids:
                return entry
            for t in targets:
                entry.pop(TARGET_FIELDS[t], None)
            # per graph: the sync leaves a removed graph out for this document from now on
            if "graph" in targets or "rdf" in targets:
                was = _entry_graphs(entry)
                g = was.graph and "graph" not in targets
                r = was.rdf and "rdf" not in targets
                entry["enabledGraph"], entry["enabledRdf"], entry["skipGraph"] = g, r, not (g or r)
            if not _in_store(entry):
                if entry.get("configId") in syncs:
                    entry["autoSync"] = False
                else:
                    return None  # an ingest-only row with nothing left: forgotten
            return entry

        def run():
            forgotten = reg.modify_entries(reg.docs_by_list("fg_docstate_docIds", doc_ids), change)
            dropped = self._drop_empty_ingest_only(e.get("configId") for e in forgotten)
            # a datasource with documents in vector + search but none left in a graph no longer
            # builds that graph (see StateManager.record_removal)
            graph_off = []
            for config_id in {r.config_id for r in rows}:
                if "graph" not in targets and "rdf" not in targets:
                    break
                doc = reg.config_doc(config_id)
                if doc is None:
                    continue
                current = _config_of(doc).graphs
                entries = self._config_entries([config_id])
                if not any(e.get("vectorSyncedAt") or e.get("searchSyncedAt") for e in entries):
                    continue
                # only a graph this removal took a document out of (see StateManager.record_removal)
                held = {t for t in ("graph", "rdf") if t in targets and any(
                    r.config_id == config_id and r.synced.get(t) for r in rows)}
                g = current.graph and not ("graph" in held and not any(e.get("graphSyncedAt") for e in entries))
                r = current.rdf and not ("rdf" in held and not any(e.get("rdfSyncedAt") for e in entries))
                if (g, r) != (current.graph, current.rdf):
                    from graph_flags import GraphFlags
                    reg.client.update(doc["sys_id"], _config_props(graphs=GraphFlags(g, r)))
                    graph_off.append(config_id)
            return {"forgotten": len(forgotten), "datasources_dropped": len(dropped),
                    "datasources_now_skip_graph": len(graph_off)}
        return await self._run(run)

    async def retire_datasource(self, config_id: str) -> str:
        reg = self.registry

        def run():
            if any(_in_store(e) for e in self._config_entries([config_id])):
                reg.update_config_doc(config_id, auto_sync=False, is_active=False)
                return "ingest-only"
            reg.modify_entries(reg.docs_by_list("fg_docstate_configIds", [config_id]),
                               lambda e: None if e.get("configId") == config_id else e)
            reg.delete_config_doc(config_id)
            return "deleted"
        return await self._run(run)

    async def resolve_duplicate_copies(self, config_id: str, sync_takeover: bool = False) -> list:
        """StateManager.resolve_duplicate_copies: here the copies of one source object are the
        entries of different data sources on its one document."""
        reg = self.registry

        def run():
            auto_sync: Dict[str, Optional[bool]] = {}

            def is_sync(cid: str) -> Optional[bool]:
                if cid not in auto_sync:
                    doc = reg.config_doc(cid)
                    auto_sync[cid] = None if doc is None else doc.get("fg_datasource_autoSync") is not False
                return auto_sync[cid]

            mine_is_sync = is_sync(config_id)
            losers: Dict[str, str] = {}  # doc id -> config id
            counts = {"others": 0, "mine": 0}
            for doc in reg.docs_by_list("fg_docstate_configIds", [config_id]):
                entries = reg.entries(doc)
                for mine in (e for e in entries if e.get("configId") == config_id):
                    for other in entries:
                        oc = other.get("configId")
                        if oc == config_id or _identity(other["docId"], oc) != _identity(mine["docId"], config_id):
                            continue
                        other_sync = is_sync(oc)
                        mine_on = mine.get("autoSync") is not False
                        # another ingest-only copy is superseded by this one
                        if other_sync is False:
                            losers[other["docId"]] = oc
                            counts["others"] += 1
                        # an auto sync following its copy keeps it over this ingest-only (or
                        # not followed) one
                        if (other_sync and other.get("autoSync") is not False and mine_is_sync is not None
                                and (mine_is_sync is False or not mine_on)):
                            if mine["docId"] not in losers:
                                counts["mine"] += 1
                            losers[mine["docId"]] = config_id
                        # a new auto sync takes the copies of other auto syncs over
                        if sync_takeover and other_sync and mine_is_sync and mine_on:
                            losers[other["docId"]] = oc
            if not losers:
                return []
            reg.modify_entries(reg.docs_by_list("fg_docstate_docIds", losers),
                               lambda e: None if e["docId"] in losers else e)
            emptied = self._drop_empty_ingest_only(set(losers.values()))
            logger.info(
                f"{config_id}: {counts['others']} older ingest cop(ies) superseded, {counts['mine']} "
                f"document(s) left to the auto-sync that already holds them; {len(emptied)} emptied "
                f"ingest record(s) removed")
            return list(losers)
        return await self._run(run)

    async def registry_rows(self, doc_ids: List[str]) -> Dict[str, dict]:
        wanted = set(doc_ids)
        reg = self.registry

        def run():
            out, configs = {}, {}
            for doc in reg.docs_by_list("fg_docstate_docIds", wanted):
                for entry in reg.entries(doc):
                    if entry["docId"] not in wanted:
                        continue
                    cid = entry.get("configId") or ""
                    if cid not in configs:
                        cdoc = reg.config_doc(cid) if cid else None
                        configs[cid] = _config_of(cdoc) if cdoc else None
                    config = configs[cid]
                    out[entry["docId"]] = {
                        "source_id": entry.get("sourceId"), "source_path": entry.get("sourcePath") or "",
                        "source_type": config.source_type if config else "",
                        "connection_params": config.connection_params if config else {}}
            return out
        return await self._run(run)

    async def load_sync_cursor(self, config_id: str) -> Optional[str]:
        doc = await self._run(self.registry.config_doc, config_id)
        return (doc or {}).get("fg_datasource_syncCursor") or None

    async def save_sync_cursor(self, config_id: str, cursor: str) -> None:
        def run():
            doc = self.registry.config_doc(config_id)
            if doc is not None:
                self.registry.client.update(doc["sys_id"], {"fg_datasource_syncCursor": cursor})
        await self._run(run)


def remove_registry(settings: Dict[str, Any]) -> Dict[str, int]:
    """Delete the data source documents, the scope rules and every document's data source
    state (scripts/cleanup.py): documents left with no content go too. Returns counts."""
    reg = OpenArchRegistry(settings)
    try:
        reg.initialize()  # the queries below name our schemas' fields
        for doc in reg.client.query_all(f"SELECT * FROM SysContent WHERE fg_rule_sourceId IS NOT NULL AND {reg.in_sources}"):
            reg.scope._clear(doc["sys_id"])
        configs = 0
        for doc in reg.config_docs():
            reg.client.delete(doc["sys_id"])
            configs += 1
        states = 0
        for doc in reg.docs_where("fg_docstate_docIds IS NOT NULL"):
            reg.modify(doc, lambda entries: [] if entries else None)
            states += 1
        return {"datasources": configs, "documents": states}
    finally:
        reg.close()
