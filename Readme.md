# Tech Trend Tracker

Tech Trend Tracker (TTT) tells you which technical skills are actually
in demand for a given job role today. You type a job title into the
search bar (e.g. *"backend engineer"*, *"embedded software engineer"*,
*"data scientist"*) and TTT shows you:

- a bar chart of the top skills appearing in real LinkedIn postings
  for that role,
- a strip of **related job titles** the system inferred semantically
  (so *"new grad backend engineer"* surfaces *"new grad software
  engineer"* and *"backend engineer 2026"*),
- counts of how many distinct postings and skills the answer is based on.

It is aimed at job seekers — especially students and entry-level
applicants — who want a data-driven view of "what tech stack should I
actually learn for the job I want" instead of guessing from vibes.

This repo contains an end-to-end implementation: scraping, LLM-based
skill extraction, semantic embedding, vector + lexical hybrid search,
a React/TypeScript SPA, and a Dockerized deploy to Google Cloud Run.

> **Setup & operations**: see [`setup.md`](setup.md) for the full
> dev-machine bootstrap, Cloud Run deploy walkthrough, and
> troubleshooting table. This README is the architectural overview.

---

## Table of contents

1. [What you see as a user](#what-you-see-as-a-user)
2. [Architecture at a glance](#architecture-at-a-glance)
3. [Tech stack and why each piece](#tech-stack-and-why-each-piece)
4. [How each part is implemented](#how-each-part-is-implemented)
   - [Ingest plane](#ingest-plane-locallong-running)
   - [Storage](#storage)
   - [Serving plane](#serving-plane-cloud-run)
   - [Frontend](#frontend)
5. [Design decisions worth knowing](#design-decisions-worth-knowing)
6. [Repo layout](#repo-layout)
7. [Running locally](#running-locally)
8. [Deploying to Cloud Run](#deploying-to-cloud-run)
9. [Out of scope (deliberately)](#out-of-scope-deliberately)

---

## What you see as a user

```
┌─────────────────────────────────────────────────────────────┐
│  TTT                                                         │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │  embedded software engineer                  →   │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                              │
│   ████████ Skills in Demand                                  │
│                                                              │
│    C++     ████████████████  12                              │
│    C       █████████████     10                              │
│    Python  ████████          7                               │
│    RTOS    ███████           5                               │
│    Linux   ██████            5                               │
│    ...                                                       │
│                                                              │
│  [Embedded SE Intern]  [Avionics Embedded SE]  [Firmware]   │
│                                                              │
│      ┌──────────┐         ┌──────────┐                       │
│      │    17    │         │    63    │                       │
│      │ Jobs     │         │ Skills   │                       │
│      └──────────┘         └──────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

The search has three notable properties:

- **No fixed taxonomy.** You can type any job title, in any wording,
  including typos. The system doesn't have a hard-coded list of
  recognized roles — it works in embedding space.
- **Concept-aware, not keyword-based.** "Backend engineer" and
  "Software Engineer, Backend" are recognized as the same role.
- **Typo-resilient.** A query like *"embeded software engineer"* still
  pulls up embedded SE postings, because lexical scoring (trigram
  similarity) catches the misspelling that pure semantic embedding
  misses.

---

## Architecture at a glance

Two planes that touch shared storage (Supabase) and a local message broker (RabbitMQ).

```
INGEST PLANE — your machine (one-shot harvest + long-running workers)

  ┌──────────────┐  publish URL    ┌─────────────────────┐  publish path
  │ linkedin.py  │ ──────────────▶ │  urls_queue         │ ──┐
  │ (Scrapy)     │                 │  (RabbitMQ, durable)│   │
  └──────────────┘                 └─────────────────────┘   │
                                                              ▼
                                              ┌─────────────────────────────┐
                                              │ content_worker.py           │
                                              │   requests.get + lxml parse │
                                              │   write JSON to disk        │
                                              └─────────────────────────────┘
                                                              │ publish file path
                                                              ▼
                                              ┌─────────────────────────────┐
                                              │  job_queue (RabbitMQ)       │
                                              └─────────────────────────────┘
                                                              │
                                                              ▼
                                              ┌─────────────────────────────┐
                                              │ processor.py                │
                                              │   Gemma 4 via Ollama        │
                                              │     → extract skills        │
                                              │   bge-small ONNX            │
                                              │     → embed title           │
                                              │   facet parser              │
                                              │     → seniority + year      │
                                              │   2-key INSERT:             │
                                              │     posting_id + content_hash│
                                              └─────────────────────────────┘
                                                              │
                                                              ▼
                                              ┌─────────────────────────────┐
                                              │  Supabase: job_postings     │
                                              │  (Postgres + pgvector +     │
                                              │   pg_trgm)                  │
                                              └─────────────────────────────┘
                                                              ▲
                          ┌───────────────────────────────────┘
                          │
SERVING PLANE — Cloud Run │
                          │
  ┌──────────────────┐    │  ANN + trigram hybrid + facet filter
  │ React SPA        │    │
  │  (Vite + TS)     │ ──▶│  GET /skills?job_title=...
  └──────────────────┘    │     │
                          │     ▼
  ┌──────────────────┐    │  ┌────────────────────────────────┐
  │ Go HTTP server   │ ──▶│  │ Embed query (hugot + ONNX)     │
  │ (same Cloud Run  │       │ Parse facets                   │
  │  binary serves   │       │ Run hybrid CTE on Supabase     │
  │  the SPA too)    │       │ Return JSON {Skills,           │
  └──────────────────┘       │   RelatedTitles, counts}        │
                              └────────────────────────────────┘
```

A few key shape decisions:

- The embedding model (`bge-small-en-v1.5`, 384-d, ONNX) is **used on both
  planes**. The Python ingest worker embeds posting titles at write time;
  the Go backend embeds the user's query at read time. Both must produce
  identical vectors — verified by a parity test (see
  `setup.md` §10).
- **Aggregation is query-time, not batch.** Each search runs a live SQL
  query against `job_postings`. There is no precomputed "top skills for
  X" table. This is the central architectural change from the original
  Spark-batch design.
- **RabbitMQ decouples scraping from extraction.** The link harvester
  is one-shot (cron-friendly); the content worker and processor are
  long-running daemons that drain whatever shows up on their queues.

---

## Tech stack and why each piece

| Layer | Choice | Why this and not the alternative |
|---|---|---|
| **Embedding model** | `BAAI/bge-small-en-v1.5` (384-d, ONNX) | bge-small is one of the strongest small open-weight encoders for short-text retrieval (MTEB top of class for its size class). 384 dims fits comfortably under Supabase's 500 MB free-tier cap (~2× the postings you'd fit with 768-d). ONNX gives us a single artifact usable from both Python (`onnxruntime`) and Go (`hugot`). |
| **Embedding runtime (Go)** | [`knights-analytics/hugot`](https://github.com/knights-analytics/hugot) | Pure-Go inference wrapping ONNX Runtime + the same HuggingFace tokenizer. No need for a separate Python sidecar in the serving path. |
| **LLM for skill extraction** | Gemma 4 via Ollama | Local-only inference keeps cost at zero and removes a third-party dependency from the ingest path. Gemma 4 is more than capable of "extract the technical skills from this job description as JSON." The previous DeepSeek/OpenAI cloud path is preserved as a fallback in `extractor.py` but not used by default. |
| **Vector store** | Supabase Postgres + `pgvector` (HNSW) | Managed Postgres with the vector extension — no separate vector DB to operate. HNSW gives sub-millisecond ANN. Free tier (500 MB, 60 conns) is enough for ~200k postings of bge-small embeddings. |
| **Hybrid lexical scoring** | `pg_trgm` similarity blended with cosine | Cosine alone is brittle on typos; `pg_trgm` catches them at the character-trigram level. Combined score is `0.4·vec + 0.6·trgm` with a 0.80 floor (tuned empirically). |
| **Backend language** | Go 1.24 | Fast cold starts on Cloud Run, native cgo for ONNX Runtime, simple deployment as a single binary. |
| **Frontend** | React 18 + TypeScript + Vite | React for UI ergonomics, TS for type safety against the Go backend's JSON shape, Vite for fast HMR in dev and tiny static output in prod (~110 KB gzipped). Not Next.js because we don't need SSR — the page is one search box and one chart. |
| **Chart library** | `react-chartjs-2` (wraps Chart.js) | Keeps visual parity with the original vanilla-JS implementation; well-maintained React wrapper. |
| **Styling** | Tailwind via PostCSS | Already used utility-first in the original templates; PostCSS pipeline replaces the CDN script for proper build-time pruning. |
| **Routing** | React Router v6 | Two routes (`/`, `/chart?job_title=...`); no need for a heavier framework. |
| **Message broker** | RabbitMQ in Docker | Already familiar pattern, durable queues survive worker restarts, free, runs locally in one container. |
| **Scraping** | Scrapy (link harvester) + plain `requests`+`lxml` (content worker) | Scrapy's value is on the link-harvest side (autothrottle, pagination, search-page concurrency). On the content side once URLs come from a queue, Scrapy's `start_requests` model fights the broker — a 50-line `pika` consumer with `requests`+`lxml` is simpler and equally correct. |
| **Raw posting archive** | Local disk (`$JOB_POSTINGS_DIR`) | Replaces an earlier HDFS dependency. JSON files on disk are inspectable, replay-able, and zero-infrastructure. Can be swapped for GCS later by replacing one client class. |
| **Process orchestration** | Bash (`run.sh`) + cron-friendly `harvest.sh` | A shell launcher with proper pre-flight checks, log files, and a `Ctrl-C` trap is enough for dev. systemd / supervisor in production. |
| **Cloud Run deploy** | Single multi-stage Docker image | Frontend `dist/`, Go binary, ONNX Runtime, libtokenizers, and the model file all bake into one image. Same-origin in prod = no CORS, no separate frontend deploy. |

---

## How each part is implemented

### Ingest plane (local/long-running)

**Link harvester** — `data_pipeline/scraper/linkedin.py`

A Scrapy spider that walks LinkedIn job search result pages
parameterized by experience level + keyword. Each posting URL it
discovers is published to RabbitMQ `urls_queue` (durable, persistent
delivery). The script is one-shot: it runs, exhausts its start URLs,
exits. Cron-friendly via `harvest.sh`.

Why Scrapy here: search-page parsing benefits from middlewares (cookie
handling, autothrottle, retry), and the spider naturally scales across
multiple search-result URLs concurrently.

**Content worker** — `data_pipeline/scraper/content_worker.py`

A long-running `pika` consumer on `urls_queue`. For each URL:

1. `requests.get(url)` with a realistic browser User-Agent.
2. Parse `job_title`, `company`, and `job_description` from the
   posting page using the same XPath selectors the original Scrapy
   spider used.
3. Write a JSON file to `$JOB_POSTINGS_DIR` via `LocalStorageClient`
   (filename: `<slug>_<company>_<date>_<8 hex>.json`). The
   storage client always returns an absolute path — important so the
   path published downstream isn't ambiguous about working directory.
4. Publish the absolute file path to `job_queue` (durable, persistent).
5. `time.sleep(random.uniform(4, 8))` between requests to stay within
   LinkedIn's tolerance.

Failure semantics:

- HTTP 404 / parse failure → `basic_nack(requeue=False)` (drop, log).
- Network errors → `basic_nack(requeue=True)` (RabbitMQ will retry).

**Extraction worker** — `data_pipeline/llm_processor/processor.py`

Long-running consumer on `job_queue`. For each file path:

1. Read the JSON payload.
2. **Skill extraction**: `Extractor.extract_skills_from_job` calls
   Gemma 4 via Ollama at `localhost:11434`. The system prompt
   (`constants/system_prompt.txt`) asks for a strict JSON list of
   technical skills.
3. **Normalization**: `RequirementsParser.clean_extracted_data` runs
   each extracted skill through `canonical_skill_map.py` (e.g.
   `"react.js" → "React"`, `"k8s" → "Kubernetes"`) and
   `tech_capitalization.py` (e.g. `"python" → "Python"`).
4. **Title embedding**: `TitleEmbedder.embed(job_title)` produces a
   384-d L2-normalized float vector via ONNX Runtime.
5. **Facet parsing**: rule-based extraction of `seniority`
   (new_grad / intern / entry / senior / unknown) and `posting_year`
   from the title. The same rules are mirrored in Go for query-time
   filtering.
6. **Two-key dedup**:
   - `posting_id = uuid5(NAMESPACE_URL, linkedin_posting_key(job_url))`
     — derived from the numeric LinkedIn job ID extracted from the
     URL path, so the same posting fetched with rotating tracking
     query params dedups correctly.
   - `content_hash = uuid5(NAMESPACE_URL, "company|title|description")`
     with normalized inputs — catches the same role re-posted under
     a *new* LinkedIn ID (which happens routinely).
7. INSERT into Supabase with `ON CONFLICT DO NOTHING` (bare form, no
   target). Postgres swallows the row if either uniqueness constraint
   matches.

The connection is opened with `autocommit=True` and
`prepare_threshold=None`. Both are non-default: the first protects
against poisoned-transaction cascades when a single insert fails; the
second works around Supabase's transaction-mode Supavisor pooler,
which rotates backend connections and breaks psycopg3's auto-prepared
statements.

### Storage

**Local disk archive** — `storage/local/local_storage.py`

`LocalStorageClient` provides `write` / `read_json` / `list` / `delete`
over a single base directory (default `/job_postings`). Used by both
the content worker (writes) and the extraction worker (reads). Always
resolves to absolute paths so the same file is unambiguous regardless
of where the consumer is running from.

**Supabase Postgres** — `schema.sql`

```sql
CREATE EXTENSION vector;
CREATE EXTENSION pg_trgm;

CREATE TABLE job_postings (
    posting_id      UUID PRIMARY KEY,
    job_title       TEXT NOT NULL,
    company         TEXT,
    skills          TEXT[] NOT NULL,
    seniority       TEXT,
    posting_year    INT,
    posted_date     DATE,
    title_embedding vector(384),
    content_hash    UUID                   -- new: content-level dedup
);

CREATE INDEX idx_jp_embedding   USING hnsw (title_embedding vector_cosine_ops);
CREATE INDEX idx_jp_title_fts   USING gin  (to_tsvector('english', job_title));
CREATE INDEX idx_jp_title_trgm  USING gin  (job_title gin_trgm_ops);
CREATE INDEX idx_jp_seniority   ON job_postings (seniority);
CREATE INDEX idx_jp_year        ON job_postings (posting_year);
CREATE UNIQUE INDEX idx_jp_content_hash
    ON job_postings (content_hash) WHERE content_hash IS NOT NULL;
```

The HNSW index serves the ANN preselect stage. The GIN trigram index
serves the lexical scoring stage. The partial unique index on
`content_hash` enforces content dedup without breaking older NULL rows.

### Serving plane (Cloud Run)

**Go backend** — `backend/`

`main.go` boots in three steps:

1. `utils.InitDB()` opens a pooled Supabase connection (small pool,
   `MaxOpenConns=8`, suited for Cloud Run's per-instance fan-out).
2. `services.InitEmbedService()` loads the bge-small ONNX file via
   `hugot.NewORTSession` + a `FeatureExtractionPipeline`. The pipeline
   is created once and reused. Embeddings are cached in-process via
   an LRU keyed on the normalized query.
3. Routes are registered via `routers.New()`:
   - `GET /skills?job_title=...` → JSON
   - everything else → static file from `$FRONTEND_DIST` (with
     `index.html` fallback so the React Router client-side routes work).

**The query, end to end** — `backend/services/skills_service.go`

```sql
WITH ann AS (
    SELECT posting_id, job_title, skills,
           1 - (title_embedding <=> $1::vector) AS vec_sim
    FROM job_postings
    WHERE ($2::text IS NULL OR seniority = $2 OR seniority = 'unknown')
      AND ($3::int  IS NULL OR posting_year >= $3)
    ORDER BY title_embedding <=> $1::vector
    LIMIT 2000
),
scored AS (
    SELECT *,
           similarity(job_title, $4) AS trgm_sim,
           (0.4 * vec_sim + 0.6 * similarity(job_title, $4)) AS combined
    FROM ann
),
matched AS (
    SELECT * FROM scored WHERE combined > 0.80
    ORDER BY combined DESC LIMIT 2000
)
SELECT skill, COUNT(*) AS cnt, ROUND(100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM matched), 0), 2) AS pct
FROM matched, unnest(skills) AS skill
GROUP BY skill ORDER BY cnt DESC LIMIT 10;
```

Two stages:

1. **ANN preselect** via HNSW on cosine similarity → top 2000
   candidates. The HNSW index makes this a few-millisecond operation
   regardless of table size.
2. **Re-rank with hybrid scoring** → blend of `vec_sim` (semantic) and
   `pg_trgm.similarity()` (lexical), threshold-filtered at 0.80. The
   threshold is the real relevance gate; `LIMIT 2000` is a safety
   valve, not a top-K knob. Every above-threshold posting feeds the
   skill histogram.

The same `matched` CTE is reused for three things:
- The top-10 skill histogram (above).
- The full list of all skills appearing in matched postings
  (`AllSkills` in the JSON; powers `SkillsCount`).
- The related-titles strip — top 8 most common `job_title` values in
  matched (drives the chips below the chart).

**Hybrid scoring weights** were tuned against the actual dataset:

| Query | Score for correct match | Score for wrong-but-close | Gap |
|---|---|---|---|
| `embedded software engineer` | 1.000 (Embedded SE) | 0.781 (plain SE) | 0.22 |
| `embeded software engineer` (typo) | 0.868 (Embedded SE) | 0.802 (plain SE) | 0.07 |
| `software engineer` | 1.000 (SE) | all SE variants ≥ 0.89 | — |

The 0.80 floor cleanly separates the relevant from the irrelevant in
all three cases. Trigram is weighted higher than the vector (0.6 vs
0.4) because trigram is what saves us on typos.

### Frontend

**`frontend/`** — Vite + React + TypeScript

Routes:
- `/` → big logo + hero search bar (`pages/Home.tsx`)
- `/chart?job_title=...` → compact search bar + bar chart +
  related-title chips + stat cards (`pages/ChartPage.tsx`)

Data flow on the chart page:
- Read `job_title` from URL search params.
- `useEffect` triggers `fetchSkills(jobTitle)` (a typed wrapper around
  `fetch('/skills?...')`).
- Render `<SkillsBarChart skills={data.Skills} />` (Chart.js wrapper
  preserving the original visual).
- Render `<RelatedTitles titles={data.RelatedTitles} />` — clickable
  chips that re-navigate to a fresh chart page.
- Render two `<StatCard>` blocks for Jobs Found / Skills Found.

In **dev**: Vite serves the SPA on `:5173` and proxies `/skills`
requests to the Go backend on `:8080` (configured in
`vite.config.ts`). Hot module reload works as usual.

In **prod**: the Go binary serves `frontend/dist/` directly. Any URL
that isn't `/skills` falls through to `index.html` so React Router can
handle client-side routes. No CORS, same origin.

---

## Design decisions worth knowing

These came up during construction and are non-obvious; capturing them
so future contributors don't re-litigate them.

**Why bge-small not bge-base/bge-large?**
At 384 dims, bge-small fits ~2× as many postings under Supabase's 500
MB free-tier cap as 768-d alternatives. The quality drop on
short-text title-similarity tasks is small (per MTEB short-text
benchmarks) and is more than compensated for by the trigram lexical
signal in the hybrid score.

**Why query-time aggregation instead of pre-computed top-skills tables?**
The original design batched skills with PySpark into a `job_skill_stats`
table. That was rebuilt nightly, locked the system to a fixed list of
job titles, and couldn't answer queries like "embedded software
engineer" because no such bucket existed. Query-time aggregation over a
per-posting table removes the bucket list entirely and lets any
free-text query work, at the cost of a few milliseconds per query —
which is the dominant tradeoff for this workload.

**Why a deterministic UUID for `posting_id` instead of `uuid4()`?**
LinkedIn's URLs carry rotating `?refId=...&trackingId=...` query
parameters. The same posting fetched on two different days produces
two different URLs but should be the same record. By deriving
`posting_id = uuid5(NAMESPACE_URL, linkedin:<numeric_id>)`, the
deterministic UUID + `ON CONFLICT (posting_id) DO NOTHING` makes
re-harvests idempotent.

**Why two dedup keys (posting_id + content_hash)?**
LinkedIn re-issues the same job under fresh numeric IDs when listings
expire and are re-listed. URL-based dedup misses this case.
Content-hash dedup catches it. Bare `ON CONFLICT DO NOTHING` (no
target) cooperates with both keys atomically.

**Why hybrid scoring instead of pure cosine?**
bge-small's subword tokenization mishandles common typos (e.g.
"embeded" → wrong embedding region, ranked closer to plain "Software
Engineer" than to "Embedded Software Engineer"). No similarity floor
can fix this. Trigram similarity over the title catches the
substring overlap that the embedding misses.

**Why plain Python `requests` for the content worker instead of more Scrapy?**
Scrapy's `start_requests` model assumes a known set of URLs at startup.
Feeding it from a long-lived RabbitMQ consumer requires either the
Pika-Twisted adapter or a separate thread calling
`crawler.engine.crawl()` — both fight the framework. A 50-line `pika`
consumer using `requests`+`lxml` does the same job with less ceremony.

**Why React + Vite, not Next.js?**
The app is essentially one form and one chart. SSR wins nothing here.
Vite's dev server is faster, the build output is smaller, and the
deploy story is "static files served by the existing Go binary" —
zero new infrastructure.

**Why `bash` for orchestration instead of `docker-compose` / `tmux` / supervisord?**
For local dev, a bash launcher with pre-flight checks, file logging,
and a `Ctrl-C` trap is enough. The full Docker image is built for
*production* deploy on Cloud Run; trying to also containerize the
local dev loop would slow iteration without adding correctness.

**Why does `run.sh` not purge queues by default?**
An earlier version did. It bit immediately when a code-change restart
silently wiped mid-flight messages. Default flipped to "preserve";
`--purge` is opt-in.

---

## Repo layout

```
TechTrendTracker/
├── README.md                         ← you are here
├── setup.md                          ← step-by-step bootstrap + Cloud Run deploy
├── Dockerfile                        ← multi-stage build (model + frontend + backend)
├── .dockerignore                     ← keeps build context small
├── docker-compose.yml                ← only RabbitMQ; Postgres is on Supabase now
├── schema.sql                        ← Supabase schema (pgvector, pg_trgm, indexes)
├── requirements.txt                  ← Python deps
├── .env.example                      ← env-var template (cp → .env)
│
├── run.sh                            ← dev launcher (4 services + live tail)
├── harvest.sh                        ← one-shot link harvest (cron-friendly)
│
├── frontend/                         ← Vite + React + TypeScript SPA
│   ├── package.json
│   ├── vite.config.ts                ← dev proxy /skills → :8080
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api.ts                    ← typed wrapper around fetch('/skills')
│       ├── types.ts                  ← SkillsResponse shape
│       ├── pages/
│       │   ├── Home.tsx
│       │   └── ChartPage.tsx
│       └── components/
│           ├── SearchBar.tsx
│           ├── SkillsBarChart.tsx
│           ├── RelatedTitles.tsx
│           └── StatCard.tsx
│
├── backend/                          ← Go HTTP server + ONNX query embedder
│   ├── go.mod
│   ├── main.go                       ← InitDB → InitEmbedService → mux → ListenAndServe
│   ├── routers/router.go             ← /skills + SPA file server with index.html fallback
│   ├── handlers/skills.go            ← JSON encoding only
│   ├── services/
│   │   ├── skills_service.go         ← the hybrid CTE; the heart of the feature
│   │   ├── embed_service.go          ← hugot pipeline + LRU cache
│   │   └── facet_service.go          ← seniority/year regexes (mirror of Python)
│   └── utils/
│       ├── db.go                     ← Supabase pooled connection
│       └── response.go               ← JSON helpers
│
├── data_pipeline/                    ← Python: scraping, LLM extraction, embedding
│   ├── scraper/
│   │   ├── linkedin.py               ← Scrapy spider → urls_queue
│   │   ├── content_worker.py         ← pika consumer; urls_queue → JSON file + job_queue
│   │   └── url_utils.py              ← linkedin_posting_key + content_hash_for
│   ├── llm_processor/
│   │   ├── processor.py              ← job_queue → Gemma + embed + facets → Supabase
│   │   ├── extractor.py              ← Ollama + cloud LLM fallback
│   │   ├── requirements_parser.py    ← skill normalization via canonical maps
│   │   └── facet_parser.py           ← rule-based seniority + year
│   ├── embeddings/
│   │   └── embedder.py               ← bge-small ONNX inference (ONNX Runtime)
│   └── storage/
│       └── supabase_client.py        ← psycopg insert with two-key ON CONFLICT
│
├── storage/local/
│   └── local_storage.py              ← LocalStorageClient (replaces HDFS)
│
├── scripts/
│   └── backfill_content_hash.py      ← one-off: populate content_hash on legacy rows
│
├── constants/
│   ├── canonical_skill_map.py        ← "react.js" → "React", etc.
│   ├── tech_capitalization.py        ← "python" → "Python", etc.
│   └── system_prompt.txt             ← Gemma extraction prompt
│
└── tests/llm_processor/              ← unit tests for the LLM-side helpers
```

---

## Running locally

See `setup.md` for the full bootstrap (Supabase, ONNX export, Ollama,
cgo deps, env vars). Once everything is installed, the two scripts
you'll use day to day:

```bash
./run.sh             # bring up RabbitMQ + processor + content_worker + Go backend + Vite dev server
                     # (queues are preserved by default; pass --purge for a clean slate)
                     # then open http://localhost:5173

./harvest.sh         # one-shot LinkedIn link harvest; publishes to urls_queue
                     # cron-friendly for daily ingest
```

`./run.sh` streams the extractor's log live so you can watch Gemma
producing skill extractions in real time; switch which service you
follow with `--follow content_worker`, `--follow backend`, etc.

---

## Deploying to Cloud Run

The full walkthrough is in `setup.md` §12. The short version:

```bash
REGION=us-central1
PROJECT=$(gcloud config get-value project)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/ttt/backend:$(git rev-parse --short HEAD)"

# 1. one-time: stash the Supabase pooled DSN in Secret Manager
printf '%s' '<your DSN>' | gcloud secrets create supabase-db-url --data-file=-

# 2. build the image (multi-stage Dockerfile at repo root)
gcloud builds submit --tag "$IMAGE"

# 3. deploy
gcloud run deploy ttt-backend \
  --image "$IMAGE" --region "$REGION" \
  --allow-unauthenticated --cpu=1 --memory=2Gi \
  --set-secrets=SUPABASE_DB_URL=supabase-db-url:latest
```

The single image bakes the frontend bundle, the Go binary, ONNX
Runtime, and the model file together. First build is ~5–8 minutes
(model export + cgo deps dominate); subsequent builds are ~1–2 min
thanks to layer caching.

---

## Out of scope (deliberately)

These were considered and explicitly left out, with notes in case you
want to pick them up later.

- **Fuzzy content dedup.** Current dedup is exact match on
  `(company, title, description)`. Catches identical re-posts; misses
  reworded ones. Would require embedding the description and adding a
  per-insert vector-NN check.
- **LLM-driven query expansion.** Searching "software engineer" doesn't
  pull in "web developer" or "backend engineer" today because they
  don't share tokens. Gemma could generate related titles per query;
  see the cost/latency analysis we wrote up before deferring it
  (rough order: 3–10s per uncached query on local CPU; pre-warmed
  cache + smaller model could make it viable).
- **Proxy rotation for the scraper.** Single residential IP →
  LinkedIn rate-limits after a few hundred requests/day. Real fix is
  a residential proxy pool; deferred until the dataset growth rate
  demands it.
- **Cluster-based hierarchical taxonomy.** Pre-clustering postings
  into role buckets via k-means / HDBSCAN could enable
  umbrella-vs-specific query behavior automatically. Larger change,
  defer until the static umbrella map becomes painful to maintain.
- **Cron'd `harvest.sh` from inside Cloud Run.** Currently the
  harvester is meant to run on your local machine (residential IP).
  Moving it to Cloud Scheduler + a Cloud Run Job would let the whole
  thing run unattended, at the cost of needing proxy egress.
