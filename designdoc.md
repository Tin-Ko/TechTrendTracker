# Tech Trend Tracker — Design Document

Tech Trend Tracker (TTT) is a skill-tracking platform that mines real job
postings from job boards (currently LinkedIn) to surface the **most in-demand
technical skills** for a given role. It is aimed at job seekers — especially
students and entry-level applicants — who want a data-driven view of what the
market is actually asking for.

A user types a job title (e.g. *Data Scientist*) into a search bar, and TTT
responds with a bar chart of the top skills for that role, plus headline
counts for how many jobs and how many distinct skills were found.

This document describes how the system is built, broken into its four parts:

1. **Data collection** — Scrapy crawlers + an LLM that extract skills from raw
   LinkedIn postings, with raw text stored in HDFS.
2. **Data analysis** — a PySpark job that aggregates extracted skills and
   writes statistics to PostgreSQL.
3. **Backend** — a Go HTTP server exposing chart/skills APIs over the database.
4. **Frontend** — server-rendered HTML enhanced with HTMX, Tailwind, and
   Chart.js.

---

## Architecture at a glance

```
                         ┌─────────────────────────────────────────────┐
                         │            DATA COLLECTION (Python)           │
                         │                                               │
  LinkedIn  ──scrapy──▶  │  linkedin.py            linkedin_scraper.py   │
  search                 │  (collect job links)    (scrape job content)  │
  pages                  │        │                      │               │
                         │        ▼                      ▼               │
                         │  *_job_links.txt        raw JSON ─▶ HDFS       │
                         │                               │   /jobs/...    │
                         │                               ▼               │
                         │                     RabbitMQ "job_queue"       │
                         │                               │ (hdfs path)   │
                         │                               ▼               │
                         │  processor.py  ── Extractor (DeepSeek/Ollama) │
                         │                ── RequirementsParser (clean)  │
                         │                               │               │
                         │                               ▼               │
                         │                  cleaned skills ─▶ HDFS        │
                         │                                  /skills/...   │
                         └───────────────────────────────┬───────────────┘
                                                         │
                         ┌───────────────────────────────▼───────────────┐
                         │            DATA ANALYSIS (PySpark)            │
                         │  analyzer.py reads /skills/<role>/<date>/*.json│
                         │  explode + group + count + percentage          │
                         │            │                                   │
                         └────────────┼───────────────────────────────────┘
                                      ▼
                         ┌───────────────────────────┐
                         │      PostgreSQL (Docker)   │
                         │  job_skill_stats           │
                         │  job_count                 │
                         └────────────┬───────────────┘
                                      ▼
                         ┌───────────────────────────┐         ┌──────────────┐
                         │     BACKEND (Go, net/http) │◀──HTTP──│  FRONTEND     │
                         │  /        home page        │  HTML   │  HTMX +       │
                         │  /chart   chart page       │  JSON   │  Tailwind +   │
                         │  /skills  top-skills JSON  │────────▶│  Chart.js     │
                         └───────────────────────────┘         └──────────────┘
```

The four parts are **decoupled** and communicate through shared infrastructure
rather than direct calls:

- The scraper and the LLM processor are decoupled via **RabbitMQ** (a job
  queue) and **HDFS** (shared file storage).
- The data pipeline and the backend are decoupled via **PostgreSQL** — the
  pipeline writes aggregate stats, the backend only reads them.
- The frontend and backend are decoupled via **HTTP** (server-rendered HTML +
  a small JSON endpoint for the chart).

---

## Repository layout

```
TechTrendTracker/
├── data_pipeline/
│   ├── scraper/
│   │   ├── linkedin.py             # Stage 1: collect job posting links
│   │   ├── linkedin_scraper.py     # Stage 2: scrape each posting → HDFS + queue
│   │   ├── data_science_job_links.txt  # collected links (input to stage 2)
│   │   └── job_links.txt
│   ├── llm_processor/
│   │   ├── extractor.py            # LLM skill extraction (DeepSeek / Ollama)
│   │   ├── requirements_parser.py  # normalize / canonicalize skill strings
│   │   ├── processor.py            # queue consumer tying extractor + parser
│   │   └── config.py               # LLM_API_KEY (gitignored, not committed)
│   └── analysis/
│       ├── analyzer.py             # PySpark aggregation → PostgreSQL
│       └── db_client.py            # (stub) Postgres client helper
├── storage/
│   └── hdfs/hdfs.py                # thin HDFS client wrapper (WebHDFS)
├── constants/
│   ├── canonical_skill_map.py      # alias → canonical skill name
│   ├── tech_capitalization.py      # lowercase → correctly cased name
│   └── system_prompt.txt           # LLM extraction instructions
├── backend/                        # Go HTTP server
│   ├── main.go                     # entrypoint, DB init, server start
│   ├── routers/router.go           # route table + static file server
│   ├── handlers/                   # HTTP handlers (chart, skills, home, test)
│   ├── services/                   # DB queries / business logic
│   ├── utils/                      # DB connection, JSON/HTML helpers
│   └── frontend/                   # templates + static assets (served by Go)
│       ├── templates/              # Go html/template files
│       └── static/                 # JS + CSS (Chart.js logic, transitions)
├── schema.sql                      # PostgreSQL table definitions
├── docker-compose.yml              # PostgreSQL + RabbitMQ
└── Readme.md                       # quick-start / deployment instructions
```

