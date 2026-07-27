# Tech Trend Tracker — Design Document

Tech Trend Tracker (TTT) is a skill-tracking platform that mines real job
postings from job boards (currently LinkedIn) to surface the **most in-demand
technical skills** for a given role. It is aimed at job seekers — especially
students and entry-level applicants — who want a data-driven view of what the
market is actually asking for.

A user types a job title (e.g. *Data Scientist*, or *new grad backend engineer*)
into a search bar, and TTT responds with a ranked bar chart of the top skills for
that role, headline counts (postings analyzed, distinct skills found), the
related job titles that cluster around the query, and 3–4 portfolio project
ideas built from skills that genuinely co-occur in those postings.

> **Document status.** This describes the system as it exists in the repository
> today. Work that is designed and stubbed but *not yet implemented* is
> confined to [§8 In-flight work](#8--in-flight-work-hierarchical-search) and is
> explicitly labelled. Nothing outside §8 is aspirational.

---

## 1 — Architecture at a glance

The system is split into two **planes** that meet only at the database. The
**ingest plane** runs locally on a schedule and does all the expensive,
model-driven work. The **serving plane** is a single stateless Go binary
deployed to Google Cloud Run.

```
 INGEST PLANE (local, cron-driven)                SERVING PLANE (Cloud Run)
 ─────────────────────────────────                ─────────────────────────────
  linkedin.py  (Scrapy link spider)                 React SPA (Vite build)
     │ posting URLs                                       │  same-origin HTTPS
     ▼                                                    ▼
  RabbitMQ  urls_queue                              Go backend (net/http)
     │                                                ├─ embed query
     ▼                                                │    bge-small ONNX
  content_worker.py (requests + lxml)                 │    via hugot (cgo)
     │  raw posting JSON ─▶ local disk                ├─ hybrid retrieval
     │                      $JOB_POSTINGS_DIR         │    pgvector HNSW
     ▼                                                │    + pg_trgm GIN
  RabbitMQ  job_queue  (file path)                    ├─ unnest + GROUP BY
     │                                                │    → top skills,
     ▼                                                │      related titles
  processor.py  (extraction worker)                   └─ catalog lookup
     ├─ Gemma (Ollama)      → skills                       skills <@ $top
     ├─ RequirementsParser  → canonical names              + greedy set-cover
     ├─ facet_parser        → seniority, year                    │
     ├─ TitleEmbedder       → 384-d vector                       │
     └─ 1 row ──────────────┐                                    │
                            ▼                                    │
                    ┌───────────────────────┐                    │
                    │  Supabase Postgres    │◀───────────────────┘
                    │   job_postings        │      read-only at request time
                    │   project_recs        │
                    │   pgvector + pg_trgm  │
                    └───────────▲───────────┘
                                │ offline batch
                  build_catalog.py (triple mining + Gemma)

 STORES
   $JOB_POSTINGS_DIR   local disk — raw scrape archive (JSON per posting)
   RabbitMQ            local queues — decouple harvest / scrape / extract
   Supabase Postgres   the ONLY thing the two planes share
```

### The central design idea

**All LLM work happens offline; the request path is fast SQL plus one small
embedding.** The Cloud Run image contains no LLM and never calls a cloud model.
The only model that runs per request is the 384-dimension `bge-small-en-v1.5`
encoder, embedded in-process. Everything expensive — skill extraction, project
generation — is precomputed and cached as rows.

### The second design idea: aggregate at query time, not ingest time

The legacy system precomputed per-role aggregate tables in a batch job. The
current system stores **one row per posting** and aggregates on demand over
whatever subset a query matches. That is what makes free-text queries
("senior embedded engineer 2026") possible at all — the matched set is
different for every query, so it cannot be precomputed.

### What was removed (and why)

| Removed | Replaced by | Reason |
|---|---|---|
| HDFS / Hadoop | Local disk (`storage/local/local_storage.py`) | Single-machine ingest; a distributed FS bought nothing |
| PySpark aggregation job | Query-time `unnest` + `GROUP BY` in Postgres | Aggregates must follow the query, not a fixed role list |
| `job_skill_stats`, `job_count` tables | `job_postings` (one row per posting) | Same reason as above; `schema.sql` drops them on cutover |
| Local Docker Postgres | Supabase Postgres (managed) | pgvector/pg_trgm without ops; Cloud Run can reach it |
| Server-rendered Go templates + HTMX | React + TypeScript + Vite SPA | Client state (two chained API calls) outgrew fragment swaps |
| DeepSeek as the primary extractor | Local Gemma via Ollama | No per-posting API cost; ingest is throughput-bound, not latency-bound |

---

## 2 — Repository layout

```
TechTrendTracker/
├── data_pipeline/
│   ├── scraper/
│   │   ├── linkedin.py            # Scrapy link spider → urls_queue
│   │   ├── content_worker.py      # urls_queue → page fetch → disk → job_queue
│   │   └── url_utils.py           # posting_id + content_hash dedup keys
│   ├── llm_processor/
│   │   ├── processor.py           # extraction worker (job_queue consumer)
│   │   ├── extractor.py           # Gemma/Ollama skill extraction (+DeepSeek fallback)
│   │   ├── requirements_parser.py # skill normalization / canonicalization
│   │   ├── facet_parser.py        # regex seniority + year  ← mirrored in Go
│   │   └── title_normalizer.py    # §8 hierarchical search (partly stubbed)
│   ├── embeddings/embedder.py     # bge-small ONNX title embedder (Python side)
│   ├── recommendations/
│   │   ├── triple_miner.py        # frequent skill triples (support + lift)
│   │   ├── generator.py           # triple → portfolio project via Gemma
│   │   └── build_catalog.py       # offline catalog build entrypoint
│   ├── taxonomy/reconcile.py      # §8 taxonomy hygiene job (stubbed)
│   └── storage/supabase_client.py # psycopg insert path
├── storage/local/local_storage.py # local-disk raw archive (replaced HDFSClient)
├── constants/
│   ├── canonical_skill_map.py     # alias → canonical skill name
│   ├── tech_capitalization.py     # lowercase → correctly cased name
│   ├── system_prompt.txt          # skill-extraction prompt
│   ├── title_norm_prompt.txt      # §8 title-normalization prompt
│   └── title_norm_fixtures.json   # §8 cross-plane parity fixtures
├── backend/                       # Go API + serves the built SPA
│   ├── main.go                    # DB init, embed init, listen on $PORT
│   ├── routers/router.go          # /skills, /recommendations, SPA fallback
│   ├── handlers/                  # thin HTTP adapters
│   ├── services/                  # retrieval, embedding, facets, recs
│   └── utils/                     # pgx pool, JSON/HTML helpers
├── frontend/                      # React + TypeScript + Vite SPA
├── scripts/                       # one-off backfills + golden-query runner
├── tests/                         # pytest units + golden_queries.json
├── schema.sql                     # Supabase schema (pgvector, indexes, catalog)
├── docker-compose.yml             # RabbitMQ only
├── Dockerfile                     # 4-stage build for Cloud Run
├── deploy.sh / run.sh / harvest.sh
├── README.md                      # product-facing overview
└── setup.md                       # step-by-step setup & deployment guide
```

---

## 3 — Ingest plane

Three processes, chained by two durable RabbitMQ queues. The split exists so
each stage can be rate-limited independently: link discovery is bursty, page
fetching is politeness-bound, and LLM extraction is CPU-bound.

### Technologies
- **Scrapy 2.11+** — link discovery only.
- **requests + lxml** — page fetch and parse in the content worker (Scrapy's
  scheduler bought nothing once the URL source became a queue).
- **RabbitMQ** (`pika`) — `urls_queue` and `job_queue`, both durable, both
  published with `delivery_mode=2`.
- **Ollama + Gemma** (`LLM_MODEL`, default `gemma4:latest`) — skill extraction.
- **ONNX Runtime + `tokenizers`** — `bge-small-en-v1.5`, 384-d.
- **psycopg 3** — the single write path into Supabase.

### 3.1 Link harvest — `data_pipeline/scraper/linkedin.py`

`LinkedInJobSpider` builds a cross-product of LinkedIn search URLs over
experience levels `f_E ∈ {1,2,3,4}` × keywords, with a fixed 7-day window
(`f_TPR=r604800`) and geo ID `102095887`. Keywords come from the
`JOB_KEYWORDS` env var (comma-separated), so the role set is **configuration,
not code** — `harvest.sh "Machine Learning Engineer"` is enough to retarget it.

Each result page yields links via
`ul.jobs-search__results-list a.base-card__full-link::attr(href)`; each link is
published to `urls_queue`. Politeness: 4s randomized download delay plus
AutoThrottle capped at target concurrency 1.0.

The spider is **one-shot** — it exits when the crawl finishes, which is what
makes it cron-safe.

### 3.2 Content worker — `data_pipeline/scraper/content_worker.py`

Consumes `urls_queue` with `prefetch_count=1`, fetches each posting with a
browser User-Agent, and XPath-extracts title, company, and description. Then:

1. Writes `{job_title, company, job_description, job_url, posted_date}` to
   `$JOB_POSTINGS_DIR/<slug>_<slug>_<date>_<rand>.json`.
2. Publishes that **file path** to `job_queue`.

**Failure taxonomy is the interesting part here.** The worker distinguishes:
- `PermanentError` (404/410, or a page with no title/description — an expired
  listing) → `basic_nack(requeue=False)`, the message is dropped;
- everything else (network blips) → `basic_nack(requeue=True)`, retried.

Requeueing a 404 forever is the failure mode this split prevents. A randomized
4–8s sleep runs in the `finally` block, so the delay applies to failures too and
a burst of errors can't turn into a burst of requests.

### 3.3 Extraction worker — `data_pipeline/llm_processor/processor.py`

Consumes `job_queue`, and for each posting produces exactly one database row:

| Step | Component | Output |
|---|---|---|
| Skill extraction | `Extractor` → `ollama.chat(format="json", temperature=0)` | raw skill list |
| Normalization | `RequirementsParser` | canonical, de-duplicated, sorted skills |
| Facets | `facet_parser.parse` | `seniority`, `posting_year` |
| Title embedding | `TitleEmbedder` | 384-d L2-normalized vector |
| Dedup keys | `url_utils` | `posting_id`, `content_hash` |
| Write | `SupabaseClient.insert_posting` | one row, `ON CONFLICT DO NOTHING` |

**Skill normalization** (`requirements_parser.py`) is what stops one technology
appearing under five spellings. `normalize_skill` lowercases and trims, unwraps
parentheses, splits on `/` into multiple skills, applies the canonical map
(`react.js`/`reactjs` → `React`), applies the capitalization map (`JavaScript`,
`C#`), then strips punctuation while **keeping `+` and `#`** so `C++` and `C#`
survive. Because the `/`-split returns a list, `clean_extracted_data` flattens
recursively and returns a sorted set.

**Two independent dedup keys**, both enforced by a bare `ON CONFLICT DO NOTHING`:
- `posting_id = uuid5(NAMESPACE_URL, "linkedin:<job id>")` — LinkedIn rotates
  tracking query params on every search render, so the raw URL is not stable;
  the numeric job ID is. This catches *the same posting seen twice*.
- `content_hash = uuid5(NAMESPACE_URL, normalize(company)|title|description)` —
  catches *the same role re-posted under a new LinkedIn ID*.

A bare `ON CONFLICT DO NOTHING` (no conflict target) lets the PK and the partial
unique index on `content_hash` both participate in one statement. `insert_posting`
returns `(pid, inserted)` from `cur.rowcount`, so the log distinguishes inserts
from suppressed duplicates. Ingest is therefore **idempotent** — re-running a
harvest is free.

**Connection settings that are not incidental:** `autocommit=True` so one failed
insert doesn't poison the connection for every subsequent message, and
`prepare_threshold=None` to disable psycopg's auto-prepared statements, which
collide with Supabase's Supavisor transaction-mode pooler. The Go side does the
same thing (§5.1).

### 3.4 Cross-plane parity

Two things must produce identical results in Python and Go, or query-time
matching silently degrades:

| Concern | Python | Go | Guard |
|---|---|---|---|
| Facet rules | `llm_processor/facet_parser.py` | `services/facet_service.go` | Regexes kept in lockstep by hand |
| Title embedding | `embeddings/embedder.py` (onnxruntime) | `services/embed_service.go` (hugot) | Same ONNX artifact in both planes; parity test in `setup.md` §10 |

The embedding parity requirement is why the Dockerfile fetches the **same
pre-converted ONNX files** local dev uses (`Xenova/bge-small-en-v1.5`) rather
than re-exporting: a different export can produce different vectors, and a
query vector that doesn't live in the same space as the stored vectors returns
plausible-looking garbage.

---

## 4 — Data model (`schema.sql`)

The schema is the **contract between the planes**: the ingest worker writes it,
the Go server only reads it.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE job_postings (
    posting_id      UUID PRIMARY KEY,
    job_title       TEXT NOT NULL,
    company         TEXT,
    skills          TEXT[] NOT NULL,
    seniority       TEXT,
    posting_year    INT,
    posted_date     DATE,
    title_embedding vector(384),
    content_hash    UUID                    -- partial UNIQUE where not null
);

CREATE TABLE project_recommendations (
    project_id    UUID PRIMARY KEY,
    title         TEXT NOT NULL,
    level         TEXT NOT NULL,            -- BEGINNER|INTERMEDIATE|ADVANCED
    blurb         TEXT NOT NULL,
    skills        TEXT[] NOT NULL,          -- the 3 skills this project builds
    support_count INT NOT NULL,             -- postings the triple co-occurs in
    lift          REAL,                     -- association strength vs chance
    score         REAL NOT NULL,            -- request-time ranking signal
    skills_key    TEXT NOT NULL UNIQUE,     -- sorted "a|b|c" dedup key
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Indexes, and what each one is for

| Index | Type | Serves |
|---|---|---|
| `idx_jp_embedding` | HNSW `vector_cosine_ops` | ANN preselect in the semantic pool |
| `idx_jp_title_trgm` | GIN `gin_trgm_ops` | The `job_title % $4` gate in the lexical pool |
| `idx_jp_title_fts` | GIN `to_tsvector` | Reserved; not on the current query path |
| `idx_jp_content_hash` | partial UNIQUE | Content dedup (only where `content_hash IS NOT NULL`) |
| `idx_jp_seniority`, `idx_jp_year` | btree | Facet filters inside both retrieval pools |
| `idx_pr_skills` | GIN `TEXT[]` | The `skills <@ $top` subset match for recommendations |

The trigram index is the non-obvious one. It exists because embeddings and
typos fail differently: `bge-small` tokenizes `embeded` into different subwords
than `embedded`, so semantic search alone cannot recover it. Trigram similarity
can. Hence §5.2.

The schema also defines the hierarchical-search tables (`title_map`,
`role_families`, `spec_vocabulary`, the derived columns on `job_postings`, and
the `taxonomy_tree` view). Those are **applied but not yet populated or read** —
see §8.

---

## 5 — Serving plane (Go)

A stateless `net/http` server that reads Supabase, runs one small model
in-process, and also serves the built SPA. Module path
`github.com/Tin-Ko/TechTrendTracker`, Go 1.24.2.

### Technologies
- **`net/http`** — no web framework.
- **`jackc/pgx/v5` (stdlib adapter)** — Postgres driver.
- **`lib/pq`** — retained solely for `pq.Array` when binding/scanning `TEXT[]`.
- **`knights-analytics/hugot` v0.3.0** — in-process ONNX inference. This is
  **cgo**: it links ONNX Runtime (shared) and `daulet/tokenizers` (static),
  which is why the Dockerfile installs both before `go build`.

### Routes

| Route | Handler | Returns |
|---|---|---|
| `GET /skills?job_title=<role>` | `HandleGetTopSkills` | JSON: top-10 skills, counts, all skills, related titles |
| `GET /recommendations?skills=A,B,C` | `HandleGetRecommendations` | JSON: 3–4 portfolio projects |
| `GET /*` | `spaHandler` | A real file under `$FRONTEND_DIST`, else `index.html` |

The SPA fallback serves `index.html` for any non-API path so React Router owns
client-side routing, with a `filepath.Abs` containment check so a `../` path
cannot escape the dist root. Serving the API and the SPA from the **same
origin** is deliberate: no separate frontend deploy, and no CORS to configure.

### 5.1 Database connection — `utils/db.go`

Opened from `SUPABASE_DB_URL`, expected to be the **Supavisor pooled DSN**
(port 6543, transaction mode) in production, because Cloud Run fans out across
instances and the Supabase free tier caps direct connections around 60.

The driver is pgx in `QueryExecModeSimpleProtocol`. Transaction-mode pooling
multiplexes clients onto fewer backends and may switch backend between
statements, so server-side prepared statements collide across connections —
surfacing as intermittent `unnamed prepared statement does not exist` errors.
Simple protocol inlines parameters client-side and prepares nothing. This is the
exact Go counterpart of the Python side's `prepare_threshold=None`.

Pool is capped at 8 open / 4 idle **per instance**, since the instance count is
what actually scales.

### 5.2 Hybrid retrieval — `services/skills_service.go`

This is the core of the read path. A query is embedded once, then two retrievers
run independently and are merged.

```
              query string
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
  embed (hugot)         normalizeQuery
   384-d vector          lowercase+trim
        │                     │
        ▼                     ▼
  semantic_search        lexical_search
  ORDER BY <=>           WHERE job_title % $4
  LIMIT 500              ORDER BY similarity DESC
  (HNSW)                 LIMIT 500  (GIN trgm)
        └──────────┬──────────┘
                   ▼
          FULL OUTER JOIN on posting_id
          missing signal COALESCEs to 0
                   ▼
       combined = 0.4·vec_sim + 0.6·trgm_sim
                   ▼
          WHERE combined > 0.80, LIMIT 2000
                   ▼
                matched          ← the CTE seam
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
  top-10 skills  all skills   related titles
  unnest+GROUP   unnest+GROUP  GROUP BY title
```

Tunables live in one `const` block: pool sizes 500/500, `matchLimit` 2000,
weights 0.4 vector / 0.6 trigram, floor 0.80.

**Why trigram outweighs vector.** Lexical misses are the worse failure mode.
A semantic near-miss still returns a *related* role; a typo that the embedding
can't recover returns an unrelated set or nothing. Weighting trigram higher
biases toward the failure that users notice less.

**What the 0.80 floor means under `FULL OUTER JOIN`.** A posting present in only
one pool scores 0 on the missing signal. Since `0.6 × 1.0 = 0.6 < 0.80`, a
single-pool posting can never clear the floor on its own. The floor therefore
encodes *"both signals must agree"* — that's intentional, not an artifact.

**Facets** parsed from the query (`ParseFacets`) filter *inside both pools*, not
after the merge — filtering before the `LIMIT 500` is what keeps the pools full
of relevant candidates. Note the `OR seniority = 'unknown'` disjunction: a
posting whose title didn't state a level shouldn't be excluded from a
seniority-qualified search.

**The `matched` CTE is a seam.** The three aggregation queries only ever say
`FROM matched`, so an entirely different definition of "the matched set" can be
swapped in without touching aggregation. §8 is built on exactly this seam.

**One implementation trap worth recording:** the CTE constants are substituted
with `strings.NewReplacer`, not `fmt.Sprintf`, because the SQL contains
pg_trgm's `%` operator, which `Sprintf` would parse as a format verb.

### 5.3 Embedding service — `services/embed_service.go`

`InitEmbedService` loads the ONNX model and tokenizer **once** at boot via
`sync.Once`, from `ONNX_MODEL_DIR`, with the ONNX Runtime shared library located
by `ONNX_LIBRARY_PATH` (hugot otherwise looks for `onnxruntime.so` without the
`lib` prefix and fails). Boot-time loading is what keeps per-request cost to a
single forward pass — and is also why Cloud Run cold starts are the latency
outlier (§7).

An in-process cache (30-minute TTL, 1024 entries, FIFO eviction) keys on the
normalized query, so repeated searches skip inference entirely. `VectorLiteral`
formats the vector as pgvector's `[v1,v2,...]` text form at 6 decimal places.

### 5.4 Recommendations — `services/recommend_service.go`

Pure catalog lookup, no model:

1. Take at most the top 5 skills from the request. Fewer than 3 → return empty,
   since a 3-skill triple cannot be a subset of a smaller set.
2. `WHERE skills <@ $1` — every candidate project's whole triple is contained in
   the searched top skills. GIN-indexed.
3. `selectByCoverage` — **greedy set cover**. Repeatedly pick the candidate
   covering the most still-uncovered top skills. Stop at 4 projects, or once
   every top skill is covered and at least 3 are picked, or once the best
   remaining candidate adds nothing new past the minimum.

The set-cover step is the design-bearing part. Sorting by `score` alone returns
projects that all cluster on the same two or three popular skills. Greedy
coverage maximizes the *span* across the user's top skills while each project
stays focused on three — the classic greedy approximation, which is more than
adequate at n ≤ a few hundred candidates. Because candidates arrive
`ORDER BY score DESC`, ties in coverage gain resolve to the higher-scoring
project for free.

---

## 6 — Frontend

A React + TypeScript SPA built by Vite. In dev it runs on :5173 and proxies
`/skills` and `/recommendations` to the Go backend on :8080; in production the
Go binary serves the built bundle from `$FRONTEND_DIST`.

### Technologies
- **React 18** + **react-router-dom 6** (routes: `/` and `/chart`).
- **TypeScript 5**, **Vite 5**.
- **Tailwind 3** is wired into the PostCSS chain, but the actual styling is a
  hand-written CSS design system in `src/index.css` (~680 lines, ported from
  `design-3-keyword-onepage.html`) using semantic class names (`.kw`, `.matchbar`,
  `.rhead`). The Tailwind config's dark palette is a leftover from an earlier
  design and is not what the current components use.
- **No charting library.** `SkillsBarChart.tsx` renders the ranked list with CSS
  width percentages and a staggered animation delay. Bars are scaled relative to
  the top skill, not to 100%, so the leader always fills its row.

`src/types.ts` mirrors the Go response structs field-for-field (Go's default
JSON encoding uses exported field names, so the TS types are `PascalCase`). Slice
fields are typed `T[] | null` because a nil Go slice marshals to `null`, not `[]`.

### Request flow

1. Search submits → `/chart?job_title=<role>`.
2. `ChartPage` calls `GET /skills`, renders chart + counts + related titles.
3. A **second** effect, keyed on the joined top-5 skill names, calls
   `GET /recommendations`.

Splitting into two calls means the bar chart paints as soon as `/skills` returns
instead of waiting on the catalog lookup, and the recommendations request is
keyed on its only real input, so it doesn't re-fire on unrelated renders.

---

## 7 — Offline recommendations catalog

Run by `python -m data_pipeline.recommendations.build_catalog` (or
`./run.sh --generate-projects`), whenever the corpus has grown enough to shift
which skill combinations are popular.

### Stage 1 — mine triples (`triple_miner.py`)

One SQL statement finds unordered skill triples `{A,B,C}` and scores them:

- `WHERE a < b AND b < c` — counts each unordered triple once instead of 3! = 6
  times.
- `skills[1:max_skills]` (default 30) — the triple join is a self cross-join,
  **O(k³) in a posting's skill count**. One pathological posting listing 60
  skills would otherwise dominate the entire mining run. This cap is the
  difference between a query that finishes and one that doesn't.
- `array_agg(DISTINCT s)` — a skill repeated inside one posting can't
  double-count a triple.
- **support** = postings containing all three; **lift** =
  `P(A,B,C) / (P(A)·P(B)·P(C))`.

Support alone is not enough: Python, Git, and SQL co-occur constantly simply
because each is individually ubiquitous, and a project built from them teaches
nothing about their *combination*. Lift > 1 is the filter that keeps combos with
genuine affinity. Support then orders the survivors.

### Stage 2 — generate (`generator.py`)

For each surviving triple, local Gemma (`format="json"`, `temperature=0`)
invents one small, finishable project using all three, returning
`{title, level, blurb}`. Invalid `level` values fall back to `INTERMEDIATE`;
empty title/blurb raises so `build_catalog` can skip that triple and keep going.

### Stage 3 — upsert (`build_catalog.py`)

`project_id = uuid5(fixed namespace, "a|b|c")` over the lowercased sorted triple,
so the same triple always maps to the same row and re-runs **update in place**
rather than accumulating near-duplicates. `score = support_count`, since lift
already gated admission at build time.

This job uses `SUPABASE_DB_DIRECT_URL` (the direct 5432 DSN), not the pooled one
— it's a long batch job, not a serverless caller.

---

## 8 — In-flight work: hierarchical search

> **Status: designed and stubbed, not implemented.** The schema is applied and
> the function signatures exist; the bodies `return "" // TODO: stub` or
> `raise NotImplementedError`. `ResolveQuery` deliberately always returns a
> fallback plan, so the code is safe to call today and changes nothing. The
> detailed spec lives in `search_design.md`, which is **gitignored** — the `§`
> references scattered through the stubs point at it.

**The problem it solves.** Today's retrieval treats "backend engineer" as a
similarity query over 100k+ raw title strings, with an uncalibrated 0.80 blended
floor deciding membership. That floor is a guess, and it scans posting titles.

**The approach.** Decide once, at ingest, what each distinct raw title *is*, and
memoize the decision:

- `title_map` — one row per distinct *normalized* raw title, mapping it to a
  `canonical_title`, a `role_family`, and `specializations[]`. This table is the
  taxonomy's ground truth; the denormalized columns on `job_postings` are a
  materialization of it. It is O(distinct titles) — thousands of rows, not
  millions — which is the whole point: fuzzy matching runs against *it*, not
  against every posting.
- `role_families` / `spec_vocabulary` — controlled vocabularies injected into
  the LLM prompt so it reuses existing families instead of inventing
  near-duplicates. Unknown specs land as `pending` for review.
- Retrieval becomes an **index hit, not a score**:
  `role_family = $1 AND specializations @> $2`. The containment direction is
  asymmetric on purpose — every *query* spec must be present on the posting, but
  posting extras never disqualify. So "software engineer" (no specs) matches
  everything in the family, and `@> '{}'` is trivially true.
- Postings the LLM abstained on (`role_family IS NULL`) are rescued by a
  high-floor (0.86) embedding pool, so an abstention degrades recall instead of
  404-ing.

**Design properties worth noting:**

- **Two arms, one seam.** The structured path substitutes a different `matched`
  CTE; the three aggregation queries are untouched. That is what the §5.2 seam
  was for.
- **Parity again.** `normalize_title_key` must be byte-identical in Python
  (`title_normalizer.py`) and Go (`NormalizeTitleKey`); `constants/title_norm_fixtures.json`
  is the shared assertion set. Go's RE2 has no lookaround, which constrains how
  the Python patterns may be ported.
- **Degrade, never fail.** The title map loads non-fatally at boot and refreshes
  on a ticker; a nil map, a failed load, or an unresolvable query all fall
  through to today's hybrid path.
- **Rollout is gated** by a `SEARCH_MODE` env var (`legacy|structured|auto`),
  and `tests/golden_queries.json` + `scripts/run_golden_queries.py` are the
  behavioral gate for flipping it.
- `data_pipeline/taxonomy/reconcile.py` is the immune system for taxonomy drift
  (merging near-duplicate canonicals, folding orphan families). Also stubbed.

---

## 9 — Deployment

### Image (`Dockerfile`) — four stages

| Stage | Base | Produces |
|---|---|---|
| `model_export` | `debian:bookworm-slim` | `bge-small-en-v1.5` ONNX + tokenizer, fetched by 3 curls from `Xenova/bge-small-en-v1.5` |
| `frontend` | `node:20-slim` | `npm ci && npm run build` → `/src/dist` |
| `backend` | `golang:1.24-bookworm` | ONNX Runtime 1.20.0 (shared) + `libtokenizers` 1.20.2 (static), then `CGO_ENABLED=1 go build` |
| `runtime` | `debian:bookworm-slim` | server binary + SPA bundle + model + `libonnxruntime.so` |

The model stage used to run `optimum-cli export onnx`, which drags in torch and
~1.5 GiB of CUDA wheels for a CPU-only 384-d encoder. Fetching the
pre-converted ONNX is three curls and ~10s — and local dev fetches the *same*
artifact, which is what the embedding-parity requirement (§3.4) demands.

Runtime env baked into the image: `ONNX_MODEL_DIR`, `ONNX_LIBRARY_PATH`,
`FRONTEND_DIST`, `PORT=8080`.

### Cloud Run (`deploy.sh`)

```
service   ttt-backend                     region  us-west1
image     us-west2-docker.pkg.dev/techtrendtracker-499821/techtrendtracker/backend
secret    SUPABASE_DB_URL ← Secret Manager `supabase-db-url:latest`
resources cpu 1 / 2Gi / max-instances 5 / startup CPU boost
```

`./deploy.sh` runs pre-flight (gcloud auth, secret present, Artifact Registry
repo exists) → Cloud Build (or `--local` docker) → `gcloud run deploy` → smoke
test. The smoke test hits `/` (container serving) and `/skills` (DB path
reachable through the secret) and reports them separately, so "container up but
DB unreachable" is distinguishable from "container down". Tags default to
`v<UTC date>-<time>`.

The DB URL is never baked into the image — it's injected from Secret Manager at
deploy time, and `--sync-secret` pushes a new version from local `.env`.

**CI/CD is not yet in the repository.** `deploy.sh` is a manually invoked script
today; there is no `.github/workflows/`. It is written to be automatable — no
interactive prompts, `--quiet` on the deploy, every knob overridable by env var,
and a non-zero exit on any pre-flight or smoke failure — so wrapping it in a
pipeline is the intended next step.

### Local development

| Script | Does |
|---|---|
| `./run.sh` | Pre-flight (venv, `.env` vars, ONNX files, ports free, docker, ollama) → RabbitMQ → extraction worker + content worker + Go backend + Vite. Logs to `logs/`; Ctrl-C tears workers down, leaves RabbitMQ up. |
| `./run.sh --scrape-only` | Ingest side only — fill the DB without the serving layer. |
| `./run.sh --generate-projects` | One-shot catalog build, then exit. |
| `./harvest.sh ["Role, Role"]` | One-shot link harvest into `urls_queue`. Cron-friendly. |

`docker-compose.yml` now contains **only RabbitMQ** — Postgres moved to Supabase
and the raw archive moved to local disk.

Required env (`.env`, gitignored): `SUPABASE_DB_URL`, `SUPABASE_DB_DIRECT_URL`,
`ONNX_MODEL_DIR`, `ONNX_LIBRARY_PATH`, `JOB_POSTINGS_DIR`, `RABBITMQ_HOST`,
`LLM_MODEL`, `PORT`. Full walkthrough in `setup.md`.

---

## 10 — End-to-end summary

1. **Harvest** — `harvest.sh` → Scrapy spider → posting URLs → `urls_queue`.
2. **Scrape** — `content_worker` → page JSON on local disk → path → `job_queue`.
3. **Extract** — `processor` → Gemma skills + normalization + facets +
   384-d title vector + dedup keys → one idempotent row in Supabase.
4. **Mine (periodic)** — `build_catalog` → frequent skill triples filtered by
   support and lift → Gemma project per triple → `project_recommendations`.
5. **Serve** — Go embeds the query, runs hybrid retrieval, aggregates the
   matched set, and answers `/skills`; the frontend's top-5 skills then hit
   `/recommendations` for a pure catalog lookup.
6. **Display** — React SPA, served same-origin by the same Go binary.

Steps 1–4 are the ingest plane, run locally on cron. Step 5–6 are the serving
plane, deployed to Cloud Run. They share nothing but Supabase.

---

## 11 — Known limitations and observations

- **No CI/CD yet.** Deploys are a manual `./deploy.sh`. Tests
  (`tests/`, `backend/services/title_service_test.go`, `npm run typecheck`,
  `scripts/run_golden_queries.py`) exist but nothing runs them automatically.
- **Cross-plane parity is maintained by hand.** The facet regexes and the ONNX
  artifact must match between Python and Go. Nothing in the build currently
  fails if they drift — the embedding parity check in `setup.md` §10 is a manual
  procedure. This is the highest-value thing a CI pipeline could enforce.
- **Ingest is single-machine and manual-ish.** Cron plus `run.sh`; no scheduler,
  no DAG, no retry policy beyond RabbitMQ's requeue.
- **LinkedIn selector fragility.** Both the link spider and the content worker
  depend on specific CSS/XPath selectors. A markup change breaks ingest silently
  — postings fail as `PermanentError` (no title/description) and are dropped.
- **Retrieval thresholds are uncalibrated.** The 0.80 floor and the 0.4/0.6
  weights were chosen by hand, not fit to labelled data. This is the motivating
  complaint behind §8.
- **`extractor.py` still carries the DeepSeek cloud path** and imports
  `LLM_API_KEY` from a gitignored `config.py`. The ingest worker only calls the
  local Ollama path; the cloud method is unused fallback, and the import will
  fail if `config.py` is absent.
- **Cold start.** Cloud Run scale-to-zero means the first request after idle
  pays the ONNX model load. `--min-instances=1` fixes it but leaves the free tier.
- **Supabase free-tier constraints.** 500 MB cap (384-d vectors roughly double
  capacity vs 768-d) and a 7-day inactivity pause — the daily cron harvest is
  what keeps the project awake.
- **`/job_postings/` grows unbounded.** Raw scrape archive is never pruned
  automatically; `setup.md` §13 suggests a cron `find -mtime +90 -delete`.
- **README drift.** `README.md` lists Chart.js in the tech stack; the frontend
  has no charting dependency and renders bars in CSS.
