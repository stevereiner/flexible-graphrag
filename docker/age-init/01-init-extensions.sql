-- AGE + pgvector init for flexible_graphrag_age
-- Runs in the default database context (flexible_graphrag_age, set by POSTGRES_DB).

-- Apache AGE graph extension
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- pgvector extension for vector similarity search alongside graph traversal
CREATE EXTENSION IF NOT EXISTS vector;

SELECT 'AGE + pgvector extensions enabled in flexible_graphrag_age' AS status;
