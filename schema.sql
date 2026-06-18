-- Schema for Supabase Postgres (with pgvector)
-- Replaces the legacy job_skill_stats / job_count tables; aggregation now
-- happens at query time over the per-posting table below.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Legacy tables (safe to drop on cutover).
DROP TABLE IF EXISTS job_skill_stats;
DROP TABLE IF EXISTS job_count;

CREATE TABLE IF NOT EXISTS job_postings (
    posting_id      UUID PRIMARY KEY,
    job_title       TEXT NOT NULL,
    company         TEXT,
    skills          TEXT[] NOT NULL,
    seniority       TEXT,
    posting_year    INT,
    posted_date     DATE,
    title_embedding vector(384)
);

CREATE INDEX IF NOT EXISTS idx_jp_embedding
    ON job_postings USING hnsw (title_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_jp_title_fts
    ON job_postings USING gin (to_tsvector('english', job_title));
-- Trigram index powers hybrid lexical scoring (similarity(job_title, query))
-- which catches typos like "embeded" → "embedded" that the bge-small
-- embedding misses (different subword tokenization).
CREATE INDEX IF NOT EXISTS idx_jp_title_trgm
    ON job_postings USING gin (job_title gin_trgm_ops);

-- Content-hash dedup. uuid5 over normalized (company, job_title,
-- job_description). Bare ON CONFLICT DO NOTHING on INSERT lets this
-- unique constraint cooperate with the PK on posting_id.
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS content_hash UUID;
CREATE UNIQUE INDEX IF NOT EXISTS idx_jp_content_hash
    ON job_postings (content_hash)
    WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jp_seniority
    ON job_postings (seniority);
CREATE INDEX IF NOT EXISTS idx_jp_year
    ON job_postings (posting_year);
