# Tech Trend Tracker (TTT)

**See what the job market is actually asking for.** Type a role like *Data
Scientist* or *new grad backend engineer* and TTT shows you the most in-demand
technical skills for that role — mined from real, recent LinkedIn postings —
plus related job titles and portfolio project ideas tailored to those skills.

It's built for job seekers, especially students and early-career applicants, who
want a data-driven answer to "what should I actually learn (and build) to get
hired for this role?"

---

## What it does

Search a job title and you get back:

- **Top skills bar chart** — the technologies most frequently required for that
  role, with the percentage of postings that mention each.
- **Headline counts** — how many matching postings were analyzed and how many
  distinct skills were found.
- **Related titles** — the real job titles that cluster around your search, so
  you can discover adjacent roles you might not have thought to look for.
- **Project recommendations** — 3–4 concrete portfolio projects, each built
  around a trio of skills that genuinely co-occur in postings for that role,
  with a difficulty level and a recruiter-facing blurb.

Everything is computed from postings TTT has ingested into its own database — no
results are faked or hand-curated.

---

## Architecture

TTT is split into two **planes** that share three **stores**. The ingest plane
runs locally (on a schedule); the serving plane is a single stateless Go binary
that's cheap to deploy to Cloud Run.

```
INGEST PLANE  (local, scheduled)              SERVING PLANE  (Go, Cloud Run)
──────────────────────────────────           ────────────────────────────────
  Scrapy link spider                            React SPA  ──HTTPS──┐
    └─ publishes posting URLs ─┐                                    ▼
  Content worker  ◀────────────┘  RabbitMQ      Go backend (net/http)
    └─ scrapes page → local JSON                  ├─ embed query  (bge-small ONNX)
  Extraction worker                               ├─ hybrid retrieval over Supabase
    ├─ Gemma 4 / Ollama   → skills                │    (pgvector ANN + pg_trgm)
    ├─ bge-small ONNX     → 384-d title vector    ├─ aggregate top skills + titles
    ├─ rule parser        → seniority / year      └─ catalog lookup → project recs
    └─ INSERT one row ──────────┐
                                ▼
                         ┌──────────────────┐
                         │ Supabase Postgres│   ← shared store
                         │  pgvector (HNSW) │
                         │  pg_trgm + GIN   │
                         └──────────────────┘

STORES
  /job_postings/      local disk — raw scrape archive
  RabbitMQ            local queue — decouples scraping from extraction
  Supabase Postgres   per-posting skills + title embeddings + project catalog
```

The two planes only ever meet at the database. The serving plane is
**model-free at request time for skill extraction and recommendations** — no
cloud LLM is called on the request path. The only model the backend runs per
request is the small embedding model, so latency stays low and the design stays
fully self-hostable.

---

## How it works under the hood

### 1. Ingest — turning raw postings into structured rows

A two-stage Scrapy pipeline feeds an extraction worker, decoupled by RabbitMQ:

1. A **link spider** walks LinkedIn search-result pages for the target roles and
   publishes each posting URL to a queue.
2. A **content worker** scrapes each posting (title, company, description) to a
   local JSON archive.
3. An **extraction worker** does the real work per posting:
   - **Skill extraction** — local **Gemma 4** (via Ollama) reads the description
     and returns a strict-JSON list of skills. Output is then **normalized**
     against hand-maintained canonical-name and capitalization maps, so
     `reactjs`, `React.js`, and `react` all collapse to a single `React`.
   - **Title embedding** — the job title is embedded into a 384-dimension vector
     with **`bge-small-en-v1.5`** exported to **ONNX**.
   - **Facet parsing** — lightweight regex rules tag each posting with a
     **seniority** (`intern` / `new_grad` / `entry` / `senior`) and a **year**.
   - One row is upserted into Supabase. A `uuid5` content hash over the
     normalized posting makes re-ingestion **idempotent** — the same posting
     never lands twice.

Aggregation is deliberately *not* precomputed here. Each posting is stored
individually, and all the interesting statistics are computed at query time
against whatever subset of postings a search matches.

### 2. Skills insights — hybrid search at query time

When you search, the Go backend embeds your query title with the **same** ONNX
model used at ingest (embedding parity is essential — both planes must produce
matching vectors), then runs **hybrid retrieval** over the postings:

- **Semantic search** — cosine similarity against the title embeddings,
  accelerated by a **pgvector HNSW** index. This catches conceptual matches
  ("ML engineer" ≈ "machine learning engineer").
- **Lexical search** — trigram similarity via **pg_trgm**, served by a GIN
  index. This catches typos and substring matches the embedding misses
  (e.g. `embeded` → `Embedded`).

The two result pools are merged with a `FULL OUTER JOIN`, blended into a single
score (trigram weighted slightly higher, since lexical misses are the worse
failure mode), filtered by a relevance floor, and capped at the top matches.
Facets parsed from your query (e.g. "intern", "2026") filter the candidate set
so seniority and year line up with intent.

