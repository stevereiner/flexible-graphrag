-- Flexible GraphRAG Incremental Update System
-- PostgreSQL Schema
--
-- NOTE: You can reuse the existing postgres-pgvector Docker service!
-- - postgres-pgvector.yaml provides PostgreSQL on port 5433 (avoids conflict with Alfresco's port 5432)
-- - Includes pgAdmin for database management (http://localhost:5050)
-- - Just create a second database "flexible_graphrag_incremental" in the same PostgreSQL instance
-- - The pgvector extension is NOT needed for incremental updates (just regular tables)
--
-- Setup:
-- 1. Create database:
--    docker exec -it flexible-graphrag-postgres-pgvector-1 \
--      psql -U postgres -c "CREATE DATABASE flexible_graphrag_incremental;"
--
-- 2. Run this schema:
--    docker exec -i flexible-graphrag-postgres-pgvector-1 \
--      psql -U postgres -d flexible_graphrag_incremental < incremental_updates/schema.sql
--
-- 3. Connection string:
--    postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental

-- Table: datasource_config
-- Stores configuration for monitored data sources
CREATE TABLE IF NOT EXISTS datasource_config (
    config_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- filesystem, s3, gcs, azure_blob, google_drive, onedrive, sharepoint, box
    source_name TEXT NOT NULL,
    connection_params JSONB NOT NULL,  -- Source-specific connection parameters
    refresh_interval_seconds INTEGER NOT NULL DEFAULT 300,
    watchdog_filesystem_seconds INTEGER NOT NULL DEFAULT 60,  -- Filesystem watchdog debounce delay
    enable_change_stream BOOLEAN NOT NULL DEFAULT FALSE,
    skip_graph BOOLEAN NOT NULL DEFAULT FALSE,  -- If TRUE, skip graph extraction (vector + search only)
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sync_status TEXT NOT NULL DEFAULT 'idle',  -- idle, syncing, error
    last_sync_ordinal BIGINT,  -- Last processed ordinal (microsecond timestamp)
    last_sync_completed_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_datasource_config_project_id 
ON datasource_config(project_id);

CREATE INDEX IF NOT EXISTS idx_datasource_config_is_active 
ON datasource_config(is_active);

-- Table: document_state
-- Tracks processing state for each document
CREATE TABLE IF NOT EXISTS document_state (
    doc_id TEXT PRIMARY KEY,  -- Unique ID: config_id:source_path
    config_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_id TEXT,  -- Source-specific file ID (e.g., Google Drive file ID)
    ordinal BIGINT NOT NULL,  -- Microsecond timestamp
    content_hash TEXT NOT NULL,  -- SHA-256 hash for content change detection
    modified_timestamp TIMESTAMPTZ,  -- Source modification timestamp (for quick change detection)
    vector_synced_at TIMESTAMPTZ,  -- When vector index was last updated
    search_synced_at TIMESTAMPTZ,  -- When search index was last updated
    graph_synced_at TIMESTAMPTZ,  -- When graph index was last updated
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_state_config_id 
ON document_state(config_id);

CREATE INDEX IF NOT EXISTS idx_document_state_ordinal 
ON document_state(config_id, ordinal);

CREATE INDEX IF NOT EXISTS idx_document_state_source_id 
ON document_state(config_id, source_id);

-- Sample data for testing (optional)
-- INSERT INTO datasource_configs 
-- (config_id, project_id, source_type, source_name, connection_params, refresh_interval_seconds)
-- VALUES 
-- ('test-fs-1', 'project-1', 'filesystem', 'Local Documents', 
--  '{"paths": ["./data/documents"]}', 300);

