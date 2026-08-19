---
name: design-ml
description: Phase 2 of the design workflow. Enumerate mid-level design decisions — API contracts, module interfaces, data flow, failure semantics — without answering them.
disable-model-invocation: true
argument-hint: [optional area to focus on]
---

# Phase 2 — Mid-level decisions

Focus: $ARGUMENTS

Read `docs/design/decisions.md` first. Every decision you list must be
consistent with the high-level answers already recorded there. Where a
high-level decision is still unanswered, say which mid-level decisions are
blocked on it rather than guessing.

## Your task

Enumerate the decisions that live between architecture and implementation. Cap
at 12.

Cover at least: module boundaries and dependency direction, the public API
contract (protocol, resource shape, verbs, pagination, idempotency), internal
interface seams and what gets injected vs constructed, the canonical data model
and where it is translated, error taxonomy and how failures propagate across
boundaries, retry/timeout/backpressure ownership, transaction and unit-of-work
boundaries, auth and authorization placement, configuration and secrets flow,
observability seams, and versioning/compatibility policy.

## Format

For each decision:

- **ML-n** — the decision as a single question
- **Constrained by** — which HL decisions bound it
- **Option space** — 2–4 named candidates, alphabetical, unevaluated

## Do not

- Answer any decision or signal a preference
- Analyse tradeoffs — that is phase 5
- Write interface signatures, schemas, or any code. Naming a decision about an
  interface is not the same as declaring the interface
- Continue into phase 3

## Output

Append to `docs/design/decisions.md` under `## Mid-level`. Print it too.

Then stop. Next step is `/decide` or `/design-ll`.
