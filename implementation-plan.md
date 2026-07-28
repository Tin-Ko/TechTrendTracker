# Implementation Plan — CI/CD Pipeline (GitHub Actions)

This plan takes TechTrendTracker from "tests exist but nothing runs them" (design
doc §11) to an automated pipeline: **unit + parity checks on every PR**,
**model/DB integration checks on the machine that has the models**, and
**tag-triggered deploy to Cloud Run** wrapping the existing `deploy.sh`.

A prerequisite refactor (Option C on `processor.py`) comes first, because a CI
job is only worth having if there's something model-free to run in it.

---

## Status legend

- `[ ]` not started `[~]` in progress `[x]` done
- Update the checkbox **and** the per-phase status line as work lands.

## Progress summary

| Phase | Title | Status |
|---|---|---|
| 0 | Test foundation (pytest + Go conventions) | `[~]` toolchains installed, pytest+ruff+go vet verified; testify + stub split deferred to Phase 2 |
| 1 | Refactor `processor.py` for testability (Option C) | `[x]` done — seam extracted, model-free unit tests green |
| 2 | CI — pull-request checks (no models, no infra) | `[~]` stub split done, `ci.yml` authored+validated; needs a real PR run |
| 3 | CD — build & deploy to Cloud Run | `[~]` deploy.yml + WIF authored; verifies on first push to main |
| 4 | Integration & golden-query gates (model machine) | `[ ]` not started |
| 5 | Hardening & nice-to-haves | `[ ]` not started |

---

## Decisions baked in (rationale)

These were reasoned through already — recorded here so the "why" survives.

- **Python runner: pytest** (keeps existing `unittest.TestCase` tests running
  unchanged; adds markers + parametrize). The zero-risk migration is the reason.
- **Go: stdlib `testing`, table-driven**, with `testify/require` only in the
  DB/service tests where fail-fast assertions read cleaner. Parity test stays
  pure stdlib (a lock should have no droppable deps).
- **Boundary discipline:** model calls (Ollama, ONNX) sit behind seams and are
  never constructed inside a unit test. Enforced by markers (Python) and build
  tags (Go), not by memory.

## ⚠️ Open decisions — using recommended defaults, confirm or override

| # | Decision | Default in this plan | Alternative |
|---|---|---|---|
| D1 | Deploy trigger | **Tag-triggered delivery** (`v*` tag → deploy) | Auto-deploy every merge to `main` |
| D2 | Go tests + cgo/ONNX in CI | **✅ CONFIRMED 2b-stub** — split `embed_service.go` behind `//go:build onnx` + a `!onnx` stub; CI runs model-free | 2a install ONNX in CI / 2c test inside the Docker image |
| D3 | GCP auth from Actions | **Workload Identity Federation** (keyless) | Service-account JSON key in a repo secret |

If you want any of these flipped, say so before Phase 2/3 — they change the
workflow files, not the earlier phases.

**D2 correction (found in Phase 0).** `backend/services/embed_service.go` imports
`hugot` at *package* level, and Go compiles a package as a unit — so `go test
./backend/services/` links ONNX/tokenizers no matter which test file runs. A build
tag on *test files alone* therefore does **not** buy a model-free `go test`. To get
2b you must split the production source:
- `embed_service.go` → `//go:build onnx` (real hugot implementation)
- new `embed_service_stub.go` → `//go:build !onnx` (same exported symbols —
  `InitEmbedService`, `EmbedQuery`, etc. — returning an error / panicking if
  called "built without onnx")
- Docker/production build adds `-tags onnx`; CI and bare `go build`/`go test` use
  the stub → no cgo, no ONNX, no tokenizers.

This is still 2b, just with a stub file instead of a one-line tag. The alternative
is **2a** (install onnxruntime 1.20 + build `libtokenizers` in CI so the real
package compiles) — no source change, but slower/heavier CI. **Confirm 2b-stub vs
2a before Phase 2.**

**Empirical confirmation (Phase 0, this machine, no native libs):**
- `go vet ./...` → passes (no linker invoked).
- `go build ./services` → passes — a *library* compile emits an archive, no link,
  so the missing `-ltokenizers` never surfaces.
- `go build .` (main) and **`go test ./services/`** → **fail at link**:
  `ld: library 'tokenizers' not found`. `go test` builds a test *binary* and links
  it, dragging in `embed_service.go`'s cgo.
- Every Go test currently lives in `package services`, so **zero Go tests can run
  today** without 2a or 2b. `go vet` is the only Go check CI can do unchanged.

---

