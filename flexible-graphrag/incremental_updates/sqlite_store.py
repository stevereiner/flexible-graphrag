"""The incremental registry in a SQLite file (INCREMENTAL_STATE_STORE=sqlite): the same
``datasource_config``, ``document_state`` and ``msgraph_delta_state`` tables as PostgreSQL, for a
setup with no database server (the desktop app, a laptop). Python's own sqlite3, nothing to
install.

The file is SQLITE_INCREMENTAL_PATH (default ``./flexible_graphrag_incremental.db``, relative to
the folder the backend runs in). One connection per file is shared by every manager in the
process, behind a lock; each call is one transaction, run off the event loop. WAL mode, so
reads don't wait for a write; another process on the same file waits up to 30 s for a write.

SqliteConfigManager / SqliteStateManager subclass the PostgreSQL managers and replace only their
SQL, so the decisions made in Python (should_process, the path fallback, scope) stay shared.
Booleans are stored as 0 / 1 and timestamps as ISO 8601 UTC text; both come back as bool and
timezone-aware datetime. Lists are passed as one JSON array (``json_each``), not one parameter
per item.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from incremental_updates.config_manager import ConfigManager, DataSourceConfig, graph_columns, graph_updates
from incremental_updates.state_manager import DocumentState, StateManager, logger

DEFAULT_PATH = "./flexible_graphrag_incremental.db"
# RETURNING (3.35); upsert, json_each, FILTER and TRUE / FALSE come earlier
MIN_SQLITE = (3, 35, 0)

_SQL_NOW = "(strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'))"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS datasource_config (
    config_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    connection_params TEXT NOT NULL,
    refresh_interval_seconds INTEGER NOT NULL DEFAULT 3600,
    watchdog_filesystem_seconds INTEGER NOT NULL DEFAULT 60,
    enable_change_stream INTEGER NOT NULL DEFAULT 0,
    skip_graph INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    auto_sync INTEGER NOT NULL DEFAULT 1,
    enabled_graph INTEGER,
    enabled_rdf INTEGER,
    sync_status TEXT NOT NULL DEFAULT 'idle',
    last_sync_ordinal INTEGER,
    last_sync_completed_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT {_SQL_NOW},
    updated_at TEXT NOT NULL DEFAULT {_SQL_NOW}
);
CREATE INDEX IF NOT EXISTS idx_datasource_config_project_id ON datasource_config(project_id);
CREATE INDEX IF NOT EXISTS idx_datasource_config_is_active ON datasource_config(is_active);

CREATE TABLE IF NOT EXISTS document_state (
    doc_id TEXT PRIMARY KEY,
    config_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_id TEXT,
    ordinal INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    modified_timestamp TEXT,
    vector_synced_at TEXT,
    search_synced_at TEXT,
    graph_synced_at TEXT,
    rdf_synced_at TEXT,
    auto_sync INTEGER NOT NULL DEFAULT 1,
    skip_graph INTEGER NOT NULL DEFAULT 0,
    enabled_graph INTEGER NOT NULL DEFAULT 1,
    enabled_rdf INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT {_SQL_NOW},
    updated_at TEXT NOT NULL DEFAULT {_SQL_NOW}
);
CREATE INDEX IF NOT EXISTS idx_document_state_config_id ON document_state(config_id);
CREATE INDEX IF NOT EXISTS idx_document_state_ordinal ON document_state(config_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_document_state_source_id ON document_state(config_id, source_id);

CREATE TABLE IF NOT EXISTS msgraph_delta_state (
    config_id TEXT PRIMARY KEY,
    delta_link TEXT,
    updated_at TEXT NOT NULL DEFAULT {_SQL_NOW}
);
"""

_BOOL_COLUMNS = {"enable_change_stream", "skip_graph", "is_active", "auto_sync", "enabled_graph", "enabled_rdf"}
_TIME_COLUMNS = {"last_sync_completed_at", "created_at", "updated_at", "modified_timestamp",
                 "vector_synced_at", "search_synced_at", "graph_synced_at", "rdf_synced_at"}

# "x IN (SELECT value FROM json_each(?))" with one JSON array parameter
_IN = "IN (SELECT value FROM json_each(?))"


