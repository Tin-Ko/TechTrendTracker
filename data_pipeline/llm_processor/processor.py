"""Ingest worker: consumes local posting paths from RabbitMQ and writes one row
per posting into Supabase.

The per-posting *transform* now lives in `pipeline.build_posting` (the Option-C
seam) so it can be unit-tested with fakes. This module is the thin worker around
it: it wires the real collaborators, owns the RabbitMQ loop, and persists the row
`build_posting` returns. Construction does NO I/O — call `connect()` before
consuming.
"""

from __future__ import annotations

import os
from dataclasses import asdict

import pika

from constants.canonical_skill_map import canonical_skill_map
from constants.tech_capitalization import tech_capitalization_map
from data_pipeline.embeddings.embedder import TitleEmbedder
from data_pipeline.llm_processor.extractor import Extractor
from data_pipeline.llm_processor.pipeline import (
    Embedder,
    SkillExtractor,
    SkillNormalizer,
    build_posting,
)
from data_pipeline.llm_processor.requirements_parser import RequirementsParser
from data_pipeline.storage.supabase_client import SupabaseClient
from storage.local.local_storage import LocalStorageClient


RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
JOB_POSTINGS_DIR = os.environ.get("JOB_POSTINGS_DIR", "/job_postings")
JOB_QUEUE = "job_queue"

# Gemma 4 served by a local Ollama daemon (design §4 ingest plane).
# Override with LLM_MODEL=<ollama-tag> if your install uses a different tag.
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma4:latest")


class Processor:
    def __init__(
        self,
        *,
        extractor: SkillExtractor,
        normalizer: SkillNormalizer,
        embedder: Embedder,
        storage,
        db,
        rabbitmq_host: str = RABBITMQ_HOST,
        job_queue: str = JOB_QUEUE,
    ) -> None:
        # Collaborators are injected, not constructed here — see build_default()
        # for production wiring. No connection is opened at construction time.
        self.extractor = extractor
        self.normalizer = normalizer
        self.embedder = embedder
        self.storage = storage
        self.db = db
        self.rabbitmq_host = rabbitmq_host
        self.job_queue = job_queue
        self.connection = None
        self.channel = None

    @classmethod
    def build_default(cls) -> "Processor":
        """Wire the real collaborators from env/config. This is the composition
        root; everything that touches Ollama/ONNX/DB is constructed here and only
        here, so tests never reach it."""
        with open("constants/system_prompt.txt", "r") as f:
            system_prompt = f.read()
        return cls(
            extractor=Extractor(model=LLM_MODEL, system_prompt=system_prompt),
            normalizer=RequirementsParser(
                canonical_skill_map=canonical_skill_map,
                tech_capitalization_map=tech_capitalization_map,
            ),
            embedder=TitleEmbedder(),
            storage=LocalStorageClient(base_dir=JOB_POSTINGS_DIR),
            db=SupabaseClient(),
        )

    def connect(self) -> None:
        """Open the RabbitMQ connection and declare the durable job queue. Kept
        out of __init__ so the worker can be constructed without a live broker —
        I/O in a constructor is what made the old version untestable."""
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=self.rabbitmq_host)
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.job_queue, durable=True)

    def process_job(self, job_path: str) -> None:
        job_data = self.storage.read_json(job_path)

        # TODO(hierarchical search §6.4): resolve the title decision here and
        # pass canonical_title/role_family/specializations into build_posting.
        # get_or_create_title_decision never raises by contract (abstains on
        # failure), so the posting still inserts unmapped.
        posting = build_posting(
            job_data,
            extractor=self.extractor,
            normalizer=self.normalizer,
            embedder=self.embedder,
        )

        pid, inserted = self.db.insert_posting(**asdict(posting))
        verb = "Inserted" if inserted else "Skipped (dup)"
        print(f"{verb} posting {pid} ({posting.job_title}) with {len(posting.skills)} skills")

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
        if self.channel is None:
            self.connect()
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=self.job_queue, on_message_callback=self.consumer_callback
        )
        self.channel.start_consuming()


if __name__ == "__main__":
    processor = Processor.build_default()
    processor.connect()
    processor.consume_messages()
