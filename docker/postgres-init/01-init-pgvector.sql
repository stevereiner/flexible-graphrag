-- Initialize pgvector extension for Flexible GraphRAG
-- This script runs automatically when the PostgreSQL container starts

-- Create the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create a database for flexible-graphrag if it doesn't exist
-- (Note: The main database is already created via POSTGRES_DB environment variable)

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
SELECT 'pgvector extension initialized successfully for Flexible GraphRAG' as status;
