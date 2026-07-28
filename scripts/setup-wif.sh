#!/usr/bin/env bash
# One-time setup of Workload Identity Federation (WIF) so GitHub Actions can
# deploy TechTrendTracker to Cloud Run WITHOUT a stored service-account key.
#
# Run ONCE, authenticated as a project owner/admin (local gcloud or Cloud Shell):
#   gcloud auth login            # if not already logged in
#   ./scripts/setup-wif.sh
#
# Idempotent — safe to re-run. Prints the two (NON-secret) values the deploy
# workflow needs at the end. Nothing here is a credential; it only configures
# GCP to trust GitHub OIDC tokens coming from this specific repo.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-techtrendtracker-499821}"
REPO="${REPO:-Tin-Ko/TechTrendTracker}"        # owner/repo the Actions run in
POOL_ID="${POOL_ID:-github-pool}"
PROVIDER_ID="${PROVIDER_ID:-github-provider}"
SA_NAME="${SA_NAME:-github-deployer}"

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

echo "== enabling APIs (no-op if already enabled) =="
gcloud services enable \
  iamcredentials.googleapis.com sts.googleapis.com \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

echo "== deployer service account =="
if ! gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA_NAME" --display-name="GitHub Actions deployer"
fi

echo "== granting deploy roles to $SA_EMAIL =="
# run.admin: deploy Cloud Run.  cloudbuild.builds.editor: `gcloud builds submit`.
# artifactregistry.writer: push the image.  iam.serviceAccountUser: act as the
# Cloud Run runtime SA during deploy (project-scoped here for simplicity; see the
# hardening note in the plan to scope it to just the runtime SA).
for ROLE in roles/run.admin roles/cloudbuild.builds.editor \
            roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" --role="$ROLE" --condition=None >/dev/null
done

echo "== workload identity pool =="
if ! gcloud iam workload-identity-pools describe "$POOL_ID" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL_ID" \
    --location=global --display-name="GitHub Actions pool"
fi

echo "== OIDC provider (pinned to ${REPO}) =="
# The attribute-condition is the security boundary: only tokens whose
# `repository` claim equals your repo can use this provider. Without it, ANY
# GitHub repo could authenticate.
if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
      --location=global --workload-identity-pool="$POOL_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --location=global --workload-identity-pool="$POOL_ID" \
    --display-name="GitHub provider" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${REPO}'"
fi

POOL_NAME="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}"

echo "== allow ${REPO} to impersonate ${SA_EMAIL} =="
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository/${REPO}" >/dev/null

cat <<EOF

============================================================================
Done. Set these NON-secret values as GitHub repo *variables*
(Settings -> Secrets and variables -> Actions -> Variables tab):

  GCP_WIF_PROVIDER = ${POOL_NAME}/providers/${PROVIDER_ID}
  GCP_DEPLOY_SA    = ${SA_EMAIL}

The deploy workflow reads them via \${{ vars.GCP_WIF_PROVIDER }} /
\${{ vars.GCP_DEPLOY_SA }}. No JSON key is stored anywhere.
============================================================================
EOF
