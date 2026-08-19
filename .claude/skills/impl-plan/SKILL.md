---
name: impl-plan
description: Phase 6 of the design workflow. Produce a sequenced implementation plan based on the user's recorded design decisions.
disable-model-invocation: true
argument-hint: [optional constraints, e.g. time budget]
---

# Phase 6 — Implementation plan

Constraints: $ARGUMENTS

Read `docs/design/decisions.md`. Build the plan from **my** answers, including
the ones you argued against in phase 5. If a milestone only makes sense under a
different answer than the one I gave, say so in one line and then plan for my
answer anyway.

## Your task

Produce an ordered sequence of milestones. Cap at 10. Order by
de-risking value, not by architectural layer: the milestone that could
invalidate the most downstream work goes first, even if it means building the
messy middle before the clean edges.

For each milestone:

- **M-n** — name and one-line goal
- **Demonstrable** — what I can run or observe at the end that proves it works.
  If a milestone has no observable outcome, it is not a milestone; fold it into
  a neighbour
- **Depends on** — earlier milestones, stated by ID
- **Decisions exercised** — which HL/ML/LL decisions this milestone puts to the
  test
- **Risk** — what most likely goes wrong here, and the cheapest way to find out
  early
- **Rough size** — hours or days, your honest estimate

Then: name the one milestone where I am most likely to discover a design
decision was wrong, and what the signal will look like.

## Do not

- Write code, signatures, file paths, or function names — that is phase 7
- Include "write tests" or "add logging" as standalone milestones; fold them
  into the milestone whose behaviour they verify
- Pad the plan with setup steps I obviously know how to do

## Output

Write to `docs/design/plan.md`. Print the milestone list in the response.

Then stop. Next step is `/scaffold-map`.