---

## Part 1 — Data collection

The goal of this part is to turn live LinkedIn job postings into a structured
list of skills per posting. It runs as a **two-stage Scrapy pipeline** glued
together by HDFS (for raw text) and RabbitMQ (for work hand-off), with an LLM
doing the actual skill extraction.

### Technologies
- **Scrapy 2.12** — web crawling framework (the "python spider").
- **HDFS (Hadoop 3.4.1)** — distributed storage for raw posting JSON, accessed
  over WebHDFS via the `hdfs` Python client.
- **RabbitMQ** — message broker decoupling scraping from LLM processing.
- **LLM** — DeepSeek (`deepseek-chat`, OpenAI-compatible API) in the primary
  path, with a local **Ollama** path (`llama3:instruct`) as an alternative.
- **pika** — RabbitMQ (AMQP) client for Python.

### Stage 1 — Collect job links (`data_pipeline/scraper/linkedin.py`)

`LinkedInJobSpider` builds a set of LinkedIn job-search URLs by taking a
cross-product of:
- **Experience levels** (`f_E` = 1–4),
- **Keywords / roles** — currently `Data Scientist`, `Data Engineer`,
  `Machine Learning Engineer` (a much larger commented-out list of ~50 tech
  roles exists for future expansion),
- a fixed **time window** (`f_TPR=r604800`, the last 7 days) and **geo ID**
  (`102095887`).

For each search results page, it extracts job links via the CSS selector
`ul.jobs-search__results-list a.base-card__full-link::attr(href)` and appends
them to `data_science_job_links.txt`. On startup it deletes any existing links
file so each run starts clean.

Politeness/anti-detection is configured through `custom_settings`: a 4-second
download delay with randomization, plus Scrapy **AutoThrottle** (start delay 4s,
max 8s, target concurrency 1.0) so it crawls one request at a time.

### Stage 2 — Scrape posting content (`data_pipeline/scraper/linkedin_scraper.py`)

`LinkedInJobContentSpider` reads the links file produced by stage 1 and uses
each link as a start URL. For every posting it extracts:
- **Job title** — `//h1[contains(@class,"top-card-layout__title")]/text()`
- **Company** — `//a[contains(@class,"topcard__org-name-link")]/text()`
- **Job description** — all text under `div.show-more-less-html__markup`,
  joined and whitespace-cleaned.

It then does two things per posting:
1. **Writes the raw JSON to HDFS** at
   `/jobs/data_scientist/<today>/<uuid>.json` (a `{job_title, company,
   job_description}` object), using the `HDFSClient` wrapper.
2. **Publishes the HDFS path** to the durable RabbitMQ queue `job_queue` (with
   persistent delivery mode) so the LLM processor can pick it up.

The same AutoThrottle/delay politeness settings as stage 1 apply. Failures on
individual postings (e.g. expired listings) are caught and skipped so the crawl
keeps going.

### HDFS client (`storage/hdfs/hdfs.py`)

A thin wrapper around `hdfs.InsecureClient` pointed at WebHDFS
(`http://localhost:9870`, user `bartsuper`). It exposes `read_json`, `write`,
`upload`, `download`, `list_dir`, and `delete`. This is the single abstraction
both the scraper (write raw postings) and the processor (read raw, write
cleaned) use to talk to HDFS.

### LLM processing (`data_pipeline/llm_processor/`)

**`processor.py`** is the orchestrator and a **RabbitMQ consumer**:
- On startup it wires together an `Extractor` (LLM) and a `RequirementsParser`
  (normalizer), connects to HDFS, declares and **purges** `job_queue`, and
  begins consuming with `prefetch_count=1` (one message at a time).
- For each message (an HDFS path), `consumer_callback` reads the raw posting
  JSON from HDFS, runs `process_job_description`, and writes the result to
  `/skills/data_scientist/<today>/<same-filename>.json`, then acks the message.
