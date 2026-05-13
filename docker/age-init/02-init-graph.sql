-- Create the default AGE knowledge graph (idempotent)

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'knowledge_graph') THEN
        PERFORM ag_catalog.create_graph('knowledge_graph');
        RAISE NOTICE 'AGE graph knowledge_graph created';
    ELSE
        RAISE NOTICE 'AGE graph knowledge_graph already exists';
    END IF;
END $$;

SELECT name, namespace FROM ag_catalog.ag_graph WHERE name = 'knowledge_graph';
