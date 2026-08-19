---
name: tradeoffs
description: Phase 5 of the design workflow. Analyse the tradeoffs of the design decisions the user has already made, including where they are likely wrong.
disable-model-invocation: true
argument-hint: [optional: specific decision IDs to analyse]
---

# Phase 5 — Tradeoff analysis

Scope: $ARGUMENTS

Read `docs/design/decisions.md`. Analyse only decisions I have answered. This is
the phase where you finally get to have opinions — use it.

## Your task

For each decision in scope:

- **Buys** — the property this answer actually secures, stated concretely
- **Costs** — what it makes permanently harder, including operational and
  cognitive cost, not just performance
- **Forecloses** — what becomes impractical to add later
- **Breaks when** — the specific condition under which this answer becomes the
  wrong one: a load level, a data shape, a team size, a failure mode. Name a
  threshold, not a vague "at scale"
- **Strongest counter** — the best case for the alternative I rejected, argued
  properly rather than strawmanned
- **Cost to reverse** — cheap / moderate / expensive, with the reason

Then, across all decisions in scope:

- Which combinations interact badly, and how
- The single decision most likely to be wrong, said plainly. If you think I got
  something wrong, say so directly and name the failure mode. Do not hedge it
  into invisibility. Then leave the call with me
- Which decisions are cheap to reverse and therefore not worth more debate now

## Do not

- Write code, schemas, interfaces, or benchmarks
- Revise `docs/design/decisions.md`. My answers stand unless I change them
- Silently substitute a better answer into later phases

## Output

Write to `docs/design/tradeoffs.md`. Print the cross-cutting section in the
response; the per-decision detail can stay in the file.

Then stop. Next step is `/decide` to revise anything, or `/impl-plan`.
