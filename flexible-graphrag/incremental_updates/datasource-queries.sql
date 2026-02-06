-- ============================================================
-- Datasource Configuration Queries for pgAdmin
-- Quick reference for managing incremental sync datasources
-- ============================================================

-- ============================================================
-- LISTING QUERIES
-- ============================================================

-- List all datasources (basic info)
SELECT 
    config_id,
    source_name,
    source_type,
    is_active,
    sync_status,
    last_sync_completed_at,
    refresh_interval_seconds,
    skip_graph,
    created_at
FROM datasource_config 
ORDER BY created_at DESC;

-- Show connection parameters (formatted JSON)
SELECT 
    config_id,
    source_name,
    source_type,
    is_active,
    jsonb_pretty(connection_params) as config
FROM datasource_config
ORDER BY created_at DESC;

-- Count documents per datasource
SELECT 
    ds.config_id,
    ds.source_name,
    ds.source_type,
    COUNT(doc.doc_id) as document_count,
    ds.is_active,
    ds.sync_status
FROM datasource_config ds
LEFT JOIN document_state doc ON ds.config_id = doc.config_id
GROUP BY ds.config_id, ds.source_name, ds.source_type, ds.is_active, ds.sync_status
ORDER BY ds.created_at DESC;

-- ============================================================
-- SPECIFIC DATASOURCE QUERIES
-- ============================================================

-- Get your current S3 datasource (replace config_id)
SELECT * FROM datasource_config 
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

-- Get connection params for your S3 datasource
SELECT 
    config_id,
    source_name,
    jsonb_pretty(connection_params) as config
FROM datasource_config 
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

-- Get documents for your S3 datasource
SELECT 
    doc_id,
    source_path,
    content_hash,
    vector_synced_at,
    search_synced_at,
    graph_synced_at,
    created_at
FROM document_state
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b'
ORDER BY created_at DESC;

-- ============================================================
-- UPDATE QUERIES
-- ============================================================

-- Add SQS queue URL to existing S3 datasource
UPDATE datasource_config
SET 
    connection_params = connection_params || '{"sqs_queue_url": "https://sqs.us-east-2.amazonaws.com/996083107418/graphrag-s3-events"}'::jsonb,
    updated_at = NOW()
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

-- Remove SQS queue URL (revert to polling)
UPDATE datasource_config
SET 
    connection_params = connection_params - 'sqs_queue_url',
    updated_at = NOW()
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

-- Update refresh interval (in seconds)
UPDATE datasource_config
SET 
    refresh_interval_seconds = 3600,  -- 1 hour
    updated_at = NOW()
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

-- Enable a datasource
UPDATE datasource_config
SET 
    is_active = true,
    updated_at = NOW()
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

-- Disable a datasource
UPDATE datasource_config
SET 
    is_active = false,
    updated_at = NOW()
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

-- ============================================================
-- BULK OPERATIONS
-- ============================================================

-- Disable all datasources
UPDATE datasource_config
SET is_active = false, updated_at = NOW();

-- Enable all datasources
UPDATE datasource_config
SET is_active = true, updated_at = NOW();

-- Set all datasources to 24 hour polling
UPDATE datasource_config
SET refresh_interval_seconds = 86400, updated_at = NOW();

-- ============================================================
-- STATISTICS & MONITORING
-- ============================================================

-- Sync statistics per datasource
SELECT 
    config_id,
    COUNT(*) as total_docs,
    COUNT(*) FILTER (WHERE vector_synced_at IS NOT NULL) as vector_synced,
    COUNT(*) FILTER (WHERE search_synced_at IS NOT NULL) as search_synced,
    COUNT(*) FILTER (WHERE graph_synced_at IS NOT NULL) as graph_synced
FROM document_state
GROUP BY config_id;

-- Recently synced datasources
SELECT 
    config_id,
    source_name,
    source_type,
    last_sync_completed_at,
    sync_status,
    last_error
FROM datasource_config
WHERE last_sync_completed_at IS NOT NULL
ORDER BY last_sync_completed_at DESC;

-- Datasources with errors
SELECT 
    config_id,
    source_name,
    sync_status,
    last_error,
    last_sync_completed_at
FROM datasource_config
WHERE sync_status = 'error'
ORDER BY updated_at DESC;

-- ============================================================
-- CLEANUP QUERIES
-- ============================================================

-- Delete a specific datasource (use carefully!)
-- DELETE FROM datasource_config WHERE config_id = 'YOUR_CONFIG_ID';

-- Delete all document states for a datasource (use carefully!)
-- DELETE FROM document_state WHERE config_id = 'YOUR_CONFIG_ID';

-- ============================================================
-- DEBUG QUERIES
-- ============================================================

-- Check if SQS is configured
SELECT 
    config_id,
    source_name,
    connection_params->>'sqs_queue_url' as sqs_url,
    CASE 
        WHEN connection_params->>'sqs_queue_url' IS NOT NULL THEN 'event-based'
        ELSE 'polling'
    END as sync_mode
FROM datasource_config
WHERE source_type = 's3';

-- Full datasource details
SELECT 
    config_id,
    project_id,
    source_type,
    source_name,
    is_active,
    sync_status,
    last_sync_ordinal,
    last_sync_completed_at,
    last_error,
    refresh_interval_seconds,
    watchdog_filesystem_seconds,
    enable_change_stream,
    skip_graph,
    created_at,
    updated_at,
    jsonb_pretty(connection_params) as config
FROM datasource_config
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

-- ============================================================
-- NOTES
-- ============================================================
/*

Your current datasource ID: f57c4872-dd05-403e-a451-bb5a8ebe6d7b
Your SQS queue URL: https://sqs.us-east-2.amazonaws.com/996083107418/graphrag-s3-events
Your S3 bucket: stevereiner-bucket-1

To add SQS to your existing datasource, run:
UPDATE datasource_config
SET connection_params = connection_params || '{"sqs_queue_url": "https://sqs.us-east-2.amazonaws.com/996083107418/graphrag-s3-events"}'::jsonb
WHERE config_id = 'f57c4872-dd05-403e-a451-bb5a8ebe6d7b';

Then restart backend or call: curl -X POST http://localhost:8000/api/sync/start-monitoring

*/
