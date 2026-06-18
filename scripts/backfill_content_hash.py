"""One-off backfill: populate content_hash on existing Supabase rows.

For each JSON file in $JOB_POSTINGS_DIR:
  1. Strong match (preferred): file has job_url → compute the same
     deterministic posting_id the processor would, UPDATE WHERE
     posting_id = X AND content_hash IS NULL.
  2. Weak match (fallback for early scrapes that have no job_url):
     UPDATE the first matching row by (company, job_title, posted_date)
     with content_hash IS NULL.
  3. Otherwise: log + skip.

If two files compute the same content_hash (true duplicate postings),
only the first UPDATE wins — the second raises UniqueViolation,
which we count and skip. The "loser" row stays NULL and can be
DELETEd later if desired.

Usage:
  source .env
  python -m scripts.backfill_content_hash             # all files
  python -m scripts.backfill_content_hash --dry-run   # show counts, no writes
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sys
import uuid
from collections import Counter
from typing import Optional

import psycopg
from psycopg import errors as pg_errors

from data_pipeline.scraper.url_utils import (
    content_hash_for,
    linkedin_posting_key,
)


JOB_POSTINGS_DIR = os.environ.get("JOB_POSTINGS_DIR", "/job_postings")


def _posting_id_from(job_url: Optional[str]) -> Optional[uuid.UUID]:
    if not job_url:
        return None
    key = linkedin_posting_key(job_url)
    if not key:
        return None
    return uuid.uuid5(uuid.NAMESPACE_URL, key)


def _parse_date(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dir", default=JOB_POSTINGS_DIR)
    args = parser.parse_args()

    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        print("SUPABASE_DB_URL not set", file=sys.stderr)
        return 2

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    print(f"scanning {len(files)} JSON files under {args.dir}")
    if args.dry_run:
        print("(dry-run; no writes)")

    stats = Counter()

    conn = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
    try:
        cur = conn.cursor()

        # Pre-flight: confirm the column exists, fail loud if migration
        # wasn't applied.
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='job_postings' AND column_name='content_hash'"
        )
        if not cur.fetchone():
            print("content_hash column missing — apply the migration first", file=sys.stderr)
            return 2

        for f in files:
            stats["files"] += 1
            try:
                data = json.load(open(f))
            except Exception as e:
                print(f"  skip (unreadable JSON): {f}: {e}", file=sys.stderr)
                stats["unreadable"] += 1
                continue

            title = data.get("job_title") or ""
            company = data.get("company")
            description = data.get("job_description") or ""
            job_url = data.get("job_url")
            posted_date = _parse_date(data.get("posted_date"))

            if not title and not description:
                stats["empty"] += 1
                continue

            ch = content_hash_for(company, title, description)
            pid = _posting_id_from(job_url)

            if args.dry_run:
                stats["strong_match_candidate" if pid else "weak_match_candidate"] += 1
                continue

            updated = 0
            try:
                if pid is not None:
                    cur.execute(
                        "UPDATE job_postings SET content_hash = %s "
                        "WHERE posting_id = %s AND content_hash IS NULL",
                        (str(ch), str(pid)),
                    )
                    updated = cur.rowcount
                    if updated:
                        stats["matched_strong"] += updated
                    else:
                        # Row missing or already has a hash. Fall through to
                        # weak match — covers the case where processor.py
                        # inserted via uuid4() (file lacks job_url at that
                        # time) and now an updated file has job_url.
                        pass

                if updated == 0:
                    cur.execute(
                        "UPDATE job_postings SET content_hash = %s "
                        "WHERE ctid = ("
                        "  SELECT ctid FROM job_postings "
                        "  WHERE company IS NOT DISTINCT FROM %s "
                        "    AND job_title = %s "
                        "    AND posted_date IS NOT DISTINCT FROM %s "
                        "    AND content_hash IS NULL "
                        "  LIMIT 1"
                        ")",
                        (str(ch), company, title, posted_date),
                    )
                    updated = cur.rowcount
                    if updated:
                        stats["matched_weak"] += updated
                    else:
                        stats["unmatched"] += 1
            except pg_errors.UniqueViolation:
                stats["collided"] += 1
            except Exception as e:
                print(f"  error on {f}: {e}", file=sys.stderr)
                stats["error"] += 1

        # Post-scan summary
        cur.execute("SELECT COUNT(*), COUNT(content_hash) FROM job_postings")
        total, filled = cur.fetchone()
        print()
        print("=== backfill summary ===")
        for k in (
            "files",
            "unreadable",
            "empty",
            "matched_strong",
            "matched_weak",
            "unmatched",
            "collided",
            "error",
            "strong_match_candidate",
            "weak_match_candidate",
        ):
            if stats.get(k):
                print(f"  {k:>26}  {stats[k]}")
        print(f"  {'rows in supabase':>26}  {total}")
        print(f"  {'rows with content_hash':>26}  {filled}")
        print(f"  {'rows still NULL':>26}  {total - filled}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
