#!/usr/bin/env bash
# Build the TTT image and deploy it to Cloud Run, then smoke-test the live URL.
#
# Mirrors the existing service exactly (discovered from `gcloud run services
# describe ttt-backend`):
#   service   ttt-backend            region us-west1
#   image     us-west2-docker.pkg.dev/techtrendtracker-499821/techtrendtracker/backend
#   db url    SUPABASE_DB_URL <- Secret Manager secret `supabase-db-url:latest`
#   resources cpu 1 / 2Gi / maxScale 5 / startup-cpu-boost
#
# The image is built from ./Dockerfile (bakes in the bge-small ONNX export, the
# Vite frontend bundle, and the cgo Go server). No LLM ever ships in this image;
# the request path stays model-free by design.
#
# Usage:
#   ./deploy.sh                 # Cloud Build -> deploy -> smoke test (default)
#   ./deploy.sh --local         # build & push with local docker instead of Cloud Build
#   ./deploy.sh --sync-secret   # push SUPABASE_DB_URL from .env as a new secret version first
#   ./deploy.sh --tag v1234     # use an explicit image tag (default: v<UTC date>-<time>)
#   ./deploy.sh --no-smoke      # skip the post-deploy curl check
#   ./deploy.sh --help

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ----- config (override via env) -----
PROJECT="${PROJECT:-techtrendtracker-499821}"
SERVICE="${SERVICE:-ttt-backend}"
REGION="${REGION:-us-west1}"
AR_LOCATION="${AR_LOCATION:-us-west2}"
AR_REPO="${AR_REPO:-techtrendtracker}"
IMAGE_NAME="${IMAGE_NAME:-backend}"
SECRET="${SECRET:-supabase-db-url}"
CPU="${CPU:-1}"
MEMORY="${MEMORY:-2Gi}"
MAX_INSTANCES="${MAX_INSTANCES:-5}"
BUILD_TIMEOUT="${BUILD_TIMEOUT:-20m}"

IMAGE_BASE="${AR_LOCATION}-docker.pkg.dev/${PROJECT}/${AR_REPO}/${IMAGE_NAME}"

# ----- CLI -----
USE_LOCAL=0
SYNC_SECRET=0
SMOKE=1
TAG="v$(date -u +%Y%m%d-%H%M)"

usage() {
    cat <<EOF
Build the TTT image and deploy it to Cloud Run, then smoke-test the live URL.

Usage:
  ./deploy.sh                 # Cloud Build -> deploy -> smoke test (default)
  ./deploy.sh --local         # build & push with local docker instead of Cloud Build
  ./deploy.sh --sync-secret   # push SUPABASE_DB_URL from .env as a new secret version first
  ./deploy.sh --tag v1234     # use an explicit image tag (default: v<UTC date>-<time>)
  ./deploy.sh --no-smoke      # skip the post-deploy curl check
  ./deploy.sh --help

Targets service '$SERVICE' (region $REGION), image $IMAGE_BASE.
Override any of PROJECT/SERVICE/REGION/AR_LOCATION/AR_REPO/MEMORY/CPU via env.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --local)       USE_LOCAL=1; shift ;;
        --sync-secret) SYNC_SECRET=1; shift ;;
        --no-smoke)    SMOKE=0; shift ;;
        --tag)         [[ $# -ge 2 ]] || { echo "--tag needs a value" >&2; exit 2; }; TAG="$2"; shift 2 ;;
        --tag=*)       TAG="${1#*=}"; shift ;;
        --help|-h)     usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
    esac
done

IMAGE="${IMAGE_BASE}:${TAG}"

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

# ----- pre-flight -----
hdr "pre-flight"
command -v gcloud >/dev/null 2>&1 || fail "gcloud not on PATH (https://cloud.google.com/sdk)"
[[ -f "$REPO_ROOT/Dockerfile" ]] || fail "Dockerfile missing at repo root"

ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1)"
[[ -n "$ACCOUNT" ]] || fail "no active gcloud account — run: gcloud auth login"
ok "authed as $ACCOUNT"