- `process_job_description` = `Extractor.extract_skills_from_job_cloudLLM` →
  `RequirementsParser.clean_extracted_data`. The output JSON keeps
  `job_title`, `company`, and a cleaned `job_skills` list.

**`extractor.py`** (`Extractor`) calls an LLM to pull skills out of free-text
descriptions:
- **Cloud path** (`extract_skills_from_job_cloudLLM`) — uses the OpenAI client
  pointed at `https://api.deepseek.com`, model `deepseek-chat`, with
  `response_format={"type":"json_object"}` to force structured output. The API
  key comes from `data_pipeline/llm_processor/config.py` (`LLM_API_KEY`), which
  is **gitignored** and not committed.
- **Local path** (`extract_skills_from_job`) — uses `ollama.chat` with
  `llama3:instruct`, `format="json"`, `temperature=0` as an offline alternative.
- The system prompt (`constants/system_prompt.txt`) instructs the model to
  return **only** programming languages, frameworks, certifications, or
  programs, in the exact shape `{"skills": ["skill1", "skill2", ...]}`, with a
  worked example to anchor the format.

**`requirements_parser.py`** (`RequirementsParser`) cleans and de-duplicates the
raw skill strings so the same technology doesn't appear under five spellings:
- `normalize_skill` lowercases/trims, strips parentheses, splits on `/` into
  multiple skills, applies the **canonical skill map** (`react.js`/`reactjs` →
  `React`), applies the **tech capitalization map** (correct casing like
  `JavaScript`, `C#`), and strips stray punctuation (keeping `+` and `#` for
  `C++`/`C#`).
- `clean_extracted_data` runs every skill through normalization, flattens any
  nested lists produced by `/`-splitting, and returns a **sorted, de-duplicated
  set** of canonical skills.

The two mapping tables live in `constants/` (`canonical_skill_map.py`,
`tech_capitalization.py`) and are the project's hand-maintained taxonomy.

**Net result of Part 1:** for each role/date, HDFS holds raw postings under
`/jobs/<role>/<date>/` and cleaned per-posting skill lists under
`/skills/<role>/<date>/`.

---

## Part 2 — Data analysis (PySpark)

This part turns the per-posting skill lists into **aggregate statistics** the
backend can serve.

### Technologies
- **PySpark 3.5.5** running against **HDFS** (`hdfs://localhost:9000`).
- **psycopg (psycopg3)** to write into PostgreSQL.

### How it works (`data_pipeline/analysis/analyzer.py`)

`JobSkillAnalyzer`:
1. Starts a `SparkSession` configured with
   `spark.hadoop.fs.defaultFS = hdfs://localhost:9000`.
2. **Loads** all cleaned skill files for a role/date via
   `spark.read.json("hdfs:///skills/data_scientist/<today>/*.json")`, then tags
   every row with the `job_title` (currently hard-coded to `"data scientist"`).
3. **Aggregates** in `get_all_skills`: `explode("job_skills")` to one row per
   (posting, skill), then `groupBy("skill").count()` ordered descending — i.e.
   how many postings mention each skill.
4. Computes a **percentage** per skill = `skill_count / total_postings * 100`.
5. **Writes to PostgreSQL** in `save_to_postgres`:
   - one row into `job_count` (`job_title`, total postings analyzed),
   - bulk `executemany` into `job_skill_stats` (`job_title`, `skill`, `count`,
     `percentage`),
   then commits and closes the connection.

The DB connection parameters (db `skillsDB`, user `bartsuper`, localhost:5432)
match the Docker Postgres service. `db_client.py` is a partially written helper
(`DatabaseClient`) intended to factor out the Postgres logic; the active code
path lives directly in `analyzer.py`.

### Schema (`schema.sql`)

```sql
CREATE TABLE job_skill_stats (
    job_title TEXT,
    skill     TEXT,
    count     INTEGER,
    percentage REAL,
    PRIMARY KEY(job_title, skill)
);

CREATE TABLE job_count (
    job_title  TEXT,
    job_count  INTEGER,
    PRIMARY KEY(job_title)
);
```

This schema is the **contract between the pipeline and the backend**: the
analyzer writes it, the Go server reads it. It is auto-applied on first DB boot
because `docker-compose.yml` mounts `schema.sql` into Postgres's
`/docker-entrypoint-initdb.d/`.

---

## Part 3 — Backend (Go)

A small, standard-library HTTP server that reads the aggregated stats from
PostgreSQL and serves both rendered HTML pages and a JSON endpoint for the
chart. It also serves the frontend's static assets and templates.

