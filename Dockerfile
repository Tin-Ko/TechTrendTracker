# syntax=docker/dockerfile:1.6
#
# Multi-stage build for the TTT Cloud Run image. Builds:
#   1. ONNX export of bge-small-en-v1.5 (replaces having models/ in git)
#   2. Vite + React frontend bundle
#   3. Go backend with cgo deps (ONNX Runtime, libtokenizers)
#   4. Slim runtime image that combines everything
#
# Build context = repo root.
#   gcloud builds submit --tag <image>
#   # or
#   docker build -t ttt-backend .

# ============================================================================
# Stage 1: export bge-small-en-v1.5 to ONNX
# Deterministic given the pinned upstream model + optimum/transformers versions.
# Heavy (~3 min on Cloud Build) but Docker caches the layer — only re-runs
# when one of these RUNs actually changes.
# ============================================================================
FROM python:3.12-slim AS model_export

RUN pip install --no-cache-dir \
        "optimum[exporters]==1.24.0" \
        "transformers==4.46.3"

RUN optimum-cli export onnx \
        --model BAAI/bge-small-en-v1.5 \
        --task feature-extraction \
        /out/models/bge-small-en-v1.5 \
 && test -f /out/models/bge-small-en-v1.5/model.onnx \
 && test -f /out/models/bge-small-en-v1.5/tokenizer.json

# ============================================================================
# Stage 2: build the Vite + React frontend
# ============================================================================
FROM node:20-bookworm-slim AS frontend

WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Output lands at /src/dist (from vite.config.ts build.outDir).

# ============================================================================
# Stage 3: build the Go backend with cgo (hugot → ONNX Runtime + libtokenizers)
# ============================================================================
FROM golang:1.24-bookworm AS backend

ARG ORT_VERSION=1.20.0
ARG TOK_VERSION=1.20.2

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl build-essential \
 && rm -rf /var/lib/apt/lists/*

# ONNX Runtime shared library
RUN curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
      | tar -xz --strip-components=1 -C /usr/local \
 && ldconfig

# daulet/tokenizers static lib (link-time dep for hugot)
RUN curl -fsSL "https://github.com/daulet/tokenizers/releases/download/v${TOK_VERSION}/libtokenizers.linux-amd64.tar.gz" \
      | tar -xz -C /usr/local/lib

WORKDIR /src
COPY backend/go.mod backend/go.sum ./
RUN go mod download
COPY backend/ ./

ENV CGO_ENABLED=1
RUN go build -trimpath -ldflags="-s -w" -o /out/server .

# ============================================================================
# Stage 4: slim runtime
# ============================================================================
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# ONNX Runtime shared library so hugot can load it at startup.
COPY --from=backend /usr/local/lib/libonnxruntime.so* /usr/local/lib/
RUN ldconfig

WORKDIR /app
COPY --from=backend      /out/server                              /app/server
COPY --from=frontend     /src/dist                                /app/frontend/dist
COPY --from=model_export /out/models/bge-small-en-v1.5            /app/models/bge-small-en-v1.5

# hugot defaults to looking up "onnxruntime.so" (no lib prefix); point it
# explicitly. The other vars match Cloud Run conventions.
ENV ONNX_MODEL_DIR=/app/models/bge-small-en-v1.5
ENV ONNX_LIBRARY_PATH=/usr/local/lib/libonnxruntime.so
ENV FRONTEND_DIST=/app/frontend/dist
ENV PORT=8080

EXPOSE 8080
CMD ["/app/server"]
