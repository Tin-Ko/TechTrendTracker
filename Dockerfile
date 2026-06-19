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
# Stage 1: fetch the pre-converted ONNX of bge-small-en-v1.5 from HF Hub.
#
# We used to run `optimum-cli export onnx` here, but that chain (torch +
# optimum) keeps growing new dynamo-exporter dependencies (onnxscript,
# onnx_ir, ...) and unconditionally pulls in ~1.5 GiB of NVIDIA CUDA
# wheels we don't need.  Xenova's port hosts the same BAAI weights
# already in ONNX form — three curl calls, no Python, ~10s.
#
# Local dev does the same fetch (setup.md §5).  Both planes share the
# same artifact, which is what our embedding-parity test requires.
# ============================================================================
FROM debian:bookworm-slim AS model_export

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

ARG HF_REPO=Xenova/bge-small-en-v1.5
ARG HF_BASE=https://huggingface.co/${HF_REPO}/resolve/main
ARG MODEL_DIR=/out/models/bge-small-en-v1.5

RUN mkdir -p ${MODEL_DIR} \
 && curl -fsSL -o ${MODEL_DIR}/model.onnx       ${HF_BASE}/onnx/model.onnx \
 && curl -fsSL -o ${MODEL_DIR}/tokenizer.json   ${HF_BASE}/tokenizer.json \
 && curl -fsSL -o ${MODEL_DIR}/config.json      ${HF_BASE}/config.json \
 && test -f ${MODEL_DIR}/model.onnx \
 && test -f ${MODEL_DIR}/tokenizer.json

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
