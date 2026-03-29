CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS cases (
    id                  BIGSERIAL PRIMARY KEY,
    case_id             TEXT UNIQUE NOT NULL,
    year                INTEGER NOT NULL,
    title               TEXT,
    petitioner          TEXT,
    respondent          TEXT,
    date_of_judgment    DATE,
    bench               TEXT,
    court               TEXT DEFAULT 'Supreme Court of India',
    disposal_nature     TEXT,
    citation            TEXT,
    s3_key              TEXT,
    pdf_url             TEXT,
    full_text           TEXT,
    summary             TEXT,
    acts_mentioned      TEXT[],
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id              BIGSERIAL PRIMARY KEY,
    case_id         TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    token_count     INTEGER,
    embedding       vector(1536),
    ts_vector       tsvector,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (case_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_cases_year       ON cases(year);
CREATE INDEX IF NOT EXISTS idx_cases_disposal   ON cases(disposal_nature);
CREATE INDEX IF NOT EXISTS idx_cases_petitioner ON cases USING gin(petitioner gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_chunks_ts        ON chunks USING gin(ts_vector);

CREATE TABLE IF NOT EXISTS search_logs (
    id          BIGSERIAL PRIMARY KEY,
    query       TEXT NOT NULL,
    results     INTEGER,
    latency_ms  INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_segments (
    id              BIGSERIAL PRIMARY KEY,
    case_id         TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    segment_type    TEXT NOT NULL,
    para_start      INTEGER NOT NULL,
    para_end        INTEGER NOT NULL,
    confidence      REAL DEFAULT 0.0,
    model_version   TEXT DEFAULT 'heuristic-v1',
    preview         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_precedents (
    id                  BIGSERIAL PRIMARY KEY,
    case_id             TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    cited_case_title    TEXT NOT NULL,
    mention_count       INTEGER DEFAULT 1,
    paragraphs          INTEGER[] DEFAULT '{}',
    extraction_method   TEXT DEFAULT 'regex-v1',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_case_segments_case ON case_segments(case_id);
CREATE INDEX IF NOT EXISTS idx_case_segments_type ON case_segments(segment_type);
CREATE INDEX IF NOT EXISTS idx_case_precedents_case ON case_precedents(case_id);

SELECT 'Schema ready.' AS status;
