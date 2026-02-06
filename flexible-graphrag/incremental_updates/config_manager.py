"""
Configuration Manager

Manages datasource configurations in PostgreSQL.
Supports multiple data sources per project with persistent configuration.
"""

import asyncpg
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, AsyncGenerator
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class DataSourceConfig:
    """Data source configuration"""
    config_id: str
    project_id: str
    source_type: str  # filesystem, s3, gcs, azure_blob, google_drive, onedrive, sharepoint, box
    source_name: str
    connection_params: Dict  # JSON config for the source
    refresh_interval_seconds: int = 3600  # Default 1 hour (periodic full scan)
    watchdog_filesystem_seconds: int = 60  # Default 1 minute (delay before processing file changes detected by watchdog filesystem monitor)
    enable_change_stream: bool = False
    skip_graph: bool = False  # If True, skip graph extraction for this datasource
    is_active: bool = True
    sync_status: str = 'idle'  # idle, syncing, error
    last_sync_ordinal: Optional[int] = None
    last_sync_completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ConfigManager:
    """Manages datasource configurations"""
    
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
        """Create datasource_config table if not exists"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS datasource_config (
                    config_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    connection_params JSONB NOT NULL,
                    refresh_interval_seconds INTEGER NOT NULL DEFAULT 3600,
                    watchdog_filesystem_seconds INTEGER NOT NULL DEFAULT 60,
                    enable_change_stream BOOLEAN NOT NULL DEFAULT FALSE,
                    skip_graph BOOLEAN NOT NULL DEFAULT FALSE,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    sync_status TEXT NOT NULL DEFAULT 'idle',
                    last_sync_ordinal BIGINT,
                    last_sync_completed_at TIMESTAMPTZ,
                    last_error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            
            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_datasource_config_project_id 
                ON datasource_config(project_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_datasource_config_is_active 
                ON datasource_config(is_active)
            """)
    
    async def create_config(self, config: DataSourceConfig) -> str:
        """Create new datasource config"""
        if not config.config_id:
            config.config_id = str(uuid4())
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO datasource_config 
                (config_id, project_id, source_type, source_name, connection_params,
                 refresh_interval_seconds, watchdog_filesystem_seconds, enable_change_stream, skip_graph, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, config.config_id, config.project_id, config.source_type, 
                config.source_name, json.dumps(config.connection_params),
                config.refresh_interval_seconds, config.watchdog_filesystem_seconds,
                config.enable_change_stream, config.skip_graph,
                config.is_active)
        
        return config.config_id
    
    async def get_config(self, config_id: str) -> Optional[DataSourceConfig]:
        """Get datasource config by ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM datasource_config WHERE config_id = $1",
                config_id
            )
            if not row:
                return None
            
            return self._row_to_config(row)
    
    async def get_all_active_configs(self) -> List[DataSourceConfig]:
        """Get all active datasource configs"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM datasource_config WHERE is_active = TRUE ORDER BY created_at"
            )
            return [self._row_to_config(row) for row in rows]
    
    async def update_sync_status(self, config_id: str, status: str, 
                                  ordinal: Optional[int] = None,
                                  error: Optional[str] = None):
        """Update sync status"""
        async with self.pool.acquire() as conn:
            if status == 'idle' and ordinal is not None:
                # Successful completion
                await conn.execute("""
                    UPDATE datasource_config 
                    SET sync_status = $1, 
                        last_sync_ordinal = $2,
                        last_sync_completed_at = NOW(),
                        last_error = NULL,
                        updated_at = NOW()
                    WHERE config_id = $3
                """, status, ordinal, config_id)
            elif status == 'error':
                await conn.execute("""
                    UPDATE datasource_config 
                    SET sync_status = $1, 
                        last_error = $2,
                        updated_at = NOW()
                    WHERE config_id = $3
                """, status, error, config_id)
            else:
                await conn.execute("""
                    UPDATE datasource_config 
                    SET sync_status = $1, 
                        updated_at = NOW()
                    WHERE config_id = $2
                """, status, config_id)
    
    async def update_last_sync(self, config_id: str, ordinal: int):
        """Update last sync ordinal (convenience method)"""
        await self.update_sync_status(config_id, 'idle', ordinal=ordinal)
    
    async def update_config(self, config_id: str, **kwargs):
        """Update datasource config fields"""
        allowed_fields = {
            'source_name', 'connection_params', 'refresh_interval_seconds',
            'enable_change_stream', 'is_active'
        }
        
        updates = []
        values = []
        param_num = 1
        
        for key, value in kwargs.items():
            if key in allowed_fields:
                if key == 'connection_params':
                    value = json.dumps(value)
                updates.append(f"{key} = ${param_num}")
                values.append(value)
                param_num += 1
        
        if not updates:
            return
        
        values.append(config_id)
        query = f"""
            UPDATE datasource_config 
            SET {', '.join(updates)}, updated_at = NOW()
            WHERE config_id = ${param_num}
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, *values)
    
    async def delete_config(self, config_id: str):
        """Delete datasource config (hard delete)"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM datasource_config WHERE config_id = $1",
                config_id
            )
    
    async def listen_for_config_changes(self) -> AsyncGenerator[Dict, None]:
        """
        Listen for config changes using PostgreSQL LISTEN/NOTIFY.
        Yields change events: {operation: 'insert'|'update'|'delete', config: DataSourceConfig}
        
        Note: Requires trigger setup in PostgreSQL. For now, this is a placeholder.
        In production, implement using NOTIFY/LISTEN or poll periodically.
        """
        # Placeholder implementation - poll every 30 seconds
        import asyncio
        
        known_configs = set()
        
        while True:
            try:
                configs = await self.get_all_active_configs()
                current_ids = {c.config_id for c in configs}
                
                # Check for new configs
                new_ids = current_ids - known_configs
                for config_id in new_ids:
                    config = await self.get_config(config_id)
                    if config:
                        yield {'operation': 'insert', 'config': config}
                
                # Check for removed configs
                removed_ids = known_configs - current_ids
                for config_id in removed_ids:
                    yield {'operation': 'delete', 'config_id': config_id}
                
                known_configs = current_ids
                
            except Exception as e:
                print(f"Error monitoring config changes: {e}")
            
            await asyncio.sleep(30)
    
    def _row_to_config(self, row) -> DataSourceConfig:
        """Convert database row to DataSourceConfig"""
        return DataSourceConfig(
            config_id=row['config_id'],
            project_id=row['project_id'],
            source_type=row['source_type'],
            source_name=row['source_name'],
            connection_params=json.loads(row['connection_params']) if isinstance(row['connection_params'], str) else row['connection_params'],
            refresh_interval_seconds=row['refresh_interval_seconds'],
            watchdog_filesystem_seconds=row.get('watchdog_filesystem_seconds', 60),
            enable_change_stream=row['enable_change_stream'],
            skip_graph=row.get('skip_graph', False),
            is_active=row['is_active'],
            sync_status=row['sync_status'],
            last_sync_ordinal=row['last_sync_ordinal'],
            last_sync_completed_at=row['last_sync_completed_at'],
            last_error=row['last_error'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

