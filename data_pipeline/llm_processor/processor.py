"""Ingest worker: consumes local posting paths from RabbitMQ, extracts
skills, embeds the title, parses facets, and inserts one row into Supabase.

This replaces the old HDFS -> Spark batch pipeline. Aggregation now lives in
the Go query path.
"""

from __future__ import annotations

import datetime
import os
import uuid
from typing import Dict, Optional

import pika

from constants.canonical_skill_map import canonical_skill_map
from constants.tech_capitalization import tech_capitalization_map
from data_pipeline.embeddings.embedder import TitleEmbedder
from data_pipeline.llm_processor.extractor import Extractor
from data_pipeline.llm_processor.facet_parser import parse as parse_facets
from data_pipeline.llm_processor.requirements_parser import RequirementsParser
from data_pipeline.scraper.url_utils import content_hash_for, linkedin_posting_key
from data_pipeline.storage.supabase_client import SupabaseClient
from storage.local.local_storage import LocalStorageClient


RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
JOB_POSTINGS_DIR = os.environ.get("JOB_POSTINGS_DIR", "/job_postings")
JOB_QUEUE = "job_queue"

# Gemma 4 served by a local Ollama daemon (design §4 ingest plane).
# Override with LLM_MODEL=<ollama-tag> if your install uses a different tag.
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma3:latest")


class Processor:
    def __init__(self, model: str, system_prompt: str) -> None:
        self.llm_extractor = Extractor(model=model, system_prompt=system_prompt)
        self.requirements_parser = RequirementsParser(
            canonical_skill_map=canonical_skill_map,
            tech_capitalization_map=tech_capitalization_map,
        )
        self.storage = LocalStorageClient(base_dir=JOB_POSTINGS_DIR)
        self.embedder = TitleEmbedder()
        self.db = SupabaseClient()

        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST)
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=JOB_QUEUE, durable=True)

    def process_job_description(self, job_description: str) -> Dict:
        extracted_data = self.llm_extractor.extract_skills_from_job(job_description)
        return self.requirements_parser.clean_extracted_data(extracted_data)

    def process_job(self, job_path: str) -> None:
        job_data = self.storage.read_json(job_path)

        job_title: str = job_data.get("job_title") or ""
        company = job_data.get("company")
        job_description: str = job_data.get("job_description") or ""
        job_url: Optional[str] = job_data.get("job_url")
        posted_date_str = job_data.get("posted_date")
        posted_date = (
            datetime.date.fromisoformat(posted_date_str) if posted_date_str else None
        )

        # Deterministic posting_id from URL (LinkedIn rotates tracking
        # query params on every search render). content_hash dedups
        # the same role re-posted under a new LinkedIn ID. Both keys
        # are checked atomically via bare ON CONFLICT DO NOTHING.
        canonical_key = linkedin_posting_key(job_url) if job_url else None
        posting_id = (
            uuid.uuid5(uuid.NAMESPACE_URL, canonical_key) if canonical_key else uuid.uuid4()
        )
        content_hash = content_hash_for(company, job_title, job_description)

        skills_payload = self.process_job_description(job_description)
        skills = skills_payload.get("skills", []) or []

        seniority, posting_year = parse_facets(job_title, posted_date)
        embedding = self.embedder.embed(job_title)

        pid, inserted = self.db.insert_posting(
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
        verb = "Inserted" if inserted else "Skipped (dup)"
        print(f"{verb} posting {pid} ({job_title}) with {len(skills)} skills")

    def consumer_callback(self, ch, method, properties, body) -> None:
        job_path = body.decode("utf-8")
        print(f"Received local path: {job_path}")
        try:
            self.process_job(job_path=job_path)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print(f"Failed to process {job_path}: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def consume_messages(self) -> None:
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=JOB_QUEUE, on_message_callback=self.consumer_callback
        )
        self.channel.start_consuming()


if __name__ == "__main__":
    with open("constants/system_prompt.txt", "r") as f:
        system_prompt = f.read()

    processor = Processor(model=LLM_MODEL, system_prompt=system_prompt)
    processor.consume_messages()
