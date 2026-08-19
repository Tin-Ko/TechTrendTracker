---
name: scaffold-map
description: Phase 7 of the design workflow. Map the file structure and every function that must be implemented, as signatures and contracts only, with no bodies.
disable-model-invocation: true
argument-hint: [optional: milestone ID to scope to]
---

# Phase 7 — Structure and function map

Scope: $ARGUMENTS

Read `docs/design/decisions.md` and `docs/design/plan.md`. If a milestone ID was
given, map only that milestone's surface. Otherwise map the whole project.

## Part 1 — File tree

Show the directory layout as a plain tree. Annotate each directory with its
single responsibility in under ten words. Mark which module may import which,
and call out any import direction that would be a violation.

## Part 2 — Function map

For every function, method, and type I need to write:

- **Signature** — name, parameter types, return type, in the target language
- **Purpose** — one line
- **Preconditions** — what must hold on entry
- **Postconditions** — what holds on return, including what is mutated
- **Raises / returns error when** — the failure cases, named
- **Complexity target** — where it is on a hot path
- **Milestone** — which M-n this belongs to

Group by file. Order within a file by call depth: entry points first.

## The hard constraint

Signatures only. Every body is empty — `pass`, `...`, `panic("todo")`, or the
language's equivalent — and nothing else. No loop bodies, no branches, no
computed expressions, no example calls, no "for reference" snippets, no
commented-out logic, no regex literals, no SQL strings.

Type declarations, struct and interface definitions, enum variants, and constant
*names* are allowed, since they are contract rather than implementation. A
constant's value is implementation unless it is a protocol constant I have no
freedom over.

If a function's contract is hard to state without showing the algorithm,
describe the algorithm in prose in the Purpose field. That is the correct move,
not a code sketch.

## Output

Write the tree and map to `docs/design/functions.md`.

Do **not** create any source files. Do not create empty stub files for me to
fill in — I will create them myself as I go, and creating them for me removes
the part of this I am trying to learn.

Then stop. Next step is that I implement, then run `/review-mine`.
