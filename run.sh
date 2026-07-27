#!/usr/bin/env bash
# Bring up the entire local dev stack: RabbitMQ + extraction worker +
# content worker + Go backend. Foreground; Ctrl-C tears down all workers
# but leaves RabbitMQ running (docker compose down to stop that too).
#
# One-shot link harvest is a separate concern: see ./harvest.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ----- CLI -----
FOLLOW="processor"   # one of: processor | content_worker | backend | frontend | all | none
VALID_FOLLOW=(processor content_worker backend frontend all none)
PURGE=0              # opt-in: --purge wipes urls_queue + job_queue at startup
SCRAPE_ONLY=0        # opt-in: --scrape-only runs ingest (content_worker +
                     # processor) without the Go backend / Vite frontend
GENERATE_PROJECTS=0  # opt-in: --generate-projects runs the one-shot
                     # recommendations catalog build, then exits

usage() {
    cat <<EOF
Usage: ./run.sh [--follow <name>] [--no-follow] [--purge] [--scrape-only]
                [--generate-projects] [--help]

Brings up RabbitMQ + extraction worker + content worker + Go backend +
Vite dev server. Stays in the foreground; Ctrl-C tears all workers down.

Options:
  --follow <name>   Stream <name>'s log file to this terminal in real time.
                    Defaults to "processor" (the LLM extractor) so you can
                    see Gemma 4 working. <name> ∈ ${VALID_FOLLOW[*]}.
                    "all" interleaves all four log files (prefixed).
                    "none" is equivalent to --no-follow.
  --no-follow       Don't tail any log file; foreground just blocks on
                    the worker PIDs (useful when run from systemd).
  --purge           Purge urls_queue + job_queue at startup. Default is
                    to keep them so a code-change restart doesn't drop
                    mid-flight messages. Use --purge for a clean slate.
  --scrape-only     Run only the ingest side: content worker + extraction
                    worker (+ RabbitMQ). Skips the Go backend and Vite
                    frontend, along with their pre-flight checks (go, npm,
                    node_modules, port binds). Use this to fill the DB from
                    scraping without standing up the serving layer.
  --generate-projects
                    One-shot: run the offline project recommendations catalog
                    build (skill-triple mining + Gemma), then exit. Does NOT
                    bring up RabbitMQ, the workers, the backend, or the
                    frontend. Needs SUPABASE_DB_DIRECT_URL set in .env and
                    Ollama running. For tuning flags, run the module directly
                    (see setup.md §11.3). Cannot be combined with --scrape-only.
  --help            Show this message and exit.

Log files always land in ./logs/<name>.log regardless of --follow.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --follow)
            [[ $# -ge 2 ]] || { echo "--follow needs a value" >&2; usage; exit 2; }
            FOLLOW="$2"; shift 2 ;;
        --follow=*) FOLLOW="${1#*=}"; shift ;;
        --no-follow) FOLLOW="none"; shift ;;
        --purge) PURGE=1; shift ;;
        --scrape-only) SCRAPE_ONLY=1; shift ;;
        --generate-projects) GENERATE_PROJECTS=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
    esac
done

# Validate --follow target.
_match=0
for v in "${VALID_FOLLOW[@]}"; do [[ "$FOLLOW" == "$v" ]] && _match=1; done
if [[ $_match -eq 0 ]]; then
    echo "unknown follow target: $FOLLOW (expected one of: ${VALID_FOLLOW[*]})" >&2
    exit 2
fi

# In --scrape-only mode the backend/frontend never launch, so their log files
# won't exist — reject a --follow that would tail a missing file.
if [[ $SCRAPE_ONLY -eq 1 && ( "$FOLLOW" == "backend" || "$FOLLOW" == "frontend" ) ]]; then
    echo "--follow $FOLLOW is invalid with --scrape-only ($FOLLOW isn't started)" >&2
    exit 2
fi

# --generate-projects is a distinct one-shot mode, not the service stack.
if [[ $GENERATE_PROJECTS -eq 1 && $SCRAPE_ONLY -eq 1 ]]; then
    echo "--generate-projects and --scrape-only are mutually exclusive" >&2
    exit 2
fi

# ----- pretty printing -----
if [[ -t 1 ]]; then
    GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; DIM=$'\e[2m'; RESET=$'\e[0m'
else
    GREEN=""; RED=""; YELLOW=""; DIM=""; RESET=""
fi
ok()   { printf "  ${GREEN}\xE2\x9C\x94${RESET} %s\n" "$*"; }
fail() { printf "  ${RED}\xE2\x9C\x97${RESET} %s\n" "$*" >&2; exit 1; }
note() { printf "  ${DIM}%s${RESET}\n" "$*"; }
hdr()  { printf "\n${YELLOW}== %s ==${RESET}\n" "$*"; }

