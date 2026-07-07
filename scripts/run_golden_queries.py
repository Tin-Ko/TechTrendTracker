"""Golden-query runner (design §10.2): executes tests/golden_queries.json
against a live /skills endpoint and prints a pass/fail table.

This is a behavioral gate, not a unit test — it needs the Go backend running
against a dev DB that has been backfilled. Run it:
  - before/after flipping SEARCH_MODE (§11 phase 5), and
  - after ANY prompt_version bump.

Usage:
  python -m scripts.run_golden_queries                         # localhost:8080
  python -m scripts.run_golden_queries --base-url http://...   # staging
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

GOLDEN_PATH = "tests/golden_queries.json"


def load_cases(path: str = GOLDEN_PATH) -> list[dict]:
    """Load the golden set, dropping the _readme entry."""
    # TODO 1. What to do:
    #    json.load the file and return only entries that have a "query" key.
    # TODO 2. Recommended approach:
    #    One list comprehension; the _readme element is just documentation.
    # TODO 3. Implementation details:
    #    - Fail loudly (let the exception propagate) if the file is missing
    #      or malformed — a broken golden set must never "pass".
    raise NotImplementedError


def fetch_skills(base_url: str, query: str) -> dict:
    """GET /skills?job_title=<query> and return the parsed JSON body."""
    # TODO 1. What to do:
    #    Build the URL with urllib.parse.urlencode({"job_title": query}),
    #    fetch with urllib.request.urlopen, json-decode the response.
    # TODO 2. Recommended approach:
    #    Stdlib urllib keeps this dependency-free (mirrors the repo's
    #    lean-scripts convention). A short timeout (10 s) so a hung backend
    #    fails the run instead of wedging it.
    # TODO 3. Implementation details:
    #    - The fields you assert on: RelatedTitles (list of canonical names
    #      once §9.2 lands) and Resolved {CanonicalTitle, RoleFamily,
    #      Specializations, MatchMode}.
    raise NotImplementedError


def evaluate_case(case: dict, base_url: str) -> tuple[bool, str]:
    """Run one golden case. Returns (passed, human-readable detail)."""
    # TODO 1. What to do:
    #    Dispatch on which expectation keys the case carries:
    #      - expect_includes:   every title appears in RelatedTitles
    #      - expect_excludes:   none of these titles appears
    #      - expect_resolves_to: Resolved.CanonicalTitle equals it
    #      - expect_seniority:  the case's facet was applied (simplest
    #        check: Resolved is present and the result set differs from the
    #        unfaceted query — or expose the facet in Resolved and assert
    #        directly; your choice, document it)
    #      - expect_same_results_as: fetch BOTH queries and assert their
    #        RelatedTitles sets (and JobCounts) are equal
    #
    # TODO 2. Recommended approach:
    #    Compare lowercased sets — canonicals are lowercase in the DB but
    #    may be title-cased for display by the handler (§9.3).
    #
    # TODO 3. Implementation details:
    #    - A case may combine keys (e.g. resolves_to + seniority): evaluate
    #      ALL present expectations and AND the results; report every
    #      failed sub-expectation in the detail string.
    #    - Catch per-case network/JSON errors and return them as failures
    #      with detail — one bad case must not abort the table.
    raise NotImplementedError


def main() -> int:
    # TODO 1. What to do:
    #    argparse (--base-url, default http://localhost:8080), load cases,
    #    evaluate each, print an aligned PASS/FAIL table with details on
    #    failures, and return 0 iff everything passed (nonzero exit makes
    #    this usable as a CI-ish gate later).
    # TODO 2. Recommended approach:
    #    print(f"{status:4}  {case['query']!r:40}  {detail}") per row, then
    #    a summary line "N/M passed".
    # TODO 3. Implementation details:
    #    - Print the MatchMode observed per query in the table — watching
    #      structured vs fallback per case is the fastest way to spot a
    #      resolution bug vs a retrieval bug.
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
