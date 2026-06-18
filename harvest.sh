#!/usr/bin/env bash
# One-shot LinkedIn link harvest. Publishes URLs to RabbitMQ urls_queue;
# the content_worker (started by ./run.sh) consumes them.
# Safe to schedule via cron:
#   0 2 * * * /path/to/TechTrendTracker/harvest.sh >> /var/log/ttt/harvest.log 2>&1

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

[[ -f "$REPO_ROOT/.env" ]] || { echo ".env missing at $REPO_ROOT/.env" >&2; exit 1; }

set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a

: "${RABBITMQ_HOST:?RABBITMQ_HOST not set in .env}"
: "${JOB_POSTINGS_DIR:?JOB_POSTINGS_DIR not set in .env}"

# Friendly warning if the broker isn't up. The spider will still try and
# fail; the message is just clearer this way.
if ! docker exec rabbitmq rabbitmq-diagnostics -q check_running >/dev/null 2>&1; then
    echo "WARNING: RabbitMQ not running (./run.sh starts it). Spider will fail on connect." >&2
fi

PYBIN="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYBIN" ]] || { echo "$PYBIN not found" >&2; exit 1; }

exec "$PYBIN" -m data_pipeline.scraper.linkedin
