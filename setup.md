# Tech Trend Tracker — Setup & Run Guide

End-to-end instructions for getting TTT running on your local machine and
deploying the Go backend to Google Cloud Run. Reference: `search_design.md`.

---

## 1. Architecture at a glance

Two planes, three stores:

```
INGEST  (local)                       SERVING  (Cloud Run)
  Scrapy spider                         Go backend (hugot + Supabase)
    -> /job_postings/*.json               <- HTTPS request
    -> RabbitMQ (local path)              -> bge-small ONNX (embed query)
  Extraction worker (Python)              -> Supabase: ANN + aggregation SQL
    consumes path
    -> Gemma 4 via Ollama (skills)
    -> bge-small ONNX  (embed title)
    -> facet parser    (seniority/year)
    -> INSERT into Supabase

STORES
  /job_postings/        local disk (raw scrape archive)
  RabbitMQ              local (decouples scraper <-> worker)
  Supabase Postgres     skills + 384-d title embeddings (pgvector)
```

You will run:
- **Supabase** (managed, free tier) — Postgres + pgvector
- **RabbitMQ** (local Docker) — queue between scraper and extraction worker
- **Ollama** (local) — serves Gemma 4 for skill extraction
- **Python scraper + extraction worker** (local, scheduled/cron)
- **Go backend** (local for dev, Cloud Run for prod)

---

## 2. Prerequisites

Install these once on your local machine.

| Tool | Why | Install |
|---|---|---|
| Docker (or compatible) | RabbitMQ | https://docs.docker.com/get-docker/ |
| Python 3.10+ | scraper + worker | system package |
| Go 1.24+ | backend | https://go.dev/dl/ |
| `gcc` + build tools | cgo (hugot) | `sudo apt install build-essential` |
| Node.js 20+ | frontend (Vite + React) | https://nodejs.org or `nvm install 20` |
| Ollama | Gemma 4 inference | https://ollama.com/download |
| `gcloud` CLI | Cloud Run deploy | https://cloud.google.com/sdk/docs/install |
| A Supabase account | managed Postgres + pgvector | https://supabase.com (free) |
| A Google Cloud project with billing enabled | Cloud Run / Artifact Registry | https://console.cloud.google.com |

Optional but helpful: `psql` for poking at Supabase.

---

## 3. Clone and create directories

```bash
git clone <repo-url> TechTrendTracker
cd TechTrendTracker

# Local archive for raw scraped postings. Pick any path you can write to.
sudo mkdir -p /job_postings
sudo chown "$USER" /job_postings
```

---

## 4. Supabase setup

### 4.1 Create the project

1. Go to https://supabase.com -> New project. Pick the closest region.
2. Save the **database password** when prompted — you cannot recover it later
   without resetting.

### 4.2 Apply the schema

In the Supabase SQL editor, paste the contents of `schema.sql` and run it.
This:
- enables the `vector` extension,
- drops the legacy `job_skill_stats` / `job_count` tables,
- creates `job_postings` with an HNSW vector index, a GIN full-text index,
  and B-tree indexes on `seniority` / `posting_year`.

Verify:
```sql
SELECT extname FROM pg_extension WHERE extname = 'vector';
\d job_postings
```

### 4.3 Grab the connection strings

Project Settings -> Database -> Connection pooling:

- **Pooler (transaction mode), port 6543** — use this for the Go backend on
  Cloud Run. Cloud Run fans out across many instances and the free tier caps
  direct (5432) connections around 60.
- **Direct connection, port 5432** — fine for the local ingest worker.

The DSN looks like:
```
postgresql://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

### 4.4 Rotate the service-role key

If you cloned a repo where `.env` was previously committed with a Supabase
key, **rotate it now** in the Supabase dashboard (API -> Reset). The new key
should only live in `.env` (gitignored) and Secret Manager.

---

## 5. ONNX model export (bge-small-en-v1.5)

The Python ingest worker and the Go backend must use the **same** ONNX
artifact, the same tokenizer, mean pooling, and L2 normalization. This is
non-negotiable — mismatched embeddings silently break the search quality.

```bash
pip install "optimum[exporters]" sentence-transformers

