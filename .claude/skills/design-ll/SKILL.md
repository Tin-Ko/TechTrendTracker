---
name: design-ll
description: Phase 3 of the design workflow. Enumerate low-level design decisions — data structures, algorithms, complexity, concurrency — without answering them.
disable-model-invocation: true
argument-hint: [optional component to focus on]
---

# Phase 3 — Low-level decisions

Focus: $ARGUMENTS

Read `docs/design/decisions.md` first. Scope every decision to the components
and interfaces already established. Skip anything whose answer is fully
determined by an earlier decision — say so once instead of listing it.

## Your task

Enumerate the implementation-level decisions with real consequences. Cap at 12.
Exclude decisions where the options are functionally equivalent at this
project's scale; those are noise.

Cover at least: the core data structures and why the access pattern demands
them, the hot-path algorithms and their target complexity, indexing and query
shape, in-memory vs on-disk representation, serialization format, caching layer
and invalidation trigger, concurrency primitives and what they protect,
allocation and copy behaviour on the hot path, batching and buffering
thresholds, and the specific edge cases that will need explicit handling.

## Format

For each decision:

- **LL-n** — the decision as a single question
- **Access pattern** — the read/write shape that makes this decision matter
- **Option space** — 2–4 named candidates, alphabetical, with their asymptotic
  complexity stated as fact where relevant, but with no recommendation

Stating that a hash map is O(1) average lookup is a fact and is allowed.
Stating that a hash map is therefore the right choice here is a recommendation
and is not.

## Do not

- Answer any decision or signal a preference
- Analyse tradeoffs — that is phase 5
- Write any code, including type declarations
- Continue into phase 4

## Output

Append to `docs/design/decisions.md` under `## Low-level`. Print it too.

Then stop. Next step is `/decide`.
