-- Initialize schema for the incremental updates database
-- Runs automatically when the PostgreSQL container starts (after 02-init-incremental.sql)

\connect flexible_graphrag_incremental

-- Table: datasource_config
CREATE TABLE IF NOT EXISTS datasource_config (
    config_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    connection_params JSONB NOT NULL,
    refresh_interval_seconds INTEGER NOT NULL DEFAULT 300,
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
);

CREATE INDEX IF NOT EXISTS idx_datasource_config_project_id ON datasource_config(project_id);
CREATE INDEX IF NOT EXISTS idx_datasource_config_is_active ON datasource_config(is_active);

-- Table: document_state
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
);

CREATE INDEX IF NOT EXISTS idx_document_state_config_id ON document_state(config_id);
CREATE INDEX IF NOT EXISTS idx_document_state_ordinal ON document_state(config_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_document_state_source_id ON document_state(config_id, source_id);

SELECT 'Incremental updates schema initialized successfully' AS status;
