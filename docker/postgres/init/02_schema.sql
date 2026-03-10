-- ─────────────────────────────────────────────────────────────────────────────
-- GraphRAG relational schema
-- ─────────────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS graphrag;

-- ── Documents ──────────────────────────────────────────────────────────────

CREATE TABLE graphrag.documents (
    doc_id      CHAR(64)    PRIMARY KEY,                -- SHA-256 hex of absolute file path
    file_path   TEXT        NOT NULL UNIQUE,            -- absolute path inside container
    file_name   TEXT        NOT NULL,                   -- basename
    title       TEXT,                                   -- first H1 heading or filename
    file_hash   CHAR(64)    NOT NULL,                   -- SHA-256 hex of file contents (change detection)
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Chunks ─────────────────────────────────────────────────────────────────

CREATE TABLE graphrag.chunks (
    chunk_id    CHAR(64)        PRIMARY KEY,            -- SHA-256 hex of (doc_id + heading + position)
    doc_id      CHAR(64)        NOT NULL REFERENCES graphrag.documents(doc_id) ON DELETE CASCADE,
    heading     TEXT,                                   -- heading text that opens this section
    position    INTEGER         NOT NULL,               -- ordinal within document (0-based)
    content     TEXT            NOT NULL,               -- raw markdown text of the chunk
    token_count INTEGER,                                -- approximate token count
    -- BAAI/bge-large-en-v1.5 produces 1024-dimensional embeddings.
    -- If you change EMBEDDING_MODEL to one with different dimensions,
    -- update this column type and recreate the index accordingly.
    embedding   vector(1024)    NOT NULL,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ANN index for cosine similarity search.
-- IVFFlat requires at least (lists * 3) rows to be used by the planner.
-- Run ANALYZE graphrag.chunks after a bulk load to help the planner.
-- For production with >100k rows consider switching to HNSW:
--   CREATE INDEX ON graphrag.chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_embedding_cosine_idx
    ON graphrag.chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX chunks_doc_id_idx      ON graphrag.chunks (doc_id);
CREATE INDEX chunks_position_idx    ON graphrag.chunks (doc_id, position);

-- ── Document links (mirrors AGE LINKS_TO edges) ────────────────────────────

CREATE TABLE graphrag.doc_links (
    id          BIGSERIAL   PRIMARY KEY,
    src_doc_id  CHAR(64)    NOT NULL REFERENCES graphrag.documents(doc_id) ON DELETE CASCADE,
    tgt_doc_id  CHAR(64)    NOT NULL REFERENCES graphrag.documents(doc_id) ON DELETE CASCADE,
    anchor      TEXT,                                   -- link display text
    href        TEXT,                                   -- original href value from markdown
    UNIQUE (src_doc_id, tgt_doc_id, href)
);

CREATE INDEX doc_links_src_idx ON graphrag.doc_links (src_doc_id);
CREATE INDEX doc_links_tgt_idx ON graphrag.doc_links (tgt_doc_id);