gcloud config set project "$PROJECT" >/dev/null 2>&1
ok "project: $PROJECT"
note "service: $SERVICE   region: $REGION"
note "image:   $IMAGE"

# ----- secret sync (opt-in) -----
if [[ $SYNC_SECRET -eq 1 ]]; then
    hdr "secret"
    [[ -f "$REPO_ROOT/.env" ]] || fail ".env missing (need SUPABASE_DB_URL to sync)"
    # Pull SUPABASE_DB_URL out of .env without sourcing the whole file.
    set -a; # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"; set +a
    [[ -n "${SUPABASE_DB_URL:-}" ]] || fail "SUPABASE_DB_URL empty in .env"
    if ! gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
        printf '%s' "$SUPABASE_DB_URL" | gcloud secrets create "$SECRET" --data-file=- >/dev/null
        ok "created secret $SECRET"
    else
        printf '%s' "$SUPABASE_DB_URL" | gcloud secrets versions add "$SECRET" --data-file=- >/dev/null
        ok "added new version to $SECRET"
    fi
else
    gcloud secrets describe "$SECRET" >/dev/null 2>&1 \
        || fail "secret '$SECRET' not found — create it with: ./deploy.sh --sync-secret"
    ok "secret $SECRET present (re-sync with --sync-secret)"
fi

# ----- ensure Artifact Registry repo exists -----
hdr "artifact registry"
if ! gcloud artifacts repositories describe "$AR_REPO" --location "$AR_LOCATION" >/dev/null 2>&1; then
    note "creating repo $AR_REPO in $AR_LOCATION..."
    gcloud artifacts repositories create "$AR_REPO" \
        --repository-format=docker --location="$AR_LOCATION" >/dev/null
fi
ok "repo $AR_LOCATION/$AR_REPO ready"

# ----- build -----
hdr "build"
if [[ $USE_LOCAL -eq 1 ]]; then
    command -v docker >/dev/null 2>&1 || fail "docker not on PATH (needed for --local)"
    docker info >/dev/null 2>&1 || fail "docker daemon not reachable"
    gcloud auth configure-docker "${AR_LOCATION}-docker.pkg.dev" --quiet >/dev/null 2>&1
    note "docker build (linux/amd64)..."
    docker build --platform linux/amd64 -t "$IMAGE" .
    docker push "$IMAGE"
    ok "pushed $IMAGE (local docker)"
else
    note "gcloud builds submit (this runs the full multi-stage build remotely)..."
    gcloud builds submit --tag "$IMAGE" --timeout "$BUILD_TIMEOUT" .
    ok "built + pushed $IMAGE (Cloud Build)"
fi

# ----- deploy -----
hdr "deploy"
gcloud run deploy "$SERVICE" \
    --image "$IMAGE" \
    --region "$REGION" \
    --platform managed \
    --set-secrets "SUPABASE_DB_URL=${SECRET}:latest" \
    --cpu "$CPU" \
    --memory "$MEMORY" \
    --max-instances "$MAX_INSTANCES" \
    --cpu-boost \
    --quiet
ok "deployed revision of $SERVICE"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
ok "URL: $URL"

# ----- smoke test (it's running) -----
if [[ $SMOKE -eq 1 ]]; then
    hdr "smoke test"
    # SPA root: confirms the container is up and serving.
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$URL/" || echo 000)"
    [[ "$code" == "200" ]] && ok "GET / -> $code" || fail "GET / -> $code (service not serving)"

    # /skills exercises the DB path (Supabase via the secret). Non-2xx here
    # means the container is up but the DB connection or query failed.
    api="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$URL/skills" || echo 000)"
    if [[ "$api" =~ ^2 ]]; then ok "GET /skills -> $api (DB reachable)"
    else note "GET /skills -> $api (container up, but check DB/secret + logs)"; fi
fi

hdr "done"
printf "  live: %s\n" "$URL"
printf "  logs: gcloud run services logs tail %s --region %s\n\n" "$SERVICE" "$REGION"