## Phase 0 — Test foundation

*Goal: make `pytest -m "not integration"` and `go test ./...` both run green on a
machine with no Ollama, no ONNX, no RabbitMQ, no DB.*

Status: `[~]` toolchains installed & baseline verified on this machine. Two items
intentionally deferred to Phase 2 (testify, stub split) — reasons inline.

**Environment note (this machine, 2026-07-25 → resolved).** Started with no Go and
only Python 3.9.6 (code needs 3.10+; PEP 604 unions fail to import on 3.9).
Installed via Homebrew: **Go 1.26.5** and **Python 3.12.13**. Created `.venv`
(3.12, gitignored) with `requirements-dev.txt` + `requirements.txt`. Note: the
model *libraries* (`ollama`, `onnxruntime`) install fine and import without a
running daemon/model — only tests that *invoke* a model need the real thing.

- [x] Add `requirements-dev.txt`: `pytest`, `pytest-cov`, `pytest-mock`, `ruff`.
- [x] Add `pyproject.toml` with markers, `addopts = "-m 'not integration'"`,
      `testpaths`, and `pythonpath = ["."]`.
- [x] Add `ruff` config (lenient: `E,W,F,I`, ignore `E501`).
- [x] Install Go + Python 3.12 (Homebrew), create `.venv`, install deps.
- [x] **Verified** `pytest -m "not integration"` runs. **Baseline: 5 passed,
      8 skipped, 3 failed, 1 collection error** — see findings below.
- [x] **Verified** `go vet ./...` passes today (no link step, no native libs).
- [x] **Verified** the D2 constraint empirically (see D2 correction below).
- [x] `ruff check .` baseline: **56 findings, 54 auto-fixable** (unused imports +
      import order). Triage deferred — do NOT mass-`--fix` (one is the intentional
      stub import in `test_title_normalizer`).
- [ ] **[Phase 2]** `go get github.com/stretchr/testify` — deferred: with nothing
      importing it yet, `go mod tidy` would strip it. Add it with the first test
      that imports `require`.
- [ ] **[Phase 2]** The `//go:build onnx` stub split (D2). Add a `setup.md` note
      once implemented.

**Phase 0 findings (surfaced by standing up the runner — triage separately):**
1. **3 real bugs in `requirements_parser`.** `normalize_skill("Python!!")` →
   `"python"` not `"Python"`: the punctuation strip runs *after* the
   capitalization-map lookup, so `"python!!"` never matches key `"python"`. Fix =
   strip punctuation *before* the map lookups (still keeps `C++`/`C#` since the
   strip regex preserves `+`/`#`). The 2 `clean_extracted_data` failures call the
   same method → same root cause. **Owner: you (normalization logic).**
2. **`test_extractor` collection error.** `extractor.py` does a module-level
   `from ...config import LLM_API_KEY` for the **unused** DeepSeek path;
   `config.py` is gitignored (§11 predicts this). Decouple in Phase 1 (make the
   import lazy) rather than adding a dummy secrets file.
3. **Import-time coupling is systemic.** `extractor.py` / `title_normalizer.py`
   do module-level `import ollama`; `processor.py` does I/O in `__init__`. All
   three block unit collection/instantiation without heavy deps — exactly what
   Phase 1's seam work removes.

## Phase 1 — Refactor `processor.py` for testability (Option C)

*Goal: separate the per-job pipeline (pure transform) from the RabbitMQ worker
(messaging glue) so the pipeline is unit-testable with fakes and constructs no
infra.*

Status: `[x]` done. Seam is `pipeline.build_posting`; **decision (ii)** applied —
the transform builds a `Posting` value and the worker persists it, so unit tests
construct nothing infrastructural.

- [x] Extracted the transform into `data_pipeline/llm_processor/pipeline.py`:
      `build_posting(job_data, *, extractor, normalizer, embedder) -> Posting`.
      Collaborators typed as **Protocols** so `pipeline.py` imports no heavy deps
      (verified: imports clean with ollama/onnx/psycopg/pika all hidden). DB insert
      stays OUT of the transform (decision ii).
- [x] `Processor` is now a thin worker: DI constructor (no I/O), a `build_default()`
      composition root that wires the real collaborators, and `process_job` =
      `build_posting(...)` then `db.insert_posting(**asdict(posting))`.
- [x] `pika.BlockingConnection` moved out of `__init__` into `connect()`.
      **Verified:** a `Processor` built with fakes has `connection is None` and
      runs `process_job` end-to-end with no broker/model/DB.