From that matched set, the backend `unnest`es the skills arrays and runs a
`GROUP BY` to produce the **top-10 skills with percentages**, the full skill
list, and the **most common job titles** in the set (the "related titles").

### 3. Project recommendations — mined offline, served instantly

Recommendations come from a catalog that's **built offline** and then served
with a single index lookup:

1. **Mine triples** — an offline job finds skill *triples* `{A, B, C}` that
   co-occur across many postings, keeping only those above a minimum **support**
   (how many postings contain all three) and a minimum **lift** (how much more
   often they co-occur than chance would predict — this filters out "three
   individually popular skills that just happen to collide").
2. **Generate projects** — for each surviving triple, local **Gemma 4** invents
   one small, finishable portfolio project that genuinely uses all three skills
   together, returning a title, difficulty level, and recruiter-facing blurb.
   These are upserted into a `project_recommendations` table.
3. **Serve** — at request time the backend takes your top skills and does a pure
   `skills <@ $top` subset match (GIN-indexed) to pull every catalog project
   whose triple fits, then runs a **greedy set-cover** selection to pick 3–4
   projects that together span as many of your top skills as possible while each
   stays focused on three. No model runs on the request path.

This split is the core design idea: the expensive, LLM-driven work happens
offline and is cached as data; the request path is just fast SQL.

---

## Tech stack

| Layer | Technology |
|---|---|
| **Ingest** | Python, Scrapy, RabbitMQ (`pika`), Ollama + **Gemma 4**, ONNX Runtime + `tokenizers` (bge-small-en-v1.5), `psycopg` |
| **Database** | Supabase Postgres with **pgvector** (HNSW), **pg_trgm**, GIN indexes |
| **Backend** | **Go** (`net/http`), [hugot](https://github.com/knights-analytics/hugot) for in-process ONNX inference (cgo: ONNX Runtime + `daulet/tokenizers`), `lib/pq` |
| **Frontend** | **React + TypeScript + Vite**, Chart.js |
| **Deploy** | Multi-stage **Docker**, **Google Cloud Run**, Artifact Registry, Secret Manager |

In production the Go binary serves the built React app and the JSON API from the
**same origin**, so there's no separate frontend deploy and no CORS to manage.

---

## API

The backend exposes two JSON endpoints (everything else falls through to the SPA):

| Endpoint | Purpose |
|---|---|
| `GET /skills?job_title=<role>` | Top skills, counts, all skills, and related titles for a role |
| `GET /recommendations?skills=A,B,C,...` | Portfolio projects covering the given top skills |

The frontend calls `/skills` on search, then passes the returned top skills to
`/recommendations` — so recommendations stay a cheap catalog lookup with no
re-run of retrieval.

---

## Getting started

### Use it

Open the app, type a job title into the search bar, and read the chart. Try
adding qualifiers like *"senior"*, *"intern"*, or a year (*"2026"*) — the search
understands seniority and year and filters accordingly.

### Run it locally

Full setup (Supabase, the ONNX model export, Ollama + Gemma 4, the Go cgo
dependencies, and Cloud Run deployment) is documented step-by-step in
**[`setup.md`](setup.md)**. Once prerequisites are in place, two scripts handle
the day-to-day lifecycle:

```bash
./run.sh        # pre-flight checks, brings up RabbitMQ, then launches the
                # extraction worker, content worker, Go backend, and Vite dev
                # server — logs stream to logs/, Ctrl-C tears it all down.

./harvest.sh    # one-shot LinkedIn harvest: discovers posting URLs and feeds
                # them through the ingest pipeline. Cron-friendly for daily runs.
```

In dev, open the Vite server at **http://localhost:5173** (it proxies API calls
to the Go backend on :8080 and gives you hot reload). Rebuild the project
recommendations catalog whenever the corpus has grown enough to shift the
popular skill combinations:

```bash
python -m data_pipeline.recommendations.build_catalog --min-support 25 --min-lift 1.0 --top-n 200
```

---

## Repository layout

```
TechTrendTracker/
├── data_pipeline/
│   ├── scraper/            # Scrapy link spider + content worker
│   ├── llm_processor/      # extraction worker: Gemma skills, facets, normalization
│   ├── embeddings/         # bge-small ONNX title embedder (Python side)
│   ├── recommendations/    # offline triple mining + Gemma project generation
│   └── storage/            # Supabase client
├── backend/                # Go API + serves the built frontend
│   ├── handlers/           # HTTP handlers (/skills, /recommendations)
│   ├── services/           # hybrid retrieval, embeddings, facets, recs
│   └── routers/            # routes + SPA fallback
├── frontend/               # React + TypeScript + Vite SPA
├── constants/              # canonical skill map, capitalization map, LLM prompt
├── schema.sql              # Supabase schema (pgvector, indexes, catalog table)
├── Dockerfile              # multi-stage build for Cloud Run
├── run.sh / harvest.sh     # local lifecycle + ingest scripts
└── setup.md                # full setup & deployment guide
```

---

## License

See [`LICENSE`](LICENSE).
```