# ----- python venv -----
# Activate the project virtualenv so PATH + VIRTUAL_ENV point at it for this
# shell and every child process (workers, harvest subprocesses, a bare
# `python`/`scrapy`). We still call "$PYBIN" explicitly below for robustness;
# activation just makes the venv the default for anything that doesn't.
hdr "python venv"
VENV_ACTIVATE="$REPO_ROOT/.venv/bin/activate"
[[ -f "$VENV_ACTIVATE" ]] \
    || fail "$VENV_ACTIVATE not found (python -m venv .venv && pip install -r requirements.txt)"
# The activate script reads a few vars (PS1, PYTHONHOME) that `set -u` would
# flag as unbound; relax nounset just around the source.
set +u
# shellcheck disable=SC1091
source "$VENV_ACTIVATE"
set -u
PYBIN="$REPO_ROOT/.venv/bin/python"
ok "venv activated ($VIRTUAL_ENV)"

# ----- one-shot: project recommendations catalog -----
# --generate-projects is a batch mode, not part of the service stack. It runs
# the offline recommendations build (skill-triple mining + Gemma) and exits;
# it never brings up RabbitMQ, the workers, the backend, or the frontend, so
# it needs only Python, Ollama, and the direct-connection DSN.
if [[ $GENERATE_PROJECTS -eq 1 ]]; then
    hdr "pre-flight (generate-projects)"

    [[ -f "$REPO_ROOT/.env" ]] || fail ".env missing at $REPO_ROOT/.env (cp .env.example .env)"
    ok ".env present"
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a

    [[ -n "${SUPABASE_DB_DIRECT_URL:-}" ]] \
        || fail "SUPABASE_DB_DIRECT_URL empty in .env (direct 5432 DSN; see setup.md §11.3)"
    [[ -n "${LLM_MODEL:-}" ]] || fail "LLM_MODEL empty in .env"
    ok "SUPABASE_DB_DIRECT_URL + LLM_MODEL set"

    curl -fsS --max-time 2 http://localhost:11434/api/tags >/dev/null \
        || fail "ollama not reachable on :11434 (sudo systemctl start ollama)"
    ok "ollama reachable"

    hdr "generate projects"
    note "running data_pipeline.recommendations.build_catalog (Ctrl-C to abort)"
    # exec: replace this shell with the batch job so its exit status is ours
    # and no service-stack trap/cleanup is installed.
    exec "$PYBIN" -m data_pipeline.recommendations.build_catalog
fi

# ----- pre-flight -----
hdr "pre-flight"

[[ -f "$REPO_ROOT/.env" ]] || fail ".env missing at $REPO_ROOT/.env (cp .env.example .env)"
ok ".env present"

# Source .env so subsequent checks see the values
set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a

require_var() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then fail "$name is empty in .env"; fi
}
for v in SUPABASE_DB_URL ONNX_MODEL_DIR ONNX_LIBRARY_PATH JOB_POSTINGS_DIR RABBITMQ_HOST LLM_MODEL; do
    require_var "$v"
done
ok "required env vars set"

[[ -f "$ONNX_MODEL_DIR/model.onnx" ]]     || fail "missing $ONNX_MODEL_DIR/model.onnx (see setup.md §5)"
[[ -f "$ONNX_MODEL_DIR/tokenizer.json" ]] || fail "missing $ONNX_MODEL_DIR/tokenizer.json"
[[ -f "$ONNX_LIBRARY_PATH" ]]             || fail "missing $ONNX_LIBRARY_PATH (see setup.md §8.1)"
ok "ONNX model + library on disk"

if [[ $SCRAPE_ONLY -eq 0 ]]; then
    command -v go  >/dev/null 2>&1 || fail "go not on PATH"
    command -v npm >/dev/null 2>&1 || fail "npm not on PATH (install Node.js >= 20)"
    [[ -d "$REPO_ROOT/frontend/node_modules" ]] \
        || fail "frontend/node_modules missing (cd frontend && npm install)"
    ok "go + npm available"
else
    note "scrape-only: skipping go + npm checks"
fi

docker info >/dev/null 2>&1 || fail "docker daemon not reachable"
ok "docker daemon reachable"

curl -fsS --max-time 2 http://localhost:11434/api/tags >/dev/null \
    || fail "ollama not reachable on :11434 (sudo systemctl start ollama)"
ok "ollama reachable"

# Ports must be free up front. A leftover backend/frontend from a previous run
# (e.g. a go-run orphan still bound to :8080) makes the new service fail to
# bind; because the foreground blocks on `wait -n`, that immediate exit tears
# the whole stack down — the "run.sh stops on its own" symptom. Fail loud here.
if [[ $SCRAPE_ONLY -eq 0 ]]; then
    for port in "${PORT:-8080}" 5173; do
        if ss -ltn "sport = :$port" 2>/dev/null | grep -q ":$port\b"; then
            fail "port $port already in use (leftover from a previous run?) — free it with: fuser -k $port/tcp"
        fi
    done
    ok "ports ${PORT:-8080} + 5173 free"