mkdir -p models
optimum-cli export onnx \
  --model BAAI/bge-small-en-v1.5 \
  --task feature-extraction \
  models/bge-small-en-v1.5

ls models/bge-small-en-v1.5
# expected: model.onnx  tokenizer.json  config.json  ...
```

If `tokenizer.json` is missing from the export, copy it:
```bash
python -c "from transformers import AutoTokenizer; \
  AutoTokenizer.from_pretrained('BAAI/bge-small-en-v1.5').save_pretrained('models/bge-small-en-v1.5')"
```

Keep this directory under source control or in a release artifact; both
planes load from the same location.

---

## 6. Ollama + Gemma 4

```bash
# Start the daemon (or rely on the system service).
ollama serve &

# Pull the Gemma model you want to use.
# The exact tag depends on what your Ollama install exposes — check `ollama list`.
ollama pull gemma4:latest      # adjust if your tag is different, e.g. gemma3:27b

# Sanity check.
ollama run gemma4:latest "Extract skills as JSON from: We use Go, gRPC, Postgres."
```

Set `LLM_MODEL` in `.env` to whatever tag you pulled.

---

## 7. Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs Scrapy, pika, ollama, psycopg, onnxruntime, tokenizers, and the
DeepSeek/OpenAI client (kept around as a cloud fallback for the extractor;
not used by default).

---

## 7b. Frontend (Vite + React + TypeScript)

The frontend lives at `frontend/` at the repo root. Install once:

```bash
cd frontend
npm install
cd ..
```

In dev, Vite serves the SPA on http://localhost:5173 and proxies `/skills`
calls to the Go backend on :8080 (configured in `vite.config.ts`). In prod
the Go binary serves the built static files out of `frontend/dist/`
alongside the JSON API, so there's no separate frontend deploy.

```bash
cd frontend && npm run build      # one-shot production build → frontend/dist
cd frontend && npm run typecheck  # strict TS check, no emit
```

---

## 8. Go backend dependencies

The Go backend uses [hugot](https://github.com/knights-analytics/hugot),
which is cgo-linked against:

- **ONNX Runtime** (shared library)
- **daulet/tokenizers** (static library `libtokenizers.a`)

### 8.1 Install ONNX Runtime

```bash
ORT_VERSION=1.20.0
mkdir -p /usr/local/lib
curl -L "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
  | sudo tar -xz --strip-components=1 -C /usr/local
# Now /usr/local/lib/libonnxruntime.so exists.
sudo ldconfig
```

### 8.2 Install libtokenizers.a

Prebuilt binaries from the daulet/tokenizers releases page:

```bash
TOK_VERSION=1.20.2
curl -L "https://github.com/daulet/tokenizers/releases/download/v${TOK_VERSION}/libtokenizers.linux-amd64.tar.gz" \
  | sudo tar -xz -C /usr/local/lib
