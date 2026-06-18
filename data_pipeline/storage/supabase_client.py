"""Thin psycopg-based client that writes one row per scraped posting into
Supabase Postgres (`job_postings`). The aggregation tables from the legacy
pipeline are gone; this is the only write sink in the new design."""

from __future__ import annotations

import datetime
import os
import uuid
from contextlib import contextmanager
from typing import Iterable, Optional, Sequence

import psycopg


_INSERT_SQL = """
    INSERT INTO job_postings (
        posting_id, job_title, company, skills, seniority,
        posting_year, posted_date, title_embedding, content_hash
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT DO NOTHING
"""


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


class SupabaseClient:
    def __init__(self, dsn: Optional[str] = None) -> None:
        dsn = dsn or os.environ.get("SUPABASE_DB_URL")
        if not dsn:
            raise ValueError(
                "SUPABASE_DB_URL not set. Use the Supabase pooled connection "
                "string (port 6543, transaction mode) for serverless callers; "
                "the direct (5432) string is fine for the ingest worker."
            )
        self.dsn = dsn
        # autocommit=True so a failed insert doesn't poison the connection
        # for every subsequent message (transactions auto-abort on error
        # and need a ROLLBACK to recover).
        # prepare_threshold=None disables psycopg3's auto-prepared statements,
        # which conflict with Supabase's Supavisor transaction-mode pooler
        # (different backend connections per transaction; prepared statement
        # names like _pg3_0 collide with "already exists" errors).
        self.conn = psycopg.connect(dsn, autocommit=True, prepare_threshold=None)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def cursor(self):
        with self.conn.cursor() as cur:
            yield cur

    def insert_posting(
        self,
        *,
        job_title: str,
        company: Optional[str],
        skills: Iterable[str],
        seniority: Optional[str],
        posting_year: Optional[int],
        posted_date: Optional[datetime.date],
        title_embedding: Sequence[float],
        posting_id: Optional[uuid.UUID] = None,
        content_hash: Optional[uuid.UUID] = None,
    ) -> tuple[uuid.UUID, bool]:
        """Returns (posting_id, inserted). `inserted` is False if either the
        posting_id PK or the content_hash unique index swallowed the row."""
        pid = posting_id or uuid.uuid4()
        with self.cursor() as cur:
            cur.execute(
                _INSERT_SQL,
                (
                    str(pid),
                    job_title,
                    company,
                    list(skills),
                    seniority,
                    posting_year,
                    posted_date,
                    _vector_literal(title_embedding),
                    str(content_hash) if content_hash else None,
                ),
            )
            inserted = cur.rowcount > 0
        # autocommit=True means each execute is its own transaction;
        # no explicit commit() needed.
        return pid, inserted
