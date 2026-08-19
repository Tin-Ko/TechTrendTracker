---
name: design-hl
description: Phase 1 of the design workflow. Enumerate the high-level architecture and system design decisions that must be made, without answering any of them.
disable-model-invocation: true
argument-hint: [what we are building]
---

# Phase 1 — High-level decisions

Subject: $ARGUMENTS

If the repository already contains code, read enough of it to ground the list in
what exists. Otherwise work from the description above and ask at most one
clarifying question before producing the list.

## Your task

Enumerate the architectural decisions this project forces. Not the ones a
textbook would list — the ones *this* system actually forces given its
constraints.

Cap the list at 8. If you have more candidates, cut the ones whose answer is
already determined by something else on the list. Ranking by cost-of-being-wrong
is how you decide what survives the cut.

Cover at least: system decomposition and component boundaries, where state
lives, process and deployment topology, synchronous vs event-driven
communication, consistency and durability requirements, failure domains and
blast radius, the build/buy/adopt calls, and the primary scaling axis.

## Format

For each decision:

- **HL-n** — the decision as a single question
- **Forces it** — what breaks or becomes unanswerable until this is settled
- **Downstream** — which later decisions this constrains
- **Option space** — 2–4 named candidate approaches, listed alphabetically, with
  no evaluation, no recommendation, and no ordering by preference

## Do not

- Answer any decision, or hint at which option you would pick
- Analyse tradeoffs — that is phase 5
- Produce any code, schema, or interface
- Continue into phase 2

## Output

Write the list to `docs/design/decisions.md` under a `## High-level` heading,
creating the file if needed. Print it in the response too.

Then stop. Tell the user the next step is to answer these with `/decide`, or to
enumerate mid-level decisions with `/design-ml`.