# Now /usr/local/lib/libtokenizers.a exists.
```

### 8.3 Build

```bash
cd backend
go build ./...
# If the linker complains about -ltokenizers or onnxruntime, double-check
# the install paths above and that /usr/local/lib is on your library path:
#   export LIBRARY_PATH=/usr/local/lib:$LIBRARY_PATH
#   export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
```

---

## 9. Environment file

```bash
cp .env.example .env
```

Fill it in:

| Var | Example | Notes |
|---|---|---|
| `SUPABASE_DB_URL` | `postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:6543/postgres` | Pooled for Cloud Run; direct (5432) is fine locally |
| `ONNX_MODEL_DIR` | `./models/bge-small-en-v1.5` | Must contain `model.onnx` + `tokenizer.json` |
| `ONNX_LIBRARY_PATH` | `/usr/local/lib/libonnxruntime.so` | hugot defaults to `onnxruntime.so` (no `lib` prefix) and will fail to load; set this explicitly |
| `JOB_POSTINGS_DIR` | `/job_postings` | Raw scrape archive |
| `RABBITMQ_HOST` | `localhost` | Broker host |
| `LLM_MODEL` | `gemma4:latest` | Whatever `ollama list` shows |
| `LLM_API_KEY` | (empty) | Only needed if you switch to DeepSeek fallback |
| `PORT` | `8080` | Cloud Run injects this in prod |

**Never commit `.env`.** Confirm `.gitignore` excludes it.

---

## 10. Embedding parity test (do this before trusting results)

The Python and Go embedders must produce matching vectors for the same input
within floating-point tolerance. Run before the first real query.

```bash
# Python side
source .venv/bin/activate
python -c "
from data_pipeline.embeddings.embedder import TitleEmbedder
e = TitleEmbedder()
v = e.embed('new grad backend engineer')
print('py', len(v), v[:5])
"
```

```bash
# Go side — write a quick smoke main or use a test, e.g.:
cd backend
cat > /tmp/embed_smoke.go <<'EOF'
package main
import (
    "fmt"
    "github.com/Tin-Ko/TechTrendTracker/services"
)
func main() {
    if err := services.InitEmbedService(); err != nil { panic(err) }
    s, _ := services.GetEmbedService()
    v, err := s.Embed("new grad backend engineer")
    if err != nil { panic(err) }
    fmt.Println("go", len(v), v[:5])
}
EOF
go run /tmp/embed_smoke.go
```

Both runs should print 384 and the first 5 values should agree to ~1e-5.
If they diverge, you have a mismatched ONNX export, tokenizer config, or
pooling/normalization difference — do not proceed.

---

## 11. Running locally

Two scripts at the repo root do all the lifecycle work:

- **`./run.sh`** — pre-flight checks, brings up RabbitMQ via Docker, then
  launches the three long-running services (extraction worker, content
  worker, Go backend) in the background with logs going to `logs/`.
  Stays in the foreground; `Ctrl-C` tears every worker down. Leaves the
  RabbitMQ container running (run `docker compose down` to stop it too).
- **`./harvest.sh`** — one-shot LinkedIn link harvest. Publishes URLs to
  `urls_queue`; the content worker consumes them. Cron-friendly.

### 11.1 Start the stack

```bash
./run.sh                          # default: live-tails the extractor (logs/processor.log)
./run.sh --follow content_worker  # tail a different worker
./run.sh --follow frontend        # tail the Vite dev server
./run.sh --follow all             # interleave all four log files
./run.sh --no-follow              # don't tail anything; just block
./run.sh --help                   # full usage
```

You should see green pre-flight ticks (`.env`, env vars, ONNX files,
Docker, Ollama, Node all reachable), `rabbitmq ready`, four PIDs
(processor, content_worker, backend, frontend), and a "stack up" line
pointing at **http://localhost:5173** (Vite dev server — open this one).
After the banner, the extractor's log streams to this terminal so you
can watch Gemma 4 producing skill extractions in real time.

Log files always land in `logs/<name>.log` regardless of which one is
being followed, so you can also `tail -f logs/<other>.log` in another
terminal at any time.

In dev, Vite proxies `/skills` requests to the Go backend on :8080
automatically. The Go backend serves the built `frontend/dist/` files
at `/` in prod, but during dev you should hit Vite (port 5173) because
it has hot reloading.

### 11.2 Ingest fresh data

```bash
./harvest.sh
```

The link spider walks LinkedIn search result pages and `basic_publish`es
each posting URL to `urls_queue` as it discovers it. The content_worker
picks them up immediately, scrapes the page, and hands the local file path
to the extraction worker, which extracts skills (Gemma 4), embeds the
title (bge-small ONNX), parses facets, and INSERTs one row into Supabase.

The `posting_id` is `uuid5(NAMESPACE_URL, job_url)`, so re-running the
harvester is idempotent — the same URL produces the same UUID, and
`ON CONFLICT (posting_id) DO NOTHING` swallows duplicate inserts.

Verify in the Supabase SQL editor:
```sql
SELECT job_title, seniority, posting_year, array_length(skills, 1) AS n_skills
FROM job_postings
ORDER BY posted_date DESC LIMIT 10;

