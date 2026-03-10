-- ─────────────────────────────────────────────────────────────────────────────
-- Bootstrap Apache AGE graph for GraphRAG
--
-- NOTE: The AGE graph is named "knowledge_graph" (not "graphrag") to avoid a schema name
-- collision with the relational schema also named "graphrag" created in
-- 02_schema.sql. AGE's create_graph() creates a PostgreSQL schema of the
-- same name, so the two names must differ.
-- ─────────────────────────────────────────────────────────────────────────────

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Create the named graph
SELECT * FROM ag_catalog.create_graph('knowledge_graph');

-- Vertex labels
SELECT * FROM ag_catalog.create_vlabel('knowledge_graph', 'Document');
SELECT * FROM ag_catalog.create_vlabel('knowledge_graph', 'Chunk');

-- Edge labels
SELECT * FROM ag_catalog.create_elabel('knowledge_graph', 'HAS_CHUNK');
SELECT * FROM ag_catalog.create_elabel('knowledge_graph', 'LINKS_TO');
SELECT * FROM ag_catalog.create_elabel('knowledge_graph', 'NEXT_CHUNK');