- [x] `tests/llm_processor/test_pipeline.py` — 9 model-free unit tests (field
      mapping, extractor/embedder wiring, deterministic uuid5 vs random id,
      content_hash, empty/missing fields). All green.
- [x] Findings fixed in the same pass: **#2** dead `openai`/`config` imports moved
      into the unused cloud method (module now imports without `config.py`); **#3**
      `processor.__init__` I/O removed. Rewrote the stale `test_extractor.py`
      (tested a removed OpenAI API) against the current Ollama path, guarded by
      `pytest.importorskip("ollama")` so it skips where the client lib is absent.
- [x] Sanity: `pytest -m "not integration"` → **17 passed, 8 skipped, 3 failed**.
      The 3 failures are the pre-existing `requirements_parser` bugs (finding #1,
      your call) — unrelated to this refactor.

**Note on "lazy imports":** did NOT lazy-import `ollama` inside `extractor.py`/
`title_normalizer.py` — those modules *are* the model adapters, so a top-level
`import ollama` is honest. The real decoupling is that the pure `pipeline.py`
never imports them (Protocols). Only the genuinely dead `openai`/`config` code
was made lazy. `title_normalizer.py` still imports `ollama` at top; its tests
already self-skip (stubbed §8) and will get a `importorskip` guard in Phase 2 so
the dev-deps-only CI job collects cleanly.

## Phase 2 — CI: pull-request checks

*Goal: one workflow, path-filtered parallel jobs, all model-free and infra-free.
This is the everyday gate.*

Status: `[~]` D2 stub split done + `ci.yml` authored & locally validated. Remaining:
verify on a real PR, facet-parity fixture, coverage flag.

**D2 stub split (done, verified on this machine):**
- [x] Split `embed_service.go` → pure shared (`EmbeddingDim`, `normalizeQuery`,
      `VectorLiteral`) + `embed_service_onnx.go` (`//go:build onnx`, real hugot) +
      `embed_service_stub.go` (`//go:build !onnx`, no-op returning `errNoONNX`).
- [x] Added `-tags onnx` to the two real build sites: `Dockerfile` and `run.sh`
      (production/local dev need the real embedder; default build is the stub).
- [x] Verified: default build `go vet ./...`, `go build ./...`, `go test ./...`
      all pass with **no native libs** (`go test ./services` → `ok`, was link-fail).
      `go vet -tags onnx ./...` type-checks the real impl too (catches drift).
- [x] Removed the unused `import ollama` from `title_normalizer.py` (it was only
      referenced in comments) so the parity tests collect without Ollama — better
      than an importorskip guard, which would have disabled the parity lock in CI.

