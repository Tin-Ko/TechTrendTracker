---
name: decide
description: Phase 4 of the design workflow. Record the user's own answers to enumerated design decisions verbatim, with no evaluation or commentary.
disable-model-invocation: true
argument-hint: [HL-1: my answer. HL-2: my answer. ...]
---

# Phase 4 — Record my answers

My answers: $ARGUMENTS

## Your task

You are a scribe here, nothing else. Record what I decided.

For each decision ID I answered, write my answer into
`docs/design/decisions.md` under that decision, as an **Answer:** line. Preserve
my wording. If my answer is ambiguous about something that matters, record it as
written and flag the ambiguity separately — do not resolve it for me.

Then report, in at most five lines: which IDs are now answered, which remain
open, and any answer that is inconsistent with another answer I gave. Naming a
direct contradiction between two of my own answers is in scope. Anything else
is not.

## Do not

- Evaluate, validate, improve, or "clean up" any answer
- Say whether an answer is good, reasonable, standard, or a solid choice
- Add caveats, risks, or considerations
- Answer an open decision yourself, or suggest what I might answer
- Continue into tradeoffs — that is phase 5, and I will ask for it

## Output

Then stop. Next step is `/decide` again for the remaining IDs, or `/tradeoffs`
once enough are answered.
