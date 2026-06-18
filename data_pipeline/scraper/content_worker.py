"""Content worker: consumes LinkedIn posting URLs from `urls_queue`,
fetches each posting page, writes a JSON file to disk, and publishes the
file path to `job_queue` for the downstream LLM extraction worker.

Replaces the old Scrapy `linkedin_scraper.py` so the link-harvest and
content-scrape stages can run async.
"""

from __future__ import annotations

import datetime
import json
import os
import random
import re
import time
import uuid

import pika
import requests
from lxml import html

from storage.local.local_storage import LocalStorageClient


RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
JOB_POSTINGS_DIR = os.environ.get("JOB_POSTINGS_DIR", "/job_postings")
URLS_QUEUE = "urls_queue"
JOB_QUEUE = "job_queue"

MIN_DELAY = float(os.environ.get("CONTENT_WORKER_MIN_DELAY", "4"))
MAX_DELAY = float(os.environ.get("CONTENT_WORKER_MAX_DELAY", "8"))
REQUEST_TIMEOUT = float(os.environ.get("CONTENT_WORKER_TIMEOUT", "20"))

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _slug(value: str, fallback: str = "untitled") -> str:
    if not value:
        return fallback
    s = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return s or fallback


class PermanentError(Exception):
    """Errors the worker should not requeue (404, parse failure, etc.)."""


class ContentWorker:
    def __init__(self) -> None:
        self.storage = LocalStorageClient(base_dir=JOB_POSTINGS_DIR)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, heartbeat=600)
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=URLS_QUEUE, durable=True)
        self.channel.queue_declare(queue=JOB_QUEUE, durable=True)

    def _fetch(self, url: str) -> str:
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            raise RuntimeError(f"network error: {e}") from e

        if resp.status_code in (404, 410):
            raise PermanentError(f"HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp.text

    def _parse(self, body: str) -> dict:
        tree = html.fromstring(body)

        job_title = tree.xpath(
            'string(//h1[contains(@class, "top-card-layout__title")]/text())'
        ).strip()
        company = tree.xpath(
            'string(//a[contains(@class, "topcard__org-name-link")]/text())'
        ).strip()
        text_parts = tree.xpath(
            '//div[contains(@class, "show-more-less-html__markup")]'
            '/descendant-or-self::*/text()'
        )
        description = " ".join(t.strip() for t in text_parts if t.strip())

        if not job_title or not description:
            raise PermanentError("missing title or description")

        return {
            "job_title": job_title,
            "company": company or None,
            "job_description": description,
        }

    def process_url(self, url: str) -> None:
        body = self._fetch(url)
        parsed = self._parse(body)

        today = datetime.date.today()
        payload = {
            **parsed,
            "job_url": url,
            "posted_date": today.isoformat(),
        }

        filename = (
            f"{_slug(parsed['job_title'])}_{_slug(parsed.get('company') or '')}_"
            f"{today.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}.json"
        )
        local_path = self.storage.write(filename, payload, overwrite=True)

        self.channel.basic_publish(
            exchange="",
            routing_key=JOB_QUEUE,
            body=local_path,
            properties=pika.BasicProperties(delivery_mode=2),
        )
        print(f"scraped {url} -> {local_path}")

    def consumer_callback(self, ch, method, properties, body) -> None:
        url = body.decode("utf-8").strip()
        print(f"received url: {url}")
        try:
            self.process_url(url)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except PermanentError as e:
            print(f"dropping {url}: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            print(f"failed {url} (requeueing): {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        finally:
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            time.sleep(delay)

    def consume(self) -> None:
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=URLS_QUEUE, on_message_callback=self.consumer_callback
        )
        print(f"content_worker waiting on {URLS_QUEUE}")
        self.channel.start_consuming()


if __name__ == "__main__":
    ContentWorker().consume()