SELECT COUNT(*), AVG(array_length(skills, 1))::int AS avg_skills
FROM job_postings;
```

### 11.3 Use the app

Open http://localhost:8080 and search for a job title. You should see a bar
chart of top skills plus a row of related-title chips. Empty chips usually
mean too few rows or facet filters that are too tight — raise `matchLimit`
in `backend/services/skills_service.go` or relax the facet rules.

### 11.4 Scheduling ingest

The harvest script is the only cron-driven piece. In production the
long-running services should sit under `systemd` or `supervisor` instead
of `./run.sh`.

```cron
# Daily link harvest at 02:00 local; URLs flow urls_queue -> job_queue.
0 2 * * * /path/to/TechTrendTracker/harvest.sh >> /var/log/ttt/harvest.log 2>&1
```

---

## 12. Deploying the Go backend to Google Cloud Run

### 12.1 One-time GCP setup

```bash
gcloud auth login
gcloud config set project <your-project-id>

# Enable required APIs
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

# Create an Artifact Registry repo for the container image
REGION=us-central1
gcloud artifacts repositories create ttt \
  --repository-format=docker \
  --location=$REGION
```

### 12.2 Store the Supabase DSN in Secret Manager

```bash
printf '%s' 'postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:6543/postgres' \
  | gcloud secrets create supabase-db-url --data-file=-
```

### 12.3 The Dockerfile

A multi-stage `Dockerfile` at the repo root assembles everything Cloud
Run needs. It has four stages:

1. **`model_export`** — exports `BAAI/bge-small-en-v1.5` to ONNX via
   `optimum-cli`. Replaces having `models/` in git; the image is
   reproducible from upstream weights + pinned `optimum`/`transformers`
   versions.
2. **`frontend`** — `npm ci && npm run build` to produce `dist/`.
3. **`backend`** — Go build with `CGO_ENABLED=1`, ONNX Runtime + the
   `daulet/tokenizers` static lib that `hugot` links against.
4. **runtime** — `debian:bookworm-slim` with just the Go binary, the
   ONNX Runtime shared library, the frontend `dist/`, and the exported
   model. Sets `ONNX_MODEL_DIR`, `ONNX_LIBRARY_PATH`, and
   `FRONTEND_DIST`.

The file is already in the repo at `Dockerfile`. A `.dockerignore`
alongside it keeps `node_modules`, `.venv`, `models/`, `logs/`, `.env`,
and `.git` out of the build context.

> If you ever swap to a larger embedding model (`bge-base`, `bge-large`)
> and the image gets close to Cloud Run's 32 GiB limit, mount the model
> directory from GCS via Cloud Storage Fuse instead.

### 12.4 Build and push

```bash
REGION=us-central1
PROJECT=$(gcloud config get-value project)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/ttt/backend:$(git rev-parse --short HEAD)"

# Build from the repo root (where Dockerfile + .dockerignore live).
# First build will take ~5–8 min: model export (~3 min) + cgo deps
# (~2 min) + Go build (~30 s). Subsequent builds reuse layer cache,
# typically ~1–2 min.
gcloud builds submit --tag "$IMAGE"
```

### 12.5 Deploy

```bash
gcloud run deploy ttt-backend \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=5 \
  --cpu=1 --memory=2Gi \
  --timeout=60 \
  --set-secrets=SUPABASE_DB_URL=supabase-db-url:latest
