"""Weekly-ish taxonomy hygiene job (design §8).

An LLM building a taxonomy incrementally makes LOCALLY sensible decisions
that drift GLOBALLY: near-duplicate canonicals ("back end engineer" vs
"backend engineer"), synonym specs ("be" vs "backend"), orphan families with
3 postings. This job is the immune system.

Default mode prints proposals only; --apply / --apply-folds execute.

Usage:
  source .env
  python -m data_pipeline.taxonomy.reconcile                # dry-run (default)
  python -m data_pipeline.taxonomy.reconcile --apply        # execute merges
  python -m data_pipeline.taxonomy.reconcile --apply-folds  # execute folds too
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from typing import Optional

from data_pipeline.embeddings.embedder import TitleEmbedder
from data_pipeline.storage.supabase_client import SupabaseClient


SNAPSHOT_DIR = "taxonomy_snapshots"

# Merge-proposal thresholds (design §8). Tune on real proposals: run dry, eyeball.
COS_THRESHOLD = 0.92
TRGM_THRESHOLD = 0.6
FAMILY_FOLD_MIN_COUNT = 15


def embed_all_canonicals(conn) -> dict[str, list[float]]:
    """Embed every placed canonical title. Design §8."""
    # TODO 1. What to do:
    #    SELECT DISTINCT canonical_title FROM title_map
    #    WHERE role_family IS NOT NULL;
    #    then embed each string and return {canonical_title: vector}.
    #
    # TODO 2. Recommended approach:
    #    Reuse TitleEmbedder — specifically embed_batch(list_of_titles),
    #    which is one ONNX call for the whole set instead of N calls. The
    #    set is small (hundreds), so brute force is fine.
    #
    # TODO 3. Implementation details:
    #    - Keep the titles in a list first, embed_batch it, then zip back
    #      into a dict — preserves the title→vector pairing trivially.
    #    - TitleEmbedder needs ONNX_MODEL_DIR set (same env as the worker).
    raise NotImplementedError


def propose_canonical_merges(
    conn,
    vecs: dict[str, list[float]],
    cos_threshold: float = COS_THRESHOLD,
    trgm_threshold: float = TRGM_THRESHOLD,
) -> list[tuple]:
    """Find near-duplicate canonicals. Returns proposals, never applies. §8."""
    # TODO 1. What to do:
    #    For every PAIR of canonical titles, propose a merge when
    #    cosine >= cos_threshold OR trigram >= trgm_threshold. The two
    #    signals catch different failure classes: cosine finds semantic
    #    twins ("qa engineer" / "test engineer"), trigram finds spelling
    #    variants ("back end engineer" / "backend engineer").
    #    Output rows: (keep, merge_from, cos, trgm, count_keep, count_merge),
    #    sorted by confidence (e.g. max(cos, trgm) descending).
    #
    # TODO 2. Recommended approach:
    #    - Cosine: the vectors are already L2-normalized (embedder does
    #      that), so cosine = plain dot product. numpy: stack the vectors
    #      into a matrix M and compute M @ M.T once — N² on hundreds is
    #      trivial. itertools.combinations over the upper triangle.
    #    - Trigram: don't reimplement pg_trgm in Python. One SQL round-trip
    #      computes all pairs:
    #        SELECT a.canonical_title, b.canonical_title,
    #               similarity(a.canonical_title, b.canonical_title)
    #        FROM (SELECT DISTINCT canonical_title FROM title_map
    #              WHERE role_family IS NOT NULL) a
    #        JOIN (...) b ON a.canonical_title < b.canonical_title;
    #      ('<' dedupes the pair ordering.) Load into a dict keyed on the
    #      sorted pair, then combine with the cosine matrix in Python.
    #    - Posting counts for the keep-side heuristic: one GROUP BY over
    #      job_postings (or query the taxonomy_tree view).
    #
    # TODO 3. Implementation details:
    #    - Keep-side heuristic: higher posting count wins; tie → shorter
    #      string wins (design §8).
    #    - NEVER auto-merge canonicals in DIFFERENT families — flag those
    #      pairs separately for a human; they usually indicate a
    #      family-assignment bug, not a duplicate. You need each canonical's
    #      family: pull it from title_map alongside the DISTINCT select.
    #    - Return plain tuples (or a small dataclass) — main() decides
    #      whether to print or apply.
    raise NotImplementedError


def apply_merge(conn, keep: str, merge_from: str) -> None:
    """Fold one canonical into another, in both tables, atomically. §8."""
    # TODO 1. What to do:
    #    In ONE transaction:
    #      UPDATE title_map SET canonical_title = %(keep)s, source = 'merge'
    #      WHERE canonical_title = %(merge)s;
    #      UPDATE job_postings SET canonical_title = %(keep)s
    #      WHERE canonical_title = %(merge)s;
    #    Log before/after row counts to stdout (the run log is the audit
    #    trail).
    #
    # TODO 2. Recommended approach:
    #    The shared SupabaseClient connection is autocommit=True, which
    #    defeats "one transaction" — open an explicit block:
    #        with conn.transaction():   # psycopg3 nested-transaction helper
    #            ...both updates...
    #    That guarantees the two tables can't diverge if the second UPDATE
    #    fails (§5.1 called out this denormalization cost explicitly).
    #
    # TODO 3. Implementation details:
    #    - source='merge' on the title_map rows records WHY this decision
    #      row no longer matches what the LLM originally said.
    #    - cur.rowcount after each UPDATE gives you the counts to log.
    raise NotImplementedError


def propose_family_folds(conn, min_count: int = FAMILY_FOLD_MIN_COUNT) -> list[tuple]:
    """Propose folding tiny families into their nearest big neighbor. §8."""
    # TODO 1. What to do:
    #    Find families with fewer than min_count postings and, for each,
    #    propose the nearest existing family by embedding similarity.
    #    Print for human confirmation; --apply-folds executes. Also print,
    #    where it reads sensibly, the suggestion to demote the old family
    #    name to a spec (e.g. family "backend engineer" folds into
    #    "software engineer" WITH spec "backend" added) — human decides.
    #
    # TODO 2. Recommended approach:
    #    - Small families: GROUP BY role_family over job_postings, HAVING
    #      COUNT(*) < min_count (don't trust role_families.posting_count
    #      until refresh_family_counts has run at least once).
    #    - Nearest family: embed all family names with TitleEmbedder,
    #      cosine against the big families only — reuse the dot-product
    #      trick from propose_canonical_merges.
    #
    # TODO 3. Implementation details:
    #    - Applying a fold means: UPDATE title_map and job_postings rows
    #      whose role_family = small_family to the target family (same
    #      two-table transaction discipline as apply_merge), then DELETE
    #      the row from role_families.
    #    - v1 can leave the actual apply function unwritten until the first
    #      real fold shows up in dry-run output — proposals alone are useful.
    raise NotImplementedError


def review_pending_specs(conn, promote: Optional[list[str]] = None,
                         reject: Optional[list[str]] = None,
                         merge: Optional[dict[str, str]] = None) -> None:
    """List pending specs with usage counts; optionally act on them. §8."""
    # TODO 1. What to do:
    #    Default: print every spec_vocabulary row WHERE status='pending'
    #    with how many postings actually use it. Optionally act:
    #      - promote: status -> 'active'
    #      - reject:  status -> 'rejected' AND remove it from every
    #        specializations array (both tables)
    #      - merge {'be': 'backend'}: array_replace it in both tables, then
    #        mark the synonym 'rejected'
    #
    # TODO 2. Recommended approach:
    #    - Usage counts in one query:
    #        SELECT s.spec, COUNT(p.posting_id)
    #        FROM spec_vocabulary s
    #        LEFT JOIN job_postings p ON s.spec = ANY(p.specializations)
    #        WHERE s.status = 'pending' GROUP BY s.spec ORDER BY 2 DESC;
    #    - Merge/remove on arrays:
    #        array_replace(specializations, %(old)s, %(new)s)   -- merge
    #        array_remove(specializations, %(spec)s)            -- reject
    #      applied to BOTH title_map and job_postings (same transaction
    #      discipline as apply_merge).
    #    - Drive actions from flags (--promote-spec X, repeatable) rather
    #      than interactive input() — flag-driven runs are loggable and
    #      scriptable; the design allows either.
    #
    # TODO 3. Implementation details:
    #    - Edge case in merge: if a posting already has BOTH 'be' and
    #      'backend', array_replace leaves a duplicate entry. Chase it with
    #      a dedupe UPDATE (e.g. rebuild via SELECT ARRAY(SELECT DISTINCT
    #      unnest(...))) or accept rare duplicates — containment (@>)
    #      semantics don't break either way; document your choice.
    raise NotImplementedError


def refresh_family_counts(conn) -> None:
    """Recompute role_families.posting_count from job_postings. Run LAST. §8."""
    # TODO 1. What to do:
    #    One UPDATE-from-aggregate so the registry ordering (and the prompt
    #    ordering derived from it) reflects reality after merges/folds.
    #
    # TODO 2. Recommended approach:
    #    UPDATE role_families rf
    #    SET posting_count = COALESCE(agg.n, 0)
    #    FROM (SELECT role_family, COUNT(*) AS n FROM job_postings
    #          WHERE role_family IS NOT NULL GROUP BY role_family) agg
    #    WHERE ... -- careful: a plain FROM-join UPDATE skips families with
    #    zero postings entirely. Either run a second UPDATE setting 0 where
    #    NOT EXISTS, or use a LEFT-JOIN-shaped subquery keyed on rf.family.
    #
    # TODO 3. Implementation details:
    #    - Runs LAST in main() by design: counts must reflect the merges and
    #      folds this run just applied.
    raise NotImplementedError


def export_taxonomy_snapshot(conn, out_path: Optional[str] = None) -> str:
    """Dump the taxonomy_tree view as an indented markdown tree. §8."""
    # TODO 1. What to do:
    #    Read the taxonomy_tree view (already ordered family, count DESC)
    #    and write taxonomy_snapshots/tree_YYYY-MM-DD.md shaped like:
    #        ## software engineer (1234)
    #        - backend engineer {backend} (410)
    #        - frontend engineer {frontend} (300)
    #    Return the path written.
    #
    # TODO 2. Recommended approach:
    #    - itertools.groupby over the rows keyed on role_family (they arrive
    #      pre-sorted by the view's ORDER BY — groupby depends on that).
    #    - datetime.date.today().isoformat() for the filename;
    #      os.makedirs(SNAPSHOT_DIR, exist_ok=True) before writing.
    #
    # TODO 3. Implementation details:
    #    - Family total = sum of its rows' posting_count.
    #    - Snapshots are line-diff-friendly on purpose: `git diff` between
    #      two snapshot files is the taxonomy-drift review tool (and, per
    #      the design, potential product content).
    raise NotImplementedError


def main() -> int:
    # TODO 1. What to do:
    #    argparse: --apply, --apply-folds, plus any spec-review action flags
    #    you chose above. Then run in the §8 order:
    #      merges -> folds -> pending specs -> refresh counts -> snapshot.
    #    Without --apply: print proposals for everything, apply nothing
    #    (except the snapshot, which is read-only and always safe to write).
    #
    # TODO 2. Recommended approach:
    #    Same skeleton as scripts/backfill_title_map.py main(): env check,
    #    connect via SupabaseClient, try/finally close, int exit codes.
    #
    # TODO 3. Implementation details:
    #    - Print proposals in a stable, copy-pasteable format — the manual
    #      workflow is: run dry, read, rerun with --apply.
    #    - refresh_family_counts and the snapshot should run even when no
    #      merges were applied; they're cheap and keep state fresh.
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
