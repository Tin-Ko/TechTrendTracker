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

-- Project recommendations catalog. Built offline by
-- data_pipeline/recommendations/build_catalog.py: each row is one portfolio
-- project that local Gemma generated from a triple of skills that co-occur in
-- real postings. The Go request path serves these with a pure
-- `skills <@ $top5` lookup -- no model at request time, no cloud LLM.
CREATE TABLE IF NOT EXISTS project_recommendations (
    project_id    UUID PRIMARY KEY,
    title         TEXT NOT NULL,
    level         TEXT NOT NULL,          -- BEGINNER | INTERMEDIATE | ADVANCED
    blurb         TEXT NOT NULL,
    skills        TEXT[] NOT NULL,        -- the 3 skills this project builds
    support_count INT  NOT NULL,          -- # postings the triple co-occurs in
    lift          REAL,                   -- association strength vs chance (>1 = real)
    score         REAL NOT NULL,          -- request-time ranking signal
    skills_key    TEXT NOT NULL UNIQUE,   -- sorted "a|b|c" dedup key for the triple
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- GIN on skills powers the request-time subset match:
--   WHERE skills <@ $top5_array   (the triple is contained by the searched top-5)
CREATE INDEX IF NOT EXISTS idx_pr_skills
    ON project_recommendations USING gin (skills);



-- ── Hierarchical search ──────────────────────────────────────────────

-- Derived title-decision columns on the fact table. Denormalized on purpose:
-- the hot path filters postings directly with two btree/GIN index hits and
-- zero joins. job_title (the raw scraped string) is never modified.
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS canonical_title TEXT;
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS role_family     TEXT;
ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS specializations TEXT[]
    NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_jp_family    ON job_postings (role_family);
CREATE INDEX IF NOT EXISTS idx_jp_canonical ON job_postings (canonical_title);
-- GIN powers the containment filter: specializations @> $query_specs
CREATE INDEX IF NOT EXISTS idx_jp_specs     ON job_postings USING gin (specializations);

-- Memoized LLM decisions: one row per distinct *normalized* raw title ever seen.
-- This table IS the taxonomy's ground truth; job_postings columns are a
-- materialization of it. Small: O(distinct titles), thousands of rows, not
-- O(postings).
CREATE TABLE IF NOT EXISTS title_map (
    raw_title_norm  TEXT PRIMARY KEY,          -- output of normalize_title_key()
    canonical_title TEXT NOT NULL,             -- lowercase display/grouping form
    role_family     TEXT,                      -- NULL = LLM abstained ("can't place")
    specializations TEXT[] NOT NULL DEFAULT '{}',
    source          TEXT NOT NULL,             -- ingest_llm | backfill | query_llm
                                               -- | manual | merge
    model_version   TEXT,                      -- e.g. "gemma4:latest@2026-07"
    prompt_version  TEXT,                      -- e.g. "title-norm-v1"
    decided_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Trigram GIN over the KEYS enables typo-tolerant query resolution against a
-- tiny table (vs. today's trigram scans over every posting title).
CREATE INDEX IF NOT EXISTS idx_title_map_trgm
    ON title_map USING gin (raw_title_norm gin_trgm_ops);

-- Family registry. Injected into the LLM prompt so it prefers reusing an
-- existing family over inventing a near-duplicate. parent_family reserved
-- for a future deeper tree (unused in v1).
CREATE TABLE IF NOT EXISTS role_families (
    family        TEXT PRIMARY KEY,
    parent_family TEXT REFERENCES role_families(family),
    posting_count INT NOT NULL DEFAULT 0,      -- maintained by reconcile job
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Controlled vocabulary for specialization tags. 'active' specs are listed in
-- the LLM prompt; LLM-proposed unknowns are inserted as 'pending' and reviewed
-- by the reconcile job (merge synonyms, promote, or reject).
CREATE TABLE IF NOT EXISTS spec_vocabulary (
    spec       TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'active', -- active | pending | rejected
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed vocabularies (design §5.2 / Appendix A) so the LLM's first prompts
-- have something to anchor to. Idempotent via ON CONFLICT DO NOTHING.
INSERT INTO role_families (family) VALUES
  ('software engineer'), ('data scientist'), ('data engineer'),
  ('machine learning engineer'), ('devops engineer'), ('security engineer'),
  ('qa engineer'), ('site reliability engineer'), ('data analyst'),
  ('product manager'), ('hardware engineer'), ('solutions architect')
ON CONFLICT DO NOTHING;

INSERT INTO spec_vocabulary (spec) VALUES
  ('backend'), ('frontend'), ('fullstack'), ('web'), ('mobile'), ('ios'),
  ('android'), ('embedded'), ('firmware'), ('platform'), ('infrastructure'),
  ('cloud'), ('distributed systems'), ('ml'), ('ai'), ('nlp'),
  ('computer vision'), ('llm'), ('gamedev'), ('graphics'), ('reliability'),
  ('networking'), ('payments'), ('search'), ('blockchain')
ON CONFLICT DO NOTHING;

-- Inspectable "tree": one row per (family, canonical, specs) with counts.
CREATE OR REPLACE VIEW taxonomy_tree AS
SELECT role_family,
       canonical_title,
       specializations,
       COUNT(*)::int AS posting_count
FROM job_postings
WHERE role_family IS NOT NULL
GROUP BY role_family, canonical_title, specializations
ORDER BY role_family, posting_count DESC;
