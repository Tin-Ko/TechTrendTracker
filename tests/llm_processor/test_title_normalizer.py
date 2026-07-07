"""Unit tests for title_normalizer (design §10.1).

Two halves:
  1. Parity fixtures: normalize_title_key over
     constants/title_norm_fixtures.json — the SAME file the Go suite
     (backend/services/title_service_test.go) asserts. If either plane
     drifts, one of the two suites goes red. That is the parity lock.
  2. validate_decision with canned LLM outputs — no Ollama, no DB (fake the
     conn), pure logic tests.

Run: python -m unittest tests.llm_processor.test_title_normalizer
"""

from __future__ import annotations

import json
import os
import unittest

from data_pipeline.llm_processor.title_normalizer import (
    TitleDecision,
    TitleLLMError,
    normalize_title_key,
    validate_decision,
)

FIXTURES_PATH = os.path.join("constants", "title_norm_fixtures.json")


class TestNormalizeTitleKeyParity(unittest.TestCase):
    def test_all_fixtures(self) -> None:
        self.skipTest("TODO: remove once you've reviewed the fixture ASSUMPTION notes")
        # TODO 1. What to do:
        #    Load FIXTURES_PATH, and for EVERY entry assert
        #    normalize_title_key(entry["raw"]) == entry["key"]. No skips,
        #    no subsetting — the whole file is the contract.
        #
        # TODO 2. Recommended approach:
        #    for case in json.load(open(FIXTURES_PATH)):
        #        with self.subTest(raw=case["raw"], note=case.get("_note")):
        #            ...
        #    subTest reports every failing fixture in one run instead of
        #    stopping at the first — the Go side uses t.Run for the same
        #    reason.
        #
        # TODO 3. Implementation details — three fixtures WILL fail against
        #    the current implementation until you make a decision (their
        #    _note fields explain; decide, then fix code or fixture, and
        #    mirror the decision in Go):
        #    - "Software Engineer II": expects roman-numeral level suffixes
        #      stripped, but facet_parser's seniority regexes don't cover
        #      I/II/III yet. Either extend _SENIORITY_PATTERNS (careful:
        #      that also changes seniority facet parsing — probably
        #      desirable, "SWE II" ≈ mid-level, but it's a product call) or
        #      add a level-suffix strip step to normalize_title_key only.
        #    - "Software Engineer, Backend (Remote) - 2026 Start": expects
        #      the dangling " - " dropped. Your `(^| )-+( |$)` rule handles
        #      exactly this — verify with this fixture.
        #    - "C# Developer": expects '#' kept. Your step-6 class already
        #      includes '#' — this fixture pins that decision so nobody
        #      "simplifies" it away later.


class TestValidateDecision(unittest.TestCase):
    """Canned-LLM-output cases from §10.1: valid, extra keys, unknown
    family, unknown spec, garbage, >4 specs."""

    # TODO 1. What to do:
    #    One test method per case below. Each builds a raw_out dict, calls
    #    validate_decision(raw_out, families, active_specs, conn) and
    #    asserts on the returned TitleDecision (or the raised TitleLLMError).
    #
    # TODO 2. Recommended approach:
    #    validate_decision takes a conn only to pass through to
    #    register_new_family/register_new_spec. Don't stand up Postgres for
    #    a unit test — replace those with unittest.mock.patch:
    #        @patch("data_pipeline.llm_processor.title_normalizer.register_new_spec")
    #    Then the mock ALSO lets you assert "was the unknown spec registered
    #    as pending?" — which is half the point of these tests.
    #
    # TODO 3. Implementation details:
    #    - Shared inputs for all cases:
    #        families = ["software engineer", "data scientist"]
    #        active_specs = ["backend", "frontend"]

    def test_valid_output_passes_through(self) -> None:
        self.skipTest("TODO")
        # {"canonical_title": "backend engineer", "role_family":
        #  "software engineer", "specializations": ["backend"]}
        # → decision matches verbatim; no register_* calls made.

    def test_head_noun_rewrite(self) -> None:
        self.skipTest("TODO")
        # canonical_title "backend developer" → decision.canonical_title
        # must come back "backend engineer" (HEAD_NOUN_MAP). This is the
        # equivalence mechanism for goal §1.1(2) — worth its own test.

    def test_extra_key_rejected(self) -> None:
        self.skipTest("TODO")
        # Valid payload PLUS {"confidence": 0.9} → TitleLLMError (or your
        # chosen abstention behavior — assert whichever you implemented).

    def test_unknown_family_registered_and_accepted(self) -> None:
        self.skipTest("TODO")
        # role_family "platform engineer" (not in families) → decision KEEPS
        # it, and register_new_family mock was called once with it.

    def test_unknown_spec_registered_pending_and_kept(self) -> None:
        self.skipTest("TODO")
        # specializations ["backend", "fintech"] → decision keeps BOTH
        # (data first, curation later), register_new_spec called with
        # ("fintech", status="pending").

    def test_garbage_rejected(self) -> None:
        self.skipTest("TODO")
        # {"skills": ["python"]} (wrong schema entirely) → TitleLLMError.

    def test_too_many_specs_becomes_abstention(self) -> None:
        self.skipTest("TODO")
        # 5 specs → sanity cap: role_family None on the result (abstention),
        # NOT an exception — better unmapped than polluted (§6.2).


if __name__ == "__main__":
    unittest.main()
