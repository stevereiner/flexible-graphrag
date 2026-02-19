-- Initialize pgvector extension for Flexible GraphRAG
-- This script runs automatically when the PostgreSQL container starts
-- Note: This runs in the default database context (flexible_graphrag)
-- which is set by POSTGRES_DB environment variable

-- Create the vector extension in flexible_graphrag database
-- (NOT in flexible_graphrag_incremental - that's for state management only)
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON DATABASE flexible_graphrag TO postgres;

-- Create a sample table structure (optional - LlamaIndex will create tables as needed)
-- This is just for reference and testing
CREATE TABLE IF NOT EXISTS sample_vectors (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(1536),  -- Adjust dimension based on your embedding model
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create an index for vector similarity search
CREATE INDEX IF NOT EXISTS sample_vectors_embedding_idx ON sample_vectors 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Display confirmation
SELECT 'pgvector extension initialized in flexible_graphrag database' as status;