def sqlite_path() -> str:
    return os.getenv("SQLITE_INCREMENTAL_PATH", "").strip() or DEFAULT_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _ts(value: Any) -> Optional[str]:
    """A timestamp to store: ISO 8601 in UTC (a naive datetime is taken as UTC)."""
    value = StateManager._ensure_datetime(value)
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _decode(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """A row as a dict, with its 0 / 1 flags as bool and its timestamps as datetime."""
    if row is None:
        return None
    out = {}
    for key in row.keys():
        value = row[key]
        if value is not None and key in _BOOL_COLUMNS:
            value = bool(value)
        elif key in _TIME_COLUMNS:
            value = _parse_ts(value)
        out[key] = value
    return out


def _ids(values: Iterable[str]) -> str:
    return json.dumps(list(values))


class _Database:
    """One file's shared connection: opened by the first manager, closed by the last."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        self.users = 0
        self.conn: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        with self.lock:
            if self.conn is None:
                if tuple(sqlite3.sqlite_version_info) < MIN_SQLITE:
                    raise RuntimeError(
                        f"SQLite {sqlite3.sqlite_version} is too old for INCREMENTAL_STATE_STORE=sqlite "
                        f"(needs {'.'.join(map(str, MIN_SQLITE))}+)")
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.executescript(_SCHEMA)
                self.conn = conn
            self.users += 1

    def close(self) -> None:
        with self.lock:
            self.users = max(0, self.users - 1)
            if self.users == 0 and self.conn is not None:
                self.conn.close()
                self.conn = None

    @property
    def is_open(self) -> bool:
        return self.conn is not None

    def run(self, work: Callable[[sqlite3.Connection], Any], write: bool) -> Any:
        """``work`` in one transaction (BEGIN IMMEDIATE when it writes)."""
        with self.lock:
            conn = self.conn
            if conn is None:
                raise RuntimeError(f"SQLite registry {self.path} is closed")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                result = work(conn)
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
            return result


_databases: Dict[str, _Database] = {}
_databases_lock = threading.Lock()


def _database(path: str) -> _Database:
    key = os.path.normcase(os.path.abspath(path))
    with _databases_lock:
        db = _databases.get(key)
        if db is None:
            db = _databases[key] = _Database(os.path.abspath(path))
        return db


class _SqliteBase:
    """The connection handling both managers share."""

    def _setup(self, path: Optional[str]) -> None:
        self.path = path or sqlite_path()
        self.db = _database(self.path)
        self._opened = False
        self.pool = None  # the PostgreSQL managers' attribute; nothing here

    async def initialize(self):
        if not self._opened:
            await asyncio.to_thread(self.db.open)
            self._opened = True

    async def close(self):
        if self._opened:
            self._opened = False
            await asyncio.to_thread(self.db.close)

    async def ensure_ready(self) -> None:
        """Reopen the file if it was closed."""
        if not self._opened or not self.db.is_open:
            self._opened = False
            await self.initialize()

    async def _read(self, work):
        return await asyncio.to_thread(self.db.run, work, False)

    async def _write(self, work):
        return await asyncio.to_thread(self.db.run, work, True)


class SqliteConfigManager(_SqliteBase, ConfigManager):
    """ConfigManager on a SQLite file."""

    def __init__(self, path: Optional[str] = None):
        self._setup(path)

    async def _create_schema(self):
        pass  # done when the file is opened

    def _configs(self, conn, sql: str, params=()) -> List[DataSourceConfig]:
        return [self._row_to_config(_decode(r)) for r in conn.execute(sql, params).fetchall()]

    async def create_config(self, config: DataSourceConfig) -> str:
        if not config.config_id:
            from uuid import uuid4
            config.config_id = str(uuid4())
        g, r, skip = graph_columns(config.graphs)
        now = _now()

        def work(conn):
            conn.execute("""
                INSERT INTO datasource_config
                (config_id, project_id, source_type, source_name, connection_params,
                 refresh_interval_seconds, watchdog_filesystem_seconds, enable_change_stream, skip_graph,
                 is_active, auto_sync, enabled_graph, enabled_rdf, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (config_id) DO UPDATE
                    SET source_name                 = excluded.source_name,
                        connection_params           = excluded.connection_params,
                        refresh_interval_seconds    = excluded.refresh_interval_seconds,
                        watchdog_filesystem_seconds = excluded.watchdog_filesystem_seconds,
                        enable_change_stream        = excluded.enable_change_stream,
                        skip_graph                  = excluded.skip_graph,
                        enabled_graph               = excluded.enabled_graph,
                        enabled_rdf                 = excluded.enabled_rdf,
                        is_active                   = excluded.is_active,
                        auto_sync                   = excluded.auto_sync,
                        updated_at                  = excluded.updated_at
            """, (config.config_id, config.project_id, config.source_type, config.source_name,
                  json.dumps(config.connection_params), config.refresh_interval_seconds,
                  config.watchdog_filesystem_seconds, config.enable_change_stream, skip,
                  config.is_active, config.auto_sync, g, r, now, now))
        await self._write(work)
        return config.config_id

    async def get_config(self, config_id: str) -> Optional[DataSourceConfig]:
        def work(conn):
            row = conn.execute("SELECT * FROM datasource_config WHERE config_id = ?", (config_id,)).fetchone()
            return self._row_to_config(_decode(row)) if row else None
        return await self._read(work)

    async def get_ingest_status_configs(self) -> List[DataSourceConfig]:
        return await self._read(lambda conn: self._configs(
            conn, "SELECT * FROM datasource_config WHERE is_active = TRUE OR auto_sync = FALSE ORDER BY created_at"))

    async def count_documents_by_config(self) -> Dict[str, int]:
        def work(conn):
            rows = conn.execute("SELECT config_id, COUNT(*) AS n FROM document_state GROUP BY config_id")
            return {r["config_id"]: r["n"] for r in rows.fetchall()}
        return await self._read(work)

    async def count_governed_documents_by_config(self, schemes) -> Dict[str, int]:
        # case-sensitive substring match, like PostgreSQL's LIKE (SQLite's LIKE ignores case)
        def work(conn):
            rows = conn.execute(
                "SELECT config_id, COUNT(*) AS n FROM document_state "
                "WHERE EXISTS (SELECT 1 FROM json_each(?) WHERE instr(document_state.doc_id, value) > 0) "
                "GROUP BY config_id", (_ids(schemes),))
            return {r["config_id"]: r["n"] for r in rows.fetchall()}
        return await self._read(work)

    async def get_all_active_configs(self) -> List[DataSourceConfig]:
        return await self._read(lambda conn: self._configs(
            conn, "SELECT * FROM datasource_config WHERE is_active = TRUE ORDER BY created_at"))

    async def update_sync_status(self, config_id: str, status: str, ordinal: Optional[int] = None,
                                 error: Optional[str] = None):
        now = _now()

        def work(conn):
            if status == "idle" and ordinal is not None:
                conn.execute("UPDATE datasource_config SET sync_status = ?, last_sync_ordinal = ?, "
                             "last_sync_completed_at = ?, last_error = NULL, updated_at = ? WHERE config_id = ?",
                             (status, ordinal, now, now, config_id))
            elif status == "error":
                conn.execute("UPDATE datasource_config SET sync_status = ?, last_error = ?, updated_at = ? "
                             "WHERE config_id = ?", (status, error, now, config_id))
            else:
                conn.execute("UPDATE datasource_config SET sync_status = ?, updated_at = ? WHERE config_id = ?",
                             (status, now, config_id))
        await self._write(work)

    async def update_config(self, config_id: str, **kwargs):
        allowed_fields = {
            'source_name', 'connection_params', 'refresh_interval_seconds',
            'enable_change_stream', 'is_active', 'skip_graph', 'auto_sync', 'enabled_graph', 'enabled_rdf'
        }
        updates, values = [], []
        for key, value in graph_updates(kwargs).items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                values.append(json.dumps(value) if key == "connection_params" else value)
        if not updates:
            return
        values += [_now(), config_id]
        sql = f"UPDATE datasource_config SET {', '.join(updates)}, updated_at = ? WHERE config_id = ?"
        await self._write(lambda conn: conn.execute(sql, values))

    async def register_ingest_only(self, config: DataSourceConfig) -> None:
        graphs = config.graphs
        g, r, skip = graph_columns(graphs)
        now = _now()

        def work(conn):
            conn.execute("""
                INSERT INTO datasource_config
                (config_id, project_id, source_type, source_name, connection_params,
                 skip_graph, is_active, auto_sync, enabled_graph, enabled_rdf, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, FALSE, FALSE, ?, ?, ?, ?)
                ON CONFLICT (config_id) DO UPDATE
                    SET source_name       = excluded.source_name,
                        connection_params = excluded.connection_params,
                        skip_graph        = excluded.skip_graph,
                        enabled_graph     = excluded.enabled_graph,
                        enabled_rdf       = excluded.enabled_rdf,
                        updated_at        = excluded.updated_at
                    WHERE datasource_config.auto_sync = FALSE
            """, (config.config_id, config.project_id, config.source_type, config.source_name,
                  json.dumps(config.connection_params), skip, g, r, now, now))
            # An ingest that built a graph makes an auto sync of the same source build it again
            # (its graph may have been removed, which turned it off -- see removal.py)
            if graphs.graph or graphs.rdf:
                conn.execute(
                    "UPDATE datasource_config SET skip_graph = FALSE, "
                    "enabled_graph = CASE WHEN ? THEN TRUE ELSE enabled_graph END, "
                    "enabled_rdf = CASE WHEN ? THEN TRUE ELSE enabled_rdf END, updated_at = ? "
                    "WHERE config_id = ? AND auto_sync = TRUE",
                    (bool(graphs.graph), bool(graphs.rdf), now, config.config_id))
        await self._write(work)

    async def get_auto_sync(self, config_id: str) -> Optional[bool]:
        def work(conn):
            row = conn.execute("SELECT auto_sync FROM datasource_config WHERE config_id = ?", (config_id,)).fetchone()
            return None if row is None else bool(row[0])
        return await self._read(work)

    async def get_paused_configs(self) -> List[DataSourceConfig]:
        return await self._read(lambda conn: self._configs(
            conn, "SELECT * FROM datasource_config WHERE is_active = FALSE AND auto_sync = TRUE ORDER BY created_at"))

    async def delete_config(self, config_id: str):
        await self._write(lambda conn: conn.execute(
            "DELETE FROM datasource_config WHERE config_id = ?", (config_id,)))


class SqliteStateManager(_SqliteBase, StateManager):
    """StateManager on a SQLite file."""

    def __init__(self, path: Optional[str] = None):
        self._setup(path)

    async def _create_schema(self):
        pass  # done when the file is opened

    @staticmethod
    def _state(row: Dict[str, Any], with_skip_graph: bool) -> DocumentState:
        # get_state / get_state_by_source_id leave skip_graph None, as PostgreSQL's do: a state
        # read and saved back must not carry the flag over a save that wrote the graph
        return DocumentState(
            doc_id=row["doc_id"], config_id=row["config_id"], source_path=row["source_path"],
            source_id=row.get("source_id"), ordinal=row["ordinal"], content_hash=row["content_hash"],
            modified_timestamp=row.get("modified_timestamp"),
            vector_synced_at=row["vector_synced_at"], search_synced_at=row["search_synced_at"],
            graph_synced_at=row["graph_synced_at"], rdf_synced_at=row.get("rdf_synced_at"),
            skip_graph=row.get("skip_graph") if with_skip_graph else None,
            enabled_graph=row.get("enabled_graph"), enabled_rdf=row.get("enabled_rdf"),
            auto_sync=row.get("auto_sync"),
        )

    async def get_state(self, doc_id: str) -> Optional[DocumentState]:
        def work(conn):
            row = _decode(conn.execute("SELECT * FROM document_state WHERE doc_id = ?", (doc_id,)).fetchone())
            return self._state(row, False) if row else None
        return await self._read(work)

    async def get_state_by_source_id(self, config_id: str, source_id: str) -> Optional[DocumentState]:
        def work(conn):
            row = _decode(conn.execute(
                "SELECT * FROM document_state WHERE config_id = ? AND source_id = ? LIMIT 1",
                (config_id, source_id)).fetchone())
            return self._state(row, False) if row else None
        return await self._read(work)

    async def get_all_states_for_config(self, config_id: str) -> List[DocumentState]:
        def work(conn):
            rows = conn.execute("SELECT * FROM document_state WHERE config_id = ?", (config_id,)).fetchall()
            return [self._state(_decode(r), True) for r in rows]
        return await self._read(work)

    async def _update_ordinal_only(self, doc_id: str, new_ordinal: int, modified_timestamp: Optional[datetime] = None):
        now = _now()

        def work(conn):
            if modified_timestamp is not None:
                conn.execute("UPDATE document_state SET ordinal = ?, modified_timestamp = ?, updated_at = ? "
                             "WHERE doc_id = ?", (new_ordinal, _ts(modified_timestamp), now, doc_id))
            else:
                conn.execute("UPDATE document_state SET ordinal = ?, updated_at = ? WHERE doc_id = ?",
                             (new_ordinal, now, doc_id))
        await self._write(work)

    async def _update_hash_only(self, doc_id: str, content_hash: str, new_ordinal: int):
        await self._write(lambda conn: conn.execute(
            "UPDATE document_state SET content_hash = ?, ordinal = ?, updated_at = ? WHERE doc_id = ?",
            (content_hash, new_ordinal, _now(), doc_id)))

    async def save_state(self, state: DocumentState):
        # the per-graph flags; the older skip_graph alone means both off
        eg, er = state.enabled_graph, state.enabled_rdf
        if state.skip_graph and eg is None and er is None:
            eg = er = False
        params = {
            "doc_id": state.doc_id, "config_id": state.config_id, "source_path": state.source_path,
            "source_id": state.source_id, "ordinal": state.ordinal, "content_hash": state.content_hash,
            "modified": _ts(state.modified_timestamp), "vector": _ts(state.vector_synced_at),
            "search": _ts(state.search_synced_at), "graph": _ts(state.graph_synced_at),
            "rdf": _ts(state.rdf_synced_at), "skip_graph": state.skip_graph, "auto_sync": state.auto_sync,
            "eg": eg, "er": er, "now": _now(),
        }
        await self._write(lambda conn: conn.execute("""
            INSERT INTO document_state
            (doc_id, config_id, source_path, source_id, ordinal, content_hash, modified_timestamp,
             vector_synced_at, search_synced_at, graph_synced_at, skip_graph, auto_sync,
             rdf_synced_at, enabled_graph, enabled_rdf, created_at, updated_at)
            VALUES (:doc_id, :config_id, :source_path, :source_id, :ordinal, :content_hash, :modified,
                    :vector, :search, :graph, COALESCE(:skip_graph, FALSE), COALESCE(:auto_sync, TRUE),
                    :rdf, COALESCE(:eg, TRUE), COALESCE(:er, TRUE), :now, :now)
            ON CONFLICT (doc_id) DO UPDATE SET
                -- the document's current name: a renamed or moved document keeps its doc_id
                -- (node id) and its row, so the display path must follow
                source_path = excluded.source_path,
                source_id = COALESCE(excluded.source_id, document_state.source_id),
                ordinal = excluded.ordinal,
                content_hash = excluded.content_hash,
                modified_timestamp = excluded.modified_timestamp,
                vector_synced_at = excluded.vector_synced_at,
                search_synced_at = excluded.search_synced_at,
                graph_synced_at = excluded.graph_synced_at,
                rdf_synced_at = excluded.rdf_synced_at,
                auto_sync = COALESCE(:auto_sync, document_state.auto_sync),
                skip_graph = COALESCE(:skip_graph, document_state.skip_graph
                                      AND excluded.graph_synced_at IS NULL AND excluded.rdf_synced_at IS NULL),
                -- a graph's flag comes back on when this save wrote that graph
                enabled_graph = COALESCE(:eg, document_state.enabled_graph OR excluded.graph_synced_at IS NOT NULL),
                enabled_rdf = COALESCE(:er, document_state.enabled_rdf OR excluded.rdf_synced_at IS NOT NULL),
                updated_at = :now
        """, params))

    async def mark_target_synced(self, doc_id: str, target: str):
        column = {"vector": "vector_synced_at", "search": "search_synced_at",
                  "graph": "graph_synced_at", "rdf": "rdf_synced_at"}.get(target)
        if not column:
            return
        now = _now()
        await self._write(lambda conn: conn.execute(
            f"UPDATE document_state SET {column} = ?, updated_at = ? WHERE doc_id = ?", (now, now, doc_id)))

    async def sync_off(self, doc_id: str) -> bool:
        def work(conn):
            row = conn.execute("SELECT auto_sync FROM document_state WHERE doc_id = ?", (doc_id,)).fetchone()
            return row is not None and row[0] is not None and not row[0]
        return await self._read(work)

    async def doc_graphs(self, doc_id: Optional[str] = None, config_id: Optional[str] = None,
                         source_id: Optional[str] = None):
        from graph_flags import GraphFlags

        def work(conn):
            if doc_id:
                return conn.execute("SELECT enabled_graph AS g, enabled_rdf AS r FROM document_state "
                                    "WHERE doc_id = ?", (doc_id,)).fetchone()
            # bool_and: MIN of 0 / 1 (NULL when there are no rows)
            return conn.execute("SELECT MIN(enabled_graph) AS g, MIN(enabled_rdf) AS r FROM document_state "
                                "WHERE config_id = ? AND source_id = ?", (config_id, source_id)).fetchone()
        row = await self._read(work)
        if not row:
            return GraphFlags()
        return GraphFlags(row["g"] is None or bool(row["g"]), row["r"] is None or bool(row["r"]))

    async def clear_targets(self, doc_id: str):
        await self._write(lambda conn: conn.execute(
            "UPDATE document_state SET vector_synced_at = NULL, search_synced_at = NULL, "
            "graph_synced_at = NULL, rdf_synced_at = NULL, updated_at = ? WHERE doc_id = ?", (_now(), doc_id)))

    async def mark_deleted(self, doc_id: str):
        await self._write(lambda conn: conn.execute("DELETE FROM document_state WHERE doc_id = ?", (doc_id,)))

    async def _update_source_path(self, doc_id: str, new_source_path: str):
        await self._write(lambda conn: conn.execute(
            "UPDATE document_state SET source_path = ?, updated_at = ? WHERE doc_id = ?",
            (new_source_path, _now(), doc_id)))

    async def get_sync_stats(self, config_id: str) -> Dict:
        def work(conn):
            row = conn.execute("""
                SELECT COUNT(*) AS total_docs,
                       COUNT(*) FILTER (WHERE vector_synced_at IS NOT NULL) AS vector_synced,
                       COUNT(*) FILTER (WHERE search_synced_at IS NOT NULL) AS search_synced,
                       COUNT(*) FILTER (WHERE graph_synced_at IS NOT NULL) AS graph_synced
                FROM document_state WHERE config_id = ?
            """, (config_id,)).fetchone()
            return dict(row) if row else {}
        return await self._read(work)

    # ----- Registry queries of the backend: ingest status, removal, duplicate copies -----

    async def doc_ids_for_config(self, config_id: str) -> List[str]:
        return await self._read(lambda conn: [r[0] for r in conn.execute(
            "SELECT doc_id FROM document_state WHERE config_id = ?", (config_id,)).fetchall()])

    async def known_doc_ids(self, doc_ids: List[str]) -> Set[str]:
        return await self._read(lambda conn: {r[0] for r in conn.execute(
            f"SELECT doc_id FROM document_state WHERE doc_id {_IN}", (_ids(doc_ids),)).fetchall()})

    async def fetch_rows(self, config_ids: List[str]):
        from incremental_updates.removal import row_from_record

        def work(conn):
            rows = conn.execute(
                "SELECT doc_id, config_id, source_id, source_path, vector_synced_at, search_synced_at, "
                f"graph_synced_at, rdf_synced_at, auto_sync FROM document_state WHERE config_id {_IN}",
                (_ids(config_ids),)).fetchall()
            return [row_from_record(_decode(r)) for r in rows]
        return await self._read(work)

    async def set_auto_sync(self, doc_ids: Iterable[str], value: bool) -> int:
        ids = list(dict.fromkeys(doc_ids))
        if not ids:
            return 0
        await self._write(lambda conn: conn.execute(
            f"UPDATE document_state SET auto_sync = ?, updated_at = ? WHERE doc_id {_IN}",
            (bool(value), _now(), _ids(ids))))
        return len(ids)

    async def record_removal(self, rows, targets: Iterable[str], auto_sync_configs: Iterable[str]) -> Dict[str, int]:
        """As StateManager.record_removal (see there), in one transaction."""
        from incremental_updates.removal import TARGET_COLUMNS
        rows, targets = list(rows), list(targets)
        cols = [TARGET_COLUMNS[t] for t in targets]
        doc_ids = list(dict.fromkeys(r.doc_id for r in rows))
        if not doc_ids or not cols:
            return {"forgotten": 0, "datasources_dropped": 0, "datasources_now_skip_graph": 0}
        ids, auto, now = _ids(doc_ids), _ids(auto_sync_configs), _now()
        sets = ", ".join(f"{c} = NULL" for c in cols)
        nothing_left = ("vector_synced_at IS NULL AND search_synced_at IS NULL AND graph_synced_at IS NULL "
                        "AND rdf_synced_at IS NULL")

        def work(conn):
            conn.execute(f"UPDATE document_state SET {sets}, updated_at = ? WHERE doc_id {_IN}", (now, ids))
            # Per document and graph: its sync's updates leave a removed graph out from now on
            offs = [f"{col} = FALSE" for t, col in (("graph", "enabled_graph"), ("rdf", "enabled_rdf"))
                    if t in targets]
            if offs:
                conn.execute(f"UPDATE document_state SET {', '.join(offs)} WHERE doc_id {_IN}", (ids,))
                conn.execute("UPDATE document_state SET skip_graph = NOT (enabled_graph OR enabled_rdf) "
                             f"WHERE doc_id {_IN}", (ids,))
            conn.execute(f"UPDATE document_state SET auto_sync = FALSE WHERE doc_id {_IN} "
                         f"AND config_id {_IN} AND {nothing_left}", (ids, auto))
            forgotten = conn.execute(
                f"DELETE FROM document_state WHERE doc_id {_IN} AND config_id NOT {_IN} AND {nothing_left} "
                "RETURNING config_id", (ids, auto)).fetchall()
            dropped = conn.execute(
                f"DELETE FROM datasource_config WHERE config_id {_IN} AND auto_sync = FALSE "
                "AND NOT EXISTS (SELECT 1 FROM document_state ds WHERE ds.config_id = datasource_config.config_id) "
                "RETURNING config_id", (_ids({r["config_id"] for r in forgotten}),)).fetchall()
            # A graph is a datasource setting too (see StateManager.record_removal)
            graph_off = set()
            for target, flag, col in (("graph", "enabled_graph", "graph_synced_at"),
                                      ("rdf", "enabled_rdf", "rdf_synced_at")):
                config_ids = list({r.config_id for r in rows if r.synced.get(target)})
                if target not in targets or not config_ids:
                    continue
                off = conn.execute(
                    f"""
                    UPDATE datasource_config SET {flag} = FALSE, updated_at = ?
                    WHERE config_id {_IN} AND {flag} IS NOT FALSE
                      AND EXISTS (SELECT 1 FROM document_state ds WHERE ds.config_id = datasource_config.config_id
                                  AND (ds.vector_synced_at IS NOT NULL OR ds.search_synced_at IS NOT NULL))
                      AND NOT EXISTS (SELECT 1 FROM document_state ds
                                      WHERE ds.config_id = datasource_config.config_id AND ds.{col} IS NOT NULL)
                    RETURNING config_id
                    """, (now, _ids(config_ids))).fetchall()
                graph_off |= {r["config_id"] for r in off}
            if graph_off:
                conn.execute(f"UPDATE datasource_config SET skip_graph = TRUE WHERE config_id {_IN} "
                             "AND enabled_graph IS FALSE AND enabled_rdf IS FALSE", (_ids(graph_off),))
            return {"forgotten": len(forgotten), "datasources_dropped": len(dropped),
                    "datasources_now_skip_graph": len(graph_off)}
        return await self._write(work)

    async def retire_datasource(self, config_id: str) -> str:
        now = _now()

        def work(conn):
            in_store = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM document_state WHERE config_id = ? AND "
                "(vector_synced_at IS NOT NULL OR search_synced_at IS NOT NULL OR graph_synced_at IS NOT NULL "
                "OR rdf_synced_at IS NOT NULL))", (config_id,)).fetchone()[0]
            if in_store:
                conn.execute("UPDATE datasource_config SET auto_sync = FALSE, is_active = FALSE, updated_at = ? "
                             "WHERE config_id = ?", (now, config_id))
                return "ingest-only"
            conn.execute("DELETE FROM document_state WHERE config_id = ?", (config_id,))
            conn.execute("DELETE FROM datasource_config WHERE config_id = ?", (config_id,))
            return "deleted"
        return await self._write(work)

    async def resolve_duplicate_copies(self, config_id: str, sync_takeover: bool = False) -> list:
        """As StateManager.resolve_duplicate_copies (see there), in one transaction."""
        same_identity = """
            substr(other.doc_id, length(other.config_id) + 2) = substr(mine.doc_id, length(mine.config_id) + 2)
            AND other.config_id <> mine.config_id
        """

        def work(conn):
            others = conn.execute(f"""
                SELECT other.doc_id, other.config_id
                FROM document_state mine
                JOIN document_state other ON {same_identity}
                JOIN datasource_config odc ON odc.config_id = other.config_id
                WHERE mine.config_id = ? AND odc.auto_sync = FALSE
            """, (config_id,)).fetchall()
            mine = conn.execute(f"""
                SELECT DISTINCT mine.doc_id, mine.config_id
                FROM document_state mine
                JOIN datasource_config mdc ON mdc.config_id = mine.config_id
                JOIN document_state other ON {same_identity}
                JOIN datasource_config odc ON odc.config_id = other.config_id
                WHERE mine.config_id = ? AND (mdc.auto_sync = FALSE OR NOT mine.auto_sync)
                  AND odc.auto_sync = TRUE AND other.auto_sync
            """, (config_id,)).fetchall()
            synced_others = []
            if sync_takeover:
                synced_others = conn.execute(f"""
                    SELECT other.doc_id, other.config_id
                    FROM document_state mine
                    JOIN datasource_config mdc ON mdc.config_id = mine.config_id
                    JOIN document_state other ON {same_identity}
                    JOIN datasource_config odc ON odc.config_id = other.config_id
                    WHERE mine.config_id = ? AND mdc.auto_sync = TRUE AND mine.auto_sync
                      AND odc.auto_sync = TRUE
                """, (config_id,)).fetchall()
            losers = list(others) + list(mine) + list(synced_others)
            if not losers:
                return [], 0, 0, 0
            doc_ids = list(dict.fromkeys(r["doc_id"] for r in losers))
            conn.execute(f"DELETE FROM document_state WHERE doc_id {_IN}", (_ids(doc_ids),))
            emptied = conn.execute(
                f"DELETE FROM datasource_config WHERE config_id {_IN} AND auto_sync = FALSE "
                "AND NOT EXISTS (SELECT 1 FROM document_state ds WHERE ds.config_id = datasource_config.config_id) "
                "RETURNING config_id", (_ids({r["config_id"] for r in losers}),)).fetchall()
            return doc_ids, len(others), len(mine), len(emptied)
        doc_ids, n_others, n_mine, n_emptied = await self._write(work)
        if doc_ids:
            logger.info(
                f"{config_id}: {n_others} older ingest cop(ies) superseded, {n_mine} document(s) "
                f"left to the auto-sync that already holds them; {n_emptied} emptied ingest record(s) removed")
        return doc_ids

    async def registry_rows(self, doc_ids: List[str]) -> Dict[str, dict]:
        def work(conn):
            return conn.execute(
                "SELECT d.doc_id, d.source_id, d.source_path, c.source_type, c.connection_params "
                "FROM document_state d LEFT JOIN datasource_config c ON c.config_id = d.config_id "
                f"WHERE d.doc_id {_IN}", (_ids(doc_ids),)).fetchall()
        out = {}
        for r in await self._read(work):
            try:
                params = json.loads(r["connection_params"]) if r["connection_params"] else {}
            except ValueError:
                params = {}
            out[r["doc_id"]] = {"source_id": r["source_id"], "source_path": r["source_path"] or "",
                                "source_type": r["source_type"] or "", "connection_params": params}
        return out

    # ----- Sync cursors (Microsoft Graph deltaLinks) -----

    async def load_sync_cursor(self, config_id: str) -> Optional[str]:
        def work(conn):
            row = conn.execute("SELECT delta_link FROM msgraph_delta_state WHERE config_id = ?", (config_id,)).fetchone()
            return row[0] if row else None
        return await self._read(work)

    async def save_sync_cursor(self, config_id: str, cursor: str) -> None:
        await self._write(lambda conn: conn.execute(
            "INSERT INTO msgraph_delta_state (config_id, delta_link, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (config_id) DO UPDATE SET delta_link = excluded.delta_link, updated_at = excluded.updated_at",
            (config_id, cursor, _now())))