else
    note "scrape-only: no ports bound (backend + frontend skipped)"
fi

# ----- bring up RabbitMQ -----
hdr "rabbitmq"
docker compose up -d rabbitmq >/dev/null
ok "compose: rabbitmq up"

# Wait for broker readiness; rabbitmq-diagnostics returns 0 when alive.
note "waiting for broker..."
for i in {1..60}; do
    if docker exec rabbitmq rabbitmq-diagnostics -q check_running >/dev/null 2>&1; then
        ok "rabbitmq ready"
        break
    fi
    sleep 1
    [[ $i -eq 60 ]] && fail "rabbitmq did not become ready within 60s"
done

# Opt-in queue purge. Default: leave whatever's mid-flight so a code-change
# restart doesn't drop already-scraped URLs or pending postings. Pass
# --purge for a clean-slate start. Errors swallowed (queues may not exist
# yet on a fresh broker).
if [[ $PURGE -eq 1 ]]; then
    docker exec rabbitmq rabbitmqctl -q purge_queue urls_queue 2>/dev/null || true
    docker exec rabbitmq rabbitmqctl -q purge_queue job_queue  2>/dev/null || true
    ok "queues purged (urls_queue, job_queue)"
else
    # Report current depth so the user knows what's about to resume.
    depths=$(docker exec rabbitmq rabbitmqctl -q list_queues name messages 2>/dev/null \
             | awk '$1=="urls_queue" || $1=="job_queue" {printf "%s=%s ", $1, $2}')
    note "queues preserved (${depths:-empty}; pass --purge to wipe)"
fi

# ----- launch services -----
hdr "services"
mkdir -p logs

declare -A PIDS=()

launch() {
    local name="$1"; shift
    local log="logs/$name.log"
    : >"$log"
    ("$@" >"$log" 2>&1) &
    PIDS[$name]=$!
    ok "$name pid=${PIDS[$name]} log=$log"
}

launch processor      "$PYBIN" -m data_pipeline.llm_processor.processor
launch content_worker "$PYBIN" -m data_pipeline.scraper.content_worker
if [[ $SCRAPE_ONLY -eq 0 ]]; then
    launch backend        bash -c "cd backend && go build -tags onnx -o ./.bin/server . && exec ./.bin/server"
    launch frontend       bash -c "cd frontend && npm run dev -- --host 0.0.0.0"
fi

# ----- trap & wait -----
SHUTTING_DOWN=0
_shutdown() {
    [[ $SHUTTING_DOWN -eq 1 ]] && return
    SHUTTING_DOWN=1
    hdr "shutdown"
    for name in "${!PIDS[@]}"; do
        local pid="${PIDS[$name]}"
        if kill -0 "$pid" 2>/dev/null; then
            note "SIGTERM $name ($pid)"
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    # Give them 10s to exit cleanly, then SIGKILL the survivors.
    for _ in {1..10}; do
        local any_alive=0
        for pid in "${PIDS[@]}"; do
            kill -0 "$pid" 2>/dev/null && any_alive=1
        done
        [[ $any_alive -eq 0 ]] && break
        sleep 1
    done
    for name in "${!PIDS[@]}"; do
        local pid="${PIDS[$name]}"
        if kill -0 "$pid" 2>/dev/null; then
            note "SIGKILL $name ($pid)"
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done
    note "rabbitmq left running (docker compose down to stop it)"
}
trap _shutdown INT TERM EXIT

hdr "stack up"
if [[ $SCRAPE_ONLY -eq 0 ]]; then
    printf "  frontend: http://localhost:5173   (Vite dev; open this one)\n"
    printf "  backend:  http://localhost:%s   (Go JSON API)\n" "${PORT:-8080}"
else
    printf "  scrape-only: content_worker + processor  (no backend/frontend)\n"
fi
printf "  logs:     tail -f %s/logs/*.log\n" "$REPO_ROOT"
printf "  follow:   %s  (--follow <name> | --no-follow to change)\n" "$FOLLOW"
printf "  queues:   %s  (--purge to wipe at startup)\n" "$([[ $PURGE -eq 1 ]] && echo purged || echo preserved)"
printf "  stop:     Ctrl-C\n\n"

# ----- foreground live tail -----
# Stream the chosen log to this terminal so the user can see the worker
# working in real time. tail is a child like everything else, so the
# shutdown trap reaps it too. wait -n then blocks on the whole group.
if [[ "$FOLLOW" != "none" ]]; then
    if [[ "$FOLLOW" == "all" ]]; then
        if [[ $SCRAPE_ONLY -eq 0 ]]; then
            tail -F logs/processor.log logs/content_worker.log logs/backend.log logs/frontend.log &
        else
            tail -F logs/processor.log logs/content_worker.log &
        fi
    else
        tail -F "logs/${FOLLOW}.log" &
    fi
    PIDS[tail]=$!
fi

# Wait on any child. If one dies on its own (crash), tear the rest down.
wait -n
exit $?
