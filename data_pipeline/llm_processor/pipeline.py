"""Pure per-posting transform: raw scraped JSON -> one `job_postings` row.

This is the Option-C seam pulled out of `processor.py`. `build_posting` does
NO I/O of its own: it takes its model-bearing collaborators as arguments and
returns a plain `Posting` value. Persistence (`db.insert_posting`) stays in the
worker (`processor.py`), not here — the worker BUILDS the row with this function,
then WRITES it. That split is what lets this be unit-tested with fakes and no
Ollama/ONNX/DB/RabbitMQ anywhere in sight.

The collaborators are typed as Protocols on purpose: this module must not import
`Extractor`/`TitleEmbedder` (they pull in `ollama`/`onnxruntime`), or it would
re-couple the pure transform to the heavy deps it was extracted to escape.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Sequence

from data_pipeline.llm_processor import facet_parser
from data_pipeline.scraper.url_utils import content_hash_for, linkedin_posting_key


class SkillExtractor(Protocol):
    def extract_skills_from_job(self, description: str) -> dict: ...


class SkillNormalizer(Protocol):
    def clean_extracted_data(self, data: dict) -> dict: ...


class Embedder(Protocol):
    def embed(self, text: str) -> Sequence[float]: ...


@dataclass
class Posting:
    """One row of `job_postings`. Field names match `SupabaseClient.insert_posting`'s
    keyword params exactly, so the worker can do `db.insert_posting(**asdict(posting))`."""

    posting_id: uuid.UUID
    job_title: str
    company: Optional[str]
    skills: list[str]
    seniority: Optional[str]
    posting_year: Optional[int]
    posted_date: Optional[datetime.date]
    title_embedding: Sequence[float]
    content_hash: Optional[uuid.UUID]


def build_posting(
    job_data: dict[str, Any],
    *,
    extractor: SkillExtractor,
    normalizer: SkillNormalizer,
    embedder: Embedder,
) -> Posting:
    """Transform one scraped posting dict into a `Posting` row. Pure given its
    injected collaborators — same ordering as the old `Processor.process_job`."""
    job_title: str = job_data.get("job_title") or ""
    company = job_data.get("company")
    job_description: str = job_data.get("job_description") or ""
    job_url: Optional[str] = job_data.get("job_url")
    posted_date_str = job_data.get("posted_date")
    posted_date = (
        datetime.date.fromisoformat(posted_date_str) if posted_date_str else None
    )

    # Deterministic posting_id from the stable LinkedIn job ID (tracking query
    # params rotate per render); fall back to a random UUID when there's no URL.
    # content_hash catches the same role re-posted under a new LinkedIn ID.
    canonical_key = linkedin_posting_key(job_url) if job_url else None
    posting_id = (
        uuid.uuid5(uuid.NAMESPACE_URL, canonical_key) if canonical_key else uuid.uuid4()
    )
    content_hash = content_hash_for(company, job_title, job_description)

    raw_skills = extractor.extract_skills_from_job(job_description)
    cleaned = normalizer.clean_extracted_data(raw_skills)
    skills = cleaned.get("skills", []) or []

    # Facets are parsed from the RAW title on purpose (seniority/year live there);
    # keep this before any future title-normalization step (§8).
    seniority, posting_year = facet_parser.parse(job_title, posted_date)
    embedding = embedder.embed(job_title)

    return Posting(
        posting_id=posting_id,
        job_title=job_title,
        company=company,
        skills=skills,
        seniority=seniority,
        posting_year=posting_year,
        posted_date=posted_date,
        title_embedding=embedding,
        content_hash=content_hash,
    )