### Technologies
- **Go 1.24** with the standard library `net/http` and `html/template`.
- **`github.com/lib/pq`** — PostgreSQL driver (used via `database/sql`).
- Module path: `github.com/Tin-Ko/TechTrendTracker`.

### Structure & flow

**Entrypoint (`main.go`)** — initializes the DB connection
(`utils.InitDB("localhost","5432","bartsuper","abcd1234","skillsDB")`), builds
the router, and listens on `0.0.0.0:$PORT` (default **8080**).

**Router (`routers/router.go`)** — registers four routes plus a static file
server:

| Route     | Handler              | Returns                                   |
|-----------|----------------------|-------------------------------------------|
| `/`       | `HomeHandler`        | Home page (search bar) as HTML            |
| `/chart`  | `HandleGetChart`     | Full chart page as HTML                    |
| `/skills` | `HandleGetTopSkills` | Top-10 skills + all skills as **JSON**    |
| `/test`   | `TestHandler`        | Plain-text health check                    |
| `/static/`| `http.FileServer`    | CSS/JS from `frontend/static`             |

**Handlers (`handlers/`)** are thin HTTP adapters:
- `HandleGetChart` reads `job_title` from the query string, calls
  `services.GetChartData`, then renders `layout.html` + `chart_page.html`.