```

The image already bakes `ONNX_MODEL_DIR`, `ONNX_LIBRARY_PATH`, and
`FRONTEND_DIST` as ENV layers (see `Dockerfile` final stage), so you
only need to pass the secret. Use `--set-env-vars` to override any of
them at deploy time.

Cloud Run prints the service URL (`https://ttt-backend-xxxxx-uc.a.run.app`).
Visit it — the Go binary serves the React SPA from `frontend/dist/` and
the `/skills` JSON endpoint, same origin, no CORS needed.

> **Memory note**: `bge-small` ONNX inference + Chart-rendering query
> traffic typically fits in 1 GiB, but the *first* request after a cold
> start loads the ~130 MB model into RAM. 2 GiB gives headroom for
> bursts and avoids OOM kills during concurrent requests. Drop to 1 GiB
> only after benchmarking with realistic traffic.

### 12.6 Custom domain (optional)

```bash
gcloud beta run domain-mappings create \
  --service ttt-backend --domain trends.example.com --region "$REGION"
```

---

## 13. Operational notes

- **Supabase 7-day inactivity pause** — the free tier pauses idle projects.
  As long as the cron scraper writes daily, you stay awake.
- **Supabase 500 MB cap** — bge-small at 384-d roughly doubles capacity vs
  768-d. When you approach the cap, either prune old postings or upgrade to
  Pro ($25/mo, 8 GB).
- **Disk pressure on `/job_postings/`** — raw files grow unbounded. Either
  prune after the row is in Supabase, or compress monthly:
  ```cron
  0 3 * * 0 find /job_postings -name '*.json' -mtime +90 -delete
  ```
- **Cold start** — Cloud Run loads the ONNX model on first request after a
  scale-to-zero. For latency-sensitive demos, set `--min-instances=1` (no
  longer free).
- **Secrets** — never commit `.env`. Rotate Supabase keys quarterly and
  immediately if a key ever lands in git history.

---

## 14. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `go build` fails with `cannot find -ltokenizers` | `libtokenizers.a` not on the link path | Re-run §8.2 or `export LIBRARY_PATH=/usr/local/lib:$LIBRARY_PATH` |
| `Error loading ONNX shared library "onnxruntime.so"` | hugot defaults to a path without `lib` prefix | Set `ONNX_LIBRARY_PATH=/usr/local/lib/libonnxruntime.so` |
| `error loading onnxruntime` at server start | `libonnxruntime.so` missing or wrong arch | Re-run §8.1, confirm `ldconfig -p \| grep onnx` |
| `SUPABASE_DB_URL not set` panic | env not loaded | `set -a; source .env; set +a` before `go run` |
| Worker logs `connection refused` from Supabase | wrong DSN or paused project | Hit the SQL editor once; for ingest use the direct (5432) DSN |
| Empty bar chart, related-titles empty | Too few rows for that query, facet filter too tight | Insert more postings, or lower `matchLimit` threshold in `skills_service.go` |
| Cloud Run cold-start times out | Model load > 60s on tiny CPU | Bump `--cpu=2 --memory=2Gi`, set `--min-instances=1` |
| Python `tokenizers.Tokenizer.from_file` fails | `tokenizer.json` missing from `ONNX_MODEL_DIR` | Re-run §5 second snippet |
| Embedding parity test diverges | Different ONNX export between planes | Re-export and reuse the same files in both `optimum-cli export` and the Docker image |

---

## 15. Quick reference

```bash
# Local end-to-end
docker compose up -d rabbitmq
ollama serve &
set -a; source .env; set +a
python -m data_pipeline.llm_processor.processor &      # terminal A
python -m data_pipeline.scraper.linkedin_scraper       # terminal B
cd backend && go run .                                  # terminal C

# Cloud Run deploy
gcloud builds submit --tag "$IMAGE"
gcloud run deploy ttt-backend --image "$IMAGE" --region $REGION \
  --set-secrets=SUPABASE_DB_URL=supabase-db-url:latest \
  --set-env-vars=ONNX_MODEL_DIR=/app/models/bge-small-en-v1.5
```