**`ci.yml` (authored, YAML-valid, 3 jobs):**
- [x] `.github/workflows/ci.yml`, triggers `pull_request` + push to `main`.
- [x] **python** job: `pip install -r requirements-dev.txt` → `ruff check`
      (`continue-on-error` until the 56-finding backlog is triaged) →
      `pytest -m "not integration"`. Verified locally with all runtime libs
      hidden: **collects cleanly, 14 pass / 9 skip / 3 fail** (the 3 = finding #1).
- [x] **go** job: `go vet ./...` → `go vet -tags onnx ./...` → `go build ./...`
      → `go test ./...` (default/stub — no ONNX link).
- [x] **frontend** job: `npm install` → `npm run typecheck` → `npm run build`.
      (unverified locally — no Node on this machine; first real run is in CI.)
- [x] Caching: pip (`setup-python`) + Go modules (`setup-go`) enabled. npm cache
      omitted — needs a committed lockfile (see finding below).
- [ ] `--cov` flag + coverage upload (deferred to Phase 5 with the threshold gate).
- [ ] Verify the workflow actually runs green on a PR (needs a push to GitHub).
- [ ] Branch protection → required checks (Phase 5).

**Parity job — folded, not separate (for now).** The Python title-norm parity
test runs inside the **python** job and the Go parity test inside the **go** job,
so drift already fails CI. A dedicated `parity` job adds little today because the
Go `NormalizeTitleKey` is still `t.Skip`-stubbed (§8). Revisit when §8 lands.
- [ ] **Facet-rule parity** (`facet_parser.py` vs `facet_service.go`): no shared
      fixture exists yet — add one, then assert both planes agree. Still open.

**Phase 2 finding — frontend lockfile (partially fixed).** `frontend/package-lock.json`
is gitignored and doesn't exist, so `npm ci` can't run in any git-based build. It
broke the Cloud Build image build (`COPY ... package-lock.json` → file not found).
**Applied:** both `ci.yml` and the **Dockerfile** now `COPY package.json` + `npm
install` (no lockfile needed). **Still open (Phase 5 reproducibility fix):** generate
+ commit a lockfile (un-ignore it) and switch both back to `npm ci`.

## Phase 3 — CD: build & deploy to Cloud Run

*Goal: automate the existing `deploy.sh`. Serving plane only — the ingest plane
runs on your local cron and is never shipped.*

Status: `[~]` authored & YAML-valid. **Decisions locked: D1 = auto-deploy on push
to `main`; D3 = Workload Identity Federation (keyless).** Unverifiable until a real
push to `main` — first deploy happens when this branch merges.

- [x] `.github/workflows/deploy.yml` — trigger `push: branches: [main]` (D1),
      `permissions: id-token: write` for WIF, `concurrency: deploy-main` so two
      deploys never overlap.
- [x] GCP auth via WIF (D3): `google-github-actions/auth@v2` reading repo
      *variables* `GCP_WIF_PROVIDER` / `GCP_DEPLOY_SA` — no key stored.
- [x] One-time GCP setup scripted in `scripts/setup-wif.sh` (idempotent): pool +
      provider pinned to `Tin-Ko/TechTrendTracker`, `github-deployer` SA with
      `run.admin` + `cloudbuild.builds.editor` + `artifactregistry.writer` +
      `iam.serviceAccountUser`, impersonation binding. **User has run it and set
      the two repo variables.**
- [x] Build + deploy handled by calling `./deploy.sh` (Cloud Build of the 4-stage
      image → `gcloud run deploy` → smoke test). Heavy cgo/ONNX build runs in
      Cloud Build, not the runner. `deploy.sh` is `100755` so `./deploy.sh` runs.
- [x] Smoke test is deploy.sh's built-in `GET /` gate (non-2xx fails the job).
- [x] DB URL stays in Secret Manager (`--set-secrets` in deploy.sh); never baked.
- [x] **Build/deploy mechanics verified via canary** (`SERVICE=ttt-backend-canary
      ./deploy.sh --no-smoke` in Cloud Shell): all 4 Docker stages built in Cloud
      Build (incl. the `-tags onnx` cgo build + the frontend `npm install` fix),
      deployed to a throwaway service, then deleted. Live `ttt-backend` untouched.
- [ ] **WIF/GitHub path verified on first push to `main`** (the merge). Watch:
      (a) the WIF token exchange in the `auth` step, (b) a possible one-time Cloud
      Build SA permission error.
- [ ] Hardening (optional): scope `iam.serviceAccountUser` to just the Cloud Run
      runtime SA instead of project-wide; consider `paths-ignore` for docs-only
      pushes so a README change doesn't trigger a full build+deploy.

## Phase 4 — Integration & golden-query gates (model machine)

*Goal: run the tests that genuinely need Ollama/ONNX/DB where those exist. These
do NOT run on the model-less laptop or on GitHub-hosted CI runners.*

Status: `[ ]` not started

- [ ] Decide the runner for model tests: **self-hosted GitHub runner on the
      model machine** vs a **manual/local `make integration` target**. (Sub-decision — flag when you get here.)
- [ ] Integration suite (`pytest -m integration`): real `Extractor` (Ollama),
      real `TitleEmbedder` (ONNX), real `SupabaseClient` against a test DB.
- [ ] Go ONNX-tagged tests (`go test -tags onnx ./...`): `embed_service` load +
      inference.
- [ ] **Embedding parity** (§3.4): assert the Python ONNX vector equals the Go
      hugot vector for the same input — the check that can't be faked.
- [ ] **Golden queries** post-deploy gate: `scripts/run_golden_queries.py`
      against the deployed service (or the test DB) using
      `tests/golden_queries.json`.

## Phase 5 — Hardening & nice-to-haves

Status: `[ ]` not started

- [ ] Branch protection on `main`: require `python`, `go`, `frontend`, `parity`.
- [ ] Coverage threshold gates (start low, ratchet up).
- [ ] `dependabot.yml` for pip / go / npm / actions.
- [ ] Frontend unit tests (Vitest) — currently only typecheck + build exist.
- [ ] Fix README drift noted in §11 (Chart.js listed but unused) while touching docs.
- [ ] Optional: `--min-instances=1` note for cold-start (leaves free tier — decide later).

---

## Out of scope (explicitly)

- Deploying the ingest plane. It stays local-cron per the two-plane design.
- Calibrating retrieval thresholds / building the §8 hierarchical search — that's
  product work, not pipeline work.