- `HandleGetTopSkills` validates `job_title`, calls `services.GetTopSkills`, and
  JSON-encodes the result (this is what the chart's JS fetches).
- `HomeHandler` renders `layout.html` + `index.html`.

**Services (`services/`)** hold the SQL/business logic:
- `GetChartData` → for a job title, returns `{JobTitle, JobCount, SkillCount}`
  by joining `job_count` and `job_skill_stats` and counting distinct skills.
- `GetTopSkills` → returns the **top 10** skills (`name`, `count`, `percentage`,
  ordered by count desc) plus the full `AllSkills` list and total counts. The
  `Skill`/`SkillsResponse` structs define the JSON the frontend consumes.

**Utils (`utils/`)**:
- `db.go` — package-level `*sql.DB` (`utils.DB`), opened with `sslmode=disable`
  and pinged on init.
- `response.go` / `error.go` — JSON and HTML response/error helpers.

> Note on configuration: DB credentials and the LinkedIn/role targeting are
> currently **hard-coded** to local development values across the Go and Python
> code (`localhost`, `bartsuper`, `skillsDB`, `data scientist`). A root `.env`
> file (Supabase URL/key) exists but isn't wired into the Go server, which talks
> to the local Docker Postgres instead.

---

## Part 4 — Frontend (HTMX + Tailwind + Chart.js)

The frontend is **server-rendered HTML** (Go `html/template`) progressively
enhanced in the browser. There is no SPA build step; assets are loaded from CDNs
and a couple of small local JS files served by the Go static handler.

### Technologies
- **HTMX 1.9.2** — declarative AJAX (loaded in the layout; the app is built to
  swap server-rendered fragments).
- **Tailwind CSS** (CDN) — utility-first styling.
- **Chart.js** (CDN) — renders the skills bar chart.
- Vanilla JS for the chart data fetch and the search-bar animation.

### Templates (`backend/frontend/templates/`)

- **`layout.html`** — the shared shell: pulls in HTMX, Tailwind, Chart.js, and
  `/static/styles.css`, then renders the `content` block via
  `{{ template "content" . }}`.
- **`index.html`** (home) — defines the `content` block: the big "TTT" logo and
  a search `form` (`GET /chart`, field `job_title`) styled as a rounded pill.
- **`chart_page.html`** (results) — defines `content` for the results view: a
  shrunken top search bar, a `#chart-container` whose `data-job-title` attribute
  carries the title into JS, a `<canvas id="tech-skills-chart">`, the
  `/static/barChart.js` script, and two stat cards showing `{{ .JobCount }}`
  Jobs Found and `{{ .SkillCount }}` Skills Found.
- **`chart_partial.html`** / **`skills_partial.html`** — smaller fragments
  (a bare chart container and a top-10 list) intended for HTMX partial swaps.

### Static assets (`backend/frontend/static/`)

- **`barChart.js`** — the heart of the chart view. It reads the job title from
  `#chart-container[data-job-title]`, `fetch`es `GET /skills?job_title=…`, and
  builds a Chart.js bar chart (skill name vs. posting count), with custom
  tooltips showing both **count** and **percentage**, dark-themed axes, and
  responsive sizing. It destroys any prior chart instance before re-rendering.
- **`searchTransition.js`** — animates the home → results transition by
  swapping Tailwind classes on submit (shrinking the logo and search bar and
  repositioning them) for a smooth visual handoff.
- **`styles.css`** — supplemental styling alongside Tailwind utilities.

### Request → render flow
1. User submits the search form → `GET /chart?job_title=<role>`.
2. Go renders `chart_page.html`, embedding the job title and the
   jobs/skills headline counts (from `GetChartData`).
3. In the browser, `barChart.js` fires `GET /skills?job_title=<role>`, gets JSON
   from `GetTopSkills`, and draws the bar chart of the top skills.

---

## How the parts tie together (end-to-end)

1. **Collect** — `linkedin.py` gathers job-posting links for the target roles.
2. **Scrape** — `linkedin_scraper.py` visits each link, stores raw posting JSON
   in **HDFS** (`/jobs/...`), and publishes its HDFS path to **RabbitMQ**.
3. **Extract** — `processor.py` consumes each path, reads the raw text from
   HDFS, has the **LLM** (DeepSeek/Ollama) extract skills, **normalizes** them
   against the canonical/capitalization maps, and writes cleaned per-posting
   skill JSON back to HDFS (`/skills/...`).
4. **Analyze** — `analyzer.py` (**PySpark**) reads all cleaned files for a
   role/date, counts skill frequencies and percentages, and writes
   `job_skill_stats` + `job_count` into **PostgreSQL**.
5. **Serve** — the **Go** backend reads those tables and serves the home page,
   the chart page, and a `/skills` JSON endpoint.
6. **Display** — the **HTMX/Tailwind/Chart.js** frontend renders the search
   experience and the in-demand-skills bar chart.

The shared infrastructure — **HDFS** (raw + cleaned text), **RabbitMQ** (scrape
→ LLM hand-off), and **PostgreSQL** (pipeline → backend) — is what keeps the
four parts independently runnable while still forming one pipeline.

### Infrastructure (`docker-compose.yml`)
- **PostgreSQL 16** (`my_postgres`, db `skillsDB`, port 5432) with `schema.sql`
  auto-loaded on first boot and a persistent `pgdata` volume.
- **RabbitMQ** (management image) exposing AMQP on 5672 and the management UI
  on 15672.

HDFS/Hadoop and the Ollama runtime (if used) run outside Docker on the host.

---

## Running the system (summary)

From the repository `Readme.md`, the intended order is:

```bash
# 1. Start HDFS for raw job descriptions
start-dfs.sh

# 2. Start Postgres + RabbitMQ
sudo docker compose up -d

# 3. Collect job links for the target roles
python3 -m data_pipeline.scraper.linkedin

# 4. Start the LLM processor first, then the content scraper
python3 -m data_pipeline.llm_processor.processor
python3 -m data_pipeline.data_pipeline.linkedin_scraper

# 5. (Run the PySpark analysis to populate Postgres)
python3 -m data_pipeline.analysis.analyzer

# 6. Start the Go backend
cd backend && go run .
# → http://localhost:8080
```

### Dependencies (from `Readme.md`)
- **Python 3.12** — PySpark 3.5.5, Scrapy 2.12.0, Ollama 0.4.8 (plus `hdfs`,
  `pika`, `openai`, `psycopg`).
- **Hadoop 3.4.1**, **Java 11**.
- **Docker 27.5.1** — PostgreSQL 16, RabbitMQ.
- **Go 1.24.2**.

---

## Notes, current limitations, and observations

- **Single-role focus.** Several places are hard-coded to `data_scientist` /
  `"data scientist"` (HDFS paths, the Spark `lit()` tag, the link file name).
  The broader role list exists but is commented out in `linkedin.py`; supporting
  many roles end-to-end would mean parameterizing these.
- **Manual orchestration.** The pipeline stages are run by hand in sequence;
  there is no scheduler/airflow-style DAG. RabbitMQ decouples scrape↔LLM, but
  the link-collection and analysis steps are invoked manually.
- **Config & secrets.** `LLM_API_KEY` lives in a gitignored `config.py`; DB
  credentials are hard-coded in both Go and Python. The root `.env` (Supabase)
  is present but not wired into the running services.
- **Resilience.** LinkedIn scraping relies on specific CSS/XPath selectors and
  polite throttling; selector changes or anti-bot measures on LinkedIn's side
  would require updates. Per-posting failures are skipped rather than retried.
- **Partial code.** `analysis/db_client.py` is an unfinished helper; the live
  DB-writing logic is inline in `analyzer.py`. Some template fragments
  (`*_partial.html`) and `testChart.js`/`test.go` are scaffolding for
  HTMX-partial and debugging workflows.
```
