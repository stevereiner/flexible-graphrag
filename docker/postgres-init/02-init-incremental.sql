-- Initialize Incremental Updates Database for Flexible GraphRAG
-- This script runs automatically when the PostgreSQL container starts

-- Create the incremental updates database if it doesn't exist
SELECT 'CREATE DATABASE flexible_graphrag_incremental'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'flexible_graphrag_incremental')\gexec

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON DATABASE flexible_graphrag_incremental TO postgres;

-- Display confirmation
SELECT 'flexible_graphrag_incremental database initialized successfully' as status;
