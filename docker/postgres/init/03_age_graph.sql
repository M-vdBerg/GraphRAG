-- ─────────────────────────────────────────────────────────────────────────────
-- Bootstrap Apache AGE graph for GraphRAG
-- ─────────────────────────────────────────────────────────────────────────────

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Create the named graph
SELECT * FROM ag_catalog.create_graph('graphrag');

-- Vertex labels
SELECT * FROM ag_catalog.create_vlabel('graphrag', 'Document');
SELECT * FROM ag_catalog.create_vlabel('graphrag', 'Chunk');

-- Edge labels
SELECT * FROM ag_catalog.create_elabel('graphrag', 'HAS_CHUNK');
SELECT * FROM ag_catalog.create_elabel('graphrag', 'LINKS_TO');
SELECT * FROM ag_catalog.create_elabel('graphrag', 'NEXT_CHUNK');
