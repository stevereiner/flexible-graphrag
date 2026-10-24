"""
State Manager

Tracks document processing state using PostgreSQL:
- Ordinal-based versioning (monotonic timestamps)
- Content hash optimization (skip unchanged files)
- Per-target sync status (vector, search, graph)
- Partial sync recovery on failures
"""

import asyncpg
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Iterable, List, Set
from datetime import datetime, timezone

logger = logging.getLogger("flexible_graphrag.incremental_system")


@dataclass
class DocumentState:
    """Document processing state"""
    doc_id: str
    config_id: str
    source_path: str
    ordinal: int  # Microsecond timestamp
    content_hash: str
    source_id: Optional[str] = None  # Source-specific file ID (e.g., Google Drive file ID)
    modified_timestamp: Optional[datetime] = None  # Source modification timestamp (for quick change detection)
    vector_synced_at: Optional[datetime] = None
    search_synced_at: Optional[datetime] = None
    graph_synced_at: Optional[datetime] = None  # the property graph (PG_GRAPH_DB)
    rdf_synced_at: Optional[datetime] = None    # the RDF graph (RDF_GRAPH_DB)
    # This document leaves the graph out (see the skip_graph column). None = keep what the row
    # has, unless this save wrote the graph. The older single flag: neither graph.
    skip_graph: Optional[bool] = None
    # Per graph (graph_flags.py): False = this document leaves that graph out (it was removed
    # from it); None = keep what the row has, unless this save wrote that graph (back on).
    enabled_graph: Optional[bool] = None
    enabled_rdf: Optional[bool] = None
    # Follows its datasource's auto sync (see the auto_sync column). None = keep what the row has.
    auto_sync: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StateManager:
    """Manages document processing state in PostgreSQL"""
    
    def __init__(self, postgres_url: str):
        self.postgres_url = postgres_url
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize connection pool and create schema"""
        self.pool = await asyncpg.create_pool(self.postgres_url)
        await self._create_schema()
    
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
    
    async def _create_schema(self):
        """Create document_state table if not exists"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_state (
                    doc_id TEXT PRIMARY KEY,
                    config_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_id TEXT,
                    ordinal BIGINT NOT NULL,
                    content_hash TEXT NOT NULL,
                    modified_timestamp TIMESTAMPTZ,
                    vector_synced_at TIMESTAMPTZ,
                    search_synced_at TIMESTAMPTZ,
                    graph_synced_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            
            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_state_config_id 
                ON document_state(config_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_state_ordinal 
                ON document_state(config_id, ordinal)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_document_state_source_id 
                ON document_state(config_id, source_id)
            """)
            # auto_sync: whether this document follows its datasource's auto sync. FALSE keeps the
            # row -- so the sync does not see a "new document" and add it back -- while the sync
            # skips its updates: frozen as it is in the stores, or kept out of them entirely
            # (removed from every store). Renames / moves and repository deletes still apply.
            # Set per row from the Processing tab's Auto Sync column (main.py) and by a removal
            # from every store (removal.py). Meaningless for an ingest-only datasource.
            await conn.execute("""
                ALTER TABLE document_state
                ADD COLUMN IF NOT EXISTS auto_sync BOOLEAN NOT NULL DEFAULT TRUE
            """)
            # excluded: the earlier form of auto_sync = FALSE (0.8.3 development); migrated once
            await conn.execute("""
                ALTER TABLE document_state
                ADD COLUMN IF NOT EXISTS excluded BOOLEAN NOT NULL DEFAULT FALSE
            """)
            await conn.execute(
                "UPDATE document_state SET auto_sync = FALSE, excluded = FALSE WHERE excluded")
            # skip_graph: this document's graph was removed while its datasource keeps building
            # graphs, so the sync's updates leave the graph out for it (datasource skip_graph OR
            # this). Cleared by any save that wrote the graph -- an ingest putting it back.
            await conn.execute("""
                ALTER TABLE document_state
                ADD COLUMN IF NOT EXISTS skip_graph BOOLEAN NOT NULL DEFAULT FALSE
            """)
            # The same per graph (graph_flags.py), and the RDF graph's own sync time; rows written
            # before these columns take skip_graph for both, once
            added = await conn.fetchval(
                "SELECT NOT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'document_state' AND column_name = 'enabled_graph')")
            await conn.execute("""
                ALTER TABLE document_state
                ADD COLUMN IF NOT EXISTS enabled_graph BOOLEAN NOT NULL DEFAULT TRUE,
                ADD COLUMN IF NOT EXISTS enabled_rdf BOOLEAN NOT NULL DEFAULT TRUE,
                ADD COLUMN IF NOT EXISTS rdf_synced_at TIMESTAMPTZ
            """)
            if added:
                await conn.execute(
                    "UPDATE document_state SET enabled_graph = FALSE, enabled_rdf = FALSE WHERE skip_graph")
    
    @staticmethod
    def make_doc_id(config_id: str, source_path: str) -> str:
        """Generate stable document ID"""
        return f"{config_id}:{source_path}"
    
    @staticmethod
    def compute_content_hash(text: str) -> str:
        """Compute SHA-256 hash of document content"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    async def get_state(self, doc_id: str) -> Optional[DocumentState]:
        """Get document state"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM document_state WHERE doc_id = $1",
                doc_id
            )
            if not row:
                return None
            
            return DocumentState(
                doc_id=row['doc_id'],
                config_id=row['config_id'],
                source_path=row['source_path'],
                source_id=row.get('source_id'),
                ordinal=row['ordinal'],
                content_hash=row['content_hash'],
                modified_timestamp=row.get('modified_timestamp'),
                vector_synced_at=row['vector_synced_at'],
                search_synced_at=row['search_synced_at'],
                graph_synced_at=row['graph_synced_at'],
                rdf_synced_at=row.get('rdf_synced_at'),
                enabled_graph=row.get('enabled_graph'),
                enabled_rdf=row.get('enabled_rdf'),
                auto_sync=row.get('auto_sync')
            )
    
    async def get_state_by_source_id(self, config_id: str, source_id: str) -> Optional[DocumentState]:
        """Get document state by source_id (e.g., file_id for cloud sources)"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM document_state WHERE config_id = $1 AND source_id = $2 LIMIT 1",
                config_id, source_id
            )
            if not row:
                return None
            
            return DocumentState(
                doc_id=row['doc_id'],
                config_id=row['config_id'],
                source_path=row['source_path'],
                source_id=row.get('source_id'),
                ordinal=row['ordinal'],
                content_hash=row['content_hash'],
                modified_timestamp=row.get('modified_timestamp'),
                vector_synced_at=row['vector_synced_at'],
                search_synced_at=row['search_synced_at'],
                graph_synced_at=row['graph_synced_at'],
                rdf_synced_at=row.get('rdf_synced_at'),
                enabled_graph=row.get('enabled_graph'),
                enabled_rdf=row.get('enabled_rdf'),
                auto_sync=row.get('auto_sync')
            )
    
    async def get_all_states_for_config(self, config_id: str) -> List[DocumentState]:
        """Get all document states for a specific config"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM document_state WHERE config_id = $1",
                config_id
            )
            
            states = []
            for row in rows:
                states.append(DocumentState(
                    doc_id=row['doc_id'],
                    config_id=row['config_id'],
                    source_path=row['source_path'],
                    source_id=row.get('source_id'),
                    ordinal=row['ordinal'],
                    content_hash=row['content_hash'],
                    modified_timestamp=row.get('modified_timestamp'),
                    vector_synced_at=row['vector_synced_at'],
                    search_synced_at=row['search_synced_at'],
                    graph_synced_at=row['graph_synced_at'],
                    rdf_synced_at=row.get('rdf_synced_at'),
                    skip_graph=row.get('skip_graph'),
                    enabled_graph=row.get('enabled_graph'),
                    enabled_rdf=row.get('enabled_rdf'),
                    auto_sync=row.get('auto_sync'),
                ))
            
            return states
    
    async def get_state_by_path_fallback(self, config_id: str, path: str) -> Optional[DocumentState]:
        """
        Find document_state by config_id and path using case-insensitive path match.
        Used for filesystem when doc_id lookup fails due to path case mismatch.
        """
        from incremental_updates.path_utils import normalize_filesystem_path
        norm_path = normalize_filesystem_path(path)
        states = await self.get_all_states_for_config(config_id)
        for state in states:
            if normalize_filesystem_path(state.source_path) == norm_path:
                return state
        return None
    
    async def should_process(self, doc_id: str, new_ordinal: int, 
                            new_hash: str) -> tuple[bool, str]:
        """
        Determine if document should be processed.
        Returns: (should_process, reason)
        
        Implements monotonic invariance and content hash optimization.
        """
        from datetime import datetime, timezone, timedelta
        
        state = await self.get_state(doc_id)
        
        if state is None:
            return True, "new document"
        
        # Monotonic invariance: never process older versions
        if new_ordinal < state.ordinal:
            return False, f"file already processed (last processed after file modification time)"
        
        if new_ordinal == state.ordinal:
            return False, "same version"
        
        # Content hash optimization
        if state.content_hash is None:
            # Content hash not yet computed (from initial bulk sync)
            # Check if this was just synced recently (within last 5 minutes)
            # If so, skip to avoid duplicate processing
            now = datetime.now(timezone.utc)
            recently_synced = False
            
            if state.vector_synced_at:
                time_since_sync = now - state.vector_synced_at
                if time_since_sync < timedelta(minutes=5):
                    recently_synced = True
            
            if recently_synced:
                # Update the hash without reprocessing
                await self._update_hash_only(doc_id, new_hash, new_ordinal)
                return False, "recently synced, updating hash without reprocessing"
            
            # If not recently synced, compute hash and process
            return True, "content hash not yet computed"
        
        if new_hash == state.content_hash:
            # Content unchanged, just update ordinal
            await self._update_ordinal_only(doc_id, new_ordinal)
            return False, "content unchanged (ordinal updated)"
        
        return True, "content changed"
    
    async def _update_ordinal_only(self, doc_id: str, new_ordinal: int, modified_timestamp: Optional[datetime] = None):
        """Update ordinal and modified_timestamp without full reprocessing"""
        async with self.pool.acquire() as conn:
            if modified_timestamp is not None:
                await conn.execute("""
                    UPDATE document_state 
                    SET ordinal = $1, modified_timestamp = $2, updated_at = NOW()
                    WHERE doc_id = $3
                """, new_ordinal, modified_timestamp, doc_id)
            else:
                await conn.execute("""
                    UPDATE document_state 
                    SET ordinal = $1, updated_at = NOW()
                    WHERE doc_id = $2
                """, new_ordinal, doc_id)
    
    async def _update_hash_only(self, doc_id: str, content_hash: str, new_ordinal: int):
        """Update content_hash and ordinal without full reprocessing (used after initial bulk sync)"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE document_state 
                SET content_hash = $1, ordinal = $2, updated_at = NOW()
                WHERE doc_id = $3
            """, content_hash, new_ordinal, doc_id)
    
    @staticmethod
    def _ensure_datetime(value):
        """Convert ISO timestamp string to datetime for PostgreSQL TIMESTAMPTZ."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                try:
                    from dateutil import parser as dateutil_parser
                    return dateutil_parser.parse(value)
                except Exception:
                    raise ValueError(f"Invalid timestamp string for document_state: {value!r}")
        return value

    async def save_state(self, state: DocumentState):
        """Save or update document state"""
        # Normalize timestamp fields to datetime (asyncpg expects datetime for TIMESTAMPTZ)
        modified_ts = self._ensure_datetime(state.modified_timestamp)
        vector_ts = self._ensure_datetime(state.vector_synced_at)
        search_ts = self._ensure_datetime(state.search_synced_at)
        graph_ts = self._ensure_datetime(state.graph_synced_at)
        rdf_ts = self._ensure_datetime(state.rdf_synced_at)
        # the per-graph flags; the older skip_graph alone means both off
        eg, er = state.enabled_graph, state.enabled_rdf
        if state.skip_graph and eg is None and er is None:
            eg = er = False
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO document_state
                (doc_id, config_id, source_path, source_id, ordinal, content_hash, modified_timestamp,
                 vector_synced_at, search_synced_at, graph_synced_at, skip_graph, auto_sync,
                 rdf_synced_at, enabled_graph, enabled_rdf)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, COALESCE($11, FALSE), COALESCE($12, TRUE),
                        $13, COALESCE($14, TRUE), COALESCE($15, TRUE))
                ON CONFLICT (doc_id) DO UPDATE SET
                    -- the document's current name: a renamed or moved document keeps its doc_id
                    -- (node id) and its row, so the display path must follow
                    source_path = EXCLUDED.source_path,
                    source_id = COALESCE(EXCLUDED.source_id, document_state.source_id),
                    ordinal = EXCLUDED.ordinal,
                    content_hash = EXCLUDED.content_hash,
                    modified_timestamp = EXCLUDED.modified_timestamp,
                    vector_synced_at = EXCLUDED.vector_synced_at,
                    search_synced_at = EXCLUDED.search_synced_at,
                    graph_synced_at = EXCLUDED.graph_synced_at,
                    rdf_synced_at = EXCLUDED.rdf_synced_at,
                    auto_sync = COALESCE($12, document_state.auto_sync),
                    skip_graph = COALESCE($11, document_state.skip_graph
                                           AND EXCLUDED.graph_synced_at IS NULL AND EXCLUDED.rdf_synced_at IS NULL),
                    -- a graph's flag comes back on when this save wrote that graph
                    enabled_graph = COALESCE($14, document_state.enabled_graph OR EXCLUDED.graph_synced_at IS NOT NULL),
                    enabled_rdf = COALESCE($15, document_state.enabled_rdf OR EXCLUDED.rdf_synced_at IS NOT NULL),
                    updated_at = NOW()
            """, state.doc_id, state.config_id, state.source_path, state.source_id, state.ordinal,
                state.content_hash, modified_ts, vector_ts, search_ts, graph_ts, state.skip_graph,
                state.auto_sync, rdf_ts, eg, er)
    
    async def mark_target_synced(self, doc_id: str, target: str):
        """Mark a target database as synced (uses UTC timezone)"""
        # Use timezone-aware UTC timestamp (PostgreSQL TIMESTAMPTZ best practice)
        now = datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            if target == 'vector':
                await conn.execute("""
                    UPDATE document_state 
                    SET vector_synced_at = $1, updated_at = NOW()
                    WHERE doc_id = $2
                """, now, doc_id)
            elif target == 'search':
                await conn.execute("""
                    UPDATE document_state 
                    SET search_synced_at = $1, updated_at = NOW()
                    WHERE doc_id = $2
                """, now, doc_id)
            elif target == 'graph':
                await conn.execute("""
                    UPDATE document_state
                    SET graph_synced_at = $1, updated_at = NOW()
                    WHERE doc_id = $2
                """, now, doc_id)
            elif target == 'rdf':
                await conn.execute(
                    "UPDATE document_state SET rdf_synced_at = $1, updated_at = NOW() WHERE doc_id = $2",
                    now, doc_id)
    
    async def sync_off(self, doc_id: str) -> bool:
        """Whether this document's auto sync is off (the auto_sync column): its sync skips it."""
        async with self.pool.acquire() as conn:
            return (await conn.fetchval(
                "SELECT auto_sync FROM document_state WHERE doc_id = $1", doc_id
            )) is False

    async def doc_graphs(self, doc_id: Optional[str] = None, config_id: Optional[str] = None,
                         source_id: Optional[str] = None):
        """This one document's own graphs (graph_flags.GraphFlags; both on when it has no row): a
        graph it was removed from stays off for it, by doc_id or by (config_id, source_id)."""
        from graph_flags import GraphFlags
        async with self.pool.acquire() as conn:
            if doc_id:
                row = await conn.fetchrow(
                    "SELECT enabled_graph AS g, enabled_rdf AS r FROM document_state WHERE doc_id = $1", doc_id)
            else:
                row = await conn.fetchrow(
                    "SELECT bool_and(enabled_graph) AS g, bool_and(enabled_rdf) AS r FROM document_state "
                    "WHERE config_id = $1 AND source_id = $2", config_id, source_id)
        if not row:
            return GraphFlags()
        return GraphFlags(row["g"] is not False, row["r"] is not False)

    async def doc_skip_graph(self, doc_id: Optional[str] = None, config_id: Optional[str] = None,
                             source_id: Optional[str] = None) -> bool:
        """Whether this one document leaves both graphs out (the older single flag; doc_graphs)."""
        return (await self.doc_graphs(doc_id, config_id, source_id)).none

    async def document_scope(self, config_id: str, path: Optional[str], source_id: Optional[str] = None,
                             ancestor_ids: Optional[List[str]] = None) -> Dict:
        """What the sync does with a document it is about to ingest (new or changed):
        ``follow`` (ingest it or not), ``graph`` / ``rdf`` (each True / False from a rule, None:
        the datasource's own setting), ``skip_graph`` (the older single flag) and the ``reason``
        when not followed. Here every document of a sync is followed; the OpenArch store answers
        from its per-object scope rules (openarch/scope.py)."""
        return {"follow": True, "graph": None, "rdf": None, "skip_graph": None, "reason": None}

    async def clear_targets(self, doc_id: str):
        """Mark a document as in no store, keeping its row (and its flags)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE document_state SET vector_synced_at = NULL, search_synced_at = NULL, "
                "graph_synced_at = NULL, rdf_synced_at = NULL, updated_at = NOW() WHERE doc_id = $1", doc_id)

    async def mark_deleted(self, doc_id: str):
        """Remove document state completely (hard delete)"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM document_state WHERE doc_id = $1',
                doc_id
            )
    
    async def _update_source_path(self, doc_id: str, new_source_path: str):
        """Update source_path to human-readable version (for migrating old records)"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE document_state 
                SET source_path = $1, updated_at = NOW()
                WHERE doc_id = $2
            """, new_source_path, doc_id)
    
    async def get_sync_stats(self, config_id: str) -> Dict:
        """Get sync statistics for a datasource"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_docs,
                    COUNT(*) FILTER (WHERE vector_synced_at IS NOT NULL) as vector_synced,
                    COUNT(*) FILTER (WHERE search_synced_at IS NOT NULL) as search_synced,
                    COUNT(*) FILTER (WHERE graph_synced_at IS NOT NULL) as graph_synced
                FROM document_state
                WHERE config_id = $1
            """, config_id)
            
            return dict(row) if row else {}

    # ----- Registry queries of the backend: ingest status, removal, duplicate copies -----

    async def doc_ids_for_config(self, config_id: str) -> List[str]:
        """doc_ids recorded for a datasource."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT doc_id FROM document_state WHERE config_id = $1", config_id)
        return [r["doc_id"] for r in rows]

    async def known_doc_ids(self, doc_ids: List[str]) -> Set[str]:
        """Which of ``doc_ids`` are recorded."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT doc_id FROM document_state WHERE doc_id = ANY($1::text[])", list(doc_ids))
        return {r["doc_id"] for r in rows}

    async def fetch_rows(self, config_ids: List[str]) -> List["StateRow"]:
        """The rows of these datasources, as removal / ingest status match them."""
        from incremental_updates.removal import row_from_record
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT doc_id, config_id, source_id, source_path, vector_synced_at, "
                "search_synced_at, graph_synced_at, rdf_synced_at, auto_sync FROM document_state "
                "WHERE config_id = ANY($1::text[])",
                list(config_ids),
            )
        return [row_from_record(r) for r in records]

    async def set_auto_sync(self, doc_ids: Iterable[str], value: bool) -> int:
        ids = list(dict.fromkeys(doc_ids))
        if not ids:
            return 0
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE document_state SET auto_sync = $2, updated_at = NOW() "
                               "WHERE doc_id = ANY($1::text[])", ids, value)
        return len(ids)

    async def record_removal(self, rows: Iterable["StateRow"], targets: Iterable[str],
                             auto_sync_configs: Iterable[str]) -> Dict[str, int]:
        """Clear ``targets`` on each row; forget ingest-only rows left with nothing, then any
        ingest-only datasource left with no rows; turn a graph off for a datasource left with
        none of its documents in it (skip_graph once both are off). Returns counts for the
        response (see incremental_updates/removal.py)."""
        from incremental_updates.removal import TARGET_COLUMNS
        rows, targets = list(rows), list(targets)
        cols = [TARGET_COLUMNS[t] for t in targets]
        doc_ids = list(dict.fromkeys(r.doc_id for r in rows))
        if not doc_ids or not cols:
            return {"forgotten": 0, "datasources_dropped": 0, "datasources_now_skip_graph": 0}
        sets = ", ".join(f"{c} = NULL" for c in cols)
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE document_state SET {sets}, updated_at = NOW() WHERE doc_id = ANY($1::text[])",
                doc_ids,
            )
            # Per document and graph: its sync's updates leave a removed graph out from now on
            # (until an ingest writes that graph again, which turns it back on -- see save_state)
            offs = [f"{col} = FALSE" for t, col in (("graph", "enabled_graph"), ("rdf", "enabled_rdf"))
                    if t in targets]
            if offs:
                await conn.execute(
                    f"UPDATE document_state SET {', '.join(offs)} WHERE doc_id = ANY($1::text[])", doc_ids)
                await conn.execute(
                    "UPDATE document_state SET skip_graph = NOT (enabled_graph OR enabled_rdf) "
                    "WHERE doc_id = ANY($1::text[])", doc_ids)
            nothing_left = ("vector_synced_at IS NULL AND search_synced_at IS NULL AND graph_synced_at IS NULL "
                            "AND rdf_synced_at IS NULL")
            await conn.execute(
                "UPDATE document_state SET auto_sync = FALSE WHERE doc_id = ANY($1::text[]) "
                "AND config_id = ANY($2::text[]) "
                f"AND {nothing_left}",
                doc_ids, list(auto_sync_configs),
            )
            forgotten = await conn.fetch(
                "DELETE FROM document_state WHERE doc_id = ANY($1::text[]) "
                "AND NOT (config_id = ANY($2::text[])) "
                f"AND {nothing_left} "
                "RETURNING config_id",
                doc_ids, list(auto_sync_configs),
            )
            dropped = await conn.fetch(
                """
                DELETE FROM datasource_config dc
                WHERE dc.config_id = ANY($1::text[]) AND dc.auto_sync = FALSE
                  AND NOT EXISTS (SELECT 1 FROM document_state ds WHERE ds.config_id = dc.config_id)
                RETURNING config_id
                """,
                list({r["config_id"] for r in forgotten}),
            )
            # A graph is a datasource setting too: once a datasource still has documents in
            # vector + search but none in a graph, it no longer builds that graph -- the same as
            # one ingested without it. Its sync (if any) then leaves it out on later updates, and
            # a re-ingest that builds it turns it back on.
            # Only where this removal took a document out of that graph: a datasource that never
            # had one (e.g. no RDF store configured) keeps building it once there is a store.
            graph_off = set()
            for target, flag, col in (("graph", "enabled_graph", "graph_synced_at"),
                                      ("rdf", "enabled_rdf", "rdf_synced_at")):
                config_ids = list({r.config_id for r in rows if r.synced.get(target)})
                if target not in targets or not config_ids:
                    continue
                off = await conn.fetch(
                    f"""
                    UPDATE datasource_config dc SET {flag} = FALSE, updated_at = NOW()
                    WHERE dc.config_id = ANY($1::text[]) AND dc.{flag} IS DISTINCT FROM FALSE
                      AND EXISTS (SELECT 1 FROM document_state ds WHERE ds.config_id = dc.config_id
                                  AND (ds.vector_synced_at IS NOT NULL OR ds.search_synced_at IS NOT NULL))
                      AND NOT EXISTS (SELECT 1 FROM document_state ds
                                      WHERE ds.config_id = dc.config_id AND ds.{col} IS NOT NULL)
                    RETURNING config_id
                    """,
                    config_ids,
                )
                graph_off |= {r["config_id"] for r in off}
            if graph_off:
                await conn.execute(
                    "UPDATE datasource_config SET skip_graph = TRUE WHERE config_id = ANY($1::text[]) "
                    "AND enabled_graph IS FALSE AND enabled_rdf IS FALSE", list(graph_off))
        return {"forgotten": len(forgotten), "datasources_dropped": len(dropped),
                "datasources_now_skip_graph": len(graph_off)}

    async def retire_datasource(self, config_id: str) -> str:
        """A datasource with no roots left: 'ingest-only' while documents of it are in a store,
        else 'deleted' (with its rows)."""
        async with self.pool.acquire() as conn:
            in_store = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM document_state WHERE config_id = $1 AND "
                "(vector_synced_at IS NOT NULL OR search_synced_at IS NOT NULL OR graph_synced_at IS NOT NULL "
                "OR rdf_synced_at IS NOT NULL))",
                config_id)
            if in_store:
                await conn.execute("UPDATE datasource_config SET auto_sync = FALSE, is_active = FALSE, "
                                   "updated_at = NOW() WHERE config_id = $1", config_id)
                return "ingest-only"
            await conn.execute("DELETE FROM document_state WHERE config_id = $1", config_id)
            await conn.execute("DELETE FROM datasource_config WHERE config_id = $1", config_id)
        return "deleted"

    async def resolve_duplicate_copies(self, config_id: str, sync_takeover: bool = False) -> list:
        """After ``config_id`` stored its documents, settle any document another datasource
        also holds, so each file ends up in the stores once:

        * another INGEST-ONLY datasource's copy is superseded by this newer one;
        * if THIS datasource is ingest-only and an AUTO-SYNC datasource holds the document, the
          sync keeps it (its detector maintains that copy, and deleting it would only have the
          detector re-ingest it) and this run's copy is the one dropped -- unless the sync's
          copy has its auto sync turned off (document_state.auto_sync, removal.py): then this
          copy is the only one, and it stays;
        * the same when THIS datasource is an auto sync but this document's auto sync is off in
          it (a row ingested, not synced, in a run that started a sync for others).

        With ``sync_takeover`` (only when ``config_id`` has just been registered as an auto
        sync): another AUTO-SYNC's copy of a document this sync follows is dropped too -- the
        new sync takes it over (a folder synced after its files were synced one by one); the
        caller then takes the covered roots off the other sync (main._hand_over_roots).
        Otherwise copies between two auto-syncs are left alone. Forgets the losing copies'
        rows, drops any ingest-only datasource left with no documents, and returns the losing
        doc_ids for the caller to delete from the stores.
        """
        # The identity part of a doc_id: everything after "{config_id}:". The same file reached
        # through two different selections has two doc_ids and one identity.
        same_identity = """
            substr(other.doc_id, length(other.config_id) + 2) = substr(mine.doc_id, length(mine.config_id) + 2)
            AND other.config_id <> mine.config_id
        """
        async with self.pool.acquire() as conn:
            others = await conn.fetch(f"""
                SELECT other.doc_id, other.config_id
                FROM document_state mine
                JOIN document_state other ON {same_identity}
                JOIN datasource_config odc ON odc.config_id = other.config_id
                WHERE mine.config_id = $1 AND odc.auto_sync = FALSE
            """, config_id)
            mine = await conn.fetch(f"""
                SELECT DISTINCT mine.doc_id, mine.config_id
                FROM document_state mine
                JOIN datasource_config mdc ON mdc.config_id = mine.config_id
                JOIN document_state other ON {same_identity}
                JOIN datasource_config odc ON odc.config_id = other.config_id
                WHERE mine.config_id = $1 AND (mdc.auto_sync = FALSE OR NOT mine.auto_sync)
                  AND odc.auto_sync = TRUE AND other.auto_sync
            """, config_id)
            synced_others = []
            if sync_takeover:
                synced_others = await conn.fetch(f"""
                    SELECT other.doc_id, other.config_id
                    FROM document_state mine
                    JOIN datasource_config mdc ON mdc.config_id = mine.config_id
                    JOIN document_state other ON {same_identity}
                    JOIN datasource_config odc ON odc.config_id = other.config_id
                    WHERE mine.config_id = $1 AND mdc.auto_sync = TRUE AND mine.auto_sync
                      AND odc.auto_sync = TRUE
                """, config_id)
            losers = list(others) + list(mine) + list(synced_others)
            if not losers:
                return []
            doc_ids = list(dict.fromkeys(r["doc_id"] for r in losers))
            await conn.execute("DELETE FROM document_state WHERE doc_id = ANY($1::text[])", doc_ids)
            emptied = await conn.fetch("""
                DELETE FROM datasource_config dc
                WHERE dc.config_id = ANY($1::text[]) AND dc.auto_sync = FALSE
                  AND NOT EXISTS (SELECT 1 FROM document_state ds WHERE ds.config_id = dc.config_id)
                RETURNING config_id
            """, list({r["config_id"] for r in losers}))
        logger.info(
            f"{config_id}: {len(others)} older ingest cop(ies) superseded, {len(mine)} document(s) "
            f"left to the auto-sync that already holds them; {len(emptied)} emptied ingest "
            f"record(s) removed"
        )
        return doc_ids

    async def registry_rows(self, doc_ids: List[str]) -> Dict[str, dict]:
        """Per doc_id: its source_id, source_path, and its datasource's source_type and
        connection_params (doc_refs names and links search results with them)."""
        async with self.pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT d.doc_id, d.source_id, d.source_path, c.source_type, c.connection_params "
                "FROM document_state d LEFT JOIN datasource_config c ON c.config_id = d.config_id "
                "WHERE d.doc_id = ANY($1::text[])",
                list(doc_ids),
            )
        out = {}
        for r in records:
            params = r["connection_params"] or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except ValueError:
                    params = {}
            out[r["doc_id"]] = {"source_id": r["source_id"], "source_path": r["source_path"] or "",
                                "source_type": r["source_type"] or "", "connection_params": params}
        return out

    # ----- Sync cursors (Microsoft Graph deltaLinks) -----

    async def _ensure_cursor_table(self, conn) -> None:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS msgraph_delta_state (
                config_id  TEXT PRIMARY KEY,
                delta_link TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

    async def load_sync_cursor(self, config_id: str) -> Optional[str]:
        """A datasource's persisted change cursor (Microsoft Graph deltaLink), if any."""
        async with self.pool.acquire() as conn:
            await self._ensure_cursor_table(conn)
            return await conn.fetchval(
                "SELECT delta_link FROM msgraph_delta_state WHERE config_id = $1", config_id)

    async def save_sync_cursor(self, config_id: str, cursor: str) -> None:
        async with self.pool.acquire() as conn:
            await self._ensure_cursor_table(conn)
            await conn.execute(
                """
                INSERT INTO msgraph_delta_state (config_id, delta_link, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (config_id)
                DO UPDATE SET delta_link = EXCLUDED.delta_link, updated_at = NOW()
                """,
                config_id, cursor,
            )

