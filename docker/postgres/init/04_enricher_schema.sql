-- ─────────────────────────────────────────────────────────────────────────────
-- Enricher schema: semantic similarity and entity extraction support
-- ─────────────────────────────────────────────────────────────────────────────

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- ── Relational tables ─────────────────────────────────────────────────────────

-- Deduplicated entity store.
-- entity_id = sha256(normalized || '|' || type) computed in Python.
CREATE TABLE graphrag.entities (
    entity_id   text        PRIMARY KEY,
    name        text        NOT NULL,
    type        text        NOT NULL,   -- PERSON | ORG | LOCATION | SYSTEM | TECHNOLOGY | CONCEPT
    normalized  text        NOT NULL,
    created_at  timestamptz DEFAULT NOW()
);

-- Many-to-many: which chunks mention which entities (per model run).
CREATE TABLE graphrag.chunk_entities (
    chunk_id    text NOT NULL REFERENCES graphrag.chunks(chunk_id)   ON DELETE CASCADE,
    entity_id   text NOT NULL REFERENCES graphrag.entities(entity_id) ON DELETE CASCADE,
    model       text NOT NULL,
    PRIMARY KEY (chunk_id, entity_id, model)
);

-- Enrichment tracking for incremental runs.
-- content_hash = sha256 of the chunk content at extraction time.
-- If the chunk content changes (same chunk_id, new content after doc edit)
-- the hash will differ → enricher re-processes that chunk.
CREATE TABLE graphrag.enrichment_log (
    chunk_id        text        NOT NULL REFERENCES graphrag.chunks(chunk_id) ON DELETE CASCADE,
    model           text        NOT NULL,
    content_hash    text        NOT NULL,
    enriched_at     timestamptz DEFAULT NOW(),
    PRIMARY KEY (chunk_id, model)
);

-- ── AGE graph labels ──────────────────────────────────────────────────────────

SELECT * FROM ag_catalog.create_vlabel('knowledge_graph', 'Entity');
SELECT * FROM ag_catalog.create_elabel('knowledge_graph', 'MENTIONS');
SELECT * FROM ag_catalog.create_elabel('knowledge_graph', 'SIMILAR_TO');
