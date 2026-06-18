"""Link harvester: walks LinkedIn job search result pages and publishes each
posting URL to RabbitMQ `urls_queue`. The content worker
(`data_pipeline/scraper/content_worker.py`) consumes from that queue.

Cron-driven, one-shot — exits when the Scrapy crawl finishes.
"""

import os

import pika
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
URLS_QUEUE = "urls_queue"


class LinkedInJobSpider(scrapy.Spider):
    name = "linkedin_jobs"

    custom_settings = {
        "DOWNLOAD_DELAY": 4,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 4,
        "AUTOTHROTTLE_MAX_DELAY": 8,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    start_url = "https://www.linkedin.com/jobs/search/?"
    f_E = ["1", "2", "3", "4"]
    f_TPR = "r604800"
    geoID = "102095887"
    keywords = [
        "Data%20Scientist",
    ]
    origin = "JOB_SEARCH_PAGE_SEARCH_BUTTON"
    start_urls = []
    for experience in f_E:
        for keyword in keywords:
            start_urls.append(
                start_url
                + "f_E=" + experience
                + "&f_TPR=" + f_TPR
                + "&geoID=" + geoID
                + "&keywords=" + keyword
                + "&origin=" + origin
                + "&refresh=true"
            )

    def __init__(self) -> None:
        super().__init__()
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST)
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=URLS_QUEUE, durable=True)
        self.published = 0

    def parse(self, response):
        job_links = response.css(
            'ul.jobs-search__results-list a.base-card__full-link::attr(href)'
        ).getall()
        for link in job_links:
            url = link.strip()
            if not url:
                continue
            self.channel.basic_publish(
                exchange="",
                routing_key=URLS_QUEUE,
                body=url,
                properties=pika.BasicProperties(delivery_mode=2),
            )
            self.published += 1
        self.logger.info(
            "published %d urls (cumulative %d) from %s",
            len(job_links), self.published, response.url,
        )

    def closed(self, reason):
        self.logger.info("spider closed (%s); total published: %d", reason, self.published)
        try:
            self.connection.close()
        except Exception:
            pass


if __name__ == "__main__":
    process = CrawlerProcess(get_project_settings())
    process.crawl(LinkedInJobSpider)
    process.start()
