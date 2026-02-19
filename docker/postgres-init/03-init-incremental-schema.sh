#!/bin/bash
# Initialize schema for incremental updates database
# This script runs automatically when the PostgreSQL container starts
# NOTE: This database is for state management ONLY - no pgvector extension needed

set -e

# Wait a moment for database to be created
sleep 1

# Apply the incremental updates schema (state management tables only)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "flexible_graphrag_incremental" <<-EOSQL
    -- Flexible GraphRAG Incremental Update System
    -- PostgreSQL Schema

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

    SELECT 'Incremental updates schema initialized successfully' as status;
EOSQL

echo "Incremental updates schema applied successfully"
