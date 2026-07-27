"""Unit tests for the Option-C seam, data_pipeline.llm_processor.pipeline.

These run with NO Ollama, ONNX, RabbitMQ, or DB — the whole point of the refactor.
Collaborators are fakes; expected facet/hash/id values are computed from the same
pure helpers build_posting uses, so these assert the *orchestration*, not the
helpers' internals (which have their own tests)."""

import datetime
import unittest
import uuid

from data_pipeline.llm_processor import facet_parser
from data_pipeline.llm_processor.pipeline import Posting, build_posting
from data_pipeline.scraper.url_utils import content_hash_for, linkedin_posting_key


class FakeExtractor:
    """Records the description it was handed and returns a canned skill dict."""

    def __init__(self, skills):
        self._skills = skills
        self.seen_description = None

    def extract_skills_from_job(self, description):
        self.seen_description = description
        return {"skills": self._skills}


class FakeNormalizer:
    """Echoes the skills back sorted — stands in for RequirementsParser without
    depending on its (separately tested) normalization logic."""

    def clean_extracted_data(self, data):
        return {"skills": sorted(data.get("skills", []))}


class FakeEmbedder:
    def __init__(self, vector):
        self._vector = vector
        self.seen_text = None

    def embed(self, text):
        self.seen_text = text
        return self._vector


def make_job_data(**overrides):
    data = {
        "job_title": "Senior Backend Engineer",
        "company": "Acme",
        "job_description": "We need Python and Go.",
        "job_url": "https://www.linkedin.com/jobs/view/senior-backend-engineer-4317707969?refId=x",
        "posted_date": "2026-01-15",
    }
    data.update(overrides)
    return data


class TestBuildPosting(unittest.TestCase):
    def _build(self, job_data, *, skills=("python", "go"), vector=(0.1, 0.2, 0.3)):
        self.extractor = FakeExtractor(list(skills))
        self.embedder = FakeEmbedder(list(vector))
        return build_posting(
            job_data,
            extractor=self.extractor,
            normalizer=FakeNormalizer(),
            embedder=self.embedder,
        )

    def test_returns_posting_with_mapped_scalar_fields(self):
        posting = self._build(make_job_data())
        self.assertIsInstance(posting, Posting)
        self.assertEqual(posting.job_title, "Senior Backend Engineer")
        self.assertEqual(posting.company, "Acme")
        self.assertEqual(posting.posted_date, datetime.date(2026, 1, 15))

    def test_skills_come_from_normalizer_output(self):
        posting = self._build(make_job_data(), skills=["go", "python"])
        self.assertEqual(posting.skills, ["go", "python"])  # FakeNormalizer sorts

    def test_wires_description_to_extractor_and_title_to_embedder(self):
        job_data = make_job_data()
        posting = self._build(job_data, vector=[0.9, 0.8])
        self.assertEqual(self.extractor.seen_description, "We need Python and Go.")
        self.assertEqual(self.embedder.seen_text, "Senior Backend Engineer")
        self.assertEqual(posting.title_embedding, [0.9, 0.8])

    def test_facets_match_the_pure_parser(self):
        job_data = make_job_data()
        posting = self._build(job_data)
        expected_seniority, expected_year = facet_parser.parse(
            job_data["job_title"], datetime.date(2026, 1, 15)
        )
        self.assertEqual(posting.seniority, expected_seniority)
        self.assertEqual(posting.posting_year, expected_year)

    def test_posting_id_is_deterministic_from_linkedin_id(self):
        job_data = make_job_data()
        expected = uuid.uuid5(uuid.NAMESPACE_URL, linkedin_posting_key(job_data["job_url"]))
        self.assertEqual(self._build(job_data).posting_id, expected)
        # Same posting seen twice -> same id (idempotent ingest).
        self.assertEqual(self._build(job_data).posting_id, self._build(job_data).posting_id)

    def test_posting_id_is_random_when_no_url(self):
        p1 = self._build(make_job_data(job_url=None))
        p2 = self._build(make_job_data(job_url=None))
        self.assertEqual(p1.posting_id.version, 4)
        self.assertNotEqual(p1.posting_id, p2.posting_id)

    def test_content_hash_matches_helper(self):
        job_data = make_job_data()
        expected = content_hash_for(
            job_data["company"], job_data["job_title"], job_data["job_description"]
        )
        self.assertEqual(self._build(job_data).content_hash, expected)

    def test_missing_skills_key_yields_empty_list(self):
        posting = self._build(make_job_data(), skills=[])
        self.assertEqual(posting.skills, [])

    def test_missing_optional_fields_default_safely(self):
        posting = self._build({"job_title": "", "job_description": ""})
        self.assertEqual(posting.job_title, "")
        self.assertIsNone(posting.company)
        self.assertIsNone(posting.posted_date)


if __name__ == "__main__":
    unittest.main()
