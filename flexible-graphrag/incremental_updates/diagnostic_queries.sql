-- Flexible GraphRAG Incremental - Diagnostic Queries
-- Run these in pgAdmin to inspect the system state

-- ============================================================
-- 1. VIEW ALL DATASOURCES
-- ============================================================
SELECT 
    config_id,
    project_id,
    source_type,
    source_name,
    connection_params,
    refresh_interval_seconds,
    watchdog_filesystem_seconds,
    enable_change_stream,
    skip_graph,
    is_active,
    sync_status,
    last_sync_ordinal,
    last_sync_completed_at,
    last_error,
    created_at,
    updated_at
FROM datasource_config
ORDER BY created_at DESC;

-- ============================================================
-- 2. VIEW DOCUMENT STATES
-- ============================================================
SELECT 
    doc_id,
    config_id,
    source_path,
    source_id,
    ordinal,
    content_hash,
    modified_timestamp,
    vector_synced_at,
    search_synced_at,
    graph_synced_at,
    created_at,
    updated_at
FROM document_state
ORDER BY updated_at DESC;

-- ============================================================
-- 3. SYNC STATISTICS BY DATASOURCE
-- ============================================================
-- Shows current active documents (deleted docs are removed from state)
SELECT 
    ds.config_id,
    ds.source_name,
    ds.sync_status,
    ds.last_sync_completed_at,
    COUNT(doc.doc_id) as total_docs,
    SUM(CASE WHEN doc.vector_synced_at IS NOT NULL THEN 1 ELSE 0 END) as vector_synced,
    SUM(CASE WHEN doc.search_synced_at IS NOT NULL THEN 1 ELSE 0 END) as search_synced,
    SUM(CASE WHEN doc.graph_synced_at IS NOT NULL THEN 1 ELSE 0 END) as graph_synced
FROM datasource_config ds
LEFT JOIN document_state doc ON ds.config_id = doc.config_id
GROUP BY ds.config_id, ds.source_name, ds.sync_status, ds.last_sync_completed_at
ORDER BY ds.created_at DESC;

-- ============================================================
-- 4. FIND DUPLICATE DATASOURCES
-- ============================================================
SELECT 
    source_name,
    COUNT(*) as count,
    STRING_AGG(config_id::text, ', ') as config_ids
FROM datasource_config
GROUP BY source_name
HAVING COUNT(*) > 1;

-- ============================================================
-- 5. FIND DOCUMENTS WITH INCOMPLETE SYNC
-- ============================================================
-- Note: Deleted documents are removed from state, so this only shows active docs
SELECT 
    doc_id,
    source_path,
    source_id,
    modified_timestamp,
    CASE 
        WHEN vector_synced_at IS NULL THEN 'Missing vector'
        WHEN search_synced_at IS NULL THEN 'Missing search'
        WHEN graph_synced_at IS NULL THEN 'Missing graph'
        ELSE 'Complete'
    END as sync_status,
    vector_synced_at,
    search_synced_at,
    graph_synced_at,
    updated_at
FROM document_state
ORDER BY updated_at DESC;

-- ============================================================
-- 6. VIEW DOCUMENTS BY SOURCE_ID (Cloud Sources)
-- ============================================================
-- Useful for Google Drive, OneDrive, S3 with file IDs
SELECT 
    doc_id,
    config_id,
    source_id,
    source_path,
    modified_timestamp,
    content_hash,
    vector_synced_at,
    updated_at
FROM document_state
WHERE source_id IS NOT NULL
ORDER BY updated_at DESC;

-- ============================================================
-- 7. FIND DOCUMENTS WITH RECENT MODIFICATIONS
-- ============================================================
-- Shows documents with modified_timestamp in the last 24 hours
SELECT 
    doc_id,
    source_path,
    source_id,
    modified_timestamp,
    ordinal,
    updated_at
FROM document_state
WHERE modified_timestamp IS NOT NULL
  AND modified_timestamp > (NOW() - INTERVAL '24 hours')::text
ORDER BY modified_timestamp DESC;

-- ============================================================
-- 8. CLOUD SOURCE STATISTICS
-- ============================================================
-- Count documents by datasource with source_id (cloud sources)
SELECT 
    ds.config_id,
    ds.source_name,
    ds.source_type,
    COUNT(doc.doc_id) as total_docs,
    COUNT(doc.source_id) as docs_with_source_id,
    COUNT(doc.modified_timestamp) as docs_with_mod_timestamp
FROM datasource_config ds
LEFT JOIN document_state doc ON ds.config_id = doc.config_id
GROUP BY ds.config_id, ds.source_name, ds.source_type
ORDER BY total_docs DESC;

-- ============================================================
-- CLEANUP QUERIES (Use carefully!)
-- ============================================================

-- Clean up all TEST datasources (keeps most recent)
-- DELETE FROM datasource_config
-- WHERE source_name = 'Test Documents'
-- AND config_id NOT IN (
--     SELECT config_id 
--     FROM datasource_config 
--     WHERE source_name = 'Test Documents'
--     ORDER BY created_at DESC 
--     LIMIT 1
-- );

-- Reset all document states (complete cleanup)
-- DELETE FROM document_state;

-- Reset specific document
-- DELETE FROM document_state WHERE source_path = 'test_document.txt';

-- Deactivate old datasources without deleting
-- UPDATE datasource_config 
-- SET is_active = FALSE 
-- WHERE source_name = 'Test Documents' 
-- AND config_id != (
--     SELECT config_id 
--     FROM datasource_config 
--     WHERE source_name = 'Test Documents' 
--     ORDER BY created_at DESC 
--     LIMIT 1
-- );
