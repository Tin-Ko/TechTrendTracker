"""One-off, resumable backfill: map every historical posting's title through
the SAME normalizer the ingest worker uses (design §7).

Key cost property: the LLM runs once per DISTINCT raw title, not per posting.
Check `SELECT COUNT(DISTINCT job_title) FROM job_postings;` before starting —
at ~1-2 s per local Gemma call, a few thousand distinct titles is one
unattended evening. Memoization in title_map makes re-runs nearly free.

Idempotent by construction: decisions are memoized in title_map, and row
updates are guarded by `WHERE canonical_title IS NULL`. Ctrl-C and rerun
freely. Process the most frequent titles first so an interrupted run has
already covered the bulk of rows.

Usage (conventions of backfill_content_hash.py):
  source .env
  python -m scripts.backfill_title_map --dry-run --limit 50   # smoke run
  python -m scripts.backfill_title_map                        # full run
  python -m scripts.backfill_title_map --min-count 2          # skip singletons
  python -m scripts.backfill_title_map --report               # coverage only
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Iterator, Optional

from data_pipeline.llm_processor.title_normalizer import TitleNormalizer
from data_pipeline.storage.supabase_client import SupabaseClient


@dataclass
class BackfillStats:
    """Tallies printed at exit (design §7: 'Tally: titles processed / LLM
    calls / cache hits / rows updated / abstentions')."""

    titles_processed: int = 0
    llm_calls: int = 0
    cache_hits: int = 0
    rows_updated: int = 0
    abstentions: int = 0
    errors: int = 0

    # TODO 1. What to do:
    #    Add a summary() method (or __str__) that renders the fields as an
    #    aligned block, like the `=== backfill summary ===` block at the end
    #    of scripts/backfill_content_hash.py — steal that formatting.
    # TODO 2. Recommended approach:
    #    Iterate dataclasses.fields(self) so adding a counter later never
    #    requires touching the printer.
    # TODO 3. Implementation details:
    #    - llm_calls vs cache_hits: the orchestrator doesn't report which
    #      path it took. Cheapest honest signal: count title_map rows before
    #      and after the run (rows gained == LLM calls that got memoized);
    #      or add a simple `self.llm_call_count` counter attribute to
    #      TitleNormalizer that its LLM branch increments, and read it here.
    #      The counter is the better learning exercise and the better metric.


def iter_distinct_raw_titles(
    conn, min_count: int = 1, only_unmapped: bool = True
) -> Iterator[tuple[str, int]]:
    """Yield (raw_title, posting_count), most frequent first. Design §7."""
    # TODO 1. What to do:
    #    Query the distinct raw titles that still need mapping, with their
    #    posting counts, ordered by count descending, and yield them one by
    #    one as (raw_title, count) tuples.
    #
    # TODO 2. Recommended approach:
    #    SELECT job_title, COUNT(*) AS n
    #    FROM job_postings
    #    [WHERE canonical_title IS NULL]          -- only when only_unmapped
    #    GROUP BY job_title
    #    HAVING COUNT(*) >= %s                    -- min_count
    #    ORDER BY n DESC;
    #    Build the WHERE clause conditionally on only_unmapped; bind
    #    min_count as a parameter (never format it into the SQL string).
    #
    # TODO 3. Implementation details:
    #    - min_count implements the --min-count flag: skip singleton weirdo
    #      titles on the first pass; sweep the long tail in a second pass.
    #    - A generator (yield) keeps memory flat and makes --limit trivial
    #      to implement in the caller with itertools.islice.
    #    - The result set is small (distinct titles), so a plain fetchall +
    #      yield-from is also fine; the generator signature is the contract.
    raise NotImplementedError


def apply_decision_to_postings(conn, raw_title: str, decision) -> int:
    """Stamp one decision onto every not-yet-mapped row with this exact raw
    title. Returns number of rows updated. Design §7."""
    # TODO 1. What to do:
    #    UPDATE job_postings
    #    SET canonical_title = %s, role_family = %s, specializations = %s
    #    WHERE job_title = %s AND canonical_title IS NULL;
    #    and return cur.rowcount.
    #
    # TODO 2. Recommended approach:
    #    Match on the EXACT raw string. We iterate distinct raw titles, so
    #    every variant spelling gets its own UPDATE — deliberately avoiding
    #    any SQL-side normalization, which would otherwise have to mirror
    #    normalize_title_key() in SQL (a parity trap, §7).
    #
    # TODO 3. Implementation details:
    #    - decision.to_db() gives you the three SET values in order; note it
    #      already list-ifies the specs tuple for psycopg.
    #    - The `canonical_title IS NULL` guard is the resumability mechanism:
    #      rerunning after Ctrl-C touches zero already-mapped rows.
    #    - Abstentions still write: canonical_title = key, role_family = NULL.
    #      That's correct — it marks the row as PROCESSED (the NULL guard
    #      skips it next run) while role_family stays NULL so the §9.2
    #      recall-patch arm can still reach it.
    raise NotImplementedError


def run_backfill(args: argparse.Namespace) -> BackfillStats:
    """Main loop: distinct titles -> shared orchestrator -> row updates."""
    # TODO 1. What to do:
    #    For each (raw_title, count) from iter_distinct_raw_titles:
    #      1. decision = normalizer.get_or_create_title_decision(
    #             raw_title, source="backfill")
    #         — the *same* orchestrator as ingest; zero duplicated logic.
    #      2. Unless --dry-run: apply_decision_to_postings(...) and add its
    #         rowcount to the stats.
    #      3. Update stats (abstention when not decision.is_placed).
    #    Return the filled BackfillStats.
    #
    # TODO 2. Recommended approach:
    #    - Build one SupabaseClient() and one TitleNormalizer(db=...,
    #      model=args.model) up front; pass client.conn into the iterator
    #      and updater.
    #    - --dry-run: resolve + print each decision, skip the UPDATE. Note
    #      the orchestrator still memoizes into title_map on a dry run —
    #      that is fine and useful (decisions are the expensive part, and
    #      they're identical either way). Mention this in the printout so
    #      it doesn't surprise you.
    #    - --limit N: itertools.islice(iter_distinct_raw_titles(...), N).
    #
    # TODO 3. Implementation details:
    #    - Progress line every 25 titles, format from the design doc:
    #        [143/1988] "sr. backend developer" -> software engineer/{backend} (37 rows)
    #      Getting the total for [i/total] needs a COUNT query first, or
    #      just materialize the iterator into a list (it's small) and len() it.
    #    - Wrap the per-title body in try/except: one poisoned title should
    #      count as an error and continue, not kill an unattended evening run.
    #    - Flush stdout on progress lines (print(..., flush=True)) so
    #      `| tee backfill.log` shows live progress.
    raise NotImplementedError


def print_coverage_report(conn) -> None:
    """Post-run (or standalone --report) coverage summary. Design §7."""
    # TODO 1. What to do:
    #    Print three sections:
    #      a. Overall coverage: % of postings WHERE role_family IS NOT NULL
    #         (plus raw counts).
    #      b. Per-family posting counts, descending — sanity-check the tree
    #         shape (one family hogging 90% means the prompt policy is off).
    #      c. Top-20 unmapped titles by frequency — this list IS the manual
    #         review worklist.
    #
    # TODO 2. Recommended approach:
    #    Three small queries:
    #      a. SELECT COUNT(*), COUNT(role_family) FROM job_postings;
    #         (COUNT(col) skips NULLs — that asymmetry does the work.)
    #      b. SELECT role_family, COUNT(*) FROM job_postings
    #         WHERE role_family IS NOT NULL GROUP BY 1 ORDER BY 2 DESC;
    #      c. SELECT job_title, COUNT(*) FROM job_postings
    #         WHERE role_family IS NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
    #
    # TODO 3. Implementation details:
    #    - Section (c) includes deliberate abstentions AND never-processed
    #      rows. Distinguish them if you like by also selecting whether
    #      canonical_title IS NULL (never processed) vs NOT NULL (abstained).
    #    - Keep it read-only; this function is also the --report entry point.
    raise NotImplementedError


def ensure_schema_ready(conn) -> bool:
    """Fail fast (§7): probe for the migration before any LLM call."""
    # TODO 1. What to do:
    #    Return True only if BOTH the title_map table and the three new
    #    job_postings columns exist.
    #
    # TODO 2. Recommended approach:
    #    Mirror the pre-flight in backfill_content_hash.py: query
    #    information_schema.columns for table_name='job_postings' AND
    #    column_name='canonical_title', and information_schema.tables for
    #    'title_map'. Print a "run the schema migration first" message to
    #    stderr on failure.
    #
    # TODO 3. Implementation details:
    #    - Probe BEFORE constructing the TitleNormalizer — the whole point
    #      is to fail before the first (expensive) LLM call.
    raise NotImplementedError


def main() -> int:
    # TODO 1. What to do:
    #    argparse with: --dry-run (flag), --limit N (int), --min-count N
    #    (int, default 1), --report (flag: print coverage and exit), --model
    #    (str, default from LLM_MODEL env like the processor). Then:
    #    check SUPABASE_DB_URL is set -> connect -> ensure_schema_ready ->
    #    either print_coverage_report (--report) or run_backfill + print
    #    stats + print_coverage_report.
    #
    # TODO 2. Recommended approach:
    #    Copy the shape of scripts/backfill_content_hash.py main(): return
    #    int exit codes (0 ok, 2 config/schema error), print to stderr for
    #    errors, wrap the connection in try/finally close.
    #
    # TODO 3. Implementation details:
    #    - Exit code 2 for "SUPABASE_DB_URL not set" and for a failed schema
    #      probe, matching the sibling script's convention.
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
