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
from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime, timezone


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
    graph_synced_at: Optional[datetime] = None
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
                graph_synced_at=row['graph_synced_at']
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
                graph_synced_at=row['graph_synced_at']
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
                    graph_synced_at=row['graph_synced_at']
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
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO document_state 
                (doc_id, config_id, source_path, source_id, ordinal, content_hash, modified_timestamp,
                 vector_synced_at, search_synced_at, graph_synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (doc_id) DO UPDATE SET
                    source_id = COALESCE(EXCLUDED.source_id, document_state.source_id),
                    ordinal = EXCLUDED.ordinal,
                    content_hash = EXCLUDED.content_hash,
                    modified_timestamp = EXCLUDED.modified_timestamp,
                    vector_synced_at = EXCLUDED.vector_synced_at,
                    search_synced_at = EXCLUDED.search_synced_at,
                    graph_synced_at = EXCLUDED.graph_synced_at,
                    updated_at = NOW()
            """, state.doc_id, state.config_id, state.source_path, state.source_id, state.ordinal,
                state.content_hash, modified_ts, vector_ts, search_ts, graph_ts)
    
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

