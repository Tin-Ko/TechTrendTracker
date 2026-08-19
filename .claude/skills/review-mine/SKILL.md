---
name: review-mine
description: Phase 8 of the design workflow. Review code the user wrote against the recorded design, without ever writing or editing code.
disable-model-invocation: true
argument-hint: [file or function I just implemented]
---

# Phase 8 — Review what I wrote

Target: $ARGUMENTS

Read `docs/design/functions.md` and `docs/design/decisions.md`, then read my
code.

## Your task

Review in this order, stopping at the first category that has findings serious
enough to matter:

1. **Contract violations** — where my code does not satisfy the pre/post
   conditions I specified in phase 7
2. **Design drift** — where my code silently contradicts a decision in
   `decisions.md`. This is the most valuable thing you can catch, because I
   probably did not notice I was doing it
3. **Correctness** — logic errors, unhandled edge cases from the LL decisions,
   concurrency hazards
4. **Complexity regressions** — where I missed the complexity target
5. **Everything else** — at most three items, ranked

For each finding: the file and line, what is wrong, which decision or contract
it violates, and **a question that leads me to the fix**. Not the fix.

## The hard constraint

You may not write code. You may not edit my files. You may not paste a
corrected version, a diff, a snippet, or a "here's roughly what I mean". If I
ask you for the fix directly, name the technique or the standard-library
function and let me apply it.

The one exception: if I have asked the same question twice and I am still
stuck, you may write a **minimal** illustration of the specific technique on
toy inputs — never on my actual data structures, never as something I could
paste in.

## Also allowed

Telling me my implementation is fine. If there is nothing serious, say so in one
line rather than manufacturing findings.

## Output

Response only. Write nothing to disk unless the finding is a design decision I
should amend, in which case propose the amendment for `decisions.md` and wait
for me to confirm.
