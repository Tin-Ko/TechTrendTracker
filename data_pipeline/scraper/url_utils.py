"""URL and content dedup helpers.

Two kinds of dedup keys live here:

- `linkedin_posting_key`: stable URL key (numeric LinkedIn job ID)
  → drives `posting_id = uuid5(NAMESPACE_URL, key)`.
- `content_dedup_key`: deterministic content key over
  (company, job_title, job_description) → drives `content_hash`.

Both feed `ON CONFLICT DO NOTHING` in the supabase_client.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional
from urllib.parse import urlparse


_LINKEDIN_JOB_ID_RE = re.compile(r"/jobs/view/[^/?#]+-(\d+)")
_WS_RE = re.compile(r"\s+")


def linkedin_posting_key(url: str) -> str:
    """Return a stable dedup key for a LinkedIn posting URL.

    `https://www.linkedin.com/jobs/view/software-engineer-...-4317707969?refId=...`
    → `"linkedin:4317707969"`

    URLs that don't match the expected shape fall through to the raw URL
    so the caller still gets *some* key (and ON CONFLICT still works
    self-consistently for that URL).
    """
    if not url:
        return url
    match = _LINKEDIN_JOB_ID_RE.search(urlparse(url).path)
    if match:
        return f"linkedin:{match.group(1)}"
    return url


def _norm(s: Optional[str]) -> str:
    """Lowercase + collapse whitespace; empty string for None."""
    if not s:
        return ""
    return _WS_RE.sub(" ", s.strip().lower())


def content_dedup_key(
    company: Optional[str],
    job_title: Optional[str],
    job_description: Optional[str],
) -> str:
    """Canonical string used to derive the content_hash UUID.

    Normalization (lowercase + collapse whitespace) keeps trivial
    formatting differences from defeating the dedup. The `|`
    separator can't appear in normalized output (it's not whitespace)
    so we don't need to escape.
    """
    return "|".join([_norm(company), _norm(job_title), _norm(job_description)])


def content_hash_for(
    company: Optional[str],
    job_title: Optional[str],
    job_description: Optional[str],
) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, content_dedup_key(company, job_title, job_description))
