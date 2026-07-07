package services

import (
	"testing"
)

// normFixture mirrors one entry of constants/title_norm_fixtures.json —
// the SAME file the Python suite asserts. If either plane drifts, one of
// the two suites fails. This is the parity lock (design §10.1), same
// discipline as the embedding parity requirement.
type normFixture struct {
	Raw  string `json:"raw"`
	Key  string `json:"key"`
	Note string `json:"_note"`
}

func TestNormalizeTitleKeyParity(t *testing.T) {
	t.Skip("TODO: delete this Skip once NormalizeTitleKey is implemented")

	// TODO 1. What to do:
	//    Load ../../constants/title_norm_fixtures.json, unmarshal into
	//    []normFixture, and assert NormalizeTitleKey(f.Raw) == f.Key for
	//    every single entry — no skips, no subsetting.
	//
	// TODO 2. Recommended approach:
	//    - os.ReadFile + encoding/json Unmarshal.
	//    - Run each fixture as a subtest:
	//        t.Run(f.Raw, func(t *testing.T) { ... })
	//      so `go test -run TestNormalizeTitleKeyParity` reports every
	//      failing case at once instead of stopping at the first.
	//    - On mismatch, include f.Note in the failure message — the notes
	//      were written to explain exactly which rule the case exercises.
	//
	// TODO 3. Implementation details:
	//    - Path: go test runs with the package dir (backend/services) as
	//      cwd, so the relative path is "../../constants/...". If that
	//      feels brittle, runtime.Caller(0) gives you this file's path to
	//      anchor against.
	//    - Two fixtures document ASSUMPTIONS ("Software Engineer II",
	//      "C# Developer") — read their _note fields BEFORE implementing;
	//      they require decisions in the shared regexes, and the Python
	//      side must make the identical decision (see the TODO in
	//      tests/llm_processor/test_title_normalizer.py).
}
